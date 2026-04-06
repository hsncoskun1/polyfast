"""PTB fetcher — orchestrates PTB acquisition with retry schedule and lock.

PTB retry schedule (bağlayıcı):
  2s → 4s → 8s → 16s → 10s → 10s → 10s → ... (event sonuna kadar her 10s)

Lock davranışı:
- PTB bir kez başarıyla alındığında kilitlenir
- Kilitlendikten sonra retry tamamen durur
- Same-event overwrite YOK
- Yeni event instance başladığında yeni PTB süreci başlar

Stop condition: PTB acquired (lock) VEYA event expired

Does NOT:
- Evaluate trading rules (→ strategy engine)
- Produce UI state (→ frontend)
- Manage positions or orders (→ execution)
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

from backend.ptb.models import PTBRecord, PTBStatus
from backend.ptb.source_adapter import PTBSourceAdapter
from backend.domain.startup_guard import HealthIncident, HealthSeverity
from backend.logging_config.service import get_logger, log_event

logger = get_logger("ptb.fetcher")

# Default retry — schema'dan override edilebilir (MarketDataConfig)
DEFAULT_PTB_RETRY_SCHEDULE = [2, 4, 8, 16]
DEFAULT_PTB_RETRY_STEADY = 10


class PTBFetcher:
    """Orchestrates PTB fetch, lock, and retry lifecycle."""

    def __init__(
        self,
        source: PTBSourceAdapter,
        retry_schedule: list[int] | None = None,
        retry_steady_seconds: int = DEFAULT_PTB_RETRY_STEADY,
    ):
        self._source = source
        self._records: dict[str, PTBRecord] = {}
        self._retry_schedule = retry_schedule or list(DEFAULT_PTB_RETRY_SCHEDULE)
        self._retry_steady = retry_steady_seconds

    def get_or_create_record(self, condition_id: str, asset: str) -> PTBRecord:
        """Get existing PTB record or create new WAITING record."""
        if condition_id not in self._records:
            self._records[condition_id] = PTBRecord(
                condition_id=condition_id,
                asset=asset,
            )
        return self._records[condition_id]

    async def fetch_ptb(
        self, condition_id: str, asset: str, event_slug: str
    ) -> PTBRecord:
        """Single fetch attempt. Respects lock — won't refetch if locked.

        For scheduled retry use fetch_ptb_with_retry().

        Returns:
            PTBRecord with current state.
        """
        record = self.get_or_create_record(condition_id, asset)

        # Already locked — return immediately (same-event overwrite YOK)
        if record.is_locked:
            return record

        # Attempt fetch
        record.record_retry()
        result = await self._source.fetch_ptb(asset, event_slug)

        if result.success and result.value is not None:
            record.lock(result.value, result.source_name)
            log_event(
                logger, logging.INFO,
                f"PTB locked: {asset} = ${result.value:,.2f} (source: {result.source_name})",
                entity_type="ptb",
                entity_id=condition_id,
                payload={"ptb_value": result.value, "source": result.source_name},
            )
        else:
            record.record_failure(result.error)
            log_event(
                logger, logging.WARNING,
                f"PTB fetch failed for {asset}: {result.error}",
                entity_type="ptb",
                entity_id=condition_id,
                payload={"retry_count": record.retry_count, "error": result.error},
            )

        return record

    async def fetch_ptb_with_retry(
        self,
        condition_id: str,
        asset: str,
        event_slug: str,
        event_end_ts: float,
    ) -> PTBRecord:
        """Fetch PTB with full retry schedule until acquired or event expired.

        Retry schedule: 2s → 4s → 8s → 16s → 10s → 10s → ...
        Stops when: PTB acquired (lock) OR event_end_ts reached.

        Args:
            condition_id: Event condition ID.
            asset: Crypto asset symbol.
            event_slug: Event slug for source lookup.
            event_end_ts: Unix timestamp when event expires.

        Returns:
            PTBRecord — locked if successful, FAILED if event expired.
        """
        record = self.get_or_create_record(condition_id, asset)

        # Already locked
        if record.is_locked:
            return record

        attempt = 0
        while time.time() < event_end_ts:
            # Determine wait time from schedule
            if attempt < len(self._retry_schedule):
                wait = self._retry_schedule[attempt]
            else:
                wait = self._retry_steady

            # Wait
            await asyncio.sleep(wait)

            # Check if event expired during wait
            if time.time() >= event_end_ts:
                break

            # Attempt fetch
            await self.fetch_ptb(condition_id, asset, event_slug)

            # Check if locked
            if record.is_locked:
                return record

            attempt += 1

        # Event expired without PTB
        if not record.is_locked:
            record.record_failure("Event expired before PTB acquired")
            log_event(
                logger, logging.WARNING,
                f"PTB not acquired before event end: {asset} ({condition_id})",
                entity_type="ptb",
                entity_id=condition_id,
            )

        return record

    def get_record(self, condition_id: str) -> PTBRecord | None:
        """Get PTB record by condition ID."""
        return self._records.get(condition_id)

    def get_all_records(self) -> dict[str, PTBRecord]:
        """Get all PTB records."""
        return dict(self._records)

    def clear_event(self, condition_id: str) -> None:
        """Clear PTB record for an event (event ended, cleanup).

        Yeni event instance başladığında yeni PTB süreci başlar.
        """
        if condition_id in self._records:
            del self._records[condition_id]
            log_event(
                logger, logging.DEBUG,
                f"PTB record cleared for {condition_id}",
                entity_type="ptb",
                entity_id=condition_id,
            )

    def get_health_incidents(self) -> list[HealthIncident]:
        """Get health incidents for failed PTB fetches."""
        incidents = []
        for record in self._records.values():
            if record.is_failed:
                incidents.append(HealthIncident(
                    severity=HealthSeverity.WARNING,
                    category="ptb",
                    message=f"PTB fetch failed for {record.asset}: {record.last_error}",
                    suggested_action="Check Polymarket event page availability.",
                ))
        return incidents

    @property
    def pending_count(self) -> int:
        return sum(1 for r in self._records.values() if r.is_waiting)

    @property
    def locked_count(self) -> int:
        return sum(1 for r in self._records.values() if r.is_locked)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self._records.values() if r.is_failed)

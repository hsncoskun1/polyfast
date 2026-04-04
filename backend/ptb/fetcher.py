"""PTB fetcher — orchestrates PTB acquisition with retry and lock semantics.

Responsibilities:
- Fetch PTB via source adapter
- Lock PTB after first successful acquisition (no overwrite)
- Retry only when PTB not yet acquired
- Surface failure/waiting state for downstream consumers
- Log all attempts

Does NOT:
- Evaluate trading rules (→ strategy engine)
- Produce UI state (→ frontend)
- Manage positions or orders (→ execution)
"""

import logging
from datetime import datetime, timezone

from backend.ptb.models import PTBRecord, PTBStatus
from backend.ptb.source_adapter import PTBSourceAdapter
from backend.domain.startup_guard import HealthIncident, HealthSeverity
from backend.logging_config.service import get_logger, log_event

logger = get_logger("ptb.fetcher")

# Default retry interval — hardcoded for now, will be config-driven later
DEFAULT_RETRY_INTERVAL_SEC = 5
DEFAULT_RETRY_MAX = 3


class PTBFetcher:
    """Orchestrates PTB fetch, lock, and retry lifecycle.

    PTB rules:
    - PTB is fetched once per event
    - Once acquired, it is LOCKED — no overwrite
    - Retry only runs while PTB is not acquired
    - Retry stops after acquisition or max attempts
    - Failure is never silent
    """

    def __init__(
        self,
        source: PTBSourceAdapter,
        retry_max: int = DEFAULT_RETRY_MAX,
    ):
        self._source = source
        self._retry_max = retry_max
        self._records: dict[str, PTBRecord] = {}  # keyed by condition_id

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
        """Fetch PTB for an event. Respects lock — won't refetch if locked.

        Args:
            condition_id: Event condition ID.
            asset: Crypto asset symbol.
            event_slug: Event slug for source lookup.

        Returns:
            PTBRecord with current state.
        """
        record = self.get_or_create_record(condition_id, asset)

        # Already locked — return immediately
        if record.is_locked:
            return record

        # Max retries exhausted
        if record.retry_count >= self._retry_max:
            if record.status != PTBStatus.FAILED:
                record.record_failure(f"Max retries ({self._retry_max}) exhausted")
                log_event(
                    logger, logging.ERROR,
                    f"PTB fetch exhausted for {asset} ({condition_id})",
                    entity_type="ptb",
                    entity_id=condition_id,
                    payload={"retry_count": record.retry_count},
                )
            return record

        # Attempt fetch
        record.record_retry()
        result = await self._source.fetch_ptb(asset, event_slug)

        if result.success and result.value is not None:
            record.lock(result.value, result.source_name)
            log_event(
                logger, logging.INFO,
                f"PTB locked: {asset} = {result.value} (source: {result.source_name})",
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

    def get_record(self, condition_id: str) -> PTBRecord | None:
        """Get PTB record by condition ID."""
        return self._records.get(condition_id)

    def clear_event(self, condition_id: str) -> None:
        """Clear PTB record for an event (event ended, cleanup)."""
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
        """Number of events still waiting for PTB."""
        return sum(1 for r in self._records.values() if r.is_waiting)

    @property
    def locked_count(self) -> int:
        """Number of events with locked PTB."""
        return sum(1 for r in self._records.values() if r.is_locked)

    @property
    def failed_count(self) -> int:
        """Number of events with failed PTB fetch."""
        return sum(1 for r in self._records.values() if r.is_failed)

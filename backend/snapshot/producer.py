"""SnapshotProducer — aggregates all data sources into SystemSnapshot.

Reads from LivePricePipeline, PTB records, Registry, Balance, and WS health
to produce a single authoritative SystemSnapshot.

v0.3.5: Snapshot production layer.

Responsibilities:
- Read live prices from LivePricePipeline
- Read PTB values from PTB store
- Read event statuses from Registry
- Read balance from BalanceSnapshot
- Read WS health from RTDSClient
- Combine into frozen SystemSnapshot

CRITICAL RULES:
- Snapshot is READ-ONLY (frozen dataclasses)
- PTB and live price are separate — never merged
- Source tracking preserved on every field
- Backend sole authority — frontend reads snapshot only
- No strategy/execution/UI logic in this module

Does NOT:
- Evaluate rules (→ v0.4.x)
- Execute trades (→ v0.5.x)
- Modify any source data (read-only aggregation)
"""

import logging
from datetime import datetime, timezone

from backend.domain.startup_guard import HealthIncident
from backend.logging_config.service import get_logger, log_event
from backend.market_data.live_price import LivePricePipeline, PriceSource, PriceStatus
from backend.snapshot.models import (
    BalanceSummary,
    EventSnapshot,
    HealthSummary,
    SnapshotEventStatus,
    SystemSnapshot,
)

logger = get_logger("snapshot.producer")


class SnapshotProducer:
    """Produces SystemSnapshot by aggregating all data sources.

    Each call to produce() creates a fresh, immutable snapshot
    reflecting the current state of all subsystems.

    Usage:
        producer = SnapshotProducer(pipeline=pipeline)
        producer.set_ptb_records(ptb_records)
        producer.set_registry_records(registry_records)
        producer.set_balance(balance_snapshot)
        producer.set_ws_status(ws_status)
        snapshot = producer.produce()
    """

    def __init__(self, pipeline: LivePricePipeline):
        self._pipeline = pipeline
        self._ptb_records: dict[str, dict] = {}    # condition_id → ptb info
        self._registry_records: dict[str, dict] = {}  # condition_id → registry info
        self._balance_total: float = 0.0
        self._balance_available: float = 0.0
        self._balance_fetched_at: datetime | None = None
        self._ws_connected: bool = False
        self._ws_state: str = "disconnected"
        self._ws_last_connected_at: datetime | None = None
        self._health_incidents: list[str] = []
        self._session_id: str = ""

    # ─── Data Source Setters ───

    def set_ptb_records(self, records: dict[str, dict]) -> None:
        """Set PTB records.

        Args:
            records: Dict of condition_id → {
                "ptb_value": float|None,
                "status": str,
                "source_name": str,
                "acquired_at": datetime|None
            }
        """
        self._ptb_records = dict(records)

    def set_registry_records(self, records: dict[str, dict]) -> None:
        """Set registry records.

        Args:
            records: Dict of condition_id → {
                "asset": str,
                "question": str,
                "status": str,
                "end_date": datetime|None
            }
        """
        self._registry_records = dict(records)

    def set_balance(
        self,
        total: float,
        available: float,
        fetched_at: datetime | None = None,
    ) -> None:
        """Set current balance."""
        self._balance_total = total
        self._balance_available = available
        self._balance_fetched_at = fetched_at

    def set_ws_status(
        self,
        connected: bool,
        state: str,
        last_connected_at: datetime | None = None,
    ) -> None:
        """Set WebSocket connection status."""
        self._ws_connected = connected
        self._ws_state = state
        self._ws_last_connected_at = last_connected_at

    def set_health_incidents(self, incidents: list[str]) -> None:
        """Set current health incident messages."""
        self._health_incidents = list(incidents)

    def set_session_id(self, session_id: str) -> None:
        """Set current session ID."""
        self._session_id = session_id

    # ─── Production ───

    def produce(self) -> SystemSnapshot:
        """Produce a fresh SystemSnapshot from all data sources.

        This is the main entry point. Reads all current state and
        returns a frozen, immutable snapshot.

        Returns:
            SystemSnapshot — complete, authoritative backend state.
        """
        now = datetime.now(timezone.utc)

        # Build event snapshots
        event_snapshots = self._build_event_snapshots()

        # Build balance summary
        balance = BalanceSummary(
            total=self._balance_total,
            available=self._balance_available,
            fetched_at=self._balance_fetched_at,
        )

        # Build health summary
        stale_count = sum(1 for e in event_snapshots if e.status == SnapshotEventStatus.STALE)
        invalid_count = sum(1 for e in event_snapshots if e.status == SnapshotEventStatus.INVALID)
        health = HealthSummary(
            ws_connected=self._ws_connected,
            ws_state=self._ws_state,
            ws_last_connected_at=self._ws_last_connected_at,
            stale_event_count=stale_count,
            invalid_event_count=invalid_count,
            incident_count=len(self._health_incidents),
            incidents=tuple(self._health_incidents),
        )

        snapshot = SystemSnapshot(
            generated_at=now,
            events=tuple(event_snapshots),
            balance=balance,
            health=health,
            session_id=self._session_id,
        )

        log_event(
            logger, logging.DEBUG,
            f"Snapshot produced: {snapshot.total_events} events "
            f"({snapshot.active_events} active, {snapshot.stale_events} stale)",
            entity_type="snapshot",
            entity_id="produced",
            payload={
                "total": snapshot.total_events,
                "active": snapshot.active_events,
                "stale": snapshot.stale_events,
            },
        )

        return snapshot

    def _build_event_snapshots(self) -> list[EventSnapshot]:
        """Build EventSnapshot list from pipeline + PTB + registry."""
        snapshots = []

        # Get all price records from pipeline
        price_records = self._pipeline.get_all_records()

        # Collect all condition_ids from all sources
        all_ids = set()
        for r in price_records:
            all_ids.add(r.condition_id)
        all_ids.update(self._ptb_records.keys())
        all_ids.update(self._registry_records.keys())

        for cond_id in sorted(all_ids):
            price_record = self._pipeline.get_record(cond_id)
            ptb_info = self._ptb_records.get(cond_id, {})
            reg_info = self._registry_records.get(cond_id, {})

            # Determine asset
            asset = ""
            if price_record:
                asset = price_record.asset
            elif reg_info.get("asset"):
                asset = reg_info["asset"]
            elif ptb_info.get("asset"):
                asset = ptb_info["asset"]

            # Determine snapshot status
            status = self._resolve_status(price_record, reg_info)

            # Build event snapshot
            ev = EventSnapshot(
                condition_id=cond_id,
                asset=asset,
                status=status,
                # Live price
                up_price=price_record.up_price if price_record else 0.0,
                down_price=price_record.down_price if price_record else 0.0,
                spread=price_record.spread if price_record else 0.0,
                best_bid=price_record.best_bid if price_record else 0.0,
                best_ask=price_record.best_ask if price_record else 0.0,
                price_source=price_record.source if price_record else PriceSource.NONE.value,
                price_status=price_record.status.value if price_record else PriceStatus.WAITING.value,
                price_updated_at=price_record.updated_at if price_record else None,
                # PTB (separate — never mixed with live price)
                ptb_value=ptb_info.get("ptb_value"),
                ptb_status=ptb_info.get("status", "waiting"),
                ptb_source=ptb_info.get("source_name", ""),
                ptb_acquired_at=ptb_info.get("acquired_at"),
                # Registry
                event_question=reg_info.get("question", ""),
                event_end_date=reg_info.get("end_date"),
                registry_status=reg_info.get("status", ""),
            )
            snapshots.append(ev)

        return snapshots

    @staticmethod
    def _resolve_status(price_record, reg_info: dict) -> SnapshotEventStatus:
        """Resolve the overall snapshot status for an event.

        Priority:
        1. Registry says inactive/expired → use that
        2. Price is invalid → INVALID
        3. Price is stale → STALE
        4. Price is waiting → WAITING
        5. Price is fresh → ACTIVE
        """
        reg_status = reg_info.get("status", "").lower()

        # Registry-level overrides
        if reg_status in ("expired", "closed"):
            return SnapshotEventStatus.EXPIRED
        if reg_status in ("inactive", "suspended"):
            return SnapshotEventStatus.INACTIVE

        # Price-level status
        if price_record is None:
            return SnapshotEventStatus.WAITING

        if price_record.status == PriceStatus.INVALID:
            return SnapshotEventStatus.INVALID
        if price_record.status == PriceStatus.STALE:
            return SnapshotEventStatus.STALE
        if price_record.status == PriceStatus.WAITING:
            return SnapshotEventStatus.WAITING
        if price_record.status == PriceStatus.FRESH:
            return SnapshotEventStatus.ACTIVE

        return SnapshotEventStatus.WAITING

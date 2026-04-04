"""Backend authoritative snapshot models.

v0.3.5: Single consolidated view of all market data for a point in time.
The snapshot is the SOLE authoritative state the frontend reads.
Frontend NEVER produces its own decisions — only displays this snapshot.

Snapshot aggregates:
- Live prices (from LivePricePipeline — WS primary, Gamma fallback)
- PTB values (from PTBFetcher — locked once acquired)
- Event registry status (from Registry)
- Balance (from BalanceSnapshot)
- Health indicators (connection state, stale warnings)

CRITICAL RULES:
- PTB and live price are SEPARATE fields — never mixed
- Source is always recorded per data point
- Stale/invalid states are visible, not hidden
- Backend is sole decision authority (CLAUDE.md)

Does NOT:
- Evaluate rules (→ v0.4.x)
- Execute trades (→ v0.5.x)
- Render UI (→ frontend)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from backend.market_data.live_price import PriceSource, PriceStatus


class SnapshotEventStatus(str, Enum):
    """Simplified event status for snapshot consumption."""
    ACTIVE = "active"           # Event is live and tradeable
    STALE = "stale"             # Data is stale — caution
    WAITING = "waiting"         # Waiting for data
    INVALID = "invalid"         # Data invalid — do not trade
    INACTIVE = "inactive"       # Event not currently active
    EXPIRED = "expired"         # Event has ended


@dataclass(frozen=True)
class EventSnapshot:
    """Snapshot of a single event/market at a point in time.

    Combines live price, PTB, and registry data into one read-only view.
    All source information is preserved for transparency.

    Attributes:
        condition_id: Market condition ID (key).
        asset: Crypto asset symbol.
        status: Snapshot-level status (active, stale, waiting, invalid, inactive).

        Live price fields:
        up_price: Current UP outcome price.
        down_price: Current DOWN outcome price.
        spread: Current bid-ask spread.
        best_bid: Best bid price (from WS).
        best_ask: Best ask price (from WS).
        price_source: Where live price came from (rtds_ws, gamma, none).
        price_status: Live price status (fresh, stale, invalid, waiting).
        price_updated_at: When live price was last updated.

        PTB fields (SEPARATE from live price — USD coin price, NOT outcome price):
        ptb_value: USD coin price at event open (e.g., 67260.12 for BTC). None if not yet.
        ptb_status: PTB status (waiting, acquired, failed).
        ptb_source: Where PTB was fetched from.
        ptb_acquired_at: When PTB was locked.

        Registry fields:
        event_question: Event title/question.
        event_end_date: When the event expires.
        registry_status: Raw registry status string.
    """
    # Identity
    condition_id: str
    asset: str
    status: SnapshotEventStatus

    # Live price
    up_price: float = 0.0
    down_price: float = 0.0
    spread: float = 0.0
    best_bid: float = 0.0
    best_ask: float = 0.0
    price_source: str = PriceSource.NONE.value
    price_status: str = PriceStatus.WAITING.value
    price_updated_at: datetime | None = None

    # PTB (separate from live price — NEVER mixed)
    ptb_value: float | None = None
    ptb_status: str = "waiting"
    ptb_source: str = ""
    ptb_acquired_at: datetime | None = None

    # Registry
    event_question: str = ""
    event_end_date: datetime | None = None
    registry_status: str = ""


@dataclass(frozen=True)
class BalanceSummary:
    """Balance summary within snapshot."""
    total: float = 0.0
    available: float = 0.0
    fetched_at: datetime | None = None
    source: str = "clob_sdk"


@dataclass(frozen=True)
class HealthSummary:
    """Health summary within snapshot."""
    ws_connected: bool = False
    ws_state: str = "disconnected"
    ws_last_connected_at: datetime | None = None
    stale_event_count: int = 0
    invalid_event_count: int = 0
    incident_count: int = 0
    incidents: tuple[str, ...] = ()


@dataclass(frozen=True)
class SystemSnapshot:
    """Complete system snapshot — the authoritative backend state.

    This is the single object that represents everything the frontend
    needs to display. Frontend reads this and NOTHING else for decisions.

    Attributes:
        generated_at: When this snapshot was produced.
        events: All tracked event snapshots.
        balance: Current balance summary.
        health: System health summary.
        total_events: Number of events in snapshot.
        active_events: Number of ACTIVE events.
        session_id: Current session ID (if any).
    """
    generated_at: datetime
    events: tuple[EventSnapshot, ...] = ()
    balance: BalanceSummary = BalanceSummary()
    health: HealthSummary = HealthSummary()
    session_id: str = ""

    @property
    def total_events(self) -> int:
        return len(self.events)

    @property
    def active_events(self) -> int:
        return sum(1 for e in self.events if e.status == SnapshotEventStatus.ACTIVE)

    @property
    def stale_events(self) -> int:
        return sum(1 for e in self.events if e.status == SnapshotEventStatus.STALE)

    @property
    def waiting_events(self) -> int:
        return sum(1 for e in self.events if e.status == SnapshotEventStatus.WAITING)

    def get_event(self, condition_id: str) -> EventSnapshot | None:
        """Get event snapshot by condition_id."""
        for e in self.events:
            if e.condition_id == condition_id:
                return e
        return None

    def get_events_by_asset(self, asset: str) -> list[EventSnapshot]:
        """Get event snapshots by asset symbol."""
        return [e for e in self.events if e.asset == asset]

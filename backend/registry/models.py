"""Registry models — authoritative event state management.

RegistryRecord is the authoritative state representation of an event.
It is NOT the same as DiscoveredEvent:
- DiscoveredEvent = raw candidate from discovery scan
- RegistryRecord = authoritative lifecycle state managed by registry

Discovery finds candidates. Registry owns their lifecycle state.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class EventStatus(str, Enum):
    """Event lifecycle states in the registry.

    This is the authoritative state machine for event lifecycle.
    Transitions are controlled by the Registry service.
    """
    DISCOVERED = "discovered"       # First seen by discovery, not yet validated
    VALIDATING = "validating"       # Being validated (live check pending)
    ACTIVE = "active"               # Validated and actively monitored
    INACTIVE = "inactive"           # Temporarily inactive (e.g., between rounds)
    EXPIRED = "expired"             # Event duration ended
    SUSPENDED = "suspended"         # Manually or automatically suspended
    CLOSED = "closed"               # Fully closed, no further action


# Allowed state transitions — registry enforces these
ALLOWED_TRANSITIONS: dict[EventStatus, set[EventStatus]] = {
    EventStatus.DISCOVERED: {EventStatus.VALIDATING, EventStatus.CLOSED},
    EventStatus.VALIDATING: {EventStatus.ACTIVE, EventStatus.INACTIVE, EventStatus.CLOSED},
    EventStatus.ACTIVE: {EventStatus.INACTIVE, EventStatus.EXPIRED, EventStatus.SUSPENDED, EventStatus.CLOSED},
    EventStatus.INACTIVE: {EventStatus.ACTIVE, EventStatus.EXPIRED, EventStatus.CLOSED},
    EventStatus.EXPIRED: {EventStatus.CLOSED},
    EventStatus.SUSPENDED: {EventStatus.ACTIVE, EventStatus.CLOSED},
    EventStatus.CLOSED: set(),  # Terminal state — no transitions out
}


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""
    def __init__(self, current: EventStatus, target: EventStatus, event_id: str = ""):
        self.current = current
        self.target = target
        self.event_id = event_id
        super().__init__(
            f"Invalid transition: {current.value} → {target.value} "
            f"for event {event_id}"
        )


@dataclass
class RegistryRecord:
    """Authoritative event record in the registry.

    Attributes:
        event_id: Internal registry identifier.
        condition_id: Polymarket condition ID (from discovery).
        asset: Crypto asset symbol (e.g., "BTC").
        question: Event question/title.
        slug: URL slug.
        status: Current lifecycle state (authoritative).
        first_seen_at: When discovery first found this event.
        last_seen_at: When discovery last confirmed this event.
        status_changed_at: When the status last changed.
        end_date: Event end timestamp.
        has_open_position: Whether there's an open position on this event.
    """
    event_id: str
    condition_id: str
    asset: str
    question: str
    slug: str
    status: EventStatus
    first_seen_at: datetime
    last_seen_at: datetime
    status_changed_at: datetime
    end_date: datetime
    has_open_position: bool = False

    def can_transition_to(self, target: EventStatus) -> bool:
        """Check if transition to target state is allowed."""
        return target in ALLOWED_TRANSITIONS.get(self.status, set())

    def transition_to(self, target: EventStatus) -> None:
        """Transition to a new state. Raises if invalid.

        Args:
            target: The target EventStatus.

        Raises:
            InvalidTransitionError: If transition is not allowed.
        """
        if not self.can_transition_to(target):
            raise InvalidTransitionError(self.status, target, self.event_id)
        self.status = target
        self.status_changed_at = datetime.now(timezone.utc)

    def update_last_seen(self) -> None:
        """Update last_seen_at to now (discovery confirmed presence)."""
        self.last_seen_at = datetime.now(timezone.utc)

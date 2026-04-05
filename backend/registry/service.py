"""EventRegistry — authoritative state management for discovered events.

The registry is the single source of truth for event lifecycle state.
Discovery finds candidate events; the registry owns their state.

Responsibilities:
- Accept candidate events from discovery
- Create RegistryRecord from DiscoveredEvent
- Manage state transitions (discovered → validating → active → ...)
- Query events by status
- Enforce transition rules

Does NOT:
- Perform live validation (→ v0.2.5)
- Implement safe sync (→ v0.2.6)
- Manage market data or PTB (→ v0.3.x)
- Evaluate trading rules (→ v0.4.x)
"""

import logging
import uuid
from datetime import datetime, timezone

from backend.discovery.models import DiscoveredEvent
from backend.registry.models import (
    RegistryRecord,
    EventStatus,
    InvalidTransitionError,
)
from backend.logging_config.service import get_logger, log_event

logger = get_logger("registry")


class EventRegistry:
    """Authoritative event registry — manages event lifecycle state.

    Holds all known events and their current status. Discovery
    submits candidates; registry decides their state.
    """

    def __init__(self) -> None:
        self._records: dict[str, RegistryRecord] = {}  # keyed by condition_id

    def register_candidate(self, candidate: DiscoveredEvent) -> RegistryRecord:
        """Register a discovered candidate event in the registry.

        If the event (by condition_id) already exists, updates last_seen_at.
        If new, creates a RegistryRecord with DISCOVERED status.

        Args:
            candidate: DiscoveredEvent from discovery scan.

        Returns:
            The RegistryRecord (new or existing).
        """
        existing = self._records.get(candidate.condition_id)

        if existing is not None:
            existing.update_last_seen()
            log_event(
                logger, logging.DEBUG,
                f"Event already registered, updated last_seen: {candidate.condition_id}",
                entity_type="registry",
                entity_id=candidate.condition_id,
            )
            return existing

        record = RegistryRecord(
            event_id=str(uuid.uuid4()),
            condition_id=candidate.condition_id,
            asset=candidate.asset,
            question=candidate.question,
            slug=candidate.slug,
            status=EventStatus.DISCOVERED,
            first_seen_at=candidate.discovered_at,
            last_seen_at=candidate.discovered_at,
            status_changed_at=candidate.discovered_at,
            end_date=candidate.end_date,
        )

        self._records[candidate.condition_id] = record

        log_event(
            logger, logging.INFO,
            f"New event registered: {candidate.asset} ({candidate.condition_id})",
            entity_type="registry",
            entity_id=candidate.condition_id,
            payload={"asset": candidate.asset, "status": record.status.value},
        )

        return record

    def transition_event(self, condition_id: str, target: EventStatus) -> RegistryRecord:
        """Transition an event to a new state.

        Args:
            condition_id: The event's condition_id.
            target: Target EventStatus.

        Returns:
            Updated RegistryRecord.

        Raises:
            KeyError: If event not found.
            InvalidTransitionError: If transition is not allowed.
        """
        record = self._records.get(condition_id)
        if record is None:
            raise KeyError(f"Event not found in registry: {condition_id}")

        old_status = record.status
        record.transition_to(target)

        log_event(
            logger, logging.INFO,
            f"Event state transition: {old_status.value} → {target.value}",
            entity_type="registry",
            entity_id=condition_id,
            payload={"from": old_status.value, "to": target.value},
        )

        return record

    def get_by_condition_id(self, condition_id: str) -> RegistryRecord | None:
        """Get a registry record by condition_id."""
        return self._records.get(condition_id)

    def get_by_status(self, status: EventStatus) -> list[RegistryRecord]:
        """Get all events with a given status."""
        return [r for r in self._records.values() if r.status == status]

    def get_all(self) -> list[RegistryRecord]:
        """Get all registry records."""
        return list(self._records.values())

    @property
    def count(self) -> int:
        """Total number of events in registry."""
        return len(self._records)

    @property
    def active_count(self) -> int:
        """Number of events with ACTIVE status."""
        return sum(1 for r in self._records.values() if r.status == EventStatus.ACTIVE)

    def expire_events(self, now: datetime) -> list[str]:
        """Süresi dolmuş event'leri EXPIRED'a geçir.

        end_date < now olan ve henüz terminal state'te olmayan event'ler
        EXPIRED'a geçirilir. has_open_position olan event'ler ATLANMAZ —
        expired olur ama position yönetimi devam eder (Faz 5).

        Returns:
            Expired olan event condition_id'leri.
        """
        expired_ids = []
        for cond_id, record in self._records.items():
            if record.status in (EventStatus.EXPIRED, EventStatus.CLOSED):
                continue  # zaten terminal
            if record.end_date and record.end_date <= now:
                try:
                    old = record.status
                    record.transition_to(EventStatus.EXPIRED)
                    expired_ids.append(cond_id)
                    log_event(
                        logger, logging.INFO,
                        f"Event expired: {record.asset} ({old.value} → expired)",
                        entity_type="registry",
                        entity_id=cond_id,
                    )
                except InvalidTransitionError:
                    pass  # geçiş izni yoksa atla
        return expired_ids

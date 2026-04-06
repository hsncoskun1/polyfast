"""SafeSync — controlled registry update without destructive deletion.

Safe sync ensures that events disappearing from discovery scans
are NOT immediately deleted from the registry. Instead, they go
through a controlled soft-remove process.

Key rules:
- Event not seen in scan → soft-removed (NOT deleted)
- Event with open position → NEVER removed by sync
- Event reappearing after soft-remove → restored
- Temporary disappearance ≠ permanent closure
- Destructive sync is FORBIDDEN

Responsibilities:
- Reconcile discovery results with registry state
- Apply soft-remove to missing events
- Protect events with open positions
- Track disappearance count (delist suspicion)

Does NOT:
- Implement persistence (→ v0.2.7)
- Manage market data or PTB (→ v0.3.x)
- Evaluate trading rules (→ v0.4.x)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.discovery.models import DiscoveredEvent
from backend.registry.models import RegistryRecord, EventStatus
from backend.registry.service import EventRegistry
from backend.domain.startup_guard import HealthIncident, HealthSeverity
from backend.logging_config.service import get_logger, log_event

logger = get_logger("safe_sync")


@dataclass
class SyncResult:
    """Result of a safe sync operation."""
    new_registered: int = 0
    updated_last_seen: int = 0
    soft_removed: int = 0
    protected_by_position: int = 0
    restored: int = 0
    total_in_registry: int = 0
    health_incidents: list[HealthIncident] = field(default_factory=list)
    synced_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SafeSync:
    """Reconciles discovery results with registry without destructive deletion.

    Rules:
    1. New candidate → register as DISCOVERED
    2. Known candidate → update last_seen
    3. Registry event not in scan → increment delist_suspicion, soft-remove if threshold hit
    4. Event with has_open_position=True → NEVER soft-removed by sync
    5. Soft-removed event reappearing → restore to previous active-path state
    """

    # Default — schema'dan override edilebilir (DiscoveryConfig.delist_threshold)
    DEFAULT_DELIST_THRESHOLD = 3

    def __init__(self, registry: EventRegistry, delist_threshold: int = DEFAULT_DELIST_THRESHOLD):
        self._registry = registry
        self._delist_threshold = delist_threshold
        self._miss_counts: dict[str, int] = {}  # condition_id → consecutive miss count

    def sync(self, discovered_events: list[DiscoveredEvent]) -> SyncResult:
        """Reconcile discovery results with registry state.

        Args:
            discovered_events: List of candidate events from latest discovery scan.

        Returns:
            SyncResult with counts and any health incidents.
        """
        result = SyncResult()
        seen_condition_ids = {e.condition_id for e in discovered_events}

        # Phase 1: Process discovered events (new or existing)
        for candidate in discovered_events:
            existing = self._registry.get_by_condition_id(candidate.condition_id)

            if existing is None:
                # New event — register
                self._registry.register_candidate(candidate)
                result.new_registered += 1
                self._miss_counts.pop(candidate.condition_id, None)
            else:
                # Known event — update last_seen
                existing.update_last_seen()
                result.updated_last_seen += 1
                self._miss_counts.pop(candidate.condition_id, None)

                # If soft-removed / inactive, consider restoring
                if existing.status == EventStatus.INACTIVE:
                    if existing.can_transition_to(EventStatus.ACTIVE):
                        existing.transition_to(EventStatus.ACTIVE)
                        result.restored += 1
                        log_event(
                            logger, logging.INFO,
                            f"Event restored from INACTIVE: {candidate.condition_id}",
                            entity_type="safe_sync",
                            entity_id=candidate.condition_id,
                        )

        # Phase 2: Handle events in registry NOT seen in this scan
        for record in self._registry.get_all():
            if record.condition_id in seen_condition_ids:
                continue

            # Skip terminal states
            if record.status in (EventStatus.CLOSED, EventStatus.EXPIRED):
                continue

            # Open position protection
            if record.has_open_position:
                result.protected_by_position += 1
                log_event(
                    logger, logging.WARNING,
                    f"Event missing from scan but has open position — PROTECTED: {record.condition_id}",
                    entity_type="safe_sync",
                    entity_id=record.condition_id,
                )
                continue

            # Increment miss count
            miss_count = self._miss_counts.get(record.condition_id, 0) + 1
            self._miss_counts[record.condition_id] = miss_count

            # Soft-remove if threshold reached
            if miss_count >= self._delist_threshold:
                if record.can_transition_to(EventStatus.INACTIVE):
                    old_status = record.status
                    record.transition_to(EventStatus.INACTIVE)
                    result.soft_removed += 1
                    log_event(
                        logger, logging.INFO,
                        f"Event soft-removed ({old_status.value} → INACTIVE) after {miss_count} missed scans: {record.condition_id}",
                        entity_type="safe_sync",
                        entity_id=record.condition_id,
                        payload={"miss_count": miss_count, "from_status": old_status.value},
                    )

        result.total_in_registry = self._registry.count
        return result

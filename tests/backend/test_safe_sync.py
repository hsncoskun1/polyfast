"""Tests for safe sync — controlled registry update, soft-remove, position protection."""

import pytest
from datetime import datetime, timezone

from backend.discovery.models import DiscoveredEvent
from backend.registry.models import EventStatus
from backend.registry.service import EventRegistry
from backend.registry.safe_sync import SafeSync, SyncResult


def _make_candidate(condition_id: str = "0x1", asset: str = "BTC") -> DiscoveredEvent:
    return DiscoveredEvent(
        condition_id=condition_id, question=f"Will {asset} go up in 5 min?",
        slug=f"{asset.lower()}-5m", asset=asset, duration="5m", category="crypto",
        end_date=datetime(2026, 4, 4, 12, 5, 0, tzinfo=timezone.utc),
        discovered_at=datetime(2026, 4, 4, 12, 0, 0, tzinfo=timezone.utc),
    )


# ===== New Event Registration =====

class TestSafeSyncNewEvents:
    def test_new_event_registered(self):
        """New candidate → registered in registry."""
        registry = EventRegistry()
        sync = SafeSync(registry=registry)
        result = sync.sync([_make_candidate("0x1")])

        assert result.new_registered == 1
        assert registry.count == 1

    def test_multiple_new_events(self):
        registry = EventRegistry()
        sync = SafeSync(registry=registry)
        result = sync.sync([_make_candidate("0x1"), _make_candidate("0x2")])

        assert result.new_registered == 2
        assert registry.count == 2


# ===== Existing Event Update =====

class TestSafeSyncExistingEvents:
    def test_existing_event_updates_last_seen(self):
        """Known event → update last_seen, not re-registered."""
        registry = EventRegistry()
        sync = SafeSync(registry=registry)
        sync.sync([_make_candidate("0x1")])
        result = sync.sync([_make_candidate("0x1")])

        assert result.new_registered == 0
        assert result.updated_last_seen == 1
        assert registry.count == 1


# ===== Soft Remove =====

class TestSafeSyncSoftRemove:
    def test_event_not_immediately_removed(self):
        """Missing event is NOT removed after 1 missed scan."""
        registry = EventRegistry()
        sync = SafeSync(registry=registry)
        sync.sync([_make_candidate("0x1")])

        # Event disappears for 1 scan
        result = sync.sync([])
        assert result.soft_removed == 0
        record = registry.get_by_condition_id("0x1")
        assert record.status == EventStatus.DISCOVERED  # not removed

    def test_event_soft_removed_after_threshold(self):
        """Missing event → soft-removed after DELIST_THRESHOLD consecutive misses."""
        registry = EventRegistry()
        sync = SafeSync(registry=registry)
        sync.sync([_make_candidate("0x1")])

        # Miss 3 consecutive scans (threshold = 3)
        sync.sync([])
        sync.sync([])
        result = sync.sync([])

        assert result.soft_removed == 1
        record = registry.get_by_condition_id("0x1")
        assert record.status == EventStatus.INACTIVE

    def test_miss_count_resets_on_reappearance(self):
        """If event reappears before threshold, miss count resets."""
        registry = EventRegistry()
        sync = SafeSync(registry=registry)
        sync.sync([_make_candidate("0x1")])

        # Miss 2 scans
        sync.sync([])
        sync.sync([])

        # Reappears
        sync.sync([_make_candidate("0x1")])

        # Miss 2 more (should NOT trigger soft-remove)
        sync.sync([])
        result = sync.sync([])

        assert result.soft_removed == 0
        record = registry.get_by_condition_id("0x1")
        assert record.status == EventStatus.DISCOVERED


# ===== Open Position Protection =====

class TestSafeSyncPositionProtection:
    def test_event_with_open_position_never_removed(self):
        """Event with has_open_position=True is NEVER soft-removed."""
        registry = EventRegistry()
        sync = SafeSync(registry=registry)
        sync.sync([_make_candidate("0x1")])

        # Set open position flag
        record = registry.get_by_condition_id("0x1")
        record.has_open_position = True

        # Miss many scans
        for _ in range(10):
            sync.sync([])

        assert record.status == EventStatus.DISCOVERED  # protected
        result = sync.sync([])
        assert result.protected_by_position >= 1

    def test_protection_logged(self):
        """Protected event produces a log (tested by checking result count)."""
        registry = EventRegistry()
        sync = SafeSync(registry=registry)
        sync.sync([_make_candidate("0x1")])
        registry.get_by_condition_id("0x1").has_open_position = True

        result = sync.sync([])
        assert result.protected_by_position == 1


# ===== Event Restoration =====

class TestSafeSyncRestoration:
    def test_inactive_event_restored_on_reappearance(self):
        """INACTIVE event → reappears → restored to ACTIVE."""
        registry = EventRegistry()
        sync = SafeSync(registry=registry)
        sync.sync([_make_candidate("0x1")])

        # Transition to validating → active first (so inactive → active is valid)
        registry.transition_event("0x1", EventStatus.VALIDATING)
        registry.transition_event("0x1", EventStatus.ACTIVE)

        # Now go inactive
        registry.transition_event("0x1", EventStatus.INACTIVE)
        assert registry.get_by_condition_id("0x1").status == EventStatus.INACTIVE

        # Reappears in scan
        result = sync.sync([_make_candidate("0x1")])
        assert result.restored == 1
        assert registry.get_by_condition_id("0x1").status == EventStatus.ACTIVE


# ===== Terminal State Skipping =====

class TestSafeSyncTerminalStates:
    def test_closed_event_not_affected(self):
        """CLOSED events are skipped during sync."""
        registry = EventRegistry()
        sync = SafeSync(registry=registry)
        sync.sync([_make_candidate("0x1")])

        registry.transition_event("0x1", EventStatus.VALIDATING)
        registry.transition_event("0x1", EventStatus.CLOSED)

        # Many scans without this event
        for _ in range(5):
            sync.sync([])

        record = registry.get_by_condition_id("0x1")
        assert record.status == EventStatus.CLOSED  # unchanged

    def test_expired_event_not_affected(self):
        """EXPIRED events are skipped during sync."""
        registry = EventRegistry()
        sync = SafeSync(registry=registry)
        sync.sync([_make_candidate("0x1")])

        registry.transition_event("0x1", EventStatus.VALIDATING)
        registry.transition_event("0x1", EventStatus.ACTIVE)
        registry.transition_event("0x1", EventStatus.EXPIRED)

        for _ in range(5):
            sync.sync([])

        assert registry.get_by_condition_id("0x1").status == EventStatus.EXPIRED


# ===== No Destructive Delete =====

class TestSafeSyncNoDestructiveDelete:
    def test_registry_count_never_decreases(self):
        """Events are never deleted from registry, only state changes."""
        registry = EventRegistry()
        sync = SafeSync(registry=registry)
        sync.sync([_make_candidate("0x1"), _make_candidate("0x2"), _make_candidate("0x3")])

        assert registry.count == 3

        # All disappear
        for _ in range(5):
            sync.sync([])

        # Count stays the same — no deletion
        assert registry.count == 3


# ===== Boundary Tests =====

class TestSafeSyncBoundaries:
    def test_no_market_data_import(self):
        import backend.registry.safe_sync as mod
        import_lines = [l.strip() for l in open(mod.__file__).readlines()
                        if l.strip().startswith(("import ", "from "))]
        for line in import_lines:
            assert "market_data" not in line
            assert "ptb" not in line

    def test_no_execution_import(self):
        import backend.registry.safe_sync as mod
        import_lines = [l.strip() for l in open(mod.__file__).readlines()
                        if l.strip().startswith(("import ", "from "))]
        for line in import_lines:
            assert "execution" not in line

    def test_no_strategy_import(self):
        import backend.registry.safe_sync as mod
        import_lines = [l.strip() for l in open(mod.__file__).readlines()
                        if l.strip().startswith(("import ", "from "))]
        for line in import_lines:
            assert "strategy" not in line

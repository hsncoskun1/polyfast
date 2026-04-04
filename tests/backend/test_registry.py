"""Tests for event registry — models, state machine, service, boundaries."""

import pytest
from datetime import datetime, timezone

from backend.discovery.models import DiscoveredEvent
from backend.registry.models import (
    RegistryRecord,
    EventStatus,
    ALLOWED_TRANSITIONS,
    InvalidTransitionError,
)
from backend.registry.service import EventRegistry


def _make_candidate(
    condition_id: str = "0xabc",
    asset: str = "BTC",
    question: str = "Will BTC go up in the next 5 minutes?",
) -> DiscoveredEvent:
    return DiscoveredEvent(
        condition_id=condition_id,
        question=question,
        slug="btc-5m-up",
        asset=asset,
        duration="5m",
        category="crypto",
        end_date=datetime(2026, 4, 4, 12, 5, 0, tzinfo=timezone.utc),
        discovered_at=datetime(2026, 4, 4, 12, 0, 0, tzinfo=timezone.utc),
    )


# ===== State Machine Tests =====

class TestEventStatusTransitions:
    def test_discovered_can_go_to_validating(self):
        record = _make_record(EventStatus.DISCOVERED)
        assert record.can_transition_to(EventStatus.VALIDATING) is True

    def test_discovered_cannot_go_to_active(self):
        record = _make_record(EventStatus.DISCOVERED)
        assert record.can_transition_to(EventStatus.ACTIVE) is False

    def test_validating_can_go_to_active(self):
        record = _make_record(EventStatus.VALIDATING)
        assert record.can_transition_to(EventStatus.ACTIVE) is True

    def test_active_can_go_to_expired(self):
        record = _make_record(EventStatus.ACTIVE)
        assert record.can_transition_to(EventStatus.EXPIRED) is True

    def test_closed_cannot_transition(self):
        record = _make_record(EventStatus.CLOSED)
        for status in EventStatus:
            assert record.can_transition_to(status) is False

    def test_invalid_transition_raises(self):
        record = _make_record(EventStatus.DISCOVERED)
        with pytest.raises(InvalidTransitionError) as exc_info:
            record.transition_to(EventStatus.ACTIVE)
        assert exc_info.value.current == EventStatus.DISCOVERED
        assert exc_info.value.target == EventStatus.ACTIVE

    def test_valid_transition_updates_status(self):
        record = _make_record(EventStatus.DISCOVERED)
        record.transition_to(EventStatus.VALIDATING)
        assert record.status == EventStatus.VALIDATING

    def test_transition_updates_timestamp(self):
        record = _make_record(EventStatus.DISCOVERED)
        old_time = record.status_changed_at
        record.transition_to(EventStatus.VALIDATING)
        assert record.status_changed_at >= old_time

    def test_all_states_have_transition_rules(self):
        """Every EventStatus has an entry in ALLOWED_TRANSITIONS."""
        for status in EventStatus:
            assert status in ALLOWED_TRANSITIONS

    def test_expired_can_only_go_to_closed(self):
        record = _make_record(EventStatus.EXPIRED)
        assert record.can_transition_to(EventStatus.CLOSED) is True
        assert record.can_transition_to(EventStatus.ACTIVE) is False

    def test_suspended_can_return_to_active(self):
        record = _make_record(EventStatus.SUSPENDED)
        assert record.can_transition_to(EventStatus.ACTIVE) is True


def _make_record(status: EventStatus) -> RegistryRecord:
    now = datetime.now(timezone.utc)
    return RegistryRecord(
        event_id="test-id",
        condition_id="0xtest",
        asset="BTC",
        question="Test event",
        slug="test",
        status=status,
        first_seen_at=now,
        last_seen_at=now,
        status_changed_at=now,
        end_date=now,
    )


# ===== Registry Service Tests =====

class TestEventRegistryService:
    def test_register_new_candidate(self):
        """New candidate creates a DISCOVERED record."""
        registry = EventRegistry()
        candidate = _make_candidate()
        record = registry.register_candidate(candidate)

        assert record.condition_id == "0xabc"
        assert record.asset == "BTC"
        assert record.status == EventStatus.DISCOVERED
        assert registry.count == 1

    def test_register_duplicate_updates_last_seen(self):
        """Re-registering same condition_id updates last_seen, doesn't duplicate."""
        registry = EventRegistry()
        candidate = _make_candidate()
        first = registry.register_candidate(candidate)

        second = registry.register_candidate(candidate)
        assert registry.count == 1  # no duplicate
        assert second is first  # same object
        # last_seen_at is updated to now (not the candidate's discovered_at)
        assert second.last_seen_at != candidate.discovered_at

    def test_register_multiple_candidates(self):
        """Multiple different candidates create separate records."""
        registry = EventRegistry()
        registry.register_candidate(_make_candidate(condition_id="0x1", asset="BTC"))
        registry.register_candidate(_make_candidate(condition_id="0x2", asset="ETH"))
        registry.register_candidate(_make_candidate(condition_id="0x3", asset="SOL"))

        assert registry.count == 3

    def test_transition_event(self):
        """Transition changes state correctly."""
        registry = EventRegistry()
        registry.register_candidate(_make_candidate())
        record = registry.transition_event("0xabc", EventStatus.VALIDATING)

        assert record.status == EventStatus.VALIDATING

    def test_transition_invalid_raises(self):
        """Invalid transition raises InvalidTransitionError."""
        registry = EventRegistry()
        registry.register_candidate(_make_candidate())

        with pytest.raises(InvalidTransitionError):
            registry.transition_event("0xabc", EventStatus.ACTIVE)  # DISCOVERED → ACTIVE invalid

    def test_transition_nonexistent_raises(self):
        """Transitioning unknown event raises KeyError."""
        registry = EventRegistry()
        with pytest.raises(KeyError):
            registry.transition_event("nonexistent", EventStatus.ACTIVE)

    def test_get_by_condition_id(self):
        registry = EventRegistry()
        registry.register_candidate(_make_candidate(condition_id="0x1"))
        assert registry.get_by_condition_id("0x1") is not None
        assert registry.get_by_condition_id("0x999") is None

    def test_get_by_status(self):
        registry = EventRegistry()
        registry.register_candidate(_make_candidate(condition_id="0x1"))
        registry.register_candidate(_make_candidate(condition_id="0x2"))
        registry.transition_event("0x1", EventStatus.VALIDATING)

        discovered = registry.get_by_status(EventStatus.DISCOVERED)
        validating = registry.get_by_status(EventStatus.VALIDATING)

        assert len(discovered) == 1
        assert len(validating) == 1

    def test_active_count(self):
        registry = EventRegistry()
        registry.register_candidate(_make_candidate(condition_id="0x1"))
        registry.register_candidate(_make_candidate(condition_id="0x2"))
        assert registry.active_count == 0

        registry.transition_event("0x1", EventStatus.VALIDATING)
        registry.transition_event("0x1", EventStatus.ACTIVE)
        assert registry.active_count == 1


# ===== Model Separation Tests =====

class TestModelSeparation:
    def test_discovered_event_is_not_registry_record(self):
        """DiscoveredEvent and RegistryRecord are distinct types."""
        candidate = _make_candidate()
        record = _make_record(EventStatus.DISCOVERED)

        assert type(candidate) is not type(record)
        assert hasattr(record, "status")
        assert hasattr(record, "event_id")
        assert hasattr(record, "has_open_position")
        assert not hasattr(candidate, "status")
        assert not hasattr(candidate, "event_id")

    def test_registry_record_has_lifecycle_fields(self):
        """RegistryRecord has fields DiscoveredEvent doesn't."""
        record = _make_record(EventStatus.ACTIVE)
        assert hasattr(record, "status")
        assert hasattr(record, "first_seen_at")
        assert hasattr(record, "last_seen_at")
        assert hasattr(record, "status_changed_at")
        assert hasattr(record, "has_open_position")


# ===== Boundary Tests =====

class TestRegistryBoundaries:
    def test_no_market_data_import(self):
        """Registry does not import market_data or ptb."""
        import backend.registry.service as mod
        import_lines = [l.strip() for l in open(mod.__file__).readlines()
                        if l.strip().startswith(("import ", "from "))]
        for line in import_lines:
            assert "market_data" not in line
            assert "ptb" not in line

    def test_no_execution_import(self):
        """Registry does not import execution."""
        import backend.registry.service as mod
        import_lines = [l.strip() for l in open(mod.__file__).readlines()
                        if l.strip().startswith(("import ", "from "))]
        for line in import_lines:
            assert "execution" not in line

    def test_no_strategy_import(self):
        """Registry does not import strategy/rule engine."""
        import backend.registry.service as mod
        import_lines = [l.strip() for l in open(mod.__file__).readlines()
                        if l.strip().startswith(("import ", "from "))]
        for line in import_lines:
            assert "strategy" not in line

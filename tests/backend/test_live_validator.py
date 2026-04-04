"""Tests for live validator — event liveness checks, health incidents, boundaries."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.auth_clients.public_client import PublicMarketClient
from backend.auth_clients.errors import ClientError, ErrorCategory
from backend.discovery.live_validator import (
    LiveValidator,
    ValidationResult,
    ValidationOutcome,
)
from backend.domain.startup_guard import HealthSeverity
from backend.registry.models import EventStatus, RegistryRecord, InvalidTransitionError
from backend.registry.service import EventRegistry
from backend.discovery.models import DiscoveredEvent
from datetime import datetime, timezone


def _make_validator(response_data=None, error=None) -> LiveValidator:
    client = PublicMarketClient(base_url="https://test.api")
    mock_response = MagicMock()
    if response_data is not None:
        mock_response.json.return_value = response_data
        client.get = AsyncMock(return_value=mock_response)
    elif error is not None:
        client.get = AsyncMock(side_effect=error)
    return LiveValidator(public_client=client)


# ===== Validation Result Tests =====

class TestLiveValidation:
    async def test_valid_event_returns_valid(self):
        """Live event → ValidationResult.VALID."""
        validator = _make_validator(response_data={"closed": False, "active": True})
        outcome = await validator.validate_event("0xabc")

        assert outcome.result == ValidationResult.VALID
        assert outcome.condition_id == "0xabc"
        assert "live" in outcome.reason.lower() or "confirmed" in outcome.reason.lower()
        assert outcome.health_incident is None

    async def test_closed_event_returns_invalid(self):
        """Closed event → ValidationResult.INVALID."""
        validator = _make_validator(response_data={"closed": True, "active": False})
        outcome = await validator.validate_event("0xabc")

        assert outcome.result == ValidationResult.INVALID
        assert outcome.health_incident is None

    async def test_empty_response_returns_invalid(self):
        """Empty API response → INVALID."""
        validator = _make_validator(response_data={})
        outcome = await validator.validate_event("0xabc")

        assert outcome.result == ValidationResult.INVALID

    async def test_none_response_returns_invalid(self):
        """None/falsy response → INVALID."""
        validator = _make_validator(response_data=None)
        # Need to handle None differently
        client = PublicMarketClient(base_url="https://test.api")
        mock_response = MagicMock()
        mock_response.json.return_value = None
        client.get = AsyncMock(return_value=mock_response)
        validator = LiveValidator(public_client=client)

        outcome = await validator.validate_event("0xabc")
        assert outcome.result == ValidationResult.INVALID


# ===== Source Error Tests =====

class TestValidationSourceErrors:
    async def test_client_error_returns_error_with_health_incident(self):
        """API failure → ERROR + HealthIncident."""
        validator = _make_validator(error=ClientError(
            "Connection failed",
            category=ErrorCategory.NETWORK,
            retryable=True,
            source="public_market",
        ))
        outcome = await validator.validate_event("0xabc")

        assert outcome.result == ValidationResult.ERROR
        assert outcome.health_incident is not None
        assert outcome.health_incident.severity == HealthSeverity.WARNING
        assert outcome.health_incident.category == "validation"
        assert outcome.health_incident.suggested_action != ""

    async def test_unexpected_error_returns_error_with_health_incident(self):
        """Unexpected error → ERROR + HealthIncident."""
        validator = _make_validator(error=RuntimeError("Boom"))
        outcome = await validator.validate_event("0xabc")

        assert outcome.result == ValidationResult.ERROR
        assert outcome.health_incident is not None
        assert outcome.health_incident.severity == HealthSeverity.WARNING

    async def test_error_does_not_claim_valid(self):
        """On error, result is never VALID — no silent active promotion."""
        validator = _make_validator(error=ClientError(
            "Timeout", category=ErrorCategory.TIMEOUT, retryable=True, source="test",
        ))
        outcome = await validator.validate_event("0xabc")

        assert outcome.result != ValidationResult.VALID


# ===== Registry Integration Tests =====

class TestValidationRegistryIntegration:
    """Test that validation results integrate correctly with registry transitions."""

    def _make_candidate(self, condition_id="0xabc"):
        return DiscoveredEvent(
            condition_id=condition_id, question="Will BTC go up in 5 min?",
            slug="btc-5m", asset="BTC", duration="5m", category="crypto",
            end_date=datetime(2026, 4, 4, 12, 5, 0, tzinfo=timezone.utc),
            discovered_at=datetime(2026, 4, 4, 12, 0, 0, tzinfo=timezone.utc),
        )

    async def test_valid_result_allows_active_transition(self):
        """VALID validation → VALIDATING → ACTIVE is allowed."""
        registry = EventRegistry()
        registry.register_candidate(self._make_candidate())
        registry.transition_event("0xabc", EventStatus.VALIDATING)

        # Simulate valid validation
        outcome = ValidationOutcome(
            condition_id="0xabc", result=ValidationResult.VALID, reason="Live"
        )

        if outcome.result == ValidationResult.VALID:
            record = registry.transition_event("0xabc", EventStatus.ACTIVE)
            assert record.status == EventStatus.ACTIVE

    async def test_invalid_result_transitions_to_inactive(self):
        """INVALID validation → VALIDATING → INACTIVE."""
        registry = EventRegistry()
        registry.register_candidate(self._make_candidate())
        registry.transition_event("0xabc", EventStatus.VALIDATING)

        outcome = ValidationOutcome(
            condition_id="0xabc", result=ValidationResult.INVALID, reason="Closed"
        )

        if outcome.result == ValidationResult.INVALID:
            record = registry.transition_event("0xabc", EventStatus.INACTIVE)
            assert record.status == EventStatus.INACTIVE

    async def test_error_result_keeps_validating(self):
        """ERROR validation → event stays VALIDATING, no silent active."""
        registry = EventRegistry()
        registry.register_candidate(self._make_candidate())
        registry.transition_event("0xabc", EventStatus.VALIDATING)

        outcome = ValidationOutcome(
            condition_id="0xabc", result=ValidationResult.ERROR, reason="Source down"
        )

        if outcome.result == ValidationResult.ERROR:
            record = registry.get_by_condition_id("0xabc")
            assert record.status == EventStatus.VALIDATING  # NOT promoted

    async def test_discovered_cannot_skip_to_active(self):
        """DISCOVERED → ACTIVE is not allowed (must go through VALIDATING)."""
        registry = EventRegistry()
        registry.register_candidate(self._make_candidate())

        with pytest.raises(InvalidTransitionError):
            registry.transition_event("0xabc", EventStatus.ACTIVE)


# ===== Outcome Model Tests =====

class TestValidationOutcome:
    def test_outcome_is_frozen(self):
        outcome = ValidationOutcome(
            condition_id="0x1", result=ValidationResult.VALID, reason="test"
        )
        with pytest.raises(AttributeError):
            outcome.result = ValidationResult.INVALID

    def test_outcome_has_timestamp(self):
        outcome = ValidationOutcome(
            condition_id="0x1", result=ValidationResult.VALID, reason="test"
        )
        assert outcome.validated_at is not None


# ===== Boundary Tests =====

class TestValidatorBoundaries:
    def test_no_market_data_import(self):
        import backend.discovery.live_validator as mod
        import_lines = [l.strip() for l in open(mod.__file__).readlines()
                        if l.strip().startswith(("import ", "from "))]
        for line in import_lines:
            assert "market_data" not in line
            assert "ptb" not in line

    def test_no_execution_import(self):
        import backend.discovery.live_validator as mod
        import_lines = [l.strip() for l in open(mod.__file__).readlines()
                        if l.strip().startswith(("import ", "from "))]
        for line in import_lines:
            assert "execution" not in line

    def test_no_strategy_import(self):
        import backend.discovery.live_validator as mod
        import_lines = [l.strip() for l in open(mod.__file__).readlines()
                        if l.strip().startswith(("import ", "from "))]
        for line in import_lines:
            assert "strategy" not in line

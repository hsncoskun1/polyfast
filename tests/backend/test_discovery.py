"""Tests for discovery engine — event scanning, filtering, boundaries."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from backend.auth_clients.public_client import PublicMarketClient
from backend.auth_clients.errors import ClientError, ErrorCategory
from backend.discovery.models import DiscoveredEvent, _extract_asset, _extract_duration
from backend.discovery.engine import DiscoveryEngine, DiscoveryResult
from backend.domain.startup_guard import HealthSeverity


def _make_raw_event(
    condition_id: str = "0x123",
    question: str = "Will BTC go up in the next 5 minutes?",
    slug: str = "btc-5m-up",
    category: str = "crypto",
    end_date: str = "2026-04-04T12:05:00Z",
) -> dict:
    return {
        "conditionId": condition_id,
        "question": question,
        "slug": slug,
        "category": category,
        "endDate": end_date,
    }


def _make_engine(events: list[dict] | None = None, error: Exception | None = None) -> DiscoveryEngine:
    client = PublicMarketClient(base_url="https://test.api")
    mock_response = MagicMock()
    if events is not None:
        mock_response.json.return_value = events
        client.get = AsyncMock(return_value=mock_response)
    elif error is not None:
        client.get = AsyncMock(side_effect=error)
    return DiscoveryEngine(public_client=client)


# ===== DiscoveredEvent Model Tests =====

class TestDiscoveredEventModel:
    def test_from_api_event_valid(self):
        raw = _make_raw_event()
        event = DiscoveredEvent.from_api_event(raw)
        assert event is not None
        assert event.condition_id == "0x123"
        assert event.asset == "BTC"
        assert event.duration == "5m"
        assert event.category == "crypto"

    def test_from_api_event_returns_none_on_invalid(self):
        event = DiscoveredEvent.from_api_event(None)
        assert event is None

    def test_frozen_model(self):
        raw = _make_raw_event()
        event = DiscoveredEvent.from_api_event(raw)
        with pytest.raises(AttributeError):
            event.asset = "ETH"

    def test_extract_asset_btc(self):
        assert _extract_asset({"question": "Will BTC go up?"}) == "BTC"

    def test_extract_asset_eth(self):
        assert _extract_asset({"question": "Will ETH go down?"}) == "ETH"

    def test_extract_asset_unknown(self):
        assert _extract_asset({"question": "Will gold go up?"}) == "UNKNOWN"

    def test_extract_duration_5m(self):
        assert _extract_duration({"question": "in the next 5 minutes"}) == "5m"

    def test_extract_duration_15m(self):
        assert _extract_duration({"question": "in the next 15 minutes"}) == "15m"

    def test_extract_duration_unknown(self):
        assert _extract_duration({"question": "some question"}) == "unknown"


# ===== DiscoveryEngine — Successful Scan =====

class TestDiscoveryEngineScan:
    async def test_scan_finds_matching_events(self):
        """5M Crypto Up/Down events are matched."""
        engine = _make_engine(events=[
            _make_raw_event(condition_id="1", question="Will BTC go up in the next 5 minutes?"),
            _make_raw_event(condition_id="2", question="Will ETH go down in the next 5 minutes?"),
        ])
        result = await engine.scan()

        assert result.success is True
        assert result.total_scanned == 2
        assert result.total_matched == 2
        assert len(result.events) == 2

    async def test_scan_filters_non_5m(self):
        """Non-5M events are filtered out."""
        engine = _make_engine(events=[
            _make_raw_event(question="Will BTC go up in the next 5 minutes?"),
            _make_raw_event(question="Will BTC go up in the next 1 hour?"),
        ])
        result = await engine.scan()

        assert result.total_scanned == 2
        assert result.total_matched == 1
        assert result.events[0].duration == "5m"

    async def test_scan_filters_non_crypto(self):
        """Non-crypto events are filtered out."""
        engine = _make_engine(events=[
            _make_raw_event(question="Will BTC go up in the next 5 minutes?", category="crypto"),
            _make_raw_event(question="Will team X win in 5 minutes?", category="sports"),
        ])
        result = await engine.scan()

        assert result.total_matched == 1
        assert result.events[0].category == "crypto"

    async def test_scan_filters_non_updown(self):
        """Events without Up/Down keywords are filtered out."""
        engine = _make_engine(events=[
            _make_raw_event(question="Will BTC go up in the next 5 minutes?"),
            _make_raw_event(question="BTC price at 5 minutes mark"),
        ])
        result = await engine.scan()

        assert result.total_matched == 1

    async def test_scan_empty_result(self):
        """No events from API → empty result, still success."""
        engine = _make_engine(events=[])
        result = await engine.scan()

        assert result.success is True
        assert result.total_matched == 0
        assert len(result.events) == 0


# ===== DiscoveryEngine — Failure Handling =====

class TestDiscoveryEngineFailure:
    async def test_api_failure_returns_error_result(self):
        """API failure → success=False, no silent bypass."""
        engine = _make_engine(error=ClientError(
            "Connection failed",
            category=ErrorCategory.NETWORK,
            retryable=True,
            source="public_market",
        ))
        result = await engine.scan()

        assert result.success is False
        assert "Connection failed" in result.error_message
        assert len(result.events) == 0

    async def test_api_failure_produces_health_incident(self):
        """API failure → HealthIncident with WARNING severity and discovery category."""
        engine = _make_engine(error=ClientError(
            "Connection failed",
            category=ErrorCategory.NETWORK,
            retryable=True,
            source="public_market",
        ))
        result = await engine.scan()

        assert len(result.health_incidents) == 1
        incident = result.health_incidents[0]
        assert incident.severity == HealthSeverity.WARNING
        assert incident.category == "discovery"
        assert "failed" in incident.message.lower()
        assert incident.suggested_action != ""

    async def test_unexpected_error_produces_health_incident(self):
        """Unexpected error → also produces HealthIncident."""
        engine = _make_engine(error=RuntimeError("Unexpected"))
        result = await engine.scan()

        assert result.success is False
        assert len(result.health_incidents) == 1
        assert result.health_incidents[0].severity == HealthSeverity.WARNING

    async def test_unexpected_error_returns_error_result(self):
        """Unexpected exception → success=False."""
        engine = _make_engine(error=RuntimeError("Unexpected"))
        result = await engine.scan()

        assert result.success is False
        assert "Unexpected" in result.error_message

    async def test_failure_does_not_return_partial_events(self):
        """On failure, no events are returned (no partial results)."""
        engine = _make_engine(error=ClientError(
            "Timeout",
            category=ErrorCategory.TIMEOUT,
            retryable=True,
            source="public_market",
        ))
        result = await engine.scan()

        assert len(result.events) == 0

    async def test_success_has_no_health_incidents(self):
        """Successful scan → no health incidents."""
        engine = _make_engine(events=[
            _make_raw_event(question="Will BTC go up in the next 5 minutes?"),
        ])
        result = await engine.scan()

        assert result.success is True
        assert len(result.health_incidents) == 0


# ===== Parse Failure Tests =====

class TestDiscoveryParseFailures:
    async def test_parse_failure_counted(self):
        """Unparseable events are counted in parse_failures."""
        engine = _make_engine(events=[
            _make_raw_event(question="Will BTC go up in the next 5 minutes?"),
            None,  # will cause from_api_event to return None
            "invalid_string",  # will cause from_api_event to return None
        ])
        result = await engine.scan()

        assert result.parse_failures == 2
        assert result.total_scanned == 3
        assert result.total_matched == 1

    async def test_parse_failure_does_not_pollute_events(self):
        """Parse failures don't add anything to events list."""
        engine = _make_engine(events=[None, None])
        result = await engine.scan()

        assert len(result.events) == 0
        assert result.parse_failures == 2
        assert result.success is True  # parse fail != scan fail


# ===== Boundary Tests =====

class TestDiscoveryBoundaries:
    def test_uses_public_client_only(self):
        """DiscoveryEngine uses PublicMarketClient, not Trading or Relayer."""
        import backend.discovery.engine as mod
        source = open(mod.__file__).read()
        import_lines = [l.strip() for l in source.splitlines() if l.strip().startswith(("import ", "from "))]
        for line in import_lines:
            assert "trading_client" not in line
            assert "relayer_client" not in line

    def test_no_registry_coupling(self):
        """Discovery engine does not import registry."""
        import backend.discovery.engine as mod
        import_lines = [l.strip() for l in open(mod.__file__).readlines() if l.strip().startswith(("import ", "from "))]
        for line in import_lines:
            assert "registry" not in line.lower()

    def test_no_market_data_coupling(self):
        """Discovery engine does not import market_data or ptb."""
        import backend.discovery.engine as mod
        import_lines = [l.strip() for l in open(mod.__file__).readlines() if l.strip().startswith(("import ", "from "))]
        for line in import_lines:
            assert "market_data" not in line
            assert "ptb" not in line

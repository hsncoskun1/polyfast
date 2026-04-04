"""Tests for discovery engine — adapted to real Polymarket Gamma API structure."""

import pytest
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

# Generate a future timestamp for test slugs (current time + 60s = still live)
_TEST_TS = str(int(time.time()) + 60)

from backend.auth_clients.public_client import PublicMarketClient
from backend.auth_clients.errors import ClientError, ErrorCategory
from backend.discovery.models import (
    DiscoveredEvent,
    _extract_category_from_tags,
    _extract_duration_from_tags,
    _extract_asset_from_slug,
)
from backend.discovery.engine import DiscoveryEngine, DiscoveryResult
from backend.domain.startup_guard import HealthSeverity


def _make_raw_event(
    condition_id: str = "0x123",
    title: str = "Bitcoin Up or Down - April 4, 3AM ET",
    slug: str | None = None,
    tags: list | None = None,
    outcomes: list | None = None,
    clob_token_ids: list | None = None,
    end_date: str = "2026-04-04T12:05:00Z",
) -> dict:
    if tags is None:
        tags = [
            {"slug": "up-or-down", "label": "Up or Down"},
            {"slug": "crypto", "label": "Crypto"},
            {"slug": "5M", "label": "5M"},
        ]
    if outcomes is None:
        outcomes = '["Up", "Down"]'
    if slug is None:
        slug = f"btc-updown-5m-{_TEST_TS}"
    if clob_token_ids is None:
        clob_token_ids = '["tok_up_123", "tok_down_456"]'
    return {
        "title": title,
        "slug": slug,
        "tags": tags,
        "endDate": end_date,
        "markets": [{
            "conditionId": condition_id,
            "question": title,
            "slug": slug,
            "outcomes": outcomes,
            "clobTokenIds": clob_token_ids,
        }],
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
        assert event.outcomes == ("Up", "Down")

    def test_from_api_event_returns_none_on_invalid(self):
        event = DiscoveredEvent.from_api_event(None)
        assert event is None

    def test_from_api_event_returns_none_without_condition_id(self):
        raw = _make_raw_event()
        raw["markets"][0]["conditionId"] = ""
        event = DiscoveredEvent.from_api_event(raw)
        assert event is None

    def test_frozen_model(self):
        raw = _make_raw_event()
        event = DiscoveredEvent.from_api_event(raw)
        with pytest.raises(AttributeError):
            event.asset = "ETH"

    def test_extract_category_from_tags(self):
        tags = [{"slug": "crypto"}, {"slug": "5M"}]
        assert _extract_category_from_tags(tags) == "crypto"

    def test_extract_category_unknown(self):
        tags = [{"slug": "sports"}]
        assert _extract_category_from_tags(tags) == "unknown"

    def test_extract_duration_5m(self):
        tags = [{"slug": "5M"}, {"slug": "crypto"}]
        assert _extract_duration_from_tags(tags) == "5m"

    def test_extract_duration_unknown(self):
        tags = [{"slug": "crypto"}]
        assert _extract_duration_from_tags(tags) == "unknown"

    def test_extract_asset_from_slug(self):
        assert _extract_asset_from_slug("btc-updown-5m-123", "") == "BTC"
        assert _extract_asset_from_slug("eth-updown-5m-456", "") == "ETH"
        assert _extract_asset_from_slug("sol-updown-5m-789", "") == "SOL"

    def test_extract_asset_from_title_fallback(self):
        assert _extract_asset_from_slug("unknown-slug", "Bitcoin Up or Down") == "BTC"
        assert _extract_asset_from_slug("unknown-slug", "Ethereum Up or Down") == "ETH"

    def test_clob_token_ids_parsed(self):
        raw = _make_raw_event()
        event = DiscoveredEvent.from_api_event(raw)
        assert len(event.clob_token_ids) == 2
        assert event.clob_token_ids[0] == "tok_up_123"


# ===== DiscoveryEngine — Successful Scan =====

class TestDiscoveryEngineScan:
    async def test_scan_finds_matching_events(self):
        engine = _make_engine(events=[
            _make_raw_event(condition_id="1"),
            _make_raw_event(condition_id="2", title="Ethereum Up or Down"),
        ])
        result = await engine.scan()
        assert result.success is True
        assert result.total_matched == 2

    async def test_scan_filters_non_5m(self):
        engine = _make_engine(events=[
            _make_raw_event(tags=[{"slug": "crypto"}, {"slug": "5M"}, {"slug": "up-or-down"}]),
            _make_raw_event(tags=[{"slug": "crypto"}, {"slug": "1h"}, {"slug": "up-or-down"}]),
        ])
        result = await engine.scan()
        assert result.total_matched == 1

    async def test_scan_filters_non_crypto(self):
        engine = _make_engine(events=[
            _make_raw_event(tags=[{"slug": "crypto"}, {"slug": "5M"}]),
            _make_raw_event(tags=[{"slug": "sports"}, {"slug": "5M"}]),
        ])
        result = await engine.scan()
        assert result.total_matched == 1

    async def test_scan_empty_result(self):
        engine = _make_engine(events=[])
        result = await engine.scan()
        assert result.success is True
        assert result.total_matched == 0


# ===== DiscoveryEngine — Failure Handling =====

class TestDiscoveryEngineFailure:
    async def test_api_failure_returns_error_result(self):
        engine = _make_engine(error=ClientError(
            "Connection failed", category=ErrorCategory.NETWORK,
            retryable=True, source="public_market",
        ))
        result = await engine.scan()
        assert result.success is False
        assert len(result.events) == 0

    async def test_api_failure_produces_health_incident(self):
        engine = _make_engine(error=ClientError(
            "Connection failed", category=ErrorCategory.NETWORK,
            retryable=True, source="public_market",
        ))
        result = await engine.scan()
        assert len(result.health_incidents) == 1
        assert result.health_incidents[0].severity == HealthSeverity.WARNING

    async def test_success_has_no_health_incidents(self):
        engine = _make_engine(events=[_make_raw_event()])
        result = await engine.scan()
        assert len(result.health_incidents) == 0


# ===== Parse Failure Tests =====

class TestDiscoveryParseFailures:
    async def test_parse_failure_counted(self):
        engine = _make_engine(events=[
            _make_raw_event(),
            None,
            "invalid",
        ])
        result = await engine.scan()
        assert result.parse_failures == 2
        assert result.total_matched == 1

    async def test_parse_failure_does_not_pollute_events(self):
        engine = _make_engine(events=[None, None])
        result = await engine.scan()
        assert len(result.events) == 0
        assert result.parse_failures == 2
        assert result.success is True


# ===== Boundary Tests =====

class TestDiscoveryBoundaries:
    def test_uses_public_client_only(self):
        import backend.discovery.engine as mod
        import_lines = [l.strip() for l in open(mod.__file__).readlines()
                        if l.strip().startswith(("import ", "from "))]
        for line in import_lines:
            assert "trading_client" not in line
            assert "relayer_client" not in line

    def test_no_registry_coupling(self):
        import backend.discovery.engine as mod
        import_lines = [l.strip() for l in open(mod.__file__).readlines()
                        if l.strip().startswith(("import ", "from "))]
        for line in import_lines:
            assert "registry" not in line.lower()

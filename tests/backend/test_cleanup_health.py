"""Cleanup + Health + Registry Expiration tests — v0.4.4."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from backend.orchestrator.cleanup import EventCleanup
from backend.orchestrator.health import HealthAggregator, OrchestratorHealth
from backend.market_data.live_price import LivePricePipeline
from backend.market_data.ws_price_bridge import WSPriceBridge
from backend.ptb.fetcher import PTBFetcher
from backend.ptb.source_adapter import PTBFetchResult
from backend.registry.service import EventRegistry
from backend.registry.models import EventStatus
from backend.discovery.models import DiscoveredEvent


# ═══════════════════════════════════════════════════════════════
# EVENT CLEANUP
# ═══════════════════════════════════════════════════════════════

class TestEventCleanup:

    def test_cleanup_clears_pipeline(self):
        pipeline = LivePricePipeline()
        pipeline.update_from_ws("0x1", "BTC", "up", best_bid=0.85, best_ask=0.86)
        assert pipeline.get_record("0x1") is not None

        ptb = MagicMock()
        bridge = WSPriceBridge(pipeline)

        cleanup = EventCleanup(pipeline, ptb, bridge)
        cleanup.cleanup_event("0x1")

        assert pipeline.get_record("0x1") is None
        ptb.clear_event.assert_called_once_with("0x1")

    def test_cleanup_clears_bridge_tokens(self):
        pipeline = LivePricePipeline()
        bridge = WSPriceBridge(pipeline)
        bridge.register_token("tok1", "0x1", "BTC", "up")
        bridge.register_token("tok2", "0x1", "BTC", "down")
        bridge.register_token("tok3", "0x2", "ETH", "up")
        assert bridge.registered_count == 3

        ptb = MagicMock()
        cleanup = EventCleanup(pipeline, ptb, bridge)
        cleanup.cleanup_event("0x1")

        # Only 0x1 tokens removed, 0x2 (ETH) stays
        assert bridge.registered_count == 1
        assert "tok3" in bridge.registered_token_ids

    def test_cleanup_does_not_touch_coin_client(self):
        """CoinPriceClient'a DOKUNMAZ."""
        import backend.orchestrator.cleanup as mod
        lines = [l.strip() for l in open(mod.__file__, encoding="utf-8").readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "coin_price" not in line

    def test_cleanup_counter(self):
        pipeline = LivePricePipeline()
        ptb = MagicMock()
        bridge = WSPriceBridge(pipeline)
        cleanup = EventCleanup(pipeline, ptb, bridge)

        cleanup.cleanup_event("0x1")
        cleanup.cleanup_event("0x2")
        assert cleanup.total_cleaned == 2

    def test_cleanup_multiple_expired(self):
        pipeline = LivePricePipeline()
        pipeline.update_from_ws("0x1", "BTC", "up", best_bid=0.85, best_ask=0.86)
        pipeline.update_from_ws("0x2", "ETH", "up", best_bid=0.60, best_ask=0.61)
        ptb = MagicMock()
        bridge = WSPriceBridge(pipeline)

        cleanup = EventCleanup(pipeline, ptb, bridge)
        count = cleanup.cleanup_expired_events(["0x1", "0x2"])

        assert count == 2
        assert pipeline.get_record("0x1") is None
        assert pipeline.get_record("0x2") is None


# ═══════════════════════════════════════════════════════════════
# REGISTRY EXPIRATION
# ═══════════════════════════════════════════════════════════════

class TestRegistryExpiration:

    def _make_event(self, cond_id, asset, end_date):
        return DiscoveredEvent(
            condition_id=cond_id,
            question=f"{asset} up or down?",
            slug=f"{asset.lower()}-updown-5m-123",
            asset=asset,
            duration="5m",
            category="crypto",
            end_date=end_date,
            discovered_at=datetime.now(timezone.utc),
            clob_token_ids=("tok1", "tok2"),
            outcomes=("Up", "Down"),
        )

    def test_expire_past_events(self):
        registry = EventRegistry()
        past = self._make_event("0x1", "BTC", datetime.now(timezone.utc) - timedelta(minutes=5))
        registry.register_candidate(past)
        registry.transition_event("0x1", EventStatus.VALIDATING)
        registry.transition_event("0x1", EventStatus.ACTIVE)

        expired = registry.expire_events(datetime.now(timezone.utc))
        assert "0x1" in expired
        assert registry.get_by_condition_id("0x1").status == EventStatus.EXPIRED

    def test_do_not_expire_future_events(self):
        registry = EventRegistry()
        future = self._make_event("0x2", "ETH", datetime.now(timezone.utc) + timedelta(minutes=5))
        registry.register_candidate(future)
        registry.transition_event("0x2", EventStatus.VALIDATING)
        registry.transition_event("0x2", EventStatus.ACTIVE)

        expired = registry.expire_events(datetime.now(timezone.utc))
        assert len(expired) == 0
        assert registry.get_by_condition_id("0x2").status == EventStatus.ACTIVE

    def test_already_expired_skipped(self):
        registry = EventRegistry()
        past = self._make_event("0x1", "BTC", datetime.now(timezone.utc) - timedelta(minutes=5))
        registry.register_candidate(past)
        registry.transition_event("0x1", EventStatus.VALIDATING)
        registry.transition_event("0x1", EventStatus.ACTIVE)
        registry.transition_event("0x1", EventStatus.EXPIRED)

        expired = registry.expire_events(datetime.now(timezone.utc))
        assert len(expired) == 0  # zaten expired


# ═══════════════════════════════════════════════════════════════
# HEALTH AGGREGATION
# ═══════════════════════════════════════════════════════════════

class TestHealthAggregator:

    def test_empty_health(self):
        agg = HealthAggregator()
        health = agg.aggregate()
        assert health.discovery_running is False
        assert health.is_healthy is False

    def test_healthy_state(self):
        disc = MagicMock()
        disc.is_running = True
        disc.scan_count = 5
        disc.events_found = 3
        disc.get_health_incidents.return_value = []

        coin = MagicMock()
        coin.fresh_count = 6
        coin.stale_count = 0
        coin.total_updates = 100
        coin.get_health_incidents.return_value = []

        agg = HealthAggregator()
        health = agg.aggregate(discovery_loop=disc, coin_client=coin)

        assert health.is_healthy is True
        assert health.discovery_running is True
        assert health.coin_usd_fresh_count == 6
        assert health.coin_usd_stale_count == 0

    def test_unhealthy_stale_coins(self):
        disc = MagicMock()
        disc.is_running = True
        disc.scan_count = 5
        disc.events_found = 3
        disc.get_health_incidents.return_value = []

        coin = MagicMock()
        coin.fresh_count = 3
        coin.stale_count = 3  # stale!
        coin.total_updates = 50
        coin.get_health_incidents.return_value = []

        agg = HealthAggregator()
        health = agg.aggregate(discovery_loop=disc, coin_client=coin)

        assert health.is_healthy is False  # stale coins

    def test_health_frozen(self):
        health = OrchestratorHealth()
        with pytest.raises(AttributeError):
            health.discovery_running = True

    def test_no_execution_coupling(self):
        import backend.orchestrator.health as mod
        lines = [l.strip() for l in open(mod.__file__, encoding="utf-8").readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "execution" not in line
            assert "position" not in line
            assert "order" not in line

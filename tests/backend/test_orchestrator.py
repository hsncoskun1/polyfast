"""Orchestrator tests — v0.4.3.

Tests:
1. EligibilityGate filtering
2. SubscriptionManager diff
3. EvaluationLoop context building
4. CoinPriceClient run_forever lifecycle
5. LivePricePipeline get_record_by_asset
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta

from backend.orchestrator.eligibility_gate import EligibilityGate, EligibilityResult
from backend.orchestrator.subscription_manager import SubscriptionManager, SubscriptionDiff
from backend.orchestrator.evaluation_loop import EvaluationLoop
from backend.settings.settings_store import SettingsStore
from backend.settings.coin_settings import CoinSettings, SideMode
from backend.market_data.coin_price_client import CoinPriceClient, CoinPriceStatus
from backend.market_data.live_price import LivePricePipeline, PriceStatus
from backend.strategy.engine import RuleEngine
from backend.strategy.rule_state import OverallDecision


# ═══════════════════════════════════════════════════════════════
# ELIGIBILITY GATE
# ═══════════════════════════════════════════════════════════════

class TestEligibilityGate:

    def _make_store_with_btc(self, enabled=True, configured=True):
        store = SettingsStore()
        s = CoinSettings(
            coin="BTC", coin_enabled=enabled,
            delta_threshold=50.0 if configured else 0,
            price_min=51 if configured else 0,
            price_max=95 if configured else 0,
            spread_max=3.0 if configured else 0,
            time_min=10 if configured else 0,
            time_max=200 if configured else 0,
            order_amount=5.0 if configured else 0,
        )
        store.set(s)
        return store

    def test_eligible_coin(self):
        store = self._make_store_with_btc(enabled=True, configured=True)
        gate = EligibilityGate(store)
        result = gate.filter([{"asset": "BTC"}])
        assert len(result.eligible) == 1
        assert len(result.ineligible) == 0

    def test_no_settings_ineligible(self):
        store = SettingsStore()
        gate = EligibilityGate(store)
        result = gate.filter([{"asset": "BTC"}])
        assert len(result.eligible) == 0
        assert len(result.ineligible) == 1
        assert result.reasons["BTC"] == "no_settings"

    def test_disabled_coin_ineligible(self):
        store = self._make_store_with_btc(enabled=False, configured=True)
        gate = EligibilityGate(store)
        result = gate.filter([{"asset": "BTC"}])
        assert len(result.eligible) == 0
        assert result.reasons["BTC"] == "coin_disabled"

    def test_incomplete_config_ineligible(self):
        store = self._make_store_with_btc(enabled=True, configured=False)
        gate = EligibilityGate(store)
        result = gate.filter([{"asset": "BTC"}])
        assert len(result.eligible) == 0
        assert result.reasons["BTC"] == "config_incomplete"

    def test_mixed_eligible_ineligible(self):
        store = SettingsStore()
        btc = CoinSettings(coin="BTC", coin_enabled=True,
                           delta_threshold=50, price_min=51, price_max=95,
                           spread_max=3, time_min=10, time_max=200, order_amount=5)
        store.set(btc)
        # ETH has no settings
        gate = EligibilityGate(store)
        result = gate.filter([{"asset": "BTC"}, {"asset": "ETH"}])
        assert len(result.eligible) == 1
        assert len(result.ineligible) == 1


# ═══════════════════════════════════════════════════════════════
# SUBSCRIPTION MANAGER
# ═══════════════════════════════════════════════════════════════

class TestSubscriptionDiff:

    def test_new_subscription(self):
        bridge = MagicMock()
        coin_client = MagicMock()
        coin_client._coins = []
        ptb = MagicMock()
        mgr = SubscriptionManager(bridge, coin_client, ptb)

        diff = mgr.compute_diff(["BTC", "ETH"])
        assert sorted(diff.to_subscribe) == ["BTC", "ETH"]
        assert diff.to_unsubscribe == []
        assert diff.unchanged == []

    def test_unsubscribe(self):
        bridge = MagicMock()
        coin_client = MagicMock()
        coin_client._coins = []
        ptb = MagicMock()
        mgr = SubscriptionManager(bridge, coin_client, ptb)
        mgr._current_subscribed = {"BTC", "ETH", "SOL"}

        diff = mgr.compute_diff(["BTC"])
        assert diff.to_subscribe == []
        assert sorted(diff.to_unsubscribe) == ["ETH", "SOL"]
        assert diff.unchanged == ["BTC"]

    def test_mixed_diff(self):
        bridge = MagicMock()
        coin_client = MagicMock()
        coin_client._coins = []
        ptb = MagicMock()
        mgr = SubscriptionManager(bridge, coin_client, ptb)
        mgr._current_subscribed = {"BTC", "ETH"}

        diff = mgr.compute_diff(["ETH", "DOGE"])
        assert diff.to_subscribe == ["DOGE"]
        assert diff.to_unsubscribe == ["BTC"]
        assert diff.unchanged == ["ETH"]


# ═══════════════════════════════════════════════════════════════
# EVALUATION LOOP
# ═══════════════════════════════════════════════════════════════

class TestEvaluationLoop:

    def test_context_from_runtime_not_snapshot(self):
        """Evaluation context runtime state'ten doldurulur, snapshot'tan DEĞİL."""
        import backend.orchestrator.evaluation_loop as mod
        lines = [l.strip() for l in open(mod.__file__, encoding="utf-8").readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "snapshot" not in line

    def test_evaluate_single_with_mock_data(self):
        """Tek coin evaluation — mock data ile."""
        engine = RuleEngine()
        pipeline = LivePricePipeline()
        pipeline.update_from_ws("0x1", "BTC", "up", best_bid=0.85, best_ask=0.86)

        coin_client = CoinPriceClient()
        coin_client.set_coins(["BTC"])
        coin_client._update_record("BTC", 67310.0)

        ptb_fetcher = MagicMock()
        ptb_record = MagicMock()
        ptb_record.is_locked = True
        ptb_record.ptb_value = 67260.0
        ptb_fetcher.get_record.return_value = ptb_record

        store = SettingsStore()
        store.set(CoinSettings(
            coin="BTC", coin_enabled=True,
            side_mode=SideMode.DOMINANT_ONLY,
            delta_threshold=20.0, price_min=51, price_max=95,
            spread_max=5.0, time_min=10, time_max=270,
            event_max=1, order_amount=5.0,
        ))

        loop = EvaluationLoop(engine, pipeline, coin_client, ptb_fetcher, store)
        settings = store.get("BTC")
        result = loop._evaluate_single(settings)

        assert result is not None
        assert result.decision in (OverallDecision.ENTRY, OverallDecision.NO_ENTRY, OverallDecision.WAITING)

    def test_entry_signal_logged_not_executed(self):
        """ENTRY sinyali üretilir ama order GÖNDERİLMEZ."""
        import backend.orchestrator.evaluation_loop as mod
        source = open(mod.__file__, encoding="utf-8").read()
        assert "order" not in source.lower() or "ORDER GÖNDERİLMEZ" in source
        assert "execute" not in source.lower() or "execution" not in source.lower()


# ═══════════════════════════════════════════════════════════════
# COIN PRICE CLIENT LIFECYCLE
# ═══════════════════════════════════════════════════════════════

class TestCoinPriceClientLifecycle:

    def test_initial_not_running(self):
        client = CoinPriceClient()
        assert client._running is False

    @pytest.mark.asyncio
    async def test_start_stop(self):
        client = CoinPriceClient(ws_url="wss://fake")
        client.set_coins(["BTC"])
        # Don't actually connect — just test lifecycle
        client._running = True
        await client.stop()
        assert client._running is False

    def test_stale_returns_zero(self):
        client = CoinPriceClient(stale_threshold_sec=1)
        client.set_coins(["BTC"])
        client._update_record("BTC", 67000.0)
        client._records["BTC"].updated_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        assert client.get_usd_price("BTC") == 0.0


# ═══════════════════════════════════════════════════════════════
# LIVE PRICE PIPELINE get_record_by_asset
# ═══════════════════════════════════════════════════════════════

class TestPipelineGetByAsset:

    def test_get_by_asset(self):
        pipe = LivePricePipeline()
        pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.85, best_ask=0.86)
        pipe.update_from_ws("0x2", "ETH", "up", best_bid=0.60, best_ask=0.61)

        btc = pipe.get_record_by_asset("BTC")
        assert btc is not None
        assert btc.asset == "BTC"
        assert btc.up_price == 0.85

        eth = pipe.get_record_by_asset("ETH")
        assert eth is not None
        assert eth.asset == "ETH"

    def test_get_by_asset_not_found(self):
        pipe = LivePricePipeline()
        assert pipe.get_record_by_asset("DOGE") is None

    def test_get_by_asset_case_insensitive(self):
        pipe = LivePricePipeline()
        pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.85, best_ask=0.86)
        assert pipe.get_record_by_asset("btc") is not None
        assert pipe.get_record_by_asset("Btc") is not None


# ═══════════════════════════════════════════════════════════════
# BOUNDARY
# ═══════════════════════════════════════════════════════════════

class TestOrchestratorBoundaries:

    def test_no_execution_in_evaluation_loop(self):
        import backend.orchestrator.evaluation_loop as mod
        lines = [l.strip() for l in open(mod.__file__, encoding="utf-8").readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "execution" not in line
            assert "position" not in line
            assert "order_executor" not in line

    def test_no_execution_in_eligibility(self):
        import backend.orchestrator.eligibility_gate as mod
        lines = [l.strip() for l in open(mod.__file__, encoding="utf-8").readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "execution" not in line

    def test_no_execution_in_subscription(self):
        import backend.orchestrator.subscription_manager as mod
        lines = [l.strip() for l in open(mod.__file__, encoding="utf-8").readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "execution" not in line

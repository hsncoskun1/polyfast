"""Discovery Loop + Side Mode Wiring tests — v0.4.2.

Tests:
1. Discovery loop slot-aware behavior
2. Retry schedule
3. Slot boundary crossing during retry
4. Registry sync caller
5. Side mode wiring (EvaluationContext + PriceRule)
"""

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from backend.orchestrator.discovery_loop import (
    DiscoveryLoop,
    DEFAULT_RETRY_SCHEDULE,
    DEFAULT_RETRY_STEADY_INTERVAL,
    SLOT_SECONDS,
    _current_slot_start,
    _slot_remaining,
)
from backend.strategy.evaluation_context import EvaluationContext
from backend.strategy.rules.price_rule import PriceRule
from backend.strategy.rule_state import RuleState
from backend.settings.coin_settings import SideMode


# ═══════════════════════════════════════════════════════════════
# DISCOVERY LOOP TESTS
# ═══════════════════════════════════════════════════════════════

class TestDiscoveryLoopConstants:

    def test_retry_schedule(self):
        assert DEFAULT_RETRY_SCHEDULE == [2, 4, 8, 16]
        assert DEFAULT_RETRY_STEADY_INTERVAL == 10

    def test_slot_seconds(self):
        assert SLOT_SECONDS == 300

    def test_current_slot_start(self):
        now = int(time.time())
        slot = _current_slot_start()
        assert slot % 300 == 0
        assert slot <= now
        assert slot + 300 > now

    def test_slot_remaining(self):
        remaining = _slot_remaining()
        assert 0 <= remaining <= 300


class TestDiscoveryLoopLifecycle:

    def test_initial_state(self):
        engine = AsyncMock()
        sync = AsyncMock()
        loop = DiscoveryLoop(discovery_engine=engine, safe_sync=sync)
        assert loop.is_running is False
        assert loop.scan_count == 0
        assert loop.events_found == 0

    @pytest.mark.asyncio
    async def test_start_stop(self):
        engine = AsyncMock()
        sync = AsyncMock()
        loop = DiscoveryLoop(discovery_engine=engine, safe_sync=sync)

        await loop.start()
        assert loop.is_running is True

        await loop.stop()
        assert loop.is_running is False


class TestDiscoveryLoopScanWithRetry:

    @pytest.mark.asyncio
    async def test_events_found_immediately(self):
        """Event hemen bulunursa retry yok, True döner."""
        engine = AsyncMock()
        sync = AsyncMock()

        mock_result = MagicMock()
        mock_result.events = [{"slug": "btc-updown-5m-123"}]
        engine.scan.return_value = mock_result
        sync.sync.return_value = None

        loop = DiscoveryLoop(discovery_engine=engine, safe_sync=sync)
        loop._running = True  # simulate started state
        slot = _current_slot_start()
        found = await loop._scan_with_retry(slot)

        assert found is True
        assert engine.scan.call_count == 1
        assert loop.events_found == 1

    @pytest.mark.asyncio
    async def test_events_not_found_retries(self):
        """Event bulunamazsa retry schedule ile dener."""
        engine = AsyncMock()
        sync = AsyncMock()

        # İlk 2 deneme boş, 3. deneme bulur
        empty_result = MagicMock()
        empty_result.events = []
        found_result = MagicMock()
        found_result.events = [{"slug": "btc-updown-5m-123"}]

        engine.scan.side_effect = [empty_result, empty_result, found_result]
        sync.sync.return_value = None

        loop = DiscoveryLoop(discovery_engine=engine, safe_sync=sync)
        loop._running = True

        with patch("backend.orchestrator.discovery_loop._current_slot_start",
                    return_value=_current_slot_start()):
            with patch("backend.orchestrator.discovery_loop.asyncio.sleep",
                       new_callable=AsyncMock):
                found = await loop._scan_with_retry(_current_slot_start())

        assert found is True
        assert engine.scan.call_count == 3

    @pytest.mark.asyncio
    async def test_slot_boundary_stops_retry(self):
        """Retry sırasında slot boundary aşılırsa retry DUR."""
        engine = AsyncMock()
        sync = AsyncMock()

        empty_result = MagicMock()
        empty_result.events = []
        engine.scan.return_value = empty_result

        loop = DiscoveryLoop(discovery_engine=engine, safe_sync=sync)
        original_slot = _current_slot_start()

        # İlk scan'dan sonra slot değişmiş gibi davran
        call_count = 0
        def slot_changes():
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return original_slot  # ilk çağrı aynı slot
            return original_slot + 300  # sonraki çağrılar yeni slot

        with patch("backend.orchestrator.discovery_loop._current_slot_start",
                    side_effect=slot_changes):
            with patch("backend.orchestrator.discovery_loop.asyncio.sleep",
                       new_callable=AsyncMock):
                found = await loop._scan_with_retry(original_slot)

        assert found is False  # slot boundary → dur

    @pytest.mark.asyncio
    async def test_scan_failure_retries(self):
        """Discovery scan exception durumunda retry devam eder."""
        engine = AsyncMock()
        sync = AsyncMock()

        found_result = MagicMock()
        found_result.events = [{"slug": "test"}]
        engine.scan.side_effect = [Exception("API error"), found_result]
        sync.sync.return_value = None

        loop = DiscoveryLoop(discovery_engine=engine, safe_sync=sync)
        loop._running = True

        with patch("backend.orchestrator.discovery_loop._current_slot_start",
                    return_value=_current_slot_start()):
            with patch("backend.orchestrator.discovery_loop.asyncio.sleep",
                       new_callable=AsyncMock):
                found = await loop._scan_with_retry(_current_slot_start())

        assert found is True
        assert len(loop.get_health_incidents()) >= 1

    @pytest.mark.asyncio
    async def test_registry_sync_called(self):
        """Event bulununca registry sync çağrılır."""
        engine = AsyncMock()
        sync = AsyncMock()

        mock_result = MagicMock()
        events = [{"slug": "btc"}, {"slug": "eth"}]
        mock_result.events = events
        engine.scan.return_value = mock_result
        sync.sync.return_value = None

        loop = DiscoveryLoop(discovery_engine=engine, safe_sync=sync)
        await loop._sync_to_registry(events)

        sync.sync.assert_called_once_with(events)


# ═══════════════════════════════════════════════════════════════
# SIDE MODE WIRING TESTS
# ═══════════════════════════════════════════════════════════════

class TestSideModeContext:

    def test_dominant_only_default(self):
        ctx = EvaluationContext(up_price=0.85, down_price=0.15,
                                up_bid=0.85, up_ask=0.85, down_bid=0.15, down_ask=0.15)
        assert ctx.side_mode == SideMode.DOMINANT_ONLY
        assert ctx.evaluated_price == 0.85
        assert ctx.evaluated_side == "UP"
        assert ctx.evaluated_price_100 == 85.0

    def test_dominant_only_down_dominant(self):
        ctx = EvaluationContext(up_price=0.30, down_price=0.70,
                                up_bid=0.30, up_ask=0.30, down_bid=0.70, down_ask=0.70)
        assert ctx.evaluated_price == 0.70
        assert ctx.evaluated_side == "DOWN"

    def test_up_only(self):
        ctx = EvaluationContext(
            up_price=0.30, down_price=0.70,
            up_bid=0.30, up_ask=0.30, down_bid=0.70, down_ask=0.70,
            side_mode=SideMode.UP_ONLY,
        )
        # up_only → up_ask kullanılır (entry ref = ask)
        assert ctx.evaluated_price == 0.30
        assert ctx.evaluated_side == "UP"
        assert ctx.evaluated_price_100 == 30.0

    def test_down_only(self):
        ctx = EvaluationContext(
            up_price=0.85, down_price=0.15,
            up_bid=0.85, up_ask=0.85, down_bid=0.15, down_ask=0.15,
            side_mode=SideMode.DOWN_ONLY,
        )
        # down_only → down_ask kullanılır (entry ref = ask)
        assert ctx.evaluated_price == 0.15
        assert ctx.evaluated_side == "DOWN"
        assert ctx.evaluated_price_100 == 15.0

    def test_backward_compat_dominant_property(self):
        """dominant_* isimleri hâlâ çalışır."""
        ctx = EvaluationContext(up_price=0.85, down_price=0.15,
                                up_bid=0.85, up_ask=0.85, down_bid=0.15, down_ask=0.15)
        assert ctx.dominant_price == ctx.evaluated_price
        assert ctx.dominant_side == ctx.evaluated_side


class TestPriceRuleSideMode:

    def test_dominant_only_pass(self):
        rule = PriceRule()
        ctx = EvaluationContext(
            up_price=0.85, down_price=0.15,
            up_bid=0.85, up_ask=0.85, down_bid=0.15, down_ask=0.15,
            side_mode=SideMode.DOMINANT_ONLY,
            outcome_fresh=True,
            price_min=51, price_max=95, price_enabled=True,
        )
        result = rule.evaluate(ctx)
        assert result.state == RuleState.PASS
        assert result.detail["side_mode"] == "dominant_only"
        assert result.detail["evaluated_price_100"] == 85.0

    def test_up_only_low_up_price_pass(self):
        """UP only modunda up_ask=30 → min=1 max=99 → 30 aralıkta → PASS."""
        rule = PriceRule()
        ctx = EvaluationContext(
            up_price=0.30, down_price=0.70,
            up_bid=0.30, up_ask=0.30, down_bid=0.70, down_ask=0.70,
            side_mode=SideMode.UP_ONLY,
            outcome_fresh=True,
            price_min=1, price_max=99, price_enabled=True,
        )
        result = rule.evaluate(ctx)
        assert result.state == RuleState.PASS
        assert result.detail["evaluated_side"] == "UP"
        assert result.detail["evaluated_price_100"] == 30.0

    def test_up_only_below_min_fail(self):
        """UP only modunda up_ask=5 → min=10 → FAIL."""
        rule = PriceRule()
        ctx = EvaluationContext(
            up_price=0.05, down_price=0.95,
            up_bid=0.05, up_ask=0.05, down_bid=0.95, down_ask=0.95,
            side_mode=SideMode.UP_ONLY,
            outcome_fresh=True,
            price_min=10, price_max=99, price_enabled=True,
        )
        assert rule.evaluate(ctx).state == RuleState.FAIL

    def test_down_only_pass(self):
        """DOWN only modunda down_ask=70 → 51-99 → PASS."""
        rule = PriceRule()
        ctx = EvaluationContext(
            up_price=0.30, down_price=0.70,
            up_bid=0.30, up_ask=0.30, down_bid=0.70, down_ask=0.70,
            side_mode=SideMode.DOWN_ONLY,
            outcome_fresh=True,
            price_min=51, price_max=99, price_enabled=True,
        )
        result = rule.evaluate(ctx)
        assert result.state == RuleState.PASS
        assert result.detail["evaluated_side"] == "DOWN"

    def test_dominant_only_below_51_impossible(self):
        """Dominant always >= 0.50, so min=51 effectively filters near 50-50."""
        rule = PriceRule()
        ctx = EvaluationContext(
            up_price=0.50, down_price=0.50,
            up_bid=0.50, up_ask=0.50, down_bid=0.50, down_ask=0.50,
            side_mode=SideMode.DOMINANT_ONLY,
            outcome_fresh=True,
            price_min=51, price_max=95, price_enabled=True,
        )
        # dominant = 0.50 → 50 < 51 → FAIL
        assert rule.evaluate(ctx).state == RuleState.FAIL

    def test_side_mode_in_detail(self):
        """PriceRule result detail contains side_mode."""
        rule = PriceRule()
        ctx = EvaluationContext(
            up_price=0.85, down_price=0.15,
            up_bid=0.85, up_ask=0.85, down_bid=0.15, down_ask=0.15,
            side_mode=SideMode.DOMINANT_ONLY,
            outcome_fresh=True,
            price_min=51, price_max=95, price_enabled=True,
        )
        result = rule.evaluate(ctx)
        assert "side_mode" in result.detail


# ═══════════════════════════════════════════════════════════════
# BOUNDARY TESTS
# ═══════════════════════════════════════════════════════════════

class TestDiscoveryLoopBoundaries:

    def test_no_execution_coupling(self):
        import backend.orchestrator.discovery_loop as mod
        lines = [l.strip() for l in open(mod.__file__, encoding="utf-8").readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "execution" not in line
            assert "position" not in line
            assert "order" not in line

    def test_no_subscription_coupling(self):
        """Discovery loop does NOT manage subscriptions (v0.4.3)."""
        import backend.orchestrator.discovery_loop as mod
        lines = [l.strip() for l in open(mod.__file__, encoding="utf-8").readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "subscription" not in line
            assert "rtds_client" not in line
            assert "coin_price" not in line

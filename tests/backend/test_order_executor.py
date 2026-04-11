"""OrderExecutor + BalanceManager tests — v0.5.2."""

import pytest
from datetime import datetime, timezone, timedelta

from backend.execution.order_executor import (
    OrderExecutor, ExecutionMode, OrderResult, ExecutionResult,
)
from backend.execution.order_intent import OrderIntent, OrderSide
from backend.execution.order_validator import OrderValidator
from backend.execution.position_tracker import PositionTracker
from backend.execution.balance_manager import BalanceManager
from backend.execution.fee_rate_fetcher import FeeRateFetcher


def _make_intent(**overrides):
    defaults = dict(
        asset="BTC", side=OrderSide.UP, amount_usd=5.0,
        condition_id="0x1", token_id="tok1", dominant_price=0.85,
    )
    defaults.update(overrides)
    return OrderIntent(**defaults)


def _make_executor(mode=ExecutionMode.PAPER, balance=100.0):
    tracker = PositionTracker()
    balance_mgr = BalanceManager()
    balance_mgr.update(available=balance, total=balance)
    validator = OrderValidator()
    fee_fetcher = FeeRateFetcher()
    return OrderExecutor(tracker, balance_mgr, validator, fee_fetcher, mode=mode)


# ═══════════════════════════════════════════════════════════════
# PAPER MODE EXECUTION
# ═══════════════════════════════════════════════════════════════

class TestPaperExecution:

    @pytest.mark.asyncio
    async def test_paper_fill(self):
        executor = _make_executor()
        intent = _make_intent()
        result = await executor.execute(intent)

        assert result.result == OrderResult.FILLED
        assert result.position_id is not None
        assert result.fill_price == 0.85  # dominant_price
        assert result.fee_rate > 0
        assert executor.fill_count == 1

    @pytest.mark.asyncio
    async def test_paper_balance_deducted(self):
        executor = _make_executor(balance=100.0)
        await executor.execute(_make_intent(amount_usd=10.0))
        assert executor._balance.available_balance == 90.0

    @pytest.mark.asyncio
    async def test_paper_position_created(self):
        executor = _make_executor()
        result = await executor.execute(_make_intent())
        pos = executor._tracker.get_position(result.position_id)
        assert pos is not None
        assert pos.is_open
        assert pos.fill_price == 0.85
        assert pos.net_position_shares > 0

    @pytest.mark.asyncio
    async def test_paper_fee_aware(self):
        executor = _make_executor()
        result = await executor.execute(_make_intent(amount_usd=10.0))
        pos = executor._tracker.get_position(result.position_id)
        assert pos.entry_fee_shares > 0
        assert pos.net_position_shares < pos.gross_fill_shares


# ═══════════════════════════════════════════════════════════════
# VALIDATION GUARDS
# ═══════════════════════════════════════════════════════════════

class TestValidationGuards:

    @pytest.mark.asyncio
    async def test_balance_stale_rejected(self):
        executor = _make_executor()
        # Balance stale yap
        executor._balance._updated_at = datetime.now(timezone.utc) - timedelta(seconds=120)
        result = await executor.execute(_make_intent())
        assert result.result == OrderResult.BALANCE_STALE

    @pytest.mark.asyncio
    async def test_insufficient_balance_rejected(self):
        executor = _make_executor(balance=2.0)
        result = await executor.execute(_make_intent(amount_usd=5.0))
        assert result.result == OrderResult.REJECTED

    @pytest.mark.asyncio
    async def test_no_pending_on_reject(self):
        """Validator reject ise pending position OLUSMAZ."""
        executor = _make_executor(balance=2.0)
        await executor.execute(_make_intent(amount_usd=5.0))
        assert len(executor._tracker.get_all_positions()) == 0

    @pytest.mark.asyncio
    async def test_missing_token_rejected(self):
        executor = _make_executor()
        result = await executor.execute(_make_intent(token_id=""))
        assert result.result == OrderResult.REJECTED

    @pytest.mark.asyncio
    async def test_event_max_reached(self):
        executor = _make_executor()
        # İlk fill
        await executor.execute(_make_intent())
        # İkinci deneme — event_max=1
        result = await executor.execute(_make_intent())
        assert result.result == OrderResult.REJECTED


# ═══════════════════════════════════════════════════════════════
# COUNTERS
# ═══════════════════════════════════════════════════════════════

class TestExecutionCounters:

    @pytest.mark.asyncio
    async def test_fill_increments_counters(self):
        executor = _make_executor()
        await executor.execute(_make_intent())
        assert executor._tracker.get_event_fill_count("0x1") == 1
        assert executor._tracker.session_trade_count == 1
        assert executor._tracker.open_position_count == 1

    @pytest.mark.asyncio
    async def test_reject_no_counters(self):
        executor = _make_executor(balance=0.5)
        await executor.execute(_make_intent())
        assert executor._tracker.get_event_fill_count("0x1") == 0
        assert executor._tracker.session_trade_count == 0


# ═══════════════════════════════════════════════════════════════
# BALANCE MANAGER
# ═══════════════════════════════════════════════════════════════

class TestBalanceManager:

    def test_initial_stale(self):
        mgr = BalanceManager()
        assert mgr.is_stale is True
        assert mgr.available_balance == 0.0

    def test_update_fresh(self):
        mgr = BalanceManager()
        mgr.update(available=100.0, total=100.0)
        assert mgr.is_fresh is True
        assert mgr.available_balance == 100.0

    def test_stale_after_threshold(self):
        mgr = BalanceManager(stale_threshold_sec=10)
        mgr.update(available=100.0)
        mgr._updated_at = datetime.now(timezone.utc) - timedelta(seconds=15)
        assert mgr.is_stale is True

    def test_deduct(self):
        mgr = BalanceManager()
        mgr.update(available=100.0)
        mgr.deduct(30.0)
        assert mgr.available_balance == 70.0

    def test_add(self):
        mgr = BalanceManager()
        mgr.update(available=50.0)
        mgr.add(20.0)
        assert mgr.available_balance == 70.0

    def test_health_incident_stale(self):
        mgr = BalanceManager()
        incidents = mgr.get_health_incidents()
        assert len(incidents) >= 1  # stale


# ═══════════════════════════════════════════════════════════════
# LIVE MODE (placeholder)
# ═══════════════════════════════════════════════════════════════

class TestLiveMode:

    @pytest.mark.asyncio
    async def test_live_no_wrapper_returns_error(self):
        """Live mode clob_wrapper=None ise NETWORK_ERROR doner."""
        executor = _make_executor(mode=ExecutionMode.LIVE)
        result = await executor.execute(_make_intent())
        assert result.result == OrderResult.NETWORK_ERROR

    @pytest.mark.asyncio
    async def test_no_fee_fetch_in_live_path(self):
        """Live execution akisinda ayri fee fetch ADIMI YOK."""
        import backend.execution.order_executor as mod
        source = open(mod.__file__, encoding="utf-8").read()
        # _execute_live icinde fetch_fee_rate cagrisi OLMAMALI
        live_section = source[source.find("async def _execute_live"):]
        live_section = live_section[:live_section.find("async def ", 10)] if "async def " in live_section[10:] else live_section
        assert "fetch_fee_rate" not in live_section


# ═══════════════════════════════════════════════════════════════
# BOUNDARY
# ═══════════════════════════════════════════════════════════════

class TestExecutorBoundaries:

    def test_no_claim_coupling(self):
        import backend.execution.order_executor as mod
        lines = [l.strip() for l in open(mod.__file__, encoding="utf-8").readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "claim" not in line
            assert "exit_engine" not in line

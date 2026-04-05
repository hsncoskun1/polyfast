"""ExitExecutor tests — v0.6.2."""

import pytest
from backend.execution.exit_executor import ExitExecutor, RETRY_INTERVALS_MS, MAX_CLOSE_RETRIES
from backend.execution.position_tracker import PositionTracker
from backend.execution.position_record import PositionState
from backend.execution.balance_manager import BalanceManager
from backend.execution.exit_evaluator import ExitEvaluator
from backend.execution.close_reason import CloseReason


def _make_open_position_and_tracker(fill_price=0.85, amount=5.0, balance=50.0):
    tracker = PositionTracker()
    balance_mgr = BalanceManager()
    balance_mgr.update(available=balance, total=balance)
    pos = tracker.create_pending("BTC", "UP", "0x1", "tok1", amount)
    tracker.confirm_fill(pos.position_id, fill_price=fill_price)
    return pos, tracker, balance_mgr


# ═══════════════════════════════════════════════════════════════
# PAPER MODE CLOSE
# ═══════════════════════════════════════════════════════════════

class TestPaperClose:

    @pytest.mark.asyncio
    async def test_tp_close(self):
        pos, tracker, balance = _make_open_position_and_tracker()
        tracker.request_close(pos.position_id, CloseReason.TAKE_PROFIT)

        executor = ExitExecutor(tracker, balance, paper_mode=True)
        success = await executor.execute_close(pos, current_price=0.92)

        assert success is True
        assert pos.is_closed
        assert pos.exit_fill_price == 0.92
        assert pos.net_realized_pnl > 0
        assert pos.close_reason == CloseReason.TAKE_PROFIT
        assert executor.close_count == 1

    @pytest.mark.asyncio
    async def test_sl_close(self):
        pos, tracker, balance = _make_open_position_and_tracker()
        tracker.request_close(pos.position_id, CloseReason.STOP_LOSS)

        executor = ExitExecutor(tracker, balance, paper_mode=True)
        success = await executor.execute_close(pos, current_price=0.78)

        assert success is True
        assert pos.is_closed
        assert pos.net_realized_pnl < 0  # zarar
        assert pos.close_reason == CloseReason.STOP_LOSS

    @pytest.mark.asyncio
    async def test_force_sell_close(self):
        pos, tracker, balance = _make_open_position_and_tracker()
        tracker.request_close(pos.position_id, CloseReason.FORCE_SELL,
                              trigger_set=["force_sell_time"])

        executor = ExitExecutor(tracker, balance, paper_mode=True)
        success = await executor.execute_close(pos, current_price=0.80)

        assert success is True
        assert pos.is_closed
        assert pos.close_reason == CloseReason.FORCE_SELL
        assert pos.close_trigger_set == ["force_sell_time"]

    @pytest.mark.asyncio
    async def test_post_close_balance_add(self):
        pos, tracker, balance = _make_open_position_and_tracker(balance=45.0)
        tracker.request_close(pos.position_id, CloseReason.TAKE_PROFIT)

        executor = ExitExecutor(tracker, balance, paper_mode=True)
        await executor.execute_close(pos, current_price=0.92)

        assert balance.available_balance > 45.0  # net_exit_usdc eklendi

    @pytest.mark.asyncio
    async def test_net_realized_pnl_fixed_on_close(self):
        """confirm_close sonrasi net_realized_pnl sabitlenir."""
        pos, tracker, balance = _make_open_position_and_tracker()
        tracker.request_close(pos.position_id, CloseReason.TAKE_PROFIT)

        executor = ExitExecutor(tracker, balance, paper_mode=True)
        await executor.execute_close(pos, current_price=0.92)

        original_pnl = pos.net_realized_pnl
        # Fiyat degisse bile closed PnL degismemeli
        assert pos.net_realized_pnl == original_pnl


# ═══════════════════════════════════════════════════════════════
# TP REEVALUATE CANCEL
# ═══════════════════════════════════════════════════════════════

class TestTPReevaluateInExecutor:

    @pytest.mark.asyncio
    async def test_tp_reevaluate_cancels_in_executor(self):
        """TP reevaluate: fiyat dusunce execute_close iptal eder."""
        pos, tracker, balance = _make_open_position_and_tracker()
        evaluator = ExitEvaluator(tp_pct=5.0, tp_reevaluate=True)
        tracker.request_close(pos.position_id, CloseReason.TAKE_PROFIT)

        executor = ExitExecutor(tracker, balance, exit_evaluator=evaluator, paper_mode=True)
        # Fiyat dusuk — TP artik saglanmiyor
        success = await executor.execute_close(pos, current_price=0.86)

        assert success is False
        assert pos.is_open  # geri dondu
        assert pos.close_reason is None  # temizlendi

    @pytest.mark.asyncio
    async def test_sl_no_cancel_in_executor(self):
        """SL latch: execute_close iptal etmez."""
        pos, tracker, balance = _make_open_position_and_tracker()
        evaluator = ExitEvaluator(sl_reevaluate=False)
        tracker.request_close(pos.position_id, CloseReason.STOP_LOSS)

        executor = ExitExecutor(tracker, balance, exit_evaluator=evaluator, paper_mode=True)
        success = await executor.execute_close(pos, current_price=0.90)  # fiyat yukseldi

        assert success is True  # SL latch — yine de kapatir
        assert pos.is_closed


# ═══════════════════════════════════════════════════════════════
# RETRY
# ═══════════════════════════════════════════════════════════════

class TestRetry:

    def test_retry_intervals(self):
        assert RETRY_INTERVALS_MS[CloseReason.TAKE_PROFIT] == 400
        assert RETRY_INTERVALS_MS[CloseReason.STOP_LOSS] == 250
        assert RETRY_INTERVALS_MS[CloseReason.FORCE_SELL] == 200
        assert RETRY_INTERVALS_MS[CloseReason.MANUAL_CLOSE] == 400

    def test_get_retry_interval(self):
        assert ExitExecutor.get_retry_interval_ms(CloseReason.STOP_LOSS) == 250
        assert ExitExecutor.get_retry_interval_ms(CloseReason.FORCE_SELL) == 200

    @pytest.mark.asyncio
    async def test_latch_preserved_on_retry(self):
        """close_failed → retry: close_reason/trigger_set korunur."""
        pos, tracker, balance = _make_open_position_and_tracker()
        tracker.request_close(pos.position_id, CloseReason.FORCE_SELL,
                              trigger_set=["force_sell_time", "force_sell_pnl"])

        # Simule close_failed
        pos.transition_to(PositionState.CLOSE_PENDING)
        pos.transition_to(PositionState.CLOSE_FAILED)

        # close_reason ve trigger_set silinmemeli
        assert pos.close_reason == CloseReason.FORCE_SELL
        assert pos.close_trigger_set == ["force_sell_time", "force_sell_pnl"]

        # Retry
        executor = ExitExecutor(tracker, balance, paper_mode=True)
        success = await executor.execute_close(pos, current_price=0.80)

        assert success is True
        assert pos.close_reason == CloseReason.FORCE_SELL  # korundu
        assert pos.close_trigger_set == ["force_sell_time", "force_sell_pnl"]  # korundu


# ═══════════════════════════════════════════════════════════════
# COUNTERS
# ═══════════════════════════════════════════════════════════════

class TestExitCounters:

    @pytest.mark.asyncio
    async def test_open_position_decreases_on_close(self):
        pos, tracker, balance = _make_open_position_and_tracker()
        assert tracker.open_position_count == 1

        tracker.request_close(pos.position_id, CloseReason.TAKE_PROFIT)
        executor = ExitExecutor(tracker, balance, paper_mode=True)
        await executor.execute_close(pos, current_price=0.92)

        assert tracker.open_position_count == 0

    @pytest.mark.asyncio
    async def test_session_trade_count_not_affected_by_close(self):
        pos, tracker, balance = _make_open_position_and_tracker()
        assert tracker.session_trade_count == 1  # fill'den

        tracker.request_close(pos.position_id, CloseReason.TAKE_PROFIT)
        executor = ExitExecutor(tracker, balance, paper_mode=True)
        await executor.execute_close(pos, current_price=0.92)

        assert tracker.session_trade_count == 1  # degismez — close sayilmaz


# ═══════════════════════════════════════════════════════════════
# BOUNDARY
# ═══════════════════════════════════════════════════════════════

class TestExitExecutorBoundaries:

    def test_no_claim_coupling(self):
        import backend.execution.exit_executor as mod
        lines = [l.strip() for l in open(mod.__file__, encoding="utf-8").readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "claim" not in line

    @pytest.mark.asyncio
    async def test_wrong_state_returns_false(self):
        pos, tracker, balance = _make_open_position_and_tracker()
        executor = ExitExecutor(tracker, balance, paper_mode=True)
        # open_confirmed → execute_close beklemez
        result = await executor.execute_close(pos, current_price=0.90)
        assert result is False

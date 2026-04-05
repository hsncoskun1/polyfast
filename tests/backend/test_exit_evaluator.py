"""ExitEvaluator tests — v0.6.0.

Tests:
1. TP trigger + reevaluate behavior
2. SL trigger + latch (no cancel)
3. Jump threshold guard
4. State machine: closing_requested → open_confirmed (TP reevaluate only)
5. SL closing_requested → open_confirmed YASAK
"""

import pytest
from backend.execution.exit_evaluator import ExitEvaluator, ExitSignal
from backend.execution.position_record import PositionRecord, PositionState
from backend.execution.position_tracker import PositionTracker
from backend.execution.close_reason import CloseReason


def _make_open_position(fill_price=0.85, amount=5.0):
    """Helper: acik pozisyon olustur."""
    tracker = PositionTracker()
    pos = tracker.create_pending("BTC", "UP", "0x1", "tok1", amount)
    tracker.confirm_fill(pos.position_id, fill_price=fill_price)
    return pos, tracker


# ═══════════════════════════════════════════════════════════════
# TP EVALUATION
# ═══════════════════════════════════════════════════════════════

class TestTPEvaluation:

    def test_tp_triggered(self):
        """PnL >= tp_pct → TP tetiklenir."""
        pos, _ = _make_open_position(fill_price=0.85)
        evaluator = ExitEvaluator(tp_pct=5.0, sl_pct=3.0)
        # current=0.92 → PnL ~6.6% > 5% → TP
        signal = evaluator.evaluate(pos, current_price=0.92)
        assert signal.should_exit is True
        assert signal.reason == CloseReason.TAKE_PROFIT

    def test_tp_not_triggered(self):
        """PnL < tp_pct → TP tetiklenmez."""
        pos, _ = _make_open_position(fill_price=0.85)
        evaluator = ExitEvaluator(tp_pct=5.0, sl_pct=3.0)
        # current=0.87 → PnL ~1.5% < 5% → no trigger
        signal = evaluator.evaluate(pos, current_price=0.87)
        assert signal.should_exit is False

    def test_tp_reevaluate_cancel(self):
        """TP reevaluate=True: koşul artık sağlanmıyorsa iptal."""
        pos, tracker = _make_open_position(fill_price=0.85)
        evaluator = ExitEvaluator(tp_pct=5.0, sl_pct=3.0, tp_reevaluate=True)

        # TP tetikle → closing_requested
        signal = evaluator.evaluate(pos, current_price=0.92)
        assert signal.should_exit is True
        tracker.request_close(pos.position_id, CloseReason.TAKE_PROFIT)

        # Fiyat geri dondü → TP artık sağlanmıyor
        should_cancel = evaluator.should_cancel_close(pos, current_price=0.86)
        assert should_cancel is True  # iptal — open_confirmed'a don

    def test_tp_reevaluate_still_valid(self):
        """TP reevaluate=True: koşul hâlâ sağlanıyorsa iptal YOK."""
        pos, tracker = _make_open_position(fill_price=0.85)
        evaluator = ExitEvaluator(tp_pct=5.0, sl_pct=3.0, tp_reevaluate=True)

        tracker.request_close(pos.position_id, CloseReason.TAKE_PROFIT)

        should_cancel = evaluator.should_cancel_close(pos, current_price=0.93)
        assert should_cancel is False  # hala karda, devam

    def test_tp_reevaluate_false_no_cancel(self):
        """TP reevaluate=False: latch — iptal yok."""
        pos, tracker = _make_open_position(fill_price=0.85)
        evaluator = ExitEvaluator(tp_pct=5.0, sl_pct=3.0, tp_reevaluate=False)

        tracker.request_close(pos.position_id, CloseReason.TAKE_PROFIT)

        # Fiyat dusmus ama reevaluate=False → iptal YOK
        should_cancel = evaluator.should_cancel_close(pos, current_price=0.86)
        assert should_cancel is False

    def test_tp_state_machine_back_to_open(self):
        """TP reevaluate iptal → closing_requested → open_confirmed geri donus."""
        pos, tracker = _make_open_position(fill_price=0.85)

        # TP tetikle
        tracker.request_close(pos.position_id, CloseReason.TAKE_PROFIT)
        assert pos.state == PositionState.CLOSING_REQUESTED

        # Reevaluate iptal → geri don
        pos.transition_to(PositionState.OPEN_CONFIRMED)
        assert pos.state == PositionState.OPEN_CONFIRMED
        assert pos.is_open


# ═══════════════════════════════════════════════════════════════
# SL EVALUATION
# ═══════════════════════════════════════════════════════════════

class TestSLEvaluation:

    def test_sl_triggered(self):
        """PnL <= -sl_pct → SL tetiklenir."""
        pos, _ = _make_open_position(fill_price=0.85)
        evaluator = ExitEvaluator(tp_pct=5.0, sl_pct=3.0)
        # current=0.80 → büyük zarar → SL
        signal = evaluator.evaluate(pos, current_price=0.80)
        assert signal.should_exit is True
        assert signal.reason == CloseReason.STOP_LOSS
        assert signal.detail["latch"] is True

    def test_sl_not_triggered(self):
        """PnL > -sl_pct → SL tetiklenmez."""
        pos, _ = _make_open_position(fill_price=0.85)
        evaluator = ExitEvaluator(tp_pct=5.0, sl_pct=3.0)
        # 0.84'te fee etkisiyle PnL -3.21% oluyor, 0.845 ile test et
        signal = evaluator.evaluate(pos, current_price=0.845)
        assert signal.should_exit is False

    def test_sl_latch_no_cancel(self):
        """SL latch zorunlu — reevaluate=False, iptal YOK."""
        pos, tracker = _make_open_position(fill_price=0.85)
        evaluator = ExitEvaluator(tp_pct=5.0, sl_pct=3.0, sl_reevaluate=False)

        tracker.request_close(pos.position_id, CloseReason.STOP_LOSS)

        # Fiyat geri yukseldi ama SL latch → iptal YOK
        should_cancel = evaluator.should_cancel_close(pos, current_price=0.90)
        assert should_cancel is False

    def test_sl_no_back_to_open_in_code(self):
        """SL closing_requested → open_confirmed: caller tarafinda ENGELLENMELI.

        State machine izin veriyor (TP reevaluate icin) ama
        SL'de should_cancel_close her zaman False doner.
        """
        pos, tracker = _make_open_position(fill_price=0.85)
        evaluator = ExitEvaluator(sl_reevaluate=False)

        tracker.request_close(pos.position_id, CloseReason.STOP_LOSS)

        # should_cancel_close SL icin her zaman False
        assert evaluator.should_cancel_close(pos, current_price=0.95) is False


# ═══════════════════════════════════════════════════════════════
# JUMP THRESHOLD
# ═══════════════════════════════════════════════════════════════

class TestJumpThreshold:

    def test_jump_blocks_sl(self):
        """Tek tick %15+ dusus → orderbook anomali → SL ATLANIR."""
        pos, _ = _make_open_position(fill_price=0.85)
        evaluator = ExitEvaluator(sl_pct=3.0, sl_jump_threshold=0.15)

        # İlk tick normal fiyat
        evaluator.evaluate(pos, current_price=0.85)

        # İkinci tick: 0.85 → 0.50 = %41 dusus > %15 threshold
        signal = evaluator.evaluate(pos, current_price=0.50)
        assert signal.should_exit is False  # SL ATLANIR
        assert signal.detail["reason"] == "jump_threshold"

    def test_normal_drop_sl_fires(self):
        """Normal dusus (<%15) → SL normal tetiklenir."""
        pos, _ = _make_open_position(fill_price=0.85)
        evaluator = ExitEvaluator(sl_pct=3.0, sl_jump_threshold=0.15)

        evaluator.evaluate(pos, current_price=0.82)  # ilk tick
        signal = evaluator.evaluate(pos, current_price=0.80)  # %2.4 dusus < %15
        assert signal.should_exit is True
        assert signal.reason == CloseReason.STOP_LOSS


# ═══════════════════════════════════════════════════════════════
# EDGE CASES
# ═══════════════════════════════════════════════════════════════

class TestExitEdgeCases:

    def test_not_open_position(self):
        """Acik olmayan pozisyon → exit signal yok."""
        pos = PositionRecord(position_id="1", asset="BTC", side="UP",
                             condition_id="0x1", token_id="tok1")
        evaluator = ExitEvaluator()
        signal = evaluator.evaluate(pos, current_price=0.90)
        assert signal.should_exit is False

    def test_zero_fill_price(self):
        """fill_price=0 → exit signal yok."""
        pos = PositionRecord(position_id="1", asset="BTC", side="UP",
                             condition_id="0x1", token_id="tok1",
                             state=PositionState.OPEN_CONFIRMED,
                             fill_price=0.0)
        evaluator = ExitEvaluator()
        signal = evaluator.evaluate(pos, current_price=0.90)
        assert signal.should_exit is False

    def test_pnl_in_signal(self):
        """ExitSignal PnL bilgisi icerir."""
        pos, _ = _make_open_position(fill_price=0.85)
        evaluator = ExitEvaluator(tp_pct=5.0)
        signal = evaluator.evaluate(pos, current_price=0.92)
        assert signal.pnl_pct > 0


# ═══════════════════════════════════════════════════════════════
# BOUNDARY
# ═══════════════════════════════════════════════════════════════

class TestExitBoundaries:

    def test_no_claim_coupling(self):
        import backend.execution.exit_evaluator as mod
        lines = [l.strip() for l in open(mod.__file__, encoding="utf-8").readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "claim" not in line

    def test_no_force_sell_in_v060(self):
        """v0.6.0'da force sell evaluation YOK (v0.6.1'de)."""
        import backend.execution.exit_evaluator as mod
        source = open(mod.__file__, encoding="utf-8").read()
        # force_sell CloseReason olarak var ama evaluation mantigi yok
        assert "FORCE_SELL" not in source or "v0.6.1" in source

"""Position tests — v0.5.1.

Tests:
1. PositionRecord state machine
2. Fee-aware entry/exit calculation
3. Net PnL model
4. PositionTracker fill/close lifecycle
5. Event Max / Bot Max / Session Trade sayaclari
6. Close reason + trigger set
7. Authoritative vs hesaplanan alan ayrimi
"""

import pytest
from datetime import datetime, timezone

from backend.execution.position_record import (
    PositionRecord, PositionState, InvalidPositionTransition, ALLOWED_TRANSITIONS,
)
from backend.execution.position_tracker import PositionTracker
from backend.execution.fee_calculator import FeeCalculator, DEFAULT_CRYPTO_FEE_RATE
from backend.execution.close_reason import CloseReason, ForceSellTrigger


# ═══════════════════════════════════════════════════════════════
# FEE CALCULATOR
# ═══════════════════════════════════════════════════════════════

class TestFeeCalculator:

    def test_buy_fee_at_85(self):
        calc = FeeCalculator(fee_rate=0.072)
        # 10 USD at 0.85 → gross 11.7647 shares
        fee = calc.calculate_buy_fee_shares(11.7647, 0.85)
        # 11.7647 × 0.072 × 0.85 × 0.15 = 0.108
        assert abs(fee - 0.108) < 0.001

    def test_sell_fee_at_92(self):
        calc = FeeCalculator(fee_rate=0.072)
        fee = calc.calculate_sell_fee_usdc(11.6567, 0.92)
        # 11.6567 × 0.072 × 0.92 × 0.08 = 0.0618
        assert abs(fee - 0.0618) < 0.001

    def test_fee_peak_at_50(self):
        """Fee peak at p=0.50."""
        calc = FeeCalculator(fee_rate=0.072)
        fee_50 = calc.calculate_buy_fee_shares(100, 0.50)
        fee_85 = calc.calculate_buy_fee_shares(100, 0.85)
        assert fee_50 > fee_85  # 50 pennede fee daha yuksek

    def test_entry_calculation(self):
        calc = FeeCalculator(fee_rate=0.072)
        result = calc.calculate_entry(10.0, 0.85)
        assert result["gross_fill_shares"] > 0
        assert result["entry_fee_shares"] > 0
        assert result["net_position_shares"] > 0
        assert result["net_position_shares"] < result["gross_fill_shares"]
        assert result["fee_rate"] == 0.072

    def test_exit_calculation(self):
        calc = FeeCalculator(fee_rate=0.072)
        result = calc.calculate_exit(11.6567, 0.92)
        assert result["exit_gross_usdc"] > 0
        assert result["actual_exit_fee_usdc"] > 0
        assert result["net_exit_usdc"] > 0
        assert result["net_exit_usdc"] < result["exit_gross_usdc"]

    def test_dynamic_fee_rate(self):
        calc = FeeCalculator(fee_rate=0.072)
        calc.set_fee_rate(0.05)
        assert calc.fee_rate == 0.05

    def test_full_round_trip_net_pnl(self):
        """$10 girdi, 0.85'ten aldi, 0.92'den satti — net PnL."""
        calc = FeeCalculator(fee_rate=0.072)
        entry = calc.calculate_entry(10.0, 0.85)
        exit_data = calc.calculate_exit(entry["net_position_shares"], 0.92)
        net_pnl = exit_data["net_exit_usdc"] - 10.0
        assert net_pnl > 0  # kar etmeli
        assert net_pnl < (0.92 - 0.85) / 0.85 * 10  # gross pnl'den dusuk


# ═══════════════════════════════════════════════════════════════
# POSITION STATE MACHINE
# ═══════════════════════════════════════════════════════════════

class TestPositionStateMachine:

    def test_initial_state(self):
        r = PositionRecord(position_id="1", asset="BTC", side="UP",
                           condition_id="0x1", token_id="tok1")
        assert r.state == PositionState.PENDING_OPEN

    def test_pending_to_open(self):
        r = PositionRecord(position_id="1", asset="BTC", side="UP",
                           condition_id="0x1", token_id="tok1")
        r.transition_to(PositionState.OPEN_CONFIRMED)
        assert r.is_open

    def test_pending_to_closed_fok_rejected(self):
        """FOK rejected — pending → closed."""
        r = PositionRecord(position_id="1", asset="BTC", side="UP",
                           condition_id="0x1", token_id="tok1")
        r.transition_to(PositionState.CLOSED)
        assert r.is_closed

    def test_open_to_closing(self):
        r = PositionRecord(position_id="1", asset="BTC", side="UP",
                           condition_id="0x1", token_id="tok1")
        r.transition_to(PositionState.OPEN_CONFIRMED)
        r.transition_to(PositionState.CLOSING_REQUESTED)
        assert r.state == PositionState.CLOSING_REQUESTED

    def test_invalid_transition_raises(self):
        r = PositionRecord(position_id="1", asset="BTC", side="UP",
                           condition_id="0x1", token_id="tok1")
        with pytest.raises(InvalidPositionTransition):
            r.transition_to(PositionState.CLOSE_PENDING)  # pending → close_pending invalid

    def test_closed_is_terminal(self):
        r = PositionRecord(position_id="1", asset="BTC", side="UP",
                           condition_id="0x1", token_id="tok1")
        r.transition_to(PositionState.CLOSED)
        with pytest.raises(InvalidPositionTransition):
            r.transition_to(PositionState.OPEN_CONFIRMED)

    def test_close_failed_can_retry(self):
        r = PositionRecord(position_id="1", asset="BTC", side="UP",
                           condition_id="0x1", token_id="tok1")
        r.transition_to(PositionState.OPEN_CONFIRMED)
        r.transition_to(PositionState.CLOSING_REQUESTED)
        r.transition_to(PositionState.CLOSE_PENDING)
        r.transition_to(PositionState.CLOSE_FAILED)
        r.transition_to(PositionState.CLOSING_REQUESTED)  # retry
        assert r.state == PositionState.CLOSING_REQUESTED


# ═══════════════════════════════════════════════════════════════
# POSITION TRACKER — FILL / CLOSE LIFECYCLE
# ═══════════════════════════════════════════════════════════════

class TestPositionTracker:

    def test_create_pending(self):
        tracker = PositionTracker()
        pos = tracker.create_pending("BTC", "UP", "0x1", "tok1", 10.0)
        assert pos.is_pending
        assert pos.requested_amount_usd == 10.0

    def test_confirm_fill_fee_aware(self):
        tracker = PositionTracker()
        pos = tracker.create_pending("BTC", "UP", "0x1", "tok1", 10.0)
        pos = tracker.confirm_fill(pos.position_id, fill_price=0.85)

        assert pos.is_open
        assert pos.fill_price == 0.85
        assert pos.gross_fill_shares > 0
        assert pos.entry_fee_shares > 0
        assert pos.net_position_shares > 0
        assert pos.net_position_shares < pos.gross_fill_shares
        assert pos.fee_rate == DEFAULT_CRYPTO_FEE_RATE

    def test_confirm_close_net_pnl(self):
        tracker = PositionTracker()
        pos = tracker.create_pending("BTC", "UP", "0x1", "tok1", 10.0)
        tracker.confirm_fill(pos.position_id, fill_price=0.85)
        tracker.request_close(pos.position_id, CloseReason.TAKE_PROFIT)
        tracker.confirm_close(pos.position_id, exit_fill_price=0.92)

        assert pos.is_closed
        assert pos.exit_fill_price == 0.92
        assert pos.net_exit_usdc > 0
        assert pos.net_realized_pnl > 0  # kar
        assert pos.close_reason == CloseReason.TAKE_PROFIT

    def test_reject_fill_no_counters(self):
        """FOK rejected — sayaclar ARTMAZ."""
        tracker = PositionTracker()
        pos = tracker.create_pending("BTC", "UP", "0x1", "tok1", 10.0)
        tracker.reject_fill(pos.position_id)

        assert pos.is_closed
        assert tracker.get_event_fill_count("0x1") == 0
        assert tracker.session_trade_count == 0
        assert tracker.open_position_count == 0

    def test_unrealized_pnl_calculation(self):
        tracker = PositionTracker()
        pos = tracker.create_pending("BTC", "UP", "0x1", "tok1", 10.0)
        tracker.confirm_fill(pos.position_id, fill_price=0.85)

        pnl = pos.calculate_unrealized_pnl(current_price=0.90)
        assert pnl["net_unrealized_pnl_estimate"] > 0
        assert pnl["estimated_exit_fee_usdc"] > 0
        assert pnl["net_exit_value_estimate"] < pnl["gross_position_value"]


# ═══════════════════════════════════════════════════════════════
# SAYACLAR
# ═══════════════════════════════════════════════════════════════

class TestCounters:

    def test_event_fill_count_increments_on_fill(self):
        tracker = PositionTracker()
        pos = tracker.create_pending("BTC", "UP", "0x1", "tok1", 10.0)
        tracker.confirm_fill(pos.position_id, fill_price=0.85)
        assert tracker.get_event_fill_count("0x1") == 1

    def test_event_fill_count_not_on_reject(self):
        tracker = PositionTracker()
        pos = tracker.create_pending("BTC", "UP", "0x1", "tok1", 10.0)
        tracker.reject_fill(pos.position_id)
        assert tracker.get_event_fill_count("0x1") == 0

    def test_open_position_count(self):
        tracker = PositionTracker()
        p1 = tracker.create_pending("BTC", "UP", "0x1", "tok1", 10.0)
        tracker.confirm_fill(p1.position_id, fill_price=0.85)
        assert tracker.open_position_count == 1

        p2 = tracker.create_pending("ETH", "UP", "0x2", "tok2", 5.0)
        tracker.confirm_fill(p2.position_id, fill_price=0.60)
        assert tracker.open_position_count == 2

        tracker.request_close(p1.position_id, CloseReason.TAKE_PROFIT)
        tracker.confirm_close(p1.position_id, exit_fill_price=0.90)
        assert tracker.open_position_count == 1

    def test_session_trade_count(self):
        tracker = PositionTracker()
        p1 = tracker.create_pending("BTC", "UP", "0x1", "tok1", 10.0)
        tracker.confirm_fill(p1.position_id, fill_price=0.85)
        assert tracker.session_trade_count == 1

        p2 = tracker.create_pending("ETH", "UP", "0x2", "tok2", 5.0)
        tracker.confirm_fill(p2.position_id, fill_price=0.60)
        assert tracker.session_trade_count == 2

        # Close p1 — session count AZALMAZ
        tracker.request_close(p1.position_id, CloseReason.TAKE_PROFIT)
        tracker.confirm_close(p1.position_id, exit_fill_price=0.90)
        assert tracker.session_trade_count == 2  # hala 2

    def test_multiple_fills_same_event(self):
        tracker = PositionTracker()
        p1 = tracker.create_pending("BTC", "UP", "0x1", "tok1", 5.0)
        tracker.confirm_fill(p1.position_id, fill_price=0.85)
        p2 = tracker.create_pending("BTC", "UP", "0x1", "tok2", 5.0)
        tracker.confirm_fill(p2.position_id, fill_price=0.86)
        assert tracker.get_event_fill_count("0x1") == 2


# ═══════════════════════════════════════════════════════════════
# CLOSE REASON + TRIGGER SET
# ═══════════════════════════════════════════════════════════════

class TestCloseReason:

    def test_force_sell_with_triggers(self):
        tracker = PositionTracker()
        pos = tracker.create_pending("BTC", "UP", "0x1", "tok1", 10.0)
        tracker.confirm_fill(pos.position_id, fill_price=0.85)
        tracker.request_close(
            pos.position_id,
            reason=CloseReason.FORCE_SELL,
            trigger_set=["force_sell_time", "force_sell_pnl"],
        )
        assert pos.close_reason == CloseReason.FORCE_SELL
        assert pos.close_trigger_set == ["force_sell_time", "force_sell_pnl"]

    def test_stop_loss_no_triggers(self):
        tracker = PositionTracker()
        pos = tracker.create_pending("BTC", "UP", "0x1", "tok1", 10.0)
        tracker.confirm_fill(pos.position_id, fill_price=0.85)
        tracker.request_close(pos.position_id, reason=CloseReason.STOP_LOSS)
        assert pos.close_reason == CloseReason.STOP_LOSS
        assert pos.close_trigger_set == []

    def test_close_triggered_at_set(self):
        tracker = PositionTracker()
        pos = tracker.create_pending("BTC", "UP", "0x1", "tok1", 10.0)
        tracker.confirm_fill(pos.position_id, fill_price=0.85)
        tracker.request_close(pos.position_id, reason=CloseReason.TAKE_PROFIT, requested_price=0.92)
        assert pos.close_triggered_at is not None
        assert pos.close_requested_price == 0.92


# ═══════════════════════════════════════════════════════════════
# AUTHORITATIVE VS HESAPLANAN
# ═══════════════════════════════════════════════════════════════

class TestAuthoritativeFields:

    def test_entry_fields_immutable_after_fill(self):
        """Fill sonrasi entry alanlari degismemeli (authoritative)."""
        tracker = PositionTracker()
        pos = tracker.create_pending("BTC", "UP", "0x1", "tok1", 10.0)
        tracker.confirm_fill(pos.position_id, fill_price=0.85)

        original_fill = pos.fill_price
        original_shares = pos.net_position_shares
        original_fee = pos.entry_fee_shares

        # Unrealized PnL hesapla — entry alanlari degismemeli
        pos.calculate_unrealized_pnl(current_price=0.90)

        assert pos.fill_price == original_fill
        assert pos.net_position_shares == original_shares
        assert pos.entry_fee_shares == original_fee

    def test_close_fields_set_on_close(self):
        """Close alanlari close aninda sabitlenir."""
        tracker = PositionTracker()
        pos = tracker.create_pending("BTC", "UP", "0x1", "tok1", 10.0)
        tracker.confirm_fill(pos.position_id, fill_price=0.85)
        tracker.request_close(pos.position_id, CloseReason.TAKE_PROFIT)
        tracker.confirm_close(pos.position_id, exit_fill_price=0.92)

        assert pos.exit_fill_price == 0.92
        assert pos.net_realized_pnl != 0
        assert pos.closed_at is not None


# ═══════════════════════════════════════════════════════════════
# BOUNDARY
# ═══════════════════════════════════════════════════════════════

class TestPositionBoundaries:

    def test_no_clob_coupling(self):
        import backend.execution.position_tracker as mod
        lines = [l.strip() for l in open(mod.__file__, encoding="utf-8").readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "clob" not in line.lower()
            assert "py_clob_client" not in line

    def test_no_strategy_coupling(self):
        import backend.execution.position_record as mod
        lines = [l.strip() for l in open(mod.__file__, encoding="utf-8").readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "strategy" not in line
            assert "rule" not in line

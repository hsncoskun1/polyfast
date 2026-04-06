"""OrderIntent + OrderValidator tests — v0.5.0.

GPT gereksinimleri:
1. amount_usd >= 1.0 guard
2. dominant_price execution/PnL referansi degil
3. Event Max / Bot Max validation/read seviyesinde
4. token_id side ile net bagli
"""

import pytest
from datetime import datetime, timezone

from backend.execution.order_intent import OrderIntent, OrderSide
from backend.execution.order_validator import OrderValidator, DEFAULT_MINIMUM_ORDER_USD
from backend.execution.models import ValidationStatus, RejectReason


# ═══════════════════════════════════════════════════════════════
# ORDER INTENT MODEL
# ═══════════════════════════════════════════════════════════════

class TestOrderIntent:

    def test_frozen(self):
        intent = OrderIntent(
            asset="BTC", side=OrderSide.UP, amount_usd=5.0,
            condition_id="0x1", token_id="tok1", dominant_price=0.85,
        )
        with pytest.raises(AttributeError):
            intent.amount_usd = 10.0

    def test_side_up(self):
        intent = OrderIntent(
            asset="BTC", side=OrderSide.UP, amount_usd=5.0,
            condition_id="0x1", token_id="up_token", dominant_price=0.85,
        )
        assert intent.side == OrderSide.UP
        assert intent.token_id == "up_token"

    def test_side_down(self):
        intent = OrderIntent(
            asset="BTC", side=OrderSide.DOWN, amount_usd=5.0,
            condition_id="0x1", token_id="down_token", dominant_price=0.15,
        )
        assert intent.side == OrderSide.DOWN
        assert intent.token_id == "down_token"

    def test_dominant_price_is_reference_only(self):
        """dominant_price evaluation ani referansi — fill price DEGIL."""
        intent = OrderIntent(
            asset="BTC", side=OrderSide.UP, amount_usd=5.0,
            condition_id="0x1", token_id="tok1", dominant_price=0.85,
        )
        # dominant_price sadece bilgi — execution/PnL'de kullanilmayacak
        assert intent.dominant_price == 0.85
        # fill_price attribute'u OLMAMALI
        assert not hasattr(intent, "fill_price")

    def test_token_id_side_contract(self):
        """token_id side ile net bagli olmali."""
        up_intent = OrderIntent(
            asset="BTC", side=OrderSide.UP, amount_usd=5.0,
            condition_id="0x1", token_id="up_tok_123", dominant_price=0.85,
        )
        down_intent = OrderIntent(
            asset="BTC", side=OrderSide.DOWN, amount_usd=5.0,
            condition_id="0x1", token_id="down_tok_456", dominant_price=0.15,
        )
        # Farkli side = farkli token
        assert up_intent.token_id != down_intent.token_id

    def test_decimal_amount(self):
        """Ondalikli USD tutar desteklenmeli."""
        intent = OrderIntent(
            asset="BTC", side=OrderSide.UP, amount_usd=2.75,
            condition_id="0x1", token_id="tok1", dominant_price=0.85,
        )
        assert intent.amount_usd == 2.75

    def test_evaluated_at_auto(self):
        intent = OrderIntent(
            asset="BTC", side=OrderSide.UP, amount_usd=5.0,
            condition_id="0x1", token_id="tok1", dominant_price=0.85,
        )
        assert intent.evaluated_at is not None


# ═══════════════════════════════════════════════════════════════
# ORDER VALIDATOR
# ═══════════════════════════════════════════════════════════════

class TestOrderValidator:

    def _make_intent(self, **overrides):
        defaults = dict(
            asset="BTC", side=OrderSide.UP, amount_usd=5.0,
            condition_id="0x1", token_id="tok1", dominant_price=0.85,
        )
        defaults.update(overrides)
        return OrderIntent(**defaults)

    def _validate(self, intent=None, balance=100.0, event_fills=0,
                  event_max=3, open_pos=0, bot_max=5):
        v = OrderValidator()
        return v.validate(
            intent or self._make_intent(),
            available_balance=balance,
            event_fill_count=event_fills,
            event_max=event_max,
            open_position_count=open_pos,
            bot_max=bot_max,
        )

    # --- All pass ---

    def test_all_valid(self):
        result = self._validate()
        assert result.is_valid
        assert result.status == ValidationStatus.VALID

    # --- Minimum amount ---

    def test_below_minimum_rejected(self):
        intent = self._make_intent(amount_usd=0.5)
        result = self._validate(intent)
        assert result.is_rejected
        assert result.reason == RejectReason.BELOW_MINIMUM_AMOUNT

    def test_exact_minimum_valid(self):
        intent = self._make_intent(amount_usd=1.0)
        result = self._validate(intent)
        assert result.is_valid

    def test_minimum_default_one_dollar(self):
        assert DEFAULT_MINIMUM_ORDER_USD == 1.0

    # --- Balance ---

    def test_insufficient_balance_rejected(self):
        intent = self._make_intent(amount_usd=10.0)
        result = self._validate(intent, balance=5.0)
        assert result.is_rejected
        assert result.reason == RejectReason.INSUFFICIENT_BALANCE
        assert result.detail["shortfall"] == 5.0

    def test_exact_balance_valid(self):
        intent = self._make_intent(amount_usd=5.0)
        result = self._validate(intent, balance=5.0)
        assert result.is_valid

    # --- Event Max ---

    def test_event_max_reached_rejected(self):
        result = self._validate(event_fills=3, event_max=3)
        assert result.is_rejected
        assert result.reason == RejectReason.EVENT_MAX_REACHED

    def test_event_max_not_reached_valid(self):
        result = self._validate(event_fills=2, event_max=3)
        assert result.is_valid

    def test_event_max_zero_fills_valid(self):
        result = self._validate(event_fills=0, event_max=1)
        assert result.is_valid

    # --- Bot Max ---

    def test_bot_max_reached_rejected(self):
        result = self._validate(open_pos=5, bot_max=5)
        assert result.is_rejected
        assert result.reason == RejectReason.BOT_MAX_REACHED

    def test_bot_max_not_reached_valid(self):
        result = self._validate(open_pos=2, bot_max=5)
        assert result.is_valid

    # --- Event Max + Bot Max combined ---

    def test_event_ok_but_bot_full_rejected(self):
        result = self._validate(event_fills=0, event_max=3, open_pos=5, bot_max=5)
        assert result.is_rejected
        assert result.reason == RejectReason.BOT_MAX_REACHED

    def test_bot_ok_but_event_full_rejected(self):
        result = self._validate(event_fills=3, event_max=3, open_pos=0, bot_max=5)
        assert result.is_rejected
        assert result.reason == RejectReason.EVENT_MAX_REACHED

    # --- Missing fields ---

    def test_missing_token_id_rejected(self):
        intent = self._make_intent(token_id="")
        result = self._validate(intent)
        assert result.is_rejected
        assert result.reason == RejectReason.MISSING_TOKEN_ID

    def test_missing_condition_id_rejected(self):
        intent = self._make_intent(condition_id="")
        result = self._validate(intent)
        assert result.is_rejected
        assert result.reason == RejectReason.MISSING_CONDITION_ID

    # --- Validation order ---

    def test_first_failure_wins(self):
        """Birden fazla sorun varsa ilk yakalanan rejection sebep olur."""
        intent = self._make_intent(token_id="", amount_usd=0.5)
        result = self._validate(intent)
        # token_id kontrolu amount'tan once
        assert result.reason == RejectReason.MISSING_TOKEN_ID


# ═══════════════════════════════════════════════════════════════
# BOUNDARY
# ═══════════════════════════════════════════════════════════════

class TestExecutionBoundaries:

    def test_no_clob_api_coupling(self):
        """v0.5.0'da gercek order gonderme YOK."""
        import backend.execution.order_validator as mod
        lines = [l.strip() for l in open(mod.__file__, encoding="utf-8").readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "clob" not in line.lower()
            assert "py_clob_client" not in line

    def test_no_position_coupling(self):
        """v0.5.0'da position lifecycle YOK."""
        import backend.execution.order_validator as mod
        lines = [l.strip() for l in open(mod.__file__, encoding="utf-8").readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "position" not in line

    def test_order_intent_no_fill_price(self):
        """OrderIntent fill_price icermez — fill sonrasi gelecek."""
        intent = OrderIntent(
            asset="BTC", side=OrderSide.UP, amount_usd=5.0,
            condition_id="0x1", token_id="tok1", dominant_price=0.85,
        )
        assert not hasattr(intent, "fill_price")
        assert not hasattr(intent, "shares")

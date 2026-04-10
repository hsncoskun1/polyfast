"""Rule Engine tests — v0.4.0 comprehensive test suite.

GPT istenen senaryolar:
1. Bir kural fail, diğerleri pass
2. Hiç fail yok ama bir kural waiting
3. Bazı kurallar disabled
4. Tüm enabled kurallar pass
5. EventMaxRule ve BotMaxRule injected counter ile pass/fail
6. PriceRule dominant taraf eşik testleri
7. DeltaRule coin_usd / PTB ayrımı
8. SpreadRule yüzde hesabı

Ek:
- Overall merge: fail baskın, waiting ikinci, pass son
- Disabled evaluation dışı
- Stale/eksik veri → waiting
- Boundary testler
"""

import pytest
from backend.strategy.rule_state import RuleState, OverallDecision
from backend.strategy.evaluation_context import EvaluationContext
from backend.strategy.base_rule import RuleResult
from backend.strategy.engine import RuleEngine, EvaluationResult
from backend.strategy.rules.time_rule import TimeRule
from backend.strategy.rules.price_rule import PriceRule
from backend.strategy.rules.delta_rule import DeltaRule
from backend.strategy.rules.spread_rule import SpreadRule
from backend.strategy.rules.event_max_rule import EventMaxRule
from backend.strategy.rules.bot_max_rule import BotMaxRule


def _make_ctx(**overrides) -> EvaluationContext:
    """Helper: create context with all rules passing by default."""
    defaults = dict(
        condition_id="0x1",
        asset="BTC",
        up_price=0.85,
        down_price=0.15,
        up_bid=0.85,
        up_ask=0.86,
        down_bid=0.15,
        down_ask=0.16,
        best_bid=0.84,
        best_ask=0.86,
        outcome_fresh=True,
        coin_usd_price=67310.0,
        coin_usd_fresh=True,
        ptb_value=67260.0,
        ptb_acquired=True,
        seconds_remaining=120.0,
        event_fill_count=0,
        open_position_count=0,
        time_min_seconds=10,
        time_max_seconds=200,
        price_min=51,
        price_max=95,
        delta_threshold=20.0,
        spread_max_pct=5.0,
        event_max_positions=3,
        bot_max_positions=5,
        time_enabled=True,
        price_enabled=True,
        delta_enabled=True,
        spread_enabled=True,
        event_max_enabled=True,
        bot_max_enabled=True,
    )
    defaults.update(overrides)
    return EvaluationContext(**defaults)


# ═══════════════════════════════════════════════════════════════
# OVERALL MERGE TESTS
# ═══════════════════════════════════════════════════════════════

class TestOverallMerge:

    def test_all_enabled_pass_gives_entry(self):
        """Tüm enabled kurallar pass → ENTRY."""
        ctx = _make_ctx()
        engine = RuleEngine()
        result = engine.evaluate(ctx)
        assert result.decision == OverallDecision.ENTRY
        assert result.fail_count == 0
        assert result.waiting_count == 0

    def test_one_fail_gives_no_entry(self):
        """Bir kural fail, diğerleri pass → NO_ENTRY."""
        ctx = _make_ctx(seconds_remaining=5)  # time rule fail (5 < min 10)
        engine = RuleEngine()
        result = engine.evaluate(ctx)
        assert result.decision == OverallDecision.NO_ENTRY
        assert result.fail_count >= 1
        assert result.get_result("time").state == RuleState.FAIL

    def test_no_fail_but_one_waiting_gives_waiting(self):
        """Hiç fail yok ama bir kural waiting → WAITING."""
        ctx = _make_ctx(coin_usd_fresh=False)  # delta waiting
        engine = RuleEngine()
        result = engine.evaluate(ctx)
        assert result.decision == OverallDecision.WAITING
        assert result.get_result("delta").state == RuleState.WAITING
        assert result.fail_count == 0

    def test_fail_overrides_waiting(self):
        """Fail ve waiting birlikte → FAIL baskın → NO_ENTRY."""
        ctx = _make_ctx(
            seconds_remaining=5,     # time fail
            coin_usd_fresh=False,    # delta waiting
        )
        engine = RuleEngine()
        result = engine.evaluate(ctx)
        assert result.decision == OverallDecision.NO_ENTRY

    def test_some_disabled_does_not_block(self):
        """Bazı kurallar disabled → evaluation dışı, kalan pass ise ENTRY."""
        ctx = _make_ctx(
            delta_enabled=False,
            spread_enabled=False,
        )
        engine = RuleEngine()
        result = engine.evaluate(ctx)
        assert result.decision == OverallDecision.ENTRY
        assert result.disabled_count == 2
        assert result.get_result("delta").state == RuleState.DISABLED
        assert result.get_result("spread").state == RuleState.DISABLED

    def test_disabled_is_not_pass(self):
        """Disabled PASS sayılmaz — evaluation dışında tutulur."""
        ctx = _make_ctx(delta_enabled=False)
        engine = RuleEngine()
        result = engine.evaluate(ctx)
        delta = result.get_result("delta")
        assert delta.state == RuleState.DISABLED
        assert delta.state != RuleState.PASS

    def test_all_disabled_gives_no_rules(self):
        """Tüm kurallar disabled → NO_RULES."""
        ctx = _make_ctx(
            time_enabled=False,
            price_enabled=False,
            delta_enabled=False,
            spread_enabled=False,
            event_max_enabled=False,
            bot_max_enabled=False,
        )
        engine = RuleEngine()
        result = engine.evaluate(ctx)
        assert result.decision == OverallDecision.NO_RULES

    def test_all_rules_evaluated_even_after_fail(self):
        """Fail sonrası da diğer kurallar çalıştırılır (log bütünlüğü)."""
        ctx = _make_ctx(seconds_remaining=5)  # time fail
        engine = RuleEngine()
        result = engine.evaluate(ctx)
        # Tüm kurallar çalıştırılmış olmalı
        assert len(result.rule_results) == 6


# ═══════════════════════════════════════════════════════════════
# TIME RULE TESTS
# ═══════════════════════════════════════════════════════════════

class TestTimeRule:

    def test_in_range_pass(self):
        rule = TimeRule()
        ctx = _make_ctx(seconds_remaining=120, time_min_seconds=10, time_max_seconds=200)
        assert rule.evaluate(ctx).state == RuleState.PASS

    def test_below_min_fail(self):
        rule = TimeRule()
        ctx = _make_ctx(seconds_remaining=5, time_min_seconds=10, time_max_seconds=200)
        assert rule.evaluate(ctx).state == RuleState.FAIL

    def test_above_max_fail(self):
        rule = TimeRule()
        ctx = _make_ctx(seconds_remaining=250, time_min_seconds=10, time_max_seconds=200)
        assert rule.evaluate(ctx).state == RuleState.FAIL

    def test_expired_fail(self):
        rule = TimeRule()
        ctx = _make_ctx(seconds_remaining=0)
        assert rule.evaluate(ctx).state == RuleState.FAIL

    def test_exact_boundary_pass(self):
        rule = TimeRule()
        ctx = _make_ctx(seconds_remaining=10, time_min_seconds=10, time_max_seconds=200)
        assert rule.evaluate(ctx).state == RuleState.PASS

    def test_disabled(self):
        rule = TimeRule()
        ctx = _make_ctx(time_enabled=False)
        assert rule.evaluate(ctx).state == RuleState.DISABLED


# ═══════════════════════════════════════════════════════════════
# PRICE RULE TESTS — DOMINANT SIDE
# ═══════════════════════════════════════════════════════════════

class TestPriceRule:

    def test_dominant_up_in_range_pass(self):
        """UP dominant 85 → 51-95 aralığında → PASS."""
        rule = PriceRule()
        ctx = _make_ctx(up_price=0.85, down_price=0.15,
                        up_bid=0.85, up_ask=0.85, down_bid=0.15, down_ask=0.15,
                        price_min=51, price_max=95)
        result = rule.evaluate(ctx)
        assert result.state == RuleState.PASS
        assert result.detail["evaluated_side"] == "UP"

    def test_dominant_down_in_range_pass(self):
        """DOWN dominant 70 → 51-95 aralığında → PASS."""
        rule = PriceRule()
        ctx = _make_ctx(up_price=0.30, down_price=0.70,
                        up_bid=0.30, up_ask=0.30, down_bid=0.70, down_ask=0.70,
                        price_min=51, price_max=95)
        result = rule.evaluate(ctx)
        assert result.state == RuleState.PASS
        assert result.detail["evaluated_side"] == "DOWN"

    def test_dominant_below_min_fail(self):
        """Dominant 52 → min=70 → FAIL."""
        rule = PriceRule()
        ctx = _make_ctx(up_price=0.52, down_price=0.48,
                        up_bid=0.52, up_ask=0.52, down_bid=0.48, down_ask=0.48,
                        price_min=70, price_max=95)
        assert rule.evaluate(ctx).state == RuleState.FAIL

    def test_dominant_above_max_fail(self):
        """Dominant 97 → max=95 → FAIL."""
        rule = PriceRule()
        ctx = _make_ctx(up_price=0.97, down_price=0.03,
                        up_bid=0.97, up_ask=0.97, down_bid=0.03, down_ask=0.03,
                        price_min=51, price_max=95)
        assert rule.evaluate(ctx).state == RuleState.FAIL

    def test_outcome_not_fresh_waiting(self):
        """Outcome verisi stale → WAITING."""
        rule = PriceRule()
        ctx = _make_ctx(outcome_fresh=False)
        assert rule.evaluate(ctx).state == RuleState.WAITING

    def test_boundary_51_pass(self):
        """Dominant tam 51 → min=51 → PASS."""
        rule = PriceRule()
        ctx = _make_ctx(up_price=0.51, down_price=0.49,
                        up_bid=0.51, up_ask=0.51, down_bid=0.49, down_ask=0.49,
                        price_min=51, price_max=95)
        assert rule.evaluate(ctx).state == RuleState.PASS

    def test_dominant_always_max(self):
        """dominant = max(up, down) — uses ask for evaluated_price."""
        ctx = _make_ctx(up_price=0.40, down_price=0.60,
                        up_bid=0.40, up_ask=0.41, down_bid=0.60, down_ask=0.61)
        assert ctx.dominant_price == 0.61  # ask of dominant side
        assert ctx.dominant_side == "DOWN"


# ═══════════════════════════════════════════════════════════════
# DELTA RULE TESTS — COIN USD / PTB AYRIMI
# ═══════════════════════════════════════════════════════════════

class TestDeltaRule:

    def test_delta_above_threshold_pass(self):
        """abs(67310 - 67260) = 50 >= 20 → PASS."""
        rule = DeltaRule()
        ctx = _make_ctx(coin_usd_price=67310, ptb_value=67260, delta_threshold=20)
        result = rule.evaluate(ctx)
        assert result.state == RuleState.PASS
        assert result.detail["delta_usd"] == 50.0

    def test_delta_below_threshold_fail(self):
        """abs(67265 - 67260) = 5 < 20 → FAIL."""
        rule = DeltaRule()
        ctx = _make_ctx(coin_usd_price=67265, ptb_value=67260, delta_threshold=20)
        assert rule.evaluate(ctx).state == RuleState.FAIL

    def test_delta_uses_coin_usd_not_outcome(self):
        """Delta coin USD fiyatından hesaplanır, outcome'dan DEĞİL."""
        rule = DeltaRule()
        ctx = _make_ctx(
            coin_usd_price=67310, ptb_value=67260,
            up_price=0.85, down_price=0.15,  # outcome — bu kullanılmaz
            delta_threshold=20,
        )
        result = rule.evaluate(ctx)
        # delta = abs(67310 - 67260) = 50, outcome ile ilgisi yok
        assert result.detail["delta_usd"] == 50.0
        assert result.detail["coin_usd_price"] == 67310.0
        assert "up_price" not in result.detail

    def test_ptb_not_acquired_waiting(self):
        """PTB alınmamışsa → WAITING."""
        rule = DeltaRule()
        ctx = _make_ctx(ptb_acquired=False)
        assert rule.evaluate(ctx).state == RuleState.WAITING

    def test_coin_usd_not_fresh_waiting(self):
        """Coin USD stale → WAITING."""
        rule = DeltaRule()
        ctx = _make_ctx(coin_usd_fresh=False)
        assert rule.evaluate(ctx).state == RuleState.WAITING

    def test_doge_small_delta(self):
        """DOGE: abs(0.0921 - 0.0920) = 0.0001 < 0.001 → FAIL."""
        rule = DeltaRule()
        ctx = _make_ctx(
            asset="DOGE",
            coin_usd_price=0.0921,
            ptb_value=0.0920,
            delta_threshold=0.001,
        )
        assert rule.evaluate(ctx).state == RuleState.FAIL

    def test_doge_sufficient_delta_pass(self):
        """DOGE: abs(0.095 - 0.092) = 0.003 >= 0.001 → PASS."""
        rule = DeltaRule()
        ctx = _make_ctx(
            asset="DOGE",
            coin_usd_price=0.095,
            ptb_value=0.092,
            delta_threshold=0.001,
        )
        assert rule.evaluate(ctx).state == RuleState.PASS


# ═══════════════════════════════════════════════════════════════
# SPREAD RULE TESTS — YÜZDE HESABI
# ═══════════════════════════════════════════════════════════════

class TestSpreadRule:

    def test_spread_below_max_pass(self):
        """spread_pct uses entry_ref_price(ask) and exit_ref_price(bid)."""
        rule = SpreadRule()
        # dominant=UP (up_bid=0.84 > down_bid), entry_ref=up_ask=0.86, exit_ref=up_bid=0.84
        ctx = _make_ctx(up_bid=0.84, up_ask=0.86, down_bid=0.14, down_ask=0.16,
                        best_bid=0.84, best_ask=0.86, spread_max_pct=5.0)
        result = rule.evaluate(ctx)
        assert result.state == RuleState.PASS
        assert abs(result.detail["spread_pct"] - 2.3256) < 0.01

    def test_spread_above_max_fail(self):
        """High spread → FAIL."""
        rule = SpreadRule()
        # dominant=UP (up_bid=0.55 > down_bid=0.40), entry_ref=up_ask=0.60, exit_ref=up_bid=0.55
        ctx = _make_ctx(up_bid=0.55, up_ask=0.60, down_bid=0.40, down_ask=0.45,
                        best_bid=0.55, best_ask=0.60, spread_max_pct=3.2)
        assert rule.evaluate(ctx).state == RuleState.FAIL

    def test_spread_formula_entry_ref_based(self):
        """Spread = (entry_ref - exit_ref)/entry_ref*100 — ask bazlı."""
        # dominant=UP (up_bid=0.55 > down_bid=0.43), entry_ref=up_ask=0.57, exit_ref=up_bid=0.55
        ctx = _make_ctx(up_bid=0.55, up_ask=0.57, down_bid=0.43, down_ask=0.45,
                        best_bid=0.55, best_ask=0.57)
        expected = (0.57 - 0.55) / 0.57 * 100
        assert abs(ctx.spread_pct - expected) < 0.001

    def test_spread_decimal_threshold(self):
        """Ondalıklı threshold: 3.2%."""
        rule = SpreadRule()
        # dominant=UP (up_bid=0.55 > down_bid=0.43), entry_ref=up_ask=0.57, exit_ref=up_bid=0.55
        # spread = (0.57 - 0.55) / 0.57 * 100 = 3.508%
        ctx = _make_ctx(up_bid=0.55, up_ask=0.57, down_bid=0.43, down_ask=0.45,
                        best_bid=0.55, best_ask=0.57, spread_max_pct=3.2)
        assert rule.evaluate(ctx).state == RuleState.FAIL  # 3.508 > 3.2

        ctx2 = _make_ctx(up_bid=0.55, up_ask=0.57, down_bid=0.43, down_ask=0.45,
                         best_bid=0.55, best_ask=0.57, spread_max_pct=4.0)
        assert rule.evaluate(ctx2).state == RuleState.PASS  # 3.508 < 4.0

    def test_outcome_not_fresh_waiting(self):
        rule = SpreadRule()
        ctx = _make_ctx(outcome_fresh=False)
        assert rule.evaluate(ctx).state == RuleState.WAITING

    def test_best_ask_zero_waiting(self):
        rule = SpreadRule()
        ctx = _make_ctx(best_ask=0, up_ask=0.0, down_ask=0.0)
        assert rule.evaluate(ctx).state == RuleState.WAITING


# ═══════════════════════════════════════════════════════════════
# EVENT MAX / BOT MAX TESTS — INJECTED COUNTER
# ═══════════════════════════════════════════════════════════════

class TestEventMaxRule:

    def test_below_limit_pass(self):
        """0 fills < max 3 → PASS."""
        rule = EventMaxRule()
        ctx = _make_ctx(event_fill_count=0, event_max_positions=3)
        assert rule.evaluate(ctx).state == RuleState.PASS

    def test_at_limit_fail(self):
        """3 fills >= max 3 → FAIL."""
        rule = EventMaxRule()
        ctx = _make_ctx(event_fill_count=3, event_max_positions=3)
        assert rule.evaluate(ctx).state == RuleState.FAIL

    def test_above_limit_fail(self):
        """5 fills >= max 1 → FAIL."""
        rule = EventMaxRule()
        ctx = _make_ctx(event_fill_count=5, event_max_positions=1)
        assert rule.evaluate(ctx).state == RuleState.FAIL

    def test_disabled(self):
        rule = EventMaxRule()
        ctx = _make_ctx(event_max_enabled=False)
        assert rule.evaluate(ctx).state == RuleState.DISABLED


class TestBotMaxRule:

    def test_below_limit_pass(self):
        """0 open < max 5 → PASS."""
        rule = BotMaxRule()
        ctx = _make_ctx(open_position_count=0, bot_max_positions=5)
        assert rule.evaluate(ctx).state == RuleState.PASS

    def test_at_limit_fail(self):
        """5 open >= max 5 → FAIL."""
        rule = BotMaxRule()
        ctx = _make_ctx(open_position_count=5, bot_max_positions=5)
        assert rule.evaluate(ctx).state == RuleState.FAIL

    def test_disabled(self):
        rule = BotMaxRule()
        ctx = _make_ctx(bot_max_enabled=False)
        assert rule.evaluate(ctx).state == RuleState.DISABLED

    def test_event_max_pass_but_bot_max_fail(self):
        """Event Max pass ama Bot Max fail → overall NO_ENTRY."""
        ctx = _make_ctx(
            event_fill_count=0, event_max_positions=3,  # pass
            open_position_count=5, bot_max_positions=5,  # fail
        )
        engine = RuleEngine()
        result = engine.evaluate(ctx)
        assert result.decision == OverallDecision.NO_ENTRY


# ═══════════════════════════════════════════════════════════════
# EVALUATION CONTEXT TESTS
# ═══════════════════════════════════════════════════════════════

class TestEvaluationContext:

    def test_dominant_price(self):
        ctx = _make_ctx(up_price=0.85, down_price=0.15,
                        up_bid=0.85, up_ask=0.85, down_bid=0.15, down_ask=0.15)
        assert ctx.dominant_price == 0.85
        assert ctx.dominant_side == "UP"
        assert ctx.dominant_price_100 == 85.0

    def test_dominant_down(self):
        ctx = _make_ctx(up_price=0.30, down_price=0.70,
                        up_bid=0.30, up_ask=0.30, down_bid=0.70, down_ask=0.70)
        assert ctx.dominant_price == 0.70
        assert ctx.dominant_side == "DOWN"

    def test_spread_pct(self):
        # dominant=UP (up_bid=0.55 > down_bid=0.43), entry_ref=up_ask=0.57, exit_ref=up_bid=0.55
        ctx = _make_ctx(up_bid=0.55, up_ask=0.57, down_bid=0.43, down_ask=0.45,
                        best_bid=0.55, best_ask=0.57)
        expected = (0.57 - 0.55) / 0.57 * 100
        assert abs(ctx.spread_pct - expected) < 0.001

    def test_delta(self):
        ctx = _make_ctx(coin_usd_price=67310, ptb_value=67260)
        assert ctx.delta == 50.0


# ═══════════════════════════════════════════════════════════════
# BOUNDARY / COUPLING TESTS
# ═══════════════════════════════════════════════════════════════

class TestRuleEngineBoundaries:

    def test_no_snapshot_coupling(self):
        """Rule engine must NOT import snapshot modules."""
        import backend.strategy.engine as mod
        lines = [l.strip() for l in open(mod.__file__, encoding="utf-8").readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "snapshot" not in line

    def test_no_execution_coupling(self):
        """Rule engine must NOT import execution modules."""
        import backend.strategy.engine as mod
        lines = [l.strip() for l in open(mod.__file__, encoding="utf-8").readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "execution" not in line
            assert "position" not in line

    def test_rule_result_frozen(self):
        """RuleResult is frozen — immutable."""
        r = RuleResult(rule_name="test", state=RuleState.PASS)
        with pytest.raises(AttributeError):
            r.state = RuleState.FAIL

    def test_evaluation_result_frozen(self):
        """EvaluationResult is frozen — immutable."""
        r = EvaluationResult(decision=OverallDecision.ENTRY, rule_results=())
        with pytest.raises(AttributeError):
            r.decision = OverallDecision.NO_ENTRY

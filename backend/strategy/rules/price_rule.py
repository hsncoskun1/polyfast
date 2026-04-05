"""PriceRule — side mode'a göre outcome fiyatına bakar.

Side mode davranışı:
- dominant_only → max(up, down)*100, aralık 51-99
- up_only → up_price*100, aralık 1-99
- down_only → down_price*100, aralık 1-99

Outcome verisi yoksa veya stale ise WAITING.
"""

from backend.strategy.base_rule import BaseRule, RuleResult
from backend.strategy.evaluation_context import EvaluationContext
from backend.settings.coin_settings import SideMode


class PriceRule(BaseRule):

    @property
    def name(self) -> str:
        return "price"

    def _is_enabled(self, ctx: EvaluationContext) -> bool:
        return ctx.price_enabled

    def _evaluate(self, ctx: EvaluationContext) -> RuleResult:
        if not ctx.outcome_fresh:
            return self._waiting({"reason": "outcome_data_not_fresh"})

        price_100 = ctx.evaluated_price_100
        side = ctx.evaluated_side
        min_p = ctx.price_min
        max_p = ctx.price_max

        detail = {
            "side_mode": ctx.side_mode.value,
            "evaluated_side": side,
            "evaluated_price_100": round(price_100, 2),
            "up_price": round(ctx.up_price, 4),
            "down_price": round(ctx.down_price, 4),
            "min_price": min_p,
            "max_price": max_p,
        }

        if min_p <= price_100 <= max_p:
            return self._pass(detail)

        return self._fail(detail)

"""PriceRule — dominant tarafın canlı outcome fiyatına bakar.

dominant = max(up_price, down_price), her zaman >= 0.51.
Kullanıcı 51-99 aralığında min/max girer (0-100 ölçeği).
Dominant fiyat bu aralıktaysa PASS.

Outcome verisi yoksa veya stale ise WAITING.
"""

from backend.strategy.base_rule import BaseRule, RuleResult
from backend.strategy.evaluation_context import EvaluationContext


class PriceRule(BaseRule):

    @property
    def name(self) -> str:
        return "price"

    def _is_enabled(self, ctx: EvaluationContext) -> bool:
        return ctx.price_enabled

    def _evaluate(self, ctx: EvaluationContext) -> RuleResult:
        if not ctx.outcome_fresh:
            return self._waiting({"reason": "outcome_data_not_fresh"})

        dominant_100 = ctx.dominant_price_100
        min_p = ctx.price_min
        max_p = ctx.price_max

        detail = {
            "dominant_side": ctx.dominant_side,
            "dominant_price_100": round(dominant_100, 2),
            "up_price": round(ctx.up_price, 4),
            "down_price": round(ctx.down_price, 4),
            "min_price": min_p,
            "max_price": max_p,
        }

        if min_p <= dominant_100 <= max_p:
            return self._pass(detail)

        return self._fail(detail)

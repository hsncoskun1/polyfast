"""SpreadRule — outcome market spread'ine bakar.

Formül: spread_pct = (best_ask - best_bid) / best_ask * 100
best_ask bazlı (mid değil). Coin USD spread'i DEĞİL.
Kullanıcı ondalıklı yüzde girer: 3.2 = max %3.2.

Outcome verisi yoksa veya stale ise WAITING.
"""

from backend.strategy.base_rule import BaseRule, RuleResult
from backend.strategy.evaluation_context import EvaluationContext


class SpreadRule(BaseRule):

    @property
    def name(self) -> str:
        return "spread"

    def _is_enabled(self, ctx: EvaluationContext) -> bool:
        return ctx.spread_enabled

    def _evaluate(self, ctx: EvaluationContext) -> RuleResult:
        if not ctx.outcome_fresh:
            return self._waiting({"reason": "outcome_data_not_fresh"})

        if ctx.best_ask <= 0:
            return self._waiting({"reason": "best_ask_zero"})

        spread_pct = ctx.spread_pct
        max_spread = ctx.spread_max_pct

        detail = {
            "best_bid": round(ctx.best_bid, 4),
            "best_ask": round(ctx.best_ask, 4),
            "spread_pct": round(spread_pct, 4),
            "max_spread_pct": max_spread,
        }

        if spread_pct <= max_spread:
            return self._pass(detail)

        return self._fail(detail)

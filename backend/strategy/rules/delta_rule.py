"""DeltaRule — PTB ile coin'in anlık USD fiyatı arasındaki mutlak fark.

Formül: abs(current_coin_usd_price - PTB)
Sabit USD fark. Yüzde değil. Yön önemsiz.
Outcome price ile hesaplanMAZ — coin canlı USD fiyatı ayrı kaynaktan.

Veri eksikse (coin USD stale veya PTB alınmamış) WAITING.
"""

from backend.strategy.base_rule import BaseRule, RuleResult
from backend.strategy.evaluation_context import EvaluationContext


class DeltaRule(BaseRule):

    @property
    def name(self) -> str:
        return "delta"

    def _is_enabled(self, ctx: EvaluationContext) -> bool:
        return ctx.delta_enabled

    def _evaluate(self, ctx: EvaluationContext) -> RuleResult:
        # PTB alınmamışsa waiting
        if not ctx.ptb_acquired:
            return self._waiting({"reason": "ptb_not_acquired"})

        # Coin USD fiyatı stale/eksikse waiting
        if not ctx.coin_usd_fresh:
            return self._waiting({"reason": "coin_usd_not_fresh"})

        delta = ctx.delta  # abs(coin_usd - PTB)
        threshold = ctx.delta_threshold

        detail = {
            "coin_usd_price": round(ctx.coin_usd_price, 4),
            "ptb_value": round(ctx.ptb_value, 4),
            "delta_usd": round(delta, 4),
            "threshold_usd": threshold,
        }

        if delta >= threshold:
            return self._pass(detail)

        return self._fail(detail)

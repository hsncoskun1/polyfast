"""TimeRule — event'in bitmesine kalan saniyeye bakar.

Kullanıcı min/max saniye girer. Kalan süre aralıktaysa PASS.
Event'in başından beri geçen süre kullanılmaz.
"""

from backend.strategy.base_rule import BaseRule, RuleResult
from backend.strategy.evaluation_context import EvaluationContext


class TimeRule(BaseRule):

    @property
    def name(self) -> str:
        return "time"

    def _is_enabled(self, ctx: EvaluationContext) -> bool:
        return ctx.time_enabled

    def _evaluate(self, ctx: EvaluationContext) -> RuleResult:
        remaining = ctx.seconds_remaining
        min_s = ctx.time_min_seconds
        max_s = ctx.time_max_seconds

        detail = {
            "seconds_remaining": round(remaining, 1),
            "min_seconds": min_s,
            "max_seconds": max_s,
        }

        if remaining <= 0:
            return self._fail({**detail, "reason": "event_expired"})

        if min_s <= remaining <= max_s:
            return self._pass(detail)

        return self._fail(detail)

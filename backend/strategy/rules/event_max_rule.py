"""EventMaxRule — tek 5dk event instance'ı içindeki max işlem sayısı.

Alış fill sayısını sayar. Fill olmayan order sayılmaz.
İşlem kapanmış olsa bile aynı event'te ikinci giriş olmaz.
Yeni event başladığında sıfırlanır.

v0.4.0: Rule contract only — sayaç dışarıdan inject edilir.
v0.5.x: Gerçek fill count position lifecycle'dan gelecek.
"""

from backend.strategy.base_rule import BaseRule, RuleResult
from backend.strategy.evaluation_context import EvaluationContext


class EventMaxRule(BaseRule):

    @property
    def name(self) -> str:
        return "event_max"

    def _is_enabled(self, ctx: EvaluationContext) -> bool:
        return ctx.event_max_enabled

    def _evaluate(self, ctx: EvaluationContext) -> RuleResult:
        fill_count = ctx.event_fill_count
        max_positions = ctx.event_max_positions

        detail = {
            "event_fill_count": fill_count,
            "max_positions": max_positions,
        }

        if fill_count < max_positions:
            return self._pass(detail)

        return self._fail({**detail, "reason": "event_limit_reached"})

"""BotMaxRule — tüm aktif event'ler genelindeki aynı anda açık toplam işlem.

Global üst limit.
Event Max + Bot Max birlikte sağlanmalı — biri doluysa işlem açılamaz.

v0.4.0: Rule contract only — sayaç dışarıdan inject edilir.
v0.5.x: Gerçek open_position_count position lifecycle'dan gelecek.
"""

from backend.strategy.base_rule import BaseRule, RuleResult
from backend.strategy.evaluation_context import EvaluationContext


class BotMaxRule(BaseRule):

    @property
    def name(self) -> str:
        return "bot_max"

    def _is_enabled(self, ctx: EvaluationContext) -> bool:
        return ctx.bot_max_enabled

    def _evaluate(self, ctx: EvaluationContext) -> RuleResult:
        open_count = ctx.open_position_count
        max_positions = ctx.bot_max_positions

        detail = {
            "open_position_count": open_count,
            "max_positions": max_positions,
        }

        if open_count < max_positions:
            return self._pass(detail)

        return self._fail({**detail, "reason": "bot_limit_reached"})

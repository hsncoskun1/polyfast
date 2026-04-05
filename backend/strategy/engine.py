"""RuleEngine — kuralları sırayla değerlendirir, overall karar üretir.

Sıralı çalışır (sequential). Tüm kurallar çalıştırılır (log bütünlüğü).
Erken çıkış yok — her kuralın sonucu kaydedilir.

Overall merge mantığı:
1. Bir enabled kural FAIL → overall NO_ENTRY
2. FAIL yoksa, bir enabled kural WAITING → overall WAITING
3. Tüm enabled kurallar PASS → overall ENTRY
4. Hiç enabled kural yoksa → overall NO_RULES
5. DISABLED kurallar evaluation dışı — PASS sayılmaz

Runtime state'ten evaluation — snapshot'tan DEĞİL.
Kör retry yok — her order denemesi önce yeniden evaluation.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from backend.strategy.base_rule import BaseRule, RuleResult
from backend.strategy.evaluation_context import EvaluationContext
from backend.strategy.rule_state import RuleState, OverallDecision
from backend.strategy.rules.time_rule import TimeRule
from backend.strategy.rules.price_rule import PriceRule
from backend.strategy.rules.delta_rule import DeltaRule
from backend.strategy.rules.spread_rule import SpreadRule
from backend.strategy.rules.event_max_rule import EventMaxRule
from backend.strategy.rules.bot_max_rule import BotMaxRule
from backend.logging_config.service import get_logger, log_event

logger = get_logger("strategy.engine")


@dataclass(frozen=True)
class EvaluationResult:
    """Overall evaluation sonucu."""
    decision: OverallDecision
    rule_results: tuple[RuleResult, ...]
    detail: dict[str, Any] = field(default_factory=dict)

    def get_result(self, rule_name: str) -> RuleResult | None:
        for r in self.rule_results:
            if r.rule_name == rule_name:
                return r
        return None

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.rule_results if r.state == RuleState.PASS)

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.rule_results if r.state == RuleState.FAIL)

    @property
    def waiting_count(self) -> int:
        return sum(1 for r in self.rule_results if r.state == RuleState.WAITING)

    @property
    def disabled_count(self) -> int:
        return sum(1 for r in self.rule_results if r.state == RuleState.DISABLED)


# Kural çalıştırma sırası
_DEFAULT_RULES: list[BaseRule] = [
    TimeRule(),
    PriceRule(),
    DeltaRule(),
    SpreadRule(),
    EventMaxRule(),
    BotMaxRule(),
]


class RuleEngine:
    """Kural değerlendirme motoru.

    Sıralı çalışır. Tüm kurallar çalıştırılır (log bütünlüğü).
    Overall karar: fail baskın → no_entry, waiting → waiting, hepsi pass → entry.
    """

    def __init__(self, rules: list[BaseRule] | None = None):
        self._rules = rules or list(_DEFAULT_RULES)

    def evaluate(self, ctx: EvaluationContext) -> EvaluationResult:
        """Tüm kuralları sırayla değerlendir ve overall karar üret.

        Her evaluation güncel context gerektirir — stale context yasak.
        Kör retry yok — her çağrı bağımsız.
        """
        results: list[RuleResult] = []

        for rule in self._rules:
            try:
                result = rule.evaluate(ctx)
                results.append(result)
            except Exception as e:
                # Kural patlarsa güvenli FAIL
                results.append(RuleResult(
                    rule_name=rule.name,
                    state=RuleState.FAIL,
                    detail={"error": str(e), "exception": True},
                ))
                log_event(
                    logger, logging.ERROR,
                    f"Rule exception: {rule.name} — {e}",
                    entity_type="rule_engine",
                    entity_id=rule.name,
                )

        # Overall merge
        decision = self._merge_decision(results)

        evaluation = EvaluationResult(
            decision=decision,
            rule_results=tuple(results),
            detail={
                "asset": ctx.asset,
                "condition_id": ctx.condition_id,
                "dominant_side": ctx.dominant_side,
            },
        )

        log_event(
            logger, logging.INFO,
            f"Evaluation: {ctx.asset} → {decision.value} "
            f"(pass={evaluation.pass_count} fail={evaluation.fail_count} "
            f"waiting={evaluation.waiting_count} disabled={evaluation.disabled_count})",
            entity_type="rule_engine",
            entity_id=ctx.condition_id,
        )

        return evaluation

    @staticmethod
    def _merge_decision(results: list[RuleResult]) -> OverallDecision:
        """Overall karar merge mantığı.

        1. FAIL baskın → NO_ENTRY
        2. FAIL yok, WAITING var → WAITING
        3. Tüm enabled PASS → ENTRY
        4. Hiç enabled kural yok → NO_RULES
        """
        has_fail = False
        has_waiting = False
        has_pass = False

        for r in results:
            if r.state == RuleState.DISABLED:
                continue  # evaluation dışı
            elif r.state == RuleState.FAIL:
                has_fail = True
            elif r.state == RuleState.WAITING:
                has_waiting = True
            elif r.state == RuleState.PASS:
                has_pass = True

        if has_fail:
            return OverallDecision.NO_ENTRY
        if has_waiting:
            return OverallDecision.WAITING
        if has_pass:
            return OverallDecision.ENTRY
        return OverallDecision.NO_RULES

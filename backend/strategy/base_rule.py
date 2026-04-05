"""BaseRule — tüm kuralların implement edeceği soyut temel sınıf.

Her kural:
- evaluate(ctx) → RuleResult döner
- enabled=False ise DISABLED döner (PASS değil)
- Veri eksikse WAITING döner (PASS/FAIL vermez)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from backend.strategy.rule_state import RuleState
from backend.strategy.evaluation_context import EvaluationContext


@dataclass(frozen=True)
class RuleResult:
    """Tek kural değerlendirme sonucu."""
    rule_name: str
    state: RuleState
    detail: dict[str, Any] = field(default_factory=dict)


class BaseRule(ABC):
    """Soyut kural sınıfı. Tüm kurallar bunu implement eder."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Kural adı (unique)."""
        ...

    @abstractmethod
    def _evaluate(self, ctx: EvaluationContext) -> RuleResult:
        """Kural değerlendirmesi. Alt sınıflar bunu implement eder."""
        ...

    def evaluate(self, ctx: EvaluationContext) -> RuleResult:
        """Kural değerlendir. Disabled kontrolünü otomatik yapar."""
        if not self._is_enabled(ctx):
            return RuleResult(
                rule_name=self.name,
                state=RuleState.DISABLED,
                detail={"reason": "rule disabled by user"},
            )
        return self._evaluate(ctx)

    @abstractmethod
    def _is_enabled(self, ctx: EvaluationContext) -> bool:
        """Bu kural context'e göre enabled mı?"""
        ...

    def _pass(self, detail: dict | None = None) -> RuleResult:
        return RuleResult(rule_name=self.name, state=RuleState.PASS, detail=detail or {})

    def _fail(self, detail: dict | None = None) -> RuleResult:
        return RuleResult(rule_name=self.name, state=RuleState.FAIL, detail=detail or {})

    def _waiting(self, detail: dict | None = None) -> RuleResult:
        return RuleResult(rule_name=self.name, state=RuleState.WAITING, detail=detail or {})

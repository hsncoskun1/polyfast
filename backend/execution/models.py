"""Execution models — order validation sonuclari.

ValidationResult: OrderIntent'in validation sonucu.
VALID ise order gonderilebilir. REJECTED ise gonderilmez + sebep.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ValidationStatus(str, Enum):
    """Order validation sonucu."""
    VALID = "valid"           # order gonderilebilir
    REJECTED = "rejected"    # order reddedildi


class RejectReason(str, Enum):
    """Order reject sebepleri."""
    INSUFFICIENT_BALANCE = "insufficient_balance"
    BELOW_MINIMUM_AMOUNT = "below_minimum_amount"
    EVENT_MAX_REACHED = "event_max_reached"
    BOT_MAX_REACHED = "bot_max_reached"
    MISSING_TOKEN_ID = "missing_token_id"
    MISSING_CONDITION_ID = "missing_condition_id"


@dataclass(frozen=True)
class ValidationResult:
    """Order validation sonucu.

    VALID: order gonderilebilir.
    REJECTED: order gonderilmez, reason ve detail ile aciklanir.
    """
    status: ValidationStatus
    reason: RejectReason | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return self.status == ValidationStatus.VALID

    @property
    def is_rejected(self) -> bool:
        return self.status == ValidationStatus.REJECTED

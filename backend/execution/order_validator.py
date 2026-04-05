"""OrderValidator — order intent'in gonderilebilirligini kontrol eder.

Kontroller:
1. amount_usd >= 1.0 (Polymarket minimum — guard/default, venue validation'a tasinabilir)
2. available_balance >= amount_usd
3. event_fill_count < event_max (Event Max — v0.5.0'da read/validation, v0.5.1'de gercek enforcement)
4. open_position_count < bot_max (Bot Max — v0.5.0'da read/validation, v0.5.1'de gercek enforcement)
5. token_id ve condition_id mevcut

Tum kontroller pass → VALID
Biri fail → REJECTED + reason

Bu validator order GONDERMEZ — sadece gonderilebilir mi kontrol eder.
Gercek order execution v0.5.2'de.
"""

import logging
from backend.execution.order_intent import OrderIntent
from backend.execution.models import ValidationResult, ValidationStatus, RejectReason
from backend.logging_config.service import get_logger, log_event

logger = get_logger("execution.validator")

# Polymarket minimum order — guard/default.
# ileride config/venue validation katmanina tasinabilir.
MINIMUM_ORDER_USD = 1.0


class OrderValidator:
    """Order intent validation.

    Event Max / Bot Max kontrolleri v0.5.0'da read seviyesinde:
    - Disaridan inject edilen sayaclarla calisir
    - Gercek sayac enforcement v0.5.1'de PositionTracker ile gelecek
    """

    def validate(
        self,
        intent: OrderIntent,
        available_balance: float,
        event_fill_count: int,
        event_max: int,
        open_position_count: int,
        bot_max: int,
        has_pending_claims: bool = False,
        wait_for_claim_redeem: bool = True,
    ) -> ValidationResult:
        """OrderIntent'i validate et.

        Args:
            intent: Order niyeti
            available_balance: Mevcut kullanilabilir bakiye (USD)
            event_fill_count: Bu event'teki alis fill sayisi (v0.5.1'de gercek)
            event_max: Bu event icin max islem sayisi
            open_position_count: Tum event'lerdeki acik pozisyon sayisi (v0.5.1'de gercek)
            bot_max: Global max acik pozisyon

        Returns:
            ValidationResult — VALID veya REJECTED + reason
        """
        # 0. Claim/redeem bekliyor mu
        if wait_for_claim_redeem and has_pending_claims:
            return self._reject(
                RejectReason.CLAIM_PENDING,
                intent,
                {"has_pending_claims": True},
            )

        # 1. Token ID ve condition_id mevcut mu
        if not intent.token_id:
            return self._reject(
                RejectReason.MISSING_TOKEN_ID,
                intent,
                {"token_id": intent.token_id},
            )

        if not intent.condition_id:
            return self._reject(
                RejectReason.MISSING_CONDITION_ID,
                intent,
                {"condition_id": intent.condition_id},
            )

        # 2. Minimum tutar kontrolu
        if intent.amount_usd < MINIMUM_ORDER_USD:
            return self._reject(
                RejectReason.BELOW_MINIMUM_AMOUNT,
                intent,
                {
                    "amount_usd": intent.amount_usd,
                    "minimum": MINIMUM_ORDER_USD,
                },
            )

        # 3. Balance kontrolu
        if available_balance < intent.amount_usd:
            return self._reject(
                RejectReason.INSUFFICIENT_BALANCE,
                intent,
                {
                    "amount_usd": intent.amount_usd,
                    "available_balance": available_balance,
                    "shortfall": round(intent.amount_usd - available_balance, 2),
                },
            )

        # 4. Event Max kontrolu
        if event_fill_count >= event_max:
            return self._reject(
                RejectReason.EVENT_MAX_REACHED,
                intent,
                {
                    "event_fill_count": event_fill_count,
                    "event_max": event_max,
                },
            )

        # 5. Bot Max kontrolu
        if open_position_count >= bot_max:
            return self._reject(
                RejectReason.BOT_MAX_REACHED,
                intent,
                {
                    "open_position_count": open_position_count,
                    "bot_max": bot_max,
                },
            )

        # Tum kontroller gecti
        log_event(
            logger, logging.INFO,
            f"Order intent VALID: {intent.asset} {intent.side.value} ${intent.amount_usd}",
            entity_type="execution",
            entity_id=intent.condition_id,
            payload={
                "asset": intent.asset,
                "side": intent.side.value,
                "amount_usd": intent.amount_usd,
            },
        )

        return ValidationResult(
            status=ValidationStatus.VALID,
            detail={
                "asset": intent.asset,
                "side": intent.side.value,
                "amount_usd": intent.amount_usd,
                "available_balance": available_balance,
            },
        )

    def _reject(
        self,
        reason: RejectReason,
        intent: OrderIntent,
        detail: dict,
    ) -> ValidationResult:
        """Reject ile logla."""
        log_event(
            logger, logging.WARNING,
            f"Order intent REJECTED: {intent.asset} {intent.side.value} — {reason.value}",
            entity_type="execution",
            entity_id=intent.condition_id,
            payload={"reason": reason.value, **detail},
        )

        return ValidationResult(
            status=ValidationStatus.REJECTED,
            reason=reason,
            detail=detail,
        )

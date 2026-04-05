"""OrderExecutor — Market FOK order gonderme + paper mode + reconciliation.

Akis (v0.5.2 guncel):
1. OrderIntent + validation gecti
2. Balance stale guard
3. Pending position olustur (SADECE order gonderme asamasinda)
4. Order gonder:
   - LIVE: py-clob-client SDK — SDK feeRateBps'yi otomatik halleder
   - PAPER: simule fill (dominant_price, default fee_rate)
5. Fill reconciliation:
   - FILLED → confirm_fill (fee_rate fill response'tan alinir)
   - NOT_FILLED → reject_fill
   - NETWORK_ERROR → reconcile
6. Post-fill balance refresh

ONEMLI DEGISIKLIK:
- Live execution akisinda ayri manual fee fetch ADIMI YOK
- SDK order gonderirken feeRateBps'yi otomatik ceker ve payload'a ekler
- Gereksiz pre-order fee fetch round trip KALDIRILDI
- Bot accounting icin fee_rate fill response'tan authoritative olarak alinir

Kurallar:
- Validator reject ise pending position OLUSMAZ
- Network error pre-send ise pending ACILMAZ
- Blind retry YOK — buy re-attempt yeniden evaluation gerektirir

Exit latch notu (implement edilmiyor ama korunuyor):
- TP/SL/force sell trigger LATCH — bir kez tetiklendikten sonra iptal edilmez
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from backend.execution.order_intent import OrderIntent
from backend.execution.order_validator import OrderValidator
from backend.execution.position_tracker import PositionTracker
from backend.execution.balance_manager import BalanceManager
from backend.execution.fee_rate_fetcher import FeeRateFetcher
from backend.execution.models import ValidationResult, ValidationStatus, RejectReason
from backend.logging_config.service import get_logger, log_event

logger = get_logger("execution.executor")


class ExecutionMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class OrderResult(str, Enum):
    FILLED = "filled"
    NOT_FILLED = "not_filled"
    NETWORK_ERROR = "network_error"
    REJECTED = "rejected"
    BALANCE_STALE = "balance_stale"


@dataclass
class ExecutionResult:
    """Order execution sonucu."""
    result: OrderResult
    position_id: str | None = None
    fill_price: float = 0.0
    fee_rate: float = 0.0
    detail: dict | None = None


class OrderExecutor:
    """Market FOK order executor.

    Paper mode: gercek CLOB API cagrilmaz, fill simule edilir.
    Live mode: py-clob-client SDK ile order gonderilir.
                SDK feeRateBps'yi otomatik halleder.
                Ayri fee fetch adimi YOK.
    """

    def __init__(
        self,
        tracker: PositionTracker,
        balance_manager: BalanceManager,
        validator: OrderValidator,
        fee_fetcher: FeeRateFetcher | None = None,
        mode: ExecutionMode = ExecutionMode.PAPER,
    ):
        self._tracker = tracker
        self._balance = balance_manager
        self._validator = validator
        self._fee_fetcher = fee_fetcher or FeeRateFetcher()  # paper mode helper
        self._mode = mode
        self._execution_count: int = 0
        self._fill_count: int = 0
        self._reject_count: int = 0

    @property
    def mode(self) -> ExecutionMode:
        return self._mode

    @property
    def execution_count(self) -> int:
        return self._execution_count

    @property
    def fill_count(self) -> int:
        return self._fill_count

    async def execute(self, intent: OrderIntent) -> ExecutionResult:
        """Order intent'i execute et.

        LIVE akis:
        1. Balance stale guard
        2. Validation (balance, EventMax, BotMax)
        3. Pending position (burda olusur — order gonderme asamasi)
        4. SDK ile Market FOK order gonder (SDK fee_rate'i otomatik halleder)
        5. Fill response'tan fee_rate al → confirm_fill
        6. Post-fill balance refresh

        PAPER akis:
        1-2. Ayni
        3. Pending position
        4. Simule fill (dominant_price + default fee_rate)
        5. confirm_fill
        6. Paper balance deduct
        """
        self._execution_count += 1

        # 1. Balance stale guard
        if self._balance.is_stale:
            log_event(
                logger, logging.WARNING,
                f"Execution rejected: balance stale ({self._balance.age_seconds:.0f}s)",
                entity_type="execution",
                entity_id=intent.condition_id,
            )
            return ExecutionResult(result=OrderResult.BALANCE_STALE)

        # 2. Validation
        validation = self._validator.validate(
            intent,
            available_balance=self._balance.available_balance,
            event_fill_count=self._tracker.get_event_fill_count(intent.condition_id),
            event_max=1,  # coin settings'ten gelecek
            open_position_count=self._tracker.open_position_count,
            bot_max=3,  # coin settings'ten gelecek
        )

        if validation.is_rejected:
            self._reject_count += 1
            return ExecutionResult(
                result=OrderResult.REJECTED,
                detail={"reason": validation.reason.value if validation.reason else "unknown"},
            )

        # 3. Pending position — SADECE order gonderme asamasinda
        position = self._tracker.create_pending(
            asset=intent.asset,
            side=intent.side.value,
            condition_id=intent.condition_id,
            token_id=intent.token_id,
            requested_amount_usd=intent.amount_usd,
        )

        # 4. Order gonder
        if self._mode == ExecutionMode.PAPER:
            return await self._execute_paper(intent, position)
        else:
            return await self._execute_live(intent, position)

    async def _execute_paper(self, intent: OrderIntent, position) -> ExecutionResult:
        """Paper mode — simule fill.

        Fill price = dominant_price (iyimser varsayim).
        Fee rate = default guard (0.072).
        Bu authoritative fill DEGIL — simulated.
        """
        fill_price = intent.dominant_price  # iyimser varsayim
        fee_rate = self._fee_fetcher.get_default_rate()

        # Fill confirm
        self._tracker.confirm_fill(
            position.position_id,
            fill_price=fill_price,
            fee_rate=fee_rate,
        )
        self._fill_count += 1

        # Paper balance deduct
        self._balance.deduct(intent.amount_usd)

        log_event(
            logger, logging.INFO,
            f"PAPER FILLED: {intent.asset} {intent.side.value} "
            f"${intent.amount_usd} @ {fill_price:.4f} fee={fee_rate}",
            entity_type="execution",
            entity_id=position.position_id,
        )

        return ExecutionResult(
            result=OrderResult.FILLED,
            position_id=position.position_id,
            fill_price=fill_price,
            fee_rate=fee_rate,
            detail={"mode": "paper", "note": "simulated fill — iyimser varsayim"},
        )

    async def _execute_live(self, intent: OrderIntent, position) -> ExecutionResult:
        """Live mode — TEKNIK GUARD ile KAPALI.

        LIVE_ORDER_ENABLED = False oldukca gercek order CIKMAZ.
        SDK wiring hazir ama order gonderme bilinçli olarak devre disi.
        Bu guard True yapilmadan canli order riski SIFIR.

        Gercek order akisi (guard acildiginda):
        1. SDK feeRateBps'yi token_id icin otomatik ceker
        2. Signed order payload olusturur
        3. CLOB API'ye gonderir
        4. Response: filled/not_filled + fill_price + fee bilgisi
        5. fill_price ve fee_rate response'tan PositionRecord'a yazilir
        """
        from backend.execution.clob_client_wrapper import LIVE_ORDER_ENABLED

        if not LIVE_ORDER_ENABLED:
            # TEKNIK GUARD — gercek order CIKMAZ
            self._tracker.reject_fill(position.position_id)

            log_event(
                logger, logging.WARNING,
                f"LIVE ORDER BLOCKED by technical guard — LIVE_ORDER_ENABLED=False",
                entity_type="execution",
                entity_id=position.position_id,
            )

            return ExecutionResult(
                result=OrderResult.NOT_FILLED,
                position_id=position.position_id,
                detail={"mode": "live", "guard": "LIVE_ORDER_ENABLED=False"},
            )

        # Guard acik oldugunda gercek SDK order buraya gelecek
        # TODO: self._clob_wrapper.send_market_fok_order(...)
        self._tracker.reject_fill(position.position_id)
        return ExecutionResult(
            result=OrderResult.NOT_FILLED,
            position_id=position.position_id,
        )

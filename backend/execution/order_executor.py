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
        clob_wrapper=None,
        mode: ExecutionMode = ExecutionMode.PAPER,
        bot_max: int = 3,
    ):
        self._tracker = tracker
        self._balance = balance_manager
        self._validator = validator
        self._fee_fetcher = fee_fetcher or FeeRateFetcher()
        self._clob_wrapper = clob_wrapper  # ClobClientWrapper — live mode icin
        self._mode = mode
        self._bot_max = bot_max  # config'ten
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
            event_max=getattr(intent, 'event_max', 1),  # OrderIntent'ten
            open_position_count=self._tracker.open_position_count,
            bot_max=self._bot_max,  # config'ten
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
        Fee rate = default guard (0.10, crypto 5M: base_fee=1000 bps).
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
        """Live mode — SDK FOK market order.

        Cift kilit:
          1. LIVE_ORDER_ENABLED=False → order cikmaz (source code guard)
          2. ExecutionMode.LIVE olmali (config'ten)

        Akis:
          SDK fee_rate_bps otomatik ceker → signed order → post FOK
          Response: matched → confirm_fill, not_matched → reject_fill

        Fee accounting:
          SDK order'a yazdigi fee_rate_bps response'tan okunur.
          feeRate = fee_rate_bps / 10000
          Bu deger confirm_fill'e gecer → PositionRecord.fee_rate authoritative.

        Retry: FOK icin ayni order retry YOK.
          Network timeout icin SDK ici tek retry var.
          Bir sonraki ENTRY sinyal yeni evaluation gerektirir.
        """
        from backend.execution.clob_client_wrapper import LIVE_ORDER_ENABLED

        if not LIVE_ORDER_ENABLED:
            self._tracker.reject_fill(position.position_id)
            log_event(
                logger, logging.WARNING,
                "LIVE ORDER BLOCKED — LIVE_ORDER_ENABLED=False",
                entity_type="execution",
                entity_id=position.position_id,
            )
            return ExecutionResult(
                result=OrderResult.NOT_FILLED,
                position_id=position.position_id,
                detail={"mode": "live", "guard": "LIVE_ORDER_ENABLED=False"},
            )

        # SDK order gonder
        response = await self._clob_wrapper.send_market_fok_order(
            token_id=intent.token_id,
            side="BUY",  # outcome token satin al
            amount=intent.amount_usd,  # BUY = USD tutar
        )

        if response is None:
            # SDK init fail veya guard
            self._tracker.reject_fill(position.position_id)
            return ExecutionResult(
                result=OrderResult.NETWORK_ERROR,
                position_id=position.position_id,
                detail={"error": "SDK returned None"},
            )

        status = response.get("status", "error")
        order_id = response.get("order_id", "")

        if status == "matched":
            # Fill — fee accounting
            fee_bps = response.get("fee_rate_bps", 0)
            fee_rate = fee_bps / 10000.0 if fee_bps > 0 else self._fee_fetcher.get_default_rate()

            # makingAmount = shares acquired, takingAmount = USDC spent
            # fill_price hesabi: BUY'da making=shares, taking=USDC
            # fill_price = USDC / shares (eger her ikisi de > 0 ise)
            making = response.get("making_amount", 0)
            taking = response.get("taking_amount", 0)

            if making > 0 and taking > 0:
                fill_price = taking / making  # USDC per share
            else:
                fill_price = intent.dominant_price  # fallback

            self._tracker.confirm_fill(
                position.position_id,
                fill_price=fill_price,
                fee_rate=fee_rate,
            )
            self._fill_count += 1

            # Balance: SDK zaten USDC dusmus, ama balance refresh
            # Post-fill balance fetch (async, non-blocking)
            try:
                await self._balance.fetch()
            except Exception:
                pass  # fetch fail balance authority'yi bozmaz

            log_event(
                logger, logging.INFO,
                f"LIVE FILLED: {intent.asset} {intent.side.value} "
                f"${intent.amount_usd} fill_price={fill_price:.4f} "
                f"fee_rate={fee_rate} order={order_id[:12]}",
                entity_type="execution",
                entity_id=position.position_id,
            )

            return ExecutionResult(
                result=OrderResult.FILLED,
                position_id=position.position_id,
                fill_price=fill_price,
                fee_rate=fee_rate,
                detail={
                    "mode": "live",
                    "order_id": order_id,
                    "making": making,
                    "taking": taking,
                    "fee_rate_bps": fee_bps,
                },
            )

        # Not matched veya error
        self._tracker.reject_fill(position.position_id)

        result_type = OrderResult.NOT_FILLED if status == "not_matched" else OrderResult.NETWORK_ERROR

        log_event(
            logger, logging.WARNING,
            f"LIVE {status.upper()}: {intent.asset} {intent.side.value} "
            f"${intent.amount_usd} error={response.get('error', '')} order={order_id}",
            entity_type="execution",
            entity_id=position.position_id,
        )

        return ExecutionResult(
            result=result_type,
            position_id=position.position_id,
            detail={"mode": "live", "status": status, "error": response.get("error", ""), "order_id": order_id},
        )

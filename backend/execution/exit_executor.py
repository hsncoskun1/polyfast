"""ExitExecutor — closing_requested pozisyonlar icin sell order gonder.

Akis:
1. ExitEvaluator tetik verdi → closing_requested
2. ExitExecutor: Market FOK sell order (paper mode)
3. Fill → confirm_close → net_realized_pnl sabitlenir
4. Not filled → close_failed → retry (latch korunur)

Retry bandlari (admin/advanced — evaluation araligi DEGIL,
tetik olustuktan sonra close denemeleri arasindaki bekleme suresi):
- TP: 400ms
- Normal sell / manual close: 400ms
- SL: 250ms
- Force sell: 200ms

Latch:
- close_failed → retry sirasinda close_reason/trigger_set SILINMEZ
- TP reevaluate=True ise retry oncesi should_cancel_close() kontrol edilir
- SL/force sell: kontrol YOK, latch zorunlu

Paper mode:
- Gercek sell order gonderilmez
- Fill price = current_price (iyimser varsayim)
"""

import asyncio
import logging
from datetime import datetime, timezone

from backend.execution.position_record import PositionRecord, PositionState
from backend.execution.position_tracker import PositionTracker
from backend.execution.balance_manager import BalanceManager
from backend.execution.close_reason import CloseReason
from backend.execution.exit_evaluator import ExitEvaluator
from backend.execution.fee_rate_fetcher import FeeRateFetcher
from backend.logging_config.service import get_logger, log_event

logger = get_logger("execution.exit_executor")

# Retry intervaller — admin/advanced (ms)
RETRY_INTERVALS_MS = {
    CloseReason.TAKE_PROFIT: 400,
    CloseReason.STOP_LOSS: 250,
    CloseReason.FORCE_SELL: 200,
    CloseReason.MANUAL_CLOSE: 400,
    CloseReason.EXPIRY: 200,
    CloseReason.SYSTEM_SHUTDOWN: 100,
}

DEFAULT_RETRY_INTERVAL_MS = 400
MAX_CLOSE_RETRIES = 10


class ExitExecutor:
    """Closing_requested pozisyonlar icin sell order gonderir.

    Paper mode: gercek order yok, simulated fill.
    Live mode: SDK ile Market FOK sell (ileride).
    """

    def __init__(
        self,
        tracker: PositionTracker,
        balance_manager: BalanceManager,
        exit_evaluator: ExitEvaluator | None = None,
        fee_fetcher: FeeRateFetcher | None = None,
        paper_mode: bool = True,
    ):
        self._tracker = tracker
        self._balance = balance_manager
        self._evaluator = exit_evaluator
        self._fee_fetcher = fee_fetcher or FeeRateFetcher()
        self._paper_mode = paper_mode
        self._close_count: int = 0
        self._retry_count: int = 0

    @property
    def close_count(self) -> int:
        return self._close_count

    @property
    def retry_count(self) -> int:
        return self._retry_count

    async def execute_close(
        self,
        position: PositionRecord,
        current_price: float,
    ) -> bool:
        """Pozisyonu kapat — sell order gonder.

        Args:
            position: closing_requested veya close_failed state'te pozisyon
            current_price: Canli held-side outcome fiyati

        Returns:
            True: basarili close (closed state)
            False: basarisiz (close_failed, retry gerekli)
        """
        if position.state not in (
            PositionState.CLOSING_REQUESTED,
            PositionState.CLOSE_FAILED,
        ):
            return False

        # TP reevaluate kontrolu
        if (
            position.state == PositionState.CLOSING_REQUESTED
            and position.close_reason == CloseReason.TAKE_PROFIT
            and self._evaluator is not None
        ):
            if self._evaluator.should_cancel_close(position, current_price):
                # TP artik saglanmiyor → iptal → open_confirmed
                position.transition_to(PositionState.OPEN_CONFIRMED)
                position.close_reason = None
                position.close_trigger_set = []
                position.close_triggered_at = None

                log_event(
                    logger, logging.INFO,
                    f"TP reevaluate cancel: {position.asset} → back to open",
                    entity_type="exit_executor",
                    entity_id=position.position_id,
                )
                return False

        # close_failed → closing_requested (retry, latch korunur)
        if position.state == PositionState.CLOSE_FAILED:
            position.transition_to(PositionState.CLOSING_REQUESTED)
            self._retry_count += 1

        # closing_requested → close_pending
        position.transition_to(PositionState.CLOSE_PENDING)

        # Sell order gonder
        if self._paper_mode:
            fill_price = current_price  # paper: iyimser varsayim
            fee_rate = self._fee_fetcher.get_default_rate()
            success = True
        else:
            # Live mode — SDK sell order (ileride)
            fill_price = 0.0
            fee_rate = 0.0
            success = False

        if success:
            # confirm_close → net_realized_pnl sabitlenir
            self._tracker.confirm_close(
                position.position_id,
                exit_fill_price=fill_price,
                fee_rate=fee_rate,
            )
            self._close_count += 1

            # Post-close balance refresh
            if self._paper_mode:
                self._balance.add(position.net_exit_usdc)
            else:
                await self._balance.fetch()

            log_event(
                logger, logging.INFO,
                f"Position closed: {position.asset} {position.side} "
                f"exit={fill_price:.4f} net_pnl=${position.net_realized_pnl:.4f} "
                f"reason={position.close_reason.value if position.close_reason else 'none'}",
                entity_type="exit_executor",
                entity_id=position.position_id,
            )
            return True
        else:
            # close_failed
            position.transition_to(PositionState.CLOSE_FAILED)

            log_event(
                logger, logging.WARNING,
                f"Close failed: {position.asset} — retry gerekli",
                entity_type="exit_executor",
                entity_id=position.position_id,
            )
            return False

    async def execute_close_with_retry(
        self,
        position: PositionRecord,
        current_price: float,
        max_retries: int = MAX_CLOSE_RETRIES,
    ) -> bool:
        """Retry ile pozisyon kapat.

        Retry interval close_reason'a gore belirlenir.
        Latch korunur — close_reason/trigger_set silinmez.

        Returns:
            True: basarili close, False: tum retryler tukendi
        """
        reason = position.close_reason or CloseReason.MANUAL_CLOSE
        interval_ms = RETRY_INTERVALS_MS.get(reason, DEFAULT_RETRY_INTERVAL_MS)
        interval_sec = interval_ms / 1000.0

        for attempt in range(max_retries):
            success = await self.execute_close(position, current_price)
            if success:
                return True

            # TP reevaluate iptal ettiyse → pozisyon acik, retry durur
            if position.is_open:
                return False

            if attempt < max_retries - 1:
                await asyncio.sleep(interval_sec)

        log_event(
            logger, logging.ERROR,
            f"Close retries exhausted: {position.asset} after {max_retries} attempts",
            entity_type="exit_executor",
            entity_id=position.position_id,
        )
        return False

    @staticmethod
    def get_retry_interval_ms(reason: CloseReason) -> int:
        """Close reason'a gore retry interval (ms)."""
        return RETRY_INTERVALS_MS.get(reason, DEFAULT_RETRY_INTERVAL_MS)

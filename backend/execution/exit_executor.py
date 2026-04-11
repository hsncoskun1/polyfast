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
import time as _time
from datetime import datetime, timezone

from backend.execution.position_record import PositionRecord, PositionState
from backend.execution.position_tracker import PositionTracker
from backend.execution.balance_manager import BalanceManager
from backend.execution.close_reason import CloseReason
from backend.execution.exit_evaluator import ExitEvaluator
from backend.execution.fee_rate_fetcher import FeeRateFetcher
from backend.logging_config.service import get_logger, log_event

logger = get_logger("execution.exit_executor")

# Default retry intervaller — schema'dan override edilebilir
DEFAULT_RETRY_INTERVALS_MS = {
    CloseReason.TAKE_PROFIT: 400,
    CloseReason.STOP_LOSS: 250,
    CloseReason.FORCE_SELL: 200,
    CloseReason.MANUAL_CLOSE: 400,
    CloseReason.EXPIRY: 200,
    CloseReason.SYSTEM_SHUTDOWN: 100,
}

DEFAULT_RETRY_INTERVAL_MS = 400
DEFAULT_MAX_CLOSE_RETRIES = 10


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
        clob_wrapper=None,
        paper_mode: bool = True,
        tp_retry_interval_ms: int = 400,
        sl_retry_interval_ms: int = 500,
        fs_retry_interval_ms: int = 500,
        manual_close_retry_interval_ms: int = 400,
        expiry_retry_interval_ms: int = 200,
        shutdown_retry_interval_ms: int = 100,
        max_close_retries: int = DEFAULT_MAX_CLOSE_RETRIES,
        close_fail_cooldown_sec: float = 1.0,
        exit_order_timeout_sec: float = 5.0,
    ):
        self._tracker = tracker
        self._balance = balance_manager
        self._evaluator = exit_evaluator
        self._fee_fetcher = fee_fetcher or FeeRateFetcher()
        self._clob_wrapper = clob_wrapper
        self._retry_intervals = {
            CloseReason.TAKE_PROFIT: tp_retry_interval_ms,
            CloseReason.STOP_LOSS: sl_retry_interval_ms,
            CloseReason.FORCE_SELL: fs_retry_interval_ms,
            CloseReason.MANUAL_CLOSE: manual_close_retry_interval_ms,
            CloseReason.EXPIRY: expiry_retry_interval_ms,
            CloseReason.SYSTEM_SHUTDOWN: shutdown_retry_interval_ms,
        }
        self._max_close_retries = max_close_retries
        self._paper_mode = paper_mode
        self._close_count: int = 0
        self._retry_count: int = 0
        # Cooldown: CLOSE_FAILED sonrasi anlik retry spam engeli
        self._close_fail_cooldown_sec = close_fail_cooldown_sec
        self._exit_order_timeout = exit_order_timeout_sec
        self._last_close_fail_at: dict[str, float] = {}  # position_id → fail timestamp

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

        # Cooldown guard — CLOSE_FAILED sonrasi anlik retry spam engeli
        # Son fail'den cooldown_sec dolmadan tekrar deneme
        if position.state == PositionState.CLOSE_FAILED:
            last_fail = self._last_close_fail_at.get(position.position_id)
            if last_fail is not None:
                elapsed = _time.time() - last_fail
                if elapsed < self._close_fail_cooldown_sec:
                    return False  # cooldown dolmadi, skip

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
            fill_price = current_price
            fee_rate = self._fee_fetcher.get_default_rate()
            success = True
        else:
            # Live mode — SDK FOK sell order
            # SELL amount = net_position_shares (TAMAMI, parca kalmaz)
            success, fill_price, fee_rate = await self._execute_live_sell(position)

        if success:
            # confirm_close → net_realized_pnl sabitlenir
            self._tracker.confirm_close(
                position.position_id,
                exit_fill_price=fill_price,
                fee_rate=fee_rate,
            )
            self._close_count += 1

            # Cooldown temizle — basarili close
            self._last_close_fail_at.pop(position.position_id, None)

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
            # close_failed — cooldown timestamp kaydet
            position.transition_to(PositionState.CLOSE_FAILED)
            self._last_close_fail_at[position.position_id] = _time.time()

            log_event(
                logger, logging.WARNING,
                f"Close failed: {position.asset} — retry after {self._close_fail_cooldown_sec}s cooldown",
                entity_type="exit_executor",
                entity_id=position.position_id,
            )
            return False

    async def _execute_live_sell(
        self, position: PositionRecord,
    ) -> tuple[bool, float, float]:
        """Live SDK SELL order — net_position_shares TAMAMI satilir.

        SELL semantik: amount = share sayisi (USD degil).
        Polymarket docs: BUY=USD, SELL=shares.

        Returns:
            (success, fill_price, fee_rate)
        """
        if self._clob_wrapper is None:
            log_event(
                logger, logging.ERROR,
                f"Live sell: clob_wrapper not set — cannot sell",
                entity_type="exit_executor",
                entity_id=position.position_id,
            )
            return False, 0.0, 0.0

        sell_amount = position.net_position_shares  # TAMAMI
        if sell_amount <= 0:
            log_event(
                logger, logging.ERROR,
                f"Live sell: net_position_shares={sell_amount} — nothing to sell",
                entity_type="exit_executor",
                entity_id=position.position_id,
            )
            return False, 0.0, 0.0

        response = await self._clob_wrapper.send_market_fok_order(
            token_id=position.token_id,
            side="SELL",
            amount=sell_amount,
            timeout_sec=self._exit_order_timeout,
        )

        if response is None:
            return False, 0.0, 0.0

        status = response.get("status", "error")

        if status == "matched":
            fee_bps = response.get("fee_rate_bps", 0)
            fee_rate = fee_bps / 10000.0 if fee_bps > 0 else self._fee_fetcher.get_default_rate()

            # takingAmount = USDC received, makingAmount = shares sold
            taking = response.get("taking_amount", 0)
            making = response.get("making_amount", 0)

            if making > 0 and taking > 0:
                fill_price = taking / making  # USDC per share
            else:
                fill_price = position.fill_price  # fallback

            log_event(
                logger, logging.INFO,
                f"LIVE SELL FILLED: {position.asset} {position.side} "
                f"shares={sell_amount:.4f} fill={fill_price:.4f} fee={fee_rate}",
                entity_type="exit_executor",
                entity_id=position.position_id,
            )
            return True, fill_price, fee_rate

        # Not matched veya error
        error = response.get("error", status)
        log_event(
            logger, logging.WARNING,
            f"LIVE SELL FAILED: {position.asset} {error}",
            entity_type="exit_executor",
            entity_id=position.position_id,
        )
        return False, 0.0, 0.0

    async def execute_close_with_retry(
        self,
        position: PositionRecord,
        current_price: float,
        max_retries: int | None = None,
    ) -> bool:
        """Retry ile pozisyon kapat.

        Retry interval close_reason'a gore belirlenir.
        Latch korunur — close_reason/trigger_set silinmez.
        """
        retries = max_retries if max_retries is not None else self._max_close_retries
        reason = position.close_reason or CloseReason.MANUAL_CLOSE
        interval_ms = self._retry_intervals.get(reason, DEFAULT_RETRY_INTERVAL_MS)
        interval_sec = interval_ms / 1000.0

        for attempt in range(retries):
            success = await self.execute_close(position, current_price)
            if success:
                return True

            if position.is_open:
                return False

            if attempt < retries - 1:
                await asyncio.sleep(interval_sec)

        log_event(
            logger, logging.ERROR,
            f"Close retries exhausted: {position.asset} after {retries} attempts",
            entity_type="exit_executor",
            entity_id=position.position_id,
        )
        return False

    def get_retry_interval_ms(self, reason: CloseReason) -> int:
        """Close reason'a gore retry interval (ms)."""
        return self._retry_intervals.get(reason, DEFAULT_RETRY_INTERVAL_MS)

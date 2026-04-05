"""ExitEvaluator — acik pozisyonlari izler, TP/SL tetik uretir.

TP (Take Profit):
- net_unrealized_pnl_pct >= tp_pct → closing_requested
- reevaluate_on_retry = True (default): sell dolmazsa kosul tekrar kontrol edilir
  → artik saglanmiyorsa closing_requested iptal → open_confirmed'a geri donus
- Bu SADECE TP icin — SL/force sell'de geri donus YOK

SL (Stop Loss):
- net_unrealized_pnl_pct <= -sl_pct → closing_requested
- LATCH zorunlu — reevaluate = False
- Geri donus YOK
- jump_threshold: tek tick'te fiyat %X+ duserse = orderbook anomali → SL tetiklenmez

Exit latch kurali:
- SL: LATCH zorunlu — tetiklendikten sonra iptal yok
- Force sell: LATCH zorunlu (v0.6.1'de implement)
- TP: reevaluate=True ise latch degil, kosul kontrol edilir

State machine uyumu:
- closing_requested → open_confirmed: SADECE TP + reevaluate=True
- SL/force sell icin bu geri donus YASAK
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.execution.position_record import PositionRecord, PositionState
from backend.execution.close_reason import CloseReason
from backend.logging_config.service import get_logger, log_event

logger = get_logger("execution.exit_evaluator")


@dataclass
class ExitSignal:
    """Exit tetik sinyali."""
    should_exit: bool
    reason: CloseReason | None = None
    pnl_pct: float = 0.0
    detail: dict | None = None


class ExitEvaluator:
    """Acik pozisyonlari izler, TP/SL tetik uretir.

    Her evaluation döngüsünde açık pozisyonlar kontrol edilir.
    Tetik → closing_requested state'ine geçiş.
    TP reevaluate: retry'da koşul kontrol edilir, sağlanmıyorsa geri dönülür.
    SL latch: tetiklendikten sonra geri dönüş YOK.
    """

    def __init__(
        self,
        tp_pct: float = 5.0,
        sl_pct: float = 3.0,
        sl_jump_threshold: float = 0.15,
        tp_reevaluate: bool = True,
        sl_reevaluate: bool = False,
    ):
        self._tp_pct = tp_pct
        self._sl_pct = sl_pct
        self._sl_jump_threshold = sl_jump_threshold
        self._tp_reevaluate = tp_reevaluate
        self._sl_reevaluate = sl_reevaluate  # ZORUNLU False
        self._last_prices: dict[str, float] = {}  # position_id → son fiyat

    def evaluate(
        self,
        position: PositionRecord,
        current_price: float,
    ) -> ExitSignal:
        """Tek pozisyon icin TP/SL kontrol.

        Args:
            position: Acik pozisyon
            current_price: Canli held-side outcome fiyati

        Returns:
            ExitSignal — should_exit=True ise closing_requested yapilmali
        """
        if not position.is_open:
            return ExitSignal(should_exit=False)

        if position.fill_price <= 0 or position.net_position_shares <= 0:
            return ExitSignal(should_exit=False)

        # Net PnL hesapla (fee-aware)
        pnl_data = position.calculate_unrealized_pnl(current_price)
        pnl_pct = pnl_data["net_unrealized_pnl_pct"]

        # Jump threshold kontrolu (SL icin)
        prev_price = self._last_prices.get(position.position_id, current_price)
        self._last_prices[position.position_id] = current_price

        # ── TP kontrolu ──
        if pnl_pct >= self._tp_pct:
            log_event(
                logger, logging.INFO,
                f"TP triggered: {position.asset} PnL={pnl_pct:.2f}% >= {self._tp_pct}%",
                entity_type="exit",
                entity_id=position.position_id,
            )
            return ExitSignal(
                should_exit=True,
                reason=CloseReason.TAKE_PROFIT,
                pnl_pct=pnl_pct,
                detail={
                    "tp_pct": self._tp_pct,
                    "current_pnl_pct": pnl_pct,
                    "current_price": current_price,
                    "reevaluate": self._tp_reevaluate,
                },
            )

        # ── SL kontrolu ──
        if pnl_pct <= -self._sl_pct:
            # Jump threshold — tek tick'te asiri dusus
            if prev_price > 0:
                drop_pct = (prev_price - current_price) / prev_price
                if drop_pct > self._sl_jump_threshold:
                    log_event(
                        logger, logging.WARNING,
                        f"SL jump threshold: {position.asset} drop={drop_pct:.2%} > {self._sl_jump_threshold:.2%} — SL ATLANIR",
                        entity_type="exit",
                        entity_id=position.position_id,
                    )
                    return ExitSignal(
                        should_exit=False,
                        detail={
                            "reason": "jump_threshold",
                            "drop_pct": drop_pct,
                            "threshold": self._sl_jump_threshold,
                        },
                    )

            log_event(
                logger, logging.WARNING,
                f"SL triggered: {position.asset} PnL={pnl_pct:.2f}% <= -{self._sl_pct}% — LATCH",
                entity_type="exit",
                entity_id=position.position_id,
            )
            return ExitSignal(
                should_exit=True,
                reason=CloseReason.STOP_LOSS,
                pnl_pct=pnl_pct,
                detail={
                    "sl_pct": self._sl_pct,
                    "current_pnl_pct": pnl_pct,
                    "current_price": current_price,
                    "latch": True,  # SL latch zorunlu
                    "reevaluate": False,  # SL geri donus YOK
                },
            )

        return ExitSignal(should_exit=False, pnl_pct=pnl_pct)

    def should_cancel_close(
        self,
        position: PositionRecord,
        current_price: float,
    ) -> bool:
        """TP reevaluate: closing_requested'da kosul hala saglanıyor mu?

        SADECE TP + reevaluate=True icin gecerli.
        SL/force sell icin her zaman False doner (iptal yok, latch).

        Returns:
            True ise closing_requested iptal → open_confirmed'a don.
        """
        if position.close_reason != CloseReason.TAKE_PROFIT:
            return False  # SL/force sell → latch, iptal yok

        if not self._tp_reevaluate:
            return False  # TP reevaluate kapali → latch

        # TP kosulu hala saglanıyor mu?
        pnl_data = position.calculate_unrealized_pnl(current_price)
        pnl_pct = pnl_data["net_unrealized_pnl_pct"]

        if pnl_pct < self._tp_pct:
            # TP artik saglanmiyor → iptal
            log_event(
                logger, logging.INFO,
                f"TP reevaluate: {position.asset} PnL={pnl_pct:.2f}% < {self._tp_pct}% — closing iptal",
                entity_type="exit",
                entity_id=position.position_id,
            )
            return True

        return False  # hala saglanıyor, devam

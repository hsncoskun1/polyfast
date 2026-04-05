"""ExitEvaluator — acik pozisyonlari izler, TP/SL/force sell tetik uretir.

TP (Take Profit):
- net_unrealized_pnl_pct >= tp_pct → closing_requested
- reevaluate = True (default): sell dolmazsa kosul tekrar kontrol edilir
  → artik saglanmiyorsa closing_requested iptal → open_confirmed'a geri donus

SL (Stop Loss):
- net_unrealized_pnl_pct <= -sl_pct → closing_requested
- LATCH zorunlu — reevaluate = False, geri donus YOK
- jump_threshold: tek tick fiyat %X+ duserse → SL tetiklenmez

Force Sell:
- Checkbox bazli: time + pnl (delta KALDIRILDI)
- Secilenlerin HEPSI saglaninca tetiklenir
- Tek kosul seciliyse o yeterli
- LATCH zorunlu — reevaluate = False, geri donus YOK
- close_trigger_set tetik aninda authoritative yazilir, sonradan degismez

Stale safety:
- Sadece time seciliyse → stale durumda force sell CALISIR
- time + pnl birlikte seciliyse ve pnl waiting → force sell TETIKLENMEZ
- Zaman bazli cikis stale durumda BLOKE OLMAZ (tek seçiliyse)

State machine uyumu:
- closing_requested → open_confirmed: SADECE TP + reevaluate=True
- SL/force sell icin bu geri donus YASAK
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.execution.position_record import PositionRecord, PositionState
from backend.execution.close_reason import CloseReason, ForceSellTrigger
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
        # Force sell
        force_sell_time_enabled: bool = True,
        force_sell_time_seconds: int = 30,
        force_sell_pnl_enabled: bool = False,
        force_sell_pnl_pct: float = 5.0,
    ):
        self._tp_pct = tp_pct
        self._sl_pct = sl_pct
        self._sl_jump_threshold = sl_jump_threshold
        self._tp_reevaluate = tp_reevaluate
        self._sl_reevaluate = sl_reevaluate  # ZORUNLU False
        # Force sell
        self._fs_time_enabled = force_sell_time_enabled
        self._fs_time_seconds = force_sell_time_seconds
        self._fs_pnl_enabled = force_sell_pnl_enabled
        self._fs_pnl_pct = force_sell_pnl_pct
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

    def evaluate_force_sell(
        self,
        position: PositionRecord,
        current_price: float,
        seconds_remaining: float,
        outcome_fresh: bool = True,
    ) -> ExitSignal:
        """Force sell evaluation — checkbox bazli kosullar.

        Secilenlerin HEPSI saglaninca tetiklenir.
        Tek kosul seciliyse o yeterli.

        Stale safety:
        - Sadece time seciliyse → stale durumda da calisir
        - time + pnl seciliyse ve outcome stale → tetiklenmez (pnl hesaplanamaz)

        trigger_set tetik aninda authoritative yazilir, sonradan degismez.

        Args:
            position: Acik pozisyon
            current_price: Canli held-side outcome fiyati
            seconds_remaining: Event bitimine kalan saniye
            outcome_fresh: Outcome verisi fresh mi

        Returns:
            ExitSignal
        """
        if not position.is_open:
            return ExitSignal(should_exit=False)

        # Hic kosul secili degil
        if not self._fs_time_enabled and not self._fs_pnl_enabled:
            return ExitSignal(should_exit=False)

        trigger_set: list[str] = []
        conditions_required = 0
        conditions_met = 0

        # ── Time kosulu ──
        if self._fs_time_enabled:
            conditions_required += 1
            if seconds_remaining <= self._fs_time_seconds:
                trigger_set.append(ForceSellTrigger.TIME.value)
                conditions_met += 1

        # ── PnL kosulu ──
        pnl_waiting = False
        if self._fs_pnl_enabled:
            conditions_required += 1
            if not outcome_fresh:
                # PnL hesaplanamaz — stale/waiting
                pnl_waiting = True
            elif position.fill_price > 0 and position.net_position_shares > 0:
                pnl_data = position.calculate_unrealized_pnl(current_price)
                pnl_pct = pnl_data["net_unrealized_pnl_pct"]
                if pnl_pct <= -self._fs_pnl_pct:
                    trigger_set.append(ForceSellTrigger.PNL.value)
                    conditions_met += 1

        # Secilenlerin HEPSI saglanmali
        # AMA: pnl waiting ise ve time saglandiysa → time safety override
        time_met = ForceSellTrigger.TIME.value in trigger_set
        time_safety_override = pnl_waiting and time_met and self._fs_time_enabled

        if time_safety_override:
            # PnL hesaplanamıyor ama time sağlandı → safety override ile çık
            log_event(
                logger, logging.WARNING,
                f"FORCE SELL time safety override: {position.asset} — PnL stale, time sağlandı",
                entity_type="exit",
                entity_id=position.position_id,
            )
            trigger_set_final = [ForceSellTrigger.TIME.value]  # sadece time tetikledi
            return ExitSignal(
                should_exit=True,
                reason=CloseReason.FORCE_SELL,
                detail={
                    "trigger_set": trigger_set_final,
                    "latch": True,
                    "reevaluate": False,
                    "seconds_remaining": seconds_remaining,
                    "safety_override": True,
                    "pnl_stale": True,
                },
            )

        if conditions_met >= conditions_required and conditions_required > 0:
            log_event(
                logger, logging.WARNING,
                f"FORCE SELL triggered: {position.asset} triggers={trigger_set} — LATCH",
                entity_type="exit",
                entity_id=position.position_id,
            )
            return ExitSignal(
                should_exit=True,
                reason=CloseReason.FORCE_SELL,
                detail={
                    "trigger_set": trigger_set,
                    "latch": True,
                    "reevaluate": False,
                    "seconds_remaining": seconds_remaining,
                },
            )

        return ExitSignal(should_exit=False)

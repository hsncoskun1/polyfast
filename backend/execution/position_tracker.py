"""PositionTracker — pozisyon lifecycle yonetimi + sayaclar.

Sorumluluklar:
- Fill geldiginde PositionRecord olustur (fee-aware)
- Close geldiginde exit alanlari doldur
- State gecislerini yonet
- Event Max / Bot Max / Session Trade Limit sayaclarini authoritative tut

Sayac kurallari:
- event_fill_count: SADECE basarili alis fill
- open_position_count: anlik acik pozisyon sayisi
- session_trade_count: SADECE basarili alis fill (session boyunca birikir, azalmaz)

ARTIRMAYAN olaylar: FOK rejected, satis fill, claim, dolmayan order
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from backend.execution.position_record import (
    PositionRecord, PositionState, InvalidPositionTransition,
)
from backend.execution.close_reason import CloseReason
from backend.execution.fee_calculator import FeeCalculator
from backend.logging_config.service import get_logger, log_event

logger = get_logger("execution.tracker")


class PositionTracker:
    """Pozisyon lifecycle yoneticisi + authoritative sayaclar.

    Persist hook: position_store set edilmisse state transition'da otomatik save.
    Write failure authority'yi kaydirmaz — health/log uretir, memory authoritative kalir.
    """

    def __init__(self, fee_calculator: FeeCalculator | None = None, position_store=None):
        self._positions: dict[str, PositionRecord] = {}  # position_id -> record
        self._fee_calc = fee_calculator or FeeCalculator()
        self._store = position_store  # PositionStore (optional)

        # Authoritative sayaclar
        self._event_fills: dict[str, int] = {}  # condition_id -> fill count
        self._session_trade_count: int = 0

    def _persist(self, record: PositionRecord) -> None:
        """State degisiminde SQLite'a kaydet. Fire-and-forget.

        Write failure authority'yi kaydirmaz — memory authoritative kalir.
        """
        if self._store is None:
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._store.save(record))
        except RuntimeError:
            pass  # event loop yoksa (test/sync context) sessizce gec

    def restore_position(self, record: PositionRecord) -> None:
        """Startup restore: SQLite'tan okunan pozisyonu memory'ye yukle.

        Sayaclari da gunceller:
        - Acik pozisyon sayaci
        - Event fill sayaci (OPEN/CLOSING durumundakiler icin)
        - Session trade count (tum fill'ler icin)
        """
        self._positions[record.position_id] = record

        # Sayaclari restore et
        if record.state in (
            PositionState.OPEN_CONFIRMED,
            PositionState.CLOSING_REQUESTED,
            PositionState.CLOSE_PENDING,
            PositionState.CLOSE_FAILED,
        ):
            # Acik pozisyon — fill sayaci var demek
            cid = record.condition_id
            self._event_fills[cid] = self._event_fills.get(cid, 0) + 1
            self._session_trade_count += 1
        elif record.state == PositionState.CLOSED:
            # Kapanmis — fill sayacina dahil ama acik degil
            cid = record.condition_id
            self._event_fills[cid] = self._event_fills.get(cid, 0) + 1
            self._session_trade_count += 1

    # ─── Fill (Entry) ───

    def create_pending(
        self,
        asset: str,
        side: str,
        condition_id: str,
        token_id: str,
        requested_amount_usd: float,
    ) -> PositionRecord:
        """Order gonderildiginde pending pozisyon olustur.

        Henuz fill olmadi — PENDING_OPEN state.
        """
        position_id = str(uuid.uuid4())
        record = PositionRecord(
            position_id=position_id,
            asset=asset,
            side=side,
            condition_id=condition_id,
            token_id=token_id,
            requested_amount_usd=requested_amount_usd,
        )
        self._positions[position_id] = record

        log_event(
            logger, logging.INFO,
            f"Position pending: {asset} {side} ${requested_amount_usd}",
            entity_type="position",
            entity_id=position_id,
        )
        self._persist(record)

        return record

    def confirm_fill(
        self,
        position_id: str,
        fill_price: float,
        fee_rate: float | None = None,
    ) -> PositionRecord:
        """Fill geldiginde pozisyonu onayla — fee-aware entry alanlarini doldur.

        Bu an sayaclar ARTAR:
        - event_fill_count +1
        - session_trade_count +1
        - open_position_count +1 (dolayli — is_open olan pozisyon sayisi)
        """
        record = self._get_record(position_id)
        calc = self._fee_calc
        if fee_rate is not None:
            calc = FeeCalculator(fee_rate)

        # Fee-aware entry hesapla
        entry = calc.calculate_entry(record.requested_amount_usd, fill_price)

        # Authoritative alanlar — bir kez yazilir, degismez
        record.fill_price = fill_price
        record.gross_fill_shares = entry["gross_fill_shares"]
        record.entry_fee_shares = entry["entry_fee_shares"]
        record.net_position_shares = entry["net_position_shares"]
        record.fee_rate = entry["fee_rate"]
        record.opened_at = datetime.now(timezone.utc)

        # State gecisi
        record.transition_to(PositionState.OPEN_CONFIRMED)

        # Sayaclar — SADECE basarili alis fill
        cond_id = record.condition_id
        self._event_fills[cond_id] = self._event_fills.get(cond_id, 0) + 1
        self._session_trade_count += 1

        log_event(
            logger, logging.INFO,
            f"Position filled: {record.asset} {record.side} "
            f"fill={fill_price:.4f} net_shares={record.net_position_shares:.4f} "
            f"fee_shares={record.entry_fee_shares:.4f}",
            entity_type="position",
            entity_id=position_id,
        )
        self._persist(record)

        return record

    def reject_fill(self, position_id: str) -> PositionRecord:
        """FOK rejected — fill olmadi, pozisyon kapanir.

        Sayaclar ARTMAZ — fill olmadi.
        Not: ileride cancelled/not_opened ayri state olabilir.
        """
        record = self._get_record(position_id)
        record.transition_to(PositionState.CLOSED)
        record.closed_at = datetime.now(timezone.utc)

        log_event(
            logger, logging.INFO,
            f"Position rejected (FOK no fill): {record.asset}",
            entity_type="position",
            entity_id=position_id,
        )

        return record

    # ─── Close (Exit) ───

    def request_close(
        self,
        position_id: str,
        reason: CloseReason,
        trigger_set: list[str] | None = None,
        requested_price: float = 0.0,
    ) -> PositionRecord:
        """Cikis karari — closing_requested state'e gec."""
        record = self._get_record(position_id)
        record.transition_to(PositionState.CLOSING_REQUESTED)
        record.close_reason = reason
        record.close_trigger_set = trigger_set or []
        record.close_triggered_at = datetime.now(timezone.utc)
        record.close_requested_price = requested_price

        log_event(
            logger, logging.INFO,
            f"Close requested: {record.asset} reason={reason.value} triggers={trigger_set}",
            entity_type="position",
            entity_id=position_id,
        )
        self._persist(record)

        return record

    def confirm_close(
        self,
        position_id: str,
        exit_fill_price: float,
        fee_rate: float | None = None,
    ) -> PositionRecord:
        """Cikis fill geldi — authoritative exit alanlarini doldur.

        open_position_count azalir (dolayli).
        """
        record = self._get_record(position_id)

        # State gecisi: close_pending ise, veya closing_requested'dan direkt
        if record.state == PositionState.CLOSING_REQUESTED:
            record.transition_to(PositionState.CLOSE_PENDING)
        record.transition_to(PositionState.CLOSED)

        # Fee-aware exit hesapla
        calc = self._fee_calc
        if fee_rate is not None:
            calc = FeeCalculator(fee_rate)

        exit_data = calc.calculate_exit(record.net_position_shares, exit_fill_price)

        # Authoritative close alanlar — bir kez yazilir
        record.exit_fill_price = exit_fill_price
        record.exit_gross_usdc = exit_data["exit_gross_usdc"]
        record.actual_exit_fee_usdc = exit_data["actual_exit_fee_usdc"]
        record.net_exit_usdc = exit_data["net_exit_usdc"]
        record.net_realized_pnl = round(
            exit_data["net_exit_usdc"] - record.requested_amount_usd, 4
        )
        record.closed_at = datetime.now(timezone.utc)

        log_event(
            logger, logging.INFO,
            f"Position closed: {record.asset} {record.side} "
            f"exit={exit_fill_price:.4f} net_pnl=${record.net_realized_pnl:.4f} "
            f"reason={record.close_reason.value if record.close_reason else 'none'}",
            entity_type="position",
            entity_id=position_id,
        )
        self._persist(record)

        return record

    # ─── Sayaclar (authoritative) ───

    def get_event_fill_count(self, condition_id: str) -> int:
        """Bu event'teki basarili alis fill sayisi."""
        return self._event_fills.get(condition_id, 0)

    @property
    def open_position_count(self) -> int:
        """Anlik acik pozisyon sayisi."""
        return sum(1 for p in self._positions.values() if p.is_open)

    @property
    def session_trade_count(self) -> int:
        """Session boyunca toplam basarili alis fill sayisi."""
        return self._session_trade_count

    # ─── Query ───

    def get_position(self, position_id: str) -> PositionRecord | None:
        return self._positions.get(position_id)

    def get_open_positions(self) -> list[PositionRecord]:
        return [p for p in self._positions.values() if p.is_open]

    def get_all_positions(self) -> list[PositionRecord]:
        return list(self._positions.values())

    def get_positions_by_condition(self, condition_id: str) -> list[PositionRecord]:
        return [p for p in self._positions.values() if p.condition_id == condition_id]

    # ─── Internal ───

    def _get_record(self, position_id: str) -> PositionRecord:
        record = self._positions.get(position_id)
        if record is None:
            raise KeyError(f"Position not found: {position_id}")
        return record

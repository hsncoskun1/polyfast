"""PositionRecord — fee-aware pozisyon kaydi + state machine.

State machine:
  pending_open → open_confirmed (fill geldi)
  pending_open → closed (FOK rejected, fill yok)
  open_confirmed → closing_requested (cikis karari)
  closing_requested → close_pending (cikis order gonderildi)
  close_pending → closed (cikis fill geldi)
  close_pending → close_failed (cikis order basarisiz)
  close_failed → closing_requested (retry)
  close_failed → closed (give up / expiry)

Not: pending_open → closed (FOK rejected) ileride cancelled/not_opened
olarak ayrilabilir. Simdilik closed olarak ele alinir.

Authoritative vs hesaplanan alan ayrimi:
A) Fill aninda BIR KEZ yazilir (degismez)
B) Acik pozisyon boyunca CANLI hesaplanir (her tick)
C) Close aninda SABITLENIR (degismez)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from backend.execution.close_reason import CloseReason, ForceSellTrigger


class PositionState(str, Enum):
    """Pozisyon lifecycle state'i."""
    PENDING_OPEN = "pending_open"
    OPEN_CONFIRMED = "open_confirmed"
    CLOSING_REQUESTED = "closing_requested"
    CLOSE_PENDING = "close_pending"
    CLOSED = "closed"
    CLOSE_FAILED = "close_failed"


ALLOWED_TRANSITIONS: dict[PositionState, set[PositionState]] = {
    PositionState.PENDING_OPEN: {PositionState.OPEN_CONFIRMED, PositionState.CLOSED},
    PositionState.OPEN_CONFIRMED: {PositionState.CLOSING_REQUESTED},
    PositionState.CLOSING_REQUESTED: {PositionState.CLOSE_PENDING, PositionState.OPEN_CONFIRMED},
    # closing_requested → open_confirmed: SADECE TP reevaluate=True durumunda izinli
    # SL ve force sell icin bu geri donus YASAK — caller tarafinda kontrol edilir
    PositionState.CLOSE_PENDING: {PositionState.CLOSED, PositionState.CLOSE_FAILED},
    PositionState.CLOSE_FAILED: {PositionState.CLOSING_REQUESTED, PositionState.CLOSED},
    PositionState.CLOSED: set(),  # terminal
}


class InvalidPositionTransition(Exception):
    pass


@dataclass
class PositionRecord:
    """Fee-aware pozisyon kaydi.

    Authoritative alanlar fill/close aninda yazilir ve DEGISMEZ.
    Hesaplanan alanlar canli fiyattan turetilir.
    """

    # ── Kimlik ──
    position_id: str
    asset: str
    side: str  # "UP" veya "DOWN"
    condition_id: str
    token_id: str

    # ── State ──
    state: PositionState = PositionState.PENDING_OPEN
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ── Entry authoritative (fill aninda yazilir, degismez) ──
    requested_amount_usd: float = 0.0
    fill_price: float = 0.0
    gross_fill_shares: float = 0.0
    entry_fee_shares: float = 0.0
    net_position_shares: float = 0.0
    fee_rate: float = 0.0
    opened_at: datetime | None = None

    # ── Close authoritative (close aninda sabitlenir) ──
    exit_fill_price: float = 0.0
    exit_gross_usdc: float = 0.0
    actual_exit_fee_usdc: float = 0.0
    net_exit_usdc: float = 0.0
    net_realized_pnl: float = 0.0

    close_reason: CloseReason | None = None
    close_trigger_set: list[str] = field(default_factory=list)
    close_triggered_at: datetime | None = None
    close_requested_price: float = 0.0
    closed_at: datetime | None = None

    # ── State machine ──

    def transition_to(self, target: PositionState) -> None:
        """State gecisi. Gecersiz gecis icin hata."""
        if target not in ALLOWED_TRANSITIONS.get(self.state, set()):
            raise InvalidPositionTransition(
                f"Cannot transition from {self.state.value} to {target.value}"
            )
        self.state = target

    @property
    def is_open(self) -> bool:
        return self.state == PositionState.OPEN_CONFIRMED

    @property
    def is_closed(self) -> bool:
        return self.state == PositionState.CLOSED

    @property
    def is_pending(self) -> bool:
        return self.state == PositionState.PENDING_OPEN

    # ── Fee-aware hesaplanan alanlar (canli) ──

    def calculate_unrealized_pnl(self, current_price: float, fee_rate: float | None = None) -> dict:
        """Acik pozisyon icin canli net PnL tahmini.

        Args:
            current_price: Canli held-side outcome fiyati
            fee_rate: Guncel fee rate (None ise entry anindaki kullanilir)

        Returns:
            Dict with gross_position_value, estimated_exit_fee_usdc,
            net_exit_value_estimate, net_unrealized_pnl_estimate
        """
        rate = fee_rate or self.fee_rate
        gross_value = self.net_position_shares * current_price
        est_fee = self.net_position_shares * rate * current_price * (1.0 - current_price)
        net_value = gross_value - est_fee
        net_pnl = net_value - self.requested_amount_usd

        return {
            "current_price": round(current_price, 4),
            "gross_position_value": round(gross_value, 4),
            "estimated_exit_fee_usdc": round(est_fee, 4),
            "net_exit_value_estimate": round(net_value, 4),
            "net_unrealized_pnl_estimate": round(net_pnl, 4),
            "net_unrealized_pnl_pct": round(net_pnl / self.requested_amount_usd * 100, 2) if self.requested_amount_usd > 0 else 0.0,
        }

"""Close reason + trigger set modeli.

State ve close_reason AYRI kavramlar:
- state = pozisyonun lifecycle durumu (open, closed, vb.)
- close_reason = NEDEN kapandı (TP, SL, force sell, vb.)
- close_trigger_set = force sell alt tetikleri

Force sell çoklu tetik:
- force_sell_time + force_sell_pnl aynı anda tetiklenebilir
- close_reason = force_sell
- close_trigger_set = ["force_sell_time", "force_sell_pnl"]
"""

from enum import Enum


class CloseReason(str, Enum):
    """Pozisyonun kapanma sebebi."""
    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"
    FORCE_SELL = "force_sell"
    MANUAL_CLOSE = "manual_close"
    EXPIRY = "expiry"
    CLAIM = "claim"
    SYSTEM_SHUTDOWN = "system_shutdown"
    ERROR_RECOVERY = "error_recovery"


class ForceSellTrigger(str, Enum):
    """Force sell alt tetikleri."""
    TIME = "force_sell_time"
    PNL = "force_sell_pnl"

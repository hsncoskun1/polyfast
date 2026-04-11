"""OrderIntent — order gonderme niyetini temsil eder.

ENTRY sinyali geldiginde OrderIntent olusturulur.
Validation'dan gecerse order gonderilebilir.
Gecmezse reject edilir — order GONDERILMEZ.

OrderIntent execution/fill referansi DEGILDIR:
- dominant_price = evaluation anindaki fiyat (referans, PnL icin KULLANILMAZ)
- fill_price = gercek fill fiyati (PnL icin KULLANILIR) — bu OrderIntent'te YOK, fill sonrasi gelir

token_id side ile net bagli:
- UP tarafinda islem acilacaksa → UP token_id
- DOWN tarafinda islem acilacaksa → DOWN token_id
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class OrderSide(str, Enum):
    """Order tarafi — hangi outcome token'i alinacak."""
    UP = "UP"
    DOWN = "DOWN"


@dataclass(frozen=True)
class OrderIntent:
    """Order gonderme niyeti — evaluation sonucu uretilir.

    Attributes:
        asset: Coin sembolu (BTC, ETH, ...)
        side: UP veya DOWN — hangi outcome token
        amount_usd: Islem tutari (USD, coin bazli order_amount'tan)
        condition_id: Event condition ID
        token_id: Alinacak token ID (side ile bagli: UP token veya DOWN token)
        dominant_price: Evaluation anindaki fiyat (0-1). REFERANS, fill price DEGIL.
        evaluated_at: Intent'in olusturulma zamani
    """
    asset: str
    side: OrderSide
    amount_usd: float
    condition_id: str
    token_id: str
    dominant_price: float  # evaluation ani referansi, PnL/execution icin KULLANILMAZ
    event_max: int = 1    # coin settings'ten — bu event'te max fill sayisi
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

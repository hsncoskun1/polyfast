"""Coin bazlı ayar modeli.

Her coin'in kendi rule config'i olur.
Ayar yapılmadan o coin'de işlem açılamaz.
Default config YOK — kullanıcı bilinçli olarak değerleri girer.

Coin bazlı alanlar:
- coin_enabled: coin trade pipeline'a dahil mi
- side_mode: dominant_only / up_only / down_only (both YOK)
- delta_threshold: sabit USD fark
- price_min / price_max: 0-100 ölçeği (side_mode'a göre range değişir)
- spread_max: ondalıklı yüzde
- time_min / time_max: kalan saniye
- event_max: tek event'teki max alış fill
- order_amount: bu coin için işlem tutarı (USD)
- reactivate_on_return: coin listeden çıkıp geri gelince otomatik devam

Side mode ve fiyat kuralı aralıkları:
- dominant_only → fiyat kuralı 51-99 (dominant = max(up,down) >= 0.51)
- up_only → fiyat kuralı 1-99 (sadece UP tarafı kontrol edilir)
- down_only → fiyat kuralı 1-99 (sadece DOWN tarafı kontrol edilir)
"""

from dataclasses import dataclass
from enum import Enum


class SideMode(str, Enum):
    """Coin'in hangi tarafta trade edeceği."""
    DOMINANT_ONLY = "dominant_only"  # max(up, down) — default
    UP_ONLY = "up_only"              # sadece UP tarafı
    DOWN_ONLY = "down_only"          # sadece DOWN tarafı
    # both YOK — bağlayıcı karar


@dataclass
class CoinSettings:
    """Tek bir coin'in trade ayarları.

    Ayar yapılmadan coin'de işlem açılamaz.
    Her alan açıkça set edilmeli — default config YOK.
    """
    coin: str                         # BTC, ETH, SOL, DOGE, XRP, BNB

    # ── Trade eligibility ──
    coin_enabled: bool = False        # disabled = WS subscription yok, evaluation yok

    # ── Side mode ──
    side_mode: SideMode = SideMode.DOMINANT_ONLY

    # ── Entry kuralları ──
    delta_threshold: float = 0.0      # sabit USD fark (0 = ayarlanmamış)
    price_min: int = 0                # 0-100 ölçeği (0 = ayarlanmamış)
    price_max: int = 0                # 0-100 ölçeği (0 = ayarlanmamış)
    spread_max: float = 0.0           # ondalıklı yüzde (0 = ayarlanmamış)
    time_min: int = 0                 # kalan saniye (0 = ayarlanmamış)
    time_max: int = 0                 # kalan saniye (0 = ayarlanmamış)
    event_max: int = 1                # tek event'teki max alış fill

    # ── Trade amount ──
    order_amount: float = 0.0         # USD (0 = ayarlanmamış)

    # ── Davranış ──
    reactivate_on_return: bool = True  # coin listeden çıkıp geri gelince devam et

    @property
    def is_configured(self) -> bool:
        """Tüm zorunlu alanlar doldurulmuş mu?

        Ayar yapılmadan trade açılamaz.
        """
        return (
            self.coin_enabled
            and self.delta_threshold > 0
            and self.price_min > 0
            and self.price_max > 0
            and self.price_min < self.price_max
            and self.spread_max > 0
            and self.time_min > 0
            and self.time_max > 0
            and self.time_min < self.time_max
            and self.order_amount > 0
        )

    @property
    def price_min_valid_range(self) -> tuple[int, int]:
        """Side mode'a göre geçerli fiyat aralığı."""
        if self.side_mode == SideMode.DOMINANT_ONLY:
            return (51, 99)
        return (1, 99)  # up_only veya down_only

    @property
    def is_trade_eligible(self) -> bool:
        """Trade pipeline'a alınabilir mi?

        coin_enabled + is_configured = eligible.
        """
        return self.coin_enabled and self.is_configured

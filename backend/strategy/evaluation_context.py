"""EvaluationContext — runtime state'ten okunan tek tutarlı veri seti.

Rule'lar doğrudan farklı kaynaklara erişmez.
Tüm veri bu context üzerinden gelir.
Context, orchestrator tarafından runtime state'ten doldurulur.
Snapshot'tan DEĞİL, canlı pipeline/PTB/coin USD'den beslenir.

İçerik:
- Outcome fiyatları (UP/DOWN, best_bid/best_ask)
- Coin canlı USD fiyatı
- PTB (referans USD coin fiyatı)
- Event timing (kalan saniye)
- Position sayaçları (injected, v0.5.x'te gerçek)
- Config değerleri (kural threshold'ları)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class EvaluationContext:
    """Tek evaluation döngüsü için gereken tüm veri.

    Tüm rule'lar bu context'ten okur.
    Doğrudan pipeline/WS/API'ye erişim YOK.
    """

    # ── Event kimliği ──
    condition_id: str = ""
    asset: str = ""
    event_slug: str = ""

    # ── Outcome fiyatları (CLOB WS'ten) ──
    up_price: float = 0.0          # UP outcome fiyatı (0.0-1.0)
    down_price: float = 0.0        # DOWN outcome fiyatı (0.0-1.0)
    best_bid: float = 0.0          # outcome best bid
    best_ask: float = 0.0          # outcome best ask
    outcome_fresh: bool = False    # outcome verisi fresh mi

    # ── Coin canlı USD fiyatı (RTDS crypto_prices'tan) ──
    coin_usd_price: float = 0.0   # BTC=$67260, DOGE=$0.092
    coin_usd_fresh: bool = False   # coin USD verisi fresh mi

    # ── PTB (SSR'den, lock'lanmış) ──
    ptb_value: float = 0.0        # USD referans coin fiyatı
    ptb_acquired: bool = False     # PTB alındı mı (lock'landı mı)

    # ── Event timing ──
    seconds_remaining: float = 0.0  # event bitimine kalan saniye
    event_end_ts: float = 0.0       # event bitiş unix timestamp

    # ── Position sayaçları (dışarıdan inject, v0.5.x'te gerçek) ──
    event_fill_count: int = 0      # bu event'teki alış fill sayısı
    open_position_count: int = 0   # tüm event'lerdeki açık pozisyon sayısı

    # ── Kural config'leri ──
    time_min_seconds: int = 30
    time_max_seconds: int = 270
    price_min: int = 51            # 0-100 ölçeği
    price_max: int = 85            # 0-100 ölçeği
    delta_threshold: float = 50.0  # sabit USD fark
    spread_max_pct: float = 3.0    # ondalıklı yüzde
    event_max_positions: int = 1
    bot_max_positions: int = 3

    # ── Kural enabled/disabled ──
    time_enabled: bool = True
    price_enabled: bool = True
    delta_enabled: bool = True
    spread_enabled: bool = True
    event_max_enabled: bool = True
    bot_max_enabled: bool = True

    # ── Timestamp ──
    evaluated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ── Türetilmiş ──

    @property
    def dominant_price(self) -> float:
        """Dominant taraf fiyatı (0.0-1.0). Her zaman >= 0.50."""
        return max(self.up_price, self.down_price)

    @property
    def dominant_side(self) -> str:
        """UP veya DOWN."""
        return "UP" if self.up_price >= self.down_price else "DOWN"

    @property
    def dominant_price_100(self) -> float:
        """Dominant fiyat 0-100 ölçeğinde."""
        return self.dominant_price * 100

    @property
    def spread_pct(self) -> float:
        """Spread yüzdesi: (ask-bid)/ask*100. best_ask bazlı."""
        if self.best_ask > 0:
            return (self.best_ask - self.best_bid) / self.best_ask * 100
        return 0.0

    @property
    def delta(self) -> float:
        """Delta: abs(coin_usd - PTB). Sabit USD fark."""
        if self.coin_usd_price > 0 and self.ptb_value > 0:
            return abs(self.coin_usd_price - self.ptb_value)
        return 0.0

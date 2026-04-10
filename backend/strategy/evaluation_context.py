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

from backend.settings.coin_settings import SideMode


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

    # ── Outcome fiyatları (CLOB WS'ten, per-side) ──
    up_price: float = 0.0          # UP token bid (exit/realizable)
    down_price: float = 0.0        # DOWN token bid (exit/realizable)
    up_bid: float = 0.0            # UP token best bid
    up_ask: float = 0.0            # UP token best ask
    down_bid: float = 0.0          # DOWN token best bid
    down_ask: float = 0.0          # DOWN token best ask
    best_bid: float = 0.0          # dominant taraf bid (geriye uyum)
    best_ask: float = 0.0          # dominant taraf ask (geriye uyum)
    outcome_fresh: bool = False    # outcome verisi fresh mi

    # ── Side mode ──
    side_mode: SideMode = SideMode.DOMINANT_ONLY

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
    def evaluated_side(self) -> str:
        """Side mode'a göre değerlendirilecek taraf."""
        if self.side_mode == SideMode.UP_ONLY:
            return "UP"
        if self.side_mode == SideMode.DOWN_ONLY:
            return "DOWN"
        # DOMINANT: bid bazlı dominant taraf (exit perspektifi)
        return "UP" if self.up_bid >= self.down_bid else "DOWN"

    @property
    def entry_ref_price(self) -> float:
        """Entry karar fiyatı — FOK market order = ASK tarafı.

        Price rule bu fiyatı kullanır (gerçek giriş maliyeti).
        """
        if self.side_mode == SideMode.UP_ONLY:
            return self.up_ask
        if self.side_mode == SideMode.DOWN_ONLY:
            return self.down_ask
        # DOMINANT: dominant tarafın ask'ı
        return self.up_ask if self.up_bid >= self.down_bid else self.down_ask

    @property
    def exit_ref_price(self) -> float:
        """Exit realizasyon fiyatı — satış = BID tarafı.

        TP/SL/FS bu fiyatı kullanır (gerçek çıkış değeri).
        """
        if self.side_mode == SideMode.UP_ONLY:
            return self.up_bid
        if self.side_mode == SideMode.DOWN_ONLY:
            return self.down_bid
        return self.up_bid if self.up_bid >= self.down_bid else self.down_bid

    @property
    def evaluated_price(self) -> float:
        """Entry karar fiyatı — price rule için (= entry_ref_price).

        FOK market order → maliyet = ask tarafı.
        """
        return self.entry_ref_price

    @property
    def evaluated_price_100(self) -> float:
        """Entry fiyat 0-100 ölçeğinde."""
        return self.evaluated_price * 100

    # Backward compat
    @property
    def dominant_price(self) -> float:
        return self.evaluated_price

    @property
    def dominant_side(self) -> str:
        return self.evaluated_side

    @property
    def dominant_price_100(self) -> float:
        return self.evaluated_price_100

    @property
    def spread_pct(self) -> float:
        """Spread yüzdesi: dominant tarafın (ask-bid)/ask*100."""
        ask = self.entry_ref_price
        bid = self.exit_ref_price
        if ask > 0:
            return (ask - bid) / ask * 100
        return 0.0

    @property
    def delta(self) -> float:
        """Delta: abs(coin_usd - PTB). Sabit USD fark."""
        if self.coin_usd_price > 0 and self.ptb_value > 0:
            return abs(self.coin_usd_price - self.ptb_value)
        return 0.0

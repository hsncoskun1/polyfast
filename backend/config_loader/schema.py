"""Configuration schema — Pydantic models for validated config.

Kullanıcı format kararları:
- Fiyat: 0-100 ölçeği (51-99 dominant side). 85 = 0.85 outcome price.
- Spread: ondalıklı yüzde. 3.2 = max %3.2.
- Delta: sabit USD fark. BTC=$50, DOGE=$0.001.
- Stop Loss / Take Profit: PnL yüzdesi. 3 = %3 zarar/kar.
- Force Sell: checkbox bazlı koşullar. Seçilenlerin HEPSİ sağlanınca tetiklenir.
- Time: kalan saniye (event bitimine).
- Event Max / Bot Max: tam sayı.
- Retry interval: milisaniye cinsinden.
"""

from pydantic import BaseModel, Field, model_validator


# --- Entry Rules ---

class TimeRuleConfig(BaseModel):
    """Zaman kuralı — event'in bitmesine kalan saniyeye bakar.

    Kullanıcı min/max saniye girer. Kalan süre aralıktaysa PASS.
    Event'in başından beri geçen süre kullanılmaz.
    """
    enabled: bool = True
    min_seconds: int = Field(default=30, ge=1, le=299)
    max_seconds: int = Field(default=270, ge=1, le=299)

    @model_validator(mode="after")
    def min_less_than_max(self):
        if self.min_seconds >= self.max_seconds:
            raise ValueError(
                f"time rule: min_seconds ({self.min_seconds}) must be < max_seconds ({self.max_seconds})"
            )
        return self


class PriceRuleConfig(BaseModel):
    """Fiyat kuralı — dominant tarafın canlı outcome fiyatına bakar.

    dominant = max(up_price, down_price), her zaman >= 0.51.
    Kullanıcı 0-100 ölçeğinde girer (85 = 0.85 outcome price).
    Min 51 — dominant taraf her zaman >= 0.51.
    Evaluation: dominant_price * 100 >= min_price AND <= max_price.
    """
    enabled: bool = True
    min_price: int = Field(default=51, ge=51, le=99)
    max_price: int = Field(default=85, ge=51, le=99)

    @model_validator(mode="after")
    def min_less_than_max(self):
        if self.min_price >= self.max_price:
            raise ValueError(
                f"price rule: min_price ({self.min_price}) must be < max_price ({self.max_price})"
            )
        return self


class DeltaRuleConfig(BaseModel):
    """Delta kuralı — PTB ile coin'in anlık USD fiyatı arasındaki mutlak fark.

    Formül: abs(current_coin_usd_price - PTB)
    Sabit USD fark. Yüzde değil. Yön önemsiz.
    Outcome price ile hesaplanMAZ — coin canlı USD fiyatı ayrı streaming kaynaktan gelir.
    Örnek: BTC threshold=50 → $50 fark, DOGE threshold=0.001 → $0.001 fark.
    """
    enabled: bool = True
    threshold: float = Field(default=50.0, ge=0.00001, le=100000.0)


class SpreadRuleConfig(BaseModel):
    """Spread kuralı — outcome market spread'ine bakar.

    Formül: spread_pct = (best_ask - best_bid) / best_ask * 100
    best_ask bazlı (mid değil). Coin USD spread'i DEĞİL.
    Kullanıcı ondalıklı yüzde girer: 3.2 = max %3.2.
    """
    enabled: bool = True
    max_spread: float = Field(default=3.0, ge=0.1, le=50.0)


class EventMaxConfig(BaseModel):
    """Event Max — tek 5dk event instance'ı içindeki max işlem sayısı.

    Alış fill sayısını sayar. Fill olmayan order sayılmaz.
    İşlem kapanmış olsa bile aynı event'te ikinci giriş olmaz.
    Yeni event başladığında sıfırlanır.
    """
    enabled: bool = True
    max_positions: int = Field(default=1, ge=1, le=10)


class BotMaxConfig(BaseModel):
    """Bot Max — tüm aktif event'ler genelindeki aynı anda açık toplam işlem.

    Global üst limit.
    Event Max + Bot Max birlikte sağlanmalı — biri doluysa işlem açılamaz.
    """
    enabled: bool = True
    max_positions: int = Field(default=3, ge=1, le=50)


class EntryRulesConfig(BaseModel):
    time: TimeRuleConfig = TimeRuleConfig()
    price: PriceRuleConfig = PriceRuleConfig()
    delta: DeltaRuleConfig = DeltaRuleConfig()
    spread: SpreadRuleConfig = SpreadRuleConfig()
    event_max: EventMaxConfig = EventMaxConfig()
    bot_max: BotMaxConfig = BotMaxConfig()


# --- Exit Rules ---

class TakeProfitConfig(BaseModel):
    """Take Profit — PnL bazli kar alma.

    PnL % = (current_held_side_price - fill_price) / fill_price * 100
    Kullanici yuzde girer: 5 = %5 kar.

    reevaluate_on_retry: True ise retry oncesi TP kosulu tekrar kontrol edilir.
    Fiyat geri cekildiyse close IPTAL edilir (open_confirmed'a doner).
    False ise latch — ilk tetikten sonra iptal yok.
    """
    enabled: bool = True
    percentage: float = Field(default=5.0, ge=0.1, le=100.0)
    retry_interval_ms: int = Field(default=400, ge=100, le=10000)
    reevaluate_on_retry: bool = True


class StopLossConfig(BaseModel):
    """Stop Loss — PnL bazlı zarar durdurma.

    PnL % = (current_held_side_price - fill_price) / fill_price * 100
    - UP pozisyonunda: current_up_price kullanılır
    - DOWN pozisyonunda: current_down_price kullanılır
    - Reference: actual fill price (order/requested price DEĞİL)
    - Market FOK — partial fill olmaz, tek fill price

    Kullanıcı yüzde girer: 3 = %3 zarar.
    retry_interval_ms: satış emri red alırsa kaç ms sonra tekrar denenecek.
    jump_threshold: tek tick'te aşırı düşüş = orderbook anomali, SL tetiklenmez.
    Tüm değerler ayarlar kısmından editlenebilir.
    """
    enabled: bool = True
    percentage: float = Field(default=3.0, ge=0.1, le=100.0)
    retry_interval_ms: int = Field(default=500, ge=100, le=10000)
    retry_max: int = Field(default=3, ge=1, le=20)
    jump_threshold: float = Field(default=0.15, ge=0.01, le=1.0)


class ForceSellTimeCondition(BaseModel):
    """Force sell zaman koşulu — event bitimine X saniye kala."""
    enabled: bool = True
    remaining_seconds: int = Field(default=30, ge=1, le=299)


class ForceSellPnlCondition(BaseModel):
    """Force sell PnL loss koşulu — PnL zarar yüzdesi."""
    enabled: bool = False
    loss_percentage: float = Field(default=5.0, ge=0.1, le=100.0)


class ForceSellConfig(BaseModel):
    """Force Sell — checkbox bazlı zorunlu çıkış koşulları.

    SADECE iki koşul var:
    1. time — event bitimine X saniye kala
    2. pnl_loss — PnL zarar yüzdesi

    Force sell delta KALDIRILDI (delta sadece entry kuralı).

    Seçilenlerin (enabled=True) HEPSİ sağlanınca force sell tetiklenir.
    Tek koşul seçildiyse o yeterli.

    Stale safety: outcome stale ise force sell time tek başına safety
    override olarak çalışabilir — zaman bazlı çıkış bloke olmaz.

    Tüm exit orderları Market FOK.
    """
    time: ForceSellTimeCondition = ForceSellTimeCondition()
    pnl_loss: ForceSellPnlCondition = ForceSellPnlCondition()
    retry_interval_ms: int = Field(default=500, ge=100, le=10000)
    retry_max: int = Field(default=3, ge=1, le=20)


class ExitRulesConfig(BaseModel):
    """Exit kurallari + genel exit retry ayarlari.

    Retry intervaller: close basarisiz olduktan sonra kac ms beklenecek.
    max_close_retries: tek cycle icerisindeki retry siniri.
    Exit orchestrator her cycle'da CLOSE_FAILED pozisyonlari tekrar secer
    → 7/24 calismada pozisyon tamamen kapanana kadar denenir.
    """
    take_profit: TakeProfitConfig = TakeProfitConfig()
    stop_loss: StopLossConfig = StopLossConfig()
    force_sell: ForceSellConfig = ForceSellConfig()
    manual_close_retry_interval_ms: int = Field(default=400, ge=100, le=10000)
    expiry_retry_interval_ms: int = Field(default=200, ge=50, le=10000)
    shutdown_retry_interval_ms: int = Field(default=100, ge=50, le=5000)
    max_close_retries: int = Field(default=10, ge=1, le=30)
    exit_order_timeout_sec: float = Field(default=5.0, ge=1.0, le=30.0)


class ClaimRedeemConfig(BaseModel):
    """Claim/redeem retry ayarlari — advanced admin.

    Claim/redeem basarisiz olduktan sonraki yeniden deneme parametreleri.
    Evaluation araligi DEGIL.
    Retry schedule: initial -> second -> steady -> steady... max attempts.
    """
    wait_for_claim_before_new_trade: bool = True
    retry_initial_seconds: int = Field(default=5, ge=1, le=60)
    retry_second_seconds: int = Field(default=10, ge=1, le=60)
    retry_steady_seconds: int = Field(default=20, ge=5, le=120)
    max_retry_attempts: int = Field(default=20, ge=1, le=50)


# --- Trading ---

class TradingConfig(BaseModel):
    min_amount_usd: float = Field(default=1.0, ge=0.1, le=10000.0)
    auto_start_bot_on_startup: bool = False
    paper_mode: bool = True  # Test asamasi: paper mode. Live'a gecis kullanici karari.
    signature_type: int = Field(default=2, ge=0, le=2)  # 0=EOA, 2=Proxy wallet (Polymarket default)
    entry_order_timeout_sec: float = Field(default=5.0, ge=1.0, le=30.0)
    order_reject_cooldown_sec: float = Field(default=1.0, ge=0.5, le=30.0)
    entry_rules: EntryRulesConfig = EntryRulesConfig()
    exit_rules: ExitRulesConfig = ExitRulesConfig()
    claim: ClaimRedeemConfig = ClaimRedeemConfig()


# --- Infrastructure ---

class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)


class DiscoveryConfig(BaseModel):
    """Discovery ayarlari — admin/advanced."""
    interval_seconds: int = Field(default=10, ge=1, le=300)
    timeout_seconds: int = Field(default=15, ge=1, le=60)
    category: str = "crypto"
    subcategory: str = "up_down"
    duration: str = "5m"
    # Retry schedule: event bulunamazsa bekleme sureleri (saniye)
    retry_initial_seconds: int = Field(default=2, ge=1, le=30)
    retry_schedule_2: int = Field(default=4, ge=1, le=30)
    retry_schedule_3: int = Field(default=8, ge=1, le=60)
    retry_schedule_4: int = Field(default=16, ge=1, le=60)
    retry_steady_seconds: int = Field(default=10, ge=1, le=60)
    # Registry delist: ardisik scan'da gorulmeyen event soft-remove esigi
    delist_threshold: int = Field(default=3, ge=1, le=10)


class NetworkConfig(BaseModel):
    """Network / HTTP / auth ayarlari — admin/advanced.

    Tum HTTP client'lar icin timeout, retry ve backoff degerleri.
    """
    default_timeout_seconds: float = Field(default=15.0, ge=1.0, le=60.0)
    default_retry_max: int = Field(default=3, ge=1, le=10)
    default_backoff_base: float = Field(default=1.0, ge=0.5, le=5.0)
    relayer_timeout_seconds: float = Field(default=30.0, ge=10.0, le=120.0)
    clob_api_timeout_seconds: float = Field(default=5.0, ge=1.0, le=30.0)
    fee_rate_timeout_seconds: float = Field(default=5.0, ge=1.0, le=30.0)


class InfraConfig(BaseModel):
    """Altyapi operasyonel ayarlar — admin/advanced.

    Supervisor, verify retry, SDK transient retry gibi
    7/24 operasyonel parametreler.
    """
    supervisor_interval_sec: float = Field(default=10.0, ge=5.0, le=60.0)
    verify_retry_interval_sec: float = Field(default=30.0, ge=10.0, le=120.0)
    sdk_transient_retry_sleep_sec: float = Field(default=3.0, ge=1.0, le=15.0)


class MarketDataConfig(BaseModel):
    """Market veri ayarlari — admin/advanced."""
    ptb_source: str = Field(default="next_data", pattern="^(next_data|api)$")
    # Stale threshold'lari
    stale_threshold_seconds: int = Field(default=30, ge=5, le=300)
    coin_price_stale_threshold_seconds: int = Field(default=15, ge=5, le=120)
    balance_stale_threshold_seconds: int = Field(default=90, ge=30, le=300)
    # Interval'lar
    coin_price_resub_interval_ms: int = Field(default=150, ge=50, le=5000)
    balance_refresh_interval_seconds: int = Field(default=20, ge=5, le=60)
    exit_cycle_interval_ms: int = Field(default=50, ge=10, le=2000)
    evaluation_interval_ms: int = Field(default=200, ge=50, le=2000)
    # WS reconnect
    ws_reconnect_backoff_base: float = Field(default=2.0, ge=1.0, le=10.0)
    ws_reconnect_backoff_max: float = Field(default=30.0, ge=5.0, le=120.0)
    # WS operational timeout'lar
    ws_close_timeout_seconds: float = Field(default=3.0, ge=1.0, le=10.0)
    ws_receive_timeout_seconds: float = Field(default=1.0, ge=0.1, le=10.0)
    ws_resub_message_timeout_seconds: float = Field(default=0.05, ge=0.01, le=1.0)
    # PTB retry (discovery ile ayni pattern)
    ptb_retry_initial_seconds: int = Field(default=2, ge=1, le=30)
    ptb_retry_schedule_2: int = Field(default=4, ge=1, le=30)
    ptb_retry_schedule_3: int = Field(default=8, ge=1, le=60)
    ptb_retry_schedule_4: int = Field(default=16, ge=1, le=60)
    ptb_retry_steady_seconds: int = Field(default=10, ge=1, le=60)


class PersistenceConfig(BaseModel):
    db_path: str = "data/polyfast.db"


class LoggingConfig(BaseModel):
    """Log ayarlari — admin/advanced.

    level: Log detay seviyesi (DEBUG en detayli, CRITICAL sadece kritik)
    format: json = makine okunur, human = insan okunur
    file_path: Log dosyasi konumu
    mask_credentials: Credential'lari logda gizle (her zaman true olmali)
    """
    level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    format: str = Field(default="json", pattern="^(json|human)$")
    file_path: str = "logs/polyfast.log"
    mask_credentials: bool = True


# --- Root ---

class AppConfig(BaseModel):
    server: ServerConfig = ServerConfig()
    trading: TradingConfig = TradingConfig()
    discovery: DiscoveryConfig = DiscoveryConfig()
    market_data: MarketDataConfig = MarketDataConfig()
    network: NetworkConfig = NetworkConfig()
    infra: InfraConfig = InfraConfig()
    persistence: PersistenceConfig = PersistenceConfig()
    logging: LoggingConfig = LoggingConfig()

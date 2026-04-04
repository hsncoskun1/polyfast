"""Configuration schema — Pydantic models for validated config."""

from pydantic import BaseModel, Field, model_validator


# --- Entry Rules ---

class TimeRuleConfig(BaseModel):
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
    enabled: bool = True
    min_price: float = Field(default=0.15, ge=0.01, le=0.99)
    max_price: float = Field(default=0.85, ge=0.01, le=0.99)

    @model_validator(mode="after")
    def min_less_than_max(self):
        if self.min_price >= self.max_price:
            raise ValueError(
                f"price rule: min_price ({self.min_price}) must be < max_price ({self.max_price})"
            )
        return self


class DeltaRuleConfig(BaseModel):
    enabled: bool = True
    threshold: float = Field(default=0.03, ge=0.001, le=0.5)


class SpreadRuleConfig(BaseModel):
    enabled: bool = True
    max_spread: float = Field(default=0.04, ge=0.001, le=0.5)


class EventMaxConfig(BaseModel):
    enabled: bool = True
    max_positions: int = Field(default=1, ge=1, le=10)


class BotMaxConfig(BaseModel):
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
    enabled: bool = True
    percentage: float = Field(default=5.0, ge=0.1, le=100.0)


class StopLossConfig(BaseModel):
    enabled: bool = True
    percentage: float = Field(default=3.0, ge=0.1, le=100.0)
    retry_interval_seconds: int = Field(default=5, ge=1, le=60)
    retry_max: int = Field(default=3, ge=1, le=20)
    jump_threshold: float = Field(default=0.15, ge=0.01, le=1.0)


class ForceSellConfig(BaseModel):
    enabled: bool = True
    combinator: str = Field(default="any", pattern="^(all|any)$")
    remaining_time_seconds: int = Field(default=30, ge=1, le=299)
    pnl_loss_percentage: float = Field(default=5.0, ge=0.1, le=100.0)
    fill_delta_drop: float = Field(default=0.05, ge=0.001, le=0.5)
    retry_interval_seconds: int = Field(default=5, ge=1, le=60)
    retry_max: int = Field(default=3, ge=1, le=20)


class ExitRulesConfig(BaseModel):
    take_profit: TakeProfitConfig = TakeProfitConfig()
    stop_loss: StopLossConfig = StopLossConfig()
    force_sell: ForceSellConfig = ForceSellConfig()


class ClaimConfig(BaseModel):
    wait_for_claim_before_new_trade: bool = True


# --- Trading ---

class TradingConfig(BaseModel):
    min_amount_usd: float = Field(default=5.0, ge=1.0, le=10000.0)
    entry_rules: EntryRulesConfig = EntryRulesConfig()
    exit_rules: ExitRulesConfig = ExitRulesConfig()
    claim: ClaimConfig = ClaimConfig()


# --- Infrastructure ---

class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)


class DiscoveryConfig(BaseModel):
    interval_seconds: int = Field(default=10, ge=1, le=300)
    timeout_seconds: int = Field(default=15, ge=1, le=60)
    category: str = "crypto"
    subcategory: str = "up_down"
    duration: str = "5m"


class MarketDataConfig(BaseModel):
    ptb_source: str = Field(default="next_data", pattern="^(next_data|api)$")
    stale_threshold_seconds: int = Field(default=30, ge=5, le=300)


class PersistenceConfig(BaseModel):
    db_path: str = "data/polyfast.db"


class LoggingConfig(BaseModel):
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
    persistence: PersistenceConfig = PersistenceConfig()
    logging: LoggingConfig = LoggingConfig()

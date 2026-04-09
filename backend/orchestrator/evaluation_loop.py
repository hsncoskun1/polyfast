"""EvaluationLoop — periyodik rule engine evaluation döngüsü.

Runtime state'ten EvaluationContext doldurur → RuleEngine.evaluate() çağırır.
ENTRY/NO_ENTRY/WAITING sinyali üretir — order göndermez.

Context doldurma:
- LivePricePipeline → up_price, down_price, best_bid, best_ask, outcome_fresh
- CoinPriceClient → coin_usd_price, coin_usd_fresh
- PTBFetcher → ptb_value, ptb_acquired
- CoinSettings → side_mode, thresholds, enabled flags
- Slot calculation → seconds_remaining

Evaluation runtime state'ten yapılır — snapshot'tan DEĞİL.
Kör retry YOK — her evaluation bağımsız güncel context.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

from backend.strategy.engine import RuleEngine, EvaluationResult
from backend.strategy.evaluation_context import EvaluationContext
from backend.strategy.rule_state import OverallDecision
from backend.market_data.live_price import LivePricePipeline, PriceStatus
from backend.market_data.coin_price_client import CoinPriceClient, CoinPriceStatus
from backend.ptb.fetcher import PTBFetcher
from backend.settings.settings_store import SettingsStore
from backend.settings.coin_settings import CoinSettings
from backend.logging_config.service import get_logger, log_event

logger = get_logger("orchestrator.evaluation")

SLOT_SECONDS = 300


class EvaluationLoop:
    """Periyodik rule evaluation döngüsü.

    Her eligible event için context doldurur ve engine'i çağırır.
    ENTRY sinyali üretir ama order GÖNDERMEz (log only).
    """

    def __init__(
        self,
        engine: RuleEngine,
        pipeline: LivePricePipeline,
        coin_client: CoinPriceClient,
        ptb_fetcher: PTBFetcher,
        settings_store: SettingsStore,
        interval_ms: int = 200,  # schema: MarketDataConfig.evaluation_interval_ms
    ):
        self._engine = engine
        self._pipeline = pipeline
        self._coin_client = coin_client
        self._ptb_fetcher = ptb_fetcher
        self._settings = settings_store
        self._interval = interval_ms / 1000.0
        self._running = False
        self._task: asyncio.Task | None = None
        self._eval_count: int = 0
        self._entry_count: int = 0
        # Son evaluation sonuçları — snapshot provider bu cache'i okur
        self._last_results: dict[str, "EvaluationResult"] = {}

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="evaluation_loop")
        log_event(
            logger, logging.INFO,
            f"Evaluation loop started (interval={self._interval*1000:.0f}ms)",
            entity_type="orchestrator",
            entity_id="evaluation_start",
        )

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def eval_count(self) -> int:
        return self._eval_count

    @property
    def entry_signal_count(self) -> int:
        return self._entry_count

    def get_last_results(self) -> dict[str, "EvaluationResult"]:
        """Son evaluation sonuçlarını döndür (snapshot provider için). Kopya döner."""
        return dict(self._last_results)

    def get_last_result(self, asset: str) -> "EvaluationResult | None":
        """Tek coin için son evaluation sonucu."""
        return self._last_results.get(asset)

    async def _loop(self) -> None:
        """Ana evaluation döngüsü."""
        while self._running:
            try:
                await self._evaluate_all_eligible()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log_event(
                    logger, logging.ERROR,
                    f"Evaluation loop error: {e}",
                    entity_type="orchestrator",
                    entity_id="evaluation_error",
                )
            await asyncio.sleep(self._interval)

    async def _evaluate_all_eligible(self) -> None:
        """Tüm eligible event'ler için evaluation yap."""
        eligible_settings = self._settings.get_eligible_coins()

        for coin_settings in eligible_settings:
            result = self._evaluate_single(coin_settings)
            if result is None:
                continue

            self._eval_count += 1

            if result.decision == OverallDecision.ENTRY:
                self._entry_count += 1
                log_event(
                    logger, logging.INFO,
                    f"ENTRY signal: {coin_settings.coin} {result.detail.get('dominant_side', '?')}",
                    entity_type="orchestrator",
                    entity_id=f"entry_{coin_settings.coin}",
                    payload={
                        "asset": coin_settings.coin,
                        "decision": result.decision.value,
                        "pass": result.pass_count,
                        "fail": result.fail_count,
                        "waiting": result.waiting_count,
                    },
                )
                # ORDER GÖNDERİLMEZ — sadece log (Faz 5)

    def _evaluate_single(self, coin_settings: CoinSettings) -> EvaluationResult | None:
        """Tek coin için context doldur ve evaluate et."""
        asset = coin_settings.coin

        # Pipeline'dan outcome fiyat
        price_record = self._pipeline.get_record_by_asset(asset)
        if price_record:
            up_price = price_record.up_price
            down_price = price_record.down_price
            best_bid = price_record.best_bid
            best_ask = price_record.best_ask
            outcome_fresh = price_record.status == PriceStatus.FRESH
            condition_id = price_record.condition_id
        else:
            up_price = down_price = best_bid = best_ask = 0.0
            outcome_fresh = False
            condition_id = ""

        # Coin USD fiyat
        coin_record = self._coin_client.get_price(asset)
        coin_usd = coin_record.usd_price if coin_record else 0.0
        coin_fresh = coin_record.status == CoinPriceStatus.FRESH if coin_record else False

        # PTB
        ptb_record = self._ptb_fetcher.get_record(condition_id) if condition_id else None
        ptb_value = ptb_record.ptb_value if ptb_record and ptb_record.is_locked else 0.0
        ptb_acquired = ptb_record.is_locked if ptb_record else False

        # Kalan süre
        now = time.time()
        slot_start = (int(now) // SLOT_SECONDS) * SLOT_SECONDS
        seconds_remaining = (slot_start + SLOT_SECONDS) - now

        # Context oluştur
        ctx = EvaluationContext(
            condition_id=condition_id,
            asset=asset,
            up_price=up_price,
            down_price=down_price,
            best_bid=best_bid,
            best_ask=best_ask,
            outcome_fresh=outcome_fresh,
            coin_usd_price=coin_usd,
            coin_usd_fresh=coin_fresh,
            ptb_value=ptb_value,
            ptb_acquired=ptb_acquired,
            seconds_remaining=seconds_remaining,
            side_mode=coin_settings.side_mode,
            time_min_seconds=coin_settings.time_min,
            time_max_seconds=coin_settings.time_max,
            price_min=coin_settings.price_min,
            price_max=coin_settings.price_max,
            delta_threshold=coin_settings.delta_threshold,
            spread_max_pct=coin_settings.spread_max,
            event_max_positions=coin_settings.event_max,
            # Event fill count ve open position count → v0.5.x (şimdilik 0)
            event_fill_count=0,
            open_position_count=0,
            time_enabled=coin_settings.time_min > 0,
            price_enabled=coin_settings.price_min > 0,
            delta_enabled=coin_settings.delta_threshold > 0,
            spread_enabled=coin_settings.spread_max > 0,
        )

        result = self._engine.evaluate(ctx)
        self._last_results[asset] = result
        return result

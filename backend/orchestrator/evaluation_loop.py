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
    ENTRY sinyali üretir.

    Order dispatch kontrolü:
    - _order_dispatch_enabled=False (default): sinyal sadece log
    - _order_dispatch_enabled=True: sinyal OrderExecutor'a gider
    - enable_order_dispatch() / disable_order_dispatch() ile kontrol
    - Bot başladığında dispatch KAPALI — manuel enable gerekli
    """

    def __init__(
        self,
        engine: RuleEngine,
        pipeline: LivePricePipeline,
        coin_client: CoinPriceClient,
        ptb_fetcher: PTBFetcher,
        settings_store: SettingsStore,
        interval_ms: int = 200,
        bot_max_positions: int = 3,
        order_executor=None,
        position_tracker=None,
        bridge=None,
        registry=None,
    ):
        self._engine = engine
        self._pipeline = pipeline
        self._coin_client = coin_client
        self._ptb_fetcher = ptb_fetcher
        self._settings = settings_store
        self._interval = interval_ms / 1000.0
        self._bot_max_positions = bot_max_positions
        self._order_executor = order_executor  # None = sinyal only
        self._position_tracker = position_tracker  # counter wiring icin
        self._bridge = bridge  # token_id lookup icin
        self._registry = registry  # current slot guard icin
        self._order_dispatch_enabled = False  # Baslatma kontrolu: False=sinyal only, True=order gonder
        self._running = False
        self._task: asyncio.Task | None = None
        self._eval_count: int = 0
        self._entry_count: int = 0
        self._last_results: dict[str, "EvaluationResult"] = {}

    async def start(self) -> None:
        if self._running and self._task and not self._task.done():
            return  # Çalışıyor — skip
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

    def enable_order_dispatch(self) -> None:
        """Order dispatch'i ac — ENTRY sinyalinde gercek order gider."""
        self._order_dispatch_enabled = True
        log_event(logger, logging.INFO, "Order dispatch ENABLED",
                  entity_type="orchestrator", entity_id="dispatch_enabled")

    def disable_order_dispatch(self) -> None:
        """Order dispatch'i kapat — ENTRY sinyali sadece log."""
        self._order_dispatch_enabled = False
        log_event(logger, logging.INFO, "Order dispatch DISABLED",
                  entity_type="orchestrator", entity_id="dispatch_disabled")

    @property
    def is_order_dispatch_enabled(self) -> bool:
        return self._order_dispatch_enabled

    def get_last_results(self) -> dict[str, "EvaluationResult"]:
        """Son evaluation sonuçlarını döndür (snapshot provider için). Kopya döner."""
        return dict(self._last_results)

    def get_last_result(self, asset: str) -> "EvaluationResult | None":
        """Tek coin için son evaluation sonucu."""
        return self._last_results.get(asset)

    def _find_current_slot_condition_id(self, asset: str) -> str:
        """Registry'den bu coin'in current slot event condition_id'sini bul.

        Gamma slug format: {asset}-updown-5m-{START_TIMESTAMP}
        Event live = START <= now < START + 300

        Returns:
            condition_id (str) veya "" (current event yok)
        """
        if not self._registry:
            return ""

        import time as _time
        import re as _re
        now = int(_time.time())

        for rec in self._registry.get_all():
            if rec.asset.upper() != asset.upper():
                continue
            m = _re.search(r'-(\d{10,})$', rec.slug)
            if not m:
                continue
            start_ts = int(m.group(1))  # slug timestamp = START
            end_ts = start_ts + 300
            if start_ts <= now < end_ts:
                return rec.condition_id

        return ""

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

                # Order dispatch — sadece enable edilmisse ve executor varsa
                if self._order_dispatch_enabled and self._order_executor is not None:
                    await self._dispatch_entry(coin_settings, result)

    async def _dispatch_entry(self, coin_settings: CoinSettings, result) -> None:
        """ENTRY sinyalini OrderExecutor'a gonder.

        CURRENT SLOT GUARD: Sadece su anki live slot event'ine order gider.
        Upcoming event'lere order gonderilMEZ.
        FOK retry YOK — bir sonraki evaluation cycle yeni sinyal uretir.
        """
        from backend.execution.order_intent import OrderIntent, OrderSide
        import time as _time
        import re as _re

        side_str = result.detail.get('dominant_side', 'UP')
        side = OrderSide.UP if side_str == 'UP' else OrderSide.DOWN

        # Current slot event'in condition_id'si ile pipeline record al
        current_cid = self._find_current_slot_condition_id(coin_settings.coin)
        if not current_cid:
            return  # current slot event yok — dispatch skip

        price_record = self._pipeline.get_record(current_cid)
        if not price_record:
            return  # pipeline'da current event record yok

        condition_id = current_cid

        # ── CURRENT SLOT GUARD ──
        # Discovery upcoming eventleri de dondurur (30dk lookahead).
        # Order SADECE current live slot event'ine gitmeli.
        # Truth source: registry'deki event slug timestamp'i.
        # Gamma slug format: {asset}-updown-5m-{START_TIMESTAMP}
        # Event live = START <= now < START + 300
        now = int(_time.time())

        if self._registry:
            reg = self._registry.get_by_condition_id(condition_id)
            if reg:
                m = _re.search(r'-(\d{10,})$', reg.slug)
                if m:
                    event_start_ts = int(m.group(1))  # slug = START
                    event_end_ts = event_start_ts + 300
                    if not (event_start_ts <= now < event_end_ts):
                        # Bu event current slot'ta degil — upcoming veya gecmis
                        log_event(
                            logger, logging.DEBUG,
                            f"DISPATCH SKIP: {coin_settings.coin} event not in current slot "
                            f"(event={event_start_ts}-{event_end_ts}, now={now})",
                            entity_type="orchestrator",
                            entity_id=f"slot_skip_{coin_settings.coin}",
                        )
                        return

        # Bridge'den bu coin'in token_id'sini bul — condition_id eslesmeliyle
        bridge = getattr(self, '_bridge', None)
        token_id = ""
        if bridge:
            for tid, route in bridge._token_routes.items():
                if route.asset.upper() != coin_settings.coin.upper():
                    continue
                if route.side.upper() != side_str:
                    continue
                if route.condition_id == condition_id:
                    token_id = tid
                    break

        if not token_id:
            log_event(
                logger, logging.WARNING,
                f"ENTRY skipped: no token_id for {coin_settings.coin} {side_str}",
                entity_type="orchestrator",
                entity_id=f"entry_skip_{coin_settings.coin}",
            )
            return

        entry_price = result.detail.get('entry_ref_price', 0)

        intent = OrderIntent(
            asset=coin_settings.coin,
            side=side,
            amount_usd=coin_settings.order_amount,
            condition_id=condition_id,
            token_id=token_id,
            dominant_price=entry_price,
            event_max=coin_settings.event_max,
        )

        try:
            exec_result = await self._order_executor.execute(intent)
            log_event(
                logger, logging.INFO,
                f"Order result: {coin_settings.coin} {side_str} → {exec_result.result.value}",
                entity_type="orchestrator",
                entity_id=f"order_{coin_settings.coin}",
                payload={"result": exec_result.result.value, "position_id": exec_result.position_id},
            )
        except Exception as e:
            log_event(
                logger, logging.ERROR,
                f"Order dispatch error: {coin_settings.coin} {type(e).__name__}: {e}",
                entity_type="orchestrator",
                entity_id=f"order_error_{coin_settings.coin}",
            )

    def _evaluate_single(self, coin_settings: CoinSettings) -> EvaluationResult | None:
        """Tek coin için context doldur ve evaluate et."""
        asset = coin_settings.coin

        # Pipeline'dan outcome fiyat — CURRENT SLOT event'i oncelikli
        # Registry'den current slot event condition_id bul,
        # sonra o condition_id ile pipeline record al.
        # get_record_by_asset kullanma — upcoming event dondurur.
        current_cid = self._find_current_slot_condition_id(asset)
        price_record = None
        if current_cid:
            price_record = self._pipeline.get_record(current_cid)
        if price_record is None:
            # Fallback: asset bazli (dashboard/non-trading icin hala calismali)
            price_record = self._pipeline.get_record_by_asset(asset)

        if price_record:
            up_bid = price_record.up_bid
            up_ask = price_record.up_ask
            down_bid = price_record.down_bid
            down_ask = price_record.down_ask
            outcome_fresh = price_record.status == PriceStatus.FRESH
            condition_id = price_record.condition_id
        else:
            up_bid = up_ask = down_bid = down_ask = 0.0
            outcome_fresh = False
            condition_id = ""

        # Coin USD fiyat
        coin_record = self._coin_client.get_price(asset)
        coin_usd = coin_record.usd_price if coin_record else 0.0
        coin_fresh = coin_record.status == CoinPriceStatus.FRESH if coin_record else False

        # PTB — condition_id ile ara, bulamazsa asset ile fallback
        # Pipeline'da outcome price yoksa condition_id bos olur,
        # ama PTB ayri fetch edildigi icin asset bazli arama gerekir.
        ptb_record = self._ptb_fetcher.get_record(condition_id) if condition_id else None
        if ptb_record is None:
            ptb_record = self._ptb_fetcher.get_record_by_asset(asset)
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
            up_price=up_bid,       # geriye uyum: up_price = up_bid
            down_price=down_bid,   # geriye uyum: down_price = down_bid
            up_bid=up_bid,
            up_ask=up_ask,
            down_bid=down_bid,
            down_ask=down_ask,
            best_bid=max(up_bid, down_bid),    # dominant bid
            best_ask=(up_ask if up_bid >= down_bid else down_ask),  # dominant ask
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
            bot_max_positions=self._bot_max_positions,
            # Position counter wiring — PositionTracker varsa gerçek, yoksa 0
            event_fill_count=self._position_tracker.get_event_fill_count(condition_id) if self._position_tracker and condition_id else 0,
            open_position_count=self._position_tracker.open_position_count if self._position_tracker else 0,
            time_enabled=coin_settings.time_min > 0,
            price_enabled=coin_settings.price_min > 0,
            delta_enabled=coin_settings.delta_threshold > 0,
            spread_enabled=coin_settings.spread_max > 0,
        )

        result = self._engine.evaluate(ctx)
        self._last_results[asset] = result
        return result

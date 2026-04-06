"""Orchestrator Wiring — tum component'lari olusturup birbirine baglar.

Bu modul tum dependency'leri olusturur ve orchestrator zincirini kurar:
Discovery -> EligibilityGate -> SubscriptionManager -> EvaluationLoop
ExitOrchestrator -> ExitEvaluator -> ExitExecutor -> Settlement

main.py lifespan'dan cagrilir.
"""

import asyncio
import logging
import time as _time

from backend.auth_clients.public_client import PublicMarketClient
from backend.auth_clients.credential_store import CredentialStore
from backend.discovery.engine import DiscoveryEngine
from backend.registry.service import EventRegistry
from backend.registry.safe_sync import SafeSync
from backend.market_data.live_price import LivePricePipeline
from backend.market_data.rtds_client import RTDSClient
from backend.market_data.ws_price_bridge import WSPriceBridge
from backend.market_data.coin_price_client import CoinPriceClient
from backend.ptb.ssr_adapter import SSRPTBAdapter
from backend.ptb.fetcher import PTBFetcher
from backend.settings.settings_store import SettingsStore
from backend.strategy.engine import RuleEngine
from backend.execution.exit_evaluator import ExitEvaluator
from backend.execution.exit_executor import ExitExecutor
from backend.execution.position_tracker import PositionTracker
from backend.execution.balance_manager import BalanceManager
from backend.execution.claim_manager import ClaimManager
from backend.execution.clob_client_wrapper import ClobClientWrapper
from backend.execution.relayer_client_wrapper import RelayerClientWrapper
from backend.execution.order_validator import OrderValidator
from backend.persistence.position_store import PositionStore
from backend.persistence.claim_store import ClaimStore
from backend.orchestrator.discovery_loop import DiscoveryLoop
from backend.orchestrator.eligibility_gate import EligibilityGate
from backend.orchestrator.subscription_manager import SubscriptionManager
from backend.orchestrator.evaluation_loop import EvaluationLoop
from backend.orchestrator.exit_orchestrator import ExitOrchestrator
from backend.orchestrator.settlement import SettlementOrchestrator
from backend.orchestrator.cleanup import EventCleanup
from backend.orchestrator.health import HealthAggregator
from backend.config_loader.schema import AppConfig
from backend.logging_config.service import get_logger, log_event

logger = get_logger("orchestrator.wiring")


class Orchestrator:
    """Tum component'lari barindirir ve lifecycle yonetir.

    Zincir:
    Discovery -> EligibilityGate -> SubscriptionManager -> EvaluationLoop
    ExitOrchestrator -> ExitEvaluator -> ExitExecutor -> Settlement
    """

    def __init__(
        self,
        credential_store: CredentialStore | None = None,
        config: AppConfig | None = None,
    ):
        # Config — None ise default degerler kullanilir
        cfg = config or AppConfig()
        self._config = cfg

        # Credential store
        self.credential_store = credential_store or CredentialStore()

        # ── Data layer ──
        self.pipeline = LivePricePipeline(
            stale_threshold_sec=cfg.market_data.stale_threshold_seconds,
        )
        self.rtds_client = RTDSClient(
            reconnect_backoff_base=cfg.market_data.ws_reconnect_backoff_base,
            reconnect_backoff_max=cfg.market_data.ws_reconnect_backoff_max,
        )
        self.bridge = WSPriceBridge(self.pipeline)
        self.coin_client = CoinPriceClient(
            stale_threshold_sec=cfg.market_data.coin_price_stale_threshold_seconds,
            resub_interval_ms=cfg.market_data.coin_price_resub_interval_ms,
        )

        # PTB — retry schedule config'den
        ptb_schedule = [
            cfg.market_data.ptb_retry_initial_seconds,
            cfg.market_data.ptb_retry_schedule_2,
            cfg.market_data.ptb_retry_schedule_3,
            cfg.market_data.ptb_retry_schedule_4,
        ]
        self.ssr_adapter = SSRPTBAdapter()
        self.ptb_fetcher = PTBFetcher(
            source=self.ssr_adapter,
            retry_schedule=ptb_schedule,
            retry_steady_seconds=cfg.market_data.ptb_retry_steady_seconds,
        )

        # Registry — delist threshold config'den
        self.registry = EventRegistry()
        self.safe_sync = SafeSync(
            self.registry,
            delist_threshold=cfg.discovery.delist_threshold,
        )

        # Settings
        self.settings_store = SettingsStore()

        # Strategy
        self.rule_engine = RuleEngine()

        # Discovery — retry schedule config'den
        discovery_schedule = [
            cfg.discovery.retry_initial_seconds,
            cfg.discovery.retry_schedule_2,
            cfg.discovery.retry_schedule_3,
            cfg.discovery.retry_schedule_4,
        ]
        self.public_client = PublicMarketClient(
            timeout_seconds=cfg.network.default_timeout_seconds,
            retry_max=cfg.network.default_retry_max,
        )
        self.discovery_engine = DiscoveryEngine(self.public_client)

        # ── Persistence stores ──
        self.position_store = PositionStore()
        self.claim_store = ClaimStore()

        # ── Execution layer ──
        self.position_tracker = PositionTracker(position_store=self.position_store)
        self.balance_manager = BalanceManager(
            stale_threshold_sec=cfg.market_data.balance_stale_threshold_seconds,
            passive_refresh_interval=cfg.market_data.balance_refresh_interval_seconds,
        )
        self.clob_client = ClobClientWrapper(credential_store=self.credential_store)
        self.relayer_client = RelayerClientWrapper(credential_store=self.credential_store)

        # Claim manager — retry config + persistence
        self.claim_manager = ClaimManager(
            self.balance_manager, paper_mode=True,
            retry_initial_seconds=cfg.trading.claim.retry_initial_seconds,
            retry_second_seconds=cfg.trading.claim.retry_second_seconds,
            retry_steady_seconds=cfg.trading.claim.retry_steady_seconds,
            max_retry_attempts=cfg.trading.claim.max_retry_attempts,
            claim_store=self.claim_store,
        )

        # Exit evaluator — TP/SL config'den
        tp = cfg.trading.exit_rules.take_profit
        sl = cfg.trading.exit_rules.stop_loss
        fs = cfg.trading.exit_rules.force_sell
        self.exit_evaluator = ExitEvaluator(
            tp_pct=tp.percentage,
            sl_pct=sl.percentage,
            sl_jump_threshold=sl.jump_threshold,
            tp_reevaluate=tp.reevaluate_on_retry,
            force_sell_time_enabled=fs.time.enabled,
            force_sell_time_seconds=fs.time.remaining_seconds,
            force_sell_pnl_enabled=fs.pnl_loss.enabled,
            force_sell_pnl_pct=fs.pnl_loss.loss_percentage,
        )

        # Exit executor — retry intervals config'den
        self.exit_executor = ExitExecutor(
            self.position_tracker, self.balance_manager, paper_mode=True,
            tp_retry_interval_ms=tp.retry_interval_ms,
            sl_retry_interval_ms=sl.retry_interval_ms,
            fs_retry_interval_ms=fs.retry_interval_ms,
            manual_close_retry_interval_ms=cfg.trading.exit_rules.manual_close_retry_interval_ms,
            max_close_retries=cfg.trading.exit_rules.max_close_retries,
        )

        # Order validator — min amount config'den
        self.order_validator = OrderValidator(
            min_order_usd=cfg.trading.min_amount_usd,
        )

        self.settlement = SettlementOrchestrator(
            self.position_tracker, self.claim_manager, self.relayer_client,
            paper_mode=True, clob_client=self.clob_client,
            ptb_fetcher=self.ptb_fetcher, coin_price_client=self.coin_client,
        )
        self.exit_orchestrator = ExitOrchestrator(
            self.position_tracker, self.exit_evaluator, self.exit_executor,
            self.settlement, self.claim_manager,
        )

        # ── Orchestrator components ──
        self.eligibility_gate = EligibilityGate(self.settings_store)
        self.subscription_manager = SubscriptionManager(
            self.bridge, self.coin_client, self.ptb_fetcher,
        )
        self.cleanup = EventCleanup(
            self.pipeline, self.ptb_fetcher, self.bridge,
        )
        self.health_aggregator = HealthAggregator()

        # ── Loops ──
        self.discovery_loop = DiscoveryLoop(
            self.discovery_engine, self.safe_sync,
            on_events_found=self._handle_discovered_events,
            retry_schedule=discovery_schedule,
            retry_steady_seconds=cfg.discovery.retry_steady_seconds,
        )
        self.evaluation_loop = EvaluationLoop(
            self.rule_engine, self.pipeline, self.coin_client,
            self.ptb_fetcher, self.settings_store,
            interval_ms=cfg.market_data.evaluation_interval_ms,
        )

        # WS message callback
        self.rtds_client.set_message_callback(self.bridge.on_ws_message)

        # Exit cycle — config'den ms, runtime'da saniye
        self._exit_cycle_interval_sec = cfg.market_data.exit_cycle_interval_ms / 1000.0
        self._exit_cycle_task: asyncio.Task | None = None
        self._exit_cycle_running: bool = False

    async def _handle_discovered_events(self, events: list) -> None:
        """Discovery event bulduğunda çağrılır.

        Zincir: events → eligibility → subscription diff → subscribe/unsubscribe
        """
        # 1. Eligibility kontrol
        result = self.eligibility_gate.filter(events)

        if not result.eligible:
            return

        # 2. Eligible asset listesi
        eligible_assets = []
        event_map = {}
        for event in result.eligible:
            asset = event.get("asset", "") if isinstance(event, dict) else getattr(event, "asset", "")
            if asset:
                eligible_assets.append(asset)
                # Event data for subscription
                event_map[asset] = {
                    "condition_id": event.get("condition_id", "") if isinstance(event, dict) else getattr(event, "condition_id", ""),
                    "token_ids": list(event.get("clob_token_ids", [])) if isinstance(event, dict) else list(getattr(event, "clob_token_ids", [])),
                    "sides": list(event.get("outcomes", [])) if isinstance(event, dict) else list(getattr(event, "outcomes", [])),
                    "slug": event.get("slug", "") if isinstance(event, dict) else getattr(event, "slug", ""),
                }

        # 3. Subscription diff
        diff = self.subscription_manager.compute_diff(eligible_assets)
        await self.subscription_manager.apply_diff(diff, event_map)

        # 4. Coin USD subscribe güncelle
        self.coin_client.set_coins(eligible_assets)

        # 5. PTB fetch — sadece lock'lanmamış olanlar için
        for asset, info in event_map.items():
            cond_id = info.get("condition_id", "")
            slug = info.get("slug", "")
            if cond_id and slug:
                existing = self.ptb_fetcher.get_record(cond_id)
                if existing and existing.is_locked:
                    continue  # zaten lock'lı, tekrar deneme
                # Background task olarak PTB retry başlat
                slot_start = (int(_time.time()) // 300) * 300
                event_end_ts = float(slot_start + 300)
                asyncio.create_task(
                    self.ptb_fetcher.fetch_ptb_with_retry(
                        cond_id, asset, slug, event_end_ts,
                    ),
                    name=f"ptb_retry_{asset}",
                )

        log_event(
            logger, logging.INFO,
            f"Event chain: {len(result.eligible)} eligible, "
            f"+{len(diff.to_subscribe)} subscribe, -{len(diff.to_unsubscribe)} unsubscribe",
            entity_type="orchestrator",
            entity_id="event_chain",
        )

    async def restore_state(self) -> dict:
        """Startup state restore — SQLite'tan memory'ye yukle.

        Acik pozisyonlar + pending claim'ler restore edilir.
        Session devam eder — yeni session acilmaz.

        Returns:
            {"positions_restored": int, "claims_restored": int, "stale_detected": int}
        """
        result = {"positions_restored": 0, "claims_restored": 0, "stale_detected": 0}

        # 1. Pozisyonlari restore et
        positions = await self.position_store.load_all()
        for pos in positions:
            self.position_tracker.restore_position(pos)
            result["positions_restored"] += 1

        # 2. Claim'leri restore et
        claims = await self.claim_store.load_all()
        for claim in claims:
            self.claim_manager.restore_claim(claim)
            result["claims_restored"] += 1

        open_count = self.position_tracker.open_position_count
        pending_claims = self.claim_manager.pending_count

        log_event(
            logger, logging.INFO,
            f"State restored: {result['positions_restored']} positions "
            f"({open_count} open), {result['claims_restored']} claims "
            f"({pending_claims} pending)",
            entity_type="orchestrator",
            entity_id="restore",
        )

        return result

    async def start(self) -> None:
        """Tum loop'lari baslat."""
        log_event(
            logger, logging.INFO,
            "Orchestrator starting all loops",
            entity_type="orchestrator",
            entity_id="start",
        )

        # State restore (7/24 — restart sonrasi kaldigi yerden devam)
        await self.restore_state()

        # Coin price batch loop
        await self.coin_client.start()

        # Discovery loop
        await self.discovery_loop.start()

        # Evaluation loop
        await self.evaluation_loop.start()

        # Exit cycle loop
        self._exit_cycle_running = True
        self._exit_cycle_task = asyncio.create_task(
            self._run_exit_cycle_loop(),
            name="exit_cycle_loop",
        )

        log_event(
            logger, logging.INFO,
            "Orchestrator all loops started (including exit cycle)",
            entity_type="orchestrator",
            entity_id="started",
        )

    async def stop(self) -> None:
        """Graceful shutdown — loop'lari durdur + state flush.

        SIGTERM, kontrollu kapanis, normal stop — hepsinde calisir.
        """
        log_event(
            logger, logging.INFO,
            "Orchestrator stopping — graceful shutdown",
            entity_type="orchestrator",
            entity_id="stop",
        )

        # Exit cycle durdur
        self._exit_cycle_running = False
        if self._exit_cycle_task and not self._exit_cycle_task.done():
            self._exit_cycle_task.cancel()
            try:
                await self._exit_cycle_task
            except asyncio.CancelledError:
                pass

        await self.evaluation_loop.stop()
        await self.coin_client.stop()
        await self.discovery_loop.stop()
        await self.rtds_client.disconnect()

        # Final state flush — tum acik pozisyon ve pending claim kaydet
        await self._flush_state()

        log_event(
            logger, logging.INFO,
            "Orchestrator stopped — state flushed",
            entity_type="orchestrator",
            entity_id="stopped",
        )

    async def _flush_state(self) -> None:
        """Final state flush — tum memory state'i SQLite'a yaz."""
        flushed_pos = 0
        flushed_claims = 0

        for pos in self.position_tracker.get_all_positions():
            if await self.position_store.save(pos):
                flushed_pos += 1

        for claim in self.claim_manager.get_pending_claims():
            if await self.claim_store.save(claim):
                flushed_claims += 1

        log_event(
            logger, logging.INFO,
            f"State flushed: {flushed_pos} positions, {flushed_claims} pending claims",
            entity_type="orchestrator",
            entity_id="flush",
        )

    async def _run_exit_cycle_loop(self) -> None:
        """Exit orchestrator periyodik cycle loop.

        Her exit_cycle_interval_sec'de bir run_cycle() cagrilir.
        Acik pozisyonlarin fiyatlarini pipeline'dan alir.
        """
        while self._exit_cycle_running:
            try:
                # Acik pozisyonlar icin canli fiyat ve remaining seconds topla
                prices = {}
                remaining = {}

                for pos in self.position_tracker.get_all_positions():
                    if pos.is_open:
                        # Held-side outcome fiyati pipeline'dan
                        price_data = self.pipeline.get_price(pos.asset)
                        if price_data:
                            side_key = f"{pos.side.lower()}_price"
                            price = getattr(price_data, side_key, 0.0) if hasattr(price_data, side_key) else 0.0
                            if price <= 0:
                                # Fallback: dominant price
                                price = getattr(price_data, "dominant_price", 0.0) if hasattr(price_data, "dominant_price") else 0.0
                            prices[pos.asset] = price

                        # Remaining seconds — slot bazli
                        slot_start = (int(_time.time()) // 300) * 300
                        event_end = slot_start + 300
                        remaining[pos.asset] = max(0, event_end - _time.time())

                result = await self.exit_orchestrator.run_cycle(
                    current_prices=prices,
                    remaining_seconds=remaining,
                )

                if result["triggers"] > 0 or result["closes"] > 0 or result["settlements"] > 0:
                    log_event(
                        logger, logging.INFO,
                        f"Exit cycle #{result['cycle']}: "
                        f"triggers={result['triggers']} closes={result['closes']} "
                        f"settlements={result['settlements']} reconciled={result['reconciled']}",
                        entity_type="orchestrator",
                        entity_id="exit_cycle",
                    )

            except Exception as e:
                log_event(
                    logger, logging.ERROR,
                    f"Exit cycle error: {e}",
                    entity_type="orchestrator",
                    entity_id="exit_cycle_error",
                )

            await asyncio.sleep(self._exit_cycle_interval_sec)

    def get_health(self):
        """Orchestrator sağlık durumu."""
        return self.health_aggregator.aggregate(
            discovery_loop=self.discovery_loop,
            coin_client=self.coin_client,
            rtds_client=self.rtds_client,
            ptb_fetcher=self.ptb_fetcher,
            eval_loop=self.evaluation_loop,
            cleanup=self.cleanup,
        )

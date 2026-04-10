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
from backend.persistence.settings_store_db import SettingsStoreDB
from backend.persistence.registry_store import RegistryStore
from backend.persistence.ptb_store import PTBStore
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

        # ── Persistence stores ── (settings_store_db önce, SettingsStore'a inject)
        self.position_store = PositionStore()
        self.claim_store = ClaimStore()
        self.settings_store_db = SettingsStoreDB()
        self.registry_store = RegistryStore()
        self.ptb_store = PTBStore()

        # Settings — db_store bağlı: set() çağrısında otomatik SQLite persist
        self.settings_store = SettingsStore(db_store=self.settings_store_db)

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

        # ── Trading mode ──
        self.trading_enabled: bool = True  # False = degraded mode
        self.paper_mode: bool = True       # True = paper trade, False = live trade
        self.paused: bool = False          # True = entry/order durur, monitoring devam
        self._verify_retry_task: asyncio.Task | None = None
        self._verify_retry_running: bool = False

        # ── Bot uptime (paused-aware) ──
        self._bot_start_time: float | None = None
        self._bot_paused_at: float | None = None
        self._bot_accumulated: float = 0.0

        # ── Execution layer ──
        self.position_tracker = PositionTracker(position_store=self.position_store)
        self.balance_manager = BalanceManager(
            stale_threshold_sec=cfg.market_data.balance_stale_threshold_seconds,
            passive_refresh_interval=cfg.market_data.balance_refresh_interval_seconds,
        )
        self.clob_client = ClobClientWrapper(credential_store=self.credential_store)
        # BalanceManager ↔ ClobClientWrapper bağlantısı — balance fetch fonksiyonu
        self.balance_manager.set_fetch_function(self.clob_client.get_balance)
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
            sl_enabled=sl.enabled,
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
        self.eligibility_gate = EligibilityGate(
            self.settings_store,
            credential_store=self.credential_store,
        )
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
            bot_max_positions=cfg.trading.entry_rules.bot_max.max_positions,
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
        # Pause guard — yeni entry üretimi durdurulur
        # NOT: Exit cycle (TP/SL/FS) DEVAM EDER — açık pozisyon koruması
        if self.paused:
            return

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

        7/24: restart sonrasi ayni session devam eder. Kullanici mudahale ETMEZ.

        Returns:
            Restore sonuc raporu.
        """
        result = {
            "positions_restored": 0,
            "claims_restored": 0,
            "settings_restored": 0,
            "registry_restored": 0,
            "ptb_restored": 0,
            "open_positions": 0,
            "pending_claims": 0,
            "trading_mode": "NORMAL",
            "balance_source": "none",
        }

        # 1. Settings restore
        settings_list = await self.settings_store_db.load_all()
        for s in settings_list:
            self.settings_store.set(s)
            result["settings_restored"] += 1

        # 2. Registry restore
        registry_records = await self.registry_store.load_active()
        for rec in registry_records:
            self.registry._records[rec.condition_id] = rec
            result["registry_restored"] += 1

        # 3. PTB cache restore (sadece locked)
        ptb_records = await self.ptb_store.load_locked()
        for rec in ptb_records:
            self.ptb_fetcher._records[rec.condition_id] = rec
            result["ptb_restored"] += 1

        # 4. Pozisyonlari restore
        positions = await self.position_store.load_all()
        for pos in positions:
            self.position_tracker.restore_position(pos)
            result["positions_restored"] += 1

        # 5. Claim'leri restore
        claims = await self.claim_store.load_all()
        for claim in claims:
            self.claim_manager.restore_claim(claim)
            result["claims_restored"] += 1

        result["open_positions"] = self.position_tracker.open_position_count
        result["pending_claims"] = self.claim_manager.pending_count

        # 6. Balance verify
        balance_ok = await self._verify_balance()
        if balance_ok:
            self.trading_enabled = True
            result["trading_mode"] = "NORMAL"
            result["balance_source"] = "verified"
        else:
            self.trading_enabled = False
            result["trading_mode"] = "DEGRADED"
            result["balance_source"] = "snapshot_only"
            # Degraded mode — periodic verify retry baslat
            self._start_verify_retry()

        # 7. Session bilgisi
        result["session"] = "resumed" if result["positions_restored"] > 0 else "new"

        # 8. Self-check raporu
        self._log_self_check(result)

        return result

    async def _verify_balance(self) -> bool:
        """Balance API ile dogrula. Basarisiz ise degraded mode.

        Degraded mode:
        - trading_enabled = False → yeni trade/order YOK
        - exit cycle DEVAM EDER (acik pozisyon yonetimi)
        - claim/redeem retry DEVAM EDER
        """
        try:
            balance_data = await self.clob_client.get_balance()
            if balance_data:
                self.balance_manager.update(
                    available=balance_data["available"],
                    total=balance_data.get("total", balance_data["available"]),
                )
                log_event(
                    logger, logging.INFO,
                    f"Balance verified: ${balance_data['available']:.2f}",
                    entity_type="orchestrator",
                    entity_id="balance_verify",
                )
                return True
        except Exception as e:
            log_event(
                logger, logging.WARNING,
                f"Balance verify failed: {e}",
                entity_type="orchestrator",
                entity_id="balance_verify_fail",
            )
        return False

    def _log_self_check(self, result: dict) -> None:
        """Startup self-check raporu."""
        log_event(
            logger, logging.INFO,
            f"=== STARTUP SELF-CHECK === "
            f"Session: {result.get('session', 'unknown')} | "
            f"Positions: {result['positions_restored']} ({result['open_positions']} open) | "
            f"Claims: {result['claims_restored']} ({result['pending_claims']} pending) | "
            f"Settings: {result['settings_restored']} coins | "
            f"Registry: {result['registry_restored']} events | "
            f"PTB: {result['ptb_restored']} locked | "
            f"Trading: {result['trading_mode']} | "
            f"Balance: {result['balance_source']}",
            entity_type="orchestrator",
            entity_id="self_check",
        )

    async def start(self) -> None:
        """Tum loop'lari baslat.

        Idempotent — zaten calisiyorsa duplicate task acilmaz.
        discovery/evaluation loop'lari kendi iclerinde guard var.
        Exit cycle icin burada guard eklendi.
        """
        # Idempotency: exit cycle zaten calisiyorsa skip
        if self._exit_cycle_running:
            log_event(
                logger, logging.WARNING,
                "Orchestrator start() called but already running — skipping",
                entity_type="orchestrator",
                entity_id="start_skip",
            )
            # Paused ise sadece resume et
            if self.paused:
                self.resume()
            self.trading_enabled = True
            return

        log_event(
            logger, logging.INFO,
            "Orchestrator starting all loops",
            entity_type="orchestrator",
            entity_id="start",
        )

        self.trading_enabled = True
        self.paused = False
        self._bot_start_time = _time.time()
        self._bot_paused_at = None
        self._bot_accumulated = 0.0

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
        self.trading_enabled = False
        self.paused = False
        self._bot_start_time = None
        self._bot_paused_at = None
        self._bot_accumulated = 0.0

        log_event(
            logger, logging.INFO,
            "Orchestrator stopping — graceful shutdown",
            entity_type="orchestrator",
            entity_id="stop",
        )

        # Verify retry durdur
        self._verify_retry_running = False
        if self._verify_retry_task and not self._verify_retry_task.done():
            self._verify_retry_task.cancel()
            try:
                await self._verify_retry_task
            except asyncio.CancelledError:
                pass

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

    def _start_verify_retry(self) -> None:
        """Degraded mode'da balance verify periodic retry baslat."""
        if self._verify_retry_running:
            return
        self._verify_retry_running = True
        self._verify_retry_task = asyncio.create_task(
            self._verify_retry_loop(),
            name="balance_verify_retry",
        )

    async def _verify_retry_loop(self) -> None:
        """Balance verify periodic retry — degraded -> normal gecis.

        30s araliklarla API'ye balance verify dener.
        Basarili olunca trading_enabled=True, loop durur.
        Normal balance refresh (20s) ile AYRI — karistirilmaz.
        """
        verify_interval = 30.0  # 30s — agresif degil
        attempt = 0

        while self._verify_retry_running and not self.trading_enabled:
            attempt += 1
            await asyncio.sleep(verify_interval)

            if not self._verify_retry_running:
                break

            ok = await self._verify_balance()
            if ok:
                self.trading_enabled = True
                self._verify_retry_running = False
                log_event(
                    logger, logging.INFO,
                    f"Balance verified on retry #{attempt} — DEGRADED -> NORMAL",
                    entity_type="orchestrator",
                    entity_id="verify_retry_ok",
                )
                return

            log_event(
                logger, logging.WARNING,
                f"Balance verify retry #{attempt}: STILL DEGRADED",
                entity_type="orchestrator",
                entity_id="verify_retry_fail",
            )

    async def _flush_state(self) -> None:
        """Final state flush — tum memory state'i SQLite'a yaz.

        Shutdown sirasinda yeni state URETILMEZ — sadece mevcut state yazilir.
        """
        flushed = {"positions": 0, "claims": 0, "settings": 0}

        for pos in self.position_tracker.get_all_positions():
            if await self.position_store.save(pos):
                flushed["positions"] += 1

        for claim in self.claim_manager.get_pending_claims():
            if await self.claim_store.save(claim):
                flushed["claims"] += 1

        for settings in self.settings_store.get_all():
            if await self.settings_store_db.save(settings):
                flushed["settings"] += 1

        log_event(
            logger, logging.INFO,
            f"State flushed: {flushed['positions']} positions, "
            f"{flushed['claims']} claims, {flushed['settings']} settings",
            entity_type="orchestrator",
            entity_id="flush",
        )

    async def _periodic_flush(self) -> None:
        """Periyodik state flush — positions + claims SQLite'a yazilir.

        Settings zaten her set() cagirisinda auto-persist yapiyor (SettingsStoreDB).
        Bu metot sadece positions ve claims yazarak crash kayip riskini azaltir.
        _flush_state()'ten farkli: settings ATLANIR (gereksiz), log sessiz (her 30s'de).
        """
        flushed_pos = 0
        flushed_claim = 0

        for pos in self.position_tracker.get_all_positions():
            if await self.position_store.save(pos):
                flushed_pos += 1

        for claim in self.claim_manager.get_pending_claims():
            if await self.claim_store.save(claim):
                flushed_claim += 1

        # Sadece veri varsa logla — bos flush sessiz kalir
        if flushed_pos > 0 or flushed_claim > 0:
            log_event(
                logger, logging.DEBUG,
                f"Periodic flush: {flushed_pos} positions, {flushed_claim} claims",
                entity_type="orchestrator",
                entity_id="periodic_flush",
            )

    async def _run_exit_cycle_loop(self) -> None:
        """Exit orchestrator periyodik cycle loop.

        Her exit_cycle_interval_sec'de bir run_cycle() cagrilir.
        Acik pozisyonlarin fiyatlarini pipeline'dan alir.

        Periyodik flush: her ~30 saniyede positions/claims SQLite'a yazilir.
        Crash durumunda kayip riski azaltilir — shutdown flush'a bagli kalma YOK.
        """
        # Flush interval: ~30 saniye (cycle interval'a gore hesaplanir)
        flush_every = max(1, int(30.0 / self._exit_cycle_interval_sec))
        cycle_counter = 0

        while self._exit_cycle_running:
            try:
                # Acik pozisyonlar icin canli fiyat ve remaining seconds topla
                prices = {}
                remaining = {}
                stale_assets: set[str] = set()

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

                            # Stale detection -- K5 guard
                            if price_data.is_stale:
                                stale_assets.add(pos.asset)

                        # Remaining seconds — slot bazli
                        slot_start = (int(_time.time()) // 300) * 300
                        event_end = slot_start + 300
                        remaining[pos.asset] = max(0, event_end - _time.time())

                result = await self.exit_orchestrator.run_cycle(
                    current_prices=prices,
                    remaining_seconds=remaining,
                    stale_assets=stale_assets,
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

            # Periyodik flush — crash/reset durumunda veri kaybi riski azaltilir
            cycle_counter += 1
            if cycle_counter >= flush_every:
                cycle_counter = 0
                try:
                    await self._periodic_flush()
                except Exception as e:
                    log_event(
                        logger, logging.WARNING,
                        f"Periodic flush error: {e}",
                        entity_type="orchestrator",
                        entity_id="periodic_flush_error",
                    )

            await asyncio.sleep(self._exit_cycle_interval_sec)

    def pause(self) -> None:
        """Bot'u duraklat — uptime donmuş olarak saklanır."""
        if self.paused:
            return
        self.paused = True
        if self._bot_start_time is not None:
            self._bot_accumulated += _time.time() - self._bot_start_time
            self._bot_paused_at = _time.time()

    def resume(self) -> None:
        """Bot'u devam ettir — uptime kaldığı yerden devam."""
        if not self.paused:
            return
        self.paused = False
        self._bot_start_time = _time.time()
        self._bot_paused_at = None

    @property
    def bot_uptime_sec(self) -> int:
        """Bot uptime — paused iken donmuş, stopped iken 0."""
        if self._bot_start_time is None:
            return 0
        if self.paused and self._bot_paused_at is not None:
            return int(self._bot_accumulated)
        return int(self._bot_accumulated + (_time.time() - self._bot_start_time))

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

    # ══════════════════════════════════════════════════════════════
    # SNAPSHOT PROVIDERS — dashboard API tarafından çağrılır
    # ══════════════════════════════════════════════════════════════

    _SLOT_SECONDS = 300
    _EVENT_URL_TEMPLATE = "https://polymarket.com/event/{slug}"

    def build_search_snapshot(self) -> list[dict]:
        """Search tile verileri — EvaluationLoop cache'inden okunur.

        Evaluation TEK YERDE yapılır (EvaluationLoop._evaluate_single).
        Bu metot sadece cache okuyup UI contract'a çevirir (presenter/adapter).
        Kendi evaluation YAPMAZ.
        """
        from backend.market_data.coin_price_client import CoinPriceStatus

        cached = self.evaluation_loop.get_last_results()
        eligible = self.settings_store.get_eligible_coins()
        tiles = []

        for cs in eligible:
            asset = cs.coin
            eval_result = cached.get(asset)
            if eval_result is None:
                continue  # henüz evaluate edilmemiş — gösterme

            # Gösterim verileri — pipeline'dan direkt (evaluation DEĞİL)
            price_rec = self.pipeline.get_record_by_asset(asset)
            condition_id = price_rec.condition_id if price_rec else ""

            coin_rec = self.coin_client.get_price(asset)
            coin_usd = coin_rec.usd_price if coin_rec else 0.0

            ptb_rec = self.ptb_fetcher.get_record(condition_id) if condition_id else None
            ptb_value = ptb_rec.ptb_value if ptb_rec and ptb_rec.is_locked else 0.0

            # Rule sonuçları — cache'ten (tek otorite)
            rules = []
            for rr in eval_result.rule_results:
                rules.append({
                    "label": rr.rule_name,
                    "live_value": str(rr.detail.get("live_value", "—")),
                    "threshold_text": str(rr.detail.get("threshold_text", "")),
                    "state": rr.state.value,
                })

            # Event URL
            reg = self.registry.get_by_condition_id(condition_id) if condition_id else None
            slug = reg.slug if reg else ""
            event_url = self._EVENT_URL_TEMPLATE.format(slug=slug) if slug else ""

            # Pass count (cache'ten — tek otorite)
            total_enabled = eval_result.pass_count + eval_result.fail_count + eval_result.waiting_count
            pnl_big = f"{eval_result.pass_count}/{total_enabled}" if total_enabled > 0 else "0/0"

            # Gösterim format
            ptb_fmt = f"{ptb_value:,.2f}" if ptb_value > 0 else "—"
            live_fmt = f"{coin_usd:,.2f}" if coin_usd > 0 else "—"
            delta_val = abs(coin_usd - ptb_value) if ptb_value > 0 and coin_usd > 0 else 0
            delta_fmt = f"${delta_val:,.0f}" if delta_val > 0 else "—"

            # Tone (cache'ten — tek otorite)
            if eval_result.pass_count >= total_enabled and total_enabled > 0:
                tone = "profit"
            elif eval_result.fail_count > 0:
                tone = "loss"
            elif eval_result.waiting_count > 0:
                tone = "pending"
            else:
                tone = "neutral"

            signal_ready = eval_result.decision.value == "entry"

            tiles.append({
                "tile_id": f"search-{asset.lower()}",
                "coin": asset,
                "event_url": event_url,
                "pnl_big": pnl_big,
                "pnl_amount": "HAZIR" if signal_ready else "BEKLE",
                "pnl_tone": tone,
                "ptb": ptb_fmt,
                "live": live_fmt,
                "delta": delta_fmt,
                "rules": rules,
                "signal_ready": signal_ready,
                "type": "ok" if signal_ready else "wait",
            })

        return tiles

    def build_idle_snapshot(self) -> list[dict]:
        """Idle tile verileri — pasif / ayarsız / hatalı coinler.

        Evaluation YAPMAZ — sadece runtime state + settings'ten besler.
        Credential yoksa coin bazlı kartlar üretilmez, tek global kart döner.
        idle_kind öncelik sırası: credential → bot_stopped → waiting_rules → error → no_events
        """
        # Credential gate — yoksa tek global kart, coin bazlı kartlar üretilmez
        if self.credential_store and not self.credential_store.credentials.has_trading_credentials():
            return [{
                "tile_id": "idle-global-credential",
                "coin": None,
                "idle_kind": "error",
                "msg": "İşleme başlamak için credential bilgilerinizi girin",
                "activity": None,
                "rules": None,
                "event_url": None,
            }]

        tiles = []
        all_settings = self.settings_store.get_all()
        # Cache'te olan coinler search'te — idle'da gösterme
        cached_assets = set(self.evaluation_loop.get_last_results().keys())

        for cs in all_settings:
            asset = cs.coin
            idle_kind = None
            msg = ""

            # 1. Bot stopped / paused → tüm coinler idle
            if not self.trading_enabled or self.paused:
                idle_kind = "bot_stopped"
                msg = "Bot çalışmıyor — işlem aranmıyor"

            # 2. Ayar eksik (enabled ama configured değil)
            elif cs.coin_enabled and not cs.is_configured:
                idle_kind = "waiting_rules"
                msg = "Ayarlar tamamlanmadan coinde işlem açılamaz"

            # 3. Coin disabled (kullanıcı kapattı)
            elif not cs.coin_enabled:
                idle_kind = "bot_stopped"
                msg = "Ayarlar yapıldı ama pasif durumda"

            # 4. Eligible + cache'te → search'te gösteriliyor, idle'da DEĞİL
            elif asset in cached_assets:
                # Error check — stale fiyat varsa idle'a düşür
                price_rec = self.pipeline.get_record_by_asset(asset)
                if price_rec and price_rec.is_stale:
                    idle_kind = "error"
                    msg = "Fiyat verisi güncel değil — stale data"
                else:
                    continue  # search'te, idle'da gösterme

            # 5. Eligible ama cache'te değil → henüz evaluate edilmemiş
            elif cs.is_trade_eligible:
                idle_kind = "no_events"
                msg = "Uygun event bekleniyor — discovery tarama devam"

            if idle_kind is None:
                continue

            # Event URL
            reg_records = self.registry.get_all()
            slug = ""
            for r in reg_records:
                if r.asset.upper() == asset.upper():
                    slug = r.slug
                    break
            event_url = self._EVENT_URL_TEMPLATE.format(slug=slug) if slug else None

            tiles.append({
                "tile_id": f"idle-{asset.lower()}",
                "coin": asset,
                "idle_kind": idle_kind,
                "msg": msg,
                "activity": None,
                "rules": None,
                "event_url": event_url,
            })

        return tiles

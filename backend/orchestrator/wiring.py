"""Orchestrator Wiring — tüm component'ları oluşturup birbirine bağlar.

Bu modül tüm dependency'leri oluşturur ve orchestrator zincirini kurar:
Discovery → EligibilityGate → SubscriptionManager → EvaluationLoop

main.py lifespan'dan çağrılır.
Execution / order / position / claim scope'u YOKTUR.
"""

import logging

from backend.auth_clients.public_client import PublicMarketClient
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
from backend.orchestrator.discovery_loop import DiscoveryLoop
from backend.orchestrator.eligibility_gate import EligibilityGate
from backend.orchestrator.subscription_manager import SubscriptionManager
from backend.orchestrator.evaluation_loop import EvaluationLoop
from backend.orchestrator.cleanup import EventCleanup
from backend.orchestrator.health import HealthAggregator
from backend.logging_config.service import get_logger, log_event

logger = get_logger("orchestrator.wiring")


class Orchestrator:
    """Tüm component'ları barındıran ve lifecycle yöneten merkezi orchestrator.

    Zincir:
    Discovery → EligibilityGate → SubscriptionManager → EvaluationLoop

    Order gönderme YOK — sadece sinyal üretimi.
    """

    def __init__(self):
        # Data layer
        self.pipeline = LivePricePipeline()
        self.rtds_client = RTDSClient()
        self.bridge = WSPriceBridge(self.pipeline)
        self.coin_client = CoinPriceClient()

        # PTB
        self.ssr_adapter = SSRPTBAdapter()
        self.ptb_fetcher = PTBFetcher(source=self.ssr_adapter)

        # Registry
        self.registry = EventRegistry()
        self.safe_sync = SafeSync(self.registry)

        # Settings
        self.settings_store = SettingsStore()

        # Strategy
        self.rule_engine = RuleEngine()

        # Discovery
        self.public_client = PublicMarketClient()
        self.discovery_engine = DiscoveryEngine(self.public_client)

        # Orchestrator components
        self.eligibility_gate = EligibilityGate(self.settings_store)
        self.subscription_manager = SubscriptionManager(
            self.bridge, self.coin_client, self.ptb_fetcher,
        )
        self.cleanup = EventCleanup(
            self.pipeline, self.ptb_fetcher, self.bridge,
        )
        self.health_aggregator = HealthAggregator()

        # Loops
        self.discovery_loop = DiscoveryLoop(
            self.discovery_engine, self.safe_sync,
        )
        self.evaluation_loop = EvaluationLoop(
            self.rule_engine, self.pipeline, self.coin_client,
            self.ptb_fetcher, self.settings_store,
        )

        # WS message callback
        self.rtds_client.set_message_callback(self.bridge.on_ws_message)

    async def start(self) -> None:
        """Tüm loop'ları başlat."""
        log_event(
            logger, logging.INFO,
            "Orchestrator starting all loops",
            entity_type="orchestrator",
            entity_id="start",
        )

        # Coin price batch loop
        await self.coin_client.start()

        # Discovery loop
        await self.discovery_loop.start()

        # Evaluation loop
        await self.evaluation_loop.start()

        log_event(
            logger, logging.INFO,
            "Orchestrator all loops started",
            entity_type="orchestrator",
            entity_id="started",
        )

    async def stop(self) -> None:
        """Tüm loop'ları durdur — graceful shutdown."""
        log_event(
            logger, logging.INFO,
            "Orchestrator stopping all loops",
            entity_type="orchestrator",
            entity_id="stop",
        )

        await self.evaluation_loop.stop()
        await self.coin_client.stop()
        await self.discovery_loop.stop()
        await self.rtds_client.disconnect()

        log_event(
            logger, logging.INFO,
            "Orchestrator all loops stopped",
            entity_type="orchestrator",
            entity_id="stopped",
        )

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

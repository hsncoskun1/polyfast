"""Orchestrator health aggregation — tüm alt sistemlerden sağlık durumu toplar.

Beslendiği kaynaklar:
- DiscoveryLoop: son scan zamanı, retry count, health incidents
- CoinPriceClient: fresh/stale count, health incidents
- RTDSClient: connection state, health incidents
- PTBFetcher: locked/failed/pending count, health incidents
- EvaluationLoop: eval count, entry signal count
- EventCleanup: cleaned count
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.startup_guard import HealthIncident
from backend.logging_config.service import get_logger

logger = get_logger("orchestrator.health")


@dataclass(frozen=True)
class OrchestratorHealth:
    """Orchestrator seviyesinde sağlık özeti."""
    # Discovery
    discovery_running: bool = False
    discovery_scan_count: int = 0
    discovery_events_found: int = 0

    # Coin USD feed
    coin_usd_fresh_count: int = 0
    coin_usd_stale_count: int = 0
    coin_usd_total_updates: int = 0

    # Outcome WS
    outcome_ws_connected: bool = False
    outcome_ws_state: str = "disconnected"

    # PTB
    ptb_locked_count: int = 0
    ptb_failed_count: int = 0
    ptb_pending_count: int = 0

    # Evaluation
    eval_count: int = 0
    entry_signal_count: int = 0

    # Cleanup
    events_cleaned: int = 0

    # Incidents
    incidents: tuple[HealthIncident, ...] = ()

    @property
    def total_incidents(self) -> int:
        return len(self.incidents)

    @property
    def is_healthy(self) -> bool:
        """Temel sağlık kontrolü."""
        return (
            self.discovery_running
            and self.coin_usd_stale_count == 0
        )


class HealthAggregator:
    """Tüm alt sistemlerden sağlık durumu toplar."""

    def aggregate(
        self,
        discovery_loop=None,
        coin_client=None,
        rtds_client=None,
        ptb_fetcher=None,
        eval_loop=None,
        cleanup=None,
    ) -> OrchestratorHealth:
        """Tüm kaynaklardan tek sağlık snapshot'ı üret."""
        incidents = []

        # Discovery
        disc_running = False
        disc_scans = 0
        disc_found = 0
        if discovery_loop:
            disc_running = discovery_loop.is_running
            disc_scans = discovery_loop.scan_count
            disc_found = discovery_loop.events_found
            incidents.extend(discovery_loop.get_health_incidents())

        # Coin USD
        coin_fresh = 0
        coin_stale = 0
        coin_updates = 0
        if coin_client:
            coin_fresh = coin_client.fresh_count
            coin_stale = coin_client.stale_count
            coin_updates = coin_client.total_updates
            incidents.extend(coin_client.get_health_incidents())

        # Outcome WS
        ws_connected = False
        ws_state = "disconnected"
        if rtds_client:
            status = rtds_client.get_status()
            ws_connected = rtds_client.is_connected
            ws_state = status.state.value
            incidents.extend(status.health_incidents)

        # PTB
        ptb_locked = 0
        ptb_failed = 0
        ptb_pending = 0
        if ptb_fetcher:
            ptb_locked = ptb_fetcher.locked_count
            ptb_failed = ptb_fetcher.failed_count
            ptb_pending = ptb_fetcher.pending_count
            incidents.extend(ptb_fetcher.get_health_incidents())

        # Evaluation
        evals = 0
        entries = 0
        if eval_loop:
            evals = eval_loop.eval_count
            entries = eval_loop.entry_signal_count

        # Cleanup
        cleaned = 0
        if cleanup:
            cleaned = cleanup.total_cleaned

        return OrchestratorHealth(
            discovery_running=disc_running,
            discovery_scan_count=disc_scans,
            discovery_events_found=disc_found,
            coin_usd_fresh_count=coin_fresh,
            coin_usd_stale_count=coin_stale,
            coin_usd_total_updates=coin_updates,
            outcome_ws_connected=ws_connected,
            outcome_ws_state=ws_state,
            ptb_locked_count=ptb_locked,
            ptb_failed_count=ptb_failed,
            ptb_pending_count=ptb_pending,
            eval_count=evals,
            entry_signal_count=entries,
            events_cleaned=cleaned,
            incidents=tuple(incidents),
        )

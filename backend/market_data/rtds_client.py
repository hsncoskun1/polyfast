"""RTDSClient — Polymarket RTDS WebSocket connection foundation.

This is the connection/transport layer for Polymarket real-time data.
v0.3.0 scope: connect, disconnect, reconnect, connection state, health.

Does NOT:
- Parse or normalize market data (→ v0.3.3)
- Map events to tokens/markets (→ v0.3.1)
- Fetch PTB (→ v0.3.2)
- Produce backend snapshots (→ v0.3.5)
- Evaluate rules (→ v0.4.x)

Connection source: Polymarket RTDS WebSocket
This is the authoritative live data source per CLAUDE.md.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

import websockets

from backend.domain.startup_guard import HealthIncident, HealthSeverity
from backend.logging_config.service import get_logger, log_event

logger = get_logger("rtds_client")


class ConnectionState(str, Enum):
    """WebSocket connection state."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


@dataclass
class ConnectionStatus:
    """Current connection status snapshot."""
    state: ConnectionState
    last_connected_at: datetime | None = None
    last_disconnected_at: datetime | None = None
    reconnect_attempts: int = 0
    health_incidents: list[HealthIncident] = field(default_factory=list)


class RTDSClient:
    """Polymarket RTDS WebSocket connection manager.

    Manages connect/disconnect/reconnect lifecycle.
    Does NOT process market data — only manages the transport layer.

    Connection health is surfaced via HealthIncident when failures occur.
    Silent bypass is prohibited per external connectivity failure policy.
    """

    RTDS_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

    def __init__(
        self,
        ws_url: str | None = None,
        reconnect_max: int = 5,
        reconnect_backoff_base: float = 2.0,
    ):
        self._ws_url = ws_url or self.RTDS_WS_URL
        self._reconnect_max = reconnect_max
        self._reconnect_backoff_base = reconnect_backoff_base

        self._state = ConnectionState.DISCONNECTED
        self._ws = None
        self._last_connected_at: datetime | None = None
        self._last_disconnected_at: datetime | None = None
        self._reconnect_attempts = 0
        self._health_incidents: list[HealthIncident] = []

    @property
    def state(self) -> ConnectionState:
        """Current connection state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._state == ConnectionState.CONNECTED

    def get_status(self) -> ConnectionStatus:
        """Get current connection status snapshot."""
        return ConnectionStatus(
            state=self._state,
            last_connected_at=self._last_connected_at,
            last_disconnected_at=self._last_disconnected_at,
            reconnect_attempts=self._reconnect_attempts,
            health_incidents=list(self._health_incidents),
        )

    async def connect(self) -> bool:
        """Attempt to connect to RTDS WebSocket.

        Returns:
            True if connected successfully, False otherwise.
        """
        self._state = ConnectionState.CONNECTING
        log_event(
            logger, logging.INFO,
            f"Connecting to RTDS: {self._ws_url}",
            entity_type="rtds",
            entity_id="connect",
        )

        try:
            self._ws = await websockets.connect(self._ws_url)
            self._state = ConnectionState.CONNECTED
            self._last_connected_at = datetime.now(timezone.utc)
            self._reconnect_attempts = 0

            log_event(
                logger, logging.INFO,
                "RTDS WebSocket connected successfully",
                entity_type="rtds",
                entity_id="connected",
            )
            return True

        except Exception as e:
            self._state = ConnectionState.FAILED
            self._last_disconnected_at = datetime.now(timezone.utc)

            incident = HealthIncident(
                severity=HealthSeverity.WARNING,
                category="market_data",
                message=f"RTDS WebSocket connection failed: {e}",
                suggested_action="Check network connectivity and RTDS endpoint availability.",
            )
            self._health_incidents.append(incident)

            log_event(
                logger, logging.WARNING,
                f"RTDS WebSocket connection failed: {e}",
                entity_type="rtds",
                entity_id="connect_failure",
            )
            return False

    async def disconnect(self) -> None:
        """Disconnect from RTDS WebSocket."""
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        self._state = ConnectionState.DISCONNECTED
        self._last_disconnected_at = datetime.now(timezone.utc)

        log_event(
            logger, logging.INFO,
            "RTDS WebSocket disconnected",
            entity_type="rtds",
            entity_id="disconnected",
        )

    async def reconnect(self) -> bool:
        """Attempt to reconnect with exponential backoff.

        Returns:
            True if reconnected successfully, False if max attempts exceeded.
        """
        self._state = ConnectionState.RECONNECTING

        for attempt in range(1, self._reconnect_max + 1):
            self._reconnect_attempts = attempt
            wait = self._reconnect_backoff_base ** attempt

            log_event(
                logger, logging.INFO,
                f"RTDS reconnect attempt {attempt}/{self._reconnect_max} in {wait}s",
                entity_type="rtds",
                entity_id="reconnecting",
                payload={"attempt": attempt, "wait_seconds": wait},
            )

            await asyncio.sleep(wait)

            try:
                import websockets
                self._ws = await websockets.connect(self._ws_url)
                self._state = ConnectionState.CONNECTED
                self._last_connected_at = datetime.now(timezone.utc)

                log_event(
                    logger, logging.INFO,
                    f"RTDS reconnected after {attempt} attempt(s)",
                    entity_type="rtds",
                    entity_id="reconnected",
                )
                return True

            except Exception as e:
                log_event(
                    logger, logging.WARNING,
                    f"RTDS reconnect attempt {attempt} failed: {e}",
                    entity_type="rtds",
                    entity_id="reconnect_failure",
                )

        # All attempts exhausted
        self._state = ConnectionState.FAILED

        incident = HealthIncident(
            severity=HealthSeverity.WARNING,
            category="market_data",
            message=f"RTDS reconnect failed after {self._reconnect_max} attempts",
            suggested_action="Check RTDS endpoint and network. Manual intervention may be needed.",
        )
        self._health_incidents.append(incident)

        log_event(
            logger, logging.ERROR,
            f"RTDS reconnect exhausted after {self._reconnect_max} attempts",
            entity_type="rtds",
            entity_id="reconnect_exhausted",
        )
        return False

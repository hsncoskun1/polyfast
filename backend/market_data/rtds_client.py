"""RTDSClient — Polymarket RTDS WebSocket connection + message pipeline.

v0.3.0: connect, disconnect, reconnect, connection state, health.
v0.3.4: subscribe, receive loop, auto-reconnect loop, auto-resubscribe,
         message callback for pipeline integration.

Connection source: Polymarket RTDS WebSocket
This is the authoritative live data source per CLAUDE.md.

Does NOT:
- Normalize prices (→ LivePricePipeline)
- Map events to tokens (→ MarketMapper)
- Fetch PTB (→ PTBFetcher)
- Produce backend snapshots (→ v0.3.5)
- Evaluate rules (→ v0.4.x)
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine

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
    total_messages_received: int = 0
    subscribed_token_count: int = 0
    health_incidents: list[HealthIncident] = field(default_factory=list)


# Type alias for message callback: receives parsed JSON dict
MessageCallback = Callable[[dict[str, Any]], Coroutine[Any, Any, None] | None]


class RTDSClient:
    """Polymarket RTDS WebSocket connection + message manager.

    Manages connect/disconnect/reconnect lifecycle AND message flow.
    Parses raw WS messages and forwards to registered callback.

    Auto-reconnect: When connection drops, automatically reconnects
    with exponential backoff and re-subscribes to all tracked tokens.

    Connection health is surfaced via HealthIncident when failures occur.
    Silent bypass is prohibited per external connectivity failure policy.
    """

    RTDS_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

    def __init__(
        self,
        ws_url: str | None = None,
        reconnect_backoff_base: float = 2.0,
        reconnect_backoff_max: float = 30.0,
        on_message: MessageCallback | None = None,
    ):
        self._ws_url = ws_url or self.RTDS_WS_URL
        self._reconnect_backoff_base = reconnect_backoff_base
        self._reconnect_backoff_max = reconnect_backoff_max
        self._on_message = on_message

        self._state = ConnectionState.DISCONNECTED
        self._ws = None
        self._last_connected_at: datetime | None = None
        self._last_disconnected_at: datetime | None = None
        self._reconnect_attempts = 0
        self._health_incidents: list[HealthIncident] = []
        self._total_messages: int = 0

        # Subscription tracking — remembers tokens for auto-resubscribe
        self._subscribed_tokens: list[str] = []

        # Background task handles
        self._receive_task: asyncio.Task | None = None
        self._auto_reconnect_running = False
        self._shutdown_event = asyncio.Event()

    # ─── Properties ───

    @property
    def state(self) -> ConnectionState:
        """Current connection state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._state == ConnectionState.CONNECTED

    @property
    def subscribed_tokens(self) -> list[str]:
        """Currently tracked token IDs (for resubscribe)."""
        return list(self._subscribed_tokens)

    @property
    def total_messages_received(self) -> int:
        return self._total_messages

    def set_message_callback(self, callback: MessageCallback) -> None:
        """Set or replace the message callback."""
        self._on_message = callback

    def get_status(self) -> ConnectionStatus:
        """Get current connection status snapshot."""
        return ConnectionStatus(
            state=self._state,
            last_connected_at=self._last_connected_at,
            last_disconnected_at=self._last_disconnected_at,
            reconnect_attempts=self._reconnect_attempts,
            total_messages_received=self._total_messages,
            subscribed_token_count=len(self._subscribed_tokens),
            health_incidents=list(self._health_incidents),
        )

    def get_health_incidents(self) -> list[HealthIncident]:
        """Get accumulated health incidents."""
        return list(self._health_incidents)

    def clear_health_incidents(self) -> None:
        """Clear resolved health incidents."""
        self._health_incidents.clear()

    # ─── Connect / Disconnect ───

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
        """Disconnect from RTDS WebSocket and stop all background tasks."""
        self._shutdown_event.set()
        self._auto_reconnect_running = False

        # Cancel receive task
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None

        # Close WS
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

    # ─── Subscribe ───

    async def subscribe(self, token_ids: list[str]) -> bool:
        """Subscribe to market data for given token IDs.

        Stores token_ids for auto-resubscribe after reconnect.

        Args:
            token_ids: List of Polymarket CLOB token IDs.

        Returns:
            True if subscribe message sent successfully, False otherwise.
        """
        if not self.is_connected or self._ws is None:
            log_event(
                logger, logging.WARNING,
                "Cannot subscribe — not connected",
                entity_type="rtds",
                entity_id="subscribe_failed",
            )
            return False

        if not token_ids:
            log_event(
                logger, logging.WARNING,
                "Empty token_ids list — nothing to subscribe",
                entity_type="rtds",
                entity_id="subscribe_empty",
            )
            return False

        # Remember for resubscribe
        self._subscribed_tokens = list(token_ids)

        subscribe_msg = {
            "assets_ids": token_ids,
            "type": "market",
            "custom_feature_enabled": True,
        }

        try:
            await self._ws.send(json.dumps(subscribe_msg))
            log_event(
                logger, logging.INFO,
                f"Subscribed to {len(token_ids)} tokens",
                entity_type="rtds",
                entity_id="subscribed",
                payload={"token_count": len(token_ids)},
            )
            return True
        except Exception as e:
            log_event(
                logger, logging.WARNING,
                f"Subscribe send failed: {e}",
                entity_type="rtds",
                entity_id="subscribe_error",
            )
            return False

    async def _resubscribe(self) -> bool:
        """Re-subscribe to previously tracked tokens after reconnect.

        Returns:
            True if resubscribed successfully, False if no tokens or failed.
        """
        if not self._subscribed_tokens:
            log_event(
                logger, logging.INFO,
                "No tokens to resubscribe",
                entity_type="rtds",
                entity_id="resubscribe_skip",
            )
            return True  # Nothing to do is success

        log_event(
            logger, logging.INFO,
            f"Resubscribing to {len(self._subscribed_tokens)} tokens after reconnect",
            entity_type="rtds",
            entity_id="resubscribing",
        )
        return await self.subscribe(self._subscribed_tokens)

    def update_subscription(self, token_ids: list[str]) -> None:
        """Update the tracked token list (takes effect on next subscribe/resubscribe).

        This does NOT send a subscribe message immediately. Use subscribe()
        to send the subscription to the WS server.
        """
        self._subscribed_tokens = list(token_ids)

    # ─── Receive Loop ───

    async def _receive_loop(self) -> None:
        """Main receive loop — reads messages, parses JSON, forwards to callback.

        Runs until disconnection or cancellation. On WS close/error,
        sets state and exits so auto-reconnect can take over.
        """
        if self._ws is None:
            return

        try:
            async for raw_message in self._ws:
                self._total_messages += 1

                # Parse JSON
                try:
                    data = json.loads(raw_message)
                except (json.JSONDecodeError, TypeError):
                    log_event(
                        logger, logging.WARNING,
                        f"Unparseable WS message (#{self._total_messages})",
                        entity_type="rtds",
                        entity_id="parse_error",
                    )
                    continue

                # Forward to callback
                if self._on_message is not None:
                    try:
                        result = self._on_message(data)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as e:
                        log_event(
                            logger, logging.ERROR,
                            f"Message callback error: {e}",
                            entity_type="rtds",
                            entity_id="callback_error",
                        )

        except websockets.exceptions.ConnectionClosed as e:
            log_event(
                logger, logging.WARNING,
                f"RTDS WebSocket connection closed: {e}",
                entity_type="rtds",
                entity_id="ws_closed",
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log_event(
                logger, logging.ERROR,
                f"RTDS receive loop unexpected error: {e}",
                entity_type="rtds",
                entity_id="receive_error",
            )
        finally:
            # Mark as disconnected so auto-reconnect kicks in
            if self._state == ConnectionState.CONNECTED:
                self._state = ConnectionState.DISCONNECTED
                self._last_disconnected_at = datetime.now(timezone.utc)

    def start_receive_loop(self) -> asyncio.Task:
        """Start the receive loop as a background task.

        Returns:
            The asyncio Task running the receive loop.
        """
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()

        self._receive_task = asyncio.create_task(self._receive_loop())
        return self._receive_task

    # ─── Auto-Reconnect ───

    async def reconnect(self, deadline: datetime | None = None) -> bool:
        """Attempt to reconnect with exponential backoff until deadline.

        Keeps trying until:
        - Successfully reconnected, OR
        - deadline is reached (e.g., event end time), OR
        - shutdown_event is set

        No fixed attempt limit — event sonuna kadar dener.

        Args:
            deadline: Stop trying after this time (UTC). None = no deadline.

        On success, auto-resubscribes to previously tracked tokens.

        Returns:
            True if reconnected successfully, False if deadline exceeded or shutdown.
        """
        self._state = ConnectionState.RECONNECTING
        attempt = 0

        while True:
            attempt += 1
            self._reconnect_attempts = attempt

            # Check deadline
            if deadline is not None and datetime.now(timezone.utc) >= deadline:
                log_event(
                    logger, logging.WARNING,
                    f"RTDS reconnect deadline reached after {attempt} attempts",
                    entity_type="rtds",
                    entity_id="reconnect_deadline",
                )
                break

            wait = min(
                self._reconnect_backoff_base ** min(attempt, 5),
                self._reconnect_backoff_max,
            )

            log_event(
                logger, logging.INFO,
                f"RTDS reconnect attempt {attempt} in {wait:.1f}s",
                entity_type="rtds",
                entity_id="reconnecting",
                payload={"attempt": attempt, "wait_seconds": wait},
            )

            await asyncio.sleep(wait)

            # Check shutdown
            if self._shutdown_event.is_set():
                return False

            # Check deadline again after sleep
            if deadline is not None and datetime.now(timezone.utc) >= deadline:
                break

            try:
                self._ws = await websockets.connect(self._ws_url)
                self._state = ConnectionState.CONNECTED
                self._last_connected_at = datetime.now(timezone.utc)

                log_event(
                    logger, logging.INFO,
                    f"RTDS reconnected after {attempt} attempt(s)",
                    entity_type="rtds",
                    entity_id="reconnected",
                )

                # Auto-resubscribe
                await self._resubscribe()

                return True

            except Exception as e:
                log_event(
                    logger, logging.WARNING,
                    f"RTDS reconnect attempt {attempt} failed: {e}",
                    entity_type="rtds",
                    entity_id="reconnect_failure",
                )

        # Deadline or max reached
        self._state = ConnectionState.FAILED

        incident = HealthIncident(
            severity=HealthSeverity.WARNING,
            category="market_data",
            message=f"RTDS reconnect failed after {attempt} attempts",
            suggested_action="Check RTDS endpoint and network. Manual intervention may be needed.",
        )
        self._health_incidents.append(incident)

        log_event(
            logger, logging.ERROR,
            f"RTDS reconnect exhausted after {attempt} attempts",
            entity_type="rtds",
            entity_id="reconnect_exhausted",
        )
        return False

    async def run_forever(self) -> None:
        """Main loop: connect → subscribe → receive → reconnect on failure.

        Runs indefinitely until disconnect() is called.
        This is the primary entry point for production use.
        """
        self._shutdown_event.clear()
        self._auto_reconnect_running = True

        while not self._shutdown_event.is_set():
            # Connect if not connected
            if not self.is_connected:
                if self._state == ConnectionState.DISCONNECTED:
                    connected = await self.connect()
                elif self._state in (ConnectionState.FAILED, ConnectionState.RECONNECTING):
                    connected = await self.reconnect()
                else:
                    connected = False

                if not connected:
                    # Wait before retry
                    try:
                        await asyncio.wait_for(
                            self._shutdown_event.wait(),
                            timeout=self._reconnect_backoff_max,
                        )
                    except asyncio.TimeoutError:
                        pass
                    continue

                # Subscribe after fresh connection
                if self._subscribed_tokens:
                    await self._resubscribe()

            # Run receive loop (blocks until disconnection)
            await self._receive_loop()

            # If we get here, connection dropped — loop will reconnect
            if not self._shutdown_event.is_set():
                log_event(
                    logger, logging.INFO,
                    "RTDS connection dropped — initiating auto-reconnect",
                    entity_type="rtds",
                    entity_id="auto_reconnect_trigger",
                )

        self._auto_reconnect_running = False

"""Tests for RTDS WebSocket client — connect, reconnect, state, health, boundaries."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta

from backend.market_data.rtds_client import (
    RTDSClient,
    ConnectionState,
    ConnectionStatus,
)
from backend.domain.startup_guard import HealthSeverity


# ===== Connection State Tests =====

class TestRTDSClientState:
    def test_initial_state_disconnected(self):
        client = RTDSClient()
        assert client.state == ConnectionState.DISCONNECTED
        assert client.is_connected is False

    def test_status_snapshot(self):
        client = RTDSClient()
        status = client.get_status()
        assert status.state == ConnectionState.DISCONNECTED
        assert status.last_connected_at is None
        assert status.reconnect_attempts == 0
        assert len(status.health_incidents) == 0


# ===== Successful Connect Tests =====

class TestRTDSConnect:
    @patch("websockets.connect", new_callable=AsyncMock)
    async def test_connect_success(self, mock_connect):
        mock_connect.return_value = MagicMock()
        client = RTDSClient(ws_url="wss://test.ws")

        result = await client.connect()

        assert result is True
        assert client.state == ConnectionState.CONNECTED
        assert client.is_connected is True
        assert client.get_status().last_connected_at is not None

    @patch("websockets.connect", new_callable=AsyncMock)
    async def test_connect_resets_reconnect_counter(self, mock_connect):
        mock_connect.return_value = MagicMock()
        client = RTDSClient(ws_url="wss://test.ws")
        client._reconnect_attempts = 3

        await client.connect()

        assert client.get_status().reconnect_attempts == 0


# ===== Failed Connect Tests =====

class TestRTDSConnectFailure:
    @patch("websockets.connect", new_callable=AsyncMock)
    async def test_connect_failure_sets_failed_state(self, mock_connect):
        mock_connect.side_effect = ConnectionError("Refused")
        client = RTDSClient(ws_url="wss://test.ws")

        result = await client.connect()

        assert result is False
        assert client.state == ConnectionState.FAILED
        assert client.is_connected is False

    @patch("websockets.connect", new_callable=AsyncMock)
    async def test_connect_failure_produces_health_incident(self, mock_connect):
        mock_connect.side_effect = ConnectionError("Refused")
        client = RTDSClient(ws_url="wss://test.ws")

        await client.connect()

        status = client.get_status()
        assert len(status.health_incidents) == 1
        assert status.health_incidents[0].severity == HealthSeverity.WARNING
        assert status.health_incidents[0].category == "market_data"
        assert "failed" in status.health_incidents[0].message.lower()
        assert status.health_incidents[0].suggested_action != ""

    @patch("websockets.connect", new_callable=AsyncMock)
    async def test_connect_failure_no_silent_bypass(self, mock_connect):
        """Failed connect must NOT silently report as connected."""
        mock_connect.side_effect = Exception("Network error")
        client = RTDSClient(ws_url="wss://test.ws")

        await client.connect()

        assert client.state != ConnectionState.CONNECTED
        assert client.is_connected is False


# ===== Disconnect Tests =====

class TestRTDSDisconnect:
    @patch("websockets.connect", new_callable=AsyncMock)
    async def test_disconnect_sets_state(self, mock_connect):
        mock_connect.return_value = MagicMock()
        client = RTDSClient(ws_url="wss://test.ws")
        await client.connect()

        await client.disconnect()

        assert client.state == ConnectionState.DISCONNECTED
        assert client.is_connected is False
        assert client.get_status().last_disconnected_at is not None

    async def test_disconnect_when_not_connected(self):
        """Disconnect on already disconnected client should not error."""
        client = RTDSClient(ws_url="wss://test.ws")
        await client.disconnect()
        assert client.state == ConnectionState.DISCONNECTED


# ===== Reconnect Tests =====

class TestRTDSReconnect:
    @patch("websockets.connect", new_callable=AsyncMock)
    @patch("backend.market_data.rtds_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_reconnect_success(self, mock_sleep, mock_connect):
        mock_connect.return_value = MagicMock()
        client = RTDSClient(ws_url="wss://test.ws", reconnect_backoff_base=0.01)
        # deadline far in future
        deadline = datetime.now(timezone.utc) + timedelta(minutes=5)
        result = await client.reconnect(deadline=deadline)

        assert result is True
        assert client.state == ConnectionState.CONNECTED

    @patch("websockets.connect", new_callable=AsyncMock)
    @patch("backend.market_data.rtds_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_reconnect_deadline_reached(self, mock_sleep, mock_connect):
        """Reconnect stops when deadline is reached."""
        mock_connect.side_effect = ConnectionError("Refused")
        client = RTDSClient(ws_url="wss://test.ws", reconnect_backoff_base=0.01)
        # deadline already passed
        deadline = datetime.now(timezone.utc) - timedelta(seconds=1)
        result = await client.reconnect(deadline=deadline)

        assert result is False
        assert client.state == ConnectionState.FAILED

    @patch("websockets.connect", new_callable=AsyncMock)
    @patch("backend.market_data.rtds_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_reconnect_deadline_produces_health_incident(self, mock_sleep, mock_connect):
        mock_connect.side_effect = ConnectionError("Refused")
        client = RTDSClient(ws_url="wss://test.ws", reconnect_backoff_base=0.01)
        deadline = datetime.now(timezone.utc) - timedelta(seconds=1)
        await client.reconnect(deadline=deadline)

        incidents = client.get_status().health_incidents
        assert len(incidents) >= 1
        assert any(i.category == "market_data" for i in incidents)

    @patch("websockets.connect", new_callable=AsyncMock)
    @patch("backend.market_data.rtds_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_reconnect_success_after_failures(self, mock_sleep, mock_connect):
        """Reconnect succeeds on 2nd attempt."""
        mock_connect.side_effect = [ConnectionError("Fail"), MagicMock()]
        client = RTDSClient(ws_url="wss://test.ws", reconnect_backoff_base=0.01)
        deadline = datetime.now(timezone.utc) + timedelta(minutes=5)
        result = await client.reconnect(deadline=deadline)

        assert result is True
        assert client.state == ConnectionState.CONNECTED


# ===== Boundary Tests =====

class TestRTDSBoundaries:
    def test_no_market_mapping_import(self):
        """RTDS client doesn't import market mapping or PTB."""
        import backend.market_data.rtds_client as mod
        import_lines = [l.strip() for l in open(mod.__file__).readlines()
                        if l.strip().startswith(("import ", "from "))]
        for line in import_lines:
            assert "ptb" not in line.lower()
            assert "market_mapping" not in line

    def test_no_strategy_import(self):
        import backend.market_data.rtds_client as mod
        import_lines = [l.strip() for l in open(mod.__file__).readlines()
                        if l.strip().startswith(("import ", "from "))]
        for line in import_lines:
            assert "strategy" not in line
            assert "execution" not in line

    def test_no_registry_import(self):
        import backend.market_data.rtds_client as mod
        import_lines = [l.strip() for l in open(mod.__file__).readlines()
                        if l.strip().startswith(("import ", "from "))]
        for line in import_lines:
            assert "registry" not in line
            assert "discovery" not in line

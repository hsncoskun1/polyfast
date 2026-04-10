"""Tests for v0.3.4 — WS → LivePricePipeline integration.

Tests cover:
- RTDSClient subscribe/resubscribe
- LivePricePipeline.update_from_ws()
- WSPriceBridge routing
- Stale handling
- Invalid WS data filtering
- Source tracking (WS vs Gamma)
- Auto-resubscribe after reconnect
"""

import asyncio
import pytest
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from backend.market_data.live_price import (
    LivePricePipeline,
    LivePriceRecord,
    PriceSource,
    PriceStatus,
)
from backend.market_data.ws_price_bridge import WSPriceBridge, TokenRoute
from backend.market_data.rtds_client import RTDSClient, ConnectionState


# ===== LivePricePipeline WS Update Tests =====

class TestUpdateFromWS:
    """Test LivePricePipeline.update_from_ws() method."""

    def test_ws_update_up_side(self):
        """WS UP side update sets up_price; DOWN stays 0 until DOWN side received."""
        pipe = LivePricePipeline()
        record = pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.55, best_ask=0.56)
        assert record.up_price == 0.55
        assert record.down_price == 0.0  # DOWN not yet received
        assert record.spread == 0.01
        assert record.status == PriceStatus.FRESH
        assert record.source == PriceSource.RTDS_WS.value

    def test_ws_update_down_side(self):
        """WS DOWN side update sets down_price; UP stays 0 until UP side received."""
        pipe = LivePricePipeline()
        record = pipe.update_from_ws("0x1", "BTC", "down", best_bid=0.45, best_ask=0.46)
        assert record.down_price == 0.45
        assert record.up_price == 0.0  # UP not yet received

    def test_ws_update_records_best_bid_ask(self):
        """WS update stores best_bid/best_ask on record."""
        pipe = LivePricePipeline()
        record = pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.55, best_ask=0.57)
        assert record.best_bid == 0.55
        assert record.best_ask == 0.57

    def test_ws_update_spread_from_bid_ask(self):
        """Spread = best_ask - best_bid from WS (not Gamma)."""
        pipe = LivePricePipeline()
        record = pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.50, best_ask=0.53)
        assert record.spread == 0.03

    def test_ws_update_is_fresh(self):
        """WS update marks record as FRESH with timestamp."""
        pipe = LivePricePipeline()
        record = pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.55, best_ask=0.56)
        assert record.is_fresh is True
        assert record.updated_at is not None
        assert record.age_seconds < 2.0

    def test_ws_update_replaces_gamma(self):
        """WS update overwrites previous Gamma data, source changes."""
        pipe = LivePricePipeline()
        # Gamma first
        pipe.update_from_gamma("0x1", "BTC", '["0.50", "0.50"]', spread=0.02)
        record = pipe.get_record("0x1")
        assert record.source == "gamma_outcome_prices"
        # WS overwrites
        pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.55, best_ask=0.56)
        record = pipe.get_record("0x1")
        assert record.source == PriceSource.RTDS_WS.value
        assert record.up_price == 0.55

    def test_ws_invalid_bid_zero(self):
        """Zero bid is invalid — CLAUDE.md rule: 0 must not reach evaluation."""
        pipe = LivePricePipeline()
        record = pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.0, best_ask=0.56)
        assert record.status == PriceStatus.INVALID

    def test_ws_invalid_ask_zero(self):
        pipe = LivePricePipeline()
        record = pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.55, best_ask=0.0)
        assert record.status == PriceStatus.INVALID

    def test_ws_invalid_bid_negative(self):
        pipe = LivePricePipeline()
        record = pipe.update_from_ws("0x1", "BTC", "up", best_bid=-0.1, best_ask=0.5)
        assert record.status == PriceStatus.INVALID

    def test_ws_invalid_bid_above_1(self):
        pipe = LivePricePipeline()
        record = pipe.update_from_ws("0x1", "BTC", "up", best_bid=1.5, best_ask=0.5)
        assert record.status == PriceStatus.INVALID

    def test_ws_invalid_does_not_overwrite_valid(self):
        """Single bad WS tick does NOT destroy existing valid data."""
        pipe = LivePricePipeline()
        pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.55, best_ask=0.56)
        assert pipe.get_record("0x1").status == PriceStatus.FRESH
        # Bad tick on existing record — stays FRESH (not overwritten)
        pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.0, best_ask=0.0)
        record = pipe.get_record("0x1")
        assert record.up_price == 0.55  # Old valid data preserved

    def test_ws_unknown_side_ignored(self):
        """Unknown side value is logged and record unchanged."""
        pipe = LivePricePipeline()
        record = pipe.update_from_ws("0x1", "BTC", "left", best_bid=0.55, best_ask=0.56)
        assert record.status == PriceStatus.WAITING  # Still waiting, not updated

    def test_ws_multiple_assets(self):
        """Multiple assets tracked independently."""
        pipe = LivePricePipeline()
        pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.55, best_ask=0.56)
        pipe.update_from_ws("0x2", "ETH", "up", best_bid=0.60, best_ask=0.61)
        assert pipe.get_record("0x1").up_price == 0.55
        assert pipe.get_record("0x2").up_price == 0.60
        assert pipe.fresh_count == 2


# ===== PriceSource Tests =====

class TestPriceSource:
    def test_source_enum_values(self):
        assert PriceSource.RTDS_WS.value == "rtds_ws"
        assert PriceSource.GAMMA_OUTCOME_PRICES.value == "gamma_outcome_prices"
        assert PriceSource.NONE.value == "none"


# ===== WSPriceBridge Tests =====

class TestWSPriceBridge:

    def test_register_token(self):
        pipe = LivePricePipeline()
        bridge = WSPriceBridge(pipe)
        bridge.register_token("tok1", "0x1", "BTC", "up")
        assert bridge.registered_count == 1
        assert "tok1" in bridge.registered_token_ids

    def test_unregister_token(self):
        pipe = LivePricePipeline()
        bridge = WSPriceBridge(pipe)
        bridge.register_token("tok1", "0x1", "BTC", "up")
        bridge.unregister_token("tok1")
        assert bridge.registered_count == 0

    def test_clear_all(self):
        pipe = LivePricePipeline()
        bridge = WSPriceBridge(pipe)
        bridge.register_token("tok1", "0x1", "BTC", "up")
        bridge.register_token("tok2", "0x1", "BTC", "down")
        bridge.clear_all()
        assert bridge.registered_count == 0

    def test_route_best_bid_ask_message(self):
        """WS best_bid_ask message routed to pipeline."""
        pipe = LivePricePipeline()
        bridge = WSPriceBridge(pipe)
        bridge.register_token("tok1", "0x1", "BTC", "up")

        msg = {
            "asset_id": "tok1",
            "event_type": "best_bid_ask",
            "best_bid": "0.55",
            "best_ask": "0.56",
        }
        bridge.on_ws_message(msg)

        record = pipe.get_record("0x1")
        assert record is not None
        assert record.up_price == 0.55
        assert record.source == PriceSource.RTDS_WS.value
        assert bridge.total_routed == 1

    def test_route_array_message(self):
        """WS array of events routed correctly."""
        pipe = LivePricePipeline()
        bridge = WSPriceBridge(pipe)
        bridge.register_token("tok1", "0x1", "BTC", "up")
        bridge.register_token("tok2", "0x2", "ETH", "up")

        msgs = [
            {"asset_id": "tok1", "best_bid": "0.55", "best_ask": "0.56"},
            {"asset_id": "tok2", "best_bid": "0.60", "best_ask": "0.61"},
        ]
        bridge.on_ws_message(msgs)

        assert pipe.get_record("0x1").up_price == 0.55
        assert pipe.get_record("0x2").up_price == 0.60
        assert bridge.total_routed == 2

    def test_unregistered_token_skipped(self):
        """Messages for unregistered tokens are skipped."""
        pipe = LivePricePipeline()
        bridge = WSPriceBridge(pipe)
        bridge.register_token("tok1", "0x1", "BTC", "up")

        msg = {"asset_id": "unknown_token", "best_bid": "0.55", "best_ask": "0.56"}
        bridge.on_ws_message(msg)

        assert pipe.get_record("0x1") is None  # No data for 0x1 (different token sent)
        assert bridge.total_skipped == 1
        assert bridge.total_routed == 0

    def test_route_price_change_message(self):
        """price_change event format (nested price_changes array) supported."""
        pipe = LivePricePipeline()
        bridge = WSPriceBridge(pipe)
        bridge.register_token("tok1", "0x1", "BTC", "up")

        # Real Polymarket format: price_change has nested price_changes array
        msg = {
            "market": "0xabc",
            "event_type": "price_change",
            "price_changes": [
                {"asset_id": "tok1", "price": "0.55", "best_bid": "0.55", "best_ask": "0.56"}
            ],
        }
        bridge.on_ws_message(msg)

        record = pipe.get_record("0x1")
        assert record.up_price == 0.55
        assert bridge.total_routed == 1

    def test_no_asset_id_ignored(self):
        """Message without asset_id is ignored silently."""
        pipe = LivePricePipeline()
        bridge = WSPriceBridge(pipe)
        bridge.register_token("tok1", "0x1", "BTC", "up")

        msg = {"event_type": "heartbeat"}
        bridge.on_ws_message(msg)
        assert bridge.total_routed == 0

    def test_both_sides_update(self):
        """UP and DOWN tokens for same event both route correctly."""
        pipe = LivePricePipeline()
        bridge = WSPriceBridge(pipe)
        bridge.register_token("tok_up", "0x1", "BTC", "up")
        bridge.register_token("tok_dn", "0x1", "BTC", "down")

        bridge.on_ws_message({"asset_id": "tok_up", "best_bid": "0.55", "best_ask": "0.56"})
        bridge.on_ws_message({"asset_id": "tok_dn", "best_bid": "0.45", "best_ask": "0.46"})

        record = pipe.get_record("0x1")
        assert record.up_price == 0.55  # Last DOWN update: up = 1 - 0.45 = 0.55
        assert record.down_price == 0.45
        assert bridge.total_routed == 2

    def test_health_no_data_received(self):
        """Health incident when token never received data."""
        pipe = LivePricePipeline()
        bridge = WSPriceBridge(pipe)
        bridge.register_token("tok1", "0x1", "BTC", "up")

        incidents = bridge.get_health_incidents()
        assert len(incidents) >= 1
        assert any("No WS data" in i.message for i in incidents)

    def test_health_stale_data(self):
        """Health incident when token data is old (>60s)."""
        pipe = LivePricePipeline()
        bridge = WSPriceBridge(pipe)
        bridge.register_token("tok1", "0x1", "BTC", "up")

        # Simulate old data
        bridge._last_message_at["tok1"] = datetime.now(timezone.utc) - timedelta(seconds=120)

        incidents = bridge.get_health_incidents()
        assert any("stale" in i.message.lower() for i in incidents)

    def test_health_clean_when_data_fresh(self):
        """No health incidents when data is fresh."""
        pipe = LivePricePipeline()
        bridge = WSPriceBridge(pipe)
        bridge.register_token("tok1", "0x1", "BTC", "up")

        # Route a message so last_message_at is set
        bridge.on_ws_message({"asset_id": "tok1", "best_bid": "0.55", "best_ask": "0.56"})

        incidents = bridge.get_health_incidents()
        assert len(incidents) == 0


# ===== RTDSClient Subscribe/Resubscribe Tests =====

class TestRTDSSubscribe:

    @pytest.mark.asyncio
    async def test_subscribe_stores_tokens(self):
        """subscribe() remembers token list for resubscribe."""
        client = RTDSClient(ws_url="ws://fake")
        # Mock WS
        mock_ws = AsyncMock()
        client._ws = mock_ws
        client._state = ConnectionState.CONNECTED

        result = await client.subscribe(["tok1", "tok2"])
        assert result is True
        assert client.subscribed_tokens == ["tok1", "tok2"]
        mock_ws.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_subscribe_not_connected_fails(self):
        """Cannot subscribe when not connected."""
        client = RTDSClient(ws_url="ws://fake")
        result = await client.subscribe(["tok1"])
        assert result is False

    @pytest.mark.asyncio
    async def test_subscribe_empty_list_fails(self):
        """Empty token list is rejected."""
        client = RTDSClient(ws_url="ws://fake")
        client._ws = AsyncMock()
        client._state = ConnectionState.CONNECTED
        result = await client.subscribe([])
        assert result is False

    @pytest.mark.asyncio
    async def test_resubscribe_sends_stored_tokens(self):
        """_resubscribe() sends previously stored tokens."""
        client = RTDSClient(ws_url="ws://fake")
        mock_ws = AsyncMock()
        client._ws = mock_ws
        client._state = ConnectionState.CONNECTED
        client._subscribed_tokens = ["tok1", "tok2", "tok3"]

        result = await client._resubscribe()
        assert result is True
        mock_ws.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_resubscribe_no_tokens_skips(self):
        """_resubscribe() with no stored tokens returns True (nothing to do)."""
        client = RTDSClient(ws_url="ws://fake")
        client._ws = AsyncMock()
        client._state = ConnectionState.CONNECTED
        result = await client._resubscribe()
        assert result is True

    @pytest.mark.asyncio
    async def test_update_subscription_updates_list(self):
        """update_subscription() updates the stored token list."""
        client = RTDSClient(ws_url="ws://fake")
        client.update_subscription(["tok1", "tok2"])
        assert client.subscribed_tokens == ["tok1", "tok2"]

    @pytest.mark.asyncio
    async def test_status_includes_subscription_count(self):
        """get_status() includes subscribed token count."""
        client = RTDSClient(ws_url="ws://fake")
        client._subscribed_tokens = ["tok1", "tok2"]
        status = client.get_status()
        assert status.subscribed_token_count == 2


# ===== RTDSClient Message Callback Tests =====

class TestRTDSMessageCallback:

    @pytest.mark.asyncio
    async def test_set_message_callback(self):
        """Message callback can be set and changed."""
        client = RTDSClient(ws_url="ws://fake")
        cb1 = MagicMock()
        cb2 = MagicMock()
        client.set_message_callback(cb1)
        assert client._on_message == cb1
        client.set_message_callback(cb2)
        assert client._on_message == cb2

    @pytest.mark.asyncio
    async def test_constructor_callback(self):
        """Callback can be set via constructor."""
        cb = MagicMock()
        client = RTDSClient(ws_url="ws://fake", on_message=cb)
        assert client._on_message == cb


# ===== RTDSClient Connection State Tests =====

class TestRTDSConnectionState:

    def test_initial_state_disconnected(self):
        client = RTDSClient(ws_url="ws://fake")
        assert client.state == ConnectionState.DISCONNECTED
        assert client.is_connected is False

    @pytest.mark.asyncio
    async def test_disconnect_clears_state(self):
        client = RTDSClient(ws_url="ws://fake")
        client._state = ConnectionState.CONNECTED
        client._ws = AsyncMock()
        await client.disconnect()
        assert client.state == ConnectionState.DISCONNECTED
        assert client.is_connected is False

    def test_status_snapshot(self):
        client = RTDSClient(ws_url="ws://fake")
        client._total_messages = 42
        status = client.get_status()
        assert status.total_messages_received == 42

    def test_health_incidents_accumulate(self):
        client = RTDSClient(ws_url="ws://fake")
        assert len(client.get_health_incidents()) == 0

    def test_clear_health_incidents(self):
        client = RTDSClient(ws_url="ws://fake")
        from backend.domain.startup_guard import HealthIncident, HealthSeverity
        client._health_incidents.append(HealthIncident(
            severity=HealthSeverity.WARNING,
            category="test",
            message="test",
            suggested_action="test",
        ))
        assert len(client.get_health_incidents()) == 1
        client.clear_health_incidents()
        assert len(client.get_health_incidents()) == 0


# ===== Stale Handling Tests =====

class TestStaleHandling:

    def test_ws_price_goes_stale_after_threshold(self):
        """WS-sourced price becomes STALE after threshold."""
        pipe = LivePricePipeline(stale_threshold_sec=1)
        pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.55, best_ask=0.56)

        # Force stale
        pipe._records["0x1"].updated_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        record = pipe.get_record("0x1")
        assert record.status == PriceStatus.STALE

    def test_gamma_fallback_after_ws_stale(self):
        """Gamma update refreshes a WS-stale record."""
        pipe = LivePricePipeline(stale_threshold_sec=1)
        # WS update
        pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.55, best_ask=0.56)
        assert pipe.get_record("0x1").source == PriceSource.RTDS_WS.value

        # Force stale
        pipe._records["0x1"].updated_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        assert pipe.get_record("0x1").status == PriceStatus.STALE

        # Gamma fallback
        pipe.update_from_gamma("0x1", "BTC", '["0.52", "0.48"]')
        record = pipe.get_record("0x1")
        assert record.status == PriceStatus.FRESH
        assert record.source == "gamma_outcome_prices"
        assert record.up_price == 0.52

    def test_ws_update_refreshes_stale(self):
        """WS reconnect → fresh data → record becomes FRESH again."""
        pipe = LivePricePipeline(stale_threshold_sec=1)
        pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.55, best_ask=0.56)
        pipe._records["0x1"].updated_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        assert pipe.get_record("0x1").status == PriceStatus.STALE

        # WS reconnects and sends new data
        pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.57, best_ask=0.58)
        record = pipe.get_record("0x1")
        assert record.status == PriceStatus.FRESH
        assert record.up_price == 0.57

    def test_health_incident_for_stale_ws(self):
        """Health incident surfaced for WS-stale records."""
        pipe = LivePricePipeline(stale_threshold_sec=1)
        pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.55, best_ask=0.56)
        pipe._records["0x1"].updated_at = datetime.now(timezone.utc) - timedelta(seconds=5)

        incidents = pipe.get_health_incidents()
        assert len(incidents) >= 1
        assert any("Stale" in i.message for i in incidents)


# ===== Boundary Tests =====

class TestWSIntegrationBoundaries:

    def test_live_price_no_strategy_coupling(self):
        import backend.market_data.live_price as mod
        lines = [l.strip() for l in open(mod.__file__).readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "strategy" not in line
            assert "execution" not in line

    def test_ws_bridge_no_strategy_coupling(self):
        import backend.market_data.ws_price_bridge as mod
        lines = [l.strip() for l in open(mod.__file__).readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "strategy" not in line
            assert "execution" not in line

    def test_rtds_client_no_pipeline_coupling(self):
        """RTDSClient is transport only — no direct pipeline import."""
        import backend.market_data.rtds_client as mod
        lines = [l.strip() for l in open(mod.__file__).readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "live_price" not in line
            assert "ws_price_bridge" not in line

    def test_ws_bridge_depends_on_pipeline(self):
        """WSPriceBridge correctly depends on LivePricePipeline."""
        import backend.market_data.ws_price_bridge as mod
        lines = [l.strip() for l in open(mod.__file__).readlines()
                 if l.strip().startswith(("import ", "from "))]
        assert any("live_price" in line for line in lines)

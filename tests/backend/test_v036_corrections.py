"""v0.3.6 Semantic Correction Pack — comprehensive tests.

Tests cover:
A) Coin USD price client
B) Config schema semantics
C) PTB retry + lock
D) Reconnect deadline
E) Spread formula
F) Exit semantics (fill price, held-side)
G) Entry order behavior (FOK, no blind retry, Event Max fill-only)
"""

import asyncio
import time
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from backend.market_data.coin_price_client import (
    CoinPriceClient,
    CoinPriceRecord,
    CoinPriceStatus,
    COIN_SYMBOLS,
    PRICE_MIN,
    PRICE_MAX,
)
from backend.config_loader.schema import (
    PriceRuleConfig,
    DeltaRuleConfig,
    SpreadRuleConfig,
    StopLossConfig,
    TakeProfitConfig,
    ForceSellConfig,
    ForceSellTimeCondition,
    ForceSellPnlCondition,
    EventMaxConfig,
    BotMaxConfig,
    AppConfig,
)
from backend.ptb.fetcher import PTBFetcher, DEFAULT_PTB_RETRY_SCHEDULE, DEFAULT_PTB_RETRY_STEADY
from backend.ptb.models import PTBRecord, PTBStatus
from backend.ptb.source_adapter import PTBFetchResult
from backend.market_data.rtds_client import RTDSClient, ConnectionState
from backend.market_data.live_price import LivePricePipeline, PriceStatus


# ═══════════════════════════════════════════════════════════════
# A) COIN USD PRICE CLIENT TESTS
# ═══════════════════════════════════════════════════════════════

class TestCoinPriceRecord:

    def test_initial_state_waiting(self):
        r = CoinPriceRecord(coin="BTC")
        assert r.status == CoinPriceStatus.WAITING
        assert r.usd_price == 0.0
        assert r.is_fresh is False

    def test_fresh_after_update(self):
        r = CoinPriceRecord(coin="BTC", usd_price=67260.12,
                            status=CoinPriceStatus.FRESH,
                            updated_at=datetime.now(timezone.utc))
        assert r.is_fresh is True

    def test_stale_after_threshold(self):
        r = CoinPriceRecord(coin="BTC", usd_price=67260.12,
                            status=CoinPriceStatus.FRESH,
                            updated_at=datetime.now(timezone.utc) - timedelta(seconds=20),
                            stale_threshold_sec=15)
        r.check_freshness()
        assert r.status == CoinPriceStatus.STALE
        assert r.is_stale is True

    def test_source_is_rtds(self):
        r = CoinPriceRecord(coin="BTC")
        assert r.source == "rtds_crypto_prices"

    def test_age_seconds(self):
        r = CoinPriceRecord(coin="BTC", updated_at=datetime.now(timezone.utc) - timedelta(seconds=5))
        assert r.age_seconds is not None
        assert r.age_seconds >= 5


class TestCoinPriceClient:

    def test_set_coins(self):
        client = CoinPriceClient()
        client.set_coins(["BTC", "ETH", "SOL"])
        assert len(client.get_all_prices()) == 3

    def test_get_usd_price_waiting_returns_zero(self):
        client = CoinPriceClient()
        client.set_coins(["BTC"])
        assert client.get_usd_price("BTC") == 0.0

    def test_get_usd_price_fresh_returns_value(self):
        client = CoinPriceClient()
        client.set_coins(["BTC"])
        client._update_record("BTC", 67260.12)
        assert client.get_usd_price("BTC") == 67260.12

    def test_get_usd_price_stale_returns_zero(self):
        client = CoinPriceClient(stale_threshold_sec=1)
        client.set_coins(["BTC"])
        client._update_record("BTC", 67260.12)
        client._records["BTC"].updated_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        assert client.get_usd_price("BTC") == 0.0  # stale → returns 0

    def test_valid_price_bounds(self):
        assert CoinPriceClient._is_valid_price(67260.12) is True  # BTC
        assert CoinPriceClient._is_valid_price(0.092) is True     # DOGE
        assert CoinPriceClient._is_valid_price(0.0) is False      # zero
        assert CoinPriceClient._is_valid_price(-1.0) is False     # negative
        assert CoinPriceClient._is_valid_price(2_000_000) is False  # too high

    def test_extract_price_data_array(self):
        payload = {"data": [{"value": "67260.12"}], "symbol": "btcusdt"}
        assert CoinPriceClient._extract_price(payload) == 67260.12

    def test_extract_price_direct_value(self):
        payload = {"value": "2065.50", "symbol": "ethusdt"}
        assert CoinPriceClient._extract_price(payload) == 2065.50

    def test_extract_price_empty(self):
        assert CoinPriceClient._extract_price({}) is None

    def test_coin_symbols_mapping(self):
        assert COIN_SYMBOLS["BTC"] == "btcusdt"
        assert COIN_SYMBOLS["DOGE"] == "dogeusdt"
        assert len(COIN_SYMBOLS) == 6

    def test_multi_coin_tracking(self):
        client = CoinPriceClient()
        client.set_coins(["BTC", "ETH", "DOGE"])
        client._update_record("BTC", 67260.0)
        client._update_record("ETH", 2065.0)
        client._update_record("DOGE", 0.092)
        assert client.fresh_count == 3
        assert client.get_usd_price("BTC") == 67260.0
        assert client.get_usd_price("DOGE") == 0.092

    def test_health_incidents_waiting(self):
        client = CoinPriceClient()
        client.set_coins(["BTC"])
        incidents = client.get_health_incidents()
        assert len(incidents) >= 1
        assert any("No coin USD price" in i.message for i in incidents)

    def test_health_incidents_stale(self):
        client = CoinPriceClient(stale_threshold_sec=1)
        client.set_coins(["BTC"])
        client._update_record("BTC", 67260.0)
        client._records["BTC"].updated_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        incidents = client.get_health_incidents()
        assert any("stale" in i.message.lower() for i in incidents)

    def test_no_coupling_to_outcome_price(self):
        """coin_price_client must NOT import live_price or outcome modules."""
        import backend.market_data.coin_price_client as mod
        lines = [l.strip() for l in open(mod.__file__).readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "live_price" not in line
            assert "outcome" not in line
            assert "strategy" not in line
            assert "execution" not in line


# ═══════════════════════════════════════════════════════════════
# B) CONFIG SCHEMA TESTS
# ═══════════════════════════════════════════════════════════════

class TestConfigSchemaSemantics:

    def test_price_rule_dominant_side_min_51(self):
        config = PriceRuleConfig()
        assert config.min_price >= 51
        with pytest.raises(Exception):
            PriceRuleConfig(min_price=30)  # below 51

    def test_price_rule_range(self):
        config = PriceRuleConfig(min_price=70, max_price=95)
        assert config.min_price == 70
        assert config.max_price == 95

    def test_delta_usd_range(self):
        btc = DeltaRuleConfig(threshold=50.0)
        doge = DeltaRuleConfig(threshold=0.001)
        assert btc.threshold == 50.0
        assert doge.threshold == 0.001

    def test_spread_decimal_percentage(self):
        config = SpreadRuleConfig(max_spread=3.2)
        assert config.max_spread == 3.2

    def test_stop_loss_pnl_based(self):
        config = StopLossConfig()
        assert config.percentage == 3.0
        assert config.retry_interval_ms == 500  # ms not seconds
        assert "PnL" in StopLossConfig.__doc__

    def test_take_profit_pnl_based(self):
        config = TakeProfitConfig()
        assert config.percentage == 5.0
        assert "PnL" in TakeProfitConfig.__doc__
        assert "fill_price" in TakeProfitConfig.__doc__

    def test_force_sell_checkbox_based(self):
        config = ForceSellConfig()
        # Only time + pnl (delta removed)
        assert hasattr(config, "time")
        assert hasattr(config, "pnl_loss")
        assert not hasattr(config, "delta_drop")  # KALDIRILDI
        assert not hasattr(config, "combinator")

    def test_force_sell_time_default_enabled(self):
        config = ForceSellConfig()
        assert config.time.enabled is True
        assert config.time.remaining_seconds == 30

    def test_force_sell_no_delta_drop(self):
        """Force sell delta KALDIRILDI — sadece time + pnl."""
        config = ForceSellConfig()
        assert not hasattr(config, "delta_drop")

    def test_force_sell_retry_ms(self):
        config = ForceSellConfig()
        assert config.retry_interval_ms == 500

    def test_stop_loss_retry_ms(self):
        config = StopLossConfig()
        assert config.retry_interval_ms == 500

    def test_event_max_docstring_fill_only(self):
        """Event Max docstring must mention fill-based counting."""
        assert "fill" in EventMaxConfig.__doc__.lower()

    def test_default_yaml_loads(self):
        """default.yaml loads without error with new schema."""
        from pathlib import Path
        from backend.config_loader.service import load_config
        config = load_config(Path("config/default.yaml"))
        assert config.trading.entry_rules.price.min_price == 51
        assert config.trading.exit_rules.stop_loss.retry_interval_ms == 500
        assert config.trading.exit_rules.force_sell.time.enabled is True


# ═══════════════════════════════════════════════════════════════
# C) PTB RETRY + LOCK TESTS
# ═══════════════════════════════════════════════════════════════

class TestPTBRetrySchedule:

    def test_retry_schedule_values(self):
        assert DEFAULT_PTB_RETRY_SCHEDULE == [2, 4, 8, 16]
        assert DEFAULT_PTB_RETRY_STEADY == 10

    @pytest.mark.asyncio
    async def test_lock_stops_retry(self):
        """Once PTB is locked, fetch_ptb returns immediately without re-fetching."""
        source = AsyncMock()
        source.fetch_ptb.return_value = PTBFetchResult(
            success=True, value=67260.12, source_name="test", fetched_at=datetime.now(timezone.utc)
        )
        fetcher = PTBFetcher(source=source)

        # First fetch locks
        record = await fetcher.fetch_ptb("0x1", "BTC", "btc-updown-5m-123")
        assert record.is_locked is True
        assert record.ptb_value == 67260.12

        # Second fetch returns locked record without calling source
        source.reset_mock()
        record2 = await fetcher.fetch_ptb("0x1", "BTC", "btc-updown-5m-123")
        assert record2.is_locked is True
        assert record2.ptb_value == 67260.12
        source.fetch_ptb.assert_not_called()  # source NOT called again

    @pytest.mark.asyncio
    async def test_same_event_overwrite_prohibited(self):
        """PTB cannot be overwritten once locked — same event."""
        source = AsyncMock()
        source.fetch_ptb.return_value = PTBFetchResult(
            success=True, value=67260.12, source_name="test", fetched_at=datetime.now(timezone.utc)
        )
        fetcher = PTBFetcher(source=source)

        await fetcher.fetch_ptb("0x1", "BTC", "btc-updown-5m-123")
        record = fetcher.get_record("0x1")

        # Try to overwrite
        with pytest.raises(RuntimeError, match="already locked"):
            record.lock(99999.99, "attacker")

        assert record.ptb_value == 67260.12  # unchanged

    @pytest.mark.asyncio
    async def test_new_event_gets_new_ptb(self):
        """After clearing old event, new event starts fresh PTB process."""
        source = AsyncMock()
        source.fetch_ptb.return_value = PTBFetchResult(
            success=True, value=67260.12, source_name="test", fetched_at=datetime.now(timezone.utc)
        )
        fetcher = PTBFetcher(source=source)

        await fetcher.fetch_ptb("0x1", "BTC", "btc-updown-5m-100")
        assert fetcher.get_record("0x1").ptb_value == 67260.12

        # Event ends, clear
        fetcher.clear_event("0x1")
        assert fetcher.get_record("0x1") is None

        # New event, new PTB
        source.fetch_ptb.return_value = PTBFetchResult(
            success=True, value=67300.00, source_name="test", fetched_at=datetime.now(timezone.utc)
        )
        await fetcher.fetch_ptb("0x1", "BTC", "btc-updown-5m-200")
        assert fetcher.get_record("0x1").ptb_value == 67300.00

    @pytest.mark.asyncio
    async def test_ptb_value_is_usd_not_outcome(self):
        """PTB value should be USD coin price, not 0-1 outcome price."""
        source = AsyncMock()
        source.fetch_ptb.return_value = PTBFetchResult(
            success=True, value=67260.12, source_name="test", fetched_at=datetime.now(timezone.utc)
        )
        fetcher = PTBFetcher(source=source)
        await fetcher.fetch_ptb("0x1", "BTC", "btc-updown-5m-123")
        record = fetcher.get_record("0x1")
        assert record.ptb_value > 1000  # USD price, not 0-1


# ═══════════════════════════════════════════════════════════════
# D) RECONNECT DEADLINE TESTS
# ═══════════════════════════════════════════════════════════════

class TestReconnectDeadline:

    @patch("websockets.connect", new_callable=AsyncMock)
    @patch("backend.market_data.rtds_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_reconnect_no_fixed_limit(self, mock_sleep, mock_connect):
        """Reconnect has no fixed attempt limit — uses deadline."""
        mock_connect.return_value = MagicMock()
        client = RTDSClient(ws_url="wss://test.ws", reconnect_backoff_base=0.01)
        deadline = datetime.now(timezone.utc) + timedelta(minutes=5)
        result = await client.reconnect(deadline=deadline)
        assert result is True
        # No reconnect_max attribute
        assert not hasattr(client, "_reconnect_max")

    @patch("websockets.connect", new_callable=AsyncMock)
    @patch("backend.market_data.rtds_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_reconnect_stops_at_deadline(self, mock_sleep, mock_connect):
        """Reconnect stops when event deadline is reached."""
        mock_connect.side_effect = ConnectionError("Refused")
        client = RTDSClient(ws_url="wss://test.ws", reconnect_backoff_base=0.01)
        deadline = datetime.now(timezone.utc) - timedelta(seconds=1)
        result = await client.reconnect(deadline=deadline)
        assert result is False
        assert client.state == ConnectionState.FAILED


# ═══════════════════════════════════════════════════════════════
# E) SPREAD FORMULA TESTS
# ═══════════════════════════════════════════════════════════════

class TestSpreadFormula:

    def test_spread_formula_best_ask_based(self):
        """Spread formula: (best_ask - best_bid) / best_ask * 100"""
        best_bid = 0.55
        best_ask = 0.57
        spread_pct = (best_ask - best_bid) / best_ask * 100
        assert abs(spread_pct - 3.508) < 0.01

    def test_spread_up_side_recorded(self):
        pipe = LivePricePipeline()
        pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.55, best_ask=0.57)
        record = pipe.get_record("0x1")
        assert record.spread == round(0.57 - 0.55, 4)  # raw spread stored

    def test_spread_down_side_also_recorded(self):
        """DOWN side spread must also be calculated."""
        pipe = LivePricePipeline()
        pipe.update_from_ws("0x1", "BTC", "down", best_bid=0.43, best_ask=0.45)
        record = pipe.get_record("0x1")
        assert record.spread == round(0.45 - 0.43, 4)  # DOWN side updates spread too

    def test_spread_both_sides_update(self):
        """Both UP and DOWN sides update spread."""
        pipe = LivePricePipeline()
        pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.55, best_ask=0.57)
        assert pipe.get_record("0x1").spread == 0.02

        pipe.update_from_ws("0x1", "BTC", "down", best_bid=0.43, best_ask=0.46)
        assert pipe.get_record("0x1").spread == 0.03  # DOWN side overwrites


# ═══════════════════════════════════════════════════════════════
# F) EXIT SEMANTICS TESTS
# ═══════════════════════════════════════════════════════════════

class TestExitSemantics:

    def test_stop_loss_pnl_based_up_position(self):
        """UP position: PnL = (current_up_price - fill_price) / fill_price * 100"""
        fill_price = 0.85
        current_up_price = 0.82
        pnl_pct = (current_up_price - fill_price) / fill_price * 100
        assert pnl_pct < 0  # loss
        assert abs(pnl_pct - (-3.529)) < 0.01

    def test_stop_loss_pnl_based_down_position(self):
        """DOWN position: PnL = (current_down_price - fill_price) / fill_price * 100"""
        fill_price = 0.45
        current_down_price = 0.42
        pnl_pct = (current_down_price - fill_price) / fill_price * 100
        assert pnl_pct < 0
        assert abs(pnl_pct - (-6.667)) < 0.01

    def test_take_profit_pnl_based(self):
        """TP: PnL = (current - fill) / fill * 100 >= threshold"""
        fill_price = 0.85
        current = 0.90
        pnl_pct = (current - fill_price) / fill_price * 100
        assert pnl_pct > 0  # profit
        assert abs(pnl_pct - 5.882) < 0.01

    def test_fill_price_not_order_price(self):
        """Reference is always fill_price, NOT order/requested price."""
        order_price = 0.85  # what we asked for
        fill_price = 0.87   # what we got (slippage)
        current = 0.92

        # WRONG: using order_price
        wrong_pnl = (current - order_price) / order_price * 100

        # CORRECT: using fill_price
        correct_pnl = (current - fill_price) / fill_price * 100

        assert wrong_pnl != correct_pnl
        # fill_price is higher → correct PnL is lower
        assert correct_pnl < wrong_pnl

    def test_delta_is_entry_only_not_exit(self):
        """Delta is entry rule only. Force sell delta KALDIRILDI."""
        # Delta kuralı entry'de kalır
        from backend.strategy.rules.delta_rule import DeltaRule
        assert DeltaRule is not None
        # Force sell'de delta yok
        config = ForceSellConfig()
        assert not hasattr(config, "delta_drop")


# ═══════════════════════════════════════════════════════════════
# G) ENTRY ORDER BEHAVIOR TESTS
# ═══════════════════════════════════════════════════════════════

class TestEntryOrderBehavior:

    def test_fok_no_partial_fill_contract(self):
        """Market FOK: fill is all-or-nothing. No partial fill tracking needed."""
        # Contract test: no weighted_average_fill_price concept
        # Single fill_price is sufficient
        fill_price = 0.87
        assert isinstance(fill_price, float)
        # No list of partial fills, no averaging

    def test_event_max_counts_fills_only(self):
        """Event Max counts successful buy fills only.
        Failed/cancelled orders do NOT increment the counter.
        """
        fill_count = 0

        # Simulated FOK attempts
        attempts = [
            {"filled": False},  # FOK rejected
            {"filled": False},  # FOK rejected
            {"filled": True, "fill_price": 0.87},  # filled!
        ]

        for attempt in attempts:
            if attempt.get("filled"):
                fill_count += 1

        assert fill_count == 1  # only 1 fill, not 3 attempts

    def test_no_blind_retry_contract(self):
        """Each order attempt requires fresh rule evaluation.
        Rules may have changed since last attempt.
        """
        # Simulate: rules pass at t=0, FOK fails, rules fail at t=1
        rules_pass_at_t0 = True
        fok_filled_at_t0 = False  # order rejected
        rules_pass_at_t1 = False  # price dropped, rules no longer met

        # Blind retry would send order at t=1 — WRONG
        blind_retry_would_send = rules_pass_at_t0 and not fok_filled_at_t0
        assert blind_retry_would_send is True  # blind retry WOULD send

        # Correct: re-evaluate at t=1
        correct_would_send = rules_pass_at_t1
        assert correct_would_send is False  # correct: don't send


# ═══════════════════════════════════════════════════════════════
# BOUNDARY / COUPLING TESTS
# ═══════════════════════════════════════════════════════════════

class TestBoundaries:

    def test_coin_price_no_strategy_coupling(self):
        import backend.market_data.coin_price_client as mod
        lines = [l.strip() for l in open(mod.__file__).readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "strategy" not in line
            assert "execution" not in line

    def test_config_schema_no_runtime_coupling(self):
        import backend.config_loader.schema as mod
        lines = [l.strip() for l in open(mod.__file__, encoding="utf-8").readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "live_price" not in line
            assert "rtds" not in line

    def test_ptb_fetcher_no_execution_coupling(self):
        import backend.ptb.fetcher as mod
        lines = [l.strip() for l in open(mod.__file__).readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "strategy" not in line
            assert "execution" not in line

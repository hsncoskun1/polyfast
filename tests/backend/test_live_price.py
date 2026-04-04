"""Tests for live price pipeline — normalization, freshness, invalid data, boundaries."""

import pytest
import time
from datetime import datetime, timezone, timedelta

from backend.market_data.live_price import (
    LivePricePipeline,
    LivePriceRecord,
    PriceStatus,
)


# ===== Normalization Tests =====

class TestPriceNormalization:
    def test_valid_outcome_prices_string(self):
        pipe = LivePricePipeline()
        record = pipe.update_from_gamma("0x1", "BTC", '["0.55", "0.45"]')
        assert record.up_price == 0.55
        assert record.down_price == 0.45
        assert record.status == PriceStatus.FRESH

    def test_valid_outcome_prices_list(self):
        pipe = LivePricePipeline()
        record = pipe.update_from_gamma("0x1", "ETH", ["0.505", "0.495"])
        assert record.up_price == 0.505
        assert record.down_price == 0.495

    def test_spread_recorded(self):
        pipe = LivePricePipeline()
        record = pipe.update_from_gamma("0x1", "BTC", '["0.55", "0.45"]', spread=0.02)
        assert record.spread == 0.02

    def test_source_is_gamma(self):
        pipe = LivePricePipeline()
        record = pipe.update_from_gamma("0x1", "BTC", '["0.55", "0.45"]')
        assert record.source == "gamma_outcome_prices"

    def test_timestamp_set(self):
        pipe = LivePricePipeline()
        record = pipe.update_from_gamma("0x1", "BTC", '["0.55", "0.45"]')
        assert record.updated_at is not None
        assert record.age_seconds is not None
        assert record.age_seconds < 2.0


# ===== Invalid Data Filtering =====

class TestInvalidDataFiltering:
    def test_empty_string_invalid(self):
        pipe = LivePricePipeline()
        record = pipe.update_from_gamma("0x1", "BTC", "")
        assert record.status == PriceStatus.INVALID

    def test_malformed_json_invalid(self):
        pipe = LivePricePipeline()
        record = pipe.update_from_gamma("0x1", "BTC", "not json")
        assert record.status == PriceStatus.INVALID

    def test_zero_prices_invalid(self):
        """Zero prices must NOT reach evaluation — CLAUDE.md rule."""
        pipe = LivePricePipeline()
        record = pipe.update_from_gamma("0x1", "BTC", '["0", "0"]')
        assert record.status == PriceStatus.INVALID
        assert record.is_valid is False

    def test_negative_prices_invalid(self):
        pipe = LivePricePipeline()
        record = pipe.update_from_gamma("0x1", "BTC", '["-0.5", "0.5"]')
        assert record.status == PriceStatus.INVALID

    def test_single_price_invalid(self):
        pipe = LivePricePipeline()
        record = pipe.update_from_gamma("0x1", "BTC", '["0.5"]')
        assert record.status == PriceStatus.INVALID

    def test_none_invalid(self):
        pipe = LivePricePipeline()
        record = pipe.update_from_gamma("0x1", "BTC", None)
        assert record.status == PriceStatus.INVALID

    def test_price_above_1_invalid(self):
        pipe = LivePricePipeline()
        record = pipe.update_from_gamma("0x1", "BTC", '["1.5", "0.5"]')
        assert record.status == PriceStatus.INVALID

    def test_invalid_does_not_silently_pass(self):
        """Invalid data must NEVER silently return as valid."""
        pipe = LivePricePipeline()
        record = pipe.update_from_gamma("0x1", "BTC", '["0", "0"]')
        assert record.is_valid is False
        assert record.status != PriceStatus.FRESH


# ===== Freshness Tests =====

class TestFreshness:
    def test_fresh_after_update(self):
        pipe = LivePricePipeline(stale_threshold_sec=30)
        record = pipe.update_from_gamma("0x1", "BTC", '["0.55", "0.45"]')
        assert record.is_fresh is True
        assert record.is_stale is False

    def test_stale_after_threshold(self):
        pipe = LivePricePipeline(stale_threshold_sec=1)
        record = pipe.update_from_gamma("0x1", "BTC", '["0.55", "0.45"]')
        # Manually set updated_at to past
        record.updated_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        record.check_freshness()
        assert record.status == PriceStatus.STALE
        assert record.is_stale is True

    def test_waiting_before_any_update(self):
        pipe = LivePricePipeline()
        record = pipe._get_or_create("0x1", "BTC")
        assert record.status == PriceStatus.WAITING
        assert record.is_fresh is False

    def test_freshness_check_on_get(self):
        pipe = LivePricePipeline(stale_threshold_sec=1)
        pipe.update_from_gamma("0x1", "BTC", '["0.55", "0.45"]')
        # Force stale
        pipe._records["0x1"].updated_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        record = pipe.get_record("0x1")
        assert record.status == PriceStatus.STALE

    def test_health_incident_for_stale(self):
        pipe = LivePricePipeline(stale_threshold_sec=1)
        pipe.update_from_gamma("0x1", "BTC", '["0.55", "0.45"]')
        pipe._records["0x1"].updated_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        incidents = pipe.get_health_incidents()
        assert len(incidents) >= 1
        assert any(i.category == "market_data" for i in incidents)

    def test_health_incident_for_invalid(self):
        pipe = LivePricePipeline()
        pipe.update_from_gamma("0x1", "BTC", "bad data")
        incidents = pipe.get_health_incidents()
        assert len(incidents) >= 1


# ===== Pipeline Management Tests =====

class TestPipelineManagement:
    def test_multiple_assets(self):
        pipe = LivePricePipeline()
        pipe.update_from_gamma("0x1", "BTC", '["0.55", "0.45"]')
        pipe.update_from_gamma("0x2", "ETH", '["0.60", "0.40"]')
        assert pipe.fresh_count == 2

    def test_update_replaces_old_price(self):
        pipe = LivePricePipeline()
        pipe.update_from_gamma("0x1", "BTC", '["0.55", "0.45"]')
        pipe.update_from_gamma("0x1", "BTC", '["0.60", "0.40"]')
        record = pipe.get_record("0x1")
        assert record.up_price == 0.60

    def test_clear_event(self):
        pipe = LivePricePipeline()
        pipe.update_from_gamma("0x1", "BTC", '["0.55", "0.45"]')
        pipe.clear_event("0x1")
        assert pipe.get_record("0x1") is None

    def test_counts(self):
        pipe = LivePricePipeline(stale_threshold_sec=1)
        pipe.update_from_gamma("0x1", "BTC", '["0.55", "0.45"]')
        pipe.update_from_gamma("0x2", "ETH", "bad")
        assert pipe.fresh_count == 1
        assert pipe.invalid_count == 1


# ===== Boundary Tests =====

class TestLivePriceBoundaries:
    def test_no_strategy_coupling(self):
        import backend.market_data.live_price as mod
        lines = [l.strip() for l in open(mod.__file__).readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "strategy" not in line
            assert "execution" not in line

    def test_no_ptb_coupling(self):
        """Live price is NOT PTB — separate modules."""
        import backend.market_data.live_price as mod
        lines = [l.strip() for l in open(mod.__file__).readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "ptb" not in line.lower()

    def test_no_ui_coupling(self):
        import backend.market_data.live_price as mod
        lines = [l.strip() for l in open(mod.__file__).readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "frontend" not in line

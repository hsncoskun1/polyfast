"""Tests for PTB fetch adapter — models, fetcher, SSR parse, lock semantics, boundaries."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from backend.ptb.models import PTBRecord, PTBStatus
from backend.ptb.source_adapter import PTBFetchResult
from backend.ptb.fetcher import PTBFetcher
from backend.ptb.ssr_adapter import SSRPTBAdapter


class FakeAdapter:
    """Fake PTB source adapter for testing."""

    def __init__(self, results: list[PTBFetchResult]):
        self._results = results
        self._call_count = 0

    @property
    def source_name(self) -> str:
        return "fake_test"

    async def fetch_ptb(self, asset: str, event_slug: str) -> PTBFetchResult:
        idx = min(self._call_count, len(self._results) - 1)
        self._call_count += 1
        return self._results[idx]

    @property
    def call_count(self) -> int:
        return self._call_count


def _ok_result(value: float = 66920.90) -> PTBFetchResult:
    return PTBFetchResult(
        success=True, value=value, source_name="fake_test",
        fetched_at=datetime.now(timezone.utc),
    )


def _fail_result(error: str = "Source unavailable") -> PTBFetchResult:
    return PTBFetchResult(
        success=False, value=None, source_name="fake_test",
        fetched_at=datetime.now(timezone.utc), error=error,
    )


# ===== PTBRecord Model Tests =====

class TestPTBRecord:
    def test_initial_state_waiting(self):
        record = PTBRecord(condition_id="0x1", asset="BTC")
        assert record.status == PTBStatus.WAITING
        assert record.is_waiting is True
        assert record.is_locked is False
        assert record.ptb_value is None

    def test_lock_sets_value_and_status(self):
        record = PTBRecord(condition_id="0x1", asset="BTC")
        record.lock(66920.90, "ssr_next_data")
        assert record.is_locked is True
        assert record.ptb_value == 66920.90
        assert record.source_name == "ssr_next_data"
        assert record.acquired_at is not None

    def test_lock_prevents_overwrite(self):
        record = PTBRecord(condition_id="0x1", asset="BTC")
        record.lock(66920.90, "ssr_next_data")
        with pytest.raises(RuntimeError, match="already locked"):
            record.lock(99999.99, "other_source")
        assert record.ptb_value == 66920.90  # unchanged

    def test_record_failure(self):
        record = PTBRecord(condition_id="0x1", asset="BTC")
        record.record_failure("Network error")
        assert record.is_failed is True
        assert record.retry_count == 1
        assert record.last_error == "Network error"

    def test_ptb_is_not_market_price(self):
        """PTB is openPrice, distinct from outcome/market prices."""
        record = PTBRecord(condition_id="0x1", asset="BTC")
        record.lock(66920.90, "ssr_next_data")
        # PTB is a fixed reference price, not a trading price
        assert record.ptb_value == 66920.90
        assert not hasattr(record, "outcome_price")
        assert not hasattr(record, "market_price")


# ===== PTBFetcher Tests =====

class TestPTBFetcher:
    async def test_successful_fetch_locks_ptb(self):
        adapter = FakeAdapter([_ok_result(66920.90)])
        fetcher = PTBFetcher(source=adapter)

        record = await fetcher.fetch_ptb("0x1", "BTC", "btc-updown-5m-123")

        assert record.is_locked is True
        assert record.ptb_value == 66920.90
        assert fetcher.locked_count == 1

    async def test_locked_ptb_not_refetched(self):
        adapter = FakeAdapter([_ok_result(66920.90), _ok_result(99999.99)])
        fetcher = PTBFetcher(source=adapter)

        await fetcher.fetch_ptb("0x1", "BTC", "btc-updown-5m-123")
        record = await fetcher.fetch_ptb("0x1", "BTC", "btc-updown-5m-123")

        assert record.ptb_value == 66920.90  # first value, NOT overwritten
        assert adapter.call_count == 1  # only called once

    async def test_failed_fetch_records_failure(self):
        adapter = FakeAdapter([_fail_result("Timeout")])
        fetcher = PTBFetcher(source=adapter)

        record = await fetcher.fetch_ptb("0x1", "BTC", "btc-updown-5m-123")

        assert record.is_locked is False
        assert record.is_failed is True
        assert "Timeout" in record.last_error
        assert fetcher.failed_count == 1

    async def test_retry_until_success(self):
        adapter = FakeAdapter([
            _fail_result("Error 1"),
            _fail_result("Error 2"),
            _ok_result(66920.90),
        ])
        fetcher = PTBFetcher(source=adapter, retry_max=5)

        # First attempt fails
        r1 = await fetcher.fetch_ptb("0x1", "BTC", "btc-updown-5m-123")
        assert r1.is_failed is True

        # Second attempt fails
        r2 = await fetcher.fetch_ptb("0x1", "BTC", "btc-updown-5m-123")
        assert r2.is_failed is True

        # Third attempt succeeds
        r3 = await fetcher.fetch_ptb("0x1", "BTC", "btc-updown-5m-123")
        assert r3.is_locked is True
        assert r3.ptb_value == 66920.90

    async def test_retry_stops_after_max(self):
        adapter = FakeAdapter([_fail_result("Error")] * 5)
        fetcher = PTBFetcher(source=adapter, retry_max=3)

        await fetcher.fetch_ptb("0x1", "BTC", "btc-updown-5m-123")
        await fetcher.fetch_ptb("0x1", "BTC", "btc-updown-5m-123")
        r3 = await fetcher.fetch_ptb("0x1", "BTC", "btc-updown-5m-123")
        r4 = await fetcher.fetch_ptb("0x1", "BTC", "btc-updown-5m-123")

        assert r3.is_failed is True
        assert r4.is_failed is True
        # 4th call should not trigger adapter — max exhausted
        assert adapter.call_count <= 3

    async def test_retry_stops_after_lock(self):
        adapter = FakeAdapter([_ok_result(66920.90)])
        fetcher = PTBFetcher(source=adapter, retry_max=5)

        await fetcher.fetch_ptb("0x1", "BTC", "btc-updown-5m-123")
        await fetcher.fetch_ptb("0x1", "BTC", "btc-updown-5m-123")

        assert adapter.call_count == 1  # only one call, lock prevents more

    async def test_clear_event_removes_record(self):
        adapter = FakeAdapter([_ok_result(66920.90)])
        fetcher = PTBFetcher(source=adapter)

        await fetcher.fetch_ptb("0x1", "BTC", "btc-updown-5m-123")
        assert fetcher.get_record("0x1") is not None

        fetcher.clear_event("0x1")
        assert fetcher.get_record("0x1") is None

    async def test_health_incidents_for_failures(self):
        adapter = FakeAdapter([_fail_result("Network down")])
        fetcher = PTBFetcher(source=adapter)

        await fetcher.fetch_ptb("0x1", "BTC", "btc-updown-5m-123")

        incidents = fetcher.get_health_incidents()
        assert len(incidents) == 1
        assert incidents[0].category == "ptb"
        assert "failed" in incidents[0].message.lower()

    async def test_no_silent_failure(self):
        """Failed PTB fetch must never silently return as if acquired."""
        adapter = FakeAdapter([_fail_result("Error")])
        fetcher = PTBFetcher(source=adapter)

        record = await fetcher.fetch_ptb("0x1", "BTC", "btc-updown-5m-123")

        assert record.is_locked is False
        assert record.ptb_value is None
        assert record.status != PTBStatus.ACQUIRED

    async def test_waiting_state_for_downstream(self):
        """PTB not yet fetched provides waiting state for downstream."""
        fetcher = PTBFetcher(source=FakeAdapter([]))
        record = fetcher.get_or_create_record("0x1", "BTC")

        assert record.is_waiting is True
        assert fetcher.pending_count == 1


# ===== Boundary Tests =====

class TestPTBBoundaries:
    def test_no_strategy_coupling(self):
        import backend.ptb.fetcher as mod
        lines = [l.strip() for l in open(mod.__file__).readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "strategy" not in line
            assert "execution" not in line

    def test_no_ui_coupling(self):
        import backend.ptb.fetcher as mod
        lines = [l.strip() for l in open(mod.__file__).readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "frontend" not in line
            assert "api/routes" not in line

    def test_no_registry_coupling(self):
        import backend.ptb.fetcher as mod
        lines = [l.strip() for l in open(mod.__file__).readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "registry" not in line


# ===== SSR Adapter Parse Tests =====

class TestSSRPTBAdapterParse:
    """Tests for SSRPTBAdapter._parse_ptb method with mock HTML."""

    def _make_adapter(self):
        return SSRPTBAdapter(timeout_seconds=5.0)

    def test_parse_price_to_beat_btc(self):
        """priceToBeat field parsed correctly for BTC."""
        adapter = self._make_adapter()
        html = 'some content "priceToBeat":"66885.87" more content'
        result = adapter._parse_ptb(html, "BTC", "btc-updown-5m-123")
        assert result.success is True
        assert result.value == 66885.87
        assert result.source_name == "ssr_price_to_beat"

    def test_parse_price_to_beat_eth(self):
        """priceToBeat works for ETH (non-BTC asset)."""
        adapter = self._make_adapter()
        html = 'data "priceToBeat":"2052.5163202565955" end'
        result = adapter._parse_ptb(html, "ETH", "eth-updown-5m-123")
        assert result.success is True
        assert abs(result.value - 2052.5163) < 0.001

    def test_parse_price_to_beat_small_value(self):
        """priceToBeat works for small values (DOGE)."""
        adapter = self._make_adapter()
        html = '"priceToBeat":"0.091137362"'
        result = adapter._parse_ptb(html, "DOGE", "doge-updown-5m-123")
        assert result.success is True
        assert abs(result.value - 0.091137) < 0.0001

    def test_parse_price_to_beat_without_quotes(self):
        """priceToBeat value without string quotes."""
        adapter = self._make_adapter()
        html = '"priceToBeat":66885.87,'
        result = adapter._parse_ptb(html, "BTC", "btc-updown-5m-123")
        assert result.success is True
        assert result.value == 66885.87

    def test_parse_fallback_to_open_price(self):
        """Falls back to openPrice if priceToBeat not found."""
        adapter = self._make_adapter()
        html = '"openPrice":66920.89960871995,"closePrice":null'
        result = adapter._parse_ptb(html, "BTC", "btc-updown-5m-123")
        assert result.success is True
        assert abs(result.value - 66920.90) < 0.01
        assert "fallback" in result.source_name

    def test_parse_no_price_field(self):
        """No price field found returns failure."""
        adapter = self._make_adapter()
        html = 'no price data here at all'
        result = adapter._parse_ptb(html, "BTC", "btc-updown-5m-123")
        assert result.success is False
        assert result.value is None
        assert "not found" in result.error.lower()

    def test_parse_empty_html(self):
        """Empty HTML returns failure."""
        adapter = self._make_adapter()
        result = adapter._parse_ptb("", "BTC", "btc-updown-5m-123")
        assert result.success is False

    def test_ptb_is_not_market_price(self):
        """priceToBeat is NOT outcomePrices/market price."""
        adapter = self._make_adapter()
        # HTML has both priceToBeat and outcomePrices
        html = '"priceToBeat":"66885.87","outcomePrices":["0.505","0.495"]'
        result = adapter._parse_ptb(html, "BTC", "btc-updown-5m-123")
        # Should return priceToBeat, NOT outcomePrices
        assert result.value == 66885.87
        assert result.value != 0.505

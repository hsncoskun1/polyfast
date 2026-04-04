"""Tests for v0.3.5 — Backend authoritative snapshot production.

GPT test requirements:
- bos state snapshot
- canli state snapshot
- stale state snapshot
- selected scope snapshot
- source alanlari dogru mu
- PTB ile live price karismiyor mu
- boundary: strategy / execution / UI logic snapshot katmanina sizmiyor mu
- mevcut testler kirilmiyor
"""

import pytest
from datetime import datetime, timezone, timedelta

from backend.market_data.live_price import LivePricePipeline, PriceSource, PriceStatus
from backend.snapshot.models import (
    BalanceSummary,
    EventSnapshot,
    HealthSummary,
    SnapshotEventStatus,
    SystemSnapshot,
)
from backend.snapshot.producer import SnapshotProducer


# ===== EventSnapshot Model Tests =====

class TestEventSnapshotModel:

    def test_frozen_immutable(self):
        """EventSnapshot is frozen — cannot be modified after creation."""
        ev = EventSnapshot(condition_id="0x1", asset="BTC", status=SnapshotEventStatus.ACTIVE)
        with pytest.raises(AttributeError):
            ev.up_price = 0.5

    def test_ptb_and_price_separate_fields(self):
        """PTB and live price are separate fields — never mixed."""
        ev = EventSnapshot(
            condition_id="0x1",
            asset="BTC",
            status=SnapshotEventStatus.ACTIVE,
            up_price=0.55,
            down_price=0.45,
            ptb_value=0.52,
        )
        # PTB and price are independent
        assert ev.up_price == 0.55
        assert ev.ptb_value == 0.52
        assert ev.up_price != ev.ptb_value

    def test_source_fields_present(self):
        """Source tracking fields exist on EventSnapshot."""
        ev = EventSnapshot(
            condition_id="0x1",
            asset="BTC",
            status=SnapshotEventStatus.ACTIVE,
            price_source=PriceSource.RTDS_WS.value,
            ptb_source="ssr_adapter",
        )
        assert ev.price_source == "rtds_ws"
        assert ev.ptb_source == "ssr_adapter"

    def test_default_values(self):
        """Default values are safe (no invalid data leaks)."""
        ev = EventSnapshot(condition_id="0x1", asset="BTC", status=SnapshotEventStatus.WAITING)
        assert ev.up_price == 0.0
        assert ev.ptb_value is None
        assert ev.price_source == PriceSource.NONE.value
        assert ev.price_status == PriceStatus.WAITING.value


# ===== SystemSnapshot Model Tests =====

class TestSystemSnapshotModel:

    def test_frozen_immutable(self):
        snap = SystemSnapshot(generated_at=datetime.now(timezone.utc))
        with pytest.raises(AttributeError):
            snap.session_id = "new"

    def test_empty_snapshot(self):
        """Empty snapshot has zero events."""
        snap = SystemSnapshot(generated_at=datetime.now(timezone.utc))
        assert snap.total_events == 0
        assert snap.active_events == 0
        assert snap.stale_events == 0
        assert snap.waiting_events == 0

    def test_event_counts(self):
        """Event counts computed correctly."""
        events = (
            EventSnapshot(condition_id="0x1", asset="BTC", status=SnapshotEventStatus.ACTIVE),
            EventSnapshot(condition_id="0x2", asset="ETH", status=SnapshotEventStatus.ACTIVE),
            EventSnapshot(condition_id="0x3", asset="SOL", status=SnapshotEventStatus.STALE),
            EventSnapshot(condition_id="0x4", asset="DOGE", status=SnapshotEventStatus.WAITING),
        )
        snap = SystemSnapshot(generated_at=datetime.now(timezone.utc), events=events)
        assert snap.total_events == 4
        assert snap.active_events == 2
        assert snap.stale_events == 1
        assert snap.waiting_events == 1

    def test_get_event_by_id(self):
        events = (
            EventSnapshot(condition_id="0x1", asset="BTC", status=SnapshotEventStatus.ACTIVE),
            EventSnapshot(condition_id="0x2", asset="ETH", status=SnapshotEventStatus.ACTIVE),
        )
        snap = SystemSnapshot(generated_at=datetime.now(timezone.utc), events=events)
        assert snap.get_event("0x1").asset == "BTC"
        assert snap.get_event("0x2").asset == "ETH"
        assert snap.get_event("0x99") is None

    def test_get_events_by_asset(self):
        events = (
            EventSnapshot(condition_id="0x1", asset="BTC", status=SnapshotEventStatus.ACTIVE),
            EventSnapshot(condition_id="0x2", asset="ETH", status=SnapshotEventStatus.ACTIVE),
        )
        snap = SystemSnapshot(generated_at=datetime.now(timezone.utc), events=events)
        btc = snap.get_events_by_asset("BTC")
        assert len(btc) == 1
        assert btc[0].condition_id == "0x1"


# ===== SnapshotProducer — Empty State =====

class TestSnapshotProducerEmpty:

    def test_empty_produce(self):
        """Produce snapshot with no data — GPT test: bos state snapshot."""
        pipe = LivePricePipeline()
        producer = SnapshotProducer(pipeline=pipe)
        snap = producer.produce()

        assert snap.total_events == 0
        assert snap.active_events == 0
        assert snap.balance.total == 0.0
        assert snap.balance.available == 0.0
        assert snap.health.ws_connected is False
        assert snap.generated_at is not None

    def test_empty_health(self):
        """Empty state health shows disconnected, no incidents."""
        pipe = LivePricePipeline()
        producer = SnapshotProducer(pipeline=pipe)
        snap = producer.produce()

        assert snap.health.ws_state == "disconnected"
        assert snap.health.stale_event_count == 0
        assert snap.health.incident_count == 0


# ===== SnapshotProducer — Live State =====

class TestSnapshotProducerLive:

    def _make_producer_with_data(self):
        """Helper: create producer with live data."""
        pipe = LivePricePipeline()
        pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.55, best_ask=0.56)
        pipe.update_from_ws("0x2", "ETH", "up", best_bid=0.48, best_ask=0.50)

        producer = SnapshotProducer(pipeline=pipe)
        producer.set_balance(total=100.0, available=95.0, fetched_at=datetime.now(timezone.utc))
        producer.set_ws_status(connected=True, state="connected", last_connected_at=datetime.now(timezone.utc))
        producer.set_session_id("session-001")

        producer.set_ptb_records({
            "0x1": {"ptb_value": 0.52, "status": "acquired", "source_name": "ssr_adapter", "acquired_at": datetime.now(timezone.utc)},
            "0x2": {"ptb_value": None, "status": "waiting", "source_name": "", "acquired_at": None},
        })

        producer.set_registry_records({
            "0x1": {"asset": "BTC", "question": "BTC up or down?", "status": "active", "end_date": datetime.now(timezone.utc) + timedelta(minutes=5)},
            "0x2": {"asset": "ETH", "question": "ETH up or down?", "status": "active", "end_date": datetime.now(timezone.utc) + timedelta(minutes=5)},
        })

        return producer

    def test_live_snapshot_events(self):
        """GPT test: canli state snapshot — events populated correctly."""
        producer = self._make_producer_with_data()
        snap = producer.produce()

        assert snap.total_events == 2
        assert snap.active_events == 2

        btc = snap.get_event("0x1")
        assert btc is not None
        assert btc.asset == "BTC"
        assert btc.up_price == 0.55
        assert btc.status == SnapshotEventStatus.ACTIVE

    def test_live_snapshot_source_tracking(self):
        """GPT test: source alanlari dogru mu."""
        producer = self._make_producer_with_data()
        snap = producer.produce()

        btc = snap.get_event("0x1")
        assert btc.price_source == PriceSource.RTDS_WS.value
        assert btc.ptb_source == "ssr_adapter"

    def test_live_snapshot_ptb_separate_from_price(self):
        """GPT test: PTB ile live price karismiyor mu."""
        producer = self._make_producer_with_data()
        snap = producer.produce()

        btc = snap.get_event("0x1")
        # PTB and live price are separate
        assert btc.ptb_value == 0.52
        assert btc.up_price == 0.55
        assert btc.ptb_value != btc.up_price

        eth = snap.get_event("0x2")
        assert eth.ptb_value is None  # Not yet acquired
        assert eth.up_price == 0.48   # But live price exists

    def test_live_snapshot_balance(self):
        """Balance in snapshot matches set values."""
        producer = self._make_producer_with_data()
        snap = producer.produce()

        assert snap.balance.total == 100.0
        assert snap.balance.available == 95.0
        assert snap.balance.fetched_at is not None

    def test_live_snapshot_ws_health(self):
        """WS health in snapshot reflects connected state."""
        producer = self._make_producer_with_data()
        snap = producer.produce()

        assert snap.health.ws_connected is True
        assert snap.health.ws_state == "connected"

    def test_live_snapshot_session_id(self):
        producer = self._make_producer_with_data()
        snap = producer.produce()
        assert snap.session_id == "session-001"


# ===== SnapshotProducer — Stale State =====

class TestSnapshotProducerStale:

    def test_stale_snapshot(self):
        """GPT test: stale state snapshot — prices stale after threshold."""
        pipe = LivePricePipeline(stale_threshold_sec=1)
        pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.55, best_ask=0.56)

        # Force stale
        pipe._records["0x1"].updated_at = datetime.now(timezone.utc) - timedelta(seconds=5)

        producer = SnapshotProducer(pipeline=pipe)
        snap = producer.produce()

        btc = snap.get_event("0x1")
        assert btc.status == SnapshotEventStatus.STALE
        assert btc.price_status == PriceStatus.STALE.value
        assert snap.stale_events == 1
        assert snap.health.stale_event_count == 1

    def test_stale_ws_disconnected(self):
        """Snapshot reflects WS disconnected state."""
        pipe = LivePricePipeline()
        producer = SnapshotProducer(pipeline=pipe)
        producer.set_ws_status(connected=False, state="disconnected")
        snap = producer.produce()

        assert snap.health.ws_connected is False
        assert snap.health.ws_state == "disconnected"


# ===== SnapshotProducer — Selected Scope =====

class TestSnapshotProducerScope:

    def test_selected_scope_only_registered_events(self):
        """GPT test: selected scope snapshot — only pipeline events appear."""
        pipe = LivePricePipeline()
        pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.55, best_ask=0.56)
        # Only BTC in pipeline, not ETH

        producer = SnapshotProducer(pipeline=pipe)
        snap = producer.produce()

        assert snap.total_events == 1
        assert snap.get_event("0x1") is not None
        assert snap.get_event("0x2") is None

    def test_registry_only_event_appears_as_waiting(self):
        """Event in registry but not in pipeline → WAITING status."""
        pipe = LivePricePipeline()
        producer = SnapshotProducer(pipeline=pipe)
        producer.set_registry_records({
            "0x99": {"asset": "DOGE", "question": "DOGE up?", "status": "active", "end_date": None},
        })
        snap = producer.produce()

        doge = snap.get_event("0x99")
        assert doge is not None
        assert doge.status == SnapshotEventStatus.WAITING
        assert doge.asset == "DOGE"

    def test_ptb_only_event_appears(self):
        """Event with PTB but no live price → shows PTB, WAITING status."""
        pipe = LivePricePipeline()
        producer = SnapshotProducer(pipeline=pipe)
        producer.set_ptb_records({
            "0x88": {"ptb_value": 0.50, "status": "acquired", "source_name": "ssr", "acquired_at": datetime.now(timezone.utc), "asset": "SOL"},
        })
        snap = producer.produce()

        sol = snap.get_event("0x88")
        assert sol is not None
        assert sol.ptb_value == 0.50
        assert sol.status == SnapshotEventStatus.WAITING


# ===== SnapshotProducer — Registry Status Overrides =====

class TestSnapshotRegistryOverrides:

    def test_expired_event_overrides_price(self):
        """Expired registry status overrides FRESH price status."""
        pipe = LivePricePipeline()
        pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.55, best_ask=0.56)

        producer = SnapshotProducer(pipeline=pipe)
        producer.set_registry_records({
            "0x1": {"asset": "BTC", "question": "BTC up?", "status": "expired", "end_date": None},
        })
        snap = producer.produce()

        btc = snap.get_event("0x1")
        assert btc.status == SnapshotEventStatus.EXPIRED
        assert btc.up_price == 0.55  # Price data still preserved

    def test_inactive_event(self):
        pipe = LivePricePipeline()
        producer = SnapshotProducer(pipeline=pipe)
        producer.set_registry_records({
            "0x1": {"asset": "BTC", "question": "BTC up?", "status": "inactive", "end_date": None},
        })
        snap = producer.produce()
        assert snap.get_event("0x1").status == SnapshotEventStatus.INACTIVE

    def test_closed_event(self):
        pipe = LivePricePipeline()
        producer = SnapshotProducer(pipeline=pipe)
        producer.set_registry_records({
            "0x1": {"asset": "BTC", "question": "BTC up?", "status": "closed", "end_date": None},
        })
        snap = producer.produce()
        assert snap.get_event("0x1").status == SnapshotEventStatus.EXPIRED


# ===== SnapshotProducer — Health Incidents =====

class TestSnapshotHealth:

    def test_health_incidents_in_snapshot(self):
        pipe = LivePricePipeline()
        producer = SnapshotProducer(pipeline=pipe)
        producer.set_health_incidents(["WS disconnected", "PTB fetch failed"])
        snap = producer.produce()

        assert snap.health.incident_count == 2
        assert "WS disconnected" in snap.health.incidents

    def test_invalid_event_count(self):
        pipe = LivePricePipeline()
        pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.0, best_ask=0.0)

        producer = SnapshotProducer(pipeline=pipe)
        snap = producer.produce()

        assert snap.health.invalid_event_count == 1


# ===== Boundary Tests =====

class TestSnapshotBoundaries:

    def test_snapshot_models_no_strategy_coupling(self):
        """Snapshot models must not import strategy/execution/UI modules."""
        import backend.snapshot.models as mod
        lines = [l.strip() for l in open(mod.__file__).readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "strategy" not in line
            assert "execution" not in line
            assert "frontend" not in line
            assert "react" not in line

    def test_snapshot_producer_no_strategy_coupling(self):
        """SnapshotProducer must not import strategy/execution/UI modules."""
        import backend.snapshot.producer as mod
        lines = [l.strip() for l in open(mod.__file__).readlines()
                 if l.strip().startswith(("import ", "from "))]
        for line in lines:
            assert "strategy" not in line
            assert "execution" not in line
            assert "frontend" not in line

    def test_snapshot_is_readonly(self):
        """SystemSnapshot and EventSnapshot are frozen — no mutation."""
        snap = SystemSnapshot(generated_at=datetime.now(timezone.utc))
        with pytest.raises(AttributeError):
            snap.session_id = "x"

        ev = EventSnapshot(condition_id="0x1", asset="BTC", status=SnapshotEventStatus.ACTIVE)
        with pytest.raises(AttributeError):
            ev.up_price = 1.0

    def test_multiple_produce_independent(self):
        """Each produce() call creates independent snapshot."""
        pipe = LivePricePipeline()
        pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.55, best_ask=0.56)

        producer = SnapshotProducer(pipeline=pipe)
        snap1 = producer.produce()

        pipe.update_from_ws("0x1", "BTC", "up", best_bid=0.60, best_ask=0.61)
        snap2 = producer.produce()

        # snap1 is frozen — not affected by snap2
        assert snap1.get_event("0x1").up_price == 0.55
        assert snap2.get_event("0x1").up_price == 0.60

    def test_snapshot_generated_at_is_current(self):
        pipe = LivePricePipeline()
        producer = SnapshotProducer(pipeline=pipe)
        before = datetime.now(timezone.utc)
        snap = producer.produce()
        after = datetime.now(timezone.utc)
        assert before <= snap.generated_at <= after

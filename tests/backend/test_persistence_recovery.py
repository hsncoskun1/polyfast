"""Persistence + Recovery tests -- v0.7.6.

Position + Claim persistence, startup restore, graceful shutdown.
7/24 mudahalesiz calisan bot icin.
"""

import pytest
import asyncio
import aiosqlite
from pathlib import Path
from datetime import datetime, timezone

from backend.persistence.position_store import PositionStore
from backend.persistence.claim_store import ClaimStore
from backend.persistence.database import init_db, close_db, get_db
from backend.execution.position_record import PositionRecord, PositionState
from backend.execution.position_tracker import PositionTracker
from backend.execution.claim_manager import ClaimManager, ClaimRecord, ClaimStatus, ClaimOutcome
from backend.execution.balance_manager import BalanceManager
from backend.execution.close_reason import CloseReason


@pytest.fixture
async def db():
    """In-memory SQLite for tests."""
    conn = await init_db(":memory:")
    # Run migration 005
    mig_dir = Path(__file__).resolve().parent.parent.parent / "backend" / "persistence" / "migrations"
    for mig_file in sorted(mig_dir.glob("*.sql")):
        sql = mig_file.read_text(encoding="utf-8")
        await conn.executescript(sql)
    await conn.commit()
    yield conn
    await close_db()


# ═══════════════════════════════════════════════════
# POSITION STORE
# ═══════════════════════════════════════════════════

class TestPositionStore:

    @pytest.mark.asyncio
    async def test_save_and_load(self, db):
        store = PositionStore()
        pos = PositionRecord(
            position_id="p1", asset="BTC", side="UP",
            condition_id="0x1", token_id="tok1",
            state=PositionState.OPEN_CONFIRMED,
            fill_price=0.85, net_position_shares=5.88,
            requested_amount_usd=5.0,
        )
        ok = await store.save(pos)
        assert ok is True

        loaded = await store.load_all()
        assert len(loaded) == 1
        assert loaded[0].position_id == "p1"
        assert loaded[0].state == PositionState.OPEN_CONFIRMED
        assert loaded[0].fill_price == 0.85

    @pytest.mark.asyncio
    async def test_load_non_terminal(self, db):
        store = PositionStore()
        # Acik pozisyon
        open_pos = PositionRecord(
            position_id="p1", asset="BTC", side="UP",
            condition_id="0x1", token_id="tok1",
            state=PositionState.OPEN_CONFIRMED,
        )
        # Kapali pozisyon
        closed_pos = PositionRecord(
            position_id="p2", asset="ETH", side="DOWN",
            condition_id="0x2", token_id="tok2",
            state=PositionState.CLOSED,
        )
        await store.save(open_pos)
        await store.save(closed_pos)

        non_terminal = await store.load_non_terminal()
        assert len(non_terminal) == 1
        assert non_terminal[0].position_id == "p1"

    @pytest.mark.asyncio
    async def test_upsert(self, db):
        store = PositionStore()
        pos = PositionRecord(
            position_id="p1", asset="BTC", side="UP",
            condition_id="0x1", token_id="tok1",
            state=PositionState.PENDING_OPEN,
        )
        await store.save(pos)

        # State degistir ve tekrar kaydet
        pos.state = PositionState.OPEN_CONFIRMED
        pos.fill_price = 0.85
        await store.save(pos)

        loaded = await store.load_all()
        assert len(loaded) == 1
        assert loaded[0].state == PositionState.OPEN_CONFIRMED
        assert loaded[0].fill_price == 0.85

    @pytest.mark.asyncio
    async def test_close_reason_persisted(self, db):
        store = PositionStore()
        pos = PositionRecord(
            position_id="p1", asset="BTC", side="UP",
            condition_id="0x1", token_id="tok1",
            state=PositionState.CLOSED,
            close_reason=CloseReason.TAKE_PROFIT,
            close_trigger_set=["force_sell_time"],
        )
        await store.save(pos)

        loaded = await store.load_all()
        assert loaded[0].close_reason == CloseReason.TAKE_PROFIT
        assert loaded[0].close_trigger_set == ["force_sell_time"]


# ═══════════════════════════════════════════════════
# CLAIM STORE
# ═══════════════════════════════════════════════════

class TestClaimStore:

    @pytest.mark.asyncio
    async def test_save_and_load(self, db):
        store = ClaimStore()
        claim = ClaimRecord(
            claim_id="c1", condition_id="0x1", position_id="p1",
            asset="BTC", side="UP",
            claim_status=ClaimStatus.PENDING,
        )
        ok = await store.save(claim)
        assert ok is True

        loaded = await store.load_all()
        assert len(loaded) == 1
        assert loaded[0].claim_id == "c1"
        assert loaded[0].claim_status == ClaimStatus.PENDING

    @pytest.mark.asyncio
    async def test_load_pending(self, db):
        store = ClaimStore()
        pending = ClaimRecord(
            claim_id="c1", condition_id="0x1", position_id="p1",
            asset="BTC", claim_status=ClaimStatus.PENDING,
        )
        success = ClaimRecord(
            claim_id="c2", condition_id="0x2", position_id="p2",
            asset="ETH", claim_status=ClaimStatus.SUCCESS,
            outcome=ClaimOutcome.REDEEMED_WON,
        )
        await store.save(pending)
        await store.save(success)

        pending_list = await store.load_pending()
        assert len(pending_list) == 1
        assert pending_list[0].claim_id == "c1"


# ═══════════════════════════════════════════════════
# TRACKER RESTORE
# ═══════════════════════════════════════════════════

class TestPositionRestore:

    def test_restore_open_position(self):
        tracker = PositionTracker()
        pos = PositionRecord(
            position_id="p1", asset="BTC", side="UP",
            condition_id="0x1", token_id="tok1",
            state=PositionState.OPEN_CONFIRMED,
            fill_price=0.85, net_position_shares=5.88,
            requested_amount_usd=5.0,
        )
        tracker.restore_position(pos)

        assert tracker.open_position_count == 1
        assert tracker.get_event_fill_count("0x1") == 1
        assert tracker.session_trade_count == 1
        assert tracker.get_position("p1") is pos

    def test_restore_closed_position(self):
        tracker = PositionTracker()
        pos = PositionRecord(
            position_id="p1", asset="BTC", side="UP",
            condition_id="0x1", token_id="tok1",
            state=PositionState.CLOSED,
        )
        tracker.restore_position(pos)

        assert tracker.open_position_count == 0  # kapali
        assert tracker.get_event_fill_count("0x1") == 1  # fill sayaci var
        assert tracker.session_trade_count == 1

    def test_restore_multiple_positions(self):
        tracker = PositionTracker()
        pos1 = PositionRecord(
            position_id="p1", asset="BTC", side="UP",
            condition_id="0x1", token_id="tok1",
            state=PositionState.OPEN_CONFIRMED,
        )
        pos2 = PositionRecord(
            position_id="p2", asset="ETH", side="DOWN",
            condition_id="0x2", token_id="tok2",
            state=PositionState.CLOSING_REQUESTED,
            close_reason=CloseReason.STOP_LOSS,
        )
        tracker.restore_position(pos1)
        tracker.restore_position(pos2)

        assert tracker.open_position_count == 1  # sadece OPEN_CONFIRMED sayilir
        assert tracker.session_trade_count == 2


class TestClaimRestore:

    def test_restore_pending_claim(self):
        balance = BalanceManager()
        balance.update(available=100.0)
        claim_mgr = ClaimManager(balance, paper_mode=True)

        claim = ClaimRecord(
            claim_id="c1", condition_id="0x1", position_id="p1",
            asset="BTC", side="UP",
            claim_status=ClaimStatus.PENDING,
        )
        claim_mgr.restore_claim(claim)

        assert claim_mgr.has_pending_claims() is True
        assert claim_mgr.pending_count == 1

    def test_restore_success_claim(self):
        balance = BalanceManager()
        balance.update(available=100.0)
        claim_mgr = ClaimManager(balance, paper_mode=True)

        claim = ClaimRecord(
            claim_id="c1", condition_id="0x1", position_id="p1",
            asset="BTC", claim_status=ClaimStatus.SUCCESS,
            outcome=ClaimOutcome.REDEEMED_WON,
        )
        claim_mgr.restore_claim(claim)

        assert claim_mgr.has_pending_claims() is False
        assert claim_mgr.total_claimed == 1


# ═══════════════════════════════════════════════════
# SESSION CONTINUITY
# ═══════════════════════════════════════════════════

class TestSessionContinuity:

    def test_session_trade_count_preserved(self):
        """Restart sonrasi session trade count korunur."""
        tracker = PositionTracker()
        # 3 kapanmis pozisyon restore et
        for i in range(3):
            pos = PositionRecord(
                position_id=f"p{i}", asset="BTC", side="UP",
                condition_id="0x1", token_id="tok1",
                state=PositionState.CLOSED,
            )
            tracker.restore_position(pos)

        assert tracker.session_trade_count == 3


# ═══════════════════════════════════════════════════
# BOUNDARY
# ═══════════════════════════════════════════════════

class TestSettingsRestore:

    @pytest.mark.asyncio
    async def test_save_and_load_settings(self, db):
        from backend.persistence.settings_store_db import SettingsStoreDB
        from backend.settings.coin_settings import CoinSettings, SideMode

        store = SettingsStoreDB()
        settings = CoinSettings(
            coin="BTC", coin_enabled=True, side_mode=SideMode.DOMINANT_ONLY,
            delta_threshold=50.0, price_min=55, price_max=80,
            order_amount=10.0,
        )
        ok = await store.save(settings)
        assert ok is True

        loaded = await store.load_all()
        assert len(loaded) == 1
        assert loaded[0].coin == "BTC"
        assert loaded[0].coin_enabled is True
        assert loaded[0].order_amount == 10.0


class TestRegistryRestore:

    @pytest.mark.asyncio
    async def test_save_and_load_registry(self, db):
        from backend.persistence.registry_store import RegistryStore
        from backend.registry.models import RegistryRecord, EventStatus

        store = RegistryStore()
        rec = RegistryRecord(
            event_id="ev1", condition_id="0x1", asset="BTC",
            question="BTC up?", slug="btc-5m", status=EventStatus.ACTIVE,
            first_seen_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc),
            status_changed_at=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc),
        )
        ok = await store.save(rec)
        assert ok is True

        loaded = await store.load_active()
        assert len(loaded) == 1
        assert loaded[0].condition_id == "0x1"
        assert loaded[0].status == EventStatus.ACTIVE


class TestPTBRestore:

    @pytest.mark.asyncio
    async def test_save_and_load_ptb(self, db):
        from backend.persistence.ptb_store import PTBStore
        from backend.ptb.models import PTBRecord

        store = PTBStore()
        rec = PTBRecord(condition_id="0x1", asset="BTC")
        rec.lock(67000.12, "ssr_open_price")

        ok = await store.save(rec)
        assert ok is True

        loaded = await store.load_locked()
        assert len(loaded) == 1
        assert loaded[0].ptb_value == 67000.12
        assert loaded[0].is_locked is True

    @pytest.mark.asyncio
    async def test_clear_event_ptb(self, db):
        from backend.persistence.ptb_store import PTBStore
        from backend.ptb.models import PTBRecord

        store = PTBStore()
        rec = PTBRecord(condition_id="0x1", asset="BTC")
        rec.lock(67000.0, "test")
        await store.save(rec)

        ok = await store.clear_event("0x1")
        assert ok is True

        loaded = await store.load_locked()
        assert len(loaded) == 0


class TestDegradedMode:

    def test_trading_enabled_default(self):
        """Default: trading_enabled = True."""
        from backend.config_loader.schema import AppConfig
        from backend.orchestrator.wiring import Orchestrator
        orch = Orchestrator(config=AppConfig())
        assert orch.trading_enabled is True


class TestPersistenceBoundaries:

    def test_store_write_failure_no_crash(self):
        """Store write basarisiz olsa bile tracker calismaya devam eder."""
        tracker = PositionTracker()  # store=None
        pos = tracker.create_pending("BTC", "UP", "0x1", "tok1", 5.0)
        tracker.confirm_fill(pos.position_id, fill_price=0.85)
        assert pos.is_open

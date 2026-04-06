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


class TestBalanceVerifyRetry:

    @pytest.mark.asyncio
    async def test_verify_retry_task_created_on_degraded(self):
        """Degraded mode'da verify retry task olusturulur."""
        from backend.config_loader.schema import AppConfig
        from backend.orchestrator.wiring import Orchestrator
        orch = Orchestrator(config=AppConfig())
        orch.trading_enabled = False
        orch._start_verify_retry()
        assert orch._verify_retry_running is True
        # Temizlik
        orch._verify_retry_running = False
        if orch._verify_retry_task:
            orch._verify_retry_task.cancel()
            try:
                await orch._verify_retry_task
            except asyncio.CancelledError:
                pass

    def test_normal_mode_no_retry(self):
        """Normal mode'da verify retry baslatilmaz."""
        from backend.config_loader.schema import AppConfig
        from backend.orchestrator.wiring import Orchestrator
        orch = Orchestrator(config=AppConfig())
        assert orch.trading_enabled is True
        assert orch._verify_retry_running is False


class TestFullRecoveryE2E:
    """SQLite'a yaz -> restore et -> state tutarli mi kontrol et."""

    @pytest.mark.asyncio
    async def test_position_roundtrip(self, db):
        """Position: save -> load -> memory state tutarli."""
        store = PositionStore()
        tracker = PositionTracker()

        # Orijinal pozisyon
        pos = PositionRecord(
            position_id="rt1", asset="BTC", side="UP",
            condition_id="0x1", token_id="tok1",
            state=PositionState.OPEN_CONFIRMED,
            fill_price=0.85, net_position_shares=5.88,
            requested_amount_usd=5.0, fee_rate=0.072,
        )
        await store.save(pos)

        # "Restart" — yeni tracker, SQLite'tan oku
        tracker2 = PositionTracker()
        loaded = await store.load_all()
        for p in loaded:
            tracker2.restore_position(p)

        assert tracker2.open_position_count == 1
        assert tracker2.session_trade_count == 1
        restored = tracker2.get_position("rt1")
        assert restored.fill_price == 0.85
        assert restored.state == PositionState.OPEN_CONFIRMED

    @pytest.mark.asyncio
    async def test_claim_roundtrip(self, db):
        """Claim: save -> load -> pending state korunur."""
        from backend.persistence.claim_store import ClaimStore

        claim_store = ClaimStore()
        balance = BalanceManager()
        balance.update(available=100.0)

        claim = ClaimRecord(
            claim_id="crt1", condition_id="0x1", position_id="p1",
            asset="BTC", side="UP",
            claim_status=ClaimStatus.PENDING,
            retry_count=3,
        )
        await claim_store.save(claim)

        # "Restart"
        mgr2 = ClaimManager(balance, paper_mode=True)
        loaded = await claim_store.load_all()
        for c in loaded:
            mgr2.restore_claim(c)

        assert mgr2.has_pending_claims() is True
        assert mgr2.pending_count == 1
        restored = mgr2.get_claim("crt1")
        assert restored.retry_count == 3

    @pytest.mark.asyncio
    async def test_settings_roundtrip(self, db):
        """Settings: save -> load -> coin config korunur."""
        from backend.persistence.settings_store_db import SettingsStoreDB
        from backend.settings.settings_store import SettingsStore
        from backend.settings.coin_settings import CoinSettings, SideMode

        db_store = SettingsStoreDB()
        settings = CoinSettings(
            coin="ETH", coin_enabled=True,
            side_mode=SideMode.UP_ONLY,
            order_amount=15.0,
        )
        await db_store.save(settings)

        # "Restart"
        store2 = SettingsStore()
        loaded = await db_store.load_all()
        for s in loaded:
            store2.set(s)

        restored = store2.get("ETH")
        assert restored is not None
        assert restored.coin_enabled is True
        assert restored.side_mode == SideMode.UP_ONLY
        assert restored.order_amount == 15.0

    @pytest.mark.asyncio
    async def test_multi_component_roundtrip(self, db):
        """Tum component'lar birlikte: save -> restore -> tutarli."""
        pos_store = PositionStore()
        claim_store = ClaimStore()

        # 2 pozisyon + 1 claim kaydet
        pos1 = PositionRecord(
            position_id="m1", asset="BTC", side="UP",
            condition_id="0x1", token_id="t1",
            state=PositionState.OPEN_CONFIRMED, fill_price=0.85,
            requested_amount_usd=5.0,
        )
        pos2 = PositionRecord(
            position_id="m2", asset="ETH", side="DOWN",
            condition_id="0x2", token_id="t2",
            state=PositionState.CLOSED, fill_price=0.60,
            close_reason=CloseReason.TAKE_PROFIT,
            requested_amount_usd=10.0,
        )
        claim1 = ClaimRecord(
            claim_id="mc1", condition_id="0x1", position_id="m1",
            asset="BTC", claim_status=ClaimStatus.PENDING,
        )
        await pos_store.save(pos1)
        await pos_store.save(pos2)
        await claim_store.save(claim1)

        # "Restart"
        tracker = PositionTracker()
        balance = BalanceManager()
        balance.update(available=50.0)
        claim_mgr = ClaimManager(balance, paper_mode=True)

        for p in await pos_store.load_all():
            tracker.restore_position(p)
        for c in await claim_store.load_all():
            claim_mgr.restore_claim(c)

        assert tracker.open_position_count == 1  # sadece m1
        assert tracker.session_trade_count == 2  # m1 + m2
        assert claim_mgr.has_pending_claims() is True
        assert claim_mgr.pending_count == 1


class TestPersistenceBoundaries:

    def test_store_write_failure_no_crash(self):
        """Store write basarisiz olsa bile tracker calismaya devam eder."""
        tracker = PositionTracker()  # store=None
        pos = tracker.create_pending("BTC", "UP", "0x1", "tok1", 5.0)
        tracker.confirm_fill(pos.position_id, fill_price=0.85)
        assert pos.is_open

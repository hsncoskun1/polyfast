"""Tests for session accounting — model, manager, persistence, boundaries."""

import pytest
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from backend.accounting.balance import BalanceSnapshot
from backend.accounting.session import SessionAccounting, SessionStatus
from backend.accounting.session_manager import (
    SessionManager,
    DuplicateSessionError,
)
from backend.persistence.database import init_db, close_db
from backend.persistence.migrations import run_migrations


@pytest.fixture
async def db():
    """Create a temporary database with migrations applied."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        conn = await init_db(db_path)
        await run_migrations(conn)
        yield conn
        await close_db()


def _make_snapshot(total: float = 247.85, available: float = 200.00) -> BalanceSnapshot:
    return BalanceSnapshot(
        total=total,
        available=available,
        fetched_at=datetime(2026, 4, 4, 12, 0, 0, tzinfo=timezone.utc),
    )


# ===== SessionAccounting Model Tests =====

class TestSessionAccountingModel:
    def test_from_balance_snapshot(self):
        """Session created from snapshot has correct fields."""
        snap = _make_snapshot(247.85, 200.00)
        session = SessionAccounting.from_balance_snapshot(snap)

        assert session.start_balance == 247.85
        assert session.available_balance == 200.00
        assert session.status == SessionStatus.ACTIVE
        assert session.balance_fetched_at == snap.fetched_at
        assert session.session_id  # non-empty
        assert session.started_at is not None

    def test_status_is_enum_not_string(self):
        """Status is SessionStatus enum, not arbitrary string."""
        snap = _make_snapshot()
        session = SessionAccounting.from_balance_snapshot(snap)
        assert isinstance(session.status, SessionStatus)

    def test_serialization_roundtrip(self):
        """to_dict / from_dict preserves all fields."""
        snap = _make_snapshot(100.50, 80.25)
        original = SessionAccounting.from_balance_snapshot(snap)
        data = original.to_dict()
        restored = SessionAccounting.from_dict(data)

        assert restored.session_id == original.session_id
        assert restored.start_balance == original.start_balance
        assert restored.available_balance == original.available_balance
        assert restored.status == original.status
        assert restored.balance_fetched_at == original.balance_fetched_at

    def test_session_is_not_balance_snapshot(self):
        """SessionAccounting and BalanceSnapshot are distinct types."""
        snap = _make_snapshot()
        session = SessionAccounting.from_balance_snapshot(snap)
        assert type(snap) is not type(session)
        assert hasattr(session, "session_id")
        assert hasattr(session, "status")
        assert not hasattr(snap, "session_id")


# ===== SessionManager — Creation Tests =====

class TestSessionManagerCreation:
    async def test_create_session_success(self, db):
        """Successful startup → session created with correct values."""
        manager = SessionManager(db)
        snap = _make_snapshot(247.85, 200.00)
        session = manager.create_session(snap)

        assert session.start_balance == 247.85
        assert session.available_balance == 200.00
        assert session.status == SessionStatus.ACTIVE
        assert manager.has_active_session is True
        assert manager.current_session is session

    async def test_duplicate_creation_rejected(self, db):
        """Creating session when active one exists → DuplicateSessionError."""
        manager = SessionManager(db)
        snap = _make_snapshot()
        manager.create_session(snap)

        with pytest.raises(DuplicateSessionError):
            manager.create_session(snap)

    async def test_no_session_initially(self, db):
        """Before creation, no active session exists."""
        manager = SessionManager(db)
        assert manager.current_session is None
        assert manager.has_active_session is False


# ===== SessionManager — Persistence Tests =====

class TestSessionManagerPersistence:
    async def test_save_and_load_roundtrip(self, db):
        """Session can be saved and loaded from database."""
        manager = SessionManager(db)
        snap = _make_snapshot(500.00, 450.00)
        original = manager.create_session(snap)
        await manager.save_session()

        # Create a new manager to simulate restart
        manager2 = SessionManager(db)
        loaded = await manager2.load_latest_session()

        assert loaded is not None
        assert loaded.session_id == original.session_id
        assert loaded.start_balance == 500.00
        assert loaded.available_balance == 450.00
        assert loaded.status == SessionStatus.ACTIVE

    async def test_load_from_empty_database(self, db):
        """Loading from empty database returns None."""
        manager = SessionManager(db)
        result = await manager.load_latest_session()
        assert result is None

    async def test_save_without_session_raises(self, db):
        """Saving without a current session raises RuntimeError."""
        manager = SessionManager(db)
        with pytest.raises(RuntimeError, match="No session to save"):
            await manager.save_session()


# ===== Boundary Tests — No Coupling =====

class TestBoundaries:
    async def test_no_discovery_coupling(self, db):
        """SessionManager has no discovery imports."""
        import backend.accounting.session_manager as mod
        import_lines = [
            line.strip() for line in open(mod.__file__).readlines()
            if line.strip().startswith(("import ", "from "))
        ]
        for line in import_lines:
            assert "discovery" not in line.lower()

    async def test_no_execution_coupling(self, db):
        """SessionManager has no execution imports."""
        import backend.accounting.session_manager as mod
        import_lines = [
            line.strip() for line in open(mod.__file__).readlines()
            if line.strip().startswith(("import ", "from "))
        ]
        for line in import_lines:
            assert "execution" not in line.lower()

    async def test_startup_guard_not_imported(self, db):
        """SessionManager does not import StartupGuard."""
        import backend.accounting.session_manager as mod
        import_lines = [
            line.strip() for line in open(mod.__file__).readlines()
            if line.strip().startswith(("import ", "from "))
        ]
        for line in import_lines:
            assert "startup_guard" not in line
            assert "StartupGuard" not in line

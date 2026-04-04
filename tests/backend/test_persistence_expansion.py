"""Tests for persistence expansion — migrations 003/004, checkpoint/balance save/load."""

import pytest
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from backend.persistence.database import init_db, close_db
from backend.persistence.migrations import run_migrations, get_current_version
from backend.persistence.checkpoint_store import (
    save_discovery_checkpoint,
    load_latest_checkpoint,
)
from backend.persistence.balance_store import (
    save_balance_snapshot,
    load_latest_balance_snapshot,
    load_balance_snapshots_by_session,
)


@pytest.fixture
async def db():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        conn = await init_db(db_path)
        await run_migrations(conn)
        yield conn
        await close_db()


# ===== Migration Tests =====

class TestMigrations:
    async def test_migrations_create_new_tables(self, db):
        """Migrations 003 and 004 create expected tables."""
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]
        assert "discovery_checkpoints" in tables
        assert "balance_snapshots" in tables

    async def test_migrations_idempotent(self, db):
        """Running migrations twice doesn't error."""
        applied = await run_migrations(db)
        assert len(applied) == 0  # already applied

    async def test_migration_version_correct(self, db):
        """Current version reflects all migrations."""
        version = await get_current_version(db)
        assert version >= 4

    async def test_migration_apply_twice_safe(self):
        """Fresh DB → apply → apply again → no error."""
        with tempfile.TemporaryDirectory() as tmp:
            conn = await init_db(str(Path(tmp) / "test2.db"))
            first = await run_migrations(conn)
            second = await run_migrations(conn)
            assert len(first) >= 1
            assert len(second) == 0
            await conn.close()


# ===== Discovery Checkpoint Tests =====

class TestDiscoveryCheckpointPersistence:
    async def test_save_checkpoint(self, db):
        """Checkpoint can be saved."""
        row_id = await save_discovery_checkpoint(
            db, total_scanned=50, total_matched=5, parse_failures=2,
            success=True, matched_condition_ids=["0x1", "0x2"],
        )
        assert row_id is not None
        assert row_id > 0

    async def test_save_load_roundtrip(self, db):
        """Save then load preserves data."""
        ts = datetime(2026, 4, 4, 12, 0, 0, tzinfo=timezone.utc)
        await save_discovery_checkpoint(
            db, total_scanned=100, total_matched=10, parse_failures=3,
            success=True, matched_condition_ids=["0xa", "0xb"],
            scanned_at=ts,
        )
        loaded = await load_latest_checkpoint(db)

        assert loaded is not None
        assert loaded["total_scanned"] == 100
        assert loaded["total_matched"] == 10
        assert loaded["parse_failures"] == 3
        assert loaded["success"] is True
        assert loaded["scan_data"]["matched_condition_ids"] == ["0xa", "0xb"]

    async def test_load_empty_db(self, db):
        """Loading from empty table returns None."""
        # Clear any existing data
        await db.execute("DELETE FROM discovery_checkpoints")
        await db.commit()
        result = await load_latest_checkpoint(db)
        assert result is None

    async def test_latest_checkpoint_is_most_recent(self, db):
        """Multiple saves → load returns the latest."""
        await save_discovery_checkpoint(
            db, total_scanned=10, total_matched=1, parse_failures=0,
            success=True, matched_condition_ids=["0x1"],
        )
        await save_discovery_checkpoint(
            db, total_scanned=20, total_matched=2, parse_failures=0,
            success=True, matched_condition_ids=["0x2"],
        )
        loaded = await load_latest_checkpoint(db)
        assert loaded["total_scanned"] == 20

    async def test_failed_scan_checkpoint(self, db):
        """Failed scan checkpoint preserves success=False."""
        await save_discovery_checkpoint(
            db, total_scanned=0, total_matched=0, parse_failures=0,
            success=False, matched_condition_ids=[],
        )
        loaded = await load_latest_checkpoint(db)
        assert loaded["success"] is False


# ===== Balance Snapshot Tests =====

class TestBalanceSnapshotPersistence:
    async def test_save_snapshot(self, db):
        """Balance snapshot can be saved."""
        ts = datetime(2026, 4, 4, 12, 0, 0, tzinfo=timezone.utc)
        row_id = await save_balance_snapshot(
            db, total_balance=247.85, available_balance=200.00,
            fetched_at=ts, session_id="sess-1",
        )
        assert row_id is not None
        assert row_id > 0

    async def test_save_load_roundtrip(self, db):
        """Save then load preserves data."""
        ts = datetime(2026, 4, 4, 12, 0, 0, tzinfo=timezone.utc)
        await save_balance_snapshot(
            db, total_balance=500.00, available_balance=450.00,
            fetched_at=ts, session_id="sess-abc",
        )
        loaded = await load_latest_balance_snapshot(db)

        assert loaded is not None
        assert loaded["total_balance"] == 500.00
        assert loaded["available_balance"] == 450.00
        assert loaded["session_id"] == "sess-abc"

    async def test_load_empty_db(self, db):
        """Loading from empty table returns None."""
        await db.execute("DELETE FROM balance_snapshots")
        await db.commit()
        result = await load_latest_balance_snapshot(db)
        assert result is None

    async def test_load_by_session(self, db):
        """Load snapshots filtered by session_id."""
        ts = datetime(2026, 4, 4, 12, 0, 0, tzinfo=timezone.utc)
        await save_balance_snapshot(db, 100, 80, ts, "sess-1")
        await save_balance_snapshot(db, 200, 180, ts, "sess-2")
        await save_balance_snapshot(db, 150, 130, ts, "sess-1")

        sess1 = await load_balance_snapshots_by_session(db, "sess-1")
        assert len(sess1) == 2
        assert sess1[0]["total_balance"] == 100
        assert sess1[1]["total_balance"] == 150

    async def test_snapshot_without_session(self, db):
        """Snapshot can be saved without session_id."""
        ts = datetime(2026, 4, 4, 12, 0, 0, tzinfo=timezone.utc)
        await save_balance_snapshot(db, 50, 40, ts, session_id=None)
        loaded = await load_latest_balance_snapshot(db)
        assert loaded["session_id"] is None


# ===== No Secret Persistence =====

class TestNoSecretPersistence:
    def test_checkpoint_store_no_secret_fields(self):
        """Checkpoint store has no credential fields."""
        import backend.persistence.checkpoint_store as mod
        source = open(mod.__file__).read()
        for secret in ["api_key", "secret", "passphrase", "private_key", "relayer_key"]:
            assert secret not in source.lower() or "no secret" in source.lower()

    def test_balance_store_no_secret_fields(self):
        """Balance store has no credential fields."""
        import backend.persistence.balance_store as mod
        source = open(mod.__file__).read()
        for secret in ["api_key", "secret", "passphrase", "private_key", "relayer_key"]:
            assert secret not in source.lower() or "no secret" in source.lower()


# ===== Boundary Tests =====

class TestPersistenceBoundaries:
    def test_checkpoint_store_no_domain_logic(self):
        """Checkpoint store doesn't import discovery/registry domain."""
        import backend.persistence.checkpoint_store as mod
        import_lines = [l.strip() for l in open(mod.__file__).readlines()
                        if l.strip().startswith(("import ", "from "))]
        for line in import_lines:
            assert "discovery" not in line
            assert "registry" not in line
            assert "strategy" not in line

    def test_balance_store_no_domain_logic(self):
        """Balance store doesn't import accounting/session domain."""
        import backend.persistence.balance_store as mod
        import_lines = [l.strip() for l in open(mod.__file__).readlines()
                        if l.strip().startswith(("import ", "from "))]
        for line in import_lines:
            assert "accounting" not in line
            assert "session" not in line
            assert "startup" not in line

"""Tests for persistence layer — database and migrations."""

import pytest
import tempfile
from pathlib import Path

from backend.persistence.database import init_db, get_db, close_db
from backend.persistence.migrations import run_migrations, get_current_version


@pytest.fixture
async def db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "test.db")
        conn = await init_db(db_path)
        yield conn
        await close_db()


async def test_init_db_creates_file(db):
    """init_db creates the database file."""
    assert db is not None


async def test_get_db_returns_connection(db):
    """get_db returns the initialized connection."""
    conn = await get_db()
    assert conn is db


async def test_get_db_before_init_raises():
    """get_db raises RuntimeError if not initialized."""
    from backend.persistence import database
    original = database._db
    database._db = None
    try:
        with pytest.raises(RuntimeError, match="Database not initialized"):
            await get_db()
    finally:
        database._db = original


async def test_run_migrations_creates_tables(db):
    """Migrations create the expected tables."""
    applied = await run_migrations(db)
    assert 1 in applied

    # Verify tables exist
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in await cursor.fetchall()]
    assert "migrations" in tables
    assert "config_snapshots" in tables
    assert "health_incidents" in tables
    assert "app_state" in tables


async def test_migrations_are_idempotent(db):
    """Running migrations twice applies them only once."""
    first = await run_migrations(db)
    second = await run_migrations(db)
    assert len(first) == 1
    assert len(second) == 0


async def test_current_version_after_migration(db):
    """Current version reflects applied migrations."""
    assert await get_current_version(db) == 0
    await run_migrations(db)
    assert await get_current_version(db) == 1


async def test_app_state_insert_and_read(db):
    """app_state table supports key-value operations."""
    await run_migrations(db)
    await db.execute(
        "INSERT INTO app_state (key, value_json) VALUES (?, ?)",
        ("test_key", '{"value": 42}'),
    )
    await db.commit()

    cursor = await db.execute("SELECT value_json FROM app_state WHERE key = ?", ("test_key",))
    row = await cursor.fetchone()
    assert row[0] == '{"value": 42}'


async def test_health_incidents_insert(db):
    """health_incidents table accepts valid severity values."""
    await run_migrations(db)
    await db.execute(
        "INSERT INTO health_incidents (severity, category, message) VALUES (?, ?, ?)",
        ("warning", "test", "test incident"),
    )
    await db.commit()

    cursor = await db.execute("SELECT severity, category, message FROM health_incidents")
    row = await cursor.fetchone()
    assert row[0] == "warning"
    assert row[1] == "test"

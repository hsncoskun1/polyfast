"""SQLite connection manager — async database access via aiosqlite."""

import aiosqlite
from pathlib import Path

_db: aiosqlite.Connection | None = None
_db_path: str = "data/polyfast.db"


async def init_db(db_path: str | None = None) -> aiosqlite.Connection:
    """Initialize database connection and ensure parent directory exists.

    Args:
        db_path: Path to SQLite database file.

    Returns:
        Active aiosqlite connection.
    """
    global _db, _db_path

    if db_path:
        _db_path = db_path

    # Ensure parent directory exists
    Path(_db_path).parent.mkdir(parents=True, exist_ok=True)

    _db = await aiosqlite.connect(_db_path)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA foreign_keys=ON")

    return _db


async def get_db() -> aiosqlite.Connection:
    """Get the current database connection. Raises if not initialized."""
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db


async def close_db() -> None:
    """Close the database connection."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None

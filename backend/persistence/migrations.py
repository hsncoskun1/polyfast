"""Migration runner — sequential SQL migrations with version tracking."""

from pathlib import Path

import aiosqlite

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def get_current_version(db: aiosqlite.Connection) -> int:
    """Get the current migration version from the database.

    Returns 0 if migrations table doesn't exist yet.
    """
    try:
        cursor = await db.execute("SELECT MAX(version) FROM migrations")
        row = await cursor.fetchone()
        return row[0] if row[0] is not None else 0
    except aiosqlite.OperationalError:
        return 0


async def run_migrations(db: aiosqlite.Connection) -> list[int]:
    """Run all pending migrations in order.

    Returns:
        List of migration versions that were applied.
    """
    # Discover migration files
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        return []

    current_version = await get_current_version(db)
    applied = []

    for migration_file in migration_files:
        # Extract version number from filename (e.g., 001_initial.sql -> 1)
        version = int(migration_file.stem.split("_")[0])

        if version <= current_version:
            continue

        # Read and execute migration
        sql = migration_file.read_text(encoding="utf-8")
        await db.executescript(sql)

        # Record migration
        await db.execute(
            "INSERT INTO migrations (version, name) VALUES (?, ?)",
            (version, migration_file.stem),
        )
        await db.commit()

        applied.append(version)

    return applied

"""Balance snapshot persistence — save/load balance fetch history.

Balance snapshot relates to accounting contract: records balance at fetch time.
This module does NOT make accounting decisions — it only persists snapshots.
No secrets or credentials are stored in this table.
"""

from datetime import datetime, timezone

import aiosqlite


async def save_balance_snapshot(
    db: aiosqlite.Connection,
    total_balance: float,
    available_balance: float,
    fetched_at: datetime,
    session_id: str | None = None,
) -> int:
    """Save a balance snapshot.

    Args:
        db: Database connection.
        total_balance: Total account balance in USD.
        available_balance: Available balance for trading in USD.
        fetched_at: When the balance was fetched from API.
        session_id: Optional session ID this snapshot belongs to.

    Returns:
        Row ID of the saved snapshot.
    """
    cursor = await db.execute(
        """INSERT INTO balance_snapshots
           (total_balance, available_balance, fetched_at, session_id)
           VALUES (?, ?, ?, ?)""",
        (total_balance, available_balance, fetched_at.isoformat(), session_id),
    )
    await db.commit()
    return cursor.lastrowid


async def load_latest_balance_snapshot(db: aiosqlite.Connection) -> dict | None:
    """Load the most recent balance snapshot.

    Returns:
        Dict with snapshot data, or None if no snapshots exist.
    """
    cursor = await db.execute(
        "SELECT id, total_balance, available_balance, fetched_at, session_id, created_at "
        "FROM balance_snapshots ORDER BY id DESC LIMIT 1"
    )
    row = await cursor.fetchone()

    if row is None:
        return None

    return {
        "id": row[0],
        "total_balance": row[1],
        "available_balance": row[2],
        "fetched_at": row[3],
        "session_id": row[4],
        "created_at": row[5],
    }


async def load_balance_snapshots_by_session(
    db: aiosqlite.Connection, session_id: str
) -> list[dict]:
    """Load all balance snapshots for a given session.

    Returns:
        List of snapshot dicts, ordered by creation time.
    """
    cursor = await db.execute(
        "SELECT id, total_balance, available_balance, fetched_at, session_id, created_at "
        "FROM balance_snapshots WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,),
    )
    rows = await cursor.fetchall()

    return [
        {
            "id": row[0],
            "total_balance": row[1],
            "available_balance": row[2],
            "fetched_at": row[3],
            "session_id": row[4],
            "created_at": row[5],
        }
        for row in rows
    ]

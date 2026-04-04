"""Discovery checkpoint persistence — save/load discovery scan results.

Checkpoint ownership: persistence layer stores, discovery engine produces.
This module does NOT make discovery decisions — it only persists results.
"""

import json
from datetime import datetime, timezone

import aiosqlite


async def save_discovery_checkpoint(
    db: aiosqlite.Connection,
    total_scanned: int,
    total_matched: int,
    parse_failures: int,
    success: bool,
    matched_condition_ids: list[str],
    scanned_at: datetime | None = None,
) -> int:
    """Save a discovery scan checkpoint.

    Args:
        db: Database connection.
        total_scanned: Number of raw events scanned.
        total_matched: Number of events matching criteria.
        parse_failures: Number of events that failed to parse.
        success: Whether the scan completed successfully.
        matched_condition_ids: List of condition_ids that matched.
        scanned_at: Scan timestamp (defaults to now).

    Returns:
        Row ID of the saved checkpoint.
    """
    ts = (scanned_at or datetime.now(timezone.utc)).isoformat()
    scan_data = {
        "matched_condition_ids": matched_condition_ids,
    }

    cursor = await db.execute(
        """INSERT INTO discovery_checkpoints
           (scan_data_json, total_scanned, total_matched, parse_failures, success, scanned_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (json.dumps(scan_data), total_scanned, total_matched, parse_failures, int(success), ts),
    )
    await db.commit()
    return cursor.lastrowid


async def load_latest_checkpoint(db: aiosqlite.Connection) -> dict | None:
    """Load the most recent discovery checkpoint.

    Returns:
        Dict with checkpoint data, or None if no checkpoints exist.
    """
    cursor = await db.execute(
        "SELECT id, scan_data_json, total_scanned, total_matched, parse_failures, success, scanned_at "
        "FROM discovery_checkpoints ORDER BY id DESC LIMIT 1"
    )
    row = await cursor.fetchone()

    if row is None:
        return None

    return {
        "id": row[0],
        "scan_data": json.loads(row[1]),
        "total_scanned": row[2],
        "total_matched": row[3],
        "parse_failures": row[4],
        "success": bool(row[5]),
        "scanned_at": row[6],
    }

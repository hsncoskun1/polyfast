"""SessionManager — owns session creation, loading, and access.

Separate from StartupGuard: guard decides if startup passes,
SessionManager creates and manages the session accounting record.

Duplicate session behavior (v0.2.2 rule):
- If an active session already exists, creating a new one is REJECTED.
- The caller must explicitly end or discard the current session first.
- This prevents accidental session overwrite.
"""

import json
import logging

import aiosqlite

from backend.accounting.balance import BalanceSnapshot
from backend.accounting.session import SessionAccounting, SessionStatus
from backend.logging_config.service import get_logger, log_event

logger = get_logger("session_manager")


class DuplicateSessionError(Exception):
    """Raised when trying to create a session while one is already active."""
    pass


class SessionManager:
    """Manages session accounting lifecycle.

    Responsibilities:
    - Create session from successful balance fetch
    - Persist session to database
    - Load session from database
    - Provide current session access

    Does NOT:
    - Decide if startup should proceed (→ StartupGuard)
    - Calculate PnL (future versions)
    - Handle discovery or trading logic
    """

    def __init__(self, db: aiosqlite.Connection):
        self._db = db
        self._current: SessionAccounting | None = None

    def create_session(self, snapshot: BalanceSnapshot) -> SessionAccounting:
        """Create a new session accounting record from a balance snapshot.

        Args:
            snapshot: Successful balance fetch result.

        Returns:
            New SessionAccounting record.

        Raises:
            DuplicateSessionError: If an active session already exists.
        """
        if self._current is not None and self._current.status == SessionStatus.ACTIVE:
            raise DuplicateSessionError(
                f"Active session already exists: {self._current.session_id}. "
                "End or discard it before creating a new one."
            )

        session = SessionAccounting.from_balance_snapshot(snapshot)
        self._current = session

        log_event(
            logger, logging.INFO,
            f"Session created: start_balance={session.start_balance}, "
            f"available={session.available_balance}",
            entity_type="session",
            entity_id=session.session_id,
        )

        return session

    @property
    def current_session(self) -> SessionAccounting | None:
        """Get the current active session, if any."""
        return self._current

    @property
    def has_active_session(self) -> bool:
        """Whether an active session exists."""
        return (
            self._current is not None
            and self._current.status == SessionStatus.ACTIVE
        )

    async def save_session(self) -> None:
        """Persist the current session to database.

        Raises:
            RuntimeError: If no current session exists.
        """
        if self._current is None:
            raise RuntimeError("No session to save.")

        data = self._current.to_dict()
        await self._db.execute(
            """INSERT OR REPLACE INTO session_accounting
               (session_id, data_json, created_at)
               VALUES (?, ?, ?)""",
            (data["session_id"], json.dumps(data), data["started_at"]),
        )
        await self._db.commit()

        log_event(
            logger, logging.INFO,
            "Session persisted to database",
            entity_type="session",
            entity_id=self._current.session_id,
        )

    async def load_latest_session(self) -> SessionAccounting | None:
        """Load the most recent session from database.

        Returns:
            SessionAccounting if found, None otherwise.
        """
        cursor = await self._db.execute(
            "SELECT data_json FROM session_accounting ORDER BY created_at DESC LIMIT 1"
        )
        row = await cursor.fetchone()

        if row is None:
            return None

        data = json.loads(row[0])
        session = SessionAccounting.from_dict(data)
        self._current = session

        log_event(
            logger, logging.INFO,
            f"Session loaded from persistence: {session.session_id}",
            entity_type="session",
            entity_id=session.session_id,
        )

        return session

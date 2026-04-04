"""Session accounting model — session bootstrap and start balance tracking.

This module defines the session accounting omurgası for v0.2.2.
Only start balance recording is in scope. Full PnL, trade aggregation,
session close logic, and performance metrics will come in later versions.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from backend.accounting.balance import BalanceSnapshot


class SessionStatus(str, Enum):
    """Session lifecycle status.

    Minimal set for v0.2.2. Will expand in later versions
    (e.g., CLOSING, CLOSED, RECOVERED).
    """
    ACTIVE = "active"
    FAILED_START = "failed_start"


@dataclass
class SessionAccounting:
    """Session accounting record — tracks session start state.

    This is NOT the same as BalanceSnapshot. BalanceSnapshot is a raw fetch result.
    SessionAccounting is the accounting layer that records the session context.

    Attributes:
        session_id: Unique session identifier.
        start_balance: Total balance at session start (USD).
        available_balance: Available balance at session start (USD).
        started_at: UTC timestamp when session was created.
        status: Current session status.
        balance_fetched_at: When the source balance was fetched.
    """
    session_id: str
    start_balance: float
    available_balance: float
    started_at: datetime
    status: SessionStatus
    balance_fetched_at: datetime

    @classmethod
    def from_balance_snapshot(cls, snapshot: BalanceSnapshot) -> "SessionAccounting":
        """Create a new session accounting record from a balance snapshot.

        Args:
            snapshot: The balance snapshot from successful startup fetch.

        Returns:
            New SessionAccounting with ACTIVE status.
        """
        return cls(
            session_id=str(uuid.uuid4()),
            start_balance=snapshot.total,
            available_balance=snapshot.available,
            started_at=datetime.now(timezone.utc),
            status=SessionStatus.ACTIVE,
            balance_fetched_at=snapshot.fetched_at,
        )

    def to_dict(self) -> dict:
        """Serialize to dict for persistence."""
        return {
            "session_id": self.session_id,
            "start_balance": self.start_balance,
            "available_balance": self.available_balance,
            "started_at": self.started_at.isoformat(),
            "status": self.status.value,
            "balance_fetched_at": self.balance_fetched_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionAccounting":
        """Deserialize from dict (persistence load)."""
        return cls(
            session_id=data["session_id"],
            start_balance=float(data["start_balance"]),
            available_balance=float(data["available_balance"]),
            started_at=datetime.fromisoformat(data["started_at"]),
            status=SessionStatus(data["status"]),
            balance_fetched_at=datetime.fromisoformat(data["balance_fetched_at"]),
        )

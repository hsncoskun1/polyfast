"""Balance snapshot — minimum model for startup balance tracking."""

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class BalanceSnapshot:
    """Point-in-time balance reading from the API.

    Attributes:
        total: Total account balance in USD (start balance).
        available: Available balance for trading in USD.
        fetched_at: UTC timestamp when the balance was fetched.
    """
    total: float
    available: float
    fetched_at: datetime

    @classmethod
    def from_api_response(cls, data: dict) -> "BalanceSnapshot":
        """Create a BalanceSnapshot from API response dict.

        Expects keys 'balance' (total) and 'available' with string values.
        """
        return cls(
            total=float(data.get("balance", "0")),
            available=float(data.get("available", "0")),
            fetched_at=datetime.now(timezone.utc),
        )

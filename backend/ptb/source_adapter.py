"""PTB source adapter — abstract interface for PTB data sources.

Adapter pattern: PTB source can change without affecting business logic.
Currently implemented: SSR __NEXT_DATA__ parse.
If a public API endpoint becomes available, only the adapter changes.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class PTBFetchResult:
    """Result of a PTB fetch attempt.

    Attributes:
        success: Whether PTB was successfully fetched.
        value: The openPrice value (None if failed).
        source_name: Adapter source identifier.
        fetched_at: When fetch was performed.
        error: Error message if failed.
    """
    success: bool
    value: float | None
    source_name: str
    fetched_at: datetime
    error: str = ""


class PTBSourceAdapter(ABC):
    """Abstract PTB source adapter.

    Subclasses implement the actual data fetching logic.
    Business logic only depends on this interface, not concrete sources.
    """

    @abstractmethod
    async def fetch_ptb(self, asset: str, event_slug: str) -> PTBFetchResult:
        """Fetch PTB (openPrice) for a given event.

        Args:
            asset: Crypto asset symbol (e.g., "BTC").
            event_slug: Event slug for lookup.

        Returns:
            PTBFetchResult with success/value/error.
        """
        ...

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Identifier for this source adapter."""
        ...

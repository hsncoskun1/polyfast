"""PTB models — Price to Beat record and status.

PTB = openPrice = event başlangıç fiyatı (Chainlink source).
PTB, outcome price / market price / live price DEĞİLDİR — ayrı kavram.

PTB event başından sonuna sabittir:
- Bir kez alındıktan sonra kilitlenir
- Aynı event içinde değişmez
- Event bittiğinde temizlenir, yeni event için yeni PTB alınır
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class PTBStatus(str, Enum):
    """PTB acquisition status."""
    WAITING = "waiting"       # PTB henüz alınmadı
    ACQUIRED = "acquired"     # PTB alındı ve kilitlendi
    FAILED = "failed"         # PTB alınamadı (source error)


@dataclass
class PTBRecord:
    """Price to Beat record for a single event.

    Attributes:
        condition_id: Event condition ID this PTB belongs to.
        asset: Crypto asset symbol (e.g., "BTC").
        ptb_value: The opening price (PTB). None if not yet acquired.
        status: Current PTB status.
        source_name: Where PTB was fetched from.
        acquired_at: When PTB was successfully fetched.
        retry_count: Number of fetch attempts made.
        last_error: Last error message if failed.
    """
    condition_id: str
    asset: str
    ptb_value: float | None = None
    status: PTBStatus = PTBStatus.WAITING
    source_name: str = ""
    acquired_at: datetime | None = None
    retry_count: int = 0
    last_error: str = ""

    @property
    def is_locked(self) -> bool:
        """PTB is locked once successfully acquired."""
        return self.status == PTBStatus.ACQUIRED and self.ptb_value is not None

    @property
    def is_waiting(self) -> bool:
        return self.status == PTBStatus.WAITING

    @property
    def is_failed(self) -> bool:
        return self.status == PTBStatus.FAILED

    def lock(self, value: float, source: str) -> None:
        """Lock PTB with acquired value. Cannot be overwritten after lock.

        Args:
            value: The PTB value (openPrice).
            source: Source name (e.g., "ssr_next_data").

        Raises:
            RuntimeError: If PTB is already locked.
        """
        if self.is_locked:
            raise RuntimeError(
                f"PTB already locked for {self.condition_id}: "
                f"value={self.ptb_value}, source={self.source_name}"
            )
        self.ptb_value = value
        self.status = PTBStatus.ACQUIRED
        self.source_name = source
        self.acquired_at = datetime.now(timezone.utc)

    def record_failure(self, error: str) -> None:
        """Record a failed fetch attempt."""
        self.retry_count += 1
        self.last_error = error
        self.status = PTBStatus.FAILED

    def record_retry(self) -> None:
        """Record a retry attempt (back to waiting)."""
        self.retry_count += 1
        self.status = PTBStatus.WAITING

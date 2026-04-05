"""ClaimManager — claim/redeem lifecycle.

Claim ve redeem TEK DAVRANIS — ayri degil, birlikte ele alinir.
Pozisyon CLOSED olduktan sonra event resolve edilince claim/redeem yapilir.

ClaimRecord ayri model — PositionRecord'a EKLENMEZ.
Cunku claim/redeem pozisyon kapatildiktan SONRA gerceklesir.

Kaybeden tarafta claim/redeem lifecycle BASLATILMAZ.
Sifir degerli tarafta otomatik claim/redeem kaydi ACILMAZ.

Retry: 5s -> 10s -> 20s -> 20s -> 20s... (max 20 deneme)

Global ayar: wait_for_claim_redeem_before_new_trade
  True → bekleyen claim/redeem varsa yeni trade ACILMAZ
  False → claim/redeem beklerken yeni trade acilabilir
  GLOBAL ayar — coin bazli DEGIL.

Post-claim/redeem: balance refresh.
claimed_amount_usdc authoritative — sabitlenir.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from backend.execution.balance_manager import BalanceManager
from backend.domain.startup_guard import HealthIncident, HealthSeverity
from backend.logging_config.service import get_logger, log_event

logger = get_logger("execution.claim")

CLAIM_REDEEM_RETRY_SCHEDULE = [5, 10]  # ilk 2 retry: 5s, 10s
CLAIM_REDEEM_RETRY_STEADY = 20        # 3. ve sonraki: 20s
CLAIM_REDEEM_MAX_RETRIES = 20         # toplam max 20 deneme


class ClaimStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class ClaimRecord:
    """Claim/redeem kaydi.

    Authoritative alanlar:
    - claimed_amount_usdc: basarili claim'de sabitlenir
    - claimed_at: basarili claim zamani
    """
    claim_id: str
    condition_id: str
    position_id: str
    asset: str
    claim_status: ClaimStatus = ClaimStatus.PENDING
    claimed_amount_usdc: float = 0.0
    claimed_at: datetime | None = None
    retry_count: int = 0
    last_error: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_pending(self) -> bool:
        return self.claim_status == ClaimStatus.PENDING

    @property
    def is_success(self) -> bool:
        return self.claim_status == ClaimStatus.SUCCESS

    @property
    def is_failed(self) -> bool:
        return self.claim_status == ClaimStatus.FAILED


class ClaimManager:
    """Claim/redeem lifecycle yoneticisi.

    Paper mode: claim simule edilir.
    Live mode: SDK ile claim (ileride).
    """

    def __init__(
        self,
        balance_manager: BalanceManager,
        paper_mode: bool = True,
    ):
        self._balance = balance_manager
        self._paper_mode = paper_mode
        self._claims: dict[str, ClaimRecord] = {}  # claim_id → record
        self._claim_count: int = 0

    def create_claim(
        self,
        condition_id: str,
        position_id: str,
        asset: str,
    ) -> ClaimRecord:
        """Claim olustur — PENDING state."""
        claim_id = str(uuid.uuid4())
        record = ClaimRecord(
            claim_id=claim_id,
            condition_id=condition_id,
            position_id=position_id,
            asset=asset,
        )
        self._claims[claim_id] = record

        log_event(
            logger, logging.INFO,
            f"Claim created: {asset} pos={position_id}",
            entity_type="claim",
            entity_id=claim_id,
        )
        return record

    async def execute_claim(self, claim_id: str) -> bool:
        """Claim execute et.

        Paper mode: simulated claim (net_position_shares × 1.0 = USDC)
        Live mode: SDK claim (ileride)

        Returns:
            True basarili, False basarisiz.
        """
        record = self._claims.get(claim_id)
        if record is None:
            return False

        if record.is_success:
            return True  # zaten claim edilmis

        record.retry_count += 1

        if self._paper_mode:
            # Paper: simulated claim — $1.00 × shares
            # Gercek claim miktari PositionRecord'dan gelecek
            # Simdilik sabit $1.00 simule ediyoruz
            record.claim_status = ClaimStatus.SUCCESS
            record.claimed_amount_usdc = 1.0  # placeholder
            record.claimed_at = datetime.now(timezone.utc)
            self._claim_count += 1

            # Post-claim balance refresh
            self._balance.add(record.claimed_amount_usdc)

            log_event(
                logger, logging.INFO,
                f"Claim SUCCESS (paper): {record.asset} ${record.claimed_amount_usdc:.2f}",
                entity_type="claim",
                entity_id=claim_id,
            )
            return True
        else:
            # Live mode — SDK claim (ileride)
            record.claim_status = ClaimStatus.FAILED
            record.last_error = "SDK claim not implemented"

            log_event(
                logger, logging.WARNING,
                f"Claim FAILED: {record.asset} — SDK not implemented",
                entity_type="claim",
                entity_id=claim_id,
            )
            return False

    # ─── Query ───

    def has_pending_claims(self) -> bool:
        """Bekleyen claim var mi?"""
        return any(r.is_pending for r in self._claims.values())

    def get_pending_claims(self) -> list[ClaimRecord]:
        return [r for r in self._claims.values() if r.is_pending]

    def get_claim(self, claim_id: str) -> ClaimRecord | None:
        return self._claims.get(claim_id)

    def get_claims_by_position(self, position_id: str) -> list[ClaimRecord]:
        return [r for r in self._claims.values() if r.position_id == position_id]

    @property
    def total_claimed(self) -> int:
        return self._claim_count

    @property
    def pending_count(self) -> int:
        return sum(1 for r in self._claims.values() if r.is_pending)

    def get_health_incidents(self) -> list[HealthIncident]:
        incidents = []
        for r in self._claims.values():
            if r.is_failed and r.retry_count >= CLAIM_REDEEM_MAX_RETRIES:
                incidents.append(HealthIncident(
                    severity=HealthSeverity.WARNING,
                    category="claim",
                    message=f"Claim failed after {r.retry_count} retries: {r.asset}",
                    suggested_action="Manual claim intervention may be needed",
                ))
        return incidents

"""ClaimManager — claim/redeem lifecycle.

Polymarket resmi surec:
- Event resolve olur (oracle sonuc bildirir)
- redeemPositions() cagirilir — HER IKI TARAF ICIN (indexSets=[1,2])
- Kazanan token'lar $1.00 USDC alir
- Kaybeden token'lar $0.00 alir (yakilir, karsiligi sifir)
- Redeem TEK ISLEM — kazanan/kaybeden ayri denemez

Bot davranisi:
- Event bittikten sonra → redeemPositions() cagir (relayer gasless TX)
- Sonuc ne olursa olsun ayni call (kazandik/kaybettik farketmez)
- Kazandiysa → USDC gelir → balance artar
- Kaybettiyse → $0 → balance degismez
- Kullanici hicbir sey yapmaz — 7/24 otomatik

ClaimOutcome:
- REDEEMED_WON: kazanan taraf, USDC alindi
- REDEEMED_LOST: kaybeden taraf, $0 (redeem yapildi ama sifir deger)
- PENDING: henuz redeem edilmedi
- FAILED: redeem basarisiz

Retry: 5s -> 10s -> 20s -> 20s -> 20s... (max 20 deneme)

Global ayar: wait_for_claim_redeem_before_new_trade
  True → bekleyen claim/redeem varsa yeni trade ACILMAZ
  False → claim/redeem beklerken yeni trade acilabilir
  GLOBAL ayar — coin bazli DEGIL.
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


class ClaimOutcome(str, Enum):
    """Redeem sonucu — kazanan mi kaybeden mi."""
    REDEEMED_WON = "redeemed_won"      # kazanan taraf, USDC alindi
    REDEEMED_LOST = "redeemed_lost"    # kaybeden taraf, $0 (redeem yapildi)
    PENDING = "pending"                 # henuz redeem edilmedi
    FAILED = "failed"                   # redeem basarisiz


@dataclass
class ClaimRecord:
    """Claim/redeem kaydi.

    Polymarket'te redeem TEK ISLEM — kazanan/kaybeden ayri denemez.
    redeemPositions() her iki outcome'u yakar.
    Kazanan taraf USDC alir, kaybeden taraf $0 alir.

    Authoritative alanlar:
    - claimed_amount_usdc: redeem sonrasi sabitlenir (kazandiysa >0, kaybettiyse 0)
    - claimed_at: basarili redeem zamani
    - outcome: REDEEMED_WON veya REDEEMED_LOST
    """
    claim_id: str
    condition_id: str
    position_id: str
    asset: str
    side: str = ""  # UP veya DOWN — hangi taraftaydik
    claim_status: ClaimStatus = ClaimStatus.PENDING
    outcome: ClaimOutcome = ClaimOutcome.PENDING
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
        side: str = "",
    ) -> ClaimRecord:
        """Redeem kaydi olustur — PENDING state.

        Event resolve olduktan sonra cagirilir.
        Kazanan/kaybeden farketmez — redeemPositions() her iki tarafi yakar.
        """
        claim_id = str(uuid.uuid4())
        record = ClaimRecord(
            claim_id=claim_id,
            condition_id=condition_id,
            position_id=position_id,
            asset=asset,
            side=side,
        )
        self._claims[claim_id] = record

        log_event(
            logger, logging.INFO,
            f"Claim created: {asset} pos={position_id}",
            entity_type="claim",
            entity_id=claim_id,
        )
        return record

    async def execute_redeem(
        self,
        claim_id: str,
        won: bool = True,
        payout_amount: float = 0.0,
    ) -> bool:
        """Redeem execute et — redeemPositions() settlement.

        Polymarket'te redeem TEK ISLEM:
        - redeemPositions(indexSets=[1,2]) her iki outcome'u yakar
        - Kazanan token $1.00 payout, kaybeden token $0.00
        - Bu method sonucu kaydeder

        Paper mode: simulated redeem
        Live mode: relayer gasless TX (ileride)

        Args:
            claim_id: ClaimRecord ID
            won: Kazandik mi? True=kazandik, False=kaybettik
            payout_amount: Kazandiysa USDC miktari, kaybettiyse 0.0

        Returns:
            True basarili, False basarisiz.
        """
        record = self._claims.get(claim_id)
        if record is None:
            return False

        if record.is_success:
            return True  # zaten redeem edilmis

        record.retry_count += 1

        if self._paper_mode:
            record.claim_status = ClaimStatus.SUCCESS
            record.claimed_at = datetime.now(timezone.utc)
            self._claim_count += 1

            if won:
                record.outcome = ClaimOutcome.REDEEMED_WON
                record.claimed_amount_usdc = payout_amount
                self._balance.add(payout_amount)

                log_event(
                    logger, logging.INFO,
                    f"Redeem WON (paper): {record.asset} ${payout_amount:.2f}",
                    entity_type="claim",
                    entity_id=claim_id,
                )
            else:
                record.outcome = ClaimOutcome.REDEEMED_LOST
                record.claimed_amount_usdc = 0.0
                # Balance degismez — kaybeden taraf $0

                log_event(
                    logger, logging.INFO,
                    f"Redeem LOST (paper): {record.asset} $0.00",
                    entity_type="claim",
                    entity_id=claim_id,
                )

            return True
        else:
            # Live mode — relayer gasless TX (ileride)
            record.claim_status = ClaimStatus.FAILED
            record.last_error = "Relayer redeem not implemented"

            log_event(
                logger, logging.WARNING,
                f"Redeem FAILED: {record.asset} — relayer not implemented",
                entity_type="claim",
                entity_id=claim_id,
            )
            return False

    # Backward compat
    async def execute_claim(self, claim_id: str) -> bool:
        """Backward compat — execute_redeem(won=True) cagirir."""
        return await self.execute_redeem(claim_id, won=True, payout_amount=1.0)

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

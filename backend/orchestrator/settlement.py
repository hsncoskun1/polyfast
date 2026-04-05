"""Settlement Orchestration — event resolve sonrasi otomatik redeem.

Akis:
1. Pozisyon CLOSED + event bitmis → settlement adayi
2. Resolved/redeemable mi kontrol et (event_end_ts gecmis YETMEZ)
3. Redeemable ise → ClaimRecord olustur + execute_redeem
4. Payout sonucu authoritative kayit: claimed_amount_usdc
5. Post-redeem balance refresh

ONEMLI:
- event_end_ts gecmis olmasi = resolved demek DEGIL
- Settlement baslatmadan once resolved/redeemable durumu NET dogrulanir
- LIVE_SETTLEMENT_ENABLED=False oldukca gercek TX cikmaz
- Paper mode'da simulated redeem yapilir
"""

import logging
import time
from datetime import datetime, timezone

from backend.execution.claim_manager import ClaimManager, ClaimOutcome
from backend.execution.position_tracker import PositionTracker
from backend.execution.position_record import PositionState
from backend.execution.relayer_client_wrapper import RelayerClientWrapper
from backend.logging_config.service import get_logger, log_event

logger = get_logger("orchestrator.settlement")

SLOT_SECONDS = 300


class SettlementOrchestrator:
    """Event resolve sonrasi otomatik settlement.

    Closed pozisyonlari tarar, resolved olanlari redeem eder.
    Paper mode: simulated. Live mode: relayer guard ile kapali.
    """

    def __init__(
        self,
        tracker: PositionTracker,
        claim_manager: ClaimManager,
        relayer: RelayerClientWrapper,
        paper_mode: bool = True,
    ):
        self._tracker = tracker
        self._claims = claim_manager
        self._relayer = relayer
        self._paper_mode = paper_mode
        self._settlement_count: int = 0

    async def process_settlements(self) -> int:
        """Tum closed pozisyonlari tara, resolved olanlari settle et.

        Returns:
            Settle edilen pozisyon sayisi.
        """
        settled = 0
        closed_positions = [
            p for p in self._tracker.get_all_positions()
            if p.is_closed and p.closed_at is not None
        ]

        for pos in closed_positions:
            # Zaten claim/redeem edilmis mi?
            existing_claims = self._claims.get_claims_by_position(pos.position_id)
            if any(c.is_success for c in existing_claims):
                continue  # zaten settled

            # Resolved/redeemable mi?
            is_redeemable = await self._check_resolved(pos.condition_id)
            if not is_redeemable:
                continue

            # Settle et
            success = await self._settle_position(pos)
            if success:
                settled += 1

        return settled

    async def _check_resolved(self, condition_id: str) -> bool:
        """Event resolved ve redeemable mi?

        event_end_ts gecmis olmasi YETMEZ.
        Relayer wrapper ile resolved kontrol yapilir.
        """
        if self._paper_mode:
            # Paper: event_end_ts gecmisse resolved varsay
            now = time.time()
            slot_start = (int(now) // SLOT_SECONDS) * SLOT_SECONDS
            # Basit kontrol: su anki slot'tan once olusturulmus pozisyon → resolved
            return True  # paper placeholder

        return await self._relayer.check_redeemable(condition_id)

    async def _settle_position(self, pos) -> bool:
        """Tek pozisyonu settle et."""
        # ClaimRecord olustur
        claim = self._claims.create_claim(
            condition_id=pos.condition_id,
            position_id=pos.position_id,
            asset=pos.asset,
            side=pos.side,
        )

        if self._paper_mode:
            # Paper: kazandik mi kaybettik mi simule et
            # Gercek bilgi event resolution'dan gelir
            # Paper'da basit varsayim: pozisyon kar'da kapandiysa kazandik
            won = pos.net_realized_pnl > 0

            if won:
                # Kazanan: net_position_shares × $1.00
                payout = pos.net_position_shares * 1.0
            else:
                payout = 0.0

            success = await self._claims.execute_redeem(
                claim.claim_id, won=won, payout_amount=round(payout, 4),
            )

            if success:
                self._settlement_count += 1
                log_event(
                    logger, logging.INFO,
                    f"Settlement: {pos.asset} {pos.side} "
                    f"outcome={'WON' if won else 'LOST'} "
                    f"payout=${payout:.4f}",
                    entity_type="settlement",
                    entity_id=pos.position_id,
                )

            return success
        else:
            # Live: relayer gasless TX (guard ile kapali)
            result = await self._relayer.redeem_positions(
                pos.condition_id, pos.side,
            )

            if result.get("success"):
                payout = result.get("payout_usdc", 0.0)
                won = payout > 0
                await self._claims.execute_redeem(
                    claim.claim_id, won=won, payout_amount=payout,
                )
                self._settlement_count += 1
                return True

            # Basarisiz — retry gerekli
            claim.claim_status = "failed"
            claim.last_error = result.get("error", "unknown")
            return False

    @property
    def settlement_count(self) -> int:
        return self._settlement_count

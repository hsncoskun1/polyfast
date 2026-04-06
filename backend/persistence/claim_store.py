"""ClaimStore — SQLite persistence for ClaimRecord.

Runtime memory AUTHORITATIVE — SQLite durable backup.
Write: claim state degisiminde (create, outcome change, retry).
Read: sadece startup restore'da.
Write failure state authority'yi kaydirmaz — health/log uretir.
"""

import logging
from datetime import datetime, timezone

from backend.persistence.database import get_db
from backend.execution.claim_manager import ClaimRecord, ClaimStatus, ClaimOutcome
from backend.logging_config.service import get_logger, log_event

logger = get_logger("persistence.claim_store")


class ClaimStore:
    """Claim persistence — save/load."""

    async def save(self, claim: ClaimRecord) -> bool:
        """Claim kaydet veya guncelle (upsert)."""
        try:
            db = await get_db()
            await db.execute(
                """INSERT OR REPLACE INTO claims (
                    claim_id, condition_id, position_id, asset, side,
                    claim_status, outcome, claimed_amount_usdc, claimed_at,
                    retry_count, last_error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    claim.claim_id, claim.condition_id, claim.position_id,
                    claim.asset, claim.side,
                    claim.claim_status.value, claim.outcome.value,
                    claim.claimed_amount_usdc,
                    claim.claimed_at.isoformat() if claim.claimed_at else None,
                    claim.retry_count, claim.last_error,
                    claim.created_at.isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await db.commit()
            return True
        except Exception as e:
            log_event(
                logger, logging.ERROR,
                f"Claim save failed: {claim.claim_id} — {e}",
                entity_type="persistence",
                entity_id=claim.claim_id,
            )
            return False

    async def load_all(self) -> list[ClaimRecord]:
        """Tum claim'leri yukle (startup restore)."""
        try:
            db = await get_db()
            cursor = await db.execute("SELECT * FROM claims ORDER BY created_at")
            rows = await cursor.fetchall()
            return [self._row_to_record(row) for row in rows]
        except Exception as e:
            log_event(
                logger, logging.ERROR,
                f"Claim load failed: {e}",
                entity_type="persistence",
                entity_id="load_all",
            )
            return []

    async def load_pending(self) -> list[ClaimRecord]:
        """Pending claim'leri yukle."""
        try:
            db = await get_db()
            cursor = await db.execute(
                "SELECT * FROM claims WHERE claim_status = 'pending' ORDER BY created_at"
            )
            rows = await cursor.fetchall()
            return [self._row_to_record(row) for row in rows]
        except Exception as e:
            log_event(
                logger, logging.ERROR,
                f"Claim load_pending failed: {e}",
                entity_type="persistence",
                entity_id="load_pending",
            )
            return []

    def _row_to_record(self, row) -> ClaimRecord:
        """SQLite row -> ClaimRecord."""
        return ClaimRecord(
            claim_id=row["claim_id"],
            condition_id=row["condition_id"],
            position_id=row["position_id"],
            asset=row["asset"],
            side=row["side"],
            claim_status=ClaimStatus(row["claim_status"]),
            outcome=ClaimOutcome(row["outcome"]),
            claimed_amount_usdc=row["claimed_amount_usdc"],
            claimed_at=datetime.fromisoformat(row["claimed_at"]) if row["claimed_at"] else None,
            retry_count=row["retry_count"],
            last_error=row["last_error"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

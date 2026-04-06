"""PTBStore — SQLite persistence for PTB cache.

Save: lock() basarili oldugunda.
Clear: event bittiginde (deterministic: CLOSED/EXPIRED status).
Read: startup restore'da — aktif event PTB'si korunur.
"""

import logging
from datetime import datetime, timezone

from backend.persistence.database import get_db
from backend.ptb.models import PTBRecord, PTBStatus
from backend.logging_config.service import get_logger, log_event

logger = get_logger("persistence.ptb_store")


class PTBStore:

    async def save(self, record: PTBRecord) -> bool:
        try:
            db = await get_db()
            await db.execute(
                """INSERT OR REPLACE INTO ptb_cache (
                    condition_id, asset, ptb_value, status, source_name,
                    acquired_at, retry_count, last_error, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.condition_id, record.asset, record.ptb_value,
                    record.status.value, record.source_name,
                    record.acquired_at.isoformat() if record.acquired_at else None,
                    record.retry_count, record.last_error,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await db.commit()
            return True
        except Exception as e:
            log_event(logger, logging.ERROR,
                      f"PTB save failed: {record.condition_id} — {e}",
                      entity_type="persistence", entity_id=record.condition_id)
            return False

    async def load_locked(self) -> list[PTBRecord]:
        """Sadece ACQUIRED (locked) PTB'leri yukle."""
        try:
            db = await get_db()
            cursor = await db.execute(
                "SELECT * FROM ptb_cache WHERE status = 'acquired'"
            )
            rows = await cursor.fetchall()
            return [self._row_to_record(row) for row in rows]
        except Exception as e:
            log_event(logger, logging.ERROR,
                      f"PTB load failed: {e}",
                      entity_type="persistence", entity_id="load_locked")
            return []

    async def clear_event(self, condition_id: str) -> bool:
        """Bitmis event PTB'sini temizle.

        Temizleme kriteri: event status CLOSED veya EXPIRED.
        Bu metod deterministic — sadece bitmis event icin cagirilir.
        """
        try:
            db = await get_db()
            await db.execute(
                "DELETE FROM ptb_cache WHERE condition_id = ?",
                (condition_id,),
            )
            await db.commit()
            return True
        except Exception as e:
            log_event(logger, logging.ERROR,
                      f"PTB clear failed: {condition_id} — {e}",
                      entity_type="persistence", entity_id=condition_id)
            return False

    def _row_to_record(self, row) -> PTBRecord:
        rec = PTBRecord(
            condition_id=row["condition_id"],
            asset=row["asset"],
            status=PTBStatus(row["status"]),
            source_name=row["source_name"],
            retry_count=row["retry_count"],
            last_error=row["last_error"],
        )
        if row["ptb_value"] is not None:
            rec.ptb_value = row["ptb_value"]
        if row["acquired_at"]:
            rec.acquired_at = datetime.fromisoformat(row["acquired_at"])
        return rec

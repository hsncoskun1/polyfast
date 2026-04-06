"""RegistryStore — SQLite persistence for EventRegistry.

Save: anlamli status transition'larda (DISCOVERED->ACTIVE, ACTIVE->EXPIRED vb).
Read: startup restore'da.
Gurultulu ara state yazimi YOK.
"""

import logging
from datetime import datetime, timezone

from backend.persistence.database import get_db
from backend.registry.models import RegistryRecord, EventStatus
from backend.logging_config.service import get_logger, log_event

logger = get_logger("persistence.registry_store")


class RegistryStore:

    async def save(self, record: RegistryRecord) -> bool:
        try:
            db = await get_db()
            await db.execute(
                """INSERT OR REPLACE INTO registry_records (
                    condition_id, event_id, asset, question, slug, status,
                    first_seen_at, last_seen_at, status_changed_at,
                    end_date, has_open_position, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.condition_id, record.event_id, record.asset,
                    record.question, record.slug, record.status.value,
                    record.first_seen_at.isoformat(),
                    record.last_seen_at.isoformat(),
                    record.status_changed_at.isoformat(),
                    record.end_date.isoformat() if record.end_date else None,
                    int(record.has_open_position),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await db.commit()
            return True
        except Exception as e:
            log_event(logger, logging.ERROR,
                      f"Registry save failed: {record.condition_id} — {e}",
                      entity_type="persistence", entity_id=record.condition_id)
            return False

    async def load_all(self) -> list[RegistryRecord]:
        try:
            db = await get_db()
            cursor = await db.execute("SELECT * FROM registry_records ORDER BY first_seen_at")
            rows = await cursor.fetchall()
            return [self._row_to_record(row) for row in rows]
        except Exception as e:
            log_event(logger, logging.ERROR,
                      f"Registry load failed: {e}",
                      entity_type="persistence", entity_id="load_all")
            return []

    async def load_active(self) -> list[RegistryRecord]:
        try:
            db = await get_db()
            cursor = await db.execute(
                "SELECT * FROM registry_records WHERE status NOT IN ('closed', 'expired')"
            )
            rows = await cursor.fetchall()
            return [self._row_to_record(row) for row in rows]
        except Exception as e:
            log_event(logger, logging.ERROR,
                      f"Registry load_active failed: {e}",
                      entity_type="persistence", entity_id="load_active")
            return []

    def _row_to_record(self, row) -> RegistryRecord:
        return RegistryRecord(
            event_id=row["event_id"],
            condition_id=row["condition_id"],
            asset=row["asset"],
            question=row["question"],
            slug=row["slug"],
            status=EventStatus(row["status"]),
            first_seen_at=datetime.fromisoformat(row["first_seen_at"]),
            last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
            status_changed_at=datetime.fromisoformat(row["status_changed_at"]),
            end_date=datetime.fromisoformat(row["end_date"]) if row["end_date"] else None,
            has_open_position=bool(row["has_open_position"]),
        )

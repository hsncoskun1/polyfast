"""PositionStore — SQLite persistence for PositionRecord.

Runtime memory AUTHORITATIVE — SQLite durable backup.
Write: state transition / onemli alan degisiminde.
Read: sadece startup restore'da.
Write failure state authority'yi kaydirmaz — health/log uretir.
"""

import json
import logging
from datetime import datetime, timezone

from backend.persistence.database import get_db
from backend.execution.position_record import PositionRecord, PositionState
from backend.execution.close_reason import CloseReason
from backend.logging_config.service import get_logger, log_event

logger = get_logger("persistence.position_store")


class PositionStore:
    """Position persistence — save/load/update."""

    async def save(self, pos: PositionRecord) -> bool:
        """Position kaydet veya guncelle (upsert)."""
        try:
            db = await get_db()
            await db.execute(
                """INSERT OR REPLACE INTO positions (
                    position_id, asset, side, condition_id, token_id, state, created_at,
                    requested_amount_usd, fill_price, gross_fill_shares, entry_fee_shares,
                    net_position_shares, fee_rate, opened_at,
                    exit_fill_price, exit_gross_usdc, actual_exit_fee_usdc, net_exit_usdc,
                    net_realized_pnl, close_reason, close_trigger_set, close_triggered_at,
                    close_requested_price, closed_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    pos.position_id, pos.asset, pos.side, pos.condition_id, pos.token_id,
                    pos.state.value, pos.created_at.isoformat(),
                    pos.requested_amount_usd, pos.fill_price, pos.gross_fill_shares,
                    pos.entry_fee_shares, pos.net_position_shares, pos.fee_rate,
                    pos.opened_at.isoformat() if pos.opened_at else None,
                    pos.exit_fill_price, pos.exit_gross_usdc, pos.actual_exit_fee_usdc,
                    pos.net_exit_usdc, pos.net_realized_pnl,
                    pos.close_reason.value if pos.close_reason else None,
                    json.dumps(pos.close_trigger_set),
                    pos.close_triggered_at.isoformat() if pos.close_triggered_at else None,
                    pos.close_requested_price,
                    pos.closed_at.isoformat() if pos.closed_at else None,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await db.commit()
            return True
        except Exception as e:
            log_event(
                logger, logging.ERROR,
                f"Position save failed: {pos.position_id} — {e}",
                entity_type="persistence",
                entity_id=pos.position_id,
            )
            return False

    async def load_all(self) -> list[PositionRecord]:
        """Tum pozisyonlari yukle (startup restore)."""
        try:
            db = await get_db()
            cursor = await db.execute("SELECT * FROM positions ORDER BY created_at")
            rows = await cursor.fetchall()
            return [self._row_to_record(row) for row in rows]
        except Exception as e:
            log_event(
                logger, logging.ERROR,
                f"Position load failed: {e}",
                entity_type="persistence",
                entity_id="load_all",
            )
            return []

    async def load_non_terminal(self) -> list[PositionRecord]:
        """Terminal olmayan (acik + closing) pozisyonlari yukle."""
        try:
            db = await get_db()
            cursor = await db.execute(
                "SELECT * FROM positions WHERE state NOT IN ('closed') ORDER BY created_at"
            )
            rows = await cursor.fetchall()
            return [self._row_to_record(row) for row in rows]
        except Exception as e:
            log_event(
                logger, logging.ERROR,
                f"Position load_non_terminal failed: {e}",
                entity_type="persistence",
                entity_id="load_non_terminal",
            )
            return []

    def _row_to_record(self, row) -> PositionRecord:
        """SQLite row -> PositionRecord."""
        close_reason = None
        if row["close_reason"]:
            try:
                close_reason = CloseReason(row["close_reason"])
            except ValueError:
                close_reason = None

        trigger_set = []
        if row["close_trigger_set"]:
            try:
                trigger_set = json.loads(row["close_trigger_set"])
            except (json.JSONDecodeError, TypeError):
                trigger_set = []

        rec = PositionRecord(
            position_id=row["position_id"],
            asset=row["asset"],
            side=row["side"],
            condition_id=row["condition_id"],
            token_id=row["token_id"],
            state=PositionState(row["state"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            requested_amount_usd=row["requested_amount_usd"],
            fill_price=row["fill_price"],
            gross_fill_shares=row["gross_fill_shares"],
            entry_fee_shares=row["entry_fee_shares"],
            net_position_shares=row["net_position_shares"],
            fee_rate=row["fee_rate"],
            opened_at=datetime.fromisoformat(row["opened_at"]) if row["opened_at"] else None,
            exit_fill_price=row["exit_fill_price"],
            exit_gross_usdc=row["exit_gross_usdc"],
            actual_exit_fee_usdc=row["actual_exit_fee_usdc"],
            net_exit_usdc=row["net_exit_usdc"],
            net_realized_pnl=row["net_realized_pnl"],
            close_reason=close_reason,
            close_trigger_set=trigger_set,
            close_triggered_at=datetime.fromisoformat(row["close_triggered_at"]) if row["close_triggered_at"] else None,
            close_requested_price=row["close_requested_price"],
            closed_at=datetime.fromisoformat(row["closed_at"]) if row["closed_at"] else None,
        )
        return rec

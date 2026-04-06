"""SettingsStoreDB — SQLite persistence for CoinSettings.

Save: set() cagirildiginda (kullanici ayar degistirdi).
Read: sadece startup restore'da.
Write failure = health/log, memory authoritative.
"""

import logging
from datetime import datetime, timezone

from backend.persistence.database import get_db
from backend.settings.coin_settings import CoinSettings, SideMode
from backend.logging_config.service import get_logger, log_event

logger = get_logger("persistence.settings_store")


class SettingsStoreDB:

    async def save(self, settings: CoinSettings) -> bool:
        try:
            db = await get_db()
            await db.execute(
                """INSERT OR REPLACE INTO coin_settings (
                    coin, coin_enabled, side_mode, delta_threshold,
                    price_min, price_max, spread_max, time_min, time_max,
                    event_max, order_amount, reactivate_on_return, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    settings.coin, int(settings.coin_enabled),
                    settings.side_mode.value, settings.delta_threshold,
                    settings.price_min, settings.price_max, settings.spread_max,
                    settings.time_min, settings.time_max, settings.event_max,
                    settings.order_amount, int(settings.reactivate_on_return),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await db.commit()
            return True
        except Exception as e:
            log_event(logger, logging.ERROR,
                      f"Settings save failed: {settings.coin} — {e}",
                      entity_type="persistence", entity_id=settings.coin)
            return False

    async def load_all(self) -> list[CoinSettings]:
        try:
            db = await get_db()
            cursor = await db.execute("SELECT * FROM coin_settings ORDER BY coin")
            rows = await cursor.fetchall()
            return [self._row_to_settings(row) for row in rows]
        except Exception as e:
            log_event(logger, logging.ERROR,
                      f"Settings load failed: {e}",
                      entity_type="persistence", entity_id="load_all")
            return []

    def _row_to_settings(self, row) -> CoinSettings:
        return CoinSettings(
            coin=row["coin"],
            coin_enabled=bool(row["coin_enabled"]),
            side_mode=SideMode(row["side_mode"]),
            delta_threshold=row["delta_threshold"],
            price_min=row["price_min"],
            price_max=row["price_max"],
            spread_max=row["spread_max"],
            time_min=row["time_min"],
            time_max=row["time_max"],
            event_max=row["event_max"],
            order_amount=row["order_amount"],
            reactivate_on_return=bool(row["reactivate_on_return"]),
        )

"""In-memory coin settings store with optional SQLite persistence.

CRUD: get/set/delete per coin.
Memory authoritative — SQLite durable backup.
Persist hook: set() cagirildiginda otomatik save.
"""

import asyncio
from backend.settings.coin_settings import CoinSettings


class SettingsStore:
    """In-memory coin settings store."""

    def __init__(self, db_store=None):
        self._settings: dict[str, CoinSettings] = {}
        self._db_store = db_store  # SettingsStoreDB (optional)

    def get(self, coin: str) -> CoinSettings | None:
        return self._settings.get(coin.upper())

    def set(self, settings: CoinSettings) -> None:
        self._settings[settings.coin.upper()] = settings
        self._persist(settings)

    def delete(self, coin: str) -> None:
        """Coin ayarını sil."""
        self._settings.pop(coin.upper(), None)

    def get_all(self) -> list[CoinSettings]:
        """Tüm coin ayarlarını getir."""
        return list(self._settings.values())

    def get_eligible_coins(self) -> list[CoinSettings]:
        """Trade-eligible coinlerin ayarlarını getir."""
        return [s for s in self._settings.values() if s.is_trade_eligible]

    def get_configured_coins(self) -> list[str]:
        """Ayarı tamamlanmış coin listesi."""
        return [s.coin for s in self._settings.values() if s.is_configured]

    def get_enabled_coins(self) -> list[str]:
        """Enabled coin listesi (configured olmayabilir)."""
        return [s.coin for s in self._settings.values() if s.coin_enabled]

    def toggle_coin(self, symbol: str) -> CoinSettings | None:
        """Coin enabled/disabled toggle. Yoksa None döner.

        set() çağrısı ile in-memory + persist zinciri otomatik tetiklenir.
        İleride explicit set endpoint'e geçişi engellemez.
        """
        settings = self.get(symbol)
        if settings is None:
            return None
        settings.coin_enabled = not settings.coin_enabled
        self.set(settings)  # in-memory + _persist() → SQLite
        return settings

    @property
    def total_count(self) -> int:
        return len(self._settings)

    @property
    def eligible_count(self) -> int:
        return len(self.get_eligible_coins())

    def _persist(self, settings: CoinSettings) -> None:
        if self._db_store is None:
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._db_store.save(settings))
        except RuntimeError:
            pass

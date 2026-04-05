"""In-memory coin settings store.

CRUD: get/set/delete per coin.
Persistence (SQLite) sonraki fazda eklenecek.
Coin ayarı kalıcı — coin listeden çıksa bile ayar saklanır.
Coin geri geldiğinde reactivate_on_return=True ise otomatik devam eder.
"""

from backend.settings.coin_settings import CoinSettings


class SettingsStore:
    """In-memory coin settings store."""

    def __init__(self):
        self._settings: dict[str, CoinSettings] = {}

    def get(self, coin: str) -> CoinSettings | None:
        """Coin ayarını getir. Yoksa None."""
        return self._settings.get(coin.upper())

    def set(self, settings: CoinSettings) -> None:
        """Coin ayarını kaydet/güncelle."""
        self._settings[settings.coin.upper()] = settings

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

    @property
    def total_count(self) -> int:
        return len(self._settings)

    @property
    def eligible_count(self) -> int:
        return len(self.get_eligible_coins())

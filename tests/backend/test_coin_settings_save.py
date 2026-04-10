"""Tests for FAZ4-5: Coin settings save endpoint.

Coverage:
- save new coin / existing coin
- partial update (only sent fields change)
- coin_enabled ignored
- persist/reload cycle
- configured calculation
- missing_fields response
- validation: side_mode enum, negative values, range checks
- eligibility after save
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.settings.coin_settings import CoinSettings, SideMode
from backend.settings.settings_store import SettingsStore


# ── Helpers ──────────────────────────────────────────────────────

def _make_configured(coin: str, enabled: bool = True) -> CoinSettings:
    return CoinSettings(
        coin=coin,
        coin_enabled=enabled,
        side_mode=SideMode.DOMINANT_ONLY,
        delta_threshold=0.50,
        price_min=51,
        price_max=85,
        spread_max=3.0,
        time_min=30,
        time_max=270,
        event_max=1,
        order_amount=5.0,
    )


# ╔══════════════════════════════════════════════════════════════╗
# ║  update_settings() unit tests                                 ║
# ╚══════════════════════════════════════════════════════════════╝

class TestUpdateSettings:

    def test_save_new_coin(self):
        """Olmayan coin → yeni CoinSettings oluşur, coin_enabled=false."""
        store = SettingsStore()
        result = store.update_settings("BTC", delta_threshold=0.50, order_amount=5.0)
        assert result.coin == "BTC"
        assert result.coin_enabled is False  # default
        assert result.delta_threshold == 0.50
        assert result.order_amount == 5.0

    def test_save_existing(self):
        """Mevcut coin → field'lar güncellenir."""
        store = SettingsStore()
        store.set(_make_configured("BTC"))
        result = store.update_settings("BTC", delta_threshold=1.0)
        assert result.delta_threshold == 1.0
        assert result.price_min == 51  # değişmedi

    def test_partial_update(self):
        """Sadece gönderilen field değişir, diğerleri korunur."""
        store = SettingsStore()
        store.set(_make_configured("ETH"))
        original = store.get("ETH")
        result = store.update_settings("ETH", spread_max=5.0)
        assert result.spread_max == 5.0
        assert result.delta_threshold == original.delta_threshold
        assert result.price_min == original.price_min
        assert result.order_amount == original.order_amount

    def test_coin_enabled_ignored(self):
        """Body'de coin_enabled gelse bile ignore edilir."""
        store = SettingsStore()
        store.set(_make_configured("BTC", enabled=False))
        result = store.update_settings("BTC", coin_enabled=True, delta_threshold=1.0)
        assert result.coin_enabled is False  # değişmedi!
        assert result.delta_threshold == 1.0

    def test_coin_field_ignored(self):
        """Body'de coin gelse bile ignore edilir."""
        store = SettingsStore()
        store.set(_make_configured("BTC"))
        result = store.update_settings("BTC", coin="ETH")
        assert result.coin == "BTC"  # değişmedi

    def test_case_insensitive(self):
        """Lowercase symbol normalize edilir."""
        store = SettingsStore()
        result = store.update_settings("btc", delta_threshold=0.50)
        assert result.coin == "BTC"
        assert store.get("BTC") is not None

    def test_side_mode_update(self):
        """side_mode güncellenebilir."""
        store = SettingsStore()
        store.set(_make_configured("BTC"))
        result = store.update_settings("BTC", side_mode=SideMode.UP_ONLY)
        assert result.side_mode == SideMode.UP_ONLY


# ╔══════════════════════════════════════════════════════════════╗
# ║  Configured / missing fields tests                            ║
# ╚══════════════════════════════════════════════════════════════╝

class TestConfiguredStatus:

    def test_configured_after_full_save(self):
        """Tüm zorunlu alanlar dolu + enabled → is_configured=true."""
        store = SettingsStore()
        store.set(CoinSettings(coin="BTC", coin_enabled=True))
        result = store.update_settings(
            "BTC",
            delta_threshold=0.50, price_min=51, price_max=85,
            spread_max=3.0, time_min=30, time_max=270,
            event_max=1, order_amount=5.0,
        )
        assert result.is_configured is True

    def test_not_configured_partial(self):
        """Eksik alanlarla save → is_configured=false."""
        store = SettingsStore()
        result = store.update_settings("BTC", delta_threshold=0.50)
        assert result.is_configured is False

    def test_configured_without_enable(self):
        """Alanlar dolu + coin_enabled=false → is_configured=true (configured ≠ enabled)."""
        store = SettingsStore()
        result = store.update_settings(
            "BTC",
            delta_threshold=0.50, price_min=51, price_max=85,
            time_min=30, time_max=270,
            event_max=1, order_amount=5.0,
        )
        assert result.coin_enabled is False
        assert result.is_configured is True   # ayarlar tamam
        assert result.is_trade_eligible is False  # ama enable değil → eligible değil

    def test_configured_without_spread(self):
        """Spread governance kapalı (spread_max=0) → is_configured=true."""
        store = SettingsStore()
        result = store.update_settings(
            "BTC",
            delta_threshold=0.50, price_min=51, price_max=85,
            time_min=30, time_max=270,
            event_max=1, order_amount=5.0,
            # spread_max gönderilmiyor → 0 kalır
        )
        assert result.spread_max == 0.0
        assert result.is_configured is True  # spread bloklamamalı


# ╔══════════════════════════════════════════════════════════════╗
# ║  Eligibility tests                                            ║
# ╚══════════════════════════════════════════════════════════════╝

class TestEligibilityAfterSave:

    def test_eligible_after_configure_and_enable(self):
        """configured + enabled → eligible."""
        store = SettingsStore()
        store.set(CoinSettings(coin="BTC", coin_enabled=True))
        store.update_settings(
            "BTC",
            delta_threshold=0.50, price_min=51, price_max=85,
            spread_max=3.0, time_min=30, time_max=270,
            event_max=1, order_amount=5.0,
        )
        assert store.get("BTC").is_trade_eligible is True

    def test_not_eligible_configured_but_disabled(self):
        """configured but disabled → not eligible."""
        store = SettingsStore()
        store.update_settings(
            "BTC",
            delta_threshold=0.50, price_min=51, price_max=85,
            spread_max=3.0, time_min=30, time_max=270,
            event_max=1, order_amount=5.0,
        )
        assert store.get("BTC").coin_enabled is False
        assert store.get("BTC").is_trade_eligible is False


# ╔══════════════════════════════════════════════════════════════╗
# ║  Persist/reload tests                                         ║
# ╚══════════════════════════════════════════════════════════════╝

class TestSettingsPersistReload:

    @pytest.mark.asyncio
    async def test_save_persist_reload(self):
        """Save → persist → reload → state korunmuş."""
        store1 = SettingsStore()
        store1.update_settings(
            "BTC",
            delta_threshold=0.75, price_min=55, price_max=90,
            spread_max=2.5, time_min=45, time_max=250,
            event_max=2, order_amount=10.0,
        )

        saved: list[CoinSettings] = []
        mock_db = MagicMock()
        mock_db.save = AsyncMock(side_effect=lambda s: saved.append(s) or True)
        mock_db.load_all = AsyncMock(return_value=saved)

        for s in store1.get_all():
            await mock_db.save(s)

        store2 = SettingsStore(db_store=mock_db)
        for s in await mock_db.load_all():
            store2.set(s)

        btc = store2.get("BTC")
        assert btc is not None
        assert btc.delta_threshold == 0.75
        assert btc.price_min == 55
        assert btc.price_max == 90
        assert btc.order_amount == 10.0
        assert btc.coin_enabled is False  # default korunmuş


# ╔══════════════════════════════════════════════════════════════╗
# ║  Validation tests (Pydantic model)                            ║
# ╚══════════════════════════════════════════════════════════════╝

class TestValidation:

    def test_valid_side_mode(self):
        """Geçerli side_mode kabul edilir."""
        from backend.api.coin import CoinSettingsRequest
        req = CoinSettingsRequest(side_mode="dominant_only")
        assert req.side_mode == "dominant_only"

    def test_invalid_side_mode(self):
        """Geçersiz side_mode → ValidationError."""
        from backend.api.coin import CoinSettingsRequest
        with pytest.raises(Exception):
            CoinSettingsRequest(side_mode="invalid_mode")

    def test_negative_delta(self):
        """Negatif delta_threshold → ValidationError."""
        from backend.api.coin import CoinSettingsRequest
        with pytest.raises(Exception):
            CoinSettingsRequest(delta_threshold=-1.0)

    def test_negative_price_min(self):
        """Negatif price_min → ValidationError."""
        from backend.api.coin import CoinSettingsRequest
        with pytest.raises(Exception):
            CoinSettingsRequest(price_min=-5)

    def test_negative_order_amount(self):
        """Negatif order_amount → ValidationError."""
        from backend.api.coin import CoinSettingsRequest
        with pytest.raises(Exception):
            CoinSettingsRequest(order_amount=-10.0)

    def test_zero_values_accepted(self):
        """Sıfır değerler kabul edilir (ayarlanmamış anlamına gelir)."""
        from backend.api.coin import CoinSettingsRequest
        req = CoinSettingsRequest(delta_threshold=0.0, price_min=0)
        assert req.delta_threshold == 0.0
        assert req.price_min == 0


# ╔══════════════════════════════════════════════════════════════╗
# ║  Missing fields helper test                                   ║
# ╚══════════════════════════════════════════════════════════════╝

class TestMissingFields:

    def test_all_missing(self):
        """Yeni coin → tüm alanlar eksik."""
        from backend.api.coin import _check_missing_fields
        settings = CoinSettings(coin="BTC")
        missing = _check_missing_fields(settings)
        assert 'delta_threshold' in missing
        assert 'order_amount' in missing

    def test_none_missing(self):
        """Tam configured coin → eksik alan yok."""
        from backend.api.coin import _check_missing_fields
        settings = _make_configured("BTC")
        missing = _check_missing_fields(settings)
        assert len(missing) == 0

    def test_partial_missing(self):
        """Bazı alanlar dolu, bazıları eksik."""
        from backend.api.coin import _check_missing_fields
        settings = CoinSettings(
            coin="BTC", delta_threshold=0.50, price_min=51, price_max=85,
        )
        missing = _check_missing_fields(settings)
        assert 'spread_max' in missing
        assert 'order_amount' in missing
        assert 'delta_threshold' not in missing


# ╔══════════════════════════════════════════════════════════════╗
# ║  Router endpoint tests                                        ║
# ╚══════════════════════════════════════════════════════════════╝

class TestSettingsEndpoint:

    def test_router_has_settings_endpoint(self):
        """Coin router'da settings endpoint var."""
        from backend.api.coin import router
        paths = [r.path for r in router.routes]
        assert "/coin/{symbol}/settings" in paths

    def test_response_model_fields(self):
        """CoinSettingsResponse doğru field'lara sahip."""
        from backend.api.coin import CoinSettingsResponse
        resp = CoinSettingsResponse(
            success=True,
            symbol="BTC",
            configured=False,
            message="BTC ayarları kaydedildi — 5 eksik alan var",
            missing_fields=["spread_max", "time_min", "time_max", "event_max", "order_amount"],
        )
        assert resp.configured is False
        assert len(resp.missing_fields) == 5

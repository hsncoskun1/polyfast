"""Global Settings UI backend integration + frontend structure tests.

Backend endpoint doğrulama + frontend component yapısal doğrulama.
Frontend vitest yokken backend test + inspect source yaklaşımı.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
import json


# ╔══════════════════════════════════════════════════════════════╗
# ║  Backend GET /api/settings/global                            ║
# ╚══════════════════════════════════════════════════════════════╝

class TestGlobalSettingsRead:
    """GET endpoint tüm 12 alanı döner."""

    def test_response_has_all_12_fields(self):
        from backend.api.settings import GlobalSettingsResponse
        fields = GlobalSettingsResponse.model_fields
        expected = {
            'auto_start_bot_on_startup', 'bot_max_positions',
            'block_new_entries_when_claim_pending',
            'tp_percentage', 'tp_reevaluate',
            'sl_enabled', 'sl_percentage', 'sl_jump_threshold',
            'fs_time_enabled', 'fs_time_seconds',
            'fs_pnl_enabled', 'fs_pnl_pct',
        }
        assert set(fields.keys()) == expected

    def test_read_returns_config_values(self):
        from backend.api.settings import _read_global_settings
        from backend.orchestrator.wiring import Orchestrator

        orch = Orchestrator()
        result = _read_global_settings(orch)

        assert result.auto_start_bot_on_startup is False  # default false
        assert result.bot_max_positions >= 1
        assert isinstance(result.sl_jump_threshold, float)
        assert result.sl_jump_threshold > 0

    def test_auto_start_default_false(self):
        """auto_start_bot_on_startup default False — plan kararı."""
        from backend.config_loader.schema import AppConfig
        cfg = AppConfig()
        assert cfg.trading.auto_start_bot_on_startup is False


# ╔══════════════════════════════════════════════════════════════╗
# ║  Backend POST /api/settings/global — Partial Update          ║
# ╚══════════════════════════════════════════════════════════════╝

class TestGlobalSettingsUpdate:
    """POST endpoint partial update + runtime yansıma."""

    def test_update_request_allows_partial(self):
        """Tüm alanlar Optional — partial update."""
        from backend.api.settings import GlobalSettingsUpdateRequest
        req = GlobalSettingsUpdateRequest()
        assert req.auto_start_bot_on_startup is None
        assert req.bot_max_positions is None
        assert req.sl_enabled is None

    def test_sl_jump_threshold_not_in_update_request(self):
        """sl_jump_threshold POST body'de YOK — read-only."""
        from backend.api.settings import GlobalSettingsUpdateRequest
        fields = GlobalSettingsUpdateRequest.model_fields
        assert 'sl_jump_threshold' not in fields

    def test_update_response_has_open_positions(self):
        """Response has_open_positions döner."""
        from backend.api.settings import GlobalSettingsUpdateResponse
        fields = GlobalSettingsUpdateResponse.model_fields
        assert 'has_open_positions' in fields


# ╔══════════════════════════════════════════════════════════════╗
# ║  Backend Validation Limits — Frontend Uyumu                  ║
# ╚══════════════════════════════════════════════════════════════╝

class TestBackendValidationLimits:
    """Backend schema limitleri — frontend bu değerleri kullanmalı."""

    def test_bot_max_positions_limits(self):
        """bot_max: min=1, max=50."""
        from backend.config_loader.schema import BotMaxConfig
        import pydantic
        # Default
        cfg = BotMaxConfig()
        assert cfg.max_positions == 3

        # Min
        cfg_min = BotMaxConfig(max_positions=1)
        assert cfg_min.max_positions == 1

        # Max
        cfg_max = BotMaxConfig(max_positions=50)
        assert cfg_max.max_positions == 50

        # Exceed max → validation error
        with pytest.raises(pydantic.ValidationError):
            BotMaxConfig(max_positions=51)

        # Below min → validation error
        with pytest.raises(pydantic.ValidationError):
            BotMaxConfig(max_positions=0)

    def test_tp_percentage_limits(self):
        """tp_percentage: min=0.1, max=100."""
        from backend.config_loader.schema import TakeProfitConfig
        import pydantic

        tp = TakeProfitConfig(percentage=0.1)
        assert tp.percentage == 0.1

        tp_max = TakeProfitConfig(percentage=100.0)
        assert tp_max.percentage == 100.0

        with pytest.raises(pydantic.ValidationError):
            TakeProfitConfig(percentage=0.0)

    def test_sl_percentage_limits(self):
        """sl_percentage: min=0.1, max=100."""
        from backend.config_loader.schema import StopLossConfig
        import pydantic

        sl = StopLossConfig(percentage=0.1)
        assert sl.percentage == 0.1

        with pytest.raises(pydantic.ValidationError):
            StopLossConfig(percentage=0.0)

    def test_sl_jump_threshold_limits(self):
        """sl_jump_threshold: min=0.01, max=1.0 (raw value, not %)."""
        from backend.config_loader.schema import StopLossConfig
        import pydantic

        sl = StopLossConfig(jump_threshold=0.15)
        assert sl.jump_threshold == 0.15  # raw 0.15, UI %15

        with pytest.raises(pydantic.ValidationError):
            StopLossConfig(jump_threshold=0.0)

        with pytest.raises(pydantic.ValidationError):
            StopLossConfig(jump_threshold=1.1)

    def test_fs_time_seconds_limits(self):
        """fs_time_seconds: min=1, max=299."""
        from backend.config_loader.schema import ForceSellTimeCondition as ForceSellTimeConfig
        import pydantic

        fs = ForceSellTimeConfig(remaining_seconds=1)
        assert fs.remaining_seconds == 1

        fs_max = ForceSellTimeConfig(remaining_seconds=299)
        assert fs_max.remaining_seconds == 299

        with pytest.raises(pydantic.ValidationError):
            ForceSellTimeConfig(remaining_seconds=0)

        with pytest.raises(pydantic.ValidationError):
            ForceSellTimeConfig(remaining_seconds=300)


# ╔══════════════════════════════════════════════════════════════╗
# ║  sl_jump_threshold Gösterim Birimi                           ║
# ╚══════════════════════════════════════════════════════════════╝

class TestSlJumpThresholdDisplay:
    """Backend raw 0.15 → UI %15 dönüşümü."""

    def test_raw_value_is_fraction(self):
        """Backend değeri 0.15 (kesir, yüzde değil)."""
        from backend.config_loader.schema import StopLossConfig
        sl = StopLossConfig()
        assert sl.jump_threshold == 0.15
        assert sl.jump_threshold < 1.0  # kesir, %15 değil

    def test_ui_display_conversion(self):
        """UI gösterimi: raw * 100 = %15."""
        raw = 0.15
        display = f"%{raw * 100:.0f}"
        assert display == "%15"

    def test_read_only_in_api(self):
        """sl_jump_threshold POST'ta ignore edilir."""
        import inspect
        from backend.api.settings import global_settings_update
        source = inspect.getsource(global_settings_update)
        assert "sl_jump_threshold" in source
        assert "IGNORE" in source or "read-only" in source.lower()


# ╔══════════════════════════════════════════════════════════════╗
# ║  Frontend Component Yapısal Doğrulama                        ║
# ╚══════════════════════════════════════════════════════════════╝

class TestFrontendStructure:
    """GlobalSettingsModal.tsx yapısal doğrulama."""

    def _read_modal_source(self):
        with open('frontend/src/preview/GlobalSettingsModal.tsx', 'r', encoding='utf-8') as f:
            return f.read()

    def test_modal_file_exists(self):
        import os
        assert os.path.exists('frontend/src/preview/GlobalSettingsModal.tsx')

    def test_has_all_12_fields(self):
        src = self._read_modal_source()
        fields = [
            'auto_start_bot_on_startup', 'bot_max_positions',
            'block_new_entries_when_claim_pending',
            'tp_percentage', 'tp_reevaluate',
            'sl_enabled', 'sl_percentage', 'sl_jump_threshold',
            'fs_time_enabled', 'fs_time_seconds',
            'fs_pnl_enabled', 'fs_pnl_pct',
        ]
        for field in fields:
            assert field in src, f"Field {field} not found in modal source"

    def test_sl_jump_threshold_readonly(self):
        """sl_jump_threshold read-only olarak gösteriliyor."""
        src = self._read_modal_source()
        assert 'gsm-readonly' in src
        assert 'salt okunur' in src

    def test_sl_jump_display_as_percentage(self):
        """sl_jump_threshold raw→% dönüşümü var."""
        src = self._read_modal_source()
        assert '* 100' in src or 'slJumpThreshold * 100' in src

    def test_save_button_text_guncelle(self):
        """Buton metni sabit 'Güncelle'."""
        src = self._read_modal_source()
        assert 'Güncelle' in src

    def test_no_kaydet_button(self):
        """'Kaydet' butonu YOK — sabit 'Güncelle'."""
        src = self._read_modal_source()
        # Kaydet kelimesi 'Kaydediliyor...' dışında olmamalı
        lines_with_kaydet = [l for l in src.split('\n') if 'Kaydet' in l and 'Kaydediliyor' not in l]
        assert len(lines_with_kaydet) == 0

    def test_has_input_mode_decimal(self):
        """Numeric input: inputMode="decimal"."""
        src = self._read_modal_source()
        assert 'inputMode="decimal"' in src

    def test_has_type_text_not_number(self):
        """type="text" — number DEĞİL (Türk locale fix)."""
        src = self._read_modal_source()
        assert 'type="text"' in src
        assert 'type="number"' not in src

    def test_has_three_groups(self):
        """3 grup başlığı var."""
        src = self._read_modal_source()
        assert 'Genel' in src
        assert 'Take Profit' in src
        assert 'Zorla Satış' in src

    def test_has_sl_off_warning(self):
        """SL kapalı uyarısı var."""
        src = self._read_modal_source()
        assert 'Stop-Loss kapalı' in src

    def test_has_all_fs_off_warning(self):
        """Tüm FS kapalı uyarısı var."""
        src = self._read_modal_source()
        assert 'Tüm Zorla Satış kuralları kapalı' in src

    def test_has_fs_time_off_warning(self):
        """FS Time kapalı uyarısı var."""
        src = self._read_modal_source()
        assert 'Zorla Satış (Süre) kapalı' in src

    def test_has_auto_start_description(self):
        """auto_start açıklaması var."""
        src = self._read_modal_source()
        assert 'Credential ve bakiye kontrolü sonrası aktif olur' in src

    def test_partial_update_logic(self):
        """Sadece değişen alanlar gönderiliyor."""
        src = self._read_modal_source()
        assert 'Object.keys(body).length === 0' in src  # no-change check

    def test_mock_mode_support(self):
        """mockMode prop destekleniyor."""
        src = self._read_modal_source()
        assert 'mockMode' in src
        assert 'MOCK_DEFAULTS' in src

    def test_get_fetch_on_mount(self):
        """Mount'ta GET /api/settings/global çağrılır."""
        src = self._read_modal_source()
        assert '/api/settings/global' in src

    def test_has_open_positions_handling(self):
        """has_open_positions backend'den gelir, mesajda gösterilir."""
        src = self._read_modal_source()
        assert 'has_open_positions' in src

    def test_disabled_when_toggle_off(self):
        """Toggle kapalıyken bağlı alan disabled."""
        src = self._read_modal_source()
        assert 'disabled={!slEnabled}' in src
        assert 'disabled={!fsTimeEnabled}' in src
        assert 'disabled={!fsPnlEnabled}' in src


class TestSidebarIntegration:
    """Sidebar → GlobalSettingsModal entegrasyonu."""

    def _read_sidebar_source(self):
        with open('frontend/src/preview/Sidebar.tsx', 'r', encoding='utf-8') as f:
            return f.read()

    def _read_dashboard_source(self):
        with open('frontend/src/preview/DashboardSidebarPreview.tsx', 'r', encoding='utf-8') as f:
            return f.read()

    def test_ayarlar_nav_enabled(self):
        """Sidebar'da Ayarlar disabled DEĞİL."""
        src = self._read_sidebar_source()
        # Ayarlar satırında disabled: false veya disabled yok
        assert "{ icon: '⚙', label: 'Ayarlar', disabled: false }" in src

    def test_sidebar_has_onNavClick(self):
        """Sidebar onNavClick prop alıyor."""
        src = self._read_sidebar_source()
        assert 'onNavClick' in src

    def test_dashboard_imports_global_settings_modal(self):
        """DashboardSidebarPreview GlobalSettingsModal import ediyor."""
        src = self._read_dashboard_source()
        assert 'GlobalSettingsModal' in src

    def test_dashboard_has_global_settings_state(self):
        """globalSettingsOpen state var."""
        src = self._read_dashboard_source()
        assert 'globalSettingsOpen' in src

    def test_dashboard_renders_modal(self):
        """GlobalSettingsModal conditional render var."""
        src = self._read_dashboard_source()
        assert '{globalSettingsOpen && (' in src

    def test_ayarlar_click_opens_modal(self):
        """Ayarlar tıklanınca modal açılıyor."""
        src = self._read_dashboard_source()
        assert "label === 'Ayarlar'" in src
        assert 'setGlobalSettingsOpen(true)' in src

"""Global settings endpoint tests.

Coverage:
- GET response contract
- POST partial update
- sl_jump_threshold read-only
- runtime update (ExitEvaluator, EvaluationLoop)
- router registration
"""

import pytest
from unittest.mock import MagicMock


class TestGlobalSettingsEndpoint:

    def test_router_has_get(self):
        from backend.api.settings import router
        methods = []
        for r in router.routes:
            if hasattr(r, 'path') and r.path == "/settings/global":
                methods.extend(r.methods or [])
        assert "GET" in methods

    def test_router_has_post(self):
        from backend.api.settings import router
        methods = []
        for r in router.routes:
            if hasattr(r, 'path') and r.path == "/settings/global":
                methods.extend(r.methods or [])
        assert "POST" in methods


class TestGlobalSettingsResponseModel:

    def test_response_fields(self):
        from backend.api.settings import GlobalSettingsResponse
        fields = set(GlobalSettingsResponse.model_fields.keys())
        expected = {
            "bot_max_positions", "block_new_entries_when_claim_pending",
            "tp_percentage", "tp_reevaluate",
            "sl_enabled", "sl_percentage", "sl_jump_threshold",
            "fs_time_enabled", "fs_time_seconds",
            "fs_pnl_enabled", "fs_pnl_pct",
        }
        assert expected == fields

    def test_update_request_no_sl_jump(self):
        """Update request'te sl_jump_threshold YOK — read-only."""
        from backend.api.settings import GlobalSettingsUpdateRequest
        fields = set(GlobalSettingsUpdateRequest.model_fields.keys())
        assert "sl_jump_threshold" not in fields

    def test_update_request_partial(self):
        """Tüm alanlar Optional — partial update."""
        from backend.api.settings import GlobalSettingsUpdateRequest
        body = GlobalSettingsUpdateRequest(tp_percentage=3.0)
        assert body.tp_percentage == 3.0
        assert body.sl_enabled is None  # dokunulmadı
        assert body.bot_max_positions is None

    def test_update_response_fields(self):
        from backend.api.settings import GlobalSettingsUpdateResponse
        resp = GlobalSettingsUpdateResponse(
            success=True, message="2 ayar güncellendi", has_open_positions=False,
        )
        assert resp.has_open_positions is False


class TestReadSettings:

    def test_read_from_config(self):
        """_read_global_settings config'ten doğru okuyor."""
        from backend.api.settings import _read_global_settings
        from backend.config_loader.schema import AppConfig

        orch = MagicMock()
        orch._config = AppConfig()  # default config

        result = _read_global_settings(orch)
        assert result.bot_max_positions == 3
        assert result.tp_percentage == 5.0
        assert result.sl_enabled is True
        assert result.sl_percentage == 3.0
        assert result.sl_jump_threshold == 0.15
        assert result.fs_time_enabled is True
        assert result.fs_time_seconds == 30
        assert result.fs_pnl_enabled is False
        assert result.fs_pnl_pct == 5.0
        assert result.block_new_entries_when_claim_pending is True

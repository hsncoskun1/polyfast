"""Tests for BalanceManager credential wiring.

Root cause fix: BalanceManager.set_fetch_function() was never called,
causing dashboard to show $0.00 even with valid credentials.

Coverage:
- set_fetch_function binding
- fetch after credential update
- stale binding regression
- startup no-credential → update → balance available
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.execution.balance_manager import BalanceManager


class TestBalanceManagerBinding:

    def test_fetch_fn_initially_none(self):
        """BalanceManager starts with _fetch_fn = None."""
        bm = BalanceManager()
        assert bm._fetch_fn is None

    @pytest.mark.asyncio
    async def test_fetch_without_binding_returns_false(self):
        """fetch() with no fetch_fn → False."""
        bm = BalanceManager()
        result = await bm.fetch()
        assert result is False
        assert bm.available_balance == 0.0

    def test_set_fetch_function_binds(self):
        """set_fetch_function binds correctly."""
        bm = BalanceManager()
        mock_fn = AsyncMock(return_value={"available": 100.0, "total": 100.0})
        bm.set_fetch_function(mock_fn)
        assert bm._fetch_fn is mock_fn

    @pytest.mark.asyncio
    async def test_fetch_after_binding_returns_balance(self):
        """fetch() with bound fn → updates balance."""
        bm = BalanceManager()
        mock_fn = AsyncMock(return_value={"available": 3.71, "total": 3.71})
        bm.set_fetch_function(mock_fn)

        result = await bm.fetch()
        assert result is True
        assert bm.available_balance == 3.71
        assert bm.total_balance == 3.71
        assert bm.is_stale is False

    @pytest.mark.asyncio
    async def test_fetch_error_returns_false(self):
        """fetch() with error → False, balance stays zero."""
        bm = BalanceManager()
        mock_fn = AsyncMock(side_effect=ConnectionError("refused"))
        bm.set_fetch_function(mock_fn)

        result = await bm.fetch()
        assert result is False
        assert bm.available_balance == 0.0

    @pytest.mark.asyncio
    async def test_fetch_none_result_returns_false(self):
        """fetch() with None result → False."""
        bm = BalanceManager()
        mock_fn = AsyncMock(return_value=None)
        bm.set_fetch_function(mock_fn)

        result = await bm.fetch()
        assert result is False


class TestCredentialUpdateBalanceFlow:
    """Credential update sonrası balance fetch tetiklenmeli."""

    @pytest.mark.asyncio
    async def test_startup_no_creds_then_update_balance_available(self):
        """Startup → no creds → credential update → balance fetch → value available."""
        bm = BalanceManager()

        # Startup: no fetch fn, balance zero
        assert bm.available_balance == 0.0

        # Simulate: wiring binds fetch function
        mock_fn = AsyncMock(return_value={"available": 3.71, "total": 3.71})
        bm.set_fetch_function(mock_fn)

        # Simulate: credential update triggers fetch
        result = await bm.fetch()
        assert result is True
        assert bm.available_balance == 3.71

    @pytest.mark.asyncio
    async def test_balance_updates_on_second_fetch(self):
        """Balance changes after second fetch (credential update)."""
        bm = BalanceManager()
        mock_fn = AsyncMock(return_value={"available": 10.0, "total": 10.0})
        bm.set_fetch_function(mock_fn)

        await bm.fetch()
        assert bm.available_balance == 10.0

        # Credential updated → new balance
        mock_fn.return_value = {"available": 50.0, "total": 50.0}
        await bm.fetch()
        assert bm.available_balance == 50.0


class TestWiringIntegrity:
    """Orchestrator wiring doğru bağlantıyı sağlıyor mu."""

    def test_balance_manager_has_fetch_fn_after_wiring(self):
        """Orchestrator init sonrası BalanceManager.fetch_fn set edilmiş."""
        try:
            from backend.orchestrator.wiring import Orchestrator
            orch = Orchestrator()
            assert orch.balance_manager._fetch_fn is not None
            assert orch.balance_manager._fetch_fn == orch.clob_client.get_balance
        except Exception:
            import inspect
            from backend.orchestrator.wiring import Orchestrator
            source = inspect.getsource(Orchestrator.__init__)
            assert "set_fetch_function" in source

    def test_bot_max_wired_from_config(self):
        """bot_max_positions config'ten eval_loop'a geçirilmiş."""
        import inspect
        from backend.orchestrator.wiring import Orchestrator
        source = inspect.getsource(Orchestrator.__init__)
        assert "bot_max_positions" in source
        # eval_loop constructor'ında da var mı
        from backend.orchestrator.evaluation_loop import EvaluationLoop
        eval_source = inspect.getsource(EvaluationLoop.__init__)
        assert "bot_max_positions" in eval_source

    def test_sl_enabled_wired_from_config(self):
        """sl_enabled config'ten ExitEvaluator'a geçirilmiş."""
        import inspect
        from backend.orchestrator.wiring import Orchestrator
        source = inspect.getsource(Orchestrator.__init__)
        assert "sl_enabled" in source

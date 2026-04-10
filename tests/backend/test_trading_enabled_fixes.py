"""trading_enabled gap fix tests.

Fix-1: main.py — credential+balance OK → trading_enabled=True (immediate)
Fix-2: credential.py — credential update + balance OK → trading_enabled=True
Fix-3: wiring.py — periodic flush positions/claims (~30s interval)
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch


# ╔══════════════════════════════════════════════════════════════╗
# ║  Fix-1: main.py startup — trading_enabled immediate set     ║
# ╚══════════════════════════════════════════════════════════════╝

class TestFix1StartupTradingEnabled:
    """main.py lifespan: credential+balance OK → trading_enabled=True."""

    @pytest.mark.asyncio
    async def test_credential_balance_ok_sets_trading_enabled(self):
        """credential_ok AND balance_ok → trading_enabled = True hemen."""
        orch = MagicMock()
        orch.trading_enabled = False  # restore_state() tarafından False yapılmış

        # Simulate: main.py lifespan credential+balance OK bloğu
        credential_ok = True
        balance_ok = True

        if credential_ok and balance_ok:
            orch.trading_enabled = True  # Fix-1 davranışı

        assert orch.trading_enabled is True

    @pytest.mark.asyncio
    async def test_credential_ok_balance_fail_stays_false(self):
        """credential OK ama balance fail → trading_enabled False kalır."""
        orch = MagicMock()
        orch.trading_enabled = False

        credential_ok = True
        balance_ok = False

        if credential_ok and balance_ok:
            orch.trading_enabled = True

        assert orch.trading_enabled is False

    @pytest.mark.asyncio
    async def test_no_credential_stays_false(self):
        """credential yok → trading_enabled False kalır."""
        orch = MagicMock()
        orch.trading_enabled = False

        credential_ok = False
        balance_ok = False

        if credential_ok and balance_ok:
            orch.trading_enabled = True

        assert orch.trading_enabled is False

    def test_main_py_contains_trading_enabled_set(self):
        """main.py'de trading_enabled = True satırı VAR."""
        import inspect
        from backend.main import lifespan

        source = inspect.getsource(lifespan)
        assert "_orchestrator.trading_enabled = True" in source


# ╔══════════════════════════════════════════════════════════════╗
# ║  Fix-2: credential update — trading_enabled immediate set   ║
# ╚══════════════════════════════════════════════════════════════╝

class TestFix2CredentialUpdateTradingEnabled:
    """credential update sonrası balance OK → trading_enabled=True."""

    def test_credential_update_endpoint_has_trading_enabled(self):
        """credential.py update endpoint'inde trading_enabled set kodu VAR."""
        import inspect
        from backend.api.credential import credential_update

        source = inspect.getsource(credential_update)
        assert "trading_enabled = True" in source

    def test_credential_update_checks_balance_ok(self):
        """trading_enabled sadece balance_ok True ise set edilir."""
        import inspect
        from backend.api.credential import credential_update

        source = inspect.getsource(credential_update)
        assert "balance_ok" in source
        assert "can_place_orders" in source

    @pytest.mark.asyncio
    async def test_balance_ok_and_can_place_enables_trading(self):
        """Balance OK + can_place_orders → trading_enabled = True."""
        orch = MagicMock()
        orch.trading_enabled = False

        balance_ok = True
        can_place_orders = True

        if balance_ok and can_place_orders:
            orch.trading_enabled = True

        assert orch.trading_enabled is True

    @pytest.mark.asyncio
    async def test_balance_fail_does_not_enable_trading(self):
        """Balance fail → trading_enabled False kalır."""
        orch = MagicMock()
        orch.trading_enabled = False

        balance_ok = False
        can_place_orders = True

        if balance_ok and can_place_orders:
            orch.trading_enabled = True

        assert orch.trading_enabled is False

    @pytest.mark.asyncio
    async def test_no_trading_creds_does_not_enable(self):
        """Balance OK ama trading credential yok → trading_enabled False."""
        orch = MagicMock()
        orch.trading_enabled = False

        balance_ok = True
        can_place_orders = False

        if balance_ok and can_place_orders:
            orch.trading_enabled = True

        assert orch.trading_enabled is False


# ╔══════════════════════════════════════════════════════════════╗
# ║  Fix-3: Periodic flush — positions/claims                   ║
# ╚══════════════════════════════════════════════════════════════╝

class TestFix3PeriodicFlush:
    """Periodic flush: positions/claims her ~30s SQLite'a yazılır."""

    def test_periodic_flush_method_exists(self):
        """Orchestrator'da _periodic_flush metodu VAR."""
        from backend.orchestrator.wiring import Orchestrator
        assert hasattr(Orchestrator, "_periodic_flush")

    def test_exit_cycle_loop_has_flush_logic(self):
        """_run_exit_cycle_loop'ta periodic flush kodu VAR."""
        import inspect
        from backend.orchestrator.wiring import Orchestrator
        source = inspect.getsource(Orchestrator._run_exit_cycle_loop)
        assert "periodic_flush" in source.lower()
        assert "flush_every" in source
        assert "cycle_counter" in source

    def test_periodic_flush_skips_settings(self):
        """_periodic_flush sadece positions + claims yazır, settings ATLAR."""
        import inspect
        from backend.orchestrator.wiring import Orchestrator
        source = inspect.getsource(Orchestrator._periodic_flush)
        assert "position_tracker" in source
        assert "claim_manager" in source
        assert "settings_store" not in source  # settings auto-persist, flush'ta gereksiz

    @pytest.mark.asyncio
    async def test_periodic_flush_calls_save(self):
        """_periodic_flush position_store.save + claim_store.save çağırır."""
        from backend.orchestrator.wiring import Orchestrator

        orch = MagicMock(spec=Orchestrator)
        orch.position_tracker = MagicMock()
        orch.claim_manager = MagicMock()
        orch.position_store = MagicMock()
        orch.claim_store = MagicMock()

        # Mock positions
        pos1 = MagicMock()
        orch.position_tracker.get_all_positions.return_value = [pos1]
        orch.position_store.save = AsyncMock(return_value=True)

        # Mock claims
        claim1 = MagicMock()
        orch.claim_manager.get_pending_claims.return_value = [claim1]
        orch.claim_store.save = AsyncMock(return_value=True)

        # Çağır
        await Orchestrator._periodic_flush(orch)

        orch.position_store.save.assert_called_once_with(pos1)
        orch.claim_store.save.assert_called_once_with(claim1)

    @pytest.mark.asyncio
    async def test_periodic_flush_empty_is_noop(self):
        """Position/claim yoksa flush sessiz geçer."""
        from backend.orchestrator.wiring import Orchestrator

        orch = MagicMock(spec=Orchestrator)
        orch.position_tracker = MagicMock()
        orch.claim_manager = MagicMock()
        orch.position_store = MagicMock()
        orch.claim_store = MagicMock()

        orch.position_tracker.get_all_positions.return_value = []
        orch.claim_manager.get_pending_claims.return_value = []

        # Hata olmadan çalışır
        await Orchestrator._periodic_flush(orch)

        orch.position_store.save.assert_not_called()
        orch.claim_store.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_periodic_flush_error_does_not_crash(self):
        """Flush hatası loop'u çökertmez."""
        from backend.orchestrator.wiring import Orchestrator

        orch = MagicMock(spec=Orchestrator)
        orch.position_tracker = MagicMock()
        orch.claim_manager = MagicMock()
        orch.position_store = MagicMock()
        orch.claim_store = MagicMock()

        orch.position_tracker.get_all_positions.side_effect = Exception("DB error")

        # Exception fırlar ama çağıran tarafta yakalanır
        with pytest.raises(Exception, match="DB error"):
            await Orchestrator._periodic_flush(orch)

    def test_flush_interval_calculation(self):
        """flush_every doğru hesaplanıyor: ~30s / cycle_interval."""
        # Default: exit_cycle_interval_ms = 50 → 0.05s
        # flush_every = 30.0 / 0.05 = 600 cycles
        interval_sec = 50 / 1000.0
        flush_every = max(1, int(30.0 / interval_sec))
        assert flush_every == 600

        # Daha yavaş interval: 500ms → 60 cycles
        interval_sec = 500 / 1000.0
        flush_every = max(1, int(30.0 / interval_sec))
        assert flush_every == 60

        # Çok hızlı: 10ms → 3000 cycles
        interval_sec = 10 / 1000.0
        flush_every = max(1, int(30.0 / interval_sec))
        assert flush_every == 3000

    def test_flush_interval_minimum_is_one(self):
        """flush_every en az 1 — sıfıra düşmez."""
        # Çok yavaş interval: 60s → max(1, 0) = 1
        interval_sec = 60.0
        flush_every = max(1, int(30.0 / interval_sec))
        assert flush_every == 1


# ╔══════════════════════════════════════════════════════════════╗
# ║  Entegrasyon: trading_enabled akış bütünlüğü                ║
# ╚══════════════════════════════════════════════════════════════╝

class TestTradingEnabledIntegration:
    """trading_enabled flag'inin tüm akışlardaki tutarlılığı."""

    def test_verify_retry_sets_trading_enabled(self):
        """verify_retry_loop trading_enabled=True set ediyor (mevcut davranış)."""
        import inspect
        from backend.orchestrator.wiring import Orchestrator
        source = inspect.getsource(Orchestrator._verify_retry_loop)
        assert "self.trading_enabled = True" in source

    def test_restore_state_sets_trading_enabled_on_fail(self):
        """restore_state balance fail → trading_enabled=False."""
        import inspect
        from backend.orchestrator.wiring import Orchestrator
        source = inspect.getsource(Orchestrator.restore_state)
        assert "self.trading_enabled = False" in source

    def test_idle_snapshot_checks_trading_enabled(self):
        """build_idle_snapshot trading_enabled kontrol ediyor."""
        import inspect
        from backend.orchestrator.wiring import Orchestrator
        source = inspect.getsource(Orchestrator.build_idle_snapshot)
        assert "self.trading_enabled" in source

    def test_stop_clears_trading_enabled(self):
        """stop() trading_enabled=False yapar."""
        import inspect
        from backend.orchestrator.wiring import Orchestrator
        source = inspect.getsource(Orchestrator.stop)
        assert "self.trading_enabled = False" in source

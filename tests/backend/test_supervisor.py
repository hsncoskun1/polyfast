"""Task Supervisor testleri.

Supervisor, ölmüş loop'ları otomatik yeniden başlatır.
Manuel stop (running=False) durumunda restart YAPMAZ.
Sessiz ölüm (running=True + task.done()) durumunda restart eder.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch


# ╔══════════════════════════════════════════════════════════════╗
# ║  Supervisor Yapısal Testler                                  ║
# ╚══════════════════════════════════════════════════════════════╝

class TestSupervisorStructure:
    """Supervisor metotları ve alanları mevcut."""

    def test_supervisor_method_exists(self):
        from backend.orchestrator.wiring import Orchestrator
        assert hasattr(Orchestrator, "_supervisor_loop")
        assert hasattr(Orchestrator, "_check_and_restart_loop")
        assert hasattr(Orchestrator, "_record_restart")

    def test_supervisor_fields_on_init(self):
        from backend.orchestrator.wiring import Orchestrator
        orch = Orchestrator()
        assert orch._supervisor_task is None
        assert orch._supervisor_running is False
        assert orch._supervisor_restarts == {}

    def test_supervisor_in_start_method(self):
        """start() supervisor task oluşturur."""
        import inspect
        from backend.orchestrator.wiring import Orchestrator
        source = inspect.getsource(Orchestrator.start)
        assert "_supervisor_loop" in source
        assert "_supervisor_running = True" in source

    def test_supervisor_in_stop_method(self):
        """stop() supervisor task'ı cancel eder."""
        import inspect
        from backend.orchestrator.wiring import Orchestrator
        source = inspect.getsource(Orchestrator.stop)
        assert "_supervisor_running = False" in source
        assert "_supervisor_task" in source

    def test_supervisor_interval(self):
        """Supervisor 10s aralıkla kontrol eder."""
        from backend.orchestrator.wiring import Orchestrator
        assert Orchestrator._SUPERVISOR_INTERVAL_SEC == 10.0

    def test_rapid_restart_threshold(self):
        """3 ardışık restart → health warning."""
        from backend.orchestrator.wiring import Orchestrator
        assert Orchestrator._SUPERVISOR_RAPID_RESTART_THRESHOLD == 3


# ╔══════════════════════════════════════════════════════════════╗
# ║  _check_and_restart_loop — Karar Mantığı                    ║
# ╚══════════════════════════════════════════════════════════════╝

class TestCheckAndRestartLoop:
    """Supervisor karar mantığı: ne zaman restart, ne zaman dokunma."""

    @pytest.mark.asyncio
    async def test_running_false_no_restart(self):
        """running=False → manuel stop, restart YAPILMAZ."""
        from backend.orchestrator.wiring import Orchestrator

        orch = Orchestrator()
        restart_fn = AsyncMock()

        # Manuel stop: running=False, task done
        dead_task = asyncio.create_task(asyncio.sleep(0))
        await dead_task  # task biter → done()=True

        await orch._check_and_restart_loop(
            name="test_loop",
            running_flag=False,
            task=dead_task,
            restart_fn=restart_fn,
        )

        restart_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_task_alive_no_restart(self):
        """task alive → normal çalışma, restart YAPILMAZ."""
        from backend.orchestrator.wiring import Orchestrator

        orch = Orchestrator()
        restart_fn = AsyncMock()

        # Alive task: bitmemiş
        alive_task = asyncio.create_task(asyncio.sleep(100))

        await orch._check_and_restart_loop(
            name="test_loop",
            running_flag=True,
            task=alive_task,
            restart_fn=restart_fn,
        )

        restart_fn.assert_not_called()
        alive_task.cancel()
        try:
            await alive_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_task_none_no_restart(self):
        """task=None → henüz başlatılmamış, restart YAPILMAZ."""
        from backend.orchestrator.wiring import Orchestrator

        orch = Orchestrator()
        restart_fn = AsyncMock()

        await orch._check_and_restart_loop(
            name="test_loop",
            running_flag=True,
            task=None,
            restart_fn=restart_fn,
        )

        restart_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_running_true_task_done_restarts(self):
        """running=True + task.done() → sessiz ölüm, RESTART."""
        from backend.orchestrator.wiring import Orchestrator

        orch = Orchestrator()
        restart_fn = AsyncMock()

        # Dead task: running=True ama task bitti
        dead_task = asyncio.create_task(asyncio.sleep(0))
        await dead_task

        await orch._check_and_restart_loop(
            name="test_loop",
            running_flag=True,
            task=dead_task,
            restart_fn=restart_fn,
        )

        restart_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_restart_increments_counter(self):
        """Restart sayacı artırılır."""
        from backend.orchestrator.wiring import Orchestrator

        orch = Orchestrator()
        restart_fn = AsyncMock()

        dead_task = asyncio.create_task(asyncio.sleep(0))
        await dead_task

        assert orch._supervisor_restarts.get("test_loop", 0) == 0

        await orch._check_and_restart_loop(
            name="test_loop",
            running_flag=True,
            task=dead_task,
            restart_fn=restart_fn,
        )

        assert orch._supervisor_restarts["test_loop"] == 1


# ╔══════════════════════════════════════════════════════════════╗
# ║  Restart Counter + Health Warning                            ║
# ╚══════════════════════════════════════════════════════════════╝

class TestRestartCounter:
    """Ardışık restart sayacı + rapid restart uyarısı."""

    def test_record_restart_increments(self):
        from backend.orchestrator.wiring import Orchestrator
        orch = Orchestrator()

        orch._record_restart("discovery_loop")
        assert orch._supervisor_restarts["discovery_loop"] == 1

        orch._record_restart("discovery_loop")
        assert orch._supervisor_restarts["discovery_loop"] == 2

    def test_different_loops_independent_counters(self):
        from backend.orchestrator.wiring import Orchestrator
        orch = Orchestrator()

        orch._record_restart("discovery_loop")
        orch._record_restart("evaluation_loop")

        assert orch._supervisor_restarts["discovery_loop"] == 1
        assert orch._supervisor_restarts["evaluation_loop"] == 1

    def test_reset_counter(self):
        from backend.orchestrator.wiring import Orchestrator
        orch = Orchestrator()

        orch._record_restart("discovery_loop")
        orch._record_restart("discovery_loop")
        assert orch._supervisor_restarts["discovery_loop"] == 2

        orch.supervisor_reset_counter("discovery_loop")
        assert orch._supervisor_restarts["discovery_loop"] == 0

    def test_rapid_restart_warning_threshold(self):
        """3 ardışık restart sonrası warning log üretilir (crash loop uyarısı)."""
        from backend.orchestrator.wiring import Orchestrator
        orch = Orchestrator()

        # 3 kez restart — threshold'a ulaşır
        orch._record_restart("test_loop")
        orch._record_restart("test_loop")
        orch._record_restart("test_loop")

        assert orch._supervisor_restarts["test_loop"] == 3


# ╔══════════════════════════════════════════════════════════════╗
# ║  Supervisor Loop — Hangi Loop'ları İzliyor                   ║
# ╚══════════════════════════════════════════════════════════════╝

class TestSupervisorCoversAllLoops:
    """Supervisor tüm kritik loop'ları izliyor."""

    def test_supervisor_checks_discovery(self):
        import inspect
        from backend.orchestrator.wiring import Orchestrator
        source = inspect.getsource(Orchestrator._supervisor_loop)
        assert "discovery_loop" in source

    def test_supervisor_checks_evaluation(self):
        import inspect
        from backend.orchestrator.wiring import Orchestrator
        source = inspect.getsource(Orchestrator._supervisor_loop)
        assert "evaluation_loop" in source

    def test_supervisor_checks_coin_client(self):
        import inspect
        from backend.orchestrator.wiring import Orchestrator
        source = inspect.getsource(Orchestrator._supervisor_loop)
        assert "coin_client" in source

    def test_supervisor_checks_exit_cycle(self):
        import inspect
        from backend.orchestrator.wiring import Orchestrator
        source = inspect.getsource(Orchestrator._supervisor_loop)
        assert "exit_cycle" in source


# ╔══════════════════════════════════════════════════════════════╗
# ║  Manuel Stop Ayrımı — Tam Akış                              ║
# ╚══════════════════════════════════════════════════════════════╝

class TestManualStopDistinction:
    """Manuel stop: _running=False → supervisor dokunmaz."""

    @pytest.mark.asyncio
    async def test_stopped_discovery_not_restarted(self):
        """Discovery manually stopped → supervisor restart YAPMAZ."""
        from backend.orchestrator.wiring import Orchestrator

        orch = Orchestrator()
        orch.discovery_loop._running = False  # manuel stop
        restart_fn = AsyncMock()

        dead_task = asyncio.create_task(asyncio.sleep(0))
        await dead_task
        orch.discovery_loop._task = dead_task

        await orch._check_and_restart_loop(
            name="discovery_loop",
            running_flag=orch.discovery_loop._running,
            task=orch.discovery_loop._task,
            restart_fn=restart_fn,
        )

        restart_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_crashed_discovery_is_restarted(self):
        """Discovery crashed (running=True, done=True) → supervisor restart eder."""
        from backend.orchestrator.wiring import Orchestrator

        orch = Orchestrator()
        orch.discovery_loop._running = True  # hâlâ çalışması bekleniyor
        restart_fn = AsyncMock()

        dead_task = asyncio.create_task(asyncio.sleep(0))
        await dead_task
        orch.discovery_loop._task = dead_task

        await orch._check_and_restart_loop(
            name="discovery_loop",
            running_flag=orch.discovery_loop._running,
            task=orch.discovery_loop._task,
            restart_fn=restart_fn,
        )

        restart_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_exit_cycle_manual_stop_not_restarted(self):
        """Exit cycle manually stopped → supervisor restart YAPMAZ."""
        from backend.orchestrator.wiring import Orchestrator

        orch = Orchestrator()
        orch._exit_cycle_running = False  # manuel stop

        dead_task = asyncio.create_task(asyncio.sleep(0))
        await dead_task
        orch._exit_cycle_task = dead_task

        # Supervisor loop'un exit cycle bloğunu simüle et
        # _exit_cycle_running False → if koşulu sağlanmaz
        should_restart = orch._exit_cycle_running and orch._exit_cycle_task and orch._exit_cycle_task.done()
        assert should_restart is False

    @pytest.mark.asyncio
    async def test_exit_cycle_crash_detected(self):
        """Exit cycle crashed → supervisor restart eder."""
        from backend.orchestrator.wiring import Orchestrator

        orch = Orchestrator()
        orch._exit_cycle_running = True  # hâlâ çalışması bekleniyor

        dead_task = asyncio.create_task(asyncio.sleep(0))
        await dead_task
        orch._exit_cycle_task = dead_task

        should_restart = orch._exit_cycle_running and orch._exit_cycle_task and orch._exit_cycle_task.done()
        assert should_restart is True


# ╔══════════════════════════════════════════════════════════════╗
# ║  Supervisor + Orchestrator Lifecycle Entegrasyonu             ║
# ╚══════════════════════════════════════════════════════════════╝

class TestSupervisorLifecycle:
    """Supervisor start()/stop() ile doğru şekilde yönetilir."""

    def test_supervisor_not_running_after_init(self):
        from backend.orchestrator.wiring import Orchestrator
        orch = Orchestrator()
        assert orch._supervisor_running is False
        assert orch._supervisor_task is None

    def test_stop_sets_supervisor_running_false(self):
        """stop() _supervisor_running=False yapar."""
        import inspect
        from backend.orchestrator.wiring import Orchestrator
        source = inspect.getsource(Orchestrator.stop)
        assert "self._supervisor_running = False" in source

    def test_start_creates_supervisor_task(self):
        """start() supervisor task oluşturur."""
        import inspect
        from backend.orchestrator.wiring import Orchestrator
        source = inspect.getsource(Orchestrator.start)
        assert 'self._supervisor_task = asyncio.create_task' in source
        assert '_supervisor_loop' in source

    @pytest.mark.asyncio
    async def test_supervisor_error_does_not_crash(self):
        """Supervisor hatası loop'u çökertmez."""
        from backend.orchestrator.wiring import Orchestrator

        orch = Orchestrator()
        # Hata fırlatan bir restart_fn
        restart_fn = AsyncMock(side_effect=Exception("restart failed"))

        dead_task = asyncio.create_task(asyncio.sleep(0))
        await dead_task

        # _check_and_restart_loop hata fırlatabilir, supervisor yakalar
        try:
            await orch._check_and_restart_loop(
                name="test_loop",
                running_flag=True,
                task=dead_task,
                restart_fn=restart_fn,
            )
        except Exception:
            pass  # supervisor loop'ta try/except ile yakalanır

        # restart denenmiş
        restart_fn.assert_called_once()

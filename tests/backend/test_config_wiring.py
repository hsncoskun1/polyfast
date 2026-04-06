"""Config -> Runtime Wiring tests -- v0.7.5.

Config'den okunan degerlerin component constructor'larina
gercekten gectigini dogrular.
"""

import pytest
from backend.config_loader.schema import AppConfig
from backend.orchestrator.wiring import Orchestrator


class TestConfigWiring:
    """Config override'larin component'lara gercekten gectigini dogrula."""

    def _make_orchestrator(self, **overrides) -> Orchestrator:
        """Custom config ile Orchestrator olustur."""
        cfg = AppConfig()
        # Nested override
        for key, value in overrides.items():
            parts = key.split(".")
            obj = cfg
            for part in parts[:-1]:
                obj = getattr(obj, part)
            setattr(obj, parts[-1], value)
        return Orchestrator(config=cfg)

    # ── Claim/Redeem retry ──

    def test_claim_retry_initial(self):
        orch = self._make_orchestrator(**{"trading.claim.retry_initial_seconds": 7})
        assert orch.claim_manager.retry_schedule[0] == 7

    def test_claim_retry_max(self):
        orch = self._make_orchestrator(**{"trading.claim.max_retry_attempts": 30})
        assert orch.claim_manager.max_retries == 30

    # ── Exit evaluator ──

    def test_tp_percentage(self):
        orch = self._make_orchestrator(**{"trading.exit_rules.take_profit.percentage": 8.0})
        assert orch.exit_evaluator._tp_pct == 8.0

    def test_sl_percentage(self):
        orch = self._make_orchestrator(**{"trading.exit_rules.stop_loss.percentage": 5.0})
        assert orch.exit_evaluator._sl_pct == 5.0

    def test_tp_reevaluate(self):
        orch = self._make_orchestrator(**{"trading.exit_rules.take_profit.reevaluate_on_retry": False})
        assert orch.exit_evaluator._tp_reevaluate is False

    def test_sl_jump_threshold(self):
        orch = self._make_orchestrator(**{"trading.exit_rules.stop_loss.jump_threshold": 0.25})
        assert orch.exit_evaluator._sl_jump_threshold == 0.25

    # ── Exit executor retry intervals ──

    def test_tp_retry_interval(self):
        orch = self._make_orchestrator(**{"trading.exit_rules.take_profit.retry_interval_ms": 200})
        from backend.execution.close_reason import CloseReason
        assert orch.exit_executor.get_retry_interval_ms(CloseReason.TAKE_PROFIT) == 200

    def test_max_close_retries(self):
        orch = self._make_orchestrator(**{"trading.exit_rules.max_close_retries": 20})
        assert orch.exit_executor._max_close_retries == 20

    # ── Order validator ──

    def test_min_order_usd(self):
        orch = self._make_orchestrator(**{"trading.min_amount_usd": 2.5})
        assert orch.order_validator._min_order_usd == 2.5

    # ── Balance manager ──

    def test_balance_stale_threshold(self):
        orch = self._make_orchestrator(**{"market_data.balance_stale_threshold_seconds": 120})
        assert orch.balance_manager._stale_threshold == 120

    def test_balance_refresh_interval(self):
        orch = self._make_orchestrator(**{"market_data.balance_refresh_interval_seconds": 30})
        assert orch.balance_manager._passive_interval == 30

    # ── Coin price client ──

    def test_coin_price_resub_interval(self):
        orch = self._make_orchestrator(**{"market_data.coin_price_resub_interval_ms": 200})
        assert orch.coin_client._resub_interval == 0.2  # ms -> sec

    # ── Discovery loop ──

    def test_discovery_retry_schedule(self):
        orch = self._make_orchestrator(**{
            "discovery.retry_initial_seconds": 3,
            "discovery.retry_schedule_2": 6,
        })
        assert orch.discovery_loop._retry_schedule[0] == 3
        assert orch.discovery_loop._retry_schedule[1] == 6

    def test_discovery_retry_steady(self):
        orch = self._make_orchestrator(**{"discovery.retry_steady_seconds": 15})
        assert orch.discovery_loop._retry_steady == 15

    # ── PTB fetcher ──

    def test_ptb_retry_schedule(self):
        orch = self._make_orchestrator(**{"market_data.ptb_retry_initial_seconds": 3})
        assert orch.ptb_fetcher._retry_schedule[0] == 3

    # ── Evaluation loop ──

    def test_evaluation_interval(self):
        orch = self._make_orchestrator(**{"market_data.evaluation_interval_ms": 100})
        assert orch.evaluation_loop._interval == 0.1  # ms -> sec

    # ── Exit cycle ──

    def test_exit_cycle_interval(self):
        orch = self._make_orchestrator(**{"market_data.exit_cycle_interval_ms": 100})
        assert orch._exit_cycle_interval_sec == 0.1

    # ── WS reconnect ──

    def test_ws_reconnect_backoff(self):
        orch = self._make_orchestrator(**{
            "market_data.ws_reconnect_backoff_base": 3.0,
            "market_data.ws_reconnect_backoff_max": 60.0,
        })
        assert orch.rtds_client._reconnect_backoff_base == 3.0
        assert orch.rtds_client._reconnect_backoff_max == 60.0

    # ── Delist threshold ──

    def test_delist_threshold(self):
        orch = self._make_orchestrator(**{"discovery.delist_threshold": 5})
        assert orch.safe_sync._delist_threshold == 5

    # ── Default config — tum degerler default ile calisiyor ──

    def test_default_config_creates_orchestrator(self):
        """Default AppConfig ile Orchestrator hatasiz olusur."""
        orch = Orchestrator(config=AppConfig())
        assert orch.claim_manager.max_retries == 20
        assert orch.exit_evaluator._tp_pct == 5.0
        assert orch._exit_cycle_interval_sec == 0.05  # 50ms

"""ExitOrchestrator -- exit akis koordinasyonu.

Acik pozisyonlari izler, tetik uretir, close execute eder, settlement tetikler.
State authority DEGIL -- PositionTracker authoritative kalir.
ExitOrchestrator karar ve akis koordine eder.

Tek cycle akisi:
1. Acik pozisyonlari al (tracker)
2. ExitEvaluator ile TP/SL/force sell tetik kontrol
3. closing_requested pozisyonlar icin TP reevaluate + close execution
4. closed pozisyonlar icin settlement
5. External reconciliation (disaridan yapilan claim/redeem algila)

Periyodik cagrilir -- evaluation loop gibi ama exit odakli.
"""

import logging

from backend.execution.exit_evaluator import ExitEvaluator
from backend.execution.exit_executor import ExitExecutor
from backend.execution.position_tracker import PositionTracker
from backend.execution.position_record import PositionState
from backend.execution.claim_manager import ClaimManager
from backend.execution.close_reason import CloseReason
from backend.orchestrator.settlement import SettlementOrchestrator
from backend.logging_config.service import get_logger, log_event

logger = get_logger("orchestrator.exit")


class ExitOrchestrator:
    """Exit akis koordinatoru.

    State authority DEGIL — PositionTracker authoritative.
    Bu class sadece karar ve akis koordine eder:
    - Evaluator'dan tetik al
    - Executor'a close gonder
    - Settlement'a settled gonder
    - External reconciliation yap
    """

    def __init__(
        self,
        tracker: PositionTracker,
        evaluator: ExitEvaluator,
        executor: ExitExecutor,
        settlement: SettlementOrchestrator,
        claim_manager: ClaimManager,
    ):
        self._tracker = tracker
        self._evaluator = evaluator
        self._executor = executor
        self._settlement = settlement
        self._claims = claim_manager
        self._cycle_count: int = 0

    async def run_cycle(
        self,
        current_prices: dict[str, float] | None = None,
        remaining_seconds: dict[str, float] | None = None,
        stale_assets: set[str] | None = None,
    ) -> dict:
        """Tek exit cycle -- periyodik cagrilir.

        Args:
            current_prices: asset -> held-side outcome fiyati
            remaining_seconds: asset -> event bitimine kalan saniye
            stale_assets: stale fiyat olan asset'ler (TP/SL evaluation skip edilir,
                          force sell evaluation devam eder)

        Returns:
            Cycle sonucu: triggers, closes, settlements, reconciled
        """
        self._cycle_count += 1
        prices = current_prices or {}
        remaining = remaining_seconds or {}
        stale = stale_assets or set()

        result = {
            "cycle": self._cycle_count,
            "triggers": 0,
            "closes": 0,
            "settlements": 0,
            "reconciled": 0,
        }

        # 1. Tetik evaluation -- acik pozisyonlar
        open_positions = [
            p for p in self._tracker.get_all_positions()
            if p.state == PositionState.OPEN_CONFIRMED
        ]

        for pos in open_positions:
            price = prices.get(pos.asset, 0.0)
            secs = remaining.get(pos.asset, 300.0)

            if price <= 0:
                continue  # fiyat yok, evaluation yapilamaz

            # K5 stale guard — stale fiyatla TP/SL evaluation skip,
            # force sell evaluation devam eder (stale override mantigi korunur)
            if pos.asset in stale:
                log_event(
                    logger, logging.WARNING,
                    f"Stale price — TP/SL skip: {pos.asset} (force sell devam)",
                    entity_type="exit",
                    entity_id=pos.position_id,
                )
                # Sadece force sell evaluate (stale override mantigi evaluate_force_sell icinde)
                fs_result = self._evaluator.evaluate_force_sell(pos, price, secs, outcome_fresh=False)
                if fs_result.should_exit:
                    fs_triggers = fs_result.detail.get("trigger_set", []) if fs_result.detail else []
                    self._tracker.request_close(
                        pos.position_id, CloseReason.FORCE_SELL,
                        trigger_set=fs_triggers,
                    )
                    result["triggers"] += 1
                continue

            # TP/SL evaluation (sadece fresh fiyatla)
            eval_result = self._evaluator.evaluate(pos, price)
            if eval_result.should_exit:
                self._tracker.request_close(
                    pos.position_id, eval_result.reason,
                )
                result["triggers"] += 1

                log_event(
                    logger, logging.INFO,
                    f"Exit trigger: {pos.asset} {pos.side} "
                    f"reason={eval_result.reason.value}",
                    entity_type="exit",
                    entity_id=pos.position_id,
                )
                continue

            # Force sell evaluation (ayri -- time bazli, fresh fiyatla)
            fs_result = self._evaluator.evaluate_force_sell(pos, price, secs)
            if fs_result.should_exit:
                fs_triggers = fs_result.detail.get("trigger_set", []) if fs_result.detail else []
                self._tracker.request_close(
                    pos.position_id, CloseReason.FORCE_SELL,
                    trigger_set=fs_triggers,
                )
                result["triggers"] += 1

        # 2. Close execution -- closing_requested pozisyonlar
        closing_positions = [
            p for p in self._tracker.get_all_positions()
            if p.state == PositionState.CLOSING_REQUESTED
        ]

        for pos in closing_positions:
            price = prices.get(pos.asset, 0.0)

            # TP reevaluate -- sadece TP icin, SL/force sell latch
            if pos.close_reason == CloseReason.TAKE_PROFIT:
                if self._evaluator.should_cancel_close(pos, current_price=price):
                    pos.transition_to(PositionState.OPEN_CONFIRMED)
                    log_event(
                        logger, logging.INFO,
                        f"TP reevaluate: cancel close, back to open: {pos.asset}",
                        entity_type="exit",
                        entity_id=pos.position_id,
                    )
                    continue

            # Close execute
            success = await self._executor.execute_close(pos, current_price=price)
            if success:
                result["closes"] += 1

        # 3. Settlement -- closed pozisyonlar
        settled = await self._settlement.process_settlements()
        result["settlements"] = settled

        # 4. External reconciliation
        reconciled = await self._reconcile_external()
        result["reconciled"] = reconciled

        return result

    async def _reconcile_external(self) -> int:
        """Disaridan yapilan claim/redeem'i algila ve local state hizala.

        Kontrol:
        - Pending claim var mi?
        - Eger pending claim'in pozisyonu zaten settled (balance degismis)?
        - already_redeemed durumu retry'dan donmus mu?

        Returns:
            Reconcile edilen kayit sayisi.
        """
        reconciled = 0
        pending = self._claims.get_pending_claims()

        for claim in pending:
            # Settlement orchestrator'da bu pozisyon retry'da mi?
            if self._settlement.is_position_in_retry(claim.position_id):
                # Retry devam ediyor -- burayi settlement yonetiyor
                continue

            # Pending ama retry'da degil -- muhtemelen external settlement
            # veya stuck kayit. Kapat.
            self._claims.mark_externally_settled(claim.claim_id)
            reconciled += 1

            log_event(
                logger, logging.WARNING,
                f"External reconciliation: pending claim closed "
                f"(not in retry): {claim.asset} pos={claim.position_id}",
                entity_type="reconciliation",
                entity_id=claim.claim_id,
            )

        return reconciled

    # ── Query ──

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

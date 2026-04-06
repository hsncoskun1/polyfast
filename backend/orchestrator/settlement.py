"""Settlement Orchestration -- event resolve sonrasi otomatik redeem.

Akis:
1. Pozisyon CLOSED + event bitmis -> settlement adayi
2. Resolved/redeemable mi kontrol et (event_end_ts gecmis YETMEZ)
3. Redeemable ise -> ClaimRecord olustur + execute_redeem
4. Basarisiz -> retry schedule: 5s/10s/20s/20s... max 20
5. Payout sonucu authoritative kayit: claimed_amount_usdc
6. Post-redeem balance refresh

Settlement modeli — IKI KATMAN:

PAPER MODE (gecici heuristic, test/gelistirme icin):
- coin_usd vs ptb karsilastirmasi ile kazanan taraf TAHMIN edilir
- Bu tahmin yanlis olabilir (stale veri, gecikme, yanlis ptb)
- Paper mode sonucu AUTHORITATIVE DEGILDIR
- Fallback: PTB/coin_usd eksikse net_realized_pnl > 0 kullanilir

LIVE MODE (authoritative, production):
- Bot kazanan/kaybeden HESAPLAMAZ
- Polymarket'e resolved/redeemable mi sorar
- redeemPositions() cagirir
- Payout sonucu ($USDC) AUTHORITATIVE kaynaktir
- payout > 0 -> WON, payout == 0 -> LOST
- Botun kendi hesabi overrule EDILEMEZ

ONEMLI:
- event_end_ts gecmis olmasi = resolved demek DEGIL
- Settlement baslatmadan once resolved/redeemable durumu NET dogrulanir
- LIVE_SETTLEMENT_ENABLED=False oldukca gercek TX cikmaz
- Paper mode'da simulated redeem yapilir
- process_settlements() periyodik cagrilir — retry state'i kontrol eder
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.execution.claim_manager import (
    ClaimManager, ClaimOutcome, ClaimStatus,
    CLAIM_REDEEM_RETRY_SCHEDULE, CLAIM_REDEEM_RETRY_STEADY,
    CLAIM_REDEEM_MAX_RETRIES,
)
from backend.execution.position_tracker import PositionTracker
from backend.execution.position_record import PositionState
from backend.execution.relayer_client_wrapper import RelayerClientWrapper
from backend.logging_config.service import get_logger, log_event

logger = get_logger("orchestrator.settlement")

SLOT_SECONDS = 300


@dataclass
class SettlementRetryState:
    """Pozisyon bazli settlement retry durumu."""
    position_id: str
    claim_id: str
    attempt_count: int = 0
    next_retry_at: float = 0.0  # unix timestamp
    exhausted: bool = False  # max retry asildi

    def get_retry_delay(self) -> float:
        """Siradaki retry icin bekleme suresi (saniye)."""
        if self.attempt_count == 0:
            return 0.0  # ilk deneme hemen
        idx = self.attempt_count - 1
        if idx < len(CLAIM_REDEEM_RETRY_SCHEDULE):
            return float(CLAIM_REDEEM_RETRY_SCHEDULE[idx])
        return float(CLAIM_REDEEM_RETRY_STEADY)

    def schedule_next(self) -> None:
        """Sonraki retry zamanini hesapla."""
        self.attempt_count += 1
        if self.attempt_count >= CLAIM_REDEEM_MAX_RETRIES:
            self.exhausted = True
            return
        delay = self.get_retry_delay()
        self.next_retry_at = time.time() + delay

    def is_ready(self) -> bool:
        """Retry zamani geldi mi?"""
        if self.exhausted:
            return False
        return time.time() >= self.next_retry_at


class SettlementOrchestrator:
    """Event resolve sonrasi otomatik settlement + retry.

    Closed pozisyonlari tarar, resolved olanlari redeem eder.
    Basarisiz olanlar retry schedule ile tekrar denenir.
    Paper mode: simulated. Live mode: relayer guard ile kapali.
    """

    def __init__(
        self,
        tracker: PositionTracker,
        claim_manager: ClaimManager,
        relayer: RelayerClientWrapper,
        paper_mode: bool = True,
        clob_client=None,
        ptb_fetcher=None,
        coin_price_client=None,
    ):
        self._tracker = tracker
        self._claims = claim_manager
        self._relayer = relayer
        self._paper_mode = paper_mode
        self._clob = clob_client                  # ClobClientWrapper — getMarket() icin
        self._ptb_fetcher = ptb_fetcher           # PTBFetcher — paper heuristic icin
        self._coin_price = coin_price_client      # CoinPriceClient — paper heuristic icin
        self._settlement_count: int = 0
        self._retry_states: dict[str, SettlementRetryState] = {}  # position_id -> state
        self._winner_cache: dict[str, str] = {}   # condition_id -> winning_side
        self._last_resolution_method: str = ""    # "api", "paper_heuristic", "pnl_fallback"

    async def process_settlements(self) -> int:
        """Tum closed pozisyonlari tara, resolved olanlari settle et.

        Her cagrildiginda:
        1. Retry bekleyen pozisyonlari kontrol et
        2. Yeni closed pozisyonlari tara
        3. Settlement dene
        4. Basarisiz olanlar retry state'e ekle

        Returns:
            Bu cagride settle edilen pozisyon sayisi.
        """
        settled = 0

        # 1. Retry bekleyen pozisyonlar
        settled += await self._process_retries()

        # 2. Yeni closed pozisyonlar (henuz settlement denenmemis)
        closed_positions = [
            p for p in self._tracker.get_all_positions()
            if p.is_closed and p.closed_at is not None
        ]

        for pos in closed_positions:
            # Zaten retry state'de mi?
            if pos.position_id in self._retry_states:
                continue

            # Zaten basarili claim/redeem var mi?
            existing_claims = self._claims.get_claims_by_position(pos.position_id)
            if any(c.is_success for c in existing_claims):
                continue  # zaten settled

            # Resolved/redeemable mi?
            is_redeemable = await self._check_resolved(pos.condition_id)
            if not is_redeemable:
                continue

            # Ilk settlement denemesi
            success = await self._settle_position(pos)
            if success:
                settled += 1
            # Basarisiz durumda _settle_position retry state olusturur

        return settled

    async def _process_retries(self) -> int:
        """Retry bekleyen pozisyonlari isle."""
        settled = 0
        exhausted_ids = []

        for pos_id, state in self._retry_states.items():
            if state.exhausted:
                exhausted_ids.append(pos_id)
                continue

            if not state.is_ready():
                continue  # henuz zamani gelmedi

            # Pozisyonu bul
            pos = self._tracker.get_position(pos_id)
            if pos is None:
                exhausted_ids.append(pos_id)
                continue

            # Tekrar dene
            success = await self._retry_settle(pos, state)
            if success:
                settled += 1
                exhausted_ids.append(pos_id)  # basarili — retry'dan cikar

        # Temizlik: basarili veya exhausted olanlari kaldir
        for pos_id in exhausted_ids:
            state = self._retry_states.get(pos_id)
            if state and state.exhausted and not self._is_settled(pos_id):
                # Max retry asildi — FAILED olarak isaretle
                self._mark_settlement_failed(pos_id, state)
            self._retry_states.pop(pos_id, None)

        return settled

    async def _retry_settle(self, pos, state: SettlementRetryState) -> bool:
        """Retry settlement denemesi — mevcut claim uzerinden."""
        claim = self._claims.get_claim(state.claim_id)
        if claim is None:
            state.exhausted = True
            return False

        if claim.is_success:
            return True  # zaten basarili

        log_event(
            logger, logging.INFO,
            f"Settlement retry #{state.attempt_count + 1}: "
            f"{pos.asset} {pos.side} pos={pos.position_id}",
            entity_type="settlement",
            entity_id=pos.position_id,
        )

        # Mevcut claim ile tekrar dene (yeni claim OLUSTURMA)
        success = await self._execute_redeem_for_claim(pos, claim)
        if success:
            return True

        # Basarisiz — sonraki retry'i planla
        state.schedule_next()
        if state.exhausted:
            log_event(
                logger, logging.WARNING,
                f"Settlement exhausted after {state.attempt_count} attempts: "
                f"{pos.asset} {pos.side}",
                entity_type="settlement",
                entity_id=pos.position_id,
            )
        return False

    async def _settle_position(self, pos) -> bool:
        """Ilk settlement denemesi. Basarisiz olursa retry state olusturur."""
        claim = self._claims.create_claim(
            condition_id=pos.condition_id,
            position_id=pos.position_id,
            asset=pos.asset,
            side=pos.side,
        )

        success = await self._execute_settle(pos, claim)
        if success:
            return True

        # Basarisiz — retry state olustur
        state = SettlementRetryState(
            position_id=pos.position_id,
            claim_id=claim.claim_id,
        )
        state.schedule_next()  # attempt_count 0->1, next_retry_at hesapla
        self._retry_states[pos.position_id] = state

        log_event(
            logger, logging.INFO,
            f"Settlement failed, retry scheduled: {pos.asset} {pos.side} "
            f"next_in={state.get_retry_delay():.0f}s",
            entity_type="settlement",
            entity_id=pos.position_id,
        )
        return False

    async def _execute_settle(self, pos, claim) -> bool:
        """Ilk settlement execution — paper veya live."""
        return await self._execute_redeem_for_claim(pos, claim)

    async def _execute_redeem_for_claim(self, pos, claim) -> bool:
        """Settlement redeem execution — paper veya live. Retry'da da kullanilir."""
        if self._paper_mode:
            won = self._determine_winner(pos)
            payout = pos.net_position_shares * 1.0 if won else 0.0

            success = await self._claims.execute_redeem(
                claim.claim_id, won=won, payout_amount=round(payout, 4),
            )

            if success:
                self._settlement_count += 1
                log_event(
                    logger, logging.INFO,
                    f"Settlement: {pos.asset} {pos.side} "
                    f"outcome={'WON' if won else 'LOST'} "
                    f"payout=${payout:.4f} "
                    f"resolution_method={self._last_resolution_method}",
                    entity_type="settlement",
                    entity_id=pos.position_id,
                )
            return success
        else:
            result = await self._relayer.redeem_positions(
                pos.condition_id, pos.side,
            )

            if result.get("success"):
                payout = result.get("payout_usdc", 0.0)
                won = payout > 0
                await self._claims.execute_redeem(
                    claim.claim_id, won=won, payout_amount=payout,
                )
                self._settlement_count += 1
                return True

            # Claim PENDING kalir — retry surecinde trade block icin
            # FAILED sadece max retry asildiginda konur
            claim.last_error = result.get("error", "unknown")
            return False

    async def _check_resolved(self, condition_id: str) -> bool:
        """Event resolved mi? Winner belli mi?

        Oncelik sirasi:
        1. CLOB API getMarket() — closed + tokens[].winner (birincil)
        2. Paper fallback — API erisimsiz ortam icin

        Resolved = closed + winner bilgisi mevcut.
        event_end_ts gecmis olmasi YETMEZ.
        """
        # 1. BIRINCIL: CLOB API getMarket()
        if self._clob is not None:
            resolution = await self._clob.get_market_resolution(condition_id)
            if resolution.resolved:
                self._winner_cache[condition_id] = resolution.winning_side
                return True
            if resolution.closed:
                # Closed ama winner yok — henuz resolved degil
                log_event(
                    logger, logging.INFO,
                    f"Market closed but not resolved: {condition_id}",
                    entity_type="settlement",
                    entity_id=condition_id,
                )
                return False
            # closed=False — henuz kapanmamis
            return False

        # 2. Paper fallback — API erisimsiz ortam
        if self._paper_mode:
            log_event(
                logger, logging.WARNING,
                f"Resolution check: paper fallback (no CLOB client): {condition_id}",
                entity_type="settlement",
                entity_id=condition_id,
            )
            return True

        return False

    def _determine_winner(self, pos) -> bool:
        """Pozisyon kazandi mi?

        Oncelik sirasi:
        1. API winner cache — getMarket()'tan gelen kesin bilgi (birincil)
        2. Paper heuristic — coin_usd vs ptb (offline test/dev icin)
        3. PnL fallback — hicbir veri yoksa (WARNING)

        Returns:
            True = pozisyon kazandi (WON), False = kaybetti (LOST)
        """
        # 1. API winner cache (birincil)
        cached_winner = self._winner_cache.get(pos.condition_id)
        if cached_winner:
            won = pos.side == cached_winner
            self._last_resolution_method = "api"
            log_event(
                logger, logging.INFO,
                f"Resolution (API): {pos.asset} winner={cached_winner}, "
                f"pos_side={pos.side} -> {'WON' if won else 'LOST'}",
                entity_type="settlement",
                entity_id=pos.position_id,
            )
            return won

        # 2. Paper heuristic — coin_usd vs ptb
        ptb_value = self._get_ptb_value(pos.condition_id)
        coin_usd = self._get_coin_usd(pos.asset)

        if ptb_value is not None and ptb_value > 0 and coin_usd > 0:
            winning_side = "UP" if coin_usd > ptb_value else "DOWN"
            won = pos.side == winning_side
            self._last_resolution_method = "paper_heuristic"
            log_event(
                logger, logging.WARNING,
                f"Resolution (paper heuristic): {pos.asset} ptb=${ptb_value:.2f} "
                f"coin_usd=${coin_usd:.2f} -> {winning_side} wins, "
                f"pos_side={pos.side} -> {'WON' if won else 'LOST'}",
                entity_type="settlement",
                entity_id=pos.position_id,
            )
            return won

        # 3. PnL fallback — hicbir veri yok
        self._last_resolution_method = "pnl_fallback"
        log_event(
            logger, logging.WARNING,
            f"Resolution (PnL fallback): {pos.asset} "
            f"ptb={'missing' if ptb_value is None else ptb_value} "
            f"coin_usd={coin_usd} -> using net_realized_pnl={pos.net_realized_pnl:.4f}",
            entity_type="settlement",
            entity_id=pos.position_id,
        )
        return pos.net_realized_pnl > 0

    def _get_ptb_value(self, condition_id: str) -> float | None:
        if self._ptb_fetcher is None:
            return None
        record = self._ptb_fetcher.get_record(condition_id)
        if record is None:
            return None
        return record.ptb_value

    def _get_coin_usd(self, asset: str) -> float:
        if self._coin_price is None:
            return 0.0
        return self._coin_price.get_usd_price(asset)

    def _is_settled(self, position_id: str) -> bool:
        """Pozisyon basarili settle edilmis mi?"""
        claims = self._claims.get_claims_by_position(position_id)
        return any(c.is_success for c in claims)

    def _mark_settlement_failed(self, position_id: str, state: SettlementRetryState) -> None:
        """Max retry asildi — health warning."""
        log_event(
            logger, logging.ERROR,
            f"Settlement FAILED permanently: pos={position_id} "
            f"attempts={state.attempt_count}",
            entity_type="settlement",
            entity_id=position_id,
        )

    # ── Query ──

    @property
    def settlement_count(self) -> int:
        return self._settlement_count

    @property
    def pending_retry_count(self) -> int:
        """Retry bekleyen settlement sayisi."""
        return sum(
            1 for s in self._retry_states.values()
            if not s.exhausted
        )

    def has_pending_settlements(self) -> bool:
        """Bekleyen settlement var mi? (retry dahil)."""
        if self._retry_states:
            return any(not s.exhausted for s in self._retry_states.values())
        # Ayrica claim_manager'daki pending'leri de kontrol et
        return self._claims.has_pending_claims()

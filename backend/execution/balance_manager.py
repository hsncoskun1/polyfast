"""BalanceManager — balance fetch + lifecycle + stale guard.

Balance fetch zamanlari (nihai karar):
- Startup'ta: ZORUNLU
- Post-fill: ZORUNLU
- Post-close: ZORUNLU
- Post-claim: ZORUNLU (Faz 6)
- Passive refresh: 15-30s arayla
- Pre-trade: YOK (execution hizini bloklamamak icin)

Stale kurali:
- Balance 60s guncellenmezse stale
- Stale balance ile order GONDERILMEZ
- OrderValidator stale guard uygular

Authoritative kaynak: CLOB SDK get_balance_allowance
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

from backend.domain.startup_guard import HealthIncident, HealthSeverity
from backend.logging_config.service import get_logger, log_event

logger = get_logger("execution.balance")

BALANCE_STALE_THRESHOLD_SEC = 60.0  # 60s guncellenmezse stale
PASSIVE_REFRESH_INTERVAL_SEC = 20.0  # 15-30s arasi, 20s default


class BalanceManager:
    """Balance lifecycle yoneticisi.

    Authoritative balance state tutar.
    Stale guard ile order gondermeden once kontrol saglar.
    Passive refresh ile drift minimize eder.
    """

    def __init__(
        self,
        stale_threshold_sec: float = BALANCE_STALE_THRESHOLD_SEC,
        passive_refresh_interval: float = PASSIVE_REFRESH_INTERVAL_SEC,
    ):
        self._available: float = 0.0
        self._total: float = 0.0
        self._updated_at: datetime | None = None
        self._stale_threshold = stale_threshold_sec
        self._passive_interval = passive_refresh_interval
        self._fetch_count: int = 0
        self._running: bool = False
        self._task: asyncio.Task | None = None

        # Fetch callback — production'da CLOB SDK cagirir
        self._fetch_fn = None

    def set_fetch_function(self, fn) -> None:
        """Balance fetch fonksiyonunu set et.

        Production'da: CLOB SDK get_balance_allowance wrapper
        Paper mode'da: simulated balance doner
        """
        self._fetch_fn = fn

    # ─── State ───

    @property
    def available_balance(self) -> float:
        return self._available

    @property
    def total_balance(self) -> float:
        return self._total

    @property
    def is_stale(self) -> bool:
        if self._updated_at is None:
            return True
        age = (datetime.now(timezone.utc) - self._updated_at).total_seconds()
        return age > self._stale_threshold

    @property
    def is_fresh(self) -> bool:
        return not self.is_stale

    @property
    def age_seconds(self) -> float | None:
        if self._updated_at is None:
            return None
        return (datetime.now(timezone.utc) - self._updated_at).total_seconds()

    @property
    def updated_at(self) -> datetime | None:
        return self._updated_at

    # ─── Fetch ───

    async def fetch(self) -> bool:
        """Balance fetch — authoritative kaynak.

        Returns:
            True basarili, False basarisiz.
        """
        if self._fetch_fn is None:
            log_event(
                logger, logging.WARNING,
                "Balance fetch function not set",
                entity_type="balance",
                entity_id="no_fetch_fn",
            )
            return False

        try:
            result = await self._fetch_fn()
            if result is not None:
                if isinstance(result, dict):
                    self._available = float(result.get("available", 0))
                    self._total = float(result.get("total", 0))
                elif isinstance(result, (int, float)):
                    self._available = float(result)
                    self._total = float(result)

                self._updated_at = datetime.now(timezone.utc)
                self._fetch_count += 1

                log_event(
                    logger, logging.DEBUG,
                    f"Balance fetched: available=${self._available:.2f} total=${self._total:.2f}",
                    entity_type="balance",
                    entity_id="fetched",
                )
                return True

        except Exception as e:
            log_event(
                logger, logging.WARNING,
                f"Balance fetch failed: {e}",
                entity_type="balance",
                entity_id="fetch_error",
            )

        return False

    # ─── Manual update (paper mode / test) ───

    def update(self, available: float, total: float | None = None) -> None:
        """Manuel balance guncelleme (paper mode / test icin)."""
        self._available = available
        self._total = total if total is not None else available
        self._updated_at = datetime.now(timezone.utc)

    def deduct(self, amount: float) -> None:
        """Post-fill: available balance'tan dusur (paper mode)."""
        self._available = max(0, self._available - amount)
        self._updated_at = datetime.now(timezone.utc)

    def add(self, amount: float) -> None:
        """Post-close: available balance'a ekle (paper mode)."""
        self._available += amount
        self._updated_at = datetime.now(timezone.utc)

    # ─── Passive refresh loop ───

    async def start_passive_refresh(self) -> None:
        """Arka plan passive refresh baslat (15-30s arayla)."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._passive_loop(), name="balance_refresh")

    async def stop_passive_refresh(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def _passive_loop(self) -> None:
        """Passive refresh dongusu."""
        while self._running:
            await asyncio.sleep(self._passive_interval)
            if self._running:
                await self.fetch()

    # ─── Health ───

    def get_health_incidents(self) -> list[HealthIncident]:
        incidents = []
        if self.is_stale:
            incidents.append(HealthIncident(
                severity=HealthSeverity.WARNING,
                category="balance",
                message=f"Balance stale (age: {self.age_seconds:.0f}s)" if self.age_seconds is not None else "Balance never fetched",
                suggested_action="Check CLOB SDK connectivity",
            ))
        return incidents

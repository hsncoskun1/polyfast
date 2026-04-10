"""Discovery Loop — slot-aware bul-ve-bekle modeli.

Davranış:
1. Yeni 5dk slot başladı → discovery tara
2. Event bulundu → DUR, slot bitene kadar bekle, tekrar tarama YOK
3. Event bulunamadı → retry: 2→4→8→16→10→10... event bulunana kadar
4. Slot bittikten sonra → yeni slot için discovery tekrar çalışır

Retry sırasında slot boundary aşılırsa:
- Retry DUR, yeni slot'a geç, baştan tara
- Eski slot'un event'ini aramaya devam etmez

Gereksiz API çağrısı YOK.
7/24 mantıkla sürekli ama verimli çalışır.

Bu modül sadece discovery + registry sync yapar.
Eligibility, subscription, evaluation YAPMAZ (v0.4.3).
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

from backend.discovery.engine import DiscoveryEngine
from backend.registry.safe_sync import SafeSync
from backend.domain.startup_guard import HealthIncident, HealthSeverity
from backend.logging_config.service import get_logger, log_event

logger = get_logger("orchestrator.discovery")

# Default retry schedule — schema'dan override edilebilir (DiscoveryConfig)
DEFAULT_RETRY_SCHEDULE = [2, 4, 8, 16]
DEFAULT_RETRY_STEADY_INTERVAL = 10
SLOT_SECONDS = 300  # venue sabiti — degismez


def _current_slot_start() -> int:
    """Şu anki 5dk slot'un başlangıç timestamp'i."""
    return (int(time.time()) // SLOT_SECONDS) * SLOT_SECONDS


def _slot_remaining() -> float:
    """Şu anki slot'un bitmesine kalan saniye."""
    now = time.time()
    slot_end = (int(now) // SLOT_SECONDS + 1) * SLOT_SECONDS
    return max(0.0, slot_end - now)


class DiscoveryLoop:
    """Slot-aware discovery döngüsü.

    Her 5dk slot'ta bir kez tarar.
    Bulursa bekler, bulamazsa retry schedule ile dener.
    Registry sync ile sonuçları registry'ye yansıtır.
    """

    def __init__(
        self,
        discovery_engine: DiscoveryEngine,
        safe_sync: SafeSync,
        on_events_found=None,
        retry_schedule: list[int] | None = None,
        retry_steady_seconds: int = DEFAULT_RETRY_STEADY_INTERVAL,
    ):
        self._engine = discovery_engine
        self._sync = safe_sync
        self._on_events_found = on_events_found
        self._retry_schedule = retry_schedule or list(DEFAULT_RETRY_SCHEDULE)
        self._retry_steady = retry_steady_seconds
        self._running = False
        self._task: asyncio.Task | None = None
        self._current_slot: int = 0
        self._events_found: int = 0
        self._scan_count: int = 0
        self._retry_count: int = 0
        from collections import deque
        self._health_incidents: deque = deque(maxlen=100)  # FIFO cap

    # ─── Lifecycle ───

    async def start(self) -> None:
        """Discovery loop'u başlat. Crashed task varsa yeniden başlat."""
        if self._running and self._task and not self._task.done():
            return  # Çalışıyor — skip
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="discovery_loop")
        log_event(
            logger, logging.INFO,
            "Discovery loop started",
            entity_type="orchestrator",
            entity_id="discovery_loop",
        )

    async def stop(self) -> None:
        """Discovery loop'u durdur."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        log_event(
            logger, logging.INFO,
            "Discovery loop stopped",
            entity_type="orchestrator",
            entity_id="discovery_loop",
        )

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def current_slot(self) -> int:
        return self._current_slot

    @property
    def events_found(self) -> int:
        return self._events_found

    @property
    def scan_count(self) -> int:
        return self._scan_count

    def get_health_incidents(self) -> list[HealthIncident]:
        return list(self._health_incidents)

    # ─── Main Loop ───

    async def _loop(self) -> None:
        """Ana discovery döngüsü — 7/24 çalışır."""
        while self._running:
            try:
                slot_start = _current_slot_start()
                self._current_slot = slot_start

                # Tara
                found = await self._scan_with_retry(slot_start)

                if found:
                    # Event bulundu → slot bitene kadar bekle
                    remaining = _slot_remaining()
                    if remaining > 0:
                        log_event(
                            logger, logging.INFO,
                            f"Events found, waiting {remaining:.0f}s for slot end",
                            entity_type="orchestrator",
                            entity_id="discovery_wait",
                            payload={"slot": slot_start, "wait_seconds": round(remaining)},
                        )
                        await asyncio.sleep(remaining)
                else:
                    # Slot boyunca bulunamadı — slot bitene kadar bekle
                    remaining = _slot_remaining()
                    if remaining > 0:
                        await asyncio.sleep(remaining)

                # Slot bitti — döngü başa döner, yeni slot taranacak

            except asyncio.CancelledError:
                break
            except Exception as e:
                log_event(
                    logger, logging.ERROR,
                    f"Discovery loop error: {e}",
                    entity_type="orchestrator",
                    entity_id="discovery_error",
                )
                # Hata durumunda 10s bekle, döngü devam eder
                await asyncio.sleep(10)

    async def _scan_with_retry(self, slot_start: int) -> bool:
        """Tek slot içinde discovery tara, bulamazsa retry.

        Retry schedule: 2→4→8→16→10→10...
        Slot boundary aşılırsa retry DUR (yeni slot'a geç).

        Returns:
            True if events found, False if slot ended without finding events.
        """
        attempt = 0

        while self._running:
            # Slot bitti mi kontrol et
            if _current_slot_start() != slot_start:
                log_event(
                    logger, logging.INFO,
                    "Slot boundary crossed during retry, moving to next slot",
                    entity_type="orchestrator",
                    entity_id="slot_boundary",
                )
                return False

            # Tara
            try:
                self._scan_count += 1
                result = await self._engine.scan()
                events = result.events if hasattr(result, 'events') else []

                if events:
                    self._events_found = len(events)
                    self._retry_count = 0

                    # Registry sync
                    await self._sync_to_registry(events)

                    log_event(
                        logger, logging.INFO,
                        f"Discovery found {len(events)} events",
                        entity_type="orchestrator",
                        entity_id="discovery_found",
                        payload={"count": len(events), "slot": slot_start},
                    )

                    # Callback: eligibility → subscription zinciri
                    if self._on_events_found:
                        try:
                            await self._on_events_found(events)
                        except Exception as e:
                            log_event(
                                logger, logging.WARNING,
                                f"on_events_found callback error: {e}",
                                entity_type="orchestrator",
                                entity_id="callback_error",
                            )

                    return True

            except Exception as e:
                log_event(
                    logger, logging.WARNING,
                    f"Discovery scan failed: {e}",
                    entity_type="orchestrator",
                    entity_id="scan_failure",
                )
                self._health_incidents.append(HealthIncident(
                    severity=HealthSeverity.WARNING,
                    category="discovery",
                    message=f"Discovery scan failed: {e}",
                    suggested_action="Check Gamma API availability",
                ))

            # Bulunamadı — retry schedule
            if attempt < len(self._retry_schedule):
                wait = self._retry_schedule[attempt]
            else:
                wait = self._retry_steady

            self._retry_count += 1
            attempt += 1

            log_event(
                logger, logging.DEBUG,
                f"Discovery retry #{attempt} in {wait}s",
                entity_type="orchestrator",
                entity_id="discovery_retry",
            )

            # Bekle — ama slot boundary kontrol et
            waited = 0.0
            while waited < wait and self._running:
                sleep_chunk = min(1.0, wait - waited)
                await asyncio.sleep(sleep_chunk)
                waited += sleep_chunk

                # Slot değişti mi?
                if _current_slot_start() != slot_start:
                    return False

        return False

    async def _sync_to_registry(self, events: list) -> None:
        """Discovery sonuçlarını registry'ye sync et."""
        try:
            sync_result = await self._sync.sync(events)
            log_event(
                logger, logging.DEBUG,
                f"Registry sync complete",
                entity_type="orchestrator",
                entity_id="registry_sync",
            )
        except Exception as e:
            log_event(
                logger, logging.WARNING,
                f"Registry sync failed: {e}",
                entity_type="orchestrator",
                entity_id="sync_failure",
            )

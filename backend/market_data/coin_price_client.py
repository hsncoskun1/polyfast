"""CoinPriceClient — Polymarket RTDS'ten coin canlı USD fiyatı çeker.

Kaynak: wss://ws-live-data.polymarket.com
Topic: crypto_prices
Format: {"action": "subscribe", "subscriptions": [{"topic": "crypto_prices", "type": "*", "filters": "{\"symbol\": \"btcusdt\"}"}]}
Response: payload.data[].value = canlı USD coin fiyatı

ÖNEMLİ NOTLAR:
- Bu kaynak Polymarket'in resmi dokümantasyonunda yer almıyor
- PolyFlow reposundan keşfedildi, 6/6 coin canlı doğrulandı
- Kaynak değişebilir — fallback stratejisi planlanmalı
- Streaming-primary: polling ana yöntem değil
- Bu modül delta kuralı ve force sell delta drop için gerekli coin USD fiyatını üretir

coin canlı USD fiyatı != outcome price (up_price/down_price)
coin canlı USD fiyatı != PTB (PTB = event açılışındaki sabit referans)

Desteklenen coinler:
  BTC, ETH, SOL, DOGE, XRP, BNB
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

import websockets

from backend.domain.startup_guard import HealthIncident, HealthSeverity
from backend.logging_config.service import get_logger, log_event

logger = get_logger("market_data.coin_price")


# Coin → RTDS symbol mapping
COIN_SYMBOLS: dict[str, str] = {
    "BTC": "btcusdt",
    "ETH": "ethusdt",
    "SOL": "solusdt",
    "DOGE": "dogeusdt",
    "XRP": "xrpusdt",
    "BNB": "bnbusdt",
}

# Reverse lookup: rtds_symbol → coin
_SYMBOL_TO_COIN: dict[str, str] = {v: k for k, v in COIN_SYMBOLS.items()}

RTDS_LIVE_URL = "wss://ws-live-data.polymarket.com"
RTDS_HEADERS = {
    "Origin": "https://polymarket.com",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
    ),
}

# Price validation bounds
PRICE_MIN = 0.00001   # DOGE gibi çok küçük fiyatlar
PRICE_MAX = 1_000_000  # BTC gibi büyük fiyatlar

# Stale threshold — bu kadar süre güncelleme gelmezse stale
DEFAULT_STALE_THRESHOLD_SEC = 15.0


class CoinPriceStatus(str, Enum):
    """Coin USD fiyat durumu."""
    FRESH = "fresh"
    STALE = "stale"
    WAITING = "waiting"     # henüz hiç veri gelmedi
    INVALID = "invalid"     # geçersiz veri


@dataclass
class CoinPriceRecord:
    """Tek bir coin'in canlı USD fiyat kaydı.

    Attributes:
        coin: Coin sembolü (BTC, ETH, vb.)
        usd_price: Canlı USD fiyatı (örn: 67260.12)
        status: FRESH / STALE / WAITING / INVALID
        updated_at: Son güncelleme zamanı (UTC)
        source: Veri kaynağı
        stale_threshold_sec: Bu kadar süre güncelleme gelmezse STALE
    """
    coin: str
    usd_price: float = 0.0
    status: CoinPriceStatus = CoinPriceStatus.WAITING
    updated_at: datetime | None = None
    source: str = "rtds_crypto_prices"
    stale_threshold_sec: float = DEFAULT_STALE_THRESHOLD_SEC

    @property
    def is_fresh(self) -> bool:
        if self.status in (CoinPriceStatus.INVALID, CoinPriceStatus.WAITING):
            return False
        if self.updated_at is None:
            return False
        age = (datetime.now(timezone.utc) - self.updated_at).total_seconds()
        return age <= self.stale_threshold_sec

    @property
    def is_stale(self) -> bool:
        if self.updated_at is None:
            return False
        age = (datetime.now(timezone.utc) - self.updated_at).total_seconds()
        return age > self.stale_threshold_sec

    @property
    def age_seconds(self) -> float | None:
        if self.updated_at is None:
            return None
        return (datetime.now(timezone.utc) - self.updated_at).total_seconds()

    def check_freshness(self) -> None:
        """Update status based on current freshness."""
        if self.status in (CoinPriceStatus.INVALID, CoinPriceStatus.WAITING):
            return
        if self.is_stale:
            self.status = CoinPriceStatus.STALE


class CoinPriceClient:
    """Polymarket RTDS'ten coin canlı USD fiyatlarını çeken WS client.

    Runtime authoritative source olarak davranır ama resmi olmayan kaynak
    olduğu için source state ve stale handling açık tutulur.

    Kullanım:
        client = CoinPriceClient()
        await client.connect()
        await client.subscribe(["BTC", "ETH", "SOL"])
        # ... mesajlar callback ile gelir
        await client.disconnect()

    Veya:
        client = CoinPriceClient()
        client.set_coins(["BTC", "ETH", "SOL"])
        await client.poll_once()  # tek batch fetch
    """

    # Default resubscribe interval — admin/advanced safety ayarı
    DEFAULT_RESUB_INTERVAL_MS = 150

    def __init__(
        self,
        ws_url: str | None = None,
        stale_threshold_sec: float = DEFAULT_STALE_THRESHOLD_SEC,
        resub_interval_ms: int = DEFAULT_RESUB_INTERVAL_MS,
    ):
        self._ws_url = ws_url or RTDS_LIVE_URL
        self._stale_threshold = stale_threshold_sec
        self._resub_interval = resub_interval_ms / 1000.0  # ms → seconds
        self._records: dict[str, CoinPriceRecord] = {}
        self._coins: list[str] = []
        self._total_updates: int = 0
        self._last_connect_at: datetime | None = None
        from collections import deque
        self._health_incidents: deque = deque(maxlen=100)  # FIFO cap
        self._running: bool = False
        self._task: asyncio.Task | None = None

        # Telemetry
        self._resub_count: int = 0
        self._reconnect_count: int = 0
        self._empty_batch_streak: int = 0
        self._connection_start: float = 0.0

    # ─── Records ───

    def get_price(self, coin: str) -> CoinPriceRecord | None:
        """Get coin price record with freshness check."""
        record = self._records.get(coin)
        if record:
            record.check_freshness()
        return record

    def get_usd_price(self, coin: str) -> float:
        """Get coin USD price. Returns 0.0 if not available."""
        record = self.get_price(coin)
        if record and record.status == CoinPriceStatus.FRESH:
            return record.usd_price
        return 0.0

    def get_all_prices(self) -> dict[str, CoinPriceRecord]:
        """Get all coin price records with freshness check."""
        for r in self._records.values():
            r.check_freshness()
        return dict(self._records)

    def set_coins(self, coins: list[str]) -> None:
        """Set which coins to track."""
        self._coins = [c.upper() for c in coins]
        # Pre-create records for tracking
        for coin in self._coins:
            if coin not in self._records:
                self._records[coin] = CoinPriceRecord(
                    coin=coin,
                    stale_threshold_sec=self._stale_threshold,
                )

    @property
    def fresh_count(self) -> int:
        return sum(1 for r in self._records.values() if r.is_fresh)

    @property
    def stale_count(self) -> int:
        return sum(1 for r in self._records.values() if r.is_stale)

    @property
    def total_updates(self) -> int:
        return self._total_updates

    @property
    def resub_count(self) -> int:
        """Toplam resubscribe sayisi."""
        return self._resub_count

    @property
    def reconnect_count(self) -> int:
        """Baglanti kopup yeniden baglanma sayisi."""
        return self._reconnect_count

    @property
    def connection_uptime_seconds(self) -> float:
        """Mevcut baglantinin suresi (saniye)."""
        if self._connection_start > 0:
            return time.time() - self._connection_start
        return 0.0

    @property
    def empty_batch_streak(self) -> int:
        """Ard arda bos batch sayisi."""
        return self._empty_batch_streak

    # ─── Batch Poll (PolyFlow pattern) ───

    async def poll_once(self) -> dict[str, float]:
        """Tek batch WS bağlantısıyla tüm coinlerin fiyatını çek.

        PolyFlow pattern: connect → subscribe → receive → close.
        ~500ms'de tüm coinleri alır.

        Returns:
            Dict of coin → USD price.
        """
        if not self._coins:
            return {}

        results: dict[str, float] = {}

        try:
            async with websockets.connect(
                self._ws_url,
                ping_interval=None,
                close_timeout=3,
                additional_headers=RTDS_HEADERS,
            ) as ws:
                self._last_connect_at = datetime.now(timezone.utc)

                # Subscribe all coins
                for coin in self._coins:
                    rtds_sym = COIN_SYMBOLS.get(coin)
                    if not rtds_sym:
                        continue
                    sub_msg = json.dumps({
                        "action": "subscribe",
                        "subscriptions": [{
                            "topic": "crypto_prices",
                            "type": "*",
                            "filters": json.dumps({"symbol": rtds_sym}),
                        }],
                    })
                    await ws.send(sub_msg)

                # Receive until all coins received or timeout
                deadline = time.time() + 3.0
                while len(results) < len(self._coins) and time.time() < deadline:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        if isinstance(raw, bytes):
                            raw = raw.decode("utf-8", errors="ignore")
                        if not raw or not raw.strip():
                            continue

                        data = json.loads(raw)
                        payload = data.get("payload", {})
                        if not isinstance(payload, dict):
                            continue

                        rtds_sym = payload.get("symbol", "")
                        coin = _SYMBOL_TO_COIN.get(rtds_sym)
                        if not coin:
                            continue

                        # Extract price from data array or direct value
                        price = self._extract_price(payload)
                        if price is not None and self._is_valid_price(price):
                            self._update_record(coin, price)
                            results[coin] = price

                    except asyncio.TimeoutError:
                        continue
                    except websockets.exceptions.ConnectionClosed:
                        break

        except Exception as e:
            log_event(
                logger, logging.WARNING,
                f"Coin price poll failed: {e}",
                entity_type="coin_price",
                entity_id="poll_error",
            )
            self._health_incidents.append(HealthIncident(
                severity=HealthSeverity.WARNING,
                category="market_data",
                message=f"Coin price WS poll failed: {e}",
                suggested_action="Check wss://ws-live-data.polymarket.com availability",
            ))

        log_event(
            logger, logging.DEBUG,
            f"Coin price poll: {len(results)}/{len(self._coins)} coins",
            entity_type="coin_price",
            entity_id="poll_complete",
            payload={"received": len(results), "expected": len(self._coins)},
        )

        return results

    # ─── Persistent Connection Loop ───

    async def run_forever(self) -> None:
        """Persistent WS bağlantısı + 200ms resubscribe döngüsü.

        Model: tek bağlantı aç → her 200ms resubscribe → fiyat al → tekrar
        Reconnect sadece bağlantı koparsa yapılır.
        Her cycle yeni bağlantı AÇMAZ — tek persistent connection.

        Kaynak: wss://ws-live-data.polymarket.com
        Bu endpoint resubscribe ile yeni snapshot verir.
        Sürekli push streaming yapmaz — resubscribe tetikler.
        """
        self._running = True
        fail_count = 0
        resub_interval = self._resub_interval

        log_event(
            logger, logging.INFO,
            f"Coin price persistent loop started — {len(self._coins)} coins, {resub_interval*1000:.0f}ms interval",
            entity_type="coin_price",
            entity_id="loop_started",
        )

        while self._running:
            try:
                await self._persistent_loop(resub_interval)
                fail_count = 0
            except Exception as e:
                fail_count += 1
                self._reconnect_count += 1
                log_event(
                    logger, logging.WARNING,
                    f"Coin price connection failed ({fail_count}): {e}",
                    entity_type="coin_price",
                    entity_id="connection_failure",
                )
                # Reconnect backoff
                wait = min(fail_count * 2, 10)
                if self._running:
                    await asyncio.sleep(wait)

        log_event(
            logger, logging.INFO,
            "Coin price persistent loop stopped",
            entity_type="coin_price",
            entity_id="loop_stopped",
        )

    async def _persistent_loop(self, resub_interval: float) -> None:
        """Tek persistent bağlantı içinde resubscribe döngüsü."""
        if not self._coins:
            await asyncio.sleep(1)
            return

        # Subscribe mesajlarını hazırla
        sub_msgs = []
        for coin in self._coins:
            rtds_sym = COIN_SYMBOLS.get(coin)
            if rtds_sym:
                sub_msgs.append(json.dumps({
                    "action": "subscribe",
                    "subscriptions": [{
                        "topic": "crypto_prices",
                        "type": "*",
                        "filters": json.dumps({"symbol": rtds_sym}),
                    }],
                }))

        async with websockets.connect(
            self._ws_url,
            ping_interval=None,
            close_timeout=3,
            additional_headers=RTDS_HEADERS,
        ) as ws:
            self._last_connect_at = datetime.now(timezone.utc)
            self._connection_start = time.time()
            last_resub = 0.0

            while self._running:
                # Resubscribe (configurable interval)
                now = time.time()
                if now - last_resub >= resub_interval:
                    for msg in sub_msgs:
                        await ws.send(msg)
                    last_resub = now
                    self._resub_count += 1

                # Mesajları oku
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=0.05)
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8", errors="ignore")
                    if not raw or not raw.strip():
                        continue

                    data = json.loads(raw)
                    payload = data.get("payload", {})
                    if not isinstance(payload, dict):
                        continue

                    rtds_sym = payload.get("symbol", "")
                    coin = _SYMBOL_TO_COIN.get(rtds_sym)
                    if not coin:
                        continue

                    price = self._extract_price(payload)
                    if price is not None and self._is_valid_price(price):
                        self._update_record(coin, price)

                except asyncio.TimeoutError:
                    continue

    async def start(self) -> asyncio.Task:
        """Batch loop'u background task olarak başlat."""
        if self._running:
            return self._task
        self._task = asyncio.create_task(self.run_forever(), name="coin_price_loop")
        return self._task

    async def stop(self) -> None:
        """Batch loop'u durdur."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    # ─── Internal ───

    def _update_record(self, coin: str, price: float) -> None:
        """Update a coin price record."""
        if coin not in self._records:
            self._records[coin] = CoinPriceRecord(
                coin=coin,
                stale_threshold_sec=self._stale_threshold,
            )

        record = self._records[coin]
        record.usd_price = price
        record.status = CoinPriceStatus.FRESH
        record.updated_at = datetime.now(timezone.utc)
        record.source = "rtds_crypto_prices"
        self._total_updates += 1

    @staticmethod
    def _extract_price(payload: dict) -> float | None:
        """Extract USD price from RTDS payload.

        Handles two formats:
        1. payload.data[].value (array format)
        2. payload.value (direct format)
        """
        # Format 1: data array
        arr = payload.get("data", [])
        if arr and isinstance(arr, list):
            last = arr[-1]
            if isinstance(last, dict):
                v = last.get("value") or last.get("v")
                if v:
                    try:
                        return float(v)
                    except (ValueError, TypeError):
                        return None

        # Format 2: direct value
        v = payload.get("value")
        if v:
            try:
                return float(v)
            except (ValueError, TypeError):
                return None

        return None

    @staticmethod
    def _is_valid_price(price: float) -> bool:
        """Check if a USD coin price is within valid bounds."""
        return PRICE_MIN <= price <= PRICE_MAX

    # ─── Health ───

    def get_health_incidents(self) -> list[HealthIncident]:
        """Get health incidents for coin price feed."""
        incidents = list(self._health_incidents)
        for coin, record in self._records.items():
            record.check_freshness()
            if record.status == CoinPriceStatus.STALE:
                incidents.append(HealthIncident(
                    severity=HealthSeverity.WARNING,
                    category="market_data",
                    message=f"Coin USD price stale for {coin} (age: {record.age_seconds:.0f}s)",
                    suggested_action="Check RTDS crypto_prices WS connection",
                ))
            elif record.status == CoinPriceStatus.WAITING:
                incidents.append(HealthIncident(
                    severity=HealthSeverity.WARNING,
                    category="market_data",
                    message=f"No coin USD price received for {coin}",
                    suggested_action="Check RTDS crypto_prices subscription",
                ))
        return incidents

    def clear_health_incidents(self) -> None:
        self._health_incidents.clear()

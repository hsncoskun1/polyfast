# POLYFAST BTC BOT — NİHAİ UYGULAMA PLANI

---

## ÜRÜN

Polymarket BTC 5M Up/Down event'lerini otomatik takip eden, kurallara göre paper veya live trade yapan, 7/24 müdahalesiz çalışan, local tek kullanıcı trading botu. Backend tek otorite. Frontend sadece display + kontrol iletimi. Spread kuralı sistemde YOK.

---

## CREDENTIAL GÜVENLİK KURALLARI (BAĞLAYICI)

1. Credential dosyası `.gitignore`'a eklenir — ASLA repo'ya girmez
2. Credential disk'te şifrelenmiş saklanır (AES-256 veya Fernet)
3. Runtime'da memory'de decrypt edilir, disk'te ASLA plaintext tutulmaz
4. Hiçbir log satırında credential geçmez — tüm log output'ları maskelenir
5. API response'larında credential dönmez — sadece `has_key: true/false` status
6. Frontend'e credential GÖNDERİLMEZ — sadece "yüklü mü" bilgisi
7. Credential dosya yolu: `data/credentials.enc` (gitignore'da)
8. Şifreleme anahtarı: kullanıcının belirlediği passphrase'den türetilir veya makine bazlı key

---

## AYARLAR MİMARİSİ

### Kural Ayarları (Settings paneli)
Kullanıcının frontend'den değiştirebileceği trade kuralları:

| Ayar | Tip | Default | Açıklama |
|------|-----|---------|----------|
| enabled | bool | true | BTC trade aktif mi |
| side_mode | enum | dominant_only | dominant_only / up_only / down_only |
| order_amount | float | 1.0 | Trade başına USD |
| time_min | int | 30 | Minimum kalan saniye |
| time_max | int | 270 | Maximum kalan saniye |
| price_min | int | 20 | Minimum dominant price (0-100) |
| price_max | int | 80 | Maximum dominant price (0-100) |
| delta_threshold | float | 0.03 | Minimum USD fark (coin - PTB) |
| event_max | int | 1 | Event başına max pozisyon |
| tp_pct | float | 5.0 | Take profit yüzdesi |
| sl_pct | float | 3.0 | Stop loss yüzdesi |
| fs_time_enabled | bool | true | Force sell zaman kuralı |
| fs_time_seconds | int | 30 | Force sell kalan saniye |
| fs_pnl_enabled | bool | false | Force sell PnL kuralı |
| fs_pnl_pct | float | 5.0 | Force sell PnL eşiği |

NOT: Spread ayarı ve kuralı sistemde YOK. Rule engine 5 rule çalıştırır: Time, Price, Delta, EventMax, BotMax.

### Gelişmiş Ayarlar (Advanced Settings paneli)
Operasyonel parametreler — retry, interval, timeout:

| Ayar | Tip | Default | Açıklama |
|------|-----|---------|----------|
| evaluation_interval_ms | int | 200 | Evaluation döngü aralığı |
| exit_cycle_interval_ms | int | 50 | Exit kontrol aralığı |
| discovery_retry_schedule | list | [2,4,8,16] | Discovery retry saniyeleri |
| discovery_retry_steady | int | 10 | Discovery steady retry |
| ptb_retry_schedule | list | [2,4,8,16] | PTB retry saniyeleri |
| ptb_retry_steady | int | 10 | PTB steady retry |
| balance_verify_retry_sec | int | 30 | Balance doğrulama retry |
| balance_passive_refresh_sec | int | 20 | Balance pasif yenileme |
| outcome_stale_sec | int | 30 | Outcome price stale eşiği |
| coin_price_stale_sec | int | 15 | Coin USD stale eşiği |
| balance_stale_sec | int | 90 | Balance stale eşiği |
| tp_retry_interval_ms | int | 400 | TP close retry aralığı |
| sl_retry_interval_ms | int | 250 | SL close retry aralığı |
| fs_retry_interval_ms | int | 200 | FS close retry aralığı |
| max_close_retries | int | 10 | Maximum close deneme |
| claim_retry_initial_sec | int | 5 | Claim ilk retry |
| claim_retry_second_sec | int | 10 | Claim ikinci retry |
| claim_retry_steady_sec | int | 20 | Claim steady retry |
| claim_max_retries | int | 20 | Claim max deneme |
| ws_reconnect_backoff_base | float | 2.0 | WS reconnect baz |
| ws_reconnect_backoff_max | float | 30.0 | WS reconnect max |
| supervisor_interval_sec | int | 10 | Supervisor kontrol aralığı |
| entry_order_timeout_sec | float | 5.0 | Entry order timeout |
| exit_order_timeout_sec | float | 5.0 | Exit order timeout |
| sl_jump_threshold | float | 0.15 | SL jump koruması (%15) |
| min_order_usd | float | 5.0 | Minimum order tutarı |

Tüm bu değerler backend'de config schema'dan gelir. Frontend save → backend validate → persist.

---

## VERİ KAYNAKLARI

| Veri | Endpoint | Credential |
|------|----------|------------|
| Event keşfi | Gamma API `https://gamma-api.polymarket.com/events?tag_slug=5M` | Gereksiz |
| Outcome fiyat | CLOB WS `wss://ws-subscriptions-clob.polymarket.com/ws/market` | Gereksiz |
| BTC USD fiyat | Live Data WS `wss://ws-live-data.polymarket.com` | Gereksiz |
| PTB | Polymarket SSR `https://polymarket.com/event/{slug}?__nextDataReq=1` | Gereksiz |
| Balance | CLOB SDK `get_balance_allowance` | Gerekli |
| Order | CLOB SDK `create_market_order` (FOK) | Gerekli |
| Market resolution | CLOB SDK `get_market` | Gerekli |

SDK: py_clob_client, chain_id=137, signature_type=2, feeRate=0.10 (1000 bps)

---

## KORUNAN ESKİ BACKEND DİSİPLİNİ

1. Startup → restore_state → balance verify → DEGRADED gate
2. Slot-aware discovery (300s cycle, retry [2,4,8,16,10s], slot sınırı kontrol)
3. Stale veri → WAITING → sinyal engelleme (outcome=30s, coin=15s, balance=90s)
4. PTB lock (bir kez alındığında üzerine yazma yok)
5. Rule priority: FAIL > WAITING > PASS (tek FAIL = sinyal yok)
6. TP reevaluate (close öncesi PnL tekrar kontrol, düşmüşse iptal)
7. SL LATCH + jump threshold (geri alınamaz + ani %15 düşüşte atla)
8. FS LATCH + time safety override (geri alınamaz + stale PnL'de time yeterli)
9. Close retry: TP=400ms, SL=250ms, FS=200ms, max=10
10. Settlement + claim retry: 5/10/20s steady, max 20
11. PnL = net (fee düşülmüş): `fee = C x feeRate x p x (1-p)`
12. Position state machine: 6 state, izinli geçişler
13. Config-driven tüm operasyonel değerler
14. 7/24 sonsuz döngü — discovery hiç durmaz

## YENİ BACKEND'DEN ALINAN İYİLEŞTİRMELER

1. Supervisor loop (10s, task ölürse auto-restart)
2. Periodic flush (~30s, crash'te max 30s kayıp)
3. PENDING_OPEN cleanup (restart'ta phantom temizleme)
4. Per-side bid/ask pipeline (up_bid, up_ask, down_bid, down_ask bağımsız)
5. Current slot ownership + condition_id rotation + RTDS resub
6. Discovery pagination (5 sayfa, 500 cap)
7. Slug timestamp = START (doğru)
8. Pipeline Gamma seed (WS öncesi dashboard'da fiyat)
9. Fee rate = 0.10 (doğru crypto rate)
10. Paper mode credential bypass + auto-dispatch
11. Position tracker reset (stop/start'ta stale counter temizleme)
12. Config-driven genişleme (supervisor, verify retry, SDK timeout hepsi config'den)

## SİSTEMDE OLMAYACAKLAR

- Spread kuralı ve ayarı (rule engine'den çıkarıldı, 5 rule)
- Multi-coin desteği (CoinSettings loop, coin selector, per-coin endpoint)
- Cloud / dağıtık mimari
- Çok kullanıcı
- Backtest
- Otomatik strateji optimizasyonu
- 5M dışında zaman dilimi
- Polling (frontend WS kullanır)

---

## FAZ PLANI

---

### FAZ 1: TEMEL ALTYAPI + CREDENTIAL

**Backend:**
- Config schema (Pydantic): kural ayarları + gelişmiş ayarlar tek schema
- SQLite persistence: init_db, positions, claims, btc_settings, registry, ptb_cache tabloları
- CredentialStore: şifrelenmiş disk storage, runtime decrypt, log maskeleme
- `.gitignore`: `data/credentials.enc`, `*.enc`, `.env`
- Logging config: structured JSON log, credential maskeleme, file output
- Health endpoint: `GET /api/health`

**Frontend:**
- Proje setup: React + Vite + TypeScript
- Tek sayfa layout: karanlık tema, monospace, operatör arayüzü
- Credential modal: API key, secret, passphrase, private_key input → backend'e POST
- Credential status göstergesi: yüklü / yüklü değil
- Bot kontrol butonları: Start, Stop (backend'e POST, sonuç göster)
- WebSocket hook altyapısı: `/ws/dashboard` bağlantı + reconnect

**API:**
- `GET /api/health` — bot durumu
- `POST /api/bot/start` — bot başlat
- `POST /api/bot/stop` — bot durdur
- `POST /api/credential/update` — credential yükle (şifrele + kaydet)
- `GET /api/credential/status` — credential var mı (has_key: true/false, asla credential dönmez)

**Tamamlandı sayılır:** Backend ayağa kalkar, credential yüklenir ve şifrelenmiş saklanır, frontend'den bot start/stop yapılır, health endpoint çalışır.

---

### FAZ 2: VERİ KATMANI + DISCOVERY

**Backend:**
- PublicMarketClient (Gamma API, timeout=15s, retry=3)
- DiscoveryEngine: BTC-only filtre, pagination (5 sayfa), slug=START
- DiscoveryLoop: slot-aware (300s), retry [2,4,8,16,10s], slot sınırı kontrol
- EventRegistry + SafeSync (3-miss delist, open position koruması)
- LivePricePipeline: per-side bid/ask, Gamma seed (outcomePrices), stale=30s
- RTDSClient: WS bağlantı, auto-reconnect (backoff 2→30s), subscribe/resubscribe
- WSPriceBridge: token routing (token_id → condition_id, asset, side)
- CoinPriceClient: BTC USD, `wss://ws-live-data.polymarket.com`, stale=15s
- PTBFetcher + SSRPTBAdapter: retry [2,4,8,16,10s], lock, regex scrape
- Current slot ownership: tek aktif event, condition_id rotation
- BTC subscription: event bul → bridge register → WS subscribe → pipeline'a fiyat

**Frontend:**
- Dashboard ana panel: BTC USD fiyat, UP/DOWN bid/ask, PTB, delta (tümü WS'ten)
- Event bilgisi: slug, remaining seconds, event URL (tıklanabilir link)
- Bağlantı durumu: WS connected / disconnected göstergesi
- Veri freshness: stale uyarısı (30s outcome, 15s coin)

**API:**
- `WS /ws/dashboard` — backend her evaluation cycle sonrası push (200ms)

**Tamamlandı sayılır:** Bot BTC event bulur, WS'ten outcome fiyat gelir, PTB çekilir, coin USD gelir, frontend'de tüm veriler realtime görünür.

---

### FAZ 3: EVALUATION + PAPER TRADE

**Backend:**
- EvaluationContext: BTC-only, runtime state'ten doldur
- RuleEngine: 5 rule (Time, Price, Delta, EventMax, BotMax — spread YOK)
- EvaluationLoop: 200ms interval, ENTRY → dispatch
- BtcSettings: tek config objesi, frontend'den save/load
- OrderExecutor: paper fill (dominant_price + fee=0.10)
- PositionTracker: 6 state machine, event_fill_count, reset()
- BalanceManager: paper deduct/add, stale=90s, passive refresh=20s
- FeeCalculator: `C x feeRate x p x (1-p)`, feeRate=0.10
- Current slot guard: order sadece live slot event'ine
- Duplicate guard: PENDING_OPEN check
- Balance verify: startup zorunlu, fail → DEGRADED, 30s retry

**Frontend:**
- Kural ayarları paneli: tüm kural ayarları (Settings modal veya panel)
- 5 rule durumu: Time, Price, Delta, EventMax, BotMax — her biri pass/fail/waiting/disabled
- Signal göstergesi: READY / NOT READY
- Pozisyon paneli: açık pozisyon varsa side, fill_price, PnL%, state göster
- Trade geçmişi: son trade'ler listesi (side, PnL%, close reason, zaman)
- Balance göstergesi: mevcut bakiye
- Save/Load: ayarlar backend'e POST, backend validate + persist, frontend onay göster

**API:**
- `GET /api/btc/settings` — mevcut ayarları oku
- `POST /api/btc/settings` — ayarları güncelle (backend validate + persist)
- WS mesajına rules, signal_ready, position, balance, session_trades eklenir

**Tamamlandı sayılır:** Tüm kurallar pass → ENTRY → paper fill → pozisyon açılır → balance düşer. Frontend'de kurallar, sinyal, pozisyon, balance realtime görünür. Ayarlar frontend'den değiştirilir.

---

### FAZ 4: EXIT + SETTLEMENT + CLAIM

**Backend:**
- ExitEvaluator: TP (reevaluate), SL (latch + jump threshold %15), FS (latch + time safety override)
- ExitExecutor: paper close, retry (TP=400ms, SL=250ms, FS=200ms), max=10
- ExitOrchestrator: 50ms cycle, pipeline'dan held-side bid, TP/SL/FS evaluate → close
- SettlementOrchestrator: paper → auto-resolved
- ClaimManager: paper redeem → balance'a payout (WON) / $0 (LOST), retry 5/10/20s max 20

**Frontend:**
- Pozisyon panelinde TP/SL/FS durumu: mevcut PnL vs threshold, tetiklendiyse close reason
- Close geçmişi: TP/SL/FS ile kapanan trade'ler ayrı gösterilir
- Claim durumu: pending / success / failed
- PnL özeti: toplam session PnL, win/loss sayısı

**Tamamlandı sayılır:** Paper BUY → hold → TP veya SL tetiklenir → close → settlement → claim → balance güncellenir. Frontend'de tüm cycle izlenebilir. Tam döngü kesintisiz çalışır.

---

### FAZ 5: 7/24 + PERSISTENCE + GELİŞMİŞ AYARLAR

**Backend:**
- Supervisor loop: 10s, 5 task (discovery, evaluation, coin_client, exit_cycle, rtds_ws), auto-restart
- Periodic flush: ~30s, positions + claims SQLite'a
- PENDING_OPEN cleanup: restart'ta reject_fill
- restore_state: btc_settings, registry, ptb, positions, claims
- Graceful shutdown: loops durdur → final flush
- DEGRADED mode: balance fail → yeni trade engelle, exit devam, 30s retry

**Frontend:**
- Gelişmiş ayarlar paneli (Advanced Settings): tüm retry interval, retry count, timeout, stale threshold düzenlenebilir
- Bot status detayı: NORMAL / DEGRADED / STOPPED
- Supervisor status: task'ların çalışma durumu
- Session bilgisi: uptime, toplam trade, toplam PnL

**API:**
- `GET /api/btc/advanced-settings` — gelişmiş ayarları oku
- `POST /api/btc/advanced-settings` — gelişmiş ayarları güncelle

**Tamamlandı sayılır:** Bot 1+ saat kesintisiz paper trade yapar. Process kill → restart → pozisyon korunur. Supervisor ölmüş task'ı restart eder. Gelişmiş ayarlar frontend'den düzenlenebilir. Periodic flush çalışır.

---

### FAZ 6: LIVE MODE

**Backend:**
- Live FOK order: py_clob_client SDK, signature_type=2, funder address
- Live sell: SDK sell, tüm shares, fill_price=taking/making
- Live balance fetch: CLOB API get_balance_allowance
- Live market resolution: CLOB API get_market → closed + winner
- Live claim/redeem: SDK veya relayer
- Paper/Live switch: config'den, runtime'da değiştirilemez (restart gerekli)
- LIVE_ORDER_ENABLED gate: çift kilit güvenliği

**Frontend:**
- Paper/Live mode göstergesi (belirgin, karıştırılamaz)
- Live mode uyarısı: "Gerçek para kullanılıyor"
- Live balance: CLOB API'den gerçek bakiye

**Tamamlandı sayılır:** Gerçek BUY → fill → TP/SL → close → settle → claim. Balance doğru. $5-10 ile test edilmiş.

---

## FRONTEND ↔ BACKEND İLETİŞİM

### WebSocket: `/ws/dashboard`
Backend → Frontend, her evaluation cycle (200ms) sonrası push:

```json
{
  "type": "tick",
  "timestamp": 1775934500,
  "slot_start": 1775934300,
  "seconds_remaining": 180,
  "event_slug": "btc-updown-5m-1775934300",
  "event_url": "https://polymarket.com/event/btc-updown-5m-1775934300",
  "btc_usd": 73500.00,
  "ptb": 73400.00,
  "delta": 100.00,
  "up_bid": 0.52,
  "up_ask": 0.53,
  "down_bid": 0.47,
  "down_ask": 0.48,
  "rules": {
    "time": "pass",
    "price": "pass",
    "delta": "pass",
    "event_max": "pass",
    "bot_max": "pass"
  },
  "signal_ready": true,
  "position": null,
  "balance": 7.73,
  "session_trades": 3,
  "session_pnl": 0.42,
  "paper_mode": true,
  "bot_running": true,
  "ws_connected": true,
  "trading_enabled": true,
  "bot_status": "normal"
}
```

Position dolu olduğunda:
```json
"position": {
  "side": "UP",
  "fill_price": 0.52,
  "pnl_pct": 2.3,
  "state": "open_confirmed",
  "close_reason": null,
  "tp_threshold": 5.0,
  "sl_threshold": -3.0
}
```

### REST API Endpoint'leri

| Endpoint | Yöntem | Amaç | Faz |
|----------|--------|------|-----|
| `/api/health` | GET | Bot durumu | 1 |
| `/api/bot/start` | POST | Bot başlat | 1 |
| `/api/bot/stop` | POST | Bot durdur | 1 |
| `/api/credential/update` | POST | Credential yükle | 1 |
| `/api/credential/status` | GET | Credential var mı | 1 |
| `/ws/dashboard` | WS | Realtime veri stream | 2 |
| `/api/btc/settings` | GET | Kural ayarları oku | 3 |
| `/api/btc/settings` | POST | Kural ayarları kaydet | 3 |
| `/api/btc/advanced-settings` | GET | Gelişmiş ayarlar oku | 5 |
| `/api/btc/advanced-settings` | POST | Gelişmiş ayarlar kaydet | 5 |

Frontend → Backend: REST POST (ayar kaydetme, bot kontrol, credential)
Backend → Frontend: WebSocket push (tüm dashboard verisi)

---

## TEKNİK REFERANSLAR

### Eski backend kodu
`C:\polyfast yedek\faz7-extract\polyfast\backend\`

### Yeni backend kodu (fix'li)
`C:\polyfast\backend\`

### Birleşik referans dokümanı
`C:\polyfast\POLYFAST_BTC_REFERENCE.md`

Bu dosya eski backend'in tam teknik işleyiş raporu, eski vs yeni kıyaslama, veri kaynakları, config defaults ve davranış matrisini içerir.

### Position State Machine
```
PENDING_OPEN → OPEN_CONFIRMED (fill)
PENDING_OPEN → CLOSED (FOK reject)
OPEN_CONFIRMED → CLOSING_REQUESTED (exit kararı)
CLOSING_REQUESTED → CLOSE_PENDING (order gönderildi)
CLOSING_REQUESTED → OPEN_CONFIRMED (TP reevaluate iptal — SADECE TP)
CLOSE_PENDING → CLOSED (fill)
CLOSE_PENDING → CLOSE_FAILED (başarısız)
CLOSE_FAILED → CLOSING_REQUESTED (retry)
CLOSE_FAILED → CLOSED (give up)
```

### 5 Rule (Spread YOK)
1. **Time:** time_min ≤ remaining ≤ time_max
2. **Price:** price_min ≤ dominant_price_100 ≤ price_max
3. **Delta:** abs(btc_usd - ptb) ≥ delta_threshold
4. **EventMax:** event_fill_count < event_max
5. **BotMax:** open_position_count < bot_max

Karar: FAIL > WAITING > PASS. Tek FAIL = sinyal yok.

### PnL Formülü
```
gross_value = shares x current_price
est_fee = shares x fee_rate x p x (1-p)
net_value = gross_value - est_fee
net_pnl = net_value - requested_amount_usd
pnl_pct = (net_pnl / requested_amount_usd) x 100
fee_rate = 0.10 (1000 bps crypto)
```

### Davranış Matrisi
Tam matris için `POLYFAST_BTC_REFERENCE.md` Bölüm 1, madde 6'ya bakınız.

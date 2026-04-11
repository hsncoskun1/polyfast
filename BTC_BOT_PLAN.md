# POLYFAST BTC-ONLY BOT — SIFIRDAN YAZIM PLANI

Bu plan, eski backend'in kanıtlanmış disiplinini temel alır ve yeni backend'de eklenen faydalı özellikleri entegre eder.

---

## REFERANS DOSYALAR

- Eski backend: `C:\polyfast yedek\faz7-extract\polyfast\backend\`
- Yeni backend: `C:\polyfast\backend\`
- Frontend: `C:\polyfast\frontend\`

---

## 1. ÜRÜN TANIMI

Tek coin (BTC), tek kullanıcı, local-first, 7/24 otonom çalışan Polymarket 5M Up/Down trading botu.

- Paper mode öncelikli (test aşaması)
- Live mode kullanıcı kararıyla aktif
- Backend tek otorite — frontend karar üretmez
- Tüm veri kaynakları eski backend ile aynı

---

## 2. VERİ KAYNAKLARI (ESKİ BACKEND İLE BİREBİR AYNI)

| Veri | Kaynak | Yöntem | Credential |
|------|--------|--------|------------|
| Event keşfi | Gamma API `/events?tag_slug=5M` | HTTP GET | Gereksiz |
| Outcome fiyat (UP/DOWN bid/ask) | CLOB WS `wss://ws-subscriptions-clob.polymarket.com/ws/market` | WebSocket push | Gereksiz |
| Coin USD fiyat | Live Data WS `wss://ws-live-data.polymarket.com` | WebSocket polling | Gereksiz |
| PTB (open price) | Polymarket SSR `polymarket.com/event/{slug}?__nextDataReq=1` | HTTP GET + regex | Gereksiz |
| Balance | CLOB API `get_balance_allowance` | SDK call | API key + secret + passphrase + private_key |
| Order gönderme | CLOB API `create_market_order` | SDK call (FOK) | Aynı |
| Market resolution | CLOB API `get_market` | SDK call | Aynı |

---

## 3. ESKİ BACKEND DİSİPLİNİ (KORUNACAK)

### A) STARTUP SIRASI
1. Config yükle (Pydantic schema, validated defaults)
2. CredentialStore oluştur (boş başlar)
3. Tüm component'leri oluştur (data layer → execution layer → orchestrator)
4. `restore_state()` — SQLite'tan memory'ye yükle (settings, registry, PTB, positions, claims)
5. Balance verify — başarılıysa NORMAL, başarısızsa DEGRADED (yeni trade yok, exit devam)
6. Loop'ları başlat: discovery → evaluation → exit cycle
7. DEGRADED ise 30s verify retry loop başlat

### B) DISCOVERY DİSİPLİNİ
- 5 dakikalık slot bazlı tarama
- Gamma API: `tag_slug=5M, closed=false`
- Filtreleme: crypto + 5m + "up or down" + current/upcoming (30dk lookahead)
- Slug timestamp = START (end = start + 300)
- Event bulursa → slot sonuna kadar bekle, yeniden tarama YAPMA
- Event bulamazsa → retry [2, 4, 8, 16, 10s steady] slot içinde
- Slot sınırı geçilirse → retry dur, yeni slot'a geç
- 7/24 sonsuz döngü — hiç durmuyor

### C) SUBSCRIPTION + CANLI VERİ DİSİPLİNİ
- Bridge: token_id → (condition_id, asset, side) routing
- WS subscribe: event bulununca token_id'ler subscribe
- WS'ten gelen fiyat → pipeline'a yaz (FRESH status)
- Coin USD: WS polling ile sürekli güncelle
- PTB: SSR scrape + retry [2,4,8,16,10s] event bitene kadar
- PTB lock: bir kez alındığında üzerine yazma yok
- Stale threshold: outcome=30s, coin=15s, balance=90s

### D) EVALUATION DİSİPLİNİ
- 200ms interval, runtime state'ten oku (snapshot değil)
- 6 rule sırayla: Time → Price → Delta → Spread → EventMax → BotMax
- Karar birleştirme: FAIL > WAITING > PASS > NO_RULES
- Tek FAIL → NO_ENTRY
- WAITING → sinyal üretme (veri eksik)
- Stale veri → WAITING (sinyal engelleme)
- DISABLED rule → evaluation dışı

### E) ENTRY DİSİPLİNİ
- ENTRY sinyali → OrderExecutor.execute(OrderIntent)
- Paper: dominant_price ile simüle fill, balance deduct
- Live: FOK market order via SDK
- Current slot guard: sadece live slot event'ine order
- Balance stale guard: stale ise order reject
- Duplicate guard: PENDING_OPEN check

### F) EXIT DİSİPLİNİ
- TP: PnL-based (default 5%), reevaluate (iptal edilebilir)
- SL: PnL-based (default 3%), LATCH (geri alınamaz), jump threshold (15% → SL atla)
- FS: checkbox bazlı (time + PnL), LATCH, time safety override
- Close retry: TP=400ms, SL=250ms, FS=200ms, max=10
- PnL formülü: net (fee düşülmüş)
  - gross_value = shares × current_price
  - est_fee = shares × fee_rate × p × (1-p)
  - net_pnl = (gross_value - est_fee) - requested_amount_usd
  - pnl_pct = net_pnl / requested_amount_usd × 100

### G) POSITION STATE MACHINE
```
PENDING_OPEN → OPEN_CONFIRMED (fill geldi)
PENDING_OPEN → CLOSED (FOK rejected)
OPEN_CONFIRMED → CLOSING_REQUESTED (exit kararı)
CLOSING_REQUESTED → CLOSE_PENDING (order gönderildi)
CLOSING_REQUESTED → OPEN_CONFIRMED (TP reevaluate iptal — SADECE TP)
CLOSE_PENDING → CLOSED (fill geldi)
CLOSE_PENDING → CLOSE_FAILED (order başarısız)
CLOSE_FAILED → CLOSING_REQUESTED (retry)
CLOSE_FAILED → CLOSED (give up)
```

### H) SETTLEMENT + CLAIM
- Position CLOSED → settlement kontrol (market resolved mı?)
- Paper: her zaman resolved=True
- Live: CLOB API get_market → closed + winner check
- Claim retry: 5s → 10s → 20s steady, max 20
- WON → balance'a payout / LOST → $0

### I) BALANCE
- Startup: MANDATORY verify
- Post-fill: deduct (paper) / re-fetch (live)
- Post-close: add (paper) / re-fetch (live)
- Passive refresh: 20s interval
- Stale: 90s → order reject
- Fee: C × feeRate × p × (1-p), feeRate=0.10 (1000 bps crypto)

### J) CONFIG DEFAULTS (ESKİ BACKEND)

| Alan | Değer |
|------|-------|
| Evaluation interval | 200ms |
| Exit cycle interval | 50ms |
| Discovery retry | [2, 4, 8, 16]s + 10s steady |
| PTB retry | [2, 4, 8, 16]s + 10s steady |
| Balance verify retry | 30s |
| Balance passive refresh | 20s |
| TP close retry | 400ms |
| SL close retry | 250ms |
| FS close retry | 200ms |
| Max close retries | 10 |
| Claim retry | 5/10/20s steady, max 20 |
| WS reconnect backoff | 2→4→8→16→30s max |
| Outcome stale | 30s |
| Coin price stale | 15s |
| Balance stale | 90s |
| Lookahead | 1800s (30dk) |
| Min order USD | 5.0 |
| SafeSync delist | 3 miss |
| Time rule | 30-270s remaining |
| Price rule | 20-80 (0-100 ölçeği) |
| Delta threshold | 0.03 USD (BTC için) |
| Spread max | 0 (disabled) |
| Event max | 1 position per event |
| Bot max | 3 (tek coin'de 1 yeterli) |
| TP | 5% |
| SL | 3% |
| FS time | 30s remaining |
| FS PnL | disabled |
| Fee rate | 0.10 (1000 bps) |
| Signature type | 2 (proxy wallet) |

---

## 4. YENİ BACKEND'DEN ALINACAK FAYDALI ÖZELLİKLER

### ✅ KORUNACAK YENİ ÖZELLİKLER

| Özellik | Açıklama | Neden Faydalı |
|---------|----------|---------------|
| **Supervisor loop (10s)** | 5 task monitör, ölürse restart | Eski backend'de task ölürse respawn yok — 7/24 için kritik |
| **Periodic flush (~30s)** | Positions + claims SQLite'a periyodik yazma | Eski backend'de sadece shutdown flush — crash = state kaybı |
| **PENDING_OPEN cleanup** | Restart'ta phantom pozisyon temizleme (reject_fill) | Eski backend'de crash sonrası phantom kalıyordu |
| **Per-side bid/ask** | up_bid, up_ask, down_bid, down_ask bağımsız | Eski backend 1-x sentetik — gerçek market verisine daha uygun |
| **Current slot ownership** | Asset başına tek aktif event, condition_id rotation | Eski backend'de event_map'te son yazan kazanıyordu |
| **Condition_id rotation** | Slot değişince: eski unsub → yeni sub → RTDS resub | Eski backend'de rotation mantığı belirsizdi |
| **Discovery pagination** | 5 sayfa, 500 event cap | Eski backend tek sayfa limit=100 — current event'ler sonraki sayfalarda |
| **Slug timestamp = START** | Doğru: slug_ts = event başlangıcı | Eski backend END varsayıyordu (yanlış) |
| **Live FOK order + live sell** | SDK implementasyonu tam | Eski backend'de LIVE_ORDER_ENABLED=False idi |
| **Config-driven değerler** | Tüm retry/interval/timeout schema.py'de | Eski backend'de bazıları hardcoded |
| **Fee rate = 0.10** | Doğru crypto 5M rate | Eski backend 0.072 kullanıyordu (yanlış) |
| **Pipeline Gamma seed** | Discovery sırasında outcomePrices → pipeline | WS bağlanmadan önce dashboard'da fiyat görünür |
| **Paper mode credential bypass** | EligibilityGate paper'da credential aramaz | Credential olmadan paper test yapılabilir |
| **Paper mode auto-dispatch** | Paper'da ENTRY → otomatik order (enable_trading gereksiz) | 7/24 otonom çalışma, manuel kapı yok |
| **Position tracker reset** | Bot stop/start'ta stale counter temizleme | Aynı process'te restart sonrası event_max sorununu çözer |

### ❌ YENİ BACKEND'DEN ALINMAYACAKLAR

| Özellik | Neden Alınmıyor |
|---------|-----------------|
| WS binary invariant (1-x) | Per-side bağımsız daha doğru |
| enable_trading() manuel kapı | Paper mode'da gereksiz |
| 3s HTTP polling (frontend) | WebSocket/SSE ile değiştirilecek |

---

## 5. MİMARİ KATMANLAR (BTC-ONLY)

```
┌─────────────────────────────────────────────┐
│                  Frontend                    │
│  React + Vite + TypeScript                   │
│  Tek coin dashboard (BTC)                    │
│  WebSocket ile backend'den realtime veri     │
└─────────────┬───────────────────────────────┘
              │ WS /ws/dashboard
┌─────────────┴───────────────────────────────┐
│               FastAPI Backend                │
│                                              │
│  ┌─────────┐  ┌──────────┐  ┌────────────┐ │
│  │Discovery│→ │Evaluation│→ │ Execution  │ │
│  │  Loop   │  │   Loop   │  │(Paper/Live)│ │
│  └────┬────┘  └────┬─────┘  └─────┬──────┘ │
│       │            │              │         │
│  ┌────┴────┐  ┌────┴─────┐  ┌────┴──────┐  │
│  │Registry │  │Pipeline  │  │ Position  │  │
│  │SafeSync │  │(bid/ask) │  │ Tracker   │  │
│  └─────────┘  └──────────┘  └───────────┘  │
│                                              │
│  ┌─────────┐  ┌──────────┐  ┌────────────┐ │
│  │  RTDS   │  │CoinPrice │  │   PTB      │ │
│  │  WS     │  │  Client  │  │ Fetcher    │ │
│  └─────────┘  └──────────┘  └────────────┘  │
│                                              │
│  ┌─────────┐  ┌──────────┐  ┌────────────┐ │
│  │  Exit   │  │Settlement│  │  Balance   │ │
│  │Orchestr.│  │+ Claim   │  │  Manager   │ │
│  └─────────┘  └──────────┘  └────────────┘  │
│                                              │
│  ┌──────────────────────────────────────┐   │
│  │ Supervisor (10s) + Periodic Flush    │   │
│  └──────────────────────────────────────┘   │
│                                              │
│  SQLite (aiosqlite)                          │
└──────────────────────────────────────────────┘
```

---

## 6. BTC-ONLY SADELEŞTİRME

Mevcut backend multi-coin. BTC-only için:

### Kaldırılabilecek karmaşıklıklar:
- CoinSettings per-coin loop → tek BTC config
- EligibilityGate multi-coin filter → BTC-only check
- SubscriptionManager multi-asset diff → tek asset track
- event_map dict → tek event reference
- Dashboard coins endpoint → gereksiz (tek coin)

### Korunacak yapılar:
- Rule engine (6 rule aynen)
- Position state machine (aynen)
- Exit evaluator (TP/SL/FS aynen)
- Pipeline (per-side bid/ask aynen)
- PTB fetcher + SSR adapter (aynen)
- RTDS WS client (aynen)
- Supervisor + periodic flush (aynen)

---

## 7. FRONTEND BTC-ONLY

### Mevcut yapı:
- Sidebar + TopBar + 3 section (Open/Search/Idle rails)
- 7 endpoint polling (3s)
- Multi-coin tile'lar

### BTC-only değişiklikler:
- Sidebar → kaldır veya minimal (sadece bot kontrol)
- Tek büyük BTC dashboard panel
- Coin selector → kaldır (tek coin)
- WebSocket ile realtime veri (3s polling yerine)
- Gösterilecek:
  - BTC USD fiyat (live)
  - UP/DOWN outcome fiyat (live)
  - PTB (event başı sabit)
  - Delta (live hesaplama)
  - 6 rule durumu (pass/fail/waiting/disabled)
  - Açık pozisyon varsa: PnL, TP/SL durumu
  - Son trade geçmişi
  - Balance

### Backend → Frontend WS endpoint:
```
GET /ws/dashboard → WebSocket
Her 200ms evaluation sonrası:
{
  "type": "tick",
  "btc_usd": 73500.00,
  "up_bid": 0.52, "up_ask": 0.53,
  "down_bid": 0.47, "down_ask": 0.48,
  "ptb": 73400.00,
  "delta": 100.00,
  "spread_pct": 1.92,
  "seconds_remaining": 180,
  "rules": { "time": "pass", "price": "pass", ... },
  "signal_ready": true,
  "position": null | { "side": "UP", "pnl_pct": 2.3, "state": "open" },
  "balance": 7.73,
  "session_trades": 3,
  "event_url": "https://polymarket.com/event/btc-updown-5m-..."
}
```

---

## 8. ÇOKLU COİN'E GEÇİŞ (SONRASI)

BTC-only bot tamamlandıktan sonra multi-coin'e genişletmek:

1. `CoinSettings` per-coin config ekle (zaten var)
2. Evaluation loop'a multi-coin döngü ekle (zaten var)
3. Frontend'e coin selector + multi-tile ekle
4. WS endpoint'e coin filter ekle

**Backend yorulur mu?** HAYIR:
- 7 coin evaluation = 7 × microsaniye = ihmal edilebilir
- Tek WS bağlantısı, 14 token (7 coin × 2 side)
- Tek discovery call, tüm coinler aynı API'den
- 7 ayrı bot = 7× memory, 7× WS = israf

**Tavsiye:** 1 bot, 7 coin. Aynı mimari, sadece config genişletme.

---

## 9. UYGULAMA FAZLARI

### Faz 1: Temel Altyapı
- Config schema (Pydantic)
- SQLite persistence
- CredentialStore
- Logging config
- Health endpoint

### Faz 2: Veri Katmanı
- PublicMarketClient (Gamma API)
- DiscoveryEngine + DiscoveryLoop (pagination, slot-aware, retry)
- LivePricePipeline (per-side bid/ask)
- RTDSClient (WS, auto-reconnect, exponential backoff)
- WSPriceBridge (token routing)
- CoinPriceClient (WS polling)
- PTBFetcher + SSRPTBAdapter (retry, lock)

### Faz 3: Strateji + Evaluation
- EvaluationContext (24 field)
- RuleEngine (6 rule)
- EvaluationLoop (200ms, runtime state, current slot guard)
- Registry + SafeSync (7 state, 3-miss delist)

### Faz 4: Execution
- OrderExecutor (paper + live)
- PositionTracker (6 state machine)
- BalanceManager (stale guard, passive refresh)
- FeeCalculator (C × feeRate × p × (1-p))
- ExitEvaluator (TP reevaluate, SL latch + jump, FS checkbox)
- ExitExecutor (close retry, live sell)
- ExitOrchestrator (trigger → evaluate → execute)
- SettlementOrchestrator + ClaimManager

### Faz 5: Orchestrator + 7/24
- Orchestrator wiring (tüm component'ler)
- Startup sequence (restore → verify → loops)
- Supervisor loop (10s, 5 task, auto-restart)
- Periodic flush (~30s)
- PENDING_OPEN cleanup
- Graceful shutdown

### Faz 6: API + Frontend
- FastAPI endpoints (health, bot control, dashboard, settings, credentials)
- WebSocket /ws/dashboard endpoint
- React BTC-only dashboard
- Realtime veri akışı (WS)

### Faz 7: Paper Test
- Uçtan uca paper cycle: BUY → hold → TP/SL → close → settle → claim
- Discovery slot geçişi
- WS reconnect
- Supervisor restart
- 24h unattended test

### Faz 8: Live Test
- Credential yükleme
- Küçük bakiye ($5-10) ile live test
- BUY → fill → exit → settle
- Balance reconciliation

---

## 10. DAVRANIŞ MATRİSİ (REFERANS)

| Olay | Başarılı | Başarısız |
|------|----------|-----------|
| Discovery event bulursa | → registry + eligibility + subscribe + PTB fetch + slot sonuna bekle | - |
| Discovery event bulamazsa | - | → retry [2,4,8,16,10s] slot içinde. Slot bitince yeni slot. |
| PTB çekilirse | → lock + delta aktif | - |
| PTB çekilemezse | - | → retry event bitene kadar. Delta WAITING. |
| WS outcome price gelirse | → pipeline FRESH + price/spread aktif | - |
| WS outcome price gelmezse | - | → pipeline STALE → price, delta, spread WAITING |
| Tüm rule pass | → ENTRY sinyali → paper fill / live order | - |
| Herhangi rule FAIL | - | → NO_ENTRY. Sonraki cycle tekrar. |
| WAITING varsa | - | → sinyal üretilmez. Veri gelince tekrar. |
| Balance verify başarısız | - | → DEGRADED (yeni trade yok, exit devam) → 30s retry |
| TP tetiklenir | → CLOSING_REQUESTED → reevaluate → close | PnL düşerse → iptal → OPEN'a dön |
| SL tetiklenir | → CLOSING_REQUESTED → LATCH → close | jump > 15% → SL atla |
| FS tetiklenir | → CLOSING_REQUESTED → LATCH → close | - |
| Close başarısız | - | → CLOSE_FAILED → retry (max 10) |
| Settlement (resolved) | → claim → balance'a ekle (WON) / $0 (LOST) | - |
| Settlement (not resolved) | - | → retry [5,10,20s steady] max 20 |
| WS disconnect | - | → exponential backoff [2→30s] → auto-resubscribe |
| Crash/restart | → restore_state → balance verify → loop başlat | Periodic flush sayesinde son 30s kaybı max |
| Task ölürse | → supervisor 10s'de tespit → auto-restart | 3+ hızlı restart → health warning |

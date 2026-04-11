# POLYFAST BTC BOT — BİRLEŞİK REFERANS DOKÜMANI

Bu dosya 3 kaynak dokümanı tek referansta birleştirir:
1. Eski backend tam teknik işleyiş raporu
2. Eski vs yeni backend kıyaslama ve sapma raporu
3. BTC-only bot sıfırdan yazım planı

---
---

# BÖLÜM 1: ESKİ BACKEND TAM TEKNİK İŞLEYİŞ RAPORU

---

## 1) ESKİ BACKENDİN GENEL İŞLEYİŞ ÖZETİ

Eski backend Faz 7 sonunda çalışan, paper mode'da tam döngü tamamlayan bir sistemdir. Live order göndermez — LIVE_ORDER_ENABLED=False guard'ı vardır. ENTRY sinyali üretir, paper fill simüle eder, exit cycle ile TP/SL/FS takip eder, settlement ile claim oluşturur.

Ana döngüsü 5 dakikalık slot'lara bağlıdır. Her slot'ta:
- Discovery yeni event tarar
- Eligible event'ler subscribe edilir (WS + coin price + PTB)
- Evaluation loop 200ms'de bir rule engine çalıştırır
- Exit cycle ~100ms'de bir açık pozisyonları kontrol eder

Bot start → restore_state → balance verify → loop'lar başlat. Balance verify başarısızsa DEGRADED mode — yeni trade yok ama exit/claim devam eder.

---

## 2) BAŞTAN SONA MODÜL AKIŞI

### A) STARTUP

**Sıralama:**
1. `Orchestrator.__init__()` — 10 adımda tüm component'ler oluşturulur
2. `await orchestrator.start()` çağrılır
3. `await self.restore_state()` — SQLite'tan memory'ye yükle
4. Balance verify — `await self._verify_balance()`
5. Başarılıysa `trading_enabled=True` (NORMAL)
6. Başarısızsa `trading_enabled=False` (DEGRADED) + 30s retry loop başlar
7. `coin_client.start()` — coin USD polling başlar
8. `discovery_loop.start()` — event tarama başlar
9. `evaluation_loop.start()` — rule evaluation başlar
10. `_exit_cycle_task` oluşturulur — exit monitoring başlar

**Component oluşturma sırası (init):**
- Config + CredentialStore (boş başlar)
- LivePricePipeline (stale=30s)
- RTDSClient (WS URL, backoff=2-30s)
- WSPriceBridge (pipeline'a bağlı)
- CoinPriceClient (stale=15s, resub=150ms)
- SSRPTBAdapter + PTBFetcher (retry=[2,4,8,16], steady=10s)
- EventRegistry + SafeSync (delist_threshold=3)
- SettingsStore + RuleEngine
- PublicMarketClient (timeout=15s, retry=3)
- DiscoveryEngine
- Persistence stores (5 adet)
- `trading_enabled=True` (default)
- PositionTracker, BalanceManager (stale=90s, passive_refresh=20s)
- ClobClientWrapper, RelayerClientWrapper (credential_store'a bağlı)
- ClaimManager (retry=5/10/20s, max=20)
- ExitEvaluator (TP=5%, SL=3%, jump=15%, FS_time=30s)
- ExitExecutor (paper=True, retry: TP=400ms, SL=250ms, FS=200ms, max=10)
- OrderValidator (min=5 USD)
- SettlementOrchestrator, ExitOrchestrator
- EligibilityGate, SubscriptionManager, EventCleanup, HealthAggregator
- DiscoveryLoop (retry=[2,4,8,16], steady=10s)
- EvaluationLoop (interval=200ms)
- RTDS callback → bridge.on_ws_message
- Exit cycle interval (config'den, ~50-100ms)

**Credential kontrolü:** Init'te YOK. Credential boş başlar. İlk API call'da (balance verify) patlayınca DEGRADED mode'a girer. Credential'lar `/api/credential/update` endpoint'i ile sonradan yüklenir.

**Balance fetch zorunlu mu:** EVET, startup'ta zorunlu. Başarısızsa trading_enabled=False.

**restore_state:** 5 katmanlı restore:
1. Settings → settings_store
2. Registry (active events) → registry._records
3. PTB (locked) → ptb_fetcher._records
4. Positions → position_tracker (tüm state'ler korunur)
5. Claims → claim_manager (pending claim'ler resume)

**Bot "hazır" ne zaman:** Explicit "ready" state YOK. Tüm loop'lar başladığında implicit hazır. `trading_enabled` ayrı bir kontrol — False ise hazır ama yeni trade almaz.

---

### B) DISCOVERY

**Loop mantığı:**
- Her 5 dakikalık slot başında çalışır: `slot_start = (now // 300) * 300`
- Gamma API: `GET /events?tag_slug=5M&closed=false&limit=100`
- Pagination YOK — tek çağrı, 100 sonuç
- Filtreleme: category=crypto, duration=5m, title contains "up or down"
- `_is_current_or_upcoming`: slug timestamp ± 1800s lookahead
- Slug'taki timestamp = event END zamanı (eski backend'de böyle varsayılmış — YANLIŞ, doğrusu START)

**Event bulursa:**
1. `retry_count = 0` sıfırla
2. `safe_sync.sync(events)` → registry'ye kaydet/güncelle
3. `on_events_found(events)` callback → eligibility → subscription zinciri
4. Slot sonuna kadar bekle, yeni scan yapma

**Event bulamazsa:**
- Retry schedule: 2s → 4s → 8s → 16s → 10s(steady)
- Her bekleme 1s chunk'lara bölünür — slot sınırı geçilirse retry durur
- Slot içinde sınırsız deneme (event bulana veya slot bitene kadar)
- Slot sınırı geçilince yeni slot'a atlar

**Slot-aware davranış:**
- Discovery slot'a kilitli: aynı slot'ta 1 başarılı tarama yeterli
- Slot bitmeden retry devam eder
- Slot değiştiğinde (5dk dolunca) yeni cycle otomatik başlar

---

### C) REGISTRY / ELIGIBILITY

**Registry:**
- In-memory dict: `_records[condition_id] → RegistryRecord`
- 7 state: DISCOVERED → VALIDATING → ACTIVE → INACTIVE → EXPIRED → SUSPENDED → CLOSED
- register_candidate: yeni event → DISCOVERED state
- Mevcut event → `update_last_seen()` timestamp güncelle

**SafeSync:**
- Phase 1: Gelen event'leri registry'ye yaz/güncelle
- Phase 2: Gelmeyenleri say — 3 ardışık miss → INACTIVE (soft-remove)
- Koruma: open position olan event asla INACTIVE yapılmaz
- Restorasyon: INACTIVE event tekrar görülürse → ACTIVE

**EligibilityGate filtreleme zinciri:**
1. Asset parse edilebiliyor mu
2. CoinSettings var mı (settings_store'da tanımlı mı)
3. `coin_enabled = True` mi
4. `is_configured = True` mi (tüm zorunlu alanlar dolu mu)
5. `is_trade_eligible = True` mi
- Herhangi biri FAIL → ineligible + reason kodu

---

### D) SUBSCRIPTION / CANLI VERİ

**Veri kaynakları:**

| Veri | Kaynak | Yöntem |
|------|--------|--------|
| Outcome fiyat (UP/DOWN) | CLOB WS | RTDSClient → WSPriceBridge → LivePricePipeline |
| Coin USD fiyat | Live Data WS | CoinPriceClient → polling/streaming |
| PTB (open price) | Polymarket SSR | SSRPTBAdapter → HTTP scrape |

**Subscribe akışı:**
1. EligibilityGate eligible event listesi verir
2. SubscriptionManager.compute_diff() — yeni/eski/unchanged ayırır
3. apply_diff():
   - Yeni asset → `_subscribe_asset()`: bridge'e token register + coin client'a coin ekle
   - Eski asset → `_unsubscribe_asset()`: bridge'den token kaldır
4. PTB fetch: `ptb_fetcher.fetch_ptb_with_retry()` async task başlatılır

**Bridge token routing:**
- `_token_routes[token_id] → TokenRoute(condition_id, asset, side)`
- WS mesajı gelince: token_id → route bul → pipeline.update_from_ws() çağır

**Pipeline storage:**
- `_records[condition_id] → LivePriceRecord`
- Alanlar: up_price, down_price, best_bid, best_ask, spread, status, source
- Binary invariant: UP güncellenince `down_price = 1.0 - up_bid`
- Source: `rtds_ws` (WS'ten) veya `gamma_outcome_prices` (Gamma fallback)

**Pipeline Gamma seed:**
- `update_from_gamma()` methodu VAR ama çağrılma yeri belirsiz
- WS birincil kaynak — WS bağlanana kadar pipeline boş kalır

**Stale threshold'lar:**
- Outcome price: 30 saniye
- Coin USD: 15 saniye
- Balance: 90 saniye

**Birden fazla aynı asset event:** SubscriptionManager asset bazlı diff yapar. Aynı asset'in iki event'i gelirse, event_map'te son yazan kazanır. Rotation mantığı: condition_id değişirse eski token unregister, yeni register.

**WS disconnect:** RTDSClient exponential backoff ile reconnect (2→4→8→16→30→30s). Reconnect sonrası auto-resubscribe.

---

### E) EVALUATION LOOP

**Çalışma şekli:**
- 200ms interval ile tüm eligible coin'leri değerlendirir
- Her coin için runtime state'ten EvaluationContext oluşturur (snapshot DEĞİL)

**Context kaynakları:**
- `pipeline.get_record_by_asset(asset)` → up_price, down_price, best_bid, best_ask, outcome_fresh
- `coin_client.get_price(asset)` → coin_usd_price, coin_usd_fresh
- `ptb_fetcher.get_record(condition_id)` → ptb_value, ptb_acquired (locked ise)
- Slot hesabı → seconds_remaining
- CoinSettings → tüm threshold'lar ve side_mode

**6 Rule ve davranışları:**

| Rule | Pass | Fail | Waiting | Disabled |
|------|------|------|---------|----------|
| **Time** | time_min ≤ remaining ≤ time_max | remaining dışında | - | time_min=0 |
| **Price** | price_min ≤ dominant_price ≤ price_max (0-100 ölçeği) | dominant_price aralık dışı | outcome_fresh=False | price_min=0 |
| **Delta** | abs(coin_usd - ptb) ≥ delta_threshold | fark < threshold | ptb_acquired=False VEYA coin_fresh=False | delta_threshold=0 |
| **Spread** | spread ≤ spread_max | spread > spread_max | outcome_fresh=False | spread_max=0 |
| **EventMax** | event_fill_count < event_max | event_fill_count ≥ event_max | - | - |
| **BotMax** | open_position_count < bot_max | open_count ≥ bot_max | - | - |

**Karar birleştirme:** FAIL > WAITING > PASS > NO_RULES
- Herhangi bir rule FAIL → NO_ENTRY
- Hiç FAIL yok, en az bir WAITING → WAITING (daha fazla veri bekle)
- Tüm active rule'lar PASS → ENTRY sinyali

**Outcome price yoksa:** Price, Delta, Spread rule'ları WAITING döner. ENTRY sinyali üretilmez.
**PTB yoksa:** Delta rule WAITING döner. ENTRY sinyali üretilmez.
**Stale veri:** outcome_fresh/coin_fresh = False → ilgili rule WAITING.

---

### F) ENTRY İŞLEYİŞİ

**ENTRY sinyali çıkınca eski backendde ne oluyordu:**
- EvaluationLoop ENTRY loglar: `"ENTRY signal: BTC UP"`
- **Faz 7'de OrderExecutor'a dispatch YOKTU** — sadece log üretiliyordu
- Kodda açık yorum: `"ORDER GÖNDERİLMEZ — sadece log (Faz 5)"`

**OrderExecutor bağlı mıydı:** EVET, component olarak oluşturulmuş ama evaluation loop'tan çağrılmıyordu. Execute methodu hazır — paper ve live path mevcut.

**Paper mode:** EVET. `_execute_paper()`: dominant_price ile fill simüle, fee hesapla, balance deduct.

**Dominant price:** Evaluation context'teki up_price/down_price'tan side_mode'a göre seçilen tarafın fiyatı.

**Order göndermiyordu çünkü:** Bilinçli karar. Faz 7 = backend tamamlanma fazı. Order dispatch mantığı Faz 8/9'da eklenecekti. Evaluation + rule engine + position lifecycle hazır, ama tetikleme zinciri bağlanmamıştı.

---

### G) POSITION / EXIT

**Position state machine:**
```
PENDING_OPEN → OPEN_CONFIRMED → CLOSING_REQUESTED → CLOSE_PENDING → CLOSED
                                                                   ↗
                                      CLOSE_FAILED → CLOSING_REQUESTED (retry)
```

**TP (Take Profit):**
- PnL-based: `pnl_pct ≥ tp_pct` (default 5%)
- **Reevaluate:** Close öncesi tekrar kontrol. PnL düştüyse → iptal → OPEN_CONFIRMED'a dön
- Retry: 400ms interval

**SL (Stop Loss):**
- PnL-based: `pnl_pct ≤ -sl_pct` (default -3%)
- **Jump threshold:** Ani %15'ten fazla düşüş → SL atlanır (manipülasyon koruması)
- **LATCH:** Tetiklenince geri alınamaz, reevaluate yok
- Retry: 250ms interval

**FS (Force Sell):**
- Checkbox bazlı: Time + PnL (aktif olan HEPSI tetiklenmeli)
- Time: remaining ≤ 30s
- PnL: pnl_pct ≤ -fs_pnl_pct (disabled by default)
- **Time safety override:** PnL stale ama time koşulu sağlanmışsa → yine tetikle
- **LATCH:** Geri alınamaz
- Retry: 200ms interval

**Close başarısız olursa:**
- State → CLOSE_FAILED
- Exit cycle sonraki turda tekrar CLOSING_REQUESTED'a alır
- Max 10 retry (configurable)
- Retry sonrası hala başarısızsa → CLOSE_FAILED'da kalır, log üretilir

**PnL hesaplama:**
```
gross_value = shares x current_price
est_fee = shares x fee_rate x current_price x (1 - current_price)
net_value = gross_value - est_fee
net_pnl = net_value - requested_amount_usd
pnl_pct = (net_pnl / requested_amount_usd) x 100
```

**Claim/Settlement:**
- Position CLOSED olduktan sonra → Settlement kontrol eder
- CLOB API'den market resolution sorgusu (resolved mi?)
- Paper mode'da her zaman resolved=True
- Resolved → ClaimManager.create_claim() → execute_redeem()
- WON → balance'a payout ekle / LOST → $0
- Claim retry: 5s → 10s → 20s(steady), max 20 deneme

---

### H) BALANCE / ACCOUNTING

**Balance kaynakları:**
- Startup: CLOB API'den fetch (zorunlu)
- Post-fill: paper=deduct, live=re-fetch
- Post-close: paper=add(net_exit_usdc), live=re-fetch
- Post-claim: paper=add(payout), live=re-fetch
- Passive refresh: 20s interval

**Stale balance:** 90s threshold. Stale ise order rejected.
**Fee hesaplama:** `fee = shares x fee_rate x p x (1-p)` — fee_rate = 0.072 (eski default — YANLIŞ, doğrusu 0.10)
**Autoritatif:** CLOB API balance, paper mode'da in-memory deduct/add.

---

### I) RESTART / 7/24

**Crash durumu:**
- State sadece shutdown'da SQLite'a yazılıyor (periodic flush YOK)
- Crash = state kaybı riski (shutdown flush çalışmaz)
- Restart → restore_state: SQLite'taki son flush'tan okur
- Son flush'tan sonraki trade'ler kaybolur

**Supervisor:** YOK. Task ölürse respawn mekanizması yok. Sadece graceful stop'ta task cancel.

**Periodic flush:** YOK. Bu eski backend'in bilinen zayıflığı.

**Recovery:** restore_state ile:
- Pozisyonlar resume (açık pozisyon varsa exit cycle devam eder)
- Pending claim'ler retry'a devam
- Balance re-verify (fail = DEGRADED)
- Discovery yeniden tarar (clean start)

**Event bulamazsa:** Slot içinde retry, slot bitince yeni slot. Sonsuz döngü — hiç durmaz.
**Stale veriyle karar:** HAYIR. outcome_fresh/coin_fresh kontrolleri var. Stale → WAITING → ENTRY üretilmez.
**Silent bypass:** YOK. Her failure loglanır, health incident oluşturulur.

---

### J) CONFIG / RETRY / INTERVAL / TIMEOUT

| Alan | Değer | Kaynak |
|------|-------|--------|
| Evaluation interval | 200ms | config |
| Exit cycle interval | ~50-100ms | config |
| Discovery retry | [2, 4, 8, 16]s + 10s steady | config |
| PTB retry | [2, 4, 8, 16]s + 10s steady | config |
| Balance verify retry | 30s | hardcoded |
| Balance passive refresh | 20s | config |
| TP close retry | 400ms | config |
| SL close retry | 250ms | config |
| FS close retry | 200ms | config |
| Manual close retry | 400ms | config |
| Max close retries | 10 | config |
| Claim retry | 5/10/20s steady, max 20 | config |
| Settlement retry | 5/10/20s steady, max 20 | config |
| WS reconnect backoff | 2→4→8→16→30s max | config |
| Outcome stale | 30s | config |
| Coin price stale | 15s | config |
| Balance stale | 90s | config |
| Bridge stale | 60s | hardcoded |
| Coin resub interval | 150ms | config |
| Network timeout | 15s | config |
| CLOB API timeout | 5s | config |
| Relayer timeout | 30s | config |
| SafeSync delist | 3 miss | config |
| Lookahead | 1800s (30dk) | hardcoded |
| Min order USD | 5.0 | config |

---

## 3) VERİ KAYNAKLARI VE VERİ AKIŞI

```
Gamma API --> DiscoveryEngine --> Registry --> EligibilityGate --> SubscriptionManager
                                                                         |
                              +------------------------------------------+
                              |
                    +---------+----------+
                    |                    |
              WSPriceBridge         CoinPriceClient        PTBFetcher
              (CLOB WS)            (Live Data WS)         (SSR HTTP)
                    |                    |                    |
              LivePricePipeline    CoinPriceRecord       PTBRecord
              (up/down/spread)     (USD fiyat)           (open price)
                    |                    |                    |
                    +------------+-------+--------------------+
                                 |
                         EvaluationContext
                                 |
                           RuleEngine (6 rule)
                                 |
                    +------------+------------+
                    |                         |
               ENTRY sinyal              NO_ENTRY / WAITING
                    |
              OrderExecutor (paper)
                    |
              PositionTracker
                    |
              ExitOrchestrator <-- Exit Cycle Loop (100ms)
                    |
              +-----+------+
              |             |
         ExitEvaluator  ExitExecutor
         (TP/SL/FS)    (close order)
                            |
                     SettlementOrchestrator
                            |
                       ClaimManager
```

---

## 4) ESKİ BACKENDİN GÜÇLÜ YANLARI

1. Rule engine temiz ayrılmış — 6 bağımsız rule, DISABLED/PASS/FAIL/WAITING state machine
2. Stale koruma katmanlı — outcome, coin, balance ayrı threshold'lar, stale = WAITING = sinyal yok
3. Exit evaluator zengin — TP reevaluate, SL latch + jump threshold, FS checkbox bazlı + time safety override
4. Position state machine net — 6 state, izinli geçişler tanımlı
5. Discovery slot-aware — 5dk sınırlarına kilitli, slot içi retry, slot arası temiz geçiş
6. Retry schedule'lar config-driven — hardcoded minimum
7. DEGRADED mode — balance yoksa durdurma ama yeni trade engelle, exit devam

---

## 5) ESKİ BACKENDİN BİLİNÇLİ SINIRLARI / EKSİKLERİ

1. Order dispatch bağlantısı YOK — ENTRY sadece log (bilinçli — Faz 8/9 işi)
2. Periodic flush YOK — crash = state kaybı (tek flush shutdown'da)
3. Supervisor YOK — task ölürse respawn yok
4. PENDING_OPEN cleanup YOK — crash sırasında phantom pozisyon kalır
5. Pagination YOK — discovery tek sayfa (limit=100)
6. Pipeline Gamma seed belirsiz — update_from_gamma() var ama çağrılma akışı net değil
7. Live order/settlement implement edilmemiş
8. Credential reload/rebind YOK
9. Slug timestamp = END varsayımı (YANLIŞ — doğrusu START)
10. Fee rate = 0.072 (YANLIŞ — doğrusu 0.10 / 1000 bps)

---

## 6) DAVRANIŞ MATRİSİ

| Olay | Başarılı Senaryo | Başarısız Senaryo |
|------|-----------------|-------------------|
| **Discovery event bulursa** | registry kaydet → eligibility → subscribe → PTB fetch → slot sonuna bekle | - |
| **Discovery event bulamazsa** | - | retry [2,4,8,16,10s] slot icinde. Slot bitince yeni slot. Sonsuz dongu. |
| **PTB cekilirse** | PTBRecord.lock() → retry durur → delta rule aktif | - |
| **PTB cekilemezse** | - | retry event bitene kadar. Delta WAITING. ENTRY yok |
| **Outcome price gelirse (WS)** | pipeline FRESH → price/spread rule aktif | - |
| **Outcome price gelmezse** | - | pipeline bos/STALE → price, delta, spread WAITING → ENTRY yok |
| **Coin USD gelirse** | CoinPriceRecord FRESH → delta hesaplanabilir | - |
| **Coin USD gelmezse** | - | STALE → delta rule WAITING → ENTRY yok |
| **Tum rule pass olursa** | ENTRY sinyali (Faz 7: sadece log, order yok) | - |
| **En az bir rule FAIL** | - | NO_ENTRY. Sonraki cycle tekrar. |
| **WAITING varsa** | - | Sinyal uretilmez. Eksik veri gelince tekrar. |
| **Balance verify basarili** | trading_enabled=True → NORMAL mode | - |
| **Balance verify basarisiz** | - | trading_enabled=False → DEGRADED → 30s retry loop |
| **Paper fill** | position OPEN_CONFIRMED → balance deduct → exit monitoring baslar | - |
| **TP tetiklenirse** | CLOSING_REQUESTED → reevaluate → close → CLOSED → settlement | reevaluate: PnL dustuyse → iptal → OPEN'a don |
| **SL tetiklenirse** | CLOSING_REQUESTED → LATCH → close → CLOSED → settlement | jump_threshold asilirsa → SL atlanir |
| **FS tetiklenirse** | CLOSING_REQUESTED → LATCH → close → CLOSED → settlement | - |
| **Close basarisiz** | - | CLOSE_FAILED → sonraki cycle retry → max 10 deneme |
| **Settlement (resolved)** | claim olustur → redeem → balance'a ekle (WON) / $0 (LOST) | - |
| **Settlement (not resolved)** | - | retry [5,10,20s steady], max 20 deneme |
| **Restart olursa** | restore_state → balance verify → loop baslat | crash: son flush'tan bu yana state kaybi |
| **WS disconnect** | - | exponential backoff [2→30s]. Reconnect sonrasi auto-resubscribe. |
| **Stale veri** | - | ilgili rule WAITING. ENTRY uretilmez. Stale kalkinca normal devam. |
| **Credential yok** | - | balance verify fail → DEGRADED. Discovery/evaluation devam ama order yok. |

---
---

# BÖLÜM 2: ESKİ vs YENİ BACKEND — KIYASLAMA VE SAPMA RAPORU

---

## 1) ESKİYE GÖRE KESİN DAHA İYİ OLANLAR

| Yeni Ozellik | Eski Durum | Karar |
|---|---|---|
| **Supervisor loop (10s)** — 5 task monitor, olurse restart | YOK — task olurse respawn yok | **KORU** |
| **Periodic flush (~30s)** — crash'te state kaybi azaltilmis | YOK — sadece shutdown'da flush | **KORU** |
| **PENDING_OPEN cleanup** — restart'ta phantom pozisyon temizleme | YOK — phantom kaliyor | **KORU** |
| **Per-side bid/ask** — up_bid, up_ask, down_bid, down_ask bagimsiz | up_price, down_price + binary invariant (1-x) | **KORU** |
| **Current slot ownership** — asset basina tek aktif event | event_map'te son yazan kazanir | **KORU** |
| **Condition_id rotation** — slot degisince eski unsub, yeni sub + RTDS resub | Rotation mantigi belirsiz | **KORU** |
| **Discovery pagination (5 sayfa)** — 500 event'e kadar tarama | Tek sayfa limit=100 | **KORU** |
| **Slug timestamp = START** (dogru) | Slug timestamp = END (yanlis varsayim) | **KORU** |
| **Live order + live sell** — FOK SDK implementasyonu | LIVE_ORDER_ENABLED=False, relayer not implemented | **KORU** |
| **Config-driven retry/interval/timeout** — schema.py'de tum operasyonel degerler | Bazilari hardcoded | **KORU** |
| **Exit cycle proper pipeline lookup** — get_record(current_cid) + fallback | get_price(asset) — method yok, silent fail | **KORU** |
| **Fee rate = 0.10 (1000 bps)** — dogru crypto rate | 0.072 — eski/yanlis | **KORU** |
| **Pipeline Gamma seed** — discovery sirasinda outcomePrices → pipeline | WS baglanmadan once dashboard'da fiyat gorunur | **KORU** |
| **Paper mode credential bypass** — EligibilityGate paper'da credential aramaz | Credential olmadan paper test yapilamaz | **KORU** |
| **Paper mode auto-dispatch** — Paper'da ENTRY → otomatik order | Manuel enable_trading gereksiz | **KORU** |
| **Position tracker reset** — Bot stop/start'ta stale counter temizleme | Ayni process'te restart sonrasi event_max sorunu | **KORU** |

---

## 2) ESKİ İŞLEYİŞTEN SAPAN AMA DOĞRU OLANLAR

| Sapma | Eski Davranis | Yeni Davranis | Karar |
|---|---|---|---|
| WS per-side bagimsiz guncelleme | UP gelince DOWN = 1-UP (sentetik) | Her side kendi WS mesajindan bagimsiz guncellenir | **YENİ DAHA DOĞRU** |
| Evaluation context genislesmis | up_price, down_price, best_bid, best_ask | up_bid, up_ask, down_bid, down_ask + backward compat | **YENİ DAHA DOĞRU** |
| EvaluationLoop'ta _dispatch_entry | ENTRY sadece log | ENTRY → _dispatch_entry → OrderExecutor.execute() | **YENİ DAHA DOĞRU** |

---

## 3) FIX EDİLMİŞ SORUNLAR (BU SOHBETTE)

Bu sohbet boyunca tespit edilip fix edilen sorunlar:

| Fix | Sorun | Commit |
|-----|-------|--------|
| Discovery pagination | Tek sayfa → current event'ler bulunamiyordu | 25cc002 |
| Exit cycle pipeline lookup | pipeline.get_price() yok → silent AttributeError → TP/SL/FS hic calismiyordu | f1adb93 |
| Pipeline Gamma seed | update_from_gamma() hic cagrilmiyordu → pipeline bos | 562134a |
| Gamma seed ask=bid | ask=0 yaziliyordu → price rule her zaman FAIL | f43eef8 |
| EligibilityGate paper bypass | Paper mode'da credential gate → tum coinler ineligible | 562134a |
| Order dispatch auto-enable | _order_dispatch_enabled=False, hic enable edilmiyordu | 562134a |
| Paper mode default | False (live) → True (paper test asamasi) | 562134a |
| PositionTracker.reset() | Stop/start'ta stale counter temizlenmiyordu | 9026253 |
| ZeroDivisionError dispatch | entry_ref_price=0 → fee_calculator crash | 81f8571 |
| Paper mode auto-dispatch | Manuel enable_trading kaldirildi, paper'da otomatik | 81f8571 |
| DiscoveredEvent.outcome_prices | outcomePrices alani model'de yoktu → Gamma seed calismiyor | 562134a |

---

## 4) KALAN BİLİNEN SORUNLAR

| Sorun | Detay | Oncelik |
|-------|-------|---------|
| Discovery slot gecisi gecikmesi | Yeni slot basladiginda event_url eski slot'ta kalabiliyor. Discovery loop slot sonuna kadar bekliyor, yeni slot basinda yeni scan yapiyor ama pipeline'a yazilmasi 10-30s surebiliyor. | P1 |
| WS DOWN bid=0 rejection | DOWN tarafi bid=0 olarak WS'ten geliyor, _is_valid_ws_price() reddediyor. Eski backend 1-x kullaniyordu o yuzden sorun yoktu, yeni backend per-side bagimsiz. | P2 |
| Frontend 3s polling | WebSocket/SSE ile degistirilmeli | P1 |
| Credential reload/rebind | Credential degisirse component'ler eski credential ile kalir | P3 |

---

## 5) HER KATMAN KIYASI

### A) STARTUP / RESTORE / READINESS

| Konu | Eski | Yeni | Karar |
|---|---|---|---|
| Component olusturma | 10 adim | Ayni + daha fazla component | KORU |
| restore_state | 5 katman | Ayni + PENDING_OPEN cleanup | YENİ DAHA İYİ |
| Balance verify | Zorunlu, fail → DEGRADED | Ayni + 30s retry | AYNI |
| Supervisor | YOK | 10s, 5 task, restart on death | YENİ DAHA İYİ |
| Periodic flush | YOK | ~30s, positions+claims | YENİ DAHA İYİ |

### B) DISCOVERY

| Konu | Eski | Yeni | Karar |
|---|---|---|---|
| API cagrisi | limit=100, tek sayfa | + pagination (5 sayfa, 500 cap) | YENİ DAHA İYİ |
| Slug timestamp | END (yanlis) | START (dogru) | YENİ DAHA İYİ |
| Slot-aware retry | [2,4,8,16,10s], slot siniri kontrol | Ayni mantik | AYNI |

### C) REGISTRY / ELIGIBILITY / SUBSCRIPTION

| Konu | Eski | Yeni | Karar |
|---|---|---|---|
| Registry | _records[condition_id], 7 state | Ayni | AYNI |
| SafeSync | 3-miss soft-remove | Ayni | AYNI |
| Subscription model | Son yazan kazanir | Current slot ownership + rotation | YENİ DAHA İYİ |

### D) OUTCOME PRICE / PTB

| Konu | Eski | Yeni | Karar |
|---|---|---|---|
| Pipeline model | up_price, down_price + 1-x | up_bid, up_ask, down_bid, down_ask per-side | YENİ DAHA DOĞRU |
| Gamma seed | Belirsiz | Subscribe sirasinda seed | YENİ DAHA İYİ |
| PTB | SSR adapter, retry, lock | Ayni mantik | AYNI |

### E) EVALUATION

| Konu | Eski | Yeni | Karar |
|---|---|---|---|
| 6 Rule | Ayni | Ayni | AYNI |
| Karar birlestirme | FAIL>WAITING>PASS | Ayni | AYNI |
| ENTRY sonrasi | Sadece log | _dispatch_entry → OrderExecutor | YENİ DAHA İYİ |
| Current slot guard | Yok | _dispatch_entry'de validate | YENİ DAHA İYİ |

### F) ENTRY / EXIT

| Konu | Eski | Yeni | Karar |
|---|---|---|---|
| Order gonderme | YOK (Faz 7) | Paper + Live | YENİ DAHA İYİ |
| Position state machine | 6 state | 6 state (ayni) | AYNI |
| TP/SL/FS | Ayni mantik | Ayni + config-driven | AYNI |
| Live sell | YOK | FOK SDK implementasyonu | YENİ DAHA İYİ |
| Fee rate | 0.072 (yanlis) | 0.10 (dogru) | YENİ DAHA İYİ |

### G) 7/24

| Konu | Eski | Yeni | Karar |
|---|---|---|---|
| Supervisor | YOK | 10s, auto-restart | YENİ DAHA İYİ |
| Periodic flush | YOK | ~30s | YENİ DAHA İYİ |
| PENDING_OPEN cleanup | YOK | Restart'ta reject_fill | YENİ DAHA İYİ |
| WS auto-reconnect | Var | Var + supervisor restart | YENİ DAHA İYİ |

---
---

# BÖLÜM 3: VERİ KAYNAKLARI

Tum veri kaynaklari eski ve yeni backend'de AYNI. Credential gerektirmeyen kaynaklar:

## Credential GEREKTIRMEYEN (public)

| Veri | Endpoint | Yontem |
|------|----------|--------|
| Event kesfi | `https://gamma-api.polymarket.com/events?tag_slug=5M&closed=false` | HTTP GET |
| Outcome fiyat | `wss://ws-subscriptions-clob.polymarket.com/ws/market` | WebSocket push |
| Coin USD fiyat | `wss://ws-live-data.polymarket.com` | WebSocket polling |
| PTB (open price) | `https://polymarket.com/event/{slug}?__nextDataReq=1` | HTTP GET + regex `"openPrice":([0-9.]+),"closePrice":null` |

## Credential GEREKTIREN

| Veri | Endpoint | Yontem | Gerekli |
|------|----------|--------|---------|
| Balance | CLOB API `get_balance_allowance` | py_clob_client SDK | API key + secret + passphrase + private_key |
| Order gonderme | CLOB API `create_market_order` | py_clob_client SDK (FOK) | Ayni |
| Market resolution | CLOB API `get_market` | py_clob_client SDK | Ayni |

## SDK Parametreleri

- `chain_id = 137` (Polygon)
- `signature_type = 2` (Gnosis Safe proxy wallet)
- `funder_address` = Polymarket wallet address (0xd019B11c6572eCDb8F0036787f853Ef1A7EC2535)
- Fee formula: `fee = C x feeRate x p x (1-p)`, feeRate = 0.10 (1000 bps)
- BUY fill_price = makingAmount / takingAmount (outcome price 0-1)
- SELL fill_price = takingAmount / makingAmount (outcome price 0-1)

## Gamma API Event Yapisi

Slug format: `{asset}-updown-5m-{START_TIMESTAMP}`
- START_TIMESTAMP = event baslangic zamani (unix epoch)
- end_date = START_TIMESTAMP + 300

Market icindeki alanlar:
- `conditionId` — market benzersiz ID
- `clobTokenIds` — UP ve DOWN token ID'leri (JSON string veya list)
- `outcomes` — ["Up", "Down"]
- `outcomePrices` — ["0.505", "0.495"] (UP fiyat, DOWN fiyat)
- `bestBid`, `bestAsk` — mevcut bid/ask (Gamma'da tek fiyat, WS'te per-side)

## PTB (Price at Time of Bet) Detaylari

- URL: `https://polymarket.com/event/{slug}?__nextDataReq=1`
- Regex: `"openPrice":([0-9.]+),"closePrice":null`
- `closePrice:null` = LIVE event (kapanmamis)
- PTB = coin USD fiyati event acilisinda (Chainlink oracle)
- Ornek: BTC=$73,222.37, ETH=$2,062.70
- Set edilmesi 1-2 dakika surebilir (Chainlink gecikmesi)
- Retry: [2, 4, 8, 16, 10s steady] event bitene kadar
- Lock: bir kez alindiginda asla uzerine yazilmaz

---
---

# BÖLÜM 4: CONFIG DEFAULTS (NİHAİ REFERANS)

Eski backend disiplini + yeni backend duzeltmeleri birlestirilmis nihai degerler:

| Alan | Deger | Not |
|------|-------|-----|
| Evaluation interval | 200ms | |
| Exit cycle interval | 50ms | |
| Discovery retry | [2, 4, 8, 16]s + 10s steady | |
| PTB retry | [2, 4, 8, 16]s + 10s steady | |
| Balance verify retry | 30s | config-driven (yeni) |
| Balance passive refresh | 20s | |
| Supervisor interval | 10s | yeni eklenti |
| Periodic flush | ~30s | yeni eklenti |
| TP close retry | 400ms | |
| SL close retry | 250ms | |
| FS close retry | 200ms | |
| Manual close retry | 400ms | |
| Max close retries | 10 | |
| Claim retry | 5/10/20s steady, max 20 | |
| Settlement retry | 5/10/20s steady, max 20 | |
| WS reconnect backoff | 2→4→8→16→30s max | |
| Outcome stale | 30s | |
| Coin price stale | 15s | |
| Balance stale | 90s | |
| Lookahead | 1800s (30dk) | |
| Min order USD | 5.0 | |
| SafeSync delist | 3 miss | |
| Time rule | 30-270s remaining | |
| Price rule | 20-80 (0-100 olcegi) | |
| Delta threshold | 0.03 USD (BTC icin) | |
| Spread max | 0 (disabled) | |
| Event max | 1 position per event | |
| Bot max | 1 (BTC-only) | |
| TP | 5% | PnL-based |
| SL | 3% | PnL-based + jump threshold 15% |
| FS time | 30s remaining | |
| FS PnL | disabled | |
| Fee rate | 0.10 (1000 bps) | duzeltilmis |
| Signature type | 2 (proxy wallet) | |
| SDK transient retry sleep | 3s | yeni eklenti |
| Entry order timeout | 5s | yeni eklenti |
| Exit order timeout | 5s | yeni eklenti |
| Paper mode | True (default, test asamasi) | |

---
---

# BÖLÜM 5: ESKİ BACKEND REFERANS DOSYA KONUMU

Eski backend kodu: `C:\polyfast yedek\faz7-extract\polyfast\backend\`

Yeni backend kodu: `C:\polyfast\backend\`

Eski backend'in kodunu herhangi bir noktada referans olarak okuyabilirsin.
Yeni backend'deki fix'leri ve iyilestirmeleri gormek icin `C:\polyfast\backend\` kullan.

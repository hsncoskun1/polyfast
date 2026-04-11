# POLYFAST — ESKİ vs YENİ BACKEND İŞLEYİŞ ANALİZİ

Bu rapor, frontend çalışmasına başlamadan önceki backend (Faz 7 tamamlanmış) ile mevcut backend (v0.9.2) arasındaki tüm farkları kapsar. GPT product review için hazırlanmıştır.

## KARŞILAŞTIRMA TABANI

- **ESKİ:** "polyfast faz 7 bitti backend tamam oto yok.rar" — frontend öncesi son stabil backend
- **YENİ:** Mevcut kod (v0.9.2) — live trade denemelerinden sonraki durum

---

## 1. GENEL MİMARİ DEĞİŞİKLİKLER

### ESKİ İŞLEYİŞ (Faz 7)
```
Discovery → Registry → Eligibility → Subscribe → Evaluate → LOG ONLY
                                                              ↓
                                                    "ORDER GÖNDERİLMEZ — Faz 5"
```
- Evaluation loop SADECE sinyal üretiyordu, order göndermiyordu
- Paper mode her yerde hardcoded True
- LIVE_ORDER_ENABLED = False
- RTDS WS bağlantısı başlatılmıyordu (run_forever çağrılmıyordu)
- Outcome price pipeline'a düşmüyordu
- OrderExecutor vardı ama wiring'e bağlı değildi

### YENİ İŞLEYİŞ (v0.9.2)
```
Discovery → Registry → Eligibility → Subscribe → Evaluate → ORDER GÖNDER (eğer dispatch enabled)
                                                              ↓
                                                    enable_trading() ile açılır
                                                    default: KAPALI
```
- Evaluation loop order dispatch yapabiliyor (ama default kapalı)
- LIVE_ORDER_ENABLED = True (güvenlik guard'ı açıldı!)
- Schema paper_mode default = False (live mode)
- AMA wiring.py hâlâ paper_mode=True hardcoded
- RTDS WS run_forever task oluşturuluyor
- Outcome price per-side bid/ask modeline geçti
- OrderExecutor live execution implemented

---

## 2. DOSYA DOSYA KARŞILAŞTIRMA

### 2.1 evaluation_loop.py

| Özellik | ESKİ | YENİ |
|---------|------|------|
| Constructor parametreleri | 6 param | 11 param (+order_executor, position_tracker, bridge, registry, bot_max) |
| ENTRY davranışı | Sadece log ("ORDER GÖNDERİLMEZ") | dispatch gate ile order gönderebilir |
| _dispatch_entry metodu | YOK | 77 satır — OrderIntent oluşturma + execute |
| Position counter | event_fill_count=0, open_position_count=0 (hardcoded) | PositionTracker'dan gerçek değer (varsa) |
| PTB lookup | Sadece condition_id ile | condition_id + asset fallback |
| Fiyat modeli | up_price, down_price, best_bid, best_ask | up_bid, up_ask, down_bid, down_ask (per-side) |
| Result cache | YOK | _last_results dict (snapshot provider için) |
| Dispatch kontrolü | YOK (zaten order yoktu) | _order_dispatch_enabled = False default |
| bot_max_positions | Evaluation context'e GEÇMİYORDU | Geçiyor |
| Crashed task recovery | YOK | _task.done() kontrolü |

### 2.2 wiring.py

| Özellik | ESKİ | YENİ |
|---------|------|------|
| EvaluationLoop wiring | 6 arg | 6 arg (order_executor/tracker/bridge/registry GEÇİRİLMİYOR!) |
| OrderExecutor | Oluşturulmuyordu | Oluşturuluyor + evaluation_loop'a inject |
| ExitExecutor | paper_mode=True, clob_wrapper YOK | paper_mode=self.paper_mode, clob_wrapper=self.clob_client |
| SubscriptionManager | 3 arg | 4 arg (+rtds_client) |
| RTDS run_forever | BAŞLATILMIYORDU | asyncio.create_task ile başlatılıyor |
| Supervisor | YOKTU | _supervisor_loop eklendi (10s interval, 4 loop izleme) |
| paper_mode propagation | Hardcoded True | self.paper_mode (config'ten) |
| signature_type | Hardcoded 2 | config'ten (default=2) |
| ClobClientWrapper | credential_store only | credential_store + signature_type |
| Periodic flush | YOKTU | exit_cycle içinde ~30s flush |
| Balance verify retry | YOKTU | _verify_retry_loop (30s interval) |
| enable_trading/disable_trading | YOKTU | Proxy metotları eklendi |

### 2.3 clob_client_wrapper.py

| Özellik | ESKİ | YENİ |
|---------|------|------|
| LIVE_ORDER_ENABLED | False | **True** (v0.9.2'de açıldı!) |
| signature_type | Hardcoded 2 | Constructor parametresi (default=0 ama schema=2) |
| SDK init | Dict credentials | ApiCreds typed object + signature_type + funder |
| Balance fetch | Basit get call | Explicit BalanceAllowanceParams + USDC 6 decimal conversion |
| send_market_fok_order | TODO stub — return None | 120 satır tam implementasyon (create_market_order + post_order + response parse + retry) |
| 0x prefix | Yoktu | _ensure_initialized'da normalize |
| Error logging | Exception detayı (credential sızıntı riski) | Sadece type(e).__name__ |
| get_fee_rate | Vardı | Değişmedi |
| get_market_resolution | Vardı | Değişmedi |

### 2.4 order_executor.py

| Özellik | ESKİ | YENİ |
|---------|------|------|
| Constructor | 5 param | 7 param (+clob_wrapper, bot_max) |
| event_max/bot_max | Hardcoded 1/3 | intent.event_max + self._bot_max (config) |
| _execute_paper | Tam çalışıyor | Değişmedi (fee comment düzeltildi 0.072→0.10) |
| _execute_live | Guard + TODO stub | Tam implementasyon (SDK call + response parse + fee accounting) |
| clob_wrapper null guard | YOKTU | Eklendi |
| Fee rate default | 0.072 | 0.10 (Polymarket crypto 5M gerçek değer) |

### 2.5 exit_executor.py

| Özellik | ESKİ | YENİ |
|---------|------|------|
| Constructor | 10 param | 13 param (+clob_wrapper, expiry_interval, shutdown_interval, cooldown) |
| SL retry default | 250ms | 500ms (schema ile hizalı) |
| FS retry default | 200ms | 500ms (schema ile hizalı) |
| Live sell | success=False stub | _execute_live_sell (72 satır, tam SDK sell) |
| Cooldown | YOKTU | 1s cooldown (CLOSE_FAILED sonrası spam engeli) |
| Expiry/shutdown interval | Hardcoded | Constructor parametresi |

### 2.6 exit_orchestrator.py

| Özellik | ESKİ | YENİ |
|---------|------|------|
| Close filter | Sadece CLOSING_REQUESTED | CLOSING_REQUESTED + CLOSE_FAILED |
| K5 stale guard | YOKTU | stale_assets parametresi, stale'de TP/SL skip |
| TP reevaluate | Orchestrator + Executor (duplicate) | SADECE Executor (tek nokta) |
| Force sell stale | outcome_fresh parametresi yoktu | outcome_fresh=False ile stale safety override |

### 2.7 live_price.py

| Özellik | ESKİ | YENİ |
|---------|------|------|
| Price fields | up_price, down_price, best_bid, best_ask (direct) | up_bid, up_ask, down_bid, down_ask (source) + property'ler |
| Synthetic price | DOWN = 1 - UP (sentetik) | Her side bağımsız WS'ten (sentetik YOK) |
| Display | YOKTU | display_up, display_down = midpoint(bid,ask) |
| update_from_ws | UP → down_price = 1-bid (cross-update) | UP → sadece up_bid, up_ask (side-only) |

### 2.8 subscription_manager.py

| Özellik | ESKİ | YENİ |
|---------|------|------|
| Constructor | 3 param | 4 param (+rtds_client) |
| RTDS subscribe | YOKTU | apply_diff sonunda update_subscription + subscribe |
| Token set yönetimi | Bridge register only | Bridge register + RTDS subscribe |

### 2.9 schema.py

| Özellik | ESKİ | YENİ |
|---------|------|------|
| auto_start_bot_on_startup | YOKTU | bool = False |
| paper_mode | YOKTU | bool = False (live!) |
| signature_type | YOKTU | int = 2 |
| entry_order_timeout_sec | YOKTU | float = 5.0 |
| order_reject_cooldown_sec | YOKTU | float = 1.0 |
| expiry_retry_interval_ms | YOKTU | int = 200 |
| shutdown_retry_interval_ms | YOKTU | int = 100 |
| exit_order_timeout_sec | YOKTU | float = 5.0 |
| delta threshold min | 0.0001 | 0.00001 (10x düşürüldü) |
| DEFAULT_CRYPTO_FEE_RATE | 0.072 | 0.10 |

### 2.10 discovery_loop.py

| Özellik | ESKİ | YENİ |
|---------|------|------|
| sync call | await self._sync.sync() (async) | self._sync.sync() (sync — fix) |
| Health incidents | list (unbounded) | deque(maxlen=100) (FIFO cap) |
| Crashed task recovery | YOKTU | _task.done() kontrolü |

---

## 3. KRİTİK TUTARSIZLIKLAR

### 3.1 Wiring ↔ Component Uyumsuzluğu
Componentlere yeni parametreler eklendi ama wiring.py bunları kısmen bağlamıyor:

| Component | Yeni Param | Wiring'de Bağlı mı? |
|-----------|-----------|---------------------|
| EvaluationLoop.order_executor | v0.9.0'da eklendi | ✅ EVET |
| EvaluationLoop.position_tracker | v0.9.0'da eklendi | ✅ EVET |
| EvaluationLoop.bridge | v0.9.0'da eklendi | ✅ EVET |
| EvaluationLoop.registry | v0.9.2'de eklendi | ✅ EVET |
| ExitExecutor.clob_wrapper | v0.9.1'de eklendi | ✅ EVET |
| SubscriptionManager.rtds_client | v0.9.0'da eklendi | ✅ EVET |
| ClobClientWrapper.signature_type | v0.9.2'de eklendi | ✅ EVET |

### 3.2 Paper/Live Mode Tutarsızlığı
- Schema default: `paper_mode=False` (live)
- Wiring: `self.paper_mode = cfg.trading.paper_mode` → config'ten False alır
- ExitExecutor/ClaimManager/Settlement: `paper_mode=self.paper_mode` → False alır
- LIVE_ORDER_ENABLED = True

**SONUÇ:** Sistem şu an **live mode'da** çalışıyor. Ama `_order_dispatch_enabled=False` ile order dispatch kapalı.

### 3.3 Balance Sorunu
ESKİ'de balance sadece session start'ta fetch ediliyordu. YENİ'de:
- Startup'ta fetch
- Passive refresh (20s interval)
- Post-fill fetch (live mode)
- Ama: live orderlar arasında balance reconciliation gecikebilir

---

## 4. ÇALIŞAN ve DOĞRULANMIŞ KISIMLAR

| Bileşen | Durum | Test |
|---------|-------|------|
| SDK order signing (sig_type=2 + doğru funder) | ✅ Çalışıyor | İlk canlı trade matched |
| SDK FOK BUY | ✅ Çalışıyor | $1 → 1.96 share alındı |
| SDK FOK SELL | ✅ Çalışıyor | Share satışı matched |
| Outcome price (CLOB WS) | ✅ Çalışıyor | up_bid/up_ask/down_bid/down_ask ayrı |
| PTB fetch (live slug fix) | ✅ Çalışıyor | $73,034 PTB locked |
| Evaluation 5/5 ENTRY | ✅ Çalışıyor | Tüm kurallar PASS |
| Supervisor (crash recovery) | ✅ Çalışıyor | 10s interval, auto-restart |
| CLOSE_FAILED retry | ✅ Çalışıyor | Her exit cycle'da tekrar denenir |
| 1s cooldown | ✅ Çalışıyor | Reject spam engeli |
| Order dispatch gate | ✅ Çalışıyor | Default kapalı |
| Fee rate (0.10) | ✅ Düzeltildi | Docs ile uyumlu |
| Credential encryption | ✅ Çalışıyor | Fernet AES + machine-specific |

---

## 5. BİLİNEN SORUNLAR

| # | Sorun | Detay |
|---|-------|-------|
| 1 | **Upcoming event'e order gitme riski** | Discovery 30dk lookahead. Dispatch guard eklendi ama evaluation tüm eligible'ları değerlendiriyor |
| 2 | **Balance hızlı düşme** | Live order gidince balance fetch asenkron — arada ikinci order gidebilir |
| 3 | **LIVE_ORDER_ENABLED=True kalıcı** | Source code'da True — yanlışlıkla order gidebilir |
| 4 | **Schema paper_mode=False** | Config default live mode — bilinçli ama riskli |

---

## 6. ESKİ TASARIMLA UYUM DURUMU

| Mimari Belge | Kural | Uyum |
|-------------|-------|------|
| CLAUDE.md | "Her modül tek sorumluluk" | ⚠️ EvaluationLoop hem sinyal hem order (ama gate ile kontrollü) |
| CLAUDE.md | "Geçersiz veri evaluation'a ulaşamaz" | ✅ Korunuyor |
| backend-authority-contract.md | "Backend tek otorite" | ✅ Korunuyor |
| data-sources-contract.md | "RTDS failure → STALE + halt" | ✅ Stale guard eklendi |
| external-connectivity-failure-policy.md | "Silent bypass FORBIDDEN" | ✅ Korunuyor |
| accounting-contract.md | "Fill-price bazlı PnL" | ✅ Korunuyor |
| stale-behavior-map.md | "Stale → WAITING" | ✅ Korunuyor |
| discovery-chain-status.md | "Slot bazlı bul ve bekle" | ⚠️ Discovery doğru ama evaluation filtresi eksik |
| credentials-contract.md | "Plaintext asla log'da" | ✅ Düzeltildi (type(e).__name__) |
| operational-risks-724.md | "FOK: kör retry yok" | ✅ Korunuyor |

---

## 7. ÖNERİLEN DÜZELTMELER

1. **Evaluation slot filtresi:** _evaluate_all_eligible'da sadece current slot event'ini evaluate et
2. **Balance gate:** Order göndermeden önce balance fetch + yeterlilik kontrolü (stale guard zaten var)
3. **LIVE_ORDER_ENABLED yönetimi:** İlk test sonrası False'a çevrilmeli mi karar verilmeli
4. **Wiring tutarlılığı:** Tüm yeni parametreler wiring'de bağlanmış mı son kontrol

---

*Rapor tarihi: 2026-04-11*
*Karşılaştırma: Faz 7 (backend tamam) vs v0.9.2 (live test sonrası)*
*Test durumu: 1223 backend test yeşil*

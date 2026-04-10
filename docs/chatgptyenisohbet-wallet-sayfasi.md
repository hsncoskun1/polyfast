# POLYFAST — Versiyon Notu
# chatgptyenisohbet wallet sayfasi
# Tarih: 2026-04-10
# Son Commit: 2680531
# Branch: main
# Toplam Test: 966 passed

---

## BU NOKTAYA KADAR YAPILANLAR

### FAZ 4 — Backend Wiring + Frontend Integration

#### FAZ4-1: Bot Control Fetch Wiring
- Commit: `62c7633`
- `POST /api/bot/start|pause|stop` → frontend Baslat/Duraklat/Durdur butonlari
- Mock mode + gercek mod ayrimli

#### FAZ4-2: Backend Bot Status Authority
- Commit: `32d5d37`
- `deriveBotMode(bot)` — backend state'ten UI mode turetme
- `localOverride` pattern — hizli feedback, sonraki poll sifirlar
- `botLocalMode` / `sessionRef` kaldirildi
- Uptime backend authority (`bot.uptime_sec`)

#### FAZ4-3: Coin Toggle Endpoint + Persist Bug Fix
- Commit: `65b9cd9`
- **KRITIK BUG FIX:** `SettingsStore` `db_store=None` → `db_store=self.settings_store_db` wiring
- `POST /api/coin/{symbol}/toggle` endpoint
- `toggle_coin()` metodu — SettingsStore
- Ayri `coin` router (`backend/api/coin.py`)
- 19 test (toggle + eligibility + persist/restart)

#### FAZ4-4: Frontend $ Butonu Wiring
- Commit: `51e6ef4`
- `coinToggle(symbol)` fetch fonksiyonu
- SearchRail/IdleRail `onToggle` prop + `toggling` Set loading state
- `waiting_rules` → "Once coin ayarlarini tamamla"
- `error` → "Bu coin su an hata durumunda, once sorunu coz"
- Fetch sirasinda disable + opacity (loading hissi)
- Mock mode korundu

#### FAZ4-5: Settings Save Endpoint
- Commit: `28cee80`
- `POST /api/coin/{symbol}/settings` — partial update
- `CoinSettingsRequest` Pydantic validation (negatif, enum, range)
- `CoinSettingsResponse` — `configured` + `missing_fields`
- `update_settings()` metodu — coin_enabled ignore
- 24 test

#### FAZ4-6: Credential Save/Update/Validate
- Commit serisi: `25acf46` → `91135f0` → `0c1b120` → `53cd5e5` → `0aefdb3`
- `POST /api/credential/update` — 6 alan → 2 alan modeli (private_key + relayer_key)
- `GET /api/credential/status` — maskeli gosterim + capability
- `POST /api/credential/validate` — gercek API check + checks array
- `is_fully_ready` semantigi — sadece `validation_status=="passed"` ise true
- `valid` alani KALDIRILDI — yaniltici semantik engellendi
- Partial update — `None` = mevcut korunsun
- Relayer ZORUNLU — auto claim olmadan is_fully_ready=false

### Credential 2-Alan Sade Modeli
- Commit: `2d7f3d0`
- Kullanici sadece `private_key` + `relayer_key` girer
- Backend derive eder: `funder_address` (eth_account), `api_key/secret/passphrase` (SDK)
- `_derive_funder_address()` + `_derive_api_creds()` helpers
- EOA-only varsayimi (proxy/safe ileride)

### Trading API Gercek Validation
- Commit: `7a736ac` → `4b8f162`
- SDK `create_or_derive_api_creds()` + `get_balance_allowance()` ile gercek balance check
- `BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, signature_type=2)`
- Error classification: auth/network/timeout/rate_limit/server/unknown
- HTTP status bazli mesajlar

### Signing Normalizasyon
- Commit: `169784e`
- Private key `0x` prefix otomatik ekleme
- 64-char hex check
- Funder address strict check: `0x` + 42 char + hex

### Frontend Credential Modal
- Commit: `d2b325c` → `7599cae` → `3110c9a` → `7db9157`
- `CredentialModal.tsx` — form + save + validate UX
- 3 grup (Trading API, Signing, Relayer) → 2 input'a sadelestirme BEKLIYOR
- Otomatik acilis: `has_any=false` → zorunlu, `has_any=true && !ready` → kapatilabilir
- Mock mode destegi
- Blur'da bos alan kontrolu
- Mock'ta field validation (hex format, uzunluk)
- Save → validate → sonuc ekrani
- Basarili → "Devam Et" butonu (kullanici kontrolunde)
- Basarisiz → "Duzelt" butonu → form'a don, kirmizi alanlar korunur
- Indeterminate yesil loading bar
- Sahte progress YOK

### Guvenlik Sertlestirme
- Commit: `2680531`
- `sanitize_error(e)` merkezi helper — exception'dan guvenli log mesaji
- `base.py` exception log'lari: `{e}` → `{type(e).__name__}`
- `clob_client_wrapper.py` SDK init hata logu: `{e}` → `{type(e).__name__}`
- `CredentialMaskingFilter` tum handler'lara uygulanmis (dogrulandi)
- 19 guvenlik testi: response redaction, mask helpers, log filter, sanitize_error, exception path
- Hicbir response model'de plaintext credential field YOK

---

## MEVCUT DURUM

### Backend Endpointler
| Endpoint | Metod | Durum |
|----------|-------|-------|
| `POST /api/bot/start\|pause\|stop` | Bot lifecycle | TAMAMLANDI |
| `GET /api/health` | Health + bot status | TAMAMLANDI |
| `GET /api/dashboard/*` | 8 GET endpoint | TAMAMLANDI |
| `POST /api/coin/{symbol}/toggle` | Coin enable/disable | TAMAMLANDI |
| `POST /api/coin/{symbol}/settings` | Coin ayar kaydet | TAMAMLANDI |
| `POST /api/credential/update` | 2-alan credential kaydet + derive | TAMAMLANDI |
| `GET /api/credential/status` | Maskeli gosterim | 2-ALAN MODELE UYARLANACAK |
| `POST /api/credential/validate` | Gercek API check | TAMAMLANDI |

### Frontend Componentler
| Component | Durum |
|-----------|-------|
| Sidebar (bot status, nav) | TAMAMLANDI |
| TopBar (overview) | TAMAMLANDI |
| OpenRail (acik islemler) | TAMAMLANDI |
| SearchRail (islem aranmalar) | TAMAMLANDI |
| IdleRail (pasif coinler) | TAMAMLANDI |
| CredentialModal | 6-INPUT → 2-INPUT SADELESTIRILECEK |
| Coin Settings Modal (⚙) | YAPILMADI |
| Ayarlar Sayfasi | YAPILMADI |

### Test Durumu
- Backend: 966 test GREEN
- TSC: clean (0 error)
- Mock mode: calisiyor

---

## SIRADAKI YAPILACAKLAR

### 1. Credential Status/Validate 2-Alan Uyumu (SONRAKI)
- `credential/status` response'u 2-alan modeline uyarla
- `credential/validate` zaten SDK derive kullaniyor (tamamlandi)
- Frontend credential modal'i 2 input'a sadelestir

### 2. Coin Settings Modal (⚙ butonu)
- Per-coin kural parametreleri modal/drawer
- `POST /api/coin/{symbol}/settings` wiring
- Missing fields vurgulama

### 3. Ayarlar Sayfasi
- Nav'da ⚙ Ayarlar aktif
- Cuzdan Ayarlari bolumu (credential guncelleme)

### 4. Tam Akis Smoke Test
- Credential gir → validate → coin ayarla → enable → bot baslat → search/open/idle kontrol

### 5. Ilerideki Isler
- Encrypted credential persistence (AES-256)
- WebSocket (polling yerine)
- History/Logs sayfalari
- Paper → Live kademeli gecis
- Responsive layout

---

## URUN KARARLARI (BAGLAYICI)

- Backend tek otorite — frontend karar uretmez
- `$` = coin enable/disable toggle
- `⚙` = coin ayarlari duzenleme
- Credential: kullanici sadece `private_key` + `relayer_key` girer
- `funder_address` + `api_key/secret/passphrase` backend derive eder
- `is_fully_ready` = validation_status=="passed" (2/2 check)
- Relayer ZORUNLU — auto claim olmadan cikis YOK
- EOA-only (proxy/safe ileride)
- Optimistic UI YOK — backend authority
- Plaintext credential: response'ta yok, log'da yok, exception'da yok
- Credential persist: simdilik in-memory, encrypted persist ileride
- "Dogrulandi" dili KULLANILMAZ — "kontrol edildi" / "kaydedildi"
- Paper mode normal kullaniciya gorunmez

# POLYFAST — Çalışma Durumu

> **Bu dosya her anlamlı commit'te güncellenir** ve push edilir. Olası bir kayıpta GitHub'dan baktığında en son durumu ve devam edilmesi gereken adımı görürsün.
>
> **Son güncelleme:** 2026-04-09 (session 2 — cyan tema, bot segmented control, claim kartları, dead code temizlik, 40+ polish commit)
> **Aktif branch:** `main`
> **Aktif önizleme URL:** `localhost:5173/?preview=sidebar&mock=full`
> **Çalışma dizini:** `C:\polyfast`

---

## 🟢 Şu an çalışan / tamamlanmış

### Backend (v0.8.0-backend-contract — main'e merge edildi)
- ✅ `/api/health` → `BotStatusContract` (running, health, paused, uptime_sec, latency_ms, vb.)
- ✅ `/api/dashboard/overview` extended (bot_status, bakiye_text, kullanilabilir_text, session_pnl, counters, winrate)
- ✅ `/api/dashboard/positions` extended (variant, live, exits, activity, pnl_*)
- ✅ `/api/dashboard/claims` extended (status enum align RETRY/OK/FAIL, retry, max_retry, next_sec, payout)
- ✅ `/api/dashboard/search` (SearchTileContract + RuleSpecContract)
- ✅ `/api/dashboard/idle` (IdleTileContract — no_events/waiting_rules/bot_stopped/cooldown/error)
- ✅ `/api/dashboard/coins` (CoinInfoContract + fallback registry)
- ✅ `/api/health` defensive None handling (overview balance None → 0.0)
- ✅ 836 / 836 backend test yeşil

### Frontend (sidebar preview — `frontend/src/preview/`)
- ✅ `dashboard.ts` — backend v0.8.0 contract surface TypeScript karşılığı
- ✅ `useDashboardData` hook (sane polling 3s, error backoff)
- ✅ `?preview=sidebar&mock=full` ile mock showcase mode

**Tema & Branding:**
- ✅ **Cyan tema** — brand token mor→cyan (#06b6d4), tüm referanslar otomatik
- ✅ **Polyfast wordmark SVG logo** (inline, cyan + lightning + zigzag underline)
- ✅ Sidebar nav "Marketler" active cyan soft bg/border
- ✅ Ambient bg — sol üst cyan radial %10 + sağ alt vignette

**Sidebar:**
- ✅ 252px, brand SVG logo, NavList (14px font, 16px icon), HealthIndicator (tooltip hover)
- ✅ **Bot Segmented Control** — status line (● Çalışıyor 5sa 6dk 18sn) + 3 segment (Başlat/Duraklat/Durdur)
  - Status line: running yeşil + dot pulse / paused sarı / stopped kırmızı
  - Aktif segment: tone bg + border, inactive soluk
  - Runtime format: `5sa 6dk 18sn` (TR okunur)
  - Frontend-only session simülasyonu: stopped→running sıfırdan, paused→running son değerden
- ✅ **Stop onay modalı** — overlay click dismiss kaldırıldı, Escape + Vazgeç ile çıkılır, aria-dialog
- ✅ Health tooltip: state bazlı açıklama (healthy/degraded/critical/unknown)

**TopBar:**
- ✅ KPI chip'ler: 3 grup (Money cyan/Activity cyan/Outcome yellow), PnlCell tarzı soft bg
- ✅ 10 chip title tooltip (açıklayıcı Türkçe)
- ✅ mockMode dead prop temizlendi

**Layout:**
- ✅ **OpenRail** (sol panel) — Açık İşlemler chrome tab + 2×3 grid kartlar
- ✅ **Main panel** (sağ) — 3 chrome tab: İşlem Arananlar (cyan) | Aranmayanlar (sarı) | Ayar Gerekli (kırmızı)
  - Aktif sekme tonuna göre border + gradient bg + scrollbar rengi dinamik
  - Tab header absolute üst -38px, aynı yükseklikte

**OpenCard (Açık İşlem kartı):**
- ✅ Grid: id (logo+ticker🔗+$+⚙+Tutar) | PNL% hero + USD + SAT | cells (Giriş▲/Canlı▲/Δ) | exits (TP/SL/FS/F-P)
- ✅ **Exit popover** — tetiklenen exit'ten (TP/SL/FS/FSP) yukarı açılan renkli bildirim
  - TP/SL/FS/FSP çoklu active (Set), primary popover ilk tetik
  - FS/FSP öncelik: önce gelen kaynak, ikincil bastırılır
- ✅ SAT butonu: aktif kırmızı / disabled gri (closing/closed/pending state), title tooltip, direkt aksiyon
- ✅ deriveSellState regex: TP/SL/FS/FSP/zorunlu kapatma → closing state
- ✅ $ butonu onClick: OpenCard "zaten aktif" alert, IdleCard "ayar tamamla" validation
- ✅ ⚙ butonu onClick: stub alert (Phase 2)
- ✅ Hover state: translateY -1 + cyan glow
- ✅ Logo tıklanabilir link (Polymarket event URL)
- ✅ Ticker hover underline + 🔗 opacity

**ClaimCard (Claim variant):**
- ✅ OpenCard ile aynı grid yapısı (id/pnl/cells/bottom)
- ✅ Claim label: CLAIM BEKLİYOR (sarı) / CLAIM BAŞARILI (yeşil) / MAX DENEME (kırmızı)
- ✅ Tahsil pnl-sub altında
- ✅ Bottom row: Deneme (3/20) + Sonraki (20s), 2 kolon
- ✅ **Claim popover** — deneme cell'den açılan bildirim:
  - RETRY sarı: "Deneme 3/20 | 20s sonra tekrar"
  - FAIL kırmızı: "Max deneme | elle claim yapınız"
  - OK yeşil: "Claim doğrulandı | $4.21 bakiyeye eklendi"
- ✅ Mock max_retry backend uyumlu (20)

**SearchCard (İşlem Aranan):**
- ✅ Grid: id (logo+ticker+Durum) | pass count hero (6/6) | cells (PTB/Canlı/Δ) | activity bar (pulse) | rules 3×2
- ✅ Rule threshold expression: `30s < 3:15 < 270s`, `78 ≥ 80` format
- ✅ Sort: pass count desc, tie → index desc (useMemo)
- ✅ Pass count rengi: ≥6 yeşil / 5 sarı / ≤4 kırmızı
- ✅ Activity bar pulse animasyonu (severity rengi)

**IdleCard (İşlem Aranmayan / Ayar Gerekli):**
- ✅ KIND_LABEL: İŞLEM ARANMIYOR / İŞLEM AÇMAK İÇİN AYARLARI YAPIN / COOLDOWN / HATA
- ✅ Inline {DOLLAR}/{GEAR} token render (activity metinde buton pill)
- ✅ Ayar Gerekli kind hero + hover kırmızı
- ✅ $ butonu: waiting_rules/error → "ayarları tamamla" validation, bot_stopped → direkt aktif

**Polish & Accessibility:**
- ✅ prefers-reduced-motion: tüm pulse/loop/transition kapanır
- ✅ :focus-visible outline (bot segment butonları)
- ✅ Loading banner: cyan spinner (dönen daire)
- ✅ Empty state SVG ikonlar (search lupa / idle çizgili daire / settings dişli)
- ✅ text/textMuted renk düzeltmesi (#a8a8b8 muted, ana text baskın)
- ✅ useCountFlash hook + flash dot (tab count değişince 2s yanıp söner)
- ✅ Bot status dot running'de pulse animasyonu

**Dead code temizlik (~1580 satır silindi):**
- ✅ EventTile.tsx (~1215 satır, hiç import yok)
- ✅ NotifRail.tsx (~204 satır, render yok)
- ✅ SectionFilterStrip.tsx (~158 satır, chrome-tab ile değiştirildi)
- ✅ useLiveUptime + deriveBotMode (sessionRef ile değiştirildi)

**Mock data:**
- ✅ 10 open (7 lifecycle + 3 sakin) + 3 claim + 6 search + 3 idle
- ✅ session_pnl +12.34 (profit), DOGE gerçekçi değerler
- ✅ SearchTile pnl_tone pass count ile uyumlu
- ✅ Claim max_retry backend default 20

- ✅ Ürün kararları kayıtlı: `~/.claude/projects/C--polyfast/memory/`

### Önemli ürün kararları (memory/)
- `product_tile_semantics.md` — PnL net, $ toggle, ⚙ trigger, alan anlamları
- `product_health_indicator.md` — 4 state (cyan unknown)
- `product_pnl_accounting.md` — 3-layer PnL
- `product_history_analytics.md` — karar+pozisyon geçmişi
- `product_spread_rule_admin_only.md` (DEC-002) — default disabled, 3-flag policy, signal_ready'den hariç
- `feedback_frontend_reusable.md` — preview-only hack yasak
- `feedback_dashboard_workflow.md` — preview-first, ana yüz korunur
- `feedback_component_questioning.md` — toplu refactor yasak, tek tek sor
- `feedback_checkpoint_discipline.md` — anlamlı her adımda commit + push
- `feedback_merge_discipline.md` — merge yalnızca user "merge yap" deyince

---

## 🟡 Şu an üzerinde çalışılan / yarıda kalan

| İş | Durum |
|---|---|
| PnL box big ortalı + 2 buton ($/⚙) altta | yapıldı, görsel doğrulama bekliyor |
| Coin logo fallback fix (lookupCoin backend coins içinde logo_url yok) | yapıldı, görsel doğrulama bekliyor |
| STATUS.md (bu dosya) | ilk versiyon yazılıyor |

---

## 🔴 Yapılacaklar — öncelik sırası (envanter)

### ÖNCE YAP (1-2 hafta, kullanıcı görünür kazanım)
1. **EventTile şişme refactor** — 875 → ayrı dosyalara çıkar (ClaimStatusPanel, ExitGrid, RuleGrid, CoinIdentityBlock kendi dosyaları). Şişme uyarısı ek not 4.
2. **Tooltip JS-positioned component** + 5 kritik yer (HealthIndicator, BotModeChip, TopBar PnL chip, ExitGrid cell, RuleGrid rule)
3. **Tile hover state** (cursor + 1px elevation, tone-lu border-left glow)
4. **Coin display name** geri ekleme (sembol yanı veya tooltip)

### SONRA YAP (3-5 hafta, animasyon turu)
5. **BotModeChip 7 sheen animasyonu** (green slide, yellow breathe, vb.)
6. **ClaimStatusPanel pulsing dot**
7. **ExitGrid cycling flash** (TP→SL→FS→FS PnL sıralı pulse)
8. **CoinIdentityBlock signalReady pulse** (6/6 HAZIR'da)
9. **Tile border flash** (3 ton: profit/loss/claim)
10. **Empty state icon SVG** (◯ ⌕ ⊙ → modern SVG)
11. **Background ambient mor radial gradient overlay**
12. **Section header collapsible** (▼ aç/kapa)
13. **Settings modal** (trigger var, içerik şimdi)
14. **Sound toggle state + localStorage persist**
15. **ActivityStatusLine inline icon registry** (`__KEY__` placeholder)
16. **Sidebar collapse/expand toggle**

### DAHA SONRA YAP (faz değişikliği gerektiren)
17. **Backend orchestrator wiring** — `build_position_live_context`, `build_search_snapshot`, `build_idle_snapshot`, `get_coin_metadata` provider'ları
18. **Tracker counters** — `session_fill_count`, `session_event_seen_count`, `session_win_count`, `session_lost_count`
19. **ClaimRecord `next_retry_at`** — gerçek live countdown
20. **Bot lifecycle gerçek API** (start/pause/stop endpoint'leri)
21. **WebSocket / SSE event stream** (polling yerine)
22. **Settings save endpoint + verify**
23. **Geçmiş sayfası** (NavBar Geçmiş tab) — pozisyon + karar log
24. **Analiz sayfası** — chart'lar + istatistik panelleri
25. **Ayarlar sayfası**
26. **Loglar sayfası** — backend log stream
27. **Notification panel** (sağ alt köşe)
28. **Spread rule admin policy panel** (DEC-002) — visible/toggleable/editable 3 bayrak UI
29. **3-layer PnL accounting görselleştirme**
30. **Responsive breakpoint** — dar viewport sidebar collapse
31. **PANIK butonu** (long-press onay)

---

## 📐 Teknik kararlar (kayıt için)

- **Hedef viewport (defensive):** 820px yükseklik (1920×1080 ekranda browser chrome + Windows taskbar dahil)
- **Hedef viewport (geniş):** 1440px (Q1=a kararı)
- **Tile h:** 118px content + padding = ~138px toplam
- **Mock cap:** mockMode iken 4+2+2=8 tile, dosyada 19 senaryo kalır (development için)
- **CSS injection key:** her component değişikliğinde key bump (`-v2`, `-v3`...) — HMR cache bypass
- **Logo CDN:** `cdn.jsdelivr.net/gh/atomiclabs/cryptocurrency-icons@1a63530/svg/color/{symbol}.svg`
- **Polling:** 3 saniye sane interval, error backoff exponential max 30s

---

## 🗂️ Yedekler

| Tarih | Konum | Branch HEAD |
|---|---|---|
| 2026-04-07 17:24 | `C:\polyfast-backups\polyfast_2026-04-07_17-24_turn3-bitti` | `a5e7db9` |
| 2026-04-07 23:12 | `C:\polyfast-backups\polyfast_2026-04-07_23-12_8tile-fit` | `bb239fe` |
| 2026-04-08 00:30 | `C:\polyfast-backups\polyfast_2026-04-08_00-30_id-row-dollar` | `65574f0` |
| 2026-04-08 02:30 | `C:\polyfast-backups\polyfast_2026-04-08_02-30_tr-translations` | `f5a7bf7` |

GitHub remote: `github.com/hsncoskun1/polyfast` (her commit + push güvende)

---

## 🚨 Kayıp önleme protokolü

1. Her anlamlı commit'te bu dosya güncellenir
2. Her commit + push birlikte gider (`feedback_checkpoint_discipline.md`)
3. PC kapanmadan önce: `git status` → `git add` → `git commit` → `git push`
4. Gün sonu / yemek molası / önemli noktalarda yerel yedek (`C:\polyfast-backups\polyfast_TARIH_NOTU\`)
5. **Stash ana güvence DEĞİL** — remote push esas

---

## 🔧 Ortam hızlı başlangıç

```bash
# Backend
cd C:\polyfast
python -m uvicorn backend.main:app --port 8000

# Frontend
cd C:\polyfast\frontend
npm run dev
# Tarayıcı: http://localhost:5173/?preview=sidebar&mock=full

# Test
python -m pytest tests/backend/ -q
```

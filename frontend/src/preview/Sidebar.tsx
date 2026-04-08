/**
 * Sidebar — sidebar preview'in sol kolonu (240px sabit).
 *
 * Icerik (yukaridan asagiya):
 *  - BrandBlock     : POLYFAST logo + tagline
 *  - NavList        : 5 nav item (Marketler aktif, digerleri disabled)
 *  - BotStatusPanel : BotModeChip + play/pause/stop (statik, animasyon yok)
 *  - HealthIndicator: 4 state + cyan unknown
 *
 * 1. tur kompakt: alt component'ler bu dosya icinde local. Stabil
 * kaldiklarinda ayri dosyalara cikarilacak (sonraki tur).
 *
 * Animasyon: YOK (1. tur statik)
 */

import { useEffect, useRef, useState } from 'react';
import { COLOR, FONT, SIZE, HEALTH_TONE, ensureStyles } from './styles';
// CSS injection key sidebar-v3 (turn 2'de yukseltildi)
import type {
  BotStatusContract,
  HealthLiteral,
  HealthResponse,
} from '../api/dashboard';

// ╔══════════════════════════════════════════════════════════════╗
// ║  CSS                                                         ║
// ╚══════════════════════════════════════════════════════════════╝

ensureStyles(
  'sidebar-v4',
  `
.dsp-sidebar {
  width: ${SIZE.sidebarWidth}px;
  flex-shrink: 0;
  height: 100vh;
  background: ${COLOR.bgRaised};
  border-right: 1px solid ${COLOR.border};
  display: flex;
  flex-direction: column;
  font-family: ${FONT.sans};
  color: ${COLOR.text};
  overflow: hidden;
}

/* Brand block — SVG logo + gradient title (buyuk + ortali) */
.dsp-sb-brand {
  padding: 24px 22px 22px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  position: relative;
}
.dsp-sb-brand::after {
  content: '';
  position: absolute;
  left: 22px;
  right: 22px;
  bottom: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, ${COLOR.borderStrong}, transparent);
}
.dsp-sb-brand-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
}
.dsp-sb-brand-logo {
  width: 56px;
  height: 56px;
  flex-shrink: 0;
  filter: drop-shadow(0 0 12px rgba(34,211,238,0.45));
}
.dsp-sb-brand-title {
  font-size: 20px;
  font-weight: ${FONT.weight.bold};
  letter-spacing: 0.06em;
  background: linear-gradient(90deg, #22d3ee, #67e8f9);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.dsp-sb-brand-bell {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: ${COLOR.brandSoft};
  border: 1px solid ${COLOR.borderStrong};
  border-radius: ${SIZE.radius}px;
  color: ${COLOR.brand};
  font-size: 15px;
  cursor: pointer;
  flex-shrink: 0;
  margin-left: 4px;
}
.dsp-sb-brand-bell:hover {
  background: ${COLOR.brand};
  color: ${COLOR.bg};
}

/* Nav — brand ile arasinda nefes */
.dsp-sb-nav {
  padding: 14px 12px 12px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.dsp-sb-nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 14px;
  border-radius: ${SIZE.radius}px;
  font-size: ${FONT.size.md};
  color: ${COLOR.textMuted};
  cursor: default;
  user-select: none;
  border: 1px solid transparent;
  font-weight: ${FONT.weight.medium};
}
.dsp-sb-nav-item.active {
  background: ${COLOR.brandSoft};
  color: ${COLOR.text};
  border-color: ${COLOR.borderStrong};
}
.dsp-sb-nav-item.disabled {
  opacity: 0.42;
}
.dsp-sb-nav-icon {
  width: 16px;
  text-align: center;
  font-size: ${FONT.size.lg};
}

.dsp-sb-spacer { flex: 1; min-height: 12px; }

/* Bot panel — 3 katmanli command center */
.dsp-sb-bot {
  padding: 14px 14px 16px;
  border-top: 1px solid ${COLOR.divider};
  background: ${COLOR.bg};
  display: flex;
  flex-direction: column;
  gap: 11px;
}

/* Hero (status) */
.dsp-sb-bot-hero {
  padding: 10px 12px;
  border-radius: ${SIZE.radius}px;
  border: 1px solid ${COLOR.border};
  background: ${COLOR.surface};
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.dsp-sb-bot-hero-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.dsp-sb-bot-hero-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dsp-sb-bot-hero-label {
  font-size: ${FONT.size.lg};
  font-weight: ${FONT.weight.bold};
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.dsp-sb-bot-hero-sub {
  font-family: ${FONT.mono};
  font-size: ${FONT.size.xs};
  color: ${COLOR.textMuted};
  padding-left: 18px;
}

/* Action buttons (3 full-width) */
.dsp-sb-bot-actions {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.dsp-sb-bot-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.border};
  border-radius: ${SIZE.radius}px;
  font-size: ${FONT.size.md};
  font-weight: ${FONT.weight.medium};
  color: ${COLOR.text};
  cursor: pointer;
  font-family: ${FONT.sans};
  text-align: left;
}
.dsp-sb-bot-btn[disabled] { opacity: 0.45; cursor: default; }
.dsp-sb-bot-btn:not([disabled]):hover { background: ${COLOR.surfaceHover}; }
.dsp-sb-bot-btn .dsp-sb-bot-btn-icon {
  width: 14px;
  text-align: center;
  font-size: ${FONT.size.md};
}
.dsp-sb-bot-btn.play  { color: ${COLOR.green}; }
.dsp-sb-bot-btn.pause { color: ${COLOR.yellow}; }
.dsp-sb-bot-btn.stop  { color: ${COLOR.red}; }

.dsp-sb-health {
  padding: 12px 14px 14px;
  display: flex;
  align-items: center;
  gap: 8px;
  border-top: 1px solid ${COLOR.divider};
}
.dsp-sb-health-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dsp-sb-health-label {
  font-size: ${FONT.size.sm};
  font-weight: ${FONT.weight.semibold};
  flex: 1;
}
.dsp-sb-health-lat {
  font-family: ${FONT.mono};
  font-size: ${FONT.size.xs};
  color: ${COLOR.textMuted};
  font-weight: ${FONT.weight.medium};
}
`
);

// ╔══════════════════════════════════════════════════════════════╗
// ║  Local renderers                                             ║
// ╚══════════════════════════════════════════════════════════════╝

function BrandBlock() {
  return (
    <div className="dsp-sb-brand">
      <div className="dsp-sb-brand-row">
        <svg
          className="dsp-sb-brand-logo"
          viewBox="0 0 64 64"
          xmlns="http://www.w3.org/2000/svg"
          aria-label="Polyfast"
        >
          <defs>
            <linearGradient id="dsp-pg" x1="0" y1="0" x2="64" y2="64" gradientUnits="userSpaceOnUse">
              <stop offset="0" stopColor="#06b6d4" />
              <stop offset="1" stopColor="#22d3ee" />
            </linearGradient>
          </defs>
          <path
            d="M14 8 L14 56 M14 8 L40 8 Q52 8 52 22 Q52 36 40 36 L14 36"
            stroke="url(#dsp-pg)"
            strokeWidth="8"
            fill="none"
            strokeLinecap="square"
            strokeLinejoin="round"
          />
          <line x1="44" y1="44" x2="58" y2="44" stroke="#22d3ee" strokeWidth="2.5" strokeLinecap="round" />
          <line x1="40" y1="50" x2="58" y2="50" stroke="#22d3ee" strokeWidth="2.5" strokeLinecap="round" opacity="0.7" />
          <line x1="44" y1="56" x2="58" y2="56" stroke="#22d3ee" strokeWidth="2.5" strokeLinecap="round" opacity="0.45" />
        </svg>
        <div className="dsp-sb-brand-title">POLYFAST</div>
      </div>
    </div>
  );
}

interface NavItem {
  icon: string;
  label: string;
  active?: boolean;
  disabled?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { icon: '📊', label: 'Marketler', active: true },
  { icon: '📜', label: 'Geçmiş', disabled: true },
  { icon: '📈', label: 'Analiz', disabled: true },
  { icon: '⚙', label: 'Ayarlar', disabled: true },
  { icon: '📋', label: 'Loglar', disabled: true },
];

function NavList() {
  return (
    <nav className="dsp-sb-nav">
      {NAV_ITEMS.map((item) => (
        <div
          key={item.label}
          className={[
            'dsp-sb-nav-item',
            item.active ? 'active' : '',
            item.disabled ? 'disabled' : '',
          ]
            .filter(Boolean)
            .join(' ')}
        >
          <span className="dsp-sb-nav-icon">{item.icon}</span>
          <span>{item.label}</span>
        </div>
      ))}
    </nav>
  );
}

// Bot mode derive — 7 mode + sub text
interface BotMode {
  label: string;
  sub: string; // hero alt satiri (uptime / aciklama)
  dot: string;
}
function deriveBotMode(bot: BotStatusContract | null | undefined): BotMode {
  if (!bot) {
    return { label: 'BAĞLANTI YOK', sub: 'Backend yanıt vermiyor', dot: COLOR.textDim };
  }
  if (bot.shutdown_in_progress) {
    return { label: 'KAPANIYOR', sub: 'Shutdown akışı sürüyor', dot: COLOR.red };
  }
  if (bot.startup_guard_blocked) {
    return { label: 'BLOK', sub: 'Startup guard engelliyor', dot: COLOR.red };
  }
  if (bot.restore_phase) {
    return { label: 'RESTORE', sub: 'Recovery devam ediyor', dot: COLOR.cyan };
  }
  if (bot.paused) {
    return {
      label: 'DURAKLATILDI',
      sub: `Bekliyor · ${formatUptime(bot.uptime_sec)}`,
      dot: COLOR.yellow,
    };
  }
  if (bot.running === false) {
    return { label: 'DURDU', sub: 'Bot başlatılmadı', dot: COLOR.textDim };
  }
  if (bot.health === 'degraded') {
    return {
      label: 'KISITLI',
      sub: `Degraded mode · ${formatUptime(bot.uptime_sec)}`,
      dot: COLOR.yellow,
    };
  }
  if (bot.health === 'critical') {
    return {
      label: 'KRITIK',
      sub: `Critical · ${formatUptime(bot.uptime_sec)}`,
      dot: COLOR.red,
    };
  }
  return {
    label: 'NORMAL',
    sub: `Çalışıyor · ${formatUptime(bot.uptime_sec)}`,
    dot: COLOR.green,
  };
}

function formatUptime(sec: number | null | undefined): string {
  if (sec == null || sec < 0) return '—';
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  // Saat:dakika:saniye, runtime tick (madde 1.2)
  // Saat 3 haneye cikabilir (uzun session: 100sa+)
  if (h > 0) {
    return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }
  return `${m}:${String(s).padStart(2, '0')}`;
}

/**
 * useLiveUptime — bot uptime'i lokal saniyede artir.
 *
 * Hook polling 3s'de yeni `uptime_sec` getirir; biz aralarda lokal
 * tick ile saniye saniye gosteririz. Hook her yeni deger getirdiginde
 * lokal saat sifirlanir ve yeni base'den ileriye gider.
 *
 * Dashboard "yasiyor" hissi icin kritik (madde 1.2).
 */
function useLiveUptime(serverUptime: number | null | undefined): number | null {
  const [tick, setTick] = useState<number>(0);
  const baseRef = useRef<{ server: number; localStart: number } | null>(null);

  // Server her yeni uptime getirdiginde base'i sifirla
  useEffect(() => {
    if (serverUptime == null) {
      baseRef.current = null;
      return;
    }
    baseRef.current = { server: serverUptime, localStart: Date.now() };
    setTick((t) => t + 1); // ilk render tetikle
  }, [serverUptime]);

  // Her saniye tick — re-render yapip Date.now()'dan delta hesapla
  useEffect(() => {
    if (serverUptime == null) return;
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [serverUptime]);

  if (baseRef.current == null) return null;
  // tick state'ini kullan — re-render trigger (lint memnun olsun)
  void tick;
  const elapsedLocal = Math.floor((Date.now() - baseRef.current.localStart) / 1000);
  return baseRef.current.server + elapsedLocal;
}

/**
 * BotLocalMode — frontend-only lifecycle state.
 *
 * Backend bot lifecycle API'si henuz yok (envanter madde 5.4), bu yuzden
 * Pause/Stop semantik (madde 1.3) frontend state ile simule edilir:
 *  - 'running' : bot calisiyor (default)
 *  - 'paused'  : bot duraklatildi (sayac durur, monitor devam)
 *  - 'stopped' : bot durduruldu (sifir, manuel close gerek)
 */
export type BotLocalMode = 'running' | 'paused' | 'stopped';

interface BotStatusPanelProps {
  bot: BotStatusContract | null | undefined;
  /** Lokal lifecycle state (frontend-only, backend wiring sonra) */
  localMode: BotLocalMode;
  /** Action handler — composition'dan modal trigger eder */
  onAction: (action: 'start' | 'pause' | 'stop') => void;
}

function BotStatusPanel({ bot, localMode, onAction }: BotStatusPanelProps) {
  // Live uptime tick — server polling arasinda saniye saniye artar
  // PAUSED state: tick durur (lokal donmus uptime gosterilir)
  // STOPPED state: uptime sifirlanmis gibi gozukmesi icin null verilir
  const effectiveServerUptime =
    localMode === 'stopped' ? null : bot?.uptime_sec;
  const liveUptimeRaw = useLiveUptime(effectiveServerUptime);
  // PAUSED iken liveUptime yerine son server degerinde sabit kal
  const liveUptime =
    localMode === 'paused' ? bot?.uptime_sec ?? null : liveUptimeRaw;

  // Lokal mode'u backend bot objesine ovrride et — deriveBotMode dogru sub uretsin
  const tickedBot = (() => {
    if (!bot) return bot;
    const base = liveUptime != null ? { ...bot, uptime_sec: liveUptime } : { ...bot };
    if (localMode === 'paused') return { ...base, paused: true, running: true };
    if (localMode === 'stopped') return { ...base, running: false, paused: false, uptime_sec: 0 };
    return base;
  })();
  const mode = deriveBotMode(tickedBot);

  // Buton disabled mantigi
  const startDisabled = localMode === 'running';
  const pauseDisabled = localMode !== 'running';
  const stopDisabled = localMode === 'stopped';

  return (
    <div className="dsp-sb-bot">
      {/* Hero — buyuk status */}
      <div
        className="dsp-sb-bot-hero"
        style={{ borderColor: `${mode.dot}55` }}
      >
        <div className="dsp-sb-bot-hero-row">
          <span
            className="dsp-sb-bot-hero-dot"
            style={{
              background: mode.dot,
              boxShadow: `0 0 8px ${mode.dot}88`,
            }}
          />
          <span className="dsp-sb-bot-hero-label" style={{ color: mode.dot }}>
            {mode.label}
          </span>
        </div>
        <div className="dsp-sb-bot-hero-sub">{mode.sub}</div>
      </div>

      {/* Action buttons — full-width */}
      <div className="dsp-sb-bot-actions">
        <button
          className="dsp-sb-bot-btn play"
          type="button"
          disabled={startDisabled}
          onClick={() => onAction('start')}
        >
          <span className="dsp-sb-bot-btn-icon">▶</span>
          <span>Başlat</span>
        </button>
        <button
          className="dsp-sb-bot-btn pause"
          type="button"
          disabled={pauseDisabled}
          onClick={() => onAction('pause')}
        >
          <span className="dsp-sb-bot-btn-icon">⏸</span>
          <span>Duraklat</span>
        </button>
        <button
          className="dsp-sb-bot-btn stop"
          type="button"
          disabled={stopDisabled}
          onClick={() => onAction('stop')}
        >
          <span className="dsp-sb-bot-btn-icon">⏹</span>
          <span>Durdur</span>
        </button>
      </div>
    </div>
  );
}

function HealthIndicator({
  bot,
}: {
  bot: BotStatusContract | null | undefined;
}) {
  const health: HealthLiteral = bot?.health ?? 'unknown';
  const tone = HEALTH_TONE[health];
  const latency = bot?.latency_ms != null ? `${bot.latency_ms}ms` : null;
  return (
    <div className="dsp-sb-health">
      <span
        className="dsp-sb-health-dot"
        style={{ background: tone.dot, boxShadow: `0 0 6px ${tone.dot}88` }}
      />
      <div className="dsp-sb-health-label" style={{ color: tone.fg }}>
        {tone.label}
      </div>
      {latency && <div className="dsp-sb-health-lat">{latency}</div>}
    </div>
  );
}

// ╔══════════════════════════════════════════════════════════════╗
// ║  Public Sidebar component                                    ║
// ╚══════════════════════════════════════════════════════════════╝

export interface SidebarProps {
  health: HealthResponse | null;
  localBotMode: BotLocalMode;
  onBotAction: (action: 'start' | 'pause' | 'stop') => void;
}

export default function Sidebar({
  health,
  localBotMode,
  onBotAction,
}: SidebarProps) {
  const bot = health?.bot_status ?? null;
  return (
    <aside className="dsp-sidebar">
      <BrandBlock />
      <NavList />
      <div className="dsp-sb-spacer" />
      <BotStatusPanel
        bot={bot}
        localMode={localBotMode}
        onAction={onBotAction}
      />
      <HealthIndicator bot={bot} />
    </aside>
  );
}

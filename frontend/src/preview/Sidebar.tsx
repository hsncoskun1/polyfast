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

import { COLOR, FONT, SIZE, HEALTH_TONE, ensureStyles } from './styles';
// (eski 'sidebar' key'i ile inject edilmis CSS'i override etmek icin
// yeni bir key kullaniyoruz: sidebar-v2)
import type {
  BotStatusContract,
  HealthLiteral,
  HealthResponse,
} from '../api/dashboard';

// ╔══════════════════════════════════════════════════════════════╗
// ║  CSS                                                         ║
// ╚══════════════════════════════════════════════════════════════╝

ensureStyles(
  'sidebar-v3',
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

/* Brand block — daha ferah, daha belirgin */
.dsp-sb-brand {
  padding: 20px 22px 18px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  position: relative;
}
.dsp-sb-brand::after {
  content: '';
  position: absolute;
  left: 22px;
  right: 22px;
  bottom: 0;
  height: 1px;
  background: linear-gradient(90deg, ${COLOR.borderStrong}, transparent);
}
.dsp-sb-brand-title {
  font-size: ${FONT.size.xl};
  font-weight: ${FONT.weight.bold};
  letter-spacing: 0.05em;
  background: linear-gradient(90deg, ${COLOR.brand}, #c084fc);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.dsp-sb-brand-tag {
  font-size: ${FONT.size.sm};
  color: ${COLOR.textMuted};
  font-weight: ${FONT.weight.medium};
  letter-spacing: 0.02em;
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

/* Info rows (Mode / Latency) */
.dsp-sb-bot-info {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 0 4px;
}
.dsp-sb-bot-info-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: ${FONT.size.xs};
}
.dsp-sb-bot-info-lbl {
  color: ${COLOR.textMuted};
  text-transform: uppercase;
  font-weight: ${FONT.weight.semibold};
  letter-spacing: 0.05em;
  width: 52px;
  flex-shrink: 0;
}
.dsp-sb-bot-info-val {
  font-family: ${FONT.mono};
  color: ${COLOR.text};
  font-weight: ${FONT.weight.medium};
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
  padding: 10px 14px 14px;
  display: flex;
  align-items: center;
  gap: 8px;
  border-top: 1px solid ${COLOR.divider};
}
.dsp-sb-health-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.dsp-sb-health-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
  flex: 1;
  min-width: 0;
}
.dsp-sb-health-label {
  font-size: ${FONT.size.sm};
  font-weight: ${FONT.weight.semibold};
}
.dsp-sb-health-meta {
  font-size: ${FONT.size.xs};
  color: ${COLOR.textMuted};
  font-family: ${FONT.mono};
}
`
);

// ╔══════════════════════════════════════════════════════════════╗
// ║  Local renderers                                             ║
// ╚══════════════════════════════════════════════════════════════╝

function BrandBlock() {
  return (
    <div className="dsp-sb-brand">
      <div className="dsp-sb-brand-title">◆ POLYFAST</div>
      <div className="dsp-sb-brand-tag">5M Trading Bot</div>
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
  if (h > 0) return `${h}sa ${String(m).padStart(2, '0')}dk`;
  return `${m}dk ${String(s).padStart(2, '0')}sn`;
}

function deriveModeText(bot: BotStatusContract | null | undefined): string {
  if (!bot) return 'Offline';
  if (bot.startup_guard_blocked) return 'Blocked';
  if (bot.shutdown_in_progress) return 'Shutdown';
  if (bot.restore_phase) return 'Recovery';
  if (bot.health === 'critical') return 'Critical';
  if (bot.health === 'degraded') return 'Degraded';
  if (bot.running === false) return 'Idle';
  if (bot.paused) return 'Paused';
  return 'Live';
}

function BotStatusPanel({ bot }: { bot: BotStatusContract | null | undefined }) {
  const mode = deriveBotMode(bot);
  const modeText = deriveModeText(bot);
  const latency = bot?.latency_ms != null ? `${bot.latency_ms}ms` : '—';

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

      {/* Info rows — Mode / Latency */}
      <div className="dsp-sb-bot-info">
        <div className="dsp-sb-bot-info-row">
          <span className="dsp-sb-bot-info-lbl">Mode</span>
          <span className="dsp-sb-bot-info-val">{modeText}</span>
        </div>
        <div className="dsp-sb-bot-info-row">
          <span className="dsp-sb-bot-info-lbl">Latency</span>
          <span className="dsp-sb-bot-info-val">{latency}</span>
        </div>
      </div>

      {/* Action buttons — full-width */}
      <div className="dsp-sb-bot-actions">
        <button className="dsp-sb-bot-btn play" type="button" disabled>
          <span className="dsp-sb-bot-btn-icon">▶</span>
          <span>Başlat</span>
        </button>
        <button className="dsp-sb-bot-btn pause" type="button" disabled>
          <span className="dsp-sb-bot-btn-icon">⏸</span>
          <span>Duraklat</span>
        </button>
        <button className="dsp-sb-bot-btn stop" type="button" disabled>
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
  // Connection meta — uptime'dan turetilir (latency bot panelinde gozukuyor)
  const uptime = bot?.uptime_sec != null && bot.uptime_sec > 0 ? `${Math.floor(bot.uptime_sec / 60)}dk uptime` : 'baglanti aktif';
  return (
    <div className="dsp-sb-health">
      <span className="dsp-sb-health-dot" style={{ background: tone.dot, boxShadow: `0 0 6px ${tone.dot}88` }} />
      <div className="dsp-sb-health-text">
        <div className="dsp-sb-health-label" style={{ color: tone.fg }}>
          {tone.label}
        </div>
        <div className="dsp-sb-health-meta">{uptime}</div>
      </div>
    </div>
  );
}

// ╔══════════════════════════════════════════════════════════════╗
// ║  Public Sidebar component                                    ║
// ╚══════════════════════════════════════════════════════════════╝

export interface SidebarProps {
  health: HealthResponse | null;
}

export default function Sidebar({ health }: SidebarProps) {
  const bot = health?.bot_status ?? null;
  return (
    <aside className="dsp-sidebar">
      <BrandBlock />
      <NavList />
      <div className="dsp-sb-spacer" />
      <BotStatusPanel bot={bot} />
      <HealthIndicator bot={bot} />
    </aside>
  );
}

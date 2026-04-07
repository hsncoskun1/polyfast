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
import type {
  BotStatusContract,
  HealthLiteral,
  HealthResponse,
} from '../api/dashboard';

// ╔══════════════════════════════════════════════════════════════╗
// ║  CSS                                                         ║
// ╚══════════════════════════════════════════════════════════════╝

ensureStyles(
  'sidebar',
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

.dsp-sb-brand {
  padding: 16px 18px 14px;
  border-bottom: 1px solid ${COLOR.divider};
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.dsp-sb-brand-title {
  font-size: ${FONT.size.lg};
  font-weight: ${FONT.weight.bold};
  letter-spacing: 0.04em;
  background: linear-gradient(90deg, ${COLOR.brand}, #c084fc);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.dsp-sb-brand-tag {
  font-size: ${FONT.size.xs};
  color: ${COLOR.textMuted};
  font-weight: ${FONT.weight.medium};
}

.dsp-sb-nav {
  padding: 10px 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  border-bottom: 1px solid ${COLOR.divider};
}
.dsp-sb-nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
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
  opacity: 0.45;
}
.dsp-sb-nav-icon {
  width: 16px;
  text-align: center;
  font-size: ${FONT.size.lg};
}

.dsp-sb-spacer { flex: 1; }

.dsp-sb-bot {
  padding: 12px 14px;
  border-top: 1px solid ${COLOR.divider};
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.dsp-sb-bot-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.dsp-sb-bot-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.dsp-sb-bot-label {
  font-size: ${FONT.size.sm};
  font-weight: ${FONT.weight.semibold};
  letter-spacing: 0.04em;
  text-transform: uppercase;
  flex: 1;
}
.dsp-sb-bot-uptime {
  font-family: ${FONT.mono};
  font-size: ${FONT.size.xs};
  color: ${COLOR.textMuted};
}
.dsp-sb-bot-controls {
  display: flex;
  gap: 6px;
}
.dsp-sb-bot-btn {
  flex: 1;
  padding: 6px 0;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.border};
  border-radius: ${SIZE.radius}px;
  font-size: ${FONT.size.md};
  color: ${COLOR.text};
  cursor: pointer;
  font-family: ${FONT.sans};
}
.dsp-sb-bot-btn:hover { background: ${COLOR.surfaceHover}; }
.dsp-sb-bot-btn.stop { color: ${COLOR.red}; }
.dsp-sb-bot-btn.pause { color: ${COLOR.yellow}; }
.dsp-sb-bot-btn.play { color: ${COLOR.green}; }

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

// Bot mode derive — basit (animasyonlu BotModeChip sonraki tur)
function deriveBotMode(bot: BotStatusContract | null | undefined): {
  label: string;
  dot: string;
  uptime: string;
} {
  if (!bot) {
    return { label: 'BAĞLANTI YOK', dot: COLOR.textDim, uptime: '—' };
  }
  // Lifecycle priority
  if (bot.shutdown_in_progress) {
    return { label: 'KAPANIYOR', dot: COLOR.red, uptime: '—' };
  }
  if (bot.startup_guard_blocked) {
    return { label: 'BLOK', dot: COLOR.red, uptime: '—' };
  }
  if (bot.restore_phase) {
    return { label: 'RESTORE', dot: COLOR.cyan, uptime: '—' };
  }
  if (bot.paused) {
    return {
      label: 'DURAKLATILDI',
      dot: COLOR.yellow,
      uptime: formatUptime(bot.uptime_sec),
    };
  }
  if (bot.running === false) {
    return { label: 'DURDU', dot: COLOR.textDim, uptime: '—' };
  }
  if (bot.health === 'degraded') {
    return {
      label: 'KISITLI',
      dot: COLOR.yellow,
      uptime: formatUptime(bot.uptime_sec),
    };
  }
  if (bot.health === 'critical') {
    return {
      label: 'KRITIK',
      dot: COLOR.red,
      uptime: formatUptime(bot.uptime_sec),
    };
  }
  return {
    label: 'NORMAL',
    dot: COLOR.green,
    uptime: formatUptime(bot.uptime_sec),
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

function BotStatusPanel({ bot }: { bot: BotStatusContract | null | undefined }) {
  const mode = deriveBotMode(bot);
  return (
    <div className="dsp-sb-bot">
      <div className="dsp-sb-bot-row">
        <span className="dsp-sb-bot-dot" style={{ background: mode.dot }} />
        <span className="dsp-sb-bot-label" style={{ color: mode.dot }}>
          {mode.label}
        </span>
        <span className="dsp-sb-bot-uptime">{mode.uptime}</span>
      </div>
      <div className="dsp-sb-bot-controls">
        <button className="dsp-sb-bot-btn play" type="button" disabled>
          ▶
        </button>
        <button className="dsp-sb-bot-btn pause" type="button" disabled>
          ⏸
        </button>
        <button className="dsp-sb-bot-btn stop" type="button" disabled>
          ⏹
        </button>
      </div>
    </div>
  );
}

function HealthIndicator({
  bot,
  latency,
}: {
  bot: BotStatusContract | null | undefined;
  latency?: number | null;
}) {
  const health: HealthLiteral = bot?.health ?? 'unknown';
  const tone = HEALTH_TONE[health];
  return (
    <div className="dsp-sb-health">
      <span className="dsp-sb-health-dot" style={{ background: tone.dot }} />
      <div className="dsp-sb-health-text">
        <div className="dsp-sb-health-label" style={{ color: tone.fg }}>
          {tone.label}
        </div>
        <div className="dsp-sb-health-meta">
          {latency != null ? `${latency}ms` : 'latency —'}
        </div>
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
      <HealthIndicator bot={bot} latency={bot?.latency_ms ?? null} />
    </aside>
  );
}

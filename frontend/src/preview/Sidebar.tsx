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
  'sidebar-v15',
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
  width: 200px;
  height: auto;
  max-width: 100%;
  flex-shrink: 0;
  filter: drop-shadow(0 0 14px rgba(34,211,238,0.4));
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
  padding: 11px 14px;
  border-radius: ${SIZE.radius}px;
  font-size: ${FONT.size.lg};
  color: ${COLOR.textMuted};
  cursor: default;
  user-select: none;
  border: 1px solid transparent;
  font-weight: ${FONT.weight.semibold};
  letter-spacing: 0.02em;
}
.dsp-sb-nav-item.active {
  background: ${COLOR.cyanSoft};
  color: ${COLOR.text};
  border-color: ${COLOR.cyan};
}
.dsp-sb-nav-item.disabled {
  opacity: 0.42;
}
.dsp-sb-nav-icon {
  width: 18px;
  text-align: center;
  font-size: ${FONT.size.xl};
}

.dsp-sb-spacer { flex: 1; min-height: 12px; }

/* Bot panel — 3 katmanli command center */
.dsp-sb-bot {
  padding: 14px 14px 16px;
  border-top: 1px solid ${COLOR.divider};
  background: ${COLOR.bg};
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* Status line — üstte bot'un mevcut durumu */
.dsp-sb-bot-status {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 12px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.border};
  border-radius: ${SIZE.radius}px;
}
.dsp-sb-bot-status-dot {
  width: 9px; height: 9px; border-radius: 50%;
  flex-shrink: 0;
}
.dsp-sb-bot-status.running .dsp-sb-bot-status-dot {
  animation: dsp-sb-bot-pulse 1.8s ease-in-out infinite;
}
@keyframes dsp-sb-bot-pulse {
  0%, 100% { opacity: 1;    transform: scale(1); }
  50%      { opacity: 0.6;  transform: scale(0.85); }
}
.dsp-sb-bot-paper {
  font-family: ${FONT.mono};
  font-size: 10px;
  font-weight: ${FONT.weight.bold};
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 4px 10px;
  border-radius: ${SIZE.radius}px;
  background: ${COLOR.cyanSoft};
  color: ${COLOR.cyan};
  border: 1px solid ${COLOR.cyan};
  text-align: left;
}
.dsp-sb-bot-status-label {
  font-size: 13px;
  font-weight: ${FONT.weight.bold};
  letter-spacing: 0.08em;
  text-transform: uppercase;
  flex: 1;
}
.dsp-sb-bot-status-time {
  font-family: ${FONT.mono};
  font-size: 13px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.textMuted};
  letter-spacing: 0.03em;
}

/* Segmented control — 3 aksiyon buton tek border içinde */
.dsp-sb-bot-seg {
  display: flex;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.border};
  border-radius: ${SIZE.radius}px;
  overflow: hidden;
  padding: 3px;
  gap: 3px;
}
.dsp-sb-bot-seg-btn {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  padding: 8px 6px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  color: ${COLOR.textMuted};
  font-family: ${FONT.sans};
  font-weight: ${FONT.weight.bold};
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s, opacity 0.15s;
}
.dsp-sb-bot-seg-btn[disabled] { opacity: 0.35; cursor: default; }
.dsp-sb-bot-seg-btn:not([disabled]):hover { background: ${COLOR.surfaceHover}; color: ${COLOR.text}; }
.dsp-sb-bot-seg-btn:focus-visible { outline: 2px solid ${COLOR.cyan}; outline-offset: 2px; }
.dsp-sb-bot-seg-btn-ico {
  font-size: 15px;
  line-height: 1;
}
.dsp-sb-bot-seg-btn-lbl {
  font-size: 10px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  white-space: nowrap;
}
/* Aktif segment (mode == this segment) */
.dsp-sb-bot-seg-btn.active.play  {
  background: ${COLOR.greenSoft};
  border-color: ${COLOR.green};
  color: ${COLOR.green};
}
.dsp-sb-bot-seg-btn.active.pause {
  background: ${COLOR.yellowSoft};
  border-color: ${COLOR.yellow};
  color: ${COLOR.yellow};
}
.dsp-sb-bot-seg-btn.active.stop  {
  background: ${COLOR.redSoft};
  border-color: ${COLOR.red};
  color: ${COLOR.red};
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
  flex-direction: row;
  gap: 4px;
}
.dsp-sb-bot-btn {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  padding: 10px 6px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.border};
  border-radius: ${SIZE.radius}px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.textMuted};
  cursor: pointer;
  font-family: ${FONT.sans};
  text-align: center;
  transition: background 0.15s, border-color 0.15s, color 0.15s, opacity 0.15s;
  opacity: 0.55;
}
.dsp-sb-bot-btn[disabled] { cursor: default; }
.dsp-sb-bot-btn:not([disabled]):hover { background: ${COLOR.surfaceHover}; opacity: 0.85; }
.dsp-sb-bot-btn:focus-visible { outline: 2px solid ${COLOR.cyan}; outline-offset: 2px; }
.dsp-sb-bot-btn .dsp-sb-bot-btn-icon {
  font-size: 16px;
  line-height: 1;
}
.dsp-sb-bot-btn .dsp-sb-bot-btn-label {
  font-size: 10px;
  font-weight: ${FONT.weight.bold};
  letter-spacing: 0.06em;
  text-transform: uppercase;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}
.dsp-sb-bot-btn .dsp-sb-bot-btn-sub {
  font-family: ${FONT.mono};
  font-size: 10px;
  font-weight: ${FONT.weight.semibold};
  color: ${COLOR.textMuted};
  letter-spacing: 0.02em;
}
.dsp-sb-bot-btn.active { opacity: 1; }
.dsp-sb-bot-btn.disabled-stopped { opacity: 0.4; }
.dsp-sb-bot-btn.play.active {
  background: ${COLOR.greenSoft};
  border-color: ${COLOR.green};
  color: ${COLOR.green};
}
.dsp-sb-bot-btn.play.active .dsp-sb-bot-btn-sub { color: ${COLOR.green}; }
.dsp-sb-bot-btn.pause.active {
  background: ${COLOR.yellowSoft};
  border-color: ${COLOR.yellow};
  color: ${COLOR.yellow};
}
.dsp-sb-bot-btn.pause.active .dsp-sb-bot-btn-sub { color: ${COLOR.yellow}; }
.dsp-sb-bot-btn.stop.active {
  background: ${COLOR.redSoft};
  border-color: ${COLOR.red};
  color: ${COLOR.red};
}
.dsp-sb-bot-btn.stop.active .dsp-sb-bot-btn-sub { color: ${COLOR.red}; }
.dsp-sb-bot-btn.play:not(.active)  { color: ${COLOR.green}; }
.dsp-sb-bot-btn.pause:not(.active) { color: ${COLOR.yellow}; }
.dsp-sb-bot-btn.stop:not(.active)  { color: ${COLOR.red}; }

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
  font-size: ${FONT.size.md};
  font-weight: ${FONT.weight.bold};
  flex: 1;
}
.dsp-sb-health-lat {
  font-family: ${FONT.mono};
  font-size: ${FONT.size.sm};
  color: ${COLOR.textMuted};
  font-weight: ${FONT.weight.semibold};
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
          viewBox="0 0 360 140"
          xmlns="http://www.w3.org/2000/svg"
          aria-label="Polyfast"
          fill="none"
        >
          {/* Wordmark "polyfast" — cyan ince çift çizgi (outline) */}
          <g
            stroke="#22d3ee"
            strokeWidth="11"
            strokeLinejoin="round"
            strokeLinecap="round"
            fontFamily="system-ui, sans-serif"
          >
            <text
              x="6"
              y="92"
              fontSize="92"
              fontWeight="800"
              letterSpacing="-2"
              fill="#22d3ee"
              stroke="#0f172a"
              strokeWidth="6"
              paintOrder="stroke"
            >
              polyfast
            </text>
          </g>
          {/* Üst sağ çift lightning bolt */}
          <path
            d="M260 6 L246 56 L262 56 L252 90 L298 30 L278 30 L292 6 Z"
            fill="#22d3ee"
            stroke="#0f172a"
            strokeWidth="3"
            strokeLinejoin="round"
          />
          <path
            d="M296 4 L286 44 L298 44 L290 72 L320 28 L306 28 L316 4 Z"
            fill="#22d3ee"
            stroke="#0f172a"
            strokeWidth="3"
            strokeLinejoin="round"
          />
          {/* Alt zigzag waveform underline */}
          <path
            d="M150 116 L172 102 L194 122 L216 100 L238 124 L260 102 L282 122 L304 102 L326 122 L350 110"
            stroke="#22d3ee"
            strokeWidth="6"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        </svg>
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
  { icon: '⚙', label: 'Ayarlar', disabled: false },
  { icon: '📋', label: 'Loglar', disabled: true },
];

function NavList({ onNavClick }: { onNavClick?: (label: string) => void }) {
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
          style={!item.disabled && !item.active ? { cursor: 'pointer' } : undefined}
          onClick={() => { if (!item.disabled && onNavClick) onNavClick(item.label); }}
        >
          <span className="dsp-sb-nav-icon">{item.icon}</span>
          <span>{item.label}</span>
        </div>
      ))}
    </nav>
  );
}

function formatUptime(sec: number | null | undefined): string {
  if (sec == null || sec < 0) return '—';
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return `${h}sa ${m}dk ${s}sn`;
  if (m > 0) return `${m}dk ${s}sn`;
  return `${s}sn`;
}

/**
 * BotMode — bot lifecycle state (backend authority).
 *
 * Backend bot_status.running + bot_status.paused → deriveBotMode() ile türetilir.
 * Mock mode'da localOverride ile hızlı feedback sağlanır.
 */
export type BotMode = 'running' | 'paused' | 'stopped';

/** Backend bot_status'tan UI mode türet — tek otorite backend. */
function deriveBotMode(bot: BotStatusContract | null | undefined): BotMode {
  if (!bot || bot.running === false) return 'stopped';
  if (bot.paused === true) return 'paused';
  return 'running';
}

interface BotStatusPanelProps {
  bot: BotStatusContract | null | undefined;
  /** Action handler — composition'dan modal trigger eder */
  onAction: (action: 'start' | 'pause' | 'stop') => void;
  /** Mock mode — backend yoksa local sim kullanır */
  mockMode?: boolean;
  /** Mock mode'da hızlı feedback için geçici local override */
  localOverride?: BotMode | null;
}

function BotStatusPanel({ bot, onAction, mockMode, localOverride }: BotStatusPanelProps) {
  // Mode: mock'ta localOverride, gerçek mod'da backend state
  const mode: BotMode = localOverride ?? deriveBotMode(bot);

  // Uptime: backend authority (bot.uptime_sec), mock'ta null
  const uptime = bot?.uptime_sec ?? null;

  // Buton disabled mantigi
  const startDisabled = mode === 'running';
  const pauseDisabled = mode !== 'running';
  const stopDisabled = mode === 'stopped';

  // Status line renkleri
  const statusColor =
    mode === 'running' ? COLOR.green :
    mode === 'paused'  ? COLOR.yellow :
    COLOR.red;
  const statusLabel =
    mode === 'running' ? 'Çalışıyor' :
    mode === 'paused'  ? 'Durakladı' :
    'Durdu';
  const statusTime =
    mode === 'stopped'
      ? '—'
      : uptime != null
        ? formatUptime(uptime)
        : '—';
  void mockMode;

  return (
    <div className="dsp-sb-bot">
      {/* Status line — bot'un mevcut durumu */}
      <div className={`dsp-sb-bot-status ${mode}`} style={{ borderColor: `${statusColor}55` }}>
        <span
          className="dsp-sb-bot-status-dot"
          style={{ background: statusColor, boxShadow: `0 0 8px ${statusColor}aa` }}
        />
        <span className="dsp-sb-bot-status-label" style={{ color: statusColor }}>
          {statusLabel}
        </span>
        <span className="dsp-sb-bot-status-time">{statusTime}</span>
      </div>
      {/* Paper badge — admin surface gelene kadar gizli. bot?.paper_mode field hazır. */}

      {/* Segmented control — 3 aksiyon */}
      <div className="dsp-sb-bot-seg">
        <button
          type="button"
          className={`dsp-sb-bot-seg-btn play${mode === 'running' ? ' active' : ''}`}
          disabled={startDisabled}
          onClick={() => onAction('start')}
          title="Başlat"
        >
          <span className="dsp-sb-bot-seg-btn-ico">▶</span>
          <span className="dsp-sb-bot-seg-btn-lbl">Başlat</span>
        </button>
        <button
          type="button"
          className={`dsp-sb-bot-seg-btn pause${mode === 'paused' ? ' active' : ''}`}
          disabled={pauseDisabled}
          onClick={() => onAction('pause')}
          title="Duraklat"
        >
          <span className="dsp-sb-bot-seg-btn-ico">⏸</span>
          <span className="dsp-sb-bot-seg-btn-lbl">Duraklat</span>
        </button>
        <button
          type="button"
          className={`dsp-sb-bot-seg-btn stop${mode === 'stopped' ? ' active' : ''}`}
          disabled={stopDisabled}
          onClick={() => onAction('stop')}
          title="Durdur"
        >
          <span className="dsp-sb-bot-seg-btn-ico">⏹</span>
          <span className="dsp-sb-bot-seg-btn-lbl">Durdur</span>
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
  const tooltip = (() => {
    const lat = latency ?? '—';
    if (health === 'healthy')  return `Backend bağlantısı sağlıklı — ${lat} gecikme`;
    if (health === 'degraded') return `Backend bağlantısı yavaş — ${lat} gecikme`;
    if (health === 'critical') return 'Backend yanıt vermiyor — bağlantı koptu';
    return 'Backend durumu bilinmiyor — henüz veri alınmadı';
  })();
  return (
    <div className="dsp-sb-health" title={tooltip}>
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
  onBotAction: (action: 'start' | 'pause' | 'stop') => void;
  /** Sidebar nav tıklama — Ayarlar gibi aktif menü öğeleri için */
  onNavClick?: (label: string) => void;
  /** Mock mode — backend yoksa local sim kullanır */
  mockMode?: boolean;
  /** Mock mode'da hızlı feedback için geçici local override */
  localOverride?: BotMode | null;
}

export default function Sidebar({
  health,
  onBotAction,
  onNavClick,
  mockMode,
  localOverride,
}: SidebarProps) {
  const bot = health?.bot_status ?? null;
  return (
    <aside className="dsp-sidebar">
      <BrandBlock />
      <NavList onNavClick={onNavClick} />
      <div className="dsp-sb-spacer" />
      <BotStatusPanel
        bot={bot}
        onAction={onBotAction}
        mockMode={mockMode}
        localOverride={localOverride}
      />
      <HealthIndicator bot={bot} />
    </aside>
  );
}

/**
 * TopBar — sidebar preview'in ust bari (64px ince).
 *
 * Tek satir KPI strip + sound toggle. Lifecycle butonlari sidebar'da,
 * top bar sadece bilgi gosterir.
 *
 * 10 kisa etiketli metric (kompakt ama okunur):
 * Bakiye / Kullanilabilir / PnL / Acilan / Gorulen / AG / Win / Lost / Bekleyen / Winrate
 *
 * 1. tur kompakt: KpiCell helper bu dosya icinde local.
 *
 * Animasyon: YOK
 */

import { COLOR, FONT, SIZE, PNL_TONE, ensureStyles } from './styles';
import type { DashboardOverview, PnlTone } from '../api/dashboard';

// ╔══════════════════════════════════════════════════════════════╗
// ║  CSS                                                         ║
// ╚══════════════════════════════════════════════════════════════╝

ensureStyles(
  'topbar-v11',
  `
.dsp-topbar {
  height: 56px;
  flex-shrink: 0;
  background: ${COLOR.bg};
  border-bottom: 1px solid ${COLOR.border};
  display: flex;
  align-items: center;
  padding: 0 12px;
  font-family: ${FONT.sans};
  color: ${COLOR.text};
  gap: 8px;
  overflow: hidden;
  min-width: 0;
}
.dsp-tb-group { flex: 1 1 0; min-width: 0; justify-content: center; }

.dsp-tb-group {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-shrink: 0;
}
.dsp-tb-divider {
  width: 1px;
  height: 32px;
  background: ${COLOR.borderStrong};
  flex-shrink: 0;
  opacity: 0.55;
}

/* Chip — boxed premium, ic bosluklar minimal, yazilar buyuk + ortali */
.dsp-tb-chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0;
  padding: 3px 8px 4px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.border};
  border-radius: ${SIZE.radius}px;
  min-width: 56px;
  white-space: nowrap;
  flex-shrink: 0;
  position: relative;
  text-align: center;
}
.dsp-tb-chip-label {
  font-size: 9px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.textMuted};
  text-transform: uppercase;
  letter-spacing: 0.06em;
  line-height: 1.1;
}
.dsp-tb-chip-value {
  font-family: ${FONT.mono};
  font-size: 14px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.text};
  line-height: 1.1;
}
.dsp-tb-chip-sub {
  font-family: ${FONT.mono};
  font-size: 11px;
  font-weight: ${FONT.weight.medium};
  margin-top: 0;
  line-height: 1;
}

/* PNL chip ozel — 2 satir, tone bg, daha buyuk vurgu */
.dsp-tb-chip.pnl {
  min-width: 92px;
  padding: 3px 10px 4px;
}
.dsp-tb-chip.pnl .dsp-tb-chip-value {
  font-size: 14px;
}
.dsp-tb-chip.pnl.profit { background: ${COLOR.greenSoft}; border-color: ${COLOR.greenSoft}; }
.dsp-tb-chip.pnl.profit .dsp-tb-chip-value, .dsp-tb-chip.pnl.profit .dsp-tb-chip-sub { color: ${COLOR.green}; }
.dsp-tb-chip.pnl.loss { background: ${COLOR.redSoft}; border-color: ${COLOR.redSoft}; }
.dsp-tb-chip.pnl.loss .dsp-tb-chip-value, .dsp-tb-chip.pnl.loss .dsp-tb-chip-sub { color: ${COLOR.red}; }
.dsp-tb-chip.pnl.neutral .dsp-tb-chip-value { color: ${COLOR.text}; }
.dsp-tb-chip.pnl.off .dsp-tb-chip-value { color: ${COLOR.textDim}; }

/* Tonelu chip — boxed bg + colored value (oturum pnl gibi) */
.dsp-tb-chip.tone-green   { background: ${COLOR.greenSoft};  border-color: ${COLOR.greenSoft}; }
.dsp-tb-chip.tone-green   .dsp-tb-chip-value { color: ${COLOR.green}; }
.dsp-tb-chip.tone-red     { background: ${COLOR.redSoft};    border-color: ${COLOR.redSoft}; }
.dsp-tb-chip.tone-red     .dsp-tb-chip-value { color: ${COLOR.red}; }
.dsp-tb-chip.tone-yellow  { background: ${COLOR.yellowSoft}; border-color: ${COLOR.yellowSoft}; }
.dsp-tb-chip.tone-yellow  .dsp-tb-chip-value { color: ${COLOR.yellow}; }
.dsp-tb-chip.tone-brand   { background: ${COLOR.brandSoft};  border-color: ${COLOR.brandSoft}; }
.dsp-tb-chip.tone-brand   .dsp-tb-chip-value { color: ${COLOR.brand}; }
.dsp-tb-chip.tone-cyan    { background: rgba(6, 182, 212, 0.16); border-color: rgba(6, 182, 212, 0.16); }
.dsp-tb-chip.tone-cyan    .dsp-tb-chip-value { color: ${COLOR.cyan}; }

/* Sound button */
.dsp-tb-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  padding-left: 14px;
  flex-shrink: 0;
}
.dsp-tb-btn {
  width: 38px;
  height: 38px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.border};
  border-radius: ${SIZE.radius}px;
  color: ${COLOR.textMuted};
  cursor: pointer;
  font-size: 15px;
}
.dsp-tb-btn:hover {
  background: ${COLOR.surfaceHover};
  color: ${COLOR.text};
}

/* MOCK badge — sadece mockMode iken */
.dsp-tb-mock {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  background: ${COLOR.brandSoft};
  border: 1px solid ${COLOR.borderStrong};
  border-radius: ${SIZE.radius}px;
  font-family: ${FONT.mono};
  font-size: 10px;
  font-weight: ${FONT.weight.bold};
  letter-spacing: 0.08em;
  color: ${COLOR.brand};
  text-transform: uppercase;
  flex-shrink: 0;
}
.dsp-tb-mock-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: ${COLOR.brand};
  box-shadow: 0 0 6px ${COLOR.brand}88;
}
`
);

// ╔══════════════════════════════════════════════════════════════╗
// ║  Local renderers                                             ║
// ╚══════════════════════════════════════════════════════════════╝

type ChipTone = 'green' | 'red' | 'yellow' | 'brand' | 'cyan';
interface KpiCellProps {
  label: string;
  value: string;
  tone?: PnlTone;
  color?: string;
  chipTone?: ChipTone;
}

function KpiCell({ label, value, tone, color: colorProp, chipTone }: KpiCellProps) {
  const color = colorProp ?? (tone ? PNL_TONE[tone].fg : COLOR.text);
  const cls = `dsp-tb-chip${chipTone ? ` tone-${chipTone}` : ''}`;
  return (
    <div className={cls}>
      <div className="dsp-tb-chip-label">{label}</div>
      <div className="dsp-tb-chip-value" style={chipTone ? undefined : { color }}>
        {value}
      </div>
    </div>
  );
}

/** Winrate -> chipTone (>=50 green, >0 yellow, =0 red). */
function winrateChipTone(raw: string | null | undefined): ChipTone {
  if (!raw) return 'brand';
  const m = raw.match(/(-?\d+(?:\.\d+)?)/);
  if (!m) return 'brand';
  const pct = parseFloat(m[1]);
  if (pct >= 50) return 'green';
  if (pct > 0) return 'yellow';
  return 'red';
}

/** PnL chip — 2 satir (deger + yuzde), tone bg */
interface PnlCellProps {
  label: string;
  value: string;
  pct: string | null;
  tone: PnlTone;
}
function PnlCell({ label, value, pct, tone }: PnlCellProps) {
  return (
    <div className={`dsp-tb-chip pnl ${tone}`}>
      <div className="dsp-tb-chip-label">{label}</div>
      <div className="dsp-tb-chip-value">{value}</div>
      {pct && <div className="dsp-tb-chip-sub">{pct}</div>}
    </div>
  );
}

/** Format helpers — null/undefined -> '—' (durust empty state) */
function fmtMoney(value: string | null | undefined): string {
  return value ?? '—';
}
function fmtNum(value: number | null | undefined): string {
  return value == null ? '—' : String(value);
}
function fmtPnlValue(value: number | null | undefined): string {
  if (value == null) return '—';
  const sign = value >= 0 ? '+' : '';
  return `${sign}$${value.toFixed(2)}`;
}
function fmtPnlPct(pct: number | null | undefined): string | null {
  if (pct == null) return null;
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(1)}%`;
}
function pnlTone(value: number | null | undefined): PnlTone {
  if (value == null) return 'off';
  if (value > 0) return 'profit';
  if (value < 0) return 'loss';
  return 'neutral';
}

// ╔══════════════════════════════════════════════════════════════╗
// ║  Public TopBar component                                     ║
// ╚══════════════════════════════════════════════════════════════╝

export interface TopBarProps {
  overview: DashboardOverview | null;
  /** Mock showcase mode — sag ust 'MOCK' badge gosterilir. Default false. */
  mockMode?: boolean;
}

export default function TopBar({ overview }: TopBarProps) {
  const pnlValue = overview?.session_pnl;
  return (
    <div className="dsp-topbar">
      {/* Group 1 — MONEY — mor yasak, sadece cyan/green/red/yellow */}
      <div className="dsp-tb-group">
        <KpiCell label="Bakiye" value={fmtMoney(overview?.bakiye_text)} chipTone="cyan" />
        <KpiCell
          label="Kullanılabilir"
          value={fmtMoney(overview?.kullanilabilir_text)}
          chipTone="green"
        />
        <PnlCell
          label="Oturum PnL"
          value={fmtPnlValue(pnlValue)}
          pct={fmtPnlPct(overview?.session_pnl_pct)}
          tone={pnlTone(pnlValue)}
        />
      </div>

      <div className="dsp-tb-divider" />

      {/* Group 2 — ACTIVITY */}
      <div className="dsp-tb-group">
        <KpiCell label="Açılan" value={fmtNum(overview?.acilan)} chipTone="cyan" />
        <KpiCell label="Görülen" value={fmtNum(overview?.gorulen)} chipTone="cyan" />
        <KpiCell label="A/G Rate" value={overview?.ag_rate ?? '—'} chipTone="yellow" />
      </div>

      <div className="dsp-tb-divider" />

      {/* Group 3 — OUTCOME */}
      <div className="dsp-tb-group">
        <KpiCell label="Kazanan" value={fmtNum(overview?.win)} chipTone="green" />
        <KpiCell label="Kaybeden" value={fmtNum(overview?.lost)} chipTone="red" />
        <KpiCell label="Bekleyen" value={fmtNum(overview?.pending_claims)} chipTone="yellow" />
        <KpiCell
          label="Winrate"
          value={overview?.winrate ?? '—'}
          chipTone={winrateChipTone(overview?.winrate)}
        />
      </div>

    </div>
  );
}

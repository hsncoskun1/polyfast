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
  'topbar-v2',
  `
.dsp-topbar {
  height: ${SIZE.topBarHeight}px;
  flex-shrink: 0;
  background: ${COLOR.bg};
  border-bottom: 1px solid ${COLOR.border};
  display: flex;
  align-items: center;
  padding: 0 16px;
  font-family: ${FONT.sans};
  color: ${COLOR.text};
  gap: 12px;
  overflow-x: auto;
}

.dsp-tb-group {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.dsp-tb-divider {
  width: 1px;
  height: 36px;
  background: ${COLOR.borderStrong};
  flex-shrink: 0;
  opacity: 0.55;
}

/* Chip — boxed premium */
.dsp-tb-chip {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 7px 11px 8px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.border};
  border-radius: ${SIZE.radius}px;
  min-width: 64px;
  white-space: nowrap;
  flex-shrink: 0;
  position: relative;
}
.dsp-tb-chip-label {
  font-size: 9px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.textMuted};
  text-transform: uppercase;
  letter-spacing: 0.07em;
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
  font-size: 10px;
  font-weight: ${FONT.weight.medium};
  margin-top: 1px;
  line-height: 1;
}

/* PNL chip ozel — 2 satir, tone bg */
.dsp-tb-chip.pnl {
  min-width: 110px;
  padding: 6px 11px 7px;
}
.dsp-tb-chip.pnl.profit { background: ${COLOR.greenSoft}; border-color: ${COLOR.greenSoft}; }
.dsp-tb-chip.pnl.profit .dsp-tb-chip-value, .dsp-tb-chip.pnl.profit .dsp-tb-chip-sub { color: ${COLOR.green}; }
.dsp-tb-chip.pnl.loss { background: ${COLOR.redSoft}; border-color: ${COLOR.redSoft}; }
.dsp-tb-chip.pnl.loss .dsp-tb-chip-value, .dsp-tb-chip.pnl.loss .dsp-tb-chip-sub { color: ${COLOR.red}; }
.dsp-tb-chip.pnl.neutral .dsp-tb-chip-value { color: ${COLOR.text}; }
.dsp-tb-chip.pnl.off .dsp-tb-chip-value { color: ${COLOR.textDim}; }

/* Sound button */
.dsp-tb-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  padding-left: 12px;
  flex-shrink: 0;
}
.dsp-tb-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.border};
  border-radius: ${SIZE.radius}px;
  color: ${COLOR.textMuted};
  cursor: pointer;
  font-size: 14px;
}
.dsp-tb-btn:hover {
  background: ${COLOR.surfaceHover};
  color: ${COLOR.text};
}
`
);

// ╔══════════════════════════════════════════════════════════════╗
// ║  Local renderers                                             ║
// ╚══════════════════════════════════════════════════════════════╝

interface KpiCellProps {
  label: string;
  value: string;
  tone?: PnlTone;
}

function KpiCell({ label, value, tone }: KpiCellProps) {
  const color = tone ? PNL_TONE[tone].fg : COLOR.text;
  return (
    <div className="dsp-tb-chip">
      <div className="dsp-tb-chip-label">{label}</div>
      <div className="dsp-tb-chip-value" style={{ color }}>
        {value}
      </div>
    </div>
  );
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
}

export default function TopBar({ overview }: TopBarProps) {
  const pnlValue = overview?.session_pnl;
  return (
    <div className="dsp-topbar">
      {/* Group 1 — MONEY */}
      <div className="dsp-tb-group">
        <KpiCell label="Bakiye" value={fmtMoney(overview?.bakiye_text)} />
        <KpiCell
          label="Kullanılabilir"
          value={fmtMoney(overview?.kullanilabilir_text)}
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
        <KpiCell label="Açılan" value={fmtNum(overview?.acilan)} />
        <KpiCell label="Görülen" value={fmtNum(overview?.gorulen)} />
        <KpiCell label="A/G" value={overview?.ag_rate ?? '—'} />
      </div>

      <div className="dsp-tb-divider" />

      {/* Group 3 — OUTCOME */}
      <div className="dsp-tb-group">
        <KpiCell label="Win" value={fmtNum(overview?.win)} />
        <KpiCell label="Lost" value={fmtNum(overview?.lost)} />
        <KpiCell label="Bekleyen" value={fmtNum(overview?.pending_claims)} />
        <KpiCell label="Winrate" value={overview?.winrate ?? '—'} />
      </div>

      <div className="dsp-tb-actions">
        <button className="dsp-tb-btn" type="button" title="Ses">
          🔔
        </button>
      </div>
    </div>
  );
}

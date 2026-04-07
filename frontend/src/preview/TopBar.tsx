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
  'topbar',
  `
.dsp-topbar {
  height: ${SIZE.topBarHeight}px;
  flex-shrink: 0;
  background: ${COLOR.bgRaised};
  border-bottom: 1px solid ${COLOR.border};
  display: flex;
  align-items: center;
  padding: 0 18px;
  font-family: ${FONT.sans};
  color: ${COLOR.text};
  gap: 14px;
  overflow-x: auto;
}

.dsp-tb-strip {
  display: flex;
  align-items: center;
  gap: 0;
  flex: 1;
  min-width: 0;
}

.dsp-tb-cell {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 0 14px;
  border-right: 1px solid ${COLOR.divider};
  min-width: 0;
  white-space: nowrap;
}
.dsp-tb-cell:first-child { padding-left: 0; }
.dsp-tb-cell:last-of-type { border-right: none; }

.dsp-tb-cell-label {
  font-size: 9px;
  font-weight: ${FONT.weight.semibold};
  color: ${COLOR.textMuted};
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.dsp-tb-cell-value {
  font-family: ${FONT.mono};
  font-size: ${FONT.size.lg};
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.text};
}

.dsp-tb-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  padding-left: 14px;
  border-left: 1px solid ${COLOR.divider};
}
.dsp-tb-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.border};
  border-radius: ${SIZE.radius}px;
  color: ${COLOR.textMuted};
  cursor: pointer;
  font-size: ${FONT.size.lg};
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
    <div className="dsp-tb-cell">
      <div className="dsp-tb-cell-label">{label}</div>
      <div className="dsp-tb-cell-value" style={{ color }}>
        {value}
      </div>
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
function fmtPnl(value: number | null | undefined, pct: number | null | undefined): string {
  if (value == null) return '—';
  const sign = value >= 0 ? '+' : '';
  const pctStr = pct != null ? ` (${sign}${pct.toFixed(1)}%)` : '';
  return `${sign}$${value.toFixed(2)}${pctStr}`;
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
  return (
    <div className="dsp-topbar">
      <div className="dsp-tb-strip">
        <KpiCell
          label="Bakiye"
          value={fmtMoney(overview?.bakiye_text)}
        />
        <KpiCell
          label="Kullanılabilir"
          value={fmtMoney(overview?.kullanilabilir_text)}
        />
        <KpiCell
          label="PnL"
          value={fmtPnl(overview?.session_pnl, overview?.session_pnl_pct)}
          tone={pnlTone(overview?.session_pnl)}
        />
        <KpiCell label="Açılan" value={fmtNum(overview?.acilan)} />
        <KpiCell label="Görülen" value={fmtNum(overview?.gorulen)} />
        <KpiCell label="AG" value={overview?.ag_rate ?? '—'} />
        <KpiCell label="Win" value={fmtNum(overview?.win)} />
        <KpiCell label="Lost" value={fmtNum(overview?.lost)} />
        <KpiCell
          label="Bekleyen"
          value={fmtNum(overview?.pending_claims)}
        />
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

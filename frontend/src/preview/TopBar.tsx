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

import { COLOR, FONT, SIZE, ensureStyles } from './styles';
import type { DashboardOverview, PnlTone } from '../api/dashboard';

// ╔══════════════════════════════════════════════════════════════╗
// ║  CSS                                                         ║
// ╚══════════════════════════════════════════════════════════════╝

ensureStyles(
  'topbar-v17',
  `
.dsp-topbar {
  height: ${SIZE.topBarHeight}px;
  flex-shrink: 0;
  background: ${COLOR.bg};
  border-bottom: 1px solid ${COLOR.border};
  display: flex;
  align-items: center;
  padding: 0 10px;
  font-family: ${FONT.sans};
  color: ${COLOR.text};
  gap: 14px;
  overflow: hidden;
  min-width: 0;
}

.dsp-tb-group {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 1;
  min-width: 0;
}
.dsp-tb-divider {
  width: 1px;
  height: 44px;
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
  gap: 1px;
  padding: 4px 9px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.border};
  border-radius: ${SIZE.radius}px;
  min-width: 64px;
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
  letter-spacing: 0.05em;
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
  min-width: 100px;
  padding: 3px 11px 4px;
}
.dsp-tb-chip.pnl .dsp-tb-chip-value {
  font-size: 15px;
}
.dsp-tb-chip.pnl.profit { background: ${COLOR.greenSoft}; border-color: ${COLOR.greenSoft}; }
.dsp-tb-chip.pnl.profit .dsp-tb-chip-value, .dsp-tb-chip.pnl.profit .dsp-tb-chip-sub { color: ${COLOR.green}; }
.dsp-tb-chip.pnl.loss { background: ${COLOR.redSoft}; border-color: ${COLOR.redSoft}; }
.dsp-tb-chip.pnl.loss .dsp-tb-chip-value, .dsp-tb-chip.pnl.loss .dsp-tb-chip-sub { color: ${COLOR.red}; }
.dsp-tb-chip.pnl.pending { background: ${COLOR.yellowSoft}; border-color: ${COLOR.yellowSoft}; }
.dsp-tb-chip.pnl.pending .dsp-tb-chip-value, .dsp-tb-chip.pnl.pending .dsp-tb-chip-sub { color: ${COLOR.yellow}; }
.dsp-tb-chip.pnl.neutral { background: ${COLOR.cyanSoft}; border-color: ${COLOR.cyanSoft}; }
.dsp-tb-chip.pnl.neutral .dsp-tb-chip-value { color: ${COLOR.cyan}; }
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

/** Winrate -> PnlTone (profit/loss/pending). */
function winrateToneFull(raw: string | null | undefined): PnlTone {
  if (!raw) return 'neutral';
  const m = raw.match(/(-?\d+(?:\.\d+)?)/);
  if (!m) return 'neutral';
  const pct = parseFloat(m[1]);
  if (pct >= 50) return 'profit';
  if (pct > 0) return 'pending';
  return 'loss';
}

/** PnL chip — 2 satir (deger + yuzde), tone bg */
interface PnlCellProps {
  label: string;
  value: string;
  pct: string | null;
  tone: PnlTone;
  title?: string;
}
function PnlCell({ label, value, pct, tone, title }: PnlCellProps) {
  return (
    <div className={`dsp-tb-chip pnl ${tone}`} title={title}>
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
      {/* Group 1 — MONEY — Oturum PnL tarzı soft bg */}
      <div className="dsp-tb-group g-money">
        <PnlCell
          label="Bakiye"
          value={fmtMoney(overview?.bakiye_text)}
          pct={null}
          tone="neutral"
          title="Polymarket wallet USDC toplam bakiyesi"
        />
        <PnlCell
          label="Kullanılabilir"
          value={fmtMoney(overview?.kullanilabilir_text)}
          pct={null}
          tone="profit"
          title="Yeni işlem için ayrılabilir tutar (bakiye - açık emir kilitli)"
        />
        <PnlCell
          label="Oturum PnL"
          value={fmtPnlValue(pnlValue)}
          pct={fmtPnlPct(overview?.session_pnl_pct)}
          tone={pnlTone(pnlValue)}
          title="Bu oturumda kapanan pozisyonlardan toplam net kar/zarar"
        />
      </div>

      <div className="dsp-tb-divider" />

      {/* Group 2 — ACTIVITY */}
      <div className="dsp-tb-group g-activity">
        <PnlCell
          label="Açılan"
          value={fmtNum(overview?.acilan)}
          pct={null}
          tone="neutral"
          title="Bu oturumda emir dolumu ile açılan pozisyon sayısı"
        />
        <PnlCell
          label="Görülen"
          value={fmtNum(overview?.gorulen)}
          pct={null}
          tone="neutral"
          title="Bu oturumda tespit edilen uygun 5M event sayısı"
        />
        <PnlCell
          label="A/G Rate"
          value={overview?.ag_rate ?? '—'}
          pct={null}
          tone="pending"
          title="Açılan / Görülen oranı — sinyal dönüşüm hızı"
        />
      </div>

      <div className="dsp-tb-divider" />

      {/* Group 3 — OUTCOME */}
      <div className="dsp-tb-group g-outcome">
        <PnlCell
          label="Kazanan"
          value={fmtNum(overview?.win)}
          pct={null}
          tone="profit"
          title="Bu oturumda karlı kapanmış pozisyon sayısı"
        />
        <PnlCell
          label="Kaybeden"
          value={fmtNum(overview?.lost)}
          pct={null}
          tone="loss"
          title="Bu oturumda zararlı kapanmış pozisyon sayısı"
        />
        <PnlCell
          label="Bekleyen"
          value={fmtNum(overview?.pending_claims)}
          pct={null}
          tone="pending"
          title="Claim sırasında bekleyen (henüz tahsil edilmemiş) pozisyon sayısı"
        />
        <PnlCell
          label="Winrate"
          value={overview?.winrate ?? '—'}
          pct={null}
          tone={winrateToneFull(overview?.winrate)}
          title="Kazanan / (Kazanan + Kaybeden) yüzdesi"
        />
      </div>

    </div>
  );
}

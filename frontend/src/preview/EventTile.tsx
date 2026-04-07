/**
 * EventTile — 3 kolon variant container.
 *
 * Sol kolon  : kimlik + ana vurgu + (opsiyonel) aksiyon
 * Orta kolon : canli operasyon ozeti + activity satiri
 * Sag kolon  : variant'a gore teknik panel
 *               - open  -> ExitGrid (TP/SL/FS/FS PnL)
 *               - claim -> ClaimStatusPanel (status hero + retry/next + payout)
 *               - search-> RuleGrid (2x3 RuleSpec)
 *               - idle  -> IdlePanel (msg + CTA dim)
 *
 * Plan v2 madde 2: kaotik tek switch yerine kucuk local render
 * helper'lar. 4 variant icin ayri SidePanel render fonksiyonlari.
 *
 * 1. tur kompakt:
 *  - alt component'ler dosya icinde local
 *  - animasyon yok
 *  - tooltip yok (title attribute)
 *  - settings modal yok (button trigger var, tiklama no-op)
 */

import {
  COLOR,
  FONT,
  SIZE,
  PNL_TONE,
  RULE_TONE,
  ACTIVITY_TONE,
  ensureStyles,
} from './styles';
import { lookupCoin, DEFAULT_COIN_TONE, type CoinFallback } from './coinRegistry';
import type {
  PositionSummary,
  ClaimSummary,
  SearchTileContract,
  IdleTileContract,
  CoinInfoContract,
  PnlTone,
  ActivityContract,
  ClaimStatusContract,
  RuleSpecContract,
  PositionLiveContract,
  PositionExitsContract,
} from '../api/dashboard';

// ╔══════════════════════════════════════════════════════════════╗
// ║  CSS                                                         ║
// ╚══════════════════════════════════════════════════════════════╝

ensureStyles(
  'eventtile-v17',
  `
/* tile height hesabi (defensive 850 viewport, 3 section, 4 sat = 8 tile):
 *   850 - 76(topbar) - 38(strip) - 22(content pad) - 66(3 hdr) - 15(hdr gap)
 *        - 8(inner row gap) - 20(section arasi gap) = 605
 *   605 / 4 sat = 151/sat
 *   tile internal: padding 11+11 + border 2 = 24 -> tile h ~150 */
.dsp-tile {
  display: grid;
  grid-template-columns: 140px minmax(0, 1fr) 220px;
  gap: 0;
  padding: 5px 14px;
  background: ${COLOR.bgRaised};
  border: 1px solid ${COLOR.border};
  border-radius: ${SIZE.radiusLg}px;
  font-family: ${FONT.sans};
  color: ${COLOR.text};
  height: 118px;
  align-items: stretch;
  min-width: 0;
  line-height: 1.2;
}
.dsp-tile.claim { border-color: ${COLOR.brandSoft}; }
.dsp-tile.open-profit { border-left: 3px solid ${COLOR.green}; }
.dsp-tile.open-loss   { border-left: 3px solid ${COLOR.red}; }
.dsp-tile.search      { }
.dsp-tile.idle        { opacity: 0.86; }

/* SOL kolon — 3 esit satir grid:
 *  Row 1: ID box (logo + ticker)
 *  Row 2: PnL box (big rakam ortali)
 *  Row 3: Actions row (\$/⚙ 2 col)
 * Hepsi eşit yükseklikte, hizali. */
.dsp-tile-l {
  display: grid;
  grid-template-rows: 1fr 1fr 1fr;
  gap: 4px;
  min-width: 0;
  padding-right: 14px;
  border-right: 1px solid ${COLOR.border};
}
.dsp-tile-l-id {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 9px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  border-radius: ${SIZE.radius}px;
}
.dsp-tile-l-avatar {
  width: 26px; height: 26px;
  border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px;
  font-weight: ${FONT.weight.bold};
  flex-shrink: 0;
  overflow: hidden;
}
.dsp-tile-l-avatar img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  border-radius: 0;
}
.dsp-tile-l-symbol {
  font-size: 14px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.text};
  letter-spacing: 0.04em;
  line-height: 1.1;
}
/* PnL box (2. satir) — big rakam ortali, sadece bu kart */
.dsp-tile-l-pnl {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 8px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  border-radius: ${SIZE.radius}px;
}
.dsp-tile-l-big {
  font-family: ${FONT.mono};
  font-size: 16px;
  font-weight: ${FONT.weight.bold};
  line-height: 1;
  text-align: center;
}
.dsp-tile-l-amt {
  display: none;
}
/* Actions (3. satir) — 2 col grid, dolu yukseklik */
.dsp-tile-l-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
  min-height: 0;
}
.dsp-tile-l-act {
  display: flex; align-items: center; justify-content: center;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  border-radius: ${SIZE.radius}px;
  color: ${COLOR.textMuted};
  font-size: 14px;
  font-weight: ${FONT.weight.bold};
  cursor: pointer;
  font-family: ${FONT.sans};
  padding: 0;
  line-height: 1;
}
.dsp-tile-l-act:hover { color: ${COLOR.text}; background: ${COLOR.surfaceHover}; }
.dsp-tile-l-act.dollar-active { color: ${COLOR.green}; }
.dsp-tile-l-act.dollar-passive { color: ${COLOR.cyan}; }

/* ORTA kolon — sol/sag padding (divider'lara hava) */
.dsp-tile-m {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 0 14px;
  justify-content: center;
  min-width: 0;
  justify-content: center;
}
.dsp-tile-m-row {
  display: flex; gap: 12px; align-items: baseline;
  min-width: 0; flex-wrap: nowrap; overflow: hidden;
}
.dsp-tile-m-cell {
  display: flex; flex-direction: column; min-width: 0;
  flex-shrink: 1;
}
.dsp-tile-m-lbl {
  font-size: 9px;
  text-transform: uppercase;
  font-weight: ${FONT.weight.semibold};
  color: ${COLOR.textMuted};
  letter-spacing: 0.05em;
  white-space: nowrap;
}
.dsp-tile-m-val {
  font-family: ${FONT.mono};
  font-size: 13px;
  font-weight: ${FONT.weight.semibold};
  color: ${COLOR.text};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.dsp-tile-m-act {
  display: flex; gap: 8px; align-items: center;
  font-size: ${FONT.size.md};
}
.dsp-tile-m-act-dot {
  width: 7px; height: 7px; border-radius: 50%;
}

/* SAG kolon — sol dikey divider, content dikey ortali */
.dsp-tile-r {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding-left: 16px;
  border-left: 1px solid ${COLOR.border};
}

/* RuleGrid — 2 col x 3 row (kompakt sag panel icin) */
.dsp-rgrid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  width: 100%;
}
.dsp-rb {
  padding: 5px 8px;
  border-radius: ${SIZE.radius}px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  display: flex; flex-direction: column; gap: 1px;
  min-width: 0;
}
.dsp-rb-lbl {
  font-size: 9px;
  text-transform: uppercase;
  font-weight: ${FONT.weight.semibold};
  letter-spacing: 0.04em;
}
.dsp-rb-val {
  font-family: ${FONT.mono};
  font-size: ${FONT.size.md};
  font-weight: ${FONT.weight.semibold};
}

/* ExitGrid — kompakt, label/value yan yana hissi */
.dsp-eg {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
  width: 100%;
}
.dsp-eg-cell {
  padding: 4px 9px;
  border-radius: ${SIZE.radius}px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  display: flex; flex-direction: column; gap: 0;
  line-height: 1.1;
}
.dsp-eg-lbl {
  font-size: 9px;
  text-transform: uppercase;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.textMuted};
  letter-spacing: 0.06em;
  line-height: 1.1;
}
.dsp-eg-val {
  font-family: ${FONT.mono};
  font-size: 13px;
  font-weight: ${FONT.weight.bold};
  line-height: 1.15;
}
.dsp-eg-cell.tp .dsp-eg-val { color: ${COLOR.green}; }
.dsp-eg-cell.sl .dsp-eg-val { color: ${COLOR.red}; }
.dsp-eg-cell.fs .dsp-eg-val { color: ${COLOR.yellow}; }
.dsp-eg-cell.fspnl .dsp-eg-val { color: ${COLOR.red}; }

/* ClaimStatusPanel — turn 3: tone bagli + payout vurgulu */
.dsp-csp {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 5px;
  width: 100%;
}
.dsp-csp-hero {
  grid-column: 1 / -1;
  padding: 7px 12px;
  border-radius: ${SIZE.radius}px;
  display: flex; align-items: center; gap: 9px;
  /* bg + border-color inline (tone bagli) */
}
.dsp-csp-hero-dot {
  width: 9px; height: 9px; border-radius: 50%;
  flex-shrink: 0;
  /* bg + glow inline (tone bagli) */
}
.dsp-csp-hero-lbl {
  font-size: 9px; text-transform: uppercase;
  font-weight: ${FONT.weight.bold}; color: ${COLOR.textMuted};
  letter-spacing: 0.06em;
}
.dsp-csp-hero-val {
  font-family: ${FONT.mono};
  font-size: ${FONT.size.xl};
  font-weight: ${FONT.weight.bold};
  margin-left: auto;
  letter-spacing: 0.04em;
  /* color inline (tone bagli) */
}
.dsp-csp-cell {
  padding: 5px 11px;
  border-radius: ${SIZE.radius}px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  display: flex; flex-direction: column; gap: 1px;
}
.dsp-csp-cell-lbl {
  font-size: 9px; text-transform: uppercase;
  font-weight: ${FONT.weight.bold}; color: ${COLOR.textMuted};
  letter-spacing: 0.06em;
}
.dsp-csp-cell-val {
  font-family: ${FONT.mono};
  font-size: 13px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.text};
}
.dsp-csp-payout {
  grid-column: 1 / -1;
  padding: 6px 12px;
  border-radius: ${SIZE.radius}px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  display: flex; justify-content: space-between; align-items: center;
}
.dsp-csp-payout-lbl {
  font-size: 10px; text-transform: uppercase;
  font-weight: ${FONT.weight.bold}; color: ${COLOR.textMuted};
  letter-spacing: 0.06em;
}
.dsp-csp-payout-val {
  font-family: ${FONT.mono};
  font-size: 16px;
  font-weight: ${FONT.weight.bold};
  /* color inline (tone bagli) */
}
.dsp-csp.ok .dsp-csp-payout {
  background: ${COLOR.greenSoft};
  border-color: ${COLOR.greenSoft};
}
.dsp-csp.ok .dsp-csp-payout-val { color: ${COLOR.green}; }

/* IdlePanel (sag taraf) */
.dsp-ip {
  width: 100%;
  padding: 12px;
  border-radius: ${SIZE.radius}px;
  background: ${COLOR.surface};
  border: 1px dashed ${COLOR.divider};
  color: ${COLOR.textMuted};
  font-size: ${FONT.size.sm};
  text-align: center;
}
`
);

// ╔══════════════════════════════════════════════════════════════╗
// ║  Local render helpers — sol kolon                            ║
// ╚══════════════════════════════════════════════════════════════╝

function CoinAvatar({ coin }: { coin: CoinFallback }) {
  const tone = coin.tone ?? DEFAULT_COIN_TONE;
  // Gercek logo varsa img, yoksa harf fallback (CDN fail-safe)
  if (coin.logo_url) {
    return (
      <div
        className="dsp-tile-l-avatar"
        title={coin.display_name}
        style={{
          background: `${tone}14`,
          border: `1.5px solid ${tone}55`,
          padding: 3,
        }}
      >
        <img
          src={coin.logo_url}
          alt={coin.symbol}
          width={22}
          height={22}
          loading="lazy"
          onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
        />
      </div>
    );
  }
  return (
    <div
      className="dsp-tile-l-avatar"
      title={coin.display_name}
      style={{
        background: `${tone}14`,
        border: `1.5px solid ${tone}55`,
        color: tone,
      }}
    >
      {coin.symbol[0]}
    </div>
  );
}

interface SidePnlProps {
  big?: string | null;
  amount?: string | null;
  tone?: PnlTone | null;
}
function SidePnl({ big, amount, tone }: SidePnlProps) {
  const t = tone ?? 'off';
  const fg = PNL_TONE[t].fg;
  return (
    <div className="dsp-tile-l-pnl">
      <div className="dsp-tile-l-big" style={{ color: fg }}>
        {big || '—'}
      </div>
      {amount && <div className="dsp-tile-l-amt">{amount}</div>}
    </div>
  );
}

/** TileActions — sol kolon PnL kutusunun altinda 2 buton ($/⚙).
 *  Kullanici talebi: PnL ortali, altinda 2 yarim genislik buton. */
function TileActions({ dollarState }: { dollarState?: 'active' | 'passive' }) {
  const dClass = dollarState ? `dollar-${dollarState}` : '';
  return (
    <div className="dsp-tile-l-actions">
      <button
        type="button"
        className={`dsp-tile-l-act ${dClass}`}
        title={dollarState === 'active' ? 'Aramada — pasife al' : dollarState === 'passive' ? 'Pasif — aramaya al' : 'Aktif/pasif toggle'}
      >
        $
      </button>
      <button type="button" className="dsp-tile-l-act" title="Ayarlar">
        ⚙
      </button>
    </div>
  );
}

function CoinIdentityBlock({
  coin,
  big,
  amount,
  tone,
  dollarState,
}: {
  coin: CoinFallback;
  big?: string | null;
  amount?: string | null;
  tone?: PnlTone | null;
  dollarState?: 'active' | 'passive';
}) {
  return (
    <div className="dsp-tile-l">
      {/* Row 1: Logo + Ticker */}
      <div className="dsp-tile-l-id" title={coin.display_name}>
        <CoinAvatar coin={coin} />
        <span className="dsp-tile-l-symbol">{coin.symbol}</span>
      </div>
      {/* Row 2: PnL big (veya 6/6 search) */}
      <SidePnl big={big} amount={amount} tone={tone} />
      {/* Row 3: Actions \$/⚙ */}
      <TileActions dollarState={dollarState} />
    </div>
  );
}

// ╔══════════════════════════════════════════════════════════════╗
// ║  Local render helpers — orta kolon                           ║
// ╚══════════════════════════════════════════════════════════════╝

interface MidCellsProps {
  cells: Array<{ label: string; value: string }>;
}
function MidCells({ cells }: MidCellsProps) {
  return (
    <div className="dsp-tile-m-row">
      {cells.map((c) => (
        <div key={c.label} className="dsp-tile-m-cell">
          <div className="dsp-tile-m-lbl">{c.label}</div>
          <div className="dsp-tile-m-val">{c.value}</div>
        </div>
      ))}
    </div>
  );
}

function ActivityStatusLine({
  activity,
}: {
  activity?: ActivityContract | null;
}) {
  if (!activity || !activity.text) return null;
  const tone = ACTIVITY_TONE[activity.severity ?? 'info'];
  return (
    <div className="dsp-tile-m-act" style={{ color: tone.fg }}>
      <span
        className="dsp-tile-m-act-dot"
        style={{ background: tone.dot }}
      />
      <span>{activity.text}</span>
    </div>
  );
}

// ╔══════════════════════════════════════════════════════════════╗
// ║  Local render helpers — sag kolon (variant panels)           ║
// ╚══════════════════════════════════════════════════════════════╝

function RuleGrid({ rules }: { rules: RuleSpecContract[] }) {
  if (!rules || rules.length === 0) {
    return <div className="dsp-ip">Kural verisi yok</div>;
  }
  return (
    <div className="dsp-rgrid">
      {rules.map((r, i) => {
        const t = RULE_TONE[r.state];
        return (
          <div
            key={`${r.label}-${i}`}
            className="dsp-rb"
            style={{ borderColor: t.border, background: t.bg }}
            title={r.threshold_text ?? undefined}
          >
            <div className="dsp-rb-lbl" style={{ color: t.fg }}>
              {r.label}
            </div>
            <div className="dsp-rb-val" style={{ color: t.fg }}>
              {r.live_value}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ExitGrid({ exits }: { exits?: PositionExitsContract | null }) {
  if (!exits) return <div className="dsp-ip">Cikis esikleri yok</div>;
  return (
    <div className="dsp-eg">
      <div className="dsp-eg-cell tp">
        <div className="dsp-eg-lbl">TP</div>
        <div className="dsp-eg-val">{exits.tp}</div>
      </div>
      <div className="dsp-eg-cell sl">
        <div className="dsp-eg-lbl">SL</div>
        <div className="dsp-eg-val">{exits.sl}</div>
      </div>
      <div className="dsp-eg-cell fs">
        <div className="dsp-eg-lbl">FS</div>
        <div className="dsp-eg-val">{exits.fs}</div>
      </div>
      <div className="dsp-eg-cell fspnl">
        <div className="dsp-eg-lbl">FS PnL</div>
        <div className="dsp-eg-val">{exits.fs_pnl ?? '—'}</div>
      </div>
    </div>
  );
}

interface ClaimPanelProps {
  status: ClaimStatusContract | null | undefined; // RETRY/OK/FAIL
  retry: number | null | undefined;
  maxRetry: number | null | undefined;
  nextSec: number | null | undefined;
  payout: string | null | undefined;
}

/** Claim status -> tone (RETRY=yellow, OK=green, FAIL=red, null=brand). */
function claimTone(status: ClaimStatusContract | null | undefined): {
  fg: string;
  bg: string;
  glow: string;
  klass: string;
} {
  switch (status) {
    case 'OK':
      return { fg: COLOR.green, bg: COLOR.greenSoft, glow: COLOR.greenGlow, klass: 'ok' };
    case 'FAIL':
      return { fg: COLOR.red, bg: COLOR.redSoft, glow: COLOR.redGlow, klass: 'fail' };
    case 'RETRY':
      return { fg: COLOR.yellow, bg: COLOR.yellowSoft, glow: COLOR.yellowGlow, klass: 'retry' };
    default:
      return { fg: COLOR.brand, bg: COLOR.brandSoft, glow: COLOR.brandGlow, klass: 'pending' };
  }
}

function ClaimStatusPanel({
  status,
  retry,
  maxRetry,
  nextSec,
  payout,
}: ClaimPanelProps) {
  const tone = claimTone(status);
  return (
    <div className={`dsp-csp ${tone.klass}`}>
      <div
        className="dsp-csp-hero"
        style={{
          background: tone.bg,
          border: `1px solid ${tone.fg}55`,
        }}
      >
        <span
          className="dsp-csp-hero-dot"
          style={{
            background: tone.fg,
            boxShadow: `0 0 6px ${tone.fg}99`,
          }}
        />
        <span className="dsp-csp-hero-lbl">STATUS</span>
        <span className="dsp-csp-hero-val" style={{ color: tone.fg }}>
          {status ?? '—'}
        </span>
      </div>
      <div className="dsp-csp-cell">
        <div className="dsp-csp-cell-lbl">Retry</div>
        <div className="dsp-csp-cell-val">
          {retry != null ? `${retry}/${maxRetry ?? '?'}` : '—'}
        </div>
      </div>
      <div className="dsp-csp-cell">
        <div className="dsp-csp-cell-lbl">Next</div>
        <div className="dsp-csp-cell-val">
          {nextSec != null ? `${nextSec}s` : '—'}
        </div>
      </div>
      <div className="dsp-csp-payout">
        <span className="dsp-csp-payout-lbl">Payout</span>
        <span
          className="dsp-csp-payout-val"
          style={{
            color: status === 'OK' ? COLOR.green : COLOR.text,
          }}
        >
          {payout ?? '—'}
        </span>
      </div>
    </div>
  );
}

function IdlePanel({ msg }: { msg: string }) {
  return <div className="dsp-ip">{msg}</div>;
}

// ╔══════════════════════════════════════════════════════════════╗
// ║  Variant body renderers (orta kolon, variant'a gore)         ║
// ╚══════════════════════════════════════════════════════════════╝

function OpenBody({
  live,
  activity,
}: {
  live?: PositionLiveContract | null;
  activity?: ActivityContract | null;
}) {
  const cells = live
    ? [
        { label: 'Giriş', value: `${live.side === 'UP' ? '▲' : '▼'} ${live.entry}` },
        { label: 'Canlı', value: live.live },
        { label: 'Delta', value: live.delta_text ?? '—' },
      ]
    : [];
  return (
    <div className="dsp-tile-m">
      {cells.length > 0 && <MidCells cells={cells} />}
      <ActivityStatusLine activity={activity} />
    </div>
  );
}

function ClaimBody({
  position,
  activity,
}: {
  position: PositionSummary;
  activity?: ActivityContract | null;
}) {
  // Q3=a karari: KAPANIS -> OUTCOME -> ENTRY
  const closeReason = position.close_reason ?? '—';
  // Outcome: legacy alanlardan turetilemez, claim summary'den lookup edilirse
  // dolu gelir; su an yoksa close_reason'dan turetelim (basit map)
  const outcome = position.net_realized_pnl > 0
    ? 'WIN'
    : position.net_realized_pnl < 0
    ? 'LOSS'
    : closeReason === 'expiry' ? 'PENDING' : '—';
  const entry = position.fill_price.toFixed(2);

  return (
    <div className="dsp-tile-m">
      <MidCells
        cells={[
          { label: 'Kapanış', value: closeReason.toUpperCase() },
          { label: 'Outcome', value: outcome },
          { label: 'Entry', value: entry },
        ]}
      />
      <ActivityStatusLine activity={activity} />
    </div>
  );
}

function SearchBody({
  ptb,
  live,
  delta,
  activity,
}: {
  ptb: string;
  live: string;
  delta: string;
  activity?: ActivityContract | null;
}) {
  return (
    <div className="dsp-tile-m">
      <MidCells
        cells={[
          { label: 'PTB', value: ptb },
          { label: 'Live', value: live },
          { label: 'Delta', value: delta },
        ]}
      />
      <ActivityStatusLine activity={activity} />
    </div>
  );
}

function IdleBody({ msg, activity }: { msg: string; activity?: ActivityContract | null }) {
  return (
    <div className="dsp-tile-m">
      <div className="dsp-tile-m-row">
        <div className="dsp-tile-m-cell">
          <div className="dsp-tile-m-val" style={{ color: COLOR.textMuted }}>
            {msg}
          </div>
        </div>
      </div>
      <ActivityStatusLine activity={activity} />
    </div>
  );
}

// ╔══════════════════════════════════════════════════════════════╗
// ║  Variant tile components (4 ayri small fn)                   ║
// ╚══════════════════════════════════════════════════════════════╝

function OpenTile({
  position,
  coins,
}: {
  position: PositionSummary;
  coins: CoinInfoContract[] | null;
}) {
  const coin = lookupCoin(position.asset, coins);
  const tone = position.pnl_tone ?? null;
  const klass =
    tone === 'profit'
      ? 'dsp-tile open-profit'
      : tone === 'loss'
      ? 'dsp-tile open-loss'
      : 'dsp-tile';
  return (
    <div className={klass}>
      <CoinIdentityBlock
        coin={coin}
        big={position.pnl_big ?? null}
        amount={position.pnl_amount ?? null}
        tone={tone}
      />
      <OpenBody live={position.live} activity={position.activity} />
      <div className="dsp-tile-r">
        <ExitGrid exits={position.exits} />
      </div>
    </div>
  );
}

function ClaimTile({
  position,
  coins,
  claims,
}: {
  position: PositionSummary;
  coins: CoinInfoContract[] | null;
  claims: ClaimSummary[] | null;
}) {
  const coin = lookupCoin(position.asset, coins);
  // turn 3: claims listesinden lookup (position_id eslesmesi)
  const claim = claims?.find((c) => c.position_id === position.position_id);
  return (
    <div className="dsp-tile claim">
      <CoinIdentityBlock
        coin={coin}
        big={position.pnl_big ?? 'CLAIM'}
        amount={position.pnl_amount ?? 'PENDING'}
        tone={position.pnl_tone ?? 'pending'}
      />
      <ClaimBody position={position} activity={position.activity} />
      <div className="dsp-tile-r">
        <ClaimStatusPanel
          status={claim?.status ?? null}
          retry={claim?.retry ?? null}
          maxRetry={claim?.max_retry ?? null}
          nextSec={claim?.next_sec ?? null}
          payout={claim?.payout ?? null}
        />
      </div>
    </div>
  );
}

function SearchTile({
  tile,
  coins,
}: {
  tile: SearchTileContract;
  coins: CoinInfoContract[] | null;
}) {
  const coin = lookupCoin(tile.coin, coins);
  return (
    <div className="dsp-tile search">
      <CoinIdentityBlock
        coin={coin}
        big={tile.pnl_big}
        amount={tile.pnl_amount ?? null}
        tone={tile.pnl_tone}
        dollarState="active"
      />
      <SearchBody
        ptb={tile.ptb}
        live={tile.live}
        delta={tile.delta}
        activity={tile.activity}
      />
      <div className="dsp-tile-r">
        <RuleGrid rules={tile.rules} />
      </div>
    </div>
  );
}

function IdleTile({
  tile,
  coins,
}: {
  tile: IdleTileContract;
  coins: CoinInfoContract[] | null;
}) {
  const coin = lookupCoin(tile.coin ?? '?', coins);
  return (
    <div className="dsp-tile idle">
      <CoinIdentityBlock
        coin={coin}
        big="OFF"
        amount={null}
        tone="off"
        dollarState="passive"
      />
      <IdleBody msg={tile.msg} activity={tile.activity} />
      <div className="dsp-tile-r">
        {tile.rules && tile.rules.length > 0 ? (
          <RuleGrid rules={tile.rules} />
        ) : (
          <IdlePanel msg={`Kategori: ${tile.idle_kind}`} />
        )}
      </div>
    </div>
  );
}

// ╔══════════════════════════════════════════════════════════════╗
// ║  Public EventTile — variant container                        ║
// ╚══════════════════════════════════════════════════════════════╝

export type EventTileVariant = 'open' | 'claim' | 'search' | 'idle';

export interface EventTileProps {
  variant: EventTileVariant;
  /** open + claim variant icin */
  position?: PositionSummary;
  /** search variant icin */
  search?: SearchTileContract;
  /** idle variant icin */
  idle?: IdleTileContract;
  /** coin metadata lookup icin */
  coins: CoinInfoContract[] | null;
  /** claim variant icin claim status lookup (position_id eslesmesi) */
  claims?: ClaimSummary[] | null;
}

export default function EventTile(props: EventTileProps) {
  switch (props.variant) {
    case 'open':
      if (!props.position) return null;
      return <OpenTile position={props.position} coins={props.coins} />;
    case 'claim':
      if (!props.position) return null;
      return (
        <ClaimTile
          position={props.position}
          coins={props.coins}
          claims={props.claims ?? null}
        />
      );
    case 'search':
      if (!props.search) return null;
      return <SearchTile tile={props.search} coins={props.coins} />;
    case 'idle':
      if (!props.idle) return null;
      return <IdleTile tile={props.idle} coins={props.coins} />;
    default:
      return null;
  }
}

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
import { lookupCoin, type CoinFallback } from './coinRegistry';
import type {
  PositionSummary,
  SearchTileContract,
  IdleTileContract,
  CoinInfoContract,
  PnlTone,
  ActivityContract,
  RuleSpecContract,
  PositionLiveContract,
  PositionExitsContract,
} from '../api/dashboard';

// ╔══════════════════════════════════════════════════════════════╗
// ║  CSS                                                         ║
// ╚══════════════════════════════════════════════════════════════╝

ensureStyles(
  'eventtile',
  `
.dsp-tile {
  display: grid;
  grid-template-columns: 240px 1fr 380px;
  gap: 16px;
  padding: 14px 18px;
  background: ${COLOR.bgRaised};
  border: 1px solid ${COLOR.border};
  border-radius: ${SIZE.radiusLg}px;
  font-family: ${FONT.sans};
  color: ${COLOR.text};
  min-height: ${SIZE.tileMinHeight}px;
}
.dsp-tile.claim { border-color: ${COLOR.brandSoft}; }
.dsp-tile.open-profit { border-left: 3px solid ${COLOR.green}; }
.dsp-tile.open-loss   { border-left: 3px solid ${COLOR.red}; }
.dsp-tile.search      { }
.dsp-tile.idle        { opacity: 0.86; }

/* SOL kolon */
.dsp-tile-l {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.dsp-tile-l-id {
  display: flex;
  align-items: center;
  gap: 8px;
}
.dsp-tile-l-avatar {
  width: 28px; height: 28px;
  border-radius: 50%;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.border};
  display: flex; align-items: center; justify-content: center;
  font-size: ${FONT.size.md};
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.text};
}
.dsp-tile-l-name {
  display: flex; flex-direction: column; min-width: 0;
}
.dsp-tile-l-symbol {
  font-size: ${FONT.size.lg};
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.text};
}
.dsp-tile-l-display {
  font-size: ${FONT.size.xs};
  color: ${COLOR.textMuted};
  font-weight: ${FONT.weight.medium};
}
.dsp-tile-l-pnl {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 2px;
}
.dsp-tile-l-big {
  font-family: ${FONT.mono};
  font-size: ${FONT.size.huge};
  font-weight: ${FONT.weight.bold};
  line-height: 1.1;
}
.dsp-tile-l-amt {
  font-family: ${FONT.mono};
  font-size: ${FONT.size.md};
  color: ${COLOR.textMuted};
}
.dsp-tile-l-actions {
  display: flex; gap: 6px; margin-top: 4px;
}
.dsp-tile-l-act {
  width: 26px; height: 26px;
  display: flex; align-items: center; justify-content: center;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.border};
  border-radius: ${SIZE.radius}px;
  color: ${COLOR.textMuted};
  font-size: ${FONT.size.md};
  cursor: pointer;
  font-family: ${FONT.sans};
}
.dsp-tile-l-act:hover { color: ${COLOR.text}; background: ${COLOR.surfaceHover}; }
.dsp-tile-l-act.dollar-active { color: ${COLOR.green}; }
.dsp-tile-l-act.dollar-passive { color: ${COLOR.cyan}; }

/* ORTA kolon */
.dsp-tile-m {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
  justify-content: center;
}
.dsp-tile-m-row {
  display: flex; gap: 18px; align-items: baseline;
  min-width: 0; flex-wrap: wrap;
}
.dsp-tile-m-cell {
  display: flex; flex-direction: column; min-width: 0;
}
.dsp-tile-m-lbl {
  font-size: 9px;
  text-transform: uppercase;
  font-weight: ${FONT.weight.semibold};
  color: ${COLOR.textMuted};
  letter-spacing: 0.05em;
}
.dsp-tile-m-val {
  font-family: ${FONT.mono};
  font-size: ${FONT.size.lg};
  font-weight: ${FONT.weight.semibold};
  color: ${COLOR.text};
}
.dsp-tile-m-act {
  display: flex; gap: 8px; align-items: center;
  font-size: ${FONT.size.md};
}
.dsp-tile-m-act-dot {
  width: 7px; height: 7px; border-radius: 50%;
}

/* SAG kolon */
.dsp-tile-r {
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

/* RuleGrid */
.dsp-rgrid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
  width: 100%;
}
.dsp-rb {
  padding: 6px 8px;
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

/* ExitGrid */
.dsp-eg {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  width: 100%;
}
.dsp-eg-cell {
  padding: 8px 10px;
  border-radius: ${SIZE.radius}px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  display: flex; flex-direction: column; gap: 2px;
}
.dsp-eg-lbl {
  font-size: 9px;
  text-transform: uppercase;
  font-weight: ${FONT.weight.semibold};
  color: ${COLOR.textMuted};
  letter-spacing: 0.05em;
}
.dsp-eg-val {
  font-family: ${FONT.mono};
  font-size: ${FONT.size.lg};
  font-weight: ${FONT.weight.bold};
}
.dsp-eg-cell.tp .dsp-eg-val { color: ${COLOR.green}; }
.dsp-eg-cell.sl .dsp-eg-val { color: ${COLOR.red}; }
.dsp-eg-cell.fs .dsp-eg-val { color: ${COLOR.yellow}; }
.dsp-eg-cell.fspnl .dsp-eg-val { color: ${COLOR.red}; }

/* ClaimStatusPanel */
.dsp-csp {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  width: 100%;
}
.dsp-csp-hero {
  grid-column: 1 / -1;
  padding: 8px 10px;
  border-radius: ${SIZE.radius}px;
  background: ${COLOR.brandSoft};
  border: 1px solid ${COLOR.borderStrong};
  display: flex; align-items: center; gap: 8px;
}
.dsp-csp-hero-dot { width: 8px; height: 8px; border-radius: 50%; background: ${COLOR.brand}; }
.dsp-csp-hero-lbl {
  font-size: 9px; text-transform: uppercase;
  font-weight: ${FONT.weight.semibold}; color: ${COLOR.textMuted};
  letter-spacing: 0.05em;
}
.dsp-csp-hero-val {
  font-family: ${FONT.mono};
  font-size: ${FONT.size.lg};
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.brand};
  margin-left: auto;
}
.dsp-csp-cell {
  padding: 6px 10px;
  border-radius: ${SIZE.radius}px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  display: flex; flex-direction: column; gap: 1px;
}
.dsp-csp-cell-lbl {
  font-size: 9px; text-transform: uppercase;
  font-weight: ${FONT.weight.semibold}; color: ${COLOR.textMuted};
  letter-spacing: 0.05em;
}
.dsp-csp-cell-val {
  font-family: ${FONT.mono};
  font-size: ${FONT.size.md};
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.text};
}
.dsp-csp-payout {
  grid-column: 1 / -1;
  padding: 8px 10px;
  border-radius: ${SIZE.radius}px;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  display: flex; justify-content: space-between; align-items: center;
}

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
  // 1. tur: harf avatari (logo_url ile asset bazli render sonraki tur)
  return (
    <div className="dsp-tile-l-avatar" title={coin.display_name}>
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
  if (!big && !amount) return null;
  const t = tone ?? 'off';
  const fg = PNL_TONE[t].fg;
  return (
    <div className="dsp-tile-l-pnl">
      {big && <div className="dsp-tile-l-big" style={{ color: fg }}>{big}</div>}
      {amount && <div className="dsp-tile-l-amt">{amount}</div>}
    </div>
  );
}

interface TileActionsProps {
  /** $ toggle current state — 'active' (search) | 'passive' (idle) | undefined (show only) */
  dollarState?: 'active' | 'passive';
  showSettings?: boolean;
}
function TileActions({ dollarState, showSettings = true }: TileActionsProps) {
  return (
    <div className="dsp-tile-l-actions">
      {dollarState && (
        <button
          type="button"
          className={`dsp-tile-l-act dollar-${dollarState}`}
          title={dollarState === 'active' ? 'Aramada — pasife al' : 'Pasif — aramaya al'}
        >
          $
        </button>
      )}
      {showSettings && (
        <button type="button" className="dsp-tile-l-act" title="Ayarlar">
          ⚙
        </button>
      )}
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
      <div className="dsp-tile-l-id">
        <CoinAvatar coin={coin} />
        <div className="dsp-tile-l-name">
          <div className="dsp-tile-l-symbol">{coin.symbol}</div>
          <div className="dsp-tile-l-display">{coin.display_name}</div>
        </div>
      </div>
      <SidePnl big={big} amount={amount} tone={tone} />
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
  status: string | null | undefined; // RETRY/OK/FAIL
  retry: number | null | undefined;
  maxRetry: number | null | undefined;
  nextSec: number | null | undefined;
  payout: string | null | undefined;
}
function ClaimStatusPanel({
  status,
  retry,
  maxRetry,
  nextSec,
  payout,
}: ClaimPanelProps) {
  return (
    <div className="dsp-csp">
      <div className="dsp-csp-hero">
        <span className="dsp-csp-hero-dot" />
        <span className="dsp-csp-hero-lbl">STATUS</span>
        <span className="dsp-csp-hero-val">{status ?? '—'}</span>
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
        <span className="dsp-csp-cell-lbl">Payout</span>
        <span className="dsp-csp-cell-val">{payout ?? '—'}</span>
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

function ClaimBody({ activity }: { activity?: ActivityContract | null }) {
  return (
    <div className="dsp-tile-m">
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
}: {
  position: PositionSummary;
  coins: CoinInfoContract[] | null;
}) {
  const coin = lookupCoin(position.asset, coins);
  return (
    <div className="dsp-tile claim">
      <CoinIdentityBlock
        coin={coin}
        big="CLAIM"
        amount="PENDING"
        tone="pending"
      />
      <ClaimBody activity={position.activity} />
      <div className="dsp-tile-r">
        <ClaimStatusPanel
          status={null /* legacy claim_summary linkage henuz yok */}
          retry={null}
          maxRetry={null}
          nextSec={null}
          payout={null}
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
  coins: CoinInfoContract[] | null;
}

export default function EventTile(props: EventTileProps) {
  switch (props.variant) {
    case 'open':
      if (!props.position) return null;
      return <OpenTile position={props.position} coins={props.coins} />;
    case 'claim':
      if (!props.position) return null;
      return <ClaimTile position={props.position} coins={props.coins} />;
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

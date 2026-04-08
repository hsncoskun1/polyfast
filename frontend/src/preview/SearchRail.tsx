/**
 * SearchRail — OpenRail kardeş paneli, "İşlem Aranan" tile'larını
 * OpenCard ile aynı grid yapısında gösterir.
 *
 *   [logo | ticker+$+⚙]        [Rule Pass hero] / [pnl_amount label] / [SAT]
 *   [    3-col cells (PTB / Canlı / Delta)           ]
 *   [    4-col rules (Zaman / Fiyat / Delta / Spread)]
 */

import { COLOR, FONT, SIZE, PNL_TONE, RULE_TONE, ensureStyles } from './styles';
import { COIN_FALLBACK } from './coinRegistry';
import type { SearchTileContract, RuleSpecContract } from '../api/dashboard';

ensureStyles(
  'searchrail-v1',
  `
.dsp-srail-list {
  display: grid;
  grid-template-rows: repeat(6, 1fr);
  gap: 6px;
  flex: 1;
  min-height: 0;
}
.dsp-scard {
  min-height: 0;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  border-left-width: 3px;
  border-left-color: ${COLOR.cyan};
  border-radius: ${SIZE.radius}px;
  padding: 10px 12px;
  display: grid;
  grid-template-columns: 1fr auto;
  grid-template-rows: auto auto auto;
  column-gap: 10px;
  row-gap: 2px;
  min-width: 0;
  overflow: hidden;
}
.dsp-scard.ready { border-left-color: ${COLOR.green}; }
.dsp-scard.wait  { border-left-color: ${COLOR.yellow}; }
.dsp-scard.block { border-left-color: ${COLOR.red}; }

/* Row 1 — id (logo + ticker + Tutar/Değer) */
.dsp-scard-id {
  grid-column: 1;
  grid-row: 1;
  display: grid;
  grid-template-columns: auto 1fr;
  grid-template-rows: auto auto auto;
  column-gap: 10px;
  row-gap: 3px;
  min-width: 0;
  align-content: start;
}
.dsp-scard-id > .dsp-scard-logo { grid-column: 1; grid-row: 1 / span 3; align-self: center; }
.dsp-scard-id-row { grid-column: 2; grid-row: 1; line-height: 1.1; display: flex; align-items: center; gap: 10px; }
.dsp-scard-id-lbl { grid-column: 2; grid-row: 2; line-height: 1.1; margin-top: 1px; font-size: 11px; text-transform: uppercase; font-weight: ${FONT.weight.bold}; letter-spacing: 0.06em; color: ${COLOR.textMuted}; }
.dsp-scard-id-val { grid-column: 2; grid-row: 3; line-height: 1.1; font-family: ${FONT.mono}; font-size: 17px; font-weight: ${FONT.weight.bold}; color: ${COLOR.cyan}; }

.dsp-scard-logo {
  width: 32px; height: 32px;
  border-radius: 50%;
  background: ${COLOR.bg};
  display: flex; align-items: center; justify-content: center;
  overflow: hidden;
  flex-shrink: 0;
}
.dsp-scard-logo img { width: 124%; height: 124%; object-fit: contain; }

.dsp-scard-ticker {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 20px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.text};
  letter-spacing: 0.02em;
  text-decoration: none;
  cursor: pointer;
}
.dsp-scard-ticker:hover { color: ${COLOR.cyan}; }
.dsp-scard-ticker-ico { font-size: 13px; opacity: 0.75; line-height: 1; }

.dsp-scard-icbtn {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  border: none;
  background: ${COLOR.yellowSoft};
  color: ${COLOR.yellow};
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 13px;
  font-weight: ${FONT.weight.bold};
  flex-shrink: 0;
  font-family: ${FONT.sans};
  line-height: 1;
  padding: 0;
}
.dsp-scard-icbtn.dollar { background: ${COLOR.greenSoft}; color: ${COLOR.green}; }
.dsp-scard-icbtn:hover { filter: brightness(1.25); }

/* Row 1 col 2 — pnl hero (Rule pass 6/6) + status label */
.dsp-scard-pnl {
  grid-column: 2;
  grid-row: 1;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  align-items: flex-end;
  gap: 3px;
  min-width: 0;
}
.dsp-scard-pct {
  font-family: ${FONT.mono};
  font-size: 24px;
  font-weight: ${FONT.weight.bold};
  line-height: 1.05;
  letter-spacing: -0.02em;
}
.dsp-scard-usd {
  font-family: ${FONT.mono};
  font-size: 13px;
  font-weight: ${FONT.weight.bold};
  text-transform: uppercase;
  letter-spacing: 0.04em;
  line-height: 1.1;
}

/* Row 2 — cells (PTB / Canlı / Delta) */
.dsp-scard-cells {
  grid-column: 1 / -1;
  grid-row: 2;
  margin-top: 4px;
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 4px;
}
.dsp-scard-cell {
  background: ${COLOR.bg};
  border: 1px solid ${COLOR.divider};
  border-radius: 7px;
  padding: 6px 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  min-width: 0;
}
.dsp-scard-cell-lbl {
  font-size: 10px;
  text-transform: uppercase;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.textMuted};
  letter-spacing: 0.05em;
  flex-shrink: 0;
}
.dsp-scard-cell-val {
  font-family: ${FONT.mono};
  font-size: 17px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.text};
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
  text-align: right;
  line-height: 1.2;
}

/* Row 3 — rules (Zaman/Fiyat/Delta/Spread) */
.dsp-scard-rules {
  grid-column: 1 / -1;
  grid-row: 3;
  margin-top: 6px;
  display: grid;
  grid-template-columns: 1fr 1fr 1fr 1fr;
  gap: 4px;
}
.dsp-scard-rule {
  background: ${COLOR.bg};
  border: 1px solid ${COLOR.divider};
  border-radius: 7px;
  padding: 11px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  min-width: 0;
  font-family: ${FONT.mono};
  font-size: 17px;
}
.dsp-scard-rule-lbl {
  font-size: 12px;
  text-transform: uppercase;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.textMuted};
  letter-spacing: 0.05em;
}
.dsp-scard-rule-val { font-weight: ${FONT.weight.bold}; }
.dsp-scard-rule.pass { background: ${COLOR.greenSoft}; border-color: ${COLOR.greenSoft}; }
.dsp-scard-rule.pass .dsp-scard-rule-val, .dsp-scard-rule.pass .dsp-scard-rule-lbl { color: ${COLOR.green}; }
.dsp-scard-rule.fail { background: ${COLOR.redSoft}; border-color: ${COLOR.redSoft}; }
.dsp-scard-rule.fail .dsp-scard-rule-val, .dsp-scard-rule.fail .dsp-scard-rule-lbl { color: ${COLOR.red}; }
.dsp-scard-rule.disabled { opacity: 0.5; }
`
);

const PICK_RULES = ['Zaman', 'Fiyat', 'Delta', 'Spread'];

function pickRule(rules: RuleSpecContract[], label: string): RuleSpecContract | undefined {
  return rules.find((r) => r.label.toLowerCase() === label.toLowerCase());
}

function SearchCard({ tile }: { tile: SearchTileContract }) {
  const coin = COIN_FALLBACK[tile.coin];
  const tone = tile.pnl_tone ?? 'neutral';
  const pnlFg = PNL_TONE[tone]?.fg ?? COLOR.text;
  const coinTone = coin?.tone;
  const bgStyle = coinTone
    ? { background: `linear-gradient(135deg, ${coinTone}1f 0%, ${COLOR.surface} 55%)` }
    : undefined;
  const klass = tile.signal_ready
    ? 'ready'
    : tile.type === 'wait'
      ? 'wait'
      : tile.pnl_tone === 'loss'
        ? 'block'
        : '';

  return (
    <div className={`dsp-scard ${klass}`} style={bgStyle}>
      <div className="dsp-scard-id">
        <div className="dsp-scard-logo">
          {coin?.logo_url ? <img src={coin.logo_url} alt={tile.coin} /> : null}
        </div>
        <div className="dsp-scard-id-row">
          <a
            className="dsp-scard-ticker"
            href={tile.event_url ?? '#'}
            target="_blank"
            rel="noopener noreferrer"
            title={`${tile.coin} Polymarket event'i aç`}
          >
            <span>{tile.coin}</span>
            <span className="dsp-scard-ticker-ico">↗</span>
          </a>
          <button type="button" className="dsp-scard-icbtn dollar" title="Aktif" aria-label="Aktif">$</button>
          <button type="button" className="dsp-scard-icbtn" title="Ayarlar" aria-label="Ayarlar">⚙</button>
        </div>
        <div className="dsp-scard-id-lbl">Durum</div>
        <div className="dsp-scard-id-val" style={{ color: pnlFg }}>
          {tile.pnl_amount ?? '—'}
        </div>
      </div>

      <div className="dsp-scard-pnl">
        <span className="dsp-scard-pct" style={{ color: pnlFg }}>
          {tile.pnl_big ?? '—'}
        </span>
      </div>

      <div className="dsp-scard-cells">
        <div className="dsp-scard-cell">
          <span className="dsp-scard-cell-lbl">PTB</span>
          <span className="dsp-scard-cell-val" style={{ color: COLOR.yellow }}>{tile.ptb}</span>
        </div>
        <div className="dsp-scard-cell">
          <span className="dsp-scard-cell-lbl">Canlı</span>
          <span className="dsp-scard-cell-val">{tile.live}</span>
        </div>
        <div className="dsp-scard-cell">
          <span className="dsp-scard-cell-lbl">Δ</span>
          <span className="dsp-scard-cell-val">{tile.delta}</span>
        </div>
      </div>

      <div className="dsp-scard-rules">
        {PICK_RULES.map((lbl) => {
          const rule = pickRule(tile.rules, lbl);
          if (!rule) return <div key={lbl} className="dsp-scard-rule disabled"><span className="dsp-scard-rule-lbl">{lbl}</span><span className="dsp-scard-rule-val">—</span></div>;
          const tt = RULE_TONE[rule.state];
          void tt;
          const stateKlass = rule.state === 'pass' ? 'pass' : rule.state === 'fail' ? 'fail' : 'disabled';
          return (
            <div key={lbl} className={`dsp-scard-rule ${stateKlass}`}>
              <span className="dsp-scard-rule-lbl">{lbl.slice(0, 3).toUpperCase()}</span>
              <span className="dsp-scard-rule-val">{rule.live_value}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function SearchRail({ tiles }: { tiles: SearchTileContract[] }) {
  return (
    <div className="dsp-srail-list">
      {tiles.map((t) => (
        <SearchCard key={t.tile_id} tile={t} />
      ))}
    </div>
  );
}

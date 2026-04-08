/**
 * NotifRail — sağ yan panel, bildirim kartları.
 *
 * Sol sidebar gibi sabit genişlikli dikey kolon. İçinde coin logosu,
 * ticker ve olay metni olan bağımsız kartlar. Her kart severity
 * rengiyle sol-bordür. Scroll'lu, en yeni üstte.
 *
 * Veri: şimdilik mock (15 kart). İleride backend feed'e bağlanır.
 */

import { COLOR, FONT, SIZE, ensureStyles } from './styles';
import { COIN_FALLBACK } from './coinRegistry';

// ─── Types ───
export type NotifSeverity = 'success' | 'warning' | 'error' | 'info' | 'pending';

export interface NotifItem {
  id: string;
  coin: string; // ticker (BTC, ETH, …)
  text: string;
  time: string; // '2s', '18s', '1m', '4m' — relatif
  severity: NotifSeverity;
}

// ─── CSS ───
ensureStyles(
  'notifrail-v4',
  `
.dsp-nrail {
  width: 280px;
  flex-shrink: 0;
  background: ${COLOR.bg};
  border-left: 1px solid ${COLOR.border};
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.dsp-nrail-hdr {
  padding: 12px 14px 10px;
  border-bottom: 1px solid ${COLOR.border};
  display: flex;
  align-items: center;
  gap: 8px;
}
.dsp-nrail-hdr-title {
  font-size: 11px;
  font-weight: ${FONT.weight.bold};
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: ${COLOR.textMuted};
}
.dsp-nrail-hdr-badge {
  font-family: ${FONT.mono};
  font-size: 10px;
  font-weight: ${FONT.weight.bold};
  padding: 1px 7px;
  border-radius: 9px;
  background: ${COLOR.brandSoft};
  color: ${COLOR.brand};
  border: 1px solid ${COLOR.brandSoft};
}
.dsp-nrail-list {
  flex: 1;
  overflow: hidden;
  padding: 8px 10px 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.dsp-nrail-group {
  flex: 1 1 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* Kart — coin logosu + ticker + metin, severity sol-bordür */
.dsp-ncard {
  flex: 1 1 0;
  min-height: 0;
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  border-left-width: 3px;
  border-radius: ${SIZE.radius}px;
  padding: 6px 10px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 3px;
  min-width: 0;
  overflow: hidden;
}
.dsp-ncard.sev-success { border-left-color: ${COLOR.green}; }
.dsp-ncard.sev-warning { border-left-color: ${COLOR.yellow}; }
.dsp-ncard.sev-error   { border-left-color: ${COLOR.red}; }
.dsp-ncard.sev-info    { border-left-color: ${COLOR.brand}; }
.dsp-ncard.sev-pending { border-left-color: ${COLOR.yellow}; }

.dsp-ncard-row {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}
.dsp-ncard-logo {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: ${COLOR.bg};
  flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  overflow: hidden;
}
.dsp-ncard-logo img { width: 124%; height: 124%; object-fit: contain; }
.dsp-ncard-ticker {
  font-size: 12px;
  font-weight: ${FONT.weight.bold};
  color: ${COLOR.text};
  letter-spacing: 0.03em;
}
.dsp-ncard-time {
  margin-left: auto;
  font-family: ${FONT.mono};
  font-size: 10px;
  color: ${COLOR.textMuted};
  flex-shrink: 0;
}
.dsp-ncard-text {
  font-size: 11px;
  font-weight: ${FONT.weight.semibold};
  line-height: 1.35;
  color: ${COLOR.text};
  word-break: break-word;
}
.dsp-ncard.sev-success .dsp-ncard-text { color: ${COLOR.green}; }
.dsp-ncard.sev-warning .dsp-ncard-text { color: ${COLOR.yellow}; }
.dsp-ncard.sev-error   .dsp-ncard-text { color: ${COLOR.red}; }
.dsp-ncard.sev-info    .dsp-ncard-text { color: ${COLOR.text}; }
.dsp-ncard.sev-pending .dsp-ncard-text { color: ${COLOR.yellow}; }
`
);

// ─── Mock — coin başına 2 bildirim (her open kartın yanına 2 notif) ───
export const MOCK_NOTIFS: NotifItem[] = [
  // BTC
  { id: 'n-btc-1', coin: 'BTC', text: 'Yeni işlem açıldı | UP 68', time: '2s', severity: 'success' },
  { id: 'n-btc-2', coin: 'BTC', text: 'Emir doldu | TP hedef 74', time: '4s', severity: 'info' },
  // ETH
  { id: 'n-eth-1', coin: 'ETH', text: 'TP yaklaşıyor | hedef 87', time: '12s', severity: 'success' },
  { id: 'n-eth-2', coin: 'ETH', text: 'Delta +2.6 | +0.31$', time: '18s', severity: 'success' },
  // AVAX
  { id: 'n-avax-1', coin: 'AVAX', text: 'TP @ 88 | +1.34$', time: '24s', severity: 'success' },
  { id: 'n-avax-2', coin: 'AVAX', text: 'Kapatma emri gönderildi', time: '26s', severity: 'info' },
  // SOL
  { id: 'n-sol-1', coin: 'SOL', text: 'SL yaklaşıyor | Limit 52', time: '34s', severity: 'warning' },
  { id: 'n-sol-2', coin: 'SOL', text: 'Delta -2.2 | -0.18$', time: '38s', severity: 'warning' },
  // DOGE
  { id: 'n-doge-1', coin: 'DOGE', text: 'SL tetiklendi | -0.24$', time: '45s', severity: 'error' },
  { id: 'n-doge-2', coin: 'DOGE', text: 'Satış emri gönderildi', time: '48s', severity: 'error' },
  // LINK
  { id: 'n-link-1', coin: 'LINK', text: 'Force sell countdown | 8s', time: '1m', severity: 'pending' },
  { id: 'n-link-2', coin: 'LINK', text: 'FS eşik -5% yakın', time: '1m', severity: 'pending' },
];

// ─── Component ───
function NotifCard({ item }: { item: NotifItem }) {
  const coin = COIN_FALLBACK[item.coin];
  return (
    <div className={`dsp-ncard sev-${item.severity}`}>
      <div className="dsp-ncard-row">
        <div className="dsp-ncard-logo">
          {coin?.logo_url ? <img src={coin.logo_url} alt={item.coin} /> : null}
        </div>
        <span className="dsp-ncard-ticker">{item.coin}</span>
        <span className="dsp-ncard-time">{item.time}</span>
      </div>
      <div className="dsp-ncard-text">{item.text}</div>
    </div>
  );
}

/** Coin listesine göre group'lar — her coin için 2 bildirim, 6 grup = 12 kart. */
export default function NotifRail({
  items = MOCK_NOTIFS,
  coins,
}: {
  items?: NotifItem[];
  /** OpenRail ile aynı sıra: her coin için 2 bildirim yan yana basılır. */
  coins?: string[];
}) {
  const groupKeys = coins && coins.length ? coins.slice(0, 6) : Array.from(new Set(items.map((i) => i.coin))).slice(0, 6);
  const groups = groupKeys.map((c) => ({
    coin: c,
    notifs: items.filter((i) => i.coin === c).slice(0, 2),
  }));
  const total = groups.reduce((s, g) => s + g.notifs.length, 0);
  return (
    <aside className="dsp-nrail">
      <div className="dsp-nrail-hdr">
        <span className="dsp-nrail-hdr-title">Bildirimler</span>
        <span className="dsp-nrail-hdr-badge">{total}</span>
      </div>
      <div className="dsp-nrail-list">
        {groups.map((g) => (
          <div key={g.coin} className="dsp-nrail-group">
            {g.notifs.map((n) => (
              <NotifCard key={n.id} item={n} />
            ))}
          </div>
        ))}
      </div>
    </aside>
  );
}

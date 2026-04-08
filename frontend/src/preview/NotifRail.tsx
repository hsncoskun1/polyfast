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
  'notifrail-v2',
  `
.dsp-nrail {
  width: 260px;
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
  overflow-y: auto;
  padding: 10px 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* Kart — coin logosu + ticker + metin, severity sol-bordür */
.dsp-ncard {
  background: ${COLOR.surface};
  border: 1px solid ${COLOR.divider};
  border-left-width: 3px;
  border-radius: ${SIZE.radius}px;
  padding: 8px 10px 9px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
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

// ─── Mock 15 bildirim ───
export const MOCK_NOTIFS: NotifItem[] = [
  { id: 'n1', coin: 'BTC', text: 'Yeni işlem açıldı | UP 59', time: '2s', severity: 'success' },
  { id: 'n2', coin: 'ETH', text: 'TP tetiklendi | +1.34$', time: '14s', severity: 'success' },
  { id: 'n3', coin: 'SOL', text: 'SL yaklaşıyor | Limit 52', time: '28s', severity: 'warning' },
  { id: 'n4', coin: 'DOGE', text: 'SL tetiklendi | -0.24$', time: '45s', severity: 'error' },
  { id: 'n5', coin: 'LINK', text: 'Force sell countdown | 8s', time: '1m', severity: 'pending' },
  { id: 'n6', coin: 'BNB', text: 'FS kapandı | -0.06$', time: '1m', severity: 'warning' },
  { id: 'n7', coin: 'XRP', text: 'Claim bekleniyor | 3/5 retry', time: '2m', severity: 'pending' },
  { id: 'n8', coin: 'ADA', text: 'Claim başarılı | Tahsil $4.21', time: '3m', severity: 'success' },
  { id: 'n9', coin: 'MATIC', text: 'Max retry | manuel kontrol', time: '4m', severity: 'error' },
  { id: 'n10', coin: 'AVAX', text: 'Sinyal hazır | UP 56', time: '5m', severity: 'info' },
  { id: 'n11', coin: 'DOT', text: 'Spread yüksek | bekleniyor', time: '6m', severity: 'warning' },
  { id: 'n12', coin: 'UNI', text: 'Delta yetersiz | $32 < $50', time: '7m', severity: 'pending' },
  { id: 'n13', coin: 'LTC', text: 'Balance yetersiz | min $1.00', time: '9m', severity: 'error' },
  { id: 'n14', coin: 'TRX', text: 'Cooldown | 18s', time: '11m', severity: 'pending' },
  { id: 'n15', coin: 'ATOM', text: 'Pozisyon kurtarıldı | restart sonrası', time: '14m', severity: 'info' },
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

export default function NotifRail({ items = MOCK_NOTIFS }: { items?: NotifItem[] }) {
  return (
    <aside className="dsp-nrail">
      <div className="dsp-nrail-hdr">
        <span className="dsp-nrail-hdr-title">Bildirimler</span>
        <span className="dsp-nrail-hdr-badge">{items.length}</span>
      </div>
      <div className="dsp-nrail-list">
        {items.map((n) => (
          <NotifCard key={n.id} item={n} />
        ))}
      </div>
    </aside>
  );
}

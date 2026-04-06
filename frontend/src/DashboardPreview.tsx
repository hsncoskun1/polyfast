/**
 * DashboardPreview — Faz 8 preview yuzeyi.
 *
 * Ana dashboard (App.tsx) KORUNUYOR.
 * Bu ayri preview component — iterasyon burda yapilacak.
 * Son onay gelmeden App.tsx REPLACE EDILMEYECEK.
 */

import { useEffect, useState } from 'react';
import {
  getOverview,
  getPositions,
  getClaims,
  getTradingStatus,
  type DashboardOverview,
  type PositionSummary,
  type ClaimSummary,
  type TradingStatus,
} from './api/dashboard';

const REFRESH_MS = 2000;

export default function DashboardPreview() {
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [positions, setPositions] = useState<PositionSummary[]>([]);
  const [claims, setClaims] = useState<ClaimSummary[]>([]);
  const [trading, setTrading] = useState<TradingStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = async () => {
    try {
      const [ov, pos, cl, tr] = await Promise.all([
        getOverview(),
        getPositions(),
        getClaims(),
        getTradingStatus(),
      ]);
      setOverview(ov);
      setPositions(pos);
      setClaims(cl);
      setTrading(tr);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    }
  };

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, REFRESH_MS);
    return () => clearInterval(interval);
  }, []);

  return (
    <div style={styles.container}>
      <header style={styles.header}>
        <h1 style={styles.title}>Polyfast</h1>
        <span style={styles.subtitle}>5M Trading Bot</span>
        {trading && (
          <span style={{
            ...styles.badge,
            background: trading.trading_enabled ? '#166534' : '#991b1b',
          }}>
            {trading.trading_enabled ? 'NORMAL' : 'DEGRADED'}
          </span>
        )}
      </header>

      {error && <div style={styles.error}>Backend: {error}</div>}

      {overview && (
        <div style={styles.grid}>
          {/* Balance Card */}
          <div style={styles.card}>
            <div style={styles.cardLabel}>Balance</div>
            <div style={styles.cardValue}>${overview.balance.available.toFixed(2)}</div>
            <div style={styles.cardSub}>
              {overview.balance.is_stale
                ? <span style={{ color: '#ef4444' }}>STALE ({overview.balance.age_seconds}s)</span>
                : <span style={{ color: '#4ade80' }}>Fresh</span>
              }
            </div>
          </div>

          {/* Open Positions */}
          <div style={styles.card}>
            <div style={styles.cardLabel}>Open Positions</div>
            <div style={styles.cardValue}>{overview.open_positions}</div>
          </div>

          {/* Pending Claims */}
          <div style={styles.card}>
            <div style={styles.cardLabel}>Pending Settlement</div>
            <div style={styles.cardValue}>{overview.pending_claims}</div>
          </div>

          {/* Session Trades */}
          <div style={styles.card}>
            <div style={styles.cardLabel}>Session Trades</div>
            <div style={styles.cardValue}>{overview.session_trade_count}</div>
          </div>

          {/* Coins */}
          <div style={styles.card}>
            <div style={styles.cardLabel}>Coins</div>
            <div style={styles.cardValue}>
              {overview.eligible_coins}/{overview.configured_coins}
            </div>
            <div style={styles.cardSub}>eligible / configured</div>
          </div>
        </div>
      )}

      {/* Positions Table */}
      {positions.length > 0 && (
        <div style={styles.section}>
          <h2 style={styles.sectionTitle}>Positions</h2>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Asset</th>
                <th style={styles.th}>Side</th>
                <th style={styles.th}>State</th>
                <th style={styles.th}>Fill</th>
                <th style={styles.th}>Amount</th>
                <th style={styles.th}>PnL</th>
                <th style={styles.th}>Reason</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => (
                <tr key={p.position_id}>
                  <td style={styles.td}>{p.asset}</td>
                  <td style={{
                    ...styles.td,
                    color: p.side === 'UP' ? '#4ade80' : '#ef4444',
                  }}>{p.side}</td>
                  <td style={styles.td}>{p.state}</td>
                  <td style={styles.td}>{p.fill_price.toFixed(4)}</td>
                  <td style={styles.td}>${p.requested_amount_usd.toFixed(2)}</td>
                  <td style={{
                    ...styles.td,
                    color: p.net_realized_pnl >= 0 ? '#4ade80' : '#ef4444',
                  }}>${p.net_realized_pnl.toFixed(4)}</td>
                  <td style={styles.td}>{p.close_reason || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pending Claims */}
      {claims.length > 0 && (
        <div style={styles.section}>
          <h2 style={styles.sectionTitle}>Pending Claims</h2>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Asset</th>
                <th style={styles.th}>Status</th>
                <th style={styles.th}>Outcome</th>
                <th style={styles.th}>Amount</th>
                <th style={styles.th}>Retries</th>
              </tr>
            </thead>
            <tbody>
              {claims.map((c) => (
                <tr key={c.claim_id}>
                  <td style={styles.td}>{c.asset}</td>
                  <td style={styles.td}>{c.claim_status}</td>
                  <td style={styles.td}>{c.outcome}</td>
                  <td style={styles.td}>${c.claimed_amount_usdc.toFixed(2)}</td>
                  <td style={styles.td}>{c.retry_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <footer style={styles.footer}>
        <span>Preview Dashboard v0.8.0</span>
      </footer>
    </div>
  );
}

// ── Inline styles (dark theme) ──

const styles: Record<string, React.CSSProperties> = {
  container: {
    padding: '1.5rem',
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
    background: '#0a0a0a',
    color: '#e0e0e0',
    minHeight: '100vh',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: '1rem',
    marginBottom: '1.5rem',
  },
  title: { color: '#4ade80', margin: 0, fontSize: '1.5rem' },
  subtitle: { color: '#666', fontSize: '0.9rem' },
  badge: {
    padding: '0.2rem 0.6rem',
    borderRadius: '4px',
    fontSize: '0.75rem',
    fontWeight: 'bold',
    color: '#fff',
  },
  error: {
    color: '#ef4444',
    padding: '0.75rem',
    background: '#1c1c1c',
    borderRadius: '6px',
    marginBottom: '1rem',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
    gap: '1rem',
    marginBottom: '1.5rem',
  },
  card: {
    background: '#141414',
    padding: '1rem',
    borderRadius: '8px',
    border: '1px solid #222',
  },
  cardLabel: { color: '#888', fontSize: '0.75rem', textTransform: 'uppercase' as const },
  cardValue: { fontSize: '1.5rem', fontWeight: 'bold', marginTop: '0.25rem' },
  cardSub: { color: '#666', fontSize: '0.75rem', marginTop: '0.25rem' },
  section: { marginBottom: '1.5rem' },
  sectionTitle: { color: '#4ade80', fontSize: '1rem', marginBottom: '0.75rem' },
  table: {
    width: '100%',
    borderCollapse: 'collapse' as const,
    fontSize: '0.85rem',
  },
  th: {
    textAlign: 'left' as const,
    padding: '0.5rem',
    borderBottom: '1px solid #333',
    color: '#888',
    fontSize: '0.75rem',
    textTransform: 'uppercase' as const,
  },
  td: {
    padding: '0.5rem',
    borderBottom: '1px solid #1a1a1a',
  },
  footer: {
    marginTop: '2rem',
    color: '#444',
    fontSize: '0.7rem',
    textAlign: 'center' as const,
  },
};

/**
 * Dashboard API client — backend READ-ONLY endpoints.
 */

const BASE = '/api';

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

// ── Types ──

export interface BalanceInfo {
  available: number;
  total: number;
  is_stale: boolean;
  age_seconds: number;
}

export interface DashboardOverview {
  trading_enabled: boolean;
  balance: BalanceInfo;
  open_positions: number;
  pending_claims: number;
  session_trade_count: number;
  configured_coins: number;
  eligible_coins: number;
}

export interface PositionSummary {
  position_id: string;
  asset: string;
  side: string;
  state: string;
  fill_price: number;
  requested_amount_usd: number;
  net_position_shares: number;
  close_reason: string | null;
  net_realized_pnl: number;
  created_at: string;
}

export interface ClaimSummary {
  claim_id: string;
  asset: string;
  position_id: string;
  claim_status: string;
  outcome: string;
  claimed_amount_usdc: number;
  retry_count: number;
}

export interface CoinSettingSummary {
  coin: string;
  coin_enabled: boolean;
  side_mode: string;
  order_amount: number;
  is_configured: boolean;
  is_trade_eligible: boolean;
}

export interface TradingStatus {
  trading_enabled: boolean;
  open_positions: number;
  pending_claims: number;
  session_trade_count: number;
  settlement_pending: number;
}

// ── API calls ──

export const getOverview = () => fetchJson<DashboardOverview>('/dashboard/overview');
export const getPositions = () => fetchJson<PositionSummary[]>('/dashboard/positions');
export const getClaims = () => fetchJson<ClaimSummary[]>('/dashboard/claims');
export const getSettings = () => fetchJson<CoinSettingSummary[]>('/dashboard/settings');
export const getTradingStatus = () => fetchJson<TradingStatus>('/dashboard/trading-status');

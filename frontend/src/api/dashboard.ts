/**
 * Dashboard API client — backend READ-ONLY endpoints.
 *
 * v0.8.0-backend-contract surface (Yol A — extend, legacy korunur):
 *
 * Backend Pydantic modellerinin TypeScript karsiligi. Tum yeni alanlar
 * `optional` cunku backend Optional/None doner — frontend null-safe tuketmeli.
 *
 * Mevcut DashboardPreview'in kullandigi legacy fonksiyonlar (getOverview,
 * getPositions, getClaims, getSettings, getTradingStatus) kirilmadan
 * korundu. Yeni typed surface fonksiyonlari yanlarina eklendi.
 *
 * Backend kaynaklari:
 *   backend/api/health.py     → BotStatusContract, HealthResponse
 *   backend/api/dashboard.py  → 12 contract model + 9 endpoint
 */

const BASE = '/api';

// ─── Generic fetch helper (legacy korunur) ───────────────────────

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

/**
 * Defensive fetch — 503 (orchestrator yok) ve network error'lari
 * `null` olarak swallow eder. Yeni typed fetcher'lar bunu kullanir,
 * sane polling icin error storm yaratmaz.
 */
async function safeFetchJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${BASE}${path}`);
    if (!res.ok) {
      // 503 = orchestrator not running (placeholder-safe)
      // 5xx = backend down/restarting
      // 4xx = client/contract drift
      return null;
    }
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

// ╔══════════════════════════════════════════════════════════════╗
// ║  v0.8.0-backend-contract: SHARED CONTRACT FRAGMENTS          ║
// ╚══════════════════════════════════════════════════════════════╝

/** PnL renk tonu — tile + summary kullanir. */
export type PnlTone = 'profit' | 'loss' | 'neutral' | 'pending' | 'off';

/** Activity bildirimi severity'si — ActivityStatusLine kullanir. */
export type ActivitySeverity =
  | 'success'
  | 'warning'
  | 'error'
  | 'info'
  | 'pending'
  | 'off';

/** Rule visual state — backend RuleState enum aynasi. */
export type RuleStateContract = 'pass' | 'fail' | 'waiting' | 'disabled';

/** Claim status — backend internal PENDING/SUCCESS/FAILED -> RETRY/OK/FAIL. */
export type ClaimStatusContract = 'RETRY' | 'OK' | 'FAIL';

/** Health enum — backend BotStatusContract.health. */
export type HealthLiteral = 'healthy' | 'degraded' | 'critical' | 'unknown';

/** Idle tile kategorisi. */
export type IdleKind =
  | 'no_events'
  | 'waiting_rules'
  | 'bot_stopped'
  | 'cooldown'
  | 'error';

/** Position variant hint — frontend EventTileVariant. */
export type PositionVariant = 'open' | 'claim';

/** Activity bildirimi (text + severity + opsiyonel inline icon placeholder). */
export interface ActivityContract {
  text: string;
  severity?: ActivitySeverity;
  inline_icons?: string[];
}

/** Bot lifecycle + health contract — frontend HealthIndicator + BotModeChip. */
export interface BotStatusContract {
  running?: boolean;
  health?: HealthLiteral;
  restore_phase?: boolean;
  shutdown_in_progress?: boolean;
  startup_guard_blocked?: boolean;
  paused?: boolean;
  uptime_sec?: number;
  latency_ms?: number;
}

/** Tek bir rule'un UI ozeti — RuleGrid/RuleBlock kullanir. */
export interface RuleSpecContract {
  label: string;
  live_value: string;
  threshold_text?: string;
  state: RuleStateContract;
}

// ╔══════════════════════════════════════════════════════════════╗
// ║  HEALTH                                                      ║
// ╚══════════════════════════════════════════════════════════════╝

/**
 * /api/health response.
 * v0.8.0: bot_status field'i eklendi (placeholder-first, optional).
 */
export interface HealthResponse {
  status: string;
  version: string;
  uptime_seconds: number;
  components: Record<string, string>;
  bot_status?: BotStatusContract | null;
}

export const fetchHealth = () => safeFetchJson<HealthResponse>('/health');

// Legacy alias (eski client.ts'den getHealth ile uyumlu kalsin diye)
export const getHealth = () => fetchJson<HealthResponse>('/health');

// ╔══════════════════════════════════════════════════════════════╗
// ║  /api/dashboard/overview                                     ║
// ╚══════════════════════════════════════════════════════════════╝

export interface BalanceInfo {
  available: number;
  total: number;
  is_stale: boolean;
  age_seconds: number;
}

/**
 * Dashboard overview — tek bakista tum durum.
 * Legacy alanlar (zorunlu) + v0.8.0 extended alanlar (optional).
 */
export interface DashboardOverview {
  // Legacy
  trading_enabled: boolean;
  balance: BalanceInfo;
  open_positions: number;
  pending_claims: number;
  session_trade_count: number;
  configured_coins: number;
  eligible_coins: number;

  // v0.8.0 extended (optional, placeholder-first)
  bot_status?: BotStatusContract | null;
  bakiye_text?: string | null;
  kullanilabilir_text?: string | null;
  session_pnl?: number | null;
  session_pnl_pct?: number | null;
  acilan?: number | null;
  gorulen?: number | null;
  ag_rate?: string | null;
  win?: number | null;
  lost?: number | null;
  winrate?: string | null;
}

export const getOverview = () =>
  fetchJson<DashboardOverview>('/dashboard/overview');

export const fetchOverview = () =>
  safeFetchJson<DashboardOverview>('/dashboard/overview');

// ╔══════════════════════════════════════════════════════════════╗
// ║  /api/dashboard/positions                                    ║
// ╚══════════════════════════════════════════════════════════════╝

/** Open variant canli fiyat + delta ozeti. */
export interface PositionLiveContract {
  side: 'UP' | 'DOWN';
  entry: string; // share price str, "83"
  live: string; // share price str, "85.6"
  delta_text?: string | null; // "+2.6"
}

/**
 * Open variant cikis esikleri (CONFIG, canli durum DEGIL).
 * Canli olay/uyari mesajlari ActivityContract'tan akar.
 */
export interface PositionExitsContract {
  tp: string;
  sl: string;
  fs: string; // "30s" countdown
  fs_pnl?: string | null; // "-5%"
}

export interface PositionSummary {
  // Legacy
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

  // v0.8.0 extended (optional)
  variant?: PositionVariant | null;
  live?: PositionLiveContract | null;
  exits?: PositionExitsContract | null;
  pnl_big?: string | null; // "+3.1%" formatted
  pnl_amount?: string | null; // "+0.31$" formatted
  pnl_tone?: PnlTone | null;
  activity?: ActivityContract | null;
  event_url?: string | null;
}

export const getPositions = () =>
  fetchJson<PositionSummary[]>('/dashboard/positions');

export const fetchPositions = () =>
  safeFetchJson<PositionSummary[]>('/dashboard/positions');

// ╔══════════════════════════════════════════════════════════════╗
// ║  /api/dashboard/claims                                       ║
// ╚══════════════════════════════════════════════════════════════╝

export interface ClaimSummary {
  // Legacy
  claim_id: string;
  asset: string;
  position_id: string;
  claim_status: string;
  outcome: string;
  claimed_amount_usdc: number;
  retry_count: number;

  // v0.8.0 extended (optional)
  status?: ClaimStatusContract | null;
  retry?: number | null;
  max_retry?: number | null;
  next_sec?: number | null; // scheduled retry delay (live countdown DEGIL)
  payout?: string | null; // "$5.83" formatted, bilinmiyorsa null
}

export const getClaims = () =>
  fetchJson<ClaimSummary[]>('/dashboard/claims');

export const fetchClaims = () =>
  safeFetchJson<ClaimSummary[]>('/dashboard/claims');

// ╔══════════════════════════════════════════════════════════════╗
// ║  /api/dashboard/search                                       ║
// ╚══════════════════════════════════════════════════════════════╝

/**
 * Search variant tile — discovery + rule engine sentezi.
 * Backend SearchTileContract karsiligi.
 */
export interface SearchTileContract {
  tile_id: string;
  coin: string;
  event_url: string;
  pnl_big: string; // "6/6" rule pass count veya "BAL"/"BOT"
  pnl_amount?: string | null; // "HAZIR" | "BEKLE" | block reason
  pnl_tone: PnlTone;
  ptb: string;
  live: string;
  delta: string;
  rules: RuleSpecContract[]; // 6 rule (Zaman/Fiyat/Delta/Spread/EvMax/BotMax)
  activity?: ActivityContract | null;
  signal_ready: boolean; // tum considered rules pass ise true
  type?: string | null; // 'pos'|'wait'|'ok'|'off' frontend type class
}

export const fetchSearch = () =>
  safeFetchJson<SearchTileContract[]>('/dashboard/search');

// ╔══════════════════════════════════════════════════════════════╗
// ║  /api/dashboard/idle                                         ║
// ╚══════════════════════════════════════════════════════════════╝

/**
 * Idle variant tile — bos durum bildirimleri.
 * Backend IdleTileContract karsiligi.
 */
export interface IdleTileContract {
  tile_id: string;
  coin?: string | null;
  idle_kind: IdleKind;
  msg: string;
  activity?: ActivityContract | null;
  rules?: RuleSpecContract[] | null; // waiting_rules kind icin
  event_url?: string | null;
}

export const fetchIdle = () => safeFetchJson<IdleTileContract[]>('/dashboard/idle');

// ╔══════════════════════════════════════════════════════════════╗
// ║  /api/dashboard/coins                                        ║
// ╚══════════════════════════════════════════════════════════════╝

/**
 * Coin metadata + ayar registry — frontend tek kaynak.
 * Backend CoinInfoContract karsiligi.
 */
export interface CoinInfoContract {
  symbol: string;
  display_name?: string | null;
  logo_url?: string | null;
  configured: boolean;
  enabled: boolean;
  trade_eligible: boolean;
  side_mode?: string | null;
  order_amount?: number | null;
}

export const fetchCoins = () => safeFetchJson<CoinInfoContract[]>('/dashboard/coins');

// ╔══════════════════════════════════════════════════════════════╗
// ║  /api/dashboard/settings (LEGACY)                            ║
// ╚══════════════════════════════════════════════════════════════╝

export interface CoinSettingSummary {
  coin: string;
  coin_enabled: boolean;
  side_mode: string;
  order_amount: number;
  is_configured: boolean;
  is_trade_eligible: boolean;
}

export const getSettings = () =>
  fetchJson<CoinSettingSummary[]>('/dashboard/settings');

export const fetchSettings = () =>
  safeFetchJson<CoinSettingSummary[]>('/dashboard/settings');

// ╔══════════════════════════════════════════════════════════════╗
// ║  /api/dashboard/trading-status (LEGACY)                      ║
// ╚══════════════════════════════════════════════════════════════╝

export interface TradingStatus {
  trading_enabled: boolean;
  open_positions: number;
  pending_claims: number;
  session_trade_count: number;
  settlement_pending: number;
}

export const getTradingStatus = () =>
  fetchJson<TradingStatus>('/dashboard/trading-status');

export const fetchTradingStatus = () =>
  safeFetchJson<TradingStatus>('/dashboard/trading-status');

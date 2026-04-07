/**
 * useDashboardData — frontend dashboard data layer (Adim 2 / Yol A)
 *
 * Tek hook ile 7 endpoint'in tamamini ceker, polling ile guncel tutar,
 * 503/network error storm'larini engeller.
 *
 * Ozellikler:
 * - sane polling: default 3000ms (tight loop YOK)
 * - error backoff: ust uste basarisizlikta interval 2x exponential (max 30s)
 * - basari sonrasi backoff sifirlanir
 * - per-endpoint independent state (biri 503 verirken digeri calismaya devam)
 * - safeFetchJson kullanir (503 -> null, network -> null, sessiz fail YOK
 *   cunku safeFetchJson icinde de log var)
 * - cleanup: unmount'ta interval temizlenir, race condition koruma
 * - manual refresh: hook return'unde refresh() callback
 *
 * Frontend kullanim:
 *   const { health, overview, positions, claims, search, idle, coins,
 *           loading, error, refresh } = useDashboardData({ pollMs: 3000 });
 *
 * NOT: Bu hook backend contract aynasi icin (api/dashboard.ts). Yeni
 * sidebarli preview ve mevcut DashboardPreview ikisi de ayni hook'tan
 * beslenebilir. Reusable, preview-only hack DEGIL.
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import {
  fetchHealth,
  fetchOverview,
  fetchPositions,
  fetchClaims,
  fetchSearch,
  fetchIdle,
  fetchCoins,
  type HealthResponse,
  type DashboardOverview,
  type PositionSummary,
  type ClaimSummary,
  type SearchTileContract,
  type IdleTileContract,
  type CoinInfoContract,
} from '../api/dashboard';

// ── Config ──────────────────────────────────────────────────────

export interface UseDashboardDataOptions {
  /** Polling interval in ms. Default: 3000 (3s). */
  pollMs?: number;
  /** Polling enabled mi. Default: true. */
  enabled?: boolean;
  /** Initial fetch otomatik mi. Default: true. */
  fetchOnMount?: boolean;
  /** Error sonrasi max backoff (ms). Default: 30000 (30s). */
  maxBackoffMs?: number;
}

const DEFAULT_POLL_MS = 3000;
const DEFAULT_MAX_BACKOFF_MS = 30000;

// ── State shape ─────────────────────────────────────────────────

export interface DashboardDataState {
  health: HealthResponse | null;
  overview: DashboardOverview | null;
  positions: PositionSummary[] | null;
  claims: ClaimSummary[] | null;
  search: SearchTileContract[] | null;
  idle: IdleTileContract[] | null;
  coins: CoinInfoContract[] | null;
}

const EMPTY_STATE: DashboardDataState = {
  health: null,
  overview: null,
  positions: null,
  claims: null,
  search: null,
  idle: null,
  coins: null,
};

export interface DashboardDataResult extends DashboardDataState {
  /** Initial fetch tamamlanmadan true */
  loading: boolean;
  /** Son cycle'da en az bir endpoint patladı mı (null-degil sayisi). */
  hasError: boolean;
  /** Ust uste basarisiz cycle sayisi (backoff tetikleyicisi). */
  errorStreak: number;
  /** Manuel refresh — disardan tetikleme. */
  refresh: () => void;
  /** Son basarili poll timestamp (ms epoch), hic basarili yoksa null. */
  lastSuccessAt: number | null;
}

// ── Hook ────────────────────────────────────────────────────────

export function useDashboardData(
  options: UseDashboardDataOptions = {}
): DashboardDataResult {
  const {
    pollMs = DEFAULT_POLL_MS,
    enabled = true,
    fetchOnMount = true,
    maxBackoffMs = DEFAULT_MAX_BACKOFF_MS,
  } = options;

  const [state, setState] = useState<DashboardDataState>(EMPTY_STATE);
  const [loading, setLoading] = useState<boolean>(fetchOnMount);
  const [hasError, setHasError] = useState<boolean>(false);
  const [errorStreak, setErrorStreak] = useState<number>(0);
  const [lastSuccessAt, setLastSuccessAt] = useState<number | null>(null);

  // Mount/unmount lifecycle ref'leri (race condition ve double-fetch koruma)
  const mountedRef = useRef<boolean>(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inFlightRef = useRef<boolean>(false);

  // Tek bir poll cycle — 7 endpoint paralel
  const runCycle = useCallback(async () => {
    if (inFlightRef.current) return; // ust uste tetiklemeyi engelle
    inFlightRef.current = true;

    try {
      const [health, overview, positions, claims, search, idle, coins] =
        await Promise.all([
          fetchHealth(),
          fetchOverview(),
          fetchPositions(),
          fetchClaims(),
          fetchSearch(),
          fetchIdle(),
          fetchCoins(),
        ]);

      if (!mountedRef.current) return;

      const next: DashboardDataState = {
        health,
        overview,
        positions,
        claims,
        search,
        idle,
        coins,
      };

      // hasError = en az 1 endpoint null mi (503 / network)
      const nullCount = Object.values(next).filter((v) => v === null).length;
      const allFailed = nullCount === Object.keys(next).length;

      setState(next);
      setHasError(nullCount > 0);

      if (allFailed) {
        // Toplu basarisizlik -> backoff arttir
        setErrorStreak((s) => s + 1);
      } else {
        // En az bir endpoint cevap verdi -> basari, backoff sifirla
        setErrorStreak(0);
        setLastSuccessAt(Date.now());
      }

      setLoading(false);
    } finally {
      inFlightRef.current = false;
    }
  }, []);

  // Polling scheduler — backoff dahil
  useEffect(() => {
    mountedRef.current = true;

    if (!enabled) {
      setLoading(false);
      return () => {
        mountedRef.current = false;
        if (timerRef.current) clearTimeout(timerRef.current);
      };
    }

    let cancelled = false;

    const schedule = () => {
      if (cancelled || !mountedRef.current) return;
      // Backoff: errorStreak^2 * pollMs, capped
      const backoff =
        errorStreak === 0
          ? pollMs
          : Math.min(pollMs * Math.pow(2, errorStreak), maxBackoffMs);
      timerRef.current = setTimeout(async () => {
        await runCycle();
        schedule();
      }, backoff);
    };

    if (fetchOnMount) {
      runCycle().then(() => schedule());
    } else {
      schedule();
    }

    return () => {
      cancelled = true;
      mountedRef.current = false;
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
    // errorStreak schedule'i etkiler ama runCycle re-init etmez (useCallback stable)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, pollMs, maxBackoffMs, fetchOnMount, errorStreak]);

  // Manuel refresh — disaridan tetikleyebilir
  const refresh = useCallback(() => {
    runCycle();
  }, [runCycle]);

  return {
    ...state,
    loading,
    hasError,
    errorStreak,
    refresh,
    lastSuccessAt,
  };
}

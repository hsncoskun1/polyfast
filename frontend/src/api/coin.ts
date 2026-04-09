/**
 * Coin action API client — toggle enable/disable.
 *
 * POST /api/coin/{symbol}/toggle → coin_enabled flip + persist
 */

const BASE_URL = '/api';

export interface CoinToggleResponse {
  success: boolean;
  symbol: string;
  enabled: boolean;
  message: string;
}

export async function coinToggle(symbol: string): Promise<CoinToggleResponse> {
  const response = await fetch(`${BASE_URL}/coin/${encodeURIComponent(symbol)}/toggle`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });

  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(`Coin toggle failed: ${response.status} ${text}`);
  }

  return response.json();
}

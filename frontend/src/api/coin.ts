/**
 * Coin action API client — toggle + settings read/save.
 *
 * POST /api/coin/{symbol}/toggle    → coin_enabled flip + persist
 * GET  /api/coin/{symbol}/settings  → mevcut ayarlar + governance
 * POST /api/coin/{symbol}/settings  → kural parametreleri kaydet
 */

const BASE_URL = '/api';

// ── Toggle ──

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

// ── Settings types ──

export interface FieldPolicy {
  visible: boolean;
  editable: boolean;
  locked: boolean;
}

export interface CoinSettingsReadResponse {
  symbol: string;
  configured: boolean;
  coin_enabled: boolean;
  missing_fields: string[];
  settings: Record<string, unknown>;
  field_governance: Record<string, FieldPolicy>;
}

export interface CoinSettingsSaveResponse {
  success: boolean;
  symbol: string;
  configured: boolean;
  message: string;
  missing_fields: string[];
}

// ── Settings fetch ──

/** Mevcut coin ayarlarını oku — modal açılınca çağrılır. */
export async function coinSettingsGet(symbol: string): Promise<CoinSettingsReadResponse> {
  const res = await fetch(`${BASE_URL}/coin/${encodeURIComponent(symbol)}/settings`);
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Coin settings read failed: ${res.status} ${text}`);
  }
  return res.json();
}

/** Coin ayarlarını kaydet — modal'dan Kaydet tıklanınca. */
export async function coinSettingsSave(
  symbol: string,
  fields: Record<string, unknown>,
): Promise<CoinSettingsSaveResponse> {
  const res = await fetch(`${BASE_URL}/coin/${encodeURIComponent(symbol)}/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Coin settings save failed: ${res.status} ${text}`);
  }
  return res.json();
}

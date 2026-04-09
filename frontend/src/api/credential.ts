/**
 * Credential API client — update / status / validate.
 *
 * POST /api/credential/update   → partial save + capability
 * GET  /api/credential/status   → maskeli gösterim + durum
 * POST /api/credential/validate → gerçek check + is_fully_ready
 */

const BASE_URL = '/api';

// ── Response types ──────────────────────────────────────────────

export interface CredentialUpdateResponse {
  success: boolean;
  has_trading_api: boolean;
  has_signing: boolean;
  has_relayer: boolean;
  can_place_orders: boolean;
  can_auto_claim: boolean;
  is_fully_ready: boolean;
  validated: boolean;
  validation_status: string;
  missing_fields: string[];
  message: string;
}

export interface CheckResult {
  name: string;
  label: string;
  status: 'passed' | 'failed' | 'skipped';
  message: string;
  related_fields: string[];
}

export interface CredentialValidateResponse {
  validated: boolean;
  validation_status: 'passed' | 'partial' | 'failed' | 'not_run';
  checks: CheckResult[];
  failed_checks: string[];
  has_trading_api: boolean;
  has_signing: boolean;
  has_relayer: boolean;
  can_place_orders: boolean;
  can_auto_claim: boolean;
  is_fully_ready: boolean;
  message: string;
}

export interface CredentialStatusResponse {
  has_any: boolean;
  has_trading_api: boolean;
  has_signing: boolean;
  has_relayer: boolean;
  can_place_orders: boolean;
  can_auto_claim: boolean;
  validated: boolean;
  validation_status: string;
  failed_checks: string[];
  is_fully_ready: boolean;
  masked_fields: Record<string, string>;
}

// ── Fetch functions ─────────────────────────────────────────────

/** Partial update — sadece gönderilen alanlar güncellenir. */
export async function credentialUpdate(
  fields: Partial<Record<'api_key' | 'api_secret' | 'api_passphrase' | 'private_key' | 'funder_address' | 'relayer_key', string>>,
): Promise<CredentialUpdateResponse> {
  const res = await fetch(`${BASE_URL}/credential/update`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Credential update failed: ${res.status} ${text}`);
  }
  return res.json();
}

/** Status — maskeli alanlar + capability + validation durumu. */
export async function credentialStatus(): Promise<CredentialStatusResponse> {
  const res = await fetch(`${BASE_URL}/credential/status`);
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Credential status failed: ${res.status} ${text}`);
  }
  return res.json();
}

/** Validate — gerçek API check + is_fully_ready. */
export async function credentialValidate(): Promise<CredentialValidateResponse> {
  const res = await fetch(`${BASE_URL}/credential/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Credential validate failed: ${res.status} ${text}`);
  }
  return res.json();
}

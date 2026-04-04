/**
 * Backend API client — typed fetch wrapper for Polyfast backend.
 * All requests go through Vite proxy to backend at /api/*.
 */

const BASE_URL = '/api';

export interface HealthResponse {
  status: string;
  version: string;
  uptime_seconds: number;
  components: Record<string, string>;
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

export async function getHealth(): Promise<HealthResponse> {
  return fetchJson<HealthResponse>('/health');
}

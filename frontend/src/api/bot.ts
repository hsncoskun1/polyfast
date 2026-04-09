/**
 * Bot lifecycle API client — start / pause / stop.
 *
 * POST /api/bot/start   → trading başlat (paused ise resume)
 * POST /api/bot/pause   → yeni entry durdur, exit monitoring devam
 * POST /api/bot/stop    → graceful shutdown
 */

const BASE_URL = '/api';

export interface BotActionResponse {
  success: boolean;
  state: 'running' | 'paused' | 'stopped';
  message: string;
}

async function postBot(action: 'start' | 'pause' | 'stop'): Promise<BotActionResponse> {
  const response = await fetch(`${BASE_URL}/bot/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });

  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(`Bot ${action} failed: ${response.status} ${text}`);
  }

  return response.json();
}

export const botStart = () => postBot('start');
export const botPause = () => postBot('pause');
export const botStop = () => postBot('stop');

import { FLAGS } from '../game/core';

/**
 * 策略機器人的後端邊界（Paper 模擬盤）。
 *
 * 跟 `api/account.ts`、`api/agent.ts` 一樣**直接打 agent-core**（同源 `/api/*`，
 * dev 走 vite proxy）。機器人狀態與成交是後端 runner 每 15 秒即時算出來的，
 * 沒有假造的意義。`?fast=1`（測試/離線錄影）回一組固定樣本、不打網路。
 */

export type BotTrade = {
  ts: number;
  side: 'buy' | 'sell';
  price: number;
  base: number;
  quote: number;
  reason: string;
};

export type BotEval = {
  ts: number;
  price?: number;
  target?: number;
  cur_pos?: number;
  note?: string;
  error?: string;
};

export type StrategyBot = {
  id: string;
  name: string;
  strategy_type: string;
  params: Record<string, unknown>;
  market: string;
  period_minutes: number;
  mode: string;
  status: 'running' | 'stopped';
  created_at: number;
  position: string;
  initial_capital: number;
  equity: number;
  realized_pnl: number;
  unrealized_pnl: number;
  total_pnl: number;
  return_pct: number;
  trade_count: number;
  last_eval?: BotEval | null;
  trades?: BotTrade[];
};

export type BotCreate = {
  name: string;
  strategy_type: 'ma_crossover' | 'rsi_reversal';
  params?: Record<string, number>;
  market?: string;
  period_minutes?: number;
};

const CANNED: StrategyBot[] = [
  {
    id: 'bot-demo',
    name: 'BTC 雙均線 5/20（示範）',
    strategy_type: 'ma_crossover',
    params: { fast_period: 5, slow_period: 20 },
    market: 'btctwd',
    period_minutes: 5,
    mode: 'paper',
    status: 'running',
    created_at: 0,
    position: '持有',
    initial_capital: 100000,
    equity: 103250,
    realized_pnl: 1800,
    unrealized_pnl: 1450,
    total_pnl: 3250,
    return_pct: 3.25,
    trade_count: 4,
    last_eval: { ts: 0, price: 2040000, target: 1, cur_pos: 1, note: 'MA5=2,041,000 > MA20=2,038,000' },
  },
];

async function fail(res: Response): Promise<never> {
  let detail = `連線異常（HTTP ${res.status}）`;
  try {
    const body: unknown = await res.json();
    if (body && typeof body === 'object' && typeof (body as { detail?: unknown }).detail === 'string') {
      detail = (body as { detail: string }).detail;
    }
  } catch {
    /* 非 JSON 回應 */
  }
  throw new Error(detail);
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(path, { credentials: 'same-origin', signal });
  if (!res.ok) await fail(res);
  return (await res.json()) as T;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) await fail(res);
  return (await res.json()) as T;
}

export async function listBots(signal?: AbortSignal): Promise<StrategyBot[]> {
  if (FLAGS.fast) return CANNED;
  return (await getJson<{ bots: StrategyBot[] }>('/api/bots', signal)).bots;
}

export async function getBot(id: string, signal?: AbortSignal): Promise<StrategyBot> {
  if (FLAGS.fast) return CANNED[0]!;
  return (await getJson<{ bot: StrategyBot }>(`/api/bots/${encodeURIComponent(id)}`, signal)).bot;
}

export async function createBot(req: BotCreate): Promise<StrategyBot> {
  return (await post<{ bot: StrategyBot }>('/api/bots', req)).bot;
}

export async function startBot(id: string): Promise<StrategyBot> {
  return (await post<{ bot: StrategyBot }>(`/api/bots/${encodeURIComponent(id)}/start`)).bot;
}

export async function stopBot(id: string): Promise<StrategyBot> {
  return (await post<{ bot: StrategyBot }>(`/api/bots/${encodeURIComponent(id)}/stop`)).bot;
}

export async function deleteBot(id: string): Promise<void> {
  const res = await fetch(`/api/bots/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    credentials: 'same-origin',
  });
  if (!res.ok) await fail(res);
}

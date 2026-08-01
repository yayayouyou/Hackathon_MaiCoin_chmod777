import { FLAGS } from '../game/core';
import { getApprovalSecret } from './agent';

/**
 * 現貨交易的後端邊界。
 *
 * ⚠ **下單是兩步，不是一步。** 這裡只做第一步：
 *
 *     previewOrder()  →  後端建計畫、凍結模式、登記 pending，回一個 token
 *     （使用者在確認框按下去）
 *     approveOrder()  →  後端才真的送單（那一支在 api/agent.ts，模型走的是同一支）
 *
 * 為什麼要多這一跳：使用者在畫面上核准的，必須就是實際送出的那一筆。表單值
 * 在確認框開著的時候還可能被改（誤觸百分比鈕、行情把價格帶動），凍結計畫讓
 * 那件事不可能發生。模式（paper / live）也在 preview 當下凍住 —— 否則
 * 「在模擬盤按下核准、送出前有人把 .env 改成 live」就會變成真單。
 *
 * ⚠ 這裡沒有任何一個函式會直接下單。要下單只能拿 token 去 approveOrder()。
 */

export type MarketRow = {
  id: string;
  name?: string;
  base: string;
  quote: string;
  last: number;
  pct: number;
  vol: number;
  /** 交易所的最小下單量。表單先擋，不要等後端退件才知道 */
  min_base_amount?: number | null;
  base_precision?: number | null;
  quote_precision?: number | null;
};

/** 後端凍結下來的下單計畫。確認框顯示的每一個數字都來自這裡，不是表單。 */
export type OrderPlan = {
  kind: string;
  exchange: string;
  market: string;
  side: string;
  volume: number;
  price: number | null;
  ord_type: string;
  /** 凍結的執行模式。核准後依它執行，不重讀環境變數 */
  mode: 'paper' | 'live' | string;
  latest_price: number;
  est_fill_price: number;
  est_notional_quote: number;
  est_notional_twd: number;
};

export type Exposure = {
  window_hours?: number;
  orders?: number;
  notional_twd?: number;
  max_notional_twd?: number;
  max_orders?: number;
};

export type OrderPreview = {
  token: string;
  hash: string;
  summary: string;
  plan: OrderPlan;
  mode: 'paper' | 'live' | string;
  mode_note: string;
  exposure: Exposure;
  ttl_sec: number;
};

/**
 * `?failApi=1` 一律失敗，訊息與 `api/index.ts` 的 `settle()` 一致。
 *
 * 這個旗標是專案刻意用來「把每個面板的錯誤狀態實際走過一遍」的機制
 * （`tests/state.mjs` 靠它斷言 failApi 時是可讀的錯誤而不是白畫面）。
 * 新的取數函式如果不實作它，那條路徑就再也走不到 —— 而且不會有人發現，
 * 因為畫面看起來完全正常。
 */
function failIfFlagged(): void {
  if (FLAGS.failApi) throw new Error('連線失敗，請稍後再試');
}

/** 可交易市場 + 當前報價。後端帶 60 秒快取，所以前端輪詢頻繁一點也不會打爆 MAX。 */
export async function getMarketRows(quote = 'twd', signal?: AbortSignal): Promise<MarketRow[]> {
  failIfFlagged();
  if (FLAGS.fast) {
    return [
      { id: 'btctwd', base: 'BTC', quote: 'twd', last: 2043000, pct: -2.07, vol: 25, min_base_amount: 0.0001 },
      { id: 'usdttwd', base: 'USDT', quote: 'twd', last: 32.4, pct: -0.09, vol: 1e6, min_base_amount: 8 },
    ];
  }
  const res = await fetch(`/api/markets?quote=${encodeURIComponent(quote)}`, { signal: signal ?? null });
  if (!res.ok) throw new Error(`後端回應 ${res.status}`);
  const body = (await res.json()) as { status?: string; markets?: MarketRow[]; error?: string };
  // 後端打不到 MAX 時是「HTTP 200 + status:ERROR」，只看 res.ok 會把失敗當成空清單
  if (body.status !== 'SUCCESS') throw new Error(body.error ?? '取不到市場清單');
  return body.markets ?? [];
}

/**
 * 產生一份待核准的下單計畫。**這不會下單。**
 *
 * `?fast=1` 直接拒絕：離線示範不該產生任何可以被核准的 token。
 */
// ── K 線 ────────────────────────────────────────────────────

/** 後端已經把秒級時間戳補成毫秒（見 app.py 的 /api/klines），前端直接用。 */
export type Candle = { t: number; o: number; h: number; l: number; c: number; v: number };

/** MAX 支援的週期。送別的字串後端會退件並列出可用值。 */
export const TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d'] as const;
export type Timeframe = (typeof TIMEFRAMES)[number];

export async function getKlines(
  market: string,
  timeframe: Timeframe,
  limit = 300,
  signal?: AbortSignal,
): Promise<Candle[]> {
  failIfFlagged();
  if (FLAGS.fast) {
    // 離線示範：用固定亂數種子生一段假 K 線，讓圖表本身仍然看得出形狀
    let p = 2_000_000;
    return Array.from({ length: 120 }, (_, i) => {
      const o = p;
      p *= 1 + Math.sin(i / 7) * 0.004 + Math.cos(i / 3) * 0.002;
      const c = p;
      return { t: Date.now() - (120 - i) * 3_600_000, o, h: Math.max(o, c) * 1.002, l: Math.min(o, c) * 0.998, c, v: 10 + (i % 9) };
    });
  }
  const res = await fetch(
    `/api/klines?market=${encodeURIComponent(market)}&timeframe=${timeframe}&limit=${limit}`,
    { signal: signal ?? null },
  );
  if (!res.ok) throw new Error(`後端回應 ${res.status}`);
  const body = (await res.json()) as { status?: string; candles?: Candle[]; error?: string };
  if (body.status !== 'SUCCESS') throw new Error(body.error ?? '取不到 K 線');
  return body.candles ?? [];
}

// ── 訂單簿 ──────────────────────────────────────────────────

/** MAX 的深度是字串陣列 [價格, 數量]，這裡轉成數字對。 */
export type DepthLevel = { price: number; volume: number };
export type Depth = { bids: DepthLevel[]; asks: DepthLevel[]; market?: string };

export async function getOrderbook(market: string, limit = 14, signal?: AbortSignal): Promise<Depth> {
  failIfFlagged();
  if (FLAGS.fast) {
    const mk = (base: number, dir: number): DepthLevel[] =>
      Array.from({ length: limit }, (_, i) => ({
        price: base * (1 + dir * i * 0.0004),
        volume: 0.002 + ((i * 7) % 11) * 0.001,
      }));
    return { bids: mk(2_043_000, -1), asks: mk(2_046_000, 1) };
  }
  const res = await fetch(
    `/api/orderbook?market=${encodeURIComponent(market)}&limit=${limit}`,
    { signal: signal ?? null },
  );
  if (!res.ok) throw new Error(`後端回應 ${res.status}`);
  const body = (await res.json()) as {
    bids?: Array<[string, string]>;
    asks?: Array<[string, string]>;
    error?: string;
  };
  if (body.error) throw new Error(body.error);
  const conv = (rows?: Array<[string, string]>): DepthLevel[] =>
    (rows ?? [])
      .map((r) => ({ price: parseFloat(r[0]), volume: parseFloat(r[1]) }))
      .filter((r) => Number.isFinite(r.price) && Number.isFinite(r.volume));
  // 賣單由低到高、買單由高到低 —— 畫面上賣在上、買在下，中間才是價差
  const asks = conv(body.asks).sort((a, b) => a.price - b.price);
  const bids = conv(body.bids).sort((a, b) => b.price - a.price);
  return { bids, asks };
}

export type OrdType = 'limit' | 'market' | 'post_only';

export async function previewOrder(
  req: { market: string; side: 'buy' | 'sell'; volume: number; ord_type: OrdType; price?: number },
  signal?: AbortSignal,
): Promise<OrderPreview> {
  failIfFlagged();
  if (FLAGS.fast) throw new Error('離線示範模式（?fast=1）不產生下單計畫');

  const secret = await getApprovalSecret();
  const res = await fetch('/api/order_preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Approval-Secret': secret },
    body: JSON.stringify({ ...req, exchange: 'max' }),
    signal: signal ?? null,
  });
  const body = (await res.json().catch(() => ({}))) as Partial<OrderPreview> & {
    status?: string;
    error?: string;
    detail?: string;
  };
  if (!res.ok) throw new Error(body.detail ?? body.error ?? `後端回應 ${res.status}`);
  if (body.status !== 'SUCCESS' || !body.token) throw new Error(body.error ?? '無法產生下單計畫');
  return body as OrderPreview;
}

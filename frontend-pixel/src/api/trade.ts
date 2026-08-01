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

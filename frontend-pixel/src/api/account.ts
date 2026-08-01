import { FLAGS } from '../game/core';

/**
 * 「我的帳戶」的後端邊界 —— 大廳右下角三個站點的資料全部從這裡來。
 *
 * 與 `api/index.ts` 的關係：那一支是 mock 沙盒（`settle()` 回假資料），
 * 這一支跟 `api/agent.ts` 一樣**直接打 agent-core**，因為個人帳戶資料
 * 沒有「假造一份」的意義 —— 對不上的帳、不足的樣本、查不到的鏈上來源，
 * 正是這一區要講的東西，捏造出來的漂亮數字反而把它的價值刪掉了。
 *
 * 三條紀律：
 *
 * ① **同源**。一律 `/api/*`，dev 走 vite proxy、正式走 CloudFront behavior。
 *    絕不從瀏覽器直接打 `max-api.maicoin.com` —— 它的回應沒有
 *    `Access-Control-Allow-Origin`，瀏覽器會在讀到 body 之前擋掉
 *    （行情跑馬燈踩過一次，見 `hud/feeds.ts` 紀律 ④）。
 *
 * ② **`?fast=1` 不打網路**，回一組固定的樣本。測試 harness 用
 *    `waitUntil:'networkidle'` 開頁，一條掛著的請求會讓它永不觸發；
 *    而 `/api/positions` 冷啟動要重播整本帳本，實測 3 秒起跳。
 *
 * ③ **每一支都收 `AbortSignal`**，綁在面板卸載上。`/api/positions` 與
 *    `/api/behavior` 都是數秒級的請求，關掉面板還在跑就是白燒後端。
 */

// ── 型別：對齊後端實際回傳，不是對齊文件 ──────────────────
//
// 這些形狀是拿真實帳戶把每一支端點打過一輪抄下來的。刻意全部標成
// optional：後端在缺金鑰/缺權限/樣本不足時是**少給欄位**而不是給 null，
// 少一個 `?` 就會在降級路徑上炸掉 —— 而降級路徑正是這一區的常態。

export type Balance = {
  currency: string;
  balance: number;
  locked?: number;
  staked?: number;
  /** 抓不到報價的資產是 null，不能拿來加總 */
  value_twd?: number | null;
  stakeable?: boolean;
};

export type Margin = {
  ad_ratio?: number | null;
  asset_in_usdt?: number;
  debt_in_usdt?: number;
  net_equity_usdt?: number;
  net_equity_twd?: number | null;
  balances?: Array<{ currency: string; balance: number; principal?: number; interest?: number }>;
};

export type Rewards = {
  count: number;
  by_type?: Record<string, number>;
  by_currency?: Record<string, number>;
  recent?: Array<{ type?: string; currency?: string; amount?: string | number }>;
};

export type TradeStats = {
  count: number;
  buy: number;
  sell: number;
  twd_volume?: number;
  top_markets?: Array<{ market: string; count: number }>;
};

export type Dashboard = {
  risk_mode?: string;
  trade_approval?: string;
  has_account?: boolean;
  balances?: Balance[];
  total_value_twd?: number;
  margin?: Margin;
  rewards?: Rewards | null;
  trade_stats?: TradeStats | null;
  traits?: string[];
  /** 有值就代表沒讀到帳戶。畫面要照實說，不要假裝成「餘額為 0」 */
  account_error?: string;
};

/** 同一檔資產依「取得期間」分組的成本批次。`basis` 是這一組的成本可信度。 */
export type LotGroup = {
  period: string;
  source: string;
  qty: number;
  cost_twd: number;
  lots: number;
  avg_cost_twd: number;
  unrealized_pnl_twd: number;
  basis: 'known' | 'unknown' | string;
};

export type Position = {
  currency: string;
  qty: number;
  avg_cost_twd: number;
  cost_twd: number;
  price_twd: number;
  value_twd: number;
  unrealized_pnl_twd: number;
  unrealized_pnl_pct: number;
  lots: number;
  /**
   * 成本基礎有多少比例是「查得到來源」的（0–100）。
   *
   * 這是整個面板最重要的一個數字：數量已經被 `adjustments` 校正到跟交易所
   * 一致，所以艙位卡的不確定性**不在數量、在成本**。100 代表每一份持有都
   * 追得到買入紀錄；低於 100 的部分是用推估補的，損益要打折看。
   */
  basis_known_pct?: number;
  actual_qty?: number;
  /** 帳本數量與交易所餘額的差。0 代表這一檔對得上 */
  qty_gap_vs_exchange?: number;
  lot_groups?: LotGroup[];
};

export type RealizedClose = {
  time: string;
  currency: string;
  qty: number;
  proceeds_twd: number;
  cost_twd: number;
  pnl_twd: number;
  pnl_pct: number;
  holding_days?: number;
  basis_quality?: string;
  note?: string;
  /** 後端用中文鍵，照抄不改 —— 改了就要在兩邊同步一份對照表 */
  matched_lots?: Array<{ 買入日: string; 數量: number; 成本單價: number; 成本來源: string }>;
};

export type ReconcileRow = {
  currency: string;
  ledger_qty: number;
  actual_qty: number;
  gap: number;
  /** 這一幣種對不對得上。「先展示對得上的」就是照這個排序 */
  ok: boolean;
  diagnosis: string;
  sources?: Record<string, number>;
};

export type Positions = {
  ok: boolean;
  method?: string;
  positions?: Position[];
  totals?: {
    total_cost_twd?: number;
    total_value_twd?: number;
    total_unrealized_pnl_twd?: number;
    total_unrealized_pnl_pct?: number | null;
  };
  /** 引擎為了對上交易所餘額做的校正。它存在本身就是資訊，不要藏起來 */
  adjustments?: Array<{ currency: string; action: string; qty: number; reason: string }>;
  unmatched_qty?: Record<string, number>;
  realized?: {
    total_twd?: number;
    closes?: number;
    by_currency?: Array<{
      currency: string;
      realized_pnl_twd: number;
      cost_twd: number;
      return_pct: number;
      closes: number;
      win_rate_pct: number;
    }>;
    recent?: RealizedClose[];
    fee_cost_twd?: Record<string, number>;
  };
  reconcile?: {
    confidence?: 'full' | 'partial' | 'none' | string;
    matched?: number;
    currencies?: number;
    mismatched?: number;
    rows?: ReconcileRow[];
    note?: string;
  };
  error?: string;
};

/**
 * 行為指標。**每一種指標的欄位都不一樣**（處置效應有 winners/losers、
 * 成本拖累有 total_fees_twd…），所以除了共通的四個欄位之外一律當成
 * 未知鍵讀 —— 前端不該為了排版把後端的指標種類寫死成一個 union，
 * 那樣後端加一種指標前端就少一格，而且不會報錯。
 */
export type BehaviorMetric = {
  metric: string;
  /** 樣本夠不夠下結論。不夠時後端**刻意把 conclusion 留成 null** */
  sample_ok?: boolean;
  conclusion?: string | null;
  note?: string;
  [k: string]: unknown;
};

export type Behavior = {
  metrics?: BehaviorMetric[];
  findings?: string[];
  insufficient_sample?: string[];
  sample?: {
    closes_total?: number;
    closes_analyzed?: number;
    dust_excluded?: number;
    min_trade_twd?: number;
    events?: number;
    method?: string;
  };
  data_confidence?: string;
  note?: string;
  error?: string;
};

export type TradingGuard = {
  effective_mode?: string;
  mode_note?: string;
  kill_switch?: { engaged?: boolean; note?: string; path?: string };
  exposure?: {
    window_hours?: number;
    orders?: number;
    notional_twd?: number;
    max_notional_twd?: number;
    max_orders?: number;
  };
  recent_decisions?: Array<Record<string, unknown>>;
  note?: string;
  error?: string;
};

export type AccountActivity = {
  ok?: boolean;
  trades?: Array<{
    market: string;
    side?: string;
    price?: string;
    volume?: string;
    funds?: string;
    time_ms?: number | null;
  }>;
  flow?: Array<{
    type?: string;
    currency?: string;
    amount?: number;
    state?: string;
    time_ms?: number | null;
    is_internal?: boolean;
    network?: string;
    txid?: string | null;
    to_address?: string | null;
  }>;
  converts?: Array<{
    from_currency?: string;
    from_amount?: number;
    to_currency?: string;
    to_amount?: number;
    fee_in_twd?: number;
    time_ms?: number | null;
  }>;
  withdraw_addresses?: Array<{
    currency?: string;
    network?: string;
    /** 後端已經遮蔽中段（`0xf1d0…575b`），前端不要再解 */
    address?: string;
    label?: string;
    is_internal?: boolean;
  }>;
  error?: string;
};

export type DepositSources = {
  checked?: number;
  traced_onchain?: number;
  named_source?: number;
  flagged_suspicious?: number;
  deposits?: Array<Record<string, unknown>>;
  skipped?: Record<string, number>;
  summary?: string;
  note?: string;
  error?: string;
};

// ── 取數 ────────────────────────────────────────────────────

/**
 * `?fast=1` 的固定樣本。
 *
 * 刻意選一組**有缺陷的**數字：對帳是 partial、樣本不足、鏈上溯源查不到。
 * 離線示範要示範的是真實情況長什麼樣，一組完美數字會讓所有降級路徑
 * 在錄影裡完全沒被走過 —— 而那些路徑正是現場最可能出現的。
 */
const CANNED = {
  dashboard: {
    risk_mode: 'paper',
    trade_approval: 'always',
    has_account: true,
    total_value_twd: 5729.9,
    balances: [
      { currency: 'TWD', balance: 2831, locked: 0, staked: 0, value_twd: 2831 },
      { currency: 'MAX', balance: 265.35, locked: 0, staked: 0, value_twd: 2270.54 },
    ],
    traits: ['主要關注 BTC 主流幣種走勢'],
  } satisfies Dashboard,
  positions: {
    ok: true,
    positions: [],
    totals: { total_value_twd: 5729.91, total_unrealized_pnl_twd: -334.5, total_unrealized_pnl_pct: -5.52 },
    realized: { total_twd: 1903.85, closes: 43 },
    reconcile: { confidence: 'partial', matched: 2, currencies: 7, mismatched: 5, rows: [] },
  } satisfies Positions,
};

async function pull<T>(path: string, signal: AbortSignal | undefined, fallback: T): Promise<T> {
  // `?failApi=1` 一律失敗，訊息與 api/index.ts 的 settle() 一致 —— 那個旗標是
  // 專案刻意用來把每個面板的錯誤狀態實際走過一遍的，不實作它那條路就走不到。
  if (FLAGS.failApi) throw new Error('連線失敗，請稍後再試');
  if (FLAGS.fast) return fallback;

  const res = await fetch(path, { signal: signal ?? null });
  if (!res.ok) throw new Error(`後端回應 ${res.status}`);
  const body = (await res.json()) as T & { error?: string };

  // 後端在打不到 MAX 時回的是「HTTP 200 + error 欄位」，不是錯誤碼。
  // 只看 res.ok 會把失敗當成功，畫面就會顯示一組空的「正常」數字。
  if (body && typeof body === 'object' && body.error) throw new Error(String(body.error));
  return body;
}

/** 帳戶總覽：餘額、質押獎勵、融資、近期交易統計、AI 記住的特質。 */
export const getDashboard = (signal?: AbortSignal): Promise<Dashboard> =>
  pull('/api/dashboard', signal, CANNED.dashboard);

/**
 * FIFO 艙位 + 已實現損益 + 對帳。**冷啟動要重播整本帳本，數秒級。**
 *
 * `sync=1` 是強制重新同步帳本（給「重新整理」按鈕用）；平常不要帶，
 * 後端本來就會在帳本超過 30 分鐘沒更新時自己同步。
 */
export const getPositions = (signal?: AbortSignal, sync = false): Promise<Positions> =>
  pull(`/api/positions${sync ? '?sync=1' : ''}`, signal, CANNED.positions);

/** 交易行為分析。需重播帳本，比 positions 更慢，所以只在切到那一頁時才打。 */
export const getBehavior = (signal?: AbortSignal): Promise<Behavior> =>
  pull('/api/behavior', signal, { data_confidence: 'partial', metrics: [], findings: [] });

export const getTradingGuard = (signal?: AbortSignal): Promise<TradingGuard> =>
  pull('/api/trading_guard', signal, { effective_mode: 'paper', recent_decisions: [] });

export const getAccountActivity = (signal?: AbortSignal): Promise<AccountActivity> =>
  pull('/api/account_activity', signal, { ok: true, trades: [], flow: [], converts: [] });

export const getDepositSources = (signal?: AbortSignal): Promise<DepositSources> =>
  pull('/api/deposit_sources', signal, { checked: 0, summary: '離線示範模式' });

/** 可分享的損益對帳單卡。回的是 SVG 網址，直接放進 `<img src>`。 */
export const pnlCardUrl = (handle = ''): string =>
  `/api/pnl_card.svg${handle ? `?handle=${encodeURIComponent(handle)}` : ''}`;

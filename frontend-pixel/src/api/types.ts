import type { Accent } from '../world/types';

export type RoomInfo = {
  id: string;
  topic: string;
  tag: string;
  /** 進入房間後套用的主題色 */
  accent: Accent;
  heat: number;
  online: number;
  /** 24 小時熱度變化 % */
  change: number;
  /**
   * 討論情緒，-100（極空）~ 100（極多）。
   *
   * 放在 RoomInfo 而不是只放在 Report 裡，有兩個原因：大廳排行榜可以直接
   * 顯示；而且遊戲層拿得到它去驅動房間的燈光與看板，不必為了一個數字
   * 在載入場景時去 await 一次 API。
   */
  sentiment: number;
};

export type ReportPoint = { title: string; body: string };
export type ReportSource = { name: string; note: string; weight: number };

export type Report = {
  roomId: string;
  updatedAt: string;
  /** -100 ~ 100 */
  sentiment: number;
  summary: string;
  points: ReportPoint[];
  risks: string[];
  sources: ReportSource[];
};

export type Post = {
  id: string;
  author: string;
  /** 頭像色塊 */
  color: string;
  time: string;
  text: string;
  likes: number;
  self?: boolean;
  source?: 'platform' | 'threads';
  sourceAuthor?: string;
  permalink?: string | null;
  parentPostId?: string | null;
  authorRole?: 'user' | 'official' | null;
  /** local = 已進 DB 但還沒發到 Threads（Threads 端暫時失敗，下次同步會補送） */
  syncState?: 'local' | 'published' | 'imported' | null;
};

export type Quote = 'TWD' | 'USDT' | 'BTC';

export type Market = {
  /** MAX 的市場代號，如 btctwd */
  id: string;
  base: string;
  quote: Quote;
  name: string;
  price: number;
  change: number;
};

export type Balance = {
  asset: string;
  available: number;
  locked: number;
  /** 質押中。MAX 的質押部位算在資產內，但既不可用也不算凍結 */
  staked: number;
  /** 目前價格（TWD）。null = 抓不到報價 */
  price: number | null;
  // 平均成本不在這裡 —— 它來自另一支慢很多的端點，見 api.getCostBasis()
};

export type OrderReq = {
  marketId: string;
  side: 'buy' | 'sell';
  type: 'limit' | 'market';
  price?: number;
  volume: number;
};

export type OrderResult = { id: string; state: string; message: string };

export type NewsItem = {
  id: string;
  title: string;
  category: '公告' | '上架' | '維護' | '安全';
  date: string;
  body: string[];
};

export type EventItem = {
  id: string;
  title: string;
  period: string;
  reward: string;
  tag: '進行中' | '即將開始' | '已結束';
  body: string[];
};

export type StrategyKind = '定投' | '網格' | '趨勢' | '波段' | '對沖';

/**
 * 社群公開分享的一套交易策略。
 *
 * ⚠ 這裡刻意**沒有**「一鍵跟單」需要的欄位（部位大小、槓桿、下單參數）。
 *   代客操作與跟單在多數司法管轄區是受規範的業務，而這個作品的評審來自
 *   一家做信託保管與洗錢防制法遵的公司。策略牆的定位是「看別人怎麼想」，
 *   不是「照著做」—— 卡片上的動作只有收藏與請 MAIA 分析。
 *
 * `trades` 一定要顯示：樣本數不足時任何報酬率都不該被當結論，
 *  面板會在 < 30 筆時掛一個警示標記。
 */
export type Strategy = {
  id: string;
  title: string;
  author: string;
  /** 頭像色塊，跟 Post 同一套 */
  color: string;
  kind: StrategyKind;
  /** 標的，例如 BTC/TWD */
  market: string;
  /** 一句話說明 */
  summary: string;
  /** 進出場規則，作者自己填的 2–4 條 */
  rules: string[];
  /** 近 30 日報酬 % */
  return30d: number;
  /** 最大回撤 %（正數） */
  drawdown: number;
  /** 勝率 % */
  winRate: number;
  /** 樣本交易筆數 */
  trades: number;
  /** 收藏人數 */
  saves: number;
  updatedAt: string;
};

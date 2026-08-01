import type { Accent } from '../world/types';
import type { PanelId } from '../ui/panels';
import type { ZoneId } from '../world/zones';

/**
 * ★ 全隊 append 點 4/4。
 *
 * 一張註冊表長出三個介面：`Tab` 快捷格、`/` 命令面板、手機常駐 FAB。
 * 三者共用 FEATURES 與同一條 `runFeature()` 執行路徑（C 軌落地，見 §7.2）。
 *
 * 這一輪只有型別與現有六個入口 —— 沒有 Deck UI。這樣 A/B/C 軌新增面板時
 * 可以順手加一筆，不必等 Deck 做完。
 *
 * 這個檔案是**葉節點**：只有 `import type`，執行期零相依，所以
 * `engine/probe.ts` 與遊戲層都可以安全地讀它。
 */
export type FeatureGroup = 'analysis' | 'market' | 'account' | 'system';

export type Feature = {
  id: string;
  label: string;
  hint: string;
  /** 搜尋關鍵字，空白分隔。含英文別名，評審打 dna / trade 也搜得到 */
  keys: string;
  group: FeatureGroup;
  accent: Accent;
  /** 1–2 個拉丁字元，用 CSS 畫成方形圖示。全專案零圖檔，不要引入 svg */
  glyph: string;
  /**
   * 這個功能在世界裡的落點。有 place 就走「傳送＋走過去＋自動觸發」——
   * 選單是捷徑（給評審），世界是容器（給創意分）。
   * ⚠ 座標必須抄自對應 zone 的既有互動點，不要自己發明：
   *   `tests/zones.mjs` 會驗證每個 place 落在某個 interactable/portal rect 內。
   */
  place?: { zone: ZoneId; wx: number; wy: number };
  panel?: PanelId;
  run?: () => void;
  /** 回字串 = 目前不可用，格子灰掉並把字串當 tooltip */
  blocked?: () => string | null;
};

export const FEATURES: Feature[] = [
  {
    id: 'ranking',
    label: '熱門排行',
    hint: '各討論室的熱度與漲跌',
    keys: 'ranking 排行 熱門 rank board',
    group: 'market',
    accent: 'cyan',
    glyph: 'RK',
    panel: 'ranking',
    place: { zone: 'lobby', wx: 480, wy: 238 },
  },
  {
    id: 'rooms',
    label: '討論區',
    hint: '挑一間討論室走進去',
    keys: 'room 討論 房間 chat forum',
    group: 'market',
    accent: 'cyan',
    glyph: 'RM',
    panel: 'roomPicker',
    place: { zone: 'lobby', wx: 288, wy: 295 },
  },
  {
    id: 'strategies',
    label: '策略牆',
    hint: '社群分享的做法 · 報酬與回撤並排',
    keys: 'strategy 策略 分享 做法 grid dca share wall',
    group: 'market',
    accent: 'amber',
    glyph: 'SW',
    panel: 'strategies',
    place: { zone: 'lobby', wx: 244, wy: 206 },
  },
  {
    id: 'trade',
    label: '現貨交易',
    hint: '行情 · 下單預覽 · 持倉',
    keys: 'trade 交易 下單 買 賣 order',
    group: 'account',
    accent: 'green',
    glyph: 'TR',
    panel: 'char',
  },
  {
    id: 'maxNews',
    label: '官方消息',
    hint: 'MAX 交易所公告',
    keys: 'news 消息 公告 max',
    group: 'system',
    accent: 'max',
    glyph: 'NW',
    panel: 'maxNews',
    place: { zone: 'lobby', wx: 616, wy: 198 },
  },
  {
    id: 'maxEvents',
    label: '最新活動',
    hint: 'MAX 交易所活動',
    keys: 'event 活動 max',
    group: 'system',
    accent: 'max',
    glyph: 'EV',
    panel: 'maxEvents',
    place: { zone: 'lobby', wx: 728, wy: 198 },
  },
  {
    id: 'agentChat',
    label: 'MAIA 對話',
    hint: '問它任何事,它會自己去查',
    keys: 'agent chat 對話 ai maia 助理 問',
    group: 'analysis',
    accent: 'max',
    glyph: 'AI',
    panel: 'agentChat',
    place: { zone: 'lobby', wx: 760, wy: 284 },
  },
  // ── 我的帳戶（大廳右下角三站）──
  // place 的座標抄自 rooms.ts 那三個 station 的互動範圍中心
  // （`frontOf` = 道具底部往上 26px、往下 60px），三個站位都是 y388。
  {
    id: 'holdings',
    label: '我的金庫',
    hint: '持倉艙位 · FIFO 成本 · 錢包餘額',
    keys: 'holdings 持倉 艙位 餘額 資產 position balance wallet vault',
    group: 'account',
    accent: 'green',
    glyph: 'HD',
    panel: 'holdings',
    place: { zone: 'lobby', wx: 576, wy: 388 },
  },
  {
    id: 'behavior',
    label: '交易性格',
    hint: '行為偏誤 · 風控防線 · AI 記住的偏好',
    keys: 'behavior 性格 行為 偏誤 風控 guard bias 偏好 traits',
    group: 'analysis',
    accent: 'green',
    glyph: 'BH',
    panel: 'behavior',
    place: { zone: 'lobby', wx: 692, wy: 388 },
  },
  {
    id: 'pnlDesk',
    label: '損益對帳',
    hint: '已實現損益 · 對帳差異 · 資金流',
    keys: 'pnl 損益 對帳 資金流 reconcile realized funds 出入金',
    group: 'account',
    accent: 'green',
    glyph: 'PL',
    panel: 'pnlDesk',
    place: { zone: 'lobby', wx: 812, wy: 388 },
  },
  // …隊友各自往下加一筆
];

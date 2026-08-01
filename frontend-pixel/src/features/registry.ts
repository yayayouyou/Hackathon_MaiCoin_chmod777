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
    place: { zone: 'guild', wx: 180, wy: 192 },
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
    place: { zone: 'guild', wx: 444, wy: 196 },
  },
  {
    id: 'trade',
    label: '現貨交易',
    hint: '行情 · 下單預覽 · 持倉',
    keys: 'trade 交易 下單 買 賣 order',
    group: 'account',
    accent: 'max',
    glyph: 'TR',
    panel: 'trade',
    // 大廳東翼 MAX 官方區的第一站。落點抄自 `makeLobby()` 的
    // frontOf(600,240,96,56) = (592,270,112,60)，站位在 (648,326)。
    place: { zone: 'lobby', wx: 648, wy: 320 },
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
    // frontOf(728,210,76,80) = (720,264,92,60)，站位在 (766,320)
    place: { zone: 'lobby', wx: 766, wy: 320 },
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
    // frontOf(836,208,96,84) = (828,266,112,60)，站位在 (884,322)
    place: { zone: 'lobby', wx: 884, wy: 320 },
  },
  {
    id: 'maxSupport',
    label: '官方客服',
    hint: '入金出金 · 手續費 · API · 帳戶安全',
    keys: 'support 客服 幫助 help faq 問題 入金 出金 手續費',
    group: 'system',
    accent: 'max',
    glyph: 'CS',
    panel: 'maxSupport',
    // 客服辦公區在東翼南側，站位在辦公室前庭 (836,466)。
    // frontOf(768,348,136,88) = (760,410,152,60)
    place: { zone: 'lobby', wx: 836, wy: 440 },
  },
  {
    id: 'agentChat',
    label: 'MAIA 對話',
    hint: '問它任何事,它會自己去查',
    keys: 'agent chat 對話 ai maia 助理 問',
    group: 'analysis',
    // MAIA 在世界裡是紫的，不是 MAX 藍 —— 它是我們自己的 agent，
    // 不是交易所的一個櫃檯。大廳裡它離 MAX 官方區 160px 遠、光池是全場
    // 唯一的紫色，這一格的顏色跟著世界走才不會互相矛盾。
    accent: 'violet',
    glyph: 'AI',
    panel: 'agentChat',
    // frontOf(376,214,64,80) = (368,268,80,60)，站位在 (408,324)
    place: { zone: 'lobby', wx: 408, wy: 320 },
  },
  // …隊友各自往下加一筆
];

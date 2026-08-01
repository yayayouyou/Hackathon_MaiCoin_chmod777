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
    // ⚠ 刻意沒有 place：客服辦公區已從大廳移除（那塊地讓給帳戶三站攤開），
    //   世界裡沒有對應的互動點了。沒有 place 的 feature 會被 FeatureBar 的
    //   runFeature() 直接 openPanel（見它的 fall-through），所以功能條與
    //   `/` 命令面板都照樣開得起來；tests/zones.mjs 的落點檢查也會跳過它
    //   （`if (!f.place) continue`）。要把客服放回世界的話，加一個 station
    //   之後再把 place 補回來。
  },
  {
    id: 'agentChat',
    label: 'MAIA 對話',
    hint: '問它任何事,它會自己去查',
    keys: 'agent chat 對話 ai maia 助理 問',
    group: 'analysis',
    // MAIA 用藍色 robot（accent:'max'），與東翼 MAX 官方區同色系；但它仍在
    // 中庭、不進 MAX 藍 zone —— 造型統一藍、空間上維持「MAIA 不是交易所櫃檯」。
    accent: 'max',
    glyph: 'AI',
    panel: 'agentChat',
    // robot(396,254)：frontOf(396,254,24,34)=(388,262,40,60)，站位落在框內
    place: { zone: 'lobby', wx: 408, wy: 300 },
  },
  // ── 我的帳戶（大廳東翼南側三站，藍上綠下；place 對齊 rooms.ts 新 frontOf 中心）──
  {
    id: 'holdings',
    label: '我的金庫',
    hint: '持倉艙位 · FIFO 成本 · 錢包餘額',
    keys: 'holdings 持倉 艙位 餘額 資產 position balance wallet vault',
    group: 'account',
    accent: 'green',
    glyph: 'HD',
    panel: 'holdings',
    // vault(594,392)：碰撞盒 y430..446，frontOf=(586,422,72,60)
    place: { zone: 'lobby', wx: 622, wy: 466 },
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
    // hologram(716,408)：碰撞盒 y436..448，frontOf=(708,422,56,60)
    place: { zone: 'lobby', wx: 736, wy: 466 },
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
    // board(822,400)：碰撞盒 y434..448，frontOf=(814,422,72,60)
    place: { zone: 'lobby', wx: 850, wy: 466 },
  },
  // ── 交易者公會（策略機器人房）──
  {
    id: 'strategyBots',
    label: '策略機器人',
    hint: '把回測策略打包成自動化 paper 機器人 · 選運行 · 看成交',
    keys: 'bot 機器人 策略 自動 回測 backtest strategy auto paper 打包 runner',
    group: 'analysis',
    accent: 'max',
    glyph: 'SB',
    panel: 'strategyBots',
    // robot(292,104)：frontOf=(284,112,40,60)，站位落在框內
    place: { zone: 'guild', wx: 304, wy: 150 },
  },
  // …隊友各自往下加一筆
];

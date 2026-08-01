import { definePanel, registerPanels, type PanelDef } from '../../engine/panel';
import { RankingBoard, RoomPicker } from './Rooms';
import { AgentReport } from './AgentReport';
import { Thread } from './Thread';
import { MaxNews, MaxEvents } from './Max';
import { AgentChat } from './AgentChat';
import { CharPanel } from './CharPanel';
import { Strategies } from './Strategies';
import { TradePanel } from './TradePanel';
import { MaxSupport } from './MaxSupport';
import { ThreadsAdmin } from './ThreadsAdmin';
import { Holdings } from './Holdings';
import { PnlDesk } from './PnlDesk';
import { Behavior } from './Behavior';

/**
 * ★ 全隊 append 點 2/4。
 *
 * 新增一個面板 = 上面一行 import + 下面一行 key。`App.tsx` 永遠不用改。
 * `as const satisfies` + `keyof typeof` 讓 PanelId 自動長出來，打錯字是
 * 紅色編譯錯誤而不是執行期的空面板。
 */
export const PANELS = {
  ranking: definePanel({ id: 'ranking', title: '熱門排行', Component: RankingBoard }),
  roomPicker: definePanel({ id: 'roomPicker', title: '選擇討論室', Component: RoomPicker }),
  agentReport: definePanel({ id: 'agentReport', title: 'Agent 分析報告', Component: AgentReport }),
  thread: definePanel({ id: 'thread', title: '玩家討論串', Component: Thread }),
  maxNews: definePanel({ id: 'maxNews', title: 'MAX 官方消息', Component: MaxNews }),
  maxEvents: definePanel({ id: 'maxEvents', title: 'MAX 最新活動', Component: MaxEvents }),
  agentChat: definePanel({ id: 'agentChat', title: 'MAIA 對話', Component: AgentChat }),
  char: definePanel({ id: 'char', title: '角色訊息窗', Component: CharPanel }),
  strategies: definePanel({ id: 'strategies', title: '策略牆', Component: Strategies }),
  trade: definePanel({ id: 'trade', title: 'MAX 現貨交易', Component: TradePanel }),
  maxSupport: definePanel({ id: 'maxSupport', title: 'MAX 官方客服', Component: MaxSupport }),
  threadsAdmin: definePanel({ id: 'threadsAdmin', title: 'MAIA 官方社群管理', Component: ThreadsAdmin }),
  // ── 大廳右下角「我的帳戶」三站（資料一律走 MAX API，見 api/account.ts）──
  holdings: definePanel({ id: 'holdings', title: '我的金庫', Component: Holdings }),
  pnlDesk: definePanel({ id: 'pnlDesk', title: '損益對帳台', Component: PnlDesk }),
  behavior: definePanel({ id: 'behavior', title: '交易性格', Component: Behavior }),
} as const satisfies Record<string, PanelDef>;

export type PanelId = keyof typeof PANELS;

/**
 * 灌進 `engine/panel.ts` 的執行期表。
 *
 * 讀取端（uiStore / App / validateWiring）一律查那張表而不是直接 import
 * 這個 barrel —— 否則 `uiStore → panels/index → 各面板 → uiStore` 會變成
 * 執行期循環相依，而且會讓 `PanelId = keyof typeof PANELS` 進入型別的
 * 循環推導。這一行是兩邊的接點。
 */
registerPanels(PANELS);

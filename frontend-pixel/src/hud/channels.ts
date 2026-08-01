import { live } from './live';

/**
 * ★ 全隊 append 點 3/4。
 *
 * 新增一個 HUD 數值 = 在 `hud` 這個物件裡加一行。撞名是編譯錯誤。
 * 這一輪只有型別與空通道，寫入端（`hud/feeds.ts`、`api/agent.ts`）
 * 與讀取端（`hud/blocks/*`）都由 C 軌落地。
 *
 * ⚠ 這裡只放「數值」。UI 開關狀態放 uiStore，不要放進來 ——
 *   live 通道沒有 React 訂閱語意，用它驅動骨架會拿不到重繪。
 */

/** agent 工具的資料來源。每顆工具晶片都要掛一個，這是 grounding 的憑證。 */
export type SourceTag = 'dna' | 'market' | 'max' | 'news' | 'local';

export type ToolStep = { name: string; source: SourceTag; detail: string; ok: boolean | null };

export type AgentPhase = 'idle' | 'thinking' | 'tool' | 'answering' | 'error';

/** live = 打得到後端且是即時；sample = 凍進 bundle 的快照；mock = 離線沙盒 */
export type DataSource = 'live' | 'sample' | 'mock';

export type Alert = { id: string; level: 'info' | 'warn' | 'danger'; text: string; at: number };

export type Ticker = { sym: string; last: number; change_pct: number };

export const hud = {
  tickers: live<Ticker[]>([]),
  portfolio: live<{ mv: number; unrealized: number } | null>(null),
  agent: live<{ phase: AgentPhase; steps: ToolStep[]; note: string; elapsed: number }>({
    phase: 'idle',
    steps: [],
    note: '',
    elapsed: 0,
  }),
  alerts: live<Alert[]>([]),
  /** 資料來源與 LLM 後端。不要假裝是即時的，評審看得出來 */
  meta: live<{ source: DataSource; llm: 'bedrock' | 'mock' | 'unknown' }>({
    source: 'mock',
    llm: 'unknown',
  }),
};

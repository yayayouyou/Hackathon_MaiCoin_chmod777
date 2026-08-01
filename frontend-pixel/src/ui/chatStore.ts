import { useSyncExternalStore } from 'react';
import {
  streamChat,
  loadSession,
  approveOrder as approveOrderApi,
  rejectOrder as rejectOrderApi,
  type AgentEvent,
  type ChatTurn,
  type ReplayStep,
} from '../api/agent';
import { hud, type SourceTag, type ToolStep } from '../hud/channels';

/**
 * MAIA 對話的狀態，放在模組層而不是元件裡。
 *
 * 理由只有一個，但它足夠：**dock 收起來再打開，對話不能消失**。
 * 原本 state 活在 `AgentChat` 元件內，`activePanel` 一變元件就卸載，
 * 現場只要誤按一次 ESC，前面問過的東西連同工具晶片全部歸零 ——
 * 那在 Live Demo 上就是重來一次。
 *
 * 串流中的文字**不在這裡**。一則 200 字的回答有數十個 delta，每個都
 * 通知訂閱者等於逼整個 dock 每秒重繪數十次。它走 `liveText` 這條命令式
 * 通道，由 dock 直接寫 `ref.textContent`，收完（final_answer）才進歷史。
 */

/** charts：本輪圖表卡快照（嵌入 + 重播）；tools：本輪用到的工具名（給分級免責）。 */
export type Msg = { id: number; who: 'agent' | 'me'; text: string; charts?: ChartItem[]; tools?: string[] };
export type Chip = { id: number; name: string; source: SourceTag; ok: boolean | null };
/** reader 攔截到疑似指令注入時留下的常駐警示（來源工具 + 命中的旗標名）。 */
export type ReaderAlert = { id: number; source: string; flags: string[] };
/** 一張圖表卡：留住 tool_result 的原始 result + 當初 tool_call 的 args（給卡片標題/去重用）。 */
export type ChartItem = { id: number; tool: string; result: unknown; args?: Record<string, unknown> };

export type ChatState = {
  msgs: Msg[];
  chips: Chip[];
  status: string;
  busy: boolean;
  approval: { summary: string; hash: string; token: string } | null;
  readerAlerts: ReaderAlert[];
  charts: ChartItem[];
};

const GREETING: Msg = {
  id: 0,
  who: 'agent',
  text: '我是 MAIA。你可以問我行情、你自己的交易紀錄，或是「如果當初…會怎樣」。我會自己去查資料再回答。',
};

let state: ChatState = {
  msgs: [GREETING],
  chips: [],
  status: '',
  busy: false,
  approval: null,
  readerAlerts: [],
  charts: [],
};

const subs = new Set<() => void>();
const emit = (patch: Partial<ChatState>): void => {
  state = { ...state, ...patch };
  for (const fn of subs) fn();
};

export const getChat = (): ChatState => state;

export function useChat(): ChatState {
  return useSyncExternalStore((fn) => {
    subs.add(fn);
    return () => void subs.delete(fn);
  }, getChat);
}

// ── 串流中的暫顯文字（不進 React） ──────────────────────────

let live = '';
const liveSubs = new Set<(s: string) => void>();

export const getLiveText = (): string => live;

/** dock 用它把 delta 直接寫進 `ref.textContent`。回傳退訂函式。 */
export function subscribeLive(fn: (s: string) => void): () => void {
  liveSubs.add(fn);
  return () => void liveSubs.delete(fn);
}

function setLive(s: string): void {
  live = s;
  for (const fn of liveSubs) fn(s);
}

// ── 工具名 → 給人看的中文與資料來源 ────────────────────────

/**
 * 查不到就退回原名，不要讓畫面出現空白。
 * `source` 決定晶片的顏色，也就是 grounding 的顏色編碼：
 * 紫 = 你自己的交易資料、MAX 藍 = 交易所、青 = 市場、琥珀 = 輿情。
 */
const TOOLS: Record<string, { label: string; source: SourceTag }> = {
  get_max_ticker: { label: 'MAX 行情', source: 'max' },
  get_max_kline: { label: 'MAX K 線', source: 'max' },
  get_max_klines: { label: 'MAX K 線', source: 'max' }, // 後端實際工具名是複數

  get_max_depth: { label: 'MAX 訂單簿', source: 'max' },
  get_max_accounts: { label: 'MAX 帳戶餘額', source: 'max' },
  get_max_my_trades: { label: 'MAX 成交紀錄', source: 'max' },
  analyze_trading_behavior: { label: '交易行為分析', source: 'dna' },
  get_trading_dna_score: { label: '交易 DNA', source: 'dna' },
  get_equity_curve: { label: '淨值曲線', source: 'dna' },
  compare_sell_vs_hold: { label: '反事實比較', source: 'dna' },
  get_open_positions: { label: '持倉', source: 'dna' },
  get_realized_pnl: { label: '已實現損益', source: 'dna' },
  run_analyst_desk: { label: '五層分析', source: 'market' },
  calculate_indicators: { label: '技術指標', source: 'market' },
  get_crypto_fear_and_greed_index: { label: '恐懼貪婪指數', source: 'market' },
  fetch_reddit_sentiment: { label: 'Reddit 輿情', source: 'news' },
  get_latest_crypto_news: { label: '加密新聞', source: 'news' },
};

export const toolLabel = (n: string): string => TOOLS[n]?.label ?? n;
export const toolSource = (n: string): SourceTag => TOOLS[n]?.source ?? 'local';

/**
 * 會產生「圖表卡」的工具（第一層：零相依 CSS/SVG 卡）。
 * 收到這些工具的 tool_result 時，把 result 留下來（過去這裡整包丟掉）；
 * 實際怎麼畫由 ui/vizCards 的 chartSpecFor(tool, result) 決定。
 */
const CHARTABLE_TOOLS = new Set<string>([
  'get_crypto_fear_and_greed_index',
  'get_max_depth',
  'get_max_accounts',
  'get_trading_dna_score',
  'analyze_trading_behavior',
  'get_max_klines', // 第二層：K 線蠟燭圖
  'get_equity_curve', // 第二層：淨值折線
]);

// tool_call 的 args 暫存（name → 依序的 args 佇列），tool_result 時取回配對，供圖表標題/去重。每輪重置。
let pendingArgs: Record<string, Array<Record<string, unknown>>> = {};

/** 從 args.market 或 result.market 取標的，作為同工具多圖的去重鍵。 */
function marketOf(tool: string, result: unknown, args?: Record<string, unknown>): string {
  if (args && typeof args.market === 'string') return args.market;
  if (result && typeof result === 'object' && !Array.isArray(result)) {
    const m = (result as { market?: unknown }).market;
    if (typeof m === 'string') return m;
  }
  return tool; // 沒有標的的工具（帳戶/DNA/淨值…）→ 用工具名當鍵，同工具留最新一張
}

/**
 * 工具是否失敗。後端執行失敗時 tool_result 的 result 會是 `{ error: ... }`
 * （見 agent/ollama_agent.py:303,315）。過去前端一律當成功、把失敗吞掉。
 */
function toolFailed(result: unknown): boolean {
  return (
    typeof result === 'object' &&
    result !== null &&
    'error' in result &&
    Boolean((result as { error?: unknown }).error)
  );
}

// ── 送出 ────────────────────────────────────────────────────

// ── session 身分（歷史存檔用）─────────────────────────────
// 每個對話一個 id（符合後端白名單 ^[A-Za-z0-9_-]{1,64}$）。送進 /api/chat 後端才會把
// 整段存成可重播 session；不送就永遠不存 —— 這正是先前 sessions/ 一直是空的原因。
function newSessionId(): string {
  return `s_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}
let currentSessionId = newSessionId();

let abort: AbortController | null = null;

/** dock 卸載時不呼叫這個 —— 收起 dock 不該中斷 agent，它會繼續查完。 */
export function cancel(): void {
  abort?.abort();
  abort = null;
}

/** 把工具晶片同步推進 HUD 的 agent 通道，讓面板關著也看得到它在做什麼。 */
function pushHud(phase: 'thinking' | 'tool' | 'answering' | 'idle' | 'error', note: string): void {
  const steps: ToolStep[] = state.chips.map((c) => ({
    name: toolLabel(c.name),
    source: c.source,
    detail: c.name,
    ok: c.ok,
  }));
  hud.agent.set({ phase, steps, note, elapsed: 0 });
}

export async function ask(question: string, model?: string): Promise<void> {
  const q = question.trim();
  if (!q || state.busy) return;

  const history: ChatTurn[] = [
    ...state.msgs
      .filter((m) => m.id !== 0)
      .map((m) => ({ role: (m.who === 'me' ? 'user' : 'assistant') as ChatTurn['role'], content: m.text })),
    { role: 'user', content: q },
  ];

  pendingArgs = {};
  setLive('');
  emit({
    msgs: [...state.msgs, { id: Date.now(), who: 'me', text: q }],
    chips: [],
    status: '',
    approval: null,
    readerAlerts: [],
    charts: [],
    busy: true,
  });
  pushHud('thinking', '讀題中…');

  const ac = new AbortController();
  abort = ac;

  const onEvent = (e: AgentEvent): void => {
    switch (e.type) {
      case 'status':
        emit({ status: e.content });
        pushHud('thinking', e.content);
        break;
      case 'tool_call':
        (pendingArgs[e.name] ??= []).push(e.args ?? {});
        emit({
          chips: [
            ...state.chips,
            { id: state.chips.length, name: e.name, source: toolSource(e.name), ok: null },
          ],
        });
        pushHud('tool', toolLabel(e.name));
        break;
      case 'tool_result': {
        const ok = !toolFailed(e.result);
        const patch: Partial<ChatState> = {};
        const i = state.chips.findIndex((x) => x.name === e.name && x.ok === null);
        if (i >= 0) {
          const next = [...state.chips];
          // 讀 result.error 決定 ✓/✗，別再把工具失敗一律當成功吞掉
          next[i] = { ...next[i]!, ok };
          patch.chips = next;
        }
        // 成功且可畫圖 → 留下 result（+配對的 tool_call args）；同工具同標的去重、保留最新一張
        if (ok && CHARTABLE_TOOLS.has(e.name) && e.result != null) {
          const args = (pendingArgs[e.name] ?? []).shift();
          const key = `${e.name}::${marketOf(e.name, e.result, args)}`;
          const idx = state.charts.findIndex((c) => `${c.tool}::${marketOf(c.tool, c.result, c.args)}` === key);
          const item: ChartItem = {
            id: idx >= 0 ? state.charts[idx]!.id : state.charts.length,
            tool: e.name,
            result: e.result,
            args,
          };
          if (idx >= 0) {
            const next = [...state.charts];
            next[idx] = item;
            patch.charts = next;
          } else {
            patch.charts = [...state.charts, item];
          }
        }
        if (Object.keys(patch).length > 0) emit(patch);
        pushHud('tool', toolLabel(e.name));
        break;
      }
      case 'reader':
        // AI 設計分的免費得分點：把「攔截了什麼」留成常駐警示卡，而不是一閃即逝的 status
        if (e.injection_detected) {
          emit({
            readerAlerts: [
              ...state.readerAlerts,
              {
                id: state.readerAlerts.length,
                source: e.name,
                flags: (e.flags ?? []).map((f) => f.label),
              },
            ],
          });
        }
        break;
      case 'answer_delta':
        setLive(live + e.content);
        pushHud('answering', '');
        break;
      case 'answer_reset':
        // 小模型會「邊講邊呼叫工具」，前導文字要清掉否則會留成假答案
        setLive('');
        break;
      case 'approval_request':
        emit({ approval: { summary: e.summary, hash: e.hash, token: e.token } });
        break;
      case 'final_answer': {
        // 把本輪的圖表卡快照 + 用到的工具名寫進這則訊息（嵌入 [圖表] 錨點 + 重播 + 分級免責），清空 live
        const turnCharts = state.charts;
        const turnTools = state.chips.map((c) => c.name);
        setLive('');
        emit({
          msgs: [
            ...state.msgs,
            { id: Date.now(), who: 'agent', text: e.content, charts: turnCharts, tools: turnTools },
          ],
          charts: [],
        });
        break;
      }
      case 'error':
        setLive('');
        emit({ msgs: [...state.msgs, { id: Date.now(), who: 'agent', text: `⚠ ${e.content}` }] });
        pushHud('error', e.content);
        break;
      default:
        break; // persona / thinking / thought 這一版先不呈現
    }
  };

  try {
    await streamChat(
      // persona:'auto' 讓後端自動依問題派角色（新手教練等），但前端不顯示大師 chip ——
      // persona 當「隱形能力」留在後端。sessionId 讓後端把整段存成可重播歷史。
      { messages: history, model, persona: 'auto', sessionId: currentSessionId, signal: ac.signal },
      onEvent,
    );
    // 串流結束但沒收到 final_answer（後端中途掛掉）→ 把暫顯的字收下來，
    // 不要讓使用者已經看到的字憑空消失
    if (live.trim()) {
      const t = live;
      const turnCharts = state.charts;
      const turnTools = state.chips.map((c) => c.name);
      setLive('');
      emit({
        msgs: [...state.msgs, { id: Date.now(), who: 'agent', text: t, charts: turnCharts, tools: turnTools }],
        charts: [],
      });
    }
  } catch (err) {
    if (!ac.signal.aborted) {
      setLive('');
      const why = err instanceof Error ? err.message : '連線異常';
      emit({
        msgs: [
          ...state.msgs,
          { id: Date.now(), who: 'agent', text: `⚠ ${why}。後端沒開的話，先在 agent-core 跑 uvicorn。` },
        ],
      });
    }
  } finally {
    if (abort === ac) abort = null;
    emit({ busy: false, status: '' });
    pushHud('idle', '');
  }
}

/** 開一個新對話：清空畫面、換一個新 session id（下一輪就會存成新的歷史檔）。 */
export function newConversation(): void {
  cancel();
  currentSessionId = newSessionId();
  setLive('');
  emit({ msgs: [GREETING], chips: [], status: '', approval: null, readerAlerts: [], charts: [], busy: false });
}

/**
 * 載入一段歷史 session 覆蓋目前對話（重播）。
 * v1 只還原文字（使用者訊息 + 每輪的 final_answer）；工具晶片與圖表另案。
 * 續存語意同舊 UI：載入後把 currentSessionId 設為該 session，接著講會接續存進同一檔。
 */
export async function loadSessionInto(id: string): Promise<void> {
  const detail = await loadSession(id);
  if (!detail) return;
  const msgs: Msg[] = [GREETING];
  let mid = 1;
  for (const turn of detail.turns) {
    if (turn.user) msgs.push({ id: mid++, who: 'me', text: turn.user });
    const fa = turn.steps.find((s) => s.type === 'final_answer');
    // 重播含圖表：掃這一輪的 tool_result，可畫圖的重建成 charts 掛到答案上
    const charts: ChartItem[] = turn.steps
      .filter((s): s is Extract<ReplayStep, { type: 'tool_result' }> => s.type === 'tool_result')
      .filter((s) => CHARTABLE_TOOLS.has(s.name))
      .map((s, i) => ({ id: i, tool: s.name, result: s.result }));
    const tools = turn.steps
      .filter((s): s is Extract<ReplayStep, { type: 'tool_call' }> => s.type === 'tool_call')
      .map((s) => s.name);
    if (fa && fa.type === 'final_answer')
      msgs.push({ id: mid++, who: 'agent', text: fa.content, charts, tools });
  }
  currentSessionId = id;
  setLive('');
  emit({ msgs, chips: [], status: '', approval: null, readerAlerts: [], charts: [], busy: false });
}

/** 核准這筆待核准下單：打後端執行，結果以一則訊息呈現，並清掉核准卡。 */
export async function approveOrder(): Promise<void> {
  const a = state.approval;
  if (!a) return;
  emit({ approval: null });
  const r = await approveOrderApi(a.token);
  emit({
    msgs: [
      ...state.msgs,
      { id: Date.now(), who: 'agent', text: r.ok ? `✅ 已核准並執行：${r.detail}` : `⚠ 核准失敗：${r.detail}` },
    ],
  });
}

/** 取消這筆待核准下單。 */
export async function rejectOrder(): Promise<void> {
  const a = state.approval;
  if (!a) return;
  emit({ approval: null });
  await rejectOrderApi(a.token);
  emit({ msgs: [...state.msgs, { id: Date.now(), who: 'agent', text: '已取消這筆待核准的下單。' }] });
}

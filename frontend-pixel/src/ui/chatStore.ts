import { useSyncExternalStore } from 'react';
import { streamChat, type AgentEvent, type ChatTurn } from '../api/agent';
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

export type Msg = { id: number; who: 'agent' | 'me'; text: string };
export type Chip = { id: number; name: string; source: SourceTag; ok: boolean | null };

export type ChatState = {
  msgs: Msg[];
  chips: Chip[];
  status: string;
  busy: boolean;
  approval: { summary: string; hash: string } | null;
};

const GREETING: Msg = {
  id: 0,
  who: 'agent',
  text: '我是 MAIA。你可以問我行情、你自己的交易紀錄，或是「如果當初…會怎樣」。我會自己去查資料再回答。',
};

let state: ChatState = { msgs: [GREETING], chips: [], status: '', busy: false, approval: null };

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

// ── 送出 ────────────────────────────────────────────────────

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

export async function ask(question: string): Promise<void> {
  const q = question.trim();
  if (!q || state.busy) return;

  const history: ChatTurn[] = [
    ...state.msgs
      .filter((m) => m.id !== 0)
      .map((m) => ({ role: (m.who === 'me' ? 'user' : 'assistant') as ChatTurn['role'], content: m.text })),
    { role: 'user', content: q },
  ];

  setLive('');
  emit({
    msgs: [...state.msgs, { id: Date.now(), who: 'me', text: q }],
    chips: [],
    status: '',
    approval: null,
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
        emit({
          chips: [
            ...state.chips,
            { id: state.chips.length, name: e.name, source: toolSource(e.name), ok: null },
          ],
        });
        pushHud('tool', toolLabel(e.name));
        break;
      case 'tool_result': {
        const i = state.chips.findIndex((x) => x.name === e.name && x.ok === null);
        if (i < 0) break;
        const next = [...state.chips];
        next[i] = { ...next[i]!, ok: true };
        emit({ chips: next });
        pushHud('tool', toolLabel(e.name));
        break;
      }
      case 'reader':
        // AI 設計分的免費得分點：把「攔截了什麼」講出來，而不是靜靜地過濾掉
        if (e.injection_detected) emit({ status: `已攔截疑似指令注入（來源：${toolLabel(e.name)}）` });
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
        emit({ approval: { summary: e.summary, hash: e.hash } });
        break;
      case 'final_answer':
        setLive('');
        emit({ msgs: [...state.msgs, { id: Date.now(), who: 'agent', text: e.content }] });
        break;
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
    await streamChat({ messages: history, signal: ac.signal }, onEvent);
    // 串流結束但沒收到 final_answer（後端中途掛掉）→ 把暫顯的字收下來，
    // 不要讓使用者已經看到的字憑空消失
    if (live.trim()) {
      const t = live;
      setLive('');
      emit({ msgs: [...state.msgs, { id: Date.now(), who: 'agent', text: t }] });
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

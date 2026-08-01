/**
 * MAIA agent 的 SSE 串流客戶端。
 *
 * 這是 `src/api/` 裡唯一一個不走 `settle()` 假資料的函式 —— 它直接打
 * `POST /api/chat`（由 vite proxy 代到 agent-core 的 FastAPI，所以永遠同源、
 * 不需要 CORS）。
 *
 * ⚠️ 三條紀律，違反任何一條都會壞掉既有的 156 項測試或現場 demo：
 *
 * 1. **只在使用者送出時才開連線，絕不在面板 mount 時開。**
 *    `tests/lib/harness.mjs` 用 `waitUntil:'networkidle'` 開頁；一條掛著的 SSE
 *    是 in-flight request，會讓 networkidle 永不觸發 → `page.goto` 撞 30s 逾時
 *    → 九個套件全部記成「套件中斷」。
 *
 * 2. **`?fast=1` 完全不打網路**，改吐一組硬編事件。測試與錄影都走這條，
 *    所以它同時是 demo 腳本的骨架。
 *
 * 3. **一定要帶 AbortSignal**，並綁在面板卸載與場景切換上。離開房間還在
 *    串流的話，回來時會有兩條連線同時寫同一個訊息。
 */

import { FLAGS } from '../game/core';

/** agent 送出的 12 種事件。名稱與 `agent/ollama_agent.py` 的 yield 一致。 */
export type AgentEvent =
  /** 每一輪 LLM 呼叫**之前**就會 yield，所以首個位元組來得很快 */
  | { type: 'status'; content: string; step: number; max_steps: number }
  | { type: 'persona'; key: string; name: string; icon: string }
  | { type: 'thinking'; content: string }
  | { type: 'thought'; content: string }
  | { type: 'tool_call'; name: string; args?: Record<string, unknown> }
  | { type: 'tool_result'; name: string; result?: unknown }
  /** Reader 淨化層。`injection_detected` 為 true 時值得在畫面上講出來 */
  | {
      type: 'reader';
      name: string;
      injection_detected?: boolean;
      // 後端（reader_agent.py）送的是 {label, snippet} 物件陣列，不是 string[]
      flags?: { label: string; snippet: string }[];
      reader_used?: boolean;
    }
  /** 下單互鎖：模型只能提議，要使用者按下確認才會執行 */
  | { type: 'approval_request'; name: string; token: string; plan: unknown; hash: string; summary: string }
  | { type: 'answer_delta'; content: string }
  /** 「邊講邊呼叫工具」的前導文字要清掉，否則會留在畫面上變成假答案 */
  | { type: 'answer_reset' }
  | { type: 'final_answer'; content: string }
  | { type: 'error'; content: string };

export type ChatTurn = { role: 'user' | 'assistant'; content: string };

export type ChatOptions = {
  messages: ChatTurn[];
  /** 空字串 = 讓後端用它自己的預設（環境變數 LLM_PROVIDER 決定的模型） */
  model?: string;
  /** 'default' 或六個大師之一；'auto' 讓後端自己分類 */
  persona?: string;
  sessionId?: string;
  signal?: AbortSignal;
};

/** `?fast=1` 用的離線腳本。順便就是 demo 錄影的分鏡。 */
const CANNED: AgentEvent[] = [
  { type: 'status', content: '讀題並挑選要用的資料來源…', step: 1, max_steps: 8 },
  { type: 'tool_call', name: 'get_max_ticker', args: { market: 'btctwd' } },
  { type: 'tool_result', name: 'get_max_ticker' },
  { type: 'tool_call', name: 'analyze_trading_behavior' },
  { type: 'tool_result', name: 'analyze_trading_behavior' },
  { type: 'final_answer', content: '這是離線示範模式（?fast=1）。實際回答由 MAIA agent 產生。' },
];

/**
 * 串流一輪對話。每收到一個事件就呼叫 `onEvent`。
 *
 * 解析邏輯與 `agent-core/agent_ui/templates/index.html:2910-2929` 相同：
 * SSE 的框架是「`data: <JSON>` + 空行」，所以用 `\n\n` 切塊、把最後一塊
 * （可能被 TCP 切一半）留在 buffer 裡等下一輪。
 */
export async function streamChat(opts: ChatOptions, onEvent: (e: AgentEvent) => void): Promise<void> {
  if (FLAGS.fast) {
    for (const e of CANNED) {
      if (opts.signal?.aborted) return;
      await new Promise((r) => setTimeout(r, 120));
      onEvent(e);
    }
    return;
  }

  /**
   * 事件間隔看門狗。
   *
   * 實測:LLM 供應商連不上時,後端不會回錯誤 —— 它 yield 完 persona 與 status
   * 之後就**無限掛著**。沒有這個計時器,畫面會永遠停在「讀題並挑選要用的
   * 資料來源…」,而且看起來像前端當掉。
   *
   * 間隔而不是總時長:一輪工具呼叫合理地會花 20-40 秒,但**兩個事件之間**
   * 不該超過這麼久 —— 後端每一輪 LLM 呼叫前都會先 yield status。
   */
  const IDLE_MS = 45_000;
  const watchdog = new AbortController();
  let timer = 0;
  const kick = () => {
    clearTimeout(timer);
    timer = setTimeout(() => watchdog.abort(), IDLE_MS) as unknown as number;
  };
  kick();

  // 使用者主動中斷(關面板/換場景)也要連帶取消看門狗那條
  const onUserAbort = () => watchdog.abort();
  opts.signal?.addEventListener('abort', onUserAbort, { once: true });

  const finish = () => {
    clearTimeout(timer);
    opts.signal?.removeEventListener('abort', onUserAbort);
  };

  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal: watchdog.signal,
    body: JSON.stringify({
      messages: opts.messages,
      model: opts.model ?? '',
      persona: opts.persona ?? 'default',
      session_id: opts.sessionId ?? '',
    }),
  });

  if (!res.ok || !res.body) {
    finish();
    throw new Error(`後端回應 ${res.status}${res.statusText ? ` ${res.statusText}` : ''}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      kick();                                    // 收到位元組就重新計時
      buffer += decoder.decode(value, { stream: true });

      const chunks = buffer.split('\n\n');
      // 最後一塊可能只收到一半，留著等下一個 TCP segment
      buffer = chunks.pop() ?? '';

      for (const chunk of chunks) {
        const line = chunk.trimStart();
        if (!line.startsWith('data:')) continue;   // `: ping` 心跳走這裡被略過
        const raw = line.slice(5).trim();
        if (!raw) continue;
        try {
          onEvent(JSON.parse(raw) as AgentEvent);
        } catch {
          // 單一事件壞掉不該讓整輪對話中斷 —— 後面的事件仍然有用
          onEvent({ type: 'error', content: `無法解析後端事件：${raw.slice(0, 80)}` });
        }
      }
    }
  } catch (e) {
    // 看門狗開火 vs 使用者主動關面板,對使用者是兩件不同的事:
    // 前者要講「逾時」,後者應該安靜收掉。
    if (watchdog.signal.aborted && !opts.signal?.aborted) {
      throw new Error(`${IDLE_MS / 1000} 秒沒有收到後端的任何回應,已中斷`);
    }
    throw e;
  } finally {
    finish();
    // abort 時 reader 已經是 released 狀態，cancel 會丟；吞掉即可
    reader.cancel().catch(() => {});
  }
}

/** 後端健康狀態。HUD 的「資料來源徽章」與 boot 的模式提示都讀它。 */
export type Health = { status?: string; provider?: string; model?: string };

export async function getHealth(signal?: AbortSignal): Promise<Health | null> {
  if (FLAGS.fast) return { status: 'ok', provider: 'demo', model: 'canned' };
  try {
    const res = await fetch('/api/config', { signal: signal ?? null });
    if (!res.ok) return null;
    return (await res.json()) as Health;
  } catch {
    return null;   // 後端沒開就是沒開，不要讓它變成畫面上的紅字
  }
}

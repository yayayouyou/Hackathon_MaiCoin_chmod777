import { useCallback, useEffect, useRef, useState } from 'react';
import { setViewInset } from '../../engine/viewport';
import { ask, loadSessionInto, newConversation, subscribeLive, toolLabel, useChat } from '../../ui/chatStore';
import { renderMarkdown } from '../../ui/markdown';
import { listSessions, type SessionSummary } from '../../api/agent';
import { closeChatDock, openChatDock, useDock } from '../dockStore';

/**
 * MAIA 側邊 dock —— **非模態**。世界在它旁邊繼續跑。
 *
 * 這是這一輪改動的核心。原本 MAIA 是 `<Panel>` 彈窗，而
 * `game/index.ts` 的 `frozen` 含 `activePanel !== null` ——
 * 也就是說「打開助理」與「世界停住」是同一件事。那正好毀掉這個專案
 * 最值錢的一段演出：agent 去查工具的那 20–40 秒，NPC 走去對應道具、
 * 工具晶片一顆一顆亮起來。把它搬進 `#hud-root` 之後：
 *
 * - 世界不凍：`dockStore` 不碰 `activePanel`，也不碰 `inputCaptured`
 * - 標籤不淡：`setLabelsVisible(!frozen)` 不再被觸發
 * - 對話不清空：state 在 `ui/chatStore.ts`，收合 dock 只是卸載 DOM
 *
 * ⚠ 串流文字走命令式 `ref.textContent`（`subscribeLive`），不進 React。
 *   一則 200 字的回答有數十個 delta，每個都 setState 等於逼整個 dock
 *   每秒重繪數十次 —— 而世界正在旁邊用同一顆 CPU 跑 60fps。
 */

const SUGGESTIONS = [
  '我的交易性格是什麼',
  'BTC 現在的行情如何',
  '如果當初買了就抱會怎樣',
  '這一年的手續費花了多少',
];

/** dock 展開時的寬度。同一個數字要餵給鏡頭，否則角色會躲進 dock 底下。 */
const DOCK_W = 340;

/**
 * 這個 workshop 帳號實測可用的 Claude 模型（opus-5/opus-4-8/sonnet-5 未授權）。
 * 清單寫死即可 —— 帳號授權在活動期間固定，不值得為它多開一個 /api/models 的
 * bedrock 分支。選到的 id 原封不動送進 POST /api/chat，後端 factory 認得含
 * anthropic/claude 的 id（見 agent/llm/factory.py）。
 */
const MODELS: ReadonlyArray<{ id: string; label: string }> = [
  { id: 'us.anthropic.claude-opus-4-5-20251101-v1:0', label: 'Opus 4.5' },
  { id: 'us.anthropic.claude-sonnet-4-6', label: 'Sonnet 4.6' },
  { id: 'us.anthropic.claude-sonnet-4-5-20250929-v1:0', label: 'Sonnet 4.5' },
  { id: 'us.anthropic.claude-haiku-4-5-20251001-v1:0', label: 'Haiku 4.5' },
];
const DEFAULT_MODEL = 'us.anthropic.claude-opus-4-5-20251101-v1:0';
const MODEL_KEY = 'maia-model';

/** ISO 時間 → 「MM-DD HH:mm」。不做 Date 解析，直接切字串（後端已是台北時間）。 */
const fmtWhen = (iso: string): string => (iso || '').slice(5, 16).replace('T', ' ');

function Elapsed({ busy }: { busy: boolean }) {
  const ref = useRef<HTMLSpanElement>(null);
  // rAF 而不是 setInterval —— `hud/feeds.ts` 是全 app 唯一的 setInterval。
  // 寫 textContent 而不是 setState，所以這顆秒數不會讓 dock 每秒重繪。
  useEffect(() => {
    if (!busy) return;
    const t0 = performance.now();
    let raf = 0;
    let last = -1;
    const tick = () => {
      const s = Math.floor((performance.now() - t0) / 1000);
      if (s !== last && ref.current) {
        last = s;
        ref.current.textContent = `${s}s`;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [busy]);
  return <span ref={ref} className="maia-elapsed" />;
}

export function AgentDock() {
  const { chat: open } = useDock();
  const { msgs, chips, status, busy, approval, readerAlerts } = useChat();
  const [text, setText] = useState('');
  // 選到的模型記在 localStorage，重整/收合再開都還在。無痕模式讀寫失敗就退回預設。
  const [model, setModel] = useState<string>(() => {
    try {
      return localStorage.getItem(MODEL_KEY) ?? DEFAULT_MODEL;
    } catch {
      return DEFAULT_MODEL;
    }
  });

  // 歷史對話抽屜。清單在打開時才抓（後端 GET /api/sessions），不常駐輪詢。
  const [historyOpen, setHistoryOpen] = useState(false);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [histLoading, setHistLoading] = useState(false);

  useEffect(() => {
    if (!historyOpen) return;
    let alive = true;
    setHistLoading(true);
    void listSessions()
      .then((s) => alive && setSessions(s))
      .finally(() => alive && setHistLoading(false));
    return () => {
      alive = false;
    };
  }, [historyOpen]);

  const liveRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  /**
   * 回報自己遮住多少畫布，鏡頭據此把死區往左推。
   * 收起來時要記得歸零 —— 否則世界會永遠留著一條看不見的邊界。
   */
  useEffect(() => {
    setViewInset({ right: open ? DOCK_W : 0 });
    return () => setViewInset({ right: 0 });
  }, [open]);

  // 串流文字的命令式通道。dock 重新掛載時要把已經串出來的字補回去，
  // 否則收合再打開會看到答案憑空少了一半。
  useEffect(() => {
    if (!open) return;
    const write = (s: string) => {
      const el = liveRef.current;
      if (!el) return;
      el.textContent = s;
      el.style.display = s ? '' : 'none';
    };
    return subscribeLive(write);
  }, [open]);

  useEffect(() => {
    if (open) endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [open, msgs, chips, status]);

  /** 遊戲式的呼叫方式：站在世界裡按 Enter 就開始跟 MAIA 講話。 */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
      if (e.key === 'Enter') {
        e.preventDefault();
        openChatDock();
        // 等 dock 掛上去再搶焦點
        requestAnimationFrame(() => inputRef.current?.focus());
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  const send = useCallback(
    (q: string) => {
      setText('');
      void ask(q, model);
    },
    [model],
  );

  if (!open) {
    return (
      <button className="maia-tab" onClick={openChatDock} aria-label="打開 MAIA 對話">
        <span className="maia-tab-glyph">AI</span>
        <span className="maia-tab-label">MAIA</span>
        <kbd>↵</kbd>
      </button>
    );
  }

  return (
    <aside className="maia-dock" style={{ width: DOCK_W }} data-testid="agent-dock">
      <header className="maia-dock-head">
        <span className="maia-dot" data-busy={busy ? '1' : '0'} />
        <h2>MAIA</h2>
        <span className="maia-sub">{busy ? status || '連線中…' : '隨時待命'}</span>
        <Elapsed busy={busy} />
        <button
          className="maia-hist"
          data-open={historyOpen ? '1' : '0'}
          onClick={() => setHistoryOpen((v) => !v)}
          title="歷史對話"
          aria-label="歷史對話"
        >
          歷史
        </button>
        <select
          className="maia-model"
          value={model}
          disabled={busy}
          title="切換 AI 模型（Opus 最強、Sonnet 平衡、Haiku 最快）"
          aria-label="切換 AI 模型"
          onChange={(e) => {
            const id = e.target.value;
            setModel(id);
            try {
              localStorage.setItem(MODEL_KEY, id);
            } catch {
              /* 無痕/隱私模式讀寫 localStorage 會丟；只在記憶體記著即可 */
            }
          }}
        >
          {MODELS.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
        <button
          className="maia-x"
          onClick={() => {
            closeChatDock();
            // 刻意**不** cancel()：收起 dock 不該中斷 agent。
            // 它會繼續查完，答案在你打開時就在那裡。
          }}
          aria-label="收起"
        >
          ✕
        </button>
      </header>

      {historyOpen && (
        <div className="maia-history" data-testid="history-drawer">
          <div className="maia-history-head">
            <button
              className="btn"
              onClick={() => {
                newConversation();
                setHistoryOpen(false);
              }}
            >
              ＋ 新對話
            </button>
            <button className="maia-x" onClick={() => setHistoryOpen(false)} aria-label="關閉歷史">
              ✕
            </button>
          </div>
          <div className="maia-history-list">
            {histLoading && <div className="chat-msg muted">載入中…</div>}
            {!histLoading && sessions.length === 0 && (
              <div className="chat-msg muted">還沒有歷史對話。開始聊天後會自動存檔。</div>
            )}
            {sessions.map((s) => (
              <button
                key={s.id}
                className="maia-history-item"
                title={s.title}
                onClick={() => {
                  void loadSessionInto(s.id);
                  setHistoryOpen(false);
                }}
              >
                <span className="maia-history-title">{s.title}</span>
                <span className="maia-history-meta">
                  {s.turns} 則 · {fmtWhen(s.updated)}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="maia-thread">
        {msgs.map((m) =>
          m.who === 'me' ? (
            // 使用者自己打的字維持純文字（React 會 escape），不當 markdown 解析
            <div key={m.id} className="chat-msg me">
              {m.text}
            </div>
          ) : (
            // MAIA 的回答渲染 markdown。renderMarkdown 先 escape 再套白名單標籤，
            // 輸出可安全餵給 dangerouslySetInnerHTML（見 ui/markdown.ts 的安全模型）。
            <div
              key={m.id}
              className="chat-msg chat-md"
              dangerouslySetInnerHTML={{ __html: renderMarkdown(m.text) }}
            />
          ),
        )}

        <div
          className="chat-msg"
          ref={liveRef}
          data-testid="agent-live"
          style={{ whiteSpace: 'pre-wrap', display: 'none' }}
        />

        {chips.length > 0 && (
          <div className="chips" data-testid="tool-chips" style={{ marginTop: 6 }}>
            {chips.map((c) => (
              <span
                key={c.id}
                className="chip maia-chip"
                data-src={c.source}
                data-state={c.ok === null ? 'pending' : c.ok ? 'ok' : 'fail'}
                title={`${toolLabel(c.name)} · _source: ${c.source} · ${c.name}`}
              >
                {c.ok === null ? <span className="spinner chip-spin" /> : c.ok ? '✓ ' : '✗ '}
                {toolLabel(c.name)}
              </span>
            ))}
          </div>
        )}

        {readerAlerts.map((a) => (
          <div key={a.id} className="maia-reader" data-testid="reader-alert">
            <strong>⚠ 已攔截疑似指令注入</strong>
            <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
              來源：{toolLabel(a.source)}
              {a.flags.length > 0 ? ` · 命中：${a.flags.join('、')}` : ''}
            </div>
          </div>
        ))}

        {approval && (
          <div className="maia-approval" data-testid="approval-card">
            <strong>需要你確認才會執行</strong>
            <div style={{ marginTop: 6 }}>{approval.summary}</div>
            <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
              計畫雜湊 {approval.hash.slice(0, 12)}… · 完整的核准流程在風控室
            </div>
          </div>
        )}

        {busy && (
          <div className="chat-msg muted" data-testid="agent-status">
            <span className="spinner" style={{ display: 'inline-block', verticalAlign: -2 }} />{' '}
            {status || '連線中…'}
          </div>
        )}

        <div ref={endRef} />
      </div>

      {msgs.length <= 1 && (
        <div className="chips maia-suggest">
          {SUGGESTIONS.map((s) => (
            <button key={s} className="chip" disabled={busy} onClick={() => send(s)}>
              {s}
            </button>
          ))}
        </div>
      )}

      <div className="composer maia-composer">
        <input
          ref={inputRef}
          type="text"
          placeholder="問我任何事…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && text.trim()) send(text);
            // ESC 把焦點還給世界，而不是關掉 dock —— 關掉的是 ✕
            if (e.key === 'Escape') (e.target as HTMLInputElement).blur();
          }}
        />
        <button className="btn btn-primary" disabled={!text.trim() || busy} onClick={() => send(text)}>
          送出
        </button>
      </div>
    </aside>
  );
}

import { useRef, useState } from 'react';
import { askBot, BOT_GREETING } from '../../api';
import { Panel } from '../Panel';

/**
 * MAX 官方客服機器人。
 *
 * 跟 MAIA 刻意分開：MAIA 是會查工具、做分析的 agent（非模態 dock，
 * 因為查工具要 20–40 秒，世界得繼續跑）；客服機器人是規則式 FAQ，
 * 問答在一秒內結束，模態彈窗反而更專注。
 *
 * 常見問題做成 chips：規則式機器人的能力邊界是固定的，直接把它能回答
 * 的主題攤在檯面上，比讓人猜關鍵字好 —— 猜不中的挫敗會讓人以為壞了。
 */

type Msg = { who: 'bot' | 'me'; text: string };

/** 對應 `api/mock.ts` 的 BOT_RULES。改那邊要同步改這裡。 */
const TOPICS = ['入金', '出金', '手續費', 'API 金鑰', '身分驗證', '帳戶安全', '系統維護'];

export function MaxSupport() {
  const [log, setLog] = useState<Msg[]>([{ who: 'bot', text: BOT_GREETING }]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const threadRef = useRef<HTMLDivElement>(null);

  const send = async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    setDraft('');
    setBusy(true);
    setLog((l) => [...l, { who: 'me', text: q }]);
    try {
      const reply = await askBot(q);
      setLog((l) => [...l, { who: 'bot', text: reply }]);
    } catch (e) {
      setLog((l) => [
        ...l,
        { who: 'bot', text: e instanceof Error ? `⚠ ${e.message}` : '⚠ 客服系統暫時無法回應' },
      ]);
    } finally {
      setBusy(false);
      // 捲到最新一則。等 state 落地後再捲，否則量到的是舊高度。
      requestAnimationFrame(() => {
        const el = threadRef.current;
        if (el) el.scrollTop = el.scrollHeight;
      });
    }
  };

  return (
    <Panel title="MAX 官方客服" accent="max" size="md">
      <div className="thread" ref={threadRef}>
        {log.map((m, i) => (
          <div key={i} className={`chat-msg${m.who === 'me' ? ' me' : ''}`}>
            {m.text}
          </div>
        ))}
        {busy && (
          <div className="chat-msg">
            <span className="spinner" />
          </div>
        )}
      </div>

      <div className="chips">
        {TOPICS.map((topic) => (
          <button key={topic} className="chip" disabled={busy} onClick={() => void send(topic)}>
            {topic}
          </button>
        ))}
      </div>

      <div className="composer">
        <input
          type="text"
          placeholder="輸入你的問題…"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void send(draft);
          }}
        />
        <button className="btn btn-primary" disabled={busy || !draft.trim()} onClick={() => void send(draft)}>
          送出
        </button>
      </div>

      <p className="warn" style={{ marginTop: 10 }}>
        這是規則式機器人，回答僅供參考。MAX 官方不會透過任何管道索取您的密碼、驗證碼或 API Secret Key。
      </p>
    </Panel>
  );
}

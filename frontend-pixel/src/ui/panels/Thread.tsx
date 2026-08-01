import { useEffect, useRef, useState } from 'react';
import { getThread, postMessage } from '../../api';
import type { Post } from '../../api/types';
import { useAsync } from '../useAsync';
import { Panel, AsyncState } from '../Panel';
import { toggleFavorite, useUI } from '../uiStore';

export function Thread() {
  const { roomId, roomTitle, nickname, favorites } = useUI();
  const { data, loading, error, reload } = useAsync(() => getThread(roomId ?? ''), [roomId]);
  const [extra, setExtra] = useState<Post[]>([]);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  // 換房間時清掉本地新增的留言，否則會跟著跑到別間去
  useEffect(() => setExtra([]), [roomId]);

  const posts = [...(data ?? []), ...extra];
  const fav = roomId !== null && favorites.includes(roomId);

  const send = async () => {
    const t = text.trim();
    if (!t || !roomId || sending) return;
    setSending(true);
    setText('');
    try {
      const post = await postMessage(roomId, nickname, t);
      setExtra((p) => [...p, post]);
      requestAnimationFrame(() => endRef.current?.scrollIntoView({ behavior: 'smooth' }));
    } catch {
      setText(t); // 送失敗把內容還給使用者，不要讓他重打
    } finally {
      setSending(false);
    }
  };

  return (
    <Panel title={`玩家討論 · ${roomTitle}`} size="md">
      <AsyncState loading={loading} error={error} onRetry={reload} />
      {data && (
        <>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: 12,
            }}
          >
            <span className="muted" style={{ fontSize: 12 }}>
              共 {posts.length} 則留言 · 你的暱稱是 <b style={{ color: 'var(--cyan)' }}>{nickname}</b>
            </span>
            {roomId && (
              <button className="chip" onClick={() => toggleFavorite(roomId)}>
                {fav ? '★ 已收藏' : '☆ 收藏這間'}
              </button>
            )}
          </div>

          <div className="thread">
            {posts.map((p) => (
              <div className={`post${p.self ? ' self' : ''}`} key={p.id}>
                <span className="av" style={{ background: p.color }} />
                <span>
                  <span className="meta">
                    <b style={{ color: p.color }}>{p.author}</b>
                    <span className="muted">{p.time}</span>
                    <span className="muted">♥ {p.likes}</span>
                  </span>
                  <span className="body">{p.text}</span>
                </span>
              </div>
            ))}
            <div ref={endRef} />
          </div>

          <div className="composer">
            <input
              type="text"
              placeholder="說點什麼…"
              maxLength={140}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && void send()}
            />
            <button className="btn btn-primary" disabled={!text.trim() || sending} onClick={() => void send()}>
              {sending ? '送出中' : '送出'}
            </button>
          </div>
        </>
      )}
    </Panel>
  );
}

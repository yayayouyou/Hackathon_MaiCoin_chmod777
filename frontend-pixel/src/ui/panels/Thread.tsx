import { useEffect, useRef, useState } from 'react';
import { archiveDiscussionSpace, getThread, postMessage, syncThread } from '../../api';
import { me } from '../../api/auth';
import type { Post } from '../../api/types';
import { useAsync } from '../useAsync';
import { Panel, AsyncState } from '../Panel';
import { toggleFavorite, useUI } from '../uiStore';

type ThreadItem = { post: Post; depth: number; parent?: Post };

function orderThreadPosts(posts: Post[]): ThreadItem[] {
  const byId = new Map(posts.map((post) => [post.id, post]));
  const children = new Map<string, Post[]>();
  const roots: Post[] = [];
  for (const post of posts) {
    if (post.parentPostId && byId.has(post.parentPostId)) {
      const siblings = children.get(post.parentPostId) ?? [];
      siblings.push(post);
      children.set(post.parentPostId, siblings);
    } else {
      roots.push(post);
    }
  }
  const ordered: ThreadItem[] = [];
  const visited = new Set<string>();
  const visit = (post: Post, depth: number, parent?: Post) => {
    if (visited.has(post.id)) return;
    visited.add(post.id);
    ordered.push({ post, depth, parent });
    for (const child of children.get(post.id) ?? []) visit(child, depth + 1, post);
  };
  for (const root of roots) visit(root, 0);
  // Retain malformed or cyclic legacy records instead of hiding them.
  for (const post of posts) visit(post, 0);
  return ordered;
}

export function Thread() {
  const { roomId, roomTitle, nickname, favorites } = useUI();
  const { data, loading, error, reload } = useAsync(() => getThread(roomId ?? ''), [roomId]);
  const { data: player } = useAsync(() => me(), []);
  const [extra, setExtra] = useState<Post[]>([]);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const [archived, setArchived] = useState(false);
  const [replyTo, setReplyTo] = useState<Post | null>(null);
  const [actionMessage, setActionMessage] = useState('');
  const endRef = useRef<HTMLDivElement>(null);

  // 換房間時清掉前一間房的暫存狀態，避免回覆到錯誤討論串。
  useEffect(() => {
    setExtra([]);
    setReplyTo(null);
    setActionMessage('');
    setText('');
    setArchived(false);
  }, [roomId]);

  const posts = [...(data ?? []), ...extra];
  const orderedPosts = orderThreadPosts(posts);
  const fav = roomId !== null && favorites.includes(roomId);

  const send = async () => {
    const t = text.trim();
    if (!t || !roomId || sending) return;
    setSending(true); setActionMessage('');
    setText('');
    try {
      const post = await postMessage(roomId, t, replyTo?.id);
      setExtra((p) => [...p, post]);
      setReplyTo(null);
      // 留言一定已經進 DB；Threads 是鏡像，失敗時不能說「已同步」。
      setActionMessage(post.syncState === 'published'
        ? '留言已發布至 MAIA，並同步到 Threads。'
        : '留言已存到 MAIA。Threads 暫時無法發布，下次同步會自動補送。');
      requestAnimationFrame(() => endRef.current?.scrollIntoView({ behavior: 'smooth' }));
    } catch (error) {
      setText(t); // 送失敗把內容還給使用者，不要讓他重打
      setActionMessage(`留言未發布：${error instanceof Error ? error.message : '未知錯誤'}`);
    } finally {
      setSending(false);
    }
  };

  const sync = async () => {
    if (!roomId || syncing) return;
    setSyncing(true); setActionMessage('');
    try {
      const result = await syncThread(roomId);
      setExtra([]);
      reload();
      const errors = result.mention_errors + result.reply_errors + result.publish_errors;
      const sent = result.published ? `補送 ${result.published} 則待同步留言、` : '';
      setActionMessage(errors ? `同步完成，但有 ${errors} 項 Threads 操作失敗，請稍後再試。` : `同步完成：${sent}匯入 ${result.replies} 則 Threads 回覆。`);
    } catch (error) {
      setActionMessage(`同步失敗：${error instanceof Error ? error.message : '未知錯誤'}`);
    } finally {
      setSyncing(false);
    }
  };

  const archive = async () => {
    if (!roomId || archiving || !window.confirm('封存此討論區？Threads 原文會保留，但平台將不再顯示此區。')) return;
    setArchiving(true); setActionMessage('');
    try {
      await archiveDiscussionSpace(roomId);
      setActionMessage('討論區已封存；Threads 原文仍會保留。');
      setArchived(true);
      setReplyTo(null);
      setText('');
    } catch (error) {
      setActionMessage(`封存失敗：${error instanceof Error ? error.message : '未知錯誤'}`);
    } finally { setArchiving(false); }
  };

  return (
    <Panel title={`玩家討論 · ${roomTitle}`} size="md">
      <AsyncState loading={loading} error={error} onRetry={reload} />
      {data && (
        <>
          {actionMessage && <p className="muted" role="status" style={{ fontSize: 12, marginBottom: 10 }}>{actionMessage}</p>}
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

          {!archived && player?.role === 'official' && <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
            <span style={{ display: 'flex', gap: 8 }}>
              <button className="chip" disabled={!roomId || syncing} onClick={() => void sync()}>{syncing ? '同步中…' : '同步 Threads'}</button>
              <button className="chip" disabled={!roomId || archiving} onClick={() => void archive()}>{archiving ? '封存中…' : '封存討論區'}</button>
            </span>
          </div>}
          <div className="thread">
            {orderedPosts.map(({ post: p, depth, parent }) => (
              <div
                className={`post${p.self ? ' self' : ''}`}
                key={p.id}
                style={depth ? { marginLeft: Math.min(depth, 4) * 28, borderLeft: '2px solid var(--line)', paddingLeft: 12 } : undefined}
              >
                <span className="av" style={{ background: p.color }} />
                <span>
                  <span className="meta">
                    <b style={{ color: p.color }}>{p.author}</b>
                    {p.authorRole === 'official' && <span style={{ color: 'var(--amber)' }}>官方</span>}
                    {p.source === 'threads' && <span className="muted">Threads · @{p.sourceAuthor ?? 'unknown'}</span>}
                    {p.permalink && <a className="muted" href={p.permalink} target="_blank" rel="noreferrer">查看原貼</a>}
                    <span className="muted">{p.time}</span>
                    <span className="muted">♥ {p.likes}</span>
                    {p.syncState === 'local' && <span className="muted" title="已存到 MAIA，Threads 尚未發布成功">⏳ 尚未同步到 Threads</span>}
                  </span>
                  <span className="body">{p.text}</span>
                  {parent && <span className="muted">↳ 回覆 @{parent.sourceAuthor ?? parent.author}</span>}
                  <button className="chip" onClick={() => setReplyTo(p)}>回覆</button>
                </span>
              </div>
            ))}
            <div ref={endRef} />
          </div>

          {!archived && <div className="composer">
            {replyTo && <span className="muted">正在回覆 @{replyTo.sourceAuthor ?? replyTo.author} <button className="chip" onClick={() => setReplyTo(null)}>取消</button></span>}
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
          </div>}
        </>
      )}
    </Panel>
  );
}

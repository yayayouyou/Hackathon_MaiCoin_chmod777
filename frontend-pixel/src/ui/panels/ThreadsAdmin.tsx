import { useState } from 'react';
import { deleteOfficialThreadsRoot, generateCommunityInsights, listDiscussionSpaces, syncThreadsMentions } from '../../api';
import { me } from '../../api/auth';
import { AsyncState, Panel } from '../Panel';
import { useAsync } from '../useAsync';

export function ThreadsAdmin() {
  const { data, loading, error, reload } = useAsync(() => listDiscussionSpaces(true), []);
  const { data: player } = useAsync(() => me(), []);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [syncing, setSyncing] = useState(false);
  const [generatingInsights, setGeneratingInsights] = useState(false);
  const removeRemote = async (id: string, title: string) => {
    if (busy || !window.confirm(`確定永久刪除「${title}」的 MAIA 官方 Threads 貼文？\n\n不會刪除任何外部使用者的原始貼文。`)) return;
    setBusy(id); setMessage('');
    try { await deleteOfficialThreadsRoot(id); setMessage('MAIA 官方貼文已刪除，平台討論區已封存。'); reload(); }
    catch (error) { setMessage(`刪除失敗：${error instanceof Error ? error.message : '未知錯誤'}`); }
    finally { setBusy(null); }
  };
  const syncMentions = async () => {
    if (syncing) return;
    setSyncing(true); setMessage('');
    try {
      const result = await syncThreadsMentions();
      setMessage(result.busy ? '已有同步作業進行中，請稍後重新整理。' : result.errors ? 'Threads 讀取暫時失敗，請稍後重試。' : `同步完成：新增 ${result.created} 個討論區。`);
      reload();
    } catch (error) { setMessage(`同步失敗：${error instanceof Error ? error.message : '未知錯誤'}`); }
    finally { setSyncing(false); }
  };
  const generateInsights = async () => {
    if (generatingInsights) return;
    setGeneratingInsights(true); setMessage('');
    try {
      const result = await generateCommunityInsights();
      setMessage(`${result.date} 社群洞察已產生：${result.rooms} 個討論區與 1 份全站總覽。`);
    } catch (error) {
      setMessage(`社群洞察產生失敗：${error instanceof Error ? error.message : '未知錯誤'}`);
    } finally { setGeneratingInsights(false); }
  };
  return <Panel title="MAIA 官方社群管理" size="md">
    {player?.role !== 'official' ? <p className="muted">此功能限官方帳號使用。</p> : <>
    <p className="muted" style={{ fontSize: 12 }}>官方專用。一般封存不會刪 Threads；此頁的刪除不可復原。</p>
    <button className="btn btn-primary" disabled={syncing} onClick={() => void syncMentions()}>{syncing ? '同步中…' : '同步 @MAIA 新話題'}</button>
    <button className="btn" style={{ marginLeft: 8 }} disabled={generatingInsights} onClick={() => void generateInsights()}>
      {generatingInsights ? '整理今日討論中…' : '產生今日社群洞察'}
    </button>
    {message && <p className="muted" style={{ fontSize: 12 }}>{message}</p>}
    <AsyncState loading={loading} error={error} onRetry={reload} />
    {data?.map((space) => <div key={space.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, borderBottom: '1px solid var(--line)', padding: '12px 0' }}>
      <span style={{ minWidth: 0 }}><b style={{ display: 'block', overflowWrap: 'anywhere' }}>{space.title}</b><span className="muted">{space.archived ? '已封存' : '進行中'} · {space.threads_root_id ? 'Threads 已連結' : '尚未連結'}{space.source_threads_id ? ' · 外部貼文匯入' : ''}</span>{space.source_threads_id && <small className="muted" style={{ display: 'block', marginTop: 3 }}>刪除僅移除 MAIA 官方同步貼文，不會影響原發文者貼文。</small>}</span>
      <button className="chip" style={{ flexShrink: 0 }} disabled={!space.threads_root_id || !!space.threads_deleted_at || busy === space.id} onClick={() => void removeRemote(space.id, space.title)}>{busy === space.id ? '刪除中…' : space.threads_deleted_at ? '已刪除' : '刪除 MAIA 官方貼文'}</button>
    </div>)}
    </>}
  </Panel>;
}

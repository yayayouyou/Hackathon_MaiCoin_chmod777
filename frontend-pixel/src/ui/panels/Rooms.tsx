import { useMemo, useState } from 'react';
import { createDiscussionSpace, getRooms } from '../../api';
import { me } from '../../api/auth';
import type { RoomInfo } from '../../api/types';
import { useAsync } from '../useAsync';
import { Panel, AsyncState } from '../Panel';
import { openPanel, toggleFavorite, travelTo, useUI } from '../uiStore';

/**
 * 大廳看板與傳送門選房共用同一份資料與同一種列。
 * 兩者的差別只在「排名編號」與「搜尋篩選」，沒必要拆成兩套元件。
 */
function RoomRow({ room, no }: { room: RoomInfo; no?: number }) {
  const { favorites } = useUI();
  const fav = favorites.includes(room.id);
  const enter = () => travelTo('discussion', { id: room.id, title: room.topic, accent: room.accent, tag: room.tag, online: room.online, sentiment: room.sentiment });

  return (
    <div
      className="rank-row"
      role="button"
      tabIndex={0}
      onClick={enter}
      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), enter())}
    >
      <span className="no" data-top={no !== undefined && no <= 3}>
        {no ?? '·'}
      </span>
      <span>
        <span className="topic">{room.topic}</span>
        <span className="tag">{room.tag}</span>
      </span>
      <span className="num muted online" title="在線人數">
        {room.online} 人
      </span>
      <span className={`num ${room.change >= 0 ? 'up' : 'down'}`} title="24 小時熱度變化">
        {room.change >= 0 ? '▲' : '▼'} {Math.abs(room.change).toFixed(1)}%
      </span>
      <button
        className="star"
        data-on={fav}
        title={fav ? '取消收藏' : '收藏'}
        onClick={(e) => {
          e.stopPropagation();
          toggleFavorite(room.id);
        }}
      >
        {fav ? '★' : '☆'}
      </button>
    </div>
  );
}

/** 大廳中央的實體看板：純排行，走近按 E 打開。 */
export function RankingBoard() {
  const { data, loading, error, reload } = useAsync(() => getRooms(), []);

  return (
    <Panel title="熱門討論室排行" size="md">
      <AsyncState loading={loading} error={error} onRetry={reload} />
      {data && (
        <>
          <p className="muted" style={{ marginBottom: 12, fontSize: 12 }}>
            依 24 小時討論熱度排序，每 15 分鐘更新。點一列即可傳送過去。
          </p>
          {data.map((r, i) => (
            <RoomRow key={r.id} room={r} no={i + 1} />
          ))}
        </>
      )}
    </Panel>
  );
}

/** 討論區傳送門：搜尋、標籤篩選、我的收藏。 */
export function RoomPicker() {
  const { data, loading, error, reload } = useAsync(() => getRooms(), []);
  const { data: player } = useAsync(() => me(), []);
  const { favorites } = useUI();
  const [q, setQ] = useState('');
  const [tag, setTag] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [openingText, setOpeningText] = useState('');
  const [creating, setCreating] = useState(false);
  const [createMessage, setCreateMessage] = useState('');

  const tags = useMemo(() => [...new Set((data ?? []).map((r) => r.tag))], [data]);
  const shown = useMemo(() => {
    const kw = q.trim().toLowerCase();
    return (data ?? []).filter(
      (r) =>
        (!tag || r.tag === tag) &&
        (!kw || r.topic.toLowerCase().includes(kw) || r.tag.toLowerCase().includes(kw)),
    );
  }, [data, q, tag]);

  const favRooms = (data ?? []).filter((r) => favorites.includes(r.id));

  const create = async () => {
    if (!title.trim() || !openingText.trim() || creating) return;
    setCreating(true); setCreateMessage('');
    try {
      await createDiscussionSpace(title.trim(), openingText.trim());
      setTitle('');
      setOpeningText('');
      setCreateMessage('討論區已建立，首篇內容已發布為 MAIA 官方 Threads 根文。');
      reload();
    } catch (error) {
      setCreateMessage(`建立失敗：${error instanceof Error ? error.message : '未知錯誤'}`);
    } finally {
      setCreating(false);
    }
  };

  return (
    <Panel title="選擇討論室" size="md">
      <AsyncState loading={loading} error={error} onRetry={reload} />
      {data && (
        <>
          <div className="search">
            <input
              type="text"
              placeholder="搜尋主題或標籤…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              autoFocus
            />
          </div>
          {player && <div className="composer" style={{ marginBottom: 14 }}>
            <input value={title} maxLength={120} placeholder="建立新討論區：主題" onChange={(e) => setTitle(e.target.value)} />
            <input value={openingText} maxLength={460} placeholder="首篇內容（最多 460 字，將由 MAIA 官方發為 Threads 根文）" onChange={(e) => setOpeningText(e.target.value)} />
            <button className="btn btn-primary" disabled={creating || !title.trim() || !openingText.trim()} onClick={() => void create()}>
              {creating ? '建立中…' : '建立討論區'}
            </button>
          </div>}
          {createMessage && <p className="muted" role="status" style={{ fontSize: 12, marginTop: -8, marginBottom: 12 }}>{createMessage}</p>}
          {player?.role === 'official' && <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 10 }}>
            <button className="chip" onClick={() => openPanel('threadsAdmin')}>MAIA 官方社群管理</button>
          </div>}
          <div className="chips" style={{ marginBottom: 14 }}>
            <button className="chip" style={{ color: tag ? undefined : 'var(--cyan)' }} onClick={() => setTag(null)}>
              全部
            </button>
            {tags.map((t) => (
              <button
                key={t}
                className="chip"
                style={{ color: tag === t ? 'var(--cyan)' : undefined }}
                onClick={() => setTag(t === tag ? null : t)}
              >
                {t}
              </button>
            ))}
          </div>

          {favRooms.length > 0 && !q && !tag && (
            <>
              <h3 style={{ fontSize: 11, letterSpacing: '0.16em', color: 'var(--amber)', marginBottom: 6 }}>
                ★ 我的收藏
              </h3>
              {favRooms.map((r) => (
                <RoomRow key={r.id} room={r} />
              ))}
              <div style={{ height: 18 }} />
            </>
          )}

          <h3 style={{ fontSize: 11, letterSpacing: '0.16em', color: 'var(--dim)', marginBottom: 6 }}>
            {q || tag ? `搜尋結果（${shown.length}）` : '全部討論室'}
          </h3>
          {shown.length === 0 ? (
            <div className="empty">沒有符合的討論室</div>
          ) : (
            shown.map((r) => <RoomRow key={r.id} room={r} />)
          )}
        </>
      )}
    </Panel>
  );
}

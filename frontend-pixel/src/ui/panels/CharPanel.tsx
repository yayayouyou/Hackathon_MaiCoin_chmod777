import { useState } from 'react';
import { getRooms } from '../../api';
import { useAsync } from '../useAsync';
import { Panel, AsyncState } from '../Panel';
import { setNickname, toggleFavorite, travelTo, useUI } from '../uiStore';
import { Trade } from './Trade';
import { CharPicker } from '../../boot/CharPicker';

export function CharPanel() {
  // 「交易」維持預設分頁。外觀是進來之後才會想調的東西，不該擋在
  // 每次按 I 都要看到的位置上。
  const [tab, setTab] = useState<'trade' | 'fav' | 'look'>('trade');
  const { nickname, favorites } = useUI();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(nickname);

  return (
    <Panel title="角色訊息窗" size="lg">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <div className="tabs" style={{ flex: 1, marginBottom: 14 }}>
          <button aria-selected={tab === 'trade'} onClick={() => setTab('trade')}>
            交易
          </button>
          <button aria-selected={tab === 'fav'} onClick={() => setTab('fav')}>
            收藏的討論室（{favorites.length}）
          </button>
          <button aria-selected={tab === 'look'} onClick={() => setTab('look')}>
            外觀
          </button>
        </div>
        <div style={{ marginBottom: 14, display: 'flex', gap: 6, alignItems: 'center' }}>
          {editing ? (
            <>
              <input
                type="text"
                value={draft}
                maxLength={16}
                style={{ width: 130 }}
                autoFocus
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && (setNickname(draft), setEditing(false))}
              />
              <button
                className="btn"
                onClick={() => {
                  setNickname(draft);
                  setEditing(false);
                }}
              >
                儲存
              </button>
            </>
          ) : (
            <button
              className="chip"
              onClick={() => {
                setDraft(nickname);
                setEditing(true);
              }}
            >
              {nickname} ✎
            </button>
          )}
        </div>
      </div>

      {tab === 'trade' && <Trade />}
      {tab === 'fav' && <Favorites />}
      {tab === 'look' && <Look />}
    </Panel>
  );
}

/**
 * 外觀設定。選了立刻生效 —— 面板還開著，世界裡的角色就已經換好了
 * （`setCharacter()` 會直接呼叫 `world.setSkin()`），不需要按「儲存」，
 * 也不需要回進場畫面。
 */
function Look() {
  return (
    <>
      <p className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
        點一個就換。選擇會記在這台瀏覽器上，下次進來還是同一個。
      </p>
      <CharPicker scale={4} />
      <p className="muted" style={{ fontSize: 12, marginTop: 12 }}>
        外觀只影響長相，不影響 MAIA 的分析結果，也不會送給後端。
      </p>
    </>
  );
}

function Favorites() {
  const { favorites } = useUI();
  const { data, loading, error, reload } = useAsync(() => getRooms(), []);

  if (favorites.length === 0) {
    return (
      <div className="empty">
        還沒有收藏任何討論室。
        <br />
        在排行看板或討論室裡按 ☆ 就會加進來。
      </div>
    );
  }

  const rooms = (data ?? []).filter((r) => favorites.includes(r.id));

  return (
    <>
      <AsyncState loading={loading} error={error} onRetry={reload} />
      {data && (
        <>
          <p className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
            點一列直接傳送過去，不用先回大廳。
          </p>
          {rooms.map((r) => (
            <div
              className="rank-row"
              key={r.id}
              role="button"
              tabIndex={0}
              onClick={() => travelTo('discussion', { id: r.id, title: r.topic, accent: r.accent, tag: r.tag, online: r.online, sentiment: r.sentiment })}
              onKeyDown={(e) =>
                e.key === 'Enter' &&
                travelTo('discussion', { id: r.id, title: r.topic, accent: r.accent, tag: r.tag, online: r.online, sentiment: r.sentiment })
              }
            >
              <span className="no">★</span>
              <span>
                <span className="topic">{r.topic}</span>
                <span className="tag">{r.tag}</span>
              </span>
              <span className="num muted online">{r.online} 人</span>
              <span className={`num ${r.change >= 0 ? 'up' : 'down'}`}>
                {r.change >= 0 ? '▲' : '▼'} {Math.abs(r.change).toFixed(1)}%
              </span>
              <button
                className="star"
                data-on="true"
                title="取消收藏"
                onClick={(e) => {
                  e.stopPropagation();
                  toggleFavorite(r.id);
                }}
              >
                ★
              </button>
            </div>
          ))}
        </>
      )}
    </>
  );
}

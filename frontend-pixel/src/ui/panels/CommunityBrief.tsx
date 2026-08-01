import { getLobbyCommunityInsight } from '../../api';
import { useAsync } from '../useAsync';
import { AsyncState, Panel } from '../Panel';
import { CommunityInsightCard } from './CommunityInsightCard';

export function CommunityBrief() {
  const { data, loading, error, reload } = useAsync(() => getLobbyCommunityInsight(), []);

  return (
    <Panel title="昨日全站社群焦點" accent="violet" size="md">
      <AsyncState loading={loading} error={error} onRetry={reload} />
      {!loading && !error && !data && (
        <div className="state">
          <p>昨日摘要尚未產生。</p>
          <p className="muted" style={{ fontSize: 12 }}>官方帳號可在社群管理頁手動產生。</p>
        </div>
      )}
      {data && (
        <>
          <CommunityInsightCard insight={data} />
          {data.rooms && data.rooms.length > 0 && (
            <>
              <h3 style={{ fontSize: 12, letterSpacing: '0.14em', color: 'var(--cyan)', marginBottom: 8 }}>各討論區焦點</h3>
              {data.rooms.map((room) => (
                <div key={room.room_id} style={{ borderBottom: '1px solid var(--line)', padding: '9px 0' }}>
                  <b>{room.title}</b>
                  <span className="muted" style={{ display: 'block', fontSize: 12 }}>{room.headline}</span>
                </div>
              ))}
            </>
          )}
          <p className="muted" style={{ fontSize: 11, marginTop: 14 }}>
            由 {data.model} 產生 · {new Date(data.generated_at).toLocaleString()}
          </p>
        </>
      )}
    </Panel>
  );
}

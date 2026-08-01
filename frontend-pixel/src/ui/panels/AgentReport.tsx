import { getRoomCommunityInsight } from '../../api';
import { AsyncState, Panel } from '../Panel';
import { useAsync } from '../useAsync';
import { useUI } from '../uiStore';
import { CommunityInsightCard } from './CommunityInsightCard';

export function AgentReport() {
  const { roomId, roomTitle } = useUI();
  const { data, loading, error, reload } = useAsync(
    () => roomId ? getRoomCommunityInsight(roomId) : Promise.resolve(null),
    [roomId],
  );

  return (
    <Panel title={`今日社群摘要 · ${roomTitle}`} accent="violet" size="md">
      <AsyncState loading={loading} error={error} onRetry={reload} />
      {!loading && !error && !data && (
        <div style={{ border: '1px solid var(--line)', padding: 16 }}>
          <p style={{ marginBottom: 6 }}>今日社群摘要尚未產生。</p>
          <p className="muted" style={{ fontSize: 12 }}>留言同步後，MAIA 會整理本討論區的焦點、分歧與社群情緒。</p>
        </div>
      )}
      {data && <CommunityInsightCard insight={data} />}
    </Panel>
  );
}

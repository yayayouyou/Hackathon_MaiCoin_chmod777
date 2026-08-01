import { useState } from 'react';
import { getReport } from '../../api';
import { useAsync } from '../useAsync';
import { Panel, AsyncState } from '../Panel';
import { DemoData } from '../DemoData';
import { useUI } from '../uiStore';

type Tab = 'summary' | 'detail' | 'sources';

export function AgentReport() {
  const { roomId, roomTitle } = useUI();
  const { data, loading, error, reload } = useAsync(() => getReport(roomId ?? ''), [roomId]);
  const [tab, setTab] = useState<Tab>('summary');

  return (
    <Panel title={`Agent 分析報告 · ${roomTitle}`} accent="violet" size="md">
      <DemoData what="房間情緒分析報告" />
      <AsyncState loading={loading} error={error} onRetry={reload} />
      {data && (
        <>
          <div className="tabs">
            {(
              [
                ['summary', '摘要'],
                ['detail', '詳細分析'],
                ['sources', '資料來源'],
              ] as const
            ).map(([k, label]) => (
              <button key={k} aria-selected={tab === k} onClick={() => setTab(k)}>
                {label}
              </button>
            ))}
          </div>

          {tab === 'summary' && (
            <>
              <div className="sentiment">
                <span style={{ fontSize: 11, letterSpacing: '0.1em', color: 'var(--dim)' }}>情緒</span>
                <div className="gauge">
                  {/* -100..100 對應 0..100%，指針位置就是情緒分數 */}
                  <i style={{ left: `calc(${(data.sentiment + 100) / 2}% - 1px)` }} />
                </div>
                <span className={`num ${data.sentiment >= 0 ? 'up' : 'down'}`} style={{ width: 44, textAlign: 'right' }}>
                  {data.sentiment > 0 ? '+' : ''}
                  {data.sentiment}
                </span>
              </div>
              <p style={{ marginBottom: 14 }}>{data.summary}</p>
              <h3 style={{ fontSize: 12, letterSpacing: '0.14em', color: 'var(--rose)', marginBottom: 6 }}>
                風險提示
              </h3>
              <ul className="risks">
                {data.risks.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
              <p className="muted" style={{ fontSize: 11, marginTop: 16 }}>
                更新於 {data.updatedAt} · 本報告為自動生成，不構成投資建議
              </p>
            </>
          )}

          {tab === 'detail' &&
            data.points.map((p) => (
              <div className="point" key={p.title}>
                <h4>{p.title}</h4>
                <p>{p.body}</p>
              </div>
            ))}

          {tab === 'sources' && (
            <>
              <p className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
                本次分析的資料組成與各自權重。
              </p>
              {data.sources.map((s) => (
                <div className="src-row" key={s.name}>
                  <span>
                    <b style={{ fontSize: 12 }}>{s.name}</b>
                    <br />
                    <span className="muted" style={{ fontSize: 11 }}>
                      {s.note}
                    </span>
                  </span>
                  <span className="bar">
                    <i style={{ width: `${s.weight}%` }} />
                  </span>
                  <span className="num muted" style={{ textAlign: 'right' }}>
                    {s.weight}%
                  </span>
                </div>
              ))}
            </>
          )}
        </>
      )}
    </Panel>
  );
}

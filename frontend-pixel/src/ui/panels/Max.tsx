import { useState, type ReactNode } from 'react';
import { getEvents, getNews } from '../../api';
import { useAsync } from '../useAsync';
import { Panel, AsyncState } from '../Panel';
import { PixelCover, eventCover, newsCover } from '../PixelCover';

/** 官方消息與活動是同一種「左列表右詳情」，共用一份版面。 */
function SplitList<T extends { id: string }>({
  items,
  renderNav,
  renderBody,
}: {
  items: T[];
  renderNav: (it: T) => ReactNode;
  renderBody: (it: T) => ReactNode;
}) {
  const [sel, setSel] = useState(0);
  const active = items[Math.min(sel, items.length - 1)];
  if (!active) return <div className="empty">目前沒有內容</div>;

  return (
    <div className="split">
      <nav>
        {items.map((it, i) => (
          <button key={it.id} className="news-item" aria-selected={i === sel} onClick={() => setSel(i)}>
            {renderNav(it)}
          </button>
        ))}
      </nav>
      <article>{renderBody(active)}</article>
    </div>
  );
}

export function MaxNews() {
  const { data, loading, error, reload } = useAsync(() => getNews(), []);
  return (
    <Panel title="MAX 官方消息" accent="max" size="lg">
      <AsyncState loading={loading} error={error} onRetry={reload} />
      {data && (
        <SplitList
          items={data}
          renderNav={(n) => (
            <span className="news-row">
              <PixelCover kind={newsCover(n)} size={30} />
              <span className="news-txt">
                <span className="k">
                  {n.category} · {n.date}
                </span>
                <span className="t">{n.title}</span>
              </span>
            </span>
          )}
          renderBody={(n) => (
            <>
              <div className="news-hero">
                <PixelCover kind={newsCover(n)} size={48} />
                <div className="news-hero-txt">
                  <h3>{n.title}</h3>
                  <p className="muted" style={{ fontSize: 11, letterSpacing: '0.08em' }}>
                    {n.category} · 發布於 {n.date}
                  </p>
                </div>
              </div>
              <div style={{ height: 12 }} />
              {n.body.map((p, i) => (
                <p key={i}>{p}</p>
              ))}
            </>
          )}
        />
      )}
    </Panel>
  );
}

export function MaxEvents() {
  const { data, loading, error, reload } = useAsync(() => getEvents(), []);
  return (
    <Panel title="MAX 最新活動" accent="max" size="lg">
      <AsyncState loading={loading} error={error} onRetry={reload} />
      {data && (
        <SplitList
          items={data}
          renderNav={(e) => (
            <span className="news-row">
              <PixelCover kind={eventCover(e)} size={30} />
              <span className="news-txt">
                <span className="k">{e.tag}</span>
                <span className="t">{e.title}</span>
              </span>
            </span>
          )}
          renderBody={(e) => (
            <>
              <div className="news-hero">
                <PixelCover kind={eventCover(e)} size={48} />
                <div className="news-hero-txt">
                  <h3>{e.title}</h3>
                  <p className="muted" style={{ fontSize: 11, letterSpacing: '0.08em' }}>
                    {e.period}
                  </p>
                </div>
              </div>
              <div className="sentiment" style={{ marginTop: 12 }}>
                <span style={{ fontSize: 11, letterSpacing: '0.1em', color: 'var(--dim)' }}>獎勵</span>
                <b style={{ color: 'var(--green)' }}>{e.reward}</b>
              </div>
              {e.body.map((p, i) => (
                <p key={i}>{p}</p>
              ))}
            </>
          )}
        />
      )}
    </Panel>
  );
}

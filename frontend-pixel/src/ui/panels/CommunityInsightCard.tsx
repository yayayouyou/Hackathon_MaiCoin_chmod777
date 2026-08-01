import type { CommunityInsight } from '../../api';

export function CommunityInsightCard({ insight, compact = false }: { insight: CommunityInsight; compact?: boolean }) {
  return (
    <section style={{ border: '1px solid var(--line)', padding: compact ? 12 : 16, marginBottom: 16, background: 'rgba(139, 92, 246, 0.07)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 8 }}>
        <b style={{ color: 'var(--violet)' }}>{insight.headline}</b>
        <span className="muted" style={{ flexShrink: 0, fontSize: 11 }}>{insight.date}</span>
      </div>
      <p style={{ marginBottom: 10 }}>{insight.summary}</p>
      <div style={{ display: 'grid', gap: 8 }}>
        {insight.directions.map((direction) => (
          <div key={`${direction.topic}-${direction.why_it_matters}`}>
            <b style={{ color: 'var(--cyan)', fontSize: 12 }}>#{direction.topic}</b>
            {!compact && <span className="muted" style={{ display: 'block', fontSize: 12 }}>{direction.why_it_matters}</span>}
          </div>
        ))}
      </div>
      {!compact && insight.disagreements.length > 0 && (
        <p className="muted" style={{ fontSize: 12, marginTop: 10 }}>
          主要分歧：{insight.disagreements.join('、')}
        </p>
      )}
      <p className="muted" style={{ fontSize: 11, marginTop: 10 }}>
        根據今日 {insight.post_count} 則討論整理 · 社群觀點，不構成投資建議
      </p>
    </section>
  );
}

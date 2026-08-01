import { useMemo, useState } from 'react';
import { getStrategies } from '../../api';
import type { Strategy, StrategyKind } from '../../api/types';
import { useAsync } from '../useAsync';
import { Panel, AsyncState } from '../Panel';
import { DemoData } from '../DemoData';
import { ask } from '../chatStore';
import { openChatDock } from '../../hud/dockStore';
import { closePanel } from '../uiStore';

/**
 * 策略牆 —— 大廳左側那面便利貼牆。
 *
 * 這一區回答的是「別人都怎麼做」。加密社群真正會停下來看的東西不是行情
 * （那到處都有），是別人的做法與**別人的虧損**，所以這面牆刻意不做成一張
 * 報酬排行榜：
 *
 * ① **回撤與樣本數跟報酬並排**，同一個字級。只秀報酬的看板會把「賭對一次」
 *    包裝成「策略有效」。樣本 < 30 筆的直接掛警示，點得開但先告訴你別當真。
 * ② **留了一張負報酬的卡片**在牆上（四小時線均線交叉，-4.3%）。一整排都賺
 *    的社群牆沒有人會信，而且那正是這類產品最常見的造假手法。
 * ③ **沒有「一鍵跟單」**。代客操作與跟單在多數司法管轄區是受規範的業務，
 *    而評審來自一家做信託保管與洗錢防制法遵的公司 —— 一顆跟單按鈕會讓
 *    整個作品的合規觀感倒扣。卡片上的動作是收藏，以及把這套規則丟給 MAIA
 *    去查資料驗證，那才是這個作品真正的賣點。
 */

const KINDS: StrategyKind[] = ['定投', '網格', '趨勢', '波段', '對沖'];

/** 樣本數低於這個值，任何報酬率都只是雜訊。 */
const THIN_SAMPLE = 30;

type Sort = 'saves' | 'return' | 'drawdown';

const SORTS: { id: Sort; label: string }[] = [
  { id: 'saves', label: '最多人收藏' },
  { id: 'return', label: '近 30 日報酬' },
  { id: 'drawdown', label: '回撤最小' },
];

const pct = (n: number): string => `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`;

function Metric({ label, value, tone }: { label: string; value: string; tone?: 'up' | 'down' }) {
  return (
    <span className="strat-metric">
      <b className={tone ?? ''}>{value}</b>
      <i>{label}</i>
    </span>
  );
}

function Card({
  s,
  saved,
  onToggleSave,
}: {
  s: Strategy;
  saved: boolean;
  onToggleSave: () => void;
}) {
  const [open, setOpen] = useState(false);
  const thin = s.trades < THIN_SAMPLE;

  /**
   * 把整套規則交給 MAIA。送的是規則本身而不是「這個策略好不好」——
   * 後者只會拿到一段沒有依據的評語，前者 agent 才有東西可以去查。
   */
  const analyse = (): void => {
    const q = [
      `幫我看這套策略：「${s.title}」，標的 ${s.market}。`,
      `規則是：${s.rules.join('；')}。`,
      `作者貼的數字是近 30 日 ${pct(s.return30d)}、最大回撤 ${s.drawdown}%、勝率 ${s.winRate}%，樣本 ${s.trades} 筆。`,
      '請用真實行情驗證這些數字合不合理，並指出這套規則在什麼市況下會失效。',
    ].join('');
    closePanel();
    openChatDock();
    void ask(q);
  };

  return (
    <article className="strat" data-thin={thin ? '1' : '0'}>
      <header className="strat-head">
        <span className="strat-face" style={{ background: s.color }} aria-hidden="true" />
        <span className="strat-title">
          <b>{s.title}</b>
          <i>
            {s.author} · {s.updatedAt}
          </i>
        </span>
        <span className="tag">{s.kind}</span>
        <span className="tag">{s.market}</span>
      </header>

      <p className="strat-summary">{s.summary}</p>

      <div className="strat-metrics">
        <Metric label="近 30 日" value={pct(s.return30d)} tone={s.return30d >= 0 ? 'up' : 'down'} />
        {/* 回撤跟報酬同一個字級：只看報酬是這類看板最常見的誤導 */}
        <Metric label="最大回撤" value={`${s.drawdown.toFixed(1)}%`} />
        <Metric label="勝率" value={`${s.winRate}%`} />
        <Metric label="樣本" value={`${s.trades} 筆`} />
      </div>

      {thin && (
        <p className="strat-thin">
          ⚠ 樣本只有 {s.trades} 筆，少於 {THIN_SAMPLE} 筆。這個報酬率有很大機率是運氣，不是策略。
        </p>
      )}

      <div className="strat-foot">
        <button className="chip" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? '▾' : '▸'} 進出場規則（{s.rules.length}）
        </button>
        <span className="strat-spacer" />
        <button className="star" data-on={saved} title={saved ? '取消收藏' : '收藏'} onClick={onToggleSave}>
          {saved ? '★' : '☆'} {s.saves + (saved ? 1 : 0)}
        </button>
        <button className="btn" onClick={analyse}>
          請 MAIA 分析
        </button>
      </div>

      {open && (
        <ol className="strat-rules">
          {s.rules.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ol>
      )}
    </article>
  );
}

export function Strategies() {
  const { data, loading, error, reload } = useAsync(() => getStrategies(), []);
  const [kind, setKind] = useState<StrategyKind | null>(null);
  const [sort, setSort] = useState<Sort>('saves');
  /**
   * 收藏只活在這個面板的 state 裡。討論室的收藏走 uiStore + localStorage，
   * 那是因為它會影響世界（選房面板的「我的收藏」分頁）；策略牆的收藏目前
   * 沒有第二個讀取端，先不落地 —— 等它真的有用途再搬去 uiStore。
   */
  const [saved, setSaved] = useState<string[]>([]);

  const shown = useMemo(() => {
    const list = (data ?? []).filter((s) => !kind || s.kind === kind);
    const by: Record<Sort, (a: Strategy, b: Strategy) => number> = {
      saves: (a, b) => b.saves - a.saves,
      return: (a, b) => b.return30d - a.return30d,
      drawdown: (a, b) => a.drawdown - b.drawdown,
    };
    return [...list].sort(by[sort]);
  }, [data, kind, sort]);

  return (
    <Panel title="策略牆" accent="amber" size="lg">
      <DemoData what="社群策略與其績效數字" />
      <AsyncState loading={loading} error={error} onRetry={reload} />
      {data && (
        <>
          <p className="strat-note">
            社群成員自己貼上來的做法與數字，<b>未經驗證，也不構成投資建議</b>。
            報酬永遠跟回撤與樣本數一起看 —— 想知道某一套到底站不站得住，
            按「請 MAIA 分析」讓它拿真實行情去驗。
          </p>

          <div className="chips" style={{ marginBottom: 10 }}>
            <button className="chip" data-on={kind === null} onClick={() => setKind(null)}>
              全部
            </button>
            {KINDS.map((k) => (
              <button key={k} className="chip" data-on={kind === k} onClick={() => setKind(k === kind ? null : k)}>
                {k}
              </button>
            ))}
          </div>

          <div className="chips" style={{ marginBottom: 14 }}>
            <span className="strat-sortlabel">排序</span>
            {SORTS.map((o) => (
              <button key={o.id} className="chip" data-on={sort === o.id} onClick={() => setSort(o.id)}>
                {o.label}
              </button>
            ))}
          </div>

          {shown.length === 0 ? (
            <div className="empty">這個分類還沒有人分享策略</div>
          ) : (
            shown.map((s) => (
              <Card
                key={s.id}
                s={s}
                saved={saved.includes(s.id)}
                onToggleSave={() =>
                  setSaved((v) => (v.includes(s.id) ? v.filter((x) => x !== s.id) : [...v, s.id]))
                }
              />
            ))
          )}
        </>
      )}
    </Panel>
  );
}

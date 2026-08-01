import { getBehavior, getDashboard, getTradingGuard, type BehaviorMetric } from '../../api/account';
import { useAsync } from '../useAsync';
import { Panel, AsyncState } from '../Panel';
import {
  AcctSplit, Hero, Note, Sec, Tiles, TrustBadge,
  twd, type Section, type Trust,
} from './AcctParts';

/**
 * 大廳右下角「全息」站點 —— 我是什麼樣的交易者、防線在哪。
 *
 * 對應 agent_ui 帳戶總覽的「交易行為 / 風控 / 偏好」三類。
 *
 * ⚠ 這一頁的核心不是「秀出結論」，是**知道什麼時候不要下結論**。
 *   後端每個指標都帶 `sample_ok`，樣本不足時它會**刻意把 conclusion 留成
 *   null**，只給數字。行為偏誤最容易從少數幾筆交易「看出」其實不存在的
 *   模式 —— 一個拿 3 筆交易就宣告「你有處置效應」的面板，在評審問第二句
 *   話的時候就會垮。所以這裡照後端的旗標走：有結論就講，沒有就只擺數字
 *   並說明還差多少筆。
 */

/** 指標卡裡不該當成「數據列」印出來的鍵。 */
const META_KEYS = new Set(['metric', 'conclusion', 'sample_ok', 'note']);

/** 把後端各式各樣的欄位名翻成看得懂的中文。查不到就用原鍵，不要空白。 */
const FIELD_LABEL: Record<string, string> = {
  winners: '獲利的',
  losers: '虧損的',
  ratio_loser_over_winner: '虧損/獲利 持有天數比',
  lookback_days: '回看天數',
  buys: '買進',
  sells: '賣出',
  n: '筆數',
  median_hold_days: '持有天數中位數',
  median_prior_change_pct: '前期價格變化中位數',
  bought_after_rise_pct: '買在漲勢後的比例',
  sold_after_fall_pct: '賣在跌勢後的比例',
  total_fees_twd: '手續費合計',
  net_realized_twd: '淨已實現',
  gross_before_fees_twd: '扣費前毛利',
  closes: '平倉筆數',
  fee_per_close_twd: '每筆平均手續費',
  fees_as_pct_of_gross: '手續費佔毛利',
  adds_below_avg_cost: '在均價之下加碼',
  adds_above_avg_cost: '在均價之上加碼',
  below_share_pct: '低於均價加碼比例',
  examples: '案例',
};

const label = (k: string): string => FIELD_LABEL[k] ?? k;

/**
 * 巢狀物件（winners/losers/buys/sells）攤成一行字，不要再多一層表格。
 *
 * `key` 只用來決定單位：後端的百分比欄位一律以 `_pct` 結尾且值已經是
 * 0–100 的數（`below_share_pct: 57.6`）。少了這個尾綴，畫面上會出現
 * 一個沒有單位的「57.60」——讀者無從判斷那是 57.6% 還是 57.6 筆。
 */
function flat(v: unknown, key = ''): string {
  if (v == null) return '—';
  const unit = key.endsWith('_pct') ? '%' : '';
  if (typeof v === 'number') {
    return (Number.isInteger(v) ? String(v) : v.toFixed(2)) + unit;
  }
  if (typeof v === 'string' || typeof v === 'boolean') return String(v);
  if (Array.isArray(v)) return `${v.length} 筆`;
  if (typeof v === 'object') {
    return Object.entries(v as Record<string, unknown>)
      .map(([k, x]) => `${label(k)} ${flat(x, k)}`)
      .join(' · ');
  }
  return String(v);
}

export function Behavior() {
  const sections: Section[] = [
    { id: 'behavior', label: '交易行為', hint: '偏誤檢測 · 樣本足夠才下結論', render: () => <BehaviorView /> },
    { id: 'guard', label: '風控', hint: '防線 · 曝險 · 決策台帳', render: () => <Guard /> },
    { id: 'prefs', label: '偏好', hint: 'AI 記住的你', render: () => <Prefs /> },
  ];
  return (
    <Panel title="交易性格" accent="green" size="lg">
      <AcctSplit sections={sections} />
    </Panel>
  );
}

// ── 交易行為 ────────────────────────────────────────────────

function MetricCard({ m }: { m: BehaviorMetric }) {
  const ok = m.sample_ok === true;
  const rows = Object.entries(m).filter(([k]) => !META_KEYS.has(k));

  return (
    <div
      style={{
        padding: '11px 13px',
        marginBottom: 8,
        background: 'var(--panel-2)',
        borderLeft: `2px solid ${ok ? 'var(--green)' : 'var(--amber)'}`,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 7, flexWrap: 'wrap' }}>
        <b style={{ fontSize: 13 }}>{m.metric}</b>
        <TrustBadge level={ok ? 'ok' : 'partial'}>{ok ? '樣本足夠' : '樣本不足'}</TrustBadge>
      </div>

      {rows.length > 0 && (
        <table className="pos-table" style={{ marginBottom: 8 }}>
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k}>
                <td>{label(k)}</td>
                <td>{flat(v, k)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/*
        有結論才印結論。沒有的時候印後端寫好的 note（「樣本僅 3 筆，需 ≥8 筆
        才足以判斷，只列數字不下結論」）—— 那句話本身就是這一頁的價值主張。
      */}
      {m.conclusion ? (
        <div style={{ fontSize: 12 }}>{m.conclusion}</div>
      ) : (
        <div className="muted" style={{ fontSize: 12 }}>{m.note ?? '樣本不足，不下結論'}</div>
      )}
    </div>
  );
}

function BehaviorView() {
  const { data, loading, error, reload } = useAsync((s) => getBehavior(s), []);
  if (loading || error) {
    return (
      <>
        {loading && (
          <p className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
            正在重播整本帳本，需要幾秒…
          </p>
        )}
        <AsyncState loading={loading} error={error} onRetry={reload} />
      </>
    );
  }

  const metrics = data?.metrics ?? [];
  const s = data?.sample;
  // 「先展示對得上的」：樣本足夠、能下結論的排前面。
  const sorted = [...metrics].sort((a, b) => Number(b.sample_ok === true) - Number(a.sample_ok === true));
  const okCount = metrics.filter((m) => m.sample_ok === true).length;

  const level: Trust =
    data?.data_confidence === 'full' ? 'ok' : data?.data_confidence === 'partial' ? 'partial' : 'none';

  return (
    <>
      <Hero
        label="可下結論的指標"
        value={`${okCount} / ${metrics.length}`}
        badge={<TrustBadge level={level}>{data?.data_confidence ?? '未知'}</TrustBadge>}
        sub={
          s
            ? `${s.closes_analyzed ?? 0} / ${s.closes_total ?? 0} 筆平倉納入分析` +
              (s.dust_excluded ? `（${s.dust_excluded} 筆低於 ${twd(s.min_trade_twd)} TWD 的灰塵已排除）` : '')
            : undefined
        }
      />

      {(data?.findings ?? []).length > 0 && (
        <>
          <Sec>結論</Sec>
          {(data?.findings ?? []).map((f, i) => (
            <div key={i} style={{ fontSize: 12, marginBottom: 6 }}>· {f}</div>
          ))}
        </>
      )}

      <Sec>逐項指標</Sec>
      {sorted.length === 0 ? (
        <div className="empty">還沒有足夠的交易可以分析</div>
      ) : (
        sorted.map((m, i) => <MetricCard key={`${m.metric}-${i}`} m={m} />)
      )}

      {data?.note && <Note warn>{data.note}</Note>}
    </>
  );
}

// ── 風控 ────────────────────────────────────────────────────

function Guard() {
  const { data, loading, error, reload } = useAsync((s) => getTradingGuard(s), []);
  if (loading || error) return <AsyncState loading={loading} error={error} onRetry={reload} />;

  const live = data?.effective_mode === 'live';
  const ex = data?.exposure;
  const halted = data?.kill_switch?.engaged === true;
  const decisions = data?.recent_decisions ?? [];

  return (
    <>
      <Hero
        label="生效模式"
        value={live ? '🔴 實盤' : '📝 模擬盤'}
        cls={live ? 'down' : 'up'}
        badge={halted ? <TrustBadge level="none">已停止交易</TrustBadge> : undefined}
        sub={data?.mode_note}
      />

      {ex && (
        <>
          <Sec>曝險上限 · 最近 {ex.window_hours} 小時</Sec>
          <Tiles
            items={[
              { k: '已下單', v: `${ex.orders ?? 0} / ${ex.max_orders ?? '—'} 筆` },
              { k: '已用金額', v: `${twd(ex.notional_twd)} / ${twd(ex.max_notional_twd)} TWD` },
            ]}
          />
          {/* 用量條：數字看不出「還剩多少」，一條看得出來 */}
          {ex.max_notional_twd ? (
            <div style={{ height: 6, background: 'var(--panel-2)', marginBottom: 10 }}>
              <div
                style={{
                  height: '100%',
                  width: `${Math.min(100, ((ex.notional_twd ?? 0) / ex.max_notional_twd) * 100)}%`,
                  background: 'var(--amber)',
                }}
              />
            </div>
          ) : null}
        </>
      )}

      <Sec>下單決策台帳</Sec>
      {decisions.length === 0 ? (
        // 空不是壞事：模擬盤本來就不會有實盤下單紀錄。講清楚它為什麼空。
        <div className="empty">
          還沒有下單決策紀錄
          <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
            {live ? '實盤模式下每一次下單與被擋下的嘗試都會記在這裡' : '模擬盤不會產生實盤下單紀錄'}
          </div>
        </div>
      ) : (
        <table className="pos-table">
          <tbody>
            {decisions.map((d, i) => (
              <tr key={i}>
                <td>{String(d['decision'] ?? '—')}</td>
                <td className="muted">{String(d['reason'] ?? d['note'] ?? '')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {data?.note && <Note>{data.note}</Note>}
    </>
  );
}

// ── 偏好 ────────────────────────────────────────────────────

function Prefs() {
  const { data, loading, error, reload } = useAsync((s) => getDashboard(s), []);
  if (loading || error) return <AsyncState loading={loading} error={error} onRetry={reload} />;

  const traits = data?.traits ?? [];
  return (
    <>
      <p className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
        MAIA 從你們的對話裡記下來的偏好。它會影響之後的分析口徑。
      </p>
      {traits.length === 0 ? (
        <div className="empty">
          還沒有記住的偏好
          <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
            去跟 MAIA 說「我只做現貨」「我風險承受 2%」，它會記起來
          </div>
        </div>
      ) : (
        traits.map((t, i) => (
          <div
            key={i}
            style={{
              padding: '9px 12px',
              marginBottom: 6,
              background: 'var(--panel-2)',
              borderLeft: '2px solid var(--violet)',
              fontSize: 12,
            }}
          >
            {t}
          </div>
        ))
      )}
    </>
  );
}

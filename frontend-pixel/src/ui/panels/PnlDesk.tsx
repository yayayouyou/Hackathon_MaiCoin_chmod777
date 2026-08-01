import { useState } from 'react';
import {
  getAccountActivity, getDashboard, getDepositSources, getPositions, pnlCardUrl,
} from '../../api/account';
import { useAsync } from '../useAsync';
import { Panel, AsyncState } from '../Panel';
import {
  AcctSplit, Hero, Note, Sec, Tiles, TrustBadge,
  pct, qty, signCls, twd, when, type Section, type Trust,
} from './AcctParts';

/**
 * 大廳右下角「看板」站點 —— 我賺賠多少、帳對不對、錢從哪來。
 *
 * 對應 agent_ui 帳戶總覽的「已實現 / 對帳 / 資金流」三類，外加可分享的
 * 損益對帳單卡。
 *
 * 這個面板是三個裡面**最需要誠實**的一個：已實現損益是拿買入成本去減的，
 * 而 MAX 的成交 API 有歷史起點，起點之前的買入抓不到 —— 那些平倉的成本
 * 是推估的。所以每一筆平倉都帶 `basis_quality`，對帳頁則直接把七種幣
 * 一種一種攤開講「對不對得上、為什麼」。
 */

export function PnlDesk() {
  const sections: Section[] = [
    { id: 'realized', label: '已實現', hint: '平倉損益 · 配對明細', render: () => <Realized /> },
    { id: 'reconcile', label: '對帳', hint: '帳本 vs 交易所餘額', render: () => <Reconcile /> },
    { id: 'funds', label: '資金流', hint: '出入金 · 閃兌 · 鏈上溯源', render: () => <Funds /> },
    { id: 'card', label: '損益卡', hint: '可分享 · 不含餘額金額', render: () => <PnlCard /> },
  ];
  return (
    <Panel title="損益對帳台" accent="green" size="lg">
      <AcctSplit sections={sections} />
    </Panel>
  );
}

// ── 已實現 ──────────────────────────────────────────────────

const BASIS_LABEL: Record<string, { text: string; level: Trust }> = {
  known: { text: '成本來源完整', level: 'ok' },
  mixed: { text: '成本部分推估', level: 'partial' },
  unknown: { text: '成本為推估', level: 'none' },
};

function Realized() {
  const pos = useAsync((s) => getPositions(s), []);
  const dash = useAsync((s) => getDashboard(s), []);
  const [open, setOpen] = useState<number | null>(null);

  if (pos.loading || pos.error) {
    return <AsyncState loading={pos.loading} error={pos.error} onRetry={pos.reload} />;
  }

  const r = pos.data?.realized;
  const ts = dash.data?.trade_stats;
  const fees = Object.entries(r?.fee_cost_twd ?? {}).sort((a, b) => b[1] - a[1]);
  const feeTotal = fees.reduce((s, [, v]) => s + v, 0);

  // 「先展示對得上的」：成本來源完整的幣種排前面。
  const byCur = [...(r?.by_currency ?? [])].sort((a, b) => b.realized_pnl_twd - a.realized_pnl_twd);

  return (
    <>
      <Hero
        label="已實現損益"
        value={`${(r?.total_twd ?? 0) > 0 ? '+' : ''}${twd(r?.total_twd)} TWD`}
        cls={signCls(r?.total_twd)}
        sub={
          <>
            {r?.closes ?? 0} 筆平倉 · 手續費已扣 {twd(feeTotal)} TWD
          </>
        }
      />

      {ts && (
        <>
          <Sec>近期交易統計 · 最近 {ts.count} 筆</Sec>
          <Tiles
            items={[
              { k: '買 / 賣', v: <><span className="up">{ts.buy}</span> / <span className="down">{ts.sell}</span></> },
              { k: '交易額', v: `${twd(ts.twd_volume)} TWD` },
            ]}
          />
          {(ts.top_markets ?? []).length > 0 && (
            <div className="chips" style={{ marginBottom: 12 }}>
              {(ts.top_markets ?? []).map((m) => (
                <span className="chip" key={m.market}>{m.market} {m.count}</span>
              ))}
            </div>
          )}
        </>
      )}

      {byCur.length > 0 && (
        <>
          <Sec>依幣種</Sec>
          <table className="pos-table">
            <thead>
              <tr><th>幣種</th><th>已實現</th><th>報酬率</th><th>勝率</th><th>平倉</th></tr>
            </thead>
            <tbody>
              {byCur.map((c) => (
                <tr key={c.currency}>
                  <td>{c.currency}</td>
                  <td className={signCls(c.realized_pnl_twd)}>{twd(c.realized_pnl_twd)}</td>
                  <td className={signCls(c.return_pct)}>{pct(c.return_pct)}</td>
                  <td>{c.win_rate_pct.toFixed(0)}%</td>
                  <td className="muted">{c.closes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <Sec>最近平倉 · 點一列看買入配對</Sec>
      {(r?.recent ?? []).length === 0 ? (
        <div className="empty">沒有平倉紀錄</div>
      ) : (
        (r?.recent ?? []).map((c, i) => {
          const b = BASIS_LABEL[c.basis_quality ?? ''] ?? BASIS_LABEL['unknown']!;
          const isOpen = open === i;
          return (
            <div key={i} style={{ background: 'var(--panel-2)', marginBottom: 6 }}>
              <button
                className="news-item"
                style={{ borderBottom: 'none' }}
                aria-selected={isOpen}
                onClick={() => setOpen(isOpen ? null : i)}
              >
                <span style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <b>{c.currency}</b>
                  <span className={`num ${signCls(c.pnl_twd)}`}>
                    {c.pnl_twd > 0 ? '+' : ''}{twd(c.pnl_twd)} ({pct(c.pnl_pct)})
                  </span>
                </span>
                <span className="k" style={{ color: 'var(--dim)', letterSpacing: 0, marginTop: 3 }}>
                  {c.time} · 賣出 {qty(c.qty)} · 持有 {c.holding_days ?? '—'} 天
                  {c.note ? ` · ${c.note}` : ''}
                </span>
                <span style={{ marginTop: 5, display: 'inline-block' }}>
                  <TrustBadge level={b.level}>{b.text}</TrustBadge>
                </span>
              </button>

              {isOpen && (
                <div style={{ padding: '0 10px 10px' }}>
                  <table className="pos-table">
                    <thead>
                      <tr><th>買入日</th><th>數量</th><th>成本單價</th><th>來源</th></tr>
                    </thead>
                    <tbody>
                      {(c.matched_lots ?? []).map((l, j) => (
                        <tr key={j}>
                          {/* 後端用中文鍵，照抄不改 —— 改了就要兩邊同步一份對照表 */}
                          <td>{l.買入日}</td>
                          <td>{qty(l.數量)}</td>
                          <td>{twd(l.成本單價)}</td>
                          <td className={l.成本來源 === 'known' ? 'up' : 'muted'}>
                            {l.成本來源 === 'known' ? '已知' : '推估'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                    賣出金額 {twd(c.proceeds_twd)} − 成本 {twd(c.cost_twd)}
                  </div>
                </div>
              )}
            </div>
          );
        })
      )}

      {fees.length > 0 && (
        <>
          <Sec>手續費成本 · 依計價幣</Sec>
          <div className="chips">
            {fees.map(([c, v]) => (
              <span className="chip" key={c}>{c} {twd(v)} TWD</span>
            ))}
          </div>
        </>
      )}
    </>
  );
}

// ── 對帳 ────────────────────────────────────────────────────

function Reconcile() {
  const { data, loading, error, reload } = useAsync((s) => getPositions(s), []);
  if (loading || error) return <AsyncState loading={loading} error={error} onRetry={reload} />;

  const rec = data?.reconcile;
  const rows = rec?.rows ?? [];
  // 「先展示對得上的」——這一頁最直接的體現：ok 的排前面，剩下依差距大小。
  const sorted = [...rows].sort((a, b) => {
    if (a.ok !== b.ok) return a.ok ? -1 : 1;
    return Math.abs(b.gap) - Math.abs(a.gap);
  });

  const level: Trust =
    rec?.confidence === 'full' ? 'ok' : rec?.confidence === 'partial' ? 'partial' : 'none';

  return (
    <>
      <Hero
        label="對帳結果"
        value={`${rec?.matched ?? 0} / ${rec?.currencies ?? 0}`}
        badge={<TrustBadge level={level}>{rec?.confidence ?? '未知'}</TrustBadge>}
        sub="帳本重播出來的數量，與 MAX 帳戶當下餘額逐幣種比對"
      />

      {sorted.length === 0 ? (
        <div className="empty">還沒有對帳結果</div>
      ) : (
        sorted.map((row) => (
          <div
            key={row.currency}
            style={{
              padding: '10px 12px',
              marginBottom: 6,
              background: 'var(--panel-2)',
              // 對得上的用綠邊、對不上的用琥珀 —— 顏色本身就是排序的理由
              borderLeft: `2px solid ${row.ok ? 'var(--green)' : 'var(--amber)'}`,
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <b>{row.currency}</b>
              <span className={`num ${row.ok ? 'up' : 'muted'}`} style={{ fontSize: 12 }}>
                {row.ok ? '相符' : `差 ${qty(row.gap)}`}
              </span>
            </div>
            <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
              帳本 {qty(row.ledger_qty)} · 交易所 {qty(row.actual_qty)}
            </div>
            {!row.ok && (
              <div style={{ fontSize: 12, marginTop: 5 }}>{row.diagnosis}</div>
            )}
            {row.sources && Object.keys(row.sources).length > 0 && (
              <div className="chips" style={{ marginTop: 6 }}>
                {Object.entries(row.sources).map(([k, v]) => (
                  <span className="chip" key={k} style={{ fontSize: 10 }}>
                    {k} {qty(v)}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))
      )}

      {rec?.note && <Note warn>{rec.note}</Note>}
    </>
  );
}

// ── 資金流 ──────────────────────────────────────────────────

const FLOW_LABEL: Record<string, string> = {
  deposit: '入金',
  withdrawal: '出金',
  transfer: '互轉',
};

function Funds() {
  const act = useAsync((s) => getAccountActivity(s), []);
  const src = useAsync((s) => getDepositSources(s), []);

  if (act.loading || act.error) {
    return <AsyncState loading={act.loading} error={act.error} onRetry={act.reload} />;
  }

  const flow = act.data?.flow ?? [];
  const trades = act.data?.trades ?? [];
  const converts = act.data?.converts ?? [];
  const addrs = act.data?.withdraw_addresses ?? [];

  return (
    <>
      <Sec>資金異動 · 出入金與互轉</Sec>
      {flow.length === 0 ? (
        <div className="empty">沒有資金異動紀錄</div>
      ) : (
        <table className="pos-table">
          <thead>
            <tr><th>類型</th><th>幣種</th><th>金額</th><th>狀態</th><th>時間</th></tr>
          </thead>
          <tbody>
            {flow.map((f, i) => (
              <tr key={i}>
                <td>
                  {FLOW_LABEL[f.type ?? ''] ?? f.type}
                  {f.is_internal && <span className="muted" style={{ fontSize: 10 }}> 站內</span>}
                </td>
                <td>{f.currency}</td>
                <td className={f.type === 'withdrawal' ? 'down' : 'up'}>{qty(f.amount)}</td>
                <td className="muted">{f.state}</td>
                <td className="muted">{when(f.time_ms)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <Sec>入金來源溯源 · 防來路不明</Sec>
      {src.loading ? (
        <div className="muted" style={{ fontSize: 12 }}>查詢鏈上來源中…</div>
      ) : (
        <>
          {/*
            這一格在多數帳戶會是「查了 N 筆、0 筆可溯源」—— 因為站內轉帳與
            法幣入金本來就沒有鏈上發送方。那不是查詢失敗，所以印的是後端寫好
            的那句 summary，而不是一個空列表加一行「沒有資料」。
          */}
          <div style={{ fontSize: 12, marginBottom: 8 }}>{src.data?.summary ?? '—'}</div>
          {(src.data?.flagged_suspicious ?? 0) > 0 && (
            <Note warn>有 {src.data?.flagged_suspicious} 筆入金來源可疑，請點開明細確認</Note>
          )}
          {Object.keys(src.data?.skipped ?? {}).length > 0 && (
            <div className="chips">
              {Object.entries(src.data?.skipped ?? {}).map(([k, v]) => (
                <span className="chip" key={k} style={{ fontSize: 10 }}>{k} {v}</span>
              ))}
            </div>
          )}
        </>
      )}

      {converts.length > 0 && (
        <>
          <Sec>閃兌</Sec>
          <table className="pos-table">
            <thead>
              <tr><th>從</th><th>到</th><th>手續費 TWD</th><th>時間</th></tr>
            </thead>
            <tbody>
              {converts.map((c, i) => (
                <tr key={i}>
                  <td>{qty(c.from_amount)} {c.from_currency}</td>
                  <td>{qty(c.to_amount)} {c.to_currency}</td>
                  <td className="muted">{c.fee_in_twd != null ? c.fee_in_twd.toFixed(4) : '—'}</td>
                  <td className="muted">{when(c.time_ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {trades.length > 0 && (
        <>
          <Sec>最近成交</Sec>
          <table className="pos-table">
            <thead>
              <tr><th>市場</th><th>方向</th><th>價格</th><th>數量</th><th>時間</th></tr>
            </thead>
            <tbody>
              {trades.map((t, i) => (
                <tr key={i}>
                  <td>{t.market}</td>
                  {/* MAX 用 bid/ask 而不是 buy/sell，直接顯示會看不懂 */}
                  <td className={t.side === 'bid' ? 'up' : 'down'}>{t.side === 'bid' ? '買' : '賣'}</td>
                  <td>{twd(Number(t.price))}</td>
                  <td>{qty(Number(t.volume))}</td>
                  <td className="muted">{when(t.time_ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {addrs.length > 0 && (
        <>
          <Sec>提幣白名單 · 地址已遮蔽</Sec>
          <table className="pos-table">
            <thead>
              <tr><th>幣種</th><th>網路</th><th>地址</th><th>標籤</th></tr>
            </thead>
            <tbody>
              {addrs.map((a, i) => (
                <tr key={i}>
                  <td>{a.currency}</td>
                  <td className="muted">{a.network}</td>
                  <td>{a.address}</td>
                  <td className="muted">{a.label || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </>
  );
}

// ── 損益卡 ──────────────────────────────────────────────────

function PnlCard() {
  return (
    <>
      <p className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
        後端算好的 SVG 對帳單卡。<b>只放百分比與勝率，不含任何餘額金額</b>，
        所以可以直接截圖分享出去。
      </p>
      {/*
        用 <img src> 而不是把 SVG 內嵌進 DOM：外部 SVG 走 img 載入時
        腳本與外部參照都被瀏覽器停用，等於免費拿到一層隔離。
      */}
      <img
        src={pnlCardUrl()}
        alt="損益對帳單卡"
        style={{ width: '100%', maxWidth: 480, display: 'block', imageRendering: 'auto' }}
      />
    </>
  );
}

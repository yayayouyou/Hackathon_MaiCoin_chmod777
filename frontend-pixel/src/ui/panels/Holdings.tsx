import { useState } from 'react';
import { getDashboard, getPositions, type Position } from '../../api/account';
import { useAsync } from '../useAsync';
import { Panel, AsyncState } from '../Panel';
import {
  AcctSplit, Hero, Note, Sec, Tiles, TrustBadge,
  pct, qty, signCls, twd, type Section, type Trust,
} from './AcctParts';

/**
 * 大廳右下角「金庫」站點 —— 我有什麼。
 *
 * 對應 agent_ui 帳戶總覽的「總覽 / 艙位 / 錢包餘額 / 質押獎勵 / 融資」五類，
 * 資料來自 `/api/dashboard` 與 `/api/positions`。
 *
 * ⚠ 這個面板最容易被誤讀的一件事，值得寫在這裡：
 *   **艙位的「數量」已經對得上交易所了**，`lot_engine` 會用 `adjustments`
 *   把帳本校正到與 MAX 餘額一致（`qty_gap_vs_exchange` 幾乎都是 0）。
 *   真正不確定的是**成本**：MAX 的成交 API 有歷史起點，更早的買入抓不到，
 *   所以 `basis_known_pct` 才是這一頁該掛徽章的地方，而不是數量。
 *   把「7 種幣有 5 種對不上」寫在艙位卡旁邊是錯的 —— 那是對帳頁的事。
 */

/** 成本可信度 → 徽章等級。門檻取 99/80：低於 80 就不該讓人照著它做決定。 */
function basisTrust(p: Position): Trust {
  const k = p.basis_known_pct;
  if (k == null) return 'none';
  if (k >= 99) return 'ok';
  return k >= 80 ? 'partial' : 'none';
}

export function Holdings() {
  const sections: Section[] = [
    { id: 'overview', label: '總覽', hint: '未實現損益 · 資產分佈', render: () => <Overview /> },
    { id: 'lots', label: '艙位', hint: 'FIFO 成本 · 批次組成', render: () => <Lots /> },
    { id: 'wallet', label: '錢包餘額', hint: '可用 / 鎖定 / 質押', render: () => <Wallet /> },
    { id: 'rewards', label: '質押獎勵', hint: '持有 · 質押 · 空投回饋', render: () => <Rewards /> },
    { id: 'margin', label: '融資錢包', hint: 'M-Wallet 維持率', render: () => <MarginView /> },
  ];
  return (
    <Panel title="我的金庫" accent="green" size="lg">
      <AcctSplit sections={sections} />
    </Panel>
  );
}

// ── 總覽 ────────────────────────────────────────────────────

function Overview() {
  const pos = useAsync((s) => getPositions(s), []);
  const dash = useAsync((s) => getDashboard(s), []);

  if (pos.loading || pos.error) {
    return <AsyncState loading={pos.loading} error={pos.error} onRetry={pos.reload} />;
  }

  const t = pos.data?.totals;
  const rec = pos.data?.reconcile;
  const upnl = t?.total_unrealized_pnl_twd ?? null;

  // 頭條的可信度取「對帳結果」而不是單一艙位 —— 總計是所有幣種加起來的，
  // 只要有一種對不上，這個總數就帶著那份不確定。
  const level: Trust = rec?.confidence === 'full' ? 'ok' : rec?.confidence === 'partial' ? 'partial' : 'none';
  const matched = rec?.matched ?? 0;
  const total = rec?.currencies ?? 0;

  const balances = dash.data?.balances ?? [];
  const priced = balances
    .filter((b) => (b.value_twd ?? 0) > 0)
    .sort((a, b) => (b.value_twd ?? 0) - (a.value_twd ?? 0));
  const sum = priced.reduce((s, b) => s + (b.value_twd ?? 0), 0);

  return (
    <>
      <Hero
        label="未實現損益"
        value={`${upnl != null && upnl > 0 ? '+' : ''}${twd(upnl)} TWD`}
        cls={signCls(upnl)}
        badge={
          <TrustBadge level={level}>
            {total ? `${matched}/${total} 幣種對得上` : '尚未對帳'}
          </TrustBadge>
        }
        sub={
          <>
            市值 {twd(t?.total_value_twd)} · 成本 {twd(t?.total_cost_twd)} ·{' '}
            <span className={signCls(t?.total_unrealized_pnl_pct)}>
              {pct(t?.total_unrealized_pnl_pct)}
            </span>
          </>
        }
      />

      {/*
        資產分佈用純 CSS 的橫條而不是圓環。
        後端那邊是 canvas 畫的甜甜圈，但這裡是像素世界 —— 引入一張 canvas
        只為了畫比例，收益低於成本（規格附錄 B 也擋掉了迷你 K 線，同一個理由）。
        橫條在窄面板上還比圓環好讀。
      */}
      <Sec>資產分佈 · 依 TWD 估值</Sec>
      {priced.length === 0 ? (
        <div className="empty">沒有可估值的資產</div>
      ) : (
        priced.map((b) => {
          const share = sum > 0 ? ((b.value_twd ?? 0) / sum) * 100 : 0;
          return (
            <div key={b.currency} style={{ marginBottom: 7 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 3 }}>
                <span>{b.currency}</span>
                <span className="num muted">
                  {twd(b.value_twd)} TWD · {share.toFixed(1)}%
                </span>
              </div>
              <div style={{ height: 6, background: 'var(--panel-2)' }}>
                <div style={{ height: '100%', width: `${share}%`, background: 'var(--green)' }} />
              </div>
            </div>
          );
        })
      )}

      <Sec>帳戶狀態</Sec>
      <Tiles
        items={[
          {
            k: '交易模式',
            v: dash.data?.risk_mode === 'live' ? '🔴 實盤' : '📝 模擬盤',
            cls: dash.data?.risk_mode === 'live' ? 'down' : 'up',
          },
          { k: '核准政策', v: dash.data?.trade_approval ?? '—' },
        ]}
      />

      {rec?.note && <Note warn>{rec.note}</Note>}
    </>
  );
}

// ── 艙位 ────────────────────────────────────────────────────

function Lots() {
  const { data, loading, error, reload } = useAsync((s) => getPositions(s), []);
  const [open, setOpen] = useState<string | null>(null);

  if (loading || error) return <AsyncState loading={loading} error={error} onRetry={reload} />;

  // 「先展示對得上的」：成本可信度高的排前面，同級再依市值。
  const list = [...(data?.positions ?? [])].sort((a, b) => {
    const d = (b.basis_known_pct ?? 0) - (a.basis_known_pct ?? 0);
    return Math.abs(d) > 1 ? d : b.value_twd - a.value_twd;
  });

  if (!list.length) return <div className="empty">目前沒有持倉</div>;

  return (
    <>
      {/* ⚠ JSX 不是 markdown：這裡要強調得用 <b>，寫 **成本** 會原樣印出星號 */}
      <p className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
        數量已經對到交易所餘額；徽章標的是<b>成本</b>有多少比例查得到來源。點一列看批次組成。
      </p>

      {list.map((p) => {
        const t = basisTrust(p);
        const isOpen = open === p.currency;
        return (
          <div key={p.currency} style={{ marginBottom: 8, background: 'var(--panel-2)' }}>
            <button
              className="news-item"
              style={{ borderBottom: 'none' }}
              aria-selected={isOpen}
              onClick={() => setOpen(isOpen ? null : p.currency)}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <b style={{ fontSize: 14 }}>{p.currency}</b>
                <TrustBadge level={t}>
                  {p.basis_known_pct != null ? `成本已知 ${p.basis_known_pct.toFixed(0)}%` : '成本來源不明'}
                </TrustBadge>
                <span className="muted" style={{ fontSize: 11 }}>{p.lots} 批</span>
              </span>
              <span className="k" style={{ color: 'var(--dim)', letterSpacing: 0 }}>
                {qty(p.qty)} · 均價 {twd(p.avg_cost_twd)} → 現價 {twd(p.price_twd)}
              </span>
              <span style={{ display: 'flex', justifyContent: 'space-between', marginTop: 5, fontSize: 12 }}>
                <span className="num muted">市值 {twd(p.value_twd)}</span>
                <span className={`num ${signCls(p.unrealized_pnl_twd)}`}>
                  {p.unrealized_pnl_twd > 0 ? '+' : ''}
                  {twd(p.unrealized_pnl_twd)} ({pct(p.unrealized_pnl_pct)})
                </span>
              </span>
            </button>

            {isOpen && (
              <div style={{ padding: '0 10px 10px' }}>
                {(p.lot_groups ?? []).length === 0 ? (
                  <div className="muted" style={{ fontSize: 12, padding: 8 }}>沒有批次明細</div>
                ) : (
                  <table className="pos-table">
                    <thead>
                      <tr>
                        <th>取得期間</th>
                        <th>數量</th>
                        <th>均價</th>
                        <th>未實現</th>
                        <th>成本來源</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(p.lot_groups ?? []).map((g, i) => (
                        <tr key={`${g.period}-${i}`}>
                          <td>{g.period}</td>
                          <td>{qty(g.qty)}</td>
                          <td>{twd(g.avg_cost_twd)}</td>
                          <td className={signCls(g.unrealized_pnl_twd)}>{twd(g.unrealized_pnl_twd)}</td>
                          <td className={g.basis === 'known' ? 'up' : 'muted'}>
                            {g.basis === 'known' ? '已知' : '推估'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
          </div>
        );
      })}

      {/*
        引擎為了對上交易所餘額做的校正。它不是雜訊 —— 它正是「帳本與交易所
        差在哪」的證據，藏起來會讓上面那句「數量已經對到交易所」變成空話。
      */}
      {(data?.adjustments ?? []).length > 0 && (
        <>
          <Sec>對到交易所餘額所做的校正</Sec>
          {(data?.adjustments ?? []).map((a, i) => (
            <div key={i} className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
              <b>{a.currency}</b> {a.action} {qty(a.qty)} — {a.reason}
            </div>
          ))}
        </>
      )}
    </>
  );
}

// ── 錢包餘額 ────────────────────────────────────────────────

function Wallet() {
  const { data, loading, error, reload } = useAsync((s) => getDashboard(s), []);
  if (loading || error) return <AsyncState loading={loading} error={error} onRetry={reload} />;

  if (data?.account_error) {
    return (
      <div className="empty">
        沒有讀到 MAX 帳戶
        <Note warn>{data.account_error}</Note>
      </div>
    );
  }
  const bals = data?.balances ?? [];
  if (!bals.length) return <div className="empty">錢包是空的</div>;

  return (
    <>
      <Tiles items={[{ k: '總估值', v: `${twd(data?.total_value_twd)} TWD` }]} />
      <table className="pos-table">
        <thead>
          <tr>
            <th>幣種</th>
            <th>可用</th>
            <th>鎖定</th>
            <th>質押</th>
            <th>估值 TWD</th>
          </tr>
        </thead>
        <tbody>
          {bals.map((b) => (
            <tr key={b.currency}>
              <td>
                {b.currency}
                {/* 持有、可質押、但還沒質押 → 這是使用者現在就能做的一件事 */}
                {b.stakeable && b.balance > 0 && !(b.staked ?? 0) && (
                  <span className="muted" style={{ fontSize: 10, marginLeft: 6 }}>可質押</span>
                )}
              </td>
              <td>{qty(b.balance)}</td>
              <td className={b.locked ? '' : 'muted'}>{b.locked ? qty(b.locked) : '—'}</td>
              <td className={b.staked ? '' : 'muted'}>{b.staked ? qty(b.staked) : '—'}</td>
              <td className={b.value_twd == null ? 'muted' : ''}>
                {b.value_twd == null ? '無報價' : twd(b.value_twd)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

// ── 質押獎勵 ────────────────────────────────────────────────

const REWARD_LABEL: Record<string, string> = {
  holding_reward: '持有獎勵',
  staking_reward: '質押獎勵',
  commission: '佣金回饋',
  airdrop_reward: '空投',
  vip_rebate: 'VIP 回饋',
  trading_reward: '交易獎勵',
  savings_interest: '活存利息',
  mining_reward: '挖礦',
  redemption_reward: '贖回',
  yield: '收益',
};

function Rewards() {
  const { data, loading, error, reload } = useAsync((s) => getDashboard(s), []);
  if (loading || error) return <AsyncState loading={loading} error={error} onRetry={reload} />;

  const rw = data?.rewards;
  if (!rw || !rw.count) return <div className="empty">沒有獎勵紀錄</div>;

  const byCur = Object.entries(rw.by_currency ?? {}).sort((a, b) => b[1] - a[1]);
  const byType = Object.entries(rw.by_type ?? {}).sort((a, b) => b[1] - a[1]);

  return (
    <>
      <Tiles items={[{ k: '累計獎勵筆數', v: rw.count }]} />
      <Sec>依幣種</Sec>
      <Tiles items={byCur.map(([c, v]) => ({ k: c, v: qty(v), cls: 'num up' }))} />
      <Sec>依類型</Sec>
      <table className="pos-table">
        <tbody>
          {byType.map(([t, v]) => (
            <tr key={t}>
              <td>{REWARD_LABEL[t] ?? t}</td>
              <td className="up">{qty(v)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

// ── 融資錢包 ────────────────────────────────────────────────

function MarginView() {
  const { data, loading, error, reload } = useAsync((s) => getDashboard(s), []);
  if (loading || error) return <AsyncState loading={loading} error={error} onRetry={reload} />;

  const m = data?.margin;
  // 沒有融資部位時後端**根本不輸出 margin** —— 那不是錯誤，是「你沒在玩融資」，
  // 所以這裡講的是一句正常的話，不是空狀態的抱歉。
  if (!m) return <div className="empty">沒有使用融資錢包</div>;

  const debt = m.debt_in_usdt ?? 0;
  const ad = m.ad_ratio;
  const hasDebt = debt > 1e-9;

  let cls = 'up';
  let risk = '無融資負債';
  if (hasDebt && ad != null) {
    if (ad >= 2) { cls = 'up'; risk = '🟢 安全'; }
    else if (ad >= 1.5) { cls = ''; risk = '🟡 注意'; }
    else { cls = 'down'; risk = '🔴 高風險 · 接近清算'; }
  }

  return (
    <>
      <Tiles
        items={[
          { k: '淨值', v: m.net_equity_twd != null ? `${twd(m.net_equity_twd)} TWD` : '—' },
          { k: '資產 (USDT)', v: qty(m.asset_in_usdt) },
          { k: '負債 (USDT)', v: qty(debt), cls: hasDebt ? 'num down' : 'num muted' },
          ...(hasDebt ? [{ k: '維持率 AD ratio', v: `${ad?.toFixed(2) ?? '—'} · ${risk}`, cls }] : []),
        ]}
      />
      {(m.balances ?? []).length > 0 && (
        <>
          <Sec>融資錢包餘額</Sec>
          <table className="pos-table">
            <thead>
              <tr><th>幣種</th><th>餘額</th><th>本金</th><th>利息</th></tr>
            </thead>
            <tbody>
              {(m.balances ?? []).map((b) => (
                <tr key={b.currency}>
                  <td>{b.currency}</td>
                  <td>{qty(b.balance)}</td>
                  <td className="muted">{b.principal ? qty(b.principal) : '—'}</td>
                  <td className="muted">{b.interest ? qty(b.interest) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </>
  );
}

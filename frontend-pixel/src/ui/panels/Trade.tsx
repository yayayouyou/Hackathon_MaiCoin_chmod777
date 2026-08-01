import { useEffect, useMemo, useState } from 'react';
import { getBalances, getCostBasis, getMarkets, placeOrder, QUOTES_WITH_LIVE_DATA } from '../../api';
import type { Balance, Market, Quote } from '../../api/types';
import { useAsync } from '../useAsync';
import { DemoData } from '../DemoData';
import { connect, disconnect, useUI } from '../uiStore';

const QUOTES: Quote[] = ['TWD', 'USDT', 'BTC'];
/** MAX 現貨費率：掛單 0.045%、吃單 0.15%（未計 MAX Token 折扣） */
const FEE = { limit: 0.00045, market: 0.0015 };

function fmt(n: number, quote: Quote): string {
  if (quote === 'BTC') return n.toFixed(6);
  if (n >= 1000) return n.toLocaleString('zh-TW', { maximumFractionDigits: 0 });
  if (n >= 1) return n.toFixed(2);
  return n.toPrecision(4);
}

const twd = (n: number) => n.toLocaleString('zh-TW', { maximumFractionDigits: 0 });

/** 拿不到的數字一律顯示破折號，不要拿 0 冒充。 */
const orDash = (n: number | null, render: (v: number) => string) => (n === null ? '—' : render(n));

/** 小數位數隨數量級調整：均價 1.62 不該被四捨五入成 2。 */
function money(n: number): string {
  const abs = Math.abs(n);
  const d = abs >= 1000 ? 0 : abs >= 10 ? 2 : abs >= 1 ? 3 : 6;
  return n.toLocaleString('zh-TW', { maximumFractionDigits: d });
}

/** 限價單帶入的價格取到該價位合理的最小跳動單位，不要出現一長串小數。 */
function tickPrice(p: number): string {
  return p.toFixed(p >= 10000 ? 0 : p >= 100 ? 1 : p >= 1 ? 2 : 6);
}

export function Trade() {
  const { connected } = useUI();
  const [quote, setQuote] = useState<Quote>('TWD');
  const [q, setQ] = useState('');
  const [picked, setPicked] = useState<string | null>(null);

  /**
   * 行情每 3 秒輪詢一次。useAsync 在定時重抓時不會翻 loading、也不清舊資料，
   * 加上 React 靠 key 保留 DOM 節點，所以列表捲動位置與輸入焦點都不會被打斷。
   */
  const mkts = useAsync(() => getMarkets(quote), [quote], { intervalMs: 3000 });
  const bal = useAsync(
    () => (connected ? getBalances() : Promise.resolve<Balance[]>([])),
    [connected],
  );

  const list = useMemo(() => {
    const kw = q.trim().toLowerCase();
    return (mkts.data ?? []).filter(
      (m) => !kw || m.base.toLowerCase().includes(kw) || m.name.toLowerCase().includes(kw),
    );
  }, [mkts.data, q]);

  const sel = list.find((m) => m.id === picked) ?? list[0] ?? null;

  return (
    <div className="trade">
      <MarketList
        quote={quote}
        onQuote={(nq) => {
          setQuote(nq);
          setPicked(null);
        }}
        q={q}
        onQ={setQ}
        list={list}
        loading={mkts.loading}
        error={mkts.error}
        selId={sel?.id ?? null}
        onPick={setPicked}
      />

      <div className="col">
        <h3>下單</h3>
        {connected ? (
          sel ? (
            <OrderForm market={sel} balances={bal.data ?? []} onDone={bal.reload} />
          ) : (
            <div className="empty">請先選擇交易對</div>
          )
        ) : (
          <CredsForm />
        )}
      </div>

      <div className="col">
        <h3>當前持倉</h3>
        {connected ? <Positions state={bal} /> : <Locked />}
      </div>
    </div>
  );
}

// ── 左欄：行情 ──────────────────────────────────────────────

function MarketList({
  quote,
  onQuote,
  q,
  onQ,
  list,
  loading,
  error,
  selId,
  onPick,
}: {
  quote: Quote;
  onQuote: (q: Quote) => void;
  q: string;
  onQ: (v: string) => void;
  list: Market[];
  loading: boolean;
  error: string | null;
  selId: string | null;
  onPick: (id: string) => void;
}) {
  return (
    <div className="col">
      <h3>交易對</h3>
      <div className="tabs" style={{ marginBottom: 8 }}>
        {QUOTES.map((qt) => (
          <button key={qt} aria-selected={quote === qt} onClick={() => onQuote(qt)}>
            {qt}
          </button>
        ))}
      </div>
      <input
        type="text"
        placeholder="搜尋幣種…"
        value={q}
        onChange={(e) => onQ(e.target.value)}
        style={{ marginBottom: 8 }}
      />
      {/* 輪詢失敗時保留最後一次的價格，只在上面標示異常 */}
      {error && (
        <p className="muted" style={{ fontSize: 11, color: 'var(--rose)', marginBottom: 6 }}>
          ⚠ {error}
        </p>
      )}
      {/* 行情端點只服務 TWD。空列表配上「找不到交易對」會被誤讀成搜尋沒中，
          所以這裡要講清楚是後端還沒有這個計價幣的資料。 */}
      {!QUOTES_WITH_LIVE_DATA.includes(quote) && (
        <p className="muted" role="note" style={{ fontSize: 11, lineHeight: 1.5, marginBottom: 8, color: 'var(--amber)' }}>
          ⚠ 後端行情端點目前只提供 <b>TWD</b> 計價的即時報價，{quote} 交易對尚未接上。
        </p>
      )}
      {loading ? (
        <div className="state">
          <span className="spinner" />
        </div>
      ) : (
        <div className="mkt-list">
          {list.map((m) => (
            <button key={m.id} className="mkt-row" aria-selected={m.id === selId} onClick={() => onPick(m.id)}>
              <span>
                <span className="sym">
                  {m.base}
                  <span className="muted">/{m.quote}</span>
                </span>
                <br />
                <span className="sub">{m.name}</span>
              </span>
              <span className="num">{fmt(m.price, m.quote)}</span>
              <span className={`chg num ${m.change >= 0 ? 'up' : 'down'}`}>
                {m.change >= 0 ? '+' : ''}
                {m.change.toFixed(2)}%
              </span>
            </button>
          ))}
          {list.length === 0 && <div className="empty">找不到交易對</div>}
        </div>
      )}
    </div>
  );
}

// ── 中欄：下單 / API 閘門 ───────────────────────────────────

function OrderForm({
  market,
  balances,
  onDone,
}: {
  market: Market;
  balances: Balance[];
  onDone: () => void;
}) {
  const [side, setSide] = useState<'buy' | 'sell'>('buy');
  const [type, setType] = useState<'limit' | 'market'>('limit');
  const [price, setPrice] = useState('');
  const [volume, setVolume] = useState('');
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<{ text: string; err: boolean } | null>(null);

  /**
   * 只在「換交易對」時把價格帶入，不跟著每 3 秒的輪詢走。
   * 否則使用者正在改價格會被行情蓋掉，那是最惱人的交易介面缺陷。
   */
  useEffect(() => {
    setPrice(tickPrice(market.price));
    setVolume('');
    setToast(null);
  }, [market.id]);

  const avail = (asset: string) => balances.find((b) => b.asset === asset)?.available ?? 0;
  const px = type === 'market' ? market.price : Number(price) || 0;
  const vol = Number(volume) || 0;
  const total = px * vol;
  const fee = total * FEE[type];
  const max = side === 'buy' ? (px > 0 ? avail(market.quote) / px : 0) : avail(market.base);
  const invalid = vol <= 0 || (type === 'limit' && px <= 0) || vol > max;

  const submit = async () => {
    setBusy(true);
    setToast(null);
    try {
      const r = await placeOrder({
        marketId: market.id,
        side,
        type,
        ...(type === 'limit' && { price: px }),
        volume: vol,
      });
      setToast({ text: `${r.message}（單號 ${r.id}）`, err: false });
      setVolume('');
      onDone();
    } catch (e) {
      setToast({ text: e instanceof Error ? e.message : '下單失敗', err: true });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <DemoData what="下單" />
      <div className="side-tabs">
        <button data-side="buy" aria-selected={side === 'buy'} onClick={() => setSide('buy')}>
          買入
        </button>
        <button data-side="sell" aria-selected={side === 'sell'} onClick={() => setSide('sell')}>
          賣出
        </button>
      </div>

      <div className="tabs" style={{ marginBottom: 10 }}>
        {(['limit', 'market'] as const).map((t) => (
          <button key={t} aria-selected={type === t} onClick={() => setType(t)}>
            {t === 'limit' ? '限價' : '市價'}
          </button>
        ))}
      </div>

      <label className="field">
        <span>價格（{market.quote}）</span>
        <input
          type="number"
          value={type === 'market' ? '' : price}
          placeholder={type === 'market' ? '以市價成交' : ''}
          disabled={type === 'market'}
          onChange={(e) => setPrice(e.target.value)}
        />
      </label>

      <label className="field">
        <span>數量（{market.base}）</span>
        <input type="number" value={volume} onChange={(e) => setVolume(e.target.value)} />
      </label>

      <div className="pcts">
        {[25, 50, 75, 100].map((p) => (
          <button key={p} onClick={() => setVolume(((max * p) / 100).toFixed(6))}>
            {p}%
          </button>
        ))}
      </div>

      <div className="summary">
        <span>可用</span>
        <span className="num">
          {side === 'buy'
            ? `${fmt(avail(market.quote), market.quote)} ${market.quote}`
            : `${avail(market.base).toFixed(6)} ${market.base}`}
        </span>
      </div>
      <div className="summary">
        <span>成交額</span>
        <span className="num">
          {fmt(total, market.quote)} {market.quote}
        </span>
      </div>
      <div className="summary">
        <span>手續費 ({(FEE[type] * 100).toFixed(3)}%)</span>
        <span className="num muted">
          {fmt(fee, market.quote)} {market.quote}
        </span>
      </div>

      <button className="submit" data-side={side} disabled={invalid || busy} onClick={() => void submit()}>
        {busy ? '送出中…' : `${side === 'buy' ? '買入' : '賣出'} ${market.base}`}
      </button>
      {vol > max && (
        <p className="muted" style={{ fontSize: 11, color: 'var(--rose)', marginTop: 6 }}>
          數量超過可用餘額
        </p>
      )}
      {toast && (
        <div className="toast" data-err={toast.err}>
          {toast.text}
        </div>
      )}
    </>
  );
}

/**
 * 這裡曾經是一張收 MAX ACCESS/SECRET KEY 的表單。
 *
 * 拿掉的理由：**那兩個欄位收到的金鑰哪裡都沒去。** 真正在對 MAX 簽名的是後端
 * （`.env` 的 `MAX_API_KEY`）。一張問你要交易所 secret、卻只是把它丟掉的表單，
 * 比沒有表單危險 —— 使用者沒有理由知道它是裝飾，而他填進去的是真的金鑰。
 */
function CredsForm() {
  return (
    <div className="gate-mask">
      <h4>查看我的 MAX 帳戶</h4>
      <p>餘額與持倉由後端以伺服器端保管的 MAX API 金鑰讀取。左側行情是公開資料，不需要這一步。</p>
      <button className="btn btn-primary" onClick={() => connect()}>
        連接
      </button>
      <p className="warn">
        瀏覽器不會、也不該持有交易所金鑰 —— 任何一個 XSS 都能把它讀走。簽名一律在後端完成。
      </p>
    </div>
  );
}

function Locked() {
  return (
    <div className="gate-mask">
      <h4>持倉未載入</h4>
      <p>點左側的「連接」即可向後端讀取你的現貨持有部位、成本與未實現盈虧。</p>
    </div>
  );
}

// ── 右欄：持倉 ──────────────────────────────────────────────

function Positions({ state }: { state: ReturnType<typeof useAsync<Balance[]>> }) {
  const { data, loading, error, reload } = state;
  // 成本另外抓，不擋餘額 —— 那支端點要重播整本帳本，會慢好幾秒。
  const cost = useAsync(() => getCostBasis(), []);

  if (loading) {
    return (
      <div className="state">
        <span className="spinner" />
        讀取帳戶…
      </div>
    );
  }
  if (error) {
    return (
      <div className="state err">
        <p>⚠ {error}</p>
        <button className="btn" onClick={reload}>
          重試
        </button>
      </div>
    );
  }

  const qtyOf = (b: Balance) => b.available + b.locked + b.staked;
  const rows = (data ?? []).filter((b) => qtyOf(b) > 0);
  const totalValue = rows.reduce((s, b) => s + (b.price === null ? 0 : qtyOf(b) * b.price), 0);
  const avgCostOf = (asset: string) => (asset === 'TWD' ? 1 : cost.data?.get(asset) ?? null);
  const noCostBasis = !cost.loading && rows.some((b) => b.asset !== 'TWD' && avgCostOf(b.asset) === null);

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <span className="badge">
          <i />
          已連接
        </span>
        <button className="btn" style={{ padding: '3px 10px', fontSize: 11 }} onClick={disconnect}>
          中斷連接
        </button>
      </div>
      <div className="summary" style={{ marginBottom: 8 }}>
        <span>資產總值</span>
        <b className="num">NT$ {twd(totalValue)}</b>
      </div>
      {/* col-drop 的欄位在窄螢幕會被 CSS 藏起來，只留幣種/可用/現值/盈虧 */}
      <div className="pos-scroll">
        <table className="pos-table">
          <thead>
            <tr>
              <th>幣種</th>
              <th>可用</th>
              <th className="col-drop">凍結</th>
              <th className="col-drop">均價</th>
              <th>現值</th>
              <th>盈虧</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((b) => {
              const qty = qtyOf(b);
              const frozen = b.locked + b.staked;
              const value = b.price === null ? null : qty * b.price;
              const avgCost = avgCostOf(b.asset);
              const known = b.asset !== 'TWD' && b.price !== null && avgCost !== null;
              const pnl = known ? value! - qty * avgCost! : null;
              const pct = known && avgCost! > 0 ? (b.price! / avgCost! - 1) * 100 : null;
              return (
                <tr key={b.asset}>
                  <td>{b.asset}</td>
                  <td>{b.available.toLocaleString('zh-TW', { maximumFractionDigits: 5 })}</td>
                  <td className="muted col-drop" title={b.staked > 0 ? `含質押中 ${b.staked}` : undefined}>
                    {frozen > 0 ? frozen.toLocaleString('zh-TW', { maximumFractionDigits: 5 }) : '—'}
                  </td>
                  <td className="muted col-drop">
                    {b.asset === 'TWD' ? '—' : cost.loading ? '計算中…' : orDash(avgCost, money)}
                  </td>
                  <td>{orDash(value, twd)}</td>
                  <td className={pnl === null ? 'muted' : pnl > 0 ? 'up' : pnl < 0 ? 'down' : 'muted'}>
                    {pnl === null || pct === null
                      ? '—'
                      : `${pnl >= 0 ? '+' : ''}${twd(pnl)} (${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%)`}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {noCostBasis && (
        <p className="muted" role="note" style={{ fontSize: 11, lineHeight: 1.5, marginTop: 10, color: 'var(--amber)' }}>
          ⚠ 均價與盈虧顯示「—」：成本要由 <code>/api/positions</code> 重播交易帳本才算得出來，這次沒有取得{cost.error ? `（${cost.error}）` : ''}。
        </p>
      )}
      <p className="muted" style={{ fontSize: 11, marginTop: 10 }}>
        餘額與均價來自後端的 MAX API 金鑰。重整頁面後這裡會回到未連接狀態。
      </p>
    </>
  );
}

import { useEffect, useMemo, useState } from 'react';
import { getDashboard, type Balance } from '../../api/account';
import {
  getMarketRows, previewOrder,
  type MarketRow, type OrderPreview, type OrdType,
} from '../../api/trade';
import { approveOrder, rejectOrder } from '../../api/agent';
import { useAsync } from '../useAsync';
import { AsyncState } from '../Panel';

/**
 * 現貨交易。CharPanel 的「交易」分頁，不是獨立面板。
 *
 * ⚠ **下單是兩步的，而且第二步才會真的送出。**
 *
 *     表單 → previewOrder() → 後端凍結計畫 + token → 確認框 → approveOrder()
 *
 *   確認框裡的每一個數字都來自**後端凍結的計畫**，不是畫面上的表單值。這不是
 *   多此一舉：確認框開著的時候表單還可能被改（誤觸百分比鈕、行情把價格帶動），
 *   而使用者按下確認時同意的必須就是實際送出的那一筆。模式（模擬／實盤）
 *   也在 preview 當下凍住 —— 否則「在模擬盤按下核准、送出前 .env 被改成 live」
 *   就會變成真單。這條互鎖與 MAIA 對話下單走的是同一支後端。
 *
 * ⚠ 這個面板**沒有**任何直接下單的路徑。取消時會呼叫 rejectOrder() 把 token
 *   作廢，不是只把畫面關掉 —— 留著一個活的 pending token 等於留了一把鑰匙。
 *
 * 金鑰不在瀏覽器。規格 §「金鑰輸入框放在 boot」那條已經否決過在前端收金鑰：
 * HMAC 簽章在伺服器端，前端只顯示「後端有沒有綁到帳戶」。
 */

const QUOTES = ['twd', 'usdt', 'btc'] as const;
type QuoteId = (typeof QUOTES)[number];

/**
 * MAX 的現貨費率。只用來預估，實際以成交回報為準。
 *
 * post_only 保證是 maker，所以它吃的一定是 maker 費率 —— 這是「只掛單」除了
 * 不會立刻成交之外的第二個好處，費率是市價單的一半。
 */
const FEE: Record<OrdType, number> = { limit: 0.0008, market: 0.0016, post_only: 0.0008 };

const ORD_TYPES: Array<{ id: OrdType; label: string; hint: string }> = [
  { id: 'limit', label: '限價', hint: '指定價格，可能立刻成交也可能掛著等' },
  { id: 'post_only', label: '只掛單', hint: '保證不會立刻成交：會成交的話交易所整筆拒絕（maker 費率）' },
  { id: 'market', label: '市價', hint: '立刻以市價成交' },
];

/** 美元計價的穩定幣。使用者下單前最常確認的就是「台幣還有多少、U 還有多少」。 */
const USD_LIKE = new Set(['USDT', 'USDC', 'USDX']);

function money(n: number, digits = 2): string {
  if (!Number.isFinite(n)) return '—';
  return n.toLocaleString('en-US', { maximumFractionDigits: digits });
}

/** 依交易對的精度截位。多送小數位 MAX 會直接退件。 */
function trim(n: number, precision?: number | null): string {
  const p = typeof precision === 'number' && precision >= 0 ? Math.min(precision, 8) : 8;
  return String(Number(n.toFixed(p)));
}

/** 只掛單的預設讓價幅度。夠遠到不會被行情跳動吃掉，又夠近到還排得上隊伍前面。 */
const POST_ONLY_OFFSET = 0.001;

/**
 * 表單的預設委託價。
 *
 * 只掛單必須落在**被動側**（買在市價之下、賣在市價之上），否則交易所整筆拒絕。
 * 預設直接帶市價的話，一選「只掛單」按鈕就是灰的 —— 一個預設就無法送出的
 * 表單會讓人以為壞了，而不是以為自己要改價。
 */
function seedPrice(type: OrdType, side: 'buy' | 'sell', m: MarketRow): string {
  if (type !== 'post_only') return trim(m.last, m.quote_precision);
  const k = side === 'buy' ? 1 - POST_ONLY_OFFSET : 1 + POST_ONLY_OFFSET;
  return trim(m.last * k, m.quote_precision);
}

export function Trade() {
  const [quote, setQuote] = useState<QuoteId>('twd');
  const [q, setQ] = useState('');
  const [picked, setPicked] = useState<string | null>(null);

  /**
   * 市場每 5 秒重抓（後端有 60 秒快取，所以實際打 MAX 的頻率遠低於此）。
   * useAsync 定時重抓時不翻 loading、不清舊資料，所以捲動位置與輸入焦點不會斷。
   */
  const mkts = useAsync((s) => getMarketRows(quote, s), [quote], { intervalMs: 5000 });
  const dash = useAsync((s) => getDashboard(s), []);

  const list = useMemo(() => {
    const kw = q.trim().toLowerCase();
    return (mkts.data ?? []).filter((m) => !kw || m.base.toLowerCase().includes(kw));
  }, [mkts.data, q]);

  const sel = list.find((m) => m.id === picked) ?? list[0] ?? null;
  const balances = dash.data?.balances ?? [];
  const hasAccount = dash.data?.has_account === true;

  return (
    <div className="trade">
      <div className="col">
        <h3>交易對</h3>
        <div className="tabs" style={{ marginBottom: 8 }}>
          {QUOTES.map((qt) => (
            <button
              key={qt}
              aria-selected={quote === qt}
              onClick={() => {
                setQuote(qt);
                setPicked(null);
              }}
            >
              {qt.toUpperCase()}
            </button>
          ))}
        </div>
        <input
          type="text"
          placeholder="搜尋幣種…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          style={{ marginBottom: 8 }}
        />
        <AsyncState loading={mkts.loading} error={mkts.error} onRetry={mkts.reload} />
        <div className="mkt-list">
          {list.map((m) => (
            <div
              key={m.id}
              className="mkt-row"
              role="button"
              tabIndex={0}
              aria-selected={m.id === sel?.id}
              onClick={() => setPicked(m.id)}
              onKeyDown={(e) => e.key === 'Enter' && setPicked(m.id)}
            >
              <span>
                <span className="sym">{m.base}</span>
                <span className="sub">/{m.quote.toUpperCase()}</span>
              </span>
              <span className="num">{money(m.last, m.last >= 1000 ? 0 : 4)}</span>
              <span className={`chg num ${m.pct >= 0 ? 'up' : 'down'}`}>
                {m.pct >= 0 ? '+' : ''}
                {m.pct.toFixed(2)}%
              </span>
            </div>
          ))}
          {!mkts.loading && list.length === 0 && <div className="empty">沒有符合的交易對</div>}
        </div>
      </div>

      <div className="col">
        <h3>下單</h3>
        {dash.loading ? (
          <AsyncState loading error={null} />
        ) : !hasAccount ? (
          <AccountGate detail={dash.data?.account_error} />
        ) : sel ? (
          <OrderForm market={sel} balances={balances} onDone={dash.reload} />
        ) : (
          <div className="empty">請先選擇交易對</div>
        )}
      </div>

      <div className="col">
        <h3>我的餘額</h3>
        <Balances state={dash} />
      </div>
    </div>
  );
}

// ── 帳戶狀態（取代原本在瀏覽器收金鑰的表單）───────────────

function AccountGate({ detail }: { detail?: string }) {
  return (
    <div className="gate-mask">
      <h4>後端未綁定 MAX 帳戶</h4>
      <p>
        金鑰放在後端（HMAC 簽章在伺服器端完成），瀏覽器不經手也不儲存。
        請在 <code>agent-core/.env</code> 設定 <code>MAX_API_KEY</code> 與{' '}
        <code>MAX_API_SECRET</code> 後重啟後端。
      </p>
      <p className="muted" style={{ fontSize: 11 }}>
        驗證方式：<code>python scripts/max_check.py</code>
      </p>
      {detail && (
        <div className="toast" data-err="true">
          {detail}
        </div>
      )}
    </div>
  );
}

// ── 餘額 ────────────────────────────────────────────────────

function Balances({ state }: { state: ReturnType<typeof useAsync<Awaited<ReturnType<typeof getDashboard>>>> }) {
  const { data, loading, error, reload } = state;
  if (loading || error) return <AsyncState loading={loading} error={error} onRetry={reload} />;

  const all = data?.balances ?? [];
  if (!all.length) return <div className="empty">沒有餘額</div>;

  /**
   * 台幣與美元穩定幣置頂：下單前要確認的就是這兩個，不該讓人在清單裡找。
   *
   * ⚠ TWD 與 USDT **就算是 0 也要畫出來**。後端只回餘額 > 0.000001 的幣種，
   *   所以沒有 U 的時候這一格會整個消失 —— 但「看不到 USDT」與「USDT 是 0」
   *   在下單前是兩件完全不同的事，前者會讓人以為沒載到而重新整理。
   */
  const PINNED = ['TWD', 'USDT'];
  const cash = [
    ...PINNED.map(
      (c) => all.find((b) => b.currency === c) ?? { currency: c, balance: 0, locked: 0, staked: 0 },
    ),
    ...all.filter((b) => !PINNED.includes(b.currency) && USD_LIKE.has(b.currency)),
  ];
  const rest = all
    .filter((b) => !PINNED.includes(b.currency) && !USD_LIKE.has(b.currency))
    .sort((a, b) => (b.value_twd ?? 0) - (a.value_twd ?? 0));

  return (
    <div className="pos-scroll">
      {cash.map((b) => (
        <div
          key={b.currency}
          style={{
            padding: '10px 12px',
            marginBottom: 6,
            background: 'var(--panel-2)',
            borderLeft: `2px solid ${b.currency === 'TWD' ? 'var(--cyan)' : 'var(--green)'}`,
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <b style={{ fontSize: 13 }}>{b.currency}</b>
            <b className="num" style={{ fontSize: 16 }}>
              {money(b.balance, 6)}
            </b>
          </div>
          {(b.locked ?? 0) > 0 && (
            <div className="muted" style={{ fontSize: 11, marginTop: 3 }}>
              掛單鎖定 {money(b.locked ?? 0, 6)}
            </div>
          )}
        </div>
      ))}

      {rest.length > 0 && (
        <table className="pos-table" style={{ marginTop: 8 }}>
          <thead>
            <tr>
              <th>幣種</th>
              <th>可用</th>
              <th>估值 TWD</th>
            </tr>
          </thead>
          <tbody>
            {rest.map((b) => (
              <tr key={b.currency}>
                <td>{b.currency}</td>
                <td>{money(b.balance, 6)}</td>
                <td className={b.value_twd == null ? 'muted' : ''}>
                  {b.value_twd == null ? '無報價' : money(b.value_twd, 0)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
        總估值 {money(data?.total_value_twd ?? 0, 0)} TWD
      </div>
    </div>
  );
}

// ── 下單表單 ────────────────────────────────────────────────

function OrderForm({
  market,
  balances,
  onDone,
}: {
  market: MarketRow;
  balances: Balance[];
  onDone: () => void;
}) {
  const [side, setSide] = useState<'buy' | 'sell'>('buy');
  // 預設「只掛單」：這個介面的預設行為應該是最不會意外花錢的那一個。
  const [type, setType] = useState<OrdType>('post_only');
  const [price, setPrice] = useState('');
  const [volume, setVolume] = useState('');
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<OrderPreview | null>(null);
  const [toast, setToast] = useState<{ text: string; err: boolean } | null>(null);

  // 只在換交易對時清空數量，不跟著每 5 秒的輪詢走 ——
  // 使用者正在改價格卻被行情蓋掉，是最惱人的交易介面缺陷。
  useEffect(() => {
    setVolume('');
    setPreview(null);
    setToast(null);
  }, [market.id]);

  /**
   * 委託價在「換交易對／換方向／換委託型別」時重新帶入。
   *
   * 方向與型別也要重帶，因為只掛單的合法價格區間是**單向**的：買單要在市價
   * 之下、賣單要在市價之上。從買切到賣時沿用舊價格，等於必定落在錯的那一側。
   * 一樣不跟輪詢走 —— 依賴只有這三個，行情跳動不會蓋掉手動輸入。
   */
  useEffect(() => {
    setPrice(seedPrice(type, side, market));
    // 行情每 5 秒換一次物件，但這裡只依賴 id/精度，不依賴 market.last
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [market.id, side, type]);

  const quoteCur = market.quote.toUpperCase();
  const avail = (asset: string) => balances.find((b) => b.currency === asset)?.balance ?? 0;
  const px = type === 'market' ? market.last : Number(price) || 0;
  const vol = Number(volume) || 0;
  const total = px * vol;
  const fee = total * FEE[type];
  const max = side === 'buy' ? (px > 0 ? avail(quoteCur) / px : 0) : avail(market.base);
  const minBase = market.min_base_amount ?? 0;

  const tooSmall = minBase > 0 && vol > 0 && vol < minBase;
  /** 只掛單的委託價跨過市價 → 交易所必拒。用最新價近似最佳買/賣價。 */
  const crossesMarket =
    type === 'post_only' && px > 0 &&
    (side === 'buy' ? px >= market.last : px <= market.last);
  const invalid =
    vol <= 0 || (type !== 'market' && px <= 0) || vol > max || tooSmall || crossesMarket;

  const doPreview = async () => {
    setBusy(true);
    setToast(null);
    try {
      const p = await previewOrder({
        market: market.id,
        side,
        volume: vol,
        ord_type: type,
        // limit 與 post_only 都必須帶價格；市價單不帶
        ...(type !== 'market' && { price: px }),
      });
      setPreview(p);
    } catch (e) {
      setToast({ text: e instanceof Error ? e.message : '無法產生下單計畫', err: true });
    } finally {
      setBusy(false);
    }
  };

  if (preview) {
    return (
      <ConfirmOrder
        preview={preview}
        onSent={(msg) => {
          setPreview(null);
          setVolume('');
          setToast({ text: msg, err: false });
          onDone();
        }}
        onCancel={(msg) => {
          setPreview(null);
          if (msg) setToast({ text: msg, err: false });
        }}
      />
    );
  }

  return (
    <>
      {/* 下單前最常確認的兩個數字，放在表單正上方而不是右欄 —— 眼睛不用移開 */}
      <div className="summary" style={{ background: 'var(--panel-2)', padding: '6px 8px' }}>
        <span>可用 {side === 'buy' ? quoteCur : market.base}</span>
        <b className="num">{money(side === 'buy' ? avail(quoteCur) : avail(market.base), 6)}</b>
      </div>

      <div className="side-tabs" style={{ marginTop: 10 }}>
        <button data-side="buy" aria-selected={side === 'buy'} onClick={() => setSide('buy')}>
          買入
        </button>
        <button data-side="sell" aria-selected={side === 'sell'} onClick={() => setSide('sell')}>
          賣出
        </button>
      </div>

      <div className="tabs" style={{ marginBottom: 4 }}>
        {ORD_TYPES.map((t) => (
          <button key={t.id} aria-selected={type === t.id} onClick={() => setType(t.id)} title={t.hint}>
            {t.label}
          </button>
        ))}
      </div>
      {/* 委託型別的差別是「錢會不會現在就出去」，值得一行字講清楚而不是只靠 tooltip */}
      <p className="muted" style={{ fontSize: 11, marginBottom: 10 }}>
        {ORD_TYPES.find((t) => t.id === type)?.hint}
      </p>

      <label className="field">
        <span>價格（{quoteCur}）</span>
        <input
          type="number"
          value={type === 'market' ? '' : price}
          placeholder={type === 'market' ? `以市價成交（約 ${money(market.last, 2)}）` : ''}
          disabled={type === 'market'}
          onChange={(e) => setPrice(e.target.value)}
        />
      </label>

      {/*
        只掛單掛不上去的唯一原因就是價格跨過市價，而使用者不會知道「跨過」是
        哪一邊。直接算給他看，並在會被拒的時候先擋住 —— 送出去被交易所退件
        才知道，是最差的學習方式。
      */}
      {type === 'post_only' && crossesMarket && (
        <p style={{ fontSize: 11, color: 'var(--amber)', marginBottom: 8 }}>
          這個價格會立刻成交 → 交易所會整筆拒絕。
          {side === 'buy' ? '買單要低於' : '賣單要高於'}市價 {money(market.last, 4)}。
        </p>
      )}

      <label className="field">
        <span>數量（{market.base}）</span>
        <input type="number" value={volume} onChange={(e) => setVolume(e.target.value)} />
      </label>

      <div className="pcts">
        {[25, 50, 75, 100].map((p) => (
          <button key={p} onClick={() => setVolume(trim((max * p) / 100, market.base_precision))}>
            {p}%
          </button>
        ))}
      </div>

      <div className="summary">
        <span>成交額</span>
        <span className="num">
          {money(total, 2)} {quoteCur}
        </span>
      </div>
      <div className="summary">
        <span>手續費（約 {(FEE[type] * 100).toFixed(2)}%）</span>
        <span className="num muted">
          {money(fee, 4)} {quoteCur}
        </span>
      </div>
      {minBase > 0 && (
        <div className="summary">
          <span>最小下單量</span>
          <span className="num muted">
            {minBase} {market.base}
          </span>
        </div>
      )}

      <button
        className="submit"
        data-side={side}
        disabled={invalid || busy}
        onClick={() => void doPreview()}
      >
        {busy ? '產生計畫中…' : `預覽${side === 'buy' ? '買入' : '賣出'}`}
      </button>
      <p className="muted" style={{ fontSize: 11, marginTop: 6 }}>
        按下之後會再出現一次確認，這一步不會送單。
      </p>

      {vol > max && (
        <p style={{ fontSize: 11, color: 'var(--rose)', marginTop: 6 }}>數量超過可用餘額</p>
      )}
      {tooSmall && (
        <p style={{ fontSize: 11, color: 'var(--rose)', marginTop: 6 }}>
          低於交易所最小下單量 {minBase} {market.base}
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

// ── 確認框 ──────────────────────────────────────────────────

/**
 * 送出前的最後一關。**顯示的每一個數字都取自後端凍結的計畫**，一個都不從
 * 上面的表單讀 —— 那正是這一步存在的意義。
 */
function ConfirmOrder({
  preview,
  onSent,
  onCancel,
}: {
  preview: OrderPreview;
  onSent: (msg: string) => void;
  onCancel: (msg?: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const p = preview.plan;
  const live = preview.mode === 'live';

  // 限價偏離市價多少。手滑把價格打錯一個數量級時，這一行是最後一道人眼防線。
  const dev = p.latest_price > 0 && p.ord_type === 'limit' && p.price
    ? ((p.price - p.latest_price) / p.latest_price) * 100
    : null;

  const ex = preview.exposure;
  const used = ex.notional_twd ?? 0;
  const cap = ex.max_notional_twd ?? 0;

  const confirm = async () => {
    setBusy(true);
    setErr(null);
    const r = await approveOrder(preview.token);
    setBusy(false);
    if (r.ok) onSent(r.detail);
    else setErr(r.detail);
  };

  const cancel = async () => {
    setBusy(true);
    // 不是只把畫面關掉：留著一個活的 pending token 等於留了一把鑰匙
    await rejectOrder(preview.token);
    setBusy(false);
    onCancel('已取消，該筆計畫已作廢');
  };

  return (
    <div
      style={{
        padding: 14,
        background: 'var(--panel-2)',
        border: `2px solid ${live ? 'var(--rose)' : 'var(--line)'}`,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span
          className="badge"
          style={{
            color: live ? 'var(--rose)' : 'var(--dim)',
            borderColor: live ? 'var(--rose)' : 'var(--dim)',
          }}
        >
          <i style={{ background: live ? 'var(--rose)' : 'var(--dim)' }} />
          {live ? '實盤 · 真實資金' : '模擬盤 · 不會送到交易所'}
        </span>
      </div>

      <b style={{ fontSize: 14, display: 'block', marginBottom: 10 }}>{preview.summary}</b>

      <div className="summary">
        <span>交易對</span>
        <span className="num">{p.market.toUpperCase()}</span>
      </div>
      <div className="summary">
        <span>方向 / 類型</span>
        <span className={`num ${p.side === 'buy' ? 'up' : 'down'}`}>
          {p.side === 'buy' ? '買入' : '賣出'} ·{' '}
          {p.ord_type === 'market' ? '市價' : p.ord_type === 'post_only' ? '只掛單' : '限價'}
        </span>
      </div>
      {/* 送出後會發生什麼，在按下去之前講完 */}
      {p.ord_type === 'post_only' && (
        <p className="muted" style={{ fontSize: 11, margin: '4px 0' }}>
          只掛單：掛上訂單簿等待成交，不會立刻成交。若送出當下就會成交，交易所整筆拒絕。
        </p>
      )}
      <div className="summary">
        <span>數量</span>
        <span className="num">{p.volume}</span>
      </div>
      <div className="summary">
        <span>價格</span>
        <span className="num">{p.price != null ? money(p.price, 4) : `市價 ≈ ${money(p.latest_price, 4)}`}</span>
      </div>
      {dev != null && Math.abs(dev) >= 0.5 && (
        <div className="summary">
          <span>偏離市價</span>
          <span className={`num ${Math.abs(dev) > 10 ? 'down' : 'muted'}`}>
            {dev > 0 ? '+' : ''}
            {dev.toFixed(2)}%（市價 {money(p.latest_price, 4)}）
          </span>
        </div>
      )}
      <div className="summary">
        <span>預估金額</span>
        <b className="num">{money(p.est_notional_twd, 0)} TWD</b>
      </div>

      {live && cap > 0 && (
        <div className="summary">
          <span>{ex.window_hours}h 額度</span>
          <span className="num muted">
            {money(used, 0)} → {money(used + p.est_notional_twd, 0)} / {money(cap, 0)} TWD ·{' '}
            {ex.orders ?? 0}/{ex.max_orders ?? 0} 筆
          </span>
        </div>
      )}

      <div className="muted" style={{ fontSize: 10, marginTop: 8, wordBreak: 'break-all' }}>
        計畫指紋 {preview.hash.slice(0, 24)}… · 逾 {preview.ttl_sec} 秒未確認自動失效
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginTop: 12 }}>
        {/* 文字要短到不換行 —— 模式已經由上方的徽章與整個框的紅邊講清楚了 */}
        <button className="submit" data-side={p.side} disabled={busy} onClick={() => void confirm()}>
          {busy ? '送出中…' : live ? '送出真單' : '確認送出'}
        </button>
        <button className="btn" disabled={busy} onClick={() => void cancel()}>
          取消
        </button>
      </div>

      {err && (
        <div className="toast" data-err="true">
          {err}
        </div>
      )}
    </div>
  );
}

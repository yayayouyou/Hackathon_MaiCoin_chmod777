import { getOpenOrders, type OpenOrder } from '../../api/trade';
import { useAsync } from '../useAsync';
import { AsyncState } from '../Panel';

/**
 * 「我的掛單」—— 帳戶目前掛在 MAX 上、還沒成交的委託。
 *
 * 這是「訂單簿」隔壁那一格刻意分開的東西：訂單簿畫的是**整個市場**的買賣盤
 * （別人的量），這一格畫的是**你自己**送出去、正停在 `wait` 等成交的單。
 * 下單（post_only／限價）確認後，右欄會自動跳到這裡，那筆單就出現在清單上。
 *
 * 唯讀。撤單要另外做（後端 `/api/orders` 只讀不寫），這裡不放任何會改動帳戶
 * 的按鈕 —— 一格「看得到掛單」的視圖不該偷偷帶著能動錢的能力。
 */

function fmtPrice(n: number | null): string {
  if (n == null || !Number.isFinite(n)) return '市價';
  if (n >= 1000) return Math.round(n).toLocaleString('en-US');
  if (n >= 1) return n.toFixed(2);
  return n.toFixed(6);
}

/** 建立時間 → HH:MM（今天）。掛單看的是「多久以前掛的」，秒級精度沒意義。 */
function fmtTime(ms?: number | null): string {
  if (!ms || !Number.isFinite(ms)) return '';
  const d = new Date(ms);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

const ORD_LABEL: Record<string, string> = { limit: '限價', market: '市價', post_only: '只掛單' };

function Row({ o }: { o: OpenOrder }) {
  const buy = o.side === 'buy';
  const col = buy ? 'var(--green)' : 'var(--rose)';
  // 成交進度：剩多少沒吃到。只掛單剛送出時是 0%，被吃一部分就往上跑。
  const filled = o.volume > 0 ? (o.executed_volume / o.volume) * 100 : 0;
  return (
    <div
      style={{
        padding: '7px 8px',
        marginBottom: 6,
        background: 'var(--panel-2)',
        borderLeft: `2px solid ${col}`,
        fontSize: 11,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <b style={{ color: col }}>
          {buy ? '買入' : '賣出'} · {ORD_LABEL[o.ord_type] ?? o.ord_type}
        </b>
        <span className="muted" style={{ fontSize: 10 }}>
          {o.market.toUpperCase()} {fmtTime(o.created_at)}
        </span>
      </div>
      <div
        className="num"
        style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, fontVariantNumeric: 'tabular-nums' }}
      >
        <span>
          <span className="muted">價 </span>
          {fmtPrice(o.price)}
        </span>
        <span>
          <span className="muted">剩 </span>
          {o.remaining_volume}
          <span className="muted"> / {o.volume}</span>
        </span>
      </div>
      {filled > 0.01 && (
        <div className="muted" style={{ fontSize: 10, marginTop: 3 }}>
          已成交 {filled.toFixed(1)}%
        </div>
      )}
    </div>
  );
}

export function OpenOrders({ market }: { market: string }) {
  // 4 秒一次。掛單狀態不像訂單簿那樣每秒在跳，慢一點也不會漏掉「單掛上去了」。
  const { data, loading, error, reload } = useAsync(
    (s) => getOpenOrders(market, s),
    [market],
    { intervalMs: 4000 },
  );

  if (loading || error) return <AsyncState loading={loading} error={error} onRetry={reload} />;

  const orders = data ?? [];
  if (!orders.length) {
    return <div className="empty">這個交易對目前沒有掛單中的訂單</div>;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
      <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
        {orders.map((o) => (
          <Row key={String(o.id)} o={o} />
        ))}
      </div>
      <p className="muted" style={{ fontSize: 10, marginTop: 4 }}>
        每 4 秒更新 · 只顯示 {market.toUpperCase()} 掛單中（wait）· 送出後會停在這裡等成交
      </p>
    </div>
  );
}

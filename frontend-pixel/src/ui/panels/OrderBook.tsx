import { getOrderbook, type DepthLevel } from '../../api/trade';
import { useAsync } from '../useAsync';
import { AsyncState } from '../Panel';

/**
 * 即時訂單簿。賣單在上、買單在下，中間是價差 —— 與所有交易所的慣例一致，
 * 反過來會讓看慣盤的人第一眼讀錯方向。
 *
 * 每一列背後的橫條是**累計**數量而不是單筆數量：交易者要看的是「吃到這個
 * 價位為止總共有多少量」，那才是滑點的來源。單筆長度只看得出哪一格比較大。
 *
 * 點價格會把它填進下單表單 —— 訂單簿最常見的用途就是「照這個價掛」。
 */

function fmtPrice(n: number): string {
  if (n >= 1000) return Math.round(n).toLocaleString('en-US');
  if (n >= 1) return n.toFixed(2);
  return n.toFixed(6);
}

function Side({
  rows,
  side,
  maxCum,
  onPick,
}: {
  rows: Array<DepthLevel & { cum: number }>;
  side: 'ask' | 'bid';
  maxCum: number;
  onPick?: (price: number) => void;
}) {
  const col = side === 'ask' ? 'var(--rose)' : 'var(--green)';
  return (
    <>
      {rows.map((r) => (
        <div
          key={r.price}
          role={onPick ? 'button' : undefined}
          tabIndex={onPick ? 0 : undefined}
          onClick={() => onPick?.(r.price)}
          onKeyDown={(e) => e.key === 'Enter' && onPick?.(r.price)}
          style={{
            position: 'relative',
            display: 'grid',
            gridTemplateColumns: '1fr auto',
            padding: '2px 6px',
            fontSize: 11,
            fontFamily: 'var(--mono)',
            fontVariantNumeric: 'tabular-nums',
            cursor: onPick ? 'pointer' : 'default',
          }}
        >
          <span
            style={{
              position: 'absolute',
              right: 0,
              top: 0,
              bottom: 0,
              width: `${maxCum > 0 ? (r.cum / maxCum) * 100 : 0}%`,
              background: side === 'ask' ? '#ff4f7822' : '#4ee88a22',
            }}
          />
          <span style={{ color: col, zIndex: 1 }}>{fmtPrice(r.price)}</span>
          <span style={{ color: 'var(--dim)', zIndex: 1 }}>{r.volume.toFixed(6)}</span>
        </div>
      ))}
    </>
  );
}

export function OrderBook({
  market,
  onPickPrice,
}: {
  market: string;
  onPickPrice?: (price: number) => void;
}) {
  // 2 秒一次。訂單簿是這個面板裡唯一真的需要「即時」的東西
  const { data, loading, error, reload } = useAsync(
    (s) => getOrderbook(market, 14, s),
    [market],
    { intervalMs: 2000 },
  );

  if (loading || error) return <AsyncState loading={loading} error={error} onRetry={reload} />;

  const asks = data?.asks ?? [];
  const bids = data?.bids ?? [];
  if (!asks.length && !bids.length) return <div className="empty">這個交易對沒有掛單</div>;

  /** 由價差往外累加，這樣橫條長度就是「吃到這一檔為止的總量」。 */
  const cumulate = (rows: DepthLevel[]) => {
    let c = 0;
    return rows.map((r) => ({ ...r, cum: (c += r.volume) }));
  };
  const askRows = cumulate(asks);
  const bidRows = cumulate(bids);
  const maxCum = Math.max(askRows.at(-1)?.cum ?? 0, bidRows.at(-1)?.cum ?? 0);

  const bestAsk = asks[0]?.price ?? 0;
  const bestBid = bids[0]?.price ?? 0;
  const spread = bestAsk - bestBid;
  const spreadPct = bestBid > 0 ? (spread / bestBid) * 100 : 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr auto',
          padding: '2px 6px',
          fontSize: 10,
          letterSpacing: '0.08em',
          color: 'var(--dim)',
          borderBottom: '1px solid var(--line)',
        }}
      >
        <span>價格</span>
        <span>數量</span>
      </div>

      <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
        {/* 賣單由高到低往下逼近價差 —— 最貼近成交價的那一檔要在最靠中間 */}
        <Side rows={[...askRows].reverse()} side="ask" maxCum={maxCum} onPick={onPickPrice} />

        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            padding: '5px 6px',
            margin: '3px 0',
            background: 'var(--panel-2)',
            fontSize: 11,
          }}
        >
          <b className="num">{fmtPrice(bestBid)}</b>
          <span className="muted" style={{ fontSize: 10 }}>
            價差 {fmtPrice(spread)}（{spreadPct.toFixed(3)}%）
          </span>
        </div>

        <Side rows={bidRows} side="bid" maxCum={maxCum} onPick={onPickPrice} />
      </div>

      <p className="muted" style={{ fontSize: 10, marginTop: 4 }}>
        每 2 秒更新 · 點價格填入下單表單 · 橫條為累計量
      </p>
    </div>
  );
}

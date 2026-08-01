import type { ReactNode } from 'react';

/**
 * 圖表卡（第一層：零相依 CSS/SVG）。
 *
 * chatStore 把「可畫圖工具」的 tool_result.result 原封留在 charts 狀態，這裡的
 * chartSpecFor(tool, result) 決定畫成哪張卡。全部走 SVG/DOM + CSS 變數，不引任何
 * 繪圖庫、不用 Canvas —— 純宣告式 JSX/SVG，好測也好維護。恐懼貪婪儀表的色帶是資料
 * 語意色，直接寫死 hex。綠漲紅跌固定西式，不做 eastern 換色。
 *
 * 每張卡的資料形狀對齊後端真實回傳（見各 norm* 的註解），normalize 一律先 guard，
 * 拿不到可畫資料就回 null → 由 chartSpecFor 顯示薄的『資料不足』卡而非空框。
 */

// ── 共用小工具 ──────────────────────────────────────────────
const isObj = (x: unknown): x is Record<string, unknown> =>
  typeof x === 'object' && x !== null && !Array.isArray(x);
const hasError = (x: unknown): x is { error: string } =>
  isObj(x) && typeof x.error === 'string' && x.error.length > 0;
const toNum = (x: unknown): number => {
  const n = typeof x === 'string' ? parseFloat(x) : typeof x === 'number' ? x : NaN;
  return Number.isFinite(n) ? n : NaN;
};
const clamp = (n: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, n));

function Frame(props: { eyebrow: string; title: string; tag: string; children: ReactNode }): ReactNode {
  return (
    <>
      <div className="viz-head">
        <span className="viz-eyebrow">{props.eyebrow}</span>
        <span className="viz-title">{props.title}</span>
        <span className="viz-tag">{props.tag}</span>
      </div>
      {props.children}
    </>
  );
}

const Empty = ({ msg }: { msg: string }): ReactNode => <div className="viz-empty">{msg}</div>;

// ── A. 恐懼貪婪半圓儀表（get_crypto_fear_and_greed_index）─────
// 後端 dict：{ latest_value:int 0-100, latest_sentiment:str（可能為 ''）, history:[...] }。
// 只需 latest；sentiment 空字串要 fallback 到區間名。
export type FngData = { v: number; label: string; zone: number };

const FNG_BANDS = [
  { to: 25, color: '#ff4f78', name: '極度恐懼' },
  { to: 45, color: '#ff9f45', name: '恐懼' },
  { to: 55, color: '#ffc23d', name: '中性' },
  { to: 75, color: '#9ad84e', name: '貪婪' },
  { to: 100, color: '#4ee88a', name: '極度貪婪' },
];
const FNG_RANGES = FNG_BANDS.map((b, i) => ({
  color: b.color,
  from: i === 0 ? 0 : FNG_BANDS[i - 1]!.to,
  to: b.to,
}));
const fngZone = (v: number): number => {
  for (let i = 0; i < FNG_BANDS.length; i++) if (v < FNG_BANDS[i]!.to) return i;
  return FNG_BANDS.length - 1;
};

export function normFng(result: unknown): FngData | null {
  if (!isObj(result) || hasError(result)) return null;
  const raw = toNum(result.latest_value);
  const v = clamp(Number.isFinite(raw) ? Math.round(raw) : 50, 0, 100);
  const zone = fngZone(v);
  const s = typeof result.latest_sentiment === 'string' ? result.latest_sentiment.trim() : '';
  return { v, label: s || FNG_BANDS[zone]!.name, zone };
}

const DEG = Math.PI / 180;
// v=0→左(180°)、v=100→右(0°)；y 向上取負 sin，畫上半圓
const polar = (cx: number, cy: number, r: number, ang: number): [number, number] => [
  cx + r * Math.cos(ang * DEG),
  cy - r * Math.sin(ang * DEG),
];
const fngAng = (v: number): number => 180 - v * 1.8;
// 用取樣點連成 polyline 畫弧，避開 SVG arc sweep-flag 的方向歧義（保證畫上半圓）
function fngArcPts(cx: number, cy: number, r: number, v1: number, v2: number): string {
  const steps = Math.max(2, Math.round((v2 - v1) / 2));
  const pts: string[] = [];
  for (let i = 0; i <= steps; i++) {
    const v = v1 + ((v2 - v1) * i) / steps;
    const [x, y] = polar(cx, cy, r, fngAng(v));
    pts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  }
  return pts.join(' ');
}

function FngGauge({ d }: { d: FngData }): ReactNode {
  const cx = 120;
  const cy = 118;
  const R = 90;
  const TH = 15;
  const zone = FNG_BANDS[d.zone]!;
  const [nx, ny] = polar(cx, cy, R - TH, fngAng(d.v));
  return (
    <div className="viz-gauge">
      <svg viewBox="0 0 240 140" className="viz-gauge-svg" role="img" aria-label={`恐懼貪婪指數 ${d.v}`}>
        {FNG_RANGES.map((b) => (
          <polyline
            key={b.to}
            points={fngArcPts(cx, cy, R, b.from, b.to)}
            stroke={b.color}
            strokeWidth={TH}
            fill="none"
            opacity={0.9}
          />
        ))}
        <line x1={cx} y1={cy} x2={Number(nx.toFixed(2))} y2={Number(ny.toFixed(2))} stroke="#f2f6ff" strokeWidth={3} />
        <circle cx={cx} cy={cy} r={6} fill="#2c3648" stroke="#0a0c12" strokeWidth={1.5} />
        <text x={cx} y={cy - 18} textAnchor="middle" className="viz-gauge-num" fill={zone.color}>
          {d.v}
        </text>
      </svg>
      <div className="viz-gauge-label" style={{ color: zone.color }}>
        {d.label}
      </div>
      <div className="viz-legend">
        {FNG_BANDS.map((b, i) => (
          <span key={b.to} className="viz-legend-item" data-on={i === d.zone ? '1' : '0'}>
            <span className="viz-swatch" style={{ background: b.color }} />
            {b.name}
          </span>
        ))}
      </div>
    </div>
  );
}

// ── B. 訂單簿深度條（get_max_depth）──────────────────────────
// 後端 dict：{ market:str, bids:[[price:str, volume:str]], asks:[...] }。
// ★陷阱：bids/asks 是「字串」二元組，務必 parseFloat。bids 高→低、asks 低→高。
type DepthRow = [number, number];
export type DepthData = {
  market: string;
  bids: DepthRow[];
  asks: DepthRow[];
  maxV: number;
  spread: number;
  spreadPct: number;
};

export function normDepth(result: unknown): DepthData | null {
  if (!isObj(result) || hasError(result)) return null;
  const parse = (arr: unknown): DepthRow[] =>
    Array.isArray(arr)
      ? arr
          .map((e): DepthRow => (Array.isArray(e) ? [toNum(e[0]), toNum(e[1])] : [NaN, NaN]))
          .filter(([p, v]) => Number.isFinite(p) && Number.isFinite(v) && p > 0)
      : [];
  const bids = parse(result.bids).slice(0, 7);
  const asks = parse(result.asks).slice(0, 7);
  if (bids.length === 0 && asks.length === 0) return null;
  const maxV = Math.max(1e-9, ...bids.map((x) => x[1]), ...asks.map((x) => x[1]));
  const bestBid = bids[0]?.[0] ?? NaN;
  const bestAsk = asks[0]?.[0] ?? NaN;
  const spread = bestAsk - bestBid;
  const spreadPct = bestBid > 0 ? (spread / bestBid) * 100 : NaN;
  const market = typeof result.market === 'string' ? result.market.toUpperCase() : '—';
  return { market, bids, asks, maxV, spread, spreadPct };
}

const fmtPrice = (n: number): string => n.toLocaleString('en-US', { maximumFractionDigits: 2 });

function ObRow({ r, maxV, side }: { r: DepthRow; maxV: number; side: 'ask' | 'bid' }): ReactNode {
  return (
    <div className={`viz-ob-row ${side}`}>
      <span className="viz-ob-bar" style={{ width: `${((r[1] / maxV) * 100).toFixed(1)}%` }} />
      <span className="viz-ob-price">{fmtPrice(r[0])}</span>
      <span className="viz-ob-vol">{r[1].toFixed(4)}</span>
    </div>
  );
}

function Orderbook({ d }: { d: DepthData }): ReactNode {
  return (
    <div className="viz-ob">
      {[...d.asks].reverse().map((r, i) => (
        <ObRow key={`a${i}`} r={r} maxV={d.maxV} side="ask" />
      ))}
      <div className="viz-ob-spread">
        <span>價差</span>
        <span>
          {Number.isFinite(d.spread) ? fmtPrice(d.spread) : '—'}
          {Number.isFinite(d.spreadPct) ? ` · ${d.spreadPct.toFixed(3)}%` : ''}
        </span>
      </div>
      {d.bids.map((r, i) => (
        <ObRow key={`b${i}`} r={r} maxV={d.maxV} side="bid" />
      ))}
    </div>
  );
}

// ── 分派 ────────────────────────────────────────────────────
/** tool_result 的 name → 一張圖表卡（未實作的工具回 null，由 AgentDock 略過不渲染）。 */
export function chartSpecFor(tool: string, result: unknown): ReactNode {
  switch (tool) {
    case 'get_max_depth': {
      const d = normDepth(result);
      return (
        <Frame eyebrow="流動性" title={`訂單簿 · ${d?.market ?? ''}`} tag="MAX">
          {d ? <Orderbook d={d} /> : <Empty msg="這一輪沒有可畫的訂單簿資料" />}
        </Frame>
      );
    }
    case 'get_crypto_fear_and_greed_index': {
      const d = normFng(result);
      return (
        <Frame eyebrow="市場情緒" title="恐懼與貪婪指數" tag="alternative.me">
          {d ? <FngGauge d={d} /> : <Empty msg="這一輪沒有可畫的情緒資料" />}
        </Frame>
      );
    }
    default:
      return null; // 其餘 CHARTABLE 工具（帳戶/DNA/行為）待下一批實作
  }
}

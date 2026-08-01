import type { ReactNode } from 'react';
import type { ChartItem } from './chatStore';

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

// ── 共用（C/D/E）小工具 ─────────────────────────────────────
const nOrDash = (x: unknown, suffix = '', digits = 1): string => {
  const n = toNum(x);
  return Number.isFinite(n) ? `${n.toFixed(digits)}${suffix}` : '—';
};
const money = (x: unknown): string => {
  const n = toNum(x);
  return Number.isFinite(n) ? `NT$${Math.round(n).toLocaleString('en-US')}` : '—';
};
const signTone = (x: unknown): 'up' | 'down' | undefined => {
  const n = toNum(x);
  if (!Number.isFinite(n) || n === 0) return undefined;
  return n > 0 ? 'up' : 'down';
};
const subObj = (m: Record<string, unknown>, k: string): Record<string, unknown> =>
  isObj(m[k]) ? (m[k] as Record<string, unknown>) : {};

function Tile({ label, value, tone }: { label: string; value: string; tone?: 'up' | 'down' | 'warn' }): ReactNode {
  return (
    <div className="viz-tile" data-tone={tone ?? ''}>
      <span className="viz-tile-v">{value}</span>
      <span className="viz-tile-l">{label}</span>
    </div>
  );
}

// ── C. 資產配置堆疊條（get_max_accounts）─────────────────────
// ★後端回「陣列」不是 dict：Array<{currency,total,...}>；空是 []（沒有 {error}）。
// ★單位陷阱：total 是各幣別原生單位數量，跨幣別加總無共同計價 → 標「未換算」，不宣稱佔比。
type AcctSeg = { currency: string; total: number; share: number };
export type AcctData = { segs: AcctSeg[] };
const ACCT_COLORS = ['#ffc23d', '#b06cff', '#00e5ff', '#4ee88a', '#6f8fff', '#ff4f78', '#7d8ba5'];
const acctColor = (i: number): string => ACCT_COLORS[i % ACCT_COLORS.length]!;

export function normAccounts(result: unknown): AcctData | null {
  if (!Array.isArray(result)) return null;
  const rows = result
    .filter((a): a is Record<string, unknown> => isObj(a))
    .map((a) => ({ currency: typeof a.currency === 'string' ? a.currency : '?', total: toNum(a.total) }))
    .filter((a) => Number.isFinite(a.total) && a.total > 0)
    .sort((x, y) => y.total - x.total);
  if (rows.length === 0) return null;
  const top = rows.slice(0, 6);
  const restSum = rows.slice(6).reduce((s, r) => s + r.total, 0);
  if (restSum > 0) top.push({ currency: '其他', total: restSum });
  const sum = top.reduce((s, r) => s + r.total, 0);
  if (sum <= 0) return null;
  return { segs: top.map((r) => ({ currency: r.currency, total: r.total, share: r.total / sum })) };
}

const fmtAmt = (n: number): string => n.toLocaleString('en-US', { maximumFractionDigits: 6 });

function Accounts({ d }: { d: AcctData }): ReactNode {
  return (
    <div className="viz-acct">
      <div className="viz-acct-note">各幣別持有量 · 未換算為單一計價</div>
      <div className="viz-acct-bar">
        {d.segs.map((s, i) => (
          <span
            key={s.currency}
            className="viz-acct-seg"
            style={{ width: `${(s.share * 100).toFixed(1)}%`, background: acctColor(i) }}
            title={`${s.currency} ${(s.share * 100).toFixed(1)}%`}
          />
        ))}
      </div>
      <div className="viz-acct-legend">
        {d.segs.map((s, i) => (
          <div className="viz-acct-row" key={s.currency}>
            <span className="viz-swatch" style={{ background: acctColor(i) }} />
            <span className="viz-acct-cur">{s.currency}</span>
            <span className="viz-acct-amt">{fmtAmt(s.total)}</span>
            <span className="viz-acct-share">{(s.share * 100).toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── D. 交易 DNA 六軸雷達（get_trading_dna_score）─────────────
// dict：{axes:[6 中文], scores:{軸名:float 0-100}, archetype:str|null, insufficient_data, tags}。
// ★scores 以「軸名」為 key，要照 axes 順序索引；insufficient 時不可宣稱 archetype。
const DNA_AXES = ['活躍度', '紀律', '擇時', '分散', '持有耐心', '風險控管'];
export type DnaData = {
  axes: string[];
  vals: number[];
  archetype: string | null;
  tags: string[];
  insufficient: boolean;
};

export function normDna(result: unknown): DnaData | null {
  if (!isObj(result) || hasError(result)) return null;
  const axes =
    Array.isArray(result.axes) && result.axes.length > 0 ? result.axes.map((a) => String(a)) : DNA_AXES;
  const scores = isObj(result.scores) ? result.scores : {};
  const vals = axes.map((name) => clamp(toNum(scores[name]) || 0, 0, 100));
  return {
    axes,
    vals,
    archetype: typeof result.archetype === 'string' ? result.archetype : null,
    tags: Array.isArray(result.tags) ? result.tags.map((t) => String(t)) : [],
    insufficient: !!result.insufficient_data,
  };
}

function DnaRadar({ d }: { d: DnaData }): ReactNode {
  const cx = 110;
  const cy = 100;
  const maxR = 76;
  const n = d.axes.length;
  const pt = (i: number, r: number): [number, number] => {
    const th = (-90 + (360 / n) * i) * DEG;
    return [cx + r * Math.cos(th), cy + r * Math.sin(th)];
  };
  const ring = (r: number): string =>
    d.axes.map((_, i) => pt(i, r).map((v) => v.toFixed(1)).join(',')).join(' ');
  const dataPts = d.axes.map((_, i) => pt(i, (maxR * (d.vals[i] ?? 0)) / 100));
  return (
    <div className="viz-radar">
      <div className="viz-radar-head">
        {d.insufficient ? (
          <span className="viz-warn">樣本不足（交易 &lt; 20 筆），尚無法判定交易性格</span>
        ) : (
          <>
            {d.archetype && <span className="viz-arche">{d.archetype}</span>}
            {d.tags.slice(0, 4).map((t) => (
              <span key={t} className="viz-tagchip">
                {t}
              </span>
            ))}
          </>
        )}
      </div>
      <svg viewBox="0 0 220 200" className="viz-radar-svg" role="img" aria-label="交易 DNA 六軸雷達">
        {[25, 50, 75, 100].map((p) => (
          <polygon key={p} points={ring((maxR * p) / 100)} fill="none" stroke="#3d4a61" strokeWidth={1} />
        ))}
        {d.axes.map((_, i) => {
          const [x, y] = pt(i, maxR);
          return <line key={i} x1={cx} y1={cy} x2={x.toFixed(1)} y2={y.toFixed(1)} stroke="#3d4a61" strokeWidth={1} />;
        })}
        <polygon
          points={dataPts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')}
          fill="#b06cff"
          fillOpacity={d.insufficient ? 0.12 : 0.28}
          stroke="#b06cff"
          strokeWidth={2}
        />
        {dataPts.map(([x, y], i) => (
          <rect key={i} x={x - 1.5} y={y - 1.5} width={3} height={3} fill="#b06cff" />
        ))}
        {d.axes.map((name, i) => {
          const [x, y] = pt(i, maxR + 13);
          const anchor = x < cx - 5 ? 'end' : x > cx + 5 ? 'start' : 'middle';
          return (
            <text
              key={name}
              x={x.toFixed(1)}
              y={y.toFixed(1)}
              textAnchor={anchor}
              dominantBaseline="middle"
              className="viz-radar-axis"
            >
              {name}
            </text>
          );
        })}
      </svg>
    </div>
  );
}

// ── E. 交易行為四維卡（analyze_trading_behavior）──────────────
// dict：{metrics:[固定4序], findings:[], sample:{closes_analyzed,closes_total}, data_confidence}。
// 各 metric 多個 float|null 欄位，務必防 null；examples.ts 是毫秒。
type BMetric = Record<string, unknown>;
export type BehaviorData = {
  metrics: BMetric[];
  findings: number;
  analyzed: number;
  totalCloses: number;
  confidence: string | null;
};

export function normBehavior(result: unknown): BehaviorData | null {
  if (!isObj(result) || hasError(result)) return null;
  const metrics = Array.isArray(result.metrics) ? result.metrics.filter((m): m is BMetric => isObj(m)) : [];
  if (metrics.length === 0) return null;
  const sample = isObj(result.sample) ? result.sample : {};
  return {
    metrics,
    findings: Array.isArray(result.findings) ? result.findings.length : 0,
    analyzed: toNum(sample.closes_analyzed) || 0,
    totalCloses: toNum(sample.closes_total) || 0,
    confidence: typeof result.data_confidence === 'string' ? result.data_confidence : null,
  };
}

function metricBody(m: BMetric, idx: number): ReactNode {
  if (idx === 0) {
    const w = subObj(m, 'winners');
    const l = subObj(m, 'losers');
    return (
      <div className="viz-tiles">
        <Tile label="賺錢單持有" value={nOrDash(w.median_hold_days, 'd')} />
        <Tile label="虧損單持有" value={nOrDash(l.median_hold_days, 'd')} />
        <Tile
          label="虧/賺持有比"
          value={nOrDash(m.ratio_loser_over_winner, '×')}
          tone={toNum(m.ratio_loser_over_winner) > 1 ? 'down' : undefined}
        />
      </div>
    );
  }
  if (idx === 1) {
    const b = subObj(m, 'buys');
    const s = subObj(m, 'sells');
    const bt = signTone(b.median_prior_change_pct); // 買在漲後=追高，反過來上色
    return (
      <div className="viz-tiles">
        <Tile
          label="買在前7日"
          value={nOrDash(b.median_prior_change_pct, '%')}
          tone={bt === 'up' ? 'down' : bt === 'down' ? 'up' : undefined}
        />
        <Tile label="賣在前7日" value={nOrDash(s.median_prior_change_pct, '%')} tone={signTone(s.median_prior_change_pct)} />
      </div>
    );
  }
  if (idx === 2) {
    return (
      <div className="viz-tiles">
        <Tile label="總手續費" value={money(m.total_fees_twd)} tone="down" />
        <Tile label="每筆手續費" value={money(m.fee_per_close_twd)} />
        <Tile label="佔毛利" value={nOrDash(m.fees_as_pct_of_gross, '%')} tone="down" />
        <Tile label="淨實現" value={money(m.net_realized_twd)} tone={signTone(m.net_realized_twd)} />
      </div>
    );
  }
  // idx 3 攤平傾向 —— 兩段分佈條
  const below = toNum(m.below_share_pct);
  const belowN = toNum(m.adds_below_avg_cost) || 0;
  const aboveN = toNum(m.adds_above_avg_cost) || 0;
  return (
    <div className="viz-beh-avg">
      {Number.isFinite(below) && (
        <div className="viz-dist">
          <span className="viz-dist-seg below" style={{ width: `${below.toFixed(0)}%` }} />
          <span className="viz-dist-seg above" style={{ width: `${(100 - below).toFixed(0)}%` }} />
        </div>
      )}
      <div className="viz-beh-legend">
        <span className="up">均價下加碼 {belowN} 筆</span>
        <span className="down">均價上追高 {aboveN} 筆</span>
      </div>
    </div>
  );
}

function Behavior({ d }: { d: BehaviorData }): ReactNode {
  return (
    <div className="viz-beh">
      <div className="viz-beh-head">
        {d.confidence === 'partial' && <span className="viz-badge warn">部分資料</span>}
        <span className="viz-beh-sample">
          分析 {d.analyzed}/{d.totalCloses} 筆平倉 · {d.findings} 項發現
        </span>
      </div>
      {d.metrics.map((m, idx) => {
        const ok = m.sample_ok !== false;
        const title = typeof m.metric === 'string' ? m.metric : `維度 ${idx + 1}`;
        const conclusion = typeof m.conclusion === 'string' ? m.conclusion : '';
        return (
          <div className="viz-beh-row" key={idx} data-ok={ok ? '1' : '0'}>
            <div className="viz-beh-title">
              {title}
              {!ok && <span className="viz-beh-thin"> · 樣本不足</span>}
            </div>
            {ok && metricBody(m, idx)}
            {ok && conclusion && <div className="viz-beh-note">{conclusion}</div>}
          </div>
        );
      })}
    </div>
  );
}

// ── F. K 線蠟燭圖（get_max_klines）— 第二層，SVG rect 天生像素感 ──
// 後端回陣列：[[ts秒, open, high, low, close, volume], ...]（MAX 原始，皆可能是數字或字串）。
type Candle = { o: number; h: number; l: number; c: number };
export type KlineData = { candles: Candle[]; lo: number; hi: number; last: number; up: boolean };

export function normKline(result: unknown): KlineData | null {
  if (!Array.isArray(result) || result.length === 0) return null;
  const rows = result
    .filter((r): r is unknown[] => Array.isArray(r) && r.length >= 5)
    .map((r) => ({ o: toNum(r[1]), h: toNum(r[2]), l: toNum(r[3]), c: toNum(r[4]) }))
    .filter((k) => [k.o, k.h, k.l, k.c].every(Number.isFinite) && k.h > 0);
  if (rows.length === 0) return null;
  const candles = rows.slice(-48); // 最近 48 根，夠密又不糊
  let lo = Infinity;
  let hi = -Infinity;
  for (const k of candles) {
    lo = Math.min(lo, k.l);
    hi = Math.max(hi, k.h);
  }
  const last = candles[candles.length - 1]!;
  return { candles, lo, hi, last: last.c, up: last.c >= last.o };
}

const fmtP = (n: number): string => n.toLocaleString('en-US', { maximumFractionDigits: n >= 100 ? 0 : 2 });

function Candles({ d }: { d: KlineData }): ReactNode {
  const W = 220;
  const H = 120;
  const padT = 6;
  const padR = 48;
  const plotL = 2;
  const plotW = W - padR - plotL;
  const plotH = H - padT * 2;
  const range = Math.max(1e-9, d.hi - d.lo);
  const y = (p: number): number => padT + (1 - (p - d.lo) / range) * plotH;
  const cw = plotW / d.candles.length;
  const bw = Math.max(1, cw * 0.6);
  const lastCol = d.up ? '#4ee88a' : '#ff4f78';
  return (
    <div className="viz-kline">
      <svg viewBox={`0 0 ${W} ${H}`} className="viz-kline-svg" role="img" aria-label="K 線">
        {d.candles.map((k, i) => {
          const cx = plotL + cw * (i + 0.5);
          const col = k.c >= k.o ? '#4ee88a' : '#ff4f78';
          const top = Math.min(y(k.o), y(k.c));
          const hgt = Math.max(1, Math.abs(y(k.c) - y(k.o)));
          return (
            <g key={i}>
              <line x1={cx.toFixed(1)} y1={y(k.h).toFixed(1)} x2={cx.toFixed(1)} y2={y(k.l).toFixed(1)} stroke={col} strokeWidth={1} />
              <rect x={(cx - bw / 2).toFixed(1)} y={top.toFixed(1)} width={bw.toFixed(1)} height={hgt.toFixed(1)} fill={col} />
            </g>
          );
        })}
        <line
          x1={plotL}
          y1={y(d.last).toFixed(1)}
          x2={W - padR}
          y2={y(d.last).toFixed(1)}
          stroke={lastCol}
          strokeWidth={0.5}
          strokeDasharray="2 2"
        />
        <text x={W - padR + 3} y={(y(d.hi) + 6).toFixed(1)} className="viz-kline-axis">{fmtP(d.hi)}</text>
        <text x={W - padR + 3} y={(y(d.lo) - 1).toFixed(1)} className="viz-kline-axis">{fmtP(d.lo)}</text>
        <text x={W - padR + 3} y={(y(d.last) + 3).toFixed(1)} className="viz-kline-last" fill={lastCol}>{fmtP(d.last)}</text>
      </svg>
    </div>
  );
}

// ── G. 淨值折線（get_equity_curve）— 第二層 ─────────────────
// dict：{ curve:[{value_twd, ...}], start/end/peak_value_twd, ... }。每點取 value_twd。
export type EquityData = { values: number[]; end: number; up: boolean };

export function normEquity(result: unknown): EquityData | null {
  if (!isObj(result) || hasError(result)) return null;
  const curve = Array.isArray(result.curve) ? result.curve : [];
  const values = curve.map((p) => (isObj(p) ? toNum(p.value_twd) : NaN)).filter((n) => Number.isFinite(n));
  if (values.length < 2) return null;
  return { values, end: values[values.length - 1]!, up: values[values.length - 1]! >= values[0]! };
}

const fmtEq = (n: number): string => {
  const a = Math.abs(n);
  if (a >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
  return n.toFixed(0);
};

function EquityLine({ d }: { d: EquityData }): ReactNode {
  const W = 220;
  const H = 100;
  const padT = 8;
  const padR = 50;
  const plotL = 2;
  const plotW = W - padR - plotL;
  const plotH = H - padT * 2;
  const lo = Math.min(...d.values);
  const hi = Math.max(...d.values);
  const range = Math.max(1e-9, hi - lo);
  const n = d.values.length;
  const x = (i: number): number => plotL + (n === 1 ? 0 : (i / (n - 1)) * plotW);
  const y = (v: number): number => padT + (1 - (v - lo) / range) * plotH;
  const col = d.up ? '#4ee88a' : '#ff4f78';
  const pts = d.values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const base = (padT + plotH).toFixed(1);
  const area = `${x(0).toFixed(1)},${base} ${pts} ${x(n - 1).toFixed(1)},${base}`;
  return (
    <div className="viz-eq">
      <svg viewBox={`0 0 ${W} ${H}`} className="viz-kline-svg" role="img" aria-label="淨值曲線">
        <polygon points={area} fill={col} fillOpacity={0.14} />
        <polyline points={pts} fill="none" stroke={col} strokeWidth={1.5} />
        <text x={W - padR + 3} y={(y(hi) + 6).toFixed(1)} className="viz-kline-axis">{fmtEq(hi)}</text>
        <text x={W - padR + 3} y={(y(lo) - 1).toFixed(1)} className="viz-kline-axis">{fmtEq(lo)}</text>
        <text x={W - padR + 3} y={(y(d.end) + 3).toFixed(1)} className="viz-kline-last" fill={col}>{fmtEq(d.end)}</text>
      </svg>
    </div>
  );
}

// ── 分派 ────────────────────────────────────────────────────
/** 從 tool_call 的 args.market 或 result.market 取標的（大寫），給多圖區分用。 */
const marketLabel = (result: unknown, args?: Record<string, unknown>): string => {
  const raw =
    args && typeof args.market === 'string'
      ? args.market
      : isObj(result) && typeof result.market === 'string'
        ? result.market
        : '';
  return raw ? raw.toUpperCase() : '';
};

/** tool_result 的 name → 一張圖表卡（未實作的工具回 null，由 AgentDock 略過不渲染）。args 帶當初 tool_call 的參數（標的）。 */
export function chartSpecFor(tool: string, result: unknown, args?: Record<string, unknown>): ReactNode {
  const mkt = marketLabel(result, args);
  switch (tool) {
    case 'get_max_depth': {
      const d = normDepth(result);
      return (
        <Frame eyebrow="流動性" title={`訂單簿${mkt ? ` · ${mkt}` : d?.market ? ` · ${d.market}` : ''}`} tag="MAX">
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
    case 'get_max_accounts': {
      const d = normAccounts(result);
      return (
        <Frame eyebrow="帳戶" title="資產配置" tag="MAX">
          {d ? <Accounts d={d} /> : <Empty msg="帳戶沒有可顯示的餘額" />}
        </Frame>
      );
    }
    case 'get_trading_dna_score': {
      const d = normDna(result);
      return (
        <Frame eyebrow="你的交易 DNA" title={d && d.archetype && !d.insufficient ? d.archetype : '交易性格側寫'} tag="帳本">
          {d ? <DnaRadar d={d} /> : <Empty msg="這一輪沒有可畫的 DNA 資料" />}
        </Frame>
      );
    }
    case 'analyze_trading_behavior': {
      const d = normBehavior(result);
      return (
        <Frame eyebrow="你的交易行為" title="行為偏誤體檢" tag="帳本">
          {d ? <Behavior d={d} /> : <Empty msg="這一輪沒有可畫的行為資料" />}
        </Frame>
      );
    }
    case 'get_max_klines': {
      const d = normKline(result);
      return (
        <Frame eyebrow="行情" title={`K 線${mkt ? ` · ${mkt}` : ''}`} tag="MAX">
          {d ? <Candles d={d} /> : <Empty msg="這一輪沒有可畫的 K 線資料" />}
        </Frame>
      );
    }
    case 'get_equity_curve': {
      const d = normEquity(result);
      return (
        <Frame eyebrow="你的淨值" title="資產淨值曲線" tag="帳本">
          {d ? <EquityLine d={d} /> : <Empty msg="這一輪沒有可畫的淨值資料" />}
        </Frame>
      );
    }
    default:
      return null;
  }
}

// ── 答案內嵌圖表：[圖表] / [圖表:工具名] 錨點規劃（純函式，好測）─────
/** answer 裡的 [圖表] / [圖表:工具名] 錨點。後端 prompt 已教 LLM 產出（agent/prompts.py）。 */
export const CHART_ANCHOR = /\[圖表(?::([a-zA-Z_]+))?\]/g;

export type BodyPart = { kind: 'text'; text: string } | { kind: 'chart'; item: ChartItem };

/**
 * 把一則答案文字 + 本輪圖表卡，規劃成「文字 / 圖表」交錯的順序清單。
 * [圖表] 消化下一張未用的圖；[圖表:工具名] 指名該工具的圖；沒被錨點消化的圖表附在最後
 * （同舊 UI：無錨點時圖排在文字之後）。純資料轉換、不碰 React，方便單元測試。
 */
export function planAgentBody(text: string, charts: ChartItem[]): BodyPart[] {
  const used = new Set<number>();
  const pick = (tool: string | null): ChartItem | null => {
    const idx = charts.findIndex((c, i) => !used.has(i) && (tool === null || c.tool === tool));
    if (idx < 0) return null;
    used.add(idx);
    return charts[idx] ?? null;
  };
  const parts: BodyPart[] = [];
  let last = 0;
  for (const m of text.matchAll(CHART_ANCHOR)) {
    const at = m.index ?? 0;
    const seg = text.slice(last, at);
    if (seg.trim()) parts.push({ kind: 'text', text: seg });
    const c = pick(m[1] ?? null);
    if (c) parts.push({ kind: 'chart', item: c });
    last = at + (m[0] ?? '').length;
  }
  const tail = text.slice(last);
  if (tail.trim()) parts.push({ kind: 'text', text: tail });
  charts.forEach((c, i) => {
    if (!used.has(i)) parts.push({ kind: 'chart', item: c });
  });
  return parts;
}

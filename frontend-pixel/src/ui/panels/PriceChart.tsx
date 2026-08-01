import { useCallback, useEffect, useRef, useState } from 'react';
import { getKlines, TIMEFRAMES, type Timeframe } from '../../api/trade';
import { useAsync } from '../useAsync';
import { AsyncState } from '../Panel';

/**
 * 互動式價格圖。**沒有圖表函式庫** —— 專案的相依只有 react/react-dom，
 * 所以蠟燭、成交量、座標軸、十字準星全部自己在 canvas 上畫。
 *
 * 做得到的：滾輪縮放（以游標為錨）、拖曳平移、十字準星 + OHLCV 浮動資訊、
 * 六段時間週期、隨面板寬度自適應。
 * 做不到的：畫線工具、技術指標、儲存版面 —— 那是另一個量級的產品。
 *
 * ⚠ 為什麼是 canvas 而不是 SVG：`vizCards.tsx` 的迷你 K 線用 SVG rect（48 根、
 *   靜態、像素感好），但這裡要畫到 300 根並且每次移動滑鼠都重繪十字準星。
 *   300 個 DOM 節點 × 每次 mousemove 重排，會讓面板明顯卡頓；canvas 是一次
 *   drawImage 等級的成本。
 *
 * ⚠ 世界在面板開啟時是凍結的（`frozen` 含 panel open），所以這張圖不會跟
 *   60fps 的世界搶 CPU。規格 §744 排除「HUD 迷你 K 線」講的是 HUD 每幀重繪，
 *   與這裡無關。
 */

const C = {
  up: '#4ee88a',
  down: '#ff4f78',
  dim: '#7d8ba5',
  txt: '#c3cede',
  line: '#253044',
  grid: '#1a2233',
  bg: '#0e131e',
  cross: '#6f8fff',
} as const;

/** 右側價格軸寬度、底部時間軸高度、成交量區塊佔比。 */
const PAD = { right: 62, bottom: 22, top: 8, left: 6 };
const VOL_RATIO = 0.22;

const MIN_BARS = 20;
const MAX_BARS = 400;

type View = { end: number; bars: number };

function fmtPrice(n: number): string {
  if (!Number.isFinite(n)) return '—';
  if (n >= 1000) return Math.round(n).toLocaleString('en-US');
  if (n >= 1) return n.toFixed(2);
  return n.toFixed(6);
}

/**
 * 成交量。大額走 K/M/B 縮寫 —— 浮動資訊框只有 116px 寬，
 * 一個 `6194080.2400` 會直接壓到左邊的欄位標籤上（實測踩過）。
 */
function fmtVol(n: number): string {
  if (!Number.isFinite(n)) return '—';
  const a = Math.abs(n);
  if (a >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `${(n / 1e3).toFixed(2)}K`;
  if (a >= 1) return n.toFixed(3);
  return n.toFixed(6);
}

function fmtTime(ms: number, tf: Timeframe): string {
  const d = new Date(ms);
  const p = (x: number) => String(x).padStart(2, '0');
  // 日線以上不需要時分，分鐘線不需要年份 —— 軸上的字越少越好讀
  if (tf === '1d') return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
  return `${p(d.getMonth() + 1)}/${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** 挑一個「好看的」刻度間距（1/2/5 × 10^n），避免出現 0.037 這種軸標。 */
function niceStep(range: number, target: number): number {
  const raw = range / Math.max(1, target);
  const mag = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / mag;
  const step = norm >= 5 ? 5 : norm >= 2 ? 2 : 1;
  return step * mag;
}

export function PriceChart({ market, base }: { market: string; base: string }) {
  const [tf, setTf] = useState<Timeframe>('1h');
  const [view, setView] = useState<View | null>(null);
  const [hover, setHover] = useState<{ x: number; y: number } | null>(null);

  const wrapRef = useRef<HTMLDivElement>(null);
  const cvsRef = useRef<HTMLCanvasElement>(null);
  const dragRef = useRef<{ x: number; end: number } | null>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });

  // 30 秒重抓一次。最短週期是 1 分鐘，比它更頻繁只是白打後端（後端另有 15 秒快取）
  const kl = useAsync((s) => getKlines(market, tf, 300, s), [market, tf], { intervalMs: 30_000 });
  const candles = kl.data ?? [];

  // 換交易對或週期時把視窗拉回最右（最新）—— 停在舊位置會看到一片空白
  useEffect(() => setView(null), [market, tf]);

  /**
   * ⚠ 容器**必須全程掛載**，否則這個 observer 接不上。
   *
   * 第一版把 loading 狀態畫成 `{loading ? <AsyncState/> : <div ref=wrapRef>}`，
   * 於是這個 effect 在首次執行時 `wrapRef.current` 是 null（畫面上是轉圈圈），
   * observer 從來沒有 observe 過任何東西 → `size` 永遠停在 0 → 繪製一律早退
   * → **canvas 全白，而且不會有任何錯誤**。
   * 現在容器一直在，載入/錯誤狀態疊在它上面。
   */
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => {
      if (e) setSize({ w: e.contentRect.width, h: e.contentRect.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const v: View = view ?? { end: candles.length, bars: Math.min(120, candles.length || 120) };

  /** 把視窗夾回合法範圍。縮放與平移都經過這裡，邊界只寫一次。 */
  const clampView = useCallback(
    (next: View): View => {
      const bars = Math.max(MIN_BARS, Math.min(MAX_BARS, Math.min(next.bars, candles.length || MAX_BARS)));
      const end = Math.max(bars, Math.min(candles.length, Math.round(next.end)));
      return { end, bars };
    },
    [candles.length],
  );

  // ── 繪製 ──────────────────────────────────────────────────
  useEffect(() => {
    const cvs = cvsRef.current;
    if (!cvs || !size.w || !size.h || candles.length === 0) return;

    const dpr = Math.min(2, window.devicePixelRatio || 1);
    cvs.width = Math.round(size.w * dpr);
    cvs.height = Math.round(size.h * dpr);
    const ctx = cvs.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size.w, size.h);

    const slice = candles.slice(Math.max(0, v.end - v.bars), v.end);
    if (!slice.length) return;

    const plotW = size.w - PAD.right - PAD.left;
    const plotH = size.h - PAD.bottom - PAD.top;
    const volH = plotH * VOL_RATIO;
    const priceH = plotH - volH - 6;

    let lo = Infinity;
    let hi = -Infinity;
    let vmax = 0;
    for (const k of slice) {
      if (k.l < lo) lo = k.l;
      if (k.h > hi) hi = k.h;
      if (k.v > vmax) vmax = k.v;
    }
    // 上下各留 4% 呼吸空間，否則最高/最低的影線會貼齊邊框看起來像被切掉
    const padY = (hi - lo) * 0.04 || hi * 0.001 || 1;
    lo -= padY;
    hi += padY;

    const bw = plotW / slice.length;
    const xOf = (i: number) => PAD.left + i * bw + bw / 2;
    const yOf = (p: number) => PAD.top + ((hi - p) / (hi - lo)) * priceH;

    // ── 格線 + 價格軸 ──
    ctx.font = '10px ui-monospace, monospace';
    ctx.textBaseline = 'middle';
    const step = niceStep(hi - lo, Math.max(2, Math.floor(priceH / 44)));
    ctx.strokeStyle = C.grid;
    ctx.fillStyle = C.dim;
    ctx.lineWidth = 1;
    for (let p = Math.ceil(lo / step) * step; p <= hi; p += step) {
      const y = Math.round(yOf(p)) + 0.5;
      ctx.beginPath();
      ctx.moveTo(PAD.left, y);
      ctx.lineTo(PAD.left + plotW, y);
      ctx.stroke();
      ctx.fillText(fmtPrice(p), PAD.left + plotW + 6, y);
    }

    // ── 時間軸 ──
    ctx.textBaseline = 'top';
    const tickEvery = Math.max(1, Math.round(slice.length / Math.max(2, Math.floor(plotW / 90))));
    for (let i = 0; i < slice.length; i += tickEvery) {
      const k = slice[i];
      if (!k) continue;
      const x = xOf(i);
      ctx.strokeStyle = C.grid;
      ctx.beginPath();
      ctx.moveTo(Math.round(x) + 0.5, PAD.top);
      ctx.lineTo(Math.round(x) + 0.5, PAD.top + plotH);
      ctx.stroke();
      ctx.fillStyle = C.dim;
      // 置中的標籤在最左/最右會被畫布邊界切掉（第一根蠟燭的中心只離左緣半根）。
      // 夾回範圍內，寧可讓它稍微偏離刻度線也不要看到半個日期。
      const half = ctx.measureText(fmtTime(k.t, tf)).width / 2;
      ctx.textAlign = 'center';
      ctx.fillText(
        fmtTime(k.t, tf),
        Math.max(PAD.left + half, Math.min(PAD.left + plotW - half, x)),
        size.h - PAD.bottom + 5,
      );
    }
    ctx.textAlign = 'left';

    // ── 成交量 ──
    const volTop = PAD.top + priceH + 6;
    for (let i = 0; i < slice.length; i++) {
      const k = slice[i]!;
      const h = vmax > 0 ? (k.v / vmax) * volH : 0;
      ctx.fillStyle = k.c >= k.o ? '#4ee88a33' : '#ff4f7833';
      ctx.fillRect(xOf(i) - bw * 0.35, volTop + volH - h, Math.max(1, bw * 0.7), h);
    }

    // ── 蠟燭 ──
    const bodyW = Math.max(1, bw * 0.7);
    for (let i = 0; i < slice.length; i++) {
      const k = slice[i]!;
      const up = k.c >= k.o;
      const col = up ? C.up : C.down;
      const x = xOf(i);
      // 影線對齊半像素，1px 的線才不會糊成 2px 的灰帶
      ctx.strokeStyle = col;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(Math.round(x) + 0.5, yOf(k.h));
      ctx.lineTo(Math.round(x) + 0.5, yOf(k.l));
      ctx.stroke();
      const yO = yOf(k.o);
      const yC = yOf(k.c);
      ctx.fillStyle = col;
      // 平盤（開＝收）畫成 1px 的橫線，不要變成看不見的 0 高度矩形
      ctx.fillRect(x - bodyW / 2, Math.min(yO, yC), bodyW, Math.max(1, Math.abs(yC - yO)));
    }

    // ── 最新價橫線 ──
    const last = slice[slice.length - 1]!;
    const yLast = yOf(last.c);
    ctx.strokeStyle = last.c >= last.o ? C.up : C.down;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(PAD.left, Math.round(yLast) + 0.5);
    ctx.lineTo(PAD.left + plotW, Math.round(yLast) + 0.5);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = last.c >= last.o ? C.up : C.down;
    ctx.fillRect(PAD.left + plotW + 2, yLast - 8, PAD.right - 4, 16);
    ctx.fillStyle = '#05070c';
    ctx.textBaseline = 'middle';
    ctx.fillText(fmtPrice(last.c), PAD.left + plotW + 6, yLast);

    // ── 十字準星 ──
    if (hover && hover.x >= PAD.left && hover.x <= PAD.left + plotW) {
      const idx = Math.max(0, Math.min(slice.length - 1, Math.floor((hover.x - PAD.left) / bw)));
      const k = slice[idx]!;
      const x = xOf(idx);
      ctx.strokeStyle = C.cross;
      ctx.setLineDash([2, 3]);
      ctx.beginPath();
      ctx.moveTo(Math.round(x) + 0.5, PAD.top);
      ctx.lineTo(Math.round(x) + 0.5, PAD.top + plotH);
      ctx.moveTo(PAD.left, Math.round(hover.y) + 0.5);
      ctx.lineTo(PAD.left + plotW, Math.round(hover.y) + 0.5);
      ctx.stroke();
      ctx.setLineDash([]);

      // 游標所在價格（跟著 Y，不是跟著蠟燭）—— 這是量距離時最常用的東西
      const pAtY = hi - ((hover.y - PAD.top) / priceH) * (hi - lo);
      if (hover.y >= PAD.top && hover.y <= PAD.top + priceH) {
        ctx.fillStyle = C.cross;
        ctx.fillRect(PAD.left + plotW + 2, hover.y - 8, PAD.right - 4, 16);
        ctx.fillStyle = '#05070c';
        ctx.fillText(fmtPrice(pAtY), PAD.left + plotW + 6, hover.y);
      }

      // OHLCV 浮動框。靠近右緣時翻到游標左邊，不要被畫布切掉
      const rows = [
        ['開', fmtPrice(k.o)],
        ['高', fmtPrice(k.h)],
        ['低', fmtPrice(k.l)],
        ['收', fmtPrice(k.c)],
        ['量', fmtVol(k.v)],
      ];
      const boxW = 124;
      const boxH = 16 + rows.length * 13;
      const bx = x + 12 + boxW > PAD.left + plotW ? x - 12 - boxW : x + 12;
      const by = Math.min(Math.max(PAD.top, hover.y - boxH / 2), PAD.top + plotH - boxH);
      ctx.fillStyle = '#0b0f18f2';
      ctx.fillRect(bx, by, boxW, boxH);
      ctx.strokeStyle = C.line;
      ctx.strokeRect(bx + 0.5, by + 0.5, boxW - 1, boxH - 1);
      ctx.fillStyle = C.dim;
      ctx.textBaseline = 'top';
      ctx.fillText(fmtTime(k.t, tf), bx + 7, by + 5);
      rows.forEach(([label, val], i) => {
        const y = by + 18 + i * 13;
        ctx.fillStyle = C.dim;
        ctx.fillText(label!, bx + 7, y);
        ctx.fillStyle = label === '收' ? (k.c >= k.o ? C.up : C.down) : C.txt;
        ctx.textAlign = 'right';
        ctx.fillText(val!, bx + boxW - 7, y);
        ctx.textAlign = 'left';
      });
    }
  }, [candles, v.end, v.bars, size, hover, tf]);

  // ── 互動 ──────────────────────────────────────────────────

  /**
   * 滾輪縮放。**必須用原生監聽器 + `{ passive: false }`。**
   *
   * React 的 `onWheel` 走的是被動監聽（瀏覽器為了捲動效能的預設），在裡面
   * 呼叫 `preventDefault()` 會被忽略並在 console 印一則警告 —— 症狀是縮放
   * 生效、但整個面板同時跟著捲動。
   */
  useEffect(() => {
    const cvs = cvsRef.current;
    if (!cvs || !candles.length) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = cvs.getBoundingClientRect();
      const plotW = rect.width - PAD.right - PAD.left;
      // 以游標位置為錨縮放：滑鼠指著的那根蠟燭要留在原地，否則縮放時畫面會亂跑
      const frac = Math.max(0, Math.min(1, (e.clientX - rect.left - PAD.left) / plotW));
      const bars = Math.round(v.bars * (e.deltaY > 0 ? 1.18 : 1 / 1.18));
      const anchor = v.end - v.bars + v.bars * frac;
      setView(clampView({ bars, end: Math.round(anchor + bars * (1 - frac)) }));
    };
    cvs.addEventListener('wheel', onWheel, { passive: false });
    return () => cvs.removeEventListener('wheel', onWheel);
  }, [candles.length, v.end, v.bars, clampView]);

  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    dragRef.current = { x: e.clientX, end: v.end };
  };

  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setHover({ x: e.clientX - rect.left, y: e.clientY - rect.top });
    const d = dragRef.current;
    if (!d) return;
    const plotW = rect.width - PAD.right - PAD.left;
    const perBar = plotW / v.bars;
    setView(clampView({ bars: v.bars, end: d.end - (e.clientX - d.x) / perBar }));
  };

  const endDrag = () => {
    dragRef.current = null;
  };

  const atLatest = v.end >= candles.length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
      <div className="tabs" style={{ marginBottom: 6 }}>
        {TIMEFRAMES.map((t) => (
          <button key={t} aria-selected={tf === t} onClick={() => setTf(t)}>
            {t}
          </button>
        ))}
      </div>

      {/* 容器全程掛載（見上方 ResizeObserver 的註解），狀態疊在上面 */}
      <div ref={wrapRef} style={{ position: 'relative', flex: 1, minHeight: 180, background: C.bg }}>
        <canvas
          ref={cvsRef}
          style={{
            width: '100%',
            height: '100%',
            display: 'block',
            cursor: 'crosshair',
            touchAction: 'none',
          }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onPointerLeave={() => {
            endDrag();
            setHover(null);
          }}
        />
        {(kl.loading || kl.error) && (
          <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', background: '#0e131ecc' }}>
            <AsyncState loading={kl.loading} error={kl.error} onRetry={kl.reload} />
          </div>
        )}
        {!atLatest && candles.length > 0 && (
          // 平移離開最新價之後要有路可以回去，不然只能一直拖
          <button
            className="btn"
            style={{ position: 'absolute', right: PAD.right + 8, bottom: PAD.bottom + 8, fontSize: 10 }}
            onClick={() => setView(null)}
          >
            回到最新
          </button>
        )}
      </div>
      <p className="muted" style={{ fontSize: 10, marginTop: 4 }}>
        {base} · 滾輪縮放 · 拖曳平移 · 停留看 OHLCV
        {candles.length ? ` · 共 ${candles.length} 根` : ''}
      </p>
    </div>
  );
}

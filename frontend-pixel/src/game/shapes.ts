import { PALETTE as C } from '../art/palette';

/**
 * 道具的共通打光語彙。
 *
 * 大型道具若逐格手排像素圖，每張要 48 行以上、而且很難動畫化。
 * 改用一組固定的「斜角方塊 + 發光 + 掃描線」組合，所有道具的
 * 受光方向與邊緣處理自動一致，這正是像素風看起來成套的關鍵。
 */

export type BevelColors = { fill: string; light: string; dark: string; line: string };

/** 光源固定在左上：左上邊亮一階、右下邊暗一階、外圍一圈輪廓。 */
export function bevelBox(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  c: BevelColors,
): void {
  ctx.fillStyle = c.line;
  ctx.fillRect(x, y, w, h);
  ctx.fillStyle = c.fill;
  ctx.fillRect(x + 1, y + 1, w - 2, h - 2);
  ctx.fillStyle = c.light;
  ctx.fillRect(x + 1, y + 1, w - 2, 1);
  ctx.fillRect(x + 1, y + 1, 1, h - 2);
  ctx.fillStyle = c.dark;
  ctx.fillRect(x + 1, y + h - 2, w - 2, 1);
  ctx.fillRect(x + w - 2, y + 1, 1, h - 2);
}

export const METAL: BevelColors = { fill: C['3'], light: C['5'], dark: C['1'], line: C['0'] };
export const DARK_METAL: BevelColors = { fill: C['2'], light: C['4'], dark: C['0'], line: C['0'] };

/**
 * 塊狀光暈：三層等距外擴的方框，透明度遞減。
 * 用徑向漸層會產生連續的軟邊，在整數放大後看起來像沾到髒污，
 * 方塊層次反而符合像素風的顆粒感。
 */
export function glow(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  color: string,
  strength = 1,
): void {
  ctx.save();
  ctx.fillStyle = color;
  for (let i = 3; i >= 1; i--) {
    ctx.globalAlpha = 0.1 * strength * (4 - i);
    ctx.fillRect(x - i * 2, y - i * 2, w + i * 4, h + i * 4);
  }
  ctx.restore();
}

/**
 * 圓形光暈。
 *
 * glow() 疊的是方框，套在圓形物件外圍會露出一圈方形亮邊 —— 金幣雕像
 * 第一版就是這樣，遠看像幣後面貼了一張黃色方紙。圓的東西要圓的光暈。
 */
export function radialGlow(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  r: number,
  color: string,
  strength = 1,
): void {
  ctx.save();
  ctx.fillStyle = color;
  for (let i = 3; i >= 1; i--) {
    ctx.globalAlpha = 0.08 * strength * (4 - i);
    ctx.beginPath();
    ctx.ellipse(cx, cy, r + i * 3, r + i * 3, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

/** 螢幕掃描線。phase 隨時間推進就會有訊號流動感。 */
export function scanlines(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  phase: number,
): void {
  ctx.save();
  ctx.globalAlpha = 0.16;
  ctx.fillStyle = C['0'];
  for (let i = 0; i < h; i += 2) ctx.fillRect(x, y + i, w, 1);
  // 一道較亮的掃描帶緩慢往下掃
  ctx.globalAlpha = 0.12;
  ctx.fillStyle = C['8'];
  ctx.fillRect(x, y + Math.floor(phase % h), w, 2);
  ctx.restore();
}

/**
 * 2x2 棋盤圖樣，用來大面積填點陣。
 *
 * 傳送轉場的光圈邊緣需要點陣感，但逐像素掃描環帶在半徑 280 時
 * 每幀要跑 33 萬次；改用 pattern 填色是 O(1)。每個顏色只建一次。
 */
const checkerCache = new Map<string, CanvasPattern>();

export function checkerPattern(ctx: CanvasRenderingContext2D, color: string): CanvasPattern {
  const hit = checkerCache.get(color);
  if (hit) return hit;
  const tile = document.createElement('canvas');
  tile.width = 2;
  tile.height = 2;
  const tctx = tile.getContext('2d')!;
  tctx.fillStyle = color;
  tctx.fillRect(0, 0, 1, 1);
  tctx.fillRect(1, 1, 1, 1);
  const pattern = ctx.createPattern(tile, 'repeat')!;
  checkerCache.set(color, pattern);
  return pattern;
}

/**
 * 5x7 的迷你點陣字，只收招牌上真正需要的那幾個字元。
 *
 * 專案的規則是「中文一律走 DOM，不畫進 backbuffer」，因為 8px 的中文字
 * 整數放大後會糊掉。但拉丁字母與符號在 5x7 完全讀得出來，而且招牌上的
 * `MAX` / `NT$` 必須跟著世界一起捲動、被光照到、被柱子擋住 —— 那是場景的
 * 一部分，不是疊在畫面上的 UI。所以這幾個字元例外，直接畫進像素。
 *
 * 要新字元就補一筆，不要為了「完整」把 A-Z 全刻出來。
 */
const GLYPHS: Record<string, readonly string[]> = {
  M: ['x...x', 'xx.xx', 'x.x.x', 'x...x', 'x...x', 'x...x', 'x...x'],
  A: ['.xxx.', 'x...x', 'x...x', 'xxxxx', 'x...x', 'x...x', 'x...x'],
  X: ['x...x', 'x...x', '.x.x.', '..x..', '.x.x.', 'x...x', 'x...x'],
  N: ['x...x', 'xx..x', 'x.x.x', 'x..xx', 'x...x', 'x...x', 'x...x'],
  T: ['xxxxx', '..x..', '..x..', '..x..', '..x..', '..x..', '..x..'],
  // MAIA 的銘牌要刻在控制台上。它跟 MAX 的招牌是同一件事：那塊字是
  // 場景的一部分，要跟著世界捲動、被光照到、被柱子擋住，所以走像素而不是 DOM。
  I: ['xxxxx', '..x..', '..x..', '..x..', '..x..', '..x..', 'xxxxx'],
  $: ['..x..', '.xxxx', 'x.x..', '.xxx.', '..x.x', 'xxxx.', '..x..'],
  // 數字與正負號：討論室的情緒計要把 -100~100 直接寫在看板上。
  // 只用一條長條表示強弱的話，「偏多多少」永遠是模糊的。
  '0': ['.xxx.', 'x...x', 'x..xx', 'x.x.x', 'xx..x', 'x...x', '.xxx.'],
  '1': ['..x..', '.xx..', '..x..', '..x..', '..x..', '..x..', '.xxx.'],
  '2': ['.xxx.', 'x...x', '....x', '...x.', '..x..', '.x...', 'xxxxx'],
  '3': ['xxxxx', '...x.', '..x..', '...x.', '....x', 'x...x', '.xxx.'],
  '4': ['...x.', '..xx.', '.x.x.', 'x..x.', 'xxxxx', '...x.', '...x.'],
  '5': ['xxxxx', 'x....', 'xxxx.', '....x', '....x', 'x...x', '.xxx.'],
  '6': ['..xx.', '.x...', 'x....', 'xxxx.', 'x...x', 'x...x', '.xxx.'],
  '7': ['xxxxx', '....x', '...x.', '..x..', '.x...', '.x...', '.x...'],
  '8': ['.xxx.', 'x...x', 'x...x', '.xxx.', 'x...x', 'x...x', '.xxx.'],
  '9': ['.xxx.', 'x...x', 'x...x', '.xxxx', '....x', '...x.', '.xx..'],
  '+': ['.....', '..x..', '..x..', 'xxxxx', '..x..', '..x..', '.....'],
  '-': ['.....', '.....', '.....', 'xxxxx', '.....', '.....', '.....'],
};

const GLYPH_W = 5;
export const GLYPH_H = 7;

/** 一串點陣字的總寬度。畫之前先算好才能置中。 */
export function glyphWidth(text: string, scale = 1, gap = 1): number {
  return text.length * (GLYPH_W + gap) * scale - gap * scale;
}

export function glyphText(
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  color: string,
  scale = 1,
  gap = 1,
): void {
  ctx.fillStyle = color;
  let cx = x;
  for (const ch of text) {
    const rows = GLYPHS[ch];
    if (rows) {
      rows.forEach((row, ry) => {
        for (let rx = 0; rx < row.length; rx++) {
          if (row[rx] !== '.') ctx.fillRect(cx + rx * scale, y + ry * scale, scale, scale);
        }
      });
    }
    cx += (GLYPH_W + gap) * scale;
  }
}

/** 假的文字列。面板上的「有字」感覺，實際內容由 DOM 標籤負責。 */
export function textBars(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  rows: number,
  color: string,
  seed = 1,
): void {
  ctx.fillStyle = color;
  let s = seed;
  for (let i = 0; i < rows; i++) {
    s = (s * 1103515245 + 12345) & 0x7fffffff;
    const len = 4 + (s % Math.max(1, w - 6));
    ctx.fillRect(x, y + i * 3, len, 1);
  }
}

// ── 材質語彙（Task 4）────────────────────────────────────────
//
// 商業水準的像素美術不是把每個道具畫得更細，是建立一套所有道具
// 共用的材質與光照語彙，然後用它重切一遍。

/**
 * 5 階明暗 ramp。每個材質一組，從最暗（輪廓/遮蔽）到最亮（高光）。
 * 所有顏色都來自既有 PALETTE，不新增 key。
 *
 * 用法：`ctx.fillStyle = RAMP.metal[2]` 取中間階。
 * bevelBox 是 2 階（只分亮暗），ramp 系統是 5 階 —— 這是視覺落差最大的
 * 單一升級：2 階 = 程式繪圖，5 階 = 手繪感。
 */
export const RAMP = {
  /** 中性石材（大廳地板、柱子基座） */
  stone: [C['0'], C['4'], C.x, C.y, C['7']] as const,
  /** 亮金屬（櫃檯、欄杆） */
  metal: [C['0'], C['2'], C['3'], C['5'], C['6']] as const,
  /** 暗金屬（機櫃、底座、框架） */
  dark_metal: [C['0'], C['1'], C['2'], C['4'], C['5']] as const,
  /** 暖木（吧台、長椅、便利貼牆底板） */
  wood: [C['0'], C.e, C.g, C.b, C.c] as const,
  /** MAX 品牌藍（終端機、代幣柱、信託櫃檯嵌條） */
  brand: [C['0'], C.k, C.l, C.m, C.A] as const,
} as const;

export type RampId = keyof typeof RAMP;
export type Ramp = readonly [string, string, string, string, string];

// ── Bayer 4×4 有序抖色 ──────────────────────────────────────

/**
 * 4×4 Bayer 矩陣（歸一化到 0..15）。
 * 有序抖色比隨機噪點更有「像素藝術」的感覺 —— 規則的圖樣在整數放大後
 * 讀起來是材質紋理而不是雜訊。
 */
const BAYER4: readonly number[] = [
  0, 8, 2, 10,
  12, 4, 14, 6,
  3, 11, 1, 9,
  15, 7, 13, 5,
];

/**
 * 回傳 (px, py) 在 Bayer 矩陣中的閾值（0..15）。
 * 如果 `value` (0..15) >= 閾值，則該像素應被填色。
 */
export function bayerThreshold(px: number, py: number): number {
  return BAYER4[(py & 3) * 4 + (px & 3)]!;
}

/** 快取的 4x4 抖色 tile（兩色交替），避免每幀重建。 */
const ditherTileCache = new Map<string, CanvasPattern>();

/**
 * 取得一個 4×4 Bayer 抖色 pattern，在 threshold 以下的像素填 colorA，
 * 以上填 colorB（透明則用 'clear'）。快取，只建一次。
 */
export function bayerPattern(
  ctx: CanvasRenderingContext2D,
  colorA: string,
  colorB: string | 'clear',
  threshold: number,
): CanvasPattern {
  const key = `${colorA}|${colorB}|${threshold}`;
  const hit = ditherTileCache.get(key);
  if (hit) return hit;
  const tile = document.createElement('canvas');
  tile.width = 4;
  tile.height = 4;
  const tc = tile.getContext('2d')!;
  for (let py = 0; py < 4; py++) {
    for (let px = 0; px < 4; px++) {
      const t = BAYER4[py * 4 + px]!;
      if (t < threshold) {
        tc.fillStyle = colorA;
        tc.fillRect(px, py, 1, 1);
      } else if (colorB !== 'clear') {
        tc.fillStyle = colorB;
        tc.fillRect(px, py, 1, 1);
      }
    }
  }
  const pattern = ctx.createPattern(tile, 'repeat')!;
  ditherTileCache.set(key, pattern);
  return pattern;
}

/**
 * 用 Bayer 抖色填一個矩形。threshold 0..16 控制密度：
 * 0 = 全透明，16 = 完全填色。適合做漸層過渡或半透明陰影。
 */
export function ditherRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  color: string,
  threshold: number,
): void {
  if (threshold <= 0) return;
  if (threshold >= 16) {
    ctx.fillStyle = color;
    ctx.fillRect(x, y, w, h);
    return;
  }
  ctx.fillStyle = bayerPattern(ctx, color, 'clear', threshold);
  ctx.fillRect(x, y, w, h);
}

/**
 * 垂直方向的抖色漸層：從 `topThreshold` 到 `bottomThreshold`。
 * 把一個矩形分成若干水平帶，每帶的 threshold 線性插值。
 * 適合牆腳 AO、光柱淡出。
 */
export function ditherGradientV(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  color: string,
  topThreshold: number,
  bottomThreshold: number,
): void {
  // 每 2px 一個帶，減少 pattern 切換次數
  const step = 2;
  for (let row = 0; row < h; row += step) {
    const t = row / Math.max(1, h - 1);
    const th = Math.round(topThreshold + (bottomThreshold - topThreshold) * t);
    ditherRect(ctx, x, y + row, w, Math.min(step, h - row), color, th);
  }
}

// ── 接地與邊緣光 ────────────────────────────────────────────

/**
 * 接觸陰影：道具腳底的抖色橢圓。
 *
 * 現在道具是「貼在地上」的，有接觸陰影才是「站在地上」。
 * 用 Bayer 抖色而不是半透明，在整數放大後不會產生灰色中間值。
 */
export function contactShadow(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  rx: number,
  ry: number,
  density = 10,
): void {
  ctx.save();
  ctx.fillStyle = bayerPattern(ctx, C['0'], 'clear', density);
  ctx.beginPath();
  ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

/**
 * 邊緣光（rim light）：受光側（左上）1px 描邊。
 *
 * 這是 AAA 像素美術最明顯的特徵之一。在 bevelBox 的基礎上，
 * 外框的左上邊再多畫一條亮色線，讓物件從背景「跳」出來。
 */
export function rimLight(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  color: string,
  alpha = 0.6,
): void {
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.fillStyle = color;
  // 左邊
  ctx.fillRect(x, y + 1, 1, h - 2);
  // 上邊
  ctx.fillRect(x + 1, y, w - 2, 1);
  ctx.restore();
}

/**
 * 1-bit 顆粒噪點：在矩形內依 Bayer + 座標偏移撒幾個亮/暗點。
 * 讓平坦的大面積填色看起來有「材質」而不是純色塊。
 */
export function grain(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  color: string,
  density = 4,
  alpha = 0.3,
): void {
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.fillStyle = color;
  for (let py = 0; py < h; py += 2) {
    for (let px = 0; px < w; px += 2) {
      if (bayerThreshold(x + px, y + py) < density) {
        ctx.fillRect(x + px, y + py, 1, 1);
      }
    }
  }
  ctx.restore();
}

// ── 動畫相位 ────────────────────────────────────────────────

/**
 * 由座標推出的穩定相位偏移。
 *
 * 讓同一種道具（如三台礦機）各自錯開閃爍，不再像同一個貼圖複製三次。
 * 回傳值約 0..6.28（一個週期），加在 `t` 上即可。
 *
 * 注意：這個 hash 跟 props.ts 裡的 `hash()` 是同一個演算法，但那邊
 * 沒有 export。這裡重新寫一份是因為 shapes.ts 是 props.ts 的上游依賴，
 * 反過來 import 會造成循環。
 */
export function phaseOf(x: number, y: number): number {
  const h = (Math.imul(x, 73856093) ^ Math.imul(y, 19349663)) >>> 0;
  return (h % 1000) / 1000 * Math.PI * 2;
}

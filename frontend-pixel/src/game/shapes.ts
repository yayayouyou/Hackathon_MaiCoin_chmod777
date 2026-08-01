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

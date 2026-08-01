import { PALETTE as C } from '../art/palette';
import {
  bevelBox,
  glow,
  radialGlow,
  scanlines,
  textBars,
  glyphText,
  glyphWidth,
  METAL,
  DARK_METAL,
} from './shapes';
import { drawShadow } from './sprite';
import type { Accent, Prop, Rect } from '../world/types';
import { PROP_SIZE } from '../world/types';

export const ACCENT: Record<Accent, { hi: string; lo: string }> = {
  cyan: { hi: C.n, lo: C.o },
  amber: { hi: C.p, lo: C.q },
  violet: { hi: C.t, lo: C.u },
  green: { hi: C.s, lo: '#26935a' },
  // MAX 的品牌深藍。
  //
  // 暗階原本用 m（#455c91）想跟地板同階，結果終端機的資料流與門內漸層
  // 全部陷進背景裡 —— 整個房間的螢幕變成一片淡藍霧。改成品牌藍真正的
  // 中間階；green 的暗階也是這樣直接寫死的，不佔調色盤的位子。
  max: { hi: C.A, lo: '#3a5fd0' },
};

/**
 * 情緒 → 顏色。-100 是全紅（空），+100 是全綠（多），0 附近轉為中性。
 *
 * 中間段刻意去飽和而不是直接紅綠對混：紅綠各半混出來是濁褐色，看起來
 * 像顏色壞掉，而不是「兩邊在拉鋸」。分歧的房間應該是灰的，不是髒的。
 */
export function sentimentColor(sentiment: number): { hi: string; lo: string } {
  const k = Math.max(-1, Math.min(1, sentiment / 100));
  const mix = (a: string, b: string, t: number) => {
    const [x, y] = [parseInt(a.slice(1), 16), parseInt(b.slice(1), 16)];
    const ch = (sh: number) =>
      Math.round((((x >> sh) & 255) * (1 - t) + ((y >> sh) & 255) * t))
        .toString(16)
        .padStart(2, '0');
    return `#${ch(16)}${ch(8)}${ch(0)}`;
  };
  const strength = Math.abs(k);
  const target = k >= 0 ? C.s : C.r;
  return {
    hi: mix(C['7'], target, 0.35 + strength * 0.65),
    lo: mix(C['5'], target, 0.25 + strength * 0.5),
  };
}

/**
 * 由座標推出的穩定亂數，讓同一個道具的粒子相位每幀都一致。
 *
 * 取值一律用無號位移 `>>>`。帶號的 `>>` 遇到大於 2^31 的雜湊會變成負數，
 * 而 JS 的負數取餘數也是負的，粒子的座標就會跑到道具框外面去。
 */
const hash = (x: number, y: number) => (Math.imul(x, 73856093) ^ Math.imul(y, 19349663)) >>> 0;

export function propSize(p: Prop): { w: number; h: number } {
  const base = PROP_SIZE[p.kind];
  return { w: base.w || (p as { w: number }).w, h: base.h };
}

/** y 排序用的基準點：道具腳底。決定它該畫在角色前面還是後面。 */
export function propFootY(p: Prop): number {
  return p.y + propSize(p).h;
}

/** 場景光源。位置是光打在地上的落點，不是道具本身的座標。 */
export type Light = { x: number; y: number; r: number; color: string; strength: number };

/**
 * 會發光的道具就該把光打在地上。
 *
 * 原本看板與拱門在發光、地板卻毫無反應，所以那些光看起來是貼在畫面上的
 * 圖案而不是光。光源由道具推導而來，房間定義裡不必額外維護一份清單。
 */
export function propLights(p: Prop): Light[] {
  const a = 'accent' in p && p.accent ? ACCENT[p.accent] : null;
  switch (p.kind) {
    case 'pillar':
      return [{ x: p.x + 8, y: p.y + 50, r: 44, color: C['7'], strength: 0.4 }];
    case 'portal':
      return [{ x: p.x + 16, y: p.y + 46, r: 72, color: a!.hi, strength: 0.95 }];
    case 'board':
      return [{ x: p.x + 28, y: p.y + 42, r: 96, color: C.n, strength: 0.85 }];
    case 'terminal':
      return [{ x: p.x + 28, y: p.y + 40, r: 78, color: a!.hi, strength: 0.7 }];
    case 'hologram':
      return [{ x: p.x + 20, y: p.y + 38, r: 66, color: C.n, strength: 0.7 }];
    case 'robot':
      return [{ x: p.x + 12, y: p.y + 32, r: 44, color: a ? a.hi : C.p, strength: 0.55 }];
    case 'chartboard':
      return [{ x: p.x + 44, y: p.y + 48, r: 88, color: C.n, strength: 0.8 }];
    // 金幣雕像是大廳的地標，光池也該是全場最大的那一圈
    case 'coinstatue':
      return [{ x: p.x + 24, y: p.y + 44, r: 108, color: C.p, strength: 1 }];
    case 'minerrack':
      return [{ x: p.x + 20, y: p.y + 48, r: 48, color: C.s, strength: 0.5 }];
    case 'vault':
      return [{ x: p.x + 28, y: p.y + 50, r: 54, color: C.q, strength: 0.5 }];
    case 'cafebar':
      return [{ x: p.x + p.w / 2, y: p.y + 30, r: 84, color: C.p, strength: 0.6 }];
    case 'tradetable':
      return [{ x: p.x + 32, y: p.y + 22, r: 56, color: C.n, strength: 0.55 }];
    case 'trustdesk':
      return [{ x: p.x + p.w / 2, y: p.y + 44, r: 92, color: C.A, strength: 0.75 }];
    case 'maxtoken':
      return [{ x: p.x + 24, y: p.y + 50, r: 104, color: C.A, strength: 1 }];
    // 情緒計是全場最大的光池，而且顏色由多空決定 ——
    // 玩家還沒開任何面板，就先從地板的顏色感覺到這個房間在吵什麼。
    case 'topicboard':
      return [{ x: p.x + 72, y: p.y + 60, r: 132, color: sentimentColor(p.sentiment).hi, strength: 0.95 }];
    case 'noteboard':
      return [{ x: p.x + 44, y: p.y + 48, r: 62, color: C.p, strength: 0.45 }];
    // 螢幕牆與跑馬燈都是一整條，用單一點光源會變成中間一顆亮斑；
    // 拆成每段一個小光源，才會是連續的一整條光帶。
    case 'screenwall': {
      const cells = Math.floor(p.w / 56);
      return Array.from({ length: cells }, (_, i) => ({
        x: p.x + i * 56 + 26,
        y: p.y + 34,
        r: 60,
        color: C['7'],
        strength: 0.5,
      }));
    }
    case 'ticker': {
      const n = Math.max(1, Math.round(p.w / 160));
      return Array.from({ length: n }, (_, i) => ({
        x: p.x + ((i + 0.5) * p.w) / n,
        y: p.y + 26,
        r: 100,
        color: C['7'],
        strength: 0.4,
      }));
    }
    default:
      return [];
  }
}

export function drawProp(ctx: CanvasRenderingContext2D, p: Prop, t: number): void {
  switch (p.kind) {
    case 'pillar':
      return pillar(ctx, p.x, p.y);
    case 'bench':
      return bench(ctx, p.x, p.y);
    case 'portal':
      return portal(ctx, p.x, p.y, p.accent, t);
    case 'board':
      return board(ctx, p.x, p.y, t);
    case 'terminal':
      return terminal(ctx, p.x, p.y, p.accent, t);
    case 'hologram':
      return hologram(ctx, p.x, p.y, t);
    case 'stool':
      return stool(ctx, p.x, p.y);
    case 'counter':
      return counter(ctx, p.x, p.y, p.w);
    case 'screenwall':
      return screenwall(ctx, p.x, p.y, p.w, t);
    case 'robot':
      return robot(ctx, p.x, p.y, t, p.accent);
    case 'plant':
      return plant(ctx, p.x, p.y);
    case 'ticker':
      return ticker(ctx, p.x, p.y, p.w, t);
    case 'chartboard':
      return chartboard(ctx, p.x, p.y, t);
    case 'vault':
      return vault(ctx, p.x, p.y, t);
    case 'minerrack':
      return minerrack(ctx, p.x, p.y, t);
    case 'cafebar':
      return cafebar(ctx, p.x, p.y, p.w, t);
    case 'coinstatue':
      return coinstatue(ctx, p.x, p.y, t);
    case 'tradetable':
      return tradetable(ctx, p.x, p.y, t);
    case 'trustdesk':
      return trustdesk(ctx, p.x, p.y, p.w, t);
    case 'maxtoken':
      return maxtoken(ctx, p.x, p.y, t);
    case 'topicboard':
      return topicboard(ctx, p.x, p.y, p.sentiment, t);
    case 'noteboard':
      return noteboard(ctx, p.x, p.y, t);
  }
}

/**
 * 道具的碰撞盒。多半只取底部一小塊，讓角色能站在道具「後面」，
 * 這是俯視角製造深度的關鍵。傳送門與牆上螢幕沒有碰撞。
 */
export function propSolid(p: Prop): Rect | null {
  switch (p.kind) {
    case 'pillar':
      return { x: p.x, y: p.y + 40, w: 16, h: 16 };
    case 'bench':
      return { x: p.x, y: p.y + 2, w: 32, h: 12 };
    case 'board':
      return { x: p.x + 16, y: p.y + 34, w: 24, h: 14 };
    case 'terminal':
      return { x: p.x + 10, y: p.y + 28, w: 36, h: 16 };
    case 'hologram':
      return { x: p.x + 6, y: p.y + 28, w: 28, h: 12 };
    case 'stool':
      return { x: p.x, y: p.y + 4, w: 14, h: 10 };
    case 'counter':
      return { x: p.x - 2, y: p.y, w: p.w + 4, h: 20 };
    case 'robot':
      return { x: p.x + 2, y: p.y + 22, w: 20, h: 12 };
    case 'plant':
      return { x: p.x + 2, y: p.y + 12, w: 12, h: 10 };
    case 'chartboard':
      return { x: p.x + 8, y: p.y + 36, w: 72, h: 14 };
    case 'vault':
      return { x: p.x + 4, y: p.y + 38, w: 48, h: 16 };
    case 'minerrack':
      return { x: p.x + 2, y: p.y + 38, w: 36, h: 16 };
    case 'cafebar':
      return { x: p.x - 2, y: p.y + 18, w: p.w + 4, h: 16 };
    case 'coinstatue':
      return { x: p.x + 2, y: p.y + 46, w: 44, h: 14 };
    case 'tradetable':
      return { x: p.x + 6, y: p.y + 14, w: 52, h: 16 };
    case 'trustdesk':
      return { x: p.x - 2, y: p.y + 32, w: p.w + 4, h: 18 };
    case 'maxtoken':
      return { x: p.x + 4, y: p.y + 52, w: 40, h: 16 };
    case 'topicboard':
      return { x: p.x + 10, y: p.y + 48, w: 124, h: 16 };
    case 'noteboard':
      return { x: p.x + 8, y: p.y + 36, w: 72, h: 14 };
    // 傳送門、掛在牆上的螢幕與跑馬燈都不擋路
    case 'portal':
    case 'screenwall':
    case 'ticker':
      return null;
  }
}

// ── 個別道具 ────────────────────────────────────────────────

/**
 * 淺色木頭。整個世界都是金屬與螢幕，一塊暖色木頭就能拉出溫度差。
 * 咖啡吧台的檯面與所有長椅共用同一組，座椅與吧台才像同一個空間的家具。
 */
const WOOD = { fill: C.g, light: C.b, dark: C.f, line: C['0'] };

function pillar(ctx: CanvasRenderingContext2D, x: number, y: number) {
  drawShadow(ctx, x + 8, y + 55, 10, 4);
  bevelBox(ctx, x + 1, y, 14, 52, METAL); // 柱身
  // 中央嵌一條霧面燈條。原本這裡是兩道深色溝縫，於是柱子成了全場唯一
  // 完全不發光的道具 —— 站在它旁邊會覺得畫面破了一個黑洞。
  ctx.fillStyle = C['1'];
  ctx.fillRect(x + 5, y + 3, 1, 44);
  ctx.fillRect(x + 10, y + 3, 1, 44);
  glow(ctx, x + 6, y + 3, 4, 44, C['7'], 0.5);
  ctx.fillStyle = C['6'];
  ctx.fillRect(x + 6, y + 3, 4, 44);
  ctx.fillStyle = C['7'];
  ctx.fillRect(x + 7, y + 3, 2, 44);
  bevelBox(ctx, x, y + 46, 16, 10, DARK_METAL); // 柱腳
  bevelBox(ctx, x, y - 2, 16, 6, DARK_METAL); // 柱頭
}

function bench(ctx: CanvasRenderingContext2D, x: number, y: number) {
  drawShadow(ctx, x + 16, y + 13, 15, 3);
  ctx.fillStyle = C['1'];
  ctx.fillRect(x + 3, y + 8, 3, 6);
  ctx.fillRect(x + 26, y + 8, 3, 6);
  // 用 cafebar 檯面那組淺色木頭。原本是 f/g 這組深棕，討論室的地毯提亮之後
  // 座椅的亮階（#7a4a44）幾乎等於地毯本體（#7a5148），長椅整個消失在地上。
  bevelBox(ctx, x, y, 32, 9, WOOD);
}

function portal(ctx: CanvasRenderingContext2D, x: number, y: number, accent: Accent, t: number) {
  const a = ACCENT[accent];
  drawShadow(ctx, x + 16, y + 51, 15, 4);
  glow(ctx, x + 4, y + 6, 24, 42, a.hi, 0.9);

  // 門內：暗底 + 由下往上變暗的階梯漸層。
  // 這裡不用點陣 —— 規則的點格在 24px 寬的範圍裡會被看成紗窗，
  // 6px 一階的橫帶反而像能量場。
  ctx.fillStyle = C['0'];
  ctx.fillRect(x + 4, y + 6, 24, 42);
  ctx.save();
  ctx.fillStyle = a.lo;
  for (let i = 0; i < 7; i++) {
    ctx.globalAlpha = 0.06 + i * 0.035;
    ctx.fillRect(x + 4, y + 42 - i * 6, 24, 6);
  }
  ctx.restore();

  const seed = hash(x, y);
  for (let i = 0; i < 16; i++) {
    const px = x + 6 + ((seed >>> (i % 12)) % 20);
    const py = y + 46 - (((t * 22 + i * 31 + (seed % 40)) % 42) | 0);
    ctx.fillStyle = i % 3 === 0 ? a.hi : a.lo;
    ctx.fillRect(px, py, 1, 2);
  }

  // 門框：兩側立柱 + 上楣，內緣打一道亮邊當光源
  bevelBox(ctx, x, y, 4, 52, METAL);
  bevelBox(ctx, x + 28, y, 4, 52, METAL);
  bevelBox(ctx, x, y, 32, 8, METAL);
  ctx.fillStyle = a.hi;
  ctx.fillRect(x + 3, y + 6, 1, 42);
  ctx.fillRect(x + 28, y + 6, 1, 42);
  ctx.fillRect(x + 4, y + 6, 24, 1);
  ctx.fillStyle = a.lo;
  ctx.fillRect(x + 4, y + 47, 24, 1);
}

function board(ctx: CanvasRenderingContext2D, x: number, y: number, t: number) {
  drawShadow(ctx, x + 28, y + 47, 20, 5);
  bevelBox(ctx, x + 18, y + 36, 20, 12, DARK_METAL); // 基座
  ctx.fillStyle = C.n;
  ctx.fillRect(x + 22, y + 38, 12, 1);
  // 懸浮的全息面板，會非常緩慢地上下呼吸
  const lift = Math.round(Math.sin(t * 1.4) * 1);
  const py = y + lift;
  glow(ctx, x + 2, py, 52, 34, C.n, 0.7);
  ctx.fillStyle = C['0'];
  ctx.fillRect(x + 2, py, 52, 34);
  ctx.strokeStyle = C.n;
  ctx.lineWidth = 1;
  ctx.strokeRect(x + 2.5, py + 0.5, 51, 33);
  ctx.fillStyle = C.n;
  ctx.fillRect(x + 5, py + 4, 20, 2); // 標題列
  ctx.fillStyle = C.r;
  ctx.fillRect(x + 46, py + 4, 4, 2); // 熱度標記
  textBars(ctx, x + 6, py + 11, 44, 7, C.o, 7);
  scanlines(ctx, x + 3, py + 1, 50, 32, t * 9);
  // 從基座打上來的光束
  ctx.save();
  ctx.globalAlpha = 0.18;
  ctx.fillStyle = C.n;
  ctx.beginPath();
  ctx.moveTo(x + 22, y + 37);
  ctx.lineTo(x + 34, y + 37);
  ctx.lineTo(x + 50, py + 34);
  ctx.lineTo(x + 6, py + 34);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

function terminal(ctx: CanvasRenderingContext2D, x: number, y: number, accent: Accent, t: number) {
  const a = ACCENT[accent];
  drawShadow(ctx, x + 28, y + 43, 24, 5);
  bevelBox(ctx, x + 14, y + 34, 28, 10, DARK_METAL); // 底座
  bevelBox(ctx, x, y, 56, 36, METAL); // 機殼
  ctx.fillStyle = C['0'];
  ctx.fillRect(x + 4, y + 4, 48, 28); // 螢幕
  glow(ctx, x + 4, y + 4, 48, 28, a.hi, 0.5);
  // 往下捲動的資料流：每欄速度不同才不會整齊得像壁紙
  const seed = hash(x, y);
  for (let col = 0; col < 12; col++) {
    const speed = 14 + ((seed >>> col) % 10);
    const off = (t * speed + col * 17) % 34;
    for (let k = 0; k < 4; k++) {
      const py = y + 4 + ((off + k * 8) % 28);
      ctx.fillStyle = k === 0 ? a.hi : a.lo;
      ctx.fillRect(x + 5 + col * 4, y + 4 + Math.floor(py - y - 4), 2, 1);
    }
  }
  ctx.fillStyle = a.hi;
  ctx.fillRect(x + 6, y + 6, 14, 1);
  scanlines(ctx, x + 4, y + 4, 48, 28, t * 11);
}

function hologram(ctx: CanvasRenderingContext2D, x: number, y: number, t: number) {
  drawShadow(ctx, x + 20, y + 39, 16, 4);
  bevelBox(ctx, x + 8, y + 30, 24, 10, DARK_METAL); // 投影基座
  ctx.fillStyle = C.n;
  ctx.fillRect(x + 14, y + 32, 12, 1);
  // 三圈以不同速度旋轉的光環，用縮放後的橢圓模擬
  ctx.save();
  for (let i = 0; i < 3; i++) {
    const ph = t * (0.9 + i * 0.35) + i * 2;
    const ry = 2 + Math.abs(Math.sin(ph)) * 4;
    ctx.globalAlpha = 0.35 + 0.25 * Math.abs(Math.cos(ph));
    ctx.strokeStyle = i === 1 ? C.n : C.o;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.ellipse(x + 20, y + 10 + i * 8, 11 - i * 2, ry, 0, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.globalAlpha = 0.16;
  ctx.fillStyle = C.n;
  ctx.beginPath();
  ctx.moveTo(x + 14, y + 31);
  ctx.lineTo(x + 26, y + 31);
  ctx.lineTo(x + 33, y + 2);
  ctx.lineTo(x + 7, y + 2);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

/** 圓凳：橢圓坐墊 + 中央單柱。方形坐墊在這個尺寸會被看成小螢幕。 */
function stool(ctx: CanvasRenderingContext2D, x: number, y: number) {
  drawShadow(ctx, x + 7, y + 13, 7, 3);
  ctx.fillStyle = C['1'];
  ctx.fillRect(x + 6, y + 7, 3, 5);
  const seat = (cy: number, rx: number, ry: number, color: string) => {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.ellipse(x + 7, y + cy, rx, ry, 0, 0, Math.PI * 2);
    ctx.fill();
  };
  seat(7, 7, 5, C['0']);
  seat(6, 6, 4, C['3']);
  seat(5, 4, 2, C['5']);
}

function counter(ctx: CanvasRenderingContext2D, x: number, y: number, w: number) {
  drawShadow(ctx, x + w / 2, y + 19, w / 2 - 2, 4);
  bevelBox(ctx, x, y + 6, w, 14, DARK_METAL);
  // 面板接縫，不然一長條會看起來只是一根棒子
  ctx.fillStyle = C['0'];
  for (let i = 24; i < w - 8; i += 24) ctx.fillRect(x + i, y + 9, 1, 9);
  bevelBox(ctx, x - 2, y, w + 4, 8, METAL); // 檯面往外突出一點
  ctx.fillStyle = C.p;
  ctx.fillRect(x + 2, y + 10, w - 4, 1);
}

function screenwall(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, t: number) {
  const cells = Math.floor(w / 56);
  for (let i = 0; i < cells; i++) {
    const cx = x + i * 56;
    bevelBox(ctx, cx, y, 52, 26, DARK_METAL);
    ctx.fillStyle = C['0'];
    ctx.fillRect(cx + 3, y + 3, 46, 20);
    // 每 0.8 秒換一次數值，模擬跳動的報價。
    // 每格加上自己的相位偏移，否則整面牆會同時翻紅翻綠 ——
    // 而且 up 要取雜湊的高位元，最低位元跟 i 的奇偶性相關，
    // 會讓所有格子的漲跌鎖在一起。
    const tick = Math.floor((t + i * 0.37) / 0.8);
    const h = hash(i * 31 + 7, tick);
    const up = ((h >>> 5) & 1) === 0;
    const col = up ? C.s : C.r;
    glow(ctx, cx + 3, y + 3, 46, 20, col, 0.35);
    ctx.fillStyle = C['6'];
    ctx.fillRect(cx + 6, y + 6, 12, 2); // 幣種代號
    ctx.fillStyle = col;
    ctx.fillRect(cx + 6, y + 12, 18 + (h % 14), 3); // 價格
    // 漲跌箭頭
    for (let k = 0; k < 4; k++) {
      const wdt = up ? 1 + k * 2 : 7 - k * 2;
      ctx.fillRect(cx + 42 - wdt / 2, y + (up ? 8 + k : 17 - k), wdt, 1);
    }
    scanlines(ctx, cx + 3, y + 3, 46, 20, t * 13 + i * 5);
  }
}

/**
 * 客服機器人：懸浮 + 眨眼。它是道具而不是 NPC，因為它不會移動、
 * 而且長得跟人形 sprite 完全不同，走道具那條路可以直接吃到 y 排序。
 */
function robot(ctx: CanvasRenderingContext2D, x: number, y: number, t: number, accent?: Accent) {
  // 眼睛、天線與懸浮光都吃站點的主題色；MAIA 傳 'max' 進來就是品牌藍，
  // 跟它所在的 MAX 藍色資訊角連成一氣。沒帶 accent 時退回原本的琥珀。
  const hi = accent ? ACCENT[accent].hi : C.p;
  const lift = Math.round(Math.sin(t * 1.8) * 2);
  const by = y + lift;
  drawShadow(ctx, x + 12, y + 34, 9 - lift, 3);
  glow(ctx, x + 4, by + 8, 16, 14, hi, 0.4);
  bevelBox(ctx, x + 2, by + 20, 20, 10, DARK_METAL); // 懸浮基座
  ctx.fillStyle = hi;
  ctx.fillRect(x + 5, by + 28, 14, 1);
  bevelBox(ctx, x + 4, by + 6, 16, 16, METAL); // 頭
  ctx.fillStyle = C['0'];
  ctx.fillRect(x + 6, by + 9, 12, 8); // 面板
  // 每三秒眨一次眼，眨眼期間畫成一條線
  const blink = t % 3 < 0.12;
  ctx.fillStyle = hi;
  if (blink) {
    ctx.fillRect(x + 8, by + 13, 3, 1);
    ctx.fillRect(x + 13, by + 13, 3, 1);
  } else {
    ctx.fillRect(x + 8, by + 11, 3, 3);
    ctx.fillRect(x + 13, by + 11, 3, 3);
  }
  ctx.fillStyle = C.q;
  ctx.fillRect(x + 9, by + 4, 6, 2); // 天線座
  ctx.fillStyle = C['6'];
  ctx.fillRect(x + 11, by, 2, 5);
  ctx.fillStyle = hi;
  ctx.fillRect(x + 10, by - 2, 4, 3);
}

// ── 大廳的虛擬貨幣主題道具 ──────────────────────────────────

/** 實心圓。金幣與金庫門都是同心圓疊出來的，抽一個出來省得重複。 */
function disc(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number, color: string) {
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.ellipse(cx, cy, r, r, 0, 0, Math.PI * 2);
  ctx.fill();
}

/**
 * 行情跑馬燈：橫貫整面上牆的 LED 燈條。
 *
 * 這是整個大廳最重要的一件道具 —— 一進門看到滿牆滾動的報價，
 * 就不需要任何文字說明這裡是什麼地方。
 *
 * 內容不是真的產生一條無限長的字串再平移，而是每 88px 一組
 * 「代號 + 價格 + 箭頭」、用取模的相位重複畫。漲跌由組序號的雜湊決定
 * 而不是時間，所以滾動時每一組的顏色是固定的，不會邊跑邊閃。
 */
function ticker(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, t: number) {
  bevelBox(ctx, x, y, w, 12, DARK_METAL);
  ctx.fillStyle = C['0'];
  ctx.fillRect(x + 1, y + 2, w - 2, 8);

  const period = 88;
  const scroll = (t * 24) % period;
  const groups = Math.ceil(w / period) + 1;
  ctx.save();
  ctx.beginPath();
  ctx.rect(x + 1, y + 2, w - 2, 8);
  ctx.clip();
  for (let i = 0; i < groups; i++) {
    const gx = Math.round(x + i * period - scroll);
    const h = hash(i * 41 + 11, 0);
    const up = ((h >>> 5) & 1) === 0;
    const col = up ? C.s : C.r;
    ctx.fillStyle = C['7'];
    ctx.fillRect(gx + 4, y + 4, 10, 2); // 幣種代號
    ctx.fillStyle = col;
    ctx.fillRect(gx + 18, y + 4, 16 + (h % 12), 2); // 價格
    for (let k = 0; k < 3; k++) {
      const wd = up ? 1 + k * 2 : 5 - k * 2;
      ctx.fillRect(gx + 52 - (wd >> 1), y + (up ? 3 + k : 7 - k), wd, 1);
    }
  }
  ctx.restore();
  ctx.fillStyle = C['5'];
  ctx.fillRect(x, y, w, 1);
}

/** K 線圖看板：漲跌一眼可讀，最後一根隨時間翻面，看得出盤還在跑。 */
function chartboard(ctx: CanvasRenderingContext2D, x: number, y: number, t: number) {
  drawShadow(ctx, x + 44, y + 50, 34, 5);
  bevelBox(ctx, x + 20, y + 40, 48, 12, DARK_METAL); // 基座
  bevelBox(ctx, x, y, 88, 44, METAL);
  ctx.fillStyle = C['0'];
  ctx.fillRect(x + 3, y + 3, 82, 38);
  glow(ctx, x + 3, y + 3, 82, 38, C.n, 0.4);

  ctx.save();
  ctx.globalAlpha = 0.22;
  ctx.fillStyle = C['5'];
  for (let gx = x + 3; gx < x + 85; gx += 10) ctx.fillRect(gx, y + 3, 1, 38);
  for (let gy = y + 7; gy < y + 41; gy += 8) ctx.fillRect(x + 3, gy, 82, 1);
  ctx.restore();

  const seed = hash(x, y) & 0xffff;
  for (let i = 0; i < 20; i++) {
    const h = hash(i * 17 + 3, seed);
    const mid = 14 + (h % 16);
    const half = 2 + ((h >>> 7) % 4);
    const wick = half + 2 + ((h >>> 11) % 3);
    // 最後一根是「還在跳的那一根」，其餘固定
    const up = i === 19 ? Math.sin(t * 2.2) > 0 : ((h >>> 3) & 1) === 0;
    const cx = x + 5 + i * 4;
    ctx.fillStyle = up ? C.s : C.r;
    ctx.fillRect(cx + 1, y + mid - wick, 1, wick * 2);
    ctx.fillRect(cx, y + mid - half, 3, half * 2);
  }
  ctx.fillStyle = C.n;
  ctx.fillRect(x + 6, y + 5, 16, 1); // 標題列
  scanlines(ctx, x + 3, y + 3, 82, 38, t * 10);
}

/**
 * 冷錢包金庫。
 *
 * 上牆只有 16px 高，做不出嵌在牆裡的圓門，所以做成靠牆的獨立櫃體。
 * 轉盤轉得很慢（0.35 rad/s）—— 快了就會像洗衣機。
 */
function vault(ctx: CanvasRenderingContext2D, x: number, y: number, t: number) {
  drawShadow(ctx, x + 28, y + 54, 24, 5);
  bevelBox(ctx, x, y, 56, 52, METAL); // 櫃體

  // 頂部控制條：LOCKED 綠燈 + 讀數
  bevelBox(ctx, x + 3, y + 2, 50, 8, DARK_METAL);
  // 緩慢呼吸而不是閃爍 —— 閃爍看起來像故障，不像上鎖
  ctx.fillStyle = t % 3 < 1.8 ? C.s : '#26935a';
  ctx.fillRect(x + 6, y + 5, 4, 2);
  textBars(ctx, x + 14, y + 5, 34, 1, C.q, 3);

  // 圓門。門板刻意比櫃體亮兩階 —— 第一版門跟櫃體同一階，整件變成
  // 一個中間有圓圈的深灰方塊，看起來像喇叭而不是金庫。
  const cx = x + 28;
  const cy = y + 31;
  disc(ctx, cx, cy, 19, C['0']);
  disc(ctx, cx, cy, 18, C.q); // 黃銅門框
  disc(ctx, cx, cy, 16, C['1']);
  disc(ctx, cx, cy, 15, C['5']);
  disc(ctx, cx, cy, 12, C['4']);

  // 轉盤：五根輻條，末端各一顆黃銅握把
  const ph = t * 0.35;
  for (let k = 0; k < 5; k++) {
    const a = ph + (k * Math.PI * 2) / 5;
    const cs = Math.cos(a);
    const sn = Math.sin(a);
    ctx.fillStyle = C['7'];
    for (let r = 3; r <= 11; r++) {
      ctx.fillRect(Math.round(cx + cs * r), Math.round(cy + sn * r), 1, 1);
    }
    ctx.fillStyle = C.p;
    ctx.fillRect(Math.round(cx + cs * 12) - 1, Math.round(cy + sn * 12) - 1, 2, 2);
  }
  disc(ctx, cx, cy, 3, C['7']);
  disc(ctx, cx, cy, 1, C.q);

  // 左側兩顆鉸鏈，右側一道門縫：沒有這些它就只是一個圓，不是一扇門
  ctx.fillStyle = C['2'];
  ctx.fillRect(x + 6, y + 18, 4, 6);
  ctx.fillRect(x + 6, y + 38, 4, 6);
  ctx.fillStyle = C['1'];
  ctx.fillRect(x + 48, y + 20, 1, 22);
}

/** 礦機機櫃：四層機板、風扇在轉、指示燈各有自己的節奏。 */
function minerrack(ctx: CanvasRenderingContext2D, x: number, y: number, t: number) {
  drawShadow(ctx, x + 20, y + 54, 17, 5);
  bevelBox(ctx, x, y, 40, 52, METAL);
  for (let i = 0; i < 4; i++) {
    const by = y + 4 + i * 12;
    bevelBox(ctx, x + 3, by, 34, 10, DARK_METAL);

    // 風扇：四片葉子用整數座標的像素點畫，不用 stroke ——
    // 1px 的斜線一旦被抗鋸齒就糊掉了，像素風容不下這個。
    const fx = x + 9;
    const fy = by + 5;
    const ph = t * (5 + i * 1.3);
    ctx.fillStyle = C['2'];
    ctx.fillRect(fx - 4, fy - 4, 9, 9);
    for (let k = 0; k < 4; k++) {
      const a = ph + (k * Math.PI) / 2;
      ctx.fillStyle = k === 0 ? C['7'] : C['5'];
      for (let r = 1; r <= 3; r++) {
        ctx.fillRect(Math.round(fx + Math.cos(a) * r), Math.round(fy + Math.sin(a) * r), 1, 1);
      }
    }
    for (let k = 0; k < 5; k++) {
      const on = ((hash(i * 7 + k, Math.floor(t * 3 + k * 0.6)) >>> 4) & 3) !== 0;
      ctx.fillStyle = on ? C.s : C['1'];
      ctx.fillRect(x + 18 + k * 4, by + 4, 2, 2);
    }
  }
}

/**
 * 咖啡吧台。
 *
 * 這一件不是虛擬貨幣元素，是刻意放的 —— 一個全是螢幕與金屬的空間會冷得
 * 沒人想待。有咖啡機、有杯子、有冒煙的杯，空間才像有人在用。
 */
function cafebar(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, t: number) {
  drawShadow(ctx, x + w / 2, y + 34, w / 2 - 2, 5);
  bevelBox(ctx, x + 4, y + 4, w - 8, 16, DARK_METAL); // 後方器具檯

  // 咖啡機刻意比檯面高出 10px。第一版整台包在檯面裡，遠看就是一排
  // 深色方塊 —— 這件道具唯一的辨識點就是那個突出去的剪影。
  bevelBox(ctx, x + 8, y - 10, 28, 30, METAL);
  ctx.fillStyle = C['0'];
  ctx.fillRect(x + 11, y - 7, 22, 8);
  ctx.fillStyle = C.p;
  ctx.fillRect(x + 13, y - 5, 9, 2);
  ctx.fillStyle = C.r;
  ctx.fillRect(x + 29, y - 6, 3, 3);
  ctx.fillStyle = C.s;
  ctx.fillRect(x + 29, y - 1, 3, 3);
  ctx.fillStyle = C['1']; // 兩顆沖煮頭
  ctx.fillRect(x + 12, y + 6, 6, 9);
  ctx.fillRect(x + 25, y + 6, 6, 9);
  ctx.fillStyle = C['6'];
  ctx.fillRect(x + 13, y + 13, 4, 1);
  ctx.fillRect(x + 26, y + 13, 4, 1);
  ctx.fillStyle = C['5'];
  ctx.fillRect(x + 21, y + 4, 1, 10); // 蒸氣管

  for (let i = 0; i < 3; i++) { // 杯架
    const cx = x + 42 + i * 9;
    ctx.fillStyle = C['7'];
    ctx.fillRect(cx, y + 7, 6, 5);
    ctx.fillStyle = C['5'];
    ctx.fillRect(cx, y + 12, 6, 1);
  }
  ctx.fillStyle = C['1']; // 價目牌
  ctx.fillRect(x + w - 32, y + 6, 24, 12);
  textBars(ctx, x + w - 29, y + 8, 18, 3, C.p, 5);

  bevelBox(ctx, x, y + 22, w, 12, WOOD); // 木質檯面
  bevelBox(ctx, x - 2, y + 20, w + 4, 5, { fill: C.b, light: C.d, dark: C.f, line: C['0'] });
  ctx.fillStyle = C.q;
  ctx.fillRect(x, y + 33, w, 1); // 檯面下緣的黃銅收邊

  // 檯面上兩杯冒煙的咖啡 —— 有蒸氣才看得出這裡剛剛有人
  for (const cx of [x + 52, x + 64]) {
    ctx.fillStyle = C['7'];
    ctx.fillRect(cx, y + 25, 5, 5);
    ctx.fillStyle = C.f;
    ctx.fillRect(cx + 1, y + 25, 3, 1);
    ctx.save();
    ctx.globalAlpha = 0.4;
    ctx.fillStyle = C['8'];
    for (let k = 0; k < 3; k++) {
      const sx = Math.round(cx + 2 + Math.sin(t * 2 + k * 1.1 + cx * 0.4) * 1.6);
      ctx.fillRect(sx, y + 22 - k * 3, 1, 2);
    }
    ctx.restore();
  }
}

/**
 * 中央的金幣雕像 —— 大廳的地標。
 *
 * 大空間需要一個「這裡是中心」的物件，否則玩家沒有方向感。三層往上收的
 * 基座負責重量，立起來的幣面負責亮點，掃過幣面的高光負責金屬感 ——
 * 少了那道高光它就只是一塊黃色的圓餅。
 */
function coinstatue(ctx: CanvasRenderingContext2D, x: number, y: number, t: number) {
  drawShadow(ctx, x + 24, y + 58, 21, 6);
  bevelBox(ctx, x + 2, y + 48, 44, 12, DARK_METAL);
  bevelBox(ctx, x + 7, y + 41, 34, 9, METAL);
  bevelBox(ctx, x + 12, y + 35, 24, 8, DARK_METAL);
  ctx.fillStyle = C.q;
  ctx.fillRect(x + 12, y + 52, 24, 1); // 銘牌

  const cx = x + 24;
  const cy = y + 18;
  radialGlow(ctx, cx, cy, 16, C.p, 1);
  disc(ctx, cx, cy, 16, C['0']);
  disc(ctx, cx, cy, 15, C.q);
  disc(ctx, cx, cy, 12, C.p);
  disc(ctx, cx, cy, 10, C.q);

  // ₿ 的塊狀化身：一豎、三橫、兩段右緣、上下各兩根出頭
  const bx = cx - 5;
  const by = cy - 8;
  ctx.fillStyle = C['8'];
  ctx.fillRect(bx, by + 2, 2, 12);
  ctx.fillRect(bx + 3, by, 2, 3);
  ctx.fillRect(bx + 6, by, 2, 3);
  ctx.fillRect(bx + 3, by + 13, 2, 3);
  ctx.fillRect(bx + 6, by + 13, 2, 3);
  ctx.fillRect(bx, by + 2, 8, 2);
  ctx.fillRect(bx, by + 7, 8, 2);
  ctx.fillRect(bx, by + 12, 8, 2);
  ctx.fillRect(bx + 7, by + 3, 2, 5);
  ctx.fillRect(bx + 7, by + 8, 2, 5);

  // 掃過幣面的高光
  ctx.save();
  ctx.beginPath();
  ctx.ellipse(cx, cy, 15, 15, 0, 0, Math.PI * 2);
  ctx.clip();
  ctx.globalAlpha = 0.3;
  ctx.fillStyle = C['8'];
  ctx.fillRect(Math.round(cx - 17 + ((t * 0.45) % 1) * 34), cy - 16, 3, 32);
  ctx.restore();

  // 火花：位置由雜湊固定，只有亮度隨時間變，不會滿天亂飛
  const seed = hash(x, y);
  for (let i = 0; i < 5; i++) {
    const a = ((seed >>> (i * 3)) % 360) * (Math.PI / 180);
    const r = 18 + ((seed >>> (i * 4 + 2)) % 8);
    const k = (t * 0.8 + i * 0.37) % 1;
    ctx.save();
    ctx.globalAlpha = 0.7 * (1 - k);
    ctx.fillStyle = C.p;
    ctx.fillRect(Math.round(cx + Math.cos(a) * r), Math.round(cy + Math.sin(a) * r - k * 6), 1, 1);
    ctx.restore();
  }
}

/** 盯盤圓桌：桌面嵌一片小螢幕，上方浮著迷你 K 線。 */
function tradetable(ctx: CanvasRenderingContext2D, x: number, y: number, t: number) {
  drawShadow(ctx, x + 32, y + 30, 27, 6);
  ctx.fillStyle = C['1'];
  ctx.fillRect(x + 29, y + 22, 6, 9); // 中柱
  const top = (dy: number, rx: number, ry: number, color: string) => {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.ellipse(x + 32, y + 20 + dy, rx, ry, 0, 0, Math.PI * 2);
    ctx.fill();
  };
  top(0, 28, 10, C['0']);
  top(-1, 27, 9, C['3']);
  top(-2, 24, 7, C['4']);

  ctx.fillStyle = C['0']; // 嵌在桌面的螢幕
  ctx.fillRect(x + 23, y + 15, 18, 6);
  glow(ctx, x + 23, y + 15, 18, 6, C.n, 0.5);
  const seed = hash(x, y);
  for (let i = 0; i < 8; i++) {
    const h = hash(i * 13 + 5, seed & 0xffff);
    ctx.fillStyle = (h >>> 3) & 1 ? C.s : C.r;
    ctx.fillRect(x + 24 + i * 2, y + 17 + (h % 3), 1, 2);
  }
  // 桌上浮著的迷你 K 線，很緩慢地上下呼吸
  const lift = Math.round(Math.sin(t * 1.5) * 1);
  ctx.save();
  ctx.globalAlpha = 0.5;
  ctx.fillStyle = C.n;
  for (let i = 0; i < 6; i++) {
    const h = hash(i * 29 + 7, seed & 0xff);
    ctx.fillRect(x + 24 + i * 3, y + 4 + lift + (h % 4), 2, 3 + (h % 3));
  }
  ctx.restore();
}

// ── 討論室 ──────────────────────────────────────────────────

/**
 * 主題看板 + 情緒計，合成一件。
 *
 * 原本打算做兩件（一塊主題招牌、一台情緒計），但兩塊看板並排會互相搶戲，
 * 玩家不知道該看哪個。合成一件之後它就是這個房間唯一的「結論板」：
 * 上半是在吵什麼，下半是吵成什麼樣子。
 *
 * 上半的深色面板刻意留空 —— 中文由 worldLabels 疊在那塊區域上。
 */
function topicboard(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  sentiment: number,
  t: number,
) {
  const c = sentimentColor(sentiment);
  drawShadow(ctx, x + 72, y + 62, 60, 6);
  bevelBox(ctx, x + 44, y + 52, 56, 12, DARK_METAL); // 基座
  bevelBox(ctx, x, y, 144, 56, METAL);

  // 上半：中文的位置。只畫一塊有內縮邊框的深色板，字交給 DOM。
  ctx.fillStyle = C['0'];
  ctx.fillRect(x + 4, y + 4, 136, 26);
  ctx.strokeStyle = c.lo;
  ctx.lineWidth = 1;
  ctx.strokeRect(x + 4.5, y + 4.5, 135, 25);

  // 下半：情緒計。中線為 0，往右是多、往左是空。
  const cx = x + 72;
  const bar = { y: y + 38, h: 8, half: 62 };
  ctx.fillStyle = C['0'];
  ctx.fillRect(cx - bar.half, bar.y, bar.half * 2, bar.h);
  const k = Math.max(-1, Math.min(1, sentiment / 100));
  const len = Math.round(Math.abs(k) * bar.half);
  ctx.fillStyle = c.lo;
  ctx.fillRect(k >= 0 ? cx : cx - len, bar.y + 1, len, bar.h - 2);
  ctx.fillStyle = c.hi;
  ctx.fillRect(k >= 0 ? cx + len - 2 : cx - len, bar.y, 2, bar.h); // 指針
  ctx.fillStyle = C['5'];
  ctx.fillRect(cx, bar.y - 1, 1, bar.h + 2); // 中線

  // 兩端的多空標記：右綠上箭頭、左紅下箭頭
  for (const [ex, up, col] of [
    [cx + bar.half + 3, true, C.s],
    [cx - bar.half - 6, false, C.r],
  ] as const) {
    ctx.fillStyle = col;
    for (let i = 0; i < 3; i++) {
      const w = up ? 1 + i * 2 : 5 - i * 2;
      ctx.fillRect(ex + 2 - (w >> 1), bar.y + (up ? 1 + i : 5 - i), w, 1);
    }
  }

  // 數值。只靠一條長條的話「偏多多少」永遠是模糊的。
  const label = `${sentiment >= 0 ? '+' : '-'}${Math.abs(Math.round(sentiment))}`;
  glyphText(ctx, label, cx - glyphWidth(label) / 2, y + 48, c.hi);
  scanlines(ctx, x + 4, y + 4, 136, 26, t * 8);
}

/**
 * 便利貼牆。
 *
 * 討論區需要一件「有人來過」的東西。便利貼是最省的做法：位置與顏色由
 * 雜湊固定（不會每幀亂跳），最新的幾張刻意畫得歪一點、疊在別人上面。
 */
function noteboard(ctx: CanvasRenderingContext2D, x: number, y: number, t: number) {
  drawShadow(ctx, x + 44, y + 50, 34, 5);
  bevelBox(ctx, x + 28, y + 38, 32, 12, DARK_METAL); // 立架
  // 軟木底板：用地毯那組暖褐，跟右半場的地毯是同一個色系
  bevelBox(ctx, x, y, 88, 42, { fill: C.w, light: C.g, dark: C.v, line: C['0'] });

  const seed = hash(x, y);
  const NOTE = [C.p, C.s, C.n, C.r, C['7']];
  for (let i = 0; i < 12; i++) {
    const h = hash(i * 23 + 5, seed & 0xffff);
    const nx = x + 5 + (i % 4) * 21 + ((h >>> 3) % 3);
    const ny = y + 4 + Math.floor(i / 4) * 12 + ((h >>> 7) % 2);
    ctx.fillStyle = C['0'];
    ctx.fillRect(nx, ny, 15, 10);
    ctx.fillStyle = NOTE[h % NOTE.length]!;
    ctx.fillRect(nx + 1, ny + 1, 13, 8);
    // 貼紙上的假字。深一點的同色系，不用純黑 —— 純黑在 8px 高的紙上太重。
    ctx.fillStyle = C['2'];
    ctx.fillRect(nx + 3, ny + 3, 8 + (h % 4), 1);
    ctx.fillRect(nx + 3, ny + 6, 5 + ((h >>> 5) % 6), 1);
  }
  // 一張最新的便利貼，被風吹得輕輕晃
  const sway = Math.round(Math.sin(t * 1.1) * 1);
  ctx.fillStyle = C['0'];
  ctx.fillRect(x + 70 + sway, y + 30, 15, 12);
  ctx.fillStyle = C.p;
  ctx.fillRect(x + 71 + sway, y + 31, 13, 10);
  ctx.fillStyle = C['2'];
  ctx.fillRect(x + 73 + sway, y + 34, 9, 1);
  ctx.fillRect(x + 73 + sway, y + 37, 6, 1);
}

// ── MAX 情報室的品牌道具 ────────────────────────────────────

/**
 * 法幣信託櫃檯。
 *
 * MAX 最獨有的一件事是「全球首家把用戶法幣交由銀行信託保管」（遠東商銀）。
 * 那是抽象的金融安排，畫不出來 —— 能畫的是它的具象化身：一整面銀行保管箱、
 * 一張辦事櫃檯、一塊寫著 NT$ 的招牌。台幣符號是這間交易所最在地的標記。
 */
function trustdesk(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, t: number) {
  drawShadow(ctx, x + w / 2, y + 50, w / 2 - 2, 5);

  // 後方保管箱牆：每一格都有小門與鎖孔
  bevelBox(ctx, x + 4, y, w - 8, 30, DARK_METAL);
  const cols = Math.floor((w - 16) / 15);
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < cols; c++) {
      const bx = x + 9 + c * 15;
      const by = y + 3 + r * 9;
      bevelBox(ctx, bx, by, 13, 7, METAL);
      ctx.fillStyle = C.A;
      ctx.fillRect(bx + 9, by + 3, 2, 1); // 鎖孔
    }
  }

  // NT$ 招牌。招牌本身發藍光，是這件道具的辨識點。
  const sw = glyphWidth('NT$', 1, 1) + 8;
  const sx = x + w - sw - 6;
  glow(ctx, sx, y + 6, sw, 13, C.A, 0.7);
  bevelBox(ctx, sx, y + 6, sw, 13, { fill: C.l, light: C.m, dark: C.k, line: C['0'] });
  glyphText(ctx, 'NT$', sx + 4, y + 9, C['8'], 1, 1);

  // 櫃檯。用 METAL（#2c3648）會整條變成一塊黑板 —— 銀行櫃檯是刷紋鋼，
  // 亮一階才有「可以走上去辦事」的感覺。
  bevelBox(ctx, x, y + 34, w, 14, { fill: C['4'], light: C['6'], dark: C['2'], line: C['0'] });
  bevelBox(ctx, x - 2, y + 32, w + 4, 6, DARK_METAL);
  ctx.fillStyle = C.A;
  ctx.fillRect(x + 2, y + 38, w - 4, 1);
  // 檯面上的受理燈，慢慢明滅表示「有在服務」
  ctx.save();
  ctx.globalAlpha = 0.5 + 0.5 * Math.abs(Math.sin(t * 0.9));
  ctx.fillStyle = C.s;
  ctx.fillRect(x + 8, y + 41, 3, 3);
  ctx.restore();
  textBars(ctx, x + 16, y + 41, Math.max(8, w - 30), 1, C['6'], 9);
}

/**
 * MAX Token 鎖倉展示柱。
 *
 * 平台幣是交易所最像「吉祥物」的東西。做成上鎖的展示台呼應 MAX Token
 * 的鎖倉收益，幣面直接刻 MAX 三個字 —— 這是全場最直白的品牌宣告，
 * 大廳那顆 BTC 金幣的藍色對位版本。
 */
function maxtoken(ctx: CanvasRenderingContext2D, x: number, y: number, t: number) {
  drawShadow(ctx, x + 24, y + 66, 20, 6);
  bevelBox(ctx, x + 2, y + 54, 44, 14, DARK_METAL);
  // 上層台座用品牌深藍而不是灰金屬：這是 MAX 自己的展示台，不是通用家具
  bevelBox(ctx, x + 8, y + 46, 32, 10, { fill: C.l, light: C.m, dark: C.k, line: C['0'] });
  // 鎖倉：基座正面一把掛鎖
  ctx.fillStyle = C.A;
  ctx.fillRect(x + 21, y + 58, 6, 5);
  ctx.fillStyle = C.m;
  ctx.fillRect(x + 22, y + 55, 4, 3);
  ctx.fillStyle = C['0'];
  ctx.fillRect(x + 23, y + 60, 2, 2);

  // 幣面：懸浮並極緩慢地上下呼吸
  const cx = x + 24;
  const cy = y + 22 + Math.round(Math.sin(t * 1.2) * 1);
  radialGlow(ctx, cx, cy, 18, C.A, 1);
  disc(ctx, cx, cy, 18, C['0']);
  disc(ctx, cx, cy, 17, C.m);
  disc(ctx, cx, cy, 15, C.A);
  disc(ctx, cx, cy, 11, C.l);
  glyphText(ctx, 'MAX', cx - glyphWidth('MAX', 1, 1) / 2, cy - 3, C['8'], 1, 1);

  // 從基座打上來的光束，把幣跟台座連起來
  ctx.save();
  ctx.globalAlpha = 0.14;
  ctx.fillStyle = C.A;
  ctx.beginPath();
  ctx.moveTo(x + 16, y + 46);
  ctx.lineTo(x + 32, y + 46);
  ctx.lineTo(x + 42, cy + 16);
  ctx.lineTo(x + 6, cy + 16);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

function plant(ctx: CanvasRenderingContext2D, x: number, y: number) {
  drawShadow(ctx, x + 8, y + 21, 7, 3);
  bevelBox(ctx, x + 3, y + 13, 10, 9, { fill: C.f, light: C.g, dark: C['0'], line: C['0'] });
  ctx.fillStyle = C.s;
  for (const [dx, dy, h] of [
    [8, 0, 13],
    [5, 3, 10],
    [11, 3, 10],
    [3, 6, 7],
    [13, 6, 7],
  ] as const) {
    ctx.fillRect(x + dx, y + dy, 1, h);
  }
  ctx.fillStyle = '#26935a';
  ctx.fillRect(x + 6, y + 4, 1, 9);
  ctx.fillRect(x + 10, y + 4, 1, 9);
}

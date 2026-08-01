import { TILE, view, FLAGS } from './core';
import { makeSprite, drawSprite, type Sprite } from './sprite';
import {
  FLOOR,
  FLOOR_ALT,
  PLAZA,
  PLAZA_ALT,
  MAXFLOOR,
  MAXFLOOR_ALT,
  WALL_CAP,
  WALL_FACE,
  TRIM,
  CARPET,
  GUILD,
  GUILD_ALT,
  SKIRT,
} from '../art/tiles';
import { drawProp, propFootY, propSize, propLights, ACCENT, type Light } from './props';
import { checkerPattern, glyphText, glyphWidth, GLYPH_H, phaseOf } from './shapes';
import { overlaps } from './collision';
import { drawPlayer, CHAR_W, CHAR_H, type Player } from './player';
import { drawNpc, type Npc } from './npc';
import { deadzoneRect, type Camera } from './camera';
import { PALETTE as C } from '../art/palette';
import type { Emblem, Room } from '../world/types';

const T: Record<string, Sprite> = {
  floor: makeSprite(FLOOR),
  floorAlt: makeSprite(FLOOR_ALT),
  plaza: makeSprite(PLAZA),
  plazaAlt: makeSprite(PLAZA_ALT),
  maxFloor: makeSprite(MAXFLOOR),
  maxFloorAlt: makeSprite(MAXFLOOR_ALT),
  wallCap: makeSprite(WALL_CAP),
  wallFace: makeSprite(WALL_FACE),
  trim: makeSprite(TRIM),
  carpet: makeSprite(CARPET),
  guild: makeSprite(GUILD),
  guildAlt: makeSprite(GUILD_ALT),
  skirt: makeSprite(SKIRT),
};

/** 上方牆佔兩格：頂蓋 + 立面。左右下各一格矮邊牆。 */
export const WALL_TOP_H = TILE * 2;
export const WALL_SIDE = TILE;

export function drawRoom(
  ctx: CanvasRenderingContext2D,
  room: Room,
  cam: Camera,
  t: number,
  player: Player,
  npcs: readonly Npc[],
): void {
  ctx.fillStyle = C['0'];
  ctx.fillRect(0, 0, view.w, view.h);
  ctx.save();
  ctx.translate(-Math.round(cam.x), -Math.round(cam.y));

  drawFloor(ctx, room, cam);
  drawWalls(ctx, room, cam);
  if (player.target) drawClickMarker(ctx, player.target, t, room.accent);

  // y 排序：腳底越下面的越晚畫，角色才會正確地被柱子擋住或擋住柱子
  const layers: { footY: number; draw: () => void }[] = [];
  for (const p of room.props) layers.push({ footY: propFootY(p), draw: () => drawProp(ctx, p, t + phaseOf(p.x, p.y)) });
  for (const n of npcs) layers.push({ footY: n.y, draw: () => drawNpc(ctx, n) });
  layers.push({ footY: player.y, draw: () => drawPlayer(ctx, player) });
  layers.sort((a, b) => a.footY - b.footY);
  for (const l of layers) l.draw();
  drawOcclusionGhost(ctx, room, player);
  ctx.restore();

  // 打光要蓋在所有實體之上，角色與道具才會一起受光
  drawLighting(ctx, room, cam, t, player);

  if (FLAGS.debug) {
    ctx.save();
    ctx.translate(-Math.round(cam.x), -Math.round(cam.y));
    drawDebug(ctx, room, cam, player);
    ctx.restore();
  }

  vignette(ctx);
}

// ── 打光 ────────────────────────────────────────────────────

/** 光照緩衝區。每幀重畫，最後以 multiply 疊到世界上。 */
const lightBuf = document.createElement('canvas');

function rgba(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`;
}

/** 把光色往白色混一點。純色光會把補色通道壓死，看起來像濾鏡而不是光。 */
function toward白(hex: string, t: number): string {
  const n = parseInt(hex.slice(1), 16);
  const mix = (c: number) => Math.round(c + (255 - c) * t);
  return `#${[(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c) => mix(c).toString(16).padStart(2, '0')).join('')}`;
}

/**
 * 光的衰減曲線。
 *
 * 第一版用硬邊分段想做出手繪光暈的階梯感，結果每一段有 25px 寬，
 * 放大三倍後就是一圈一圈畫在地上的同心圓。階梯感只適合小而硬的燈；
 * 這裡是大面積的環境光池，得用連續衰減，靠 backbuffer 本身的
 * 低解析度提供顆粒感就夠了。
 */
const FALLOFF: [number, number][] = [
  [0.0, 1.0],
  [0.35, 0.52],
  [0.62, 0.22],
  [0.84, 0.06],
  [1.0, 0.0],
];

/**
 * 加亮階段的強度。
 *
 * 只有 multiply 那一道的話，環境光一調亮就沒有對比可言 —— multiply 的上限
 * 是「材質原本的顏色」，光池再強也亮不過去。所以第二道用 lighter 把同一批
 * 光源加回去，讓光池真的比周圍亮，而不只是「比較不暗」。
 */
const BLOOM = 0.32;

function addLight(lc: CanvasRenderingContext2D, l: Light, cam: Camera, gain: number) {
  const sx = Math.round(l.x - cam.x);
  const sy = Math.round(l.y - cam.y);
  const color = toward白(l.color, 0.42);
  const g = lc.createRadialGradient(sx, sy, 0, sx, sy, l.r);
  for (const [pos, level] of FALLOFF) {
    g.addColorStop(pos, rgba(color, level * l.strength * gain));
  }
  lc.fillStyle = g;
  lc.fillRect(sx - l.r, sy - l.r, l.r * 2, l.r * 2);
}

/** 視野外的光源直接丟掉。兩道疊光都吃這份清單，剔除只做一次。 */
function visibleLights(room: Room, cam: Camera, player: Player): Light[] {
  const out: Light[] = [];
  const push = (l: Light) => {
    const sx = l.x - cam.x;
    const sy = l.y - cam.y;
    if (sx < -l.r || sx > view.w + l.r || sy < -l.r || sy > view.h + l.r) return;
    out.push(l);
  };
  for (const p of room.props) for (const l of propLights(p)) push(l);
  // 角色自帶一點微光：走進沒有光源的角落時不該完全看不見自己。
  // 強度刻意壓低，太強會變成「角色手上拿著燈」。
  push({ x: player.x, y: player.y - 6, r: 52, color: '#cfd8ff', strength: 0.26 });
  return out;
}

/**
 * 打光：先壓暗，再把光加回去。
 *
 * ① multiply：環境色 + 光源鋪成一張遮罩乘上世界。地板、道具、角色一起受光，
 *    不會出現「地板很暗但站在上面的人全亮」那種貼圖感。
 * ② lighter：同一批光源打在黑底上加回去，光池才會真的發亮。
 *
 * 第一版只有 ①，環境光又壓到 0.5 左右，整個畫面暗到看不清東西。
 * 兩道分工之後，環境光可以拉到 0.8 保持明亮，對比則交給 ② 負責。
 */
function drawLighting(
  ctx: CanvasRenderingContext2D,
  room: Room,
  cam: Camera,
  t: number,
  player: Player,
) {
  if (lightBuf.width !== view.w || lightBuf.height !== view.h) {
    lightBuf.width = view.w;
    lightBuf.height = view.h;
  }
  const lc = lightBuf.getContext('2d')!;
  const lights = visibleLights(room, cam, player);
  // 極輕微的呼吸，讓靜止畫面不死板；幅度刻意小到不會讓人注意到在閃
  const breath = 0.94 + 0.06 * Math.sin(t * 1.3);

  lc.globalCompositeOperation = 'source-over';
  lc.fillStyle = room.ambient;
  lc.fillRect(0, 0, view.w, view.h);
  lc.globalCompositeOperation = 'lighter';
  for (const l of lights) addLight(lc, l, cam, breath);
  ctx.globalCompositeOperation = 'multiply';
  ctx.drawImage(lightBuf, 0, 0);

  lc.globalCompositeOperation = 'source-over';
  lc.fillStyle = '#000000';
  lc.fillRect(0, 0, view.w, view.h);
  lc.globalCompositeOperation = 'lighter';
  for (const l of lights) addLight(lc, l, cam, breath * BLOOM);
  ctx.globalCompositeOperation = 'lighter';
  ctx.drawImage(lightBuf, 0, 0);

  ctx.globalCompositeOperation = 'source-over';
}

function drawFloor(ctx: CanvasRenderingContext2D, room: Room, cam: Camera) {
  // 只畫視野內的格子。整個大廳有 60x34 格，全畫是白費力氣。
  const x0 = Math.max(0, Math.floor(cam.x / TILE));
  const y0 = Math.max(0, Math.floor(cam.y / TILE));
  const x1 = Math.min(Math.ceil(room.w / TILE), Math.ceil((cam.x + view.w) / TILE) + 1);
  const y1 = Math.min(Math.ceil(room.h / TILE), Math.ceil((cam.y + view.h) / TILE) + 1);

  // 每個房間自己的地板材質。三個房間若共用同一塊地板，
  // 光的顏色再怎麼換都還是同一個空間。
  const [tileA, tileB] =
    room.floor === 'maxstone'
      ? [T.maxFloor!, T.maxFloorAlt!]
      : room.floor === 'plaza'
        ? [T.plaza!, T.plazaAlt!]
        : room.floor === 'guild'
          ? [T.guild!, T.guildAlt!]
          : [T.floor!, T.floorAlt!];
  // 嵌線的顏色就是房間的身分：大廳黃銅、MAX 品牌藍
  const inlay = room.floor === 'plaza' ? C.q : room.floor === 'maxstone' ? C.A : null;

  const rug = room.carpet;
  for (let ty = y0; ty < y1; ty++) {
    for (let tx = x0; tx < x1; tx++) {
      const px = tx * TILE;
      const py = ty * TILE;
      const onRug =
        rug !== undefined &&
        px >= rug.x && px < rug.x + rug.w && py >= rug.y && py < rug.y + rug.h;
      // 交錯兩種變體打散重複感
      const tile = onRug ? T.carpet! : (tx + ty) % 2 === 0 ? tileA : tileB;
      drawSprite(ctx, tile, px, py);
    }
  }

  // 地毯四邊各點陣化一格，邊緣才不是一條生硬的直線。
  //
  // 這裡用 checkerPattern 而不是 dither()：dither 是逐像素 fillRect，
  // 四條邊加起來每幀要跑兩萬多次；pattern 填色是 O(1)。圖樣跟著世界的
  // 平移一起走，所以點陣是鎖在地板上的，不會隨鏡頭滑動。
  if (rug) {
    ctx.save();
    ctx.globalAlpha = 0.55;
    ctx.fillStyle = checkerPattern(ctx, C.v);
    ctx.fillRect(rug.x - TILE, rug.y - TILE, rug.w + TILE * 2, TILE);
    ctx.fillRect(rug.x - TILE, rug.y + rug.h, rug.w + TILE * 2, TILE);
    ctx.fillRect(rug.x - TILE, rug.y, TILE, rug.h);
    ctx.fillRect(rug.x + rug.w, rug.y, TILE, rug.h);
    ctx.restore();
  }

  if (inlay) {
    // 每 4 格一道金屬嵌線，把地板切成 64px 的大方塊。
    // 石材配嵌線是機構空間的地板語彙 —— 一眼就知道這裡是機構，
    // 而不只是一片鋪滿的磚。
    ctx.save();
    ctx.globalAlpha = 0.4;
    ctx.fillStyle = inlay;
    for (let ty = y0; ty < y1; ty++) {
      if (ty % 4 === 0) ctx.fillRect(x0 * TILE, ty * TILE, (x1 - x0) * TILE, 1);
    }
    for (let tx = x0; tx < x1; tx++) {
      if (tx % 4 === 0) ctx.fillRect(tx * TILE, y0 * TILE, 1, (y1 - y0) * TILE);
    }
    ctx.restore();
  } else {
    // 每 8 格一道深色拼接縫，只做橫向。
    //
    // 原本是兩個軸向、每 4 格一條的青色發光線 —— 那是方格紙，會變成畫面上
    // 最搶眼卻最沒有意義的東西，而且「每個位置都一樣亮」把空間感壓平了。
    // 現在只留單軸、稀疏、深色：提供「地板是一片片鋪的」這個空間參照，
    // 但不搶走光源的戲。亮暗完全交給 drawLighting()。
    ctx.save();
    ctx.globalAlpha = 0.5;
    ctx.fillStyle = C['2'];
    for (let ty = y0; ty < y1; ty++) {
      if (ty % 8 === 0) ctx.fillRect(x0 * TILE, ty * TILE, (x1 - x0) * TILE, 1);
    }
    ctx.restore();
  }

  // 功能分區的背景色塊：鋪在地板上、徽章與道具之下。世界座標（ctx 已被相機平移）。
  if (room.zones) {
    ctx.save();
    for (const z of room.zones) {
      ctx.fillStyle = z.tint;
      ctx.fillRect(z.rect.x, z.rect.y, z.rect.w, z.rect.h);
      if (z.border) {
        ctx.globalAlpha = 0.55;
        ctx.fillStyle = z.border;
        ctx.fillRect(z.rect.x, z.rect.y, z.rect.w, 2); // 上
        ctx.fillRect(z.rect.x, z.rect.y + z.rect.h - 2, z.rect.w, 2); // 下
        ctx.fillRect(z.rect.x, z.rect.y, 2, z.rect.h); // 左
        ctx.fillRect(z.rect.x + z.rect.w - 2, z.rect.y, 2, z.rect.h); // 右
        ctx.globalAlpha = 1;
      }
    }
    ctx.restore();
  }

  if (room.emblems) for (const e of room.emblems) drawEmblem(ctx, e);
}

/**
 * 地面徽章。畫在地板上、所有立體物件之下。
 *
 * 大廳最難處理的不是道具不夠，是地面太空。一圈紋樣就能把空曠的地面收成
 * 一個「中央」，成本只有幾十個 fillRect —— 這是大型公共空間最省的構圖手法。
 */
function drawEmblem(ctx: CanvasRenderingContext2D, e: Emblem) {
  const max = e.kind === 'max';
  const hi = max ? C.A : C.p;
  const lo = max ? C.m : C.q;

  ctx.save();
  const ring = (r: number, width: number, alpha: number, color: string) => {
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.beginPath();
    ctx.arc(e.x, e.y, r, 0, Math.PI * 2);
    ctx.stroke();
  };
  ring(e.r, 2, max ? 0.55 : 0.45, lo);
  ring(e.r - 6, 1, 0.35, hi);

  if (max) {
    // MAX 情報室：徽章正中央就是品牌字樣。玩家一進場站在它上面，
    // 不需要任何說明就知道自己在哪裡。
    const s = 3;
    ctx.globalAlpha = 0.5;
    glyphText(ctx, 'MAX', Math.round(e.x - glyphWidth('MAX', s) / 2), Math.round(e.y - (GLYPH_H * s) / 2), hi, s);
  } else {
    ring(e.r * 0.4, 1, 0.3, lo);
    // 放射刻度：外環往內咬一段，做出錢幣邊齒的感覺
    ctx.globalAlpha = 0.26;
    ctx.fillStyle = lo;
    for (let i = 0; i < 24; i++) {
      const a = (i / 24) * Math.PI * 2;
      for (let k = 0; k < 5; k++) {
        const r = e.r - 12 - k;
        ctx.fillRect(Math.round(e.x + Math.cos(a) * r), Math.round(e.y + Math.sin(a) * r), 1, 1);
      }
    }
  }
  ctx.restore();
}

function drawWalls(ctx: CanvasRenderingContext2D, room: Room, cam: Camera) {
  const cols = Math.ceil(room.w / TILE);
  const rows = Math.ceil(room.h / TILE);
  const x0 = Math.max(0, Math.floor(cam.x / TILE));
  const x1 = Math.min(cols, Math.ceil((cam.x + view.w) / TILE) + 1);
  const y0 = Math.max(0, Math.floor(cam.y / TILE));
  const y1 = Math.min(rows, Math.ceil((cam.y + view.h) / TILE) + 1);

  for (let tx = x0; tx < x1; tx++) {
    drawSprite(ctx, T.wallCap!, tx * TILE, 0);
    drawSprite(ctx, T.wallFace!, tx * TILE, TILE);
    drawSprite(ctx, T.trim!, tx * TILE, (rows - 1) * TILE);
  }
  for (let ty = Math.max(y0, 2); ty < Math.min(y1, rows - 1); ty++) {
    drawSprite(ctx, T.trim!, 0, ty * TILE);
    drawSprite(ctx, T.trim!, (cols - 1) * TILE, ty * TILE);
  }

  // 牆腳收邊帶（skirt）：牆與地板交接處的 AO 過渡。
  // 讓牆「長在地板上」而不是兩張貼圖剛好擺在旁邊。
  // 上牆底部（y = WALL_TOP_H）
  for (let tx = x0; tx < x1; tx++) {
    drawSprite(ctx, T.skirt!, tx * TILE, WALL_TOP_H);
  }
}

/**
 * 點擊移動的目的地光圈。畫在世界座標系內，所以會跟著地板一起捲動。
 * 用房間的 accent 色，跟傳送門與地板接縫共用同一套視覺語言。
 */
function drawClickMarker(
  ctx: CanvasRenderingContext2D,
  target: { x: number; y: number },
  t: number,
  accent: Room['accent'],
) {
  const a = ACCENT[accent];
  const x = Math.round(target.x);
  const y = Math.round(target.y);
  // 壓扁成 0.45 的橢圓，貼合 3/4 斜俯視角的地面透視
  const ring = (rx: number) => {
    ctx.beginPath();
    ctx.ellipse(x, y, rx, rx * 0.45, 0, 0, Math.PI * 2);
    ctx.stroke();
  };

  ctx.save();
  ctx.lineWidth = 1;
  ctx.strokeStyle = a.hi;
  // 兩圈錯開半個週期往外擴散，看起來是連續的漣漪而不是一閃一閃
  for (const phase of [0, 0.5]) {
    const k = (t / 0.6 + phase) % 1;
    ctx.globalAlpha = 0.8 * (1 - k);
    ring(4 + k * 12);
  }
  // 常駐內圈：擴散的兩圈在淡出時會幾乎看不見，這圈保證任何時刻都讀得到
  ctx.globalAlpha = 0.95;
  ring(4);
  ctx.fillStyle = a.hi;
  ctx.fillRect(x - 2, y, 5, 1);
  ctx.fillRect(x, y - 2, 1, 5);
  ctx.restore();
}

/**
 * 傳送轉場的光圈。r 是可見範圍的半徑，圓外全部塗滿。
 *
 * 用單一路徑（矩形 + 反向圓弧）取「圓的外部」，比先塗滿再挖洞快。
 * 邊緣 8px 的環帶填 2x2 棋盤圖樣做出點陣感 —— 逐像素掃描在大半徑
 * 時每幀要跑數十萬次，pattern 是 O(1)。
 */
export function drawIris(
  ctx: CanvasRenderingContext2D,
  r: number,
  accent: Room['accent'],
): void {
  const a = ACCENT[accent];
  const cx = view.w / 2;
  const cy = view.h / 2;

  ctx.save();
  ctx.fillStyle = C['0'];
  ctx.beginPath();
  ctx.rect(0, 0, view.w, view.h);
  ctx.arc(cx, cy, Math.max(0, r), 0, Math.PI * 2, true);
  ctx.fill();

  if (r > 0) {
    ctx.globalAlpha = 0.85;
    ctx.fillStyle = checkerPattern(ctx, a.hi);
    ctx.beginPath();
    ctx.arc(cx, cy, r + 8, 0, Math.PI * 2);
    ctx.arc(cx, cy, r, 0, Math.PI * 2, true);
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.strokeStyle = a.hi;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.restore();
}

/** 光圈全開時的半徑：要蓋滿整個畫面的對角線一半。 */
export function irisMaxRadius(): number {
  return Math.hypot(view.w, view.h) / 2 + 10;
}

/**
 * 角色被前方道具擋住時，在上面補一層半透明的輪廓。
 *
 * 俯視角的 y 排序必然會讓角色走到高道具後面時整個消失 —— 玩家會以為
 * 自己掉出了場景。逐個把道具的碰撞盒加寬「不讓人走到後面」也能解，
 * 但那要為每個道具調參數；補一層 ghost 是通解，而且新道具自動適用。
 */
function drawOcclusionGhost(ctx: CanvasRenderingContext2D, room: Room, player: Player) {
  const body = { x: player.x - CHAR_W / 2, y: player.y - CHAR_H, w: CHAR_W, h: CHAR_H };
  for (const p of room.props) {
    if (propFootY(p) <= player.y) continue; // 畫在角色之前，擋不到
    const s = propSize(p);
    if (!overlaps(body, { x: p.x, y: p.y, w: s.w, h: s.h })) continue;
    ctx.save();
    ctx.globalAlpha = 0.4;
    drawPlayer(ctx, player);
    ctx.restore();
    return;
  }
}

/**
 * 四周壓暗一點，把注意力收到畫面中央。
 *
 * 原本 0.45 太重 —— 它跟環境光一起把畫面壓掉兩次，走到房間角落時
 * 幾乎看不到自己。收到 0.22 之後仍然有收束感，但不再吃掉可讀性。
 */
function vignette(ctx: CanvasRenderingContext2D) {
  const g = ctx.createRadialGradient(view.w / 2, view.h / 2, view.h * 0.4, view.w / 2, view.h / 2, view.h * 0.9);
  g.addColorStop(0, 'rgba(0,0,0,0)');
  g.addColorStop(1, 'rgba(0,0,0,0.22)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, view.w, view.h);
}

/**
 * ?debug=1 疊層。驗證死區鏡頭最直接的方法就是把那個框畫出來 ——
 * 角色在黃框內走動時鏡頭應該完全不動。
 */
function drawDebug(ctx: CanvasRenderingContext2D, room: Room, cam: Camera, player: Player) {
  ctx.save();
  ctx.lineWidth = 1;

  ctx.strokeStyle = 'rgba(255,79,120,0.9)';
  for (const s of room.solids) ctx.strokeRect(s.x + 0.5, s.y + 0.5, s.w - 1, s.h - 1);

  ctx.strokeStyle = 'rgba(78,232,138,0.9)';
  for (const i of room.interactables) ctx.strokeRect(i.rect.x + 0.5, i.rect.y + 0.5, i.rect.w - 1, i.rect.h - 1);

  ctx.strokeStyle = 'rgba(0,229,255,0.9)';
  for (const p of room.portals) ctx.strokeRect(p.rect.x + 0.5, p.rect.y + 0.5, p.rect.w - 1, p.rect.h - 1);

  const dz = deadzoneRect(cam);
  ctx.strokeStyle = 'rgba(255,194,61,1)';
  ctx.strokeRect(dz.x + 0.5, dz.y + 0.5, dz.w - 1, dz.h - 1);

  ctx.fillStyle = 'rgba(255,255,255,0.9)';
  ctx.fillRect(player.x - 1, player.y - 1, 2, 2);
  ctx.restore();
}

import { input } from './core';
import { hitsAny } from './collision';
import { type CharSprites, CHAR_W, CHAR_H } from '../art/sprites';
import { characterSprites, DEFAULT_CHARACTER, type CharacterId } from '../art/characters';
import { drawSprite, drawShadow } from './sprite';
import type { Rect } from '../world/types';

/**
 * 100 px/s ≈ 6.25 tile/s。原本是 72，橫跨大廳（960px）要 13 秒，
 * 走起來拖拖拉拉。這個場景沒有戰鬥也沒有精確跳躍，快一點只有好處。
 */
const SPEED = 100;
/**
 * 走路動畫換一幀所需的位移，不是時間。
 *
 * 用固定的秒數換幀，速度一改腳步就會跟地面脫節（看起來像在滑冰）。
 * 綁在位移上，不管速度怎麼調，一步永遠踏過同樣的距離。
 */
const STRIDE = 9;
/** 碰撞盒只取腳下這一塊，不是整張圖 —— 俯視角的標準做法，
 *  這樣頭才可以疊在牆前面，走位也不會覺得卡卡的。 */
const FOOT_W = 12;
const FOOT_H = 9;
/** 點擊移動的到達判定。太小會在目標點附近抖動。 */
const ARRIVE = 2;
/** 與目標的距離連續這麼久沒有縮短，就當作走不到並放棄。 */
const STALL_GIVE_UP = 0.7;

export type Dir = 'down' | 'up' | 'left' | 'right';

export type Player = {
  /** 腳底中心點，也是 y 排序與鏡頭跟隨的基準 */
  x: number;
  y: number;
  dir: Dir;
  moving: boolean;
  /** 走路動畫的累積位移，不是時間。見 STRIDE。 */
  animDist: number;
  target: { x: number; y: number } | null;
  /** 卡住偵測：距離目標最近曾到達的值，以及停滯了多久 */
  bestDist: number;
  stallT: number;
  sprites: CharSprites;
};

export function createPlayer(x: number, y: number): Player {
  return {
    x,
    y,
    dir: 'down',
    moving: false,
    animDist: 0,
    target: null,
    bestDist: Infinity,
    stallT: 0,
    sprites: characterSprites(DEFAULT_CHARACTER),
  };
}

/**
 * 換一套外觀。整包 20 張圖直接換掉，沒有中間狀態。
 *
 * `characterSprites()` 有快取，所以在設定畫面裡來回點四個角色不會每次
 * 重烘 20 張離屏 canvas —— 那正是「選角預覽」最容易變卡的地方。
 */
export function setPlayerLook(p: Player, id: CharacterId): void {
  p.sprites = characterSprites(id);
}

/** 設定點擊移動的目標，順便重置卡住偵測。 */
export function setTarget(p: Player, x: number, y: number): void {
  p.target = { x, y };
  p.bestDist = Infinity;
  p.stallT = 0;
}

export function footBox(x: number, y: number): Rect {
  return { x: x - FOOT_W / 2, y: y - FOOT_H, w: FOOT_W, h: FOOT_H };
}

export function playerBox(p: Player): Rect {
  return footBox(p.x, p.y);
}

/**
 * 每軸獨立試移：X 撞牆就只還原 X，Y 仍然照走。
 * 這就是沿牆滑動的來源 —— 斜著撞牆時會自然沿著牆面前進，
 * 而不是整個停住。凹形障礙可能卡住，但場景裡刻意不放凹形。
 */
function moveAndSlide(p: Player, dx: number, dy: number, solids: readonly Rect[]): void {
  if (dx !== 0) {
    const nx = p.x + dx;
    if (!hitsAny(footBox(nx, p.y), solids)) p.x = nx;
  }
  if (dy !== 0) {
    const ny = p.y + dy;
    if (!hitsAny(footBox(p.x, ny), solids)) p.y = ny;
  }
}

export function updatePlayer(p: Player, dt: number, solids: readonly Rect[], frozen: boolean): void {
  if (frozen) {
    p.moving = false;
    p.target = null;
    return;
  }

  let vx = 0;
  let vy = 0;
  if (input.held('KeyA') || input.held('ArrowLeft')) vx -= 1;
  if (input.held('KeyD') || input.held('ArrowRight')) vx += 1;
  if (input.held('KeyW') || input.held('ArrowUp')) vy -= 1;
  if (input.held('KeyS') || input.held('ArrowDown')) vy += 1;

  // 鍵盤一介入就立刻接管，不等點擊路徑走完
  if (vx !== 0 || vy !== 0) {
    p.target = null;
  } else if (p.target) {
    const dx = p.target.x - p.x;
    const dy = p.target.y - p.y;
    const d = Math.hypot(dx, dy);
    if (d < ARRIVE) {
      p.target = null;
    } else {
      // 目標可能根本走不到（斜角撞上凹形障礙）。沒有尋路，角色會一直
      // 頂著牆，而目的地光圈就永遠留在那裡。距離停止縮短就放棄。
      if (d < p.bestDist - 1) {
        p.bestDist = d;
        p.stallT = 0;
      } else {
        p.stallT += dt;
        if (p.stallT > STALL_GIVE_UP) {
          p.target = null;
          p.moving = false;
          p.animDist = 0;
          return;
        }
      }
      vx = dx / d;
      vy = dy / d;
    }
  }

  const len = Math.hypot(vx, vy);
  p.moving = len > 0;
  if (!p.moving) {
    p.animDist = 0;
    return;
  }

  // 正規化，否則斜走會比直走快 41%
  vx /= len;
  vy /= len;
  moveAndSlide(p, vx * SPEED * dt, vy * SPEED * dt, solids);

  // 以較大的分量決定朝向；正斜角時偏好左右，因為側面圖比較好看
  if (Math.abs(vx) >= Math.abs(vy)) p.dir = vx < 0 ? 'left' : 'right';
  else p.dir = vy < 0 ? 'up' : 'down';

  // 用「打算移動的距離」而不是「實際移動的距離」：頂著牆走的時候
  // 腳還是要動，那是原地踏步，不是靜止。
  p.animDist += SPEED * dt;
}

export function drawPlayer(ctx: CanvasRenderingContext2D, p: Player): void {
  const set =
    p.dir === 'down'
      ? p.sprites.down
      : p.dir === 'up'
        ? p.sprites.up
        : p.dir === 'right'
          ? p.sprites.side
          : p.sprites.sideLeft;
  const frame = p.moving ? Math.floor(p.animDist / STRIDE) % 4 : 4;
  drawShadow(ctx, p.x, p.y - 1, 7, 3);
  drawSprite(ctx, set[frame]!, p.x - CHAR_W / 2, p.y - CHAR_H);
}

export { CHAR_W, CHAR_H };

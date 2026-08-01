import { propSolid } from '../game/props';
import { WALL_TOP_H, WALL_SIDE } from '../game/render';
import type { Accent, Rect, Room } from '../world/types';

/**
 * 蓋房間的共用零件（規格 附錄 A · engine/kit.ts）。
 *
 * 這三個函式原本埋在 `world/rooms.ts` 裡是私有的，所以任何新 zone 都得
 * 自己重抄一份牆壁與互動範圍的算法 —— 抄歪了不會報錯，只會出現「站在
 * 道具旁邊卻按不了 E」。搬到這裡之後 rooms.ts 只是它的第一個使用者。
 * 行為與原本一模一樣，純粹是位置移動。
 */

/**
 * 四面邊界牆。上方牆佔兩格（頂蓋 + 立面）所以比較厚，
 * 其餘三面各一格。所有房間共用，不用每間重寫一次數字。
 */
export function borderSolids(w: number, h: number): Rect[] {
  return [
    { x: 0, y: 0, w, h: WALL_TOP_H },
    { x: 0, y: h - WALL_SIDE, w, h: WALL_SIDE },
    { x: 0, y: 0, w: WALL_SIDE, h },
    { x: w - WALL_SIDE, y: 0, w: WALL_SIDE, h },
  ];
}

/** 道具的碰撞盒自動併入，房間定義裡就不必手抄一份座標。 */
export function finish(room: Omit<Room, 'solids'> & { extraSolids?: Rect[] }): Room {
  const solids = [...borderSolids(room.w, room.h), ...(room.extraSolids ?? [])];
  for (const p of room.props) {
    const s = propSolid(p);
    if (s) solids.push(s);
  }
  const { extraSolids: _drop, ...rest } = room;
  return { ...rest, solids };
}

/**
 * 道具正前方的互動範圍：從道具底部往上一點、往下 34px，左右各外擴 8px。
 *
 * 玩家會很自然地站在道具下方靠著它，若互動範圍只框住道具本體，
 * 站在「看起來明明就在旁邊」的位置卻按不了 E，會讓人以為互動壞了。
 * 統一用這個函式算，就不會每個道具各自抓一組座標而寬鬆不一。
 */
export function frontOf(x: number, y: number, w: number, h: number): Rect {
  return { x: x - 8, y: y + h - 26, w: w + 16, h: 60 };
}

/**
 * accent 的執行期表。
 *
 * `ZoneParams` 是 `string | number | boolean`，所以從參數裡拿到的 accent
 * 一定要驗過才能當 Accent 用。附錄 B 規則 8 說「新增 accent 要同步四處，
 * CSS 那三處 TypeScript 守不到」—— 這一處守得到：`Record<Accent, true>`
 * 少列一個就是編譯錯誤，多列一個也是。
 */
const ACCENT_TABLE: Record<Accent, true> = {
  cyan: true,
  amber: true,
  violet: true,
  green: true,
  max: true,
};

export const ACCENTS = Object.keys(ACCENT_TABLE) as Accent[];

export const isAccent = (v: unknown): v is Accent =>
  typeof v === 'string' && Object.hasOwn(ACCENT_TABLE, v);

/** 讀 ZoneParams 裡的 accent；不是合法值就退回 fallback，永遠不會是 undefined。 */
export const accentOf = (v: unknown, fallback: Accent = 'cyan'): Accent =>
  isAccent(v) ? v : fallback;

/** 讀 ZoneParams 裡的字串／數字，型別不對就用預設值。 */
export const paramStr = (v: unknown, fallback: string): string =>
  typeof v === 'string' && v.length > 0 ? v : fallback;

export const paramNum = (v: unknown, fallback: number): number =>
  typeof v === 'number' && Number.isFinite(v) ? v : fallback;

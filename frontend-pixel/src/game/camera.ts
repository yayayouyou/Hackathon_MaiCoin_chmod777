import { view } from './core';
import { worldInset } from '../engine/viewport';

export type Camera = { x: number; y: number };

/**
 * 死區佔視野的比例：畫面正中央這塊矩形內角色怎麼動鏡頭都不動，
 * 碰到邊界才推。用比例而不是固定像素，是因為視野會隨視窗伸縮 ——
 * 固定 176x96 在 688 寬的視野裡會顯得太小。
 * 0.36 在基準的 480x270 下算出 173x97，跟原本的手感一致。
 */
export const DEADZONE_RATIO = 0.36;

const clamp = (v: number, lo: number, hi: number) => (v < lo ? lo : v > hi ? hi : v);

/**
 * 真正看得到的那塊矩形（世界座標）。
 *
 * backbuffer 是滿版的，但右側的 MAIA dock 與底部的功能條蓋掉了一部分。
 * 死區與邊界夾制都必須以這塊為準，否則角色走到右下角會**整個躲進 UI 底下**，
 * 而畫面上完全看不出他去了哪裡。
 *
 * 沒有任何 HUD 回報內縮量時它就等於整個視野，行為與加這層之前逐像素相同 ——
 * 這是刻意的，既有的鏡頭測試不能因為多了一層抽象就開始飄。
 */
export function visibleRect(cam: Camera) {
  const i = worldInset();
  return {
    x: cam.x + i.left,
    y: cam.y + i.top,
    w: Math.max(32, view.w - i.left - i.right),
    h: Math.max(32, view.h - i.top - i.bottom),
  };
}

/** 死區在世界座標中的位置，鏡頭邏輯與 debug 疊層共用同一份計算。 */
export function deadzoneRect(cam: Camera) {
  const vis = visibleRect(cam);
  const w = Math.round(vis.w * DEADZONE_RATIO);
  const h = Math.round(vis.h * DEADZONE_RATIO);
  return { x: vis.x + (vis.w - w) / 2, y: vis.y + (vis.h - h) / 2, w, h };
}

/**
 * 房間比可見區小的時候要置中，不能夾在 0。
 * 直立手機的視野可能比房間還高，夾在 0 會讓房間貼著左上角、
 * 其餘露出背景色；置中至少看起來像是刻意留白。
 *
 * `lo` / `hi` 是這條軸兩端的內縮量。要對齊世界邊界的是**可見區**的邊，
 * 不是 backbuffer 的邊 —— 所以鏡頭刻意允許超出世界外緣 `hi` 個像素，
 * 讓被 dock 蓋住的那一條剛好落在牆外，玩家看到的仍是完整貼齊的房間。
 */
function clampAxis(v: number, room: number, size: number, lo: number, hi: number): number {
  if (size - lo - hi >= room) return room / 2 - (lo + size - hi) / 2;
  return clamp(v, -lo, room - size + hi);
}

/**
 * 角色推著死區邊界走：只有超出邊界的那幾個像素會轉成鏡頭位移，
 * 所以鏡頭不會有跟隨的延遲感，也不會在角色微幅移動時晃動。
 * 最後夾在世界邊界內，走到房間角落時不會露出外面。
 */
export function updateCamera(cam: Camera, tx: number, ty: number, worldW: number, worldH: number) {
  const dz = deadzoneRect(cam);
  if (tx < dz.x) cam.x -= dz.x - tx;
  else if (tx > dz.x + dz.w) cam.x += tx - (dz.x + dz.w);
  if (ty < dz.y) cam.y -= dz.y - ty;
  else if (ty > dz.y + dz.h) cam.y += ty - (dz.y + dz.h);

  const i = worldInset();
  cam.x = clampAxis(cam.x, worldW, view.w, i.left, i.right);
  cam.y = clampAxis(cam.y, worldH, view.h, i.top, i.bottom);
}

/** 進入新場景時直接把鏡頭對到角色身上，否則會從左上角捲過去。 */
export function snapCamera(cam: Camera, tx: number, ty: number, worldW: number, worldH: number) {
  const i = worldInset();
  cam.x = clampAxis(tx - (i.left + view.w - i.right) / 2, worldW, view.w, i.left, i.right);
  cam.y = clampAxis(ty - (i.top + view.h - i.bottom) / 2, worldH, view.h, i.top, i.bottom);
}

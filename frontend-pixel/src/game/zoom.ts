import { baseScale, MAX_VIEW } from './core';
import { cssInset } from '../engine/viewport';

/**
 * 全景倍率：讓整個房間進得了視野的最大整數倍率。
 *
 * 為什麼需要它：`baseScale()` 是「填滿視窗」的倍率（1920×1080 是 4 倍，
 * 視野 480×270），但大廳是 960×512 —— 一進場只看得到房間的四分之一，
 * 完全不知道這個空間裡有什麼、有幾個出入口。走進去問東西的前提是
 * **先知道有哪些地方可以走進去**。
 *
 * 三個刻意的選擇：
 *
 * ① 用 `round` 而不是 `floor` 算貼合倍率。討論室是 768×544，
 *    1080/544 = 1.985 —— `floor` 會選 1 倍（視野 1920×1080），房間縮成
 *    畫面正中央一小塊，四周全是背景色；`round` 選 2 倍，只差 4px 的高度
 *    看不完，但那 4px 是牆壁。
 * ② 扣掉 HUD 遮住的部分再算。行情條、功能條、dock 加起來吃掉不少畫面，
 *    不扣的話「全景」會有一半躲在 UI 底下 —— 那就不叫全景了。
 * ③ 有下限，而且下限是**用房間算的、不是用倍率算的**。
 *    縮到視野超過房間 2.2 倍之後，房間會變成畫面正中央的一座孤島、
 *    四周全是背景色，那不叫全景，那叫把東西推遠。下限訂在
 *    「視野剛好是房間的 2.2 倍」的那個倍率。
 *
 *    這裡刻意不用「`baseScale() - 2`」這種寫法：它在 1920×1080 上剛好
 *    可用，但 2560×1440 的 `baseScale()` 是 5，下限就變成 3，反而把
 *    「本來放得下」的房間切掉了 —— 下限應該跟房間有關，跟螢幕多大無關。
 */
export function overviewScale(roomW: number, roomH: number): number {
  const focus = baseScale();
  const i = cssInset();
  const availW = Math.max(320, innerWidth - i.left - i.right);
  const availH = Math.max(240, innerHeight - i.top - i.bottom);

  /**
   * 容許 5% 的裁切。大廳是 960×512，1920×1080 扣掉 HUD 之後垂直方向只夠
   * 1.93 倍 —— 嚴格的 floor 會退到 1 倍（房間縮成畫面中央一小塊），
   * 但 2 倍其實只切掉最上下各 8px，而那是牆。
   */
  const fit = Math.floor(Math.min(availW / roomW, availH / roomH) / 0.95);

  // 兩軸都不准超過房間的 2.2 倍，所以取比較嚴格（比較大）的那個下限。
  const roomFloor = Math.ceil(Math.max(availW / (roomW * 2.2), availH / (roomH * 2.2)));

  /**
   * 另一個下限來自 backbuffer 的上限：倍率太小會讓
   * `ceil(innerWidth / s)` 撞到 `MAX_VIEW` 被夾住，畫布就填不滿視窗，
   * 兩側露出背景色。這個下限是硬性的 —— 露出黑邊比看不完房間難看得多。
   */
  const bufFloor = Math.ceil(Math.max(innerWidth / MAX_VIEW.w, innerHeight / MAX_VIEW.h));

  // 永遠不會比跟隨模式更近 —— 那個方向叫放大，不叫全景。
  return Math.min(focus, Math.max(1, bufFloor, roomFloor, fit));
}

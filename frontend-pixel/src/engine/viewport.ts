/**
 * 可見視野的內縮量 —— HUD 疊層與鏡頭之間唯一的橋。
 *
 * 為什麼需要它：canvas 是滿版的，右側的 MAIA dock 與底部的功能條是蓋在
 * 上面的 DOM。沒有這份內縮量，角色走到右下角就會**整個躲進 UI 底下**，
 * 而畫面上完全看不出他去了哪裡。鏡頭必須知道「真正看得到的那塊矩形」
 * 比 backbuffer 小。
 *
 * 為什麼放在 `engine/` 而不是 `hud/` 或 `game/`：
 * §3.2 的分層鐵律是 `ui/` 與 `hud/` 都不可 import `game/`。而鏡頭在
 * `game/camera.ts`、寫入端在 `hud/blocks/*`，兩邊都已經在 import
 * `engine/`（`engine/panel`、`engine/doors`、`engine/kit`），所以這裡是
 * 唯一一個兩邊都碰得到、又不製造反向相依的位置。
 *
 * ⚠ 單位有兩套，不要混：
 * - `setViewInset()` 收的是 **CSS 像素**（HUD 量自己的 `offsetWidth`）
 * - `worldInset()` 吐的是 **backbuffer 像素**（世界座標，鏡頭用的）
 *   兩者差一個整數倍率 `scale`，由 `game/core.ts` 的 resize 餵進來。
 */

export type Inset = { left: number; right: number; top: number; bottom: number };

const css: Inset = { left: 0, right: 0, top: 0, bottom: 0 };
let scale = 1;

/** 由 `core.ts` 的 resize 呼叫。倍率變了，同一塊 dock 佔掉的世界寬度就變了。 */
export function setViewScale(s: number): void {
  scale = s > 0 ? s : 1;
}

/**
 * HUD 區塊掛載 / 尺寸改變時回報自己佔掉多少 CSS 像素。
 * 只給有實際遮住畫布的區塊用 —— 半透明的膠囊、通知卡不要回報，
 * 否則鏡頭會為了一塊看得穿的東西把視野讓出來。
 */
export function setViewInset(patch: Partial<Inset>): void {
  Object.assign(css, patch);
}

/** 鏡頭要的版本：換算成 backbuffer 單位並取整，避免半像素造成鏡頭抖動。 */
export function worldInset(): Inset {
  return {
    left: Math.round(css.left / scale),
    right: Math.round(css.right / scale),
    top: Math.round(css.top / scale),
    bottom: Math.round(css.bottom / scale),
  };
}

/**
 * 原始的 CSS 像素版本。算「全景倍率」時要用它 ——
 * 那個計算的目的正是要決定倍率是多少，不能拿還沒決定的倍率去換算。
 */
export const cssInset = (): Inset => ({ ...css });

// ── 鏡頭模式 ────────────────────────────────────────────────

/**
 * 全景 / 跟隨。放在這裡而不是 `uiStore` 或 `hud/`，理由跟內縮量一樣：
 * 寫入端在 `game/`、按鈕在 `hud/`，而 `hud/` 不可 import `game/`。
 *
 * 這是「請求」與「狀態」分開的兩件事：HUD 的按鈕只送出一個切換請求
 * （遊戲迴圈下一幀來取），實際的模式由遊戲層決定後回寫。沒有這個分離，
 * HUD 就得知道房間尺寸、內縮量、整數倍率這些它不該知道的東西。
 */
export type ZoomMode = 'overview' | 'focus';

let pendingToggle = false;
let mode: ZoomMode = 'overview';
const modeSubs = new Set<(m: ZoomMode) => void>();

/** HUD 的按鈕呼叫。遊戲迴圈下一幀會取走。 */
export const requestZoomToggle = (): void => {
  pendingToggle = true;
};

/** 遊戲迴圈每幀呼叫一次，取走就清掉 —— 跟 `input.takeClick()` 同一個語意。 */
export function takeZoomToggle(): boolean {
  const v = pendingToggle;
  pendingToggle = false;
  return v;
}

export const getZoomMode = (): ZoomMode => mode;

/** 由遊戲層回寫。HUD 靠它決定按鈕上寫「全景」還是「跟隨」。 */
export function setZoomMode(next: ZoomMode): void {
  if (next === mode) return;
  mode = next;
  for (const fn of modeSubs) fn(next);
}

export function subscribeZoomMode(fn: (m: ZoomMode) => void): () => void {
  modeSubs.add(fn);
  return () => void modeSubs.delete(fn);
}

import { useSyncExternalStore } from 'react';
import { getZoomMode, requestZoomToggle, subscribeZoomMode } from '../../engine/viewport';

/**
 * 全景 / 跟隨的切換鈕。
 *
 * 它為什麼不是直接呼叫 `game/` 的函式：`hud/` 不可 import `game/`（§3.2）。
 * 按鈕只送出一個「請求」，遊戲迴圈下一幀取走，實際換倍率由遊戲層做完再
 * 把模式回寫 —— 這樣 HUD 完全不必知道房間尺寸、內縮量、整數倍率這些事。
 *
 * 掛在角色卡旁邊，因為這兩顆是同一類東西：都是「關於你自己的視角」，
 * 而不是世界裡的某個功能。
 */
export function ZoomToggle() {
  const mode = useSyncExternalStore(subscribeZoomMode, getZoomMode);
  const overview = mode === 'overview';

  return (
    <button
      className="zoombtn"
      onClick={requestZoomToggle}
      data-testid="zoom-toggle"
      title={overview ? '拉近到角色身上' : '看整個空間'}
    >
      <span className="zoombtn-glyph" aria-hidden="true">
        {overview ? '⤢' : '⤡'}
      </span>
      {overview ? '跟隨' : '全景'}
      <kbd>Z</kbd>
    </button>
  );
}

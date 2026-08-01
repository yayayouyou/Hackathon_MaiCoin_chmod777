import { defineZone } from '../../../engine/zone';
import { makeLobby } from '../../rooms';

/**
 * 中庭（大廳）。legacy 薄包裝 —— 房間內容仍在 `world/rooms.ts:makeLobby()`。
 *
 * 為什麼是 `lobby` 而不是規格附錄 A 寫的 `atrium`：`room.id === 'lobby'`
 * 被 portals / rooms / interaction 三個套件直接斷言，改名要一併動測試，
 * 而接縫 PR 的前提是「132 項不能掉」。等 D 軌把中庭門帶落地時再一起改名。
 *
 * 這個 zone 是 `getZone()` 找不到目標時的退路，所以它永遠不會被
 * validateWiring() 移除 —— 沒有中庭可以退，就只剩白畫面。
 */
export const lobby = defineZone({
  id: 'lobby',
  title: '數位廣場 · 大廳',
  accent: 'cyan',
  build: () => makeLobby(),
});

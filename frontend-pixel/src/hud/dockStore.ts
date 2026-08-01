import { useSyncExternalStore } from 'react';

/**
 * `#hud-root` 裡各個非模態疊層的開關。
 *
 * 為什麼不放進 `uiStore`：那是**凍結檔**，而且它的 `activePanel` 一被設值，
 * `game/index.ts` 的 `frozen` 就成立、世界停住、`world-labels` 淡成 0。
 * dock 要的正好相反 —— 開著的時候世界必須繼續跑，因為 agent 去查工具時
 * NPC 走去道具前的那段演出，就發生在這個時候。
 *
 * 也刻意不碰 `inputCaptured`：`core.ts` 的鍵盤處理本來就會跳過
 * INPUT / TEXTAREA（`core.ts` 裡的 tagName 判斷），所以在 dock 裡打字
 * 角色不會亂走；而設了 `inputCaptured` 反而會把世界一起凍住。
 */
type DockState = { chat: boolean };

let state: DockState = { chat: false };
const subs = new Set<() => void>();

const set = (patch: Partial<DockState>): void => {
  state = { ...state, ...patch };
  for (const fn of subs) fn();
};

export const getDock = (): DockState => state;

export function useDock(): DockState {
  return useSyncExternalStore((fn) => {
    subs.add(fn);
    return () => void subs.delete(fn);
  }, getDock);
}

export const openChatDock = (): void => set({ chat: true });
export const closeChatDock = (): void => set({ chat: false });
export const toggleChatDock = (): void => set({ chat: !state.chat });

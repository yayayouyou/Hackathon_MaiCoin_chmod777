import { useEffect } from 'react';
import { closePanel } from '../uiStore';
import { openChatDock } from '../../hud/dockStore';

/**
 * MAIA 已經不是彈窗了 —— 這個檔剩下的唯一職責是把舊入口轉過去。
 *
 * 為什麼保留 panel id 而不是直接刪掉：`agentChat` 被三個地方寫死 ——
 * MAX 情報室的互動點（`world/rooms.ts`）、`features/registry.ts`、
 * 以及 agent 回傳的 deeplink。全部改完之前，任何一個漏網就會踩到
 * `openPanel()` 的「未註冊 panel 一律 no-op」——**症狀是走過去按 E 沒反應**，
 * 而 console 只有一行紅字，現場沒有人會看 console。
 *
 * 對話的 state 在 `ui/chatStore.ts`，UI 在 `hud/blocks/AgentDock.tsx`。
 * 搬家的理由：`game/index.ts` 的 `frozen` 含 `activePanel !== null`，
 * 所以「打開 MAIA」與「世界停住」原本是同一件事 —— 而 agent 查工具的
 * 那 20–40 秒正是世界最該動起來的時候。
 */
export function AgentChat() {
  useEffect(() => {
    openChatDock();
    // 同一拍把面板收掉，`frozen` 才不會多凍一幀。
    closePanel();
  }, []);
  return null;
}

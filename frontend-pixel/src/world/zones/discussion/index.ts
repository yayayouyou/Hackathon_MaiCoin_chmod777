import { defineZone, type ZoneParams } from '../../../engine/zone';
import { accentOf, paramNum, paramStr } from '../../../engine/kit';
import { getThread } from '../../../api';
import { makeDiscussionRoom, type DiscussionSpec } from '../../rooms';

/**
 * 討論室。legacy 薄包裝 —— 房間內容仍在 `world/rooms.ts:makeDiscussionRoom()`。
 *
 * 這是「一個 zone 服務 12 個房間」的範例：房間差異全部走 `ctx.params`，
 * 不需要 12 份 zone 檔。新 zone 照抄這個形狀就好。
 */

type Spec = DiscussionSpec & { roomId: string };

/**
 * 空 params 時的樣子。
 *
 * 這一組數字原本是 `game/index.ts:swapRoom()` 那個 catch-all else 分支裡的
 * 匿名物件 —— 它同時也是「打錯 scene 名字會靜默把玩家送進 BTC 討論室」
 * 的兇手。搬到這裡之後它只剩下正當用途：討論室在沒有選房資訊時的預設值。
 */
const FALLBACK: Spec = {
  roomId: 'btc-halving',
  title: '討論室',
  accent: 'cyan',
  tag: '綜合',
  online: 0,
  sentiment: 0,
};

function specOf(params: ZoneParams): Spec {
  return {
    roomId: paramStr(params['roomId'], FALLBACK.roomId),
    title: paramStr(params['title'], FALLBACK.title),
    accent: accentOf(params['accent'], FALLBACK.accent),
    tag: paramStr(params['tag'], FALLBACK.tag),
    online: paramNum(params['online'], FALLBACK.online),
    sentiment: paramNum(params['sentiment'], FALLBACK.sentiment),
  };
}

export const discussion = defineZone({
  id: 'discussion',
  title: '討論室',
  accent: 'cyan',
  gateway: {
    label: '討論區',
    accent: 'cyan',
    pinned: { x: 272, y: 250 },
    // 這道門不是直接 travel，是先開選房面板讓玩家挑一間
    action: { type: 'panel', panel: 'roomPicker' },
  },

  build: (ctx) => makeDiscussionRoom(specOf(ctx.params)),

  /**
   * 讓 NPC 講的是這個房間真正的留言。
   *
   * 這段原本硬編在 `game/index.ts:loadRoom()` 裡，用
   * `if (room.id === 'discussion')` 當防呆 —— 那個判斷只認房間「種類」，
   * 從 A 討論室快速切到 B 討論室時，A 的留言會灌進 B 的泡泡。
   * `ifStillHere` 認的是這一次進場，切換就自動失效。
   *
   * 失敗就安靜：?failApi=1 或後端掛掉時，場景不該因為一個裝飾功能而爆掉。
   * `rt.signal` 與 `ifStillHere` 是兩層而不是二選一：signal 讓在途的請求
   * 真的被放棄（不再佔著連線），ifStillHere 擋住已經回來的結果。
   */
  onEnter: (ctx, rt) => {
    const { roomId } = specOf(ctx.params);
    getThread(roomId, rt.signal)
      .then((posts) => rt.ifStillHere(() => rt.setChatter(posts.map((p) => p.text))))
      .catch(() => {});
  },
});

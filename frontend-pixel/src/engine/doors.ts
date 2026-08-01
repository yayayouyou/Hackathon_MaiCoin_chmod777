import type { Accent, Portal, Prop, Rect } from '../world/types';

/** 觸發區頂端回推到門框頂端的距離，名牌就掛在那裡 */
export const PORTAL_PLATE_DY = 28;

export type Door = { prop: Prop; portal: Portal };

/**
 * 站在門前的互動範圍：從拱門中段一路涵蓋到門框底下 12px，像一塊門前的踏墊。
 *
 * 傳送門是場中獨立的拱門，不是嵌在牆上的門。嵌在上牆的話，出生點在
 * 房間下半部時永遠看不到它們 —— 鏡頭最多只能對準角色，而上牆離角色太遠。
 * 範圍若只框住門檻那一條，玩家停在門前一兩個像素就構不到。
 *
 * ★ 全專案唯一一份「門墊相對於門框」的公式。door() 與 world/rooms.ts
 *   都必須經過這裡，不准再手抄第二份。
 */
export const doorRect = (x: number, y: number): Rect => ({ x: x + 3, y: y + 26, w: 26, h: 38 });

/**
 * 門座標只寫一次（規格 §4.3 · engine/doors.ts）。
 *
 * 現況 `world/rooms.ts` 的 `{kind:'portal', x:272, y:250}` 與
 * `portalRect(272,250)` 是同一組座標手抄兩次，型別完全守不到 ——
 * 抄錯的症狀是「看得到門但走過去沒反應」。這個函式讓它只寫一次。
 *
 * ⚠ `target.id` 刻意是 `string` 而不是 `ZoneId`。
 *   `ZoneId = keyof typeof ZONES`，而 ZONES 由各 zone 檔組成；若這裡
 *   型別依賴 ZoneId，任何 import 了 door() 的 zone 都會讓 TS 進入
 *   「ZONES 的型別參照到自己」的循環推導（TS7022）。規格 §4.5 也是
 *   基於同一個理由把 `SceneId` 放寬成 string。
 *   目的地是否存在改由 `validateWiring()` 與 `tests/zones.mjs` 守。
 */
export function door(
  target: { id: string; accent: Accent },
  x: number,
  y: number,
  opts: {
    label: string;
    enterLabel?: string;
    params?: Record<string, string>;
    /**
     * 覆寫這道門按下去要做什麼。省略 = 直接傳送到 `target.id`。
     *
     * 討論區那道門就是靠它：後面有 12 間房，要先開一個選房面板讓人挑，
     * 而不是直接傳送。門的外觀、門墊公式、名牌全部照舊 —— 只有動作不同，
     * 所以沒有理由讓它退回去手寫一組 portal 座標。
     */
    action?: Portal['action'];
  } = { label: '' },
): Door {
  return {
    prop: { kind: 'portal', x, y, accent: target.accent },
    portal: {
      rect: doorRect(x, y),
      label: opts.label,
      ...(opts.enterLabel ? { enterLabel: opts.enterLabel } : {}),
      // 門色 = 目的地色，穿過去看到同一種藍
      accent: target.accent,
      action: opts.action ?? {
        type: 'travel',
        scene: target.id,
        ...(opts.params ? { params: opts.params } : {}),
      },
    },
  };
}

export const doorProps = (ds: Door[]): Prop[] => ds.map((d) => d.prop);
export const doorPortals = (ds: Door[]): Portal[] => ds.map((d) => d.portal);

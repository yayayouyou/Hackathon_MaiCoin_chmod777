import { frontOf } from './kit';
import { PROP_SIZE } from '../world/types';
import type { Accent, Interactable, Prop, Rect } from '../world/types';
import type { PanelId } from '../ui/panels';

/**
 * 世界的可重複零件。
 *
 * 房間定義原本是一長串手打座標，同一個東西要在兩個地方各寫一次：
 *
 *   ① 一組「圓桌 + 三張凳」在大廳出現四次，而且已經飄掉了 ——
 *      中段兩組的凳子偏移是 (-16,+14)(+70,+14)(+26,+40)，
 *      下緣兩組卻是 (-15,+12)(+71,+12)(+25,+38)。同一個視覺單元、
 *      兩套數字，沒有人會發現，因為它不會報錯。
 *   ② `frontOf(452, 186, 56, 48)` 把看板的尺寸又抄了一次，
 *      而 `PROP_SIZE.board` 早就是 `{w:56, h:48}`。
 *
 * 這個檔把「一個站點」「一組座位」變成一次呼叫就產出的**純資料**。
 *
 * ⚠ 刻意**不做註冊表**。規格 §2 已經否決過 `defineProp` 註冊表，理由是
 *   把編譯期錯誤換成執行期 throw（＝白畫面，現場 demo 最不能出的事）。
 *   這裡全部是回傳純資料的工廠函式：型別就是 `Prop[]` / `Interactable`，
 *   打錯字是紅色編譯錯誤，沒有 runtime lookup、沒有字串 id、沒有 glob。
 *   模組化拿到了，代價是零。
 *
 * `engine/doors.ts` 的 `door()` 是同一類東西（一次產出 prop + portal），
 * 這個檔是它的兄弟。
 */

/** 一個零件對房間的貢獻。組進房間時用 `assemble()`。 */
export type Part = {
  props: Prop[];
  interactables?: Interactable[];
};

/**
 * 道具實際佔的位置。
 *
 * `counter` / `screenwall` / `ticker` / `cafebar` / `trustdesk` 的寬度是
 * 自帶在 prop 上的（`PROP_SIZE` 裡那一格是 0），其餘查表。有了它，
 * 互動範圍就不必再手抄一次道具尺寸 —— 換道具種類時範圍自己跟著變。
 */
export function sizeOf(p: Prop): { w: number; h: number } {
  const base = PROP_SIZE[p.kind];
  return { w: 'w' in p ? p.w : base.w, h: base.h };
}

/**
 * 一個功能站點 = 一件道具 + 它正前方的互動範圍 + 頭上的常駐站牌。
 *
 * 搬位置只要改 `prop` 的 x/y，互動範圍與站牌自己跟著走。這正是
 * 「公告區塊是一個元件」的意思：它三個部分永遠是一起的，不會有人
 * 搬了道具卻忘記搬互動範圍。
 *
 * `rect` 是給極少數形狀不規則的站點用的逃生口（討論室的座位圈就是：
 * 玩家會被圓凳擋在圈外，範圍必須涵蓋整圈而不是道具正前方）。
 */
export function station(opts: {
  prop: Prop;
  /** `[E]` 提示的文字，動詞 ——「讀取官方消息」 */
  label: string;
  /** 常駐站牌的文字，名詞 ——「公告」 */
  sign: string;
  accent?: Accent;
  panel?: PanelId;
  run?: () => void;
  /** 自訂互動範圍。省略時取道具正前方 */
  rect?: Rect;
}): Part {
  const { w, h } = sizeOf(opts.prop);
  return {
    props: [opts.prop],
    interactables: [
      {
        rect: opts.rect ?? frontOf(opts.prop.x, opts.prop.y, w, h),
        label: opts.label,
        sign: opts.sign,
        // 牌子掛在道具頭上，不是互動範圍頭上 —— 互動範圍是從道具底部往上
        // 算的，用它當錨點牌子會蓋在道具臉上。
        signAt: { x: opts.prop.x + w / 2, y: opts.prop.y - 2 },
        accent: opts.accent,
        panel: opts.panel,
        run: opts.run,
      },
    ],
  };
}

/**
 * 盯盤座位圈：一張圓桌 + 三張凳，凳子的相對位置只寫這一次。
 *
 * 傳入的是圓桌座標，凳子跟著走。大廳四組共用這一份偏移 ——
 * 之前那 1–2px 的差異就是手抄四次的結果。
 */
export function seats(x: number, y: number): Part {
  return {
    props: [
      { kind: 'tradetable', x, y },
      { kind: 'stool', x: x - 16, y: y + 14 },
      { kind: 'stool', x: x + 70, y: y + 14 },
      { kind: 'stool', x: x + 26, y: y + 40 },
    ],
  };
}

/**
 * 把一組零件併成房間要的兩個陣列。
 *
 * props 的先後順序不影響畫面 —— `render.ts` 依腳底 y 排序，
 * 所以零件可以照「講故事的順序」寫，不必照 y 排。
 */
export function assemble(parts: readonly Part[]): {
  props: Prop[];
  interactables: Interactable[];
} {
  return {
    props: parts.flatMap((p) => p.props),
    interactables: parts.flatMap((p) => p.interactables ?? []),
  };
}

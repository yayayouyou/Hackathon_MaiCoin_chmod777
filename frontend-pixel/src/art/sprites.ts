import { makeSprite, flipH, bob, type Sprite } from '../game/sprite';
import type { Recolor } from './palette';

/**
 * 角色 16x25，Q 版比例：頭 14 行、身 5 行、腿 5 行 —— 約 1.8 頭身。
 *
 * 原本是頭 16 身 16 的標準二頭身。Q 版不是把頭放大就好，是五件事一起做
 * 才成立：
 *   1. 頭寬 14px，比肩膀（8px）還寬 —— 這是最關鍵的一項
 *   2. 眼睛 2x2 加眼白，佔臉的比例大到接近誇張
 *   3. 完全沒有脖子，頭直接坐在肩上
 *   4. 身體只有 5 行，手是兩格短袖 + 一格手掌
 *   5. 腿只有 5 行，腳掌 3px
 * 少做任何一項都只會變成「頭比較大的寫實角色」。
 *
 * 走路 4 幀之間只有腿部（最後 5 行）與 1px 的身體晃動不同，
 * 所以只手繪 3 套上半身 + 3 套腿部姿勢，其餘靠合成。
 *
 * 第 0 行刻意留空：bob() 是把整份上半身往上移一行，若第 0 行有內容，
 * 通過幀的頭頂輪廓會被裁掉一條。
 */

const BODY_ROWS = 20; // 上半身佔第 0..19 行，腿部佔第 20..24 行

// ── 上半身：正面 ────────────────────────────────────────────
const BASE_DOWN = [
  '................',
  '....00000000....',
  '..00ffffffff00..',
  '.0ffffffffffff0.',
  '.0fggggggggggf0.',
  '.0fgggggggggff0.',
  '.0ffffffffffff0.', // 瀏海下緣
  '.0ffddddddddff0.', // 額頭：兩側留鬢角，髮際線才不是一條直線
  // 眼睛是 2x2 的實心黑加左上一點眼白高光。
  // 在 2px 的尺度下畫眼白會糊成灰點，「大黑眼 + 一點高光」才讀得出來，
  // 而且那點高光就是 Q 版角色看起來有神的全部原因。
  '.0fd80ddd80ddf0.',
  '.0fd00ddd00ddf0.',
  '.0fddddddddddf0.',
  '.0fdbddddddbdf0.', // 腮紅
  '.0fddddaaddddf0.', // 嘴用最深的膚色，不用純黑 —— 純黑會變成一張苦臉
  '..0fcddddddcf0..', // 下顎陰影
  '...0cccccccc0...', // 下巴。沒有脖子，直接接肩膀
  '...0jjjjjjjj0...', // 肩
  '..0ijjjjjjjji0..', // 短袖
  '..0djjjjjjjjd0..', // 手掌
  '...0hhhhhhhh0...', // 衣襬陰影
  '...0kkkkkkkk0...', // 腰
];

// ── 上半身：背面 ────────────────────────────────────────────
const BASE_UP = [
  '................',
  '....00000000....',
  '..00ffffffff00..',
  '.0ffffffffffff0.',
  '.0fggggggggggf0.',
  '.0fggggggggggf0.',
  '.0fggggggggggf0.',
  '.0fgggggggggff0.',
  '.0fgfggggggfgf0.', // 髮流
  '.0fggggggggggf0.',
  '.0fggggggggggf0.',
  '.0ffffggggffff0.', // 光從上面來，後腦下緣壓暗
  '.0ffffffffffff0.',
  '..0ffffffffff0..',
  '...0ffffffff0...',
  '...0jjjjjjjj0...',
  '..0ijjjjjjjji0..',
  '..0djjjjjjjjd0..',
  '...0hhhhhhhh0...',
  '...0kkkkkkkk0...',
];

// ── 上半身：側面（朝右，朝左靠鏡像）────────────────────────
const BASE_SIDE = [
  '................',
  '....00000000....',
  '..00ffffffff00..',
  '.0ffffffffffff0.',
  '.0fggggggggggf0.',
  '.0fgggggggggff0.',
  '.0ffffffffffff0.',
  '.0ffffffdddddd0.', // 側臉
  '.0fffffd80dddd0.', // 側面只看得到一隻眼
  '.0fffffd00dddd0.',
  '.0fffffddddcdd0.', // 鼻樑陰影
  '.0ffffffddddcd0.',
  '.0ffffffddaadd0.', // 嘴
  '..0fffffddddc0..',
  '...0ffffcccc0...',
  '....0jjjjjj0....', // 側面的肩比正面窄
  '...0ijjjjjji0...',
  '...0djjjjjjd0...',
  '....0hhhhhh0....',
  '....0kkkkkk0....',
];

/**
 * ── 另外三套上半身 ──────────────────────────────────────────
 *
 * 只畫上半身，腿部四套共用。理由是腿只用到 `m`/`l`/`1`/`0` 四個字元
 * （褲子與鞋），換色表一改就跟著變 —— 為了換件衣服重畫六套腿是白費工。
 * 差異全部放在剪影上：及肩長髮、連帽、鴨舌帽，在 16px 寬底下這三個
 * 輪廓一眼分得出來，光靠換色分不出來。
 *
 * 帽兜與帽子刻意用上衣的 `h`/`i`/`j`，不另外開調色盤格子 ——
 * 這樣「選了紫色角色」時帽子跟著變紫，是同一套衣服而不是拼裝。
 */

// ── 上半身：及肩長髮 ────────────────────────────────────────
const BASE_LONG_DOWN = [
  '................',
  '....00000000....',
  '..00ffffffff00..',
  '.0ffffffffffff0.',
  '.0fggggggggggf0.',
  '.0fgggggggggff0.',
  '.0ffffffffffff0.',
  '.0ffddddddddff0.',
  '.0fd80ddd80ddf0.',
  '.0fd00ddd00ddf0.',
  '.0fddddddddddf0.',
  '.0fdbddddddbdf0.',
  '.0fddddaaddddf0.',
  '.0fgcddddddcgf0.', // 下顎兩側不再內縮，換成垂下來的髮束
  '.0fg0cccccc0gf0.',
  '0fg0jjjjjjjj0gf0', // 髮束垂過肩線 —— 這一格是長髮跟短髮唯一的剪影差別
  '0g0ijjjjjjjji0g0',
  '0g0djjjjjjjjd0g0',
  '.000hhhhhhhh000.', // 髮尾與衣襬一起收在這一行
  '...0kkkkkkkk0...',
];
const BASE_LONG_UP = [
  '................',
  '....00000000....',
  '..00ffffffff00..',
  '.0ffffffffffff0.',
  // 背面整片是頭髮，肩膀完全看不到 —— 這就是長髮。
  // 但整片同一個 g 會變成一塊沒有形狀的色塊（而背面正是往上走時一直看到的
  // 那一面），所以拉兩道 f 的髮流，每兩行內外交換一次，讓它有束感。
  '.0fgfggggggfgf0.',
  '.0fgfggggggfgf0.',
  '.0fggfggggfggf0.',
  '.0fggfggggfggf0.',
  '.0fgfggggggfgf0.',
  '.0fgfggggggfgf0.',
  '.0fggfggggfggf0.',
  '.0fggfggggfggf0.',
  '.0fgfggggggfgf0.',
  '.0fgfggggggfgf0.',
  '.0fggfggggfggf0.',
  '.0fggfggggfggf0.',
  '.0fgffggggffgf0.', // 髮尾開始壓暗
  '.0ffffffffffff0.',
  '..0ffffffffff0..',
  '...0kkkkkkkk0...',
];
const BASE_LONG_SIDE = [
  '................',
  '....00000000....',
  '..00ffffffff00..',
  '.0ffffffffffff0.',
  '.0fggggggggggf0.',
  '.0fgggggggggff0.',
  '.0ffffffffffff0.',
  '.0ffffffdddddd0.',
  '.0fffffd80dddd0.',
  '.0fffffd00dddd0.',
  '.0fffffddddcdd0.',
  '.0ffffffddddcd0.',
  '.0ffffffddaadd0.',
  '.0ffffffdddddc0.',
  '.0fffff0cccc0...', // 頭髮沿著後腦一路垂下去，臉那一側照常收
  '.0ffff0jjjjjj0..',
  '.0fff0ijjjjjji0.',
  '.0fff0djjjjjjd0.',
  '..0ff0hhhhhh0...',
  '...00kkkkkk0....',
];

// ── 上半身：連帽外套 ────────────────────────────────────────
const BASE_HOOD_DOWN = [
  '................',
  '....00000000....',
  '..00iiiiiiii00..',
  '.0iijjjjjjjjii0.',
  '0ijjjjjjjjjjjji0', // 帽兜比頭還寬一圈，剪影才認得出來
  '0ij00cccccc00ji0',
  '0ij0cccccccc0ji0',
  '0ij0c80cc80c0ji0',
  '0ij0c00cc00c0ji0',
  '0ij0cccccccc0ji0',
  '0ij0cbccccbc0ji0',
  '0ij0cccaaccc0ji0',
  '0ij0cbbbbbbc0ji0', // 帽兜下的臉整片降一階明度 —— 那個陰影就是「戴著帽兜」
  '.0ij0bbbbbb0ji0.',
  '..0ijjjjjjjji0..',
  '...0jjjjjjjj0...',
  '..0ijjjjjjjji0..',
  '..0djjjjjjjjd0..',
  '...0hhhhhhhh0...',
  '...0kkkkkkkk0...',
];
const BASE_HOOD_UP = [
  '................',
  '....00000000....',
  '..00iiiiiiii00..',
  '.0iijjjjjjjjii0.',
  '0ijjjjjjjjjjjji0',
  '0ijjjjjjjjjjjji0',
  '0ijjjjjjjjjjjji0',
  '0ijjjjjjjjjjjji0',
  '0ijjjjjjjjjjjji0',
  // 光從上面來，帽兜下緣壓暗 —— 跟 BASE_UP 的後腦是同一個處理。
  //
  // 整片同一個 j 是一塊沒有形狀的色塊，但**中央**加任何直線都會被讀成符號
  // （1px 的接縫像「1」，2px 的像「Ø」），靠單邊壓暗又會變成缺一角的月亮。
  // 明暗只沿著光的方向走才不會長出形狀來。
  '0iiiiijjjjiiiii0',
  '0iiiiiiiiiiiiii0',
  '0iiiiiiiiiiiiii0',
  '.0iiiiiiiiiiii0.',
  '..0iiiiiiiiii0..',
  '...0iiiiiiii0...',
  '...0jjjjjjjj0...',
  '..0ijjjjjjjji0..',
  '..0djjjjjjjjd0..',
  '...0hhhhhhhh0...',
  '...0kkkkkkkk0...',
];
const BASE_HOOD_SIDE = [
  '................',
  '....00000000....',
  '..00iiiiiiii00..',
  '.0iijjjjjjjjii0.',
  '0ijjjjjjjjjjjj00',
  '0ijjjjj0ccccccc0',
  '0ijjjjj0c80cccc0',
  '0ijjjjj0c00cccc0',
  '0ijjjjj0cccccbc0',
  '0ijjjjj0ccccccb0',
  '0ijjjjj0cccaacc0',
  '0ijjjjj0ccccccb0',
  '0ijjjjjj0bbbbb0.',
  '.0ijjjjj0bbbb0..',
  '..0ijjjjjjjj0...',
  '....0jjjjjj0....',
  '...0ijjjjjji0...',
  '...0djjjjjjd0...',
  '....0hhhhhh0....',
  '....0kkkkkk0....',
];

// ── 上半身：鴨舌帽 ──────────────────────────────────────────
const BASE_CAP_DOWN = [
  '................',
  '....00000000....',
  '..00iiiiiiii00..',
  '.0ijjjjjjjjjji0.',
  '.0ijjjjjjjjjji0.',
  '00iiiiiiiiiiii00', // 帽簷比頭寬，正面看是一條橫線
  '.0ffffffffffff0.', // 帽子底下只露一線頭髮
  '.0ffddddddddff0.',
  '.0fd80ddd80ddf0.',
  '.0fd00ddd00ddf0.',
  '.0fddddddddddf0.',
  '.0fdbddddddbdf0.',
  '.0fddddaaddddf0.',
  '..0fcddddddcf0..',
  '...0cccccccc0...',
  '...0jjjjjjjj0...',
  '..0ijjjjjjjji0..',
  '..0djjjjjjjjd0..',
  '...0hhhhhhhh0...',
  '...0kkkkkkkk0...',
];
const BASE_CAP_UP = [
  '................',
  '....00000000....',
  '..00iiiiiiii00..',
  '.0ijjjjjjjjjji0.',
  '.0ijjjj00jjjji0.', // 背面的調節扣
  '.0iiiiiiiiiiii0.', // 背面沒有帽簷，帽緣是平的
  '.0fggggggggggf0.',
  '.0fgfggggggfgf0.',
  '.0fggggggggggf0.',
  '.0fggggggggggf0.',
  '.0fggggggggggf0.',
  '.0ffffggggffff0.',
  '.0ffffffffffff0.',
  '..0ffffffffff0..',
  '...0ffffffff0...',
  '...0jjjjjjjj0...',
  '..0ijjjjjjjji0..',
  '..0djjjjjjjjd0..',
  '...0hhhhhhhh0...',
  '...0kkkkkkkk0...',
];
const BASE_CAP_SIDE = [
  '................',
  '....00000000....',
  '..00iiiiiiii00..',
  '.0ijjjjjjjjjji0.',
  '.0ijjjjjjjjjji0.',
  '.0iiiiiiiiiiiii0', // 帽簷往臉的方向多伸一格
  '.0ffffffffffff0.',
  '.0ffffffdddddd0.',
  '.0fffffd80dddd0.',
  '.0fffffd00dddd0.',
  '.0fffffddddcdd0.',
  '.0ffffffddddcd0.',
  '.0ffffffddaadd0.',
  '..0fffffddddc0..',
  '...0ffffcccc0...',
  '....0jjjjjj0....',
  '...0ijjjjjji0...',
  '...0djjjjjjd0...',
  '....0hhhhhh0....',
  '....0kkkkkk0....',
];

// ── 腿部：正面 / 背面共用。Q 版的腿短而粗，腳掌只有 3px ──────
const LEGS_N = [
  '...0mmm00mmm0...',
  '...0mmm00mmm0...',
  '...0lll00lll0...',
  '...0111001110...',
  '...0000..0000...',
];
const LEGS_A = [
  '...0mmm00mmm0...',
  '...0mmm00mmm0...',
  '...0lll001110...', // 右腿抬起
  '...0111000000...', // 左腿踩實
  '...0000.........',
];
const LEGS_B = [
  '...0mmm00mmm0...',
  '...0mmm00mmm0...',
  '...011100lll0...',
  '...0000001110...',
  '.........0000...',
];

// ── 腿部：側面（跨步幅度較大）──────────────────────────────
const LEGS_SIDE_N = [
  '....0mmmmmm0....',
  '....0mmmmmm0....',
  '....0llllll0....',
  '...011111110....',
  '...000000000....',
];
const LEGS_SIDE_A = [
  '....0mmmmmm0....',
  '...0lll00lll0...',
  '..0lll0..0lll0..',
  '..01110..0lll0..', // 後腳離地
  '..00000..01110..', // 前腳著地
];
const LEGS_SIDE_B = [
  '....0mmmmmm0....',
  '...0lll00lll0...',
  '..0lll0..0lll0..',
  '..0lll0..01110..',
  '..01110..00000..',
];

export type Facing = 'down' | 'up' | 'side';

/** 一個朝向的 5 張圖：0..3 是走路循環，4 是靜止。 */
export type FacingFrames = readonly [Sprite, Sprite, Sprite, Sprite, Sprite];

export type CharSprites = {
  down: FacingFrames;
  up: FacingFrames;
  /** 朝右 */
  side: FacingFrames;
  /** 朝左（side 的鏡像） */
  sideLeft: FacingFrames;
};

/**
 * 走路循環用「接觸 → 通過 → 接觸 → 通過」的標準四拍：
 * 跨步的兩幀身體壓低，雙腳併攏的兩幀身體抬高 1px。
 * 這是實際的步態力學，少了這 1px 就會看起來像在滑行。
 */
function buildFacing(
  base: readonly string[],
  legsN: readonly string[],
  legsA: readonly string[],
  legsB: readonly string[],
  recolor?: Recolor,
): FacingFrames {
  const contactA = makeSprite([...base, ...legsA], recolor);
  const contactB = makeSprite([...base, ...legsB], recolor);
  const passing = makeSprite([...bob(base), ...legsN], recolor);
  const idle = makeSprite([...base, ...legsN], recolor);
  return [contactA, passing, contactB, passing, idle];
}

/** 一套上半身的三個朝向。朝左由 side 鏡像而來，不另外畫。 */
type Body = { down: readonly string[]; up: readonly string[]; side: readonly string[] };

export type BodyId = 'classic' | 'long' | 'hood' | 'cap';

/**
 * 四套上半身。腿部四套共用（見上方註解）。
 *
 * 這是一張純資料表，不是註冊表 —— `BodyId` 由 key 推導，打錯字是紅色
 * 編譯錯誤，沒有執行期查表失敗這回事。
 */
export const BODIES = {
  classic: { down: BASE_DOWN, up: BASE_UP, side: BASE_SIDE },
  long: { down: BASE_LONG_DOWN, up: BASE_LONG_UP, side: BASE_LONG_SIDE },
  hood: { down: BASE_HOOD_DOWN, up: BASE_HOOD_UP, side: BASE_HOOD_SIDE },
  cap: { down: BASE_CAP_DOWN, up: BASE_CAP_UP, side: BASE_CAP_SIDE },
} as const satisfies Record<BodyId, Body>;

/**
 * `recolor` 排在前面是為了不動既有呼叫端：`npc.ts` 一直是
 * `buildCharSprites(spec.recolor)`，加上第二個參數之後那一行仍然成立。
 */
export function buildCharSprites(recolor?: Recolor, bodyId: BodyId = 'classic'): CharSprites {
  const body = BODIES[bodyId];
  const side = buildFacing(body.side, LEGS_SIDE_N, LEGS_SIDE_A, LEGS_SIDE_B, recolor);
  return {
    down: buildFacing(body.down, LEGS_N, LEGS_A, LEGS_B, recolor),
    up: buildFacing(body.up, LEGS_N, LEGS_A, LEGS_B, recolor),
    side,
    sideLeft: side.map(flipH) as unknown as FacingFrames,
  };
}

/** 給驗證腳本用：所有原始像素圖，方便一次檢查行寬與字元合法性。 */
export const RAW_ROWS = {
  BASE_DOWN,
  BASE_UP,
  BASE_SIDE,
  BASE_LONG_DOWN,
  BASE_LONG_UP,
  BASE_LONG_SIDE,
  BASE_HOOD_DOWN,
  BASE_HOOD_UP,
  BASE_HOOD_SIDE,
  BASE_CAP_DOWN,
  BASE_CAP_UP,
  BASE_CAP_SIDE,
  LEGS_N,
  LEGS_A,
  LEGS_B,
  LEGS_SIDE_N,
  LEGS_SIDE_A,
  LEGS_SIDE_B,
};

export const CHAR_W = 16;
export const CHAR_H = 25;
export { BODY_ROWS };

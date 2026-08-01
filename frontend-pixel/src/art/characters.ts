import { buildCharSprites, type BodyId, type CharSprites } from './sprites';
import type { Recolor } from './palette';
import type { Accent } from '../world/types';

/**
 * 可選角色表。
 *
 * 一個角色 = 一套上半身剪影（`art/sprites.ts` 的 `BODIES`）+ 一張換色表。
 * 兩者缺一不可：光換色的話，四個角色在 16px 寬底下只是同一個人穿不同顏色
 * 的衣服；光換剪影的話，遠看只剩一個輪廓差別。
 *
 * ⚠ 這裡**只有外觀**，沒有任何會影響 agent 行為的欄位。
 *   「分析取向」是另一件事（`boot/stances.ts`），刻意不跟外觀綁在一起 ——
 *   綁在一起就會變成「選了兜帽所以 MAIA 給你比較激進的答案」，那既不合理
 *   也不好解釋。
 *
 * 換色表只覆寫那套剪影**實際用到**的字元：兜帽整顆頭都是外套（`h`/`i`/`j`），
 * 一根頭髮都看不到，所以它沒有 `f`/`g`。多寫不會壞，但會讓人以為有作用。
 */
export type CharacterId = 'classic' | 'long' | 'hood' | 'cap';

export type Character = {
  id: CharacterId;
  /** 選單上的名字。用外觀命名，不用花名 —— 玩家要的是「認出剛剛那個」 */
  name: string;
  /** 一句話個性。純風味，不暗示任何投資行為 */
  hint: string;
  /** 卡片邊框與選中時的光暈 */
  accent: Accent;
  body: BodyId;
  recolor?: Recolor;
};

export const CHARACTERS = [
  {
    id: 'classic',
    name: '短髮',
    hint: '站在中間，什麼都想先看一眼',
    accent: 'cyan',
    body: 'classic',
    // 不換色 —— 這就是 palette.ts 原本定義的那組青色配色
  },
  {
    id: 'long',
    name: '長髮',
    hint: '習慣把線圖拉到最長的那一格',
    accent: 'violet',
    body: 'long',
    recolor: {
      f: '#2e1a3a',
      g: '#5c3a6b',
      h: '#2e1252',
      i: '#5c2ba3',
      j: '#b06cff',
      k: '#1e1830',
      l: '#33284f',
      m: '#4a3a6b',
    },
  },
  {
    id: 'hood',
    name: '兜帽',
    hint: '凌晨三點還在盯盤的那個',
    accent: 'green',
    body: 'hood',
    recolor: {
      h: '#123d1e',
      i: '#1f7a38',
      j: '#4ee88a',
      k: '#16241c',
      l: '#25402e',
      m: '#375c44',
    },
  },
  {
    id: 'cap',
    name: '鴨舌帽',
    hint: '先問手續費，再問報酬',
    accent: 'amber',
    body: 'cap',
    recolor: {
      f: '#2e1c10',
      g: '#5c3a20',
      h: '#5c3a0a',
      i: '#b87a12',
      j: '#ffc23d',
      k: '#241c14',
      l: '#3f3324',
      m: '#5c4a33',
    },
  },
] as const satisfies readonly Character[];

export const DEFAULT_CHARACTER: CharacterId = 'classic';

/**
 * 查角色。**永遠回得出一個角色**，查不到就退回預設。
 *
 * 參數型別刻意是 `string`：真正會傳進來的是 localStorage 讀出來的值，
 * 那是上一個版本的人存的，可能是任何東西。讓它 throw 或回 undefined
 * 只會換來「換了角色表之後舊使用者開起來是白畫面」。
 */
export function getCharacter(id: string): Character {
  return CHARACTERS.find((c) => c.id === id) ?? CHARACTERS[0];
}

/**
 * 角色的整套圖，建一次就留著。
 *
 * 一次 `buildCharSprites()` 會產出 20 張離屏 canvas。選角畫面四張卡、
 * 左下角色卡、世界裡的玩家都要同一套圖 —— 沒有這層快取的話，每次
 * React 重繪都在重新烘 20 張圖。
 */
const cache = new Map<CharacterId, CharSprites>();

export function characterSprites(id: CharacterId): CharSprites {
  let s = cache.get(id);
  if (!s) {
    const c = getCharacter(id);
    s = buildCharSprites(c.recolor, c.body);
    cache.set(id, s);
  }
  return s;
}

import { PALETTE, type PaletteKey, type Recolor } from '../art/palette';

export type Sprite = { canvas: HTMLCanvasElement; w: number; h: number };

/** 一張畫不出東西但存在的 sprite。驗證失敗到連寬高都不成立時的退路。 */
function blankSprite(w: number, h: number): Sprite {
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  return { canvas, w, h };
}

/**
 * 把「一個字元一個像素」的字串陣列烘成離屏 canvas。
 *
 * 驗證仍然是嚴格的（行號 + 實際內容照印），但**絕不 throw**。
 *
 * 原本這裡是「讓它安靜地畫歪不如當場炸掉」，那是單人開發時代的決定。
 * 現在 `game/render.ts:24` 在 **module 頂層**呼叫這個函式十次，而 render 被
 * game import、game 被 main.tsx import —— `art/tiles.ts` 打錯一個字元，
 * 整張 module graph 求值失敗，`main.tsx` 的 body 一行都不會跑，兩個 React
 * root 都掛不上去，結果是字面意義的白畫面。美術是獨立一條軌，現場 Live Demo
 * 也沒有第二次機會，所以改成跟 `engine/validate.ts` 同一條原則：
 * **壞掉的東西是被降級不是 throw**。非法字元當透明、行寬不齊補齊或截斷，
 * 壞掉的道具長歪一塊，總比全場白畫面好。
 *
 * 打錯字不會因此被放過：`console.error` 會讓所有「全程無執行期錯誤」的斷言
 * 紅燈，而 `tests/art.mjs` 本來就在測試階段靜態掃過每一份像素圖。
 */
export function makeSprite(rows: readonly string[], recolor?: Recolor): Sprite {
  const h = rows.length;
  if (h === 0) {
    console.error('makeSprite: 空的像素圖');
    return blankSprite(1, 1);
  }
  const w = rows[0]!.length;
  if (w === 0) {
    console.error('makeSprite: 第 0 行是空字串，寬度無法決定');
    return blankSprite(1, h);
  }

  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d')!;

  // 一份壞掉的 16x16 圖磚可以生出 256 則訊息，足以拖垮 console 與測試 runner。
  // 前兩則照印（紅燈條件不變），之後只計數。
  const QUIET_AFTER = 2;
  let problems = 0;
  const complain = (msg: string): void => {
    if (problems < QUIET_AFTER) console.error(msg);
    problems++;
  };

  for (let y = 0; y < h; y++) {
    const row = rows[y]!;
    if (row.length !== w) {
      complain(`makeSprite: 第 ${y} 行長度 ${row.length}，應為 ${w}\n  "${row}"`);
    }
    for (let x = 0; x < w; x++) {
      const ch = row[x];
      // 行太短時 ch 是 undefined —— 當透明補齊；太長的部分自然被截斷
      if (ch === undefined || ch === '.') continue;
      const color = recolor?.[ch as PaletteKey] ?? PALETTE[ch as PaletteKey];
      if (!color) {
        complain(`makeSprite: 第 ${y} 行第 ${x} 欄的字元 "${ch}" 不在調色盤中\n  "${row}"`);
        continue; // 不在調色盤中就當透明
      }
      ctx.fillStyle = color;
      ctx.fillRect(x, y, 1, 1);
    }
  }
  if (problems > QUIET_AFTER) {
    console.error(`makeSprite: 這份像素圖另有 ${problems - QUIET_AFTER} 處問題`);
  }
  return { canvas, w, h };
}

/** 水平鏡像。側面圖只畫朝右的那份，朝左靠這個生出來。 */
export function flipH(src: Sprite): Sprite {
  const canvas = document.createElement('canvas');
  canvas.width = src.w;
  canvas.height = src.h;
  const ctx = canvas.getContext('2d')!;
  ctx.translate(src.w, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(src.canvas, 0, 0);
  return { canvas, w: src.w, h: src.h };
}

/**
 * 身體上下晃動：整個上半身往上移 1px，最後一行拉長 1px 讓腰跟腿保持相連。
 * 走路時交替使用原版與晃動版，動作才不會像滑行。
 */
export function bob(base: readonly string[]): string[] {
  return [...base.slice(1), base[base.length - 1]!];
}

export function drawSprite(
  ctx: CanvasRenderingContext2D,
  sprite: Sprite,
  x: number,
  y: number,
): void {
  ctx.drawImage(sprite.canvas, Math.round(x), Math.round(y));
}

/** 腳下的橢圓軟陰影。所有會站在地上的東西都用這個，視覺語言才統一。 */
export function drawShadow(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  rx: number,
  ry: number,
): void {
  ctx.save();
  ctx.globalAlpha = 0.28;
  ctx.fillStyle = '#000000';
  ctx.beginPath();
  ctx.ellipse(Math.round(cx), Math.round(cy), rx, ry, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

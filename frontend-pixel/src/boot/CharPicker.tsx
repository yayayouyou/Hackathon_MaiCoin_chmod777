import { useEffect, useRef } from 'react';
import { CHARACTERS, characterSprites, type CharacterId } from '../art/characters';
import { CHAR_H, CHAR_W } from '../art/sprites';
import { setCharacter, useUI } from '../ui/uiStore';

/**
 * 選角。進場畫面與設定畫面共用同一個元件。
 *
 * 兩邊共用不是為了省行數，是為了讓「進場時看到的那四個」跟「之後在設定
 * 裡換的那四個」保證是同一份資料 —— 分成兩份的話，加第五個角色時一定會
 * 有一邊漏掉，而那種漏法不會報錯。
 */

/**
 * 一張角色的靜止正面圖。
 *
 * 直接畫 `art/characters.ts` 烘好的那張離屏 canvas，不另外做 DOM 版的頭像：
 * 選角預覽跟世界裡走動的角色必須是**同一張圖**，否則選的時候看到一種、
 * 進去看到另一種。
 *
 * `imageSmoothingEnabled = false` 少了會讓 16px 的圖放大後糊成一團 ——
 * 這是整個專案「整數倍放大、不做補間」那條規則在 DOM 這一側的同一件事。
 */
/** 只取頭那一段時的來源高度：第 1 行到第 15 行（第 0 行是留給 bob() 的空行）。 */
const HEAD_Y = 1;
const HEAD_H = 15;

export function CharPreview({
  id,
  scale = 3,
  head = false,
}: {
  id: CharacterId;
  scale?: number;
  /** 只畫頭。左下角色卡是 32x32 的方框，塞整個人會變成一根細長條 */
  head?: boolean;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const sh = head ? HEAD_H : CHAR_H;
  const sy = head ? HEAD_Y : 0;

  useEffect(() => {
    const cv = ref.current;
    const ctx = cv?.getContext('2d');
    if (!cv || !ctx) return;
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, cv.width, cv.height);
    // down[4] 是靜止幀（0..3 是走路循環）
    ctx.drawImage(characterSprites(id).down[4].canvas, 0, sy, CHAR_W, sh, 0, 0, cv.width, cv.height);
  }, [id, scale, sy, sh]);

  return (
    <canvas
      ref={ref}
      className="char-art"
      width={CHAR_W * scale}
      height={sh * scale}
      aria-hidden="true"
    />
  );
}

export function CharPicker({ scale = 3 }: { scale?: number }) {
  const { character } = useUI();

  return (
    <div className="char-grid" role="radiogroup" aria-label="選擇角色">
      {CHARACTERS.map((c) => (
        <button
          key={c.id}
          type="button"
          role="radio"
          aria-checked={character === c.id}
          className="char-card"
          data-accent={c.accent}
          data-id={c.id}
          onClick={() => setCharacter(c.id)}
        >
          <CharPreview id={c.id} scale={scale} />
          <b>{c.name}</b>
          <span>{c.hint}</span>
        </button>
      ))}
    </div>
  );
}

import { openPage, gameState } from './lib/harness.mjs';

const SIZES = [
  [1920, 1080, '1080p'],
  [1440, 900, '桌機'],
  [1180, 700, '小筆電'],
  [900, 600, '窄視窗'],
  [1366, 768, '筆電'],
  [430, 820, '手機直立'],
];

/** run.mjs 掃描 tests/*.mjs，套件名字從這裡讀（省略就用檔名）。 */
export const title = '畫布尺寸';

/**
 * 動態解析度：畫布要剛好填滿視窗，且縮放倍率必須是整數。
 *
 * 非整數倍會讓一個來源像素跨到兩個螢幕像素上，即使關掉平滑化也會出現
 * 寬度不一的鋸齒 —— 那是像素風最不能妥協的地方。
 */
export default async function screen({ browser, ok }) {
  for (const [width, height, tag] of SIZES) {
    const page = await openPage(browser, { viewport: { width, height } });
    const g = await gameState(page);
    const m = await page.evaluate(() => {
      const r = document.getElementById('screen').getBoundingClientRect();
      return {
        cw: Math.round(r.width),
        ch: Math.round(r.height),
        hOverflow: document.documentElement.scrollWidth > innerWidth,
      };
    });

    // ceil 會讓畫布最多多出 scale-1 px，由 #stage 的 overflow:hidden 裁掉。
    // 這是刻意的：寧可多一點被裁，也不要少一點露出背景。
    ok(
      `${tag} ${width}x${height} 畫布填滿視窗`,
      m.cw >= width && m.ch >= height && m.cw - width < g.view.scale && m.ch - height < g.view.scale,
      `畫布 ${m.cw}x${m.ch}`,
    );
    ok(`${tag} 無橫向溢出`, !m.hOverflow);
    ok(
      `${tag} 倍率為整數`,
      Number.isInteger(g.view.scale),
      `${g.view.scale}x → backbuffer ${g.view.w}x${g.view.h}`,
    );
    ok(`${tag} 無執行期錯誤`, page.collectedErrors.length === 0, page.collectedErrors[0] ?? '');
    await page.close();
  }
}

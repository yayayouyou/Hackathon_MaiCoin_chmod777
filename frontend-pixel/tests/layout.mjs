import { openPage, gameState, walkTo, waitForPanel, settle } from './lib/harness.mjs';

const SIZES = [
  [1440, 900, '桌機'],
  [1400, 560, '寬而矮'],
  [900, 600, '窄視窗'],
  [760, 700, '中窄'],
  [430, 820, '手機'],
];

/** run.mjs 掃描 tests/*.mjs，套件名字從這裡讀（省略就用檔名）。 */
export const title = '面板版面';

/**
 * 彈窗的 RWD。
 *
 * 這裡的重點是兩個曾經真的壞掉的東西：
 * 1. `.panel { max-height: 100% }` 在 place-items:center 的 grid 裡會被當成
 *    none，面板長到視窗外而且內層永遠不出現捲軸 —— 所以驗 bottom <= 視窗高。
 * 2. `min-height: 0` 用在 grid 項目上會讓列比內容矮，下一區塊疊上來 ——
 *    所以驗三個欄位的矩形互不重疊。
 */
export default async function layout({ browser, ok }) {
  for (const [width, height, tag] of SIZES) {
    // 刻意不帶 ?debug=1（這一段不讀 __game()，順便驗一次沒有 debug 疊層的路徑），
    // 但 ?fast=1 一定要帶：掛著的 HUD 輪詢會讓 networkidle 永不觸發。
    const page = await openPage(browser, { query: '?fast=1', viewport: { width, height } });
    await page.keyboard.press('KeyI');
    await page.waitForTimeout(1300);

    const m = await page.evaluate(() => {
      const q = (s) => document.querySelector(s);
      const panel = q('.panel');
      const body = q('.panel-body');
      const trade = q('.trade');
      const r = panel.getBoundingClientRect();
      const cols = [...document.querySelectorAll('.trade > .col')].map((c) => c.getBoundingClientRect());
      let overlap = false;
      for (let i = 0; i < cols.length; i++) {
        for (let j = i + 1; j < cols.length; j++) {
          const a = cols[i];
          const b = cols[j];
          if (a.left < b.right - 1 && a.right > b.left + 1 && a.top < b.bottom - 1 && a.bottom > b.top + 1) {
            overlap = true;
          }
        }
      }
      return {
        top: Math.round(r.top),
        bottom: Math.round(r.bottom),
        tradeOverflow: trade ? trade.scrollWidth > trade.clientWidth + 1 : false,
        tradeCols: trade ? getComputedStyle(trade).gridTemplateColumns.split(' ').length : 0,
        hOverflow: document.documentElement.scrollWidth > innerWidth,
        bodyCanScroll: getComputedStyle(body).overflowY === 'auto',
        overlap,
      };
    });

    ok(`${tag} 面板不超出視窗`, m.bottom <= height && m.top >= 0, `top=${m.top} bottom=${m.bottom} / ${height}`);
    ok(`${tag} 交易面板不橫向溢出`, !m.tradeOverflow, `${m.tradeCols} 欄`);
    ok(`${tag} 頁面無橫向捲動`, !m.hOverflow);
    ok(`${tag} 三個區塊互不重疊`, !m.overlap);
    ok(`${tag} 面板內容可捲動`, m.bodyCanScroll);
    await page.close();
  }

  // 討論串：內部捲動 + 輸入框固定在底部，在矮視窗下也要成立
  const page = await openPage(browser, { viewport: { width: 900, height: 560 } });
  // 走到討論區門前再按 E 開選房面板（點擊不再自動觸發，一律走近按鍵）
  await walkTo(page, 288, 300);
  await page.keyboard.press('KeyE');
  await waitForPanel(page);
  await page.locator('.rank-row').first().click();
  // 等轉場真的結束再走位。固定 waitForTimeout 在討論串改接後端之後不夠了 ——
  // 面板會先以 loading 狀態開起來，.thread 與 .composer 都還沒 render，
  // 這時量到的是「有面板但沒有內容」，看起來像版面壞掉。
  for (let i = 0; i < 60 && (await gameState(page)).room.id !== 'discussion'; i++) {
    await page.waitForTimeout(100);
  }
  await settle(page);
  await walkTo(page, 578, 292);
  await page.keyboard.press('KeyE');
  await waitForPanel(page);
  for (let i = 0; i < 40 && !(await page.locator('.thread').count()); i++) {
    await page.waitForTimeout(100);
  }

  const m = await page.evaluate(() => {
    const thread = document.querySelector('.thread');
    const composer = document.querySelector('.composer');
    const panel = document.querySelector('.panel');
    return {
      // 不驗「現在有沒有捲軸」—— 貼文改由後端提供之後，那取決於這間房剛好
      // 有幾則留言。要守的是版面規則：討論串自己捲，不是整個面板被撐長。
      threadScrolls: thread ? ['auto', 'scroll'].includes(getComputedStyle(thread).overflowY) : null,
      composerBottom: composer ? Math.round(composer.getBoundingClientRect().bottom) : null,
      panelBottom: Math.round(panel.getBoundingClientRect().bottom),
    };
  });
  ok('討論串自己捲而不是撐長面板', m.threadScrolls === true);
  ok('輸入框固定在面板內', m.composerBottom !== null && m.composerBottom <= m.panelBottom,
    `composer=${m.composerBottom} panel=${m.panelBottom}`);
  ok('面板不超出 560 高的視窗', m.panelBottom <= 560, `bottom=${m.panelBottom}`);
  await page.close();
}

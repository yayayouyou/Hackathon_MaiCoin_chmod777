import { devices } from 'playwright';
import { openPage, gameState, tapWorld, waitForPanel } from './lib/harness.mjs';

/** run.mjs 掃描 tests/*.mjs，套件名字從這裡讀（省略就用檔名）。 */
export const title = '觸控';

/**
 * 觸控裝置。手機沒有 WASD 也沒有 E 鍵，所以要驗兩條替代路徑：
 * 點擊地面移動、點擊互動點走過去後再點浮動提示觸發。
 */
export default async function touch({ browser, ok }) {
  const page = await openPage(browser, { device: { ...devices['iPhone 14 Pro'], hasTouch: true, isMobile: true } });
  const g = await gameState(page);

  ok('被辨識為 coarse pointer', await page.evaluate(() => matchMedia('(pointer: coarse)').matches));
  ok('提示文字改成觸控說明', (await page.locator('.hud-hint').textContent()).includes('點擊'),
    await page.locator('.hud-hint').textContent());
  ok('畫布填滿手機視窗',
    await page.evaluate(() => {
      const r = document.getElementById('screen').getBoundingClientRect();
      return r.width >= innerWidth && r.height >= innerHeight;
    }),
    `視野 ${g.view.w}x${g.view.h} @${g.view.scale}x`);
  // 直立手機的視野可能比房間還高，這時鏡頭要置中（負值）而不是夾在 0
  ok('房間比視野小時鏡頭置中', g.cam.y < 0 || g.room.h > g.view.h,
    `cam.y=${g.cam.y.toFixed(0)} room.h=${g.room.h} view.h=${g.view.h}`);

  // 目標要離出生點夠遠。點在幾十像素外的話 350ms 內就走到了，
  // target 被清掉，這條會變成偽陰性 —— 測的是「有沒有產生目標」，
  // 不是「走得多快」。(620,400) 是一片淨空地板，路上沒有障礙。
  await tapWorld(page, 620, 400);
  await page.waitForTimeout(350);
  ok('觸控點擊會產生移動目標', (await gameState(page)).target !== null);

  // 觸控沒有 E 鍵：點互動點會走過去並冒出浮動提示，再點提示才開。
  // 提示有上下浮動的動畫，Playwright 的穩定性檢查會一直等它停下來，
  // 所以直接派發事件；真人點擊不受影響。
  // (648,300) 落在東翼現貨交易台的互動範圍 (592,270,112,60) 裡
  await tapWorld(page, 648, 300);
  for (let i = 0; i < 30 && !(await page.locator('.world-prompt').isVisible()); i++) {
    await page.waitForTimeout(200);
  }
  ok('觸控點擊互動點會走過去並顯示提示', await page.locator('.world-prompt').isVisible());
  await page.locator('.world-prompt').dispatchEvent('pointerdown');
  ok('點提示可開啟面板', await waitForPanel(page));
  ok('手機上面板不超出視窗',
    await page.evaluate(() => {
      const r = document.querySelector('.panel').getBoundingClientRect();
      return r.bottom <= innerHeight + 1 && r.top >= -1;
    }));

  await page.keyboard.press('Escape');
  await page.waitForTimeout(700);
  ok('提示按鈕可接收觸控事件',
    await page.evaluate(() => getComputedStyle(document.querySelector('.world-prompt')).pointerEvents === 'auto'));
  // 觸控裝置上畫鍵帽只會誤導，改成可點的箭頭
  ok('提示不再顯示 E 鍵帽', !(await page.locator('.world-prompt b').textContent()).includes('E'),
    await page.locator('.world-prompt b').textContent());
  ok('全程無執行期錯誤', page.collectedErrors.length === 0, page.collectedErrors[0] ?? '');
  await page.close();
}

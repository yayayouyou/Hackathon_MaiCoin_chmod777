import { openPage, gameState, gotoWorld, waitForPanel, BASE } from './lib/harness.mjs';

/** run.mjs 掃描 tests/*.mjs，套件名字從這裡讀（省略就用檔名）。 */
export const title = '狀態與持久化';

/** 錯誤狀態、金鑰不落地、收藏持久化。 */
export default async function state({ browser, ok }) {
  // ── ?failApi=1 時每個面板都要有可讀的錯誤，不能是白畫面 ──
  {
    const page = await openPage(browser, { query: '?failApi=1&fast=1' });
    await page.keyboard.press('KeyI');
    await page.waitForTimeout(1300);
    const text = await page.locator('.trade').textContent();
    ok('failApi 時行情顯示錯誤而非白畫面', text.includes('連線失敗'),
      text.slice(0, 30).replace(/\s+/g, ' '));
    await page.close();
  }

  // ── 金鑰只存記憶體、收藏存 localStorage ──
  {
    const page = await openPage(browser);
    await page.evaluate(() => localStorage.clear());
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForTimeout(900);

    await page.keyboard.press('KeyI');
    await page.waitForTimeout(800);
    await page.locator('input[type=text]').nth(1).fill('demo-access');
    await page.locator('input[type=password]').fill('demo-secret');
    // exact 不可省：HUD 那張角色卡的無障礙名稱含「○ 未連接 · 示範帳戶」，
    // 而 getByRole 的 name 預設是子字串比對 —— 少了 exact 會同時命中兩顆
    // 按鈕，Playwright 的 strict mode 直接丟例外，整支套件中斷。
    await page.getByRole('button', { name: '連接', exact: true }).click();
    await page.waitForTimeout(1000);
    ok('填入金鑰後持倉解鎖', await page.locator('.pos-table').isVisible());
    ok('金鑰沒有寫進 localStorage',
      await page.evaluate(() => !JSON.stringify(localStorage).toLowerCase().includes('demo-secret')));

    await page.locator('.tabs button', { hasText: '收藏' }).click();
    await page.waitForTimeout(700);
    ok('未收藏時顯示空狀態', (await page.locator('.empty').textContent()).includes('還沒有收藏'));
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);

    // 點在排行看板的互動範圍內：會走過去，站定後按 E 才開
    // （世界裡一律走近再按鍵，滑鼠點擊不再自動觸發）
    await gotoWorld(page, 480, 240);
    await page.keyboard.press('KeyE');
    ok('排行看板可開啟', await waitForPanel(page));
    await page.locator('.star').first().click();
    await page.waitForTimeout(500);

    const nickname = await page.evaluate(() => localStorage.getItem('goodui.nickname'));
    const favorites = await page.evaluate(() => localStorage.getItem('goodui.favorites'));
    ok('收藏寫入 localStorage', favorites && JSON.parse(favorites).length === 1, favorites);
    ok('預設暱稱有寫入 localStorage', !!nickname, String(nickname));

    await page.goto(`${BASE}/?debug=1&fast=1`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    await page.keyboard.press('KeyI');
    await page.waitForTimeout(900);
    ok('重整後金鑰清空、回到未連接', await page.locator('.gate-mask').first().isVisible());
    await page.locator('.tabs button', { hasText: '收藏' }).click();
    await page.waitForTimeout(900);
    ok('重整後收藏還在', (await page.locator('.rank-row').count()) === 1,
      `${await page.locator('.rank-row').count()} 筆`);
    ok('重整後暱稱不變', (await page.evaluate(() => localStorage.getItem('goodui.nickname'))) === nickname);
    await page.close();
  }

  // ── 視窗改變時仍維持整數倍且填滿 ──
  {
    const page = await openPage(browser);
    const rows = [];
    for (const [width, height] of [[1440, 900], [1000, 700], [900, 500], [700, 420]]) {
      await page.setViewportSize({ width, height });
      await page.waitForTimeout(400);
      const g = await gameState(page);
      const css = await page.evaluate(() => parseInt(document.getElementById('screen').style.width, 10));
      rows.push({ scale: g.view.scale, css, vw: g.view.w, win: width });
    }
    ok('改變視窗尺寸仍維持整數倍且填滿',
      rows.every((r) => Number.isInteger(r.scale) && r.css === r.vw * r.scale && r.css >= r.win),
      rows.map((r) => `${r.scale}x/${r.vw}px`).join(', '));
    await page.close();
  }
}

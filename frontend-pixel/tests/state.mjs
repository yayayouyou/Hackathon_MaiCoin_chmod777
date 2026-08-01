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

  // ── 金鑰完全不在瀏覽器、收藏存 localStorage ──
  //
  // ⚠ 這一段原本是「在面板裡填 access/secret → 持倉解鎖 → 檢查金鑰沒進
  //   localStorage」。金鑰改由後端 .env 保管（HMAC 簽章在伺服器端完成）之後，
  //   那個輸入框已經移除，所以斷言換成**更強**的版本：不是「金鑰沒有被寫進
  //   localStorage」，而是「前端根本沒有地方可以輸入金鑰」。
  //   收藏與暱稱的持久化斷言原封不動 —— 它們跟金鑰無關。
  {
    const page = await openPage(browser);
    await page.evaluate(() => localStorage.clear());
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForTimeout(900);

    await page.keyboard.press('KeyI');
    await page.waitForTimeout(800);
    ok('前端沒有任何密碼輸入框（金鑰不經手瀏覽器）',
      (await page.locator('input[type=password]').count()) === 0);
    ok('不需要前端金鑰就能顯示餘額', await page.locator('.pos-table').first().isVisible());
    ok('localStorage 沒有金鑰痕跡',
      await page.evaluate(() => !/secret|apikey|api_key/i.test(JSON.stringify(localStorage))));

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
    ok('重整後前端仍然沒有金鑰輸入框',
      (await page.locator('input[type=password]').count()) === 0);
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

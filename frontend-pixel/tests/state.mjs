import { openPage, gameState, gotoWorld, waitForPanel, BASE } from './lib/harness.mjs';

/** run.mjs 掃描 tests/*.mjs，套件名字從這裡讀（省略就用檔名）。 */
export const title = '狀態與持久化';

/** 錯誤狀態、金鑰不進瀏覽器、收藏持久化。 */
export default async function state({ browser, ok }) {
  // ── 行情讀不到時要有可讀的錯誤，不能是白畫面 ──
  //
  // 行情已改接後端 /api/tickers。這條斷言要在「後端有起」與「後端沒起」兩種
  // 環境下都成立，所以失敗必須由 ?failApi=1 強制製造 —— 靠「本機剛好沒開後端」
  // 來讓它綠燈，等於後端一起來這條就失效。
  {
    const page = await openPage(browser, { query: '?failApi=1&fast=1' });
    await page.keyboard.press('KeyI');
    await page.waitForTimeout(1300);
    const text = await page.locator('.trade').textContent();
    ok('行情讀不到時顯示錯誤而非白畫面', text.includes('連線失敗'),
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
    // 餘額在交易面板第三欄的「餘額」分頁（第三欄預設顯示價格圖）
    await page.locator('.trade > .col').nth(2).locator('.tabs button', { hasText: '餘額' }).click();
    await page.waitForTimeout(600);
    ok('不需要前端金鑰就能顯示餘額',
      (await page.locator('.trade > .col').nth(2).innerText()).includes('TWD'));
    ok('localStorage 沒有金鑰痕跡',
      await page.evaluate(() => !/secret|apikey|api_key/i.test(JSON.stringify(localStorage))));

    await page.locator('.tabs button', { hasText: '收藏' }).click();
    await page.waitForTimeout(700);
    ok('未收藏時顯示空狀態', (await page.locator('.empty').textContent()).includes('還沒有收藏'));
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);

    /**
     * 收藏的來源是選房面板的星號。
     *
     * 這裡原本走 (480,240) —— 那是「大廳的排行看板」，但排行榜早就搬進
     * 交易者公會了，那個座標在大廳只會撞到現貨交易台，而交易面板裡
     * 沒有 `.star`，於是這支套件從那次搬家之後就一直在同一行斷掉。
     * 改走討論區拱門的選房面板：一樣是收藏房間、一樣寫進 localStorage，
     * 而且門的座標寫在 zone 的 gateway.pinned 裡，不會再被排版變動帶走。
     */
    await gotoWorld(page, 288, 300);
    await page.keyboard.press('KeyE');
    ok('選房面板可開啟', await waitForPanel(page));
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

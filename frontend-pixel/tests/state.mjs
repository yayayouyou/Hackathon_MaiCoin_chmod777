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

  // ── 不向使用者索取金鑰、帳戶失敗要有提示、收藏存 localStorage ──
  {
    const page = await openPage(browser);
    await page.evaluate(() => localStorage.clear());
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForTimeout(900);

    await page.keyboard.press('KeyI');
    await page.waitForTimeout(800);
    // 簽名在後端做，瀏覽器不該持有交易所金鑰 —— 這個面板不能再出現密碼欄位。
    ok('不再向使用者索取交易所金鑰',
      (await page.locator('.trade input[type=password]').count()) === 0);
    // exact 不可省：HUD 那張角色卡的無障礙名稱含「○ 未連接」，而 getByRole 的
    // name 預設是子字串比對 —— 少了 exact 會同時命中兩顆按鈕，Playwright 的
    // strict mode 直接丟例外，整支套件中斷。
    await page.getByRole('button', { name: '連接', exact: true }).click();
    await page.waitForTimeout(1200);
    // 測試環境沒有後端，帳戶必定讀不到。要看到的是可讀的提示，
    // 不是白畫面，更不是一張憑空生出來的持倉表。
    const account = await page.locator('.trade .col').last().textContent();
    ok('後端讀不到帳戶時顯示可讀提示', /連線失敗|無法|尚未|請先登入/.test(account),
      account.slice(0, 40).replace(/\s+/g, ' '));

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
    ok('重整後回到未連接', await page.locator('.gate-mask').first().isVisible());
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

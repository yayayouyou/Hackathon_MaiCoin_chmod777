import {
  openPage,
  gameState,
  clickWorld,
  gotoWorld,
  waitForPanel,
  panelVisible,
  promptText,
} from './lib/harness.mjs';

/** run.mjs 掃描 tests/*.mjs，套件名字從這裡讀（省略就用檔名）。 */
export const title = '互動回饋';

/** 點擊光圈、卡住自動放棄、點擊物件自動前往、傳送光圈轉場。 */
export default async function interaction({ browser, ok }) {
  const page = await openPage(browser);

  // ── 目的地光圈 ──
  await clickWorld(page, 700, 430);
  await page.waitForTimeout(250);
  const during = await gameState(page);
  ok('點擊後出現目的地光圈', during.target !== null,
    during.target ? `target=(${during.target.x.toFixed(0)},${during.target.y.toFixed(0)})` : 'null');

  for (let i = 0; i < 40 && (await gameState(page)).target; i++) await page.waitForTimeout(200);
  ok('抵達後光圈消失', (await gameState(page)).target === null);

  await clickWorld(page, 300, 430);
  await page.waitForTimeout(250);
  ok('再次點擊出現光圈', (await gameState(page)).target !== null);
  await page.keyboard.down('KeyD');
  await page.waitForTimeout(200);
  await page.keyboard.up('KeyD');
  ok('WASD 接管後光圈消失', (await gameState(page)).target === null);

  // 走不到的目標（柱子後方）不能讓光圈永遠留著 —— 沒有尋路，角色會頂著牆
  await clickWorld(page, 852, 130);
  await page.waitForTimeout(400);
  const stuckStart = (await gameState(page)).target !== null;
  await page.waitForTimeout(9000);
  ok('走不到的目標會自動放棄', stuckStart && (await gameState(page)).target === null,
    `起始有目標=${stuckStart}`);
  await page.close();

  // ── 點擊互動點會自己走過去，但**不會**自動開啟 ──
  //
  // 世界裡只有一條規則：走近，然後按鍵。原本用滑鼠點會自動開、用 WASD
  // 靠近要按 E，同一個目標兩套行為。觸控裝置沒有 E 鍵，改點浮動提示
  // （下面那幾條驗的就是它）。
  {
    const p2 = await openPage(browser);
    await clickWorld(p2, 480, 240);
    for (let i = 0; i < 30 && !(await promptText(p2)); i++) await p2.waitForTimeout(200);
    ok('點擊互動點會走過去但不自動開啟',
      (await promptText(p2)) !== null && !(await panelVisible(p2)),
      `提示=${await promptText(p2)}`);

    // 浮動提示本身就是按鈕。它有上下浮動的動畫，Playwright 的穩定性檢查
    // 會一直等它停下來，所以直接派發事件；真人點擊不受影響。
    ok('浮動提示可見', (await promptText(p2)) !== null, await promptText(p2));
    ok('提示可接收指標事件',
      await p2.evaluate(() => getComputedStyle(document.querySelector('.world-prompt')).pointerEvents === 'auto'));
    await p2.locator('.world-prompt').dispatchEvent('pointerdown');
    await p2.waitForTimeout(800);
    ok('點擊浮動提示即開啟面板', await panelVisible(p2));
    await p2.keyboard.press('Escape');
    await p2.waitForTimeout(500);

    // ── 傳送光圈轉場 ──
    // 走到討論區門前按 E 開選房面板，挑一間進去。選房那一下是直接呼叫
    // travel()，不經過走路，所以這段驗的純粹是轉場狀態機本身。
    await gotoWorld(p2, 288, 300);
    await p2.keyboard.press('KeyE');
    await waitForPanel(p2);
    await p2.locator('.rank-row').first().click();

    let sawOut = false;
    let sawIn = false;
    let changedAt = -1;
    const t0 = Date.now();
    for (let i = 0; i < 150; i++) {
      const s = await gameState(p2);
      if (s.transition === 'out') sawOut = true;
      if (s.transition === 'in') sawIn = true;
      if (s.room.id === 'discussion' && changedAt < 0) changedAt = Date.now() - t0;
      if (s.room.id === 'discussion' && s.transition === null && sawIn) break;
      await p2.waitForTimeout(40);
    }
    ok('轉場有收合階段', sawOut);
    ok('轉場有張開階段', sawIn);
    ok('換房間發生在轉場中段而非瞬間', changedAt > 0, `${changedAt}ms`);
    const fin = await gameState(p2);
    ok('轉場結束後回到可操作狀態', fin.transition === null && fin.room.id === 'discussion');
    ok('全程無執行期錯誤', p2.collectedErrors.length === 0, p2.collectedErrors[0] ?? '');
    await p2.close();
  }
}

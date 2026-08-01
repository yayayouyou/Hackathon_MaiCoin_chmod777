import { openPage, gameState, settle, promptText } from './lib/harness.mjs';

/** run.mjs 掃描 tests/*.mjs，套件名字從這裡讀（省略就用檔名）。 */
export const title = '功能條導引';

/**
 * 底部功能條的「傳送 → 走過去 → 站定顯示 [E]」。
 *
 * 這支存在的理由：在它之前，功能條**完全沒有測試覆蓋**（全 tests/ 沒有
 * 任何一支點過 `.fslot`），而它其實壞掉很久了 —— `onArrive` 在 iris 轉場
 * 還沒結束時就被呼叫，`walkTo()` 設下的 `player.target` 在下一幀被
 * `updatePlayer(..., frozen)` 清掉，角色從頭到尾停在出生點。
 *
 * 症狀在畫面上是「房間換了、人沒動、什麼都沒開」，但沒有任何斷言會紅。
 *
 * ⚠ 必須測**跨房**的路徑：同房間內的 goto 不經過轉場，踩不到那個 race。
 *   FEATURES 的落點現在全部在大廳，所以要先跑去討論室再點功能條。
 */
export default async function featurebar({ browser, ok }) {
  const page = await openPage(browser);

  // 先進討論室，製造跨房情境
  await page.locator('.fslot', { hasText: '討論區' }).click();
  for (let i = 0; i < 60 && !(await page.locator('.panel').isVisible()); i++) {
    await page.waitForTimeout(100);
  }
  await page.keyboard.press('KeyE');
  for (let i = 0; i < 40 && !(await page.locator('.panel').isVisible()); i++) {
    await page.waitForTimeout(100);
  }
  await page.locator('.rank-row').first().click();
  for (let i = 0; i < 80; i++) {
    await page.waitForTimeout(100);
    if ((await gameState(page)).room.id === 'discussion') break;
  }
  ok('先進討論室製造跨房情境', (await gameState(page)).room.id === 'discussion');
  await settle(page);

  // ── 正題：從討論室點功能條「官方消息」，落點在大廳的 MAX 資訊角 ──
  await page.locator('.fslot', { hasText: '官方消息' }).click();
  for (let i = 0; i < 80; i++) {
    await page.waitForTimeout(100);
    if ((await gameState(page)).room.id === 'lobby') break;
  }
  ok('功能條會傳送回大廳', (await gameState(page)).room.id === 'lobby');
  await settle(page);

  // 大廳出生點是 (480,322)，公告塔的站位在 (766,326)。
  // 壞掉時角色會一直待在出生點 —— 這條斷言就是那個 bug 的照妖鏡。
  const spawn = { x: 480, y: 322 };
  let moved = false;
  for (let i = 0; i < 60; i++) {
    const s = await gameState(page);
    if (Math.hypot(s.px - spawn.x, s.py - spawn.y) > 20) {
      moved = true;
      break;
    }
    await page.waitForTimeout(100);
  }
  const end = await gameState(page);
  ok('到站後角色會自己走離出生點', moved, `px=${end.px.toFixed(0)}, py=${end.py.toFixed(0)}`);

  /**
   * ⚠ 一定要先等**走完**再讀提示。
   *
   * 走去公告塔的路上會經過現貨交易台的互動範圍，那一瞬間提示會顯示
   * 「進行現貨交易」—— 原本這裡是「輪詢到有提示就讀」，於是十次有九次
   *  讀到的是路過交易台那一下，斷言紅在一個完全正常的行為上。
   *
   * `target` 是點擊移動的目標，抵達（或放棄）時由 player.ts 清成 null，
   * 所以「target 變回 null」就是「這段導引結束了」最準的訊號。
   */
  for (let i = 0; i < 80; i++) {
    if ((await gameState(page)).target === null) break;
    await page.waitForTimeout(100);
  }
  await page.waitForTimeout(300);

  // 走到定位就會冒出提示。刻意**不**自動開面板 —— 功能條是導航不是快捷開啟，
  // 世界裡一律走近再按鍵。
  for (let i = 0; i < 40 && !(await promptText(page)); i++) await page.waitForTimeout(200);
  ok('站定後顯示 [E] 提示', (await promptText(page))?.includes('官方消息'), await promptText(page));
  ok('功能條不會自動開面板', !(await page.locator('.panel').isVisible()));

  await page.keyboard.press('KeyE');
  await page.waitForTimeout(900);
  const title = (await page.locator('.panel-head h2').count())
    ? await page.locator('.panel-head h2').textContent()
    : '無面板';
  ok('按 E 才開面板', title.includes('官方消息'), title);

  ok('全程無執行期錯誤', page.collectedErrors.length === 0, page.collectedErrors[0] ?? '');
  await page.close();
}

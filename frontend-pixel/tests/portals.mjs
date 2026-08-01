import { openPage, gameState, walkTo, settle, panelVisible, promptText } from './lib/harness.mjs';

/** run.mjs 掃描 tests/*.mjs，套件名字從這裡讀（省略就用檔名）。 */
export const title = '傳送門';

/**
 * 傳送門與互動點共用同一套規則：走近顯示提示、按 E 才觸發。
 *
 * 這裡刻意全部用 WASD 靠近而不是點擊 —— 點擊落在物件上會走「自動前往並
 * 觸發」那條路徑，測不到「站著不動不會被傳走」這件事。
 */
export default async function portals({ browser, ok }) {
  const page = await openPage(browser);

  // ── 開面板型的拱門：走上去不會自動開 ──
  await walkTo(page, 288, 300);
  ok('討論區拱門提示為「進入 討論區」', (await promptText(page))?.includes('討論區'), await promptText(page));
  ok('站在拱門上不會自動彈出面板', !(await panelVisible(page)));
  await page.keyboard.press('KeyE');
  await page.waitForTimeout(900);
  ok('按 E 開啟選房面板', await panelVisible(page));
  await page.keyboard.press('Escape');
  await page.waitForTimeout(700);
  ok('關閉後不會自己再彈出', !(await panelVisible(page)));
  await page.waitForTimeout(1500);
  ok('站在原地等 1.5 秒仍不會彈出', !(await panelVisible(page)));
  await page.keyboard.press('KeyE');
  await page.waitForTimeout(900);
  ok('再按 E 可以再次開啟', await panelVisible(page));

  // ── 選房 → 討論室的兩個互動點 ──
  await page.locator('.rank-row').first().click();
  for (let i = 0; i < 60; i++) {
    await page.waitForTimeout(60);
    if ((await gameState(page)).room.id === 'discussion') break;
  }
  ok('選房後進入討論室', (await gameState(page)).room.id === 'discussion');
  await settle(page);

  // ── 主題看板：守住 RoomInfo → TravelTarget → Room → DOM 這一整條 ──
  const board = page.locator('.topic-board');
  ok('主題看板顯示房間主題', (await board.locator('b').textContent())?.includes('BTC'),
    await board.locator('b').textContent());
  // 標籤與線上人數是 mock 的真實欄位，不是寫死的字串
  const meta = await board.locator('span').textContent();
  ok('主題看板顯示標籤與線上人數', meta.includes('比特幣') && meta.includes('412'), meta);

  // ── NPC 對話泡泡。輪播的，所以要等 ──
  const shown = page.locator('.npc-bubble:not([hidden])');
  let bubble = null;
  for (let i = 0; i < 60 && bubble === null; i++) {
    if (await shown.count()) bubble = (await shown.first().textContent())?.trim() ?? null;
    else await page.waitForTimeout(200);
  }
  ok('NPC 會冒出對話泡泡', bubble !== null && bubble.length > 0, bubble ?? '等 12 秒都沒出現');

  await walkTo(page, 156, 296);
  await page.keyboard.press('KeyE');
  await page.waitForTimeout(1300);
  ok('Agent 分析報告可開啟', (await page.locator('.panel-head h2').textContent()).includes('Agent'));
  await page.keyboard.press('Escape');
  await page.waitForTimeout(500);

  await walkTo(page, 578, 292);
  await page.keyboard.press('KeyE');
  await page.waitForTimeout(1300);
  const title = await page.locator('.panel-head h2').textContent();
  ok('玩家討論串可開啟', title.includes('玩家討論'), title);
  await page.locator('.composer input').fill('這是測試留言');
  await page.locator('.composer button').click();
  await page.waitForTimeout(1000);
  ok('可以本地發言', (await page.locator('.post').count()) === 11, `留言數 ${await page.locator('.post').count()}`);

  // 泡泡的內容必須真的來自這間房的討論串，不是寫死的裝飾字串。
  // 這條是端到端的：遊戲層 → src/api → 命令式 DOM。
  const posts = await page.locator('.post').allTextContents();
  const head = (bubble ?? '').replace(/…$/, '');
  ok('泡泡講的是討論串裡真的留言', head.length > 6 && posts.some((p) => p.includes(head)), head);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(500);

  // ── travel 型的門也一樣要按 E ──
  // 上面那道討論區門是 panel 型的（開選房面板）。這道返回門是 travel 型，
  // 兩種 action 走的是 activatables() 裡不同的分支，都要驗到。
  await walkTo(page, 368, 432);
  ok('返回拱門提示為「返回大廳」', (await promptText(page))?.includes('返回大廳'), await promptText(page));
  await page.waitForTimeout(1200);
  ok('站在返回拱門上不會自動回去', (await gameState(page)).room.id === 'discussion');
  await page.keyboard.press('KeyE');
  for (let i = 0; i < 60; i++) {
    await page.waitForTimeout(60);
    if ((await gameState(page)).room.id === 'lobby') break;
  }
  ok('按 E 才回到大廳', (await gameState(page)).room.id === 'lobby');
  await settle(page);

  ok('全程無執行期錯誤', page.collectedErrors.length === 0, page.collectedErrors[0] ?? '');
  await page.close();
}

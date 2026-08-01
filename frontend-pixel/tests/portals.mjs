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
  // 標籤與線上人數是後端 RoomInfo 的真實欄位，不是寫死的字串。
  // 不比對特定值：房間清單現在來自 /api/discussion-spaces，內容會隨資料變。
  // 這條要守的是「這兩個欄位有一路傳到 DOM」，不是某一間房叫什麼名字。
  const meta = await board.locator('span').textContent();
  ok('主題看板顯示標籤與線上人數', /\S/.test(meta) && /\d+\s*人/.test(meta), meta);

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
  // 貼文是跟後端要的，面板會先以 loading 狀態開起來 —— 固定等待量到的是空的。
  for (let i = 0; i < 40 && !(await page.locator('.post').count()); i++) {
    await page.waitForTimeout(100);
  }
  // ⚠ 這裡**刻意不真的送出**。發言已經不是本地的了：POST /api/discussions
  //   會寫進團隊共用的 DynamoDB，並以 MAIA 官方帳號發到真的 Threads 上。
  //   無人看管的測試不該有那種副作用。改為驗「輸入介面在、且討論串確實
  //   從後端載到了貼文」；發文本身由 agent-core 的 test_threads_bridge 覆蓋。
  ok('討論串有從後端載到貼文', (await page.locator('.post').count()) > 0,
    `留言數 ${await page.locator('.post').count()}`);
  ok('發言輸入框可用',
    (await page.locator('.composer input').isEnabled()) && (await page.locator('.composer button').count()) > 0);

  // 泡泡的內容必須真的來自這間房的討論串，不是寫死的裝飾字串。
  // 這條是端到端的：遊戲層 → src/api → 命令式 DOM。
  const posts = await page.locator('.post').allTextContents();
  const head = (bubble ?? '').replace(/…$/, '');
  // 門檻放在 2 個字：真實貼文可能很短（DB 裡就有一則只有五個字的「我是慢癈龍」），
  // 原本的 > 6 是照著 mock 那批長句子訂的。
  ok('泡泡講的是討論串裡真的留言', head.length >= 2 && posts.some((p) => p.includes(head)), head);
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

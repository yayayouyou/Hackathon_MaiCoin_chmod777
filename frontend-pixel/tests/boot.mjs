import { BASE, openPage, gameState } from './lib/harness.mjs';

/** run.mjs 掃描 tests/*.mjs，套件名字從這裡讀（省略就用檔名）。 */
export const title = '進場畫面與選角';

/**
 * 進場畫面。
 *
 * ⚠ 這一支是全站唯一帶 `?boot=1` 的：其他 178 項都靠 `?fast=1` 跳過進場，
 *   否則每一支都會停在第一步（`harness.openPage` 的假設是「載入完 900ms
 *   就站在可操作的大廳」）。兩個旗標各管一件事 —— `fast` 關掉 HUD 輪詢
 *   （networkidle 要用到），`boot` 決定進場畫面蓋不蓋。
 *
 * 這支守的是四件會壞掉但不會報錯的事：
 *   ① 進場畫面亮著時世界必須是凍住的（不然人在背後被走掉）
 *   ② 選角是**外觀**，選完進世界後身上那套圖要真的換掉
 *   ③ 選擇要留在 localStorage，重整後還是同一個
 *   ④ 三個逃生口都要通 —— 現場 demo 卡在第一個畫面是最不能出的事
 */
export default async function boot({ browser, ok }) {
  const page = await openPage(browser, { query: '?debug=1&fast=1&boot=1' });

  ok('帶 ?boot=1 時進場畫面蓋著', await page.locator('.boot').isVisible());
  ok('此時 phase 是 boot', (await gameState(page)).phase === 'boot');
  // HUD 在 boot 期間整層收起來（Hud.tsx 的 `phase !== 'world'` 早退）
  ok('進場畫面上沒有 HUD', !(await page.locator('.pod').isVisible()));

  // ── ① 世界必須凍住 ──
  // 暱稱輸入框是 autoFocus 的，而 core.ts 在焦點落在 INPUT 時本來就不收鍵盤。
  // 先點標題把焦點移開，否則測到的是「打字沒有讓角色動」，那不是這條要驗的事。
  await page.locator('.boot h1').click();
  const before = await gameState(page);
  await page.keyboard.down('KeyD');
  await page.waitForTimeout(700);
  await page.keyboard.up('KeyD');
  const held = await gameState(page);
  ok('進場畫面亮著時角色不會動', held.px === before.px && held.py === before.py,
    `${before.px} → ${held.px}`);

  // ── 選角 ──
  const cards = page.locator('.char-card');
  ok('四個角色都在', (await cards.count()) === 4, `${await cards.count()} 個`);
  ok('預設選中短髮',
    (await page.locator('.char-card[data-id="classic"]').getAttribute('aria-checked')) === 'true');

  // 每張卡都要真的畫出一張圖 —— canvas 存在但寬度 0 的話畫面上是空白，
  // 而那不會有任何錯誤訊息。
  const artW = await page.locator('.char-card .char-art').first()
    .evaluate((c) => ({ w: c.width, h: c.height }));
  ok('角色預覽有畫出來', artW.w === 48 && artW.h === 75, `${artW.w}x${artW.h}`);

  await page.locator('.char-card[data-id="hood"]').click();
  await page.waitForTimeout(200);
  ok('點了兜帽就選中它',
    (await page.locator('.char-card[data-id="hood"]').getAttribute('aria-checked')) === 'true');
  ok('原本那張同時取消選中',
    (await page.locator('.char-card[data-id="classic"]').getAttribute('aria-checked')) === 'false');

  // ── 暱稱 ──
  const nick = page.locator('.boot-nick input');
  const nick0 = await nick.inputValue();
  ok('暱稱有預設值，不用自己想', nick0.length > 0, nick0);
  await page.locator('.boot-nick .chip').click();
  await page.waitForTimeout(150);
  ok('骰子會換一個名字', (await nick.inputValue()) !== nick0,
    `${nick0} → ${await nick.inputValue()}`);
  await nick.fill('測試員');

  // ── ② 進入世界 ──
  await page.locator('.boot-go').click();
  await page.waitForTimeout(1200); // ENTER_TIME = 0.55s，等光圈張完
  ok('進場畫面收掉了', !(await page.locator('.boot').isVisible()));
  const inWorld = await gameState(page);
  ok('phase 變成 world', inWorld.phase === 'world');
  ok('身上是剛剛選的角色', inWorld.character === 'hood', inWorld.character);
  ok('HUD 出現了', await page.locator('.pod').isVisible());
  ok('左下角色卡用的是同一個角色的圖',
    await page.locator('.pod-face .char-art').isVisible());

  // ── 世界解凍 ──
  const p0 = await gameState(page);
  await page.keyboard.down('KeyD');
  await page.waitForTimeout(500);
  await page.keyboard.up('KeyD');
  const p1 = await gameState(page);
  ok('進去之後角色可以動了', Math.abs(p1.px - p0.px) > 20, `${p0.px} → ${p1.px}`);

  // ── ③ 記在 localStorage ──
  await page.goto(`${BASE}/?debug=1&fast=1`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  const back = await gameState(page);
  ok('重整後角色還是兜帽', back.character === 'hood', back.character);
  ok('沒帶 ?boot=1 就不再擋著進場畫面', back.phase === 'world');
  ok('暱稱也留著', (await page.locator('.pod-name').textContent()).includes('測試員'));

  // ── ④ 鍵盤逃生口 ──
  await page.goto(`${BASE}/?debug=1&fast=1&boot=1`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  ok('again：進場畫面又蓋上了', await page.locator('.boot').isVisible());
  // 焦點在輸入框也要能用 —— 這個組合鍵是掛在 window 上的，不是掛在畫面上
  await page.keyboard.press('Control+Shift+Enter');
  await page.waitForTimeout(900);
  ok('Ctrl+Shift+Enter 直接進世界', (await gameState(page)).phase === 'world');

  // 略過鈕
  await page.goto(`${BASE}/?debug=1&fast=1&boot=1`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  await page.locator('.boot-skip').click();
  await page.waitForTimeout(900);
  ok('「略過」也直接進世界', (await gameState(page)).phase === 'world');

  ok('全程無執行期錯誤', page.collectedErrors.length === 0, page.collectedErrors[0] ?? '');
  await page.close();
}

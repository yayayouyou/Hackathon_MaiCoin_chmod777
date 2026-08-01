import { openPage, gameState, gotoWorld } from './lib/harness.mjs';

/** run.mjs 掃描 tests/*.mjs，套件名字從這裡讀（省略就用檔名）。 */
export const title = 'MAX 資訊角';

/**
 * 大廳裡的 MAX 三個站點：公告、活動、MAIA 對話。
 *
 * 這三個原本在一個叫 maxinfo 的獨立房間裡，要穿過傳送門才到得了。命題單位
 * 就是 MAX，把它的東西放在一進場就看得到的中段右側，比擺一道門值錢 ——
 * 所以那個房間整個併進大廳、傳送門移除。
 */
export default async function rooms({ browser, ok }) {
  const page = await openPage(browser);

  /** 走過去 → 按 E → 比對面板標題。點擊不再自動開，一律走近按鍵。 */
  const openAt = async (wx, wy, expect) => {
    await gotoWorld(page, wx, wy);
    await page.keyboard.press('KeyE');
    await page.waitForTimeout(1400);
    const n = await page.locator('.panel-head h2').count();
    const title = n ? await page.locator('.panel-head h2').textContent() : '(沒有面板)';
    ok(expect, title.includes(expect.split(' ')[0]), title);
    return title;
  };

  await openAt(616, 198, 'MAX 官方消息');
  await page.keyboard.press('Escape');
  await page.waitForTimeout(500);

  await openAt(728, 198, 'MAX 最新活動');
  await page.keyboard.press('Escape');
  await page.waitForTimeout(500);

  // ── MAIA 櫃檯 ──
  // ⚠ MAIA **不是彈窗**。`panels/AgentChat.tsx` 只是把舊的 panel id 轉去開
  //   `#hud-root` 的非模態 dock，所以這裡不能驗 `.panel-head h2` ——
  //   那正是這條斷言在 dock 化之後一直紅著沒人發現的原因。
  //   非模態是刻意的：agent 查工具的那 20–40 秒，世界要繼續跑。
  await gotoWorld(page, 760, 284);
  await page.keyboard.press('KeyE');
  await page.waitForTimeout(1200);
  ok('MAIA 開的是非模態 dock 而不是彈窗',
    (await page.locator('.maia-dock').isVisible()) && !(await page.locator('.panel').isVisible()));
  // 非模態的意思就是這個：dock 開著，角色還走得動。彈窗做不到這件事
  // （`game/index.ts` 的 frozen 含 activePanel !== null）。
  const before = await gameState(page);
  await page.keyboard.down('KeyA');
  await page.waitForTimeout(500);
  await page.keyboard.up('KeyA');
  const after = await gameState(page);
  ok('開著 dock 時世界沒有被凍住', Math.abs(after.px - before.px) > 5,
    `px ${before.px.toFixed(0)}→${after.px.toFixed(0)}`);

  // canned 事件路徑（harness 預設帶 ?fast=1），不需要後端在跑 —— 但它走的是
  // 跟真後端**同一條** onEvent 分派，final_answer 進訊息陣列這件事被真的驗到了。
  await page.locator('.maia-composer input').fill('測試');
  await page.locator('.maia-composer .btn-primary').click();
  await page.waitForTimeout(2400);
  ok('MAIA 會回覆', (await page.locator('.chat-msg').count()) >= 3,
    `對話 ${await page.locator('.chat-msg').count()} 則`);
  ok('工具晶片有長出來', (await page.locator('[data-testid="tool-chips"] .chip').count()) >= 2,
    `晶片 ${await page.locator('[data-testid="tool-chips"] .chip').count()} 顆`);
  await page.locator('.maia-x').click();
  await page.waitForTimeout(500);

  // 三個站點頭上都要有常駐站牌，而且是名詞（「公告」）不是動詞
  // （「讀取官方消息」）—— 遠遠一眼要看得出那是什麼。
  const signs = await page.locator('#world-labels .spot-label').allTextContents();
  ok('MAX 三個站點都有常駐站牌',
    ['公告', '活動', 'MAIA'].every((s) => signs.includes(s)), signs.join(' / '));
  ok('站牌用的是名詞不是動詞', !signs.some((s) => s.includes('讀取') || s.includes('查看')),
    signs.join(' / '));

  ok('全程無執行期錯誤', page.collectedErrors.length === 0, page.collectedErrors[0] ?? '');
  await page.close();
}

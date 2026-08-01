import { openPage, gameState, walkTo } from './lib/harness.mjs';

/** run.mjs 掃描 tests/*.mjs，套件名字從這裡讀（省略就用檔名）。 */
export const title = '大廳站點';

/**
 * 大廳五個功能站點：東翼 MAX 官方區的四個（現貨交易 / 公告 / 活動 / 客服）
 * 與中庭的 MAIA。
 *
 * 這一支同時是「主走道淨空」那條排版規則的驗證：五個站點分散在
 * x408..884、y320..460，全部用同一個 `openAt()` 走過去按 E。任何一件裝飾
 * 掉進走道，這裡就會有一條變成「(沒有面板)」—— 因為角色會卡在半路。
 *
 * ⚠ 走位一律用 walkTo（鍵盤）而不是點擊移動。東翼那四個站點在角色出生點的
 *   鏡頭下都落在畫面外，而 harness 的 toScreen() 會把點擊夾到畫布邊緣 ——
 *   夾出來的世界座標 (719,320) 剛好在障礙物上，引擎直接拒絕建立移動目標
 *   （target 保持 null），角色一步都不會動。於是這四條長期紅著，看起來像
 *   走道被擋，其實是測試自己點不到。
 */
export default async function rooms({ browser, ok }) {
  const page = await openPage(browser);

  /** 走過去 → 按 E → 比對面板標題。點擊不再自動開，一律走近按鍵。 */
  const openAt = async (wx, wy, expect) => {
    await walkTo(page, wx, wy);
    await page.keyboard.press('KeyE');
    await page.waitForTimeout(1400);
    const n = await page.locator('.panel-head h2').count();
    const title = n ? await page.locator('.panel-head h2').textContent() : '(沒有面板)';
    ok(expect, title.includes(expect.split(' ')[0]), title);
    return title;
  };

  // 座標抄自 features/registry.ts 的 place —— 那份跟 makeLobby() 的
  // 互動範圍是同一組數字，tests/zones.mjs 會驗它們對得上。
  await openAt(766, 320, 'MAX 官方消息');
  await page.keyboard.press('Escape');
  await page.waitForTimeout(500);

  await openAt(884, 320, 'MAX 最新活動');
  await page.keyboard.press('Escape');
  await page.waitForTimeout(500);

  await openAt(648, 320, 'MAX 現貨交易');
  await page.keyboard.press('Escape');
  await page.waitForTimeout(500);

  await openAt(836, 460, 'MAX 官方客服');
  await page.keyboard.press('Escape');
  await page.waitForTimeout(500);

  // ── MAIA 櫃檯 ──
  // ⚠ MAIA **不是彈窗**。`panels/AgentChat.tsx` 只是把舊的 panel id 轉去開
  //   `#hud-root` 的非模態 dock，所以這裡不能驗 `.panel-head h2` ——
  //   那正是這條斷言在 dock 化之後一直紅著沒人發現的原因。
  //   非模態是刻意的：agent 查工具的那 20–40 秒，世界要繼續跑。
  await walkTo(page, 408, 320);
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

  // 五個站點頭上都要有常駐站牌，而且是名詞（「公告」）不是動詞
  // （「讀取官方消息」）—— 遠遠一眼要看得出那是什麼。
  const signs = await page.locator('#world-labels .spot-label').allTextContents();
  ok('五個站點都有常駐站牌',
    ['現貨交易', '公告', '活動', '客服', 'MAIA'].every((s) => signs.includes(s)),
    signs.join(' / '));
  // MAIA 的站牌是紫色，MAX 那四個是品牌藍。顏色是「這一區不是 MAX 的」
  // 最快的說明，比距離還快 —— 所以它是一條斷言而不是註解。
  const maiaAccent = await page
    .locator('#world-labels .spot-label', { hasText: 'MAIA' })
    .first()
    .getAttribute('data-accent');
  ok('MAIA 站牌用紫色跟 MAX 的藍分開', maiaAccent === 'violet', String(maiaAccent));
  ok('站牌用的是名詞不是動詞', !signs.some((s) => s.includes('讀取') || s.includes('查看')),
    signs.join(' / '));

  ok('全程無執行期錯誤', page.collectedErrors.length === 0, page.collectedErrors[0] ?? '');
  await page.close();
}

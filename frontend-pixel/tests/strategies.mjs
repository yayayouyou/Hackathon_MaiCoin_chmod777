import { openPage, gotoWorld, waitForPanel } from './lib/harness.mjs';

/** run.mjs 掃描 tests/*.mjs，套件名字從這裡讀（省略就用檔名）。 */
export const title = '策略牆';

/**
 * 大廳左側的策略牆：社群分享的做法。
 *
 * 這支測的重點不只是「面板打得開」，還有三條**刻意的設計**不能被改掉：
 *   ① 報酬旁邊一定要有回撤與樣本數（只秀報酬是這類看板最常見的誤導）
 *   ② 樣本 < 30 筆要掛警示
 *   ③ 卡片上沒有「跟單」，只有收藏與請 MAIA 分析（合規觀感）
 */
export default async function strategies({ browser, ok }) {
  const page = await openPage(browser);

  await gotoWorld(page, 244, 206);
  await page.keyboard.press('KeyE');
  ok('走到策略牆按 E 可開啟', await waitForPanel(page));
  ok('面板標題是策略牆',
    (await page.locator('.panel-head h2').textContent()).includes('策略牆'));

  // ⚠ waitForPanel 只等 `.panel` 出現，但卡片要等 getStrategies() 的延遲回來
  //   （api/index.ts 刻意留了 120–300ms，逼每個面板都有真的 loading 狀態）。
  //   少了這一等，count() 會在資料到之前跑，時快時慢地紅。
  const cards = page.locator('.strat');
  await cards.first().waitFor({ timeout: 8000 });
  const total = await cards.count();
  ok('牆上有策略卡片', total >= 5, `${total} 張`);

  // ① 報酬、回撤、勝率、樣本四個數字同時存在
  const labels = await cards.first().locator('.strat-metric i').allTextContents();
  ok('報酬與回撤、樣本數並列',
    ['近 30 日', '最大回撤', '勝率', '樣本'].every((l) => labels.includes(l)), labels.join(' / '));

  // ② 樣本不足要掛警示，而且卡片本身要標記出來
  ok('樣本不足的卡片有警示', (await page.locator('.strat[data-thin="1"] .strat-thin').count()) >= 1);

  // ③ 沒有跟單／複製交易的入口
  const body = await page.locator('.panel-body').textContent();
  ok('沒有一鍵跟單的入口', !/跟單|複製交易|一鍵下單/.test(body));
  ok('有不構成投資建議的說明', body.includes('不構成投資建議'));

  // 分類篩選
  await page.locator('.chip', { hasText: '網格' }).first().click();
  await page.waitForTimeout(400);
  const grid = await cards.count();
  ok('分類篩選有效', grid > 0 && grid < total, `網格 ${grid} 張 / 全部 ${total} 張`);
  await page.locator('.chip', { hasText: '全部' }).first().click();
  await page.waitForTimeout(400);
  ok('回到全部', (await cards.count()) === total);

  // 排序：回撤最小的那一張要排到第一
  await page.locator('.chip', { hasText: '回撤最小' }).click();
  await page.waitForTimeout(400);
  const drawdowns = await page.locator('.strat .strat-metric:nth-child(2) b').allTextContents();
  const nums = drawdowns.map((d) => parseFloat(d));
  ok('依回撤排序後是遞增的',
    nums.every((n, i) => i === 0 || n >= nums[i - 1]), nums.join(' → '));

  // 規則可展開
  await page.locator('.strat .chip', { hasText: '進出場規則' }).first().click();
  await page.waitForTimeout(400);
  ok('進出場規則可展開', (await page.locator('.strat-rules li').count()) >= 2);

  // 收藏
  const star = page.locator('.strat .star').first();
  const before = await star.textContent();
  await star.click();
  await page.waitForTimeout(300);
  ok('可以收藏', (await star.textContent()) !== before, `${before} → ${await star.textContent()}`);

  // ── 交給 MAIA ──
  // 這是策略牆真正的出口：不是「照著做」，是把規則丟給 agent 去查證。
  await page.locator('.strat .btn', { hasText: '請 MAIA 分析' }).first().click();
  await page.waitForTimeout(1600);
  ok('會關掉面板並打開 MAIA dock',
    !(await page.locator('.panel').isVisible()) && (await page.locator('.maia-dock').isVisible()));

  const asked = await page.evaluate(() =>
    [...document.querySelectorAll('.chat-msg.me')].map((e) => e.textContent).join('\n'));
  ok('送出的問題帶著這套策略的規則', asked.includes('規則是') && asked.length > 60,
    asked.slice(0, 60));

  ok('全程無執行期錯誤', page.collectedErrors.length === 0, page.collectedErrors[0] ?? '');
  await page.close();
}

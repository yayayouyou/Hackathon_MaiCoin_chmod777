import { BASE } from './lib/harness.mjs';

/** run.mjs 掃描 tests/*.mjs，套件名字從這裡讀（省略就用檔名）。 */
export const title = '玩家登入';

/**
 * 進場的第一步。
 *
 * ⚠ 這一支**不能用 `harness.openPage`**：它在內部就 `page.goto` 了，
 *   而路由攔截必須在導航之前掛上。所以這裡自己開 context。
 *
 * ⚠ 也**不能帶 `?fast=1`**：`api/auth.ts` 在 `FLAGS.fast` 下直接回傳 canned
 *   玩家、完全不發請求（離線錄影與其他 202 項測試靠的就是這條捷徑），
 *   帶了就永遠測不到登入卡。代價是要自己把 `/api/**` 全部擋掉，
 *   否則沒有後端時 `waitUntil:'networkidle'` 不會觸發。
 *
 * 守的是四件事：
 *   ① 未登入要看得到登入卡，不能默默把人放進世界
 *   ② 已登入要跳過登入卡，而且暱稱是**伺服器那份**不是 localStorage 那份
 *   ③ 訪客入口要通 —— 後端掛掉時世界不該跟著鎖死
 *   ④ 後端錯誤要顯示後端寫的中文，不是「HTTP 409」
 */

const PLAYER = {
  username: 'alice', nickname: '小明', character: '', stance: '',
  favorites: [], created_at: '2026-08-01T00:00:00Z',
};

const json = (status, body) => ({
  status, contentType: 'application/json', body: JSON.stringify(body),
});

/**
 * 開一個頁面，並把後端的 `/api/*` 換成受控的假回應。
 *
 * `me` 為 null 代表未登入（401）；`fail` 為 true 代表後端整個連不上。
 *
 * ⚠ **攔截條件用 pathname 判斷，不要用 `'**\/api\/**'` 這種 glob。**
 *   前端自己的原始碼就住在 `src/api/`，vite dev server 會以
 *   `/src/api/auth.ts` 的路徑供應它 —— glob 會把那個模組請求也攔下來回
 *   JSON，瀏覽器因為 MIME 檢查拒絕載入 module script，結果是整個 app
 *   一片空白、`#ui-root` 是空的，而畫面上完全沒有任何錯誤提示。
 */
async function openAuthPage(browser, { me = null, fail = false, overrides = {} } = {}) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });

  await context.route(
    (url) => url.pathname.startsWith('/api/'),
    (route) => {
      const { pathname } = new URL(route.request().url());
      if (overrides[pathname]) return route.fulfill(overrides[pathname]);
      if (pathname === '/api/auth/me') {
        if (fail) return route.abort('failed');
        return route.fulfill(me ? json(200, { player: me }) : json(401, { detail: '請先登入。' }));
      }
      // 其餘一律空回應：沒有後端時讓 networkidle 有機會觸發
      return route.fulfill(json(200, {}));
    },
  );

  const page = await context.newPage();
  await page.goto(`${BASE}/?debug=1&boot=1`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  return page;
}

export default async function auth({ browser, ok }) {
  // ── ① 未登入 ──
  {
    const page = await openAuthPage(browser);
    ok('未登入時顯示登入卡', await page.locator('[data-testid=login]').isVisible());
    // 用選角盤而不是文字輸入框判斷：登入卡的「帳號」欄位共用 .boot-nick 樣式，
    // 拿它當「還沒進到取名步驟」的依據會永遠是真
    ok('此時還看不到選角盤', !(await page.locator('.char-grid').isVisible()));
    ok('世界仍被進場畫面蓋著', await page.locator('.boot').isVisible());
    await page.context().close();
  }

  // ── ② 已登入 ──
  {
    const page = await openAuthPage(browser, { me: PLAYER });
    ok('已登入時跳過登入卡', !(await page.locator('[data-testid=login]').isVisible()));
    const nick = await page.locator('.boot-nick input[type=text]').first().inputValue();
    ok('暱稱來自伺服器而不是 localStorage', nick === '小明', `讀到「${nick}」`);
    await page.context().close();
  }

  // ── ③ 訪客入口 ──
  {
    const page = await openAuthPage(browser);
    await page.locator('.boot-guest').click();
    await page.waitForTimeout(200);
    ok('按訪客後進到取名選角', await page.locator('.boot-nick input[type=text]').first().isVisible());
    ok('訪客不會看到登入卡', !(await page.locator('[data-testid=login]').isVisible()));
    await page.context().close();
  }

  // ── ④ 後端錯誤訊息 ──
  {
    const page = await openAuthPage(browser, {
      overrides: { '/api/auth/register': json(409, { detail: '這個帳號已經有人用了。' }) },
    });
    await page.locator('.boot-tab', { hasText: '註冊' }).click();
    await page.locator('input[autocomplete=username]').fill('alice');
    await page.locator('input[type=password]').fill('hunter2xyz');
    await page.locator('.boot-go').click();
    await page.waitForTimeout(400);
    const msg = await page.locator('.boot-err').textContent();
    ok('顯示後端寫的中文錯誤', msg === '這個帳號已經有人用了。', `讀到「${msg}」`);
    ok('失敗後仍停在登入卡', await page.locator('[data-testid=login]').isVisible());
    await page.context().close();
  }

  // ── ⑤ 後端整個連不上 ──
  {
    const page = await openAuthPage(browser, { fail: true });
    ok('後端掛掉時不會卡在「確認登入狀態…」',
      !(await page.locator('[data-testid=auth-checking]').isVisible()));
    ok('後端掛掉時仍給得出登入卡（訪客入口在上面）',
      await page.locator('[data-testid=login]').isVisible());
    await page.context().close();
  }
}

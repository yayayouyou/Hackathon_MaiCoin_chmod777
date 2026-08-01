import { spawn } from 'node:child_process';

/** 明確指定 BASE_URL 才會沿用外部 server，否則一律自己起（見 ensureServer）。 */
const EXPLICIT = process.env.BASE_URL ?? null;

/**
 * ⚠ 這是 `let` 而不是 `const`：沒指定 BASE_URL 時 ensureServer() 會挑一個
 *   隨機 port 並回寫這個值。ESM 的 live binding 讓 import 端自動看到新值，
 *   所以 `import { BASE }` 的檔案不必改。
 */
export let BASE = EXPLICIT ?? 'http://localhost:5173';

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function ping(url = BASE) {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(800) });
    return res.ok;
  } catch {
    return false;
  }
}

function spawnVite(port) {
  return spawn('npx', ['vite', '--port', String(port), '--strictPort'], { stdio: 'ignore' });
}

/**
 * 確保有 dev server 可以連。
 *
 * 陷阱 A（規格 §8.4）：舊版先 ping :5173，通了就直接沿用，**完全不驗證那台
 * server 服務的是哪個分支**。integrator 開著自己分支的 `npm run dev`、
 * checkout 隊友分支跑測試 → 132 項全綠，但測的是自己的程式碼。
 * 現在沒指定 `BASE_URL` 就一律用隨機 port 自己起一台，測到的必定是
 * 當前工作目錄的程式碼。要沿用外部 server 請顯式 `BASE_URL=... npm test`。
 */
export async function ensureServer() {
  if (EXPLICIT) {
    if (await ping(EXPLICIT)) return null;
    const port = new URL(EXPLICIT).port || '5173';
    const child = spawnVite(port);
    for (let i = 0; i < 80; i++) {
      await sleep(250);
      if (await ping(EXPLICIT)) return child;
    }
    child.kill();
    throw new Error(`dev server 沒有在 ${EXPLICIT} 起來`);
  }

  // 隨機 port，撞到就換一個再試（--strictPort 保證撞到時會直接死掉而不是偷偷換 port）
  for (let attempt = 0; attempt < 3; attempt++) {
    const port = 21000 + Math.floor(Math.random() * 20000);
    const url = `http://localhost:${port}`;
    const child = spawnVite(port);
    for (let i = 0; i < 80; i++) {
      await sleep(250);
      if (child.exitCode !== null) break; // strictPort 撞掉了
      if (await ping(url)) {
        BASE = url;
        return child;
      }
    }
    child.kill();
  }
  throw new Error('連續三次都起不起 dev server（隨機 port）');
}

/** 一組檢查的收集器。ok() 收集結果，套件本身不印任何東西。 */
export function checks() {
  const rows = [];
  return {
    rows,
    ok(name, cond, detail) {
      rows.push({ name, pass: !!cond, detail: detail === undefined ? '' : String(detail) });
    },
  };
}

/**
 * 網路層失敗的白名單（規格 §8.4 陷阱 B）。
 *
 * 瀏覽器對失敗的 fetch 會自己吐一則 error-level 的 console 訊息，
 * 而且那是瀏覽器發的、`console.warn` 換不掉。有五個套件斷言
 * `collectedErrors.length === 0`，所以只要真的打了一次會失敗的請求
 * （?failApi=1、後端沒開、HUD 輪詢逾時）就會全線變紅 ——
 * 而那些情境本來就是我們**刻意要走過一遍**的降級路徑。
 *
 * 這裡只放「網路請求失敗」這一類。程式碼自己 console.error 的一律不放行，
 * 因為 validateWiring() 與 getZone() 的抱怨正是要靠這條斷言抓出來。
 */
const IGNORED_CONSOLE = [/Failed to load resource/i, /net::ERR_/];

/**
 * 開一個頁面並收集錯誤。
 *
 * 預設帶 `?debug=1`（驗證幾乎都要讀 window.__game() 的座標與鏡頭數字，
 * 比對數字遠比盯截圖可靠）與 `?fast=1`（關掉 HUD 輪詢 —— 掛著的輪詢會讓
 * `waitUntil:'networkidle'` 永不觸發，page.goto 撞 30s 逾時，
 * 每個套件都會記成「套件中斷」）。
 */
export async function openPage(browser, opts = {}) {
  const { query = '?debug=1&fast=1', viewport = { width: 1440, height: 900 }, device } = opts;
  const context = await browser.newContext(device ? { ...device } : { viewport });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  page.on('console', (m) => {
    if (m.type() !== 'error') return;
    const text = m.text();
    if (IGNORED_CONSOLE.some((re) => re.test(text))) return;
    errors.push(`console: ${text}`);
  });
  await page.goto(`${BASE}/${query}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  page.collectedErrors = errors;
  return page;
}

export const gameState = (page) => page.evaluate(() => window.__game());

/** 世界座標 → 螢幕座標。畫布已滿版，沒有 letterbox 偏移要補。 */
async function toScreen(page, wx, wy) {
  const s = await gameState(page);
  const size = page.viewportSize();
  return {
    x: Math.min(size.width - 4, Math.max(4, (wx - s.cam.x) * s.view.scale)),
    y: Math.min(size.height - 4, Math.max(4, (wy - s.cam.y) * s.view.scale)),
  };
}

export async function clickWorld(page, wx, wy) {
  const { x, y } = await toScreen(page, wx, wy);
  await page.mouse.click(x, y);
}

export async function tapWorld(page, wx, wy) {
  const { x, y } = await toScreen(page, wx, wy);
  await page.touchscreen.tap(x, y);
}

const panelVisible = (page) => page.locator('.panel').isVisible();

/**
 * 點擊移動過去，輪詢到抵達為止。
 *
 * 目標可能落在畫面外（角色在房間另一端），所以夾在畫布內分段點擊。
 * 換場或面板彈出就提早結束 —— 那表示點到了可互動物件。
 */
export async function gotoWorld(page, wx, wy, tol = 12) {
  const start = await gameState(page);
  for (let leg = 0; leg < 8; leg++) {
    const s = await gameState(page);
    if (Math.hypot(s.px - wx, s.py - wy) < tol) break;
    await clickWorld(page, wx, wy);
    for (let i = 0; i < 30; i++) {
      await page.waitForTimeout(200);
      const c = await gameState(page);
      if (c.room.id !== start.room.id) return;
      if (await panelVisible(page)) return;
      if (Math.hypot(c.px - wx, c.py - wy) < tol) break;
    }
  }
  await page.waitForTimeout(400);
}

/**
 * 用 WASD 走過去。
 *
 * 跟 gotoWorld 的差別很重要：點擊落在可互動物件上會「自動走過去並觸發」，
 * 想驗證「站在門上不會自動傳送」就必須用鍵盤靠近，否則測到的是另一條路徑。
 */
export async function walkTo(page, wx, wy, tol = 8) {
  for (let i = 0; i < 120; i++) {
    const s = await gameState(page);
    const dx = wx - s.px;
    const dy = wy - s.py;
    if (Math.hypot(dx, dy) < tol) break;
    const keys = [];
    if (dx > 4) keys.push('KeyD');
    else if (dx < -4) keys.push('KeyA');
    if (dy > 4) keys.push('KeyS');
    else if (dy < -4) keys.push('KeyW');
    if (!keys.length) break;
    for (const k of keys) await page.keyboard.down(k);
    await page.waitForTimeout(60);
    for (const k of keys) await page.keyboard.up(k);
  }
  await page.waitForTimeout(200);
}

/** 等到轉場結束，避免下一步在光圈還沒張開時就操作。 */
export async function settle(page, tries = 60) {
  for (let i = 0; i < tries; i++) {
    if (!(await gameState(page)).transition) return;
    await page.waitForTimeout(60);
  }
}

export async function waitForPanel(page, tries = 60) {
  for (let i = 0; i < tries; i++) {
    if (await panelVisible(page)) return true;
    await page.waitForTimeout(200);
  }
  return false;
}

export async function promptText(page) {
  const el = page.locator('.world-prompt');
  return (await el.isVisible()) ? await el.textContent() : null;
}

export { panelVisible };

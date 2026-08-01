import { readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { chromium } from 'playwright';
import { checks, ensureServer, BASE } from './lib/harness.mjs';

/**
 * 掃描 `tests/*.mjs`（規格 §8.3 規則 5）。
 *
 * 原本 SUITES 是手寫的 10 行陣列 —— 四份設計提案都要往裡面加一筆，
 * 那是保證衝突的一行。改成掃描之後，新增套件是**純新檔、零共用編輯**。
 *
 * 套件檔的契約：
 *   export default async function ({ browser, ok }) { … }
 *   export const title = '中文套件名';   ← 省略就用檔名
 *
 * 執行順序是檔名字母序。套件之間必須互相獨立（各自 openPage），
 * 不要依賴前一個套件留下的狀態。
 */
const here = dirname(fileURLToPath(import.meta.url));

const SUITES = [];
for (const file of readdirSync(here).filter((f) => f.endsWith('.mjs') && f !== 'run.mjs').sort()) {
  const mod = await import(pathToFileURL(join(here, file)).href);
  if (typeof mod.default !== 'function') {
    console.error(`跳過 ${file}：沒有 default export 的套件函式`);
    continue;
  }
  SUITES.push([mod.title ?? file.replace(/\.mjs$/, ''), mod.default, file]);
}

const only = process.argv.slice(2);
const picked = only.length
  ? SUITES.filter(([name, , file]) => only.some((o) => name.includes(o) || file.includes(o)))
  : SUITES;
if (!picked.length) {
  console.error(`找不到套件：${only.join(', ')}\n可用：${SUITES.map(([n]) => n).join(', ')}`);
  process.exit(1);
}

const server = await ensureServer();
if (server) console.log(`（自行啟動 dev server：${BASE}）\n`);
const browser = await chromium.launch();

let pass = 0;
let fail = 0;
const start = Date.now();

for (const [name, run] of picked) {
  const h = checks();
  try {
    await run({ browser, ok: h.ok });
  } catch (e) {
    h.ok('套件中斷', false, e.message.split('\n')[0]);
  }
  const bad = h.rows.filter((r) => !r.pass).length;
  pass += h.rows.length - bad;
  fail += bad;
  console.log(`${bad ? '✗' : '✓'} ${name}  ${h.rows.length - bad}/${h.rows.length}`);
  // 通過的只在有失敗時才展開，平常保持輸出精簡
  for (const r of h.rows) {
    if (r.pass && !bad) continue;
    console.log(`    ${r.pass ? '✓' : '✗'} ${r.name}${r.detail ? ` — ${r.detail}` : ''}`);
  }
}

await browser.close();
server?.kill();

const secs = ((Date.now() - start) / 1000).toFixed(0);
console.log(`\n${pass} 通過 / ${fail} 失敗（${secs}s）`);
process.exit(fail ? 1 : 0);

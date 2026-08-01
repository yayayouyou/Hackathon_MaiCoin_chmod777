import { build } from 'vite';
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import react from '@vitejs/plugin-react';

/**
 * 把整個前端壓成**一個可以雙擊打開的 HTML**。
 *
 *   cd frontend-pixel && node scripts/build-single.mjs
 *   → ../預覽-新介面.html
 *
 * 為什麼需要它：不是每個要看設計的人手上都有 node 與 npm，現場也不見得有
 * 時間開一個 dev server。這支腳本產出的檔案沒有任何外部請求，用 file://
 * 打開就會跑 —— 傳給隊友、給評審看、或臨時換一台筆電都只是一個檔案。
 *
 * ⚠ 兩個關鍵設定，少一個就打不開：
 * ① `format: 'iife'`。Vite 預設吐 ESM，而瀏覽器在 file:// 底下的 origin 是
 *    `null`，`<script type="module">` 的 import 會被 CORS 擋掉。
 *    iife 是一般 script，沒有這個問題。
 * ② `inlineDynamicImports`。有動態 import 的話 iife 打不成單一檔案。
 *
 * 這只是預覽用的產物，`.gitignore` 擋著不進版控。
 * 正式部署仍然走 `npm run build`（ESM、分檔、可快取）。
 */

const OUT = '../預覽-新介面.html';
const TMP = 'dist-single';

await build({
  root: process.cwd(),
  plugins: [react()],
  logLevel: 'warn',
  build: {
    outDir: TMP,
    emptyOutDir: true,
    // 所有資產都內嵌，不留任何外部請求
    assetsInlineLimit: 100_000_000,
    cssCodeSplit: false,
    rollupOptions: {
      input: 'index.html',
      output: {
        format: 'iife',
        inlineDynamicImports: true,
        entryFileNames: 'a.js',
        assetFileNames: 'a[extname]',
      },
    },
  },
});

let html = readFileSync(join(TMP, 'index.html'), 'utf8');
const js = readFileSync(join(TMP, 'a.js'), 'utf8');
const css = readFileSync(join(TMP, 'a.css'), 'utf8');
// config.js 是 public/ 的靜態檔，刻意不進 bundle —— 單檔版要自己塞回去
const cfg = readFileSync('public/config.js', 'utf8');

html = html.replace(/<script src="\/config\.js"><\/script>/, `<script>${cfg}</script>`);
html = html.replace(/<script type="module"[^>]*src="[^"]*"[^>]*><\/script>/, '');
html = html.replace(/<link[^>]*rel="stylesheet"[^>]*>/, `<style>${css}</style>`);
// script 放在 </body> 之前：#stage / #hud-root / #ui-root 要先存在
html = html.replace('</body>', `<script>${js}</script>\n</body>`);

writeFileSync(OUT, html);
console.log(`${OUT} · ${(html.length / 1024).toFixed(0)}KB`);

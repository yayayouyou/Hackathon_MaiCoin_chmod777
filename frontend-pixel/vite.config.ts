import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    /**
     * 把 /api/* 代到 agent-core 的 FastAPI。
     *
     * 走 proxy 而不是在前端寫死 `http://localhost:8000`，有兩個理由：
     * ① 前端對後端永遠同源 → 完全不需要 CORS，也就不會有「本機好好的、
     *    部署後被 preflight 擋掉」這種只在正式環境才出現的錯。
     * ② 部署時把 CloudFront 的 /api/* behavior 指到後端就好，前端 build
     *    產物一個字都不用改。
     *
     * SSE（POST /api/chat）必須 `changeOrigin` 且不能被緩衝 —— Vite 的 proxy
     * 底層是 http-proxy，預設就是逐塊轉發，不會把 text/event-stream 收完才吐。
     *
     * 目標寫死本機而不是讀 `process.env`：devDependencies 沒有 `@types/node`
     * （附錄 B 規則 1 禁止新增相依），而 vite.config.ts 也在嚴格 tsc 的範圍內。
     * 要指到別台機器就改這一行 —— 這是開發用設定，正式部署走 CloudFront 的
     * /api/* behavior，跟這裡無關。
     */
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      /**
       * 行情的備援路徑（`hud/feeds.ts` 的第二層），**只在 dev 存在**。
       *
       * MAX 的公開 REST 回應沒有 `Access-Control-Allow-Origin`，所以瀏覽器
       * 直接 fetch 它一定被擋 —— 那正是行情條曾經整排顯示「—」的原因。
       * CORS 是瀏覽器的規則，proxy 是 server 對 server，不適用，所以繞這裡走得通。
       *
       * 它不是主路徑：主路徑是同源的 `/api/tickers`（agent-core 轉發 + 10 秒快取）。
       * 這條只是讓「只跑前端、沒開 agent-core」的人也看得到真行情，
       * 因此正式環境刻意不提供對應 behavior，feeds 也只在 localhost 才會試它。
       */
      '/maxapi': {
        target: 'https://max-api.maicoin.com',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/maxapi/, ''),
      },
    },
  },
  build: {
    rollupOptions: {
      /**
       * 多入口預留（規格 §10 W19、附錄 A）。
       *
       * `pro.html` + `src/pro.tsx` 是給評審看「這能變成 MAX 的產品」的那一頁，
       * 也是硬性交付的「Live Demo 部署網址」要填的東西。它落地時在這裡加一行
       * `pro: 'pro.html',` 就好 —— 路徑相對於專案根目錄。
       *
       * 現在就把 input 寫成物件的理由：從單一入口切成多入口會改變 Vite 的
       * 預設行為（chunk 命名與 html 輸出位置），與其到時候在最後一天發現，
       * 不如現在就固定下來。
       */
      input: {
        main: 'index.html',
      },
    },
  },
});

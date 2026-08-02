import { createRoot } from 'react-dom/client';
import './world/zones'; // ① zone barrel 先求值（PANELS 由 ui/App 那條 import 帶進來）
import { startGame } from './game';
import { App } from './ui/App';
import { Hud } from './hud/Hud';
import { startFeeds } from './hud/feeds';
import { validateWiring } from './engine/validate';
import './ui/styles.css'; // @layer core
import './hud/hud.css'; // @layer hud

/**
 * ★ 接縫 PR 後凍結，要動請開 issue。
 *
 * 這幾行原本有四份設計提案要各自改同一行，所以一次改到最終形態：
 * 兩個 React root（面板層與 HUD 層）、世界、接線驗證、資料泵。
 *
 * ⚠ 順序與規格 §9 的草稿相反：`validateWiring()` 排在 `startGame()` **之前**。
 *   規格沒有考慮到 `startGame()` 內含第一次 `swapRoom('lobby')` —— 驗證排在
 *   後面的話，它保護不了它最該保護的那一次換場。它只 import `world/zones`
 *   與 `engine/panel` 兩個葉節點，沒有任何相依理由要排在遊戲之後。
 *
 * ⚠ `startGame()` 包 try/catch 的理由同上：世界起不來時至少讓兩個 React root
 *   掛上去，畫面上有東西可看、面板還能開，而不是整片白。
 */

validateWiring(); // ② dev 與 prod 都跑，壞掉的 zone/panel 被移除而非 throw
try {
  startGame(); // ③ 世界立刻跑（之後的 boot overlay 蓋在它之上，它就是最好的背景動畫）
} catch (e) {
  console.error('[boot] 世界起不來，改用只有面板的降級模式', e);
}
startFeeds(); // ④ 內含 ?fast=1 早退
createRoot(document.getElementById('hud-root')!).render(<Hud />);
createRoot(document.getElementById('ui-root')!).render(<App />);

/**
 * ⑤ PWA service worker —— 讓手機可把 MAIA 裝成 app。
 *
 * 只在**正式環境**註冊：dev 下 SW 會攔截 Vite 的模組請求、把 HMR 弄壞。
 * 部署（CloudFront）是 prod build，SW 就會生效 → Android 跳「安裝」、
 * iOS 走 apple-touch-icon「加入主畫面」。SW 本身刻意不快取 /api/*（見 sw.js）。
 */
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  addEventListener('load', () => {
    void navigator.serviceWorker.register('/sw.js').catch((e) => console.warn('[pwa] sw 註冊失敗', e));
  });
}

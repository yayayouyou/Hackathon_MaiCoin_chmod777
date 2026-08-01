import { useUI } from '../ui/uiStore';
import { AgentDock } from './blocks/AgentDock';
import { FeatureBar } from './blocks/FeatureBar';
import { ProfilePod } from './blocks/ProfilePod';
import { TickerStrip } from './blocks/TickerStrip';
import { ZoomToggle } from './blocks/ZoomToggle';

/**
 * 第三 DOM 層的根（規格 §3.1、§7.1）。
 *
 * 它為什麼必須是獨立的 React root 而不是塞進 `#ui-root`：
 * 1. `tests/movement.mjs` 只 watch `#ui-root` 與 `#world-labels`，
 *    `#hud-root` 是未被觀測的兄弟節點；
 * 2. `game/index.ts` 的 `setLabelsVisible(!frozen)` 會在開面板時把整層
 *    `#world-labels` 淡成 opacity 0 —— 而 agent 狀態恰恰是開著面板時
 *    最需要看到的東西。
 *
 * 紀律：骨架用 React 畫一次，跳動的數值一律走命令式更新（`LiveText`
 * 或直接寫 `textContent`）。`#hud-root` 的 childList + attributes 變動
 * 在角色走動期間必須維持 0 —— 這三個區塊都只在人操作時才重繪，
 * dock 裡唯一每秒在跳的秒數走 `Elapsed` 的 rAF + textContent。
 *
 * boot 期間整層收起來：進場動畫要的是一個乾淨的世界，不是一個已經
 * 長滿 UI 的畫面。
 *
 * 還沒掛的：AlertStack（洞察通知）、SourceBadge、PortfolioTile。
 * 前兩者要等主動預警與真的資料來源判定，第三個要等 FIFO 的持倉端點。
 */
export function Hud() {
  const { phase } = useUI();
  if (phase !== 'world') return null;

  return (
    <>
      <TickerStrip />
      <ProfilePod />
      <ZoomToggle />
      <FeatureBar />
      <AgentDock />
    </>
  );
}

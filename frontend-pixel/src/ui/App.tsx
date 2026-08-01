import { useEffect, useSyncExternalStore } from 'react';
import { closePanel, setPhase, useUI } from './uiStore';
import { getPanel } from '../engine/panel';
import { PanelBoundary } from './PanelBoundary';
import { BootScreen } from '../boot/BootScreen';
// 只為了求值：barrel 在模組載入時把面板灌進 engine/panel 的註冊表。
// App 本身刻意不 import PANELS —— 它只認註冊表，所以新增面板永遠不用改這個檔。
import './panels';

/**
 * React 只負責這些彈窗。★ 接縫 PR 後凍結，要動請開 issue。
 *
 * 角色走動、鏡頭捲動、[E] 提示都不在這裡 —— 那些每幀都在變的東西走
 * game/ 的命令式 DOM 更新，所以在場景裡跑來跑去時 React 一次都不會重繪。
 *
 * 原本這裡是一條 8 行的 `activePanel?.kind === 'xxx' && <Xxx />` 條件鏈：
 * 新增一個面板要改 3 檔 4 處，而且四個人同時加面板就是同一行的衝突。
 * 現在是查表，新增面板只剩 `panels/index.ts` 一行 append。
 */

/** 觸控裝置沒有 WASD 與 E 鍵，提示文字要換一套講法。 */
const coarse = matchMedia('(pointer: coarse)');
function useCoarsePointer(): boolean {
  return useSyncExternalStore(
    (cb) => {
      coarse.addEventListener('change', cb);
      return () => coarse.removeEventListener('change', cb);
    },
    () => coarse.matches,
  );
}

/**
 * 右下角的操作提示。**只有文字，沒有按鈕。**
 *
 * 這裡原本還有一顆「角色訊息窗」按鈕，但 HUD 那張左下角色卡
 * （`hud/blocks/ProfilePod.tsx`）做的是完全同一件事 —— 同樣 `openPanel('char')`、
 * 同樣標著 `I` 鍵。畫面上兩顆功能相同的按鈕本身就是雜訊，而且它站的位置
 * （右下）會把那一塊地板變成點不到的死區：世界是可以點擊移動的，HUD 每多
 * 佔一塊，可走的地方就少一塊。
 */
function HudHints() {
  const touch = useCoarsePointer();
  return (
    <div className="hud">
      <span className="hud-hint">
        {touch ? (
          <>點擊地面移動 · 點擊互動點自動前往</>
        ) : (
          <>
            <kbd>WASD</kbd> 移動 · <kbd>滑鼠</kbd> 點擊移動 · <kbd>E</kbd> 互動
          </>
        )}
      </span>
    </div>
  );
}

/** 進場畫面掛了就直接把人放進世界 —— 玩不到 boot 動畫遠比玩不到遊戲好。 */
function bootFailed(): void {
  setPhase('world');
  closePanel();
}

export function App() {
  const { activePanel, phase } = useUI();
  // 查不到就什麼都不渲染。openPanel() 已經先擋過一次，這裡是第二道 ——
  // validateWiring() 可能在開著面板時把它移除（例如熱更新後）。
  const def = activePanel ? getPanel(activePanel.kind) : null;

  /**
   * 查表落空時自我修復。
   *
   * `openPanel()` 守的是「進」的方向，這裡守「出」：`activePanel` 非 null 而
   * 查不到 def 時，畫面上沒有 `<Panel>`，也就沒有 ESC 監聽器（它掛在
   * `Panel.tsx` 的 useEffect 裡，隨元件掛載/卸載），但 `game/index.ts` 的
   * `frozen` 只看 `activePanel !== null` —— 於是世界被凍住、螢幕上什麼都沒有、
   * ESC 沒反應，只能重整。那正是 `uiStore.openPanel()` 註解宣稱已經消滅的死結，
   * 只是從另一個方向重現。
   */
  useEffect(() => {
    if (activePanel && !def) {
      console.error(`[ui] 面板「${activePanel.kind}」已不在註冊表中，自動關閉以免凍住世界`);
      closePanel();
    }
  }, [activePanel, def]);

  return (
    <>
      {/* Boot 也要有邊界：它在 #ui-root 這棵樹裡，渲染時丟例外會把整棵樹
          （面板與操作提示）一起帶走，只剩一個打不開任何東西的世界。
          它的「關掉它」必須順手把 phase 推回 'world'，否則 frozen 仍為真。 */}
      {phase !== 'world' && (
        <PanelBoundary onDismiss={bootFailed}>
          <BootScreen />
        </PanelBoundary>
      )}
      {phase === 'world' && <HudHints />}
      {def && activePanel && (
        <PanelBoundary key={activePanel.kind}>
          <def.Component ctx={activePanel.ctx} />
        </PanelBoundary>
      )}
    </>
  );
}

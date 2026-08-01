import { useEffect, useRef } from 'react';
import { FEATURES, type Feature, type FeatureGroup } from '../../features/registry';
import { openPanel, worldCommands } from '../../ui/uiStore';
import { setViewInset } from '../../engine/viewport';
import { openChatDock } from '../dockStore';

/**
 * 底部功能切換條 —— 世界的目錄。
 *
 * 這個世界的設計前提是「不同功能分在不同區域」。那個前提有一個代價：
 * **不知道有哪些區域的人，就不知道這裡能做什麼。** 走路探索是體驗，
 * 但評審只有幾分鐘，他不會走。
 *
 * 所以這條 bar 不是「另一套 UI」，它是同一個世界的索引：點一格不是直接
 * 開面板，而是**傳送過去、角色自己走到定位、然後跟走路過去一樣按 `E`**。
 * 選單是捷徑，世界仍然是容器 —— 這樣才不會出現「有選單之後就沒人走進
 * 世界」的結果，也不會有「用滑鼠會自己開、用鍵盤要按鍵」兩套規則。
 *
 * 資料全部來自 `features/registry.ts`（append 點 4/4）。隊友新增一個功能
 * 只要往那張表加一筆，這條 bar 自己會長出來，這個檔不用改。
 */

const GROUP_LABEL: Record<FeatureGroup, string> = {
  analysis: '分析',
  market: '市場',
  account: '帳戶',
  system: '交易所',
};

const ORDER: FeatureGroup[] = ['analysis', 'market', 'account', 'system'];

/** bar 的高度。同一個數字要餵給鏡頭，否則角色會走到 bar 底下不見了。 */
const BAR_H = 62;

function runFeature(f: Feature): void {
  const blocked = f.blocked?.();
  if (blocked) return;

  // MAIA 是非模態 dock，不是面板 —— 它不能走 openPanel，那會凍住世界。
  if (f.id === 'agentChat') {
    openChatDock();
    return;
  }
  if (f.run) {
    f.run();
    return;
  }

  /**
   * 有落點就走世界：傳送 → 走過去 → 站定顯示 `[E]` 提示。
   *
   * 刻意停在提示，不自動開面板 —— 這條 bar 是**導航**，不是快捷開啟。
   * 世界裡所有東西都是走近再按鍵，功能條只是幫你省下找路的時間。
   *
   * `goto` 由 `game/index.ts` 反向注入（`ui/` 不可 import `game/`）。
   * 注入還沒發生時退回直接開面板 —— 少一段動畫，但功能不會消失。
   */
  const goto = worldCommands().goto;
  if (f.place && goto) {
    goto(f.place.zone, f.place.wx, f.place.wy);
    return;
  }
  if (f.panel) openPanel(f.panel);
}

export function FeatureBar() {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const h = ref.current?.offsetHeight ?? BAR_H;
    setViewInset({ bottom: h });
    // 角色卡要疊在 bar 上方，高度只有這裡量得到 —— 用一個 CSS 變數傳過去，
    // 比在兩個檔案各寫一次 62px 好：這種數字遲早會有一邊忘了改。
    document.documentElement.style.setProperty('--fbar-h', `${h}px`);
    return () => setViewInset({ bottom: 0 });
  }, []);

  const groups = ORDER.map((g) => [g, FEATURES.filter((f) => f.group === g)] as const).filter(
    ([, list]) => list.length > 0,
  );

  return (
    <nav className="fbar" ref={ref} data-testid="feature-bar" aria-label="功能區域">
      {groups.map(([g, list]) => (
        <div className="fbar-group" key={g}>
          <span className="fbar-glabel">{GROUP_LABEL[g]}</span>
          <div className="fbar-slots">
            {list.map((f) => {
              const blocked = f.blocked?.() ?? null;
              return (
                <button
                  key={f.id}
                  className="fslot"
                  data-accent={f.accent}
                  disabled={blocked !== null}
                  title={blocked ?? `${f.label} — ${f.hint}`}
                  onClick={() => runFeature(f)}
                >
                  <span className="fslot-glyph">{f.glyph}</span>
                  <span className="fslot-label">{f.label}</span>
                  {f.place && (
                    <span className="fslot-go" aria-hidden="true">
                      ↗
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}

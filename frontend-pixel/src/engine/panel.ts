import type { ReactNode } from 'react';

/**
 * 面板契約（規格 §4.3）。
 *
 * 這個檔案刻意是**葉節點**：只 import react 的型別，不 import 任何面板、
 * 不 import uiStore。可註冊表（runtime table）放在這裡而不是放在
 * `ui/panels/index.ts`，是為了讓 `uiStore.openPanel()` 能查表卻不會
 * 產生 `uiStore → panels/index → 各面板 → uiStore` 這條執行期循環。
 *
 * 編譯期的型別安全仍然來自 barrel：`PanelId = keyof typeof PANELS`。
 * 這裡的表只負責兩件事：openPanel 的 no-op 守門、validateWiring 的移除。
 */

/** 所有面板收到的唯一參數。`ctx` 讓同一種面板可以針對不同對象各開一份。 */
export type PanelProps = { ctx?: string };

export type PanelDef = {
  /** 必須等於 barrel 裡的 key，validateWiring() 會比對 */
  id: string;
  /** 給 Deck 與除錯用的短名。畫面上的標題仍由元件自己的 <Panel title> 決定 */
  title: string;
  Component: (p: PanelProps) => ReactNode;
};

/** 純粹是型別輔助，讓面板檔案在自己內部就享有完整檢查。 */
export const definePanel = <T extends PanelDef>(p: T): T => p;

/**
 * 執行期註冊表。由 `ui/panels/index.ts` 在模組求值時灌進來。
 * 讀取端（uiStore / App / validate）只透過下面四個函式存取。
 */
const TABLE: Record<string, PanelDef> = {};

export function registerPanels(defs: Record<string, PanelDef>): void {
  for (const [id, def] of Object.entries(defs)) TABLE[id] = def;
}

export const getPanel = (id: string): PanelDef | null => TABLE[id] ?? null;

export const hasPanel = (id: string): boolean => Object.hasOwn(TABLE, id);

export const listPanels = (): [string, PanelDef][] => Object.entries(TABLE);

/**
 * 壞掉的面板是「被移除」不是 throw —— 白畫面在現場 demo 是致命的，
 * 少一個面板不是。移除之後 openPanel() 對它一律 no-op。
 */
export function unregisterPanel(id: string): void {
  delete TABLE[id];
}

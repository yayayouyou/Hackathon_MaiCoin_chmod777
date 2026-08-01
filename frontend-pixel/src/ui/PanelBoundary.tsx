import { Component, type ErrorInfo, type ReactNode } from 'react';
import { closePanel } from './uiStore';

type Props = {
  children: ReactNode;
  /**
   * 「關掉它」要做什麼。省略 = `closePanel()`（面板用）。
   * Boot 那一層要傳自己的版本 —— 光關面板不會把 `phase` 推回 `'world'`，
   * 世界仍然是凍的。
   */
  onDismiss?: () => void;
};
type State = { err: Error | null };

/**
 * React 樹的錯誤邊界。面板與 Boot 各包一層。
 *
 * 四個人平行開發面板，其中一個在台上丟例外時，預設行為是整棵 React 樹
 * 被卸載 —— `#ui-root` 變空，連 `.hud` 那行操作提示也一起消失，
 * 只剩一個動不了的世界。有了它，壞掉的只有那一個面板。
 *
 * 它不產生任何額外 DOM 節點（沒出錯時直接回 children），所以
 * `movement.mjs` 的「走動 2 秒 #ui-root 零變動」不受影響。
 */
export class PanelBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { err: null };
  }

  static getDerivedStateFromError(err: Error): State {
    return { err };
  }

  override componentDidCatch(err: Error, info: ErrorInfo): void {
    console.error('[panel] 面板渲染失敗', err, info.componentStack);
  }

  override render(): ReactNode {
    const { err } = this.state;
    if (!err) return this.props.children;
    const dismiss = this.props.onDismiss ?? closePanel;
    return (
      <div className="backdrop" onPointerDown={(e) => e.target === e.currentTarget && dismiss()}>
        <section className="panel panel-sm" data-accent="amber">
          <header className="panel-head">
            <h2>這個面板出錯了</h2>
            <button className="x" onClick={dismiss} aria-label="關閉">
              ✕
            </button>
          </header>
          <div className="panel-body">
            <div className="state err">
              <p>⚠ {err.message || '未知錯誤'}</p>
              <button className="btn" onClick={dismiss}>
                關掉它，世界照常運作
              </button>
            </div>
          </div>
          <footer className="panel-foot">
            <kbd>ESC</kbd> 關閉
          </footer>
        </section>
      </div>
    );
  }
}

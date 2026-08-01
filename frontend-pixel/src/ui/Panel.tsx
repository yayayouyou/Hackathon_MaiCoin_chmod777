import { useEffect, type ReactNode } from 'react';
import { closePanel } from './uiStore';

/**
 * 所有彈窗共用的殼：遮罩、標題列、ESC 關閉。
 *
 * ESC 掛在 document 上而不是元素上，因為焦點常常在面板內的輸入框裡，
 * 而遊戲的鍵盤處理刻意會跳過輸入框（否則打字會讓角色亂走）。
 */
export function Panel({
  title,
  accent = 'cyan',
  size = 'md',
  children,
}: {
  title: string;
  accent?: 'cyan' | 'amber' | 'violet' | 'green' | 'max';
  size?: 'sm' | 'md' | 'lg';
  children: ReactNode;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closePanel();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  return (
    <div className="backdrop" onPointerDown={(e) => e.target === e.currentTarget && closePanel()}>
      <section className={`panel panel-${size}`} data-accent={accent}>
        <header className="panel-head">
          <h2>{title}</h2>
          <button className="x" onClick={closePanel} aria-label="關閉">
            ✕
          </button>
        </header>
        <div className="panel-body">{children}</div>
        <footer className="panel-foot">
          <kbd>ESC</kbd> 關閉
        </footer>
      </section>
    </div>
  );
}

/** 三種資料狀態的統一外觀，讓每個面板不用各自發明一套。 */
export function AsyncState({
  loading,
  error,
  onRetry,
}: {
  loading: boolean;
  error: string | null;
  onRetry?: () => void;
}) {
  if (loading) {
    return (
      <div className="state">
        <span className="spinner" />
        載入中…
      </div>
    );
  }
  if (error) {
    return (
      <div className="state err">
        <p>⚠ {error}</p>
        {onRetry && (
          <button className="btn" onClick={onRetry}>
            重試
          </button>
        )}
      </div>
    );
  }
  return null;
}

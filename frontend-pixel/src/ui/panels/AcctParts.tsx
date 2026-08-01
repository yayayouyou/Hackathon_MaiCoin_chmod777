import { useState, type ReactNode } from 'react';

/**
 * 「我的帳戶」三個面板共用的零件。
 *
 * ⚠ **零新 CSS。** 全部沿用 `ui/styles.css` 既有的 class（`.split`／
 *   `.news-item`／`.pos-table`／`.badge`／`.toast`／`.up`／`.down`）。
 *   那個檔是接縫 PR 之後凍結的，而且此刻隊友正在同一個目錄下改別的東西 ——
 *   多開一個 CSS 檔換來的一致性，不值得多一個會衝突的共用檔。
 *   需要換色的地方（可信度徽章有三種顏色）用 inline style 蓋，只有三處。
 *
 * 這一區的設計主軸是**誠實**：後端幾乎每一支端點都會回「這份數字可不可信」
 * 的旗標（`reconcile.rows[].ok`、`positions[].basis_known_pct`、
 * `metrics[].sample_ok`），因為真實帳戶的常態就是對不齊。把可信的排前面、
 * 不可信的照樣列出來但講清楚為什麼 —— 藏起來才是真的扣分。
 */

// ── 數字格式 ────────────────────────────────────────────────

/** TWD 金額。整數 + 千分位；小於 1 元的殘渣直接收成 0，不要印 0.0001 佔一格。 */
export function twd(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '—';
  if (Math.abs(n) < 1) return '0';
  return Math.round(n).toLocaleString('en-US');
}

/** 幣的數量。位數依大小調整，否則 0.00000034 會被四捨五入成 0。 */
export function qty(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '—';
  const a = Math.abs(n);
  if (a >= 1000) return n.toLocaleString('en-US', { maximumFractionDigits: 2 });
  if (a >= 1) return n.toLocaleString('en-US', { maximumFractionDigits: 4 });
  return n.toLocaleString('en-US', { maximumFractionDigits: 8 });
}

export function pct(n: number | null | undefined, sign = true): string {
  if (n == null || !Number.isFinite(n)) return '—';
  return `${sign && n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
}

/** 漲跌配色。`0` 走中性 —— 把 0 染成綠色會讓「沒有變化」看起來像獲利。 */
export const signCls = (n: number | null | undefined): string =>
  n == null || !Number.isFinite(n) || n === 0 ? 'muted' : n > 0 ? 'up' : 'down';

/** 後端的時間戳一律毫秒（`_norm_ts_ms` 統一過）。 */
export function when(ms: number | null | undefined): string {
  if (!ms || !Number.isFinite(ms)) return '—';
  const d = new Date(ms);
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

// ── 可信度徽章 ──────────────────────────────────────────────

export type Trust = 'ok' | 'partial' | 'none';

const TRUST_COLOR: Record<Trust, string> = {
  ok: 'var(--green)',
  partial: 'var(--amber)',
  none: 'var(--dim)',
};

/**
 * 掛在數字旁邊的可信度標記。
 *
 * 它**必須貼著數字**，不能收在面板角落 —— 一個「未實現損益 -334」旁邊沒有
 * 任何標記的畫面，讀起來就是「這個數字是準的」。後端 `reconcile.note` 講得
 * 很白：API 成交歷史有起點、平台有未公開流水，所以更早的買入抓不到。
 * 那不是 bug，是資料的邊界，講出來比蓋掉可信。
 */
export function TrustBadge({ level, children }: { level: Trust; children: ReactNode }) {
  const c = TRUST_COLOR[level];
  return (
    <span className="badge" style={{ color: c, borderColor: c }}>
      <i style={{ background: c }} />
      {children}
    </span>
  );
}

/** 說明區塊。後端很多端點自帶 `note`，那些字是作者寫給使用者看的，照登。 */
export function Note({ children, warn }: { children: ReactNode; warn?: boolean }) {
  if (!children) return null;
  return (
    <div className="toast" data-err={warn ? 'true' : undefined} style={{ marginTop: 12 }}>
      {children}
    </div>
  );
}

// ── 版面零件 ────────────────────────────────────────────────

/** 一排 key/value 小方塊。對應後端 `dash-tiles`。 */
export function Tiles({ items }: { items: Array<{ k: string; v: ReactNode; cls?: string }> }) {
  if (!items.length) return null;
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
        gap: 8,
        marginBottom: 14,
      }}
    >
      {items.map((it) => (
        <div key={it.k} style={{ padding: '9px 11px', background: 'var(--panel-2)' }}>
          <span
            style={{
              display: 'block',
              fontSize: 10,
              letterSpacing: '0.1em',
              color: 'var(--dim)',
              marginBottom: 3,
            }}
          >
            {it.k}
          </span>
          <b className={it.cls ?? 'num'} style={{ fontSize: 14 }}>
            {it.v}
          </b>
        </div>
      ))}
    </div>
  );
}

/** 區塊標題。對應後端 `dash-sec`。 */
export function Sec({ children }: { children: ReactNode }) {
  return (
    <h3
      style={{
        fontSize: 10,
        letterSpacing: '0.16em',
        color: 'var(--dim)',
        margin: '18px 0 8px',
        fontWeight: 500,
      }}
    >
      {children}
    </h3>
  );
}

/** 頭條數字。一個面板只該有一個 —— 兩個就沒有頭條了。 */
export function Hero({
  label,
  value,
  cls,
  sub,
  badge,
}: {
  label: string;
  value: string;
  cls?: string;
  sub?: ReactNode;
  badge?: ReactNode;
}) {
  return (
    <div style={{ padding: '14px 16px', background: 'var(--panel-2)', marginBottom: 4 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
        <span style={{ fontSize: 10, letterSpacing: '0.16em', color: 'var(--dim)' }}>{label}</span>
        {badge}
      </div>
      <b className={`num ${cls ?? ''}`} style={{ fontSize: 26, lineHeight: 1.1 }}>
        {value}
      </b>
      {sub && <div style={{ marginTop: 6, fontSize: 12, color: 'var(--dim)' }}>{sub}</div>}
    </div>
  );
}

// ── 左選單 ──────────────────────────────────────────────────

export type Section = {
  id: string;
  /** 選單上的分類名 */
  label: string;
  /** 分類名底下那行小字，回答「這一頁是什麼」 */
  hint: string;
  render: () => ReactNode;
};

/**
 * 左選單 + 右內容，與 agent_ui 的 `acct-layout` 同構。
 *
 * ⚠ **只渲染選中的那一頁**，這不是省效能而是必要的：`/api/behavior` 要重播
 *   整本帳本，實測數秒；八頁一次全掛上去等於一開面板就同時打八支慢端點。
 *   每一頁各自在自己 mount 時才 `useAsync` —— 切過去才開始抓。
 */
export function AcctSplit({ sections }: { sections: Section[] }) {
  const [sel, setSel] = useState(0);
  const active = sections[Math.min(sel, sections.length - 1)];
  if (!active) return <div className="empty">沒有可顯示的分類</div>;

  return (
    <div className="split">
      <nav>
        {sections.map((s, i) => (
          <button
            key={s.id}
            className="news-item"
            aria-selected={i === sel}
            onClick={() => setSel(i)}
          >
            <span className="t">{s.label}</span>
            <span className="k" style={{ color: 'var(--dim)', letterSpacing: 0 }}>
              {s.hint}
            </span>
          </button>
        ))}
      </nav>
      <article key={active.id}>{active.render()}</article>
    </div>
  );
}

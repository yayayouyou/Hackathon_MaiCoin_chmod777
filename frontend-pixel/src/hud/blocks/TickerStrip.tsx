import { useEffect, useRef } from 'react';
import { hud, type Ticker } from '../channels';
import { TICKER_MARKETS } from '../ticker-config';
import { LiveText } from '../LiveText';
import { setViewInset } from '../../engine/viewport';

/**
 * 畫面最上方的行情跑馬燈。
 *
 * 它做兩件事，第二件才是重點：
 * ① 把即時報價放在不用走過去、不用開任何東西就看得到的位置
 * ② **讓這個世界看起來是活的**。像素世界最怕的評語是「這只是一張很漂亮的
 *    靜態圖」—— 一條持續橫向捲動、數字每 5 秒真的會換的 bar，是最便宜的
 *    反證。動畫本身純 CSS transform，不碰 DOM，所以它不佔任何一幀的 JS。
 *
 * ⚠ 骨架**必須是固定的**：幣種清單來自 `ticker-config.ts` 的白名單，
 *   順序固定。若改成「拿到什麼就 render 什麼」，React 會在每次輪詢重建
 *   整條 bar 的 DOM —— 那正是 `#hud-root` childList 變動必須維持 0 的反面。
 *   數字全部走 `<LiveText>`，React 從掛載之後就沒再參與過。
 */

/** bar 的高度。同一個數字要餵給鏡頭與 dock 的 top，所以只寫在這裡一次。 */
const STRIP_H = 28;

const pick = (v: Ticker[], id: string): Ticker | undefined =>
  v.find((t) => `${t.sym}${t.quote}`.toLowerCase() === id);

/**
 * 台幣報價的位數：貴的幣不要小數（3,412,000 後面掛 .47 只是雜訊），
 * 便宜的幣不給小數就全部變成 6 跟 0。門檻取 1000。
 */
function fmtPrice(n: number): string {
  if (n >= 1000) return Math.round(n).toLocaleString('en-US');
  if (n >= 1) return n.toFixed(2);
  return n.toFixed(6);
}

/**
 * `fmt` / `color` 必須是**穩定的函式參考**，否則 `LiveText` 的 effect
 * 每次重繪都會退訂重訂。所以這裡照 market id 建一次就快取起來，
 * 而不是在 JSX 裡寫 inline 箭頭函式。
 */
const priceFns = new Map<string, (v: Ticker[]) => string>();
const changeFns = new Map<string, (v: Ticker[]) => string>();
const colorFns = new Map<string, (v: Ticker[]) => string>();

function priceFn(id: string) {
  let f = priceFns.get(id);
  if (!f) {
    f = (v) => {
      const t = pick(v, id);
      return t ? fmtPrice(t.last) : '—';
    };
    priceFns.set(id, f);
  }
  return f;
}

function changeFn(id: string) {
  let f = changeFns.get(id);
  if (!f) {
    f = (v) => {
      const t = pick(v, id);
      if (!t) return '';
      const s = t.change_pct;
      return `${s >= 0 ? '+' : ''}${s.toFixed(2)}%`;
    };
    changeFns.set(id, f);
  }
  return f;
}

/**
 * 顏色是 attribute 變動（`style.color`），`LiveText` 已經先 diff 過，
 * 所以只有漲跌**方向真的翻轉**時才會寫一次，不是每次報價都寫。
 */
function colorFn(id: string) {
  let f = colorFns.get(id);
  if (!f) {
    f = (v) => {
      const t = pick(v, id);
      if (!t) return 'var(--dim)';
      return t.change_pct >= 0 ? 'var(--green)' : 'var(--rose)';
    };
    colorFns.set(id, f);
  }
  return f;
}

/** 徽章文字：依 hud.meta.source 動態切換 */
const badgeFmt = (meta: { source: string }): string => {
  switch (meta.source) {
    case 'live':
      return 'MAX · 即時';
    case 'sample':
      return 'MAX · 快照';
    default:
      return 'MAX · 模擬';
  }
};

function Row() {
  return (
    <>
      {TICKER_MARKETS.map((m) => (
        <span className="tk-item" key={m.id}>
          <span className="tk-sym">{m.base}/{m.quote}</span>
          <LiveText className="tk-price" ch={hud.tickers} fmt={priceFn(m.id)} />
          <LiveText className="tk-chg" ch={hud.tickers} fmt={changeFn(m.id)} color={colorFn(m.id)} />
        </span>
      ))}
    </>
  );
}

export function TickerStrip() {
  const ref = useRef<HTMLDivElement>(null);
  const badgeRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const h = ref.current?.offsetHeight ?? STRIP_H;
    setViewInset({ top: h });
    document.documentElement.style.setProperty('--ticker-h', `${h}px`);
    return () => setViewInset({ top: 0 });
  }, []);

  // 訂閱 hud.meta 更新徽章文字（不走 React state，與 LiveText 同理）
  useEffect(() => {
    const write = (meta: { source: string }): void => {
      const el = badgeRef.current;
      if (!el) return;
      const s = badgeFmt(meta);
      if (el.textContent !== s) el.textContent = s;
    };
    write(hud.meta.get());
    return hud.meta.sub(write);
  }, []);

  return (
    <div className="tk" ref={ref} data-testid="ticker-strip">
      {/*
        兩份一模一樣的內容 + `translateX(-50%)` 的動畫 = 無縫接回開頭。
        少了第二份，跑到底時會出現一段空白再瞬間跳回去。
        兩份都綁同一條通道，所以捲到哪一份看到的都是同一個即時數字。
      */}
      <div className="tk-track">
        <div className="tk-row">
          <Row />
        </div>
        <div className="tk-row" aria-hidden="true">
          <Row />
        </div>
      </div>
      <span className="tk-badge" ref={badgeRef}>MAX · 模擬</span>
    </div>
  );
}

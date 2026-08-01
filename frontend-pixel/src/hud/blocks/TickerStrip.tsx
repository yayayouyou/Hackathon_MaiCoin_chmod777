import { useEffect, useRef } from 'react';
import { hud, type Ticker } from '../channels';
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
 * ⚠ 骨架**必須是固定的**：幣種清單寫死在 `feeds.ts` 的 SYMS，這裡照著它
 *   查表。若改成「拿到什麼就 render 什麼」，React 會在每次輪詢重建整條
 *   bar 的 DOM —— 那正是 `#hud-root` childList 變動必須維持 0 的反面。
 *   數字全部走 `<LiveText>`，React 從掛載之後就沒再參與過。
 */

const SYMS = ['BTC', 'ETH', 'USDT', 'SOL', 'DOGE', 'MAX'] as const;

/** bar 的高度。同一個數字要餵給鏡頭與 dock 的 top，所以只寫在這裡一次。 */
const STRIP_H = 28;

const pick = (v: Ticker[], sym: string): Ticker | undefined => v.find((t) => t.sym === sym);

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
 * 每次重繪都會退訂重訂。所以這裡照幣種建一次就快取起來，
 * 而不是在 JSX 裡寫 inline 箭頭函式。
 */
const priceFns = new Map<string, (v: Ticker[]) => string>();
const changeFns = new Map<string, (v: Ticker[]) => string>();
const colorFns = new Map<string, (v: Ticker[]) => string>();

function priceFn(sym: string) {
  let f = priceFns.get(sym);
  if (!f) {
    f = (v) => {
      const t = pick(v, sym);
      return t ? fmtPrice(t.last) : '—';
    };
    priceFns.set(sym, f);
  }
  return f;
}

function changeFn(sym: string) {
  let f = changeFns.get(sym);
  if (!f) {
    f = (v) => {
      const t = pick(v, sym);
      if (!t) return '';
      const s = t.change_pct;
      return `${s >= 0 ? '+' : ''}${s.toFixed(2)}%`;
    };
    changeFns.set(sym, f);
  }
  return f;
}

/**
 * 顏色是 attribute 變動（`style.color`），`LiveText` 已經先 diff 過，
 * 所以只有漲跌**方向真的翻轉**時才會寫一次，不是每次報價都寫。
 */
function colorFn(sym: string) {
  let f = colorFns.get(sym);
  if (!f) {
    f = (v) => {
      const t = pick(v, sym);
      if (!t) return 'var(--dim)';
      return t.change_pct >= 0 ? 'var(--green)' : 'var(--rose)';
    };
    colorFns.set(sym, f);
  }
  return f;
}

function Row() {
  return (
    <>
      {SYMS.map((sym) => (
        <span className="tk-item" key={sym}>
          <span className="tk-sym">{sym}</span>
          <LiveText className="tk-price" ch={hud.tickers} fmt={priceFn(sym)} />
          <LiveText className="tk-chg" ch={hud.tickers} fmt={changeFn(sym)} color={colorFn(sym)} />
        </span>
      ))}
    </>
  );
}

export function TickerStrip() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const h = ref.current?.offsetHeight ?? STRIP_H;
    setViewInset({ top: h });
    // dock 是 `top: 0` 的，沒有這個變數它會被行情條蓋住標題列。
    document.documentElement.style.setProperty('--ticker-h', `${h}px`);
    return () => setViewInset({ top: 0 });
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
      <span className="tk-badge">MAX · 即時</span>
    </div>
  );
}

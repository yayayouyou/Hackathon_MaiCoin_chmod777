import { useEffect, useRef } from 'react';
import type { Live } from './live';

/**
 * 綁在一條 live 通道上的一段文字。**全程不 setState。**
 *
 * 這是 HUD 唯一被允許「跳動」的東西。行情每 5 秒換一次數字，若走 React
 * state，一條六檔的行情條就會每 5 秒把整片 HUD 重繪一次 —— 而世界正在
 * 旁邊用同一顆 CPU 跑 60fps。這裡只寫 `textContent`，React 從掛載之後
 * 就再也沒有參與過。
 *
 * ⚠ `fmt` 與 `color` **必須是模組層的穩定函式**。寫成 inline 箭頭函式的話
 *   每次 render 都是新的參考，effect 會跟著退訂重訂，等於每次重繪都斷一次
 *   訂閱 —— 症狀是數字偶爾卡住不動，而且很難重現。
 *
 * ⚠ 兩處都先 diff 再寫。`tests/hud.mjs` 守的是 childList 與 attributes 的
 *   變動次數，characterData 可以 >0；但 `style.color` 是 **attribute**，
 *   所以顏色只在漲跌方向真的翻轉時才寫一次，不是每次報價都寫。
 */
export function LiveText<T>({
  ch,
  fmt,
  color,
  className,
}: {
  ch: Live<T>;
  fmt: (v: T) => string;
  color?: (v: T) => string;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const write = (v: T): void => {
      const el = ref.current;
      if (!el) return;
      const s = fmt(v);
      if (el.textContent !== s) el.textContent = s;
      if (color) {
        const c = color(v);
        if (el.style.color !== c) el.style.color = c;
      }
    };
    write(ch.get()); // 掛載時先補一次，否則要等下一次推送才有字
    return ch.sub(write);
  }, [ch, fmt, color]);

  return <span ref={ref} className={className} />;
}

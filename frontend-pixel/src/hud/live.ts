/**
 * HUD 的資料通道（規格 §7.3）。零相依，不 import 任何東西。
 *
 * 為什麼不用 useState：`#hud-root` 裡的行情、損益、agent 計時器都是
 * 每秒甚至每幀在跳的數值，走 React 會讓「每幀變動的東西不進 React」
 * （附錄 B 規則 4）這條鐵律破功。骨架用 React 畫一次，數值走
 * `<LiveText>` 只寫 textContent。
 */
export type Live<T> = { get(): T; set(v: T): void; sub(fn: (v: T) => void): () => void };

export function live<T>(init: T): Live<T> {
  let v = init;
  const subs = new Set<(v: T) => void>();
  return {
    get: () => v,
    set(next) {
      if (Object.is(next, v)) return;
      v = next;
      for (const f of subs) f(v);
    },
    sub(fn) {
      subs.add(fn);
      return () => void subs.delete(fn);
    },
  };
}

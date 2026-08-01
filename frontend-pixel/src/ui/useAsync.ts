import { useCallback, useEffect, useState } from 'react';

export type Async<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
};

/**
 * 取代 react-query 的 40 行版本。這個專案只需要「抓一次」與「定時重抓」。
 *
 * 定時重抓時刻意不把 loading 翻回 true、也不清掉舊資料 ——
 * 否則行情每 3 秒就會整個列表消失變成轉圈圈，捲動位置也會歸零。
 * 錯誤同理：連線瞬斷時保留最後一次的價格，只在旁邊標示異常。
 */
export function useAsync<T>(
  /**
   * 取數函式。收到的 `signal` 在**卸載、重抓、切 deps** 時都會 abort ——
   * 傳給 fetch 就能讓在途請求真的被放棄。
   *
   * 不傳也完全正常（既有呼叫端全都寫成 `() => getRooms()`，參數少一個在
   * TypeScript 是合法的），差別只在請求會跑完才被 `alive` 擋掉結果。
   * 對 120ms 的 mock 無所謂，對 `/api/positions` 這種要重播整本帳本、
   * 數秒級的端點就是白燒後端。
   */
  fn: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[],
  opts?: { intervalMs?: number },
): Async<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const intervalMs = opts?.intervalMs;

  useEffect(() => {
    let alive = true;
    let first = true;
    const ac = new AbortController();

    const run = async () => {
      if (first) setLoading(true);
      try {
        const res = await fn(ac.signal);
        if (!alive) return;
        setData(res);
        setError(null);
      } catch (e) {
        if (!alive) return;
        // 自己 abort 掉的不是錯誤，不要在畫面上留一行紅字給使用者看
        if (ac.signal.aborted) return;
        setError(e instanceof Error ? e.message : '未知錯誤');
        if (first) setData(null);
      } finally {
        if (alive && first) {
          setLoading(false);
          first = false;
        }
      }
    };

    void run();
    if (!intervalMs) return () => { alive = false; ac.abort(); };
    const id = setInterval(() => void run(), intervalMs);
    return () => {
      alive = false;
      ac.abort();
      clearInterval(id);
    };
    // fn 每次 render 都是新的 function，靠呼叫端給的 deps 決定何時重抓
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce, intervalMs]);

  return { data, loading, error, reload };
}

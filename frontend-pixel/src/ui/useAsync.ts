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
  fn: () => Promise<T>,
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

    const run = async () => {
      if (first) setLoading(true);
      try {
        const res = await fn();
        if (!alive) return;
        setData(res);
        setError(null);
      } catch (e) {
        if (!alive) return;
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
    if (!intervalMs) return () => { alive = false; };
    const id = setInterval(() => void run(), intervalMs);
    return () => {
      alive = false;
      clearInterval(id);
    };
    // fn 每次 render 都是新的 function，靠呼叫端給的 deps 決定何時重抓
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce, intervalMs]);

  return { data, loading, error, reload };
}

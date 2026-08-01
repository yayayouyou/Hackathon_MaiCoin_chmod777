import { FLAGS } from '../game/core';

/**
 * 玩家帳號 API。
 *
 * `credentials: 'same-origin'`（也是 fetch 的預設）而不是 `'include'`：本專案的
 * 前後端**永遠同源** —— 開發走 vite 的 `/api` proxy，部署走 CloudFront 的 `/api/*`
 * behavior。寫死 same-origin 等於把這個架構前提編碼進來：真的有人把前端搬到別的
 * 網域時，症狀會是「cookie 沒帶上」而不是悄悄改用需要 CORS 的路徑。
 *
 * （後端 `tests/test_app_security.py` 有一條測試明文擋著 CORSMiddleware，
 *   原因相同 —— 核准端點的 CSRF 防線建立在同源政策上。）
 */

export type Player = {
  username: string;
  nickname: string;
  character: string;
  stance: string;
  favorites: string[];
  created_at: string;
};

export type Progress = {
  nickname?: string;
  character?: string;
  stance?: string;
  favorites?: string[];
};

/** `?fast=1` 的假玩家。測試與離線錄影都不該需要後端。 */
const CANNED: Player = {
  username: 'demo', nickname: '', character: '', stance: '',
  favorites: [], created_at: '',
};

/**
 * FastAPI 的錯誤格式是 `{"detail": "..."}`。把它抽出來當 Error.message，
 * 這樣畫面上顯示的就是後端寫好的中文訊息，不是「HTTP 409」。
 */
async function fail(res: Response): Promise<never> {
  let detail = `連線異常（HTTP ${res.status}）`;
  try {
    const body: unknown = await res.json();
    if (body && typeof body === 'object' && typeof (body as { detail?: unknown }).detail === 'string') {
      detail = (body as { detail: string }).detail;
    }
  } catch {
    /* 回應不是 JSON（例如代理層的 502 HTML）就用預設訊息 */
  }
  throw new Error(detail);
}

async function post(path: string, body?: unknown): Promise<Response> {
  return fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

/**
 * 目前登入的玩家；未登入回 `null`（後端回 401，那是預期狀態不是錯誤）。
 *
 * 帶 5 秒逾時：這支是進場畫面的第一個動作，後端沒起來或網路掛掉時，
 * 沒有逾時就會**永遠停在「確認登入狀態…」** —— 正是 BootScreen 的三個
 * 逃生口想避免的那種「卡在第一個畫面」。逾時後當作未登入，人還進得去。
 */
export async function me(): Promise<Player | null> {
  if (FLAGS.fast) return CANNED;
  const res = await fetch('/api/auth/me', {
    credentials: 'same-origin',
    signal: AbortSignal.timeout(5000),
  });
  if (res.status === 401) return null;
  if (!res.ok) return fail(res);
  return (await res.json()).player as Player;
}

export async function register(username: string, password: string): Promise<Player> {
  if (FLAGS.fast) return CANNED;
  const res = await post('/api/auth/register', { username, password });
  if (!res.ok) return fail(res);
  return (await res.json()).player as Player;
}

export async function login(username: string, password: string): Promise<Player> {
  if (FLAGS.fast) return CANNED;
  const res = await post('/api/auth/login', { username, password });
  if (!res.ok) return fail(res);
  return (await res.json()).player as Player;
}

export async function logout(): Promise<void> {
  if (FLAGS.fast) return;
  await post('/api/auth/logout');
}

/**
 * 儲存世界進度。**刻意吞掉錯誤**：呼叫點是 `state.ts` 的偏好寫入，
 * 存不進去時使用者仍該能繼續玩（localStorage 那份還在），
 * 為了一次背景同步失敗跳錯誤視窗是本末倒置。
 */
export async function saveProgress(progress: Progress): Promise<void> {
  if (FLAGS.fast) return;
  try {
    await fetch('/api/auth/progress', {
      method: 'PUT',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(progress),
    });
  } catch {
    /* 離線或後端沒起來 */
  }
}

import { saveProgress, type Progress } from './api/auth';

export type Creds = { access: string; secret: string };

const NICK_KEY = 'goodui.nickname';
const FAV_KEY = 'goodui.favorites';
const CHAR_KEY = 'goodui.character';

/**
 * 世界進度的伺服器同步。
 *
 * 掛在這裡而不是 `ui/uiStore.ts`，理由是下面那段註解已經立好的規矩：
 * **localStorage 的存取一律走這幾個函式**。所有進度寫入本來就都經過它們，
 * 於是「同步到 DynamoDB」變成一個掛勾點而不是散落在每個呼叫點的重複程式碼 ——
 * 而且 `uiStore.ts` 是凍結檔（SPEC 規則 1），一行都不用動。
 *
 * localStorage 從此降級為本機快取：登入後以伺服器那份為準，未登入時它仍是
 * 唯一的來源（訪客不必註冊也能玩，只是換裝置就不見）。
 */
let authed = false;
let hydrating = false;
let pending: Progress = {};
let syncTimer = 0;

/** 登入/登出時由 `boot/LoginPanel.tsx` 呼叫。未登入時所有同步都是 no-op。 */
export function setAuthed(v: boolean): void {
  authed = v;
}

/**
 * 把伺服器那份進度灌進本機時，包在這裡面呼叫。
 *
 * 沒有這道閘門會發生：登入 → 讀到伺服器的暱稱 → 寫進 localStorage →
 * 觸發同步 → 把剛讀到的值再 PUT 回去。功能上無害，但每次登入都多一次沒有
 * 意義的寫入，而且在網路差的時候會跟使用者接下來的真正修改互相覆蓋。
 */
export function hydrate(fn: () => void): void {
  hydrating = true;
  try {
    fn();
  } finally {
    hydrating = false;
  }
}

/**
 * 累積 400ms 再送。改暱稱是逐字觸發的，沒有 debounce 就是每按一個鍵打一次 API。
 * 累積成單一 patch 而不是排隊多個請求，避免後送的舊值蓋掉先送的新值。
 */
function sync(patch: Progress): void {
  if (!authed || hydrating) return;
  Object.assign(pending, patch);
  clearTimeout(syncTimer);
  syncTimer = setTimeout(() => {
    const payload = pending;
    pending = {};
    void saveProgress(payload);
  }, 400) as unknown as number;
}

/**
 * 交易所金鑰只活在這個模組變數裡，絕不寫進 localStorage。
 *
 * 交易所 API Key 放在瀏覽器本來就不安全：任何一個 XSS 都能把它讀走，
 * 等於交出帳戶。寫進 localStorage 只是讓這個風險從「分頁存活期間」
 * 延長成「永久」。真正要接 MAX API 時，簽名應該在自己的後端做，
 * 金鑰永遠不進瀏覽器；這裡的表單只是先把 UI 的閘門邏輯做出來。
 */
let creds: Creds | null = null;

export function getCreds(): Creds | null {
  return creds;
}

export function setCreds(c: Creds | null): void {
  creds = c;
}

/**
 * localStorage 的存取一律走這兩個函式。
 *
 * 不只是「配額爆掉」而已：Safari 無痕、被封鎖 storage access 的 iframe 嵌入、
 * 企業瀏覽器政策底下，連讀 `window.localStorage` 這個 getter 本身就會丟
 * `SecurityError`。而 `ui/uiStore.ts` 在 **module 頂層**呼叫 `loadNickname()`，
 * uiStore 又被 `game/index.ts` 與 `ui/App.tsx` 兩邊 import —— 沒包起來的話，
 * 評審用哪個瀏覽器開我們的 Live Demo 網址，就決定他看到的是世界還是白畫面。
 *
 * 失敗一律靜默降級（讀不到 = null、寫不進去 = 這輪偏好只活在記憶體裡），
 * 不 console.error：這不是接線錯誤，是使用者環境，紅燈在這裡沒有意義。
 */
function safeGet(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeSet(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* 存不了就算了 */
  }
}

export function loadNickname(): string {
  const saved = safeGet(NICK_KEY);
  if (saved) return saved;
  // 隨機產生的預設暱稱要當場存起來，否則每次重整都會換一個名字，
  // 討論串裡的留言看起來就會像是別人發的。
  const fresh = `遊客${Math.floor(1000 + Math.random() * 9000)}`;
  safeSet(NICK_KEY, fresh);
  return fresh;
}

export function saveNickname(n: string): void {
  safeSet(NICK_KEY, n);
  sync({ nickname: n });
}

/**
 * 選好的角色。回傳 `string` 而不是 `CharacterId` —— 存進去的是上一個版本
 * 的人選的，角色表改過之後那個 id 可能已經不存在了。合法性由
 * `art/characters.ts` 的 `getCharacter()` 負責（查不到退回預設）。
 */
export function loadCharacter(): string {
  return safeGet(CHAR_KEY) ?? '';
}

export function saveCharacter(id: string): void {
  safeSet(CHAR_KEY, id);
  sync({ character: id });
}

/** 收藏是純偏好設定，不敏感，存 localStorage 讓重整後還在。 */
export function loadFavorites(): string[] {
  try {
    const raw = safeGet(FAV_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === 'string') : [];
  } catch {
    return [];
  }
}

export function saveFavorites(f: readonly string[]): void {
  safeSet(FAV_KEY, JSON.stringify(f));
  sync({ favorites: [...f] });
}

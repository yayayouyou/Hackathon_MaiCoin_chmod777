export type Creds = { access: string; secret: string };

const NICK_KEY = 'goodui.nickname';
const FAV_KEY = 'goodui.favorites';
const CHAR_KEY = 'goodui.character';

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
}

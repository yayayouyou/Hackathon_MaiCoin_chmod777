import type { Accent, Room } from '../world/types';
import type { PanelId } from '../ui/panels';

/**
 * Zone 契約（規格 §4.3）。
 *
 * 一個 zone = 一塊可以獨立開發的區域：它自己決定房間長什麼樣、進場要載
 * 什麼資料、在中庭有沒有門。新增一個 zone 只要新資料夾 + `zones/index.ts`
 * 一行 append，不必再去改 `game/index.ts` 的 swapRoom。
 */

/** zone 之間傳遞的參數。討論室的 roomId、DNA 室的幣種都走這裡。 */
export type ZoneParams = Record<string, string | number | boolean>;

export type ZoneCtx = {
  id: string;
  params: ZoneParams;
  /** 從哪個 zone 走過來。開場是 null */
  from: string | null;
};

export type ZoneRuntime = {
  room: Room;
  /**
   * 非同步回來時玩家可能已經換場了。所有 .then() 都要包這個。
   * 這取代了 game/index.ts 那段硬編的 `if (room.id === 'discussion')` ——
   * 那個判斷只認房間種類，同一種房間換到另一間時會把上一間的留言灌進來。
   */
  ifStillHere: (fn: () => void) => void;
  /**
   * 換場時自動 abort。輪詢與 fetch 都要吃它，否則離開房間還在打 API。
   * `api/` 的函式收 `signal?` 當最後一個參數，參考實作見
   * `world/zones/discussion/index.ts` 的 `getThread(roomId, rt.signal)`。
   */
  signal: AbortSignal;
  /** 餵 NPC 對話泡泡。空陣列 = 這個房間沒人講話 */
  setChatter: (lines: string[]) => void;
};

/**
 * 這個區塊在中庭的門面。宣告了就自動長出一道門，
 * 完全不必去改中庭的房間定義 —— 這消滅了「門座標在 props 與 portals
 * 各寫一次、型別守不到、抄錯的症狀是看得到門但走過去沒反應」這個地雷。
 *
 * ⚠ 這一輪（接縫 PR）中庭還沒有自動配位，兩道既有的門仍然寫在
 *   `world/rooms.ts` 裡。這裡宣告的 `pinned` 由 `tests/zones.mjs` 比對，
 *   對不上就是紅燈 —— 在自動配位落地之前，測試就是那份契約。
 */
export type ZoneGateway = {
  /** 門牌上的名字。2–6 個字 —— 名牌寬度上限 128px */
  label: string;
  enterLabel?: string;
  accent: Accent;
  /**
   * 只有既有兩道門會用（它們的座標被 12 項測試鎖死）。
   * 新 zone 一律不填，由中庭依 zone id 字母序自動配位 ——
   * 讓人自己選 slot 編號會產生「兩個 zone 搶同一格 → 兩道門重疊
   * → 其中一道永遠打不開 → git 零衝突、TS 零錯誤」的靜默失敗。
   */
  pinned?: { x: number; y: number };
  /** 省略 = travel 到這個 zone。也可以先開一個選擇面板（討論區就是這樣） */
  action?: { type: 'panel'; panel: PanelId };
};

export type ZoneDef = {
  /** 必須等於 barrel 裡的 key，validateWiring() 會比對 */
  id: string;
  title: string;
  accent: Accent;
  /**
   * 建房間。每次進場呼叫一次，可以依 params 參數化 ——
   * 12 間討論室共用一個 zone 就是靠這個。
   * ⚠ 必須能在「空 params」下建得起來（validateWiring 會這樣試），
   *   而且 `room.id` 必須等於 zone id。
   * ⚠ build 內才可以呼叫 listZones()，module 層呼叫會拿到不完整的表。
   */
  build: (ctx: ZoneCtx) => Room;
  /** 進場副作用：載資料、餵 NPC 台詞、開輪詢。回傳 cleanup。 */
  onEnter?: (ctx: ZoneCtx, rt: ZoneRuntime) => void | (() => void);
  gateway?: ZoneGateway;
};

/** 純粹是型別輔助，讓 zone 檔案在自己內部就享有完整檢查。 */
export const defineZone = <T extends ZoneDef>(z: T): T => z;

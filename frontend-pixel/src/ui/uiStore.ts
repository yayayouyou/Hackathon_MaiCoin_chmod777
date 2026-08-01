import { useSyncExternalStore } from 'react';
import type { Accent, SceneId } from '../world/types';
import { getCharacter, type CharacterId } from '../art/characters';
import type { ZoneId } from '../world/zones';
import type { ZoneParams } from '../engine/zone';
import { hasPanel } from '../engine/panel';
import type { PanelId } from './panels';
import {
  loadCharacter,
  loadFavorites,
  loadNickname,
  saveCharacter,
  saveFavorites,
  saveNickname,
} from '../state';
import { DEFAULT_STANCE, type StanceId } from '../boot/stances';

/**
 * 遊戲與 React 之間唯一的橋。★ 接縫 PR 後凍結，要動請開 issue。
 *
 * 這裡刻意只放「以人類速度變動」的狀態：面板開關、場景、暱稱、收藏。
 * 角色座標、互動提示位置這些每幀都在變的東西一律不放進來 ——
 * 它們走 game/worldLabels.ts 的命令式 DOM 更新，React 完全不參與。
 * HUD 上跳動的數值也不放這裡，走 `hud/channels.ts` 的 live 通道。
 */
export type UIState = {
  // ── 既有 7 個 ──
  activePanel: { kind: PanelId; ctx?: string } | null;
  scene: SceneId;
  /** 目前所在的討論室 id，其他場景為 null */
  roomId: string | null;
  roomTitle: string;
  nickname: string;
  favorites: string[];
  /** 只暴露「有沒有連接」，金鑰本身留在 state.ts 不進 React */
  connected: boolean;

  // ── 接縫 PR 一次加齊的 4 個 ──
  /**
   * `game/index.ts` 的 `frozen` 條件含 `phase !== 'world'` —— 進場畫面蓋著
   * 的時候角色本來就不該能動，這正是要的行為。預設值由旗標決定，見
   * `initialPhase()`。
   *
   * ⚠ `'entering'` 目前沒有人設。進場的過場交給 `world.enter()` 播的光圈
   *   （光圈期間 `transition !== null` 已經把輸入凍住了），再多一個狀態只是
   *   同一件事寫兩遍。留著是因為它是既有型別的一部分，不是這次要動的東西。
   */
  phase: 'boot' | 'entering' | 'world';
  stance: StanceId;
  /** 玩家選的角色外觀。只影響長相，不影響任何行為 */
  character: CharacterId;
  /**
   * 非模態疊層（Deck / HUD 互動）開啟時要凍結遊戲輸入，
   * 否則會出現「你在選單裡點東西，角色在背後被傳走」。
   */
  inputCaptured: boolean;
  deckOpen: boolean;
};

/**
 * 開場要不要蓋進場畫面。
 *
 * `?fast=1` 是全站的測試／錄影旗標，178 項 e2e 全部帶著它跑，而
 * `harness.openPage` 的假設是「載入完 900ms 就站在可操作的大廳」——
 * 進場畫面一蓋上去，每一支測試都會停在第一步。所以帶 `fast` 就直接進世界。
 *
 * `?boot=1` 是給「要測進場畫面本身」的那一支用的：它得跟其他套件一樣關掉
 * HUD 輪詢（否則 `waitUntil:'networkidle'` 永不觸發），但又需要看到畫面。
 * 兩件事各一個旗標，比讓 `fast` 身兼二職清楚。
 */
function initialPhase(): UIState['phase'] {
  const q = new URLSearchParams(location.search);
  return q.has('boot') || !q.has('fast') ? 'boot' : 'world';
}

let state: UIState = {
  activePanel: null,
  scene: 'lobby',
  roomId: null,
  roomTitle: '',
  nickname: loadNickname(),
  favorites: loadFavorites(),
  connected: false,
  phase: initialPhase(),
  stance: DEFAULT_STANCE,
  character: getCharacter(loadCharacter()).id,
  inputCaptured: false,
  deckOpen: false,
};

const listeners = new Set<() => void>();

function set(patch: Partial<UIState>): void {
  state = { ...state, ...patch };
  for (const fn of listeners) fn();
}

export function getUI(): UIState {
  return state;
}

function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function useUI(): UIState {
  return useSyncExternalStore(subscribe, getUI);
}

// ── 面板 ────────────────────────────────────────────────────

/**
 * 未註冊的 panel id 一律 no-op（規格 §9）。
 *
 * 絕不能讓 `activePanel` 被設成一個渲染不出東西的值：那會造成「面板打不開
 * 但世界被 frozen 凍住、也沒有面板可以按 ESC 關」的死結，只能重整 ——
 * 而現場 demo 重整一次就等於這一段演砸了。
 *
 * 參數型別是 `string` 而不是 `PanelId`：呼叫端有一半來自房間資料
 * （`Interactable.panel`），那邊已經是 PanelId 了；這裡守的是執行期
 * 才決定的那一半（Deck 的搜尋結果、agent 回傳的 deeplink）。
 */
export function openPanel(kind: string, ctx?: string): void {
  if (!hasPanel(kind)) {
    console.error(`[ui] 未註冊的 panel「${kind}」，忽略這次開啟`);
    return;
  }
  set({ activePanel: { kind: kind as PanelId, ...(ctx !== undefined && { ctx }) } });
}

export function closePanel(): void {
  set({ activePanel: null });
}

/** 角色訊息窗是切換式的：再按一次 I 就關掉。 */
export function toggleCharPanel(): void {
  if (state.activePanel?.kind === 'char') closePanel();
  else openPanel('char');
}

// ── 場景 ────────────────────────────────────────────────────

export function setScene(scene: SceneId, roomTitle: string, roomId: string | null): void {
  set({ scene, roomTitle, roomId });
}

// ── boot / deck ─────────────────────────────────────────────

export function setPhase(phase: UIState['phase']): void {
  set({ phase });
}

export function setStance(stance: StanceId): void {
  set({ stance });
}

/**
 * 進場畫面按下「進入數位廣場」。
 *
 * 順序不能反：先讓世界換上角色並起一次光圈張開，再把 phase 推成 `'world'`。
 * 反過來的話中間會有幾幀是「舊角色站在沒有光圈的世界裡」。
 */
export function enterWorld(): void {
  world.enter?.(state.character);
  set({ phase: 'world' });
}

/** Deck 或任何非模態疊層拿走鍵盤時呼叫，離開時記得還回去。 */
export function setInputCaptured(inputCaptured: boolean): void {
  set({ inputCaptured });
}

export function setDeckOpen(deckOpen: boolean): void {
  set({ deckOpen, inputCaptured: deckOpen });
}

// ── 反向注入：ui 指揮 game ───────────────────────────────────

/**
 * `ui/` 不可 import `game/`（§3.2 的既有鐵律）。遊戲層在 `startGame()` 時
 * 把命令註冊進來，面板要指揮世界時查這張表。
 *
 * `enter` / `setSkin` 傳的是 `CharacterId` 而不是換色表：換色表只是角色的
 * 一半，另一半是上半身剪影，兩個參數傳來傳去遲早會有人只傳一個。id 是
 * 那張表的唯一鍵，兩邊都去 `art/characters.ts` 查同一筆。
 */
export type WorldCommands = {
  travel: (zone: ZoneId, params?: ZoneParams) => void;
  /**
   * 傳送 + 走到定位。到了之後由世界的靠近判定顯示 `[E]` 提示，
   * **不自動開面板** —— 世界裡一律走近再按鍵，功能條只是導航。
   */
  goto: (zone: ZoneId, wx: number, wy: number) => void;
  /** 進場：換上角色 + 播一次光圈張開。只有 BootScreen 會呼叫 */
  enter: (id: CharacterId) => void;
  /** 設定畫面裡即時換角色，不播轉場 */
  setSkin: (id: CharacterId) => void;
};

const world: Partial<WorldCommands> = {};

export function registerWorld(cmds: Partial<WorldCommands>): void {
  Object.assign(world, cmds);
}

export function worldCommands(): Partial<WorldCommands> {
  return world;
}

/**
 * 進入討論室需要的房間資料。刻意不讓 world 反過來 import 這個型別 ——
 * 選房面板本來就已經抓到房間資料了，遊戲層因此完全不需要知道 api 的存在。
 */
export type TravelTarget = {
  id: string;
  title: string;
  accent: Accent;
  /** 分類標籤，顯示在房間的主題看板上 */
  tag: string;
  online: number;
  /** -100 ~ 100，驅動房間的燈光與情緒計 */
  sentiment: number;
};

/** TravelTarget → ZoneParams。討論室 zone 的 `build(ctx)` 讀的就是這些 key。 */
const travelParams = (t: TravelTarget): ZoneParams => ({
  roomId: t.id,
  title: t.title,
  accent: t.accent,
  tag: t.tag,
  online: t.online,
  sentiment: t.sentiment,
});

export function travelTo(scene: ZoneId, room?: TravelTarget): void {
  closePanel();
  world.travel?.(scene, room ? travelParams(room) : undefined);
}

// ── 偏好 ────────────────────────────────────────────────────

export function setNickname(n: string): void {
  const name = n.trim().slice(0, 16) || '無名氏';
  saveNickname(name);
  set({ nickname: name });
}

/** 換角色。世界裡的角色立刻跟著換，不必重整也不必回進場畫面。 */
export function setCharacter(id: CharacterId): void {
  saveCharacter(id);
  set({ character: id });
  world.setSkin?.(id);
}

export function toggleFavorite(roomId: string): void {
  const next = state.favorites.includes(roomId)
    ? state.favorites.filter((f) => f !== roomId)
    : [...state.favorites, roomId];
  saveFavorites(next);
  set({ favorites: next });
}

// ── 帳戶檢視 ────────────────────────────────────────────────
//
// 曾經是「前端收 MAX 金鑰」的閘門。金鑰現在由後端的 .env 保管、簽名也在後端做，
// 所以這裡只剩一個純 UI 開關：要不要向後端要帳戶資料。

export function connect(): void {
  set({ connected: true });
}

export function disconnect(): void {
  set({ connected: false });
}

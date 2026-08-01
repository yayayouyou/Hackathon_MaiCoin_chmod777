import { initScreen, initInput, startLoop, input, view, setZoom, FLAGS, type Screen } from './core';
import { updateCamera, snapCamera, type Camera } from './camera';
import { overviewScale } from './zoom';
import {
  createPlayer,
  updatePlayer,
  playerBox,
  setTarget,
  setPlayerLook,
  CHAR_H,
  type Player,
} from './player';
import { getCharacter } from '../art/characters';
import { createNpc, type Npc } from './npc';
import { overlaps, expand } from './collision';
import { drawRoom, drawIris, irisMaxRadius } from './render';
import {
  initLabels,
  setSceneTitle,
  setNameplates,
  setPrompt,
  setPlayerNickname,
  setTopicBoard,
  setBubbleAnchors,
  setBubbleText,
  setSpotLabels,
  setSpotSuppressed,
  setLabelZoom,
  syncLabels,
  setLabelsVisible,
} from './worldLabels';
import { getZoomMode, setZoomMode, takeZoomToggle, type ZoomMode } from '../engine/viewport';
import { PORTAL_PLATE_DY } from '../engine/doors';
import { accentOf } from '../engine/kit';
import { FALLBACK_ZONE_ID, getZone, unregisterZone } from '../world/zones';
import { worldProbe } from '../engine/probe';
import type { ZoneCtx, ZoneDef, ZoneParams } from '../engine/zone';
import { getUI, openPanel, registerWorld, setScene, toggleCharPanel } from '../ui/uiStore';
import type { ZoneId } from '../world/zones';
import type { Accent, Rect, Room } from '../world/types';

/** 靠近判定：腳底盒往外擴這麼多像素才算「站在互動點旁邊」。 */
const REACH = 12;
/**
 * NPC 對話泡泡的節奏：亮 4.2 秒、收 3.4 秒。
 *
 * 刻意留空檔而不是一直掛著。三顆泡泡永久顯示會變成三塊擋住畫面的告示牌，
 * 而且看久了就沒有人在講話的感覺 —— 有停頓才像對話。
 */
const BUBBLE_ON = 4.2;
const BUBBLE_GAP = 3.4;
/** 光圈收合 / 張開各自的時間 */
const IRIS_TIME = 0.26;
/**
 * 從進場畫面進世界時，光圈張得慢一點。
 *
 * 換房的 0.26 秒要的是「不擋路」，進場的這一次要的是「這是開場」——
 * 它是評審看到世界的第一眼，跟換房不是同一件事，所以不共用同一個常數。
 */
const ENTER_TIME = 0.55;

let screen: Screen;
let room: Room;
let npcs: Npc[] = [];
let player: Player;
const cam: Camera = { x: 0, y: 0 };
let clock = 0;
/** NPC 嘴裡的台詞，來自該房間的真實討論串。抓不到就沒有泡泡。 */
let chatter: string[] = [];
/**
 * 目前腳下踩著的傳送門。只有「從沒踩著變成踩著」的那一瞬間才觸發，
 * 所以關掉選房面板後站在原地不會被重複彈出，走開再踩回來才會再觸發。
 */
/**
 * 傳送轉場。收合期間畫面被光圈吃掉，收到 0 時才真的換房間，
 * 所以玩家看不到瞬間切換的突兀感。轉場中一律凍結輸入。
 */
type Transition = {
  dir: 'out' | 'in';
  t: number;
  /** 這一次光圈要跑多久。換房是 IRIS_TIME，開場進世界是 ENTER_TIME */
  dur: number;
  accent: Accent;
  pending: (() => void) | null;
};
let transition: Transition | null = null;

/**
 * 場景中所有「可互動的東西」的統一形式：互動點與傳送門都長這樣。
 *
 * 傳送門原本是踩上去自動觸發、互動點要按 E，兩套規則並存讓人搞不清
 * 什麼時候該按鍵、什麼時候會自己發生。現在一律走近顯示提示、按 E 才動作。
 */
type Activatable = {
  rect: Rect;
  label: string;
  run: () => void;
  /** 對應的站牌索引（傳送門沒有站牌，所以是 undefined）。走近時那一塊要讓位。 */
  spot?: number;
};

/**
 * 每次進場遞增。zone 的 onEnter 用它判斷「非同步回來時玩家還在不在這一次
 * 進場裡」—— 比對 zone id 是不夠的，從 A 討論室切到 B 討論室時 id 一樣。
 */
let loadToken = 0;
/** 上一個 zone 的 onEnter 回傳的 cleanup 與它的 AbortController */
let zoneCleanup: (() => void) | null = null;
let zoneAbort: AbortController | null = null;

/**
 * 換場結束的那一瞬間要做的事。底部功能條的「傳送＋走過去＋自動觸發」
 * 靠它把後半段接上 —— 傳送是非同步的（要等光圈收合），而目的地的
 * 互動點清單要等新房間建好才存在。
 */
let onArrive: (() => void) | null = null;

/**
 * 鏡頭模式。`overview` 看得到整個空間、每個功能點都掛著名牌；
 * `focus` 是原本那個貼身跟隨的視角。一旦角色真的動起來就切到 focus ——
 * 「你開始走了」是「你已經看完這個空間」最可靠的訊號，不需要多按一個鍵。
 */
/**
 * ⚠ `?fast=1` 一律從 focus 開始。那是測試與錄影的旗標，而 156 項 e2e 全部
 * 跑在 `?fast=1&debug=1` 底下 —— 全景會改變開場的 `view` 尺寸與鏡頭位置，
 * 任何一項用世界座標導航的斷言都會跟著飄。要錄有全景的示範片段，
 * 錄影時把旗標拿掉就好。
 */
const DEFAULT_ZOOM: ZoomMode = FLAGS.fast ? 'focus' : 'overview';
let zoomMode: ZoomMode = DEFAULT_ZOOM;

/**
 * 套用目前的鏡頭模式：換倍率、把鏡頭重新對準、切換標籤大小。
 *
 * 進新房間一律從全景開始 —— 一進門先看清楚這個空間裡有什麼、有幾個
 * 出入口，再決定要走去哪。`applyZoom()` 必須排在 `snapCamera()` 之前，
 * 因為換倍率會改變 `view` 的尺寸，而 snapCamera 是拿 view 去算置中的。
 */
function applyZoom(): void {
  setZoom(zoomMode === 'overview' ? overviewScale(room.w, room.h) : null);
  setZoomMode(zoomMode);
  // 站牌不再跟著鏡頭模式開關（常駐），只有字級由 setLabelZoom 的 CSS 降階
  setLabelZoom(zoomMode);
  snapCamera(cam, player.x, player.y, room.w, room.h);
}

function setZoomModeAndApply(next: ZoomMode): void {
  if (next === zoomMode) return;
  zoomMode = next;
  applyZoom();
}

function loadRoom(next: Room): void {
  room = next;
  npcs = room.npcs.map(createNpc);
  player.x = room.spawn.x;
  player.y = room.spawn.y;
  player.target = null;
  // 出生面向鏡頭。原本是 'up'，玩家一進場看到的是後腦勺 ——
  // Q 版角色的臉是它唯一的賣點，沒有理由把它藏起來。
  player.dir = 'down';

  setSceneTitle(room.title);
  setNameplates(
    room.portals.map((p) => ({
      text: p.label,
      wx: p.rect.x + p.rect.w / 2,
      wy: p.rect.y - PORTAL_PLATE_DY,
      accent: p.accent,
    })),
  );
  setPrompt(null);

  // 主題看板的中文疊在 topicboard 那塊深色面板的正中央
  const tb = room.props.find((p) => p.kind === 'topicboard');
  setTopicBoard(
    tb && room.topic
      ? { title: room.title, tag: room.topic.tag, online: room.topic.online, wx: tb.x + 72, wy: tb.y + 17 }
      : null,
  );

  // 功能點名牌：每個互動點頭上常駐一塊「這裡是什麼」。
  // 標在互動範圍的正上方，跟 `[E]` 提示同一個錨點 —— 走近時這一塊會讓位給
  // 提示，位置一致才不會讓人覺得「走近之後標籤跳了一下」。
  //
  // sign 是名詞（「公告」）、label 是動詞（「讀取官方消息」）：牌子要在遠處
  // 就回答「那是什麼」，提示要在面前回答「按下去會怎樣」。
  setSpotLabels(
    room.interactables.map((it) => ({
      text: it.sign ?? it.label,
      // 掛在道具頭上（signAt），不是互動範圍頭上 —— 後者是從道具底部往上算的，
      // 拿它當錨點牌子會壓在道具臉上。手寫的互動點沒有 signAt 才退回用 rect。
      wx: it.signAt?.x ?? it.rect.x + it.rect.w / 2,
      wy: it.signAt?.y ?? it.rect.y - 2,
      accent: it.accent ?? room.accent,
    })),
  );

  setBubbleAnchors(npcs.map((n) => ({ wx: n.x, wy: n.y - CHAR_H - 4 })));
  chatter = [];

  // 進新房間一律回到全景。放在最後：它會 snapCamera，而上面那些
  // setter 只寫錨點、不碰鏡頭。
  zoomMode = DEFAULT_ZOOM;
  applyZoom();
  // 原本這裡硬編了一段 `getThread(roomId)` 只為了討論室的 NPC 泡泡 ——
  // 遊戲層因此知道了一個特定房間的 api。那段搬進了 discussion zone 的
  // onEnter，這個函式現在對所有 zone 一視同仁。
}

/**
 * 把互動點與傳送門攤成同一份清單。每幀重建，內容很少所以不值得快取；
 * 換來的是提示、E 鍵、點擊提示、點擊物件四條路徑共用同一套判定。
 */
function activatables(): Activatable[] {
  const list: Activatable[] = room.interactables.map((it, i) => ({
    rect: it.rect,
    label: it.label,
    spot: i,
    // 互動點解鎖任意 callback：不再只能開面板，也可以觸發 agent、播動畫、
    // 跳下單確認。兩個都沒填的話 openPanel(undefined) 會 no-op 並抱怨。
    run: it.run ?? (() => openPanel(it.panel!)),
  }));
  for (const p of room.portals) {
    list.push({
      rect: p.rect,
      label: p.enterLabel ?? `進入 ${p.label}`,
      run: () =>
        p.action.type === 'travel'
          ? travel(p.action.scene, p.action.params, p.accent)
          : openPanel(p.action.panel),
    });
  }
  return list;
}

/**
 * 連中庭都建不起來時的最後一張底牌。
 *
 * 它存在的唯一理由是「`room` 這個變數永遠不能是 undefined」：`step()` 每幀都
 * 讀 `room.solids`，一旦沒有房間，主迴圈就會每幀丟例外。空房間很難看，
 * 但走得動、面板打得開、其他門還在，比白畫面好。
 */
const EMERGENCY_ROOM: Room = {
  id: FALLBACK_ZONE_ID,
  title: '⚠ 場景載入失敗',
  w: 320,
  h: 240,
  accent: 'amber',
  ambient: '#ffffff',
  floor: 'plaza',
  props: [],
  solids: [],
  portals: [],
  interactables: [],
  npcs: [],
  spawn: { x: 160, y: 160 },
};

/** 建房 + 掛 onEnter。build 會往外丟例外，由 swapRoom() 決定怎麼退。 */
function enterZone(z: ZoneDef, params: ZoneParams): void {
  const ctx: ZoneCtx = { id: z.id, params, from: room ? room.id : null };
  loadRoom(z.build(ctx));
  setScene(z.id, room.title, typeof params['roomId'] === 'string' ? params['roomId'] : null);

  zoneAbort = new AbortController();
  const token = ++loadToken;
  // onEnter 是副作用（載資料、開輪詢），它炸掉不該連累已經站進去的房間
  try {
    zoneCleanup =
      z.onEnter?.(ctx, {
        room,
        ifStillHere: (fn) => {
          if (token === loadToken) fn();
        },
        signal: zoneAbort.signal,
        setChatter: (lines) => {
          chatter = lines;
        },
      }) ?? null;
  } catch (e) {
    console.error(`[zones] zone「${z.id}」的 onEnter() 丟出例外，房間照常進`, e);
    zoneCleanup = null;
  }

  // ⚠ 到站導引（onArrive）刻意**不在這裡**執行。這個函式是從
  //   stepTransition() 同步呼叫的，此刻 transition 還沒歸零，設下的
  //   player.target 會在下一幀被 frozen 清掉。它改由 step() 在
  //   `transition === null` 的那一幀執行，理由寫在那裡。
}

/**
 * 換房間：查表 → 建房 → 掛 onEnter。**全程不准把例外放出去。**
 *
 * 原本這裡是 `if (lobby) … else if (maxinfo) … else …`，那個 else 是
 * catch-all：新增房間時漏加一個分支，症狀不是錯誤而是「玩家被靜默送進
 * BTC 討論室」，而 TypeScript 一個字都不會說。現在找不到 zone 會退回中庭
 * 並在 console 大聲抱怨 —— 測試的「全程無執行期錯誤」會抓到。
 *
 * 但「id 找不到」只是兩種失敗的其中一種。另一種是「zone 自己炸了」：
 * 這個函式是從 rAF 迴圈裡被呼叫的，例外會一路穿出去把主迴圈殺死
 * （轉場中就是永遠停在全黑）。而 `validateWiring()` 只用空 params 試 build，
 * 「帶特定 params 才炸」的分支它抓不到 —— 討論室正是靠 params 分歧的。
 * 所以壞掉的 zone 在這裡被踢出註冊表一次，然後退回中庭。
 */
function swapRoom(id: string, params: ZoneParams = {}): void {
  // 先收掉上一個 zone：cleanup 停輪詢、abort 讓在途的 fetch 放棄。
  // 沒有這兩行的話，離開房間之後它還在打 API，而且回來的資料會蓋掉新房間。
  // cleanup 炸掉不該擋住進新場，所以它自己一層 try。
  try {
    zoneCleanup?.();
  } catch (e) {
    console.error(`[zones] 上一個 zone「${room ? room.id : '?'}」的 cleanup 丟出例外，忽略`, e);
  }
  zoneAbort?.abort();
  zoneCleanup = null;

  const z = getZone(id); // 找不到退回中庭，不 throw
  try {
    enterZone(z, params);
    return;
  } catch (e) {
    console.error(`[zones] zone「${z.id}」進場失敗，已移除它並退回中庭`, e);
    unregisterZone(z.id); // 中庭會拒絕被移除，那條路走下面的 EMERGENCY_ROOM
  }

  if (z.id !== FALLBACK_ZONE_ID) {
    try {
      enterZone(getZone(FALLBACK_ZONE_ID), {});
      return;
    } catch (e) {
      console.error('[zones] 連中庭都建不起來', e);
    }
  }
  loadRoom(EMERGENCY_ROOM);
  setScene(EMERGENCY_ROOM.id, EMERGENCY_ROOM.title, null);
}

/**
 * 換場一律經過光圈轉場：先收合，全黑那一瞬間才換房間，再張開。
 * accent 用來源的顏色 —— 從大廳走進 MAX 是琥珀色，從討論室回大廳
 * 是該討論室的主題色，視覺上跟你剛穿過的那道門是同一個東西。
 */
function travel(scene: string, params: ZoneParams = {}, accent: Accent = 'cyan'): void {
  if (transition) return; // 轉場中不接受新的傳送
  transition = {
    dir: 'out',
    t: 0,
    dur: IRIS_TIME,
    accent,
    pending: () => swapRoom(scene, params),
  };
}

/** 推進轉場，回傳目前的光圈半徑；沒有轉場時回傳 null。 */
function stepTransition(dt: number): number | null {
  if (!transition) return null;
  const maxR = irisMaxRadius();
  transition.t += dt;
  const k = Math.min(1, transition.t / transition.dur);

  if (transition.dir === 'out') {
    if (k >= 1) {
      transition.pending?.();
      transition = {
        dir: 'in',
        t: 0,
        dur: transition.dur,
        accent: transition.accent,
        pending: null,
      };
      return 0;
    }
    return maxR * (1 - k);
  }
  if (k >= 1) {
    transition = null;
    return null;
  }
  return maxR * k;
}

/**
 * 點擊落在可互動物件上：走過去，站定後顯示 `[E]` 提示。
 *
 * **不自動觸發。** 一個世界裡只該有一條「東西會發生」的規則：走近，然後
 * 按鍵。原本用鍵盤靠近要按 E、用滑鼠點就自動開，同一個目標兩套行為，
 * 沒有人講得清楚什麼時候會自己發生。觸控裝置沒有 E 鍵，但浮動提示本身
 * 就可以點（`worldLabels.setPrompt` 在觸控上把鍵帽畫成 `▸`）。
 *
 * 回傳 true 表示這次點擊已經被物件吃掉。
 */
function tryClickActivatable(list: Activatable[], wx: number, wy: number): boolean {
  const hit = list.find(
    (a) => wx >= a.rect.x && wx <= a.rect.x + a.rect.w && wy >= a.rect.y && wy <= a.rect.y + a.rect.h,
  );
  if (!hit) return false;
  // 走到互動範圍的下緣，也就是玩家自然會站的位置
  setTarget(player, hit.rect.x + hit.rect.w / 2, hit.rect.y + hit.rect.h - 4);
  return true;
}

/**
 * 走到世界裡的某個座標。到了之後由每幀的靠近判定接手顯示 `[E]` 提示。
 *
 * 落點若落在某個互動點的範圍內就走到那個互動點的定位 —— 這樣「走到定位」
 * 的定義與玩家自己點擊時完全一致，不會出現「選單走到的位置跟走路走到的
 * 位置差兩像素，於是提示不出現」。
 */
function walkTo(wx: number, wy: number): void {
  const hit = activatables().find(
    (a) => wx >= a.rect.x && wx <= a.rect.x + a.rect.w && wy >= a.rect.y && wy <= a.rect.y + a.rect.h,
  );
  if (hit) {
    setTarget(player, hit.rect.x + hit.rect.w / 2, hit.rect.y + hit.rect.h - 4);
    return;
  }
  setTarget(player, wx, wy);
}

/**
 * 底部功能條的執行路徑：**傳送 → 角色自己走過去 → 站定顯示 `[E]`**。
 *
 * 刻意不是「直接開面板」。選單是給趕時間的人的捷徑，但按下去之後看到的
 * 仍然是角色走進那個區域 —— 世界才是容器。少了中間這段，這個專案就只是
 * 一個貼了像素貼圖的 dashboard。
 */
function gotoPlace(zone: string, wx: number, wy: number): void {
  if (transition) return; // 轉場中不接受新的導引，否則 onArrive 會被覆蓋掉
  if (room.id === zone) {
    walkTo(wx, wy);
    return;
  }
  onArrive = () => walkTo(wx, wy);
  travel(zone, {}, getZone(zone).accent);
}

function step(dt: number): void {
  clock += dt;
  const ui = getUI();
  const iris = stepTransition(dt);

  /**
   * 到站要做的事，**必須等轉場真的結束才跑**。
   *
   * 這裡曾經是一個很難看見的 bug：原本 `onArrive` 是在 `enterZone()` 裡
   * 直接呼叫的，而 `enterZone()` 由 `stepTransition()` 同步觸發 —— 那一刻
   * `transition` 還沒歸零。於是 `walkTo()` 設下的 `player.target` 在下一幀
   * 就被 `updatePlayer(..., frozen)` 的 `p.target = null` 清掉（frozen 含
   * `transition !== null`），角色從頭到尾沒有動過一步。
   *
   * 症狀是：點功能條 → 房間換了 → 角色站在出生點不動 → 沒有提示也沒有面板。
   * 看起來像「功能條只做了傳送」，其實是走路那段被自己的凍結條件吃掉。
   *
   * 修法就是讓 onArrive 與 frozen 讀同一份 `transition` 值 —— 排在算 frozen
   * 之前的這一幀，`transition` 已經是 null，設下的 target 不會再被清掉。
   */
  if (transition === null && onArrive) {
    const arrive = onArrive;
    onArrive = null;
    try {
      arrive();
    } catch (e) {
      console.error('[zones] 到站後的自動導引失敗，玩家留在原地', e);
    }
  }

  /**
   * 一次加齊四個凍結條件（規格 §9 ①）。
   * `inputCaptured` 是 Deck / HUD 這類**非模態**疊層用的 —— 沒有它就會
   * 出現「你在選單裡按方向鍵，角色在背後被走掉」。
   */
  const frozen =
    ui.phase !== 'world' || ui.activePanel !== null || ui.inputCaptured || transition !== null;

  /**
   * 世界的快捷鍵，`phase === 'world'` 才受理。
   *
   * 這兩個刻意不用 `frozen` 當閘門（`frozen` 在面板開著時是真，但 I 鍵正是
   * 要在那時候把面板關掉），而是只擋進場畫面。少了這一道，站在進場畫面上
   * 按 I 會在 overlay 底下偷開一個角色訊息窗，按 Z 會把還沒看到的世界
   * 切成全景。
   */
  const inWorld = ui.phase === 'world';

  // 角色訊息窗是切換式的，所以開著的時候也要收 I 鍵。
  // 焦點在輸入框時 core.ts 本來就不會收鍵盤，打字不會誤觸。
  if (inWorld && input.pressed('KeyI') && !transition) toggleCharPanel();

  // 全景／跟隨的手動切換：Z 鍵，或 HUD 上那顆按鈕（`takeZoomToggle`）。
  // 轉場中不受理 —— 換場本來就會把模式重設成全景。
  if (inWorld && !transition && (input.pressed('KeyZ') || takeZoomToggle())) {
    setZoomModeAndApply(zoomMode === 'overview' ? 'focus' : 'overview');
  }

  const list = activatables();

  if (frozen) {
    input.takeClick(); // 丟掉面板開啟期間累積的點擊
  } else {
    const click = input.takeClick();
    if (click) {
      const wx = click.sx + cam.x;
      const wy = click.sy + cam.y;
      if (!tryClickActivatable(list, wx, wy)) setTarget(player, wx, wy);
    }
  }

  const wasX = player.x;
  const wasY = player.y;
  updatePlayer(player, dt, room.solids, frozen);
  /**
   * 角色真的移動了就切到跟隨。
   *
   * 判定用「座標有沒有變」而不是「有沒有按方向鍵」：點擊移動、被選單
   * 導引過去、之後可能加的尋路，全部都算 —— 只要人在動，就該把鏡頭
   * 拉近到他身上。撞牆原地不動時不會誤觸發，因為 move-and-slide 會讓
   * 座標真的沒變。
   */
  if (zoomMode === 'overview' && (player.x !== wasX || player.y !== wasY)) {
    setZoomModeAndApply('focus');
  }
  if (!frozen) {
    // 走近顯示提示，按 E 或直接點提示才觸發。傳送門也走這條路 ——
    // 不再有「踩上去就被傳走」的意外。
    const reach = expand(playerBox(player), REACH);
    let nearest: Activatable | null = null;
    let best = Infinity;
    for (const a of list) {
      if (!overlaps(reach, a.rect)) continue;
      const dx = a.rect.x + a.rect.w / 2 - player.x;
      const dy = a.rect.y + a.rect.h / 2 - player.y;
      const d = dx * dx + dy * dy;
      if (d < best) {
        best = d;
        nearest = a;
      }
    }
    if (nearest) {
      const target = nearest;
      setPrompt(target.label, target.rect.x + target.rect.w / 2, target.rect.y - 2, target.run);
      setSpotSuppressed(target.spot ?? null);
      if (input.pressed('KeyE')) target.run();
    } else {
      setPrompt(null);
      setSpotSuppressed(null);
    }
  }

  updateCamera(cam, player.x, player.y, room.w, room.h);
  drawRoom(screen.ctx, room, cam, clock, player, npcs);
  if (iris !== null) drawIris(screen.ctx, iris, transition?.accent ?? 'cyan');

  // NPC 輪流講話。每個人的相位錯開，才不會三個人同時開口。
  for (let i = 0; i < npcs.length; i++) {
    const phase = clock + i * 2.7;
    const cycle = BUBBLE_ON + BUBBLE_GAP;
    const line = chatter.length
      ? chatter[(Math.floor(phase / cycle) + i) % chatter.length]!
      : null;
    setBubbleText(i, phase % cycle < BUBBLE_ON ? line : null);
  }

  setPlayerNickname(ui.nickname, player.x, player.y - CHAR_H - 3);
  setLabelsVisible(!frozen);
  syncLabels(cam, screen);
}

export function startGame(): void {
  screen = initScreen();
  initInput(screen);
  initLabels();
  player = createPlayer(0, 0);
  // 重整之後要是上次選的那個角色。uiStore 在 module 頂層就把 localStorage
  // 讀好了，所以這裡拿到的已經是驗證過的 id。
  setPlayerLook(player, getUI().character);
  // 反向注入：ui/ 不可 import game/，所以由遊戲層自己把命令送過去。
  registerWorld({
    travel: (zone, params = {}) => travel(zone, params, accentOf(params['accent'])),
    goto: (zone: ZoneId, wx, wy) => gotoPlace(zone, wx, wy),
    setSkin: (id) => setPlayerLook(player, id),
    /**
     * 進場畫面按下「進入數位廣場」。
     *
     * 只有 `dir: 'in'`，沒有前半段的收合 —— 世界從第一幀就在 overlay 背後
     * 跑著（`main.tsx` 的 `startGame()` 是無條件執行的），此刻畫面上本來就是
     * 全黑的進場畫面，再收合一次只是多等 0.55 秒。直接張開就是「幕拉開」。
     */
    enter: (id) => {
      setPlayerLook(player, id);
      transition = {
        dir: 'in',
        t: 0,
        dur: ENTER_TIME,
        accent: getCharacter(id).accent,
        pending: null,
      };
    },
  });
  swapRoom('lobby'); // 開場直接進大廳，不需要轉場
  // 視窗大小一變，「整個房間放得下」的倍率就跟著變。排在 initScreen 的
  // resize 之後註冊，所以 view 已經是新的了。
  addEventListener('resize', () => {
    if (room && zoomMode === 'overview') applyZoom();
  });
  startLoop(step);

  // debug 疊層把碰撞盒與死區畫出來給人看，這兩個鉤子則是給自動化測試讀數字用的。
  // 「鏡頭在死區內完全不動」這種事，比對座標比盯著截圖可靠得多。
  if (FLAGS.debug) {
    const w = window as unknown as {
      __game: () => unknown;
      __zones: () => unknown;
      __travel: (id: string, params?: ZoneParams) => void;
    };
    w.__game = () => ({
      px: player.x,
      py: player.y,
      cam: { x: cam.x, y: cam.y },
      room: { id: room.id, w: room.w, h: room.h },
      view: { w: view.w, h: view.h, scale: screen.scale },
      // 鏡頭模式與倍率一起讀出來，測試才驗得了「進場是全景、一走就跟隨」
      zoomMode: getZoomMode(),
      target: player.target ? { x: player.target.x, y: player.target.y } : null,
      transition: transition?.dir ?? null,
      // 接縫 PR 新增：測試唯一的狀態讀取口
      phase: getUI().phase,
      stance: getUI().stance,
      character: getUI().character,
      zone: room.id,
      ready: true,
    });
    // 註冊表的唯讀快照。tests/zones.mjs 靠它一秒驗完所有 zone 不變式。
    w.__zones = worldProbe;
    // 讓測試可以送出「不存在的 zone id」，驗證它退回中庭而不是白畫面。
    w.__travel = (id, params) => travel(id, params);
  }
}

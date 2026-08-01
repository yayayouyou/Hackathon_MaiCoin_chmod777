import { setViewScale } from '../engine/viewport';

/** 設計基準解析度。實際視野會依視窗調整，但倍率由這個尺寸推導。 */
const BASE_W = 480;
const BASE_H = 270;

/**
 * 視野上限，純粹是防呆用的。
 *
 * 原本訂得很保守（720x400）想擋掉「視野比房間大」的情況，但那反而
 * 讓直立手機被夾成 430x400，剩下一半螢幕是空的 —— 沒填滿正是要修的問題。
 * 房間比視野小的情形交給 camera.ts 置中處理就好，這裡只擋住荒謬的尺寸。
 *
 * 寬度從 1024 放寬到 1600：全景模式在 1440 寬的筆電上會選 1 倍，
 * 夾在 1024 的話畫布只有 1024px 寬、兩側各露 208px 的背景色。
 * 成本是 backbuffer 最大到 1600×1024，而地板本來就只畫視野內的格子
 * （最大的房間 960×512 也才 60×32 格），打光緩衝區的合成是唯一真的
 * 隨面積成長的部分 —— 實測仍在一幀的預算內。
 */
export const MAX_VIEW = { w: 1600, h: 1024 };

/**
 * 目前的內部解析度。所有世界座標都以此為單位，最後才整數倍放大到畫面。
 * 這是可變的：視窗改變時會重算，讓畫布剛好填滿而不留黑邊。
 */
export const view = { w: BASE_W, h: BASE_H };

export const TILE = 16;

export const FLAGS = {
  debug: new URLSearchParams(location.search).has('debug'),
  failApi: new URLSearchParams(location.search).has('failApi'),
  /**
   * 全域測試／錄影旗標（規格 §5.4）：跳過 boot、跳過進場取景、
   * 關閉所有 HUD 輪詢。取代提案裡的 skipIntro / boot=skip 三套旗標 ——
   * 只有一個旗標，就不會出現「這台機器上是關的那台是開的」。
   *
   * `hud/feeds.ts` 不 import 這裡（§3.2 禁止 hud → game），它自己讀
   * location。同一個旗標名字，兩處讀。
   */
  fast: new URLSearchParams(location.search).has('fast'),
};

export type Screen = {
  canvas: HTMLCanvasElement;
  ctx: CanvasRenderingContext2D;
  /** 目前的整數放大倍率 */
  scale: number;
};

/**
 * 動態解析度 + 整數倍縮放：畫布剛好填滿視窗，像素仍維持硬邊。
 *
 * 整數倍率不能妥協 —— 非整數倍會讓一個來源像素跨到兩個螢幕像素上，
 * 即使關掉平滑化也會出現寬度不一的鋸齒。所以改成固定倍率、伸縮視野：
 * 先取最接近的整數倍率，再把 backbuffer 撐成剛好填滿的尺寸。
 *
 * 倍率用 round 而不是 floor 是關鍵。floor 在 1366x768 會選 2 倍，
 * backbuffer 變成 683x384，世界範圍大到房間裝不下；round 選 3 倍
 * 得到 456x256，視野比基準略小但完全填滿，也還在房間尺寸內。
 */

/**
 * 視窗能放下的最大倍率 —— 也就是「跟隨模式」的倍率。
 * 全景模式會挑一個比它小的整數倍，讓整個房間進得了視野。
 */
export function baseScale(): number {
  return Math.max(1, Math.round(Math.min(innerWidth / BASE_W, innerHeight / BASE_H)));
}

let zoomScale: number | null = null;
let doResize: (() => void) | null = null;

/**
 * 覆寫倍率（`null` = 回到自動）。倍率一改，backbuffer 尺寸跟著改，
 * 所以這裡直接重跑一次 resize —— 沒有第二條路可以同時維持
 * 「整數倍率」與「畫布填滿視窗」這兩件事。
 *
 * ⚠ 縮放是**瞬間切換**，不是補間動畫。補間必然經過非整數倍率，那會讓
 *   一個來源像素跨到兩個螢幕像素上、糊掉一整段轉場 —— 而整數倍率是這個
 *   專案不妥協的前提。遊戲裡的地圖／戰鬥視角切換本來也都是硬切。
 */
export function setZoom(s: number | null): void {
  const next = s === null ? null : Math.max(1, Math.round(s));
  if (next === zoomScale) return;
  zoomScale = next;
  doResize?.();
}

export function initScreen(): Screen {
  const canvas = document.getElementById('screen') as HTMLCanvasElement;
  const ctx = canvas.getContext('2d', { alpha: false })!;
  const screen: Screen = { canvas, ctx, scale: 1 };

  const resize = () => {
    const s = zoomScale ?? baseScale();
    screen.scale = s;
    // HUD 用 CSS 像素回報自己遮住多少，鏡頭要的是 backbuffer 像素 ——
    // 倍率是這兩套單位之間唯一的換算因子，只有這裡知道它變了。
    setViewScale(s);
    view.w = Math.min(MAX_VIEW.w, Math.ceil(innerWidth / s));
    view.h = Math.min(MAX_VIEW.h, Math.ceil(innerHeight / s));

    canvas.width = view.w;
    canvas.height = view.h;
    canvas.style.width = `${view.w * s}px`;
    canvas.style.height = `${view.h * s}px`;
    // 改動 canvas 的 width/height 屬性會重置 context 狀態，所以放在這之後
    ctx.imageSmoothingEnabled = false;

    const root = document.documentElement.style;
    root.setProperty('--scale', String(s));
    root.setProperty('--view-w', String(view.w));
    root.setProperty('--view-h', String(view.h));
  };
  doResize = resize;
  resize();
  addEventListener('resize', resize);
  // 手機轉向時 innerWidth/Height 有時要等一拍才更新
  addEventListener('orientationchange', () => setTimeout(resize, 100));
  return screen;
}

// ── 輸入 ────────────────────────────────────────────────────

const down = new Set<string>();
const justDown = new Set<string>();
let pendingClick: { sx: number; sy: number } | null = null;

export const input = {
  held: (code: string) => down.has(code),
  /** 只在按下的那一幀為 true，用於 E 互動這類不該連發的操作 */
  pressed: (code: string) => justDown.has(code),
  /** 取走這一幀的點擊（螢幕座標），取走後即清空 */
  takeClick(): { sx: number; sy: number } | null {
    const c = pendingClick;
    pendingClick = null;
    return c;
  },
  clear() {
    down.clear();
    justDown.clear();
    pendingClick = null;
  },
  endFrame() {
    justDown.clear();
  },
};

export function initInput(screen: Screen): void {
  addEventListener('keydown', (e) => {
    // 面板裡的輸入框要能正常打字，所以焦點在表單元素時不攔截
    const t = e.target as HTMLElement | null;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
    if (!down.has(e.code)) justDown.add(e.code);
    down.add(e.code);
    // 空白與方向鍵預設會捲動頁面
    if (e.code === 'Space' || e.code.startsWith('Arrow')) e.preventDefault();
  });
  addEventListener('keyup', (e) => down.delete(e.code));
  // 切到別的分頁時放開所有按鍵，否則回來會一直往同一個方向走
  addEventListener('blur', () => down.clear());

  screen.canvas.addEventListener('pointerdown', (e) => {
    const r = screen.canvas.getBoundingClientRect();
    pendingClick = {
      sx: (e.clientX - r.left) / screen.scale,
      sy: (e.clientY - r.top) / screen.scale,
    };
  });
}

// ── 主迴圈 ──────────────────────────────────────────────────

/**
 * dt 夾在 50ms 以內：分頁切回來時 rAF 的間隔可能是好幾秒，
 * 不夾住的話角色會瞬間穿過整個房間。
 *
 * `step(dt)` 一定要包 try/catch，理由是排程順序：`requestAnimationFrame(frame)`
 * 排在 `step(dt)` 之後，所以 step 只要丟一次例外，下一幀就永遠不會被排進去 ——
 * 主迴圈**永久死亡**，畫面停在最後一幀（換場中就是整片黑）、角色不能動、
 * 只能重整。而 step 裡直接呼叫的是四條平行軌隊友寫的東西（zone 的
 * build/onEnter/cleanup、互動點的 run()），任何一個炸掉都不該把世界帶走。
 * 包起來之後最壞情況只是「掉一幀」。
 *
 * 錯誤輸出有上限：壞掉的那一幀通常每幀都會再壞一次，60 次/秒的 console.error
 * 會把瀏覽器與測試 runner 一起拖垮。前三次照印（測試的「全程無執行期錯誤」
 * 照樣紅燈），之後閉嘴。
 */
export function startLoop(step: (dt: number) => void): void {
  let last = performance.now();
  let errors = 0;
  const frame = (now: number) => {
    const dt = Math.min((now - last) / 1000, 0.05);
    last = now;
    try {
      step(dt);
    } catch (e) {
      if (errors < 3) console.error('[loop] 這一幀出錯，已跳過', e);
      else if (errors === 3) console.error('[loop] 幀錯誤過多，後續不再輸出');
      errors++;
    }
    input.endFrame();
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

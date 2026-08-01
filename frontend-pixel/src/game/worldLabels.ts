import type { Camera } from './camera';
import type { Screen } from './core';

/**
 * 世界標籤層：傳送門名牌、[E] 互動提示、場景標題。
 *
 * 這一層刻意不經過 React。它們的座標每一幀都在變，若走 React state
 * 會逼元件每秒重繪 60 次；而中文字若畫進 480x270 的 backbuffer，
 * 8px 的字被整數放大 4 倍後會糊成一團。所以：DOM 元素 + 命令式更新，
 * 字是螢幕原生解析度的銳利中文，成本只有幾個 style.transform。
 */

type Anchor = { el: HTMLElement; wx: number; wy: number };
type Bubble = { el: HTMLElement; wx: number; wy: number; text: string };

const coarse = matchMedia('(pointer: coarse)');
const isCoarse = () => coarse.matches;

let root: HTMLElement;
let titleEl: HTMLElement;
let promptEl: HTMLElement;
let nickEl: HTMLElement;
let anchors: Anchor[] = [];
let spots: Anchor[] = [];
/** 正在被 `[E]` 提示取代的那一塊站牌。null = 都不讓位。 */
let suppressedSpot: number | null = null;
let bubbles: Bubble[] = [];
let topicEl: HTMLElement;
let topicAnchor: { wx: number; wy: number } | null = null;
let promptAnchor: { wx: number; wy: number } | null = null;
let promptText = '';
let promptAction: (() => void) | null = null;
let nickText = '';
let nickAnchor = { wx: 0, wy: 0 };

export function initLabels(): void {
  root = document.getElementById('world-labels')!;
  root.innerHTML = '';

  titleEl = document.createElement('div');
  titleEl.className = 'scene-title';
  root.appendChild(titleEl);

  promptEl = document.createElement('div');
  promptEl.className = 'world-prompt';
  promptEl.hidden = true;
  // 提示本身就是觸控裝置的互動按鈕 —— 手機沒有 E 鍵。
  // 滑鼠與觸控共用同一個元件，不另外做一套 UI。
  promptEl.addEventListener('pointerdown', (e) => {
    e.stopPropagation();
    promptAction?.();
  });
  root.appendChild(promptEl);

  topicEl = document.createElement('div');
  topicEl.className = 'topic-board';
  topicEl.hidden = true;
  root.appendChild(topicEl);

  nickEl = document.createElement('div');
  nickEl.className = 'nickname';
  root.appendChild(nickEl);
}

/**
 * 主題看板上的文字。
 *
 * 它不是浮在空中的標籤，而是貼在 topicboard 那塊深色面板上 —— 所以
 * 尺寸要跟著世界像素一起放大。寬高用 core.ts 已經發佈的 `--scale`
 * 算，這樣就不必每幀去寫 style。
 */
export function setTopicBoard(
  v: { title: string; tag: string; online: number; wx: number; wy: number } | null,
): void {
  if (!v) {
    topicEl.hidden = true;
    topicAnchor = null;
    return;
  }
  const html = `<b>${v.title}</b><span>${v.tag} · ${v.online} 人在線</span>`;
  if (topicEl.innerHTML !== html) topicEl.innerHTML = html;
  topicEl.hidden = false;
  topicAnchor = { wx: v.wx, wy: v.wy };
}

/** 換房間時重建對話泡泡的元素，一個 NPC 一個。 */
export function setBubbleAnchors(items: readonly { wx: number; wy: number }[]): void {
  for (const b of bubbles) b.el.remove();
  bubbles = items.map((it) => {
    const el = document.createElement('div');
    el.className = 'npc-bubble';
    el.hidden = true;
    root.appendChild(el);
    return { el, wx: it.wx, wy: it.wy, text: '' };
  });
}

/**
 * 設定某個 NPC 的台詞，null 表示收起來。每幀都會被呼叫，
 * 所以只有內容真的變了才動 DOM —— 否則瀏覽器會一直重算排版。
 */
export function setBubbleText(i: number, text: string | null): void {
  const b = bubbles[i];
  if (!b) return;
  const next = text === null ? '' : text.length > 18 ? `${text.slice(0, 18)}…` : text;
  if (next === b.text) return;
  b.text = next;
  if (next === '') {
    b.el.hidden = true;
  } else {
    b.el.textContent = next;
    b.el.hidden = false;
  }
}

/** 玩家頭上的暱稱。文字只在改名時更新，位置每幀跟著角色。 */
export function setPlayerNickname(text: string, wx: number, wy: number): void {
  if (text !== nickText) {
    nickText = text;
    nickEl.textContent = text;
  }
  nickAnchor = { wx, wy };
}

export function setSceneTitle(text: string): void {
  titleEl.textContent = text;
}

/**
 * 功能點名牌：每個互動點頭上一塊「這裡能做什麼」。
 *
 * **常駐**，兩種鏡頭模式都掛著。原本只在全景顯示，理由是「跟隨模式下走近
 * 會有 `[E]` 提示，全部掛著只會把房間蓋滿」—— 但那個顧慮的解法是走近時
 * 讓對應的那一塊讓位（見 `syncLabels`），不是全部收起來：收起來之後，
 * 沒走到面前的設備就完全不會自我介紹，人只能一個一個試過去。
 *
 * 跟隨模式下字級與透明度由 CSS 降一階（`[data-zoom='focus'] .spot-label`），
 * 全景模式維持放大 —— 那一眼要回答的是「這個空間裡有哪些功能」。
 */
export function setSpotLabels(
  items: readonly { text: string; wx: number; wy: number; accent: string }[],
): void {
  for (const s of spots) s.el.remove();
  suppressedSpot = null;
  spots = items.map((it) => {
    const el = document.createElement('div');
    el.className = 'spot-label';
    el.dataset.accent = it.accent;
    el.textContent = it.text;
    root.appendChild(el);
    return { el, wx: it.wx, wy: it.wy };
  });
}

/**
 * 走近某個站點時，把那一塊站牌收起來讓位給 `[E]` 提示。
 *
 * 傳索引而不是比對座標：站牌掛在道具頭上、提示掛在互動範圍頭上，兩者本來
 * 就不同高，比座標永遠對不上；而且就算對得上，浮點相等也是個遲早會出事的
 * 判斷。索引由 `activatables()` 產生，跟 `room.interactables` 同一個順序。
 */
export function setSpotSuppressed(i: number | null): void {
  suppressedSpot = i;
}

/**
 * 全景 / 跟隨。只改 `#world-labels` 上的一個 data 屬性，放大交給 CSS ——
 * 這樣「標籤在全景時要多大」是一條可以直接看、直接改的樣式規則，
 * 而不是散在 JS 裡的一堆 style 寫入。
 */
export function setLabelZoom(mode: 'overview' | 'focus'): void {
  if (root.dataset['zoom'] !== mode) root.dataset['zoom'] = mode;
}

/** 換場景時重建名牌。頻率是「每次換房間」，不是每幀。 */
export function setNameplates(items: readonly { text: string; wx: number; wy: number; accent: string }[]): void {
  for (const a of anchors) a.el.remove();
  anchors = items.map((it) => {
    const el = document.createElement('div');
    el.className = 'nameplate';
    el.dataset.accent = it.accent;
    el.textContent = it.text;
    root.appendChild(el);
    return { el, wx: it.wx, wy: it.wy };
  });
}

/**
 * 互動提示。每幀都會被呼叫，但只有文字真的變了才動 DOM ——
 * 每幀重設 textContent 會讓瀏覽器一直重算排版。
 */
export function setPrompt(text: string | null, wx = 0, wy = 0, onActivate?: () => void): void {
  if (text === null) {
    if (promptText !== '') {
      promptText = '';
      promptEl.hidden = true;
    }
    promptAnchor = null;
    promptAction = null;
    return;
  }
  if (text !== promptText) {
    promptText = text;
    // 觸控裝置沒有 E 鍵，畫個鍵帽只會誤導；改成單純的「可點」箭頭
    promptEl.innerHTML = `<b>${isCoarse() ? '▸' : 'E'}</b>${text}`;
    promptEl.hidden = false;
  }
  promptAnchor = { wx, wy };
  promptAction = onActivate ?? null;
}

/** 每幀把世界座標換算成螢幕像素。只碰 transform，不觸發重排。 */
export function syncLabels(cam: Camera, screen: Screen): void {
  const s = screen.scale;
  for (const a of anchors) {
    a.el.style.transform = `translate(${(a.wx - cam.x) * s}px, ${(a.wy - cam.y) * s}px) translate(-50%, -100%)`;
  }
  // 走近時只有「正在被提示的那一個」讓位，其餘站牌照常掛著（見 setSpotSuppressed）
  for (let i = 0; i < spots.length; i++) {
    const s2 = spots[i]!;
    s2.el.hidden = i === suppressedSpot;
    if (s2.el.hidden) continue;
    s2.el.style.transform = `translate(${(s2.wx - cam.x) * s}px, ${(s2.wy - cam.y) * s}px) translate(-50%, -100%)`;
  }
  for (const b of bubbles) {
    if (b.el.hidden) continue;
    b.el.style.transform = `translate(${(b.wx - cam.x) * s}px, ${(b.wy - cam.y) * s}px) translate(-50%, -100%)`;
  }
  // 看板文字貼在面板中央，所以是 -50%/-50% 而不是浮在上方的 -100%
  if (topicAnchor) {
    topicEl.style.transform = `translate(${(topicAnchor.wx - cam.x) * s}px, ${(topicAnchor.wy - cam.y) * s}px) translate(-50%, -50%)`;
  }
  if (promptAnchor) {
    promptEl.style.transform = `translate(${(promptAnchor.wx - cam.x) * s}px, ${(promptAnchor.wy - cam.y) * s}px) translate(-50%, -100%)`;
  }
  // 互動提示與暱稱都浮在角色頭上，同時出現會疊在一起。
  // 提示是功能性的、暱稱只是裝飾，所以有提示時讓暱稱讓位。
  nickEl.hidden = promptAnchor !== null;
  if (!nickEl.hidden) {
    nickEl.style.transform = `translate(${(nickAnchor.wx - cam.x) * s}px, ${(nickAnchor.wy - cam.y) * s}px) translate(-50%, -100%)`;
  }
}

/** 面板開啟時整層隱藏，避免名牌浮在彈窗上面。 */
export function setLabelsVisible(v: boolean): void {
  root.style.opacity = v ? '1' : '0';
}

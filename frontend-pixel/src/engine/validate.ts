import { ZONES, hasZone, unregisterZone } from '../world/zones';
import { hasPanel, listPanels, unregisterPanel } from './panel';
import type { Room } from '../world/types';
import type { ZoneDef } from './zone';

/**
 * 接線驗證（規格 §9 ③、§4.2）。
 *
 * 三條原則：
 * 1. **dev 與 prod 都跑。** 提案四把它包在 `if (import.meta.env.DEV)` 裡，
 *    等於正式 build 完全不驗 —— 而現場 demo 跑的正是正式 build。
 * 2. **壞掉的東西是「被移除」不是 throw。** 白畫面在台上是致命的，
 *    少一個面板不是。
 * 3. **一律 console.error。** 測試的「全程無執行期錯誤」斷言會抓到它，
 *    所以接線壞掉在 CI 就是紅燈，不必等到有人手動開那個房間。
 *
 * 它只 import `world/zones` 與 `engine/panel`（葉節點），不 import 任何
 * React 元件 —— 這樣 `game/` 也可以安全地用它而不會把 ui 拖進遊戲層。
 */

let last: string[] = [];

/** 最近一次 validateWiring() 的結果。tests/zones.mjs 透過 debug 探針讀它。 */
export const lastWiringProblems = (): string[] => last;

export function validateWiring(): string[] {
  const problems: string[] = [];
  const bad = (msg: string): void => {
    problems.push(msg);
    console.error(`[wiring] ${msg}`);
  };

  // ── 面板：只有「根本不能渲染」才移除 ──
  for (const [id, def] of listPanels()) {
    if (typeof def.Component !== 'function') {
      bad(`面板「${id}」沒有可渲染的 Component，已移除`);
      unregisterPanel(id);
      continue;
    }
    if (def.id !== id) bad(`面板「${id}」的 def.id 是「${def.id}」，barrel 的 key 與 id 必須一致`);
  }

  // ── zone 第一輪：結構性錯誤 → 移除 ──
  const built = new Map<string, Room>();
  for (const [id, z] of Object.entries(ZONES) as [string, ZoneDef][]) {
    const drop = (msg: string): void => {
      bad(`${msg}，已移除 zone「${id}」`);
      unregisterZone(id);
    };
    if (typeof z.build !== 'function') {
      drop(`zone「${id}」沒有 build()`);
      continue;
    }
    if (z.id !== id) {
      drop(`zone「${id}」的 def.id 是「${z.id}」，barrel 的 key 與 id 必須一致`);
      continue;
    }
    let room: Room;
    try {
      room = z.build({ id, params: {}, from: null });
    } catch (e) {
      drop(`zone「${id}」的 build() 在空 params 下丟出「${e instanceof Error ? e.message : String(e)}」`);
      continue;
    }
    if (room.id !== id) {
      drop(`zone「${id}」build 出來的 room.id 是「${room.id}」`);
      continue;
    }
    built.set(id, room);
  }

  // ── zone 第二輪：出口指到不存在的地方 → 只回報不移除 ──
  // （整個 zone 還是可以進，只是某一道門會 fallback 回中庭；
  //   把整個 zone 拔掉反而是更大的傷害。）
  for (const [id, room] of built) {
    if (!hasZone(id)) continue; // 第一輪已經被移除
    for (const p of room.portals) {
      if (p.action.type === 'travel' && !hasZone(p.action.scene)) {
        bad(`zone「${id}」的門「${p.label}」指向不存在的 zone「${p.action.scene}」`);
      }
      if (p.action.type === 'panel' && !hasPanel(p.action.panel)) {
        bad(`zone「${id}」的門「${p.label}」要開不存在的面板「${p.action.panel}」`);
      }
    }
    for (const it of room.interactables) {
      if (!it.panel && !it.run) {
        bad(`zone「${id}」的互動點「${it.label}」既沒有 panel 也沒有 run，按 E 不會有任何事`);
      }
      if (it.panel && !hasPanel(it.panel)) {
        bad(`zone「${id}」的互動點「${it.label}」要開不存在的面板「${it.panel}」`);
      }
    }
  }

  // ── gateway ──
  for (const [id, z] of Object.entries(ZONES) as [string, ZoneDef][]) {
    const g = z.gateway;
    if (!g || !hasZone(id)) continue;
    if (g.action && !hasPanel(g.action.panel)) {
      bad(`zone「${id}」的 gateway 要開不存在的面板「${g.action.panel}」`);
    }
    // 門牌長度（名牌寬度上限 128px）不在這裡驗：CJK 與拉丁字元寬度不同，
    // 用 .length 會把「MAX 交易所」誤判成超長。那條交給 tests/zones.mjs
    // 量真實 DOM 的 offsetWidth。
  }

  last = problems;
  return problems;
}

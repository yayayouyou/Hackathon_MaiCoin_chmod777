import { ZONES, listZones } from '../world/zones';
import { listPanels } from './panel';
import { FEATURES } from '../features/registry';
import { door } from './doors';
import { lastWiringProblems } from './validate';
import type { ZoneDef, ZoneParams } from './zone';
import type { Room } from '../world/types';

/**
 * 註冊表的唯讀快照，給 `tests/zones.mjs` 用（掛在 `window.__zones`，
 * 只有 `?debug=1` 才會掛，見 `game/index.ts` 的 debug 區塊）。
 *
 * 為什麼要有這個檔：zone 的不變式（每個 zone 都建得起來、門位兩兩不重疊、
 * travel 目標存在、FEATURES 的落點真的踩得到）都是**資料層的**，用
 * playwright 開頁面點來點去驗要花幾十秒而且驗不完整。把資料吐成 JSON
 * 讓測試直接算，一秒驗完全部。
 *
 * 它只 import 葉節點（zones / engine / features），沒有 React、沒有 game，
 * 所以 `game/index.ts` 可以安全地 import 它。
 */

/** 用來戳出 zone 裡「有帶參數才會走到」的分支。 */
const REPRESENTATIVE: ZoneParams = {
  roomId: 'eth-merge',
  title: '測試討論室',
  accent: 'violet',
  tag: '測試',
  online: 7,
  sentiment: -30,
};

/**
 * 一個 zone 的唯讀快照。
 *
 * build 包 try/catch 的理由是「失敗要指向壞掉的 zone，不能讓整份契約測試
 * 一起消失」：這個函式對每個 zone 各 build 兩次，任何一個丟例外都會讓
 * `window.__zones()` 本身 throw，於是 `tests/zones.mjs` 第一行就死掉、
 * 21 項斷言（含最關鍵的「validateWiring() 零問題」）一項都跑不到，
 * 而錯誤訊息還會指向 probe.ts 而不是出問題的 zone。
 */
function probeZone(z: ZoneDef, params: ZoneParams) {
  let room: Room;
  try {
    room = z.build({ id: z.id, params, from: null });
  } catch (e) {
    return {
      buildError: e instanceof Error ? e.message : String(e),
      id: z.id,
      title: '',
      w: 0,
      h: 0,
      accent: z.accent,
      portals: [],
      interactables: [],
      portalProps: [],
    };
  }
  return {
    buildError: null as string | null,
    id: room.id,
    title: room.title,
    w: room.w,
    h: room.h,
    accent: room.accent,
    portals: room.portals.map((p) => ({
      rect: p.rect,
      label: p.label,
      accent: p.accent,
      action: p.action,
    })),
    interactables: room.interactables.map((it) => ({
      rect: it.rect,
      label: it.label,
      panel: it.panel ?? null,
      hasRun: typeof it.run === 'function',
    })),
    /** 場上實際畫出來的拱門道具座標，用來比對 portal.rect 有沒有抄歪 */
    portalProps: room.props.flatMap((p) => (p.kind === 'portal' ? [{ x: p.x, y: p.y }] : [])),
  };
}

export function worldProbe() {
  return {
    /** 靜態 barrel 的 key。含已被 validateWiring() 移除的 zone */
    zoneIds: Object.keys(ZONES),
    /**
     * 執行期真的還在表裡的 zone，順序與 `empty` / `rep` 一致。
     *
     * `zoneIds` 與 `empty` 長度可能不同（被移除的 zone 只會從後者消失），
     * 拿 `zoneIds[i]` 去對齊 `empty[i]` 一旦有 zone 被移除就整排錯位 ——
     * 而「有 zone 被移除」正是這套框架設計來處理的那個情境。
     */
    liveZoneIds: listZones().map((z) => z.id),
    panelIds: listPanels().map(([id]) => id),
    /** validateWiring() 的結果。非空 = 有人接線接錯了 */
    wiring: lastWiringProblems(),
    gateways: listZones().flatMap((z) => (z.gateway ? [{ zone: z.id, ...z.gateway }] : [])),
    /** 空 params 與代表性 params 各 build 一次，條件分支才驗得到 */
    empty: listZones().map((z) => probeZone(z, {})),
    rep: listZones().map((z) => probeZone(z, REPRESENTATIVE)),
    features: FEATURES.map((f) => ({
      id: f.id,
      panel: f.panel ?? null,
      place: f.place ?? null,
    })),
    /** door() 的門墊公式。守「門座標只寫一次」 */
    doorSample: door({ id: 'lobby', accent: 'cyan' }, 100, 100, { label: '樣本' }),
  };
}

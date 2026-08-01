import { lobby } from './lobby';
import { discussion } from './discussion';
import type { ZoneDef } from '../../engine/zone';

/**
 * ★ 全隊 append 點 1/4。
 *
 * 新增一個區塊 = 上面一行 import + 下面一行 key。就這樣。
 * `satisfies` 保證每個值都是合法 ZoneDef；`keyof typeof` 讓 ZoneId
 * 自動長出來，沒有人需要手改一個封閉 union。
 *
 * 刻意**不用** `import.meta.glob`（規格 §4.2）：eager glob 讓任何一個 zone
 * 在 module 層 throw = 整包白畫面，而且「兩個人取同一個 id」在 glob 下是
 * 執行期才炸、在 barrel 下是 git 衝突 —— 後者 5 秒可解。
 */
export const ZONES = {
  lobby,
  discussion,
} as const satisfies Record<string, ZoneDef>;

export type ZoneId = keyof typeof ZONES;

/**
 * 找不到任何 zone 時的退路。
 * 它是唯一一個 validateWiring() 不准移除的 zone —— 沒有中庭可以退，
 * `swapRoom()` 就只能 throw，而 throw 在渲染迴圈裡就是白畫面。
 */
export const FALLBACK_ZONE_ID: ZoneId = 'lobby';

/**
 * 執行期的可變表。barrel 本身是 `as const` 的常數（型別來源），
 * 這張表才是實際被查的（validateWiring 可以從這裡移除壞掉的 zone）。
 */
const TABLE: Record<string, ZoneDef> = { ...ZONES };

/** 找不到就退回中庭並大聲抱怨。渲染迴圈永遠不能因為一個 id 打錯而死。 */
export function getZone(id: string): ZoneDef {
  const z = TABLE[id];
  if (z) return z;
  console.error(`[zones] 找不到 zone「${id}」，退回中庭`);
  return ZONES[FALLBACK_ZONE_ID];
}

export const hasZone = (id: string): boolean => Object.hasOwn(TABLE, id);

export const listZones = (): ZoneDef[] => Object.values(TABLE);

/** 壞掉的 zone 是「被移除」不是 throw。中庭例外，見上。 */
export function unregisterZone(id: string): void {
  if (id === FALLBACK_ZONE_ID) {
    console.error(`[zones] 中庭「${id}」壞掉也不能移除，保留以免整個世界進不去`);
    return;
  }
  delete TABLE[id];
}

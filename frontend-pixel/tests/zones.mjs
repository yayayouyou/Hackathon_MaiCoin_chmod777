import { openPage, gameState, settle } from './lib/harness.mjs';

/** run.mjs 掃描 tests/*.mjs，套件名字從這裡讀（省略就用檔名）。 */
export const title = 'zone 註冊表';

/**
 * zone 註冊表的不變式（規格 §11）。
 *
 * 這個套件幾乎不操作瀏覽器 —— 它讀 `window.__zones()`（`engine/probe.ts`
 * 吐出來的唯讀 JSON）直接在 node 這邊算。理由：座標與接線是**資料層**的
 * 錯誤，用 playwright 走過去按 E 驗一次要幾十秒而且驗不完整；把資料吐出來
 * 一秒就能驗完全部，而且新 zone 加進 barrel 的當下就自動被納入。
 *
 * 最後一項刻意放在最後：它會故意送一個不存在的 zone id，getZone() 會
 * console.error（那正是要驗的行為），所以「全程無執行期錯誤」必須先驗完。
 */

/** 兩個矩形有沒有真的重疊（碰邊不算）。 */
const overlaps = (a, b) =>
  a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;

const inside = (r, x, y) => x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h;

/** legacy 兩房是在尺寸上限訂出來之前就存在的，不受 640x384 約束。 */
const LEGACY = new Set(['lobby', 'discussion']);
const FALLBACK = 'lobby';

export default async function zones({ browser, ok }) {
  const page = await openPage(browser);
  const p = await page.evaluate(() => window.__zones());

  // ── 接線 ──
  ok('validateWiring() 零問題', p.wiring.length === 0, p.wiring.join(' / '));
  ok('barrel 至少有中庭與一個 legacy zone', p.zoneIds.length >= 2, p.zoneIds.join(', '));
  ok(`退路 zone「${FALLBACK}」在表內`, p.zoneIds.includes(FALLBACK), p.zoneIds.join(', '));
  ok('面板註冊表非空', p.panelIds.length >= 8, `${p.panelIds.length} 個：${p.panelIds.join(', ')}`);

  // 靜態 barrel 與執行期表的差集 = 被 validateWiring() 移除的 zone。
  // 下面所有以 liveZoneIds 對齊的斷言，在這條紅燈時才讀得懂。
  const removed = p.zoneIds.filter((id) => !p.liveZoneIds.includes(id));
  ok('沒有 zone 被 validateWiring() 移除', removed.length === 0, removed.join(', '));

  // ── 每個 zone 都建得起來，空 params 與代表性 params 各一次 ──
  // ⚠ 對齊用 liveZoneIds 不是 zoneIds：後者是靜態 barrel（含已被移除的），
  //   拿它的索引去對 empty/rep 只要有一個 zone 被移除就整排錯位。
  for (const [tag, rooms] of [
    ['空 params', p.empty],
    ['帶 params', p.rep],
  ]) {
    const broken = rooms.filter((r) => r.buildError);
    ok(`${tag} 每個 zone 的 build() 都不丟例外`, broken.length === 0,
      broken.map((r) => `${r.id}: ${r.buildError}`).join(' / '));
    const wrong = rooms.flatMap((r, i) => (r.id === p.liveZoneIds[i] ? [] : [`${p.liveZoneIds[i]}→${r.id}`]));
    ok(`${tag} 每個 zone 都 build 得起來且 room.id 對得上`, wrong.length === 0,
      wrong.join(', ') || `${rooms.length} 個`);
  }

  // 帶了不同 params 就該長出不同房間，否則 params 根本沒接上
  const paramSensitive = p.empty.some((e, i) => e.title !== p.rep[i].title || e.accent !== p.rep[i].accent);
  ok('至少一個 zone 的 build() 真的吃 params', paramSensitive,
    p.rep.map((r) => `${r.id}:${r.title}`).join(', '));

  // ── 出口 ──
  const known = new Set(p.liveZoneIds);
  const dangling = [];
  const noWayBack = [];
  for (const r of p.empty) {
    const travels = r.portals.filter((x) => x.action.type === 'travel');
    for (const t of travels) if (!known.has(t.action.scene)) dangling.push(`${r.id}→${t.action.scene}`);
    if (r.id !== FALLBACK && !travels.some((t) => t.action.scene === FALLBACK)) noWayBack.push(r.id);
  }
  ok('每道 travel 門的目的地都存在於 barrel', dangling.length === 0, dangling.join(', '));
  ok('每個非中庭 zone 至少一道門指回中庭', noWayBack.length === 0, noWayBack.join(', '));

  const orphanPanels = p.empty.flatMap((r) =>
    r.interactables.filter((it) => !it.hasRun && !p.panelIds.includes(it.panel)).map((it) => `${r.id}:${it.label}`),
  );
  ok('每個互動點都接到已註冊的面板或 run()', orphanPanels.length === 0, orphanPanels.join(', '));

  // ── 門座標只寫一次 ──
  // door(x,y) 的門墊必須是 (x+3, y+26, 26, 38)。這條守住 engine/doors.ts 的公式。
  const d = p.doorSample;
  ok('door() 的門墊 = (x+3, y+26, 26, 38)',
    d.prop.x === 100 && d.prop.y === 100 &&
    d.portal.rect.x === 103 && d.portal.rect.y === 126 &&
    d.portal.rect.w === 26 && d.portal.rect.h === 38,
    JSON.stringify(d.portal.rect));

  // 真房間裡的每道門，portal.rect 也必須對得上它的拱門道具 —— 抓「拱門畫在
  // 這裡、觸發區卻在那裡」這種手抄失誤（症狀是看得到門但走過去沒反應）。
  const mismatched = [];
  for (const r of p.empty) {
    for (const portal of r.portals) {
      const hit = r.portalProps.some(
        (pp) => portal.rect.x === pp.x + 3 && portal.rect.y === pp.y + 26,
      );
      if (!hit) mismatched.push(`${r.id}:${portal.label}`);
    }
  }
  ok('每道門的觸發區都對齊它的拱門道具', mismatched.length === 0, mismatched.join(', '));

  // ── gateway 契約 ──
  const lobby = p.empty.find((r) => r.id === FALLBACK);
  ok('每個宣告 gateway 的 zone 都在中庭真的有一道門',
    p.gateways.every((g) =>
      g.pinned
        ? lobby.portalProps.some((pp) => pp.x === g.pinned.x && pp.y === g.pinned.y)
        : true,
    ),
    p.gateways.map((g) => `${g.zone}@${g.pinned ? `${g.pinned.x},${g.pinned.y}` : 'auto'}`).join(' '));

  ok('中庭的門數 = 有 gateway 的 zone 數', lobby.portals.length === p.gateways.length,
    `門 ${lobby.portals.length} 道 / gateway ${p.gateways.length} 個`);

  const bad = [];
  for (let i = 0; i < lobby.portals.length; i++) {
    for (let j = i + 1; j < lobby.portals.length; j++) {
      const a = lobby.portals[i].rect;
      const b = lobby.portals[j].rect;
      if (overlaps(a, b)) bad.push(`${lobby.portals[i].label}×${lobby.portals[j].label} 重疊`);
      const dx = Math.abs(a.x + a.w / 2 - (b.x + b.w / 2));
      if (dx < 128) bad.push(`${lobby.portals[i].label}×${lobby.portals[j].label} 中心距 ${dx} < 128`);
    }
  }
  ok('中庭門位兩兩不重疊且中心 x 距離 ≥ 128（名牌寬度上限）', bad.length === 0, bad.join('; '));

  const plates = await page.locator('#world-labels .nameplate').count();
  ok('大廳名牌數 = 有 gateway 的 zone 數', plates === p.gateways.length,
    `名牌 ${plates} 片 / gateway ${p.gateways.length} 個`);

  // ── 新 zone 的尺寸上限（規格 §6.3：640x384 是多數桌機取景成功的上限）──
  const newRooms = p.empty.filter((r) => !LEGACY.has(r.id));
  const oversize = newRooms.filter((r) => r.w > 640 || r.h > 384);
  ok('新 zone 的房間不超過 640x384', oversize.length === 0,
    oversize.map((r) => `${r.id} ${r.w}x${r.h}`).join(', ') || `legacy 三房豁免，新 zone ${newRooms.length} 個`);

  // ── FEATURES 的落點必須踩得到 ──
  const badPlace = [];
  for (const f of p.features) {
    if (f.panel && !p.panelIds.includes(f.panel)) badPlace.push(`${f.id} 的面板「${f.panel}」沒註冊`);
    if (!f.place) continue;
    const room = p.empty.find((r) => r.id === f.place.zone);
    if (!room) {
      badPlace.push(`${f.id} 的 zone「${f.place.zone}」不存在`);
      continue;
    }
    const hit =
      room.interactables.some((it) => inside(it.rect, f.place.wx, f.place.wy)) ||
      room.portals.some((pt) => inside(pt.rect, f.place.wx, f.place.wy));
    if (!hit) badPlace.push(`${f.id} 的落點 (${f.place.wx},${f.place.wy}) 不在任何互動點內`);
  }
  ok('每個 FEATURES 落點都踩得到既有互動點', badPlace.length === 0, badPlace.join('; '));

  ok('全程無執行期錯誤', page.collectedErrors.length === 0, page.collectedErrors[0] ?? '');

  // ── 未知 zone id：退回中庭，不是白畫面 ──
  // ⚠ 這一步之後 collectedErrors 會有一則 [zones] 抱怨，那是刻意的。
  await page.evaluate(() => window.__travel('__no_such_zone__'));
  await settle(page);
  const after = await gameState(page);
  ok('未知 zone id 退回中庭而不是白畫面', after.room.id === FALLBACK && after.ready === true,
    `room=${after.room.id} ready=${after.ready}`);
  ok('退回時有在 console 大聲抱怨',
    page.collectedErrors.some((e) => e.includes('__no_such_zone__')),
    page.collectedErrors.join(' | ') || '（沒有任何訊息）');

  await page.close();
}

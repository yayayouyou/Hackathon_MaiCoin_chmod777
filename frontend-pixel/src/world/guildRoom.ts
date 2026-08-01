import { RECOLORS } from '../art/palette';
import { finish } from '../engine/kit';
import { door, doorPortals, doorProps } from '../engine/doors';
import { assemble, seats, station } from '../engine/parts';
import type { Prop, Room } from './types';

/**
 * 交易者公會 —— 排行榜與策略牆的新家。
 *
 * 608×352（在 640×384 上限內）。主色 amber，地板用 tech（暗色科技磚），
 * 配上暖色調的環境光與木質家具，跟大廳的冷石材形成對比。
 *
 * 構圖：
 *   上方（y 32..120）　裝飾帶：K 線看板 + 螢幕牆 + 植物
 *   中段（y 120..240）　兩個功能站點左右分列：排行看板(152,140) / 策略牆(400,140)
 *   中央走廊（y 220..270）　出生點(304,236)，貫通淨空確保 R8 直線可達
 *   下方（y 260..320）　返回門(288,272) + 座位圈 + NPC
 *
 * 從 spawn (304,236) 到排行看板站位 (180,192)：直線不穿過任何 solid。
 * 從 spawn (304,236) 到策略牆站位 (444,196)：直線不穿過任何 solid。
 * 從 spawn (304,236) 到返回門 (301,310)：往下直走，淨空。
 */
export function makeGuildRoom(): Room {
  const doors = [
    door({ id: 'lobby', accent: 'amber' }, 288, 272, {
      label: '← 返回大廳',
      enterLabel: '返回大廳',
    }),
  ];

  const stations = [
    station({
      prop: { kind: 'board', x: 152, y: 140 },
      label: '查看熱門排行',
      sign: '排行榜',
      accent: 'cyan',
      panel: 'ranking',
    }),
    station({
      prop: { kind: 'noteboard', x: 400, y: 140 },
      label: '看看大家的策略',
      sign: '策略牆',
      accent: 'amber',
      panel: 'strategies',
    }),
  ];

  const seating = [seats(80, 280), seats(460, 280)];

  const decor: Prop[] = [
    // 上牆裝飾
    { kind: 'chartboard', x: 40, y: 40 },
    { kind: 'screenwall', x: 180, y: 32, w: 248 },
    { kind: 'chartboard', x: 472, y: 40 },

    // 中段氛圍
    { kind: 'pillar', x: 56, y: 140 },
    { kind: 'pillar', x: 544, y: 140 },
    { kind: 'plant', x: 32, y: 200 },
    { kind: 'plant', x: 568, y: 200 },
    { kind: 'bench', x: 240, y: 180 },
    { kind: 'bench', x: 340, y: 180 },

    // 下方
    { kind: 'plant', x: 32, y: 300 },
    { kind: 'plant', x: 568, y: 300 },
  ];

  const built = assemble([...stations, ...seating]);

  return finish({
    id: 'guild',
    title: '交易者公會',
    w: 608,
    h: 352,
    accent: 'amber',
    // 暖色環境光，跟大廳的冷灰 #d2d4e2 形成對比
    ambient: '#d8cebe',
    // 暗色科技磚，讓琥珀色的光池特別突出
    floor: 'guild',
    // 地面徽章放在出生點附近，讓人一進來就知道到了
    emblems: [{ x: 304, y: 260, r: 48 }],
    props: [...decor, ...built.props, ...doorProps(doors)],
    portals: doorPortals(doors),
    interactables: built.interactables,
    npcs: [
      { x: 112, y: 300, facing: 'up', recolor: RECOLORS.npcAmber },
      { x: 492, y: 300, facing: 'up', recolor: RECOLORS.npcRose },
      { x: 340, y: 310, facing: 'left', recolor: RECOLORS.npcGreen },
    ],
    spawn: { x: 304, y: 236 },
  });
}

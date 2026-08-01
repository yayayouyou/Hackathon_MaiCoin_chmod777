import { defineZone } from '../../../engine/zone';
import { makeGuildRoom } from '../../guildRoom';

/**
 * 交易者公會 —— 排行榜與策略牆的所在地。
 *
 * 從大廳西翼的琥珀色拱門傳送過來。暖色木質空間，跟大廳的冷石材
 * 與 MAX 翼的品牌藍形成三段材質對比。
 *
 * gateway.pinned 告訴測試：大廳在 (128,250) 要有一道通往這裡的門。
 */
export const guild = defineZone({
  id: 'guild',
  title: '交易者公會',
  accent: 'amber',
  gateway: {
    label: '交易者公會',
    accent: 'amber',
    pinned: { x: 128, y: 250 },
  },
  build: () => makeGuildRoom(),
});

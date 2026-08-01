import { buildCharSprites, type CharSprites } from '../art/sprites';
import { drawSprite, drawShadow } from './sprite';
import { CHAR_W, CHAR_H } from './player';
import type { NpcSpec } from '../world/types';

/** 站樁 NPC：不會移動，用同一份角色像素圖換色而已。 */
export type Npc = { x: number; y: number; dir: NpcSpec['facing']; sprites: CharSprites };

export function createNpc(spec: NpcSpec): Npc {
  return { x: spec.x, y: spec.y, dir: spec.facing, sprites: buildCharSprites(spec.recolor) };
}

export function drawNpc(ctx: CanvasRenderingContext2D, n: Npc): void {
  const set =
    n.dir === 'down'
      ? n.sprites.down
      : n.dir === 'up'
        ? n.sprites.up
        : n.dir === 'right'
          ? n.sprites.side
          : n.sprites.sideLeft;
  drawShadow(ctx, n.x, n.y - 1, 7, 3);
  drawSprite(ctx, set[4]!, n.x - CHAR_W / 2, n.y - CHAR_H);
}

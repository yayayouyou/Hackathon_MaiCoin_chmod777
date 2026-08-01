import { openPage, gameState, clickWorld } from './lib/harness.mjs';

const hold = async (page, key, ms) => {
  await page.keyboard.down(key);
  await page.waitForTimeout(ms);
  await page.keyboard.up(key);
  await page.waitForTimeout(120);
};

/** run.mjs 掃描 tests/*.mjs，套件名字從這裡讀（省略就用檔名）。 */
export const title = '移動與鏡頭';

/** 移動、死區鏡頭、碰撞滑動，以及「走動時 React 完全不重繪」。 */
export default async function movement({ browser, ok }) {
  // ── 死區鏡頭 ──
  {
    const page = await openPage(browser);
    const a = await gameState(page);
    await hold(page, 'KeyD', 300);
    const mid = await gameState(page);
    ok('死區內移動鏡頭不動', mid.cam.x === a.cam.x && mid.px > a.px,
      `px ${a.px.toFixed(0)}→${mid.px.toFixed(0)}, cam.x ${a.cam.x}`);

    await hold(page, 'KeyD', 1600);
    const far = await gameState(page);
    ok('跨過死區邊界鏡頭開始推', far.cam.x > mid.cam.x,
      `cam.x ${mid.cam.x.toFixed(0)}→${far.cam.x.toFixed(0)}`);

    await hold(page, 'KeyD', 6000);
    const end = await gameState(page);
    ok('鏡頭夾在世界邊界內不露黑邊', Math.abs(end.cam.x - (end.room.w - end.view.w)) < 1,
      `cam.x ${end.cam.x.toFixed(1)} / max ${end.room.w - end.view.w}`);
    ok('角色被右牆擋住', end.px < end.room.w - 16, `px ${end.px.toFixed(1)}`);
    await page.close();
  }

  // ── 碰撞與滑動 ──
  {
    const page = await openPage(browser);
    await hold(page, 'KeyS', 4000);
    const s1 = await gameState(page);
    await hold(page, 'KeyS', 1500);
    const s2 = await gameState(page);
    ok('撞牆後不再穿透', Math.abs(s2.py - s1.py) < 0.5, `py ${s1.py.toFixed(1)}→${s2.py.toFixed(1)}`);

    const before = s2.px;
    await page.keyboard.down('KeyS');
    await page.keyboard.down('KeyD');
    await page.waitForTimeout(1200);
    await page.keyboard.up('KeyS');
    await page.keyboard.up('KeyD');
    const s3 = await gameState(page);
    ok('貼著牆斜走會沿牆滑動', s3.px > before + 20, `px ${before.toFixed(0)}→${s3.px.toFixed(0)}`);
    await page.close();
  }

  // ── 點擊移動與鍵盤接管 ──
  {
    const page = await openPage(browser);
    const a = await gameState(page);
    await clickWorld(page, a.px + 140, a.py + 60);
    await page.waitForTimeout(600);
    const c = await gameState(page);
    ok('點擊會朝目標移動', c.px > a.px + 20, `px ${a.px.toFixed(0)}→${c.px.toFixed(0)}`);

    await hold(page, 'KeyA', 400);
    const d = await gameState(page);
    await page.waitForTimeout(600);
    const e = await gameState(page);
    ok('WASD 立即接管點擊路徑', Math.abs(e.px - d.px) < 0.5,
      `放開後 px ${d.px.toFixed(1)}→${e.px.toFixed(1)}`);
    await page.close();
  }

  // ── 走動期間 React 不重繪 ──
  // 每幀變動的東西（提示位置、暱稱）刻意走命令式 DOM，不進 uiStore。
  // 這一項就是在守住那個架構決策。
  {
    const page = await openPage(browser);
    const counts = await page.evaluate(async () => {
      const watch = (sel) => {
        let n = 0;
        new MutationObserver((ms) => (n += ms.length)).observe(document.querySelector(sel), {
          subtree: true,
          childList: true,
          attributes: true,
          characterData: true,
        });
        return () => n;
      };
      const ui = watch('#ui-root');
      const labels = watch('#world-labels');
      const ev = (type, code) => window.dispatchEvent(new KeyboardEvent(type, { code }));
      ev('keydown', 'KeyD');
      await new Promise((r) => setTimeout(r, 2000));
      ev('keyup', 'KeyD');
      return { ui: ui(), labels: labels() };
    });
    ok('走動 2 秒期間 React 零 DOM 變動', counts.ui === 0, `#ui-root ${counts.ui} 次`);
    ok('世界標籤層有在更新（命令式 DOM）', counts.labels > 50, `#world-labels ${counts.labels} 次`);
    await page.close();
  }
}

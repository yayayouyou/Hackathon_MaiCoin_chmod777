import { readFileSync } from 'node:fs';

/** run.mjs 掃描 tests/*.mjs，套件名字從這裡讀（省略就用檔名）。 */
export const title = '像素圖';

/**
 * 像素圖驗證。不需要瀏覽器 —— 直接讀原始碼裡的字串陣列。
 *
 * 手排像素圖最常犯的錯就是某一行少打一個字元。makeSprite() 在執行期會丟
 * 例外，但那要等到開機才會發現；這裡在測試階段就抓出來，還能一次列出全部。
 */
export default async function art({ ok }) {
  const palette = readFileSync('src/art/palette.ts', 'utf8');
  const keys = new Set([...palette.matchAll(/^\s*'?([0-9a-zA-Z])'?:\s*'#/gm)].map((m) => m[1]));
  keys.add('.');

  const problems = [];
  const sizes = [];

  for (const file of ['src/art/sprites.ts', 'src/art/tiles.ts']) {
    const src = readFileSync(file, 'utf8');
    for (const m of src.matchAll(/(?:export )?const (\w+) = \[([\s\S]*?)\n\];/g)) {
      const [, name, body] = m;
      const rows = [...body.matchAll(/'([^']*)'/g)].map((r) => r[1]);
      if (!rows.length) continue;
      const w = rows[0].length;
      rows.forEach((row, i) => {
        if (row.length !== w) problems.push(`${name}[${i}] 寬度 ${row.length}，應為 ${w}`);
        for (const ch of row) {
          if (!keys.has(ch)) problems.push(`${name}[${i}] 未知字元 "${ch}"`);
        }
      });
      sizes.push(`${name} ${w}x${rows.length}`);
    }
  }

  ok('調色盤有定義出顏色', keys.size > 20, `${keys.size} 個字元`);
  ok('找得到所有像素圖', sizes.length >= 15, `${sizes.length} 份`);
  ok('每份像素圖行寬一致且字元都在調色盤內', problems.length === 0, problems.slice(0, 5).join('; '));

  // 角色是 16x25 的 Q 版比例：頭 14 + 身 5 + 腿 5，約 1.8 頭身。
  // 上半身 20 行（含最上面刻意留空的一行給 bob 用）+ 腿部 5 行合成。
  //
  // ⚠ 這裡不數「剛好幾套」。原本寫死 3 套上半身 / 6 套腿部，結果是每加一個
  //   可選角色就要來改測試 —— 而它其實從來不保護任何東西：真正會出事的是
  //   尺寸。一行少打一個點不會報錯，只會讓那張圖整個錯位，而且錯得很難看出
  //   來源。所以只守「至少有基本的三向 + 六套步態」與「每一套都是對的尺寸」。
  const bodies = sizes.filter((s) => s.startsWith('BASE_'));
  const legs = sizes.filter((s) => s.startsWith('LEGS'));
  ok('每套上半身都是 16x20', bodies.length >= 3 && bodies.every((s) => s.endsWith('16x20')),
    `${bodies.length} 套：${bodies.join(', ')}`);
  ok('每套腿部都是 16x5', legs.length >= 6 && legs.every((s) => s.endsWith('16x5')),
    `${legs.length} 套：${legs.join(', ')}`);

  // bob() 是把整份上半身往上移一行。第 0 行若有內容，通過幀的頭頂會被裁掉，
  // 走路時看起來像頭在抽動 —— 這條就是在守住那一行必須留空。
  //
  // 數量要跟 bodies 對齊：新增一套上半身如果沒被這條正則掃到（例如換了寫法），
  // 它就會安靜地跳過檢查，而那正是最需要被檢查的那一套。
  const src = readFileSync('src/art/sprites.ts', 'utf8');
  const firstRows = [...src.matchAll(/const BASE_\w+ = \[\s*\n\s*'([^']*)'/g)].map((m) => m[1]);
  ok('每套上半身的第一行都留空給 bob()',
    firstRows.length === bodies.length && firstRows.every((r) => /^\.+$/.test(r)),
    `${firstRows.length}/${bodies.length} 套：${firstRows.join(' | ')}`);

  // 每個 accent 都要有對應的 CSS。TypeScript 守得住 props.ts 那份 Record，
  // 但守不住 styles.css —— 漏掉規則不會報錯，只會靜靜退回預設的青色，
  // 於是 MAX 的面板長得跟討論區一模一樣。加 accent 時最容易忘的就是這裡。
  const css = readFileSync('src/ui/styles.css', 'utf8');
  const accents = [...(/export type Accent =([^;]+);/.exec(readFileSync('src/world/types.ts', 'utf8'))?.[1] ?? '')
    .matchAll(/'(\w+)'/g)].map((m) => m[1]);
  const missing = accents
    .filter((a) => a !== 'cyan') // cyan 是預設值，不需要覆寫規則
    .flatMap((a) => [
      css.includes(`--${a}:`) ? null : `--${a} 變數`,
      css.includes(`.nameplate[data-accent='${a}']`) ? null : `${a} 名牌規則`,
      css.includes(`.panel[data-accent='${a}']`) ? null : `${a} 面板規則`,
    ])
    .filter(Boolean);
  ok('每個 accent 都有對應的 CSS 變數與規則', accents.length >= 4 && missing.length === 0,
    missing.length ? `缺少 ${missing.join('、')}` : accents.join(', '));
}

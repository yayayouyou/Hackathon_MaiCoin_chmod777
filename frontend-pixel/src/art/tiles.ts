/**
 * 16x16 場景 tile。地板與牆用手排像素圖（需要細緻的紋理），
 * 道具則由 game/shapes.ts 的斜角方塊組出來 —— 大型道具手排像素圖
 * 每張要 48 行以上，用共通的打光語彙組合反而更一致也更好動畫化。
 */

/**
 * 地板：深藍灰科技磚。
 *
 * 原本每格右側與底部各留 1px 深色溝縫，結果整個房間變成方格紙 ——
 * 每 16px 一條線，那個密度會蓋掉所有其他資訊。改成沒有格線，
 * 只用雜點與斑駁做材質；空間參照交給 render.ts 每 8 格一道的拼接縫。
 */
export const FLOOR = [
  '4444444445444444',
  '4454444444444434',
  '4444444444444444',
  '4444344444445444',
  '4444444444444444',
  '4444444444444444',
  '3444444444444444',
  '4444444444344444',
  '4444544444444444',
  '4444444444444444',
  '4444444444445444',
  '4544444444444444',
  '4444444344444444',
  '4444444444444444',
  '4444444444444444',
  '4444444445444443',
];

// 變體：雜點與斑駁位置不同，交錯鋪設打散重複感
export const FLOOR_ALT = [
  '4444444444444444',
  '4444444444544444',
  '4434444444444444',
  '4444444444444454',
  '4444444444444444',
  '4444544444344444',
  '4444444444444444',
  '4444444444444444',
  '4444444454444434',
  '4444444444444444',
  '4344444444444444',
  '4444444444444444',
  '4444445444444444',
  '4444444444444444',
  '4444344444445444',
  '4444444444444444',
];

/*
 * 牆整體比原本亮一階（2→3、1→2、3→4）。
 *
 * 原本的牆用 1/2/3 三個最深的中性色，環境光乘上去之後就是一片黑 ——
 * 走到房間上緣時畫面頂端會出現一條純黑的帶子，像是畫布沒畫完。
 * 牆是空間的邊界，它必須看得見才有「房間」的感覺。
 */

// 上方牆的頂蓋（俯視看到的牆頂面）
export const WALL_CAP = [
  '0000000000000000',
  '4444444444444444',
  '4444444444444444',
  '3333333333333333',
  '3333333333333333',
  '3333333333333333',
  '3333333333333333',
  '3333333333333333',
  '3333333333333333',
  '3333333333333333',
  '3333333333333333',
  '3333333333333333',
  '3333333333333333',
  '2222222222222222',
  '2222222222222222',
  '0000000000000000',
];

// 上方牆的立面：金屬板，有垂直接縫與一道橫向腰帶
export const WALL_FACE = [
  '4444444444444444',
  '3332333333233333',
  '3332333333233333',
  '3332333333233333',
  '3332333333233333',
  '3332333333233333',
  '2222222222222222',
  '3332333333233333',
  '3332333333233333',
  '3332333333233333',
  '3332333333233333',
  '3332333333233333',
  '3332333333233333',
  '3333333333333333',
  '2222222222222222',
  '0000000000000000',
];

// 左 / 右 / 下三面的矮邊牆
export const TRIM = [
  '0000000000000000',
  '4444444444444444',
  '3333333333333333',
  '3333333333333333',
  '2333333333333332',
  '2333333333333332',
  '2333333333333332',
  '2333333333333332',
  '2333333333333332',
  '2333333333333332',
  '2333333333333332',
  '2333333333333332',
  '3333333333333333',
  '3333333333333333',
  '2222222222222222',
  '0000000000000000',
];

/**
 * 大廳地板：拋光石板廣場。
 *
 * 這裡刻意保留每格的拼縫，跟科技磚的做法相反 —— 之前拿掉溝縫是因為
 * 深色場景配深色格線會變成方格紙。石板亮、縫只暗一階，讀起來是
 * 「一片片鋪的石材」而不是網格；真實的挑高大廳地板本來就看得到分割。
 */
export const PLAZA = [
  'yyyyyyyyyyyyyyyz',
  'yxxxxxxxxxxxxxxz',
  'yxxxxxxxxxxxxxxz',
  'yxxxxxxxxxxxxxxz',
  'yxxxxxxxxxxxxxxz',
  'yxxxxxxxxxxxxxxz',
  'yxxxxxxxxxxxxxxz',
  'yxxxxxxxxxxxxxxz',
  'yxxxxxxxxxxxxxxz',
  'yxxxxxxxxxxxxxxz',
  'yxxxxxxxxxxxxxxz',
  'yxxxxxxxxxxxxxxz',
  'yxxxxxxxxxxxxxxz',
  'yxxxxxxxxxxxxxxz',
  'yxxxxxxxxxxxxxxz',
  'zzzzzzzzzzzzzzzz',
];

/**
 * 變體只多兩顆雜點，而且刻意錯開到不同象限。
 *
 * 第一版兩塊各放三到四顆，兩種變體又是棋盤交錯 —— 結果整片地板變成
 * 每 16px 一顆的圓點壁紙。石材的雜點在真實尺度下本來就很稀疏。
 */
export const PLAZA_ALT = [
  'yyyyyyyyyyyyyyyz',
  'yxxxxxxxxxxxxxxz',
  'yxxxxxyxxxxxxxxz',
  'yxxxxxxxxxxxxxxz',
  'yxxxxxxxxxxxxxxz',
  'yxxxxxxxxxxxxxxz',
  'yxxxxxxxxxxxxxxz',
  'yxxxxxxxxxxxxxxz',
  'yxxxxxxxxxxxxxxz',
  'yxxxxxxxxxxxxxxz',
  'yxxxxxxxxxxxxxxz',
  'yxxxxxxxxxyxxxxz',
  'yxxxxxxxxxxxxxxz',
  'yxxxxxxxxxxxxxxz',
  'yxxxxxxxxxxxxxxz',
  'zzzzzzzzzzzzzzzz',
];

/**
 * MAX 情報室地板：深藍的機構石材。
 *
 * 用的是 k/l/m 這組深藍（原本是角色褲子的顏色，色相剛好就是 MAX 的品牌藍）。
 * 比大廳的冷灰石板暗一階、飽和度高得多 —— 大廳是公共廣場，情報室是
 * 交易所自己的地盤，材質必須明確不同，光的顏色換一換是不夠的。
 */
export const MAXFLOOR = [
  '5mmmmmmmmmmmmmml',
  '5mmmmmmmmmmmmmml',
  '5mmmmmmmmmmmmmml',
  '5mmmmmmmmmmmmmml',
  '5mmmmmmmmmmmmmml',
  '5mmmmmmmmmmmmmml',
  '5mmmmmmmmmmmmmml',
  '5mmmmmmmmmmmmmml',
  '5mmmmmmmmmmmmmml',
  '5mmmmmmmmmmmmmml',
  '5mmmmmmmmmmmmmml',
  '5mmmmmmmmmmmmmml',
  '5mmmmmmmmmmmmmml',
  '5mmmmmmmmmmmmmml',
  '5mmmmmmmmmmmmmml',
  'llllllllllllllll',
];

export const MAXFLOOR_ALT = [
  '5mmmmmmmmmmmmmml',
  '5mmmmmmmmmmmmmml',
  '5mmmmm5mmmmmmmml',
  '5mmmmmmmmmmmmmml',
  '5mmmmmmmmmmmmmml',
  '5mmmmmmmmmmmmmml',
  '5mmmmmmmmmmmmmml',
  '5mmmmmmmmmmmmmml',
  '5mmmmmmmmmmmmmml',
  '5mmmmmmmmmmmmmml',
  '5mmmmmmmmm5mmmml',
  '5mmmmmmmmmmmmmml',
  '5mmmmmmmmmmmmmml',
  '5mmmmmmmmmmmmmml',
  '5mmmmmmmmmmmmmml',
  'llllllllllllllll',
];

// 討論室右半場的暖色地毯
export const CARPET = [
  'wwwwwwwwwwwwwwwv',
  'wwwwwwwwwwwwwwwv',
  'wwwvwwwwwwwwwwwv',
  'wwwwwwwwwwwwwwwv',
  'wwwwwwwwwwwvwwwv',
  'wwwwwwwwwwwwwwwv',
  'wwwwwwwwwwwwwwwv',
  'wvwwwwwwwwwwwwwv',
  'wwwwwwwwwwwwwwwv',
  'wwwwwwwwwwwwwwwv',
  'wwwwwwwwvwwwwwwv',
  'wwwwwwwwwwwwwwwv',
  'wwwwwwwwwwwwwwwv',
  'wwwwwwwwwwwwwwwv',
  'wwwwwwwwwwwwwwwv',
  'vvvvvvvvvvvvvvvv',
];

/**
 * 交易者公會地板：暖色木板。
 *
 * 用 e/g/b 這組（頭髮棕→深棕→淺膚），橫向排列模擬木紋方向。
 * 每 4 行為一條木板，板間 1px 深色接縫。跟大廳冷灰石板、
 * 討論室科技磚形成三種截然不同的材質。
 */
export const GUILD = [
  'gggbggggggggggge',
  'ggggggggggbgggge',
  'ggggggggggggggge',
  'eeeeeeeeeeeeeeee',
  'gggggggbggggggge',
  'ggbgggggggggggge',
  'ggggggggggggggge',
  'eeeeeeeeeeeeeeee',
  'ggggggggggbgggge',
  'gggggggggggggbge',
  'ggggggggggggggge',
  'eeeeeeeeeeeeeeee',
  'gbggggggggggggge',
  'ggggggbgggggggge',
  'ggggggggggggggge',
  'eeeeeeeeeeeeeeee',
];

export const GUILD_ALT = [
  'gggggggggbggggge',
  'ggggggggggggggge',
  'gggbggggggggggge',
  'eeeeeeeeeeeeeeee',
  'ggggggggggggbgge',
  'ggggggggggggggge',
  'ggbgggggggggggge',
  'eeeeeeeeeeeeeeee',
  'ggggggbgggggggge',
  'ggggggggggggggge',
  'gggggggggggbggge',
  'eeeeeeeeeeeeeeee',
  'ggggggggggggggge',
  'ggggbgggggggggge',
  'ggggggggggggggge',
  'eeeeeeeeeeeeeeee',
];

/**
 * 牆腳收邊帶：牆與地板交接處的 AO（環境遮蔽）過渡。
 *
 * 上半是跟牆同色的深色，往下逐漸變淡消失。這讓牆「長在地板上」，
 * 而不是兩張貼圖剛好擺在旁邊。用 0/1/2 三個最深的中性色做漸層。
 * 只有 8px 高（半格），放在牆的下緣覆蓋。
 */
export const SKIRT = [
  '0000000000000000',
  '0000000000000000',
  '1010101010101010',
  '1010101010101010',
  '0101010101010101',
  '................',
  '................',
  '................',
  '................',
  '................',
  '................',
  '................',
  '................',
  '................',
  '................',
  '................',
];

export const TILE_ROWS = {
  FLOOR,
  FLOOR_ALT,
  PLAZA,
  PLAZA_ALT,
  MAXFLOOR,
  MAXFLOOR_ALT,
  WALL_CAP,
  WALL_FACE,
  TRIM,
  CARPET,
  GUILD,
  GUILD_ALT,
  SKIRT,
};

import { RECOLORS } from '../art/palette';
import { finish } from '../engine/kit';
import { door, doorPortals, doorProps } from '../engine/doors';
import { assemble, seats, station } from '../engine/parts';
import type { Accent, Prop, Room } from './types';

/**
 * 兩個房間的建構函式，被 `world/zones/{lobby,discussion}/index.ts` 呼叫。
 *
 * 房間內容不再是一長串手打座標：功能站點走 `engine/parts.ts` 的
 * `station()`（道具 + 互動範圍 + 站牌一次產出）、座位圈走 `seats()`、
 * 門走 `engine/doors.ts` 的 `door()`（門座標只寫一次）。純裝飾道具
 * 仍然直接列在 `decor` 陣列裡 —— 它們沒有重複的相對偏移，包一層抽象
 * 只會多一層要讀的東西。
 *
 * MAX 情報室原本是第三個房間，內容已經併進大廳的「MAX 資訊角」——
 * 命題單位就是 MAX，它的東西沒有理由藏在要傳送才到得了的地方。
 */

// ── 大廳 ────────────────────────────────────────────────────

/**
 * 大廳的構圖分成四條帶，由上而下：
 *
 *   ① 上牆（y 18..100）　行情跑馬燈橫貫整面牆，牆下一排設施：
 *      　　　　　　　　　　咖啡吧台 → K 線看板 → 冷錢包金庫 → K 線看板 → 礦機牆
 *   ② 中段（y 110..300）　柱列、熱門排行看板、討論區傳送門、MAX 資訊角
 *   ③ 中央（y 330..430）　金幣雕像立在地面徽章上 —— 全場的視覺中心
 *   ④ 下緣（y 420..490）　兩組盯盤圓桌，把原本空掉的房間下半部填起來
 *
 * 每一帶都有自己的功能與密度，這樣玩家從上往下掃過去才會覺得空間是被
 * 設計過的，而不是道具隨機散落。「充滿主題元素」的關鍵不是數量多，
 * 是每件道具都在講同一件事。
 *
 * 中段右半是 **MAX 資訊角**（公告 / 活動 / MAIA 三個站點 + 信託櫃檯 +
 * 代幣柱），佔的正是原本 MAX 傳送門的位置。命題單位就是 MAX，把它的
 * 東西放在一進場就看得到的地方，比擺一道要走過去才知道通往哪裡的門值錢。
 *
 * 排行看板（452,186）與討論區傳送門（272,250）的座標不能動 ——
 * 驗證腳本用世界絕對座標導航到它們。
 */
export function makeLobby(): Room {
  /**
   * 門。座標只寫這一次 —— prop 與門墊觸發區都由 `door()` 從同一組 x/y 推。
   * 討論區後面有 12 間房，所以它的動作是開選房面板而不是直接傳送。
   */
  const doors = [
    door({ id: 'discussion', accent: 'cyan' }, 272, 250, {
      label: '討論區',
      action: { type: 'panel', panel: 'roomPicker' },
    }),
  ];

  /** 功能站點：道具 + 互動範圍 + 常駐站牌，三件事一次寫完。 */
  const stations = [
    station({
      prop: { kind: 'board', x: 452, y: 186 },
      label: '查看熱門排行',
      sign: '排行榜',
      accent: 'cyan',
      panel: 'ranking',
    }),

    // ── MAX 資訊角（中段右側，原本 MAX 傳送門的位置）──
    //
    // 命題單位就是 MAX，它的東西沒有理由藏在一個要傳送才到得了的房間裡。
    // 三個站點全部走品牌藍，站牌也是藍的，一眼看得出這一區是誰的地盤。
    //
    // ⚠ 排版的硬約束是**從出生點 (480,322) 到每個站點的直線都要走得通**。
    //   這個世界沒有尋路：`walkTo()` 直線走、撞牆滑一下、0.7 秒沒進展就放棄
    //   （player.ts 的 STALL_GIVE_UP）。所以任何一件擋路的道具橫在出生點與
    //   站點之間，功能條導引就會靜默失敗 —— 人停在半路、提示指向別的東西。
    //   第一版把 MAIA 櫃檯放在 (540,240)，它 124px 寬的碰撞盒剛好橫在出生點
    //   與兩台終端機中間，三條路徑全斷。現在櫃檯退到右下、兩台終端機在上排，
    //   三條直線各自淨空。
    station({
      prop: { kind: 'terminal', x: 588, y: 150, accent: 'max' },
      label: '讀取官方消息',
      sign: '公告',
      accent: 'max',
      panel: 'maxNews',
    }),
    station({
      prop: { kind: 'terminal', x: 700, y: 150, accent: 'max' },
      label: '查看最新活動',
      sign: '活動',
      accent: 'max',
      panel: 'maxEvents',
    }),
    station({
      prop: { kind: 'counter', x: 700, y: 260, w: 120 },
      label: '與 MAIA 對話',
      sign: 'MAIA',
      accent: 'max',
      panel: 'agentChat',
    }),

    // ── 策略牆（中段左側）──
    //
    // 跟右邊的 MAX 資訊角對稱：右邊是官方發布的東西（藍），左邊是社群自己
    // 貼上來的東西（琥珀）。走進大廳往左往右，看到的是兩種不同來源的資訊，
    // 這個對比本身就是空間在講的話。
    //
    // 用便利貼牆而不是終端機：策略是人寫的、會被撕下來換掉的東西，
    // 一面貼滿紙條的牆比一台螢幕更像「大家在這裡交換做法」。
    // 它下面就是既有的盯盤圓桌，讀起來是「看完牆坐下來聊」。
    //
    // 站位 (244,232)，從出生點 (480,322) 過來的直線淨空：路徑最靠近的
    // 障礙是左側圓桌組（solid 在 x156..234, y264..304），而直線在 y264
    // 時已經走到 x328。
    station({
      prop: { kind: 'noteboard', x: 200, y: 150 },
      label: '看看大家的策略',
      sign: '策略牆',
      accent: 'amber',
      panel: 'strategies',
    }),
  ];

  /**
   * 盯盤座位圈。三組共用 `seats()` 的同一份偏移 —— 它們原本是手抄四次的，
   * 中段兩組與下緣兩組的凳子位置差了 1–2px。
   *
   * 原本中段右側還有一組 (712,250)，那塊地現在是 MAX 資訊角的櫃檯 ——
   * 四組一模一樣的圓桌本來就偏重複，讓出一組換一個有內容的角落划算。
   *
   * 圓桌都在 y 304 以上：出生點那一列（y 322）必須是一條貫通左右牆的
   * 淨空走道，否則從中央直線往右走會被圓凳卡住。
   */
  const seating = [seats(150, 250), seats(120, 430), seats(760, 430)];

  const decor: Prop[] = [
    // ① 上牆
    { kind: 'ticker', x: 16, y: 18, w: 928 },
    { kind: 'cafebar', x: 48, y: 52, w: 128 },
    { kind: 'chartboard', x: 248, y: 44 },
    { kind: 'vault', x: 408, y: 40 },
    { kind: 'chartboard', x: 536, y: 44 },
    { kind: 'minerrack', x: 700, y: 40 },
    { kind: 'minerrack', x: 752, y: 40 },
    { kind: 'minerrack', x: 804, y: 40 },

    // ② 中段
    { kind: 'pillar', x: 96, y: 150 },
    { kind: 'pillar', x: 848, y: 150 },
    { kind: 'plant', x: 60, y: 140 },
    { kind: 'plant', x: 884, y: 140 },
    { kind: 'bench', x: 48, y: 230 },
    { kind: 'bench', x: 880, y: 230 },

    // MAX 資訊角的招牌與打光。這兩件不是互動點，是「讓人一眼知道
    // 這一區是 MAX」的東西：信託櫃檯是 MAX 唯一講得出來的差異化故事
    // （法幣交由銀行信託保管），代幣柱是全場最強的光源之一。
    //
    // 兩件都貼在 y 96..168 這條帶上（上牆設施結束、終端機開始之前），
    // 碰撞盒全部高於站點的站位，不會擋到從出生點過來的三條直線。
    { kind: 'trustdesk', x: 640, y: 96, w: 140 },
    // 代幣柱站在公告終端機左邊當這一區的門柱。它的碰撞盒在 y 202..218，
    // 高於公告站點的站位（y 224），所以不擋從出生點過來的那條直線。
    { kind: 'maxtoken', x: 528, y: 150 },

    // ③ 中央：雕像立在徽章上，四角各一組盯盤圓桌把它圍起來
    { kind: 'pillar', x: 96, y: 330 },
    { kind: 'pillar', x: 848, y: 330 },
    { kind: 'coinstatue', x: 456, y: 350 },
    { kind: 'plant', x: 60, y: 420 },
    { kind: 'plant', x: 884, y: 420 },
  ];

  const built = assemble([...stations, ...seating]);

  return finish({
    id: 'lobby',
    title: '數位廣場 · 大廳',
    w: 960,
    // 高度比構圖需要的多出一段：視野會隨視窗伸縮，房間太矮的話
    // 大螢幕上垂直方向幾乎不會捲動，死區鏡頭會看起來像壞掉。
    h: 512,
    accent: 'cyan',
    // 明亮的公共空間。之前是 #7b84b8（乘上去只剩五成亮度），配上暗色
    // 科技磚整個房間看不清東西；大廳該是三個場景裡最亮的那一個。
    //
    // 幾乎是中性色，只帶一點冷。偏藍的環境光會把膚色乘成灰紫，角色的臉
    // 就糊成一團 —— 房間的冷調交給地板材質本身，不要靠光去染。
    ambient: '#d2d4e2',
    floor: 'plaza',
    emblem: { x: 480, y: 420, r: 66 },
    props: [...decor, ...built.props, ...doorProps(doors)],
    portals: doorPortals(doors),
    interactables: built.interactables,
    // NPC 擺在有事情發生的地方 —— 圍著圓桌盯盤、在吧台前排隊、
    // 在雕像旁邊聊天。散在空地上只會像放置的模型。
    npcs: [
      { x: 152, y: 452, facing: 'up', recolor: RECOLORS.npcRose },
      { x: 198, y: 440, facing: 'left', recolor: RECOLORS.npcGreen },
      { x: 792, y: 452, facing: 'up', recolor: RECOLORS.npcViolet },
      { x: 738, y: 440, facing: 'right', recolor: RECOLORS.npcAmber },
      { x: 128, y: 128, facing: 'up', recolor: RECOLORS.npcAmber },
      { x: 552, y: 344, facing: 'left', recolor: RECOLORS.npcGreen },
    ],
    // 出生點在雕像上方的中央空地：一轉身就看到地標，抬頭就是跑馬燈
    spawn: { x: 480, y: 322 },
  });
}

// ── 討論室（依主題參數化）──────────────────────────────────

/** 進入討論室需要的房間資料。刻意不從 ui/uiStore 匯入 TravelTarget ——
 *  world 不該依賴 ui；結構相容，呼叫端直接傳過來就行。 */
export type DiscussionSpec = {
  title: string;
  accent: Accent;
  tag: string;
  online: number;
  /** -100 ~ 100 */
  sentiment: number;
};

/**
 * 討論室。房間的構圖就是它的功能：**左邊是機器，右邊是人。**
 *
 *   左半（x 16..416）Agent 區　冷色科技磚、分析主機與 K 線牆、無人。
 *                            刻意留白 —— 「沒有人」本身就是資訊。
 *   中央（x 272..416）結論板　主題 + 情緒計。全場最大的光池，顏色由多空決定。
 *   右半（x 416..752）討論區　暖色地毯、便利貼牆、咖啡吧、圍成圈的座位、NPC。
 *
 * 原本這兩區只用一塊地毯區分，兩邊都是「會發光的科技物件」，看不出一邊是
 * 機器給的分析、一邊是人在聊天。溫度差要靠材質、密度與有沒有人一起拉開。
 *
 * 座標限制：終端機（128,210）與全息投影（540,210）不能動，驗證腳本靠
 * 世界絕對座標導航；而且 y 283..296 這條走廊必須貫通左右，測試會用純
 * WASD 從一個互動點直線走到另一個。
 */
export function makeDiscussionRoom(spec: DiscussionSpec): Room {
  const { title, accent, tag, online, sentiment } = spec;
  const holoX = 540;
  const holoY = 210;
  const stools: Prop[] = [];
  // 全息投影周圍圍一圈圓凳，做出「大家圍著看」的感覺
  for (let i = 0; i < 6; i++) {
    const a = (i / 6) * Math.PI * 2 + Math.PI / 6;
    stools.push({
      kind: 'stool',
      x: Math.round(holoX + 20 + Math.cos(a) * 62 - 7),
      y: Math.round(holoY + 26 + Math.sin(a) * 34 - 7),
    });
  }

  const doors = [
    door({ id: 'lobby', accent }, 352, 380, { label: '← 返回大廳', enterLabel: '返回大廳' }),
  ];

  const stations = [
    station({
      prop: { kind: 'terminal', x: 128, y: 210, accent },
      label: '讀取 Agent 分析報告',
      sign: '分析報告',
      panel: 'agentReport',
    }),
    station({
      prop: { kind: 'hologram', x: holoX, y: holoY },
      label: '加入玩家討論',
      sign: '討論串',
      panel: 'thread',
      // 這裡不用道具正前方：玩家會被圓凳擋在座位圈外，範圍必須涵蓋整圈，
      // 只框住中央投影的話站在旁邊卻按不了 E。
      rect: { x: holoX - 48, y: holoY - 10, w: 136, h: 100 },
    }),
  ];

  const built = assemble([...stations, seats(600, 360)]);

  const decor: Prop[] = [
    // ── 左半：Agent 區。冷、機械、無人 ──
    { kind: 'minerrack', x: 40, y: 44 },
    { kind: 'minerrack', x: 92, y: 44 },
    { kind: 'chartboard', x: 176, y: 44 },
    { kind: 'minerrack', x: 196, y: 206 },
    { kind: 'minerrack', x: 60, y: 400 },
    { kind: 'pillar', x: 56, y: 330 },

    // ── 中央：結論板 ──
    { kind: 'topicboard', x: 272, y: 208, sentiment },

    // ── 右半：討論區。暖、鬆散、有人 ──
    { kind: 'noteboard', x: 452, y: 44 },
    { kind: 'cafebar', x: 588, y: 52, w: 140 },
    ...stools,
    { kind: 'bench', x: 620, y: 336 },
    { kind: 'bench', x: 652, y: 336 },
    { kind: 'plant', x: 728, y: 300 },
    { kind: 'plant', x: 568, y: 470 },
    { kind: 'pillar', x: 696, y: 330 },
  ];

  const props: Prop[] = [...decor, ...built.props, ...doorProps(doors)];

  return finish({
    id: 'discussion',
    title,
    w: 768,
    h: 544,
    accent,
    // 討論室比大廳暗一階：這裡是坐下來看報告的地方，壓低亮度讓結論板
    // 與全息投影成為視線的落點。仍然接近中性 —— 偏色的環境光會吃掉膚色。
    ambient: '#c2bcd4',
    // 討論區腳下鋪一塊地毯，涵蓋座位圈與圓桌。座標對齊 16px 格線。
    //
    // 尺寸刻意小於視野高度（240）。第一版鋪了 352 高，結果它的上下邊界
    // 永遠在畫面外，玩家看到的只有一條貫穿螢幕的垂直直線 —— 那讀起來是
    // 「兩種地板的交界」。看得到邊角，它才是一塊地毯。
    carpet: { x: 448, y: 144, w: 272, h: 256 },
    topic: { tag, online },
    props,
    portals: doorPortals(doors),
    interactables: built.interactables,
    // 全部集中在右半場。左半場一個人也沒有 —— 那是機器的地盤，
    // 「沒有人」正是這一區要傳達的東西。
    npcs: [
      { x: 486, y: 306, facing: 'right', recolor: RECOLORS.npcAmber },
      { x: 628, y: 304, facing: 'left', recolor: RECOLORS.npcRose },
      { x: 556, y: 326, facing: 'up', recolor: RECOLORS.npcGreen },
      { x: 640, y: 116, facing: 'down', recolor: RECOLORS.npcViolet },
    ],
    // 322 而不是 330：視野最矮（240）時 cam.y = spawn - 120 = 202，
    // 結論板在 y 208 才不會頂到畫面上緣被切掉。
    spawn: { x: 384, y: 322 },
  });
}

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
 * 大廳的構圖：**三個直向的翼 × 五條橫向的帶**。
 *
 * 改版前這裡是「東西各堆一坨、中軸插一台交易台」，六個功能站點的座標
 * 是各自談出來的：公告在 y150、MAIA 在 y260、客服在 y350，站位分別落在
 * y198 / y284 / y348。沒有一條線可以同時走到它們，所以每加一個站點就得
 * 重新驗一次「從出生點的直線會不會被誰擋住」—— 那正是畫面看起來凌亂的
 * 來源：擺放順序是照著碰撞驗證的結果長出來的，不是照著空間的邏輯。
 *
 * 現在反過來，先定規則再放東西。
 *
 * ── 直向：三個翼 ──────────────────────────────────
 *   西翼　x 16..320　　社群。公會門 + 討論區門的門廊、咖啡吧、休息長椅
 *   中庭　x 320..524　　廣場。MAIA（紫）+ 金幣雕像。**這一段是緩衝區**
 *   東翼　x 528..944　　MAX 官方區（藍）。代幣柱當門柱，走道上一枚 MAX 地徽
 *
 *   MAIA 與最近的 MAX 站點（交易台 x600）之間隔著 160px 的空地與代幣柱，
 *   而且它是全場唯一的紫光。距離 + 顏色 + 一根門柱，三層都在說同一件事：
 *   MAIA 不是 MAX 的櫃檯之一。
 *
 * ── 橫向：五條帶 ──────────────────────────────────
 *   ① 上牆帶　y 18..110　行情跑馬燈 + 靠牆設施（咖啡吧 / 金庫 / 礦機）
 *   ② 後場帶　y 118..212　純景深：目的地看板、保管箱牆、盆栽長椅
 *   ③ 站點帶　y 216..296　**所有互動站點的本體都在這裡**
 *   ④ 主走道　y 300..382　**全場淨空，一個碰撞盒都沒有**
 *   ⑤ 休息帶　y 384..492　雕像、盯盤圓桌、客服辦公區、候位動線
 *
 * ── 唯一的硬約束 ──────────────────────────────────
 *
 * 這個世界沒有尋路：`walkTo()` 直線走、撞牆滑一下、0.7 秒沒進展就放棄
 * （player.ts 的 STALL_GIVE_UP）。所以**出生點到每個站位的直線必須淨空**，
 * 否則功能條導引會靜默失敗 —— 人停在半路、提示指向別的東西。
 *
 * 過去這件事靠「每次擺完再算一次」維持。現在靠兩條可以機械檢查的規則：
 *
 *   R1　站點帶的碰撞盒一律 **底邊 ≤ y288**；休息帶的一律 **頂邊 ≥ y384**。
 *   R2　每個站位（互動範圍的底邊中心）都落在 y 297..384 之間。
 *
 * ⚠ R1 的門檻是 288 而不是 296，差的那 8px 是**腳底盒的高度**。
 *   角色的碰撞盒是 `footBox = (x-6, y-9, 12, 9)`（player.ts）—— 它從腳底
 *   往**上**長 9px，所以站在 y300 的人，身體佔的是 y291..300。一件碰撞盒
 *   底邊在 296 的道具，會擋住站在 y300..304 的人，而那正是「沿著走道北緣
 *   往西走」的人所在的緯度。第一版把門廊柱列放在 y240（底邊 296），症狀是
 *   從出生點往西走到 x334 就再也走不動 —— 而柱子看起來明明在走道北邊。
 *   底邊壓到 288，走道從 y297 起就真的走得通。
 *
 * 出生點 (480,322) 本身就在走道上，所以 R1+R2 直接推出「從出生點到任何
 * 站位都是一條走道內的近水平直線」—— 不必再逐條驗算。五個站位分別是：
 *   MAIA (408,324) / 現貨交易 (648,326) / 公告 (766,320) / 活動 (884,322)
 * 兩道門的門墊（y 276..314）也壓在走道上，站位是 (144,310) 與 (288,310)。
 *
 * 唯一的例外是客服辦公區：它在南側，站位在 (836,466)。走過去是一條
 * 西北→東南的斜線，所以它的碰撞盒刻意向內縮 24px（見 props.ts 的
 * `propSolid` 註解），讓那條斜線從辦公區敞開的西側門進前庭。
 *
 * ⚠ 兩道門的座標（128,250）與（272,250）不能動：它們寫在 guild / discussion
 *   兩個 zone 的 `gateway.pinned` 裡，tests/zones.mjs 會比對。兩門中心 x
 *   距離 144 ≥ 128（名牌寬度上限）。
 */
export function makeLobby(): Room {
  /**
   * 門。座標只寫這一次 —— prop 與門墊觸發區都由 `door()` 從同一組 x/y 推。
   * 討論區後面有 12 間房，所以它的動作是開選房面板而不是直接傳送。
   */
  const doors = [
    door({ id: 'guild', accent: 'amber' }, 128, 250, {
      label: '交易者公會',
      enterLabel: '進入交易者公會',
    }),
    door({ id: 'discussion', accent: 'cyan' }, 272, 250, {
      label: '討論區',
      action: { type: 'panel', panel: 'roomPicker' },
    }),
  ];

  /**
   * 功能站點：道具 + 互動範圍 + 常駐站牌，三件事一次寫完。
   *
   * 四件道具全部是這一版新畫的（`props.ts` 的「大廳四個功能站點的專屬造型」）。
   * 之前公告與活動共用 `terminal`、MAIA 與客服共用 `counter` —— 四個功能
   * 兩種外觀，遠遠看只知道「那裡有台機器」。站牌上的中文得走近才讀得到，
   * 所以辨識的重擔其實全在剪影與光色上，那才是要花力氣的地方。
   */
  const stations = [
    // ── 中庭：MAIA（唯一不屬於 MAX 的站點）──
    //
    // 紫色、圓形、懸浮，跟東翼那一排方正的藍色櫃檯完全不同語彙。
    // 位置在中庭偏西，離最近的 MAX 站點 160px，中間還隔著一根代幣門柱。
    //
    // 互動範圍 frontOf(376,214,64,80) = (368,268,80,60)，右緣 448 刻意停在
    // 出生點的靠近判定（x 462 起）之外 —— 否則玩家一進場就被自己站著的
    // 位置彈出「與 MAIA 對話」的提示，而按 E 是要留給玩家自己決定的。
    station({
      prop: { kind: 'maiapod', x: 376, y: 214 },
      label: '與 MAIA 對話',
      sign: 'MAIA',
      accent: 'violet',
      panel: 'agentChat',
    }),

    // ── 東翼：MAX 官方區的四個站點 ──
    //
    // 由西往東是一條服務動線：先下單（交易台）、再看消息（公告）、
    // 再看活動，出了問題往南進客服辦公區。四個站點的正面全部朝主走道，
    // 所以站位在同一條緯度上（y326），從出生點過去都是水平直線。
    station({
      prop: { kind: 'tradedesk', x: 600, y: 240 },
      label: '進行現貨交易',
      sign: '現貨交易',
      accent: 'max',
      panel: 'trade',
    }),
    station({
      prop: { kind: 'newsboard', x: 728, y: 210 },
      label: '讀取官方消息',
      sign: '公告',
      accent: 'max',
      panel: 'maxNews',
    }),
    station({
      prop: { kind: 'eventstage', x: 836, y: 208 },
      label: '查看最新活動',
      sign: '活動',
      accent: 'max',
      panel: 'maxEvents',
    }),

    // ── 東翼南側：MAX 官方客服辦公區 ──
    //
    // 這是全場唯一「畫得出一個房間」的站點：隔屏、後場兩張辦公桌、
    // 跳號的叫號螢幕、戴著耳機麥克風的值班機器人、櫃檯上的服務鈴。
    // 客服跟 MAIA 的差別要看得出來 —— MAIA 是會查工具的分析 agent，
    // 客服是規則式 FAQ（入金出金、手續費、API、身分驗證、帳戶安全），
    // 所以一個是懸浮的核心，一個是有人上班的辦公室。
    //
    // 它是唯一放在南側的站點：東翼北側那一排已經滿了（交易台 96 +
    // 公告 76 + 活動 96 + 間距，剛好用完 x528..944），而客服要 136px
    // 才畫得出隔間。擺在走道南邊反而更像分行 —— 櫃檯沿牆、辦公室獨立
    // 成一島，中間是動線。
    //
    // 站位 (836,466) 在辦公室**南側**（俯視角裡「前方」永遠是 y 較大的
    // 那一側，所以櫃檯朝南是唯一畫得通的朝向）。
    station({
      prop: { kind: 'supportdesk', x: 768, y: 348, w: 136 },
      label: '詢問官方客服',
      sign: '客服',
      accent: 'max',
      panel: 'maxSupport',
    }),
  ];

  /**
   * 盯盤座位圈。兩組共用 `seats()` 的同一份偏移。
   * 西邊那組是門廊的等待區，東邊那組是客服辦公區的候位區。
   * 兩組的碰撞盒都在 y≥384（規則 R1）。
   */
  const seating = [seats(112, 400), seats(600, 424)];

  /*
   * decor 的排版規則（動任何一件之前先讀，函式頂端的註解是完整版）：
   *
   *   R1　站點帶的碰撞盒底邊 ≤ y296；休息帶的碰撞盒頂邊 ≥ y384。
   *   R2　主走道 y 300..382 全場一個碰撞盒都不准有。
   *
   * 換算成常用道具的可放範圍（碰撞盒的 y 偏移查 props.ts 的 propSolid）：
   *   pillar     底邊 y+56 → 站點帶 y ≤ 232
   *   plant      底邊 y+22 → 站點帶 y ≤ 266 ／ 休息帶 y ≥ 372
   *   bench      底邊 y+14 → 站點帶 y ≤ 274 ／ 休息帶 y ≥ 382
   *   chartboard 底邊 y+50 ／ vault、minerrack 底邊 y+54（都在上牆帶，不受限）
   *   maxtoken   底邊 y+68 → 站點帶 y ≤ 220
   *   coinstatue 頂邊 y+46 → 休息帶 y ≥ 338
   *   tradetable 頂邊 y+14 → 休息帶 y ≥ 370（seats() 最下面那張凳是 y+44）
   *   robot      頂邊 y+22 → 休息帶 y ≥ 362
   *
   * 兩個由驗證腳本盯著的點：
   *   (700,430) 與 (300,430) 必須從出生點直線走得到（tests/interaction.mjs）
   *   (700,168) 必須**走不到** —— 那是保管箱牆的碰撞盒裡面，員工區。
   */
  const decor: Prop[] = [
    // ── ① 上牆帶（y 18..110）───────────────────────────────
    // 跑馬燈橫貫全場：一進門看到滿牆滾動的報價，就不需要任何文字說明
    // 這裡是什麼地方。它是三個翼共用的唯一一件道具。
    { kind: 'ticker', x: 16, y: 18, w: 928 },
    // 西翼：咖啡吧台 + K 線牆。全是螢幕與金屬的空間會冷得沒人想待。
    { kind: 'cafebar', x: 48, y: 52, w: 128 },
    { kind: 'chartboard', x: 196, y: 44 },
    // 中庭：一整面影像牆。screenwall 沒有碰撞盒，純粹是廣場上方的密度。
    { kind: 'screenwall', x: 320, y: 44, w: 224 },
    // 東翼：冷錢包金庫 + K 線牆 + 三櫃礦機。這一段的材質最「機房」，
    // 跟西翼的木頭吧台正好是兩端。
    { kind: 'vault', x: 592, y: 40 },
    { kind: 'chartboard', x: 664, y: 44 },
    { kind: 'minerrack', x: 792, y: 40 },
    { kind: 'minerrack', x: 844, y: 40 },
    { kind: 'minerrack', x: 896, y: 40 },

    // ── ② 後場帶（y 118..212）純景深，沒有任何互動 ──────────
    // 西翼：目的地看板懸在兩道門上方
    { kind: 'screenwall', x: 176, y: 122, w: 168 },
    { kind: 'plant', x: 56, y: 160 },
    { kind: 'bench', x: 36, y: 190 },
    { kind: 'plant', x: 296, y: 160 },
    // 東翼：法幣信託的保管箱牆。它是 MAX 最獨有的一件事（全球首家把
    // 用戶法幣交由銀行信託保管）的具象化身，擺在後場當整個東翼的背板。
    //
    // ⚠ 它的碰撞盒 (634,158,144,18) 就是「走不到的目標」那條測試靠的東西
    //   （tests/interaction.mjs 點 (700,168)）。要移動它請一起改那支測試。
    { kind: 'trustdesk', x: 636, y: 126, w: 140 },
    { kind: 'plant', x: 800, y: 164 },
    { kind: 'bench', x: 848, y: 156 },
    { kind: 'pillar', x: 912, y: 140 },

    // ── ③ 站點帶（y 216..296）─────────────────────────────
    // 西翼門廊的柱列：每道門左右各一根，四根等距排出門廊的節奏。
    // y232 而不是 y240 —— 差的那 8px 就是 R1 註解裡講的腳底盒高度。
    { kind: 'pillar', x: 96, y: 232 },
    { kind: 'pillar', x: 168, y: 232 },
    { kind: 'pillar', x: 240, y: 232 },
    { kind: 'pillar', x: 312, y: 232 },
    // 中庭：兩盆綠化夾著 MAIA，把它框成一個獨立的凹室而不是走道上的一台機器
    { kind: 'plant', x: 348, y: 250 },
    { kind: 'plant', x: 444, y: 250 },
    // 東翼的門柱：MAX Token 鎖倉展示柱。它是全場第二亮的藍光源，
    // 站在中庭往東看，這根柱子就是「MAX 的地盤從這裡開始」。
    { kind: 'maxtoken', x: 528, y: 220 },

    // ── ④ 主走道（y 300..382）──────────────────────────────
    // 這裡刻意什麼都不放。改版前有一盆植物在 (568,306)，它的碰撞盒
    // (570,318,12,10) 剛好卡在走道正中央 —— 症狀是「往東走到 x564 就
    // 再也走不動」，而 tests/movement.mjs 那三條紅燈（鏡頭推不動、
    // 鏡頭夾不到邊界、標籤層更新次數不足）全部是它一個人造成的。
    // 走道要空，這是這一版最重要的一條規則。

    // ── ⑤ 休息帶（y 384..492）─────────────────────────────
    // 西翼：門廊前的等待區
    { kind: 'bench', x: 36, y: 396 },
    { kind: 'plant', x: 40, y: 452 },
    { kind: 'plant', x: 232, y: 400 },
    { kind: 'bench', x: 216, y: 456 },
    // 中庭：雕像立在地面徽章上當地標，南側兩張長椅面向它 ——
    // 有人坐著看的東西才像地標。
    { kind: 'coinstatue', x: 456, y: 350 },
    { kind: 'bench', x: 400, y: 436 },
    { kind: 'bench', x: 528, y: 436 },
    { kind: 'plant', x: 368, y: 458 },
    { kind: 'plant', x: 552, y: 458 },
    // 東翼：迎賓機器人站在代幣柱南邊，等於站在 MAX 服務區的門口。
    // 它的碰撞盒 (570,414,20,12) 刻意在客服斜線（經過 y414 時 x 在 708 之後）
    // 的西邊 —— 這是唯一一件需要對著那條斜線算過位置的裝飾。
    { kind: 'robot', x: 568, y: 392 },
    // 候位動線：兩根伸縮帶欄杆把辦公區前的空地變成「候位區」。
    // 用兩件 32px 的小道具說明一整塊地面的用途，比多擺兩張椅子清楚。
    { kind: 'queuerail', x: 700, y: 452 },
    { kind: 'queuerail', x: 748, y: 452 },
    { kind: 'plant', x: 916, y: 400 },
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
    /**
     * 兩枚地面徽章，一枚一個翼。
     *
     * 中庭那枚是錢幣邊齒，金幣雕像立在正中央 —— 全場的地標。
     * 東翼那枚是 MAX 字樣，位置刻意壓在主走道上：往東走進 MAX 官方區的
     * 第一件事就是踩過他們的徽章。地面標記畫在所有立體物件之下，
     * 所以它是唯一「不佔走位、不擋視線」的分區手段，比多擺幾根柱子有效。
     */
    emblems: [
      { x: 480, y: 420, r: 66 },
      { x: 736, y: 340, r: 54, kind: 'max' },
    ],
    props: [...decor, ...built.props, ...doorProps(doors)],
    portals: doorPortals(doors),
    interactables: built.interactables,
    // NPC 擺在有事情發生的地方 —— 門廊附近等傳送、圍著圓桌盯盤、
    // 在客服前排隊。散在空地上只會像放置的模型。
    npcs: [
      // 西翼門廊：等著傳送的人
      { x: 152, y: 336, facing: 'up', recolor: RECOLORS.npcAmber },
      { x: 296, y: 336, facing: 'up', recolor: RECOLORS.npcGreen },
      // 咖啡吧台前
      { x: 100, y: 120, facing: 'up', recolor: RECOLORS.npcViolet },
      // 中庭：一個人站在 MAIA 前面（有人在用它，它才不像展示品）
      { x: 352, y: 330, facing: 'right', recolor: RECOLORS.npcViolet },
      // 雕像旁的長椅
      { x: 416, y: 458, facing: 'up', recolor: RECOLORS.npcRose },
      // 客服候位區：一個坐在圓桌邊、一個站在動線欄杆旁
      { x: 640, y: 402, facing: 'up', recolor: RECOLORS.npcAmber },
      { x: 704, y: 444, facing: 'right', recolor: RECOLORS.npcGreen },
    ],
    // 出生點就在主走道上：一轉身看到雕像，往東是 MAX 官方區、
    // 往西是兩道門、左前方是 MAIA。四個方向各有東西，而且都走得到。
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

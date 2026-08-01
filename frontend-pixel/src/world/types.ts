import type { Recolor } from '../art/palette';
/**
 * ⚠ 這是**唯一**一條 `world/ → ui/` 的邊，而且是 `import type`：
 *   `verbatimModuleSyntax` 保證它在 build 時被完全抹掉，執行期沒有這條相依，
 *   所以 §3.2 的「world 不可 import ui」（那條講的是執行期耦合）沒有被破壞。
 *   換來的是房間定義裡的 `panel: 'ranking'` 打錯字就是紅色編譯錯誤。
 */
import type { PanelId } from '../ui/panels';

export type Rect = { x: number; y: number; w: number; h: number };
/** `max` 是 MAX 交易所的品牌深藍，只給 MAX 相關的場景與面板用。 */
export type Accent = 'cyan' | 'amber' | 'violet' | 'green' | 'max';

/**
 * 場景 id。
 *
 * 刻意放寬成 `string`：真正的來源是 `world/zones/index.ts` 的 barrel
 * （`ZoneId = keyof typeof ZONES`），但 barrel import 房間、房間 import
 * 這個檔，型別依賴會繞回來變成循環推導。所以這裡只留結構型別，
 * **所有實際使用點一律標註 `ZoneId`**（uiStore 的 travelTo、features 的
 * place.zone），房間內部的 travel 目標則由 `validateWiring()` 與
 * `tests/zones.mjs` 守（規格 §4.5）。
 */
export type SceneId = string;

/** @deprecated 用 `PanelId`（= `keyof typeof PANELS`）。留著只為了相容。 */
export type PanelKind = string;

export type Prop =
  | { kind: 'pillar'; x: number; y: number }
  | { kind: 'bench'; x: number; y: number }
  | { kind: 'portal'; x: number; y: number; accent: Accent }
  | { kind: 'board'; x: number; y: number }
  | { kind: 'terminal'; x: number; y: number; accent: Accent }
  | { kind: 'hologram'; x: number; y: number }
  | { kind: 'stool'; x: number; y: number }
  | { kind: 'counter'; x: number; y: number; w: number }
  | { kind: 'screenwall'; x: number; y: number; w: number }
  | { kind: 'robot'; x: number; y: number }
  | { kind: 'plant'; x: number; y: number }
  // ── 大廳的虛擬貨幣主題道具 ──
  /** 牆上的行情跑馬燈 */
  | { kind: 'ticker'; x: number; y: number; w: number }
  /** K 線圖看板 */
  | { kind: 'chartboard'; x: number; y: number }
  /** 冷錢包金庫 */
  | { kind: 'vault'; x: number; y: number }
  /** 礦機機櫃 */
  | { kind: 'minerrack'; x: number; y: number }
  /** 咖啡吧台 */
  | { kind: 'cafebar'; x: number; y: number; w: number }
  /** 中央的金幣雕像 */
  | { kind: 'coinstatue'; x: number; y: number }
  /** 盯盤用的圓桌 */
  | { kind: 'tradetable'; x: number; y: number }
  // ── MAX 情報室的品牌道具 ──
  /** 法幣信託櫃檯：保管箱牆 + NT$ 招牌 */
  | { kind: 'trustdesk'; x: number; y: number; w: number }
  /** MAX Token 鎖倉展示柱 */
  | { kind: 'maxtoken'; x: number; y: number }
  // ── 大廳中軸 ──
  /** 現貨交易台：行情看板 + 下單櫃檯 */
  | { kind: 'tradedesk'; x: number; y: number }
  // ── 大廳的功能站點專屬道具 ──
  //
  // 這四件是「一個功能一個造型」。原本公告與活動共用 `terminal`（同一台
  // 機殼、同一片資料流），MAIA 與客服共用 `counter`（同一條檯面）——
  // 四個功能兩種外觀，遠遠看過去只知道「那裡有台機器」，不知道是哪一個。
  // 站牌上的中文得走近才讀得到，所以辨識的重擔其實全落在剪影上。
  /** MAIA 智慧核心：懸浮全息核心 + 弧形控制台 + MAIA 銘牌。紫色 = AI，跟 MAX 的藍分開 */
  | { kind: 'maiapod'; x: number; y: number }
  /** 公告塔：頂端滾動標題燈條 + 玻璃公告櫃裡的紙本公告 + 官方鋼印 */
  | { kind: 'newsboard'; x: number; y: number }
  /** 活動舞台：三角旗串 + 倒數看板 + 抬高的舞台 + 獎品箱與轉盤 + 紙花 */
  | { kind: 'eventstage'; x: number; y: number }
  /** MAX 官方客服辦公區：玻璃隔屏 + 後場兩張辦公桌 + 叫號螢幕 + 服務櫃檯 */
  | { kind: 'supportdesk'; x: number; y: number; w: number }
  /** 排隊動線欄杆：立柱 + 伸縮帶。客服辦公區的候位動線 */
  | { kind: 'queuerail'; x: number; y: number }
  // ── 討論室 ──
  /** 主題看板 + 情緒計。中文由 worldLabels 疊在看板的深色面板上 */
  | { kind: 'topicboard'; x: number; y: number; sentiment: number }
  /** 便利貼牆 */
  | { kind: 'noteboard'; x: number; y: number };

/** 道具尺寸。y 排序與碰撞盒都從這裡推導，避免兩邊各寫一份數字。 */
export const PROP_SIZE: Record<Prop['kind'], { w: number; h: number }> = {
  pillar: { w: 16, h: 56 },
  bench: { w: 32, h: 14 },
  portal: { w: 32, h: 52 },
  board: { w: 56, h: 48 },
  terminal: { w: 56, h: 44 },
  hologram: { w: 40, h: 40 },
  stool: { w: 14, h: 14 },
  counter: { w: 0, h: 20 }, // 寬度由 prop 自帶
  screenwall: { w: 0, h: 26 },
  robot: { w: 24, h: 34 },
  plant: { w: 16, h: 22 },
  ticker: { w: 0, h: 12 },
  chartboard: { w: 88, h: 52 },
  vault: { w: 56, h: 56 },
  minerrack: { w: 40, h: 56 },
  cafebar: { w: 0, h: 36 },
  coinstatue: { w: 48, h: 60 },
  tradetable: { w: 64, h: 32 },
  trustdesk: { w: 0, h: 52 },
  maxtoken: { w: 48, h: 68 },
  topicboard: { w: 144, h: 64 },
  noteboard: { w: 88, h: 52 },
  tradedesk: { w: 96, h: 56 },
  maiapod: { w: 64, h: 80 },
  newsboard: { w: 76, h: 80 },
  eventstage: { w: 96, h: 84 },
  supportdesk: { w: 0, h: 88 }, // 寬度由 prop 自帶
  queuerail: { w: 32, h: 30 },
};

/** 踩上去就觸發：可能是換場景，也可能是開一個面板。 */
export type PortalAction =
  /** `params` 會原封不動送進目的地 zone 的 `build(ctx)`。取代了死欄位 roomId。 */
  | { type: 'travel'; scene: SceneId; params?: Record<string, string> }
  | { type: 'panel'; panel: PanelId };

export type Portal = {
  rect: Rect;
  /** 掛在拱門上方的名牌 */
  label: string;
  /** [E] 提示的文字。省略時用「進入 {label}」 */
  enterLabel?: string;
  accent: Accent;
  action: PortalAction;
};

/** 走近顯示提示、按 E 觸發。 */
export type Interactable = {
  /** 靠近判定區（通常比道具本體大一圈） */
  rect: Rect;
  /** `[E]` 提示上的文字。是動詞 ——「讀取官方消息」 */
  label: string;
  /**
   * 頭上那塊常駐站牌的文字。是名詞 ——「公告」。
   *
   * 跟 `label` 分成兩個欄位是因為兩者的任務不同：站牌要在還沒走過去時就
   * 回答「那是什麼」，越短越好；提示要在人站到面前時回答「按下去會發生
   * 什麼」，動詞才講得清楚。省略時退回用 `label`，不會沒有牌子。
   */
  sign?: string;
  /**
   * 站牌掛的世界座標（牌子的底邊）。
   *
   * 必須是**道具本身的上緣**，不是 `rect` 的上緣。`rect` 由 `frontOf()` 從
   * 道具底部往上算，通常落在道具身上 —— 拿它當錨點，牌子會蓋在道具的臉上
   * （排行看板那塊螢幕正中央就會壓著一個「排行榜」）。
   *
   * 省略時退回用 `rect` 上緣，所以手寫的互動點不會沒有牌子；
   * 但用 `station()` 建的一律有正確的錨點。
   */
  signAt?: { x: number; y: number };
  /** 站牌顏色。省略時用 `room.accent`。 */
  accent?: Accent;
  /** 二選一：開面板，或跑一段自訂邏輯（觸發 agent、播動畫、下單確認）。
   *  兩個都沒有 = 按 E 不會有任何事，`validateWiring()` 會抓出來。 */
  panel?: PanelId;
  run?: () => void;
};

/** 地面徽章。`coin` 是錢幣邊齒，`max` 是 MAX 字樣。 */
export type Emblem = { x: number; y: number; r: number; kind?: 'coin' | 'max' };

export type NpcSpec = {
  x: number;
  y: number;
  facing: 'down' | 'up' | 'left' | 'right';
  recolor: Recolor;
};

export type Room = {
  id: SceneId;
  /** 顯示在畫面頂端的場景名稱 */
  title: string;
  w: number;
  h: number;
  /** 主題色：影響拱門、終端螢幕、光源顏色 */
  accent: Accent;
  /**
   * 環境光。整個場景會先乘上這個顏色壓暗，再由各個光源照亮回來。
   * 越暗的環境光對比越強、氣氛越重，但太暗會看不清路。
   */
  ambient: string;
  /**
   * 地板材質。`plaza` 是明亮的石板廣場（大廳），`tech` 是深色科技磚。
   * 三個房間若共用同一塊地板，光的顏色再怎麼換都還是同一個空間。
   */
  floor?: 'tech' | 'plaza' | 'maxstone' | 'guild';
  /**
   * 地面徽章：畫在地板上、所有立體物件之下的圓形紋樣。
   *
   * 是**陣列**而不是單一件：一個大空間可以有好幾個「這一區是誰的」的地面
   * 標記。大廳用兩枚 —— 中庭的錢幣徽章是全場的地標，東翼走道上的 MAX 徽章
   * 是「你踏進交易所的地盤了」。地面標記比多加幾件道具便宜太多，而且它
   * 畫在所有立體物件之下，不會跟走位打架。
   */
  emblems?: Emblem[];
  /**
   * 暖色地毯的範圍（討論室用）。
   *
   * 原本是一個 x 門檻、右半場整片填滿，結果畫面正中央出現一條貫穿上下的
   * 直線接縫 —— 亮度提高之後那條線變成整個房間最搶眼的東西。改成一塊
   * 有邊界的地毯，它就從「兩種地板的交界」變成「地上放了一塊地毯」。
   * 座標必須對齊 16px 格線。
   */
  carpet?: Rect;
  /**
   * 討論室的主題資訊。中文文字由 worldLabels 疊在 topicboard 上 ——
   * 8px 的中文畫進 backbuffer 會糊掉，這是全專案一致的做法。
   */
  topic?: { tag: string; online: number };
  props: Prop[];
  solids: Rect[];
  portals: Portal[];
  interactables: Interactable[];
  npcs: NpcSpec[];
  spawn: { x: number; y: number };
};

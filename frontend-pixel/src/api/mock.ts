import type {
  Balance,
  EventItem,
  Market,
  NewsItem,
  Post,
  Quote,
  Report,
  RoomInfo,
  Strategy,
} from './types';

/**
 * 全部的假資料。換成真後端時整個檔案會被刪掉，
 * api/index.ts 的函式簽名維持不變，面板一行都不用改。
 */

export const ROOMS: RoomInfo[] = [
  { id: 'btc-halving', topic: 'BTC 減半後的籌碼結構', tag: '比特幣', accent: 'amber', heat: 9840, online: 412, change: 12.4, sentiment: 42 },
  { id: 'eth-l2', topic: 'ETH L2 費用戰爭', tag: '以太坊', accent: 'violet', heat: 7620, online: 305, change: 6.1, sentiment: 18 },
  { id: 'ai-agent', topic: 'AI Agent 會吃掉哪些工作', tag: 'AI', accent: 'violet', heat: 7150, online: 288, change: 24.8, sentiment: 61 },
  { id: 'twd-flow', topic: '台幣入金與匯率溢價觀察', tag: '台股/匯率', accent: 'green', heat: 6480, online: 241, change: -3.2, sentiment: -12 },
  { id: 'sol-eco', topic: 'SOL 生態的真實用戶數', tag: 'Solana', accent: 'cyan', heat: 5930, online: 219, change: 8.7, sentiment: 27 },
  { id: 'stable', topic: '穩定幣監管與 USDT 風險', tag: '穩定幣', accent: 'green', heat: 5210, online: 187, change: 1.9, sentiment: -34 },
  { id: 'defi-yield', topic: 'DeFi 收益還剩多少肉', tag: 'DeFi', accent: 'cyan', heat: 4870, online: 164, change: -6.5, sentiment: -21 },
  { id: 'tw-regulation', topic: '台灣 VASP 專法進度', tag: '法規', accent: 'amber', heat: 4360, online: 152, change: 15.3, sentiment: 8 },
  { id: 'nvda-chain', topic: '算力股與加密礦業的連動', tag: '美股', accent: 'green', heat: 3980, online: 131, change: 4.4, sentiment: 35 },
  { id: 'memecoin', topic: '迷因幣還有沒有下一輪', tag: '迷因幣', accent: 'violet', heat: 3540, online: 118, change: -11.2, sentiment: -58 },
  { id: 'rwa', topic: 'RWA 代幣化的實際落地', tag: 'RWA', accent: 'cyan', heat: 2910, online: 94, change: 7.6, sentiment: 14 },
  { id: 'quant', topic: '散戶量化策略的幸存者偏差', tag: '量化', accent: 'amber', heat: 2450, online: 76, change: 2.1, sentiment: -4 },
];

const REPORT_TEMPLATES: Omit<Report, 'roomId' | 'updatedAt'>[] = [
  {
    sentiment: 42,
    summary:
      '過去 24 小時討論量成長 12.4%，情緒偏多但已出現分歧。多方論點集中在長期籌碼沉澱，空方則反覆提及槓桿比率偏高。整體屬於「有基本面支撐但短線擁擠」的結構。',
    points: [
      { title: '籌碼面', body: '長期持有地址佔比連續 5 週上升，交易所餘額創 18 個月新低。這通常領先價格反應 2–6 週，但不構成短線訊號。' },
      { title: '情緒面', body: '社群提及量高於 90 日均值 1.8 個標準差。歷史上超過 2 個標準差後 10 天內回檔機率明顯升高，目前尚未觸及。' },
      { title: '資金面', body: '現貨溢價轉正、永續資金費率連續 3 日為正但未過熱。台幣場外溢價約 0.4%，屬正常區間。' },
      { title: '分歧點', body: '討論串中最大的爭議是「本輪是否已提前反映減半」。支持與反對的留言數接近 1:1，沒有明顯共識。' },
    ],
    risks: [
      '槓桿多單佔比偏高，突發利空時容易觸發連環清算',
      '樣本以中文社群為主，可能低估歐美市場的空方聲量',
      '情緒指標為滯後指標，不應單獨作為進出場依據',
    ],
    sources: [
      { name: '房間內留言', note: '近 24 小時 1,284 則，去重後 1,102 則', weight: 45 },
      { name: '鏈上指標', note: '交易所餘額、長期持有者供給', weight: 30 },
      { name: '衍生品數據', note: '資金費率、未平倉合約', weight: 15 },
      { name: '新聞摘要', note: '中英文財經媒體標題', weight: 10 },
    ],
  },
  {
    sentiment: -18,
    summary:
      '討論熱度上升但情緒轉為謹慎。負面留言集中在「敘事先行、落地緩慢」，正面留言則多為長線觀點。這是典型的期待值修正階段，而非趨勢反轉。',
    points: [
      { title: '敘事強度', body: '關鍵字提及量仍在高檔，但帶有「還要多久」「什麼時候能用」的疑問句式比例從 12% 升到 27%。' },
      { title: '實際數據', body: '活躍地址與交易筆數的成長率低於敘事熱度成長率，兩者背離已持續約 3 週。' },
      { title: '對照組', body: '同類專案的討論在同期呈現一致的降溫，顯示這是板塊性的而非個案。' },
    ],
    risks: [
      '敘事類題材的情緒指標波動大，短期讀數參考價值有限',
      '樣本偏向已經持倉的參與者，存在確認偏誤',
    ],
    sources: [
      { name: '房間內留言', note: '近 24 小時 906 則', weight: 50 },
      { name: '鏈上活躍度', note: '日活地址、合約呼叫次數', weight: 30 },
      { name: '同類專案對照', note: '4 個可比標的', weight: 20 },
    ],
  },
];

export function reportFor(roomId: string): Report {
  const idx = Math.abs(hashStr(roomId)) % REPORT_TEMPLATES.length;
  const tpl = REPORT_TEMPLATES[idx]!;
  // sentiment 一律以房間本身的值為準，不用模板的。
  // 場景的燈光與看板讀的是 RoomInfo.sentiment；若報告面板顯示另一個數字，
  // 玩家會看到「房間一片綠、報告寫著 -18」這種自相矛盾的畫面。
  const room = ROOMS.find((r) => r.id === roomId);
  return { ...tpl, roomId, updatedAt: '3 分鐘前', ...(room && { sentiment: room.sentiment }) };
}

const AUTHORS: [string, string][] = [
  ['鏈上打工仔', '#35b8cf'],
  ['台南阿明', '#ffc23d'],
  ['只做現貨', '#4ee88a'],
  ['看圖說故事', '#b06cff'],
  ['被套的老王', '#ff4f78'],
  ['冷錢包保管員', '#7d8ba5'],
  ['夜盤守夜人', '#00e5ff'],
];

const BODIES = [
  '這份報告的籌碼面我認同，但情緒指標我覺得已經過熱了，上一次這個讀數之後跌了兩成。',
  '交易所餘額創新低這件事被講到爛了，問題是有多少是搬去冷錢包、有多少是進了 ETF 託管。',
  '我還是那句話，資金費率沒過熱之前都還算健康。真正要怕的是費率翻倍那天。',
  '樓上說的對照組能不能貼一下來源？我自己抓的數字跟報告差蠻多的。',
  '台幣溢價 0.4% 其實不太正常，之前平常都在 0.1 以下。可能有大戶在進場。',
  '單純提醒一下，這種討論室的樣本偏差很嚴重，會來討論的本來就都是有部位的人。',
  '長期我看好，但短線我減了三成。不是看空，是槓桿太多我睡不著。',
  '報告裡「分歧點」那段寫得不錯，至少沒有硬要給一個方向。',
  '有人注意到最近入金的速度變慢了嗎？我這邊銀行轉帳延遲明顯變久。',
  '我的做法很簡單：定期定額，不看情緒指標。過去三年這樣做贏過我所有的擇時嘗試。',
];

export function threadFor(roomId: string): Post[] {
  const seed = Math.abs(hashStr(roomId));
  return BODIES.map((text, i) => {
    const a = AUTHORS[(seed + i * 3) % AUTHORS.length]!;
    return {
      id: `${roomId}-${i}`,
      author: a[0],
      color: a[1],
      time: `${BODIES.length - i} 分鐘前`,
      text,
      likes: (seed + i * 7) % 48,
    };
  });
}

// ── 行情 ────────────────────────────────────────────────────

type Seed = { base: string; name: string; quote: Quote; price: number; volume: number };

const MARKET_SEEDS: Seed[] = [
  { base: 'USDT', name: '泰達幣', quote: 'TWD', price: 32.48, volume: 168_000_000 },
  { base: 'BTC', name: '比特幣', quote: 'TWD', price: 3_412_000, volume: 96_400_000 },
  { base: 'ETH', name: '以太幣', quote: 'TWD', price: 118_600, volume: 41_200_000 },
  { base: 'USDC', name: 'USD Coin', quote: 'TWD', price: 32.41, volume: 22_800_000 },
  { base: 'SOL', name: 'Solana', quote: 'TWD', price: 6_820, volume: 18_900_000 },
  { base: 'XRP', name: 'Ripple', quote: 'TWD', price: 78.4, volume: 14_600_000 },
  { base: 'DOGE', name: '狗狗幣', quote: 'TWD', price: 6.18, volume: 9_300_000 },
  { base: 'ADA', name: 'Cardano', quote: 'TWD', price: 25.3, volume: 6_100_000 },
  { base: 'LINK', name: 'Chainlink', quote: 'TWD', price: 698, volume: 5_400_000 },
  { base: 'AVAX', name: 'Avalanche', quote: 'TWD', price: 1_146, volume: 4_200_000 },
  { base: 'DOT', name: 'Polkadot', quote: 'TWD', price: 191, volume: 3_100_000 },
  { base: 'LTC', name: '萊特幣', quote: 'TWD', price: 3_284, volume: 2_800_000 },
  { base: 'BCH', name: '比特幣現金', quote: 'TWD', price: 16_940, volume: 2_400_000 },
  { base: 'TRX', name: 'TRON', quote: 'TWD', price: 9.46, volume: 1_900_000 },
  { base: 'MAX', name: 'MAX Token', quote: 'TWD', price: 1.34, volume: 1_200_000 },
  { base: 'SHIB', name: '柴犬幣', quote: 'TWD', price: 0.000748, volume: 880_000 },

  { base: 'BTC', name: '比特幣', quote: 'USDT', price: 105_040, volume: 12_400_000 },
  { base: 'ETH', name: '以太幣', quote: 'USDT', price: 3_651, volume: 6_800_000 },
  { base: 'SOL', name: 'Solana', quote: 'USDT', price: 209.9, volume: 3_200_000 },
  { base: 'XRP', name: 'Ripple', quote: 'USDT', price: 2.414, volume: 2_100_000 },
  { base: 'DOGE', name: '狗狗幣', quote: 'USDT', price: 0.1903, volume: 1_400_000 },
  { base: 'ADA', name: 'Cardano', quote: 'USDT', price: 0.779, volume: 940_000 },
  { base: 'LINK', name: 'Chainlink', quote: 'USDT', price: 21.49, volume: 810_000 },
  { base: 'AVAX', name: 'Avalanche', quote: 'USDT', price: 35.28, volume: 620_000 },
  { base: 'DOT', name: 'Polkadot', quote: 'USDT', price: 5.88, volume: 450_000 },
  { base: 'LTC', name: '萊特幣', quote: 'USDT', price: 101.1, volume: 390_000 },
  { base: 'BCH', name: '比特幣現金', quote: 'USDT', price: 521.5, volume: 280_000 },
  { base: 'TRX', name: 'TRON', quote: 'USDT', price: 0.2912, volume: 210_000 },

  { base: 'ETH', name: '以太幣', quote: 'BTC', price: 0.03476, volume: 142 },
];

/** 現價會在原始價附近隨機漫步，讓 3 秒一次的輪詢看起來像真的在跳。 */
const live = new Map<string, { price: number; change: number }>();

function marketId(s: Seed): string {
  return `${s.base}${s.quote}`.toLowerCase();
}

export function driftMarkets(): Market[] {
  return MARKET_SEEDS.map((s) => {
    const id = marketId(s);
    // hashStr 可能是負的，取絕對值才會落在 -4.5% ~ +4.5% 的預期區間
    const cur = live.get(id) ?? { price: s.price, change: (Math.abs(hashStr(id)) % 900) / 100 - 4.5 };
    // 每次抓取漂移約 ±0.15%，並輕微往原始價回歸，避免長時間跑掉
    const drift = (Math.random() - 0.5) * 0.003;
    const pull = (s.price - cur.price) / s.price * 0.05;
    const price = cur.price * (1 + drift + pull);
    const change = cur.change + (price / cur.price - 1) * 100;
    live.set(id, { price, change });
    return { id, base: s.base, quote: s.quote, name: s.name, price, change, volume: s.volume };
  });
}

export function priceOf(asset: string): number {
  if (asset === 'TWD') return 1;
  const id = `${asset}twd`.toLowerCase();
  const l = live.get(id);
  if (l) return l.price;
  return MARKET_SEEDS.find((s) => s.base === asset && s.quote === 'TWD')?.price ?? 0;
}

export const BALANCE_SEEDS: Omit<Balance, 'price'>[] = [
  { asset: 'TWD', available: 184_260, locked: 12_000, avgCost: 1 },
  { asset: 'USDT', available: 3_240.51, locked: 0, avgCost: 31.86 },
  { asset: 'BTC', available: 0.08412, locked: 0.005, avgCost: 2_980_000 },
  { asset: 'ETH', available: 1.284, locked: 0, avgCost: 124_500 },
  { asset: 'SOL', available: 18.6, locked: 0, avgCost: 5_940 },
  { asset: 'MAX', available: 12_400, locked: 0, avgCost: 1.62 },
];

// ── MAX 官方消息 / 活動 ─────────────────────────────────────

export const NEWS: NewsItem[] = [
  {
    id: 'n1',
    title: 'MAX 新增交易對上架公告',
    category: '上架',
    date: '2026-07-28',
    body: [
      'MAX 將於台北時間 2026 年 7 月 30 日 14:00 開放新交易對的委託掛單，並於 15:00 正式開放撮合。',
      '開放初期採用較寬的價格限制區間，請留意掛單價格。新上架標的波動通常高於平均，建議先小額測試。',
      '入金與提幣功能將於撮合開始後 24 小時內陸續開放，實際時間以站內公告為準。',
    ],
  },
  {
    id: 'n2',
    title: '系統維護通知：撮合引擎升級',
    category: '維護',
    date: '2026-07-26',
    body: [
      '為提升撮合效能，MAX 將於 2026 年 8 月 2 日 03:00–05:00 進行系統維護。',
      '維護期間現貨交易、入出金與 API 將暫停服務。既有掛單會保留，維護結束後恢復撮合。',
      '若您使用 API 交易，請預先處理好維護時段的錯誤重試邏輯，避免重複下單。',
    ],
  },
  {
    id: 'n3',
    title: '關於近期釣魚網站的安全提醒',
    category: '安全',
    date: '2026-07-24',
    body: [
      '近期出現多個仿冒 MAX 的釣魚網站，網址與官方僅有一兩個字元差異。',
      '請務必確認網址為 max.maicoin.com，並開啟兩步驟驗證。MAX 官方不會以任何形式向您索取密碼、驗證碼或 API Secret。',
      '再次提醒：任何要求您提供 API Secret Key 的對象都是詐騙。Secret Key 一旦外流等同於交出帳戶控制權。',
    ],
  },
  {
    id: 'n4',
    title: '新台幣信託帳戶月度報告',
    category: '公告',
    date: '2026-07-20',
    body: [
      'MAX 為用戶新台幣存款設立專用信託帳戶，由合作銀行依正式信託契約監管。',
      '本月度信託餘額與用戶負債對帳結果已公布於官網「資產證明」專區。',
    ],
  },
  {
    id: 'n5',
    title: 'API v3 文件更新與舊版停用時程',
    category: '公告',
    date: '2026-07-15',
    body: [
      'API v3 新增批次下單與 WebSocket 增量訂單簿推送。',
      '舊版 v2 將於 2026 年 12 月 31 日停止服務，請開發者提早移轉。',
    ],
  },
];

export const EVENTS: EventItem[] = [
  {
    id: 'e1',
    title: '新用戶入金回饋 最高 NT$1,000',
    period: '2026/07/01 – 2026/08/31',
    reward: '最高 NT$1,000 交易金',
    tag: '進行中',
    body: [
      '完成身分驗證並於活動期間首次台幣入金，依入金金額級距發放交易金。',
      '交易金可折抵現貨交易手續費，有效期 30 天，不可提領。',
      '每個帳戶限領一次，需完成第二級以上身分驗證。',
    ],
  },
  {
    id: 'e2',
    title: '現貨交易量排行賽',
    period: '2026/07/15 – 2026/08/15',
    reward: '總獎池 500,000 MAX',
    tag: '進行中',
    body: [
      '活動期間現貨交易量前 100 名，依名次瓜分獎池。',
      '交易量以計價幣換算新台幣計算，自成交對敲不計入。',
      '排行榜每小時更新一次，最終以官方結算為準。',
    ],
  },
  {
    id: 'e3',
    title: 'MAX Token 持有回饋計畫',
    period: '長期',
    reward: '手續費最低 8 折',
    tag: '進行中',
    body: [
      '依 30 日平均持有 MAX Token 數量分級，享現貨交易手續費折扣。',
      '等級每日 00:00 重新計算，升級即時生效、降級隔日生效。',
    ],
  },
  {
    id: 'e4',
    title: '定期定額功能上線體驗活動',
    period: '2026/08/05 – 2026/09/05',
    reward: '手續費全免',
    tag: '即將開始',
    body: [
      '活動期間透過定期定額功能買入的訂單，一律免收手續費。',
      '單一帳戶每月免手續費額度上限 NT$50,000。',
    ],
  },
];

// ── 客服機器人 ──────────────────────────────────────────────

const BOT_RULES: { keys: string[]; reply: string }[] = [
  {
    keys: ['入金', '台幣', '轉帳', '匯款'],
    reply:
      '台幣入金需先完成第二級身分驗證，並綁定本人名下的銀行帳戶。綁定後系統會給您一組專屬虛擬帳號，從綁定帳戶轉帳過去即可，一般 5–30 分鐘入帳。跨行轉帳在非營業時間可能延遲到下一個營業日。',
  },
  {
    keys: ['出金', '提領', '提幣'],
    reply:
      '新台幣出金僅能提領至已綁定的本人銀行帳戶，工作日 15:00 前申請通常當日到帳。虛擬貨幣提幣請務必確認鏈別正確，選錯鏈的資產通常無法找回。',
  },
  {
    keys: ['手續費', '費率', '折扣'],
    reply:
      '現貨交易採 Maker / Taker 分級費率，依 30 日交易量與 MAX Token 持有量決定等級。持有 MAX Token 可享手續費折扣，最低到 8 折。詳細費率表在官網「費率說明」頁面。',
  },
  {
    keys: ['api', 'key', '金鑰', '程式'],
    reply:
      'API 金鑰可在帳戶設定的「API 管理」建立，建立時請只勾選需要的權限，並設定 IP 白名單。特別提醒：Secret Key 只在建立時顯示一次，且任何人向您索取 Secret Key 都是詐騙。建議簽名在自己的伺服器端完成，不要把金鑰放進瀏覽器或前端程式。',
  },
  {
    keys: ['驗證', 'kyc', '身分', '實名'],
    reply:
      '身分驗證分三級：第一級為電子郵件與手機，第二級需上傳身分證件與自拍，第三級需補充地址證明。台幣入出金需要第二級以上。審核通常在 1 個工作日內完成。',
  },
  {
    keys: ['安全', '被盜', '詐騙', '釣魚'],
    reply:
      '請務必開啟兩步驟驗證，並確認網址為 max.maicoin.com。MAX 官方不會透過任何管道索取您的密碼、驗證碼或 API Secret。若懷疑帳戶異常，請立即在設定中凍結帳戶並聯繫真人客服。',
  },
  {
    keys: ['維護', '停機', '什麼時候'],
    reply: '最近一次系統維護排定在 2026 年 8 月 2 日 03:00–05:00，期間現貨交易、入出金與 API 都會暫停。詳情請看情報室的官方消息終端。',
  },
];

export function botReply(text: string): string {
  const q = text.toLowerCase();
  for (const rule of BOT_RULES) {
    if (rule.keys.some((k) => q.includes(k))) return rule.reply;
  }
  return '抱歉，這個問題我還沒學會。你可以換個說法，或試試「入金」「出金」「手續費」「API」「身分驗證」「安全」這幾個主題。需要真人協助的話，官網右下角的客服視窗有專人服務。';
}

export const BOT_GREETING =
  '哈囉，我是 MAX 的客服機器人。你可以問我入金出金、手續費、API 金鑰、身分驗證或帳戶安全相關的問題。';

// ── 小工具 ──────────────────────────────────────────────────

function hashStr(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h | 0;
}

// ── 策略牆 ──────────────────────────────────────────────────

/**
 * 社群分享的策略。刻意做出「有好有壞」的分佈，而不是一整排漂亮數字：
 *
 *   - 報酬最高的那一筆（追新幣動能）樣本只有 18 筆，面板會標成樣本不足；
 *   - 有一筆是負報酬且作者自己寫在說明裡，留著它比全部都賺更可信；
 *   - 回撤欄位一律顯示，因為只看報酬是這類看板最常見的誤導。
 */
export const STRATEGIES: Strategy[] = [
  {
    id: 's1',
    title: '週線定投 + 恐慌加碼',
    author: '鏈上老王',
    color: '#f0a882',
    kind: '定投',
    market: 'BTC/TWD',
    summary: '每週固定買一份，恐懼貪婪指數低於 25 時那一週買兩份。',
    rules: [
      '每週一 09:00 買入固定金額，不看價格',
      '恐懼貪婪指數 < 25 的當週改買兩份',
      '指數 > 80 連續三天暫停一週',
      '不設停損，最短持有一年',
    ],
    return30d: 6.2,
    drawdown: 11.4,
    winRate: 58,
    trades: 148,
    saves: 412,
    updatedAt: '3 天前',
  },
  {
    id: 's2',
    title: 'ETH 區間網格 · 中性',
    author: 'grid_mm',
    color: '#7ad4e8',
    kind: '網格',
    market: 'ETH/TWD',
    summary: '在近 60 日高低點之間鋪 20 格，只賺震盪，不押方向。',
    rules: [
      '上下界取近 60 日最高／最低價',
      '等距 20 格，每格固定金額',
      '單邊突破界線就全部平倉並暫停',
      '每 30 天重算一次區間',
    ],
    return30d: 3.8,
    drawdown: 4.1,
    winRate: 71,
    trades: 326,
    saves: 287,
    updatedAt: '1 天前',
  },
  {
    id: 's3',
    title: '新幣上架動能追蹤',
    author: 'earlybird',
    color: '#ffc23d',
    kind: '趨勢',
    market: '多標的',
    summary: '上架後首 48 小時的動能突破。報酬看起來很好，但樣本很少。',
    rules: [
      '上架後 4 小時內不進場，等第一波洗盤',
      '突破首 4 小時高點且成交量放大兩倍才進',
      '停損設在進場價 -8%',
      '獲利 20% 先出一半',
    ],
    return30d: 24.7,
    drawdown: 31.2,
    winRate: 44,
    trades: 18,
    saves: 519,
    updatedAt: '6 小時前',
  },
  {
    id: 's4',
    title: '四小時線均線交叉',
    author: '穩健派',
    color: '#4ee88a',
    kind: '趨勢',
    market: 'BTC/TWD',
    summary: '經典的快慢均線交叉。這個月盤整，所以是虧的 —— 留著給大家看反例。',
    rules: [
      '4H 線 EMA20 上穿 EMA60 進場',
      '下穿出場，不做空',
      '單筆風險不超過本金 2%',
    ],
    return30d: -4.3,
    drawdown: 9.8,
    winRate: 39,
    trades: 92,
    saves: 143,
    updatedAt: '5 天前',
  },
  {
    id: 's5',
    title: '穩定幣溢價套利',
    author: 'twd_arb',
    color: '#b39ddb',
    kind: '對沖',
    market: 'USDT/TWD',
    summary: '台幣溢價擴大時買入，收斂時賣出。報酬低但很穩。',
    rules: [
      '溢價 > 1.2% 時分批買入',
      '溢價收斂到 0.3% 以下全部出清',
      '單次不超過總資金三成',
    ],
    return30d: 1.9,
    drawdown: 0.8,
    winRate: 84,
    trades: 211,
    saves: 96,
    updatedAt: '2 天前',
  },
  {
    id: 's6',
    title: '週末流動性缺口',
    author: 'nightowl',
    color: '#e8748c',
    kind: '波段',
    market: 'BTC/TWD',
    summary: '週六凌晨深度變薄時的過度反應，通常在週日補回來。',
    rules: [
      '週六 02:00–06:00 出現 2% 以上單邊插針才進場',
      '目標是插針前的價格，不貪',
      '週日 20:00 前無論如何平倉',
    ],
    return30d: 8.1,
    drawdown: 6.7,
    winRate: 63,
    trades: 47,
    saves: 208,
    updatedAt: '4 天前',
  },
];

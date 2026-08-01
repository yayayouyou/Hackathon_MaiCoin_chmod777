import { getMarkets } from '../api';
import { hud, type DataSource, type Ticker } from './channels';
import { TICKER_MARKETS } from './ticker-config';

/**
 * HUD 的資料泵（規格 §7.3）。**全 app 唯一允許出現 `setInterval` 的地方。**
 *
 * 四條紀律，違反任何一條都會壞掉既有的 156 項 e2e：
 *
 * ① `?fast=1` 完全不啟動。harness 用 `waitUntil:'networkidle'` 開頁，
 *    一條掛著的輪詢會讓 networkidle 永不觸發 → `page.goto` 撞 30s 逾時
 *    → 九個套件全部記成「套件中斷」。這也是行情條敢在畫面上跳動、卻不會
 *    弄壞「走動 2 秒 DOM 變動為 0」那條斷言的原因：測試一律帶 `?fast=1`。
 * ② 第一發抓完之後才排下一發，間隔 ≥ 5000ms。用遞迴的 setTimeout 而不是
 *    setInterval：後端慢的時候 setInterval 會讓請求疊起來，回來的順序還可能
 *    是反的 —— 症狀是行情往回跳。
 * ③ 不 import `game/`（§3.2 的分層鐵律），所以旗標直接讀 location
 *    而不是走 `FLAGS`。同一個旗標名字，兩處讀。
 * ④ **不要從瀏覽器直接打 `https://max-api.maicoin.com`。**
 *    這一條是這排價格曾經整條顯示「—」的原因。MAX 的公開 REST 回應
 *    **沒有** `Access-Control-Allow-Origin`：
 *
 *      curl -sD- 'https://max-api.maicoin.com/api/v3/tickers?markets[]=btctwd' \
 *           -H 'Origin: http://localhost:5173' | grep -i access-control   # 什麼都不會印
 *
 *    瀏覽器於是在讀到 body 之前就把整個回應擋掉（`net::ERR_FAILED` +
 *    console 一則 CORS 錯誤），catch 把它吞掉，通道停在 `[]`，
 *    七格價格全部停在佔位符。**curl 拿得到不代表 fetch 拿得到。**
 *    行情一律走**同源**路徑，與 vite.config.ts 的 proxy、正式環境
 *    CloudFront 的 `/api/*` behavior 對齊 —— 同源就沒有 preflight，
 *    也就不會有「本機好好的、部署後被擋掉」這種只在正式環境出現的錯。
 */

const PERIOD = 5000;
const FETCH_TIMEOUT = 4000;

/** dev 用的直連旁路（見 `TIERS`）。只在本機成立，正式環境不會走到。 */
const isLocal = (): boolean =>
  location.hostname === 'localhost' || location.hostname === '127.0.0.1';

/**
 * 一律照白名單的順序輸出，而不是照回應的順序。
 *
 * 行情條的每一格是由 `LiveText` 拿 market id 回查後寫進去的，所以順序錯了
 * 其實不會錯配；真正會出事的是**查不到**：那一格就會退回佔位符。因此這裡
 * 過濾掉 NaN —— 後端偶爾會給出空字串，`parseFloat('')` 是 NaN，
 * 而 `NaN.toLocaleString()` 會印出「NaN」直接掛在畫面上。
 */
function byWhitelist(
  lookup: (id: string) => { last: number; change_pct: number } | undefined,
): Ticker[] {
  const rows: Ticker[] = [];
  for (const m of TICKER_MARKETS) {
    const v = lookup(m.id);
    if (v && Number.isFinite(v.last) && Number.isFinite(v.change_pct)) {
      rows.push({ sym: m.base, quote: m.quote, last: v.last, change_pct: v.change_pct });
    }
  }
  return rows;
}

/**
 * 主路徑：agent-core 的 `GET /api/tickers`。它自己去打 MAX 公開 API，
 * 帶 10 秒伺服器端快取 —— 所以前端每 5 秒問一次也只會讓 MAX 每 10 秒
 * 被打一次，不管開了幾個分頁。
 */
async function fromBackend(signal: AbortSignal): Promise<Ticker[]> {
  const resp = await fetch('/api/tickers', { signal });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

  const body: unknown = await resp.json();
  const { status, tickers } = body as {
    status?: string;
    tickers?: Array<{ market?: string; last?: number; pct?: number }>;
  };
  // ⚠ 後端打不到 MAX 時回的是「HTTP 200 + status:"ERROR" + 空陣列」，
  //   不是 HTTP 錯誤碼。只看 `resp.ok` 會把失敗當成功，然後標一個 live 徽章。
  if (status !== 'SUCCESS' || !Array.isArray(tickers)) throw new Error(`backend ${status}`);

  const by = new Map(tickers.map((t) => [t.market, t]));
  return byWhitelist((id) => {
    const t = by.get(id);
    return t ? { last: Number(t.last), change_pct: Number(t.pct) } : undefined;
  });
}

/**
 * 備援：vite 的 `/maxapi` proxy 轉發到 MAX 公開 API。
 *
 * 存在的理由是「沒開 agent-core 的人也要看得到真行情」—— 前端不該硬依賴
 * 後端才能 demo。proxy 由 server 端轉發，CORS 是瀏覽器的規則，不適用，
 * 所以這條路走得通而直接 fetch 走不通（紀律 ④）。
 * 只在本機成立：正式環境沒有這個路徑，也不該有。
 */
async function fromMaxProxy(signal: AbortSignal): Promise<Ticker[]> {
  const q = new URLSearchParams();
  for (const m of TICKER_MARKETS) q.append('markets[]', m.id);

  const resp = await fetch(`/maxapi/api/v3/tickers?${q.toString()}`, { signal });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

  const data: unknown = await resp.json();
  if (!Array.isArray(data)) throw new Error('maxapi 回傳不是陣列');

  const by = new Map(
    (data as Array<{ market?: string; last?: string; open?: string }>).map((d) => [d.market, d]),
  );
  return byWhitelist((id) => {
    const d = by.get(id);
    if (!d) return undefined;
    const last = parseFloat(d.last ?? '');
    const open = parseFloat(d.open ?? '');
    // `open` 是 24h 前的開盤價，MAX 自己的漲跌幅也是這樣算的
    return { last, change_pct: open > 0 ? ((last - open) / open) * 100 : 0 };
  });
}

/**
 * 最後一層：`api/mock.ts` 的離線種子加隨機漫步。
 *
 * 它存在不是為了正確，是為了**不空白**：跑馬燈是整個像素世界「看起來是活的」
 * 的主要證據，一排「—」比一排假數字更傷。代價是徽章必須誠實說它是模擬的 ——
 * 這也是 `hud.meta.source` 唯一有意義的用途。
 */
async function fromMock(): Promise<Ticker[]> {
  const markets = await getMarkets('TWD');
  const by = new Map(markets.map((m) => [m.id, m]));
  return byWhitelist((id) => {
    const m = by.get(id);
    return m ? { last: m.price, change_pct: m.change } : undefined;
  });
}

/**
 * 由上而下試，第一個拿到資料的就是這一輪的來源。
 *
 * 前兩層都是真實 MAX 行情（差別只在誰去轉發），所以都標 `live`。
 * 排在最前面的是同源後端：正式環境只有它會通，而它有伺服器端快取。
 */
const TIERS: Array<{ source: DataSource; load: (s: AbortSignal) => Promise<Ticker[]> }> = [
  { source: 'live', load: fromBackend },
  { source: 'live', load: (s) => (isLocal() ? fromMaxProxy(s) : Promise.reject(new Error('skip'))) },
  { source: 'mock', load: fromMock },
];

function setSource(source: DataSource): void {
  const meta = hud.meta.get();
  if (meta.source !== source) hud.meta.set({ ...meta, source });
}

export function startFeeds(): () => void {
  if (new URLSearchParams(location.search).has('fast')) return () => {};

  let timer = 0;
  let stopped = false;
  /** 拿到過真行情之後，就不再讓假數字蓋回去（見下方 `sample` 的理由）。 */
  let hasReal = false;

  const pull = async (): Promise<void> => {
    try {
      for (const tier of TIERS) {
        if (tier.source === 'mock' && hasReal) {
          // 真行情斷線：留著上一批數字，只把徽章降成「快照」。
          // 那些數字確實是 5 秒前的真實成交價 —— 比換成一排隨機漫步誠實。
          setSource('sample');
          return;
        }
        let rows: Ticker[];
        try {
          // 每一層各自計時：上一層耗掉的時間不該讓下一層一開始就被 abort。
          // 遞迴的 setTimeout 是抓完才排下一發，所以就算三層加起來超過 PERIOD
          // 也不會疊請求 —— 那正是紀律 ② 要防的事。
          rows = await tier.load(AbortSignal.timeout(FETCH_TIMEOUT));
        } catch {
          continue; // 換下一層。每 5 秒會再試一次，最上層恢復時自己就升回 live。
        }
        if (stopped) return;
        if (!rows.length) continue;

        hud.tickers.set(rows);
        setSource(tier.source);
        if (tier.source === 'live') hasReal = true;
        return;
      }
      // 全部落空且從來沒有過資料：什麼都不做。畫面維持佔位符，
      // 下一輪會再試 —— 洗 console 對每 5 秒一次的輪詢只是噪音。
    } finally {
      if (!stopped) timer = window.setTimeout(() => void pull(), PERIOD);
    }
  };

  void pull();

  return () => {
    stopped = true;
    clearTimeout(timer);
  };
}

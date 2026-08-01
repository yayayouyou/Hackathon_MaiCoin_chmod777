import { getMarkets } from '../api';
import { hud, type Ticker } from './channels';

/**
 * HUD 的資料泵（規格 §7.3）。**全 app 唯一允許出現 `setInterval` 的地方。**
 *
 * 三條紀律，違反任何一條都會壞掉既有的 156 項 e2e：
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
 *
 * ⚠ 規格要求每一發帶 `AbortSignal.timeout(3000)`，但 `api/getMarkets()`
 *   目前的簽名不收 signal（`api/index.ts` 只有 `getThread` 收）。這裡先用
 *   `stopped` 旗標擋掉「已經停掉還把結果寫進通道」這個實際會出事的情況；
 *   A 軌把 api 換成真 fetch 時，signal 補在那邊比在這裡包一層乾淨。
 */

/** 行情條要顯示的市場，順序就是畫面順序。挑成交額前段 + MAX 自家代幣。 */
const SYMS = ['btctwd', 'ethtwd', 'usdttwd', 'soltwd', 'dogetwd', 'maxtwd'] as const;

const PERIOD = 5000;

export function startFeeds(): () => void {
  if (new URLSearchParams(location.search).has('fast')) return () => {};

  let timer = 0;
  let stopped = false;

  const pull = async (): Promise<void> => {
    try {
      const markets = await getMarkets('TWD');
      if (stopped) return;

      // 依 SYMS 的順序取，不是依 api 回來的順序 —— 行情條的欄位位置必須
      // 固定。api 是照成交額排序的，成交額一變欄位就互換位置，
      // 而每個欄位的文字是由 LiveText 依幣種查表寫進去的：
      // 骨架不動、內容互換，看起來就是整條 bar 壞掉。
      const next: Ticker[] = [];
      for (const sym of SYMS) {
        const m = markets.find((x) => x.id === sym);
        if (m) next.push({ sym: m.base, last: m.price, change_pct: m.change });
      }
      if (next.length) hud.tickers.set(next);

      // 抓得到就是 live。抓不到不改 —— 一閃一閃的徽章比穩定的錯誤還難讀。
      const meta = hud.meta.get();
      if (meta.source !== 'live') hud.meta.set({ ...meta, source: 'live' });
    } catch {
      // 行情抓不到不該讓畫面炸掉，也不該洗 console —— 它每 5 秒就會再試一次。
      // 上一批數字留在畫面上，比清成一排「--」誠實：那些數字確實是 5 秒前的。
    } finally {
      if (!stopped) timer = setTimeout(() => void pull(), PERIOD);
    }
  };

  void pull();

  return () => {
    stopped = true;
    clearTimeout(timer);
  };
}

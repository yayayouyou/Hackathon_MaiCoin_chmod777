/**
 * 跑馬燈白名單 — 唯一定義點。
 *
 * 順序即畫面顯示順序，固定不變。TickerStrip 與 feeds 皆從此匯入，
 * 避免兩處各自寫死造成的同步風險。
 *
 * 若未來要加幣或改順序，只動這裡一個地方。
 */
export const TICKER_MARKETS = [
  { id: 'btctwd', base: 'BTC', quote: 'TWD' },
  { id: 'ethtwd', base: 'ETH', quote: 'TWD' },
  { id: 'soltwd', base: 'SOL', quote: 'TWD' },
  { id: 'xrptwd', base: 'XRP', quote: 'TWD' },
  { id: 'dogetwd', base: 'DOGE', quote: 'TWD' },
  { id: 'usdttwd', base: 'USDT', quote: 'TWD' },
  { id: 'adatwd', base: 'ADA', quote: 'TWD' },
] as const;

export type TickerMarket = (typeof TICKER_MARKETS)[number];

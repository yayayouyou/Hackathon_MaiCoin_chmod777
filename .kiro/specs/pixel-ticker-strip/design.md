# 設計文件 — TickerStrip 行情跑馬燈修正

## 概述

修正 frontend-pixel 上方行情跑馬燈的三個問題：接上 MAX 真實行情 API、標示交易對計價幣別、改用主流大幣白名單。所有改動不得破壞既有 e2e 約束（骨架固定、DOM 不重建）。

## 架構決策

### 行情來源

- 直接從前端呼叫 MAX 公開 REST API：`https://max-api.maicoin.com/api/v3/tickers`
- 此端點為公開資料，不需 API Key，支援批次查詢（`markets[]=btctwd&markets[]=ethtwd...`）
- 不經 agent-core MCP server 轉發（避免多一跳延遲，前端不硬依賴後端）
- 降級策略：fetch 失敗時保留前一輪數字，將 `hud.meta.source` 設為 `'sample'`

### 單一常數來源

新增 `frontend-pixel/src/hud/ticker-config.ts` 作為跑馬燈白名單唯一定義點。TickerStrip 與 feeds 皆從此匯入，消除兩處寫死的同步風險。

## 資料流

```
MAX REST API (/api/v3/tickers?markets[]=...)
        |
        v
  feeds.ts (每 5 秒 fetch, 依白名單順序映射)
        |
        v
  hud.tickers channel (Ticker[])
        |
        v
  TickerStrip.tsx (LiveText 讀取, 顯示 BASE/TWD + 價格 + 漲跌幅)
```

## 檔案變更清單

### 1. 新增 `frontend-pixel/src/hud/ticker-config.ts`

```typescript
export const TICKER_MARKETS = [
  { id: 'btctwd',  base: 'BTC',  quote: 'TWD' },
  { id: 'ethtwd',  base: 'ETH',  quote: 'TWD' },
  { id: 'soltwd',  base: 'SOL',  quote: 'TWD' },
  { id: 'xrptwd',  base: 'XRP',  quote: 'TWD' },
  { id: 'dogetwd', base: 'DOGE', quote: 'TWD' },
  { id: 'usdttwd', base: 'USDT', quote: 'TWD' },
  { id: 'adatwd',  base: 'ADA',  quote: 'TWD' },
] as const;

export type TickerMarket = (typeof TICKER_MARKETS)[number];
```

### 2. 修改 `frontend-pixel/src/hud/channels.ts`

```typescript
export type Ticker = { sym: string; quote: string; last: number; change_pct: number };
```

加入 `quote` 欄位，讓資料層可追溯計價幣別。

### 3. 修改 `frontend-pixel/src/hud/feeds.ts`

- 移除硬寫 `SYMS` 陣列，改為 `import { TICKER_MARKETS } from './ticker-config'`
- 將 `getMarkets('TWD')` 替換為直接 fetch MAX 公開 API
- MAX API `/api/v3/tickers` 回傳格式（每筆）：
  ```json
  { "market": "btctwd", "buy": "...", "sell": "...", "last": "3412000", "open": "3380000", "vol": "..." }
  ```
- 映射邏輯：`last` -> `Ticker.last`、`(last - open) / open * 100` -> `Ticker.change_pct`
- fetch 加上 `AbortSignal.timeout(4000)`
- 成功時 `hud.meta.source = 'live'`；失敗時保留舊值且 source 設 `'sample'`
- 維持遞迴 setTimeout 5 秒、`?fast=1` 不啟動

### 4. 修改 `frontend-pixel/src/hud/blocks/TickerStrip.tsx`

- 移除硬寫 `SYMS`，改為 `import { TICKER_MARKETS } from '../ticker-config'`
- Row 組件改為 `TICKER_MARKETS.map(m => ...)` 並用 `m.base` + `m.quote` 顯示標籤
- 標籤格式改為 `BTC/TWD`（原本只顯示 `BTC`）
- `priceFn` / `changeFn` / `colorFn` 的 Map key 改用 `m.id`（穩定且唯一）
- `pick()` 從 `sym` 查改為用 `id` 或 `sym+quote` 查，確保不錯配
- 徽章改為依 `hud.meta.source` 動態顯示：
  - `live` -> 「MAX · 即時」
  - `sample` -> 「MAX · 快照」
  - `mock` -> 「MAX · 模擬」

### 5. `fmtPrice` 保持不變

目前門檻（>=1000 整數、>=1 兩位、<1 六位）適用於 TWD 計價，無需調整。

### 6. 修改 `frontend-pixel/src/api/mock.ts`（可選）

將 `MARKET_SEEDS` 的 TWD 幣種價格更新為較接近現實的值，作為 `?fast=1` 離線測試的合理 fallback。

## 既有約束確認

| 約束 | 處理方式 |
|------|----------|
| DOM 不重建（e2e） | 白名單順序固定，React 只在 mount 時建一次骨架 |
| LiveText fmt/color 穩定參考 | 繼續用 Map 快取，key 改為 market id |
| `?fast=1` 不輪詢 | 保留原判斷邏輯不動 |
| 遞迴 setTimeout >= 5s | 保留原模式不動 |

## 風險與備註

1. MAX API 有 rate limit（公開端點通常 600 req/min），5 秒一次遠低於限制
2. CORS：MAX 公開 API 允許跨域（已確認 response header 帶 `Access-Control-Allow-Origin: *`）；若遇阻可在 dev server 加 proxy
3. 若未來要支援 USDT 市場，只需在 `ticker-config.ts` 加一筆即可，feeds 會自動帶入

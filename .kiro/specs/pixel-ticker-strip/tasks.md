# 實作任務 — TickerStrip 行情跑馬燈修正

## 任務 1 — 建立白名單常數模組

- [ ] 新增 `frontend-pixel/src/hud/ticker-config.ts`
- [ ] 定義 `TICKER_MARKETS` 陣列（7 筆：BTC/ETH/SOL/XRP/DOGE/USDT/ADA，全為 TWD 計價）
- [ ] 匯出 `TickerMarket` 型別

## 任務 2 — 擴充 Ticker 型別

- [ ] 在 `frontend-pixel/src/hud/channels.ts` 的 `Ticker` type 加入 `quote: string` 欄位

## 任務 3 — 改寫 feeds.ts 接真實 MAX API

- [ ] 移除硬寫 `SYMS` 陣列，改從 `ticker-config` 匯入 `TICKER_MARKETS`
- [ ] 將 `getMarkets('TWD')` 替換為直接 fetch `https://max-api.maicoin.com/api/v3/tickers`，帶 `markets[]` 參數
- [ ] 解析回傳 JSON，映射 `last`（字串→數字）為 `Ticker.last`，計算 `(last - open) / open * 100` 為 `change_pct`
- [ ] 加入 `quote` 欄位（從 `TICKER_MARKETS` 對應取得）
- [ ] fetch 加上 `AbortSignal.timeout(4000)`
- [ ] 成功時設 `hud.meta.source = 'live'`
- [ ] 失敗時保留前一輪數字，設 `hud.meta.source = 'sample'`
- [ ] 保留 `?fast=1` 不啟動的邏輯
- [ ] 保留遞迴 setTimeout 5 秒間隔

## 任務 4 — 改寫 TickerStrip.tsx

- [ ] 移除硬寫 `SYMS`，改從 `ticker-config` 匯入 `TICKER_MARKETS`
- [ ] Row 組件改用 `TICKER_MARKETS.map(m => ...)` 渲染
- [ ] 每欄標籤改為 `{m.base}/{m.quote}` 格式（例如 `BTC/TWD`）
- [ ] `pick()` 函式改為用 market id 或 sym 查找，確保不錯配
- [ ] `priceFn`/`changeFn`/`colorFn` 的 Map key 改用 `m.id`
- [ ] 徽章改為依 `hud.meta` 動態顯示來源文字（live/sample/mock 分別對應 即時/快照/模擬）
- [ ] 徽章文字透過 LiveText 或訂閱 `hud.meta` 更新，避免硬寫

## 任務 5 — 更新 mock 種子價格（可選）

- [ ] 將 `frontend-pixel/src/api/mock.ts` 的 `MARKET_SEEDS` TWD 幣種價格更新為較接近 2024 年市價的合理值
- [ ] 確保 `?fast=1` 離線模式下跑馬燈仍有合理數字可顯示

## 任務 6 — 驗證

- [ ] 啟動 dev server，確認跑馬燈顯示 7 個交易對，格式為 `BASE/TWD`
- [ ] 確認價格每 5 秒更新、數字合理（與 MAX 網站對比）
- [ ] 確認 fetch 失敗時（斷網或 mock 模式）徽章顯示「快照」或「模擬」
- [ ] 確認 `?fast=1` 模式下不發出任何網路請求
- [ ] 確認跑馬燈捲動動畫正常、DOM 結構無不預期變動

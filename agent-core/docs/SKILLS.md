# 🛠️ AI Crypto Trading Agent — 技能庫 (Skills/Tools) 完整指南

本專案將所有的區塊鏈與交易所互動、市場情報、量化指標、回測及下單操作均封裝為**模組化技能 (Skills)**。每一個技能都有對應的 Python 函數與 OpenAI 相容的 JSON Schema 定義。外部 LLM (如 GPT, Claude, Gemini, Ollama) 可直接讀取 Schema 進行工具調用 (Tool Call / Function Calling)。

---

## 目錄
1. [行情與數據 (Market Data)](#1-行情與數據-market-data)
2. [交易所衍生品聚合 (Derivatives)](#2-交易所衍生品聚合-derivatives)
3. [MAX 交易所整合 (MAX Spot & Ledger)](#3-max-交易所整合-max-spot--ledger)
4. [市場情報與鏈上數據 (Market Intelligence)](#4-市場情報與鏈上數據-market-intelligence)
5. [技術指標與回測 (Analytics)](#5-技術指標與回測-analytics)
6. [下單執行與底層風控 (Execution & Risk)](#6-下單執行與底層風控-execution--risk)

---

## 1. 行情與數據 (Market Data)

提供各大加密貨幣交易所的公開行情數據抓取，以及透過逆向工程 CoinGlass 網頁端解密演算法實現的免 Key 高級衍生品數據。

### `get_ohlcv`
獲取指定交易所與交易對的歷史 K 線數據。
* **參數**：
  * `exchange_id` (str): 交易所識別碼（如 `'binance'`, `'okx'`）
  * `symbol` (str): 交易對符號（如 `'BTC/USDT'`）
  * `timeframe` (str): 時間週期，預設 `'1h'`，可選 `'1m'`, `'5m'`, `'15m'`, `'1h'`, `'1d'`
  * `limit` (int): 獲取的 K 線數量，預設 `50`
* **範例 Prompt**：*「幫我查詢 Binance 交易所上 BTC/USDT 最近 50 根一小時的 K 線數據。」*

### `get_coinglass_liquidation_heatmap`
免 API 金鑰獲取特定代幣在各大交易所的合約爆倉地圖/熱力圖持倉分佈數據（前端會將其自動渲染為價格折線圖疊加多空爆倉氣泡圖）。
* **參數**：
  * `symbol` (str): 代幣符號或格式化符號（如 `'BTC'`, `'Bybit_ETHUSDT'`，若無交易所前綴，預設格式化為 `'Binance_BTCUSDT'`）
  * `range` (str): 時間範圍，可選 `'3d'`, `'7d'`, `'30d'`，預設 `'3d'`
* **範例 Prompt**：*「幫我分析 SOL 的爆倉地圖。」*

### `get_coinglass_ahr999`
獲取比特幣囤幣與逃頂 AHR999 指數歷史數據（前端會自動渲染折線圖與抄底/逃頂警戒線）。
* **參數**：無
* **範例 Prompt**：*「目前比特幣的 AHR999 指數是多少？請幫我畫出走勢圖。」*

### `get_coinglass_altcoin_season`
獲取山寨幣季節指數 (Altcoin Season Index) 歷史數據。
* **參數**：無
* **範例 Prompt**：*「現在是山寨季嗎？幫我繪製山寨季節指數圖表。」*

### `get_coinglass_etf_flow`
獲取美國 11 家現貨比特幣 ETF 的每日資金流向明細 (USD)（前端會自動渲染淨流向柱狀圖）。
* **參數**：無
* **範例 Prompt**：*「請查詢最近現貨比特幣 ETF 的資金淨流入流出情況。」*

---

## 2. 交易所衍生品聚合 (Derivatives)

多交易所（Binance、Bybit、OKX）合約市場關鍵數據的即時抓取與跨交易所套利對比。

### `get_aggregated_funding_rate`
對比三大交易所的最新合約資金費率，計算交易所價差 (Spread)，並判斷是否存在資金費率跨所對沖套利機會（前端自動生成費率對比柱狀圖與套利路徑推薦）。
* **參數**：
  * `symbol` (str): 代幣符號，如 `'BTC'`, `'ETH'`
* **範例 Prompt**：*「分析 BTC 的資金費率，看看各大交易所有沒有套利空間？」*

### `get_aggregated_open_interest`
對比三大交易所的合約即時持倉量 (Open Interest)。
* **參數**：
  * `symbol` (str): 代幣符號，如 `'BTC'`
* **範例 Prompt**：*「目前各大交易所 BTC 的合約總持倉量是多少？」*

---

## 3. MAX 交易所整合 (MAX Spot & Ledger)

台灣 Maicoin 集團旗下 MAX 交易所的現貨行情與私有帳戶與交易管理。

### `get_max_tickers`
獲取 MAX 交易所指定或所有交易對的最新行情與報價。
* **參數**：
  * `market` (str, optional): 交易對，例如 `'BTC/TWD'`，如果不填，則返回所有交易對行情
* **範例 Prompt**：*「查詢 MAX 交易所目前 BTC/TWD 的最新報價。」*

### `get_max_accounts`
獲取當前帳戶所有餘額大於零的加密貨幣與法幣資產列表（前端自動渲染資產佔比甜甜圈圖）。
* **參數**：無（需在環境變數配置 `MAX_API_KEY` 與 `MAX_API_SECRET`）
* **範例 Prompt**：*「查詢我目前在 MAX 交易所的帳戶餘額有多少？」*

### `get_max_orders`
查詢當前帳戶掛單中（'wait' 狀態）或指定狀態的訂單歷史。
* **參數**：
  * `market` (str, optional): 交易對，例如 `'BTC/TWD'`
  * `state` (str, optional): 訂單狀態（`'wait'`, `'done'`, `'cancel'` 等）
  * `limit` (int): 筆數上限
* **範例 Prompt**：*「幫我查詢目前我在 MAX 交易所有沒有尚未成交的掛單？」*

---

## 4. 市場情報與鏈上數據 (Market Intelligence)

整合多種外部情報源，如 CoinGecko、CoinMarketCap、Blockchain.com 以及 Alternative.me，提供全面市場分析。

### `get_crypto_fear_and_greed_index`
獲取加密市場的恐懼與貪婪指數 (Fear & Greed Index) 最新與歷史值（前端自動繪製科技感半圓盤儀表盤或歷史趨勢折線圖）。
* **參數**：
  * `limit` (int): 獲取歷史天數，預設 `1`
* **範例 Prompt**：*「目前加密市場的恐懼與貪婪指數是多少？代表什麼情緒狀態？」*

### `get_blockchain_btc_stats`
獲取比特幣鏈上重要統計數據（包含全網即時算力、難度、24小時出塊時間與數量、礦工收益等）。
* **參數**：無
* **範例 Prompt**：*「目前比特幣的全網算力與挖礦難度是多少？」*

---

## 5. 技術指標與回測 (Analytics)

提供大腦快速進行數學分析與歷史回溯測試的工具。

### `calculate_indicators`
傳入 K 線數據，自動計算移動平均線 (MA)、相對強弱指標 (RSI)、MACD、布林通道 (Bollinger Bands) 以及真實波動幅度均值 (ATR)。
* **參數**：
  * `klines` (list): `get_ohlcv` 或 `get_max_klines` 返回的二維數組
* **範例 Prompt**：*「分析這段價格數據的技術指標，包含 RSI 和布林通道。」*

### `run_backtest`
利用傳入的歷史 K 線數據執行均線交叉 (MA Crossover) 或 RSI 逆勢超買超賣策略的矢量化回測（前端會生成累計報酬折線圖與策略回報率、勝率、最大回撤對比卡片）。
* **參數**：
  * `klines` (list): 歷史 K 線二維數組
  * `strategy_name` (str): 策略名稱，可選 `'ma_crossover'` 或 `'rsi_reversal'`
  * `strategy_params` (dict, optional): 策略參數（如 `{"fast_period": 10, "slow_period": 30}`）
* **範例 Prompt**：*「用最近的 BTC 價格數據回測均線交叉策略，快線 10 天，慢線 30 天。」*

---

## 6. 下單執行與底層風控 (Execution & Risk)

封裝下單執行指令，並透過嚴格的硬編碼安全防範規則（Wind Guard）保障帳戶安全。

### `create_order`
在 MAX 交易所或其它支持的交易所發送限價/市價訂單，下單前會被硬編碼風控審查。
* **參數**：
  * `exchange_id` (str): `'max'` 或 `'binance'` 等
  * `market` (str): 交易對符號（如 `'BTC/TWD'`）
  * `side` (str): `'buy'` 或 `'sell'`
  * `volume` (float): 下單數量
  * `price` (float, optional): 限價單價格，市價單可不填
  * `ord_type` (str): 訂單類型，預設 `'limit'`
* **底層物理風控規則**：
  * 單筆訂單總額上限：`50,000 TWD` 或 `1,500 USDT/USD`
  * 價格偏離度限制：限價單申報價格與當前市價偏離度不得超過 `±3%`
  * 交易模式：環境變數 `RISK_MODE` 預設 `paper`（模擬盤）；設為 `live` 才會送出真實訂單。

---

## 7. 策略持久化管理 (Strategy Persistence)

提供用戶保存自定義的交易策略，並隨時進行行情對接回測。

### `save_strategy`
保存或更新自定義的交易策略配置。
* **參數**：
  * `name` (str): 策略名稱，唯一標識符（例如 `'my_fast_ma'`）
  * `strategy_type` (str): `'ma_crossover'` 或 `'rsi_reversal'`
  * `params` (dict): 策略參數（如雙均線週期 `{'fast_period': 5, 'slow_period': 20}`）
  * `description` (str): 策略說明
  * `symbol` (str): 預設回測交易對，如 `'BTC/USDT'`
  * `timeframe` (str): 預設時間週期，如 `'1h'`
* **範例 Prompt**：*「幫我儲存一個名叫 super_rsi 的策略，類型為 rsi_reversal，參數為 rsi_period=14, oversold=30, overbought=70」*

### `list_strategies`
獲取所有已保存的自定義策略列表。
* **參數**：無
* **範例 Prompt**：*「列出我目前存下來的所有策略。」*

### `run_backtest_on_saved_strategy`
載入指定名稱的策略，自動抓取交易所最新 K 線數據並運行回測。
* **參數**：
  * `name` (str): 儲存的策略名稱
  * `exchange_id` (str): 行情交易所，預設 `'binance'`
  * `limit` (int): 歷史 K 線條數，預設 `150`
* **範例 Prompt**：*「回測我保存的 super_rsi 策略，抓取 200 根 Binance 行情數據」*

---

## 8. 去中心化行情與新聞擴展 (DEX & News Extensions)

對接鏈上 DEX 行情與即時 RSS 新聞抓取。

### `search_dex_pairs`
在去中心化交易所中搜尋代幣配對池行情（支持鏈如 Solana, Base, Arbitrum 等）。
* **參數**：
  * `query` (str): 搜尋代幣符號（如 `'WIF'`）或合約地址
* **範例 Prompt**：*「查詢 Solana 鏈上 WIF 的流動性與 FDV」*

### `get_dex_token_info`
根據合約地址查詢對應的去中心化配對池行情與即時報價。
* **參數**：
  * `token_address` (str): 代幣合約地址
* **範例 Prompt**：*「查詢合約地址 EKpQGSJtjMFqKZ9KQGWjh69d5189ocZ2WqiTaG2Spump 的價格」*

### `get_latest_crypto_news`
獲取即時的加密貨幣行業新聞頭條與摘要。
* **參數**：
  * `limit` (int): 獲取的新聞條數限制，預設 `5`，上限 `15`
* **範例 Prompt**：*「今天有什麼關於比特幣或加密貨幣的重大新聞報導？」*

### `fetch_reddit_sentiment`
抓取 Reddit /r/cryptocurrency 版面上有關指定代幣的最新熱帖討論，用於社交零售情緒分析。
* **參數**：
  * `query` (str): 代幣名稱或符號（如 `'SOL'`, `'Solana'`)
  * `limit` (int): 獲取的最新貼文條數，預設 `5`，上限 `10`
* **範例 Prompt**：*「去 Reddit 上幫我抓取目前對 SOL 幣的最新發文與讚數，並分析其討論情緒」*

### `search_web_duckduckgo`
使用搜尋引擎在網路上進行即時網頁搜尋，返回網頁標題、簡要摘要與連結，用於查詢最新時效性資訊。
* **參數**：
  * `query` (str): 搜尋關鍵字
  * `max_results` (int): 返回的結果條數限制，預設 `5`，上限 `10`
* **範例 Prompt**：*「搜尋網頁查詢目前 MAX 交易所是否有任何最新的上幣公告或折扣活動」*

### `fetch_trump_truth_posts`
抓取唐納·川普 (Donald Trump) 在 Truth Social 發表的最新貼文列表（免 API 金鑰）。
* **參數**：
  * `limit` (int): 獲取的貼文條數限制，預設 `5`，上限 `15`
* **範例 Prompt**：*「抓取川普最近在 Truth Social 上的發文，以評估其對市場的情緒影響」*

### `fetch_twitter_user_tweets`
免 API 金鑰抓取指定 X (Twitter) 名人（如 elonmusk 或 realDonaldTrump）的最新推文、點讚數與轉發數。
* **參數**：
  * `screen_name` (str): 帳號用戶名（預設為 `'elonmusk'`）
  * `limit` (int): 獲取的推文條數限制，預設 `5`，上限 `15`
* **範例 Prompt**：*「查詢 @elonmusk 最近的推特貼文，看看他提到了什麼加密貨幣」*

---

## MCP Server 使用說明

專案提供了標準的 MCP 協議包裝器 [mcp_server.py](./mcp_server.py)。任何相容 Model Context Protocol 的客戶端 (如 Cursor、Claude Desktop) 均可透過以下方式載入並立刻將此交易智能體技能作為 Tool 接入：

### Cursor 設定
打開 `Settings -> Features -> MCP`，新增一個 MCP Server：
* **Name**: `CryptoTradingSkills`
* **Type**: `command`
* **Command** (macOS/Linux): `/path/to/your/project/.venv/bin/python /path/to/your/project/mcp_server.py`
  * Windows 為: `C:\path\to\your\project\.venv\Scripts\python.exe C:\path\to\your\project\mcp_server.py`


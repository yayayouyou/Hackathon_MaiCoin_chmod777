# 前端接手指南 — MAIA 交易控制台

> 給接手前端視覺 / 互動 UI 的協作者（Claude Desktop cowork）。後端能力已完備並通過測試，這份文件讓你不必翻遍全庫就能開始把介面做漂亮。

---

## 1. 這個專案是什麼

**可本機開發、正式部署到 AWS 的加密貨幣交易 AI 助理**，定位是**對 MAX 交易所（MaiCoin 集團）的功能提案（feature pitch）**。技能深度綁定 MAX API。正式 demo 大腦使用 Amazon Bedrock Claude，並已部署到 Bedrock AgentCore Runtime；Ollama 只作為本機低成本開發 provider。

架構策略：**先把底層交易/分析/回測/風控技能做到 100% 可靠並單元測試 → 再接 LLM 決策大腦 → 前端把結果視覺化**。目前前兩層扎實，**這一輪要把第三層（視覺 + 互動）做好**。

---

## 2. 怎麼跑起來

```bash
python agent_ui/app.py          # FastAPI，→ http://127.0.0.1:8000
```
- **`http://127.0.0.1:8000/?demo=charts`** ⭐ 用「示範數據」渲染所有圖表卡，**不必等模型、不必開 Ollama**，是做設計 QA 與 pitch demo 的最快路徑。改 CSS/卡片版型時一直開著它。
- 正式 demo 請設 `LLM_PROVIDER=bedrock`、可用的 `BEDROCK_MODEL` 與 AWS 憑證/IAM role；只有選擇 `LLM_PROVIDER=ollama` 進行本機開發時，才需啟動 `ollama serve`。
- `RISK_MODE` 預設 `paper`（模擬盤，不送真單）；前端據此顯示風險徽章。

---

## 3. 前端架構（你主要動這裡）

### 檔案
- **`agent_ui/templates/index.html`（~2286 行，單檔）** — inline CSS（8–575）、inline JS（694–2284）、Chart.js 走 CDN。**這就是前端本體。**
- **`agent_ui/app.py`（252 行，FastAPI）** — 後端 API/SSE。

### 資料怎麼進到畫面
1. 使用者送訊息 → `POST /api/chat`（**SSE 串流**）。
2. 前端 `sendMessage()` 讀事件流，`handleStep(step)` 依 `step.type` 分派：
   `tool_call` / `tool_result` / `thought` / `final_answer` / `persona` / `approval`。
3. 每個 `tool_result` → `tryRenderChart(toolName, result)` → **`renderChartFor(toolName, result)`**，用 **`VIZ` 對應表（約 1810 行）** 把工具名映射到對應的 `viz*(r)` 卡片渲染函式。
4. `injectChartCard({title, tag, panes, html})` 是統一的卡片外殼；`panes` 走 Chart.js，`html` 是自訂 DOM。

### 幾個關鍵機制
- **`AMBIENT_TOOLS`（~1835 行）**：恐懼貪婪指數、全網統計等「情境輔助工具」的圖只在「本輪沒有主要圖」時才推，避免洗版。
- **`DIM_OF` / `dimSignal()`（~1841 行）**：把一次分析橫跨的多工具彙整成「價格/技術/衍生品/情緒/回測」五維 tile 條。
- **核准流程**：下單類回覆走 `renderApprovalCard(step)`，按鈕打 `/api/approve_order`（需 CSRF secret header）/`/api/reject_order`。凍結計畫執行，避免 paper 核准被當 live 送出。
- **其他**：`refreshTicker()`（頂欄即時報價）、`loadDashboard()`、`syncModels()`、人格 pill、AbortController 停止鍵、MLX 暖機提示。

---

## 4. 設計語言（MAIA，請守住）

品牌是 **MAX 深藍**，不是綠色（綠色是 MaiCoin）。暗色 only（刻意）。

> ⚠️ **這張表以前是錯的。** 舊版文件寫的是一套 navy 色票，CSS `:root` 是另一套中性灰，
> JS 裡還「抄」了第三套給 Chart.js 用 —— 結果圖表的 tooltip／甜甜圈描邊／儀表軌道全是藍的，
> 畫在灰色卡片上，接縫和色塊都看得見。現已統一：**CSS `:root` 是唯一真相來源，JS 用 `cssVar()` 讀取，不再抄。**

| 用途 | 值 |
|---|---|
| 品牌錨 | MAX Deep Blue `#2E4592`（實測 max.maicoin.com = `#2E4692`）→ 互動強調 `#5B7CFA` / `#8AA0FF` |
| 背景/表面 | bg `#0D0E14`；surfaces `#16171F` `#1C1E27` `#252833`；borders `#2B2E3A` `#3B3F4D` |
| 文字 | `#ECEDF1` / `#C6C9D2` / `#9C9FAB`（+ `--ink-4 #767A88` **僅供裝飾，不得承載資訊**） |
| 圖表格線 | `--grid`（由 ink-2 淡化，與表面同源） |
| 漲/跌/警示 | up `#2EBD85` / down `#F6465D` / warn `#E0A020` |
| 衍生色 | `--up-bg` `--up-line` `--down-bg` `--down-line` `--warn-*` `--accent-*`（`color-mix` 從主色推導） |
| 實色底上的字 | `--on-up` `--on-down` `--on-warn` |
| 類別 6 色 | `#5B7CFA #0E9478 #CC7F1E #D64F94 #8461E8 #1E93CE` |
| 字體 | PingFang TC 系統字 + `ui-monospace` `tabular-nums`（數字對齊） |

### 為什麼是這組漲跌色（有實際去看過）

2026-07 實測三家交易所的線上色票：

| | MAX | OKX | Binance | 我們 |
|---|---|---|---|---|
| 背景 | 淺色 | `#000` | `#0B0E11` | `#0D0E14` |
| 主文字 | `#000` | `#FAFAFA` | `#EAECEF` | `#ECEDF1` |
| 漲 | `#49A870` | `#31BD65` | `#2EBD85` | **`#2EBD85`** |
| 跌 | 紅 | `#EB4B6D` | `#F6465D` | **`#F6465D`** |
| 數字字體 | Iosevka（mono） | 專用 sans | BinanceNova | mono ✓ |

暗色終端的跌色**普遍偏粉紅**，不是磚紅 —— 粉紅調在黑底上更跳，也不會跟橘色警示混淆。
順帶一提這組色也**比舊色更容易讀**：`#F6465D` 對 surface 是 5.06:1（舊的 `#E5544B` 只有 ~4.3，卡在 AA 邊緣）。

### 頂部行情列（別再讓它「亮代號、暗價格」）

OKX / Binance / MAX 的報價條都是**靜態**的，而且階層一致：**標籤壓暗、數值最亮**。
舊版剛好相反（代號 ink-2、價格吃到瀏覽器連結藍），還 55 秒無限捲動 —— 會動的數字本來就讀不了。
現在：價格 = `--ink` + mono + 700，代號 = `--ink-3` + 10.5px，漲跌 = 有底色的膠囊；捲動放慢到 180s，
且 hover / 分頁隱藏 / `prefers-reduced-motion` 都會停。

### ⚠️ `color-scheme: dark` 是必要的，不是裝飾

沒有它，瀏覽器會對 UA 樣式套用**淺色模式預設值**，於是：

- `<button>` → `color: buttontext` = **黑色** → 歡迎頁能力卡標題是黑字（對比 **1.26:1**）
- `<a>` → `color: -webkit-link` = **`#0000EE`** → 跑馬燈價格是連結藍（對比 **1.9:1**）

這就是「畫面有黑色文字」「價格看不清楚」的根因 —— 不是色票調得不好，是 UA 預設值漏進來。
已在 `:root` 加 `color-scheme: dark`，並補 `button, a, input, select, textarea { color: inherit; }` 當第二道防線。

**規則**：新卡片一律 `var(--...)`，**不要硬編顏色**；JS 要用色就 `C.xxx`（已從 CSS 變數讀進來）。
承載資訊的文字**不得低於 `--ink-3`**。改完跑一次對比稽核（見下），目前全站 **WCAG AA 0 失敗**。

```js
// 貼進 DevTools Console 就能跑：列出所有低於 AA 的文字
// （會把 alpha 疊合、往上追真正的背景色一起算，不是只比 color vs body）
// 完整腳本見 git log；重點是每次改色票都要重跑一次，別靠肉眼。
```

### ⚠️ CSS class 命名地雷（踩過兩次，別再踩）

單檔 inline CSS 沒有 scope，通用 class 名會跨元件互撞。已修但要記住：

- `.stat`（回測 KPI 磚）曾撞上 `.thinking .stat`（思考中狀態列）→ 狀態列莫名長出卡片外框。**KPI 磚現已改名 `.kpi`。**
- `.status`（頂欄連線狀態，`white-space: nowrap`）曾撞上 `.tl.status`（執行紀錄日誌行）→ 日誌長訊息不換行、被面板直接切掉。**頂欄現已限定 `.topbar .status`。**

新增通用名稱的 class 前，先 grep 一下。

---

## 5. 後端有哪些「資料形狀」可以視覺化

（你要畫什麼，取決於工具回傳什麼。欄位定義在 `skills/*/schemas.py` 與各技能的回傳 dict。）

- **即時行情/衍生品**：報價、K線、掛單簿深度、資金費率、未平倉、多空比、爆倉熱力圖、ETF 流向、財庫增持、板塊輪動、加密概念股。（多數已有 viz 卡）
- **五維分析台 `run_analyst_desk`**：宏觀/資金流/部位/情緒/技術五層 → {signal, strength, evidence[]} + 共振評級 + **背離警示** + 論點/失效價位。（有 `vizAnalystDesk`）
- **事件研究回測 `run_signal_backtest`**（15 訊號，含新的動能突破/RSI超賣/波動突增因子）：回傳 `events_tested / avg_abnormal_return_pct / win_rate_pct / t_stat / p_value / **permutation_p** / **abnormal_ci90_pct** / significant / verdict / **run_card**{run_id}`。
- **組合回測 `run_composite_backtest`**：多訊號 AND 共振 / OR 聯集，回傳同上 + `composite{mode, window_days, signals[], per_signal_event_counts[]}`。
- **分析沙盒 `run_analysis`**：agent 臨場寫 Python 算的結果，回傳 `{ok, result, stdout, skill_calls}`。
- **黃金/宏觀**：金價（PAXG/XAUT）、實質利率、DXY、與 BTC 相關係數。（有 `vizGoldPrice/vizMacro/vizGoldBrief`）
- **安全**：下單有硬編風控（單筆 50k TWD / 1.5k USD 上限、限價 ±3%），需人工核准。

---

## 6. 前端狀態（2026-07 視覺輪已完成）

**A. 補齊新功能的視覺 — ✅ 已完成**
1. ~~組合回測借用單一訊號卡~~ → 已有專屬 **`vizCompositeBacktest`**：AND/OR 模式徽章、**訊號漏斗**（各訊號事件數 → 共振後剩幾個）、共振後績效。漏斗是重點：AND 共振常把樣本從 34 砍到 9，報酬看起來變好其實只是樣本變小 —— 現在這件事在畫面上藏不住。
2. ~~回測嚴謹度沒被呈現~~ → `vizSignalBacktest` / `vizCompositeBacktest` 現在都顯示 **`permutation_p`**（排列檢定，列在統計註腳第一位）、**`abnormal_ci90_pct` 信賴區間橫條**（跨 0 會標紅字警告）、**`run_card.run_id`**（可重現標記）。
3. `vizAnalysis`（沙盒）已加 `max-height` + 捲動，不再無限撐長。（程式碼摺疊仍可再做）
4. ~~`DIM_OF` 回測維度過時~~ → 已納入 `run_signal_backtest` / `run_composite_backtest`，改讀 `permutation_p`，且**不顯著時標中性**（p=0.4 的正報酬不該被畫成看多）。

**B. 視覺 / 互動 — ✅ 本輪已修**
- **設計 token 統一**：JS 不再抄色票，改 `cssVar()` 讀 CSS `:root`（見 §4 警告）。
- **卡片滿版**：原本 `min(96%, 720px)` 在 ~1000px 欄寬下留了 300px 死空間 → 改 `100%`。單值型圖（儀表、3 根柱的長條）用 `panes[].maxWidth` 收窄置中，不強拉滿版。
- **卡片標頭三層**：eyebrow（分類）→ 標題 15px → 來源 pill，加底線分隔。
- **雙窗格**：加 `panes[].label` + 分隔線 —— 以前 AHR999 的「120K/110K/…/3.0/2.5」會被讀成同一條 Y 軸。
- **空值防護**：`_tile` / `_tiles` / `_tileText` / `_title` —— 不再出現「$—」「爆倉分佈 · 」這種空殼卡。
- **五維儀表**：加共振判讀列（幾多幾空），並 `insertAfter` 貼在答案正下方（以前被沖到所有圖表最後面，摘要放在證據後面等於沒有摘要）。
- **自動捲動**：改成只有貼底時才跟捲（`threadEl._pinned`），串流中可以往回看圖。
- **清除對話**：現在也會清掉 `.approval-card` / `.reader-alert`（以前會殘留）。
- **圖例**：`dist-legend` 的 🔴🟢 emoji → CSS 色點。
- **demo 覆蓋率**：8 種 → **21 種卡全覆蓋**（含分析師簡報／事件回測／組合回測／五維／黃金／情緒／訂單簿／熱力圖／沙盒）。且修好原本第一張就餵錯資料形狀、渲染成空殼的「爆倉概況」。

**仍可著力**
- 響應式：已加 860 / 560 斷點，但只做到「不爆版」，沒有真正的行動版設計。
- 沙盒卡的程式碼摺疊 / 語法高亮。
- 匯出：目前無法複製答案或存圖，pitch 場景可能會想要。

### `injectChartCard(spec)` API
```js
injectChartCard({
  title, tag,                      // 標題 / 右上來源 pill（title 會自動逸出，呼叫端別再 escapeHtml）
  eyebrow: "回測",                  // 分類標籤（預設「MAIA 自動製圖」）
  panes: [{ height, label?, maxWidth?, config, overlayHtml? }],   // label = 窗格標籤；maxWidth = 收窄置中
  html,                            // 自訂 DOM（接在 panes 之後）
  insertAfter,                     // 給「結論型」卡片用：插在指定節點之後而非附加到最後
});
```

> 建議工作法：一直開 `?demo=charts` 對著改；動到卡片就先在 demo 數據上確認版型，再接真模型驗證。

---

## 7. 檔案地圖（快速定位）

| 想改什麼 | 去哪 |
|---|---|
| 版型 / 卡片 / 顏色 / 動效 | `agent_ui/templates/index.html`（CSS 8–575、JS 694–2284） |
| 工具→卡片對應 | index.html `VIZ` 表（~1810）+ 各 `viz*()` 函式 |
| demo 數據 | index.html `?demo=charts` 區塊（~2225） |
| API / SSE / 核准 | `agent_ui/app.py` |
| 工具回傳欄位定義 | `skills/*/schemas.py`、`skills/analytics/event_study.py`（回測回傳 dict） |
| 後端能力全貌 | `README.md`（部分過時）、`SKILLS.md` |

---

## 8. 注意事項
- 別把設計往綠色帶（那是 MaiCoin，MAX 是藍）。
- 別動後端的風控/核准/沙盒隔離邏輯（那是安全牆，前端只呈現）。
- 改完跑一下 `python -m pytest -q`；已知有 4 個既有網路相關測試會失敗（`_real_` 網路題 + 2 個受測試順序污染的 coingecko mock），與前端無關。

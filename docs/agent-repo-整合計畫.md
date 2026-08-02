# max-ai-trading-agent → Hackathon_MaiCoin 整合計畫 v1

> 決策文件。看完可以拍板，隊友看完可以開工。
> 前提：`docs/前端框架規格.md`（1326 行）**已拍板，本文相容它、不推翻它**。本文只在三處明確標註「規格前提已變更」並提出修訂。
> 所有數字都是我實際下指令量到的，不是讀文件轉述。文件與程式碼衝突時一律以程式碼為準。
> 本文只新增這一個檔案，未修改 repo 任何其他檔案。
>
> **2026-08-02 狀態追記**：這是整併前的決策紀錄，不是未完成待辦。Bedrock 端到端呼叫、`ConverseStream`、18 項 provider 測試與 AgentCore Runtime AWS 部署都已完成；下文的相關項目已改標「已解」，工時與步驟僅保留為演進紀錄。

---

## 0. 三十秒摘要

| | 結論 |
|---|---|
| **值不值得整合** | 值得，而且是壓倒性的。實測估分 **61/110 → 89/110**（不含 Kiro）。最大增益在「AI 設計 15%」(+7) 與「技術可行性 20%」(+6)，因為 HITL 下單閘門、Reader 淨化層、審計雜湊鏈、四道實盤防線、AgentCore 部署入口**全部已經寫好且有測試**，不是待實作。 |
| **怎麼整合** | `git subtree merge` 掛進 `agent-core/`（保留 111 個 commit）；同批刪掉 `backend/` 與 `frontend/`，但先搶救 `backend/maia/` 的 4 個模組（約 344 行）。 |
| **體積** | 已追蹤檔 123 → 約 257 個、1.42 MB → 約 2.89 MB；但 `.git` 從 **39.28 MiB 縮到約 5 MB**（刪掉未合併的 `origin/eason` 42.4 MB 素材分支）。**程式碼變多、交付 repo 反而變小。** |
| **前端** | `frontend-pixel` 是唯一前端不變。106 個工具分四層落地：**3 個新 Zone + 5 個新 Panel + 1 個 HUD 核准疊層 + 約 55 個只走 agent 對話 + 約 12 個不接**。四個 append 點各加 3–6 行，六個凍結檔一行都不用動。 |
| **最大風險（現況）** | Bedrock 已有真串流與自動化測試，AgentCore Runtime `maia_agent` 已部署且為 `READY`。目前剩餘風險是 prompt caching、多實例核准狀態與尚未雲端化的審計/run-card 資料。 |
| **仍需團隊確認** | 見 §11。D1（Bedrock 驗證）已解；CSV 定位、公開部署的帳戶邊界、Secrets Manager 與賽制/commit 合規性仍屬團隊決策。 |

---

## 1. 這套系統到底有什麼 —— 從競賽與整合角度的資產負債表

### 1.1 一頁盤點（實測數字）

```
/Users/shihyayou/Developer/max-ai-trading-agent
├─ git:      111 commits · 20 天 · 單一作者 · 單一 main 分支 · 工作樹乾淨
├─ 追蹤:     172 檔 / 1.64 MB（pack 824 KiB）   ← 目錄 316 MB 的 97% 是 .venv，不會被帶走
├─ agent/    23 檔  · 主編排器 run_agent_turn（provider-agnostic ReAct，max_steps=8）
│            · LLM 三供應商抽象層（ollama / openrouter / bedrock，一個 env 切換）
│            · 三段式工具檢索（關鍵字意圖 → bge-m3 語意 → 信心自適應 top-k）
│            · Critic 子 agent · Reader 淨化層 · 分層記憶 · SHA256 審計鏈 · HITL 下單互鎖
├─ skills/   74 檔（72 個 skill + _http + __init__）· 9 個家族
│            → 對外 106 個 OpenAI 格式 tool schema / 108 個 callable
│            analytics 18 · max_exchange 22 · market_data 21 · market_intel 16(+社群 4)
│            derivatives 7 · calculators 5 · execution 4 · education 4 · gold 3 · memory 2
├─ agent_ui/ 9 檔 · FastAPI（不是 Flask）654 行 / 25 條路由 + 4776 行單頁 UI + PWA
├─ deploy/   AgentCore Runtime 入口（/invocations SSE + /ping）+ ARM64 Dockerfile
├─ mcp_*     兩個 MCP server：根目錄 42 工具 stdio 全家桶 · mcp_servers/ 10 工具 streamable-http
├─ tests/    44 檔 / 725 個 test（來源實測 717 passed / 4 failed / 31 秒）
├─ analyst_sandbox/  548 行唯讀 code-as-action 沙盒（無金鑰子行程 + AST 閘門）
└─ scripts/  skill_healthcheck.py（108 個工具一次全打，內建下單黑名單）
```

**全庫 `TODO|FIXME|XXX|HACK` 命中數 = 0。**

### 1.2 A 級資產 —— 直接換分，整合的主要理由

| 資產 | 位置 | 對應評分 | 為什麼是 A 級 |
|---|---|---|---|
| **HITL 下單互鎖** | `agent/trade_approval.py` + `skills/execution/live_guard.py` | AI 設計 15% + 主題 10% | 模型只能「提議」→ SHA256 凍結計畫（只雜湊意圖欄位，排除市價避免價格跳動 mismatch）→ 120 秒**單調時鐘** TTL（防 NTP 回撥）→ 執行前再驗雜湊 → 依凍結模式而非重讀 env → 四道防線再跑一次。多數參賽作品的 AI 下單就是一個直接呼叫。**後端 100% 完成，前端零實作。** |
| **實盤四道防線** | `skills/execution/live_guard.py:62-283` | 技術可行性 20% | Kill switch 刻意用檔案（「出事當下 touch 一個檔案任何人都做得到」）、`LIVE_UNTIL` 授權到期、24h 滾動曝險（20 萬 TWD / 20 筆）、被擋下的決策也寫台帳（「只記成功的等於只留下一半的故事」）。註解本身就是簡報素材。18 個測試把每道防線的繞過情境都覆蓋。 |
| **Reader 不可信內容淨化層** | `agent/reader_agent.py`（274 行） | AI 設計 15% | 破解零寬字 / 同形字 / leet / 拆字 / base64 / hex 六種混淆，且 base64 是「**解碼後**含注入關鍵字才判定」以免誤殺鏈上地址與 txid。同類作品罕見的深度。 |
| **Bedrock Converse 實作** | `agent/llm/bedrock.py`（264 行） | 硬約束「限用 AWS 基礎模型」 | 已實作 Converse + ConverseStream、tool 雙向翻譯、partial JSON 重組與 `answer_delta`。`tests/test_bedrock_provider.py` 共 18 項測試且全數通過。 |
| **AgentCore Runtime（已部署）** | `deploy/agentcore_app.py` + `Dockerfile.agentcore` | 技術可行性 20% | AWS runtime `maia_agent`（ID `maia_agent-4dRDgpAt4P`）已是 `READY`；`/invocations`(SSE) + `/ping`(Healthy/HealthyBusy) + ARM64 + 0.0.0.0:8080 四項合約齊備。 |
| **MAX Private API 深度** | `skills/max_exchange/max_private.py` | **+5% 加分項** | 13 個唯讀端點 + 下單撤單，自建 HMAC-SHA256 簽章（GET/POST/DELETE 共用）。最強證據是 `position_ledger.fetch_events()` 用 my_trades / converts / rewards / fund_transactions / accounts **五支端點做對帳** —— 這是「真的用了 Private API 而不是只查餘額」。 |
| **審計鏈** | `agent/audit_logger.py:35-57` | AI 設計 15% | 開場先讀檔取上一筆 `chain_hash`，是真的一條跨會話鏈而非每筆獨立雜湊。「每一個 AI 決策都可回溯且可驗證未被竄改」。 |
| **個人帳本三件組** | `position_ledger → lot_engine → shadow_account` | 商業 20% + 智慧分析 | FIFO/移動平均雙配對、成本來源分級（known/market/unknown/zero）、對帳 confidence、**樣本不足就不下結論**（`shadow_account.py:46-51`）。註解裡寫著「590 筆 MAX 獎勵一度把攤平樣本灌到 945 筆」——這是實際跑過真帳戶才寫得出來的。 |
| **event_study 事件研究引擎** | `skills/analytics/event_study.py` | 技術可行性 20% | Monte Carlo 排列檢定 + bootstrap 90% CI + 重疊窗叢集折疊 + `publish_lag` T+1 去前視 + 最小獨立樣本閘門 + run_card 結果雜湊。15 種訊號可 AND/OR 組合。統計嚴謹度遠超黑客松水準。 |
| **`_http.py` 限流表** | `skills/_http.py:37-55` | 技術可行性 20%（明文要求說明費用/用量） | 17 個主機的免費層限制寫成程式碼常數。**這張表可以原樣貼進簡報。** |
| **`?demo=charts` 離線示範** | `agent_ui/templates/index.html:4479-4696` | 現場保險 | 零網路、零金鑰、零模型，一個 query param 渲染 20 張卡。**比為 CSV 做 adapter 實用一個量級**（CSV 只能餵行為分析一塊面板）。 |
| **教育 + 計算器 8 工具** | `skills/education/` `skills/calculators/` | 主題 10% | 唯二 100% 離線、零外部依賴，且直接對準 MAX（手續費結構、台幣入出金、KYC、56 個名詞、3 大類防詐）。我實跑驗證過。 |

### 1.3 B 級資產 —— 要改造才用得上

| 項目 | 現況 | 要做什麼 |
|---|---|---|
| `agent_ui/app.py` 的 25 條路由 | 是**現成的 HTTP 契約**，frontend-pixel 的 `api/index.ts` 直接對接 | 加 CORS 或改同源、修 `logger` bug、加 `/api/models` 的 bedrock 分支、新增 `/api/markets` `/api/balances` 兩支聚合端點 |
| 21 種工具→圖表卡 | 其中 **15 個是 `panes:[]` 純 CSS 橫條**，不碰 Chart.js | 純 CSS 那 15 個直接移植邏輯；6 個 Chart.js 的**必須手刻**（規格附錄 B 規則 1 禁止新 runtime 相依，Chart.js 不論 CDN 或 npm 都不准） |
| `[圖表]` 錨點協議 | `index.html:2294` 的 30 行，模型決定圖表插在文字哪個位置，沒錨點就完全不改排版 | **創意度 25% 最有賣點的 30 行**，直接移植進 agentChat 面板 |
| 6 種投資大師人格 | 結構化 XML addendum（不是一句話 prompt）+ LLM 自動派發 | 天然對應 6 個可走近對話的 NPC。⚠️ 但**不可取代規格已拍板的 3 個「分析取向」**，見 §8.6 |
| Session 重播 | `conversation_log.py:139-207` 存完整 steps 含圖表資料 | **斷網下可還原整段對話含圖表**，已經寫好了。比 CSV fallback 實用 |
| `backend/maia/` 四個模組 | 見 §3.1 | 搶救約 344 行，其餘刪 |

### 1.4 負債 —— 會扣分、會在台上壞掉，或不能公開繳交

| # | 負債 | 證據 | 嚴重度 |
|---|---|---|---|
| L1 ✅ | **Bedrock 真串流** | `BedrockProvider.chat_stream()` 已接 `converse_stream`，主迴圈路會產生 `answer_delta` | 已解 |
| L2 ✅ | **Bedrock 測試與 SDK** | boto3 已安裝；18 項 Bedrock provider 專屬測試全數通過，且已實跑 AWS | 已解 |
| L3 | **沒有 `.dockerignore`，Dockerfile 是 `COPY . .`** | `ls .dockerignore` → No such file；`Dockerfile.agentcore:14` | **金鑰會進 image layer** |
| L4 | **`agent_ui/app.py` 的 `logger` NameError** | 檔案 8–19 行 import 清單無 `logging` 也無 `loguru`，卻在 `:428 :440 :451` 呼叫 `logger.warning` | 三個端點在「沒有 MAX 金鑰」時 500 而非優雅降級 ——**那正是評審機器的狀態** |
| L5 | **`.env.example` 的正式值仍需覆寫** | 已有 `LLM_PROVIDER` / `BEDROCK_*` / DynamoDB / Threads 範例，但 provider 預設仍是 Ollama，fallback 仍是 2024 model ID | 正式部署要明確設成 Bedrock 與可用 inference profile |
| L6 | **`/api/models` 沒有 bedrock 分支** | `app.py:115` 只判 `== "openrouter"`，否則打 Ollama（10 秒 timeout） | 評審螢幕上顯示 `gemma4:12b-mlx` 而不是 Claude |
| L7 | **核准 token 與 secret 都是行程內狀態** | `trade_approval.py:117` module 級 dict（作者自己在 `:15-16` 註明）；`app.py:56` import 時產生 | 多 worker/多實例 → 核准回 403 或「權杖不存在」 |
| L8 | **帳戶端點零認證** | `/api/dashboard` `/api/positions` `/api/account_activity` 直吐真實餘額與損益 | 硬性交付要求公開部署網址 = 公開帳戶 |
| L9 | **部分狀態仍在本機檔案** | 玩家/session、討論/留言、社群摘要已用 DynamoDB，報告/對話可用 S3；審計鏈、部分 agent memory 與 run card 仍本機化 | 未遷移的部分容器重啟後可能遺失 |
| L10 | **語意工具檢索硬綁本地 ollama** | `tool_embeddings.py:27-31` 打 `OLLAMA_HOST/api/embed` 抓 bge-m3；`:119-121` 失敗一次 `_index_failed=True` 永不重試 | 上雲**靜默**退化成純關鍵字，只有 `logger.debug` |
| L11 ✅ | **主要 README / 前端交接文件已對齊 Bedrock** | `FRONTEND_HANDOFF.md` 現已區分正式 Bedrock 與本機 Ollama，README 也已補 AWS 實際部署狀態 | 已解 |
| L12 | **CoinGlass AES-ECB 逆向解密死碼** | `skills/market_data/coinglass_scraper.py:23-99`（含硬編碼 webpack 金鑰表），生產路徑已全改走免費第一方來源，只剩測試在引用 | 逆向他人網站加密的程式碼隨「完整原始碼」繳交，有 ToS 與觀感風險 |
| L13 | **工具結果硬截斷 4000 字元** | `ollama_agent.py:296-297` | K 線 100 根 + 指標很容易超過，模型拿到壞掉的 JSON 尾巴；與 prompt 的 G12「至少取 50~100 根 K 線」直接衝突 |
| L14 | **每輪最多 3 次額外 LLM 呼叫 + 62 工具 schema + 無 prompt caching** | 實測「分析一下 BTC 該不該買」路由出 **62 個工具 ≈ 8,888 token**；`grep cachePoint` 在 bedrock.py 零命中 | 一題可能 12 次 Converse、數十秒 |
| L15 | **簡報口徑：repo 沒有用 Strands** | agent loop 是 `agent/ollama_agent.py:369` 的手工 while 迴圈 | `docs/架構與實作計畫.md` 六處寫 Strands 主線 = 不實陳述 |

### 1.5 不接 —— 離題或風險大於收益

`run_twitter_mention_backtest`（X syndication 常限流、只取 41 天）、`analyze_influence_decay`（HTTP Range 拉 8MB 鏡像逐字元解析）、CoinGlass v4 四支付費工具（無 key 必失敗，`tool_router.py:45-46` 已從預設意圖集移除）、`get_crypto_stocks`（美股概念股離題）、`get_aggregated_funding_rate`（`multi_exchange.py:89` **直接教使用者跨所套利**，對台灣合規現貨命題離題且有風險）、gold 家族 3 支（價值完全取決於「MAX 是否即將上線黃金交易對」這個未驗證宣稱，且 `macro.py:149` 把 `london_gold_pm_usd_oz` 硬寫 None → 代幣化溢價是**永遠回 None 的死功能**）。

---

## 2. Blocker —— 不解掉，後面都是裝飾

> 依「不解會怎樣」排序，不依難度。

### BLOCKER-1 · Bedrock 合規 —— ✅ 2026-08-02 已驗證

**這是整併時風險最高的一項，目前已解。**

| 面向 | 實測狀態 |
|---|---|
| 程式碼存在嗎 | ✅ `agent/llm/bedrock.py` 264 行，Converse + ConverseStream + 完整 tool 雙向翻譯 |
| 預設走哪個 | ❌ `factory.py:31` = `os.getenv("LLM_PROVIDER", "ollama")` → **預設 ollama** |
| 有測試嗎 | ✅ `tests/test_bedrock_provider.py` 18 項，包含文字串流、partial JSON tool args、異常處理與主迴圈路分支 |
| boto3 裝了嗎 | ✅ 專案 venv 已安裝，AWS Bedrock、DynamoDB、S3 也已實際連線 |
| 串流 | ✅ `BedrockProvider.chat_stream()` 使用 `converse_stream`，主迴圈路輸出 `answer_delta` |
| model id | ⚠️ `bedrock.py:19` = `us.anthropic.claude-3-5-sonnet-20241022-v2:0`（**2024 年的模型**） |
| region | `BEDROCK_REGION` → `AWS_REGION` → `us-west-2` |
| 結構化輸出 | ⚠️ `bedrock.py:132` 只是附加一句 system「只回 JSON」，**不是 constrained decoding**。依賴它的三處（`personas.classify_persona_llm`、traits 摘要、`social_analysis`）都有 try/except 不會炸，但會**靜默降級** |
| 容器/雲端 | ✅ `Dockerfile.agentcore` 已設 `LLM_PROVIDER=bedrock`；AWS runtime `maia_agent` 已部署且為 `READY` |

**整併時的必做項與現況：**

1. ✅ boto3 已安裝並在 `requirements.txt` 釘版本。
2. ✅ 最新 AWS 部署腳本以 `BEDROCK_MODEL=us.anthropic.claude-opus-4-5-20251101-v1:0` 覆寫 fallback。新帳號/區域仍應查實際 model access：
   ```bash
   aws bedrock list-inference-profiles --region <你們的 region>
   aws bedrock list-foundation-models --region <region> --by-provider anthropic
   ```
3. ✅ `.env.example` 已有 `LLM_PROVIDER` / `BEDROCK_*` / AWS / DynamoDB 等範例；但正式環境仍必須覆寫 Ollama 預設值。
4. ⚠️ `/api/models` 的 Bedrock 分支仍需根據前端是否實際使用模型清單來決定是否補上。
5. ✅ 已實跑 Bedrock 對話/摘要並部署 AgentCore ARM64 runtime。

> **多供應商抽象層是資產，不是要拿掉的東西。** 簡報應該正面講：「同一份 agent loop、三個推理後端：正式 demo 走 Bedrock（合規）、開發期走本地 Ollama（零成本、讓 725 個測試可以無限跑）、Bedrock 配額或區域異常時 30 秒切 OpenRouter 續命。金融場景的推理腦是單點故障，我們用 60 行 factory 把它變成可替換元件。」這正好答「技術可行性 20% 明文要求說明費用、權限、用量」。

### BLOCKER-2 · Bedrock 串流 —— ✅ 已解；大型 tool schema 成本仍在

實測「分析一下 BTC 該不該買」曾路由出 **62 個工具**（`analysis_full` meta 意圖）。現在 Bedrock 已有真串流，但 `bedrock.py` 仍沒有 `cachePoint`，大型 tool schema 的 token 成本與首 token 延遲仍需監測。

**三層修法（由零成本到高投報）：**

| 修法 | 工時 | 說明 |
|---|---|---|
| ① Demo 動線避開 `analysis_full` + `max_steps` 降到 5 | 0.5h | `ollama_agent.py:373`。零成本立即見效 |
| ② **前端狀態 + 後端心跳 + 雙看門狗** | 保留 | 真串流不代表工具呼叫期間不會空檔；這些仍是網路與長任務保底 |
| ③ `bedrock.py` 的 `converse_stream` + `chat_stream` | ✅ 已完成 | 主迴圈路透過 `hasattr` 自動走串流分支，並有專屬測試 |
| ④ Bedrock prompt caching | 2h | `tool_router` 刻意依 `ALL_TOOLS` 固定順序輸出以穩定 KV prefix ——前綴穩定、命中率會很高 |

串流缺口已解；下一個實際優化點是 prompt caching 與路由候選工具數，不是再做 paced reveal。

### BLOCKER-3 · CSV 的最終定位（硬約束已被推翻，但不是「完全不用」）

**先確認推翻：** `docs/競爭情報與策略.md:16` 寫「必須實際使用主辦提供的企業資料（= 這份 CSV）—— 沒用到是最大失分點之一」、`:23` 寫「必用 CSV」。**這兩句已被主辦方本人推翻**（優先使用 MAX API 真實資料更好）。這是全 repo 最危險的過時敘述 —— 照著它做會浪費半天。

**但「完全不用」也是錯的答案。** 我逐項評估兩個角度：

| 角度 | 判定 | 理由 |
|---|---|---|
| **(a) 斷網 fallback** | ❌ **不值得為此做** | ① CSV 只能餵行為分析**一塊**面板，而 `?demo=charts` 一次填滿 20 張卡；② `shadow_account._timing()` 會呼叫 `twd_price_at()` → `get_max_klines` **打網路**，斷網下這條就廢了；③ CSV **沒有手續費欄位** → `_cost_drag()` 會算出 fees=0 然後下結論「成本尚可控 0%」，這是**會誤導評審的假結論**；④ 真正的斷網保險是三層：`?demo=charts` + 預錄 session 重播 + 本機 Ollama 續命 |
| **(b) 沒有 Lv2 帳號的評審自己試用** | ✅ **這才是 CSV 站得住的理由，而且是真的** | 硬性交付要求「Dashboard Live Demo 部署網址」。評審點進去若所有帳戶面板都空的、或要求輸入 API key，體驗是零。而這**同時解掉 L8**（公網部署洩漏真實帳戶）—— 訪客模式就掛示範資料 |

**建議：改名定位為「訪客示範帳戶（Demo Account）」，不要叫 fallback。** UI 上誠實標註「示範資料」。這跟主辦說的「用 API 更好」不衝突 —— 那句話講的是**你們 demo 用什麼資料**，不是**評審試用時看到什麼**。

**這對規格 §12.1 的 demo 骨架的影響（重要）：** 規格第 ①② 段的「797 筆餘額不一致」「10,000 筆 CSV」敘事**不需要拿掉，而是升級**。`position_ledger.reconcile()` 對**真實 MAX 帳戶**做同一件事，並輸出 `confidence: high/partial/low` 與逐幣種差異成因診斷 —— 這比對合成 CSV 對帳強一個量級。敘事改成：「MAIA 連上你的 MAX 帳戶，第一步不是給建議，是對帳；它讀了成交、閃兌、獎勵、出入金五類事件重播出一本帳，跟交易所餘額比對，並告訴你哪幾個幣種對得上、哪幾個對不上、為什麼。」

**接 CSV 的真實成本（若決定做）：** adapter 本身 80–120 行，但有**三個非改不可的接縫**：
1. `analyze_trading_behavior()`（`shadow_account.py:226,242`）**沒有 events 參數**，要改成接受注入（+10 行）；
2. 預先塞 `lot_engine._px_cache[幣種] = {日epoch: CSV 價格}`（模組層 dict，`lot_engine.py:24`），否則會拿 MAX**現在**的日 K 當歷史成本，語意就錯了（+10 行）；
3. 手續費指標必須抑制或注入合成事件，不能留著那個 0% 假結論。
   → **實際約 2 小時，不是 30 分鐘。**

### BLOCKER-4 · CORS —— 目前一行 API 都呼叫不到

`agent_ui/app.py` 全檔沒有 `add_middleware`（grep 零命中）；`frontend-pixel/vite.config.ts` 也沒有 `server.proxy`。**Vite :5173 → FastAPI :8000 是跨源。**

而核准端點的整套 CSRF 防護（`app.py:54-64`，註解明寫「跨源 CSRF 頁面因同源政策讀不到此值」）**建立在同源假設上** —— 加 `allow_origins=["*"]` 等於親手拆掉它，而它正是要拿來講 AI 設計 15% 的東西。

**建議（雙軌，3 行 + 1 行）：**
- 開發期：`vite.config.ts` 加 `server: { proxy: { '/api': 'http://127.0.0.1:8000' } }`。**後端一行不動。**
- 部署期：FastAPI `app.mount("/", StaticFiles(directory="frontend-pixel/dist", html=True))` 維持同源。這也最貼近作者原設計。

### BLOCKER-5 · 金鑰衛生

**好消息（已驗證）：**
```bash
git -C max-ai-trading-agent log --all --full-history -- .env   # → 0 行
```
**`.env` 從未進過 git 歷史。** 原始碼硬編碼金鑰掃描（`api_key|secret|token|password|bearer` + `AKIA`/`sk-`/`ghp_` 特徵）也是 0 命中。**所以 subtree merge 在金鑰衛生上是安全的，不需要 `git filter-repo` 清史。**

**⚠️ 真正的危險在別處 —— 沒有 `.dockerignore`：**
```
ls .dockerignore                    → No such file or directory
deploy/Dockerfile.agentcore:14      → COPY . .
```
任何人在來源目錄 `docker build`，就會把 `.env`（真實 MAX / 交易所金鑰）烤進 image layer，連同 306 MB `.venv`、884 KB 含明文 `user_query` 的稽核紀錄、228 KB 作者個人記憶。**若那個 image 推上 ECR 或在台上被檢視，就是真實的安全事件。這是合併後第一個要修的檔案。**

三條紀律：
1. **`.env` 全程不讀、不印、不複製。** 需要了解設定項時讀 `.env.example`。
2. subtree 只會帶入 `git ls-files` 的 172 個檔 —— 這是它相對 `cp -r` 的決定性優勢（`cp -r` 會把上面那一整包搬進參賽 repo）。
3. 推公開 GitHub 前跑最後一道閘：
   ```bash
   git log --all -p | grep -nE "AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----" | head
   ```

### BLOCKER-6 · 三個一行級的必修 bug

| bug | 位置 | 修法 | 為什麼是 blocker |
|---|---|---|---|
| `logger` NameError | `agent_ui/app.py:428,440,451` | `from loguru import logger`（`agent/llm/factory.py:9` 已在用） | 觸發條件正是「沒有 MAX 金鑰」= 評審機器的狀態，會 500 而不是優雅降級 |
| `/api/models` 無 bedrock 分支 | `app.py:108-144` | 加一個分支回 Claude 清單 | 評審螢幕顯示 gemma4 = 自白沒用 AWS 模型 |
| 待核准訂單/密鑰是行程內狀態 | `trade_approval.py:117`、`app.py:56` | **Demo 鎖單一 worker / 單實例**，簡報標為 known limitation | 下單核准是最亮眼的橋段，不能在台上壞掉 |

---

## 3. 三組重疊的判決

> 使用者已授權「目標 repo 有不好的地方可以直接移除」。以下是**確認例外**，不是論證該不該取代。

### 3.1 `agent-core/skills/analytics/`（18 工具）vs `backend/maia/`（882 行）

**判決：analytics 留、`backend/maia` 刪 —— 但先搶救 4 個模組約 344 行。**

我逐檔比對過，這不是「新的比較好所以全換」，兩邊各有對方完全沒有的東西：

| 面向 | analytics | backend/maia | 勝 |
|---|---|---|---|
| 配對法 | FIFO + 移動平均雙軌 | 只有 FIFO | analytics |
| 成本來源 | 分級 known/market/unknown/zero，賣超部分進 `unmatched` 不硬湊 | 無 | analytics |
| 對帳 | `reconcile()` 比對交易所餘額 → `confidence: high/partial/low` + 差異成因診斷 | 只有筆數統計 | analytics |
| 樣本閘門 | `_verdict()` 樣本 < MIN_N 就 `conclusion=None` | 無 | analytics |
| 資料源 | MAX Private API（五支端點） | CSV | 各有用途 |
| **CSV 讀取 + data_health** | ❌ 唯一入口 `load_events()` 讀死路徑 JSONL，該檔目前**不存在** | ✅ `loader.py` 110 行 | **maia** |
| **淨值曲線（時間序列）** | ❌ `lot_engine` 只給某一時點快照 | ✅ `portfolio.py:218-224` `_record_equity()` + `report.py:24-32` 壓成每日 | **maia** |
| **0–100 六軸分數 + archetype** | ❌ 只有原始指標，沒有產品外殼 | ✅ `behavior.py:178-244`（活躍度/紀律/擇時/分散/持有耐心/風險控管 + 5 種標籤） | **maia** |
| **反事實 sell_vs_hold** | ❌ 兩個回測引擎都是**市場策略**回測 | ✅ `backtest.py` 對使用者自己交易紀錄的反事實比較 | **maia** |

那四樣正好是像素世界「交易 DNA 面板」要渲染的內容 —— 雷達圖、資產曲線、「高頻無 alpha 交易者」標籤。

**搬遷落點：**
```
backend/maia/loader.py               → agent-core/skills/analytics/csv_source.py      (110 行)
backend/maia/portfolio.py:218-224    → agent-core/skills/analytics/equity_curve.py    (~40 行)
backend/maia/behavior.py:178-244     → agent-core/skills/analytics/dna_score.py       (~70 行)
backend/maia/backtest.py             → agent-core/skills/analytics/counterfactual.py  (124 行)
```

**兩個必須帶過去的修正（否則搬過去就是搬 bug）：**
- `_compute_scores` 的係數是**針對合成隨機 CSV 調的**。接真實 MAX 帳本後分數分布會偏，archetype 可能全部落在同一格。**要重新校準門檻。** 順帶把規格 §B3 第 4 點的 logistic 修正（實跑值「活躍度 100.0 / 紀律 0.0」兩軸貼死）一起做掉。
- `sell_vs_hold` **必須帶著規格 §B3 的 `capital_feasible` 旗標一起搬**（實跑顯示它宣稱續抱多賺 26,937,347 TWD，但帳戶淨投入本金只有 24,274,547 TWD）。它是**次要指標不是頭條** —— 規格 §13 決策 1 已拍板，本文不推翻。

**其餘 15 個檔（`backend/agent/`、`backend/api/`、`backend/tools/`、`chat_cli.py`、`verify.py`、`analyze.py`）全刪。**

### 3.2 `agent/tool_router.py`（三段式檢索）vs `backend/tools/registry.py`（100 行）

**判決：registry.py 刪 —— 但抄走一個概念。**

✅ **確認多餘：**
- Bedrock toolSpec 直出這件事 `agent/llm/bedrock.py:_to_bedrock_tools` 已經做完，而且做得更完整（含 toolUse / toolResult 雙向翻譯、role 交替合併）。
- 舊 registry 沒有任何路由能力，11 個工具**全餵**。新架構是 106 個工具 → `select_tools()` 砍到 8~25 個（實測 9/15/24/62）。106 個工具不可能全餵 —— 舊 registry 的模式在新規模下直接不成立。

⚠️ **但有一個東西不能一起丟：`Tool.call()`（`registry.py:36-40`）自動補 `_source`。**

新架構 106 個工具的回傳格式**完全不統一**：`max_public` 失敗 `raise RuntimeError`、`ccxt_fetcher` 部分 raise 部分回 `{'error':...}`、`dex_screener` 一律回 `{'error':...}`、`market_overview` 每個欄位各自帶 error/pending。只有 4 個本地計算工具自帶 `source` 字串。

而 `frontend-pixel/src/hud/channels.ts:17` 的 `ToolStep = { name, source: SourceTag, detail, ok }` **強制每顆工具晶片都要掛來源** —— 規格 §7.1 明講這是「grounding 的實體憑證」，對應 AI 設計 15% + 創意 25%。

**做法：在 `ollama_agent.py:295` 的 `_execute_tool_call` 外層加一個約 15 行的 `_wrap_result()`**，統一補 `_source` / `_ok` / `_fetched_at`。這是概念搬遷不是程式碼搬遷。順帶把 L13（4000 字元截斷）處理掉：**餵回模型的那份截斷，送給前端 SSE 的 `tool_result` 送完整** —— 否則前端拿截斷後的壞 JSON 去畫圖卡，圖表直接壞掉。

### 3.3 `agent_ui/`（FastAPI + 4776 行單頁）vs `frontend-pixel/`

**判決：`frontend-pixel` 是唯一且最終的前端（使用者指示 4，不動搖）。但 `agent_ui/` 整包保留，只是換一個身分。**

先更正一個前提：**`agent_ui/app.py` 是 FastAPI 不是 Flask**（`:15-16` `from fastapi import ...`、`:32` `app = FastAPI(...)`、`:653` uvicorn）。這是好消息 —— SSE `StreamingResponse` 已經是原生的，前端整合不需要換框架。

| 部件 | 判決 | 理由 |
|---|---|---|
| `app.py`（654 行 / 25 條路由） | ✅ **保留，這是後端本體** | 它不是 legacy，它就是 frontend-pixel 的 `api/index.ts` 要 fetch 的那個後端。25 條路由是一份現成的 HTTP 契約 |
| `templates/index.html`（4776 行） | ✅ **保留當參考實作，不當前端** | 21 種圖表卡、五維儀表、分級免責、`?demo=charts` 都在裡面。移植時沒有它等於盲改 |
| `templates/analytics.html`（125 行） | ❌ 刪 | 配色是舊 navy+cyan，明顯沒跟上重設計，是孤島 |
| `static/_spec.html`（91 行） | ❌ 刪或移 docs/ | 沒有任何路由指向它 |
| `static/icons.js`（45 枚線性 SVG） | ❌ 不移植 | 與像素風衝突。`features/registry.ts:27` 明寫「全專案零圖檔，不要引入 svg」，用 `glyph` 兩個拉丁字元的 CSS 方塊 |
| PWA（sw.js / manifest） | ❌ 不移植 | 且 `sw.js:4` 把 Chart.js 的跨源 CDN URL 放進 `cache.addAll()` 的 SHELL 陣列（all-or-nothing）→ **PWA 離線能力實際上很可能從來沒生效過** |

**為什麼 `agent_ui/` 不改名成 `legacy-ui/`：** 啟動方式是 `uvicorn agent_ui.app:app`，`legacy-ui` 含連字號不是合法 Python 識別字，改名會炸 import。真要改只能 `legacy_ui`，收益不抵風險。**處置：保留原名，在 `agent-core/agent_ui/README.md` 放一段話說清楚定位，根 README 再重複一次。** 誠實標註兩個 UI 的分工反而顯示開發深度，比藏起來好。

### 3.4 三組小重疊

| 重疊 | 判決 |
|---|---|
| `mcp_server.py`（42 工具 stdio）vs `mcp_servers/max_mcp_server.py`（10 工具 + streamable-http） | **兩個都留，但 README 明確標主線是後者。** 後者對齊 AgentCore Runtime 的 MCP server 合約、與原生工具同名（方便 dogfood 覆蓋）、回原生 dict 讓 FastMCP 自動生 schema。前者有 `tests/test_mcp_server.py` 覆蓋（雖然它的 docstring 說 19 個、清單列 30 個、實際 42 個，三個數字都對不上——順手修） |
| `agent/personas.py` 6 個大師 vs `boot/stances.ts` 3 個分析取向 | **兩層並存，不合併。** 見 §8.6 |
| `agent/prompts.py`（新，XML 合約 + G1–G16）vs `backend/agent/prompts.py`（36 行） | 舊的刪 |

---

## 4. 最終目錄樹

```
Hackathon_MaiCoin/
├── README.md                 ← 重寫：專案本體介紹（評審點進 GitHub 的第一眼）
├── .gitignore                ← 合併版（來源的完整很多，補 15 項執行期產物）
├── .env.example              ← 根層總表：把 agent-core 的 32 個 key + 缺漏的 16 個一次補齊
├── (MaiCoin) 命題文件 ....pdf  ← 保留
│
├── agent-core/               ← ★ agent 大腦 + 106 個工具 + AgentCore 部署入口（subtree，170 檔 / 1.55 MB）
│   ├── .dockerignore         ← ★ 新增（來源沒有，且 Dockerfile 是 COPY . .）
│   ├── .gitignore            ← 隨 subtree 帶入，自動涵蓋巢狀執行期產物（見 §5 說明）
│   ├── .env.example          ← 保留（指示 6：設定機制必須完整）
│   ├── README.md             ← 新寫：agent 系統導覽 + 怎麼跑 + Bedrock 切換
│   ├── requirements.txt  pytest.ini
│   ├── agent/                主編排器 · 三供應商 LLM 抽象層 · 工具路由 · Critic/Reader · 記憶 · 審計 · 核准
│   ├── skills/               9 個家族 72 支 skill → 106 個 tool schema / 108 個 callable
│   ├── tests/                44 檔 / 725 個 test
│   ├── analyst_sandbox/      唯讀 code-as-action 沙盒（是原始碼不是產物，保留）
│   ├── mcp_servers/          MAX MCP Server（streamable-http，對齊 AgentCore 合約）★主線
│   ├── mcp_server.py         舊 stdio 全家桶（42 工具，給 Cursor/Claude Desktop 掛）
│   ├── scripts/              skill_healthcheck.py（上台前必跑）· contrast_audit.py · cdp.py
│   ├── deploy/               agentcore_app.py + Dockerfile.agentcore
│   ├── demo_fixtures/        ← ★ 新增：破例保留 2–3 張 run_card 當斷網重播素材
│   ├── agent_ui/             FastAPI 服務（25 條路由）+ 開發期內部終端（★不是產品前端）
│   │   └── README.md         ← ★ 新增：一段話說清楚定位
│   └── docs/                 SKILLS.md（程式化重生成 106 個）· FRONTEND_HANDOFF.md（先修 SSE 表）
│
├── frontend-pixel/           ← 唯一且最終的前端（Vite + React 19，本次整合完全不碰它的既有檔）
├── data_set/                 ← 主辦 CSV，定位改為「訪客示範帳戶」種子（565 KB）
└── docs/                     ← 5 份決策文件（見 §7）
```

**刪除：** `backend/`（19 檔 / 2042 行，搶救 4 模組後）、`frontend/`（20 檔舊 Next.js console）、`agent-core/binancedesign.md`、`agent-core/coinbasedesign.md`、`agent_ui/templates/analytics.html`、`static/_spec.html`。

**體積帳（實測算出來的）：**

| | 現在 | 整合後 | 變化 |
|---|---:|---:|---|
| 已追蹤檔案 | 123 | ≈ 257 | +134 |
| 已追蹤內容 | 1.42 MB | ≈ 2.89 MB | +1.47 MB |
| `.git` pack | **39.28 MiB** | **≈ 5 MB** | **−34 MB** |

最後一行是很好的簡報事實：**程式碼從 2,000 行純標準庫變成 27,000 行 + 106 個工具，交付 repo 的 `.git` 反而縮小 87%。**

---

## 5. 合併步驟

### 5.0 git 策略：subtree merge，保留 111 個 commit

| 選項 | 判定 | 一句話 |
|---|---|---|
| **(a) `git subtree add`（完整歷史）** | ✅ **採用** | 111 個 commit / 20 天 / 中文具體描述 / TODO 全庫為 0 = 真人開發的證據；體積成本只有 +824 KiB |
| (b) `--squash`（單一 commit） | ❌ | 27,000 行的巨型 commit 在評審眼中像程式碼傾倒，反傷完成度與可信度 |
| (c) submodule | ❌ | 點進去只看到一個 hash 指標。**直接違反「GitHub 連結含完整原始碼」的硬性交付** |
| (d) 兩 repo + API 串接 | ❌ | 要交兩個連結；現場多一個網路跳點 = 多一個當機點 |

**演進脈絡本身就是簡報素材：** 07-09 建 skills 骨架 → 07-11 爆量 34 個安全稽核 commit → **07-20 一天內補齊 BedrockProvider + AgentCore 入口 + MAX MCP Server** → 07-28 實盤四道防線 + Shadow Account。「技術可行性 20%」可以直接指著 git log 講。

> ⚠️ **唯一風險，需向主辦確認（見決策 D13）：** 這 111 個 commit 的日期全部是 2026-07-09 ~ 07-28，**早於決賽 8/1–8/2**。若賽制明文要求程式碼須於現場實作期間產出，可見的賽前歷史會變成扣分甚至失格的把柄。**先確認再推公開遠端** —— 一旦推上去就無法回收。備案是改用 `--squash` 重做（20 分鐘）。**不要用改 commit date 之類的手法規避，那是造假，風險遠大於收益。**

**一個技術副作用要知道：** subtree 的歷史 commit 內部路徑仍是 `agent/`、`skills/`（repo 根），重新掛載靠 merge commit 完成。所以 `git log agent-core/skills/xxx.py` 預設看不到合併前的歷史，要加 `--follow`。要根治得用 `git filter-repo --to-subdirectory-filter` 改寫來源（會改掉所有 hash，+30 分鐘）——**不建議，收益不值得**。

### 5.1 執行步驟（含驗證與回退）

> **現況：** 目標 repo 在 `frontend-framework` 分支，`frontend-pixel/src/{game/core.ts, game/index.ts, game/sprite.ts, ui/App.tsx}` **正在被另一個 agent 修改中**。以下全程用 `git worktree` 在獨立目錄操作，**完全不碰對方的工作樹**。

**Step 0 · 前置保險**（5 分鐘，風險低）
```bash
cd /Users/shihyayou/Developer/Hackathon_MaiCoin
git add "docs/前端框架規格.md" && git commit -m "docs: 納入前端框架規格（整合前先落地）"
git tag pre-agent-core-merge
git bundle create ~/maicoin-eason-archive.bundle origin/eason     # ★ 刪遠端分支前的唯一保險
git bundle verify ~/maicoin-eason-archive.bundle
```
> 驗證：bundle 約 39–42 MB 且 verify 通過。回退：`git reset --hard pre-agent-core-merge`

**Step 1 · 隔離工作區**（2 分鐘，風險低）
```bash
git worktree add /Users/shihyayou/Developer/maicoin-integrate \
    -b integrate-agent-core frontend-framework
cd /Users/shihyayou/Developer/maicoin-integrate
```
> 同一個 `.git`、不同 checkout，沒有檔案鎖競爭。從 `frontend-framework` 切是為了繼承已落地的接縫 PR。
> 回退：`git worktree remove ... --force && git branch -D integrate-agent-core`

**Step 2 · subtree merge**（5 分鐘，風險低）
```bash
git remote add agent-src /Users/shihyayou/Developer/max-ai-trading-agent
git fetch agent-src
git subtree add --prefix=agent-core agent-src/main
```
> 驗證（★ 第二行最關鍵）：
> ```bash
> git ls-files agent-core | wc -l          # 期望 172
> ls agent-core/.env                        # 期望 No such file or directory
> git log --all --full-history -- agent-core/.env   # 期望 0 行
> du -sh agent-core                         # 期望 ~1.7 MB
> ```
> 回退：`git reset --hard HEAD~2`（subtree add 產生 2 個 commit）

**為什麼路徑叫 `agent-core` 而不是直接叫 `backend`：** `--prefix` 要求目標路徑不存在。沿用 `backend/` 得先刪再加，會讓「取代」關係在歷史上變模糊。用新名字，然後在**下一個 commit** 明確 `git rm -r backend frontend` —— 取代關係在 git 歷史上一目了然，也貼合「Agent 為核心」的敘事。

**Step 3 · 衛生檔與清理**（20 分鐘，風險低）
```bash
git rm agent-core/binancedesign.md agent-core/coinbasedesign.md
git rm agent-core/agent_ui/templates/analytics.html agent-core/agent_ui/static/_spec.html
mkdir -p agent-core/docs && git mv agent-core/SKILLS.md agent-core/FRONTEND_HANDOFF.md agent-core/docs/
# ★ 新增 agent-core/.dockerignore（內容見下）
# ★ 根 .gitignore 補齊（清單見下）
sed -i '' 's/python:3.12-slim/python:3.13-slim/' agent-core/deploy/Dockerfile.agentcore
sed -i '' 's/^mcp$/mcp==1.28.1/' agent-core/requirements.txt
git commit -am "chore(agent-core): 補 .dockerignore、移除競品設計報告、對齊 Python 3.13"
```

`agent-core/.dockerignore`（**最高優先的單一檔案**）：
```
.env
*.env
.venv/
venv/
.git/
__pycache__/
*.pyc
.pytest_cache/
audit_logs/
agent_memory/
conversation_logs/
run_cards/
etf_flows_store.json
strategies.json
tests/
agent_ui/templates/index.html
.DS_Store
```
> 驗證：`docker build ... && docker run --rm <image> sh -c 'ls -la /app/.env /app/.venv'` 必須全部 `No such file`。

根 `.gitignore` 補（縱深防禦，萬一之後有人在 repo 根跑 agent）：
```
audit_logs/  conversation_logs/  agent_memory/  run_cards/
strategies.json  etf_flows_store.json  position_ledger.jsonl  order_ledger.jsonl
TRADING_HALTED  .pytest_cache/  .coverage  htmlcov/  *.env  *.log  logs/  *.egg-info/
```

**Step 4 · 搶救 4 模組並刪除舊 backend/frontend**（約 3 小時，風險中）
```bash
# 4.1 人工改寫（不是純複製，要對齊 agent-core 的事件格式，見 §3.1 的兩個修正）
# 4.2
git rm -r backend frontend
git commit -m "refactor: 以 agent-core 取代舊 backend；移除未維護的 Next.js console"
```
> 驗證：`cd agent-core && .venv/bin/python -m pytest -q | tail -5`；
> `grep -rn "backend\." --include="*.ts" --include="*.tsx" ../frontend-pixel/src` 應無殘留引用。

**Step 5 · 建環境並實跑**（約 4 小時，風險**高** —— 這是 BLOCKER-1 的落地）
```bash
cd agent-core
/opt/homebrew/bin/python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt && .venv/bin/pip install boto3
.venv/bin/python -m pytest -q | tail -5          # 來源基準：717 passed / 4 failed / 31s
# ✅ Bedrock 端到端驗證（現況已完成，此指令保留供新環境 smoke test）
LLM_PROVIDER=bedrock BEDROCK_MODEL=<實際可用的 inference profile> \
  .venv/bin/python -c "from agent.llm import get_provider; \
  print(get_provider('claude').chat([{'role':'user','content':'回一個字：好'}]).content)"
.venv/bin/python -m uvicorn deploy.agentcore_app:app --port 8080 &
curl -s localhost:8080/ping                       # 期望 {"status":"Healthy"}
.venv/bin/python scripts/skill_healthcheck.py --json /tmp/health.json
```

**Python 環境收斂：** 本機只有 3.9.6（系統）與 3.13.14（homebrew），**沒有 3.11/3.12**；Dockerfile 原本寫 `python:3.12-slim`。三方不一致必須收斂 → **統一 3.13**（唯一有 717 tests 通過紀錄的版本；反向降級做不到，機器上沒有 3.12）。刪掉 `backend/.venv`（3.9），只留 `agent-core/.venv`。

**Step 6 · 合回主線**（10 分鐘，風險低，★需協調）
```bash
cd /Users/shihyayou/Developer/Hackathon_MaiCoin
git status --porcelain            # 先確認另一個 agent 的 frontend-pixel 改動已 commit
git checkout frontend-framework
git merge --no-ff integrate-agent-core -m "feat: 併入 agent-core（agent + 106 skills + AgentCore 部署入口）"
```
> **衝突面分析：** 本次所有變更只碰 `agent-core/`（新增）、`backend/` `frontend/`（刪除）、`docs/`、根層三個檔 —— **完全不碰 `frontend-pixel/`**，所以合回去零衝突。唯一可能要手動合的是根 `.gitignore`。

---

## 6. 分支收斂到單一 `main`

### 起始狀態（實測）

| ref | 狀態 | 處置 |
|---|---|---|
| `master`（+ `origin/master`，預設分支） | 追蹤 100 檔 / 1.42 MB | → 改名 `main` |
| `frontend-framework`（僅本地） | 接縫 PR + 本次整合 | → 併入後刪 |
| `integrate-agent-core`（僅本地 worktree） | 本次整合 | → 併入後刪 |
| **`origin/eason`（僅遠端）** | **42.4 MB / 56 commits，`git merge-base --is-ancestor origin/eason master` → NO，從未併入** | → **bundle 封存後刪除遠端** |
| tag `backup-before-pixel-merge` | 舊錨點 | → 刪 |
| tag `pre-agent-core-merge` | 本次錨點 | → 全部驗完後刪 |
| 來源 repo `main` | 另一個 GitHub repo | 保持獨立不動（上游備份） |

**`eason` 是 `.git` 39.28 MiB 的元凶。** 內容是 `agent-atlas/art-source/` 的概念圖 PNG（單檔最大 5.05 MB），而 frontend-pixel 的設計原則是「全專案零圖檔、用 CSS 像素方塊」—— 這些是**設計來源不是 runtime 資產**，交付 repo 不需要。但那是 Eason 的美術產出，**不要直接刪掉沒備份**。

### 收斂步驟

```bash
# 6.1 全部併進 master                                             【風險低】
git checkout master
git merge --no-ff frontend-framework -m "feat: 併入前端框架重構與 agent-core 整合"
git push origin master

# 6.2 master → main                                               【風險低】
git branch -m master main
git push -u origin main

# 6.3 ★ 到 GitHub 網頁 Settings → General → Default branch 改成 main
#     ⚠️ 必須先做這步，否則下一步刪 origin/master 會被 GitHub 拒絕     【風險中：人工步驟最容易漏】

# 6.4 刪除舊遠端分支                                               【風險中高：不可逆】
git push origin --delete master
git push origin --delete eason          # 已於 Step 0 bundle 封存
git remote set-head origin -a

# 6.5 清本地                                                       【風險低】
git worktree remove /Users/shihyayou/Developer/maicoin-integrate
git branch -d frontend-framework integrate-agent-core
git tag -d backup-before-pixel-merge
git remote remove agent-src

# 6.6 ★ 回收空間                                                   【風險高：之後 eason 物件在本地真的消失】
git bundle verify ~/maicoin-eason-archive.bundle    # ← 執行下一行前務必先過這一行
git reflog expire --expire=now --all && git gc --prune=now --aggressive
git count-objects -vH | grep size-pack               # 期望 39.28 MiB → ~5 MB

# 6.7 最終驗證
git branch -a      # 期望只有 * main 與 remotes/origin/main
```

復原 eason：`git clone ~/maicoin-eason-archive.bundle recovered`。

---

## 7. 文件盤點

### 7.1 `Hackathon_MaiCoin/docs/` 現有四份

| 檔案 | 判決 | 被推翻的具體行號 |
|---|---|---|
| `README.md`（根，3.2 KB） | **重寫** | 整份是命題轉貼 + 資料集欄位表 + 評分標準，**沒有一個字在講我們做了什麼**。評審點進 GitHub 第一眼看到的就是它。改成：MAIA 是什麼、AWS 架構圖、目錄導覽（明確說 `frontend-pixel/` 是產品前端、`agent-core/agent_ui/` 是參考實作）、怎麼跑、部署說明。命題與評分表移到 `docs/` 附錄 |
| `docs/競爭情報與策略.md`（115 行） | **併入後刪除** | **`:16`「必須實際使用主辦提供的企業資料（=這份 CSV）—— 沒用到是最大失分點之一」與 `:23`「必用 CSV」已被主辦方本人推翻**（見 BLOCKER-3）。這是全 repo 最危險的過時敘述。`:15`「限用 AWS 基礎模型」仍成立，連同競品分析併進新的 `docs/競賽約束與資源.md` |
| `docs/架構與實作計畫.md`（233 行） | **重寫成 v3** | 三處被推翻：① `:15,:78,:84,:89,:140,:192` 反覆寫「**Strands Agents SDK on Bedrock 主線**」→ agent-core **完全沒用 Strands**，是 `ollama_agent.py:369` 的手工 while 迴圈，**寫進簡報就是不實陳述**；② `:49,:205` 工具註冊表列 5 個 `dna_*` + 5 個 `max_*` → 實際 106 個 schema / 108 個 callable；③ `:30` 五 agent supervisor 拓撲 → 實際是 1 個 orchestrator + Critic + Reader 兩個真子 agent。**倖存可用：** `:91-104` Converse 工具調用機制、成本分層、`:115-123` AWS 服務表、`:177-181` Kiro 計畫 |
| `docs/前端框架規格.md` | **已對齊現況** | §B1 已更新為 Bedrock `ConverseStream` 與 `answer_delta` 已完成；B2、B4 已解，B3 部分推翻。§3–§13 與兩個附錄仍是前端有效資產。 |
| `docs/提案簡報骨架.md`（164 行） | **保留，等 v3 落地後更新** | 骨架沒問題，內容跟著架構 v3 改 |

### 7.2 來源 repo 五份

| 檔案 | 判決 | 理由 |
|---|---|---|
| `README.md`（117 行） | **不搬原文，改寫成 `agent-core/README.md`** | `:9` 宣稱「六大技能模組」（實際 9 個家族）、`:60` 宣稱「135 個測試案例」（實際 44 檔 / 725 個 test，**低報到 1/5**）、`:45` 目錄樹印著 Windows 路徑。最致命的是**把大腦定位成本地 Ollama**。另外 `:14` 宣傳「反向工程 CoinGlass 網頁端 AES-128-ECB 解密」—— 那段已是死碼，**留在公開繳交的 repo 有 ToS 與觀感風險** |
| `SKILLS.md`（245 行） | **搬 `agent-core/docs/`，並程式化重生** | 沒有幽靈工具（列的 25 個都存在），問題是只覆蓋 **24%**。未文件化的正好是最能拿分的：`run_analyst_desk`、`run_signal_backtest`、`run_analysis` 沙盒、`analyze_trading_behavior`、`get_trading_guard_status`、整個 gold/education/calculators 家族。用 `agent.prompts.ALL_TOOLS` 自動生成完整版約 30 分鐘，「106 個工具都有文件」本身就是完成度訊號 |
| `FRONTEND_HANDOFF.md`（189 行） | **搬 `agent-core/docs/`，先修 SSE 表** | §4 設計語言（色票、WCAG、`color-scheme: dark` 陷阱）與 §6 `injectChartCard` 契約已逐項回程式碼驗證成立，是真資產。但**必須先修 `:34` 的 SSE 事件表** —— 它只列 6 種而實際有 **12 種**，且把 `approval_request` 寫成 `approval`。照它實作會拿不到串流、開不出核准卡。所有行號加註「07-13 快照，已過期」（它說 app.py 252 行 / index.html 2286 行，實際 654 / 4776） |
| `binancedesign.md`（301 行） | **刪除** | binance.com 官網設計系統的機器抽取報告（`:42` 明講由 dembrandt 頻率分析器產出），repo 內零程式碼引用。放在參賽 repo 讀起來像「照抄競品」，傷創意度 25%。只保留三條規則寫進自己的設計文件：**漲跌色只當文字色不當卡片底色、數字走 mono/tabular、Inter + JetBrains Mono 替代字體** |
| `coinbasedesign.md`（269 行） | **刪除** | 同上 |

### 7.3 目標文件清單（收斂後 8 份）

```
README.md                              ← 重寫
docs/
  ├── 前端框架規格.md                   ← 保留 + 三個補丁（§7.1）
  ├── agent-repo-整合計畫.md            ← 本文
  ├── 架構與實作計畫.md                 ← v3：拿掉 Strands、106 工具、真實三層 agent 拓撲
  ├── 提案簡報骨架.md                   ← 跟著 v3 更新
  └── 競賽約束與資源.md                 ← 新：競爭情報倖存部分 + _http.py 的費用/權限/用量表
agent-core/
  ├── README.md                        ← 新寫
  ├── agent_ui/README.md               ← 新寫：一段話說明是參考實作
  └── docs/{SKILLS.md, FRONTEND_HANDOFF.md}
```

---

## 8. 前端呈現設計：106 個工具 × 像素世界

> **本節嚴格相容 `docs/前端框架規格.md`。** 四個 append 點各加 3–6 行，**六個凍結檔（`main.tsx` / `index.html` / `App.tsx` / `uiStore.ts` / `game/index.ts` / `world/types.ts`）一行都不用動。**
> 現況已驗證：接縫 PR 已落地（`engine/` `hud/` `features/` `boot/` 都在），`ZONES = {lobby, discussion, maxinfo}`，`PANELS` 有 8 個。

### 8.1 分層原則

**判準只有一條：「這個能力需要一個常駐的、可以反覆回來看的空間嗎？」**

- **需要空間、且有實體隱喻** → Zone（房間）
- **需要常駐、但只是一塊內容** → Panel
- **需要一直看得到（不論在哪個房間）** → HUD block
- **一次性查詢、參數空間大、或只在特定問題下有意義** → 只走 agent 對話（但要出圖卡）
- **離題或會壞** → 不接

按這條判準，106 個工具落成：**3 個新 Zone + 5 個新 Panel + 2 個新 HUD 通道 + 1 個核准疊層 + 約 55 個只走對話 + 約 12 個不接**。

### 8.2 Zone 對應（append 點 1/4：`world/zones/index.ts`，+3 行）

規格 §6.2 定義中庭上排有 **4 個空門位**（y=150，x=208/336/624/752），新 zone **一律不填 `pinned`**，由 atrium 依 zone id 字母序自動配位。

| Zone | 狀態 | 內容 | 自動配位 |
|---|---|---|---|
| `lobby`（中庭） | 既有 | + **交割櫃檯**（規格 §6.2 已定座標 528,252，HITL 落點） | — |
| `discussion` | **既有，升級** | 房間與留言維持 mock（掛 `SourceChip="示範資料"`，規格 §13 決策 9 已拍板），但**三個互動點升級成真資料**：`agentReport` → `run_analyst_desk`（五層真分析）；NPC 台詞 → `fetch_reddit_sentiment` 真實貼文；新增「情緒背離看板」→ `analyze_sentiment_divergence`（菁英 vs 群眾） | pinned (272,250) |
| `maxinfo` | **既有，升級** | `maxNews`/`maxEvents` 維持 mock（MAX 官方公告本來就沒 API）；**`maxBot`（wx 580, wy 224）→ 升級成 `agentChat`，接真 SSE**；新增訂單簿終端與圖表牆互動點 | pinned (656,250) |
| **`dna`** | 新 | 交易 DNA 檔案室：六軸雷達 + 淨值曲線 + FIFO 艙位 + 對帳信心 + Shadow Account 四個行為偏誤 | slot 208 |
| **`guard`** | 新 | **風控室**：一支實體的緊急停止拉桿 + 曝險儀表 + 決策台帳 + 授權到期倒數 | slot 336 |
| **`whatif`** | 新 | 反事實推演室：`sell_vs_hold`（帶 `capital_feasible` 旗標）+ `run_signal_backtest` 15 種訊號 AND/OR 組合 | slot 624 |
| — | — | slot 752 保留 | — |

自動配位排序（字母序）：`dna` → 208、`guard` → 336、`whatif` → 624。三個 zone 都必須 `w ≤ 640 且 h ≤ 384`（規格 §6.3，`tests/zones.mjs` 會驗）。

**`guard`（風控室）是整份整合裡最值得做的一個房間。** 理由：它是唯一能把「AI 有煞車」這件抽象事做成**實體互動**的地方 —— 走過去、看到一支紅色拉桿、旁邊是 24h 曝險進度條與決策台帳。資料完全現成（`GET /api/trading_guard` ← `live_guard.ledger_summary()` 回 `{effective_mode, kill_switch, exposure, recent_decisions}`），不需要新後端。對「技術可行性 20%」與「AI 設計 15%」是一個評審會記住的畫面。

### 8.3 Panel 對應（append 點 2/4：`ui/panels/index.ts`，+5 行 / 1 個 rename）

現有 8 個：`ranking` `roomPicker` `agentReport` `thread` `maxNews` `maxEvents` `maxBot` `char`

| 動作 | Panel | 吃什麼 | 說明 |
|---|---|---|---|
| **rename** | `maxBot` → **`agentChat`** | `POST /api/chat` 全部 12 種 SSE 事件 | 規格 §11 已預期這個改名會弄壞 `rooms.mjs:25`（保留語意，串流完成後再數）。要同步改兩處**非凍結檔**：`features/registry.ts` 一行、`maxinfo` zone 的 interactable 一行 |
| **升級 Component** | `agentReport` | `run_analyst_desk` 五層（`layers[]` 各有 signal/strength/evidence、`confluence`、`divergences`、`thesis`、`invalidation`、`risk_note`） | **key 不動、registry 不動**。這個工具的輸出結構天生就是給面板用的，一層一格直接渲染 |
| **擴充分頁** | `char` | `/api/dashboard` + `/api/positions` + `/api/account_activity` | 沿用 `index.html:1820-1849` 的八分類：總覽 / 艙位 / 已實現 / 對帳 / 資金流 / 交易行為 / 風控 / 偏好。**既有 432 行的 Trade 現貨面板保留，只加核准卡** |
| **新增** | **`dna`** | `/api/behavior` + `/api/positions` + `equity_curve` + `dna_score` | 規格 §附錄A 已規劃 |
| **新增** | **`backtest`** | `counterfactual`（帶 `capital_feasible`）+ `run_signal_backtest` + `run_composite_backtest` | 規格 §附錄A 已規劃 |
| **新增** | **`guard`** | `/api/trading_guard` | 風控室的面板 |
| **新增** | **`dataSource`** | 對帳結果 + 帳本事件 + 訪客示範帳戶的 CSV 原始列 | 規格 W13「投報最高的 2 小時」 |
| **新增** | **`pro`** | ProConsole | 規格 §13 決策 7：硬性交付的部署網址填 `pro.html` |

**⚠️ 核准卡不是 Panel。** 這是一個容易做錯的設計決定：

規格 §3.1 的 z-index 契約說 `#ui-root .backdrop` 在 z=10 最上層，而開 Panel 會讓 `game/index.ts` 的 `frozen` 為 true、`setLabelsVisible(false)`。核准卡如果做成 Panel：① 世界被凍結、② backdrop 把 HUD 的 agent 狀態蓋掉 —— 但**核准當下最需要同時看到的就是 agent 剛才查了哪些工具**。

**正解：核准卡是 `#hud-root` 底下的一個非模態疊層 block**（跟 `AlertStack` 同層），配合 `uiStore.setInputCaptured(true)` 凍結遊戲輸入（規格已為此預留這個欄位，`tests/hud.mjs` 有對應斷言：「Tab 開 deck 後按住 KeyD 兩秒角色座標不變」）。這完全相容既有契約，而且畫面更好 —— 核准卡浮在世界上方，背後 agent 的工具晶片還在亮。

### 8.4 HUD 對應（append 點 3/4：`hud/channels.ts`，+2 行）

現有 5 個通道：`tickers` `portfolio` `agent` `alerts` `meta`

```ts
// 新增兩個
guard:    live<{ mode: 'paper'|'live'|'halted'; killSwitch: boolean;
                 exposurePct: number; ordersUsed: number } | null>(null),
approval: live<ApprovalPlan | null>(null),   // 驅動 §8.3 的核准疊層
```

**`guard` 通道讓「模擬盤 / 實盤」徽章常駐在 HUD**。這一格價值很高：評審全程看得到「現在是 paper」，而下單 demo 的說服力來自「它**知道**自己在哪個模式，而且模式是凍結在計畫裡的，不是執行時重讀環境變數」。

**`SourceTag` 不擴充。** 現有 5 個（`dna | market | max | news | local`）夠用，106 個工具靠規格附錄 A 已規劃的 `shared/sources.ts` 的 `TOOL_SOURCE` 映射表分派：

| SourceTag | 涵蓋家族 | 約略工具數 |
|---|---|---|
| `max` | max_exchange（22）+ execution（4） | 26 |
| `dna` | analytics 的個人帳本線 + 行為分析 | 10 |
| `market` | market_data（21）+ derivatives（7）+ gold（3）+ analytics 市場線 | 39 |
| `news` | market_intel（16）+ 社群（4） | 20 |
| `local` | calculators（5）+ education（4）+ memory（2） | 11 |

改 union 是安全的（撞名是編譯錯誤），但不改更相容 —— 規格規則 4 的命名空間表不用動。

### 8.5 SSE 12 事件 → 前端映射（這是整合的核心契約）

⚠️ 作者的 `FRONTEND_HANDOFF.md:34` 只列 6 種且 `approval` 名字是錯的。**以下是我從 `agent/ollama_agent.py` 實際 grep 出來的完整 12 種**：

| 事件 | 產生行號 | payload | 前端落點 |
|---|---|---|---|
| `status` | 403, 465, 610 | `{content, step, max_steps}` | `hud.agent.set({phase:'thinking', note, elapsed})` |
| `persona` | 421 | `{key, name, icon}` | agentChat 訊息頭 + 世界裡 NPC 換色 |
| `thinking` / `thought` | 491 / 495 | `{content}` | agentChat 的可摺疊「思考過程」 |
| `tool_call` | 509 | `{name, args}` | `hud.agent.steps` push（`ok: null`）+ **世界層：NPC 走到對應道具前**（純 canvas，不碰 DOM） |
| `tool_result` | 540, 544, 548 | `{name, result}` | 對應 step 的 `ok` 落定 + 觸發圖卡渲染 |
| `reader` | 553+ | `{name, injection_detected, flags, reader_used}` | **`injection_detected` 為 true 時在 HUD 閃一張「已攔截疑似指令注入」** —— 這是 AI 設計 15% 的免費得分點，目前完全沒有出口 |
| `approval_request` | 518-525 | `{name, token, plan, hash, summary}` | `hud.approval.set(plan)` → 開核准疊層 + `setInputCaptured(true)` |
| `answer_delta` | 主迴圈路串流分支 | `{content}` | 累積顯示；Ollama 與 Bedrock `ConverseStream` 路徑都會出現 |
| `answer_reset` | 501 | `{}` | **必須實作** —— 否則小模型「邊講邊呼叫工具」的前導文字會留在畫面上變成假答案 |
| `final_answer` | 628, 636 | `{content}` | 收尾 + `[圖表]` 錨點解析 + 五維儀表 + 分級免責 |
| `error` | 395, 449, 484 | `{content}` | 錯誤訊息帶「重試」，**已串出的字不清掉**（規格 §B1 第 3 條） |

**SSE 解析器約 20 行可以從 `index.html:2913-2930` 原封不動搬**（`getReader()` + `TextDecoder` + `split("\n\n")`），包成 `src/api/agent.ts` 的 `streamChat(body, onStep, signal)`。要重寫的是 `handleStep`（`index.html:2932-3049`，118 行直接操作 DOM）→ 改成 reducer + 一組 `hud.*.set()`。

**六條必須寫進實作規範的紀律：**

1. **SSE 只在使用者送出時開，絕不在面板 mount 時開。** `tests/lib/harness.mjs:113` 用 `waitUntil:'networkidle'` —— 一條掛著的 SSE 是 in-flight request，會讓 networkidle 永不觸發 → `page.goto` 撞 30s 逾時 → **132 項測試全部記成「套件中斷」**。
2. **`?fast=1` 完全不打 SSE**，改吐一組硬編 canned 事件（順便就是 demo 錄影腳本）。
3. **`AbortController` 綁面板卸載 + 場景切換**（`engine/zone.ts` 的 `ZoneRuntime.signal` 已經是這個形狀）。
4. **後端補心跳**：`app.py:567` 那個 generator 外層包一層，15 秒無事件就 `yield ": ping\n\n"`。Bedrock 路徑上一輪工具呼叫可能 20–40 秒無事件。
5. **`answer_delta` 累積走命令式 `ref.textContent`**（跟 `worldLabels.ts` 同一套紀律），一則訊息「收完」時才 `setState` 一次推進歷史陣列。
6. **`hud.agent` 的 `elapsed` 用 rAF 驅動，不用 `setInterval`**（`feeds.ts` 是全 app 唯一的 setInterval，規格 §7.3）。

### 8.6 人格：兩層並存，不合併（這一條容易做錯）

| 層 | 是什麼 | 為什麼不能互相取代 |
|---|---|---|
| **Boot 的 3 個「分析取向」**（`boot/stances.ts`：risk / discipline / opportunity） | 進場選角，只換色 | 規格 §2 與 §13 決策 2 **已拍板**：對做合規／信託／ISO 27001 的公司，「投資人格」在形式上接近受規範的**投資屬性／適合度評估**，商業 20% 的風險大於它能換到的創意分。而且前端**永遠只送 enum、不送 prompt 文字**（防注入） |
| **世界裡的 6 個大師 NPC**（`personas.py`：buffett / dalio / livermore / whale / beginner / default） | 走近某個 NPC 對話時，該次對話帶對應的 `persona` key | 這是**後端 agent 的分析視角**，不是對使用者的人格分類 —— 語意完全不同，沒有合規問題。而且 `personas.py` 是結構化 XML addendum 不是一句話 prompt，`run_analyst_desk` 的 persona 還會調整五層的權重 |

**映射：** `stance` → 影響前端的預設排序與強調（規格 §B2 第 3 點的「段落排序」語意）；`persona` → 走近 NPC 時才變，或 `auto` 讓 `classify_persona_llm` 決定。兩者互不干擾。

**⚠️ 規格 §B2 的狀態更新：** 「人格在預設路徑上是假的」這個 blocker **已被新後端解掉** —— `ollama_agent.py:404-421` 的 system prompt 是 per-call 組的、`personas.py` 有 6 段實質不同的 addendum。但 `backend/verify.py` 那條不變式（三種 stance 對同一問題輸出兩兩不同）**要跟著搬進 agent-core 的測試**，否則沒有機器守。

### 8.7 圖表策略（⚠️ 這裡有一條硬約束容易被忽略）

**規格附錄 B 規則 1：「零外部 CDN、零 CSS 框架、零新 runtime 相依」，且明講「不要引入 react-query / zustand」。**

→ **Chart.js 不論走 CDN 還是 npm 都不准。** `package.json` 的 dependencies 只有 `react` + `react-dom`，這是離線 live demo 的前提。

好消息是成本比想像低：`index.html` 的 21 個 `viz*` 卡裡有 **15 個是 `panes: []`** —— 純 CSS div 寬度百分比畫的橫條 / 分佈條 / 熱力列，**根本不碰 Chart.js**。

| 類別 | 數量 | 處置 |
|---|---|---|
| 純 CSS 橫條類（訂單簿、爆倉熱力、板塊、信賴區間、五層分析、多空比…） | 15 | **直接移植邏輯**，換像素風視覺 |
| 恐懼貪婪儀表 | 1 | 原本就是手刻 SVG path（`index.html:4390-4468`），**邏輯可抄**，改成像素階梯色帶 |
| 折線 / 柱狀 / 甜甜圈 / 泡泡 / scatter | 6 | **手刻 SVG**，用規格附錄 A 已規劃的 `ui/charts/{Radar,Donut,EquityCurve}.tsx` 再補 `Bars.tsx` `Line.tsx` 兩支 |

**`[圖表]` 錨點協議必須移植**（`index.html:2294-2338`，約 30 行）：
```js
const CHART_ANCHOR_RE = /\[圖表(?::\s*([A-Za-z0-9_]+))?\]/g;
```
模型在 markdown 裡寫 `[圖表]` 或 `[圖表:run_backtest]`，前端把答案依錨點切段、段間插入圖卡；**沒錨點就完全不改變排版**。這是真正的 generative UI（不是關鍵字掃描），降級路徑乾淨。在像素世界裡可以做成「NPC 在對話框中間掏出一張圖表卡」—— 這是全案對「創意度 25%」最有賣點的 30 行。

### 8.8 Deck（append 點 4/4：`features/registry.ts`，+6 筆）

現有 6 筆：`ranking` `rooms` `trade` `maxNews` `maxEvents` `maxBot`

新增（`place` 座標必須抄自對應 zone 的既有互動點，`tests` 會驗它落在某個 rect 內）：
```
dna       交易 DNA     analysis  violet  DN   panel:'dna'        place:{zone:'dna',    ...}
whatif    反事實推演   analysis  amber   WI   panel:'backtest'   place:{zone:'whatif', ...}
guard     風控室       system    max     GD   panel:'guard'      place:{zone:'guard',  ...}
source    資料與對帳   system    cyan    DS   panel:'dataSource'
pro       專業終端     system    max     PR   panel:'pro'
（既有 maxBot 改成 agent / agentChat）
```
`blocked?()` 的用法：`guard` 在後端 `/api/trading_guard` 回 error 時回字串「風控服務未連線」讓格子灰掉，比開一個空面板好。

### 8.9 不接清單（明說，避免隊友加料）

除了 §1.5 的 12 個工具之外，這些**明確不做**：

| 項目 | 理由 |
|---|---|
| `icons.js` 45 枚線性 SVG | 與像素風衝突，`registry.ts:27` 明寫零圖檔 |
| PWA / service worker | 且它的 SHELL 快取本來就沒生效過 |
| Dock 拖曳調寬 + localStorage | 像素世界用固定尺寸面板 |
| `analytics.html` / `_spec.html` | 孤島 |
| 12 間討論室換成 12 個市場 | 規格 §2 已否決（29 次序列 urlopen 最壞 348 秒），§13 決策 9 拍板保留 mock + `SourceChip` |
| 為 `cancel_all_orders` 做 UI 按鈕 | 保留後端閘門，但**不給按鈕** —— 它會清掉止損保護單 |

### 8.10 與規格的相容性檢查表

| 規格條款 | 本節是否相容 |
|---|---|
| 四個 append 點各一行 append | ✅ zones +3、panels +5(+1 rename)、channels +2、features +6 |
| 六個檔凍結 | ✅ 一行都不動 |
| `#hud-root` 走動 2 秒 childList/attributes = 0 | ✅ 所有跳動數值走 `LiveText`；核准卡是「開/關」不是每幀 |
| 新 zone ≤ 640×384、不填 `pinned` | ✅ 三個新 zone 都遵守 |
| 中庭只加不移 | ✅ 只用 4 個空門位 + 規格已定的交割櫃檯 (528,252) |
| 零新 runtime 相依 | ✅ 不引入 Chart.js，手刻 SVG |
| 中文走 DOM | ✅ |
| `?fast=1` 不打真後端 | ✅ 且不開 SSE |
| `?failApi=1` 故障注入在 fetch 之前 | ✅ `api/index.ts` 的 `settle()` 換成 `fetch()` 時保留 FLAGS 檢查 |
| 金鑰不進瀏覽器 | ✅ HMAC 在 `agent-core`，前端只拿 `approval_secret`（同源、一次性） |
| localStorage 用 `maia.v1.` | ✅ |
| **§B1 串流** | ✅ **仍然成立，證據段要換**（見 §7.1） |
| **§B2 人格** | ⚠️ **已被新後端解掉**，verify 不變式要搬進 agent-core |
| **§B3 反事實** | ✅ `capital_feasible` 旗標跟著 `sell_vs_hold` 一起搬，維持次要指標定位 |
| §B4 接縫 PR | ✅ 已落地 |
| §13 決策 6（架構圖） | ⚠️ **前提已變更**，見 D9 |

---

## 9. 工作包（工時 / 風險 / 分數對應）

> 不排時程。沿用規格的 W 編號，本次新增從 W25 起，避免與既有 backlog 撞號。

### 必修（不做就會在台上壞掉或直接失分）

| # | 工作包 | h | 風險 | 對應 |
|---|---|---:|---|---|
| W25 | subtree merge + `.dockerignore` + `.gitignore` + 清理兩份 design.md | 2 | 低 | 金鑰安全（**L3 是唯一的真安全事件風險**） |
| W26 | `logger` 修復 + `/api/models` bedrock 分支 + `.env.example` 補 16 個變數 | 1 | 低 | 完成度 10%（三個廉價失分點） |
| W27 | CORS（vite proxy + 部署同源） | 0.5 | 低 | **不做則一行 API 都呼叫不到** |
| W28 ✅ | **Bedrock 端到端驗證 + AgentCore AWS 部署** | 已完成 | — | 實際對話/摘要成功，runtime `maia_agent` 為 `READY` |
| W29 ✅ | `bedrock.py` 的 `converse_stream` + `chat_stream` | 已完成 | — | 18 項 provider 測試通過 |
| W30 | SSE 心跳 + paced reveal + 雙看門狗（規格 §B1 三條，證據段更新） | 3 | 低 | **W29 的保底，順序不能反** |
| W31 | `src/api/agent.ts`（streamChat + 12 事件型別 + `_wrap_result` 的 `_source`） | 3 | 中 | AI 設計 15% |
| W32 | 刪 backend/frontend + 搶救 4 模組（含係數重校準 + `capital_feasible`） | 6 | 中 | 商業 20% |

### 主要得分

| # | 工作包 | h | 風險 | 對應 |
|---|---|---:|---|---|
| W33 | `agentChat` 面板（含 `[圖表]` 錨點 + 五維儀表 + 分級免責） | 8 | 中 | 創意 25% + AI 設計 15% |
| W34 | **HITL 核准疊層**（HUD block + `setInputCaptured` + 五種回報狀態） | 6 | 中 | **AI 設計 15% + 主題 10%，分數密度最高的 6 小時** |
| W35 | HUD 資料泵落地（`feeds.ts` + 5 個 block + 新增 guard/approval 通道） | 6 | 中 | 商業 20% + AI 設計 15% |
| W36 | `/api/markets` + `/api/balances` 兩支聚合端點 + `types.ts` 擴充 | 3 | 低 | 商業 20%（`avgCost` 是 MAX API 給不出來的） |
| W37 | `guard` zone（風控室 + 實體拉桿） | 4 | 低 | 技術可行性 20%（**最有畫面的一個房間**） |
| W38 | `dna` zone + `dna` panel（六軸雷達 + 淨值曲線 + 行為偏誤） | 8 | 中 | 商業 20% + 智慧分析 |
| W39 | `char` 八分類擴充 + Trade 面板接真資料 | 5 | 低 | 商業 20% |
| W40 | `?demo=1` 離線示範模式移植（20 張卡） | 4 | 低 | **斷網保險** |
| W41 | 15 個純 CSS 圖卡移植 + 5 支手刻 SVG chart 元件 | 8 | 中 | 創意 25% |

### 加分 / 保險

| # | 工作包 | h | 風險 | 對應 |
|---|---|---:|---|---|
| W42 | 文件重寫（README + 架構 v3 + SKILLS 程式化重生 + FRONTEND_HANDOFF 修 SSE 表） | 4 | 低 | 完成度 10% |
| W43 | 分支收斂到 main + gc | 1 | **高**（不可逆） | 交付品質 |
| W44 | 訪客示範帳戶（CSV adapter，含三個接縫） | 3 | 中 | 評審可自行試用 + 解 L8 |
| W45 | Bedrock prompt caching（cachePoint） | 2 | 中 | 技術可行性 20%（費用） |
| W46 | 6 個大師 NPC + `whatif` zone | 6 | 低 | 創意 25% |
| W47 | 預先 bake `tool_embeddings.json` 進映像檔 | 1 | 低 | 解 L10（**零成本**：sha256 簽章機制已支援，工具描述不變就直接載快取） |
| W48 | 刪 CoinGlass 逆向死碼 + 對應測試 | 0.5 | 低 | 解 L12（並改寫成「主動移除逆向依賴」的加分敘事） |

**合計：必修 22.5h / 主要得分 52h / 加分保險 17.5h。**

---

## 10. 現場 Live Demo 檢查表

**要幾個服務：** 2 個行程（FastAPI 後端**必須單一 worker** + 前端；選配第 3 個 MCP server 用於展示雙節點架構）。

**要幾把金鑰：**

| 類別 | 項目 | 缺了會怎樣 |
|---|---|---|
| 必要 | AWS 憑證 + `BEDROCK_MODEL` + region 已開通 model access | 推理腦不動 |
| 加分必要 | `MAX_API_KEY` / `MAX_API_SECRET`（Lv2） | 失去 +5% 與所有帳戶面板 |
| **免費但要事前註冊（4 把）** | `SOSOVALUE`（ETF flow + 財庫 + 板塊 + 概念股共用一把；缺了 event_study 有 3 個訊號源掛掉）· `COINALYZE`（缺了 4 個訊號源掛掉）· `FRED` · `COINGECKO`（選填） | **現場註冊來不及，務必事前備妥** |
| 付費（可不要） | `COINGLASS` | 四支工具已從預設意圖集移除，不影響 |

**啟動時間（實測）：** agent module import 載入 72 個 skill = **0.59 秒**；uvicorn 到可服務 ~2 秒；首次 `/api/positions`（帳本冷同步 + 抓日 K）= **~4.6 秒**。

**開場前三件暖機：** ① 先跑一次 `reconcile_holdings(sync=True)` 建帳本（`conversation_logs/position_ledger.jsonl` 目前**不存在**，沒建帳本 `analyze_trading_behavior()` 會直接回「本地帳本是空的」）；② 先問一題暖 Bedrock 連線；③ 跑 `scripts/skill_healthcheck.py` 知道今天哪些外部 API 掛了。

**斷網時還剩什麼（我實跑驗證過前三項）：** education 4 工具 + calculators 5 工具（實跑 `calculate_pnl` 回「做多 1.0 顆，進 100.00 出 120.00，扣掉手續費 0.33 後淨賺 19.67（+19.67%）」）+ `calculate_indicators` + `run_backtest`（自帶 K 線）+ `export_strategy` + `pnl_card` SVG + VADER 情緒打分 + `etf_flows_store.json` 既有 53 筆 + 26 張 run_card。

**但注意：斷網時 Bedrock 也斷。** 真正的兩層保險是：① **本機 Ollama 續命**（`LLM_PROVIDER=ollama` 一個環境變數，對話 + 上面那批離線工具全部還能動 —— **這正是指示 6 要保留多供應商的實際價值，應該在簡報上主動講成設計而不是應急**）；② **session 重播**（`conversation_log.py:139-207` 存了完整 steps 含圖表資料，完全斷網下能還原整段對話）。

**⚠️ 目前的斷網保險其實不成立：** `index.html:16` 的 Chart.js 走 CDN，斷網時 `window.Chart` 是 undefined → `injectChartCard` 在 `new Chart(...)` 拋例外 → 被 catch 吞掉 → **卡片外框有、圖是空白**。移植到 frontend-pixel 時因為改成手刻 SVG，這個問題自然消失。

**原規劃建議現場維持 `RISK_MODE=paper`，但 2026-08-02 最新公開部署實際是 `RISK_MODE=live`、`MAIA_ACCOUNT_OWNERS=*`、`LIVE_UNTIL=2026-08-05`。** 這是刻意的 demo 取捨，不可再將 paper 寫成線上現況。

---

## 11. 需要團隊主導者拍板的決策

| # | 決策 | 選項 | **推薦** | 一句話理由 |
|---|---|---|---|---|
| **D1 ✅** | Bedrock 端到端與 ARM64 部署 | 已驗證 | **完成** | boto3、18 項 provider 測試、AWS 實跑與 AgentCore runtime `READY` 均已確認 |
| **D2** | `BEDROCK_MODEL` 用哪個 | (a) 照抄一個較新的 id (b) 用 `aws bedrock list-inference-profiles` 查帳號實際可用的最新 Claude (c) 維持 2024 年預設 | **(b)** | 模型可用性依帳號/region/是否申請 model access 而不同，猜錯就是現場 404；且 model id 上的 2024 年份評審看得到 |
| **D3** | 主辦 CSV 的定位 | (a) 做完整 adapter 當斷網 fallback (b) **重新定位成「訪客示範帳戶」** (c) 完全不用 | **(b)** | 斷網理由站不住（CSV 只餵一塊面板、`_timing()` 仍要打網路、無手續費欄位會產出「成本 0%」假結論）；但「評審沒 Lv2 帳號也要有東西看」是真的，且同時解掉公網部署洩漏真實帳戶 |
| **D4** | `backend/maia/` 留還是刪 | (a) 整包刪 (b) **搶救 4 模組約 344 行** (c) 整包留 | **(b)** | analytics 帳務嚴謹度完勝，但 CSV loader / 淨值曲線 / 六軸分數+archetype / 反事實回測**它一樣都沒有**，而那正是像素世界 DNA 面板要渲染的 |
| **D5** | git 策略 | (a) **subtree merge 保留 111 commits** (b) squash (c) submodule (d) 兩 repo | **(a)** | 111 個中文具體 commit + TODO 全庫為 0 是真人開發的證據；submodule 直接違反「完整原始碼」的硬性交付 |
| **D6** | 核准卡做成 Panel 還是 HUD 疊層 | (a) Panel (b) **HUD 非模態疊層 + `setInputCaptured`** | **(b)** | Panel 會 freeze 世界且 backdrop 蓋掉 HUD 的工具晶片，但核准當下最需要同時看到 agent 剛才查了什麼；規格已為此預留 `inputCaptured` |
| **D7** | 圖表用什麼畫 | (a) npm 引入 Chart.js (b) **手刻 SVG** | **(b)** | 規格附錄 B 規則 1「零新 runtime 相依」是離線 demo 的前提；且 21 個 viz 卡有 15 個本來就是純 CSS，成本比想像低 |
| **D8** | 6 個大師 vs 3 個分析取向 | (a) 前端擴成 6 個 (b) 後端映射 (c) **兩層並存** | **(c)** | 規格 §13 決策 2 已拍板「投資人格」有合規觀感風險；但 `personas.py` 是 agent 的分析視角不是對使用者的分類，做成 NPC 沒有這個問題 |
| **D9** | ⚠️ **架構圖修訂**（規格 §13 決策 6 的前提已變更） | (a) 維持「誠實版 + 虛線 Phase 2」 (b) **MCP / AgentCore 改實線、Strands 整條拿掉、Guardrails 維持虛線或補做** | **(b)** | 規格 `:1214`「已 grep 確認 backend 只有註解、零實作」對 agent-core **不再成立**（真的有 Converse 實作、實測 `/ping` 回 200、兩個 MCP server）；但**全 repo 沒有 Strands**，寫進簡報是不實陳述 |
| **D10** | 公網部署怎麼處理帳戶洩漏 | (a) 加認證 (b) **只掛訪客示範帳戶** (c) 維持現狀 | **(b)** | `/api/dashboard` 等三支零認證直吐真實餘額損益；(b) 同時解掉 D3 的評審試用問題，而且「我們區分了 demo 與真帳戶環境」主動講出來是「權限」段落的加分 |
| **D11** | Kiro +5% 要不要拿 | (a) 全隊改用 (b) **指定一人只用 Kiro 做文件與簡報** (c) 放棄 | **(b)** | 兩個 repo 都沒有 `.kiro/`（find 過，零命中），這是過程證據不是功能；兩天內要完成大整合同時全隊換 IDE 會拖垮主線，但 Kiro 的 spec-driven 產出正好可當整合計畫交付物 |
| **D12** | `eason` 分支怎麼處置 | (a) **bundle 封存後刪遠端** (b) 直接刪 (c) 併進 main (d) 不動 | **(a)** | 它是 `.git` 39.28 MiB 的元凶且從未併入 master（實測 `merge-base --is-ancestor` = NO），刪掉省的空間是整個 agent-core 的 40 倍；但那是 Eason 的美術產出，不備份就刪不妥 |
| **D13** | ⚠️ **賽前 commit 是否合規** | — | **推公開遠端前先向主辦確認** | 111 個 commit 全部早於 8/1；若賽制要求現場產出，可見歷史會變扣分把柄。一旦推上公開 GitHub 就無法回收。**不要用改 commit date 規避** |
| **D14** | MAX Lv2 帳號用誰的、金鑰放哪、權限開到哪 | — | **開賽前決定；權限最小化（只開唯讀 + 現貨交易，不開提幣）；金鑰進 Secrets Manager** | +5% 的前提，且「API Key 權限最小化」這一句寫進簡報就是「權限」段落的具體證據 |

---

## 附錄 · 一頁備忘（貼牆用）

**合併後第一個小時的四件事，順序不能換：**
1. 建 `agent-core/.dockerignore` —— 沒有它，任何一次 `docker build` 都會把真實金鑰烤進 image layer
2. `from loguru import logger` 補進 `agent_ui/app.py` —— 一行，解掉「評審機器上三個端點 500」
3. `vite.config.ts` 加 3 行 proxy —— 沒有它一行 API 都呼叫不到
4. ✅ boto3 + Bedrock 實跑 + AgentCore AWS 部署已完成；新環境仍用 `scripts/bedrock_check.py` 做 smoke test

**三句不能出現在簡報裡的話：**
- 「我們用 Strands Agents SDK」（repo 裡沒有）
- 「我們的大腦是本地 Ollama + gemma4」（舊版交接文件用語，現已更正）
- 「我們反向工程了 CoinGlass 的 AES-128-ECB 加密」（`README.md:14` 原文，那段已是死碼且有 ToS 風險 —— 改講「我們主動移除了對逆向抓取的依賴，改用可持續的免費第一方來源」）

**三個現場最容易炸又最難當場 debug 的：**
- MAX 私有 API 沒有伺服器時間校準（`max_private.py` 的 nonce 只用本機時鐘）→ **筆電睡眠喚醒後時鐘漂移會讓私有 API 整組 401，而錯誤訊息完全不指向時鐘**。前一晚開 NTP 同步，demo 腳本第一步放 `get_max_member_info()` 驗簽
- 任一 skill 的 import 錯誤會讓整個 agent 起不來（`ollama_agent.py:25-235` 在 module import 時載入全部 72 個 skill），失敗訊息是 `ImportError` 而不是「某個工具不可用」→ **用一台乾淨機器從 requirements.txt 裝一次驗證**
- 多 worker / 多實例會讓核准 token 找不到 → **`uvicorn --workers 1`，鎖單一實例**

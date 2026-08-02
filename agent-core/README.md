# agent-core — MAIA 的大腦與工具層

> 這個目錄原本是獨立 repo `max-ai-trading-agent`,2026-07-30 以 subtree 併入 `Hackathon_MaiCoin`,完整保留 111 個 commit。
>
> **產品前端是 `../frontend-pixel/`(像素風可走動 2D 世界)。這裡的 `agent_ui/` 是開發期的參考實作,不是產品。**

---

## 一分鐘理解

```
使用者問一句話
  → tool_router 從 110 個工具裡挑 8–25 個候選(關鍵字 → embedding → 信心自適應)
  → LLM(Bedrock Claude)決定要呼叫哪些
  → 逐一執行,不可信來源先過 Reader 淨化
  → 要下單?只能提議,凍結成 SHA256 計畫等使用者核准
  → 產生答案,Critic 複審
  → 全程寫進 SHA256 審計鏈
```

主迴圈在 `agent/ollama_agent.py` 的 `run_agent_turn()` —— **手寫 ReAct 迴圈,上限 8 步**,provider-agnostic。

⚠️ 檔名叫 `ollama_agent.py` 是歷史遺留(最早只支援 Ollama),現在它與供應商無關。

---

## 目錄

| 路徑 | 內容 |
|---|---|
| `agent/` | 編排層:主迴圈、三供應商 LLM 抽象、工具檢索、Reader、Critic、記憶、審計、下單互鎖 |
| `agent/llm/` | `base.py` 介面 + `bedrock.py` / `ollama.py` / `openrouter.py` + `factory.py` |
| `skills/` | **9 個家族 72 支 skill → 對外 110 個 tool schema** |
| `deploy/` | Amazon Bedrock AgentCore Runtime 入口 + ARM64 Dockerfile |
| `mcp_servers/` | MAX MCP Server(streamable-http,對齊 AgentCore 合約)**★ 主線** |
| `mcp_server.py` | 舊的 stdio 全家桶(42 工具),給 Cursor / Claude Desktop 掛 |
| `agent_ui/` | FastAPI 服務(25 條路由)+ 開發期內部終端 —— **不是產品前端**,見 `agent_ui/README.md` |
| `analyst_sandbox/` | 唯讀 code-as-action 沙盒(無金鑰子行程 + AST 閘門) |
| `scripts/` | `skill_healthcheck.py`(110 個工具一次全打,內建下單黑名單)· `contrast_audit.py` · `bedrock_check.py`(Bedrock 端到端連線檢查)· `aws_creds_import.sh` / `.ps1`(臨時憑證匯入) |
| `tests/` | 44 檔 pytest |
| `docs/` | `ONBOARDING_AWS.md` AWS 打通指南 · `SKILLS.md` 工具清單 · `FRONTEND_HANDOFF.md` 前端接手文件 |

### 9 個 skill 家族

| 家族 | 內容 | 離線可跑 |
|---|---|:---:|
| `max_exchange` | MAX 公開行情 + 13 個私有端點 + 下單撤單,自建 HMAC-SHA256 | |
| `market_data` | ccxt 多所行情、DexScreener、鏈上、熱力圖、AHR999、山寨季 | |
| `analytics` | 個人帳本三件組、event_study、回測、指標、交易 DNA、反事實 | 部分 ✅ |
| `market_intel` | 新聞 RSS、輿論情緒(VADER)、恐懼貪婪、ETF flow | 部分 |
| `derivatives` | 資金費率、OI、爆倉、多空比 | |
| `calculators` | 手續費、部位、風報比 | ✅ |
| `execution` | 下單執行 + live_guard 四道防線 | |
| `education` | 名詞、KYC、防詐、MAX 手續費結構 | ✅ |
| `gold` | 黃金總經 | |

---

## 怎麼跑

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m pytest -q
uvicorn agent_ui.app:app --workers 1 --port 8000
```

⚠️ **`--workers 1` 不是可選的。** `agent/trade_approval.py` 的核准 token 是行程內狀態,多 worker 會讓核准回「權杖不存在」。

### 切換 LLM 供應商

```bash
LLM_PROVIDER=bedrock      # 正式 demo 與部署(命題限用 AWS 提供之基礎模型)
LLM_PROVIDER=ollama       # 本機開發,零成本
LLM_PROVIDER=openrouter   # Bedrock 額度或服務異常時的續命路徑
```

三者共用 `agent/llm/base.py` 的 `LLMProvider` 介面,主迴圈零改動。`deploy/Dockerfile.agentcore` 已寫死 `LLM_PROVIDER=bedrock`。

**保留三個供應商是刻意的** —— 那是開發環境與擴充介面,不是為了規避「限用 AWS 模型」。正式路徑走 Bedrock。

第一次接 Bedrock(匯入黑客松臨時憑證、驗證、找出帳號實際可用的 model id)照 [`docs/ONBOARDING_AWS.md`](./docs/ONBOARDING_AWS.md) 走,約 5 分鐘。同一份文件也涵蓋 S3 報告匯出的設定。

### 金鑰

不設任何私有 key 時,約 **80% 的公開技能仍可運作**。需要的金鑰與各家免費層限制見 `../docs/競賽約束與資源.md` §五。

⚠️ `.env` 被 `.gitignore` 與 `.dockerignore` 雙重擋住。`Dockerfile.agentcore` 是 `COPY . .`,**沒有 `.dockerignore` 就會把金鑰烤進 image layer**。

### AgentCore Runtime

```bash
docker buildx build --platform linux/arm64 \
  -f deploy/Dockerfile.agentcore -t maia-agentcore .
```

服務合約四項齊備:`/invocations`(SSE)、`/ping`(Healthy / HealthyBusy)、ARM64、`0.0.0.0:8080`。

**2026-08-02 實際狀態**:AWS 上的 AgentCore Runtime `maia_agent`（ID `maia_agent-4dRDgpAt4P`）已是 `READY`。正式路徑使用 Bedrock Claude，`BedrockProvider.chat_stream()` 已以 `ConverseStream` 對主迴圈路輸出 `answer_delta`。`tests/test_bedrock_provider.py` 有 18 項專屬測試且全數通過。

### 接進 IDE(MCP)

`mcp_server.py` 是 stdio 封裝(42 工具),可掛進 Cursor / Claude Desktop:

```
Name:    CryptoTradingSkills
Type:    command
Command: /path/to/agent-core/.venv/bin/python /path/to/agent-core/mcp_server.py
```

生產路線請用 `mcp_servers/max_mcp_server.py`(streamable-http,對齊 AgentCore Runtime 的 MCP server 合約)。

---

## 幾個值得知道的設計

**Kill switch 刻意用檔案。** `skills/execution/live_guard.py` 的原始註解:「出事當下 touch 一個檔案任何人都做得到」。同一支檔案還有另外三道防線:授權到期、24h 滾動曝險上限(20 萬 TWD / 20 筆)、決策台帳 —— **被擋下的決策也寫**,因為「只記成功的等於只留下一半的故事」。

**Reader 的 base64 判定在解碼之後。** `agent/reader_agent.py` 破解零寬字 / 同形字 / leet / 拆字 / base64 / hex 六種混淆,但 base64 是**解碼後**含注入關鍵字才判定 —— 否則會誤殺鏈上地址與 txid。

**審計鏈是真的一條鏈。** `agent/audit_logger.py:35-57` 開場先讀檔取上一筆 `chain_hash`,跨會話串起來,不是每筆獨立雜湊。

**下單計畫的雜湊排除市價。** `agent/trade_approval.py` 只雜湊意圖欄位 —— 把市價一起雜湊,使用者按下確認的瞬間價格跳動就會 mismatch。

**110 個工具不可能全餵。** `agent/tool_router.py` 三段式:關鍵字比對意圖 → 沒命中走 embedding 語意檢索 → 依信心自適應決定候選數。實測同一個問題會路由出 9 到 62 個工具不等,決策寫進 `routing_log.jsonl`。

---

## 已知缺口

| # | 缺口 | 影響 |
|---|---|---|
| 1 | 無 prompt caching(`grep cachePoint` 零命中) | 成本與延遲 |
| 2 | `tool_embeddings.py` 綁本地 ollama 的 bge-m3,失敗一次後 `_index_failed` 永不重試 | 上雲**靜默**退化成純關鍵字路由 |
| 3 | 核准 token 是行程內 dict | 多 worker / 多實例會 403 |
| 4 | 持久化尚未全面 AWS 化：玩家/session、討論區/留言、社群摘要已用 DynamoDB，報告與對話可用 S3；`agent_memory/` 其餘記憶、`audit_logs/` 與 `run_cards/` 仍有本機檔案 | 尚未遷移的資料在容器重啟後可能遺失 |
| 5 | 部分交易帳戶端點的授權邊界仍需在公開部署前複核 | 若將真實 MAX 帳戶掛在公開網址，可能洩露餘額與損益 |
| 6 | 工具結果硬截斷 4000 字元(`ollama_agent.py`) | 與 prompt 要求「至少 50~100 根 K 線」衝突 |
| 7 | `.env.example` 雖已有 Bedrock 與 DynamoDB 變數，但預設仍是 Ollama，且 fallback model ID 仍是 2024 Claude 3.5 | 正式部署必須覆寫 `LLM_PROVIDER` 與 `BEDROCK_MODEL` |
| 8 | `TOOL_CALLABLES` 與 tool schema 的完整對應仍需定期用測試驗證 | 未對應的工具無法由模型呼叫 |
| 9 | `skills/market_data/coinglass_scraper.py` 仍保留 AES-ECB 逆向解密舊碼 | 公開繳交有 ToS 與觀感風險 |
| 10 | `max_private.py` 的 nonce 仍需依賴本機時鐘正確 | 時鐘漂移可能使私有 API 回 401 |

處理優先序見 `../docs/agent-repo-整合計畫.md` §9。

---

## 技能手冊

工具清單與自然語言呼叫範例見 [`docs/SKILLS.md`](./docs/SKILLS.md)。
⚠️ 該文件只覆蓋約 24% 的工具,未文件化的正好包含最能拿分的幾支(`run_analyst_desk`、`run_signal_backtest`、`analyze_trading_behavior`、`get_trading_guard_status`)。用 `agent.prompts.ALL_TOOLS` 程式化重生成完整版是待辦事項。

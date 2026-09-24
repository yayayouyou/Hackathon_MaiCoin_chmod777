# MAIA — 走進去問，而不是盯著看

> 2026 雲湧智生：臺灣生成式 AI 應用黑客松 · MaiCoin 命題「打造現代 AI 投資工具」

傳統投資工具停在「單向的數據圖表」。命題原文說得很直接:**鼓勵參賽者跳脫傳統靜態網頁的框架**。

所以 MAIA 不是一個 Dashboard。它是一個**可以走進去的地方** —— 一個像素風的 2D 世界,你走到哪個區域,就等於在問哪一類問題、用哪一個資料源。世界裡有一位助理 agent:你問它任何事,它會自己決定要查什麼工具、把查到的東西拼起來回答你,需要下單時它**只能提議,不能執行** —— 得你走到交割櫃檯按下確認才算數。

```
走進「交易 DNA 檔案室」 → 你的六軸行為指紋 · 淨值曲線 · FIFO 艙位 · 對帳信心
走進「MAX 情報室」      → 即時行情 · K 線 · 訂單簿 · 跟 agent 對話
走進「風控室」          → 一支實體的緊急停止拉桿 · 24h 曝險儀表 · 決策台帳
走進「反事實推演室」    → 如果當初不這樣做會怎樣
```

---

## 這個 repo 有什麼

```
.
├── frontend-pixel/    像素風可走動 2D 世界 —— 唯一且最終的前端
│                      Vite + React 19 · 原生 Canvas 60fps · 156 項 playwright e2e
│                      零外部 runtime 相依(dependencies 只有 react + react-dom)
│
├── agent-core/        agent 大腦 + 106+ 個工具
│   ├── agent/         手寫 ReAct 迴圈(≤8 步)· 三供應商 LLM 抽象層
│   │                  三段式工具檢索 · Reader 淨化 · Critic 複審
│   │                  HITL 下單互鎖 · SHA256 審計鏈 · 分層記憶
│   ├── skills/        9 個家族 72 支 skill
│   │                  max_exchange · execution · market_data · market_intel
│   │                  analytics · derivatives · calculators · education · gold
│   ├── deploy/        Amazon Bedrock AgentCore Runtime 部署入口(ARM64)
│   ├── mcp_servers/   MAX MCP Server(streamable-http,對齊 AgentCore 合約)
│   ├── agent_ui/      FastAPI 服務(25 條路由)+ 開發期內部終端
│   │                  ⚠️ 不是產品前端,是參考實作
│   └── tests/         44 檔 pytest
│
├── data_set/          主辦提供的一年份交易紀錄 CSV(訪客示範帳戶的種子)
└── docs/              決策文件(見下)
```

---

## 三個支柱,對應命題的三個建議延伸

### 1 · 多維度互動式介面 → 像素世界

不是 Dashboard,是一個有空間感的地方。但**該有的儀表一項不少**:常駐 HUD 有即時行情條、持倉市值與未實現損益、agent 狀態與工具晶片、資料來源徽章。按 `Tab` 開快捷格、按 `/` 開命令面板,3 秒到任一功能 —— 走路探索是體驗,選單是給趕時間的人。

### 2 · 智慧 AI 數據分析 → 106+ 個工具與三段式檢索

106 個工具塞不進一次 prompt。`tool_router` 先用關鍵字比對意圖,沒命中就走 embedding 語意檢索,再依信心自適應決定候選數 —— 實測同一個問題會路由出 9 到 62 個工具不等。

分析的深度不在工具數量,在**帳務嚴謹度**:

- FIFO / 移動平均雙軌配對,成本來源分級(known / market / unknown / zero),賣超進 `unmatched` **不硬湊**
- `reconcile()` 比對交易所餘額 → `confidence: high / partial / low` + 差異成因診斷
- 樣本不足就**不下結論**

### 3 · 對話式下單生態 → 模型只能提議

```
模型提議下單
  → SHA256 凍結計畫(只雜湊意圖欄位,排除市價以免價格跳動造成 mismatch)
  → 120 秒單調時鐘 TTL(防 NTP 回撥)
  → 使用者在世界裡按下確認
  → 執行前再驗一次雜湊
  → 依「凍結在計畫裡的模式」而非重讀環境變數
  → 四道實盤防線再跑一次
```

**四道防線**:kill switch(刻意用檔案 —— 出事當下 touch 一個檔案任何人都做得到)、授權到期、24h 滾動曝險上限、決策台帳(**被擋下的決策也寫**,只記成功的等於只留下一半的故事)。

---

## 怎麼跑

**開兩個終端機,一個後端一個前端。** 前端不需要設定任何後端網址 ——
`vite.config.ts` 已經把 `/api/*` 代到 `127.0.0.1:8000`,所以瀏覽器看到的永遠是同源:
不會有 CORS,也就不會出現「本機好好的、部署後被 preflight 擋掉」這種只在正式環境才炸的錯。

### 每次 demo 前(已經裝好之後)

第一次安裝看下面的「終端機 1 / 終端機 2」。裝好之後每次只要開兩個終端機、各跑一組,**一行一行貼**:

```powershell
# 終端機 1 · 後端 —— 一定要用 .venv 裡的 python,全域(Anaconda)那支會缺套件
cd D:\Hackathon_MaiCoin_chmod777\agent-core
.\.venv\Scripts\python.exe -m uvicorn agent_ui.app:app --workers 1 --port 8000

# 終端機 2 · 像素世界前端 —— 5173 沒被 Windows 擋的機器直接 npm run dev 也行
cd D:\Hackathon_MaiCoin_chmod777\frontend-pixel
npm run dev -- --port 3000
```

| 網址 | 是什麼 |
|---|---|
| <http://localhost:3000> | 像素世界(主要前端) |
| <http://localhost:8000> | 後端內建的對話介面 —— 不用另外啟動,後端起來就有 |
| <http://localhost:8000/analytics> | 使用者行為分析(讀 `conversation_logs/` 的對話紀錄) |

停止:在各自的終端機按 `Ctrl+C`。改了 `.env` 或後端程式碼都要**重啟後端**才會生效(沒有開 `--reload`)。

- 只是 demo 對話與帳戶:`.env` 開 `MAIA_LOCAL_NO_LOGIN=1` 就不用登入,見「[兩個對話介面](#兩個對話介面)」。
- 要讓人註冊 / 登入(討論區發文、進度跟著帳號走):先開 Docker Desktop,見「[登入與帳號](#登入與帳號dynamodb)」。

### 終端機 1 · Agent 後端

<details open>
<summary>Windows PowerShell</summary>

**一行一行貼,不要整段貼。** 整段貼進 PowerShell 時它會照順序不管成敗一路往下跑 ——
venv 還沒建好就先 activate、pip 掛了還是照樣執行 uvicorn,最後看到的錯誤跟真正的原因差三步。

```powershell
cd D:\Hackathon_MaiCoin_chmod777\agent-core
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env             # 填金鑰;不填也能跑約 80% 的公開技能
python -m uvicorn agent_ui.app:app --workers 1 --port 8000
```

最後一行**用 `python -m uvicorn` 而不是直接 `uvicorn`**。裝了 Anaconda 的機器上
`uvicorn.exe` 也在全域 PATH 裡,venv 少裝一個套件時它會安靜地退回去用全域那支,
症狀是一個看起來毫不相干的 `ModuleNotFoundError`(例如 `feedparser`)。
`python -m` 綁的是**當下這個直譯器**,不會跑錯環境。
</details>

<details>
<summary>macOS / Linux</summary>

```bash
cd agent-core
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn agent_ui.app:app --workers 1 --port 8000
```
</details>

> ⚠️ **`.env` 不在版控裡**(`.gitignore` 擋著,金鑰不該進 git)。
> 從舊 repo 搬一份已經填好的過來會省很多事:
> `copy ..\..\Skill_for_maicoin_agent\.env .env`
>
> ⚠️ **後端只讀 `agent-core/.env`**。repo 根目錄那份 `.env` 後端不會讀 ——
> 金鑰改在那裡等於沒改(症狀:`scripts/max_check.py` 還是報舊金鑰的錯)。

<details>
<summary>裝不起來的三種情況</summary>

**`Permission denied: ...\.venv\Scripts\python.exe`**
`.venv` 已經是啟用狀態,python.exe 被自己佔住,建不上去。先退出再砍掉重建:

```powershell
deactivate
Remove-Item -Recurse -Force .venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

`Remove-Item` 若說檔案被占用,關掉這個終端機開一個新的再刪。

**`UnicodeDecodeError: 'cp950' codec can't decode byte ...`**
requirements 類的檔案裡有非 ASCII 字元。pip 是用
`locale.getpreferredencoding()` 讀它的,在 zh-TW 的 Windows 上那是 cp950,
一個中文註解就會讓整個安裝掛掉 —— 而 traceback 指的是 pip,不是那個檔案。
`requirements.txt` 已經清成純 ASCII 並在檔頭寫了規則,**別再把中文加回去**。
臨時繞過可以先 `$env:PYTHONUTF8=1`。

**`ModuleNotFoundError` 指向一個明明裝過的套件**
八成是跑到全域(Anaconda)的直譯器去了。確認一下站在哪裡:

```powershell
python -c "import sys; print(sys.executable)"
```

印出來的不是 `...\agent-core\.venv\Scripts\python.exe` 就是跑錯環境了。
</details>

### `.env` 本機 demo 要設的幾項

| 變數 | 本機 demo 建議值 | 說明 |
|---|---|---|
| `LLM_PROVIDER` | `openrouter` | 大腦供應商,見下方「LLM 供應商」 |
| `OPENROUTER_API_KEY` | 你的 key | 到 OpenRouter 後台建立 |
| `OPENROUTER_MODEL` | `google/gemini-2.5-flash` | 便宜、快、中文佳;要更強可換 `anthropic/claude-sonnet-4.5`(約貴 10 倍) |
| `MAX_API_KEY` / `MAX_API_SECRET` | 選填 | 「我的帳戶」、掛單、撤單要用;不填只看得到公開行情。填完跑 `python scripts/max_check.py` 驗證 |
| `MAIA_LOCAL_NO_LOGIN` | `1` | 本機免登入,見「[兩個對話介面](#兩個對話介面)」 |
| `RISK_MODE` | `paper` | 模擬盤。`live` 還要搭配未過期的 `LIVE_UNTIL` 才會真的送出 MAX 訂單 |

### 終端機 2 · 像素世界前端

```bash
cd frontend-pixel
npm install
npm run dev        # http://localhost:5173
```

打開 <http://localhost:5173>,按 `Enter` 開 MAIA 隨便問一句 ——
**工具晶片一顆一顆亮起來就是兩邊接上了**。跳「連線異常」就是後端沒起來、或不在 8000 埠。

<details>
<summary><code>listen EACCES: permission denied 127.0.0.1:5173</code></summary>

不是程式的問題:Windows 的 Hyper-V / WSL(Docker Desktop 會用到)啟動時會保留幾段 TCP port,
5173 剛好落在裡面就誰都綁不上。查目前被保留的範圍:

```powershell
netsh interface ipv4 show excludedportrange protocol=tcp
```

換一個不在範圍內的 port 就好,proxy 設定跟 port 無關:`npm run dev -- --port 3000`。
保留範圍重開機後可能會變,所以今天被擋、明天不一定。
</details>

### 兩個對話介面

同一個後端、同一支 `POST /api/chat`(SSE),只是入口不同:

| 入口 | 網址 | 登入 |
|---|---|---|
| 像素世界的 MAIA dock | `localhost:3000`(或 5173),進世界後按 `Enter` | 有登入畫面;「以訪客身分逛逛」也進得去 |
| 後端內建對話頁 | `localhost:8000` | **沒有登入畫面** |

對話、帳戶總覽 / 持倉 / 帳戶紀錄、我的掛單、撤單都在登入牆後面 ——
在公開網址上,它們分別是 LLM 帳單與真實帳戶。本機 demo 有兩種做法:

- **免登入(建議)**:`agent-core/.env` 設 `MAIA_LOCAL_NO_LOGIN=1`,重啟後端。
  只放行**直接從本機**連進來、且不帶任何轉發標頭(`X-Forwarded-For` 等)的請求 ——
  部署在 CloudFront / ALB 後面一定帶這個標頭,所以雲端照樣要登入。
  身分相關的(我是誰、進度、發文、官方操作)仍要登入。
  ⚠️ 開著它時**別用 `npm run dev -- --host` 開放區網**:其他裝置經 Vite 轉發進來也會被當成本機,看得到帳戶、也能撤單。
- **登入**:先在像素世界註冊 / 登入,再開 `localhost:8000`。cookie 只看主機名稱不看 port,
  所以兩邊要**用同一個主機名稱**(都用 `localhost`,別一邊用 `127.0.0.1`)。登入需要 DynamoDB,見下一節。

沒登入時 `:8000` 會回「尚未登入(HTTP 401)」,像素世界的帳戶面板會顯示「請先登入才能查看帳戶」。

### 登入與帳號(DynamoDB)

玩家帳號與登入 session 存 DynamoDB(`maia_players`、`maia_sessions`)。沒有有效的 AWS 憑證時註冊會回 500
(`UnrecognizedClientException`)—— 本機改用 DynamoDB Local,程式碼一個字不用改。**以下只要做一次**:

```powershell
# 1) 開 Docker Desktop,起一個會保存資料的 DynamoDB Local(之後只要 Docker 開著它就會自己起來)
docker run -d --name maia-ddb --restart unless-stopped -p 8001:8000 --user root -v maia-ddb-data:/home/dynamodblocal/data amazon/dynamodb-local -jar DynamoDBLocal.jar -sharedDb -dbPath ./data

# 2) 建表。dummy key 只是讓 boto3 肯簽名,DynamoDB Local 不驗證。
#    這幾個 $env: 只活在這個終端機 —— 建完表就關掉它,別拿它來跑後端
cd D:\Hackathon_MaiCoin_chmod777\agent-core
$env:DYNAMODB_ENDPOINT_URL="http://localhost:8001"; $env:AWS_DEFAULT_REGION="us-west-2"
$env:AWS_ACCESS_KEY_ID="dummy"; $env:AWS_SECRET_ACCESS_KEY="dummy"
.\.venv\Scripts\python.exe scripts\create_tables.py
```

然後在 `agent-core/.env` 加上這兩行(之後要回雲端,把它們註解掉即可):

```
DYNAMODB_ENDPOINT_URL=http://localhost:8001
AWS_DEFAULT_REGION=us-west-2
```

- **`-sharedDb` 不能省**:沒有它,DynamoDB Local 會依「access key + region」分開存 ——
  建表用 dummy key、後端用你的 AWS profile,兩邊看到的是兩個不同的資料庫,症狀是「表明明建了卻說找不到」。
- 埠用 8001:DynamoDB Local 預設也是 8000,會跟後端撞。
- 機器上完全沒有 AWS 憑證(沒有 `AWS_PROFILE`、也沒有 key)時,`.env` 再加
  `AWS_ACCESS_KEY_ID=dummy` 與 `AWS_SECRET_ACCESS_KEY=dummy`,否則後端登入時會報 `Unable to locate credentials`。
- `S3_REPORTS_BUCKET` 有設時,對話重播存 S3;沒有有效 AWS 憑證就把它註解掉,改存本機 `conversation_logs/sessions/`。

<details>
<summary>社群 bot(Telegram / LINE)</summary>

- **Telegram**:`agent-core/.env` 有 `TELEGRAM_BOT_TOKEN` 時,後端一啟動就自動開 long polling,本機就能收發,不需要公開網址。
  ⚠️ bot 目前**沒有使用者白名單**,而且跟對話介面共用全部工具:MAX 金鑰有效時,任何人私訊 bot 都查得到帳戶、也能撤單。
  不 demo bot 時把 token 註解掉。
- **LINE**:只能走 webhook(`POST /api/webhook/line`),需要公開的 https 網址(部署環境或 ngrok 這類通道);本機直接跑收不到訊息。
</details>

### 世界裡的操作

| 按鍵 | 動作 |
|---|---|
| `WASD` / 方向鍵 / 滑鼠左鍵 | 移動(點擊互動點會走過去並自動觸發) |
| `E` | 與最近的互動點 / 傳送門互動 |
| `Enter` | 開 MAIA 對話 dock(**非模態,世界繼續跑**) |
| `Z` | 全景 ⇄ 跟隨。進場預設全景,角色一動就自動切跟隨 |
| `I` | 角色訊息窗 |
| `ESC` | 關閉彈窗 |

底部功能條點一格是**傳送 → 角色自己走過去 → 自動觸發**,不是直接開面板 ——
選單是給趕時間的人的捷徑,世界仍然是容器。

### 驗證與除錯

```bash
cd frontend-pixel && npm test      # 156 項 playwright e2e(會自己起 dev server)
cd frontend-pixel && npm run build # tsc --noEmit && vite build
cd agent-core && ./.venv/Scripts/python -m pytest -q   # macOS / Linux:./.venv/bin/python
```

`npm test` 第一次會自己下載 Chromium。合併任何一支 PR 之前這三條都要綠。

pytest 在 **Windows 上有幾項注定會紅**,不是你改壞的:`test_analyst_sandbox.py` 的 7 項
(沙盒用了 `pass_fds`,Windows 不支援)與 `test_analyst_desk.py` 的 2 項(時間戳換算在 Windows 上會 `OSError`);
另外 `test_real_*` 這類會打真實外部 API(新聞、CoinGlass、MAX),網路或金鑰不對時也會失敗。要全綠請在 Linux / macOS 跑。

金鑰與外部服務的檢查腳本(都在 `agent-core/` 底下跑;沒 activate `.venv` 就把 `python` 換成 `./.venv/Scripts/python`):

```bash
python scripts/max_check.py --no-backend   # MAX 金鑰:形狀 → 公開 API → 簽章 → 右側面板用到的每支端點
python scripts/bedrock_check.py            # Bedrock:列出這個 AWS 帳號實際可用的模型並試打一次
python scripts/skill_healthcheck.py        # 逐一實際呼叫每個工具,列出誰活著、誰缺 key、誰壞了
```

| 網址參數 | 作用 |
|---|---|
| `?debug=1` | 畫出碰撞盒、鏡頭死區、互動範圍,並開放 `window.__game()` / `__zones()` |
| `?fast=1` | 跳過進場、關閉所有輪詢、強制跟隨鏡頭(測試與錄影用) |
| `?failApi=1` | 讓所有 API 呼叫失敗,檢查每個面板的錯誤狀態 |

### 想直接看畫面,手上沒有 node

```bash
cd frontend-pixel && node scripts/build-single.mjs   # → ../預覽-新介面.html
```

壓成一個沒有任何外部請求的單檔 HTML,雙擊就會跑。傳給隊友、給評審看、
或臨時換一台筆電都只是一個檔案。只是預覽產物,`.gitignore` 擋著不進版控;
正式部署仍然走 `npm run build`。

**LLM 供應商**由 `agent-core/.env` 的 `LLM_PROVIDER` 切換(改完重啟後端):

| 值 | 用途 |
|---|---|
| `openrouter` | **目前本機用這個**(黑客松的 AWS 臨時憑證已失效)。一把 `OPENROUTER_API_KEY` 可接 Gemini / Claude / GPT,模型由 `OPENROUTER_MODEL` 決定。回覆不逐字串流,整段一次出現 |
| `bedrock` | 黑客松正式 demo 與部署時用的(命題限用 AWS 提供之基礎模型)。需要有效 AWS 憑證,用 `python scripts/bedrock_check.py` 驗證 |
| `ollama` | 本機開發,零成本(`OLLAMA_HOST` 指到你的 Ollama) |

三者共用同一個 `LLMProvider` 介面,主迴圈零耦合。`deploy/Dockerfile.agentcore` 已寫死 `LLM_PROVIDER=bedrock`。

### AgentCore Runtime

```bash
docker buildx build --platform linux/arm64 \
  -f deploy/Dockerfile.agentcore -t maia-agentcore .
```

服務合約四項齊備:`/invocations`(SSE)、`/ping`(Healthy / HealthyBusy)、ARM64、`0.0.0.0:8080`。

**2026-08-02 部署狀態**:

> **2026-09-23 更新**:黑客松 workshop 帳號的 AWS 臨時憑證已失效(`InvalidClientTokenId`),
> 下面的 CloudFront 網址 DNS 也已解析不到 —— 以下是當時的部署紀錄,目前雲端不可用。
> 本機 demo 請照上面「[每次 demo 前](#每次-demo-前已經裝好之後)」的步驟。

- AWS Bedrock AgentCore Runtime `maia_agent` 已部署，runtime ID 為 `maia_agent-4dRDgpAt4P`，狀態 `READY`。
- `frontend-pixel` 已以 Amazon CloudFront + S3 對外部署：<https://d1kok6d2wto1xz.cloudfront.net/>（2026-08-02 實測 HTTP 200，頁面標題「MAIA · 數位廣場」）；同網域 `/api/config` 也回 200，表示 CloudFront `/api/*` 同源後端路由已啟用。
- `/api/*` 實際路徑是 CloudFront → ALB → ECS Fargate `maia-api`（ARM64、固定 1 task）；後端 image 在 ECR，金鑰由 Secrets Manager `maia/app` 注入，log 寫入 CloudWatch Logs。
- 正式 LLM 路徑使用 Amazon Bedrock Claude；`BedrockProvider.chat_stream()` 已接 `ConverseStream`，會產生 `answer_delta`。
- 雲端共用資料使用 DynamoDB（玩家、session、討論區、留言、社群摘要）；S3 用於報告、對話紀錄與 Transcribe 暫存音檔。
- Bedrock provider 有 18 項專屬自動化測試，包含文字串流、工具參數 partial JSON 重組、錯誤降級與主迴圈路分支。

這些是目前可由程式碼、自動化測試、HTTP 回應與部署設定直接驗證的部分。Amplify Hosting、EventBridge Scheduler、Lambda 與 Bedrock Guardrails 沒有使用。

---

## 文件

| 檔案 | 內容 |
|---|---|
| [`docs/功能與服務總覽.md`](docs/功能與服務總覽.md) | **功能、113 個工具(skill)與串接服務的現況總覽**,每一項都有實測狀態與待修清單 |
| [`docs/架構與實作計畫.md`](docs/架構與實作計畫.md) | 系統架構、agent 設計、AWS 部署、**已知缺口誠實清單** |
| [`docs/AWS服務盤點.md`](docs/AWS服務盤點.md) | AWS 已接入/已部署、待確認與規劃中服務的正準狀態 |
| [`docs/AWS部署.md`](docs/AWS部署.md) | CloudFront、ALB、ECS Fargate、ECR、Secrets Manager 與 AgentCore 的實際資源與重新部署步驟 |
| [`docs/前端框架規格.md`](docs/前端框架規格.md) | 像素世界的擴充架構:Zone/Panel 註冊表、HUD 分層、多人協作契約 |
| [`docs/agent-repo-整合計畫.md`](docs/agent-repo-整合計畫.md) | agent 系統併入本 repo 的盤點與判決 |
| [`docs/競賽約束與資源.md`](docs/競賽約束與資源.md) | 競賽事實、MAX API 能力、**費用/權限/用量表** |
| [`docs/提案簡報骨架.md`](docs/提案簡報骨架.md) | 簡報結構 |
| [`agent-core/docs/SKILLS.md`](agent-core/docs/SKILLS.md) | 工具清單 |

---

## 技術選型的幾個刻意決定

**前端零外部 runtime 相依。** `package.json` 的 dependencies 只有 `react` 與 `react-dom` —— 沒有圖表庫、沒有狀態管理、沒有 CSS 框架、沒有 CDN。所有圖表手刻 SVG/CSS。理由是**現場 Live Demo 的網路不可信**,任何一個外部資源載不進來就是一塊空白。

**整數倍縮放不妥協。** 非整數倍會讓一個來源像素跨到兩個螢幕像素,即使關掉平滑化也會出現寬度不一的鋸齒。做法是先取最接近的整數倍率,再把 backbuffer 撐成剛好填滿視窗。

**每幀變動的東西不進 React。** `[E]` 提示、傳送門名牌、行情數字每幀都在動,走 React state 會逼元件每秒重繪 60 次。它們由 `worldLabels.ts` 與 HUD 的 `LiveText` 直接操作 DOM。有一項測試專門守著:走動 2 秒期間 `#ui-root` 的 DOM 變動次數必須是 **0**。

**中文一律走 DOM,不畫進 backbuffer。** 內部解析度只有 480×270 上下,8px 的中文整數放大後會糊成一團。

**MAX 串接 100% 自建。** 自寫 HMAC-SHA256 簽章(GET/POST/DELETE 共用),覆蓋 13 個私有端點 + 下單撤單,而不是接現成的 MCP server —— 換來的是端點覆蓋更完整,以及可以把風控層直接內嵌在呼叫路徑上。

---

## 命題資訊

- 命題單位:MaiCoin 現代財富科技股份有限公司
- 命題類別:智慧理財 · 主題:打造現代 AI 投資工具
- 決賽:8/1–8/2 現場實作 + 評審簡報 + **Live Demo(現場實跑)**
- 完整命題說明見 repo 根目錄的 PDF;評分權重與資源清單見 [`docs/競賽約束與資源.md`](docs/競賽約束與資源.md)

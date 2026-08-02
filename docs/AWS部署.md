# AWS 部署

> 這份文件描述 MAIA 在 AWS 上的實際部署形態。所有 ID、ARN、設定值都是**現行環境的真值**，
> 不是範例。可執行版本在 [`agent-core/deploy/aws/`](../agent-core/deploy/aws/)。
>
> 標 ⚠️ 者是**已知缺口**，不是待辦裝飾 —— 每一條都寫了實際後果。

**Live Demo：<https://d1kok6d2wto1xz.cloudfront.net>**

---

## 1 · 架構

```
                        評審 / 使用者 Browser
                                │ HTTPS
                                ▼
        ┌────────────────────────────────────────────┐
        │  CloudFront  E2TEDCZ57EDLGJ                │  唯一入口
        │  d1kok6d2wto1xz.cloudfront.net             │
        └───────┬────────────────────────┬───────────┘
      預設 /*   │                        │  /api/*
    CachingOptimized              CachingDisabled
                │                        │  AllViewerExceptHostHeader
                ▼                        ▼
    ┌───────────────────┐     ┌──────────────────────┐
    │ S3 maia-web-…     │     │ ALB maia-alb  :80    │  idle_timeout 300s
    │ 私有桶 · OAC 簽章  │     │ 只收 CloudFront 前綴 │
    └───────────────────┘     └──────────┬───────────┘
                                          │ :8000
                                          ▼
                        ┌──────────────────────────────────┐
                        │ ECS Fargate  ARM64  1vCPU/2GB    │
                        │ service maia-api  · 固定 1 task   │
                        │ uvicorn --proxy-headers          │
                        └──┬────────┬────────┬─────────┬───┘
                           ▼        ▼        ▼         ▼
                      Bedrock    MAX API  DynamoDB    S3
                   Sonnet 4.6    (HMAC)    ×5 表    reports/
                                                    sessions

  ── 與上面那條並行、互不影響 ──────────────────────────────
  Bedrock AgentCore Runtime  maia_agent-4dRDgpAt4P  · READY
  /invocations (SSE) · /ping (Healthy/HealthyBusy) · ARM64 · :8080
```

**為什麼是單一 CloudFront 入口。** 前端對後端永遠同源，所以完全不需要 CORS。
這不是部署時才想到的 —— [`vite.config.ts`](../frontend-pixel/vite.config.ts) 的註解早就寫明
「部署時把 CloudFront 的 `/api/*` behavior 指到後端就好，前端 build 產物一個字都不用改」。
實際部署驗證了這件事：`dist/config.js` 的 `apiBase` 是空字串，一個字都沒改。

---

## 2 · 資源清單

### 這次建立的

| 服務 | 資源 | 備註 |
|---|---|---|
| CloudFront | `E2TEDCZ57EDLGJ` / `d1kok6d2wto1xz.cloudfront.net` | 兩個 origin |
| CloudFront OAC | `E26RUL37BM29RW` (`maia-web-oac`) | sigv4，取代舊的 OAI |
| S3 | `maia-web-218322564712` | 前端靜態產出。私有，桶政策綁死 distribution ARN |
| ECR | `maia-api` / `maia-agentcore` | 皆 ARM64 |
| ECS | cluster `maia` · service `maia-api` · taskdef `maia-api` | Fargate ARM64 |
| ELB | ALB `maia-alb` · TG `maia-api-tg` | 健康檢查 `/api/config` |
| VPC | SG `maia-alb-sg` / `maia-task-sg` · 前綴清單 `pl-82a045eb` | default VPC，3 個 AZ |
| Secrets Manager | `maia/app` | 4 把真金鑰 |
| IAM | `maia-ecs-exec-role` / `maia-task-role` / `maia-agentcore-role` | 拉 image 與跑起來之後的權限分離 |
| CloudWatch Logs | `/ecs/maia-api`（保留 7 天）· `/aws/bedrock-agentcore/runtimes/…` | |
| Bedrock AgentCore | `maia_agent-4dRDgpAt4P` | 命題合約入口 |

### 原本就存在，只是接上

| 服務 | 資源 |
|---|---|
| Bedrock | `us.anthropic.claude-sonnet-4-6`（跨區推理設定檔） |
| DynamoDB | `maia_players` · `maia_sessions` · `maia-discussion-spaces-*` · `maia-discussion-posts-*` · `maia_community_insights` |
| S3 | `maia-218322564712-20260801`（reports / sessions） |

**沒有用到、不要畫進架構圖的**：Bedrock Guardrails（未實作）、App Runner（見下）、EventBridge Scheduler、Lambda。

---

## 3 · 幾個刻意的決定

**App Runner 不能用。** 這個帳號的 SCP 明文擋掉 `apprunner:*`：

```
User: .../WSParticipantRole/Participant is not authorized to perform:
apprunner:ListServices ... because no service control policy allows the action
```

`docs/架構與實作計畫.md` 把 App Runner 列為替代方案 —— 在這個帳號上它不是選項，所以走 ECS Fargate + ALB。

**永遠只有 1 個 task。** service 設 `maximumPercent=100` / `minimumHealthyPercent=0`，
也就是先停舊的再起新的。因為核准 token 是**行程內狀態**（`agent/trade_approval.py`），
兩個實例並存時 A 開出的核准單送到 B 會 403 —— 這正是 `docs/架構與實作計畫.md` 已知缺口 #5。
代價是部署期間有 1–2 分鐘斷線，**不要在台上按部署**。

**ARM64。** 開發機是 Apple Silicon，原生建置不用模擬；Fargate 的 ARM64 也比 x86 便宜。
AgentCore 那支則是合約硬性要求 ARM64，沒有選擇餘地。

**ALB 只收 CloudFront。** 入口綁受管前綴清單 `pl-82a045eb`（`com.amazonaws.global.cloudfront.origin-facing`）。
擋掉的是「繞過 CloudFront 直連 ALB」那條路 —— 那條是 http，session cookie 不會帶 `Secure`。
**代價：你也不能直接 curl ALB 除錯**，只能看 CloudWatch Logs。

**`.env` 沒有進 image。** 兩份 `.dockerignore` 的第一條規則就是擋它。金鑰改走 Secrets Manager，
由 ECS 在啟動時注入成環境變數；task definition 裡只有 ARN 參照，看不到值。

---

## 4 · 踩過的坑

**① 根目錄的 `.dockerignore` 把 `agent_ui/` 排除掉了。**
那份是為 `Dockerfile.agentcore` 寫的（AgentCore 入口確實用不到 agent_ui）。
直接沿用會建出一個**沒有前端 API 的 image**。
解法是新增 [`deploy/Dockerfile.api.dockerignore`](../agent-core/deploy/Dockerfile.api.dockerignore) ——
BuildKit 會優先採用 `<dockerfile 路徑>.dockerignore`，所以原本那份對 AgentCore build 的行為完全不變。

**② 後端在兩層代理後面，不加 `--proxy-headers` 會「登入成功但每次都說沒登入」。**
`agent_ui/app.py` 的 `_cookie_secure()` 看 `request.url.scheme` 決定 cookie 要不要帶 `Secure`。
CloudFront → ALB 這段是 http，所以還額外設了 `MAIA_COOKIE_SECURE=1` 直接寫死，不依賴推斷。

**③ ALB 預設 idle timeout 60 秒會把 SSE 切斷。** 已調到 300 秒。
實測一輪完整對話（243 個事件）約 19 秒，但帶多輪工具呼叫的問題會更久。

**④ zsh 不做 word splitting。**
`--subnets $LIST` 在 zsh 會被當成**單一個** subnet id，噴 `InvalidSubnet`。
所有腳本一律用 `#!/usr/bin/env bash` shebang，並把 subnet 分開傳。

**⑤ `aws bedrock-agentcore invoke-agent-runtime --payload` 不吃非 ASCII。**
中文 prompt 會噴 `string argument should contain only ASCII characters`，必須走 `fileb://` 檔案。

**⑥ 新模型只能用跨區推理設定檔 id。** `us.` 開頭。填基礎模型 id 會 `ValidationException`。

---

## 5 · 怎麼重新部署

先取得憑證（主辦給的臨時憑證三個一組，缺 `AWS_SESSION_TOKEN` 一定 401）：

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_SESSION_TOKEN=...
```

然後：

| 情境 | 指令 |
|---|---|
| 改了前端 | `./deploy/aws/deploy-frontend.sh` |
| 改了後端程式碼 | `./deploy/aws/deploy-backend.sh` |
| 改了環境變數 / 模型 / CPU | `./deploy/aws/register-taskdef.sh` |
| 改了 AgentCore 入口 | `./deploy/aws/deploy-agentcore.sh` |
| 換一個全新 AWS 帳號 | `./deploy/aws/provision.sh` 然後把印出的 ID 貼回 `env.sh` |

看後端日誌（ALB 已鎖，這是唯一途徑）：

```bash
aws logs tail /ecs/maia-api --follow
```

授予官方帳號身分（**不需要重新部署**，角色是每次請求即時查 DynamoDB 的）：

```bash
cd agent-core && .venv/bin/python scripts/grant_official.py <username>
```

---

## 6 · 已知缺口

⚠️ **審計鏈存在 ephemeral disk 上。**
`agent_memory/`、`audit_logs/`、`conversation_logs/`、`run_cards/` 仍寫容器本機檔案系統，
**task 一重啟就全沒了** —— 包含「跨會話 SHA256 不可竄改審計鏈」這個賣點。
已經在 DynamoDB 的是討論室、玩家、session、社群洞察；已經在 S3 的是 reports 與 sessions。
架構圖上 DynamoDB 可以畫實線，但審計鏈那條要標清楚。

⚠️ **語意工具檢索在雲上是死的。**
`OLLAMA_HOST` 指向容器內不存在的 `127.0.0.1:11434`，CloudWatch 會看到
`工具 embedding 呼叫失敗（降級）：Connection refused`。三段式檢索的第二段實際沒作用，
目前靠關鍵字比對仍能正確路由。要修得把 embedding 換成 Bedrock Titan。

⚠️ **`/api/dashboard` 沒有分帳。**
`get_max_accounts()` 不吃 user 參數，讀的是那唯一一把 `MAX_API_KEY`。
session gate 擋掉匿名掃描，但**任何人註冊一個帳號就會看到同一份真實 MAX 帳戶資料**。
這既是 Lv2 Private API 的最強證據，也是隱私風險 —— 取捨要自己決定。

⚠️ **登入端點沒有節流。**
`/api/auth/login` 無 rate limit、無失敗鎖定。PBKDF2 210k 疊代只擋離線破解，擋不住線上猜測。

⚠️ **Bedrock Guardrails 未實作。** 架構圖上請畫虛線標 Phase 2。

⚠️ **部署形態是手動建立的，沒有 IaC。**
`provision.sh` 是可執行的紀錄，不是 CloudFormation/Terraform —— 它不管理狀態、不會偵測飄移。

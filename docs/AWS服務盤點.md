# MAIA AWS 服務盤點

> 最後核對：2026-08-02。本文是 AWS 使用與部署狀態的正準來源；程式碼、自動化測試或 AWS 資源狀態無法驗證的服務，一律標為「規劃中」或「待團隊確認」。

## 已接入或已部署

| AWS 服務 | 狀態 | MAIA 用途 | 主要實作 |
|---|---|---|---|
| Amazon Bedrock Runtime | ✅ 已實際使用 | MAIA 對話、工具調用、討論區/全站社群摘要 | `agent-core/agent/llm/bedrock.py` |
| Bedrock ConverseStream | ✅ 已實作並測試 | 逐字輸出 `answer_delta`，tool partial JSON 重組 | `agent-core/agent/llm/bedrock.py`、`tests/test_bedrock_provider.py` |
| Amazon Bedrock AgentCore Runtime | ✅ 已部署 | 承載 `/invocations` SSE 與 `/ping` | runtime `maia_agent`，ID `maia_agent-4dRDgpAt4P`，狀態 `READY` |
| Amazon CloudFront + S3 | ✅ 已部署 | `frontend-pixel` 公開靜態網站 + `/api/*` 同源路由 | <https://d1kok6d2wto1xz.cloudfront.net/>；2026-08-02 實測 HTTP 200、`Via: CloudFront`、`Server: AmazonS3`、標題「MAIA · 數位廣場」；`/api/config` 也回 200 |
| Amazon ECS Fargate + ALB | ✅ 已部署 | `/api/*` FastAPI 後端 | CloudFront → ALB `maia-alb` → ECS service `maia-api`；ARM64 1vCPU/2GB、固定 1 task，ALB idle timeout 300s |
| Amazon ECR | ✅ 已部署 | API 與 AgentCore ARM64 container images | repositories `maia-api` / `maia-agentcore` |
| AWS Secrets Manager | ✅ 已部署 | MAX、Threads 與第三方 API 金鑰 | secret `maia/app`，ECS task definition 只保留 ARN 參照 |
| Amazon CloudWatch Logs | ✅ 已部署 | ECS API 與 AgentCore runtime log | `/ecs/maia-api`（保留 7 天）與 AgentCore runtime log group |
| Amazon DynamoDB | ✅ 已實際使用 | 玩家、登入 session、討論區、留言、社群摘要 | `agent_ui/store.py`、`threads_bridge.py`、`community_insights.py` |
| Amazon S3 | ✅ 已實際使用 | 私有報告 JSON、15 分鐘 presigned URL、對話 session、Transcribe 暫存音檔 | `agent_ui/app.py`、`agent/conversation_log.py` |
| Amazon Transcribe | ✅ 已實作並實際轉錄成功 | 瀏覽器錄音的批次語音轉文字；完成後清除 job 與 S3 暫存檔 | `POST /api/transcribe`、`agent_ui/app.py` |
| AWS IAM / STS | ✅ 已使用 | 為 Bedrock、DynamoDB、S3、Transcribe 與 AgentCore 提供憑證/角色授權 | boto3 default credential chain、本機 AWS profile、雲端 IAM role |

### 已驗證的 Bedrock 狀態

- 正式 demo provider：`LLM_PROVIDER=bedrock`。
- 最新部署腳本與線上 revision 2 基準 model：`us.anthropic.claude-opus-4-5-20251101-v1:0`；程式碼與 `.env.example` 的 2024 Claude 3.5 值僅是 fallback。
- `tests/test_bedrock_provider.py` 共 18 項測試，包含 ConverseStream、tool call、錯誤處理與主迴圈路分支。

## 已實作但仍要注意

| 項目 | 現況 |
|---|---|
| Amazon Transcribe | 團隊已確認在正式流程中轉錄成功。程式在完成後會主動刪除 Transcribe job 與 S3 暫存音檔，因此 AWS 上沒有近期 job 紀錄是預期的隱私清理結果 |
| 社群摘要排程 | 目前是 FastAPI 行程內單 worker 排程；單實例 demo 可用，多實例生產環境應改 EventBridge Scheduler |
| 持久化 | 玩家/session/討論/摘要已用 DynamoDB，報告/對話已可用 S3；審計鏈、部分 agent memory、run card 與核准 token 仍在本機檔案或行程記憶體 |
| 單 task 限制 | ECS service 刻意固定 1 task，因為核准 token 仍在行程記憶體；部署時會有 1–2 分鐘中斷，不要在 demo 中部署 |
| 公開實盤模式 | 最新部署設定是 `MAIA_ACCOUNT_OWNERS=*`、`RISK_MODE=live`、`LIVE_UNTIL=2026-08-05`；任何註冊者都可看到共用 MAX 帳戶，並在 HITL/live guard 後送出真實訂單 |
| `approval_secret` | 是每次後端啟動產生、交給同源前端的 CSRF nonce，不是登入憑證或 AWS/MAX 金鑰；安全性依賴同源策略與不開放 permissive CORS |

## 規劃中，不宣稱已部署

| AWS 服務 | 預計用途 | 現況 |
|---|---|---|
| AWS Amplify Hosting | 可選的前端托管方案 | 未使用；現行公開前端已是 CloudFront + S3 |
| Amazon EventBridge Scheduler / Lambda | 跨實例的每日摘要與主動任務 | 目前未實作，現行是行程內排程 |
| Amazon Bedrock Guardrails | Denied Topics、PII、grounding check | 目前未接入，不能在 demo 宣稱是 Guardrails 擋下回答 |
| Amazon Cognito | 託管登入 | 目前沒有使用；實際登入是 FastAPI + DynamoDB 玩家/session |

## 非 AWS 外部服務

- Meta Threads API：討論區根文、平台留言回覆、mention 匯入與同步。
- MaiCoin MAX API：即時行情、帳戶資料與交易功能。

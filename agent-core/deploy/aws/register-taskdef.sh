#!/usr/bin/env bash
# 註冊 ECS task definition，並在 service 還不存在時建立它。
#
#   ./deploy/aws/register-taskdef.sh
#
# 什麼時候要重跑：改環境變數、換模型、調 CPU/記憶體、加減 Secrets Manager 的欄位。
# 只是換程式碼的話不用 —— 那走 deploy-backend.sh（image tag 沒變，force-new-deployment 就會拉新的）。
#
# ⚠️ 這裡的環境變數**不是**直接照抄 agent-core/.env，有幾項刻意不同：
#   RISK_MODE      → 強制 paper。公開網址不開實盤（本機 .env 維持 live 不受影響）
#   LIVE_UNTIL     → 不帶。paper 模式下留著沒意義，還像個待引爆的開關
#   AWS_PROFILE    → 不帶。容器裡沒有 ~/.aws，帶了 boto3 會找不到 profile 而爆掉，改用 task role
#   OLLAMA_*       → 不帶。雲上走 Bedrock
#   MAIA_COOKIE_SECURE=1 → .env 沒有，但這裡必須有（見下）

source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
_require_creds

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/taskdef.json" <<EOF
{
  "family": "${ECS_TASKDEF_FAMILY}",
  "requiresCompatibilities": ["FARGATE"],
  "networkMode": "awsvpc",
  "cpu": "1024",
  "memory": "2048",
  "runtimePlatform": { "cpuArchitecture": "ARM64", "operatingSystemFamily": "LINUX" },
  "executionRoleArn": "${ROLE_EXEC}",
  "taskRoleArn": "${ROLE_TASK}",
  "containerDefinitions": [{
    "name": "maia-api",
    "image": "${ECR_API}:latest",
    "essential": true,
    "portMappings": [{ "containerPort": 8000, "protocol": "tcp" }],
    "environment": [
      { "name": "LLM_PROVIDER",        "value": "bedrock" },
      { "name": "BEDROCK_REGION",      "value": "${AWS_DEFAULT_REGION}" },
      { "name": "BEDROCK_MODEL",       "value": "${BEDROCK_MODEL}" },
      { "name": "AWS_DEFAULT_REGION",  "value": "${AWS_DEFAULT_REGION}" },
      { "name": "S3_REPORTS_BUCKET",   "value": "${REPORTS_BUCKET}" },
      { "name": "DYNAMODB_REGION",     "value": "${AWS_DEFAULT_REGION}" },
      { "name": "DYNAMODB_DISCUSSION_SPACES_TABLE", "value": "maia-discussion-spaces-${ACCOUNT_ID}" },
      { "name": "DYNAMODB_DISCUSSION_POSTS_TABLE",  "value": "maia-discussion-posts-${ACCOUNT_ID}" },
      { "name": "COMMUNITY_INSIGHTS_STORAGE",       "value": "dynamodb" },
      { "name": "DYNAMODB_COMMUNITY_INSIGHTS_TABLE","value": "maia_community_insights" },
      { "name": "RISK_MODE",           "value": "paper" },
      { "name": "TRADE_APPROVAL",      "value": "always" },
      { "name": "TRADE_AUTO_APPROVE_TWD", "value": "5000" },
      { "name": "READER_AGENT",        "value": "llm" },
      { "name": "AGENT_THINK",         "value": "auto" },
      { "name": "DEFAULT_EXCHANGE",    "value": "binance" },
      { "name": "DEFAULT_SYMBOL",      "value": "BTC/USDT" },
      { "name": "DEFAULT_TIMEFRAME",   "value": "1h" },
      { "name": "THREADS_AUTO_SYNC",   "value": "true" },
      { "name": "THREADS_SYNC_INTERVAL_SECONDS", "value": "300" },
      { "name": "MAIA_COOKIE_SECURE",  "value": "1" }
    ],
    "secrets": [
      { "name": "MAX_API_KEY",         "valueFrom": "${SECRET_ARN}:MAX_API_KEY::" },
      { "name": "MAX_API_SECRET",      "valueFrom": "${SECRET_ARN}:MAX_API_SECRET::" },
      { "name": "MAIA_ADMIN_TOKEN",    "valueFrom": "${SECRET_ARN}:MAIA_ADMIN_TOKEN::" },
      { "name": "THREADS_ACCESS_TOKEN","valueFrom": "${SECRET_ARN}:THREADS_ACCESS_TOKEN::" }
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/ecs/maia-api",
        "awslogs-region": "${AWS_DEFAULT_REGION}",
        "awslogs-stream-prefix": "task"
      }
    }
  }]
}
EOF

echo "▸ 註冊 task definition"
REV=$(aws ecs register-task-definition --cli-input-json "file://$TMP/taskdef.json" \
        --query 'taskDefinition.revision' --output text)
echo "  ${ECS_TASKDEF_FAMILY}:${REV}"

if aws ecs describe-services --cluster "$ECS_CLUSTER" --services "$ECS_SERVICE" \
     --query 'services[0].status' --output text 2>/dev/null | grep -q ACTIVE; then
  echo "▸ service 已存在 → 更新到新 revision"
  aws ecs update-service --cluster "$ECS_CLUSTER" --service "$ECS_SERVICE" \
    --task-definition "${ECS_TASKDEF_FAMILY}:${REV}" >/dev/null
else
  echo "▸ 建立 service"
  # maximumPercent=100 / minimumHealthyPercent=0 → 先停舊的再起新的，永遠只有 1 個 task。
  # 核准 token 是行程內狀態（agent/trade_approval.py），兩個實例並存時
  # A 開出的核准單送到 B 會 403。代價是部署期間有 1–2 分鐘斷線。
  aws ecs create-service --cluster "$ECS_CLUSTER" --service-name "$ECS_SERVICE" \
    --task-definition "${ECS_TASKDEF_FAMILY}:${REV}" --desired-count 1 --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[${SUBNET_A},${SUBNET_B},${SUBNET_C}],securityGroups=[${SG_TASK}],assignPublicIp=ENABLED}" \
    --load-balancers "targetGroupArn=${TG_ARN},containerName=maia-api,containerPort=8000" \
    --health-check-grace-period-seconds 180 \
    --deployment-configuration "maximumPercent=100,minimumHealthyPercent=0" >/dev/null
fi

aws ecs wait services-stable --cluster "$ECS_CLUSTER" --services "$ECS_SERVICE"
echo "✓ service 穩定"

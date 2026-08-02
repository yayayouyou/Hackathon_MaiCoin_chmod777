#!/usr/bin/env bash
# 部署共用設定。**這裡沒有任何金鑰** —— 帳號 ID 與 ARN 不是機密，
# 真正的祕密在 AWS Secrets Manager（maia/app）與你自己的環境變數裡。
#
# 用法：其他腳本會 `source` 這一份。你只需要先把主辦給的臨時憑證 export 進來：
#
#   export AWS_ACCESS_KEY_ID=...
#   export AWS_SECRET_ACCESS_KEY=...
#   export AWS_SESSION_TOKEN=...        # 臨時憑證三個一組，缺這個一定 401
#
# 憑證會過期。過期後重新從主辦的入口取一組即可，不需要改這個檔。

set -euo pipefail

export AWS_DEFAULT_REGION="us-west-2"
export ACCOUNT_ID="218322564712"

# ── 容器 ──────────────────────────────────────────────
export ECR_API="${ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com/maia-api"
export ECR_AGENTCORE="${ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com/maia-agentcore"

# ── 運算 ──────────────────────────────────────────────
export ECS_CLUSTER="maia"
export ECS_SERVICE="maia-api"
export ECS_TASKDEF_FAMILY="maia-api"

# ── 網路 ──────────────────────────────────────────────
export VPC_ID="vpc-0e2252cb286867ef0"
export SUBNET_A="subnet-07729d81691b43284"   # us-west-2a
export SUBNET_B="subnet-04c58f7fa501c57c0"   # us-west-2b
export SUBNET_C="subnet-0f16f114c8d04126a"   # us-west-2c
export SG_ALB="sg-0041c44f66fc98f90"
export SG_TASK="sg-0507449ac8e92a9cc"
# CloudFront 對源站的受管前綴清單。ALB 只收這個來源 → 沒人能繞過 CloudFront 直連
export PREFIX_LIST_CLOUDFRONT="pl-82a045eb"

export ALB_NAME="maia-alb"
export ALB_DNS="maia-alb-1280008743.us-west-2.elb.amazonaws.com"
export TG_NAME="maia-api-tg"
export TG_ARN="arn:aws:elasticloadbalancing:${AWS_DEFAULT_REGION}:${ACCOUNT_ID}:targetgroup/maia-api-tg/b3588482635ae50c"

# ── 前端 ──────────────────────────────────────────────
export WEB_BUCKET="maia-web-218322564712"
export CF_DIST_ID="E2TEDCZ57EDLGJ"
export CF_DOMAIN="d1kok6d2wto1xz.cloudfront.net"
export CF_OAC_ID="E26RUL37BM29RW"

# ── 狀態與祕密 ────────────────────────────────────────
export REPORTS_BUCKET="maia-218322564712-20260801"
export SECRET_ARN="arn:aws:secretsmanager:${AWS_DEFAULT_REGION}:${ACCOUNT_ID}:secret:maia/app-rH6bEh"

# ── IAM ───────────────────────────────────────────────
export ROLE_EXEC="arn:aws:iam::${ACCOUNT_ID}:role/maia-ecs-exec-role"
export ROLE_TASK="arn:aws:iam::${ACCOUNT_ID}:role/maia-task-role"
export ROLE_AGENTCORE="arn:aws:iam::${ACCOUNT_ID}:role/maia-agentcore-role"

# ── AgentCore ─────────────────────────────────────────
export AGENTCORE_ID="maia_agent-4dRDgpAt4P"
export AGENTCORE_ARN="arn:aws:bedrock-agentcore:${AWS_DEFAULT_REGION}:${ACCOUNT_ID}:runtime/${AGENTCORE_ID}"

# ── 模型 ──────────────────────────────────────────────
# 新模型多半只能用跨區推理設定檔 id（us. 開頭），填基礎模型 id 會 ValidationException
export BEDROCK_MODEL="us.anthropic.claude-sonnet-4-6"

# 專案根目錄（本檔在 agent-core/deploy/aws/ 底下）
export REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
export AGENT_CORE="${REPO_ROOT}/agent-core"
export FRONTEND="${REPO_ROOT}/frontend-pixel"

_require_creds() {
  if ! aws sts get-caller-identity >/dev/null 2>&1; then
    echo "✗ AWS 憑證無效或已過期。請重新 export AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN" >&2
    exit 1
  fi
}

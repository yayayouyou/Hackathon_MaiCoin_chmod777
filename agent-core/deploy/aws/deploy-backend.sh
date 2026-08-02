#!/usr/bin/env bash
# 重新部署 agent_ui 後端：build ARM64 image → ECR → ECS 換新 task。
#
#   ./deploy/aws/deploy-backend.sh
#
# ⚠️ 部署期間服務會短暫中斷（約 1–2 分鐘）。
# 這是刻意的：service 設定 maximumPercent=100 / minimumHealthyPercent=0，
# 也就是「先停舊的、再起新的」，永遠只有 1 個 task 在跑。
# 原因是核准 token 是行程內狀態（agent/trade_approval.py），
# 同時存在兩個實例時，A 開的核准單送到 B 會 403。
# 現場 demo 前請預留這段時間，不要在台上按。

source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
_require_creds

cd "$AGENT_CORE"

echo "▸ build（ARM64；Fargate runtimePlatform 設的是 ARM64，架構不符會起不來）"
docker buildx build --platform linux/arm64 \
  -f deploy/Dockerfile.api -t maia-api:latest --load .

echo "▸ 推 ECR"
aws ecr get-login-password | docker login --username AWS --password-stdin \
  "${ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com"
docker tag maia-api:latest "${ECR_API}:latest"
docker push "${ECR_API}:latest"

echo "▸ 換新 task"
aws ecs update-service --cluster "$ECS_CLUSTER" --service "$ECS_SERVICE" \
  --force-new-deployment >/dev/null
aws ecs wait services-stable --cluster "$ECS_CLUSTER" --services "$ECS_SERVICE"

echo "▸ 等 ALB target 健康"
until [ "$(aws elbv2 describe-target-health --target-group-arn "$TG_ARN" \
          --query 'TargetHealthDescriptions[0].TargetHealth.State' --output text)" = "healthy" ]; do
  sleep 10
done

echo "▸ 冒煙測試"
curl -sf "https://${CF_DOMAIN}/api/config" | python3 -m json.tool

echo "✓ https://${CF_DOMAIN}"

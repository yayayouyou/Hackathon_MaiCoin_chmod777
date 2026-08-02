#!/usr/bin/env bash
# 重新部署 Bedrock AgentCore Runtime（命題合約入口，與主 demo 路徑並行、互不影響）。
#
#   ./deploy/aws/deploy-agentcore.sh
#
# 主 demo（像素世界）走的是 ECS 上的 agent_ui，不是這條。
# 這條的存在意義是命題的「AWS 基礎模型 + AgentCore」合規展示：
#   /invocations (SSE) · /ping (Healthy/HealthyBusy) · ARM64 · 0.0.0.0:8080

source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
_require_creds

cd "$AGENT_CORE"

echo "▸ build（AgentCore 合約要求 ARM64，這裡沒有選擇餘地）"
docker buildx build --platform linux/arm64 \
  -f deploy/Dockerfile.agentcore -t maia-agentcore:latest --load .

echo "▸ 推 ECR"
aws ecr get-login-password | docker login --username AWS --password-stdin \
  "${ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com"
docker tag maia-agentcore:latest "${ECR_AGENTCORE}:latest"
docker push "${ECR_AGENTCORE}:latest"

echo "▸ 更新 runtime"
aws bedrock-agentcore-control update-agent-runtime \
  --agent-runtime-id "$AGENTCORE_ID" \
  --agent-runtime-artifact "{\"containerConfiguration\":{\"containerUri\":\"${ECR_AGENTCORE}:latest\"}}" \
  --role-arn "$ROLE_AGENTCORE" \
  --network-configuration '{"networkMode":"PUBLIC"}' \
  --protocol-configuration '{"serverProtocol":"HTTP"}' \
  --environment-variables "{\"LLM_PROVIDER\":\"bedrock\",\"BEDROCK_REGION\":\"${AWS_DEFAULT_REGION}\",\"BEDROCK_MODEL\":\"${BEDROCK_MODEL}\",\"RISK_MODE\":\"paper\",\"AGENT_TOOL_K_SCALE\":\"2\"}" \
  >/dev/null

echo "▸ 等 READY"
until [ "$(aws bedrock-agentcore-control get-agent-runtime --agent-runtime-id "$AGENTCORE_ID" \
          --query status --output text)" = "READY" ]; do
  sleep 10
done

# CLI 不吃非 ASCII 的 --payload 字串（會噴 "string argument should contain only ASCII
# characters"），必須經由檔案走 fileb://
echo "▸ 實際 invoke 一次"
TMP=$(mktemp -d)
printf '%s' '{"prompt":"現在 BTC 多少錢？","stream":false}' > "$TMP/payload.json"
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn "$AGENTCORE_ARN" \
  --runtime-session-id "deploy-smoke-$(date +%s)-000000000000000000000000000" \
  --content-type "application/json" \
  --payload "fileb://$TMP/payload.json" \
  "$TMP/out.json" >/dev/null
python3 -c "
import json;d=json.load(open('$TMP/out.json'));o=d.get('output',d)
print('  tools:',o.get('tools_used'));print('  answer:',(o.get('answer') or '')[:200])
"
rm -rf "$TMP"

echo "✓ AgentCore ${AGENTCORE_ID} READY"

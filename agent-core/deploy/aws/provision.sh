#!/usr/bin/env bash
# 一次性建立整套基礎設施。**現有環境已經跑過這支了** —— 它的用途是：
#   ① 這套部署到底做了什麼的可執行紀錄
#   ② 換一個 AWS 帳號（例如憑證換了新環境）要重來一次時照跑
#
#   ./deploy/aws/provision.sh
#
# 對已存在的資源會噴 AlreadyExists 然後往下走（每一步都包了 || true）。
# 跑完後 env.sh 裡的 ID/ARN 會對不上新帳號 —— 腳本末尾會印出新值，自己貼回 env.sh。
#
# 前置：VPC_ID / SUBNET_* 用的是該區的 default VPC。新帳號請先確認：
#   aws ec2 describe-subnets --filters Name=default-for-az,Values=true \
#     --query 'Subnets[].{Id:SubnetId,AZ:AvailabilityZone,Vpc:VpcId}' --output table

source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
_require_creds

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

echo "══ 1. ECR ══"
for r in maia-api maia-agentcore; do
  aws ecr create-repository --repository-name "$r" \
    --image-scanning-configuration scanOnPush=false >/dev/null 2>&1 || echo "  $r 已存在"
done

echo "══ 2. Secrets Manager ══"
# 從本機 .env 抽出真金鑰。佔位字串（your_xxx_here）與空值一律跳過，
# 免得把假 key 寫進去，之後在雲上除錯時分不清是「沒設」還是「設錯」。
python3 - "$AGENT_CORE/.env" "$TMP/secret.json" <<'PY'
import json, re, sys
KEYS = {"BINANCE_API_KEY","BINANCE_SECRET","OKX_API_KEY","OKX_SECRET","OKX_PASSPHRASE",
        "MAX_API_KEY","MAX_API_SECRET","BYBIT_API_KEY","BYBIT_SECRET",
        "COINGECKO_API_KEY","COINMARKETCAP_API_KEY","COINGLASS_API_KEY","COINALYZE_API_KEY",
        "SOSOVALUE_API_KEY","FRED_API_KEY","ALPHAVANTAGE_API_KEY",
        "MAIA_ADMIN_TOKEN","THREADS_ACCESS_TOKEN"}
out = {}
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line: continue
    k, v = line.split("=", 1); k = k.strip(); v = v.strip().strip('"').strip("'")
    if k in KEYS and v and not re.match(r"^your_.*_here$", v): out[k] = v
json.dump(out, open(sys.argv[2], "w"), indent=1)
print(f"  抓到 {len(out)} 把真金鑰：{', '.join(sorted(out))}")
PY
aws secretsmanager create-secret --name maia/app \
  --description "MAIA runtime API keys" \
  --secret-string "file://$TMP/secret.json" --query ARN --output text 2>/dev/null \
  || aws secretsmanager put-secret-value --secret-id maia/app \
       --secret-string "file://$TMP/secret.json" --query ARN --output text

echo "══ 3. IAM ══"
cat > "$TMP/trust-ecs.json" <<'EOF'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}
EOF
cat > "$TMP/trust-agentcore.json" <<EOF
{"Version":"2012-10-17","Statement":[{
  "Effect":"Allow","Principal":{"Service":"bedrock-agentcore.amazonaws.com"},"Action":"sts:AssumeRole",
  "Condition":{"StringEquals":{"aws:SourceAccount":"${ACCOUNT_ID}"},
               "ArnLike":{"aws:SourceArn":"arn:aws:bedrock-agentcore:${AWS_DEFAULT_REGION}:${ACCOUNT_ID}:*"}}}]}
EOF
cat > "$TMP/pol-exec.json" <<EOF
{"Version":"2012-10-17","Statement":[
 {"Effect":"Allow","Action":["secretsmanager:GetSecretValue"],
  "Resource":"arn:aws:secretsmanager:${AWS_DEFAULT_REGION}:${ACCOUNT_ID}:secret:maia/app-*"}]}
EOF
cat > "$TMP/pol-task.json" <<EOF
{"Version":"2012-10-17","Statement":[
 {"Sid":"BedrockInvoke","Effect":"Allow","Action":["bedrock:InvokeModel","bedrock:InvokeModelWithResponseStream","bedrock:Converse","bedrock:ConverseStream"],"Resource":"*"},
 {"Sid":"ReportsBucket","Effect":"Allow","Action":["s3:GetObject","s3:PutObject","s3:DeleteObject","s3:ListBucket"],
  "Resource":["arn:aws:s3:::${REPORTS_BUCKET}","arn:aws:s3:::${REPORTS_BUCKET}/*"]},
 {"Sid":"StateTables","Effect":"Allow","Action":["dynamodb:GetItem","dynamodb:PutItem","dynamodb:UpdateItem","dynamodb:DeleteItem","dynamodb:Query","dynamodb:Scan","dynamodb:BatchGetItem","dynamodb:BatchWriteItem"],
  "Resource":["arn:aws:dynamodb:${AWS_DEFAULT_REGION}:${ACCOUNT_ID}:table/maia*","arn:aws:dynamodb:${AWS_DEFAULT_REGION}:${ACCOUNT_ID}:table/maia*/index/*"]},
 {"Sid":"Logs","Effect":"Allow","Action":["logs:CreateLogStream","logs:PutLogEvents","logs:DescribeLogStreams"],
  "Resource":"arn:aws:logs:${AWS_DEFAULT_REGION}:${ACCOUNT_ID}:log-group:/ecs/maia*"}]}
EOF
cat > "$TMP/pol-agentcore.json" <<EOF
{"Version":"2012-10-17","Statement":[
 {"Sid":"EcrPull","Effect":"Allow","Action":["ecr:GetAuthorizationToken","ecr:BatchGetImage","ecr:GetDownloadUrlForLayer","ecr:BatchCheckLayerAvailability"],"Resource":"*"},
 {"Sid":"Logs","Effect":"Allow","Action":["logs:CreateLogGroup","logs:CreateLogStream","logs:PutLogEvents","logs:DescribeLogGroups","logs:DescribeLogStreams"],"Resource":"arn:aws:logs:${AWS_DEFAULT_REGION}:${ACCOUNT_ID}:log-group:*"},
 {"Sid":"Telemetry","Effect":"Allow","Action":["xray:PutTraceSegments","xray:PutTelemetryRecords","cloudwatch:PutMetricData"],"Resource":"*"},
 {"Sid":"BedrockInvoke","Effect":"Allow","Action":["bedrock:InvokeModel","bedrock:InvokeModelWithResponseStream","bedrock:Converse","bedrock:ConverseStream"],"Resource":"*"},
 {"Sid":"WorkloadIdentity","Effect":"Allow","Action":["bedrock-agentcore:GetWorkloadAccessToken","bedrock-agentcore:GetWorkloadAccessTokenForJWT","bedrock-agentcore:GetWorkloadAccessTokenForUserId"],"Resource":"*"}]}
EOF
aws iam create-role --role-name maia-ecs-exec-role  --assume-role-policy-document "file://$TMP/trust-ecs.json" >/dev/null 2>&1 || true
aws iam attach-role-policy --role-name maia-ecs-exec-role --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy || true
aws iam put-role-policy --role-name maia-ecs-exec-role --policy-name maia-secrets-read --policy-document "file://$TMP/pol-exec.json"
aws iam create-role --role-name maia-task-role      --assume-role-policy-document "file://$TMP/trust-ecs.json" >/dev/null 2>&1 || true
aws iam put-role-policy --role-name maia-task-role --policy-name maia-runtime --policy-document "file://$TMP/pol-task.json"
aws iam create-role --role-name maia-agentcore-role --assume-role-policy-document "file://$TMP/trust-agentcore.json" >/dev/null 2>&1 || true
aws iam put-role-policy --role-name maia-agentcore-role --policy-name maia-agentcore-runtime --policy-document "file://$TMP/pol-agentcore.json"

echo "══ 4. 安全群組 ══"
# 先開 0.0.0.0/0，最後一步再收斂成只收 CloudFront。
# 中間這段期間可以直接 curl ALB 除錯 —— 收斂之後就不行了。
ALBSG=$(aws ec2 create-security-group --group-name maia-alb-sg --description "MAIA ALB ingress" \
          --vpc-id "$VPC_ID" --query GroupId --output text 2>/dev/null) \
  || ALBSG=$(aws ec2 describe-security-groups --filters Name=group-name,Values=maia-alb-sg --query 'SecurityGroups[0].GroupId' --output text)
TASKSG=$(aws ec2 create-security-group --group-name maia-task-sg --description "MAIA Fargate task" \
          --vpc-id "$VPC_ID" --query GroupId --output text 2>/dev/null) \
  || TASKSG=$(aws ec2 describe-security-groups --filters Name=group-name,Values=maia-task-sg --query 'SecurityGroups[0].GroupId' --output text)
aws ec2 authorize-security-group-ingress --group-id "$ALBSG"  --protocol tcp --port 80   --cidr 0.0.0.0/0        >/dev/null 2>&1 || true
aws ec2 authorize-security-group-ingress --group-id "$TASKSG" --protocol tcp --port 8000 --source-group "$ALBSG" >/dev/null 2>&1 || true
echo "  ALB=$ALBSG  TASK=$TASKSG"

echo "══ 5. ALB + target group ══"
# ⚠️ zsh 不會對未加引號的變數做 word splitting，所以 --subnets "$LIST" 會被當成
# 單一個 subnet id 而噴 InvalidSubnet。這些腳本一律用 bash shebang，並且把
# subnet 分開傳 —— 這是實際踩過的坑。
ALBARN=$(aws elbv2 create-load-balancer --name "$ALB_NAME" --type application --scheme internet-facing \
           --subnets "$SUBNET_A" "$SUBNET_B" "$SUBNET_C" --security-groups "$ALBSG" \
           --query 'LoadBalancers[0].LoadBalancerArn' --output text 2>/dev/null) \
  || ALBARN=$(aws elbv2 describe-load-balancers --names "$ALB_NAME" --query 'LoadBalancers[0].LoadBalancerArn' --output text)
TGARN=$(aws elbv2 create-target-group --name "$TG_NAME" --protocol HTTP --port 8000 --vpc-id "$VPC_ID" \
          --target-type ip --health-check-path /api/config --health-check-interval-seconds 30 \
          --health-check-timeout-seconds 10 --healthy-threshold-count 2 --unhealthy-threshold-count 5 \
          --query 'TargetGroups[0].TargetGroupArn' --output text 2>/dev/null) \
  || TGARN=$(aws elbv2 describe-target-groups --names "$TG_NAME" --query 'TargetGroups[0].TargetGroupArn' --output text)
aws elbv2 create-listener --load-balancer-arn "$ALBARN" --protocol HTTP --port 80 \
  --default-actions "Type=forward,TargetGroupArn=$TGARN" >/dev/null 2>&1 || true
# SSE 對話可以跑好幾分鐘。ALB 預設 idle timeout 是 60 秒，不改的話串到一半會被切斷。
aws elbv2 modify-load-balancer-attributes --load-balancer-arn "$ALBARN" \
  --attributes Key=idle_timeout.timeout_seconds,Value=300 >/dev/null
ALBDNS=$(aws elbv2 describe-load-balancers --load-balancer-arns "$ALBARN" --query 'LoadBalancers[0].DNSName' --output text)
echo "  ALB_DNS=$ALBDNS"

echo "══ 6. ECS cluster + log group ══"
aws ecs create-cluster --cluster-name "$ECS_CLUSTER" >/dev/null 2>&1 || true
aws logs create-log-group --log-group-name /ecs/maia-api >/dev/null 2>&1 || true
aws logs put-retention-policy --log-group-name /ecs/maia-api --retention-in-days 7

echo "══ 7. 前端桶（私有；只有 CloudFront 讀得到）══"
aws s3api create-bucket --bucket "$WEB_BUCKET" --region "$AWS_DEFAULT_REGION" \
  --create-bucket-configuration "LocationConstraint=$AWS_DEFAULT_REGION" >/dev/null 2>&1 || true
aws s3api put-public-access-block --bucket "$WEB_BUCKET" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

echo "══ 8. CloudFront（OAC + 兩個 origin）══"
OACID=$(aws cloudfront create-origin-access-control --origin-access-control-config \
          'Name=maia-web-oac,Description=MAIA static site,SigningProtocol=sigv4,SigningBehavior=always,OriginAccessControlOriginType=s3' \
          --query 'OriginAccessControl.Id' --output text 2>/dev/null) \
  || OACID="$CF_OAC_ID"
# CachePolicyId          658327ea… = 受管 CachingOptimized（靜態）
# CachePolicyId          4135ea2d… = 受管 CachingDisabled（API，SSE 絕不能快取）
# OriginRequestPolicyId  b689b0a8… = 受管 AllViewerExceptHostHeader（帶 cookie/query/header，去掉 Host）
cat > "$TMP/cf.json" <<EOF
{
  "CallerReference": "maia-$(date +%s)",
  "Comment": "MAIA — pixel world (S3) + agent API (ALB) on one origin",
  "Enabled": true, "DefaultRootObject": "index.html",
  "Origins": { "Quantity": 2, "Items": [
    { "Id": "s3-web", "DomainName": "${WEB_BUCKET}.s3.${AWS_DEFAULT_REGION}.amazonaws.com",
      "OriginAccessControlId": "${OACID}", "S3OriginConfig": { "OriginAccessIdentity": "" } },
    { "Id": "alb-api", "DomainName": "${ALBDNS}",
      "CustomOriginConfig": { "HTTPPort": 80, "HTTPSPort": 443, "OriginProtocolPolicy": "http-only",
        "OriginSslProtocols": { "Quantity": 1, "Items": ["TLSv1.2"] },
        "OriginReadTimeout": 60, "OriginKeepaliveTimeout": 60 } } ] },
  "DefaultCacheBehavior": {
    "TargetOriginId": "s3-web", "ViewerProtocolPolicy": "redirect-to-https",
    "AllowedMethods": { "Quantity": 2, "Items": ["GET","HEAD"], "CachedMethods": { "Quantity": 2, "Items": ["GET","HEAD"] } },
    "CachePolicyId": "658327ea-f89d-4fab-a63d-7e88639e58f6", "Compress": true },
  "CacheBehaviors": { "Quantity": 1, "Items": [
    { "PathPattern": "/api/*", "TargetOriginId": "alb-api", "ViewerProtocolPolicy": "redirect-to-https",
      "AllowedMethods": { "Quantity": 7, "Items": ["GET","HEAD","OPTIONS","PUT","POST","PATCH","DELETE"],
                          "CachedMethods": { "Quantity": 2, "Items": ["GET","HEAD"] } },
      "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
      "OriginRequestPolicyId": "b689b0a8-53d0-40ab-baf2-68738e2966ac", "Compress": false } ] },
  "PriceClass": "PriceClass_All", "HttpVersion": "http2and3"
}
EOF
DIST=$(aws cloudfront create-distribution --distribution-config "file://$TMP/cf.json" \
         --query 'Distribution.Id' --output text 2>/dev/null) || DIST="$CF_DIST_ID"
DISTDOMAIN=$(aws cloudfront get-distribution --id "$DIST" --query 'Distribution.DomainName' --output text)

# 桶政策綁死 distribution ARN：只有這一個 distribution 讀得到，換一個也不行
cat > "$TMP/bucketpol.json" <<EOF
{"Version":"2012-10-17","Statement":[{"Sid":"AllowCloudFrontOAC","Effect":"Allow",
 "Principal":{"Service":"cloudfront.amazonaws.com"},"Action":"s3:GetObject",
 "Resource":"arn:aws:s3:::${WEB_BUCKET}/*",
 "Condition":{"StringEquals":{"AWS:SourceArn":"arn:aws:cloudfront::${ACCOUNT_ID}:distribution/${DIST}"}}}]}
EOF
aws s3api put-bucket-policy --bucket "$WEB_BUCKET" --policy "file://$TMP/bucketpol.json"

echo "══ 9. 收斂 ALB 入口：只收 CloudFront ══"
# 做完這步就 curl 不到 ALB 了，除錯只能看 CloudWatch。
# 它擋掉的是「繞過 CloudFront 直連 ALB」—— 那條路是 http，session cookie 不會帶 Secure。
aws ec2 authorize-security-group-ingress --group-id "$ALBSG" \
  --ip-permissions "IpProtocol=tcp,FromPort=80,ToPort=80,PrefixListIds=[{PrefixListId=${PREFIX_LIST_CLOUDFRONT},Description=CloudFront only}]" >/dev/null 2>&1 || true
aws ec2 revoke-security-group-ingress --group-id "$ALBSG" --protocol tcp --port 80 --cidr 0.0.0.0/0 >/dev/null 2>&1 || true

cat <<EOF

══ 完成。把下面的值貼回 env.sh ══
  SG_ALB="$ALBSG"
  SG_TASK="$TASKSG"
  ALB_DNS="$ALBDNS"
  TG_ARN="$TGARN"
  WEB_BUCKET="$WEB_BUCKET"
  CF_DIST_ID="$DIST"
  CF_DOMAIN="$DISTDOMAIN"
  CF_OAC_ID="$OACID"

接著跑（task definition 在 register-taskdef.sh，要先有它才能起 service）：
  ./deploy/aws/register-taskdef.sh
  ./deploy/aws/deploy-backend.sh
  ./deploy/aws/deploy-frontend.sh
  ./deploy/aws/deploy-agentcore.sh
EOF

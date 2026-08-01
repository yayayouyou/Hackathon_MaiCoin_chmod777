#!/usr/bin/env bash
# 把黑客松給的臨時 AWS 憑證匯入本機（寫成 ~/.aws 的具名 profile），供 AWS CLI 與 boto3 共用。
# macOS / Linux 版；Windows 請用同目錄的 aws_creds_import.ps1。
#
# 為什麼需要這支：活動頁給的 `export AWS_...="..."` 區塊直接貼進終端機是會動，但只對
# 「那一個」視窗有效 —— 你在別的視窗、IDE 內開的 shell、或 uvicorn 子行程全都看不到。
# 這是「我明明已經貼上 token 了，程式卻說找不到憑證」的標準成因。
# 寫成 profile 後：① 任何新終端機都吃得到 ② AWS CLI 與 boto3 走同一份 ③ 續期重跑一次即可。
#
# 用法：
#   複製活動頁的憑證區塊後 ->  ./scripts/aws_creds_import.sh          # 讀剪貼簿（pbpaste）
#   ./scripts/aws_creds_import.sh -f creds.txt                        # 從檔案讀
#   pbpaste | ./scripts/aws_creds_import.sh                           # 從 stdin 讀
#   ./scripts/aws_creds_import.sh -p hackathon -r us-east-1           # 指定 profile / region
set -euo pipefail

PROFILE="hackathon"
REGION="us-west-2"
FILE=""

die() { printf '\033[31m[FAIL]\033[0m %s\n' "$1" >&2; exit 1; }

while getopts ":p:r:f:h" opt; do
  case "$opt" in
    p) PROFILE="$OPTARG" ;;
    r) REGION="$OPTARG" ;;
    f) FILE="$OPTARG" ;;
    h) sed -n '2,18p' "$0"; exit 0 ;;
    *) die "未知參數：-$OPTARG（用 -h 看說明）" ;;
  esac
done

command -v aws >/dev/null 2>&1 || die "找不到 aws CLI。macOS：brew install awscli"

# ---- 取得輸入：-f 檔案 > stdin（被導入時）> 剪貼簿 ----
if [ -n "$FILE" ]; then
  [ -f "$FILE" ] || die "找不到檔案：$FILE"
  RAW="$(cat "$FILE")"
elif [ ! -t 0 ]; then
  RAW="$(cat)"
elif command -v pbpaste >/dev/null 2>&1; then
  echo "未提供 -f，改讀剪貼簿..."
  RAW="$(pbpaste)"
else
  die "沒有輸入來源。用 -f 指定檔案，或用管線把憑證區塊導進來。"
fi
[ -n "${RAW//[[:space:]]/}" ] || die "輸入是空的。請先複製憑證區塊。"

# ---- 解析：容忍 export / set 前綴，引號可有可無 ----
get() {
  printf '%s\n' "$RAW" | sed -nE \
    "s/^[[:space:]]*(export[[:space:]]+|set[[:space:]]+)?$1[[:space:]]*=[[:space:]]*[\"']?([^\"'[:space:]]+)[\"']?[[:space:]]*\$/\2/p" \
    | tail -n1
}

AKID="$(get AWS_ACCESS_KEY_ID)"
SKEY="$(get AWS_SECRET_ACCESS_KEY)"
TOKEN="$(get AWS_SESSION_TOKEN)"
[ -n "$TOKEN" ] || TOKEN="$(get AWS_SECURITY_TOKEN)"   # 舊名
FOUND_REGION="$(get AWS_DEFAULT_REGION)"
[ -n "$FOUND_REGION" ] || FOUND_REGION="$(get AWS_REGION)"
[ -z "$FOUND_REGION" ] || REGION="$FOUND_REGION"

[ -n "$AKID" ] && [ -n "$SKEY" ] \
  || die "解析不到 AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY。請確認貼進來的內容包含這兩行。"
# ASIA 開頭 = STS 臨時憑證，沒有 session token 一定 InvalidClientTokenId
case "$AKID" in
  ASIA*) [ -n "$TOKEN" ] || die "這是臨時憑證（ASIA 開頭）但缺少 AWS_SESSION_TOKEN。請把三行一起複製。" ;;
esac

# ---- 寫入 profile（aws configure set 只換掉該 profile 的欄位，其他 profile 原樣保留）----
aws configure set aws_access_key_id     "$AKID"  --profile "$PROFILE"
aws configure set aws_secret_access_key "$SKEY"  --profile "$PROFILE"
if [ -n "$TOKEN" ]; then
  aws configure set aws_session_token   "$TOKEN" --profile "$PROFILE"
fi
aws configure set region "$REGION" --profile "$PROFILE"
aws configure set output json     --profile "$PROFILE"

printf '\n\033[32m[ OK ]\033[0m 已寫入 profile '"'"'%s'"'"'（access key ...%s，region %s）\n' \
  "$PROFILE" "${AKID: -4}" "$REGION"
printf '       檔案：%s/.aws/credentials 與 %s/.aws/config（不會進 Git）\n\n' "$HOME" "$HOME"
printf '接下來：\n'
printf '  1) 在 agent-core/.env 設 AWS_PROFILE=%s\n' "$PROFILE"
printf '  2) .venv/bin/python scripts/bedrock_check.py\n\n'
printf '憑證過期時（通常數小時）重新複製一次憑證區塊，再跑這支腳本即可。\n'

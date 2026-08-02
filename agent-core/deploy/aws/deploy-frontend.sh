#!/usr/bin/env bash
# 重新發佈像素世界前端：build → S3 → CloudFront 失效。
#
#   ./deploy/aws/deploy-frontend.sh
#
# 全程約 1 分鐘，其中大半是等 invalidation 生效。前端沒有任何後端網址需要設定 ——
# dist/config.js 的 apiBase 是空字串（同源），/api/* 由 CloudFront 的 behavior 導去 ALB。

source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
_require_creds

echo "▸ build"
cd "$FRONTEND"
npm run build

echo "▸ 上傳 assets（內容雜湊檔名 → 長快取）"
aws s3 sync dist/assets "s3://${WEB_BUCKET}/assets" \
  --cache-control "public,max-age=31536000,immutable" --delete

# index.html 與 config.js 是「不用重 build 就能換後端位址」的逃生口，必須每次回源
echo "▸ 上傳 index.html / config.js（no-cache）"
aws s3 cp dist/index.html "s3://${WEB_BUCKET}/index.html" \
  --cache-control "no-cache" --content-type "text/html; charset=utf-8"
aws s3 cp dist/config.js "s3://${WEB_BUCKET}/config.js" \
  --cache-control "no-cache" --content-type "application/javascript; charset=utf-8"

# PWA：manifest / service worker / 圖示都在 dist 根目錄（不在 assets/，沒有內容雜湊）。
# sw.js 一定要 no-cache —— 否則使用者的瀏覽器抱著舊 SW 不放，之後的更新永遠推不出去。
echo "▸ 上傳 PWA 檔（manifest / sw.js / 圖示）"
aws s3 cp dist/sw.js "s3://${WEB_BUCKET}/sw.js" \
  --cache-control "no-cache" --content-type "application/javascript; charset=utf-8"
aws s3 cp dist/manifest.webmanifest "s3://${WEB_BUCKET}/manifest.webmanifest" \
  --cache-control "no-cache" --content-type "application/manifest+json; charset=utf-8"
for f in icon-192.png icon-512.png icon-180.png favicon-32.png; do
  aws s3 cp "dist/$f" "s3://${WEB_BUCKET}/$f" \
    --cache-control "public,max-age=86400" --content-type "image/png"
done

echo "▸ CloudFront 失效"
INV=$(aws cloudfront create-invalidation --distribution-id "$CF_DIST_ID" \
        --paths '/*' --query 'Invalidation.Id' --output text)
aws cloudfront wait invalidation-completed --distribution-id "$CF_DIST_ID" --id "$INV"

echo "✓ https://${CF_DOMAIN}"

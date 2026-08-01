<#
.SYNOPSIS
    把黑客松給的臨時 AWS 憑證匯入本機（寫成 ~/.aws 的具名 profile），供 AWS CLI 與 boto3 共用。

.DESCRIPTION
    為什麼需要這支：黑客松發的是 STS 臨時憑證（三個一組、數小時到期），而活動頁面
    給的複製區塊是 bash 的 `export AWS_...="..."` 格式 —— 在 PowerShell 貼上去無效
    （PowerShell 要 $env:AWS_...="..."），而且只對「那一個」終端機視窗有效：
    你在別的視窗、或 IDE 內開的 shell、或 uvicorn 子行程，全都看不到。
    這是「我明明已經貼上 token 了，程式卻說找不到憑證」的標準成因。

    這支腳本把憑證寫進 ~/.aws/credentials 的一個 profile（預設名 hackathon），
    於是：① 任何新終端機都吃得到 ② AWS CLI 與 boto3 走同一份 ③ 續期只要重跑一次。
    只覆蓋該 profile 區塊，其他 profile 原樣保留。

    憑證不會被印出來（只顯示末 4 碼），也不會寫進專案目錄。

.EXAMPLE
    # 1) 從活動頁面複製整個憑證區塊（Ctrl+C），然後：
    .\scripts\aws_creds_import.ps1

.EXAMPLE
    # 2) 直接貼在參數裡（多行字串）
    .\scripts\aws_creds_import.ps1 -Text @'
    export AWS_ACCESS_KEY_ID="ASIA..."
    export AWS_SECRET_ACCESS_KEY="..."
    export AWS_SESSION_TOKEN="..."
    '@

.EXAMPLE
    # 3) 存成檔案再匯入，並指定 region / profile 名稱
    .\scripts\aws_creds_import.ps1 -Path .\creds.txt -Region us-east-1 -ProfileName hackathon
#>
[CmdletBinding()]
param(
    [string]$Text,
    [string]$Path,
    [string]$ProfileName = "hackathon",
    [string]$Region = "us-west-2"
)

$ErrorActionPreference = "Stop"

# ---- 取得輸入：-Text > -Path > 剪貼簿 ----
if ($Text) {
    $raw = $Text
} elseif ($Path) {
    if (-not (Test-Path $Path)) { throw "找不到檔案：$Path" }
    $raw = Get-Content -Raw -Path $Path
} else {
    Write-Host "未提供 -Text/-Path，改讀剪貼簿..." -ForegroundColor DarkGray
    $raw = Get-Clipboard -Raw
    if (-not $raw) { throw "剪貼簿是空的。請先複製憑證區塊，或用 -Text / -Path 指定。" }
}

# ---- 解析：容忍 export / set / $env: / 純 KEY=VALUE 四種寫法，引號可有可無 ----
function Get-CredValue {
    param([string]$Blob, [string]$Key)
    $m = [regex]::Match(
        $Blob,
        # 允許前綴 export / set / $env: ，等號兩側空白，值可用單雙引號包住
        '(?im)^\s*(?:export\s+|set\s+|\$env:)?' + [regex]::Escape($Key) + '\s*=\s*["'']?([^"''\r\n]+)["'']?\s*$'
    )
    if ($m.Success) { return $m.Groups[1].Value.Trim() }
    return $null
}

$akid  = Get-CredValue $raw "AWS_ACCESS_KEY_ID"
$skey  = Get-CredValue $raw "AWS_SECRET_ACCESS_KEY"
$token = Get-CredValue $raw "AWS_SESSION_TOKEN"
if (-not $token) { $token = Get-CredValue $raw "AWS_SECURITY_TOKEN" }  # 舊名
$reg   = Get-CredValue $raw "AWS_DEFAULT_REGION"
if (-not $reg) { $reg = Get-CredValue $raw "AWS_REGION" }
if ($reg) { $Region = $reg }

if (-not $akid -or -not $skey) {
    throw "解析不到 AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY。請確認貼進來的內容包含這兩行。"
}
if (-not $token -and $akid.StartsWith("ASIA")) {
    # ASIA 開頭 = STS 臨時憑證，沒有 session token 一定 InvalidClientTokenId
    throw "這是臨時憑證（ASIA 開頭）但缺少 AWS_SESSION_TOKEN。請把三行一起複製。"
}

# ---- 寫入 ~/.aws/credentials（只換掉目標 profile 區塊）----
$awsDir = Join-Path $HOME ".aws"
if (-not (Test-Path $awsDir)) { New-Item -ItemType Directory -Path $awsDir | Out-Null }
$credFile = Join-Path $awsDir "credentials"
$cfgFile  = Join-Path $awsDir "config"

function Set-IniSection {
    param([string]$File, [string]$Header, [string[]]$Body)
    $kept = New-Object System.Collections.Generic.List[string]
    if (Test-Path $File) {
        $inTarget = $false
        foreach ($line in (Get-Content -Path $File)) {
            if ($line -match '^\s*\[') {
                $inTarget = ($line.Trim() -eq $Header)
            }
            if (-not $inTarget) { $kept.Add($line) }
        }
    }
    # 去掉尾端空行後再接上新區塊，避免每次執行都長出一堆空行
    while ($kept.Count -gt 0 -and [string]::IsNullOrWhiteSpace($kept[$kept.Count - 1])) {
        $kept.RemoveAt($kept.Count - 1)
    }
    if ($kept.Count -gt 0) { $kept.Add("") }
    $kept.Add($Header)
    foreach ($b in $Body) { $kept.Add($b) }
    # ASCII，避免 BOM 讓 botocore 讀 config 時把第一個 section 名稱解析歪掉
    Set-Content -Path $File -Value $kept -Encoding ascii
}

$body = @("aws_access_key_id = $akid", "aws_secret_access_key = $skey")
if ($token) { $body += "aws_session_token = $token" }
Set-IniSection -File $credFile -Header "[$ProfileName]" -Body $body
Set-IniSection -File $cfgFile  -Header "[profile $ProfileName]" -Body @("region = $Region", "output = json")

# ---- 同時設進「當前這個」session，讓馬上接著跑的指令就吃得到 ----
$env:AWS_PROFILE = $ProfileName
$env:AWS_REGION  = $Region

$tail = if ($akid.Length -ge 4) { $akid.Substring($akid.Length - 4) } else { "????" }
Write-Host ""
Write-Host "[ OK ] 已寫入 profile '$ProfileName'（access key ...$tail，region $Region）" -ForegroundColor Green
Write-Host "       檔案：$credFile / $cfgFile（不會進 Git）" -ForegroundColor DarkGray
Write-Host ""
Write-Host "接下來：" -ForegroundColor Cyan
Write-Host "  1) 在 agent-core/.env 設 AWS_PROFILE=$ProfileName（已幫你設好就略過）"
Write-Host "  2) .\.venv\Scripts\python.exe scripts\bedrock_check.py"
Write-Host ""
Write-Host "憑證過期時（通常數小時）重新複製一次憑證區塊，再跑這支腳本即可。" -ForegroundColor DarkGray

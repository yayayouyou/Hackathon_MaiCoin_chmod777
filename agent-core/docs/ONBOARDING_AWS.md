# AWS 打通指南 — Bedrock 推理 + S3 報告匯出

> 給第一次要在本機跑 agent-core 後端的組員。順利的話 5 分鐘。
>
> 本文以 **macOS / Linux** 為主。Windows 只有第 2 步不一樣，見 [附錄 A](#附錄-awindows-powershell)。

## 這三步各自在做什麼

| 步驟 | 產出 | 憑證過期後要重做嗎 |
|---|---|:---:|
| 1 安裝相依 | `boto3 >= 1.40` | 否 |
| 2 匯入臨時憑證 | `~/.aws` 的 `hackathon` profile | **要，數小時一次** |
| 3 驗證 → 寫 `.env` | 這個帳號實際可用的 model id | 否 |

---

## 1. 安裝相依

```bash
cd agent-core
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # 第一次才需要
```

⚠️ **要用 Python 3.13，不要用 3.14。** 實測 3.14 會在 `coincurve==21.0.0` 卡住：它沒有 3.14 的 wheel，退回原始碼編譯時自己的 build hook 會噴 `RuntimeError: Expected exactly one LICENSE file in cffi distribution, got 0`，整個 `pip install` 中斷。3.13.9 全部 54 個套件一次裝完。

⚠️ **`boto3 >= 1.40` 不是可有可無的版本潔癖。** `bedrock-runtime.converse` 在 botocore 1.34.116 才進來，舊版拿到的是 `AttributeError` 而不是 `ClientError` —— 這是最容易被誤判成「程式壞了」的一種失敗。理由寫在 [requirements.txt:99-103](../requirements.txt#L99-L103)。

---

## 2. 匯入臨時憑證

先在活動頁面**複製整個憑證區塊**（三行 `export`），然後：

```bash
./scripts/aws_creds_import.sh
```

腳本讀剪貼簿，解析出三個值，寫進 `~/.aws/credentials` 的 `hackathon` profile。憑證不會被印出來（只顯示末 4 碼），也不會寫進專案目錄。

**為什麼不直接把那三行 `export` 貼進終端機？** 貼了確實會動 —— 但只對**那一個視窗**有效。你等一下在另一個視窗跑 `uvicorn`，它看不到那些環境變數，於是 `NoCredentialsError`。這是「我明明已經貼上 token 了，程式卻說找不到憑證」的標準成因。寫成 profile 之後：任何新終端機都吃得到、AWS CLI 與 boto3 走同一份、續期只要重跑一次。

其他輸入方式：

```bash
./scripts/aws_creds_import.sh -f creds.txt        # 從檔案
pbpaste | ./scripts/aws_creds_import.sh           # 從管線
./scripts/aws_creds_import.sh -p hackathon -r us-east-1
```

需要 `aws` CLI（`brew install awscli`）。

---

## 3. 驗證

```bash
.venv/bin/python scripts/bedrock_check.py
```

[bedrock_check.py](../scripts/bedrock_check.py) 依序打六個檢查點，並且**把這個帳號實際可用的 model id 印出來**，不用去 console 翻：

| # | 檢查 | 壞掉時的症狀 |
|---|---|---|
| 1 | SDK 有沒有 `converse` / `converse_stream` | `AttributeError` |
| 2 | 憑證解不解得開（STS） | `NoCredentialsError` / `ExpiredToken` |
| 3 | 列出可用模型與跨區推理設定檔 | — |
| 4 | 真的打一次 Converse | `AccessDenied` / `ValidationException` |
| 5 | ConverseStream（前端逐字輸出靠它） | 畫面卡住到最後一次性吐出 |
| 6 | 原生 function-calling | 模型叫不動任何工具 |

離開碼 0 = 全綠。只想看有哪些模型可用：`--list-only`。

全綠時腳本會直接把該填的值印在最後一行。

---

## 4. 寫進 `.env` — 是四行，不是三行

```bash
LLM_PROVIDER=bedrock
BEDROCK_REGION=us-west-2
BEDROCK_MODEL=us.anthropic.claude-opus-4-6-v1
AWS_PROFILE=hackathon        # ← 最容易漏掉的一行
```

⚠️ **step 3 印出來的清單「不等於」你有權限用。** `list_inference_profiles` 列的是該區域存在的推理設定檔，不是這個帳號被授權的模型。2026-08-01 實測本次 workshop 帳號：`claude-opus-5` / `4-8` / `4-7`、`sonnet-5`、`fable-5` 都在清單裡，但實際 Converse 一律 `AccessDeniedException: not available for this account`。**實際可用的最高階是 Opus 4.6**，另外 Opus 4.5 / 4.1、Sonnet 4.6 / 4.5、Haiku 4.5 也可用。

清單靠不住，唯一的判準是真的打一次。要重測（例如主辦方之後開了新權限）：

```bash
AWS_PROFILE=hackathon .venv/bin/python - <<'PY'
import boto3, botocore
c = boto3.client("bedrock-runtime", region_name="us-west-2")
for m in ["us.anthropic.claude-opus-5", "us.anthropic.claude-opus-4-8",
          "us.anthropic.claude-opus-4-6-v1", "us.anthropic.claude-sonnet-4-6"]:
    try:
        c.converse(modelId=m, messages=[{"role":"user","content":[{"text":"say OK"}]}],
                   inferenceConfig={"maxTokens":8})
        print("[ OK ]  ", m)
    except botocore.exceptions.ClientError as e:
        print("[DENIED]", m, "->", e.response["Error"]["Code"])
PY
```

**漏掉 `AWS_PROFILE` 會怎樣：** [aws_creds_import.sh](../scripts/aws_creds_import.sh) 把憑證寫進的是名為 `hackathon` 的 profile，不是 `default`。boto3 在沒有 `AWS_PROFILE` 時只找 `default`，於是 `NoCredentialsError` —— 而你剛剛才看到 step 3 全綠，很容易以為是別的問題。（step 3 會過，是因為腳本在它自己那個 shell session 裡臨時設了 `AWS_PROFILE`；換個視窗就沒了。）

`.env` 由 [agent/ollama_config.py:22](../agent/ollama_config.py#L22) 的 `load_dotenv(override=True)` 載入，`agent_ui/app.py` 一 import 就吃得到。

⚠️ **`BEDROCK_MODEL` 不要照抄 [.env.example:17](../.env.example#L17) 的預設值**（`us.anthropic.claude-3-5-sonnet-20241022-v2:0`，2024 年的）。另外，新模型多半只能用 `us.` / `eu.` / `apac.` 開頭的**跨區推理設定檔 id** 呼叫，直接填基礎模型 id 會吃 `ValidationException`。

---

## 5. S3 報告匯出（選配）

MAIA 完成市場／交易 DNA／回測分析後，可把報告以**私有、AES-256 加密**的 JSON 存進共用 bucket，並取得 15 分鐘有效的下載連結。

`.env` 再加兩行：

```bash
S3_REPORTS_BUCKET=maia-218322564712-20260801
AWS_DEFAULT_REGION=us-west-2
```

⚠️ S3 讀的是 `AWS_DEFAULT_REGION`，**跟 `BEDROCK_REGION` 是兩個不同的變數**（[app.py:661](../agent_ui/app.py#L661)），而它在 `.env.example` 裡是註解掉的。

### 呼叫方式

端點 `POST /api/reports/upload` 掛了跟下單同一道 same-origin 驗證，**必須帶 `X-Approval-Secret` 標頭**，否則 403。密鑰每次啟動隨機產生，從 `GET /api/config` 拿：

```bash
SECRET=$(curl -s localhost:8000/api/config \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["approval_secret"])')

curl -s -X POST localhost:8000/api/reports/upload \
  -H "Content-Type: application/json" \
  -H "X-Approval-Secret: $SECRET" \
  -d '{"title":"BTC 週報","report":{"summary":"demo"}}'
```

回應含 `download_url`（presigned，900 秒到期）與 `key`。

### 物件長什麼樣

| 項目 | 值 |
|---|---|
| Key | `reports/YYYY/MM/DD/maia-<亂數>.json` |
| 加密 | `ServerSideEncryption=AES256` |
| ACL | 私有（bucket 必須維持非公開） |
| 下載 | presigned URL，15 分鐘 |

### bucket 內的分區規劃

| 前綴 | 用途 | 狀態 |
|---|---|---|
| `reports/` | AI 分析、交易 DNA、回測與風控報告 | 已啟用 |
| `social/raw/` | Threads、X、Truth Social 貼文快照 | 規劃中 |
| `social/derived/` | 情緒分數、摘要與趨勢分析結果 | 規劃中 |

---

## 6. 憑證過期了

臨時憑證通常只有數小時。重新複製一次憑證區塊，重跑 step 2 那支腳本即可，`.env` 不用動。

---

## 常見錯誤對照表

| 看到的訊息 | 真正原因 | 解法 |
|---|---|---|
| `NoCredentialsError` | 沒設 `AWS_PROFILE`，boto3 去找 `default` | `.env` 補 `AWS_PROFILE=hackathon` |
| `ExpiredToken` / `InvalidClientTokenId` | 臨時憑證過期 | 重跑 step 2 |
| `ProfileNotFound` | `.env` 指了一個 `~/.aws` 裡沒有的 profile | 先跑 step 2 建立它 |
| `AttributeError` 提到 `converse` | botocore 太舊 | `pip install -U 'boto3>=1.40.0'` |
| `AccessDeniedException` | 該模型這個帳號沒授權（**清單裡有 ≠ 能用**） | 用 §4 的探測腳本找出真的可用的 id |
| `ValidationException` / `ResourceNotFound` | model id 打錯，或該區要用跨區推理設定檔 | 用 `us.` 開頭的 id |
| 上傳報告吃 `403` | 少帶 `X-Approval-Secret` | 見 §5 |
| 上傳報告吃 `503` | `S3_REPORTS_BUCKET` 沒設 | 見 §5 |

---

## 附錄 A：Windows（PowerShell）

只有第 2 步不同，改用 [aws_creds_import.ps1](../scripts/aws_creds_import.ps1)（行為與 `.sh` 版一致）：

```powershell
cd agent-core
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 先從活動頁複製整個憑證區塊，再跑（預設讀剪貼簿）
.\scripts\aws_creds_import.ps1

.\.venv\Scripts\python.exe scripts\bedrock_check.py
```

活動頁給的是 bash 的 `export AWS_...="..."`，**在 PowerShell 貼上去無效**（PowerShell 要 `$env:AWS_...="..."`）—— 這正是要用腳本的原因之一。

---

## 安全守則

- 憑證**不要**貼進群組聊天、GitHub 或 `.env`。走 `~/.aws` profile。
- `.env` 被 `.gitignore` 與 `.dockerignore` 雙重擋住，維持這樣。
- S3 bucket 維持私有，對外只給 presigned URL。

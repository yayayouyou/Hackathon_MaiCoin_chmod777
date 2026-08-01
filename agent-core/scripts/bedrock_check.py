#!/usr/bin/env python3
"""
scripts/bedrock_check.py — Bedrock 端到端連線檢查（憑證 → model access → Converse → 工具呼叫）。

為什麼需要：`tests/test_bedrock_provider.py` 用假的 boto3 client 把「訊息翻譯」釘住，
但它一行真實網路都不打。真正會在 demo 當天爆的是另外四件事，而且四件的錯誤訊息
長得很像（都是一個 botocore ClientError）：

    1. 沒憑證 / 憑證過期            → NoCredentialsError / ExpiredToken
    2. botocore 太舊，沒有 converse → AttributeError（不是 ClientError，最容易誤判成程式壞了）
    3. region 沒開 / 模型沒授權     → AccessDeniedException
    4. 模型 id 打錯 / 該區不支援    → ValidationException / ResourceNotFoundException

這支腳本把四者分開報，並且**印出這個帳號實際可用的模型 id**，不用去 console 翻。

用法：
    python scripts/bedrock_check.py                      # 全部檢查
    python scripts/bedrock_check.py --list-only          # 只列可用模型，不打推理
    python scripts/bedrock_check.py --region us-east-1
    python scripts/bedrock_check.py --model us.anthropic.claude-3-5-sonnet-20241022-v2:0

離開碼：0 = 全綠；1 = 有紅燈（CI / hook 可直接用）。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 掃描順序：命題常給的區域優先。列模型時會逐區試，找到就停。
CANDIDATE_REGIONS = ["us-west-2", "us-east-1", "ap-northeast-1", "eu-central-1"]

OK, FAIL, WARN, INFO = "[ OK ]", "[FAIL]", "[WARN]", "[INFO]"
_failed = False


def say(tag: str, msg: str) -> None:
    global _failed
    if tag == FAIL:
        _failed = True
    print(f"{tag} {msg}", flush=True)


def step_sdk() -> bool:
    """① SDK 版本與 converse 方法是否存在。"""
    try:
        import boto3
        import botocore
    except ImportError:
        say(FAIL, "未安裝 boto3。請 `pip install 'boto3>=1.40.0'`")
        return False
    say(INFO, f"boto3 {boto3.__version__} / botocore {botocore.__version__}")

    # 不需要憑證就能檢查方法是否存在（client 建立本身不打網路）。但若 .env 設了
    # AWS_PROFILE 指向一個還沒建立的 profile，boto3 在「建 client」這一步就會丟
    # ProfileNotFound —— 比 step_identity 更早，會蓋掉那邊的友善提示變成 traceback。
    # 這正是組員「設了 profile 但還沒匯入憑證」的常態，這裡先擋下來講白。
    from botocore.exceptions import ProfileNotFound
    try:
        c = boto3.client("bedrock-runtime", region_name="us-west-2")
    except ProfileNotFound:
        prof = os.getenv("AWS_PROFILE")
        say(FAIL, f"設了 AWS_PROFILE={prof} 但 ~/.aws 裡沒有這個 profile。"
                  f"先跑 `.\\scripts\\aws_creds_import.ps1`（貼上黑客松臨時憑證）建立它，"
                  f"或把 .env 的 AWS_PROFILE 註解掉改走環境變數 / IAM Role。")
        return False
    missing = [m for m in ("converse", "converse_stream") if not hasattr(c, m)]
    if missing:
        say(FAIL, f"botocore 太舊，bedrock-runtime 缺少 {missing}。"
                  f"請 `pip install -U 'boto3>=1.40.0'`（converse 需 botocore>=1.34.116）")
        return False
    say(OK, "bedrock-runtime 具備 converse / converse_stream")
    return True


def step_identity(region: str) -> bool:
    """② 憑證能不能解析（這一步失敗就不用往下了）。"""
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError, ProfileNotFound
    prof = os.getenv("AWS_PROFILE")
    if prof:
        say(INFO, f"使用 AWS_PROFILE={prof}")
    try:
        ident = boto3.client("sts", region_name=region).get_caller_identity()
    except ProfileNotFound:
        # .env 設了 AWS_PROFILE 但 ~/.aws 裡沒這個 profile —— 錯誤原文很難懂，這裡講白
        say(FAIL, f"~/.aws 裡找不到 profile `{prof}`。先跑 `.\\scripts\\aws_creds_import.ps1 "
                  f"-ProfileName {prof}` 建立它，或把 .env 的 AWS_PROFILE 註解掉")
        return False
    except NoCredentialsError:
        say(FAIL, "找不到 AWS 憑證。三種補法任選一："
                  "① 設 AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY/AWS_SESSION_TOKEN 環境變數；"
                  "② `aws configure sso` + 設 AWS_PROFILE；③ 在有 IAM Role 的環境跑（AgentCore/Lambda）")
        return False
    except (ClientError, BotoCoreError) as e:
        low = str(e).lower()
        if "expired" in low or "invalidclienttokenid" in low:
            say(FAIL, f"憑證已過期或無效（黑客松臨時憑證通常只有數小時）：{e}")
        else:
            say(FAIL, f"STS 呼叫失敗：{e}")
        return False
    # 只印 account 與 arn 的尾段，不印完整 arn 裡可能帶的使用者名稱以外資訊
    say(OK, f"憑證有效 — account={ident.get('Account')} arn={ident.get('Arn')}")
    return True


def step_list_models(region: str, scan_all: bool):
    """③ 這個帳號在這個 region 實際能用哪些模型。回傳 (region, [model_ids])。"""
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    regions = [region] if not scan_all else ([region] + [r for r in CANDIDATE_REGIONS if r != region])
    for reg in regions:
        bc = boto3.client("bedrock", region_name=reg)
        ids: list[str] = []

        # 跨區推理設定檔（us./eu./apac. 開頭）—— 新模型多半只能用這個叫
        try:
            for p in bc.list_inference_profiles(maxResults=100).get("inferenceProfileSummaries", []):
                pid = p.get("inferenceProfileId") or ""
                if pid:
                    ids.append(pid)
        except (ClientError, BotoCoreError) as e:
            say(WARN, f"{reg}: list_inference_profiles 失敗（不影響直呼 model id）：{type(e).__name__}")

        # 基礎模型（含未授權的，所以下面要標註 access）
        try:
            for m in bc.list_foundation_models().get("modelSummaries", []):
                mid = m.get("modelId") or ""
                if "TEXT" in (m.get("outputModalities") or []) and "ON_DEMAND" in (
                        m.get("inferenceTypesSupported") or []):
                    ids.append(mid)
        except (ClientError, BotoCoreError) as e:
            say(WARN, f"{reg}: list_foundation_models 失敗：{type(e).__name__}: {e}")

        if ids:
            say(OK, f"{reg}: 取得 {len(ids)} 個候選模型 id")
            claude = sorted({i for i in ids if "anthropic" in i.lower() or "claude" in i.lower()})
            print("      Anthropic/Claude 可選 id（優先用 us./eu./apac. 開頭的推理設定檔）：")
            for i in claude or ["（無）"]:
                print(f"        - {i}")
            others = sorted({i for i in ids if i not in claude})[:15]
            if others:
                print(f"      其他（前 15 個）：{', '.join(others)}")
            return reg, ids
        say(WARN, f"{reg}: 列不到任何模型（可能該區未啟用 Bedrock）")
    return region, []


def step_converse(region: str, model: str) -> bool:
    """④ 真的打一次 Converse（非串流）。這一步過了，agent 主迴圈就一定會動。"""
    from agent.llm.base import LLMError
    from agent.llm.bedrock import BedrockProvider
    try:
        p = BedrockProvider(model=model, region=region, timeout=60, max_retries=1)
        r = p.chat(messages=[{"role": "user", "content": "回答兩個字：測試通過"}], temperature=0.0)
    except LLMError as e:
        msg = str(e)
        low = msg.lower()
        if "accessdenied" in low:
            say(FAIL, f"model access 被拒。到 Bedrock console → Model access 申請 `{model}`，"
                      f"或改用該帳號已授權的 id。原文：{msg[:300]}")
        elif "validationexception" in low or "resourcenotfound" in low:
            say(FAIL, f"模型 id `{model}` 在 {region} 不可用（打錯或該區不支援；"
                      f"新模型多半要用 us. 開頭的跨區推理設定檔）。原文：{msg[:300]}")
        elif "expired" in low or "credential" in low:
            say(FAIL, f"憑證問題：{msg[:300]}")
        else:
            say(FAIL, f"Converse 失敗：{msg[:400]}")
        return False
    say(OK, f"Converse 成功（{region} / {model}）→ 模型回覆：{r.content[:80]!r}")
    return True


def step_stream(region: str, model: str) -> bool:
    """⑤ ConverseStream。前端的逐字輸出靠它；壞了畫面會整段卡住才一次噴完。"""
    from agent.llm.base import LLMError
    from agent.llm.bedrock import BedrockProvider
    try:
        p = BedrockProvider(model=model, region=region, timeout=60, max_retries=1)
        deltas, final = 0, None
        for kind, payload in p.chat_stream(
                messages=[{"role": "user", "content": "用一句話說明什麼是比特幣"}], temperature=0.0):
            if kind == "delta":
                deltas += 1
            elif kind == "final":
                final = payload
    except LLMError as e:
        say(FAIL, f"ConverseStream 失敗：{str(e)[:300]}")
        return False
    if deltas == 0:
        say(WARN, "串流沒有收到任何 delta（前端會看到死畫面直到最後一次性吐出）")
        return True
    say(OK, f"ConverseStream 成功 — {deltas} 個增量、共 {len((final.content if final else ''))} 字")
    return True


def step_tool_use(region: str, model: str) -> bool:
    """⑥ 原生 function-calling。整個 agent 的命脈；模型不吐 toolUse 就等於沒有工具。"""
    from agent.llm.base import LLMError
    from agent.llm.bedrock import BedrockProvider
    tools = [{
        "type": "function",
        "function": {
            "name": "get_price",
            "description": "查詢某個加密貨幣交易對的最新價格",
            "parameters": {
                "type": "object",
                "properties": {"symbol": {"type": "string", "description": "例如 BTC/USDT"}},
                "required": ["symbol"],
            },
        },
    }]
    try:
        p = BedrockProvider(model=model, region=region, timeout=60, max_retries=1)
        r = p.chat(messages=[{"role": "user", "content": "幫我查 BTC/USDT 現在多少錢"}],
                   tools=tools, temperature=0.0)
    except LLMError as e:
        say(FAIL, f"工具呼叫測試失敗：{str(e)[:300]}")
        return False
    if not r.tool_calls:
        say(WARN, f"模型沒有發出 toolUse（該模型可能不支援 tool use）。回覆：{r.content[:120]!r}")
        return True
    tc = r.tool_calls[0]
    say(OK, f"原生 function-calling 正常 — 模型要求呼叫 {tc.name}({tc.args})")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Bedrock 端到端連線檢查")
    ap.add_argument("--region", default=os.getenv("BEDROCK_REGION") or os.getenv("AWS_REGION") or "us-west-2")
    ap.add_argument("--model", default=None, help="預設讀 BEDROCK_MODEL，再退回 provider 內建值")
    ap.add_argument("--list-only", action="store_true", help="只列可用模型，不打推理")
    ap.add_argument("--no-scan", action="store_true", help="不要跨區掃描，只看 --region")
    args = ap.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    print("=" * 68)
    print(f"Bedrock 連線檢查 — region={args.region}")
    print("=" * 68)

    if not step_sdk():
        return 1
    if not step_identity(args.region):
        return 1

    region, ids = step_list_models(args.region, scan_all=not args.no_scan)
    if args.list_only:
        return 1 if _failed else 0

    from agent.llm.bedrock import DEFAULT_BEDROCK_MODEL
    model = args.model or os.getenv("BEDROCK_MODEL") or DEFAULT_BEDROCK_MODEL
    if ids and model not in ids:
        say(WARN, f"`{model}` 不在 {region} 的可用清單裡，仍會試打一次（清單不一定完整）")

    print("-" * 68)
    if step_converse(region, model):
        step_stream(region, model)
        step_tool_use(region, model)

    print("=" * 68)
    if _failed:
        print("結果：有紅燈，見上方 [FAIL]")
        return 1
    print(f"結果：全綠。把這兩行寫進 .env 即可切換：\n"
          f"  LLM_PROVIDER=bedrock\n  BEDROCK_REGION={region}\n  BEDROCK_MODEL={model}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

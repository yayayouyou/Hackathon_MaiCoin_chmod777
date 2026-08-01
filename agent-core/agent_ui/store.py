"""
agent_ui/store.py — 玩家與登入 session 的 DynamoDB 存取層

兩張表，欄位都很小：

    maia_players    PK=username   帳號身分（密碼雜湊）+ 世界進度（暱稱/角色/立場/收藏）
    maia_sessions   PK=token      登入 session；expires_at 設為 DynamoDB TTL 屬性

**boto3 resource 一律延遲建立。** `agent_ui/app.py` 一被 import 就會連鎖 import 到這裡，
而 agent-core 的 46 個 pytest 檔在沒有 AWS 憑證的機器上也必須跑得完 —— 在 module 層建
client 等於把「跑測試」變成「要先有 AWS 帳號」。

本機開發把 `DYNAMODB_ENDPOINT_URL` 指向 DynamoDB Local 就好，其餘程式碼一個字不用改。
"""

import os
import time
from typing import Any, Dict, List, Optional

_PLAYERS_TABLE = os.getenv("MAIA_PLAYERS_TABLE", "maia_players")
_SESSIONS_TABLE = os.getenv("MAIA_SESSIONS_TABLE", "maia_sessions")

_resource = None


def _db():
    """延遲建立並快取 boto3 DynamoDB resource。

    region 讀 `AWS_DEFAULT_REGION`，與 S3 報告匯出（app.py 的 upload_report_to_s3）
    同一個變數 —— Bedrock 用的是另一個 `BEDROCK_REGION`，這兩個在本專案裡刻意分開，
    詳見 docs/ONBOARDING_AWS.md §5。
    """
    global _resource
    if _resource is None:
        import boto3
        _resource = boto3.resource(
            "dynamodb",
            region_name=os.getenv("AWS_DEFAULT_REGION") or None,
            # 只有本機 DynamoDB Local 會設這個；正式環境維持 None 走真正的 AWS 端點
            endpoint_url=os.getenv("DYNAMODB_ENDPOINT_URL") or None,
        )
    return _resource


def _players():
    return _db().Table(_PLAYERS_TABLE)


def _sessions():
    return _db().Table(_SESSIONS_TABLE)


def reset_cache() -> None:
    """丟掉快取的 resource。測試在 monkeypatch 環境變數後用得到。"""
    global _resource
    _resource = None


# ────────────────────────── 玩家 ──────────────────────────

def get_player(username: str) -> Optional[Dict[str, Any]]:
    return _players().get_item(Key={"username": username}).get("Item")


def create_player(item: Dict[str, Any]) -> bool:
    """建立玩家。帳號已存在時回 False。

    用 DynamoDB 的條件寫入而不是「先 get 再 put」：後者在兩個人同時註冊同一個帳號時，
    兩邊的 get 都會回空，然後後寫的那個**靜默覆蓋**先註冊的人的密碼。條件寫入把這件事
    交給資料庫做原子判斷。
    """
    from botocore.exceptions import ClientError
    try:
        _players().put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(username)",
        )
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise


def update_progress(username: str, progress: Dict[str, Any]) -> None:
    """只更新世界進度欄位，不碰密碼雜湊。

    白名單而不是直接把前端送來的 dict 展開：否則一個 `{"password_hash": "..."}`
    的請求就能改掉別人的密碼，或一個 `{"role": "official"}` 就能自己升成官方帳號。
    """
    allowed = ("nickname", "character", "stance", "favorites")
    fields = {k: progress[k] for k in allowed if k in progress}
    if not fields:
        return

    # DynamoDB 的保留字很多（name、status…），一律走 #alias 比逐個判斷安全
    names = {f"#{k}": k for k in fields}
    values = {f":{k}": v for k, v in fields.items()}
    names["#u"] = "updated_at"
    values[":u"] = now_iso()
    sets = ", ".join(f"#{k} = :{k}" for k in fields) + ", #u = :u"

    _players().update_item(
        Key={"username": username},
        UpdateExpression=f"SET {sets}",
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def set_role(username: str, role: str) -> bool:
    """設定玩家角色。帳號不存在時回 False，不會憑空建出一個帳號。

    刻意沒有對應的 HTTP 端點 —— 授予官方身分只能從後台（scripts/grant_official.py）
    執行。任何「讓已登入者改自己 role」的路徑都等於把權限系統交給使用者自己決定。
    """
    from botocore.exceptions import ClientError
    try:
        _players().update_item(
            Key={"username": username},
            UpdateExpression="SET #r = :r, #u = :u",
            ExpressionAttributeNames={"#r": "role", "#u": "updated_at"},
            ExpressionAttributeValues={":r": role, ":u": now_iso()},
            ConditionExpression="attribute_exists(username)",
        )
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise


# ────────────────────────── Session ──────────────────────────

def create_session(token: str, username: str, ttl_seconds: int) -> None:
    now = int(time.time())
    _sessions().put_item(Item={
        "token": token,
        "username": username,
        "created_at": now_iso(),
        # DynamoDB TTL 要的是 epoch 秒的 Number，不是 ISO 字串
        "expires_at": now + ttl_seconds,
    })


def get_session(token: str) -> Optional[Dict[str, Any]]:
    """取 session，過期的一律當作不存在。

    ⚠️ **不能只靠 DynamoDB TTL。** TTL 的刪除是背景批次，官方說明是「通常 48 小時內」——
    也就是說過期的 session 還會被 get 到很久。TTL 是幫我們省清理排程的，不是安全邊界；
    真正的判準是這裡這一行比較。
    """
    item = _sessions().get_item(Key={"token": token}).get("Item")
    if not item:
        return None
    if int(item.get("expires_at", 0)) <= int(time.time()):
        return None
    return item


def delete_session(token: str) -> None:
    _sessions().delete_item(Key={"token": token})


# ────────────────────────── 建表 ──────────────────────────

def create_tables() -> List[str]:
    """建立兩張表（已存在就跳過）。給 scripts/create_tables.py 呼叫，不在 import 期執行。"""
    from botocore.exceptions import ClientError
    created: List[str] = []

    for name in (_PLAYERS_TABLE, _SESSIONS_TABLE):
        key = "username" if name == _PLAYERS_TABLE else "token"
        try:
            _db().create_table(
                TableName=name,
                KeySchema=[{"AttributeName": key, "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": key, "AttributeType": "S"}],
                # 黑客松規模用量極低，PAY_PER_REQUEST 不必預估容量也不會超額計費
                BillingMode="PAY_PER_REQUEST",
            )
            _db().Table(name).wait_until_exists()
            created.append(name)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") != "ResourceInUseException":
                raise

    # TTL 只對 sessions 表有意義；重複設定是冪等的
    try:
        _db().meta.client.update_time_to_live(
            TableName=_SESSIONS_TABLE,
            TimeToLiveSpecification={"Enabled": True, "AttributeName": "expires_at"},
        )
    except Exception:  # noqa: BLE001
        # DynamoDB Local 對 TTL 的支援時好時壞，而 get_session() 本來就自己驗過期，
        # 設不起來只是少了自動清理，不影響正確性
        pass

    return created


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

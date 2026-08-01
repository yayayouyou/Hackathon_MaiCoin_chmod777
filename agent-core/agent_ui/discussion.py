"""
agent_ui/discussion.py — 討論室貼文的 DynamoDB 存取層

沿用 agent_ui/store.py 的形狀（延遲建立 resource、表名走環境變數），因為兩者
會被同一批測試與同一個容器共用，兩種寫法只會讓人以為它們的行為保證不同。

    maia_discussion_spaces  PK=space_id                討論室
    maia_discussion_posts   PK=space_id  SK=post_key   貼文

**post_key 的格式是 `<created_at 毫秒>#<亂數>`。** 用時間戳當排序鍵的前綴，Query 就能
直接依時間排序（DynamoDB 的 SK 是字典序，毫秒補零後與時間序一致）；接一段亂數是因為
同一毫秒內的兩篇貼文若只用時間戳會撞鍵，後寫的那篇會**靜默覆蓋**前一篇。
"""

import os
import secrets
import time
from typing import Any, Dict, List, Optional

_SPACES_TABLE = os.getenv("MAIA_DISCUSSION_SPACES_TABLE", "maia_discussion_spaces")
_POSTS_TABLE = os.getenv("MAIA_DISCUSSION_POSTS_TABLE", "maia_discussion_posts")

MAX_TEXT_LEN = 2000

_resource = None


def _db():
    global _resource
    if _resource is None:
        import boto3
        _resource = boto3.resource(
            "dynamodb",
            region_name=os.getenv("AWS_DEFAULT_REGION") or None,
            endpoint_url=os.getenv("DYNAMODB_ENDPOINT_URL") or None,
        )
    return _resource


def _posts():
    return _db().Table(_POSTS_TABLE)


def _spaces():
    return _db().Table(_SPACES_TABLE)


def reset_cache() -> None:
    global _resource
    _resource = None


def new_post_key(now_ms: Optional[int] = None) -> str:
    ms = now_ms if now_ms is not None else int(time.time() * 1000)
    # 13 碼零填充：毫秒時間戳到公元 2286 年都是 13 位，補零讓字典序等於時間序
    return f"{ms:013d}#{secrets.token_hex(4)}"


def create_post(space_id: str, author: str, author_role: str, text: str) -> Dict[str, Any]:
    """寫入一篇貼文並回傳它。

    `author` 與 `author_role` 一律由呼叫端從 session 取得後傳入，**不可以來自請求主體** ——
    否則任何人都能送一個 author_role=official 的請求把自己的發言標成官方。

    role 是**寫入當下的快照**，不是讀取時再查。原因有二：① 之後撤銷某人的官方身分時，
    他過去以官方名義發過的貼文不該追溯性地變成一般發言（那會讓歷史紀錄對不上已經同步
    出去的 Threads 貼文）；② 讀取時查等於每篇貼文多一次 DynamoDB 讀取。
    """
    now_ms = int(time.time() * 1000)
    item = {
        "space_id": space_id,
        "post_key": new_post_key(now_ms),
        "author": author,
        "author_role": author_role,
        "text": text[:MAX_TEXT_LEN],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_ms / 1000)),
        "likes": 0,
    }
    _posts().put_item(Item=item)
    return item


def list_posts(space_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """依時間由舊到新列出貼文。

    取最新的 `limit` 筆（ScanIndexForward=False 由新到舊），再反轉成聊天室的閱讀順序 ——
    直接正序取前 N 筆會拿到**最舊**的 N 筆，討論室永遠停在開版第一天。
    """
    from boto3.dynamodb.conditions import Key
    resp = _posts().query(
        KeyConditionExpression=Key("space_id").eq(space_id),
        ScanIndexForward=False,
        Limit=max(1, min(int(limit), 200)),
    )
    return list(reversed(resp.get("Items", [])))


def get_space(space_id: str) -> Optional[Dict[str, Any]]:
    return _spaces().get_item(Key={"space_id": space_id}).get("Item")


def create_tables() -> List[str]:
    """建立討論室兩張表（已存在就跳過）。給 scripts/create_tables.py 呼叫。"""
    from botocore.exceptions import ClientError
    created: List[str] = []

    specs = [
        (_SPACES_TABLE, [{"AttributeName": "space_id", "KeyType": "HASH"}],
         [{"AttributeName": "space_id", "AttributeType": "S"}]),
        (_POSTS_TABLE, [{"AttributeName": "space_id", "KeyType": "HASH"},
                        {"AttributeName": "post_key", "KeyType": "RANGE"}],
         [{"AttributeName": "space_id", "AttributeType": "S"},
          {"AttributeName": "post_key", "AttributeType": "S"}]),
    ]
    for name, keys, attrs in specs:
        try:
            _db().create_table(TableName=name, KeySchema=keys,
                               AttributeDefinitions=attrs, BillingMode="PAY_PER_REQUEST")
            _db().Table(name).wait_until_exists()
            created.append(name)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") != "ResourceInUseException":
                raise
    return created

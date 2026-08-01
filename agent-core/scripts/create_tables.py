#!/usr/bin/env python3
"""建立玩家登入與每日社群摘要所需的 DynamoDB 表。

討論室的兩張表不在這裡 —— 它們由 threads_bridge 使用，表名走
DYNAMODB_DISCUSSION_{SPACES,POSTS}_TABLE 環境變數指定既有的表，不由本腳本建立。

本機（DynamoDB Local）：
    docker run -d -p 8000:8000 --name maia-ddb amazon/dynamodb-local
    DYNAMODB_ENDPOINT_URL=http://localhost:8000 AWS_DEFAULT_REGION=us-west-2 \
      AWS_ACCESS_KEY_ID=dummy AWS_SECRET_ACCESS_KEY=dummy \
      python scripts/create_tables.py

⚠️ DynamoDB Local 預設也在 8000 埠，跟 uvicorn 撞。二選一改埠 ——
   下面的範例是把 DynamoDB Local 放 8001 的版本：
    docker run -d -p 8001:8000 --name maia-ddb amazon/dynamodb-local
    DYNAMODB_ENDPOINT_URL=http://localhost:8001 ...

正式 AWS：
    AWS_PROFILE=hackathon AWS_DEFAULT_REGION=us-west-2 python scripts/create_tables.py
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_ui import community_insights, store  # noqa: E402


def main() -> int:
    where = os.getenv("DYNAMODB_ENDPOINT_URL") or "AWS DynamoDB"
    print(f"目標：{where}（region={os.getenv('AWS_DEFAULT_REGION') or '預設'}）")
    try:
        created = store.create_tables() + community_insights.create_table()
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] 建表失敗：{e}")
        return 1

    if created:
        print(f"[ OK ] 已建立：{', '.join(created)}")
    else:
        print("[ OK ] 所有表都已存在，沒有動作")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""授予／撤銷官方帳號身分。

刻意只做成 CLI 而沒有 HTTP 端點：升級權限的路徑只要能從網路上呼叫，就得再設計一層
「誰能呼叫它」的驗證，而第一個官方帳號又是先有雞還是先有蛋。從後台執行避開整個問題。

    # 先註冊一個普通帳號，再升成官方
    AWS_PROFILE=hackathon AWS_DEFAULT_REGION=us-west-2 python scripts/grant_official.py maia_official

    # 撤銷
    AWS_PROFILE=hackathon AWS_DEFAULT_REGION=us-west-2 python scripts/grant_official.py maia_official --revoke

    # 查目前角色
    AWS_PROFILE=hackathon AWS_DEFAULT_REGION=us-west-2 python scripts/grant_official.py maia_official --show

本機 DynamoDB Local 則加 DYNAMODB_ENDPOINT_URL=http://localhost:8001（見 create_tables.py）。
"""

import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_ui import auth, store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="授予／撤銷官方帳號身分")
    ap.add_argument("username", help="要操作的帳號（大小寫不拘，會正規化成小寫）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--revoke", action="store_true", help="降回一般使用者")
    g.add_argument("--show", action="store_true", help="只顯示目前角色，不修改")
    args = ap.parse_args()

    username = auth.normalize_username(args.username)

    try:
        player = store.get_player(username)
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] 讀取失敗：{e}")
        return 1

    if not player:
        print(f"[FAIL] 找不到帳號 `{username}`。請先在前端註冊，再回來執行這支腳本。")
        return 1

    current = auth.role_of(player)
    if args.show:
        print(f"[INFO] `{username}` 目前是 {current}")
        return 0

    target = auth.ROLE_USER if args.revoke else auth.ROLE_OFFICIAL
    if current == target:
        print(f"[ OK ] `{username}` 已經是 {target}，沒有動作")
        return 0

    if not store.set_role(username, target):
        print(f"[FAIL] 設定失敗：`{username}` 在寫入前被刪除了")
        return 1

    print(f"[ OK ] `{username}`：{current} → {target}")
    if target == auth.ROLE_OFFICIAL:
        print("       該帳號目前開著的 session 立即生效（角色是每次請求即時查的，不存在 cookie 裡）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

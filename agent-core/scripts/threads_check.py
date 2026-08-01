#!/usr/bin/env python3
"""Read-only verification for the MAIA official Threads account token.

Usage (from agent-core):
    .\.venv\Scripts\python.exe scripts\threads_check.py
"""

import argparse
import os
import sys

import requests
from dotenv import load_dotenv


API_ROOT = "https://graph.threads.net"
TIMEOUT_SECONDS = 15


def request(path: str, fields: str, **params: object) -> dict:
    token = os.environ["THREADS_ACCESS_TOKEN"]
    response = requests.get(
        f"{API_ROOT}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params={"fields": fields, **params},
        timeout=TIMEOUT_SECONDS,
    )
    if not response.ok:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
    return response.json()


def publish_test_post() -> None:
    token = os.environ["THREADS_ACCESS_TOKEN"]
    text = "MAIA API 連線測試（可忽略）"
    create = requests.post(
        f"{API_ROOT}/me/threads",
        headers={"Authorization": f"Bearer {token}"},
        data={"media_type": "TEXT", "text": text},
        timeout=TIMEOUT_SECONDS,
    )
    if not create.ok:
        raise RuntimeError(f"create HTTP {create.status_code}: {create.text[:500]}")

    creation_id = create.json().get("id")
    if not creation_id:
        raise RuntimeError("create response did not include a creation id")
    publish = requests.post(
        f"{API_ROOT}/me/threads_publish",
        headers={"Authorization": f"Bearer {token}"},
        data={"creation_id": creation_id},
        timeout=TIMEOUT_SECONDS,
    )
    if not publish.ok:
        raise RuntimeError(f"publish HTTP {publish.status_code}: {publish.text[:500]}")
    print("[ OK ] threads_content_publish: test post published (post id hidden)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--publish-test",
        action="store_true",
        help="publish one visible 'MAIA API connection test' post",
    )
    args = parser.parse_args()
    load_dotenv()
    if not os.getenv("THREADS_ACCESS_TOKEN"):
        print("[FAIL] THREADS_ACCESS_TOKEN is empty in .env")
        return 1

    print("Threads connection check" + (" (includes publish test)" if args.publish_test else " (read-only)"))
    try:
        profile = request("/me", "id,username")
        print(f"[ OK ] threads_basic: @{profile.get('username', '(unknown)')} (id hidden)")
    except requests.RequestException as exc:
        print(f"[FAIL] network error: {exc}")
        return 1
    except RuntimeError as exc:
        print(f"[FAIL] Threads API rejected the request: {exc}")
        return 1

    failed = False
    checks = (
        ("threads_manage_mentions", "/me/mentions", "id,text,username,timestamp,permalink"),
        ("threads_read_replies", "/me/replies", "id,text,username,timestamp,permalink"),
    )
    for permission, path, fields in checks:
        try:
            data = request(path, fields, limit=1)
            print(f"[ OK ] {permission}: readable ({len(data.get('data', []))} item(s) on latest page)")
        except (requests.RequestException, RuntimeError) as exc:
            failed = True
            print(f"[FAIL] {permission}: {exc}")

    if failed:
        print("Result: token is valid, but one or more read permissions are missing.")
        return 1

    if args.publish_test:
        try:
            publish_test_post()
        except (requests.RequestException, RuntimeError) as exc:
            print(f"[FAIL] threads_content_publish: {exc}")
            return 1
    else:
        print("[INFO] threads_content_publish is not tested: use --publish-test to create a real post.")
    print("Result: Threads permissions checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

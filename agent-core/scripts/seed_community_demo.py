#!/usr/bin/env python3
"""Seed synthetic MAIA discussions for the daily-insight demo.

The topics are grounded in recent public research/protocol updates, but every
author and comment is fictional. With ``--publish-threads`` the same hierarchy
is published through MAIA's official Threads account and the remote ids are
saved back to DynamoDB.

Preview (defaults to today's Taipei date for the live "today" demo):
    python scripts/seed_community_demo.py

Write the records and generate summaries:
    python scripts/seed_community_demo.py --apply --publish-threads --generate
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TAIPEI = ZoneInfo("Asia/Taipei")
SEED_VERSION = "community-demo-2026-08-v1"

SOURCES = {
    "btc_flows": "https://www.coinbase.com/en-ca/institutional/research-insights/research",
    "btc_monitor": "https://www.imfconnect.org/content/dam/imf/News%20and%20Generic%20Content/GMM/Special%20Features/Crypto%20Monitor%20Q1%202026.pdf",
    "eth_priorities": "https://blog.ethereum.org/2026/02/18/protocol-priorities-update-2026",
    "eth_roadmap": "https://ethereum.org/roadmap/",
    "sol_upgrades": "https://solana.com/uk/upgrades",
    "sol_fees": "https://solana.com/docs/core/fees",
}

ROOMS: list[dict[str, Any]] = [
    {
        "slug": "btc-etf-flows",
        "title": "Demo｜BTC ETF 資金回流，是趨勢反轉還是短線補倉？",
        "source": SOURCES["btc_flows"],
        "posts": [
            ("鏈上阿哲", "coin_azhe", "近期機構研究又把焦點拉回 ETF 資金與市場部位。我比較想知道，連續流入代表長線配置回來了，還是只是前一波去槓桿後的補倉？"),
            ("風控小林", "risk_lin", "我不會只看單日淨流入。若價格反彈但現貨成交量沒有同步放大，可能只是資金輪動，不能直接解讀成新一輪趨勢。"),
            ("定投阿姨", "dca_auntie", "對長期配置的人來說，ETF 讓進出更方便，但也可能讓 BTC 更受美股交易時段與風險資產情緒影響。我的做法還是分批，不追單日數字。"),
            ("量化小周", "quant_zhou", "可以把 ETF 淨流量、期貨基差與永續資金費率一起看。若流入增加但基差快速擴張，裡面可能有不少套利盤，不全是方向性買盤。"),
            ("新手小雨", "newbie_yu", "所以真正的分歧不是 ETF 有沒有流入，而是這些流入能不能持續，以及是不是帶著過高槓桿，對嗎？"),
        ],
    },
    {
        "slug": "btc-risk-plan",
        "title": "Demo｜BTC 波動放大時，分批進場該看價格還是風險預算？",
        "source": SOURCES["btc_monitor"],
        "posts": [
            ("風控小林", "risk_lin", "近期機構資金進出變化很快，我認為分批策略應先決定最大可承受虧損，再回推每一批的部位，而不是先猜哪個價位一定是底。"),
            ("定投阿姨", "dca_auntie", "我會固定時間投入，但波動突然放大時把單次金額降一點。這樣不必猜底，也能保留後續加碼空間。"),
            ("鏈上阿哲", "coin_azhe", "如果長期持有者供給沒有明顯鬆動，我會把急跌看成觀察點；但鏈上訊號反應較慢，不能拿來決定很短線的進場。"),
            ("合約老吳", "futures_wu", "現貨分批和合約攤平不能混在一起。槓桿部位有清算線，越跌越加可能在方向判斷正確前就先被迫退出。"),
            ("新手小雨", "newbie_yu", "我整理成：先定總風險、分批只是執行方法，而且現貨與槓桿要用不同規則。這比直接問支撐價更實用。"),
        ],
    },
    {
        "slug": "eth-l1-l2",
        "title": "Demo｜ETH 擴容重心回到 L1，會改變 L2 的角色嗎？",
        "source": SOURCES["eth_priorities"],
        "posts": [
            ("DeFi工程師", "defi_dev", "Ethereum 2026 的協議優先事項同時談共識、執行與 blob 擴容。我覺得重點不是 L1 取代 L2，而是兩層之間的責任重新分配。"),
            ("Rollup研究員", "rollup_lab", "同意。L1 容量提高可以降低資料可用性壓力，但應用仍需要 L2 的客製執行環境。真正痛點是跨 L2 資產與帳戶體驗仍然割裂。"),
            ("錢包小陳", "wallet_chen", "一般使用者根本不想知道自己在哪條 L2。若互操作和帳戶抽象做不起來，再便宜的手續費也只是把複雜度轉嫁給使用者。"),
            ("Gas觀察員", "gas_watch", "我比較保守。提高容量後需求也可能跟著增加，不能假設費用會永久下降；節點硬體需求與去中心化成本也要一起評估。"),
            ("新手小雨", "newbie_yu", "這串看起來有共識的是體驗必須變簡單，分歧在於 L1 擴容能改善多少，以及會不會增加節點負擔。"),
        ],
    },
    {
        "slug": "eth-staking-ux",
        "title": "Demo｜ETH 質押門檻下降後，流動性與中心化風險怎麼平衡？",
        "source": SOURCES["eth_roadmap"],
        "posts": [
            ("驗證者No7", "validator_07", "質押機制持續改善，對小額參與者是好事；但多數人最後仍可能選大型服務商，操作門檻下降不一定等於驗證者更分散。"),
            ("DeFi工程師", "defi_dev", "流動質押讓資本效率提高，卻把協議風險、智能合約風險和脫鉤風險疊在一起。不能只比較名目收益率。"),
            ("定投阿姨", "dca_auntie", "如果是長期持有，我會在意退出時間、服務商費用和能不能自己保管。收益多一點，但鎖定規則看不懂，我寧願先不參加。"),
            ("治理小白", "dao_beginner", "我想知道大型質押池占比提高後，治理或區塊提議會不會太集中。這應該比短期 APR 高低更值得追蹤。"),
            ("驗證者No7", "validator_07", "可觀察的方向包括客戶端多樣性、節點營運者數量、最大服務商占比，以及獨立驗證者的實際成本。"),
        ],
    },
    {
        "slug": "sol-capacity",
        "title": "Demo｜SOL 區塊容量升到 100M CU，真實需求跟得上嗎？",
        "source": SOURCES["sol_upgrades"],
        "posts": [
            ("Solana開發者", "sol_builder", "Solana 近期把主網區塊上限從 60M 提到 100M CU。對高頻應用是實質空間，但我更在意增加的容量最後被哪些交易使用。"),
            ("量化小周", "quant_zhou", "交易數增加不一定代表使用者增加。機器人、套利和失敗交易都可能灌高活動量，最好同時看付費用戶、DEX 有效成交與穩定幣轉帳。"),
            ("NFT老王", "nft_wang", "對 NFT 和遊戲來說，便宜與不卡頓比 TPS headline 重要。如果尖峰期間優先費仍突然上升，容量提升的體感就有限。"),
            ("風控小林", "risk_lin", "容量提高也要觀察驗證者硬體與頻寬負擔。如果只有大型節點跟得上，效能提升可能換來更高集中度。"),
            ("Solana開發者", "sol_builder", "所以驗證方式應該是：尖峰成功率、實際費用、非機器人用戶留存，以及不同規模驗證者是否能穩定跟上。"),
        ],
    },
    {
        "slug": "sol-finality-validators",
        "title": "Demo｜Alpenglow 更快確認，SOL 驗證者門檻會不會更高？",
        "source": SOURCES["sol_fees"],
        "posts": [
            ("驗證者No7", "validator_07", "更快 finality 對支付與交易體驗很有吸引力，但協議升級不能只看毫秒數，也要看離線容錯假設和驗證者升級成本。"),
            ("Solana開發者", "sol_builder", "應用端最期待的是確認狀態更一致，減少錢包顯示成功、後端卻還在等待的落差。這會直接改善支付和鏈上交易 UX。"),
            ("節點小蔡", "node_tsai", "驗證者除了硬體，還有投票費、頻寬和維運人力。若新版要求持續提高，小型營運者可能只能依賴委託或退出。"),
            ("DeFi工程師", "defi_dev", "速度提升也可能讓 MEV 競爭更激烈。使用者得到更快確認，但排序權與基礎設施優勢是否更集中，需要另外量測。"),
            ("新手小雨", "newbie_yu", "我看到的主要分歧是：應用端很需要更快確認，但社群擔心效能提升的成本最後由小型驗證者承擔。"),
        ],
    },
]


def normalize_day(raw: str | None) -> str:
    return date.fromisoformat(raw).isoformat() if raw else datetime.now(TAIPEI).date().isoformat()


def build_records(day: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    local_day = date.fromisoformat(day)
    spaces: list[dict[str, Any]] = []
    posts: list[dict[str, Any]] = []
    for room_index, room in enumerate(ROOMS):
        room_id = f"demo-{room['slug']}"
        room_start = datetime.combine(local_day, time(9, 0), TAIPEI) + timedelta(minutes=room_index * 65)
        spaces.append({
            "space_id": room_id,
            "title": room["title"],
            "creator": room["posts"][0][0],
            "created_at": room_start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "archived": False,
            "demo_seed": SEED_VERSION,
            "synthetic": True,
            "reference_url": room["source"],
        })
        parent_id: str | None = None
        for post_index, (author, username, text_value) in enumerate(room["posts"]):
            post_id = f"{room_id}-p{post_index + 1}"
            created_at = room_start + timedelta(minutes=post_index * 9)
            posts.append({
                "space_id": room_id,
                "post_key": f"P#{post_id}",
                "id": post_id,
                "room_id": room_id,
                "author": author,
                "author_username": username,
                "author_role": "user",
                "source_author": author,
                "text": text_value,
                "source": "platform",
                "created_at": created_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "threads_id": None,
                "permalink": None,
                "sync_state": "demo",
                "is_thread_root": post_index == 0,
                "thread_root_id": None,
                "parent_post_id": parent_id,
                "threads_parent_id": None,
                "kind": "topic" if post_index == 0 else "comment",
                "demo_seed": SEED_VERSION,
                "synthetic": True,
                "reference_url": room["source"],
            })
            parent_id = post_id if post_index in {0, 2} else parent_id
    return spaces, posts


def _resource():
    import boto3
    return boto3.resource(
        "dynamodb",
        region_name=os.getenv("DYNAMODB_REGION") or os.getenv("AWS_DEFAULT_REGION") or None,
        endpoint_url=os.getenv("DYNAMODB_ENDPOINT_URL") or None,
    )


def write_records(
    spaces: list[dict[str, Any]],
    posts: list[dict[str, Any]],
    *,
    publish_threads: bool = False,
) -> None:
    spaces_name = (os.getenv("DYNAMODB_DISCUSSION_SPACES_TABLE") or "").strip()
    posts_name = (os.getenv("DYNAMODB_DISCUSSION_POSTS_TABLE") or "").strip()
    if not spaces_name or not posts_name:
        raise RuntimeError("DYNAMODB_DISCUSSION_SPACES_TABLE and DYNAMODB_DISCUSSION_POSTS_TABLE are required")
    resource = _resource()
    spaces_table = resource.Table(spaces_name)
    posts_table = resource.Table(posts_name)
    publish = None
    if publish_threads:
        from agent_ui.threads_bridge import publish_platform_post
        publish = publish_platform_post

    posts_by_room: dict[str, list[dict[str, Any]]] = {}
    for post in posts:
        posts_by_room.setdefault(str(post["space_id"]), []).append(dict(post))

    for source_space in spaces:
        space = dict(source_space)
        room_posts = sorted(posts_by_room[space["space_id"]], key=lambda item: item["created_at"])
        remote_by_local_id: dict[str, str] = {}
        root_threads_id: str | None = None
        for post in room_posts:
            existing = posts_table.get_item(
                Key={"space_id": post["space_id"], "post_key": post["post_key"]},
                ConsistentRead=True,
            ).get("Item")
            if existing and existing.get("demo_seed") == SEED_VERSION and existing.get("threads_id"):
                post.update({
                    "threads_id": existing["threads_id"],
                    "threads_parent_id": existing.get("threads_parent_id"),
                    "thread_root_id": existing.get("thread_root_id"),
                    "sync_state": "published",
                })
            elif publish:
                parent_threads_id = remote_by_local_id.get(str(post.get("parent_post_id") or "")) or root_threads_id
                remote = publish(post["author"], post["text"], parent_threads_id)
                post.update(remote)
                post["threads_parent_id"] = parent_threads_id
                post["sync_state"] = "published"
            if post.get("threads_id"):
                remote_by_local_id[post["id"]] = str(post["threads_id"])
                if post.get("is_thread_root"):
                    root_threads_id = str(post["threads_id"])
                post["thread_root_id"] = root_threads_id
            # Persist each successful publish immediately. A retry then reuses
            # its remote id instead of creating a duplicate Threads post.
            posts_table.put_item(Item=post)
        if root_threads_id:
            space["threads_root_id"] = root_threads_id
            space["discussion_root_threads_id"] = root_threads_id
        spaces_table.put_item(Item=space)


def main() -> int:
    load_dotenv(override=False)
    parser = argparse.ArgumentParser(description="Seed synthetic MAIA/Threads community discussions")
    parser.add_argument("--date", help="Taipei discussion date (YYYY-MM-DD); defaults to today for tomorrow's demo")
    parser.add_argument("--apply", action="store_true", help="write to the configured DynamoDB discussion tables")
    parser.add_argument("--publish-threads", action="store_true", help="publish the same roots/replies through the official Threads account")
    parser.add_argument("--generate", action="store_true", help="generate room and lobby insights after writing")
    args = parser.parse_args()
    day = normalize_day(args.date)
    spaces, posts = build_records(day)
    print(f"Demo date: {day} (Asia/Taipei)")
    print(f"Synthetic data: {len(spaces)} rooms, {len(posts)} posts, {len({p['author_username'] for p in posts})} users")
    for space in spaces:
        print(f"- {space['title']}")
    if not args.apply:
        print("Preview only. Re-run with --apply to write DynamoDB; Threads will not be called.")
        return 0
    if args.publish_threads and not args.apply:
        parser.error("--publish-threads requires --apply")
    write_records(spaces, posts, publish_threads=args.publish_threads)
    print("DynamoDB discussion seed completed.")
    if args.publish_threads:
        print("Threads roots/replies published and their remote ids saved to MAIA.")
    if args.generate:
        from agent_ui.community_insights import generate_daily_insights
        result = generate_daily_insights(day, force=True)
        print(f"Insight generation completed: rooms={result['rooms']} date={result['date']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

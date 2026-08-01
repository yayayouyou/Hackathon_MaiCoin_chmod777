"""
skills/market_intel/reddit_client.py

Reddit 社群輿情 — 基於 Arctic Shift 公開歸檔 API（免 key）
===========================================================
治本改版：原本匿名打 www.reddit.com/.../search.json，Reddit 於 2025-2026 對匿名端點
加了驗證牆，回 403 "Blocked"，匿名爬取已死。

改用 Arctic Shift（arctic-shift.photon-reddit.com，社群維護的 Reddit 歸檔 API，
免 key/OAuth/帳號）。實測其全文 query 參數不穩，故採更耐用的策略：抓 r/cryptocurrency
最近一批貼文，再『客戶端關鍵字過濾』出提到該幣的討論，並彙整讚數/留言數作為熱度訊號。

（長久最佳解為官方 Reddit Data API + async-praw，但需註冊 app 且審核約一週；
Arctic Shift 讓 agent 現在就能持續產出輿情，官方 app 核准後可再切為主來源。）
"""
from typing import Dict, Any, List
from datetime import datetime, timezone

from loguru import logger

from skills._http import fetch_json, FetchError

ARCTIC_POSTS_URL = "https://arctic-shift.photon-reddit.com/api/posts/search"


def _clean_post(p: Dict[str, Any]) -> Dict[str, Any]:
    created = p.get("created_utc") or 0
    try:
        pub = datetime.fromtimestamp(float(created), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        pub = None
    selftext = (p.get("selftext") or "").strip()
    if len(selftext) > 200:
        selftext = selftext[:200].rsplit(" ", 1)[0] + "…"
    permalink = p.get("permalink") or ""
    return {
        "title": (p.get("title") or "").strip(),
        "summary": selftext,
        "upvotes": int(p.get("score") or p.get("ups") or 0),
        "comments": int(p.get("num_comments") or 0),
        "url": f"https://www.reddit.com{permalink}" if permalink else (p.get("url") or ""),
        "published_at": pub,
    }


def fetch_reddit_sentiment(query: str, limit: int = 5, subreddit: str = "cryptocurrency") -> Dict[str, Any]:
    """
    【LLM Tool】在 Reddit 的 /r/cryptocurrency 中搜尋提到指定代幣的最新討論，分析社群零售情緒。

    Args:
        query: 搜尋關鍵字，如 'SOL', 'Solana', 'BTC'
        limit: 回傳貼文數量，預設 5，上限 10。
        subreddit: 子版（預設 cryptocurrency）
    """
    limit = max(1, min(10, limit))
    kw = (query or "").strip().lower()
    logger.info(f"抓取 Reddit /r/{subreddit} 有關 '{query}' 的討論（Arctic Shift）")

    try:
        # 抓最近一批（客戶端過濾更耐用），fetch_json 失敗即拋（不靜默）
        data = fetch_json(
            ARCTIC_POSTS_URL,
            params={"subreddit": subreddit, "limit": 100, "sort": "desc"},
            expect_keys=["data"],
        )
    except FetchError as e:
        logger.error(f"Reddit(Arctic Shift) 抓取失敗: {e}")
        return {"error": f"抓取 Reddit 輿情出錯: {e}"}

    raw: List[Dict[str, Any]] = data.get("data") or []
    matched = []
    for p in raw:
        blob = f"{p.get('title', '')} {p.get('selftext', '')}".lower()
        if not kw or kw in blob:
            matched.append(_clean_post(p))
        if len(matched) >= limit:
            break

    if not matched:
        return {"query": query, "subreddit": f"r/{subreddit}", "source": "Arctic Shift",
                "count": 0, "posts": [],
                "message": f"最近的 r/{subreddit} 貼文中未見提到 '{query}' 的討論"}

    total_up = sum(p["upvotes"] for p in matched)
    total_cm = sum(p["comments"] for p in matched)
    return {
        "query": query,
        "subreddit": f"r/{subreddit}",
        "source": "Arctic Shift",
        "count": len(matched),
        "buzz": {"total_upvotes": total_up, "total_comments": total_cm,
                 "avg_upvotes": round(total_up / len(matched), 1)},
        "posts": matched,
    }

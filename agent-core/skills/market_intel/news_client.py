"""
skills/market_intel/news_client.py

加密貨幣即時新聞 — 基於 feedparser + 多源 RSS
===========================================================
治本改版：原本手刻 xml.etree 解析『單一』CoinTelegraph RSS，對版面/日期格式/編碼
變動都很脆弱，且 fetched_at 蓋成 now() 掩蓋了 CDN 快取造成的過期。

改為維護中的 feedparser（穩健處理各種畸形 feed 與日期）+ 多來源（任一來源掛掉
其餘仍可用）；正確解析發佈時間並附 age_minutes 供判斷新鮮度；HTML 反轉義 +
斷詞截斷；90 秒 TTL 快取以省重複抓取。所有來源皆失敗才回 error（不靜默）。
"""
import re
import html
import time
import threading
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

import feedparser
from loguru import logger

from skills._http import session_get

# 多來源 RSS（主流媒體皆持續發佈；任一掛掉不影響整體）
NEWS_FEEDS = [
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Decrypt", "https://decrypt.co/feed"),
    ("CryptoSlate", "https://cryptoslate.com/feed/"),
]

_CACHE_TTL = 90.0  # 秒
_cache: Dict[str, Any] = {"ts": 0.0, "items": None, "failed": None}
_cache_lock = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean(text: str, cap: int = 240) -> str:
    t = html.unescape(re.sub(r"<[^>]*>", "", text or "")).strip()
    if len(t) > cap:
        t = t[:cap].rsplit(" ", 1)[0] + "…"   # 斷詞截斷，不切在字中間
    return t


def _parse_feed(name: str, url: str) -> List[Dict[str, Any]]:
    raw = session_get(url).content            # 走共用 Session（重試/連線重用/UA）
    parsed = feedparser.parse(raw)
    if getattr(parsed, "bozo", 0) and not parsed.entries:
        raise ValueError(f"feed 解析失敗或為空：{name}")
    items = []
    for e in parsed.entries:
        pub_iso: Optional[str] = None
        age_min: Optional[int] = None
        if e.get("published_parsed"):
            dt = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
            pub_iso = dt.isoformat()
            age_min = max(0, int((_now() - dt).total_seconds() / 60))
        items.append({
            "title": _clean(e.get("title", ""), 200),
            "link": e.get("link", ""),
            "summary": _clean(e.get("summary") or e.get("description") or ""),
            "published_at": pub_iso,
            "age_minutes": age_min,
            "author": e.get("author", ""),
            "source": name,
        })
    return items


def _fetch_all() -> Dict[str, Any]:
    """抓所有來源（帶 90s 快取），回 {items, failed}。"""
    with _cache_lock:
        if _cache["items"] is not None and (time.time() - _cache["ts"]) < _CACHE_TTL:
            return {"items": _cache["items"], "failed": _cache["failed"], "cached": True}

    all_items: List[Dict[str, Any]] = []
    failed: List[str] = []
    for name, url in NEWS_FEEDS:
        try:
            all_items.extend(_parse_feed(name, url))
        except Exception as e:  # noqa: BLE001 — 單一來源失敗不影響其餘
            logger.warning(f"新聞來源 {name} 抓取失敗：{e.__class__.__name__}")
            failed.append(name)

    # 依新鮮度排序（無日期者排後）
    all_items.sort(key=lambda x: x["age_minutes"] if x["age_minutes"] is not None else 1_000_000)
    with _cache_lock:
        _cache.update(ts=time.time(), items=all_items, failed=failed)
    return {"items": all_items, "failed": failed, "cached": False}


def get_latest_crypto_news(limit: int = 5) -> Dict[str, Any]:
    """
    【LLM Tool】獲取加密貨幣市場最新即時新聞頭條（多來源聚合），可用於評估市場情緒。

    Args:
        limit: 獲取的新聞條數限制，預設為 5，上限為 15。
    """
    limit = max(1, min(15, limit))
    logger.info(f"抓取多源加密新聞，限制 {limit} 條")
    got = _fetch_all()
    items = got["items"]
    if not items:
        return {"error": "所有新聞來源皆抓取失敗，請稍後再試", "failed_sources": got["failed"]}
    news = items[:limit]
    return {
        "sources": [n for n, _ in NEWS_FEEDS],
        "failed_sources": got["failed"],           # 空 = 全部正常
        "fetched_at": _now().isoformat(),
        "count": len(news),
        "news": news,
    }

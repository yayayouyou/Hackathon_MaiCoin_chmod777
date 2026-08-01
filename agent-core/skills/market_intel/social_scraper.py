"""
skills/market_intel/social_scraper.py

川普 (Truth Social) 與馬斯克 (Twitter/X) 名人社群言論抓取工具
============================================================
免 API 金鑰，使用公共嵌入網頁與開放存檔 Feed 抓取最新發言。
"""

import re
import json
import html
import email.utils
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from loguru import logger

from skills._http import session_get

TRUMP_TRUTH_FEED_URL = "https://trumpstruth.org/feed"                                  # 主源（小 RSS）
CNN_TRUTH_MIRROR_URL = "https://ix.cnn.io/data/truth-social/truth_archive.json"        # 備援（大檔，用 Range 只取開頭）
TWITTER_EMBED_BASE_URL = "https://syndication.twitter.com/srv/timeline-profile/screen-name/{screen_name}"

_STALE_HOURS = 24  # 最新貼文超過此時數 → 標記 stale（提醒可能過期，非錯誤）


def _post_age_hours(s: str) -> Optional[float]:
    """解析貼文時間（RFC2822 或 ISO），回傳距今小時數。"""
    if not s:
        return None
    dt = None
    try:
        dt = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError):
        pass
    if dt is None:
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return round((datetime.now(timezone.utc) - dt).total_seconds() / 3600, 1)


def _clean_text(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]*>", "", s or "")).strip()


def _fetch_trump_rss(limit: int) -> List[Dict[str, str]]:
    """主源：trumpstruth.org RSS。失敗會拋例外。"""
    resp = session_get(TRUMP_TRUTH_FEED_URL)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    posts = []
    for item in root.findall(".//item")[:limit]:
        title = (item.findtext("title") or "無標題").strip()
        desc = _clean_text(item.findtext("description") or "")
        if desc.startswith(title) and len(desc) > len(title):
            desc = desc[len(title):].strip()
        posts.append({"title": title, "text": desc,
                      "published_at": item.findtext("pubDate") or "", "url": item.findtext("link") or ""})
    return posts


def _fetch_trump_cnn_mirror(limit: int) -> List[Dict[str, str]]:
    """備援：CNN 鏡像（~19MB，newest-first）。用 HTTP Range 只取開頭 128KB，解析前幾則完整貼文。"""
    resp = session_get(CNN_TRUTH_MIRROR_URL, headers={"Range": "bytes=0-131072"}, timeout=(3.05, 20))
    if resp.status_code not in (200, 206):
        resp.raise_for_status()
    text = resp.text
    posts: List[Dict[str, str]] = []
    i = text.find("{")
    while i >= 0 and len(posts) < limit:
        depth, end = 0, -1
        for j in range(i, len(text)):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    end = j
                    break
        if end < 0:
            break  # 物件被 Range 截斷 → 停止
        try:
            obj = json.loads(text[i:end + 1])
            content = _clean_text(obj.get("content", ""))
            posts.append({"title": content[:80], "text": content,
                          "published_at": obj.get("created_at", ""), "url": obj.get("url", "")})
        except json.JSONDecodeError:
            pass
        i = text.find("{", end + 1)
    return posts


def fetch_trump_truth_posts(limit: int = 5) -> Dict[str, Any]:
    """
    【LLM Tool】抓取唐納·川普在 Truth Social 的最新貼文，用於分析其對加密市場的潛在情緒與政策影響。
    含『陳舊偵測』（latest_post_age_hours / feed_health）與『CNN 鏡像備援』（主源失敗時自動切換）。

    Args:
        limit: 獲取的貼文數量，預設 5，上限 15。
    """
    limit = max(1, min(15, limit))
    logger.info(f"抓取川普 Truth Social 最新言論，限制 {limit}")

    posts: List[Dict[str, str]] = []
    source = "trumpstruth.org (RSS)"
    primary_err = None
    try:
        posts = _fetch_trump_rss(limit)
    except Exception as e:  # noqa: BLE001
        primary_err = f"{e.__class__.__name__}: {e}"
        logger.warning(f"川普主源失敗，改試 CNN 鏡像備援：{primary_err}")

    # 備援：主源失敗或回空時，才動用大檔鏡像（Range 取開頭）
    if not posts:
        try:
            posts = _fetch_trump_cnn_mirror(limit)
            source = "CNN mirror (fallback)"
        except Exception as e2:  # noqa: BLE001
            logger.error(f"川普主源與備援皆失敗: primary={primary_err} fallback={e2}")
            return {"error": f"抓取川普 Truth Social 失敗（主源與備援皆不可用）: {primary_err or e2}",
                    "feed_health": "down"}

    if not posts:
        return {"error": "川普 Truth Social 無可用貼文", "feed_health": "down"}

    latest_age = _post_age_hours(posts[0].get("published_at", ""))
    stale = latest_age is not None and latest_age > _STALE_HOURS
    logger.success(f"抓取 {len(posts)} 條川普貼文（來源 {source}，最新 {latest_age} 小時前）")
    return {
        "source": source,
        "account": "realDonaldTrump",
        "count": len(posts),
        "latest_post_age_hours": latest_age,
        "feed_health": "stale" if stale else ("fallback" if "fallback" in source else "ok"),
        "posts": posts,
    }


def fetch_twitter_user_tweets(screen_name: str = "elonmusk", limit: int = 5) -> Dict[str, Any]:
    """
    【LLM Tool】免 Key 抓取指定 Twitter/X 使用者（如 elonmusk 或 realDonaldTrump）的最新推文列表與點讚轉發數。
    
    Args:
        screen_name: 使用者帳號，如 'elonmusk', 'realDonaldTrump'，預設為 'elonmusk'。
        limit: 返回的推文條數限制，預設 5，上限 15。
    """
    screen_name = screen_name.strip().replace("@", "")
    limit = max(1, min(15, limit))
    
    url = TWITTER_EMBED_BASE_URL.format(screen_name=screen_name)
    logger.info(f"正在抓取 X 使用者 '{screen_name}' 的最新推文 (Embed)，限制數量: {limit}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = session_get(url, headers=headers)
        response.raise_for_status()
        
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', response.text, re.DOTALL)
        if not m:
            logger.warning(f"無法在 X 嵌入頁面中解析出 __NEXT_DATA__。")
            return {"error": "解析 X 推文失敗，推文頁面格式不匹配或受到反爬蟲限制。"}
            
        data = json.loads(m.group(1))
        props = data.get("props", {})
        page_props = props.get("pageProps", {})
        timeline = page_props.get("timeline", {})
        entries = timeline.get("entries", [])
        
        tweets = []
        for entry in entries:
            if len(tweets) >= limit:
                break
                
            if entry.get("type") != "tweet":
                continue
                
            tdata = entry.get("content", {}).get("tweet", {})
            if not tdata:
                continue
                
            tweet_id = tdata.get("id_str", "")
            text = tdata.get("full_text") or tdata.get("text", "")
            created_at = tdata.get("created_at", "")
            
            # 清理推文鏈結/小尾巴
            text = re.sub(r'https://t\.co/\w+$', '', text).strip()
            
            tweets.append({
                "tweet_id": tweet_id,
                "text": text,
                "created_at": created_at,
                "likes": tdata.get("favorite_count", 0),
                "retweets": tdata.get("retweet_count", 0),
                "replies": tdata.get("reply_count", 0),
                "url": f"https://x.com/{screen_name}/status/{tweet_id}"
            })
            
        logger.success(f"成功抓取 {len(tweets)} 條 X 推文 ({screen_name})")
        return {
            "source": "Twitter/X",
            "screen_name": screen_name,
            "count": len(tweets),
            "tweets": tweets
        }
        
    except Exception as e:
        logger.error(f"抓取 X 推文 ({screen_name}) 失敗: {e}")
        return {"error": f"抓取 X 推文出錯: {str(e)}"}

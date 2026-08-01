"""
tests/test_reddit_client.py

Reddit 輿情（Arctic Shift）單元與整合測試
==================================
"""
import pytest
from unittest.mock import patch

from skills.market_intel.reddit_client import fetch_reddit_sentiment
from skills._http import FetchError

# Arctic Shift 回傳 {"data": [ <post>, ... ]}（扁平貼文清單）
_POSTS = {"data": [
    {"title": "Should I buy SOL now?", "selftext": "SOL looks very strong, hit $200?",
     "score": 42, "num_comments": 15, "permalink": "/r/cryptocurrency/comments/sol-buy/",
     "created_utc": 1783382400.0},
    {"title": "Bitcoin ETF inflows hit record", "selftext": "BTC demand surging",
     "score": 100, "num_comments": 50, "permalink": "/r/cryptocurrency/comments/btc/",
     "created_utc": 1783382400.0},
]}


@patch("skills.market_intel.reddit_client.fetch_json")
def test_filters_by_keyword_and_aggregates(mock_fj):
    """客戶端關鍵字過濾 + 熱度彙整。"""
    mock_fj.return_value = _POSTS
    res = fetch_reddit_sentiment("SOL", limit=5)
    assert "error" not in res
    assert res["count"] == 1                       # 只匹配到 SOL 那篇
    assert res["posts"][0]["title"] == "Should I buy SOL now?"
    assert res["posts"][0]["upvotes"] == 42        # 讀 score
    assert res["posts"][0]["comments"] == 15
    assert res["posts"][0]["url"] == "https://www.reddit.com/r/cryptocurrency/comments/sol-buy/"
    assert res["posts"][0]["published_at"] is not None
    assert res["buzz"]["total_upvotes"] == 42


@patch("skills.market_intel.reddit_client.fetch_json")
def test_no_match_returns_empty_not_error(mock_fj):
    mock_fj.return_value = _POSTS
    res = fetch_reddit_sentiment("SOMEUNSEENCOIN", limit=5)
    assert "error" not in res
    assert res["count"] == 0 and "message" in res


@patch("skills.market_intel.reddit_client.fetch_json")
def test_fetch_error_surfaces_as_error(mock_fj):
    """來源失敗（如 Arctic Shift 掛掉）回 error，不靜默。"""
    mock_fj.side_effect = FetchError("HTTP 503")
    res = fetch_reddit_sentiment("BTC")
    assert "error" in res


# --- 真實整合測試 ---
def test_real_reddit_sentiment():
    res = fetch_reddit_sentiment("bitcoin", limit=3)
    assert isinstance(res, dict)
    if "error" not in res and res.get("count", 0) > 0:
        assert res["posts"][0]["url"].startswith("https://www.reddit.com")
        assert res["source"] == "Arctic Shift"

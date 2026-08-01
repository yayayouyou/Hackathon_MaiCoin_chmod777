"""
tests/test_web_search.py

網頁搜尋功能單元與整合測試
=========================
"""

import pytest
from unittest.mock import patch, MagicMock
from skills.market_intel.web_search_client import search_web_duckduckgo

# --- Mock 測試 ---

@patch("skills.market_intel.web_search_client.DDGS")
def test_search_web_duckduckgo_mock(mock_ddgs):
    """測試 ddgs 回傳的結果正確映射為 {title, link, snippet} (Mock)"""
    inst = MagicMock()
    inst.text.return_value = [
        {"title": "MAX Exchange Announcement",
         "href": "https://max.maicoin.com/news/123",
         "body": "MAX Exchange launches zero fee campaign for USDT pairs starting July 2026."},
    ]
    mock_ddgs.return_value.__enter__.return_value = inst

    res = search_web_duckduckgo("MAX Exchange Announcement", max_results=1)

    assert res["count"] == 1
    assert res["results"][0]["title"] == "MAX Exchange Announcement"
    assert res["results"][0]["link"] == "https://max.maicoin.com/news/123"   # 真連結，非包裝跳轉
    assert "zero fee campaign" in res["results"][0]["snippet"]


@patch("skills.market_intel.web_search_client.DDGS")
def test_search_ratelimit_returns_error_not_silent_empty(mock_ddgs):
    """限流時應回 error（不可靜默當成無結果）。"""
    mock_ddgs.return_value.__enter__.side_effect = Exception("RatelimitException")
    res = search_web_duckduckgo("x")
    assert "error" in res


# --- 真實整合測試 ---

def test_real_search_web_duckduckgo():
    """真實對接 ddgs 搜尋 'Bitcoin'"""
    res = search_web_duckduckgo("Bitcoin news", max_results=3)
    assert "error" not in res
    assert "results" in res
    assert res["count"] > 0
    assert res["results"][0]["title"] != ""
    assert res["results"][0]["link"].startswith("http")

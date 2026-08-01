"""
tests/test_crypto_news.py

即時加密新聞獲取單元與整合測試
==================================
"""

import pytest
from unittest.mock import patch, MagicMock
from skills.market_intel import news_client
from skills.market_intel.news_client import get_latest_crypto_news

_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:dc="http://purl.org/dc/elements/1.1/" version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Bitcoin hits new high amid ETF inflows</title>
      <link>https://cointelegraph.com/news/btc-hits-high</link>
      <description>&lt;p&gt;Bitcoin price broke past crucial resistance following record ETF flows...&lt;/p&gt;</description>
      <pubDate>Mon, 06 Jul 2026 12:00:00 +0000</pubDate>
      <dc:creator>John Doe</dc:creator>
    </item>
  </channel>
</rss>"""


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    # 單一測試來源 + 清空 90s 快取，避免跨測試污染
    monkeypatch.setattr(news_client, "NEWS_FEEDS", [("TestSource", "http://test/rss")])
    news_client._cache.update(ts=0.0, items=None, failed=None)
    yield


# --- Mock 測試 ---

@patch("skills.market_intel.news_client.session_get")
def test_get_latest_crypto_news_mock(mock_get):
    """測試 feedparser 解析與新聞結構映射 (Mock)"""
    resp = MagicMock()
    resp.content = _RSS
    mock_get.return_value = resp

    res = get_latest_crypto_news(limit=1)

    assert res["count"] == 1
    assert res["failed_sources"] == []
    assert res["news"][0]["title"] == "Bitcoin hits new high amid ETF inflows"
    assert res["news"][0]["author"] == "John Doe"
    assert res["news"][0]["source"] == "TestSource"
    assert res["news"][0]["age_minutes"] is not None       # 有正確解析發佈時間
    assert "Bitcoin price broke past crucial resistance" in res["news"][0]["summary"]
    assert "<p>" not in res["news"][0]["summary"]           # HTML 已清除+反轉義


@patch("skills.market_intel.news_client.session_get")
def test_all_sources_fail_returns_error(mock_get):
    """所有來源失敗時回 error，不靜默回空當成有效。"""
    mock_get.side_effect = Exception("network down")
    res = get_latest_crypto_news(limit=3)
    assert "error" in res


# --- 真實整合測試 ---

def test_real_get_latest_crypto_news():
    """真實對接多源 RSS 獲取最新新聞"""
    res = get_latest_crypto_news(limit=3)
    assert "error" not in res
    assert res["count"] > 0
    assert res["news"][0]["title"] != ""
    assert res["news"][0]["link"].startswith("http")

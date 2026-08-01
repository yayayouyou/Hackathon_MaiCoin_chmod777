"""
tests/test_social_scraper.py

社交名人言論抓取器 (Truth Social & X) 單元與整合測試
===================================================
"""

import pytest
from unittest.mock import patch, MagicMock
from skills.market_intel.social_scraper import fetch_trump_truth_posts, fetch_twitter_user_tweets

# --- Mock 測試 ---

@patch("skills.market_intel.social_scraper.session_get")
def test_fetch_trump_truth_posts_mock(mock_get):
    """測試川普 Truth Social RSS 封裝解析邏輯 (Mock)"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <item>
                <title>MAGA 2026</title>
                <link>https://truthsocial.com/@realDonaldTrump/posts/1111</link>
                <description><![CDATA[<p>We will make America great again! MAGA 2026!</p>]]></description>
                <pubDate>Mon, 06 Jul 2026 12:00:00 EST</pubDate>
            </item>
        </channel>
    </rss>
    """
    mock_get.return_value = mock_response
    
    res = fetch_trump_truth_posts(limit=1)
    
    assert "error" not in res
    assert res["count"] == 1
    assert res["posts"][0]["title"] == "MAGA 2026"
    assert res["posts"][0]["text"] == "We will make America great again! MAGA 2026!"
    assert res["posts"][0]["published_at"] == "Mon, 06 Jul 2026 12:00:00 EST"
    assert res["posts"][0]["url"] == "https://truthsocial.com/@realDonaldTrump/posts/1111"


@patch("skills.market_intel.social_scraper.session_get")
def test_fetch_twitter_user_tweets_mock(mock_get):
    """測試 X/Twitter 公共嵌入 Next.js JSON 提取與欄位清洗 (Mock)"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    # 提供包含 __NEXT_DATA__ script 標記的 HTML 模擬內容
    mock_response.text = """
    <html>
      <body>
        <script id="__NEXT_DATA__" type="application/json">
        {
          "props": {
            "pageProps": {
              "timeline": {
                "entries": [
                  {
                    "type": "tweet",
                    "content": {
                      "tweet": {
                        "id_str": "9999",
                        "full_text": "Working on SpaceX Starship Flight 5 today. https://t.co/xyz123",
                        "created_at": "Sun Jul 05 15:00:00 +0000 2026",
                        "favorite_count": 50000,
                        "retweet_count": 8000,
                        "reply_count": 4000
                      }
                    }
                  }
                ]
              }
            }
          }
        }
        </script>
      </body>
    </html>
    """
    mock_get.return_value = mock_response
    
    res = fetch_twitter_user_tweets("elonmusk", limit=1)
    
    assert "error" not in res
    assert res["count"] == 1
    assert res["tweets"][0]["tweet_id"] == "9999"
    # 小尾巴網址 https://t.co/xyz123 應被成功清除
    assert res["tweets"][0]["text"] == "Working on SpaceX Starship Flight 5 today."
    assert res["tweets"][0]["likes"] == 50000
    assert res["tweets"][0]["retweets"] == 8000
    assert res["tweets"][0]["replies"] == 4000
    assert res["tweets"][0]["url"] == "https://x.com/elonmusk/status/9999"

# --- P1: 陳舊偵測 + CNN 鏡像備援 ---

import skills.market_intel.social_scraper as ss


def test_post_age_parses_rfc2822_and_iso():
    assert ss._post_age_hours("Mon, 06 Jul 2020 12:00:00 +0000") > 1000    # 很舊
    assert ss._post_age_hours("2020-01-01T00:00:00Z") > 1000
    assert ss._post_age_hours("") is None


def test_stale_flag_when_latest_post_old():
    old = [{"title": "t", "text": "x", "published_at": "Mon, 06 Jul 2020 12:00:00 +0000", "url": "u"}]
    with patch.object(ss, "_fetch_trump_rss", return_value=old):
        res = ss.fetch_trump_truth_posts(limit=1)
    assert res["feed_health"] == "stale"        # 舊貼文 → 標記陳舊（非錯誤）
    assert res["latest_post_age_hours"] > 24


def test_fallback_to_cnn_mirror_on_primary_failure():
    fb = [{"title": "t", "text": "policy on crypto reserve", "published_at": "2099-01-01T00:00:00Z", "url": "u"}]
    with patch.object(ss, "_fetch_trump_rss", side_effect=Exception("primary down")), \
         patch.object(ss, "_fetch_trump_cnn_mirror", return_value=fb):
        res = ss.fetch_trump_truth_posts(limit=1)
    assert "error" not in res
    assert res["source"] == "CNN mirror (fallback)"
    assert res["count"] == 1


def test_both_sources_down_returns_error():
    with patch.object(ss, "_fetch_trump_rss", side_effect=Exception("primary down")), \
         patch.object(ss, "_fetch_trump_cnn_mirror", side_effect=Exception("mirror down")):
        res = ss.fetch_trump_truth_posts(limit=1)
    assert "error" in res
    assert res["feed_health"] == "down"


def test_cnn_mirror_parses_leading_objects_from_partial_json():
    # 模擬 Range 取回的『被截斷』JSON 陣列：兩個完整物件 + 一個被切斷的
    partial = ('[\n  {"id":"1","created_at":"2026-07-10T00:00:00Z","content":"<p>Crypto reserve!</p>","url":"a"},\n'
               '  {"id":"2","created_at":"2026-07-09T00:00:00Z","content":"Great day","url":"b"},\n'
               '  {"id":"3","created_at":"2026-07-08T00:00:00Z","content":"trunca')
    resp = MagicMock()
    resp.status_code = 206
    resp.text = partial
    with patch.object(ss, "session_get", return_value=resp):
        posts = ss._fetch_trump_cnn_mirror(limit=5)
    assert len(posts) == 2                       # 只取完整的兩則，截斷的略過
    assert posts[0]["text"] == "Crypto reserve!"  # HTML 已清除
    assert posts[0]["published_at"] == "2026-07-10T00:00:00Z"


# --- 真實整合測試 ---

def test_real_trump_truth_posts():
    """測試真實川普 Truth Social 貼文抓取"""
    res = fetch_trump_truth_posts(limit=3)
    
    assert "error" not in res
    assert res["count"] > 0
    assert len(res["posts"]) > 0
    assert res["posts"][0]["title"] != ""
    assert res["posts"][0]["url"].startswith("https://")


def test_real_twitter_user_tweets():
    """測試真實 X 馬斯克推文抓取 (若被 X 反爬蟲限制則自動跳過，不中斷測試)"""
    res = fetch_twitter_user_tweets("elonmusk", limit=3)
    
    assert isinstance(res, dict)
    if "error" not in res:
        assert "tweets" in res
        if res["count"] > 0:
            assert res["tweets"][0]["tweet_id"] != ""
            assert "text" in res["tweets"][0]

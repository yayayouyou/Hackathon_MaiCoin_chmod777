"""事件驅動社交回測（誠實版）單元測試 — 驗證無前視、異常報酬、排列檢定、誠實揭露。"""
import email.utils
from unittest.mock import patch, MagicMock

from skills.analytics.backtester import run_twitter_mention_backtest

_BASE = 1_700_000_000_000  # ms
_HOUR = 3_600_000


def _klines(n=300, start=0.1, drift=0.0):
    out, p = [], float(start)
    for i in range(n):
        o = p
        c = p * (1 + drift)
        out.append([_BASE + i * _HOUR, o, max(o, c) * 1.01, min(o, c) * 0.99, c, 1000.0])
        p = c
    return out


class _FakeEx:
    def fetch_ohlcv(self, symbol, timeframe="1h", limit=1000):
        if symbol.upper().startswith("DOGE"):
            return _klines(300, 0.1, drift=0.003)     # DOGE 緩漲
        return _klines(300, 60000.0, drift=0.001)     # BTC 基準微漲


def _tweet_at(candle_idx, text):
    ts_sec = _BASE // 1000 + candle_idx * 3600
    return {"text": text, "created_at": email.utils.formatdate(ts_sec, usegmt=True)}


def _run(tweets):
    with patch("skills.market_intel.social_scraper.fetch_twitter_user_tweets",
               return_value={"tweets": tweets}), \
         patch("skills.market_data.ccxt_fetcher._create_exchange", return_value=_FakeEx()):
        return run_twitter_mention_backtest("DOGE/USDT", screen_name="elonmusk", hold_hours=24)


class TestHonestEventStudy:
    def test_structure_and_no_lookahead(self):
        res = _run([_tweet_at(100, "Dogecoin is amazing"),
                    _tweet_at(150, "buy doge now"),
                    _tweet_at(200, "doge to the moon")])
        assert res["events_used"] == 3
        assert res["benchmark"] == "BTC/USDT"
        # 進場價 = 事件『後一根』的開盤（無前視）：candle 101 的 open
        first = res["sample_trades"][0]
        assert "entry_open_price" in first and "24h" in first["by_horizon"]
        # 有多持有期
        assert set(res["by_horizon"].keys()) >= {"1h", "4h", "24h"}
        # 每個持有期有淨報酬與『相對 BTC 異常報酬』
        assert res["by_horizon"]["24h"]["abnormal_vs_btc"] is not None

    def test_permutation_test_present(self):
        res = _run([_tweet_at(c, "doge") for c in (80, 120, 160, 200, 240)])
        perm = res["permutation_test"]
        assert perm is not None
        assert 0.0 <= perm["p_value_two_sided"] <= 1.0
        assert perm["null_samples"] == 1000
        assert "abnormal" in perm["metric"]

    def test_small_sample_warning(self):
        res = _run([_tweet_at(100, "doge")])
        assert any("樣本過小" in n for n in res["honesty_notes"])

    def test_reproducible_p_value(self):
        tw = [_tweet_at(c, "doge") for c in (90, 140, 190)]
        p1 = _run(tw)["permutation_test"]["p_value_two_sided"]
        p2 = _run(tw)["permutation_test"]["p_value_two_sided"]
        assert p1 == p2   # 固定種子 → 可重現

    def test_no_matching_mentions(self):
        res = _run([_tweet_at(100, "I like turtles and pizza")])
        assert res["matched_events_count"] == 0

    def test_events_outside_price_window_dropped(self):
        # 事件在價格資料涵蓋範圍『之後』（candle 500 > 300 根）→ 應被計入 outside、不進回測
        res = _run([_tweet_at(500, "doge"), _tweet_at(100, "doge")])
        assert res["events_used"] == 1
        assert res["events_outside_price_window"] >= 1

    def test_negative_hold_hours_no_crash(self):
        # 負 hold_hours 以前會產生負索引 KeyError；夾限後應正常回傳
        with patch("skills.market_intel.social_scraper.fetch_twitter_user_tweets",
                   return_value={"tweets": [_tweet_at(100, "doge"), _tweet_at(150, "doge")]}), \
             patch("skills.market_data.ccxt_fetcher._create_exchange", return_value=_FakeEx()):
            res = run_twitter_mention_backtest("DOGE/USDT", screen_name="elonmusk", hold_hours=-5)
        assert isinstance(res, dict) and "error" not in res
        assert res["events_used"] == 2

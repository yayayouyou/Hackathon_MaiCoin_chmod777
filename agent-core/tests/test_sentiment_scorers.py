"""群眾情緒批次量化打分器測試 — VADER+加密詞庫、分佈彙整、兩極化、CryptoBERT 回落。"""
import pytest

from skills.market_intel import sentiment_scorers as ss
from skills.market_intel.sentiment_scorers import score_text, bulk_score, _aggregate


class TestCryptoLexicon:
    def test_crypto_slang_scored_bullish(self):
        # 純加密黑話（一般 VADER 詞典幾乎給 0）→ 加了詞庫後應明顯偏多
        r = score_text("HODL diamond hands, ath soon, wagmi")
        assert r["label"] == "bullish"
        assert r["score"] > 0.4

    def test_crypto_slang_scored_bearish(self):
        r = score_text("total rugpull, everyone rekt, capitulation and bloodbath")
        assert r["label"] == "bearish"
        assert r["score"] < -0.4

    def test_neutral_text(self):
        r = score_text("The conference is scheduled for next Tuesday in Taipei")
        assert r["label"] == "neutral"

    def test_engine_defaults_to_vader(self):
        assert score_text("moon")["engine"] == "vader"


class TestAggregate:
    def test_distribution_shares_sum_to_one(self):
        agg = _aggregate([0.9, 0.8, -0.7, -0.6, 0.0])
        assert abs(agg["bullish_share"] + agg["bearish_share"] + agg["neutral_share"] - 1.0) < 1e-6
        assert agg["sample_size"] == 5

    def test_polarized_crowd_flagged_divided(self):
        # 一半極多、一半極空、淨值接近 0 → 應標記 divided
        agg = _aggregate([0.9, 0.85, -0.9, -0.85])
        assert agg["is_polarized"] is True
        assert agg["label"] == "divided"
        assert agg["polarization"] == 1.0

    def test_unanimous_bullish_not_polarized(self):
        agg = _aggregate([0.7, 0.8, 0.6, 0.9])
        assert agg["is_polarized"] is False
        assert agg["label"] in ("bullish", "strong_bullish")
        assert agg["polarization"] == 0.0

    def test_net_sentiment_sign(self):
        assert _aggregate([0.9, 0.8, 0.7, -0.1])["net_sentiment"] > 0
        assert _aggregate([-0.9, -0.8, -0.7, 0.1])["net_sentiment"] < 0


class TestBulkScore:
    def test_bulk_structure(self):
        out = bulk_score(["moon and bullish", "rug and rekt", "meeting on tuesday"])
        assert out["engine"] == "vader"
        assert out["aggregate"]["sample_size"] == 3
        assert "most_bullish" in out and "most_bearish" in out

    def test_empty_input(self):
        out = bulk_score([])
        assert "error" in out
        assert out["aggregate"]["sample_size"] == 0

    def test_examples_sorted_and_bounded(self):
        out = bulk_score(["moon wagmi lfg", "rugpull rekt bloodbath", "neutral text here",
                          "bullish accumulate ath", "dump capitulation ngmi"], keep_examples=2)
        # 最多 2 則代表例；且多方例分數 > 0、空方例分數 < 0
        assert len(out["most_bullish"]) <= 2
        assert all(e["score"] > 0 for e in out["most_bullish"])
        assert all(e["score"] < 0 for e in out["most_bearish"])


class TestCryptoBertFallback:
    def test_falls_back_to_vader_when_unavailable(self, monkeypatch):
        # 模擬 transformers 未安裝 → 要求 cryptobert 時應優雅回落 vader
        monkeypatch.setattr(ss, "_cryptobert_state", {"tried": False, "pipe": None})
        monkeypatch.setattr(ss, "_get_cryptobert", lambda: None)
        r = score_text("moon", engine="cryptobert")
        assert r["engine"] == "vader"

    def test_cryptobert_used_when_available(self, monkeypatch):
        # 注入假 pipeline 回傳三分類機率 → 應走 cryptobert 且 score = P(bull)-P(bear)
        def fake_pipe(text):
            return [[{"label": "Bullish", "score": 0.8},
                     {"label": "Neutral", "score": 0.15},
                     {"label": "Bearish", "score": 0.05}]]
        monkeypatch.setattr(ss, "_cryptobert_state", {"tried": True, "pipe": fake_pipe})
        monkeypatch.setattr(ss, "_get_cryptobert", lambda: fake_pipe)
        r = score_text("anything", engine="cryptobert")
        assert r["engine"] == "cryptobert"
        assert abs(r["score"] - 0.75) < 1e-6

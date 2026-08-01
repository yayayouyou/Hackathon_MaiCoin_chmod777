"""社群情緒分析層 (skills/market_intel/social_analysis.py) 單元測試"""
import json

import pytest

from skills.market_intel import social_analysis as sa
from agent.llm.base import LLMResponse


class FakeProvider:
    """回傳固定 JSON content 的假 provider，並記錄呼叫參數。"""
    name = "fake"
    model = "fake"

    def __init__(self, content):
        self.content = content
        self.calls = []

    def chat(self, messages, tools=None, temperature=None, think=None, format=None):
        self.calls.append({"temperature": temperature, "think": think, "format": format})
        return LLMResponse(content=self.content)


def _post_json(**over):
    base = {
        "is_market_relevant": True, "event_type": "strategic_reserve", "signal": "bullish",
        "sentiment_score": 0.8, "affected_assets": ["BTC"], "impact_magnitude": "high",
        "time_horizon": "short_term", "confidence": 0.7, "is_sarcastic": False,
        "reversal_risk": "medium", "evidence_quotes": [], "rationale": "測試",
    }
    base.update(over)
    return json.dumps(base, ensure_ascii=False)


class TestGrounding:
    def test_verbatim_evidence_kept_fake_dropped(self):
        text = "Bitcoin is the future. We will make it a strategic reserve asset!"
        prov = FakeProvider(_post_json(
            evidence_quotes=["strategic reserve asset", "this line is NOT in the post"]))
        res = sa.analyze_social_post(text, author="trump", source="truth_social", provider=prov)
        assert res["evidence_quotes"] == ["strategic reserve asset"]   # 只留原文子字串
        assert res["grounded"] is True
        assert res["signal"] == "bullish"
        # 結構化輸出：format 有傳、think 關閉、溫度 0
        assert prov.calls[0]["format"] is not None
        assert prov.calls[0]["think"] is False
        assert prov.calls[0]["temperature"] == 0.0

    def test_whitelist_clamps_invented_asset(self):
        text = "BTC to the moon and also FAKECOIN"
        prov = FakeProvider(_post_json(affected_assets=["BTC", "FAKECOIN", "ETH"],
                                       evidence_quotes=["BTC to the moon"]))
        res = sa.analyze_social_post(text, provider=prov)
        assert "FAKECOIN" not in res["affected_assets"]
        assert set(res["affected_assets"]) <= set(sa.TRADEABLE_ASSETS)
        assert "BTC" in res["affected_assets"]

    def test_ungrounded_downgrades_to_neutral(self):
        prov = FakeProvider(_post_json(
            is_market_relevant=True, signal="bullish", impact_magnitude="high", confidence=0.9,
            evidence_quotes=["totally fabricated quote not present"]))
        res = sa.analyze_social_post("Real post text about markets", provider=prov)
        assert res["grounded"] is False
        assert res["signal"] == "neutral"           # 未落地 → 保守降級
        assert res["confidence"] <= 0.3

    def test_irrelevant_forced_neutral(self):
        prov = FakeProvider(_post_json(is_market_relevant=False, signal="bullish",
                                       impact_magnitude="high", evidence_quotes=[]))
        res = sa.analyze_social_post("Happy birthday to my dog", provider=prov)
        assert res["signal"] == "neutral"
        assert res["impact_magnitude"] == "none"

    def test_empty_text(self):
        assert "error" in sa.analyze_social_post("   ")

    def test_short_evidence_quote_rejected(self):
        # 太短的『證據』(<12 正規化字元) 不算落地 → 防幻覺被單一詞繞過
        text = "BTC is going up today according to the report"
        prov = FakeProvider(_post_json(evidence_quotes=["BTC"]))
        res = sa.analyze_social_post(text, provider=prov)
        assert res["evidence_quotes"] == []
        assert res["grounded"] is False
        assert res["signal"] == "neutral"


class TestFigureTool:
    def test_unknown_person(self):
        assert "error" in sa.analyze_figure_sentiment("jeff_bezos")

    def test_supported_people_listed(self):
        assert "trump" in sa.FIGURES and "elon" in sa.FIGURES


class TestSchemas:
    def test_affected_assets_enum_is_whitelist(self):
        enum = sa.POST_SIGNAL_SCHEMA["properties"]["affected_assets"]["items"]["enum"]
        assert enum == sa.TRADEABLE_ASSETS
        assert "CRYPTO_MARKET" in enum   # 泛市場/政策事件用

    def test_crowd_schema_has_trend_and_stance(self):
        props = sa.CROWD_SENTIMENT_SCHEMA["properties"]
        assert "overall_stance" in props and "trend" in props and "conviction" in props


def _crowd_json(**over):
    base = {"overall_stance": "bullish", "stance_score": 0.6, "conviction": "moderate",
            "trend": "improving", "dominant_themes": ["ETF"], "notable_divergence": "",
            "summary": "測試"}
    base.update(over)
    return json.dumps(base, ensure_ascii=False)


class TestCrowdQuantLayer:
    """慢軌『量化打分器 + gemma 彙整』兩層互補整合。"""

    def test_quant_block_attached(self, monkeypatch):
        # analyze_crowd_sentiment 內部用 _get_provider()，故 patch 它
        monkeypatch.setattr(sa, "_gather_crowd_texts",
                            lambda a, m: ["BTC to the moon, bullish, accumulate", "ETF inflows huge"])
        monkeypatch.setattr(sa, "_get_provider", lambda p=None: FakeProvider(_crowd_json()))
        res = sa.analyze_crowd_sentiment("BTC")
        assert "quant" in res
        assert res["quant"]["engine"] == "vader"
        assert res["quant"]["aggregate"]["sample_size"] == 2
        assert res["sample_size"] == 2

    def test_cross_check_flags_disagreement(self, monkeypatch):
        # 量化偏空（rug/rekt/dump）但 gemma 硬說 bullish → 應標記分歧
        monkeypatch.setattr(sa, "_gather_crowd_texts",
                            lambda a, m: ["rugpull rekt bloodbath", "dump capitulation ngmi",
                                          "total scam liquidations"])
        monkeypatch.setattr(sa, "_get_provider",
                            lambda p=None: FakeProvider(_crowd_json(overall_stance="bullish", stance_score=0.7)))
        res = sa.analyze_crowd_sentiment("BTC")
        assert "cross_check" in res
        assert res["quant"]["aggregate"]["net_sentiment"] < 0

    def test_graceful_degradation_when_gemma_fails(self, monkeypatch):
        monkeypatch.setattr(sa, "_gather_crowd_texts", lambda a, m: ["moon bullish", "rug rekt"])
        monkeypatch.setattr(sa, "_get_provider", lambda p=None: FakeProvider("not json at all"))
        res = sa.analyze_crowd_sentiment("BTC")
        assert "quant" in res                 # 量化層仍在
        assert "warning" in res               # 質性層失敗但不整體崩潰

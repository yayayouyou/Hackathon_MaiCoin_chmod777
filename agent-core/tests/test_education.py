"""
tests/test_education.py

小白教育技能單元測試 + 新工具註冊完整性檢查
"""

import pytest
from skills.education import (
    explain_crypto_term,
    get_max_guide,
    get_beginner_safety_checklist,
    get_max_fee_info,
)


class TestGlossary:
    def test_direct_hit(self):
        r = explain_crypto_term("現貨")
        assert r["found"] is True
        assert r["term"] == "現貨"
        assert "explanation" in r and r["explanation"]

    def test_alias_hit(self):
        r = explain_crypto_term("spot")
        assert r["found"] is True
        assert r["term"] == "現貨"

    def test_uppercase_and_english(self):
        r = explain_crypto_term("RSI")
        assert r["found"] is True
        assert r["term"] == "rsi"

    def test_fuzzy_contains(self):
        r = explain_crypto_term("合約交易")
        assert r["found"] is True
        assert r["term"] == "合約"

    def test_miss_returns_available(self):
        r = explain_crypto_term("這個詞不存在xyz")
        assert r["found"] is False
        assert isinstance(r["available_terms"], list) and len(r["available_terms"]) > 10

    def test_empty(self):
        r = explain_crypto_term("")
        assert "available_terms" in r


class TestMaxGuide:
    def test_alias(self):
        r = get_max_guide("入金")
        assert r["found"] is True
        assert r["topic"] == "台幣入金"
        assert len(r["steps"]) >= 3

    def test_list_topics(self):
        r = get_max_guide()
        assert "available_topics" in r
        assert "台幣入金" in r["available_topics"]

    def test_api_topic(self):
        r = get_max_guide("api")
        assert r["found"] is True
        assert r["topic"] == "api金鑰"


class TestSafety:
    def test_scam_category(self):
        r = get_beginner_safety_checklist("詐騙")
        assert r["found"] is True
        assert len(r["items"]) >= 3

    def test_all(self):
        r = get_beginner_safety_checklist()
        assert set(["詐騙", "資產安全", "心態"]).issubset(set(r["categories"]))


class TestFeeInfo:
    def test_structure(self):
        r = get_max_fee_info()
        assert "trading_fee" in r
        assert "max_token_discount" in r
        assert "summary" in r


class TestToolRegistration:
    """確保新工具正確併入 ALL_TOOLS，且沒有重複名稱、Schema/實作對得起來。"""

    def test_all_tools_unique_and_present(self):
        from agent.prompts import ALL_TOOLS
        names = [t["function"]["name"] for t in ALL_TOOLS]
        # 無重複
        assert len(names) == len(set(names)), "ALL_TOOLS 有重複的工具名稱"
        # 新工具都在
        for n in [
            "explain_crypto_term", "get_max_guide", "get_beginner_safety_checklist", "get_max_fee_info",
            "calculate_dca", "calculate_position_size", "calculate_pnl",
            "calculate_average_down", "calculate_target_sell_price",
        ]:
            assert n in names, f"{n} 未註冊進 ALL_TOOLS"

    def test_new_schemas_have_callables(self):
        from skills.education.schemas import EDUCATION_TOOLS
        from skills.calculators.schemas import CALCULATORS_TOOLS
        from agent.ollama_agent import TOOL_CALLABLES
        for t in EDUCATION_TOOLS + CALCULATORS_TOOLS:
            name = t["function"]["name"]
            assert name in TOOL_CALLABLES, f"{name} 有 Schema 但未在 TOOL_CALLABLES 註冊實作"

"""
tests/test_personas.py

投資大師人格引擎單元測試
"""

import pytest
from agent.personas import get_persona, list_personas, get_persona_addendum, PERSONAS


class TestPersonas:
    """人格引擎核心功能測試"""
    
    def test_list_personas_returns_all(self):
        """確認 list_personas 返回所有人格"""
        personas = list_personas()
        assert len(personas) >= 5  # default, buffett, dalio, livermore, whale
        keys = [p["key"] for p in personas]
        assert "default" in keys
        assert "buffett" in keys
        assert "dalio" in keys
        assert "livermore" in keys
        assert "whale" in keys

    def test_list_personas_structure(self):
        """確認每個人格都有完整的字段"""
        for persona in list_personas():
            assert "key" in persona
            assert "name" in persona
            assert "icon" in persona
            assert "description" in persona
            assert len(persona["name"]) > 0
            assert len(persona["icon"]) > 0

    def test_get_persona_default(self):
        """測試獲取預設人格"""
        persona = get_persona("default")
        assert persona["name"] == "AI 加密分析師"
        assert persona["icon"] == "🤖"

    def test_get_persona_buffett(self):
        """測試獲取巴菲特人格"""
        persona = get_persona("buffett")
        assert "巴菲特" in persona["name"]
        assert "護城河" in persona["system_addendum"]

    def test_get_persona_dalio(self):
        """測試獲取達利歐人格"""
        persona = get_persona("dalio")
        assert "達利歐" in persona["name"]
        assert "風險平價" in persona["system_addendum"]

    def test_get_persona_livermore(self):
        """測試獲取李佛摩人格"""
        persona = get_persona("livermore")
        assert "李佛摩" in persona["name"]
        assert "趨勢" in persona["system_addendum"]

    def test_get_persona_whale(self):
        """測試獲取巨鯨人格"""
        persona = get_persona("whale")
        assert "巨鯨" in persona["name"]

    def test_get_persona_invalid_key_returns_default(self):
        """無效的人格鍵名應返回預設人格"""
        persona = get_persona("nonexistent")
        assert persona["name"] == "AI 加密分析師"

    def test_get_persona_addendum_contains_xml(self):
        """確認人格附加段落包含 XML 結構"""
        for key in PERSONAS:
            addendum = get_persona_addendum(key)
            assert "<persona>" in addendum
            assert "</persona>" in addendum
            assert "<role>" in addendum

    def test_get_persona_addendum_buffett_has_quotes(self):
        """確認巴菲特人格包含名言引用"""
        addendum = get_persona_addendum("buffett")
        assert "<quotes>" in addendum
        assert "恐懼" in addendum  # 巴菲特經典名言

    def test_get_persona_addendum_invalid_returns_default(self):
        """無效鍵名的附加段落應返回預設"""
        addendum = get_persona_addendum("nonexistent")
        assert "CFA" in addendum  # 預設人格提到 CFA


class TestPromptIntegration:
    """測試人格與 System Prompt 的整合"""
    
    def test_system_prompt_with_default_persona(self):
        """確認預設人格的 System Prompt 可正確生成"""
        from agent.prompts import get_system_prompt
        prompt = get_system_prompt("default")
        assert "<agent_contract>" in prompt
        assert "<reasoning_protocol>" in prompt
        assert "<guardrails>" in prompt
        assert "CFA" in prompt  # 預設人格

    def test_system_prompt_with_buffett_persona(self):
        """確認巴菲特人格注入到 System Prompt"""
        from agent.prompts import get_system_prompt
        prompt = get_system_prompt("buffett")
        assert "巴菲特" in prompt
        assert "護城河" in prompt

    def test_system_prompt_xml_structure(self):
        """確認 XML 結構完整性"""
        from agent.prompts import get_system_prompt
        prompt = get_system_prompt()
        assert prompt.count("<agent_contract>") == 1
        assert prompt.count("</agent_contract>") == 1
        assert "<tool_calling_protocol>" in prompt
        assert "<reasoning_protocol>" in prompt
        assert "<guardrails>" in prompt
        assert "<output_format>" in prompt


class TestAutoDispatch:
    """角色自動派發（依問題內容判斷該派哪個角色）。"""

    def test_dispatch_by_keywords(self):
        from agent.personas import auto_select_persona
        assert auto_select_persona("新手第一次買幣 會不會被騙") == "beginner"
        assert auto_select_persona("追蹤巨鯨大戶錢包淨流出") == "whale"
        assert auto_select_persona("宏觀總經 ETF 資金流 週期") == "dalio"
        assert auto_select_persona("價值投資 長期 護城河 內在價值") == "buffett"
        assert auto_select_persona("突破趨勢 關鍵價 進場點 背離") == "livermore"

    def test_defaults_when_no_signal(self):
        from agent.personas import auto_select_persona
        assert auto_select_persona("BTC 現在多少錢") == "default"
        assert auto_select_persona("") == "default"

    def test_resolve_persona(self):
        from agent.personas import resolve_persona
        assert resolve_persona("auto", "新手怎麼買") == "beginner"   # auto → 依問題派發
        assert resolve_persona("", "巨鯨錢包流出") == "whale"        # 空 → 派發
        assert resolve_persona("buffett", "隨便問") == "buffett"     # 指定 → 鎖定
        assert resolve_persona("nonexistent", "x") == "default"      # 未知 → default
        for k in PERSONAS:
            assert resolve_persona(k, "") == k

"""
tests/test_agent.py

Ollama Agent 大腦與決策循環單元測試
=====================================
"""

import pytest
from unittest.mock import patch, MagicMock
from agent.ollama_agent import _parse_tool_call, run_agent_turn
from agent.llm.base import LLMResponse, ToolCall


class FakeProvider:
    """測試用假供應商：依序回傳預先腳本化的 LLMResponse。"""
    name = "fake"
    model = "fake-model"

    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = []

    def chat(self, messages, tools=None, temperature=None, think=None, format=None):
        self.calls.append({"messages": messages, "tools": tools, "temperature": temperature,
                           "think": think, "format": format})
        return self.scripted.pop(0)


CRITIC_PASS = LLMResponse(content="審查通過：無發現明顯邏輯漏洞。")

def test_parse_tool_call_markdown_json():
    # 測試帶有 markdown code block 的 JSON 格式解析
    text = """
    好的，我需要先獲取 K 線。
    ```json
    {
        "tool": "get_ohlcv",
        "args": {
            "exchange_id": "binance",
            "symbol": "BTC/USDT"
        }
    }
    ```
    這是我的第一個步驟。
    """
    res = _parse_tool_call(text)
    assert res is not None
    assert res["tool"] == "get_ohlcv"
    assert res["args"]["symbol"] == "BTC/USDT"

def test_parse_tool_call_raw_json():
    # 測試純 JSON 格式解析
    text = '{"tool": "get_ticker", "args": {"exchange_id": "okx", "symbol": "ETH/USDT"}}'
    res = _parse_tool_call(text)
    assert res is not None
    assert res["tool"] == "get_ticker"
    assert res["args"]["exchange_id"] == "okx"

def test_parse_tool_call_none():
    # 測試無工具調用之普通文字解析
    text = "您好！BTC 當前的價格大約是 63,000 USD。"
    res = _parse_tool_call(text)
    assert res is None


class TestAgentLoop:
    def test_run_agent_turn_no_tools(self):
        # 1. 供應商直接給出最終回答，無工具調用（第 2 次呼叫為 Critic 審查）
        provider = FakeProvider([
            LLMResponse(content="BTC/TWD 當前在 MAX 的最新價格是 2,000,500 元。"),
            CRITIC_PASS,
        ])
        messages = [{"role": "user", "content": "現在 BTC 多少錢？"}]
        steps = list(run_agent_turn(messages, provider=provider))

        types = [s["type"] for s in steps]
        assert "status" in types
        assert "thought" in types
        assert "final_answer" in types

        final_answer = next(s for s in steps if s["type"] == "final_answer")
        assert "2,000,500" in final_answer["content"]
        # Critic 審查通過 -> 不附風險警示
        assert "Critic Agent 審查報告" not in final_answer["content"]

    @patch("agent.ollama_agent.TOOL_CALLABLES")
    def test_run_agent_turn_with_native_tool_call(self, mock_tool_callables):
        # 2. 原生 function-calling：發起 tool_call -> 執行 -> 給出最終解答
        mock_tool = MagicMock(return_value={"price": 63500.0})
        mock_tool_callables.__contains__.return_value = True
        mock_tool_callables.__getitem__.return_value = mock_tool

        provider = FakeProvider([
            LLMResponse(
                content="我需要先查價格。",
                tool_calls=[ToolCall(id="c1", name="get_ticker",
                                     args={"exchange_id": "binance", "symbol": "BTC/USDT"})],
                native_tools=True,
                raw_message={"role": "assistant", "content": "我需要先查價格。", "tool_calls": []},
            ),
            LLMResponse(content="查到了，BTC 在幣安最新價格是 63,500 USD。"),
            CRITIC_PASS,
        ])

        messages = [{"role": "user", "content": "幣安 BTC 多少錢？"}]
        steps = list(run_agent_turn(messages, provider=provider))

        types = [s["type"] for s in steps]
        assert "tool_call" in types
        assert "tool_result" in types
        assert "final_answer" in types

        mock_tool.assert_called_once_with(exchange_id="binance", symbol="BTC/USDT")
        final_answer = next(s for s in steps if s["type"] == "final_answer")
        assert "63,500" in final_answer["content"]

    @patch("agent.ollama_agent.TOOL_CALLABLES")
    def test_run_agent_turn_multiple_tools_one_step(self, mock_tool_callables):
        # 3. 單一輪一次發起「多個」工具呼叫，全部應被執行
        mock_tool = MagicMock(return_value={"ok": True})
        mock_tool_callables.__contains__.return_value = True
        mock_tool_callables.__getitem__.return_value = mock_tool

        provider = FakeProvider([
            LLMResponse(
                content="平行收集多維度數據。",
                tool_calls=[
                    ToolCall(id="a", name="get_crypto_fear_and_greed_index", args={"limit": 7}),
                    ToolCall(id="b", name="get_aggregated_funding_rate", args={"symbol": "BTC"}),
                ],
                native_tools=True,
                raw_message={"role": "assistant", "content": "平行收集多維度數據。"},
            ),
            LLMResponse(content="綜合以上數據，BTC 情緒偏空但資金費率中性。"),
            CRITIC_PASS,
        ])

        steps = list(run_agent_turn([{"role": "user", "content": "分析 BTC"}], provider=provider))
        tool_calls = [s for s in steps if s["type"] == "tool_call"]
        assert len(tool_calls) == 2
        assert {t["name"] for t in tool_calls} == {"get_crypto_fear_and_greed_index", "get_aggregated_funding_rate"}
        assert mock_tool.call_count == 2

    def test_run_agent_turn_critic_flags_risk(self):
        # 4. Critic 未通過 -> 附上風險警示與審查報告
        provider = FakeProvider([
            LLMResponse(content="強烈買入！所有訊號都看漲，絕對穩賺。"),
            LLMResponse(content="發現確認偏誤：忽略了鏈上資金流出。評級應降為觀望。"),
        ])
        steps = list(run_agent_turn([{"role": "user", "content": "該買嗎"}], provider=provider))
        final = next(s for s in steps if s["type"] == "final_answer")
        assert "風險警示" in final["content"]
        assert "Critic" in final["content"]
        assert "觀望" in final["content"]

    def test_educational_answer_skips_critic(self):
        # 5. 知識性回答（無買賣建議）不應觸發 Critic，避免拖慢與贅述
        provider = FakeProvider([
            LLMResponse(content="ARB 是 Arbitrum 的原生代幣，用於這個以太坊 Layer2 的治理與生態。"),
        ])
        steps = list(run_agent_turn([{"role": "user", "content": "ARB 是什麼幣"}], provider=provider))
        final = next(s for s in steps if s["type"] == "final_answer")
        assert "Arbitrum" in final["content"]
        assert "Critic" not in final["content"]
        # 未再為 Critic 呼叫 provider（只跑了一次主回合）
        assert len(provider.calls) == 1

    @patch("agent.ollama_agent.TOOL_CALLABLES")
    def test_text_tool_calls_not_treated_as_final(self, mock_tool_callables):
        # 7. ARB 案例：模型把工具寫成文字 + 捏造結論。應執行工具並在下一輪給真實結論，
        #    而不是把「假設數據」的那坨當成最終答案直接輸出。
        mock_tool = MagicMock(return_value={"price": 1.23})
        mock_tool_callables.__contains__.return_value = True
        mock_tool_callables.__getitem__.return_value = mock_tool

        blob = LLMResponse(
            content='分析中 {"name":"get_cmc_latest_quotes","args":{"symbols":"ARB"}} '
                    '<analysis>假設數據：ARB 強烈做空</analysis>',
            tool_calls=[ToolCall(id="textparse-0", name="get_cmc_latest_quotes", args={"symbols": "ARB"})],
            native_tools=False,
            raw_message={"role": "assistant", "content": "分析中..."},
        )
        real = LLMResponse(content="根據真實數據，ARB 現價 1.23、情緒中性，維持觀望。")
        provider = FakeProvider([blob, real, CRITIC_PASS])

        steps = list(run_agent_turn([{"role": "user", "content": "ARB 該空嗎"}], provider=provider))
        final = next(s for s in steps if s["type"] == "final_answer")
        assert "假設數據" not in final["content"]          # 捏造的草稿不得成為最終答案
        assert "真實數據" in final["content"]
        assert any(s["type"] == "tool_call" for s in steps)  # 工具真的被執行
        mock_tool.assert_called_once_with(symbols="ARB")

    def test_nudge_when_model_asks_permission(self):
        # 6. 模型反問「是否要我繼續執行工具」卻沒真的呼叫 -> 自動推進，不卡住
        provider = FakeProvider([
            LLMResponse(content="我打算查一些資料，是否要我繼續執行這兩個 API 工具？"),
            LLMResponse(content="ARB 是 Arbitrum 的 Layer2 代幣，近期價格區間整理。"),
        ])
        steps = list(run_agent_turn([{"role": "user", "content": "介紹 ARB"}], provider=provider))
        final = next(s for s in steps if s["type"] == "final_answer")
        assert "Arbitrum" in final["content"]
        assert len(provider.calls) == 2  # 第一次被 nudge 推進，第二次才定案

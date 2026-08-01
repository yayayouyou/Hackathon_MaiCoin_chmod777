"""
tests/test_llm_providers.py

LLM 供應商抽象層單元測試（Ollama / OpenRouter 解析 + 文字解析備援 + Critic 守衛）
"""

import pytest
from unittest.mock import patch, MagicMock

from agent.llm.base import parse_text_tool_call, extract_tool_calls_from_text, LLMResponse, ToolCall
from agent.llm.ollama import OllamaProvider
from agent.llm.openrouter import OpenRouterProvider
from agent.llm.base import LLMError


# ── 文字解析備援 ─────────────────────────────
class TestTextParse:
    def test_json_block(self):
        r = parse_text_tool_call('前綴 ```json\n{"tool":"get_ticker","args":{"symbol":"BTC/USDT"}}\n``` 後綴')
        assert r["tool"] == "get_ticker"

    def test_raw_brace(self):
        r = parse_text_tool_call('{"tool":"get_ohlcv","args":{"limit":50}}')
        assert r["args"]["limit"] == 50

    def test_ignores_leading_garbage_brace(self):
        # 第一個 { 無法構成合法 JSON，應跳過並找到後面合法的物件
        r = parse_text_tool_call('文字 {不是JSON} 再來 {"tool":"x","args":{}}')
        assert r == {"tool": "x", "args": {}}

    def test_none(self):
        assert parse_text_tool_call("純文字沒有工具") is None

    def test_extract_multiple_openai_style(self):
        # 模型把多個工具用 OpenAI 風格 {"name","args"} 寫成文字（ARB 案例的失敗樣態）
        blob = '''### 分析
<tool_calling_protocol>
{ "name": "get_cmc_latest_quotes", "args": { "symbols": "ARB" } }
{ "name": "get_crypto_fear_and_greed_index" }
{ "name": "fetch_reddit_sentiment", "args": { "query": "ARB", "limit": 5 } }
</tool_calling_protocol>
<analysis>假設數據：ARB 目前...</analysis>'''
        calls = extract_tool_calls_from_text(blob)
        names = [c["tool"] for c in calls]
        assert names == ["get_cmc_latest_quotes", "get_crypto_fear_and_greed_index", "fetch_reddit_sentiment"]
        assert calls[0]["args"] == {"symbols": "ARB"}
        assert calls[2]["args"] == {"query": "ARB", "limit": 5}

    def test_extract_pseudo_call_tags(self):
        # 實測 qwen 幻覺輸出 <call_toolname arg="值"> 這種自創標籤，需被解析成真正的工具呼叫
        blob = '我來用白話文解釋！ <call_explain_crypto_term term="資金費率"> <call_get_max_fee_info>'
        calls = extract_tool_calls_from_text(blob)
        names = [c["tool"] for c in calls]
        assert names == ["explain_crypto_term", "get_max_fee_info"]
        assert calls[0]["args"] == {"term": "資金費率"}
        assert calls[1]["args"] == {}

    def test_pseudo_tags_ignore_prompt_xml(self):
        # 系統提示裡的 XML 標籤（<tools> <persona> 等）不可被誤判為工具呼叫
        assert extract_tool_calls_from_text("<tools><persona><reasoning_protocol><output_format>") == []

    def test_extract_dedupes_and_ignores_noise(self):
        # 純參數物件（無 name/tool）與重複呼叫應被過濾/去重
        blob = '{"symbols":"ARB"} {"name":"get_ohlcv","args":{"symbol":"BTC/USDT"}} {"name":"get_ohlcv","args":{"symbol":"BTC/USDT"}}'
        calls = extract_tool_calls_from_text(blob)
        assert len(calls) == 1
        assert calls[0]["tool"] == "get_ohlcv"


# ── Ollama 供應商解析 ─────────────────────────
class TestOllamaProvider:
    @patch("agent.llm.ollama.requests.post")
    def test_native_tool_calls(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "get_max_tickers", "arguments": {"market": "BTC/TWD"}}}
                ],
            }
        }
        mock_post.return_value = mock_resp

        p = OllamaProvider(model="qwen2.5:7b", host="http://x:11434")
        res = p.chat([{"role": "user", "content": "hi"}], tools=[{"type": "function"}])
        assert res.native_tools is True
        assert len(res.tool_calls) == 1
        assert res.tool_calls[0].name == "get_max_tickers"
        assert res.tool_calls[0].args == {"market": "BTC/TWD"}

    @patch("agent.llm.ollama.requests.post")
    def test_think_mode_parses_thinking(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "message": {"role": "assistant", "content": "最終答案", "thinking": "我的內部推理"}
        }
        mock_post.return_value = mock_resp
        p = OllamaProvider(model="gemma4:12b-mlx", host="http://x:11434")
        res = p.chat([{"role": "user", "content": "hi"}], think=True)
        assert res.thinking == "我的內部推理"       # 推理走 thinking 通道
        assert res.content == "最終答案"             # content 保持乾淨
        assert mock_post.call_args.kwargs["json"]["think"] is True  # payload 帶 think

    @patch("agent.llm.ollama.requests.post")
    def test_text_fallback(self, mock_post):
        # 模型未用原生 tools，內容夾帶 JSON -> 備援解析
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "message": {"role": "assistant",
                        "content": '好的 ```json\n{"tool":"get_ohlcv","args":{"symbol":"ETH/USDT"}}\n```'}
        }
        mock_post.return_value = mock_resp

        p = OllamaProvider(model="gemma2", host="http://x:11434")
        res = p.chat([{"role": "user", "content": "hi"}])
        assert res.native_tools is False
        assert res.tool_calls[0].name == "get_ohlcv"

    @patch("agent.llm.ollama.requests.post")
    def test_text_fallback_multiple_tools(self, mock_post):
        # 模型把多個工具用文字寫出 + 夾帶假結論 -> 應解析出「多個」工具呼叫，而非當成最終答案
        blob = ('我來分析。\n{"name":"get_cmc_latest_quotes","args":{"symbols":"ARB"}}\n'
                '{"name":"get_crypto_fear_and_greed_index"}\n<analysis>假設數據...</analysis>')
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"message": {"role": "assistant", "content": blob}}
        mock_post.return_value = mock_resp

        p = OllamaProvider(model="qwen3.5:9b", host="http://x:11434")
        res = p.chat([{"role": "user", "content": "分析 ARB"}])
        assert res.native_tools is False
        assert [t.name for t in res.tool_calls] == ["get_cmc_latest_quotes", "get_crypto_fear_and_greed_index"]

    @patch("agent.llm.ollama.time.sleep", return_value=None)
    @patch("agent.llm.ollama.requests.post", side_effect=Exception("boom"))
    def test_retry_then_error(self, mock_post, _sleep):
        p = OllamaProvider(model="m", host="http://x:11434", max_retries=2)
        with pytest.raises(LLMError):
            p.chat([{"role": "user", "content": "hi"}])
        assert mock_post.call_count == 3  # 初次 + 2 次重試


# ── OpenRouter 供應商解析 ──────────────────────
class TestOpenRouterProvider:
    def test_requires_key(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        with pytest.raises(LLMError):
            OpenRouterProvider(model="anthropic/claude-3.5-sonnet", api_key="")

    @patch("agent.llm.openrouter.requests.post")
    def test_openai_tool_calls(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "choices": [
                {"message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"id": "call_1", "type": "function",
                         "function": {"name": "get_ohlcv", "arguments": '{"symbol":"BTC/USDT","limit":50}'}}
                    ],
                }}
            ]
        }
        mock_post.return_value = mock_resp

        p = OpenRouterProvider(model="anthropic/claude-3.5-sonnet", api_key="sk-test")
        res = p.chat([{"role": "user", "content": "hi"}], tools=[{"type": "function"}])
        assert res.native_tools is True
        assert res.tool_calls[0].name == "get_ohlcv"
        # arguments 為 JSON 字串，應被解析成 dict
        assert res.tool_calls[0].args == {"symbol": "BTC/USDT", "limit": 50}


# ── Critic 守衛 ───────────────────────────────
class TestCriticGuard:
    def test_empty_draft_short_circuits(self):
        from agent.critic_agent import evaluate_decision

        # 空/極短草稿：不應呼叫任何 provider，直接通過
        sentinel = MagicMock()
        result = evaluate_decision(reasoning_steps=[], draft_decision="   ", provider=sentinel)
        assert "審查通過" in result
        sentinel.chat.assert_not_called()

    def test_real_draft_calls_provider(self):
        from agent.critic_agent import evaluate_decision

        provider = MagicMock()
        provider.chat.return_value = LLMResponse(content="審查通過：無發現明顯邏輯漏洞。")
        result = evaluate_decision(
            reasoning_steps=[{"type": "thought", "content_preview": "看漲"}],
            draft_decision="綜合分析後，我認為 BTC 短線偏多，但需注意風險。",
            provider=provider,
        )
        assert "審查通過" in result
        provider.chat.assert_called_once()

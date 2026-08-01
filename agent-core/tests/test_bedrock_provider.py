"""
tests/test_bedrock_provider.py

Bedrock 供應商單元測試（訊息翻譯 / 非串流 chat / ConverseStream 串流）。

為什麼要有這一份：`LLM_PROVIDER=bedrock` 是命題「限用 AWS 提供之基礎模型」下
**唯一合規的推理路徑**，而它原本零測試覆蓋——本機用 ollama 開發，Bedrock 只在
正式 demo 那天才會被執行。這裡用假的 boto3 client 把翻譯與串流組裝的邏輯釘住，
真的連線問題（憑證、model access、region）留給 `scripts/` 的端到端檢查。
"""

import json
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from agent.llm.base import LLMError


def _install_fake_boto3(client: MagicMock):
    """把假的 boto3 塞進 sys.modules，讓 BedrockProvider.__init__ 拿到它。

    BedrockProvider 是在 __init__ 內部才 `import boto3`（讓沒裝 boto3 的環境
    也能 import 這個模組），所以 patch 的落點是 sys.modules 而不是屬性。
    """
    fake_boto3 = types.ModuleType("boto3")
    fake_boto3.client = MagicMock(return_value=client)
    fake_botocore = types.ModuleType("botocore")
    fake_config_mod = types.ModuleType("botocore.config")
    fake_config_mod.Config = MagicMock()
    fake_botocore.config = fake_config_mod
    return patch.dict(sys.modules, {
        "boto3": fake_boto3,
        "botocore": fake_botocore,
        "botocore.config": fake_config_mod,
    })


def _provider(client: MagicMock):
    from agent.llm.bedrock import BedrockProvider
    with _install_fake_boto3(client):
        return BedrockProvider(model="test-model", region="us-west-2")


# ── 訊息翻譯 ─────────────────────────────
class TestMessageTranslation:
    def test_system_is_extracted(self):
        from agent.llm.bedrock import _to_bedrock_messages
        system, msgs = _to_bedrock_messages([
            {"role": "system", "content": "你是助理"},
            {"role": "user", "content": "你好"},
        ])
        assert system == [{"text": "你是助理"}]
        assert msgs == [{"role": "user", "content": [{"text": "你好"}]}]

    def test_empty_text_becomes_space(self):
        """Bedrock 不接受空字串文字塊，會回 ValidationException。"""
        from agent.llm.bedrock import _to_bedrock_messages
        _, msgs = _to_bedrock_messages([{"role": "user", "content": ""}])
        assert msgs[0]["content"][0]["text"] == " "

    def test_adjacent_same_role_is_merged(self):
        """Bedrock 要求 role 嚴格交替；相鄰的 user 必須合併成一則。"""
        from agent.llm.bedrock import _to_bedrock_messages
        _, msgs = _to_bedrock_messages([
            {"role": "user", "content": "第一句"},
            {"role": "user", "content": "第二句"},
        ])
        assert len(msgs) == 1
        assert [b["text"] for b in msgs[0]["content"]] == ["第一句", "第二句"]

    def test_tool_results_merge_into_one_user_message(self):
        from agent.llm.bedrock import _to_bedrock_messages
        _, msgs = _to_bedrock_messages([
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "t1", "function": {"name": "get_x", "arguments": '{"a":1}'}},
                {"id": "t2", "function": {"name": "get_y", "arguments": '{"b":2}'}},
            ]},
            {"role": "tool", "tool_call_id": "t1", "content": "結果一"},
            {"role": "tool", "tool_call_id": "t2", "content": "結果二"},
        ])
        assert msgs[0]["role"] == "assistant"
        assert len(msgs[0]["content"]) == 2          # 兩個 toolUse
        assert msgs[1]["role"] == "user"
        assert len(msgs[1]["content"]) == 2          # 兩個 toolResult 合併成一則
        assert msgs[1]["content"][0]["toolResult"]["toolUseId"] == "t1"

    def test_string_arguments_are_parsed_to_dict(self):
        """OpenAI 格式的 arguments 是字串，Bedrock 的 toolUse.input 要是物件。"""
        from agent.llm.bedrock import _to_bedrock_messages
        _, msgs = _to_bedrock_messages([
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "t1", "function": {"name": "get_x", "arguments": '{"symbol":"BTC"}'}},
            ]},
        ])
        assert msgs[0]["content"][0]["toolUse"]["input"] == {"symbol": "BTC"}

    def test_malformed_arguments_become_empty_dict(self):
        from agent.llm.bedrock import _to_bedrock_messages
        _, msgs = _to_bedrock_messages([
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "t1", "function": {"name": "get_x", "arguments": "{壞掉的"}},
            ]},
        ])
        assert msgs[0]["content"][0]["toolUse"]["input"] == {}


class TestToolSpec:
    def test_openai_tools_become_toolconfig(self):
        from agent.llm.bedrock import _to_bedrock_tools
        cfg = _to_bedrock_tools([{
            "type": "function",
            "function": {"name": "get_price", "description": "查價",
                         "parameters": {"type": "object", "properties": {"s": {"type": "string"}}}},
        }])
        spec = cfg["tools"][0]["toolSpec"]
        assert spec["name"] == "get_price"
        assert spec["inputSchema"]["json"]["properties"]["s"]["type"] == "string"

    def test_description_is_truncated(self):
        """Bedrock 的 description 有長度上限，超過會 ValidationException。"""
        from agent.llm.bedrock import _to_bedrock_tools
        cfg = _to_bedrock_tools([{"function": {"name": "x", "description": "描" * 5000}}])
        assert len(cfg["tools"][0]["toolSpec"]["description"]) == 1000


# ── 非串流 ─────────────────────────────
class TestChat:
    def test_text_and_tool_calls_are_parsed(self):
        client = MagicMock()
        client.converse.return_value = {"output": {"message": {"content": [
            {"text": "我來查一下。"},
            {"toolUse": {"toolUseId": "tu1", "name": "get_max_ticker", "input": {"market": "btctwd"}}},
        ]}}}
        r = _provider(client).chat([{"role": "user", "content": "BTC 多少"}])
        assert r.content == "我來查一下。"
        assert len(r.tool_calls) == 1
        assert r.tool_calls[0].name == "get_max_ticker"
        assert r.tool_calls[0].args == {"market": "btctwd"}
        assert r.native_tools is True
        assert r.raw_message["tool_calls"][0]["function"]["arguments"] == '{"market": "btctwd"}'

    def test_throttling_is_retried_then_raises_llmerror(self):
        client = MagicMock()
        client.converse.side_effect = RuntimeError("ThrottlingException: slow down")
        with patch("time.sleep"):
            with pytest.raises(LLMError, match="Bedrock Converse 失敗"):
                _provider(client).chat([{"role": "user", "content": "hi"}])
        assert client.converse.call_count == 3       # 初次 + max_retries(2)

    def test_tools_are_passed_through(self):
        client = MagicMock()
        client.converse.return_value = {"output": {"message": {"content": [{"text": "ok"}]}}}
        _provider(client).chat(
            [{"role": "user", "content": "hi"}],
            tools=[{"function": {"name": "f", "description": "d", "parameters": {"type": "object"}}}],
        )
        kwargs = client.converse.call_args.kwargs
        assert kwargs["toolConfig"]["tools"][0]["toolSpec"]["name"] == "f"


# ── 串流 ─────────────────────────────
def _stream_events(events):
    client = MagicMock()
    client.converse_stream.return_value = {"stream": iter(events)}
    return client


class TestChatStream:
    def test_yields_deltas_then_final(self):
        client = _stream_events([
            {"messageStart": {"role": "assistant"}},
            {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "你"}}},
            {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "好"}}},
            {"contentBlockStop": {"contentBlockIndex": 0}},
            {"messageStop": {"stopReason": "end_turn"}},
        ])
        out = list(_provider(client).chat_stream([{"role": "user", "content": "hi"}]))
        assert [k for k, _ in out] == ["delta", "delta", "final"]
        assert [p for k, p in out if k == "delta"] == ["你", "好"]
        assert out[-1][1].content == "你好"
        assert out[-1][1].tool_calls == []

    def test_partial_json_tool_args_are_reassembled(self):
        """toolUse.input 是分段的 partial JSON，中途 json.loads 一定失敗，
        必須整段收完才解析——這是 ConverseStream 最容易寫錯的地方。"""
        client = _stream_events([
            {"contentBlockStart": {"contentBlockIndex": 0,
                                   "start": {"toolUse": {"toolUseId": "tu1", "name": "get_max_kline"}}}},
            {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"toolUse": {"input": '{"mark'}}}},
            {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"toolUse": {"input": 'et":"btc'}}}},
            {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"toolUse": {"input": 'twd","limit":50}'}}}},
            {"messageStop": {"stopReason": "tool_use"}},
        ])
        out = list(_provider(client).chat_stream([{"role": "user", "content": "K線"}]))
        assert [k for k, _ in out] == ["final"]      # 純工具回合，沒有 delta
        final = out[-1][1]
        assert final.tool_calls[0].name == "get_max_kline"
        assert final.tool_calls[0].args == {"market": "btctwd", "limit": 50}
        assert json.loads(final.raw_message["tool_calls"][0]["function"]["arguments"])["limit"] == 50

    def test_interleaved_text_and_tool_blocks(self):
        """文字與 toolUse 可能落在不同的 contentBlockIndex 且交錯出現。"""
        client = _stream_events([
            {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "先查行情"}}},
            {"contentBlockStart": {"contentBlockIndex": 1,
                                   "start": {"toolUse": {"toolUseId": "a", "name": "tool_a"}}}},
            {"contentBlockStart": {"contentBlockIndex": 2,
                                   "start": {"toolUse": {"toolUseId": "b", "name": "tool_b"}}}},
            {"contentBlockDelta": {"contentBlockIndex": 1, "delta": {"toolUse": {"input": '{"x":1}'}}}},
            {"contentBlockDelta": {"contentBlockIndex": 2, "delta": {"toolUse": {"input": '{"y":2}'}}}},
            {"messageStop": {"stopReason": "tool_use"}},
        ])
        final = list(_provider(client).chat_stream([{"role": "user", "content": "hi"}]))[-1][1]
        assert final.content == "先查行情"
        names = {tc.name: tc.args for tc in final.tool_calls}
        assert names == {"tool_a": {"x": 1}, "tool_b": {"y": 2}}

    def test_broken_tool_json_degrades_to_empty_args(self):
        """收到不完整的 JSON 就當空參數，讓工具自己回參數錯誤——
        比在這裡丟例外炸掉整輪好，模型下一輪還有機會補正。"""
        client = _stream_events([
            {"contentBlockStart": {"contentBlockIndex": 0,
                                   "start": {"toolUse": {"toolUseId": "t", "name": "f"}}}},
            {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"toolUse": {"input": '{"a":'}}}},
            {"messageStop": {"stopReason": "tool_use"}},
        ])
        final = list(_provider(client).chat_stream([{"role": "user", "content": "hi"}]))[-1][1]
        assert final.tool_calls[0].args == {}

    def test_stream_error_becomes_llmerror(self):
        client = MagicMock()
        client.converse_stream.side_effect = RuntimeError("no credentials")
        with pytest.raises(LLMError, match="ConverseStream 失敗"):
            list(_provider(client).chat_stream([{"role": "user", "content": "hi"}]))

    def test_main_loop_will_pick_the_streaming_branch(self):
        """run_agent_turn 用 hasattr(provider,'chat_stream') 決定走不走串流。
        這條斷言就是那個介面契約——刪掉 chat_stream 會讓整個聊天靜默降級，
        而且不會有任何錯誤訊息。"""
        client = _stream_events([{"messageStop": {"stopReason": "end_turn"}}])
        assert hasattr(_provider(client), "chat_stream")

    def test_stream_and_nonstream_build_the_same_request(self):
        """兩條路徑共用 _build_kwargs；分開組裝遲早會漂（例如只有一邊加了
        cachePoint 或改了 maxTokens）。"""
        msgs = [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}]
        tools = [{"function": {"name": "f", "description": "d", "parameters": {"type": "object"}}}]

        c1 = MagicMock()
        c1.converse.return_value = {"output": {"message": {"content": [{"text": "x"}]}}}
        _provider(c1).chat(msgs, tools=tools)

        c2 = _stream_events([{"messageStop": {}}])
        list(_provider(c2).chat_stream(msgs, tools=tools))

        assert c1.converse.call_args.kwargs == c2.converse_stream.call_args.kwargs

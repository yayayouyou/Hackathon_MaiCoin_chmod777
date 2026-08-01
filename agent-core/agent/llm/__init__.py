"""
agent/llm

LLM 供應商抽象層 (Provider Abstraction)
=====================================================
把大腦與具體 LLM 供應商解耦，支援：
  - Ollama    (本地/自架，原生 tools function-calling，含文字解析備援)
  - OpenRouter(OpenAI 相容雲端閘道，一把 key 可接 Claude / GPT 等)

所有供應商共用統一介面 `LLMProvider.chat(messages, tools) -> LLMResponse`，
回傳結構化的 `tool_calls`，讓 ReAct 迴圈不再依賴脆弱的文字 JSON 解析。
"""

from agent.llm.base import (
    LLMProvider, LLMResponse, ToolCall, LLMError,
    parse_text_tool_call, extract_tool_calls_from_text,
)
from agent.llm.factory import get_provider

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "ToolCall",
    "LLMError",
    "parse_text_tool_call",
    "extract_tool_calls_from_text",
    "get_provider",
]

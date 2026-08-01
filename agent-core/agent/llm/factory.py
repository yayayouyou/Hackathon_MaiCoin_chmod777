"""
agent/llm/factory.py

依環境變數 LLM_PROVIDER 建立對應的供應商實例。
"""

import os
from typing import Optional
from loguru import logger

from agent.llm.base import LLMProvider
from agent.ollama_config import resolve_host, resolve_auth

DEFAULT_OLLAMA_MODEL = "gemma4:12b-mlx"
DEFAULT_OPENROUTER_MODEL = "google/gemini-2.5-flash"  # 舊的 claude-3.5-sonnet 已從 OpenRouter 下架


def get_provider(
    model_name: Optional[str] = None,
    host: Optional[str] = None,
    provider_name: Optional[str] = None,
) -> LLMProvider:
    """
    建立 LLM 供應商。

    Args:
        model_name: 模型名稱（Ollama 用；OpenRouter 未指定時改用 OPENROUTER_MODEL）
        host:       Ollama host 覆蓋（前端可傳入）
        provider_name: 覆蓋 LLM_PROVIDER，方便測試
    """
    name = (provider_name or os.getenv("LLM_PROVIDER", "ollama")).strip().lower()

    if name == "bedrock":
        from agent.llm.bedrock import BedrockProvider, DEFAULT_BEDROCK_MODEL
        # 前端下拉可能帶 Ollama 名稱；Bedrock 模型 id 一律含 "anthropic"/"claude"，否則用 BEDROCK_MODEL
        ml = (model_name or "").lower()
        model = model_name if (model_name and ("anthropic" in ml or "claude" in ml)) \
            else os.getenv("BEDROCK_MODEL", DEFAULT_BEDROCK_MODEL)
        logger.info(f"使用 Bedrock 供應商，模型: {model}")
        return BedrockProvider(model=model)

    if name == "openrouter":
        from agent.llm.openrouter import OpenRouterProvider
        # 前端模型下拉可能仍帶 Ollama 名稱（如 gemma4:12b-mlx）。OpenRouter 的模型 id 一律是
        # "vendor/model" 格式，因此只有當傳入的 model_name 看起來像 OpenRouter id（含 "/"）才採用，
        # 否則以 .env 的 OPENROUTER_MODEL 為準，避免把 Ollama 名稱送去 OpenRouter 而 404。
        env_model = os.getenv("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)
        model = model_name if (model_name and "/" in model_name) else env_model
        logger.info(f"使用 OpenRouter 供應商，模型: {model}")
        return OpenRouterProvider(model=model)

    # 預設：Ollama
    from agent.llm.ollama import OllamaProvider
    # 與 Bedrock/OpenRouter 一致，讓 .env 的 OLLAMA_MODEL 可覆蓋內建預設。
    # 沒有這個覆蓋點時，後端內部呼叫 LLM 的工具（社群情緒分析等）只能吃寫死的
    # DEFAULT_OLLAMA_MODEL —— 在沒裝該模型的機器上一律 404，且錯誤訊息會誤導成
    # 「/api/chat 路徑不存在」。前端傳入的 model_name 仍優先。
    model = model_name or os.getenv("OLLAMA_MODEL", "").strip() or DEFAULT_OLLAMA_MODEL
    resolved_host = resolve_host(host)
    logger.info(f"使用 Ollama 供應商，模型: {model}，host: {resolved_host}")
    return OllamaProvider(model=model, host=resolved_host, auth=resolve_auth())

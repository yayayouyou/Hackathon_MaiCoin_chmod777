"""
agent/llm/openrouter.py

OpenRouter 供應商（OpenAI 相容雲端閘道）。
一把 OPENROUTER_API_KEY 可接 Claude / GPT / Llama 等強模型，
使用原生 function-calling。尚未設定 key 時建構會拋 LLMError。
"""

import os
import time
import json
import requests
from typing import Any, Dict, List, Optional
from loguru import logger

from agent.llm.base import LLMProvider, LLMResponse, ToolCall, LLMError


class OpenRouterProvider(LLMProvider):
    name = "openrouter"
    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        timeout: int = 180,
        max_retries: int = 2,
    ):
        self._model = model
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        if not self.api_key:
            raise LLMError(
                "OPENROUTER_API_KEY 未設定。請在 .env 填入 OpenRouter 金鑰，"
                "或將 LLM_PROVIDER 設回 ollama。"
            )
        self.timeout = timeout
        self.max_retries = max_retries

    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # OpenRouter 建議帶上來源識別（非必填）
            "HTTP-Referer": "https://github.com/ai-crypto-trading-agent",
            "X-Title": "AI Crypto Trading Agent",
        }
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.post(self.BASE_URL, json=payload, headers=headers, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt < self.max_retries:
                    backoff = 1.5 * (attempt + 1)
                    logger.warning(f"OpenRouter 請求失敗（第 {attempt + 1} 次），{backoff:.1f}s 後重試: {e}")
                    time.sleep(backoff)
        raise LLMError(f"OpenRouter 連線失敗（已重試 {self.max_retries} 次）: {last_err}")

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        think: Optional[bool] = None,     # OpenRouter 不支援 gemma 原生 think，接受但忽略
        format: Optional[Dict[str, Any]] = None,  # 結構化輸出：OpenRouter 走 response_format，此處先接受（未實作映射）
    ) -> LLMResponse:
        payload: Dict[str, Any] = {"model": self._model, "messages": messages}
        if temperature is not None:
            payload["temperature"] = temperature
        if tools:
            payload["tools"] = tools

        data = self._post(payload)
        choices = data.get("choices") or []
        if not choices:
            raise LLMError(f"OpenRouter 回覆缺少 choices: {data}")
        choice_msg = choices[0].get("message", {}) or {}
        content = (choice_msg.get("content") or "").strip()

        tool_calls: List[ToolCall] = []
        raw_tcs = choice_msg.get("tool_calls") or []
        for i, tc in enumerate(raw_tcs):
            fn = tc.get("function", {}) or {}
            args = fn.get("arguments", "{}")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            tool_calls.append(ToolCall(
                id=str(tc.get("id") or f"or-{i}"),
                name=fn.get("name", ""),
                args=args or {},
            ))

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            raw_message=choice_msg or {"role": "assistant", "content": content},
            native_tools=bool(raw_tcs),
        )

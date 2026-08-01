"""
agent/llm/ollama.py

Ollama 供應商：優先使用原生 tools function-calling，
對不支援 tools 的模型則以文字解析備援。含重試/退避。
"""

import time
import json
import requests
from typing import Any, Dict, List, Optional
from loguru import logger

from agent.llm.base import LLMProvider, LLMResponse, ToolCall, LLMError, extract_tool_calls_from_text


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(
        self,
        model: str,
        host: str,
        auth: Optional[tuple] = None,
        num_ctx: int = 32768,
        timeout: int = 300,
        max_retries: int = 2,
        keep_alive: str = "30m",
        default_temperature: float = 0.2,
    ):
        self._model = model
        self.host = host.rstrip("/")
        self.auth = auth
        # num_ctx=32768：移除內嵌 schema 後 prompt 大幅縮小，24GB M4 因 gemma 的 SWA 機制
        # 32K context 僅約 2.3GB KV，很寬裕；放大是為了避免多步分析時工具歷史被前端截斷。
        self.num_ctx = num_ctx
        self.timeout = timeout
        self.max_retries = max_retries
        # keep_alive：讓模型在記憶體多留一段時間，避免每輪冷載入（預設 5 分鐘太短）。
        self.keep_alive = keep_alive
        # 工具呼叫預設低溫（gemma4 原生預設 temperature=1.0 對 function-calling 是災難；
        # 研究顯示工具呼叫 temp 0 vs 0.7 可差 10% 準確率）。呼叫端可覆蓋。
        self.default_temperature = default_temperature

    def _probe(self, path: str) -> str:
        """輕量探測某端點，回傳簡短狀態字串（供 404 診斷用，不拋錯）。"""
        try:
            r = requests.get(f"{self.host}{path}", auth=self.auth, timeout=8)
            body = (r.text or "")[:60].replace("\n", " ")
            return f"HTTP {r.status_code} {body}"
        except Exception as e:  # noqa: BLE001
            return f"連線失敗 ({e.__class__.__name__})"

    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.host}/api/chat"
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.post(url, json=payload, auth=self.auth, timeout=self.timeout)
                # 404 不重試：伺服器有回應但找不到 /api/chat，重試無意義，直接給精準診斷。
                if resp.status_code == 404:
                    # Ollama 對「模型不存在」也回 404 —— 先分辨清楚，否則會被導去查代理設定。
                    body = (resp.text or "")[:300]
                    if "not found" in body.lower() and "model" in body.lower():
                        raise LLMError(
                            f"Ollama 找不到模型 `{self.model}`。\n"
                            f"  伺服器回應：{body}\n"
                            "  請在設定裡改選已安裝的模型，或先 `ollama pull` 該模型。\n"
                            "  （注意 *-mlx 是 macOS 專用的 MLX build，Linux/CUDA 機器上不存在。）"
                        )
                    ver = self._probe("/api/version")
                    tags = self._probe("/api/tags")
                    raise LLMError(
                        "Ollama 回傳 404：伺服器有回應，但 `/api/chat` 路徑不存在。\n"
                        f"  ├ 探測 /api/version → {ver}\n"
                        f"  └ 探測 /api/tags    → {tags}\n"
                        "  常見原因：(1) OLLAMA_HOST 前有反向代理（Basic Auth）但未把 /api/* 轉發到 Ollama；"
                        "(2) 該端點根本不是 Ollama 或版本過舊；(3) 正確位址可能含子路徑（如 /ollama）。\n"
                        f"  目前 host = {self.host}\n"
                        "  可執行 `python scratch/diagnose_ollama.py` 取得完整診斷。"
                    )
                resp.raise_for_status()
                return resp.json()
            except LLMError:
                raise  # 404 診斷訊息直接上拋，不進重試
            except Exception as e:  # noqa: BLE001 — 網路/其他 HTTP 皆重試
                last_err = e
                if attempt < self.max_retries:
                    backoff = 1.5 * (attempt + 1)
                    logger.warning(f"Ollama 請求失敗（第 {attempt + 1} 次），{backoff:.1f}s 後重試: {e}")
                    time.sleep(backoff)
        raise LLMError(f"Ollama 連線失敗（已重試 {self.max_retries} 次）: {last_err}")

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        think: Optional[bool] = None,
        format: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        options: Dict[str, Any] = {"num_ctx": self.num_ctx}
        # 未明確指定溫度時，套用低溫預設（利於工具呼叫穩定度）
        options["temperature"] = temperature if temperature is not None else self.default_temperature
        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": options,
            "keep_alive": self.keep_alive,
        }
        if tools:
            payload["tools"] = tools
        # gemma4 原生思考通道：think=True 時推理走 message.thinking，content 保持乾淨
        if think is not None:
            payload["think"] = think
        # 結構化輸出：傳入 JSON schema → llama.cpp grammar 約束，content 保證是合法 JSON
        if format is not None:
            payload["format"] = format

        data = self._post(payload)
        return self._build_response(data.get("message", {}) or {})

    def _build_response(self, msg: Dict[str, Any]) -> LLMResponse:
        """把 ollama 回應的 message dict 解析成 LLMResponse（native tool_calls + 文字備援）。
        chat()（一次拿完整）與 chat_stream()（串流累積後）共用同一套解析。"""
        content = (msg.get("content") or "").strip()
        thinking = (msg.get("thinking") or "").strip()

        tool_calls: List[ToolCall] = []
        native = False

        raw_tcs = msg.get("tool_calls")
        if raw_tcs:
            native = True
            for i, tc in enumerate(raw_tcs):
                fn = tc.get("function", {}) or {}
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                tool_calls.append(ToolCall(
                    id=str(tc.get("id") or f"ollama-{i}"),
                    name=fn.get("name", ""),
                    args=args or {},
                ))
        elif content:
            # 備援：模型未使用原生 tools，改由文字解析「所有」工具呼叫
            # （模型常把多個工具呼叫用文字寫出，需全部抓出來真正執行，避免當成最終答案）
            for i, call in enumerate(extract_tool_calls_from_text(content)):
                tool_calls.append(ToolCall(
                    id=f"textparse-{i}",
                    name=call["tool"],
                    args=call.get("args", {}) or {},
                ))

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            raw_message=msg or {"role": "assistant", "content": content},
            native_tools=native,
            thinking=thinking,
        )

    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        think: Optional[bool] = None,
        format: Optional[Dict[str, Any]] = None,
    ):
        """串流版 chat：POST `stream:True`，逐行讀 NDJSON。
        依序 `yield ("delta", content_piece)`（每個內容增量），最後 `yield ("final", LLMResponse)`。
        因 ollama 有『文字解析工具呼叫』備援（需完整 content 才能判斷），呼叫端應把 delta 視為
        『暫顯』，等 final 才定案是最終答案還是工具前導文字。"""
        options: Dict[str, Any] = {"num_ctx": self.num_ctx}
        options["temperature"] = temperature if temperature is not None else self.default_temperature
        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "options": options,
            "keep_alive": self.keep_alive,
        }
        if tools:
            payload["tools"] = tools
        if think is not None:
            payload["think"] = think
        if format is not None:
            payload["format"] = format

        url = f"{self.host}/api/chat"
        acc_content, acc_thinking = "", ""
        final_tool_calls = None
        try:
            with requests.post(url, json=payload, auth=self.auth, timeout=self.timeout, stream=True) as resp:
                if resp.status_code == 404:
                    body = (resp.text or "")[:300]
                    if "not found" in body.lower() and "model" in body.lower():
                        raise LLMError(f"Ollama 找不到模型 `{self.model}`：{body}"
                                       "（*-mlx 是 macOS 專用 build，Linux 機器上不存在）")
                    raise LLMError("Ollama 回傳 404：`/api/chat` 路徑不存在（串流模式）。")
                resp.raise_for_status()
                for line in resp.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    m = obj.get("message", {}) or {}
                    piece = m.get("content") or ""
                    if piece:
                        acc_content += piece
                        yield ("delta", piece)
                    if m.get("thinking"):
                        acc_thinking += m["thinking"]
                    if m.get("tool_calls"):
                        final_tool_calls = m["tool_calls"]
                    if obj.get("done"):
                        break
        except LLMError:
            raise
        except Exception as e:  # noqa: BLE001
            raise LLMError(f"Ollama 串流失敗: {e}")

        final_msg: Dict[str, Any] = {"role": "assistant", "content": acc_content}
        if acc_thinking:
            final_msg["thinking"] = acc_thinking
        if final_tool_calls:
            final_msg["tool_calls"] = final_tool_calls
        yield ("final", self._build_response(final_msg))

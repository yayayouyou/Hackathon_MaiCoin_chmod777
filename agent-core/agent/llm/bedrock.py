"""
agent/llm/bedrock.py

Amazon Bedrock 供應商（Claude on Bedrock，原生 function-calling via Converse API）。
與 OpenRouter/Ollama 同介面：對外收/回 OpenAI 格式（messages/tools/raw_message），
內部翻譯成 Bedrock Converse 格式 → 讓 run_agent_turn 的迴圈與其他 provider 完全一致。

啟用：LLM_PROVIDER=bedrock，BEDROCK_MODEL=<inference-profile-id>，AWS 憑證由環境/IAM 提供。
（AgentCore Runtime / Lambda 環境天生有 boto3 與 IAM 角色。）
"""
import os
import json
import time
from typing import Any, Dict, List, Optional, Tuple
from loguru import logger

from agent.llm.base import LLMProvider, LLMResponse, ToolCall, LLMError

DEFAULT_BEDROCK_MODEL = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"  # 跨區推理設定檔；可用 BEDROCK_MODEL 覆蓋


def _to_bedrock_tools(tools: List[Dict[str, Any]]) -> Dict[str, Any]:
    """OpenAI tools → Bedrock toolConfig。"""
    specs = []
    for t in tools or []:
        fn = t.get("function", {}) or {}
        specs.append({"toolSpec": {
            "name": fn.get("name", ""),
            "description": (fn.get("description", "") or "")[:1000],
            "inputSchema": {"json": fn.get("parameters") or {"type": "object", "properties": {}}},
        }})
    return {"tools": specs}


def _text_block(s: str) -> Dict[str, Any]:
    # Bedrock 不接受空字串文字塊 → 空的補一個空白
    return {"text": s if (s and s.strip()) else " "}


def _to_bedrock_messages(messages: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """OpenAI messages → (system 區塊, Bedrock messages)。tool 結果合併成一則 user.toolResult。"""
    system: List[Dict[str, Any]] = []
    bmsgs: List[Dict[str, Any]] = []
    pending: List[Dict[str, Any]] = []

    def flush():
        if pending:
            bmsgs.append({"role": "user", "content": list(pending)})
            pending.clear()

    for m in messages or []:
        role = m.get("role")
        if role == "system":
            system.append(_text_block(m.get("content", "")))
        elif role == "tool":
            c = m.get("content", "")
            pending.append({"toolResult": {
                "toolUseId": str(m.get("tool_call_id") or m.get("name") or "t"),
                "content": [{"text": c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)}],
            }})
        elif role == "user":
            flush()
            bmsgs.append({"role": "user", "content": [_text_block(m.get("content", ""))]})
        elif role == "assistant":
            flush()
            blocks: List[Dict[str, Any]] = []
            if (m.get("content") or "").strip():
                blocks.append({"text": m["content"]})
            for tc in (m.get("tool_calls") or []):
                fn = tc.get("function", {}) or {}
                args = fn.get("arguments", "{}")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                blocks.append({"toolUse": {"toolUseId": str(tc.get("id") or "tc"),
                                           "name": fn.get("name", ""), "input": args or {}}})
            bmsgs.append({"role": "assistant", "content": blocks or [_text_block("")]})
    flush()
    # Bedrock 要求 role 嚴格交替 → 合併相鄰同 role（例：toolResult(user) 後接 user 提問）
    merged: List[Dict[str, Any]] = []
    for m in bmsgs:
        if merged and merged[-1]["role"] == m["role"]:
            merged[-1]["content"].extend(m["content"])
        else:
            merged.append(m)
    return system, merged


class BedrockProvider(LLMProvider):
    name = "bedrock"

    def __init__(self, model: Optional[str] = None, region: Optional[str] = None,
                 timeout: int = 180, max_retries: int = 2):
        self._model = model or os.getenv("BEDROCK_MODEL", DEFAULT_BEDROCK_MODEL)
        self.max_retries = max_retries
        try:
            import boto3
            from botocore.config import Config
        except ImportError as e:
            raise LLMError("未安裝 boto3。請 `pip install boto3`（AgentCore/Lambda 環境內建）。") from e
        reg = region or os.getenv("BEDROCK_REGION") or os.getenv("AWS_REGION") or "us-west-2"
        try:
            self._client = boto3.client("bedrock-runtime", region_name=reg,
                                        config=Config(read_timeout=timeout, retries={"max_attempts": 1}))
        except Exception as e:  # noqa: BLE001
            raise LLMError(f"建立 Bedrock client 失敗（檢查 AWS 憑證/區域）: {e}") from e

    def _converse(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        last: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                return self._client.converse(**kwargs)
            except Exception as e:  # noqa: BLE001 — 節流/暫時錯誤重試
                last = e
                if attempt < self.max_retries and "Throttl" in str(e):
                    time.sleep(1.5 * (attempt + 1))
                    continue
                break
        raise LLMError(f"Bedrock Converse 失敗: {last}")

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        think: Optional[bool] = None,          # Bedrock 無 gemma 原生 think；接受並忽略
        format: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        kwargs = self._build_kwargs(messages, tools, temperature, format)
        resp = self._converse(kwargs)
        out_msg = (resp.get("output") or {}).get("message") or {}
        text_parts: List[str] = []
        tool_calls: List[ToolCall] = []
        oai_tcs: List[Dict[str, Any]] = []
        for b in out_msg.get("content", []) or []:
            if "text" in b:
                text_parts.append(b["text"])
            elif "toolUse" in b:
                tu = b["toolUse"]
                tool_calls.append(ToolCall(id=str(tu.get("toolUseId", "")),
                                           name=tu.get("name", ""), args=tu.get("input") or {}))
                oai_tcs.append({"id": str(tu.get("toolUseId", "")), "type": "function",
                                "function": {"name": tu.get("name", ""),
                                             "arguments": json.dumps(tu.get("input") or {}, ensure_ascii=False)}})
        content = "".join(text_parts).strip()
        raw: Dict[str, Any] = {"role": "assistant", "content": content}
        if oai_tcs:
            raw["tool_calls"] = oai_tcs
        return LLMResponse(content=content, tool_calls=tool_calls, raw_message=raw, native_tools=bool(tool_calls))

    def _build_kwargs(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        temperature: Optional[float],
        format: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """chat 與 chat_stream 共用的請求組裝。兩邊各組一次遲早會漂。"""
        system, bmsgs = _to_bedrock_messages(messages)
        if format:
            system.append({"text": "You must reply with ONLY a single valid JSON object matching this JSON "
                                   "schema (no prose, no markdown fences): " + json.dumps(format)})
        infcfg: Dict[str, Any] = {"maxTokens": int(os.getenv("BEDROCK_MAX_TOKENS", "4096"))}
        if temperature is not None:
            infcfg["temperature"] = float(temperature)
        kwargs: Dict[str, Any] = {"modelId": self._model, "messages": bmsgs, "inferenceConfig": infcfg}
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["toolConfig"] = _to_bedrock_tools(tools)
        return kwargs

    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        think: Optional[bool] = None,          # Bedrock 無 gemma 原生 think；接受並忽略
        format: Optional[Dict[str, Any]] = None,
    ):
        """串流版 chat（ConverseStream）。

        介面與 ollama.chat_stream 完全一致：依序 `yield ("delta", 文字增量)`，
        最後 `yield ("final", LLMResponse)`。

        `run_agent_turn` 用 `hasattr(provider, "chat_stream")` 決定走不走串流分支，
        所以這個方法一旦存在，主迴圈**一行都不用改**就會自動改走串流。

        三個 Converse Stream 的實務細節：
        ① 工具參數是**分段的 partial JSON**（`toolUse.input` 每次來一小截字串），
           必須整段收完才能 json.loads —— 中途解析一定會失敗。
        ② `contentBlockStart` 才帶 toolUseId 與工具名，`contentBlockDelta` 只帶
           input 片段，靠 `contentBlockIndex` 對應回去。
        ③ 文字與 toolUse 可能交錯在不同 block index，所以用 dict 而不是「當前這個」。
        """
        kwargs = self._build_kwargs(messages, tools, temperature, format)

        try:
            resp = self._client.converse_stream(**kwargs)
        except Exception as e:  # noqa: BLE001
            raise LLMError(f"Bedrock ConverseStream 失敗: {e}") from e

        text_parts: List[str] = []
        # blockIndex → {"id","name","buf"}；buf 是還沒收完的 partial JSON
        tool_blocks: Dict[int, Dict[str, Any]] = {}

        try:
            for event in resp.get("stream", []):
                if "contentBlockStart" in event:
                    ev = event["contentBlockStart"]
                    start = ev.get("start") or {}
                    if "toolUse" in start:
                        tu = start["toolUse"]
                        tool_blocks[ev.get("contentBlockIndex", 0)] = {
                            "id": str(tu.get("toolUseId", "")),
                            "name": tu.get("name", ""),
                            "buf": "",
                        }

                elif "contentBlockDelta" in event:
                    ev = event["contentBlockDelta"]
                    delta = ev.get("delta") or {}
                    if "text" in delta:
                        piece = delta["text"]
                        if piece:
                            text_parts.append(piece)
                            yield ("delta", piece)
                    elif "toolUse" in delta:
                        idx = ev.get("contentBlockIndex", 0)
                        blk = tool_blocks.get(idx)
                        if blk is not None:
                            blk["buf"] += delta["toolUse"].get("input", "") or ""

                elif "messageStop" in event:
                    break

                # metadata / messageStart / contentBlockStop 不需要處理
        except Exception as e:  # noqa: BLE001 — 串到一半斷線
            raise LLMError(f"Bedrock 串流中斷: {e}") from e

        tool_calls: List[ToolCall] = []
        oai_tcs: List[Dict[str, Any]] = []
        for blk in tool_blocks.values():
            buf = blk["buf"].strip()
            try:
                args = json.loads(buf) if buf else {}
            except json.JSONDecodeError:
                # 收到不完整的 JSON 就當空參數，讓工具自己回參數錯誤，
                # 比在這裡丟例外炸掉整輪好 —— 模型下一輪還有機會補正。
                logger.warning(f"Bedrock toolUse 參數解析失敗（{blk['name']}）: {buf[:120]}")
                args = {}
            tool_calls.append(ToolCall(id=blk["id"], name=blk["name"], args=args))
            oai_tcs.append({"id": blk["id"], "type": "function",
                            "function": {"name": blk["name"],
                                         "arguments": json.dumps(args, ensure_ascii=False)}})

        content = "".join(text_parts).strip()
        raw: Dict[str, Any] = {"role": "assistant", "content": content}
        if oai_tcs:
            raw["tool_calls"] = oai_tcs
        yield ("final", LLMResponse(content=content, tool_calls=tool_calls,
                                    raw_message=raw, native_tools=bool(tool_calls)))

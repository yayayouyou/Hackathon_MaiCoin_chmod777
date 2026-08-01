"""
agent/llm/base.py

LLM 供應商共用型別與介面
=====================================================
"""

import re
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class LLMError(Exception):
    """LLM 供應商呼叫失敗（連線、認證、額度等）。"""


@dataclass
class ToolCall:
    """一次工具呼叫請求。"""
    id: str
    name: str
    args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """供應商回覆的統一結構。"""
    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    # 供應商原生的 assistant 訊息 dict，於多輪對話時原樣附回以維持上下文
    raw_message: Optional[Dict[str, Any]] = None
    # tool_calls 是否來自原生 function-calling API（False = 由文字解析備援取得）
    native_tools: bool = False
    # 原生 thinking 通道的推理內容（gemma4 think 模式；不進最終答案，僅供觀察/規劃）
    thinking: str = ""


class LLMProvider:
    """所有供應商的抽象基底。"""
    name: str = "base"

    @property
    def model(self) -> str:
        return getattr(self, "_model", "")

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        think: Optional[bool] = None,
        format: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        raise NotImplementedError


# 工具名稱常見前綴（用於在雜訊中辨識工具呼叫物件）
_TOOL_NAME_PREFIXES = (
    "get_", "fetch_", "search_", "run_", "calculate_", "create_",
    "cancel_", "save_", "list_", "analyze_", "detect_",
)


def _iter_json_objects(content: str):
    """逐一 yield 文字中每一個「平衡括號」且可解析的 JSON 物件 (dict)。"""
    if not content:
        return
    i, n = 0, len(content)
    while i < n:
        if content[i] != "{":
            i += 1
            continue
        depth = 0
        for j in range(i, n):
            ch = content[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = content[i:j + 1]
                    try:
                        obj = json.loads(candidate)
                        if isinstance(obj, dict):
                            yield obj
                    except json.JSONDecodeError:
                        pass
                    i = j + 1
                    break
        else:
            # 沒有配對的右括號，結束
            return


def _normalize_tool_obj(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """把一個 dict 正規化為 {'tool': name, 'args': {...}}；非工具呼叫則回 None。"""
    name = obj.get("tool") or obj.get("name") or obj.get("function")
    # 有些模型會包成 {"function": {"name":..., "arguments":...}}
    if isinstance(name, dict):
        inner = name
        name = inner.get("name")
        obj = {**obj, "args": inner.get("arguments", inner.get("args", {}))}
    if not isinstance(name, str) or not name:
        return None
    args = obj.get("args")
    if args is None:
        args = obj.get("arguments")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}
    if not isinstance(args, dict):
        args = {}
    # 過濾雜訊：需帶 args/arguments 欄位，或名稱符合工具前綴，才視為工具呼叫
    has_args_field = ("args" in obj) or ("arguments" in obj)
    if not has_args_field and not name.startswith(_TOOL_NAME_PREFIXES):
        return None
    return {"tool": name, "args": args}


# 幻覺式「偽標籤」工具呼叫：小模型常把工具寫成 <call_toolname arg="值"> 這種自創標籤
# （實測 qwen 會輸出 <call_explain_crypto_term term="資金費率"> 這種，若不解析就會把標籤當答案洩漏給用戶）
_TOOL_PREFIX_ALT = "get|fetch|search|run|calculate|create|cancel|save|list|analyze|detect|explain"
_PSEUDO_TAG_RE = re.compile(
    r"<\s*(call_[a-zA-Z_]\w*|(?:%s)_[a-zA-Z_]\w*)\s*([^>]*?)/?>" % _TOOL_PREFIX_ALT
)
_ATTR_RE = re.compile(r'([a-zA-Z_]\w*)\s*=\s*"([^"]*)"|([a-zA-Z_]\w*)\s*=\s*\'([^\']*)\'')


def _extract_pseudo_tag_calls(content: str) -> List[Dict[str, Any]]:
    """解析 <call_toolname key="v"> / <toolname key='v'> 這類自創標籤式工具呼叫。"""
    out: List[Dict[str, Any]] = []
    for m in _PSEUDO_TAG_RE.finditer(content or ""):
        name = m.group(1)
        if name.startswith("call_"):
            name = name[len("call_"):]
        if not name:
            continue
        args: Dict[str, Any] = {}
        for a in _ATTR_RE.finditer(m.group(2) or ""):
            key = a.group(1) if a.group(1) is not None else a.group(3)
            val = a.group(2) if a.group(2) is not None else a.group(4)
            if key:
                args[key] = val
        out.append({"tool": name, "args": args})
    return out


def extract_tool_calls_from_text(content: str) -> List[Dict[str, Any]]:
    """
    文字解析備援：抽取「所有」看似工具呼叫的物件（去重，保序）。
    支援三種格式：
      1. {"tool":..,"args":..}
      2. OpenAI 風格 {"name":..,"args"/"arguments":..}
      3. 幻覺偽標籤 <call_toolname arg="值"> / <toolname arg='值'>
    僅在供應商/模型「不支援原生 tools」時使用。
    """
    calls: List[Dict[str, Any]] = []
    seen = set()

    def _add(norm: Optional[Dict[str, Any]]):
        if not norm:
            return
        key = (norm["tool"], json.dumps(norm["args"], sort_keys=True, ensure_ascii=False))
        if key in seen:
            return
        seen.add(key)
        calls.append(norm)

    for obj in _iter_json_objects(content):
        _add(_normalize_tool_obj(obj))
    for pseudo in _extract_pseudo_tag_calls(content):
        _add(pseudo)
    return calls


def parse_text_tool_call(content: str) -> Optional[Dict[str, Any]]:
    """向後相容：回傳文字中第一個工具呼叫 {'tool':.., 'args':..}，無則 None。"""
    calls = extract_tool_calls_from_text(content)
    return calls[0] if calls else None

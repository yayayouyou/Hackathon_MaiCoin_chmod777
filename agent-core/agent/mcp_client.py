"""
agent/mcp_client.py — MCP client 層（dogfood）
=====================================================
把 MAX MCP Server 的工具「經 MCP 協定發現並包成 sync callable」，讓主 agent 吃自己的
狗糧——工具定義單一來源(MCP server)、呼叫走標準 MCP 介面。
預設 in-process（同進程直呼 FastMCP，零傳輸開銷，介面仍是 MCP）；之後可換遠端傳輸
（AgentCore Runtime streamable-http）而呼叫端不變。以 AGENT_MCP_DOGFOOD=1 啟用；
未啟用時回空 dict → 主 agent 沿用原生工具（零影響、可回退）。
"""
import os
import json
import asyncio
import threading
from typing import Dict, Any, Callable, List
from loguru import logger

_loop: asyncio.AbstractEventLoop = None
_lock = threading.Lock()


def _enabled() -> bool:
    return os.getenv("AGENT_MCP_DOGFOOD", "0").strip().lower() in ("1", "true", "yes")


def _ensure_loop() -> asyncio.AbstractEventLoop:
    """背景常駐事件迴圈：讓同步的 agent 迴圈能安全呼叫 async 的 MCP。"""
    global _loop
    with _lock:
        if _loop is None:
            _loop = asyncio.new_event_loop()
            threading.Thread(target=_loop.run_forever, daemon=True, name="mcp-loop").start()
        return _loop


def _run(coro, timeout: float = 180.0):
    return asyncio.run_coroutine_threadsafe(coro, _ensure_loop()).result(timeout=timeout)


def _extract(result: Any) -> Any:
    """FastMCP call_tool 回傳 (content_blocks, structured) 或 content_blocks → 取回原始 dict/list。"""
    content, structured = (result if isinstance(result, tuple) and len(result) == 2 else (result, None))
    if isinstance(structured, dict):
        # FastMCP 對回傳非 dict 者會包成 {"result": ...}；dict 本身則原樣
        return structured["result"] if set(structured.keys()) == {"result"} else structured
    try:
        for c in (content or []):
            txt = getattr(c, "text", None)
            if txt:
                try:
                    return json.loads(txt)
                except (ValueError, TypeError):
                    return txt
    except TypeError:
        pass
    return content


def _sync_tool(server, name: str) -> Callable:
    def call(**kwargs):
        try:
            return _extract(_run(server.call_tool(name, kwargs)))
        except Exception as e:  # noqa: BLE001
            return {"error": f"MCP 工具 {name} 呼叫失敗：{e.__class__.__name__}: {e}"}
    return call


def load_mcp_callables() -> Dict[str, Callable]:
    """回傳 {工具名: sync callable}（經 MCP 介面）。未啟用或失敗回空 dict → 沿用原生工具。"""
    if not _enabled():
        return {}
    try:
        from mcp_servers.max_mcp_server import mcp as server
        tools = _run(server.list_tools())
        callables = {t.name: _sync_tool(server, t.name) for t in tools}
        logger.info(f"MCP dogfood 啟用：{len(callables)} 個工具改走 MCP 介面 → {sorted(callables)}")
        return callables
    except Exception as e:  # noqa: BLE001
        logger.warning(f"MCP dogfood 載入失敗，退回原生工具：{e}")
        return {}

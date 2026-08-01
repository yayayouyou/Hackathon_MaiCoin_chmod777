"""
deploy/agentcore_app.py — Amazon Bedrock AgentCore Runtime 相容入口
=====================================================
符合 AgentCore Runtime 服務合約：
  - POST /invocations : JSON 進、SSE（或 JSON）出 —— 包裝現有 run_agent_turn
  - GET  /ping        : 健康檢查（Healthy / HealthyBusy）
容器需求：ARM64、host 0.0.0.0、port 8080（見同層 Dockerfile）。
我們自製的 agent loop（語意路由 / Critic / Reader 淨化 / 核准流）原封不動複用；
大腦由 LLM_PROVIDER 決定（AgentCore 上設 bedrock → Claude）。

本地跑：.venv/bin/python -m uvicorn deploy.agentcore_app:app --host 0.0.0.0 --port 8080
"""
import os
import sys
import json
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.ollama_agent import run_agent_turn

app = FastAPI(title="MAIA · AgentCore Runtime")

# 同時併發計數 → /ping 回報 Healthy / HealthyBusy（AgentCore 據此調度）
_inflight = 0


def _extract_body(payload: Any) -> Dict[str, Any]:
    """AgentCore 可能把輸入包成 {"input": {...}} 或直接傳 → 統一取出。"""
    if isinstance(payload, dict):
        return payload.get("input") if isinstance(payload.get("input"), dict) else payload
    return {}


def _to_messages(body: Dict[str, Any]) -> List[Dict[str, str]]:
    msgs = body.get("messages")
    if isinstance(msgs, list) and msgs:
        return msgs
    prompt = body.get("prompt") or body.get("query") or body.get("text") or ""
    return [{"role": "user", "content": str(prompt)}] if prompt else []


@app.get("/ping")
def ping():
    """健康檢查（AgentCore Runtime 合約）。"""
    return {"status": "HealthyBusy" if _inflight > 0 else "Healthy"}


@app.post("/invocations")
async def invocations(request: Request):
    """主 agent 互動端點（AgentCore Runtime 合約）：預設 SSE 串流；body 帶 "stream": false 則回 JSON 終答。"""
    global _inflight
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    body = _extract_body(payload)
    messages = _to_messages(body)
    if not messages:
        return JSONResponse({"error": "缺少 prompt 或 messages"}, status_code=400)
    model = body.get("model") or os.getenv("AGENT_MODEL", "")
    persona = body.get("persona") or "default"
    stream = body.get("stream", True)

    def run_steps():
        for step in run_agent_turn(history_messages=messages,
                                   model_name=model or os.getenv("AGENT_MODEL", "gemma4:12b-mlx"),
                                   persona_key=persona):
            yield step

    if not stream:
        # 非串流：收斂成單一 JSON（最終答案 + 用過的工具）
        global _inflight
        _inflight += 1
        try:
            final, tools = "", []
            for step in run_steps():
                if step.get("type") == "tool_call":
                    tools.append(step.get("name"))
                elif step.get("type") == "final_answer":
                    final = step.get("content", "")
            return JSONResponse({"output": {"answer": final, "tools_used": tools}})
        finally:
            _inflight -= 1

    def sse():
        global _inflight
        _inflight += 1
        try:
            for step in run_steps():
                yield f"data: {json.dumps(step, ensure_ascii=False)}\n\n"
        finally:
            _inflight -= 1

    return StreamingResponse(sse(), media_type="text/event-stream")

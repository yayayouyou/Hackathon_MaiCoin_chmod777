"""
agent/tool_embeddings.py — 工具語意檢索（embedding top-k，供路由 fallback）
=====================================================
當關鍵字路由沒命中任何「資料類」意圖時，用本地 embedding（預設 bge-m3 via ollama）
對所有工具描述做語意檢索，取 top-k 相關工具，取代原本「無聲退回 price」的漏接。
（依據 POC：「把BTC換成USDT的紀錄 / show my balance / 帳號打幾折」等關鍵字漏接
  皆能命中 top-1~2 的正確工具。）

設計要點：
- 工具向量「一次算好、磁碟快取」（key = 模型 + 工具描述雜湊）；描述變了才自動重算。
- 查詢時只 embed 一次（3060 上約數十~百毫秒），cosine top-k。
- **優雅降級**：ollama／模型不可用或任何錯誤 → 回 None，呼叫端沿用舊 price fallback，
  絕不因此讓路由壞掉（保證測試、離線環境照常運作）。
- 可用環境變數關閉：TOOL_SEMANTIC_ROUTER=0；換模型：TOOL_EMBED_MODEL。
"""
import os
import json
import math
import hashlib
import urllib.request
from typing import List, Optional, Dict, Any, Tuple

from loguru import logger

from agent.tool_concepts import expand_tool_text

_HOST = os.getenv("OLLAMA_HOST", "127.0.0.1:11434")
if not _HOST.startswith("http"):
    _HOST = "http://" + _HOST
_EMBED_URL = _HOST.rstrip("/") + "/api/embed"
_MODEL = os.getenv("TOOL_EMBED_MODEL", "bge-m3")
_CACHE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "conversation_logs", "tool_embeddings.json",
)

_index: Optional[Dict[str, Any]] = None      # 記憶體快取：{"names":[...], "vecs":[[...]]}
_index_failed = False                         # 建索引失敗過就別每次重試（避免每題都卡逾時）


def _enabled() -> bool:
    return os.getenv("TOOL_SEMANTIC_ROUTER", "1").strip().lower() not in ("0", "false", "no")


def _embed(texts: List[str], timeout: float) -> Optional[List[List[float]]]:
    """呼叫 ollama /api/embed；任何失敗回 None（讓呼叫端降級）。"""
    try:
        payload = json.dumps({"model": _MODEL, "input": texts}).encode()
        req = urllib.request.Request(_EMBED_URL, data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            embs = json.load(r).get("embeddings")
        if embs and all(embs):
            return embs
    except Exception as e:  # noqa: BLE001
        logger.debug(f"工具 embedding 呼叫失敗（降級）：{e}")
    return None


def _norm(v: List[float]) -> List[float]:
    s = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / s for x in v]


def _tool_text(t: Dict[str, Any]) -> str:
    """工具的「擴充索引文件」：描述 + 概念 + 範例問句（Document Expansion）。"""
    f = t["function"]
    return expand_tool_text(f["name"], f.get("description") or "")


def _signature(tools: List[Dict[str, Any]]) -> str:
    """擴充文件的雜湊；描述或概念表任一變動就使快取失效、重算向量。"""
    h = hashlib.sha256()
    for t in tools:
        h.update((t["function"]["name"] + "\x00" + _tool_text(t)).encode())
    return h.hexdigest()[:16]


def _build_index(tools: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """建立或載入工具向量索引（磁碟快取，簽章不符才重算 embedding）。"""
    sig = _signature(tools)
    if os.path.exists(_CACHE):
        try:
            with open(_CACHE, encoding="utf-8") as f:
                c = json.load(f)
            if c.get("model") == _MODEL and c.get("sig") == sig and c.get("names") and c.get("vecs"):
                return {"names": c["names"], "vecs": c["vecs"]}
        except Exception:  # noqa: BLE001
            pass
    texts = [_tool_text(t) for t in tools]        # Document Expansion：描述 + 概念 + 範例問句
    embs = _embed(texts, timeout=120.0)
    if not embs:
        return None
    names = [t["function"]["name"] for t in tools]
    vecs = [_norm(v) for v in embs]
    try:
        os.makedirs(os.path.dirname(_CACHE), exist_ok=True)
        tmp = _CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"model": _MODEL, "sig": sig, "names": names, "vecs": vecs}, f)
        os.replace(tmp, _CACHE)
        logger.info(f"工具語意索引已建立（{len(names)} 工具，模型 {_MODEL}）")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"工具向量快取寫入失敗（仍可用記憶體索引）：{e}")
    return {"names": names, "vecs": vecs}


def semantic_tool_scores(query: str, tools: List[Dict[str, Any]]) -> Optional[List[Tuple[str, float]]]:
    """
    回傳「所有工具的 (名稱, cosine 相似度)」依分數由高到低排序；任何不可用情況
    （關閉/無模型/逾時/錯誤）回 None，讓呼叫端沿用關鍵字/price 行為。
    呼叫端可自行取 top-k 或套相似度門檻（增補 recall 用）。
    """
    global _index, _index_failed
    if not _enabled() or not query or _index_failed:
        return None
    if _index is None:
        _index = _build_index(tools)
        if _index is None:
            _index_failed = True     # 建不起來（多半沒 ollama/模型）→ 不再重試
            return None
    qv = _embed([query], timeout=15.0)
    if not qv:
        return None
    q = _norm(qv[0])
    names, vecs = _index["names"], _index["vecs"]
    return sorted(
        ((n, sum(a * b for a, b in zip(q, v))) for n, v in zip(names, vecs)),
        key=lambda x: x[1], reverse=True,
    )


def semantic_tool_names(query: str, tools: List[Dict[str, Any]], k: int = 8) -> Optional[List[str]]:
    """語意最相關的 k 個工具名稱（薄包裝 semantic_tool_scores）；不可用回 None。"""
    scored = semantic_tool_scores(query, tools)
    return None if scored is None else [n for n, _ in scored[:k]]

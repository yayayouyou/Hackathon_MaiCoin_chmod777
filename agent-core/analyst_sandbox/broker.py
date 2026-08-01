"""
analyst_sandbox/broker.py — Skill Broker（父行程端）
=====================================================
在【父行程】(agent，持有金鑰) 執行「唯讀資料類」skill，只把資料結果回給沙盒子行程。
金鑰與下單能力留在父行程，永不進入沙盒。

白名單原則：預設放行所有 skill，再明確排除『有副作用/存取私有帳戶/需金鑰授權操作』者：
  - 下單/撤單（create_order / cancel_order / cancel_all_orders）
  - 寫入（save_strategy / remember_about_me / forget_about_me）
  - 私有帳戶讀取（get_max_accounts / my_trades / deposits / withdrawals / orders / member_info…）
  - 沙盒本身（run_analysis）→ 防遞迴
"""

import math
from typing import Any, Dict, List

from loguru import logger

# 明確排除（有副作用 / 私有 / 需授權 / 遞迴）
_DENY: set = {
    # 執行 / 撤單
    "create_order", "cancel_order", "cancel_all_orders",
    # 寫入 / 記憶
    "save_strategy", "remember_about_me", "forget_about_me",
    # 私有帳戶（含金鑰授權讀取的個人資料）
    "get_max_accounts", "get_max_member_info", "get_max_my_trades",
    "get_max_deposits", "get_max_withdrawals", "get_max_order",
    "get_max_orders", "get_max_order_history", "recall_history",
    # 沙盒自身
    "run_analysis",
}

_MAX_JSON_BYTES = 300_000     # 單次 skill 結果上限（防灌爆沙盒/傳輸）
_MAX_DEPTH = 12


def _callables() -> Dict[str, Any]:
    """延遲載入 TOOL_CALLABLES（避免模組載入期循環匯入）。"""
    from agent.ollama_agent import TOOL_CALLABLES
    return TOOL_CALLABLES


def whitelist() -> List[str]:
    """回傳沙盒可呼叫的唯讀 skill 名單（排序）。"""
    return sorted(n for n in _callables() if n not in _DENY)


def catalog() -> Dict[str, List[str]]:
    """把白名單依前綴粗分類，供工具說明/agent 參考。"""
    groups: Dict[str, List[str]] = {}
    for n in whitelist():
        key = ("price/market" if n.startswith(("get_ticker", "get_orderbook", "get_ohlcv", "get_max_", "get_coingecko", "get_dex", "search_dex"))
               else "derivatives" if ("funding" in n or "open_interest" in n or "long_short" in n or "liquidation" in n or "coinalyze" in n)
               else "sentiment/intel" if (n.startswith(("get_latest", "fetch_", "search_web", "analyze_figure", "analyze_crowd")) or "fear_and_greed" in n or "treasur" in n or "sector" in n or "crypto_stocks" in n)
               else "onchain/indices" if ("ahr999" in n or "mayer" in n or "altcoin" in n or "blockchain" in n or "unconfirmed" in n or "etf" in n or "grayscale" in n or "home_stats" in n)
               else "gold" if "gold" in n
               else "analytics/backtest" if (n.startswith(("run_", "calculate_indicators", "detect_market", "analyze_portfolio", "list_strategies")))
               else "calculators" if n.startswith("calculate_")
               else "education" if (n.startswith(("explain_", "get_beginner", "get_max_guide", "get_max_fee")))
               else "other")
        groups.setdefault(key, []).append(n)
    return groups


def _sanitize(obj: Any, depth: int = 0) -> Any:
    """把 skill 結果轉成 JSON-safe（numpy/pandas/datetime/set → 原生型別），並限制深度。"""
    if depth > _MAX_DEPTH:
        return "…(too deep)"
    if obj is None or isinstance(obj, (bool, int, str)):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    # numpy / pandas（延遲判斷，避免硬相依）
    tname = type(obj).__module__
    if tname.startswith("numpy"):
        try:
            return _sanitize(obj.item() if hasattr(obj, "item") and obj.ndim == 0 else obj.tolist(), depth + 1)
        except Exception:  # noqa: BLE001
            return str(obj)
    if tname.startswith("pandas"):
        try:
            return _sanitize(obj.to_dict() if hasattr(obj, "to_dict") else obj.tolist(), depth + 1)
        except Exception:  # noqa: BLE001
            return str(obj)
    if isinstance(obj, dict):
        return {str(k): _sanitize(v, depth + 1) for k, v in list(obj.items())[:2000]}
    if isinstance(obj, (list, tuple, set)):
        return [_sanitize(v, depth + 1) for v in list(obj)[:5000]]
    # datetime 等
    for attr in ("isoformat",):
        if hasattr(obj, attr):
            try:
                return getattr(obj, attr)()
            except Exception:  # noqa: BLE001
                pass
    return str(obj)


def _safe_kwargs(kwargs: Any) -> Dict[str, Any]:
    """只放行簡單型別的參數（防夾帶物件/callable）。"""
    if not isinstance(kwargs, dict):
        return {}
    out = {}
    for k, v in kwargs.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[str(k)] = v
        elif isinstance(v, (list, tuple)) and all(isinstance(x, (str, int, float, bool)) or x is None for x in v):
            out[str(k)] = list(v)
    return out


def execute(name: str, kwargs: Any) -> Dict[str, Any]:
    """服務一次沙盒的 skill 請求。回 {'ok':bool, 'data'|'error'}。"""
    if not isinstance(name, str) or name in _DENY:
        return {"ok": False, "error": f"skill '{name}' 不在分析沙盒白名單（唯讀資料類；下單/私有/寫入一律禁止）。"}
    fns = _callables()
    fn = fns.get(name)
    if fn is None:
        return {"ok": False, "error": f"未知 skill '{name}'。可用清單見 whitelist()。"}
    try:
        import json
        data = _sanitize(fn(**_safe_kwargs(kwargs)))
        blob = json.dumps(data, ensure_ascii=False)
        if len(blob.encode("utf-8")) > _MAX_JSON_BYTES:
            return {"ok": False, "error": f"skill '{name}' 結果過大（>{_MAX_JSON_BYTES} bytes），請縮小查詢範圍。"}
        return {"ok": True, "data": data}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"沙盒 broker 執行 skill 失敗 [{name}]: {e}")
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:150]}"}

"""
skills/analytics/run_card.py — 回測可重現性紀錄（run card，借鏡 Vibe-Trading）
=====================================================
每次回測落地一張「執行卡」，讓任何結論都可被稽核與重跑比對：

  - run_id      = hash(kind + 完整參數 + 引擎版本)   → 相同設定永遠得到相同 id（辨識「同一個實驗」）
  - result_hash = hash(關鍵結果)                     → 重跑時可偵測結果是否漂移（資料更新／程式改動）
  - created_at / engine_version / params / result_summary 全數存檔

排列檢定與 bootstrap 皆用固定種子 → 給定同一份資料，結果雜湊必然一致；
若 result_hash 改變，代表底層 K 線/資料已更新（而非隨機性），可據此判斷結論是否過期。
"""
import os
import json
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict

from loguru import logger

ENGINE_VERSION = "event-study-v2"

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DIR = os.environ.get("RUN_CARDS_DIR", os.path.join(_ROOT, "run_cards"))

# 納入結果雜湊與摘要的關鍵欄位（只取可重現的統計結論，不含時間戳）
_REPORT_KEYS = (
    "signal", "signals", "combine", "asset", "events_tested", "hold_days", "direction",
    "publish_lag", "avg_abnormal_return_pct", "abnormal_ci90_pct", "t_stat", "p_value",
    "permutation_p", "significant", "win_rate_pct", "baseline_return_pct", "verdict",
)


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)


def _hash(obj: Any) -> str:
    return hashlib.sha256(_canon(obj).encode("utf-8")).hexdigest()[:16]


def write_run_card(kind: str, params: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, str]:
    """落地一張 run card，回傳 {run_id, result_hash}（供附加到回測結果）。落地失敗不影響回測。"""
    summary = {k: result[k] for k in _REPORT_KEYS if k in result}
    run_id = _hash({"kind": kind, "params": params, "engine": ENGINE_VERSION})
    result_hash = _hash(summary)
    card = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "engine_version": ENGINE_VERSION,
        "kind": kind,
        "params": params,
        "result_summary": summary,
        "result_hash": result_hash,
    }
    try:
        os.makedirs(_DIR, exist_ok=True)
        with open(os.path.join(_DIR, f"{run_id}.json"), "w", encoding="utf-8") as f:
            json.dump(card, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.warning(f"run card 落地失敗（不影響回測）: {e}")
    return {"run_id": run_id, "result_hash": result_hash, "engine_version": ENGINE_VERSION}

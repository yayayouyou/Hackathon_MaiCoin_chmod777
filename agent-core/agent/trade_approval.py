"""
agent/trade_approval.py — 交易核准互鎖 (Human-in-the-loop Trade Approval)
=====================================================
借鏡 OpenClaw exec-approvals 的安全模型：**模型只能「提議」訂單，真正送出前必須經人工核准。**
核准的訂單計畫會被「凍結」並雜湊 (SHA256)；執行時只依凍結計畫執行，模型在核准後無法竄改。

這是「模型最後、風控在外」原則的體現：核准判斷是交易所無關的純 Python 邏輯，
不受對話內容或提示注入影響（配合 prompts.py 的 G4/G9/G10 形成縱深防禦）。

政策（環境變數 TRADE_APPROVAL）：
  always   （預設）— 每筆下單都要人工核准（連 paper 模擬盤也要，利於安全展示與提案）
  allowlist        — 名目價值低於門檻者自動核准，其餘仍要人工核准
  off              — 不啟用核准（回到直接執行的舊行為）

注意：核准狀態存於行程內記憶體，適用單一 uvicorn 行程（本地／展示）。
多 worker 佈署需改為共用存儲（Redis 等）。
"""
import os
import json
import time
import math
import uuid
import hashlib
from typing import Dict, Any, Optional, Callable, Tuple, List

_APPROVAL_TTL_SEC = 120   # 待核准訂單存活秒數；逾時的核准會被拒（防過期意圖被執行）


def get_policy() -> str:
    p = (os.getenv("TRADE_APPROVAL", "always") or "always").strip().lower()
    return p if p in ("always", "allowlist", "off") else "always"


def _auto_approve_ceiling() -> float:
    """allowlist 模式下，名目價值 ≤ 此金額 (TWD) 才自動核准。"""
    try:
        return float(os.getenv("TRADE_AUTO_APPROVE_TWD", "5000"))
    except (TypeError, ValueError):
        return 5000.0


def _normalize_market(market: str) -> str:
    return (market or "").replace("/", "").replace("_", "").lower()


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_order_plan(args: Dict[str, Any], latest_price: float, mode: str) -> Dict[str, Any]:
    """把模型的下單參數 + 當前市價 組成「規範化訂單計畫」。"""
    ord_type = str(args.get("ord_type", "limit")).lower()
    volume = _to_float(args.get("volume")) or 0.0
    price = _to_float(args.get("price"))
    # 限價型（limit / post_only）用委託價估算；市價單沒有委託價，用市價
    fill_price = price if (ord_type in ("limit", "post_only") and price is not None) else latest_price
    market_id = _normalize_market(args.get("market", ""))
    notional_quote = volume * (fill_price or 0.0)
    # 換算成 TWD 才能跟 TWD 核准門檻正確比較；無法換算 → inf 強制人工核准（fail-safe）
    from skills.execution.quote_convert import notional_to_twd
    nt = notional_to_twd(notional_quote, market_id)
    est_twd = round(nt, 2) if nt is not None else float("inf")
    return {
        "kind": "order",
        "exchange": str(args.get("exchange_id", "max")).lower(),
        "market": market_id,
        "side": str(args.get("side", "")).lower(),
        "volume": volume,
        "price": price,
        "ord_type": ord_type,
        "mode": mode,                       # paper / live
        "latest_price": latest_price,
        "est_fill_price": fill_price,
        "est_notional_quote": round(notional_quote, 8),   # 計價幣別原值（透明用）
        "est_notional_twd": est_twd,
    }


def build_cancel_all_plan(exchange: str, mode: str) -> Dict[str, Any]:
    """全帳戶撤單（無指定 market）的核准計畫：走與下單相同的人工核准互鎖。"""
    return {
        "kind": "cancel_all",
        "action": "cancel_all_markets",
        "exchange": (exchange or "max").lower(),
        "market": None,
        "mode": mode,
    }


# 只有「意圖」欄位進入雜湊（市價等執行時資訊不算，避免價格跳動導致無法執行）；kind/action 讓撤單計畫與下單計畫雜湊區隔
_HASH_FIELDS = ("kind", "action", "exchange", "market", "side", "volume", "price", "ord_type", "mode")


def plan_hash(plan: Dict[str, Any]) -> str:
    core = {k: plan.get(k) for k in _HASH_FIELDS}
    blob = json.dumps(core, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def needs_approval(plan: Dict[str, Any]) -> bool:
    policy = get_policy()
    if policy == "off":
        return False
    if policy == "allowlist":
        nt = plan.get("est_notional_twd")
        # 無法可信估算（None/非有限/負值）→ 一律需人審（fail-safe，不因 truthiness 誤自動核准）
        if not isinstance(nt, (int, float)) or not math.isfinite(nt) or nt < 0:
            return True
        return nt > _auto_approve_ceiling()
    return True  # always


class _PendingStore:
    """行程內待核准訂單存儲。"""
    def __init__(self) -> None:
        self._d: Dict[str, Dict[str, Any]] = {}

    def add(self, plan: Dict[str, Any]) -> str:
        self._evict()
        token = f"appr-{uuid.uuid4().hex[:12]}"
        self._d[token] = {
            "plan": plan,
            "hash": plan_hash(plan),
            "ts": time.time(),
            "mono": time.monotonic(),   # 單調時鐘供 TTL 判斷，免受系統時間回撥/NTP 校正影響
            "state": "pending",   # pending / executed / rejected / mismatch / expired
            "result": None,
        }
        return token

    def _evict(self) -> None:
        """清掉終態或過久的項目，避免記憶體無限成長。"""
        now = time.monotonic()
        stale = [t for t, v in self._d.items()
                 if v["state"] != "pending" or now - v.get("mono", now) > _APPROVAL_TTL_SEC * 5]
        for t in stale:
            self._d.pop(t, None)

    def get(self, token: str) -> Optional[Dict[str, Any]]:
        return self._d.get(token)

    def pending(self) -> List[str]:
        return [t for t, v in self._d.items() if v["state"] == "pending"]


STORE = _PendingStore()


def register_pending(plan: Dict[str, Any]) -> Tuple[str, str]:
    """登記一筆待核准訂單，回傳 (token, hash)。"""
    token = STORE.add(plan)
    return token, STORE.get(token)["hash"]


def approve_and_execute(token: str, executor: Callable[[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
    """
    核准並執行。以「凍結計畫」呼叫 executor；模型在核准後無法變更任何參數。
    executor(plan) 應回傳真正的下單結果 dict。
    """
    entry = STORE.get(token)
    if not entry:
        return {"status": "ERROR", "reason": "核准權杖不存在或已失效"}
    if entry["state"] != "pending":
        return {"status": "ERROR", "reason": f"此訂單已處理過（{entry['state']}），不可重複執行"}
    # 逾時的待核准訂單不可執行：避免用『過期意圖』（舊限價/舊數量）在非預期時點成交。
    # 用單調時鐘，避免系統時間回撥讓 age 變負而繞過 TTL。
    if time.monotonic() - entry.get("mono", 0) > _APPROVAL_TTL_SEC:
        entry["state"] = "expired"
        return {"status": "ERROR",
                "reason": f"核准逾時（超過 {_APPROVAL_TTL_SEC} 秒）：待核准訂單已過期，請重新提交下單。"}
    plan = entry["plan"]
    # 執行前再次驗雜湊：偵測凍結計畫是否遭竄改（縱深防禦）
    if plan_hash(plan) != entry["hash"]:
        entry["state"] = "mismatch"
        return {"status": "ERROR", "reason": "核准不符 (approval mismatch)：訂單計畫與核准當下不一致，已拒絕執行"}
    try:
        result = executor(plan)
    except Exception as e:  # noqa: BLE001
        entry["state"] = "error"
        return {"status": "FAILED", "reason": f"執行時異常: {e}"}
    entry["state"] = "executed"
    entry["result"] = result
    return result


def reject(token: str, reason: str = "使用者取消") -> Dict[str, Any]:
    entry = STORE.get(token)
    if not entry:
        return {"status": "ERROR", "reason": "核准權杖不存在"}
    if entry["state"] != "pending":
        return {"status": "ERROR", "reason": f"此訂單已是 {entry['state']} 狀態"}
    entry["state"] = "rejected"
    return {"status": "REJECTED", "reason": reason}


def human_summary(plan: Dict[str, Any]) -> str:
    """給 UI/模型看的一句話摘要。"""
    if plan.get("kind") == "cancel_all":
        mode_zh = "🔴 實盤" if plan.get("mode") == "live" else "📝 模擬盤"
        return f"{mode_zh}｜撤銷『全部市場』的所有掛單（含止損/止盈保護單）"
    side_zh = "買入" if plan["side"] == "buy" else "賣出"
    # post_only 一定要在摘要裡講清楚「不會立刻成交」——使用者按下核准時，
    # 對「會發生什麼」的預期必須正確，這是核准這個動作唯一的意義。
    _OT_ZH = {
        "market": "市價單",
        "limit": f"限價單 @ {plan.get('price')}",
        "post_only": f"只掛單 @ {plan.get('price')}（maker，會立即成交則整筆被拒）",
    }
    ot_zh = _OT_ZH.get(plan["ord_type"], f"{plan['ord_type']} @ {plan.get('price')}")
    mode_zh = "🔴 實盤" if plan["mode"] == "live" else "📝 模擬盤"
    nt = plan.get("est_notional_twd")
    nt_zh = f"{nt:,.0f} TWD" if isinstance(nt, (int, float)) and math.isfinite(nt) else "金額無法估算（需人工確認）"
    return (f"{mode_zh}｜{side_zh} {plan['volume']} {plan['market'].upper()}"
            f"（{ot_zh}）｜預估 ≈ {nt_zh}")

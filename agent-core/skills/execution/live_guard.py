"""
skills/execution/live_guard.py — 實盤專用防線（單筆風控之外的四道）

`risk_guard.py` 擋的是「這一筆合不合理」，本模組擋的是「這一連串合不合理」，
以及「現在到底該不該讓它下單」。四道防線：

  1. Kill switch      —— 一個檔案存在就全面停手，不必改設定、不必重啟
  2. 授權到期         —— RISK_MODE=live 之外還要 LIVE_UNTIL，過期自動退回模擬盤
  3. 累計曝險上限     —— 滾動視窗內的下單總額，擋掉「單筆都合法但連續下十筆」
  4. 決策台帳         —— 每一次下單決策（含被擋下的）都寫成結構化紀錄

設計原則：**fail-closed**。台帳讀寫失敗、時間解析失敗、任何不確定的狀況，
一律當作「不可下單」而非放行 —— 這是真錢，寧可擋錯不可放錯。
"""
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_LOG_DIR = os.path.join(_ROOT, "conversation_logs")

# 一個檔案就能全面停手：`touch conversation_logs/TRADING_HALTED`
KILL_SWITCH_PATH = os.path.join(_LOG_DIR, "TRADING_HALTED")
# 下單決策台帳（含被擋下的）；累計曝險也從這裡算
ORDER_LEDGER_PATH = os.path.join(_LOG_DIR, "order_ledger.jsonl")

# 滾動視窗與上限（可用環境變數覆蓋，但預設保守）
DEFAULT_WINDOW_HOURS = 24
DEFAULT_MAX_NOTIONAL_TWD = 200_000.0     # 視窗內下單總額上限
DEFAULT_MAX_ORDERS = 20                   # 視窗內筆數上限（擋住高頻迴圈）

_TZ = timezone(timedelta(hours=8))


def _now() -> datetime:
    return datetime.now(_TZ)


def _f(x: Any, d: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        v = float(raw)
        return v if v > 0 else default
    except ValueError:
        logger.warning(f"{name} 不是有效數字（{raw!r}），改用預設 {default}")
        return default


# ── 1. Kill switch ────────────────────────────────────────────────
def kill_switch_engaged() -> Tuple[bool, str]:
    """檔案存在就停手。回 (是否停手, 說明)。

    刻意用檔案而不是環境變數或設定項：出事的當下最需要的是「立刻、不必重啟、
    不必進 UI 也能生效」的手段 —— `touch` 一個檔案任何人都做得到，SSH 進去也行。
    """
    if not os.path.exists(KILL_SWITCH_PATH):
        return False, ""
    note = ""
    try:
        with open(KILL_SWITCH_PATH, "r", encoding="utf-8") as f:
            note = f.read().strip()[:200]
    except OSError:
        pass
    return True, (f"交易已被全域停止開關擋下（{KILL_SWITCH_PATH}）。"
                  + (f"備註：{note}" if note else "刪除該檔案即可恢復。"))


def engage_kill_switch(reason: str = "") -> Dict[str, Any]:
    """啟動停止開關（寫入檔案）。"""
    os.makedirs(_LOG_DIR, exist_ok=True)
    with open(KILL_SWITCH_PATH, "w", encoding="utf-8") as f:
        f.write(f"{_now().isoformat()} {reason}".strip())
    logger.warning(f"⛔ 交易停止開關已啟動：{reason or '(無備註)'}")
    return {"halted": True, "path": KILL_SWITCH_PATH, "reason": reason}


def release_kill_switch() -> Dict[str, Any]:
    """解除停止開關（刪除檔案）。"""
    try:
        os.remove(KILL_SWITCH_PATH)
        logger.warning("交易停止開關已解除")
    except FileNotFoundError:
        pass
    return {"halted": False, "path": KILL_SWITCH_PATH}


# ── 2. 授權到期 ────────────────────────────────────────────────────
def live_authorization() -> Tuple[bool, str]:
    """實盤授權是否仍有效。回 (是否有效, 說明)。

    只有 RISK_MODE=live 是不夠的 —— 那是設定一次就永久生效的旗標，
    很容易「這禮拜要用」設下去、三個月後還開著。因此額外要求 LIVE_UNTIL
    這個明確的到期時間，過期自動退回模擬盤，強迫定期重新確認。
    """
    raw = os.getenv("LIVE_UNTIL", "").strip()
    if not raw:
        return False, ("實盤未授權：RISK_MODE=live 之外還需要在 .env 設定 "
                       "LIVE_UNTIL（授權到期時間，例如 LIVE_UNTIL=2026-08-05）。"
                       "未設定時一律以模擬盤執行。")
    try:
        txt = raw.replace("Z", "+00:00")
        until = datetime.fromisoformat(txt)
        if until.tzinfo is None:            # 只給日期時，視為當日結束
            until = until.replace(tzinfo=_TZ)
            if len(raw) <= 10:
                until = until + timedelta(days=1) - timedelta(seconds=1)
    except ValueError:
        # fail-closed：時間解析不出來，當作未授權
        return False, f"實盤未授權：LIVE_UNTIL 格式無法解析（{raw!r}），請用 YYYY-MM-DD 或 ISO 時間。"

    now = _now()
    if now > until:
        return False, (f"實盤授權已於 {until.strftime('%Y-%m-%d %H:%M')} 到期，已自動退回模擬盤。"
                       "要繼續實盤請更新 .env 的 LIVE_UNTIL。")
    left = until - now
    hrs = int(left.total_seconds() // 3600)
    return True, f"實盤授權有效至 {until.strftime('%Y-%m-%d %H:%M')}（剩約 {hrs} 小時）"


def effective_risk_mode() -> Tuple[str, str]:
    """把 RISK_MODE 與授權/停止開關合併成「實際生效」的模式。

    這是唯一該被信任的模式來源 —— 只讀 RISK_MODE 會漏掉授權過期與停手。
    """
    raw = os.getenv("RISK_MODE", "paper").strip().lower()
    if raw != "live":
        return "paper", "模擬盤（RISK_MODE 未設為 live）"
    halted, why = kill_switch_engaged()
    if halted:
        return "halted", why
    ok, note = live_authorization()
    return ("live", note) if ok else ("paper", note)


# ── 3+4. 台帳與累計曝險 ────────────────────────────────────────────
def _read_ledger(since: Optional[datetime] = None) -> List[Dict[str, Any]]:
    if not os.path.exists(ORDER_LEDGER_PATH):
        return []
    out: List[Dict[str, Any]] = []
    with open(ORDER_LEDGER_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if since is not None:
                try:
                    if datetime.fromisoformat(rec.get("ts", "")) < since:
                        continue
                except ValueError:
                    continue
            out.append(rec)
    return out


def record_decision(decision: str, market: str, side: str, volume: float,
                    price: Optional[float], notional_twd: float, mode: str,
                    reason: str = "", order_id: Any = None,
                    extra: Optional[Dict[str, Any]] = None) -> None:
    """把一次下單決策寫進台帳。**被擋下的也要寫** —— 事後要重建「當時發生什麼」，
    只記成功的等於只留下一半的故事。"""
    rec = {
        "ts": _now().isoformat(), "decision": decision, "mode": mode,
        "market": market, "side": side, "volume": _f(volume), "price": price,
        "notional_twd": round(_f(notional_twd), 2), "reason": reason, "order_id": order_id,
    }
    if extra:
        rec.update(extra)
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        with open(ORDER_LEDGER_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            f.flush()
    except OSError as e:
        logger.error(f"下單台帳寫入失敗（這會讓累計曝險失準）：{e}")


def exposure_window(hours: Optional[int] = None) -> Dict[str, Any]:
    """統計滾動視窗內「實際送出」的下單量。"""
    h = int(hours or _env_float("LIVE_WINDOW_HOURS", DEFAULT_WINDOW_HOURS))
    since = _now() - timedelta(hours=h)
    recs = [r for r in _read_ledger(since)
            if r.get("decision") == "SUBMITTED" and r.get("mode") == "live"]
    total = sum(_f(r.get("notional_twd")) for r in recs)
    return {"window_hours": h, "orders": len(recs), "notional_twd": round(total, 2),
            "max_notional_twd": _env_float("LIVE_MAX_NOTIONAL_TWD", DEFAULT_MAX_NOTIONAL_TWD),
            "max_orders": int(_env_float("LIVE_MAX_ORDERS", DEFAULT_MAX_ORDERS))}


def check_cumulative(notional_twd: float, hours: Optional[int] = None) -> Tuple[bool, str]:
    """這一筆加上去會不會超過滾動視窗上限。回 (是否通過, 說明)。

    單筆上限擋不住「連續十筆都剛好低於上限」——這正是模型跑進迴圈或被誘導時
    最可能發生的樣子。
    """
    try:
        w = exposure_window(hours)
    except OSError as e:
        # fail-closed：算不出累計曝險就不准下單
        return False, f"風控攔截：無法讀取下單台帳以計算累計曝險（{e}）。為安全起見暫停實盤下單。"

    after = w["notional_twd"] + _f(notional_twd)
    if after > w["max_notional_twd"]:
        return False, (f"風控攔截：近 {w['window_hours']} 小時已下單 "
                       f"{w['notional_twd']:,.0f} TWD，本筆 {_f(notional_twd):,.0f} TWD 後將達 "
                       f"{after:,.0f} TWD，超過累計上限 {w['max_notional_twd']:,.0f} TWD。")
    if w["orders"] + 1 > w["max_orders"]:
        return False, (f"風控攔截：近 {w['window_hours']} 小時已下 {w['orders']} 筆，"
                       f"超過筆數上限 {w['max_orders']} 筆（防止高頻迴圈）。")
    return True, (f"累計曝險 {after:,.0f}/{w['max_notional_twd']:,.0f} TWD · "
                  f"{w['orders'] + 1}/{w['max_orders']} 筆")


def preflight(market: str, side: str, volume: float, price: Optional[float],
              notional_twd: float, intended_mode: Optional[str] = None) -> Tuple[bool, str, str]:
    """實盤下單前的總閘門：停止開關 → 授權 → 累計曝險。

    回 (是否可送出, 生效模式, 說明)。模式為 'paper' 時代表不該送真單
    （呼叫端應改走模擬），'halted' 代表連模擬都不該做。

    intended_mode：核准流程「凍結」下來的模式。使用者在介面上核准的是那個當下
    看到的模式，這份同意不該被之後改動的 RISK_MODE 改寫 —— 所以有凍結模式時
    以它為準。但**停止開關、授權到期、累計曝險三道閘門一律照樣套用**：
    核准當下合法不代表送出當下仍合法。
    """
    if intended_mode in ("paper", "live"):
        if intended_mode == "paper":
            return False, "paper", "模擬盤（核准時凍結的模式）"
        halted, why = kill_switch_engaged()
        if halted:
            record_decision("HALTED", market, side, volume, price, notional_twd, "live", why)
            return False, "halted", why
        ok, note = live_authorization()
        if not ok:
            return False, "paper", note
        mode = "live"
    else:
        mode, note = effective_risk_mode()
    if mode == "halted":
        record_decision("HALTED", market, side, volume, price, notional_twd, mode, note)
        return False, mode, note
    if mode != "live":
        return False, mode, note      # 模擬盤：由呼叫端走模擬路徑，不記台帳（不是被擋，是本來就模擬）

    ok, why = check_cumulative(notional_twd)
    if not ok:
        record_decision("REJECTED_CUMULATIVE", market, side, volume, price, notional_twd, mode, why)
        return False, "halted", why   # 已達上限：這一筆不可改走模擬假裝成功，直接擋
    return True, mode, f"{note}；{why}"


def ledger_summary(limit: int = 20) -> Dict[str, Any]:
    """【LLM Tool】查看實盤下單防線狀態與最近的下單決策紀錄（含被擋下的）。"""
    mode, note = effective_risk_mode()
    halted, hnote = kill_switch_engaged()
    try:
        w = exposure_window()
        recent = _read_ledger()[-limit:][::-1]
    except OSError as e:
        return {"error": f"台帳讀取失敗：{e}"}
    return {
        "effective_mode": mode, "mode_note": note,
        "kill_switch": {"engaged": halted, "note": hnote, "path": KILL_SWITCH_PATH},
        "exposure": w,
        "recent_decisions": recent,
        "note": "decision 欄位：SUBMITTED=實際送出、REJECTED_*=被擋下、HALTED=停止開關。"
                "被擋下的也會記錄，事後才能重建當時發生什麼。",
    }

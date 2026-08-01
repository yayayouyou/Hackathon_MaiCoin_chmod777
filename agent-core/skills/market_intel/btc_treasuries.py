"""
skills/market_intel/btc_treasuries.py — 企業比特幣財庫（BTC Treasuries）持幣與買賣動向
=====================================================
資料來源：SoSoValue OpenAPI（第一方，免費 Demo 金鑰）。

企業財庫（MicroStrategy/Strategy、Metaplanet、MARA…）的持幣增減是相當獨特的『機構級』
市場信號：大額增持 = 長線買盤承接；減持/出售 = 值得警惕的籌碼鬆動。

  - 列表      : GET /openapi/v1/btc-treasuries          → [{ticker, name, list_location}]
  - 持幣歷史  : GET /openapi/v1/btc-treasuries/{ticker}/purchase-history
                → [{date, btc_holding(總持幣), btc_acq(當次買賣,負=賣出), acq_cost(USD), avg_btc_cost}]（最新在前）

需一次性免費 SOSOVALUE_API_KEY（同 ETF flow）。含 30 分鐘 TTL 快取（財庫數據日更，省額度）。
"""

import os
import time
from typing import Any, Dict, List, Optional

from loguru import logger
from dotenv import load_dotenv

from skills._http import session_get

load_dotenv()

SOSOVALUE_BASE_URL = "https://openapi.sosovalue.com"
_FREE_SIGNUP = "免費申請金鑰：https://sosovalue.com/developer （Demo 免付費、~20 req/min）"
_TTL = 1800  # 30 分鐘
_cache: Dict[str, Any] = {}


def _is_placeholder_key(key: str) -> bool:
    k = (key or "").strip().lower()
    if not k:
        return True
    return (k.startswith("your") or k.startswith("<") or
            k in ("changeme", "placeholder", "xxx", "api_key", "todo", "none"))


def _soso_get(path: str) -> Any:
    """SoSoValue GET（帶金鑰 + TTL 快取）。"""
    now = time.time()
    hit = _cache.get(path)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    api_key = os.getenv("SOSOVALUE_API_KEY", "").strip()
    if _is_placeholder_key(api_key):
        raise EnvironmentError(f"SOSOVALUE_API_KEY 未設定（或仍為 .env 範本佔位符）！{_FREE_SIGNUP}")
    resp = session_get(f"{SOSOVALUE_BASE_URL}{path}", headers={"x-soso-api-key": api_key})
    if resp.status_code in (401, 403):
        raise RuntimeError(f"SoSoValue 金鑰無效或無權限（{resp.status_code}）。{_FREE_SIGNUP}")
    resp.raise_for_status()
    data = (resp.json() or {}).get("data")
    _cache[path] = (now, data)
    return data


def _fnum(x) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _company_history(ticker: str) -> List[Dict[str, Any]]:
    raw = _soso_get(f"/openapi/v1/btc-treasuries/{ticker}/purchase-history")
    return raw if isinstance(raw, list) else []


def _event(row: Dict[str, Any], name: str = "") -> Dict[str, Any]:
    acq = _fnum(row.get("btc_acq")) or 0.0
    cost = _fnum(row.get("acq_cost")) or 0.0
    return {
        "date": row.get("date"),
        "ticker": row.get("ticker"),
        "name": name,
        "btc_delta": round(acq, 2),
        "usd_cost": round(cost, 0),
        "action": "增持" if acq > 0 else ("減持" if acq < 0 else "持平"),
        "btc_holding": _fnum(row.get("btc_holding")),
    }


def get_btc_treasuries(ticker: Optional[str] = None, top_n: int = 8) -> Dict[str, Any]:
    """
    【LLM Tool】企業比特幣財庫（BTC Treasuries）持幣排名與近期增減持動向。

    Args:
        ticker : 指定公司代號（如 'MSTR','MARA','3350'）→ 回該公司持幣與近期買賣；
                 省略 → 回總覽（前幾大財庫持幣排名 + 全體近期淨增減持）。
        top_n  : 總覽模式追蹤的公司數（預設 8，受免費額度保護）。
    """
    # 單一公司
    if ticker:
        tk = ticker.upper().strip()
        try:
            hist = _company_history(tk)
        except EnvironmentError as e:
            return {"error": str(e).splitlines()[0], "needs_free_key": True}
        except Exception as e:  # noqa: BLE001
            return {"error": f"財庫資料抓取失敗: {e.__class__.__name__}"}
        if not hist:
            return {"ticker": tk, "error": "查無此公司財庫資料（代號可能有誤）。"}
        latest = hist[0]
        events = [_event(r) for r in hist[:8]]
        net30 = round(sum(e["btc_delta"] for e in events[:3]), 2)  # 最近 3 筆事件
        return {
            "source": "SoSoValue 企業財庫（第一方，免費）",
            "ticker": tk,
            "latest_holding_btc": _fnum(latest.get("btc_holding")),
            "latest_date": latest.get("date"),
            "recent_net_btc": net30,
            "recent_bias": "近期增持" if net30 > 0 else ("近期減持" if net30 < 0 else "近期持平"),
            "recent_events": events,
        }

    # 總覽
    try:
        companies = _soso_get("/openapi/v1/btc-treasuries")
    except EnvironmentError as e:
        return {"error": str(e).splitlines()[0], "needs_free_key": True,
                "hint": "設定免費 SOSOVALUE_API_KEY 後即可追蹤企業財庫持幣動向。"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"財庫列表抓取失敗: {e.__class__.__name__}"}
    if not isinstance(companies, list) or not companies:
        return {"error": "財庫列表暫無資料。"}

    picks = companies[:max(1, min(top_n, 12))]
    holders: List[Dict[str, Any]] = []
    activity: List[Dict[str, Any]] = []
    for c in picks:
        tk, name = c.get("ticker"), c.get("name")
        try:
            hist = _company_history(tk)
        except Exception:  # noqa: BLE001
            continue
        if not hist:
            continue
        latest = hist[0]
        hold = _fnum(latest.get("btc_holding"))
        if hold is not None:
            holders.append({"ticker": tk, "name": name, "list_location": c.get("list_location"),
                            "btc_holding": round(hold, 0), "latest_date": latest.get("date")})
        for r in hist[:2]:
            ev = _event(r, name)
            if ev["btc_delta"]:
                activity.append(ev)

    holders.sort(key=lambda x: x["btc_holding"], reverse=True)
    activity.sort(key=lambda x: (x.get("date") or ""), reverse=True)
    total_btc = round(sum(h["btc_holding"] for h in holders), 0)
    net_recent = round(sum(a["btc_delta"] for a in activity), 2)
    return {
        "source": "SoSoValue 企業財庫（第一方，免費）",
        "company_count": len(companies),
        "tracked": len(holders),
        "total_btc_tracked": total_btc,
        "recent_net_btc": net_recent,
        "recent_bias": "整體增持" if net_recent > 0 else ("整體減持" if net_recent < 0 else "整體持平"),
        "top_holders": holders,
        "recent_activity": activity[:10],
        "guide": "企業財庫增持＝長線機構買盤承接；減持/出售＝籌碼鬆動、值得警惕。",
    }

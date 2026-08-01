"""
skills/market_intel/etf_flow.py — 美國現貨 BTC/ETH ETF 每日資金流向（免費第一方 API）
=====================================================
治本：取代原本靠 CoinGlass AES 逆向抓取的 ETF flow。改用第一方官方 API（SoSoValue OpenAPI，
免費 Demo tier），遠比爬蟲耐用。

架構考量（依研究批判 R1/R3）：
  1. Provider 介面：來源可插拔（SoSoValue 為主，未來可加 Farside/issuer 備援），防單點風險。
  2. 每日本地快照 store：每次抓取都把當日資料落地本地 JSON（etf_flows_store.json，gitignored）。
     SoSoValue 官方已預告『付費方案即將上線』且 ETF 是其招牌 → 從第一天起把它當『當日增量來源』
     而非唯一歷史來源，累積的歷史才不會因斷源而丟失。

需一次性免費註冊 SOSOVALUE_API_KEY：https://sosovalue.com/developer （Demo 免付費，~20 req/min）。
"""

import os
import json
from typing import Any, Dict, List, Optional

from loguru import logger
from dotenv import load_dotenv

from skills._http import session_get

load_dotenv()

SOSOVALUE_BASE_URL = "https://openapi.sosovalue.com"
_STORE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "etf_flows_store.json",
)
_FREE_SIGNUP = "免費申請金鑰：https://sosovalue.com/developer （Demo 免付費、~20 req/min）"


def _is_placeholder_key(key: str) -> bool:
    k = (key or "").strip().lower()
    if not k:
        return True
    return (k.startswith("your") or k.startswith("<") or
            k in ("changeme", "placeholder", "xxx", "api_key", "todo", "none"))


# ──────────────────────────────────────────────
#  每日本地快照 store（累積歷史，防斷源）
# ──────────────────────────────────────────────
def _load_store() -> Dict[str, Any]:
    try:
        with open(_STORE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def _save_store(store: Dict[str, Any]) -> None:
    try:
        with open(_STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, indent=0)
    except OSError as e:  # noqa: BLE001
        logger.warning(f"ETF 快照 store 寫入失敗: {e}")


def _merge_store(asset: str, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把新抓到的每日紀錄併入本地 store（以 date 為鍵去重、更新），回傳併後的完整序列。"""
    store = _load_store()
    a = asset.upper()
    by_date: Dict[str, Dict[str, Any]] = {r["date"]: r for r in store.get(a, []) if r.get("date")}
    for r in records:
        if r.get("date"):
            by_date[r["date"]] = r  # 新值覆蓋舊值
    merged = sorted(by_date.values(), key=lambda x: x["date"])
    store[a] = merged
    _save_store(store)
    return merged


# ──────────────────────────────────────────────
#  Provider 介面（來源可插拔）
# ──────────────────────────────────────────────
def _sosovalue_available() -> bool:
    return not _is_placeholder_key(os.getenv("SOSOVALUE_API_KEY", ""))


def _sosovalue_fetch(asset: str) -> List[Dict[str, Any]]:
    """從 SoSoValue OpenAPI 抓每日 ETF 淨流向（彙總）。回傳 [{date, net_flow_usd, ...}]。"""
    api_key = os.getenv("SOSOVALUE_API_KEY", "").strip()
    if _is_placeholder_key(api_key):
        raise EnvironmentError(f"SOSOVALUE_API_KEY 未設定（或仍為 .env 範本佔位符）！{_FREE_SIGNUP}")

    headers = {"x-soso-api-key": api_key, "accept": "application/json"}
    sym = "BTC" if asset.upper() in ("BTC", "BITCOIN") else "ETH"
    url = f"{SOSOVALUE_BASE_URL}/openapi/v1/etfs/summary-history"
    resp = session_get(url, headers=headers, params={"symbol": sym, "country_code": "US"})
    if resp.status_code in (401, 403):
        raise RuntimeError(f"SoSoValue 金鑰無效或無權限（{resp.status_code}）。{_FREE_SIGNUP}")
    resp.raise_for_status()
    body = resp.json()

    # 實測回傳：{"code":0,"data":[{"date","total_net_inflow","total_net_assets","cum_net_inflow"}, ...]}
    data = body.get("data", body)
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("list") or data.get("history") or data.get("data") or []
    else:
        rows = []
    out: List[Dict[str, Any]] = []
    for r in rows if isinstance(rows, list) else []:
        date = r.get("date") or r.get("dataDate") or r.get("day") or r.get("time")
        flow = (r.get("totalNetInflow") if r.get("totalNetInflow") is not None else
                r.get("netInflow") if r.get("netInflow") is not None else
                r.get("total_net_inflow") if r.get("total_net_inflow") is not None else
                r.get("value"))
        if date is None or flow is None:
            continue
        rec = {"date": str(date)[:10], "net_flow_usd": float(flow)}
        na = r.get("totalNetAssets") or r.get("netAssets") or r.get("total_net_assets")
        if na is not None:
            rec["net_assets_usd"] = float(na)
        out.append(rec)
    return out


# 優先序：SoSoValue（第一方，主）。未來可在此插入 Farside/issuer 備援。
_PROVIDERS = [("sosovalue", _sosovalue_available, _sosovalue_fetch)]


def get_etf_flows(asset: str = "BTC", days: int = 14) -> Dict[str, Any]:
    """
    【LLM Tool】美國現貨 BTC/ETH ETF 每日資金淨流向（第一方 SoSoValue，免費金鑰）。

    Args:
        asset : 'BTC' 或 'ETH'
        days  : 回傳最近幾日（預設 14）

    行為：有金鑰 → 抓最新 + 併入本地快照 store；無金鑰 → 回本地 store 既有歷史（若有），
          否則優雅提示需一次性免費註冊。累積的歷史存於 etf_flows_store.json（防斷源）。
    """
    a = asset.upper()
    a = "BTC" if a in ("BTC", "BITCOIN") else ("ETH" if a in ("ETH", "ETHEREUM") else a)
    used_provider: Optional[str] = None
    fetch_error: Optional[str] = None

    for name, available, fetch in _PROVIDERS:
        if not available():
            continue
        try:
            records = fetch(a)
            if records:
                _merge_store(a, records)
                used_provider = name
                break
        except EnvironmentError as e:
            fetch_error = str(e).splitlines()[0]
        except Exception as e:  # noqa: BLE001
            fetch_error = f"{name} 抓取失敗: {e.__class__.__name__}: {str(e)[:80]}"
            logger.warning(fetch_error)

    history = _load_store().get(a, [])
    if not history:
        return {
            "asset": a,
            "error": fetch_error or f"ETF flow 需一次性免費金鑰。{_FREE_SIGNUP}",
            "needs_free_key": bool(fetch_error is None or "未設定" in (fetch_error or "")),
            "hint": "設定免費 SOSOVALUE_API_KEY 後即可取得第一方 ETF 每日流向並開始累積本地歷史。",
        }

    recent = history[-days:]
    latest = recent[-1] if recent else {}
    cum = round(sum(r.get("net_flow_usd", 0) for r in recent), 2)
    return {
        "asset": a,
        "source": f"SoSoValue OpenAPI（第一方，免費）→ 本地快照 store（{len(history)} 日累積）",
        "provider_used": used_provider or "local_store_only",
        "latest_date": latest.get("date"),
        "latest_net_flow_usd": latest.get("net_flow_usd"),
        "window_days": len(recent),
        "cumulative_net_flow_usd": cum,
        "history": recent,
        "note": None if used_provider else "本次未刷新（無金鑰或抓取失敗），回傳本地既有歷史。",
    }

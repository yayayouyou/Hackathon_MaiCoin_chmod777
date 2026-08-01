"""
skills/derivatives/coinalyze_client.py

Coinalyze API v1 封裝 — 免費金鑰的跨交易所衍生品彙整
=====================================================
治本：取代原本靠 CoinGlass AES 逆向抓取的爆倉數據。Coinalyze 是唯一「官方免費層 +
直接給多/空拆分 + 跨約 25 家交易所彙整」的來源。

提供：
  - get_coinalyze_liquidations   : 爆倉歷史（多/空拆分、跨所彙整、USD）
  - get_coinalyze_open_interest  : 跨所彙整持倉量（把 OI 覆蓋從 3 所擴到 ~25 所）

認證：免費註冊金鑰（coinalyze.net，免付費、40 req/min），以 `api_key` query 參數送出。
      申請：https://coinalyze.net/account/api-settings

彙整符號：以 `.A` 結尾（如 BTCUSDT_PERP.A）= 跨所彙整。
"""

import os
import time
from typing import Any, Dict, List, Optional

from loguru import logger
from dotenv import load_dotenv

from skills._http import session_get

load_dotenv()

COINALYZE_BASE_URL = "https://api.coinalyze.net/v1"

# Coinalyze 支援的時間間隔
_INTERVAL_MAP = {
    "1m": "1min", "1min": "1min", "5m": "5min", "5min": "5min",
    "15m": "15min", "15min": "15min", "30m": "30min", "30min": "30min",
    "1h": "1hour", "1hour": "1hour", "2h": "2hour", "2hour": "2hour",
    "4h": "4hour", "4hour": "4hour", "6h": "6hour", "6hour": "6hour",
    "12h": "12hour", "12hour": "12hour", "1d": "daily", "daily": "daily",
}
_INTERVAL_SECONDS = {
    "1min": 60, "5min": 300, "15min": 900, "30min": 1800, "1hour": 3600,
    "2hour": 7200, "4hour": 14400, "6hour": 21600, "12hour": 43200, "daily": 86400,
}

_FREE_SIGNUP = "免費申請金鑰：https://coinalyze.net/account/api-settings（免付費、40 req/min）"


def _is_placeholder_key(key: str) -> bool:
    """偵測 .env 內仍為範本佔位符（如 your_xxx_here）而非真實金鑰的情況。"""
    k = (key or "").strip().lower()
    if not k:
        return True
    return (k.startswith("your") or k.startswith("<") or
            k in ("changeme", "placeholder", "xxx", "api_key", "todo", "none"))


def _norm_interval(interval: str) -> str:
    return _INTERVAL_MAP.get((interval or "1hour").lower(), "1hour")


def _agg_symbol(symbol: str) -> str:
    """把裸幣種轉成 Coinalyze 跨所彙整永續符號（BTC -> BTCUSDT_PERP.A）。"""
    s = (symbol or "BTC").upper().split("/")[0].replace("USDT", "").replace("PERP", "").strip("_")
    return f"{s}USDT_PERP.A"


def _coinalyze_request(endpoint: str, params: Dict[str, Any]) -> Any:
    """執行 Coinalyze v1 GET 請求（金鑰以 api_key query 參數送出）。"""
    api_key = os.getenv("COINALYZE_API_KEY", "").strip()
    if _is_placeholder_key(api_key):
        raise EnvironmentError(
            "COINALYZE_API_KEY 未設定（或仍為 .env 範本佔位符）！這是取得跨所爆倉/持倉的免費來源。\n"
            f"{_FREE_SIGNUP}"
        )
    q = dict(params)
    q["api_key"] = api_key
    url = f"{COINALYZE_BASE_URL}{endpoint}"
    logger.debug(f"Coinalyze 請求：{url} 參數：{ {k: v for k, v in q.items() if k != 'api_key'} }")

    resp = session_get(url, params=q)
    if resp.status_code == 401:
        raise RuntimeError(f"Coinalyze 金鑰無效或未授權（401）。{_FREE_SIGNUP}")
    if resp.status_code == 429:
        raise RuntimeError("Coinalyze 觸發免費層限流（40 req/min），請稍後再試。")
    resp.raise_for_status()
    return resp.json()


def _window(interval_norm: str, limit: int) -> Dict[str, int]:
    """依 interval 與筆數，回推 from/to（unix 秒）。"""
    span = _INTERVAL_SECONDS.get(interval_norm, 3600)
    to = int(time.time())
    frm = to - max(1, limit) * span
    return {"from": frm, "to": to}


def get_coinalyze_liquidations(symbol: str = "BTC", interval: str = "1hour",
                               limit: int = 24) -> Dict[str, Any]:
    """
    【LLM Tool】跨交易所彙整的爆倉歷史（多/空拆分、USD）。

    Args:
        symbol   : 幣種符號，例如 'BTC', 'ETH'
        interval : 時間間隔（1h/4h/1d…；預設 1hour）
        limit    : 回溯桶數（預設 24）

    誠實限制：自 2021-04 起 Binance 對 forceOrder 節流（每秒每標的最多 1 筆），
    所有免費彙整爆倉總額在『劇烈行情』會系統性偏低——UI 應標註。
    """
    iv = _norm_interval(interval)
    sym = _agg_symbol(symbol)
    params = {"symbols": sym, "interval": iv, "convert_to_usd": "true", **_window(iv, limit)}
    logger.info(f"抓取爆倉（Coinalyze 跨所）：{symbol} interval={iv} x{limit}")
    raw = _coinalyze_request("/liquidation-history", params)

    # 回傳為 [{symbol, history:[{t, l(多單爆倉USD), s(空單爆倉USD)}]}]
    records: List[Dict[str, Any]] = []
    if isinstance(raw, list) and raw:
        records = raw[0].get("history", []) if isinstance(raw[0], dict) else []

    history, tl, ts = [], 0.0, 0.0
    for it in records:
        t = int(it.get("t", 0))
        long_liq = float(it.get("l", 0) or 0)
        short_liq = float(it.get("s", 0) or 0)
        tl += long_liq
        ts += short_liq
        history.append({
            "timestamp": t * 1000,  # 對齊前端毫秒
            "long_liquidation_usd": round(long_liq, 2),
            "short_liquidation_usd": round(short_liq, 2),
            "total_usd": round(long_liq + short_liq, 2),
        })

    total = tl + ts
    bias = ("多頭爆倉為主" if tl > ts * 1.5 else
            ("空頭爆倉為主" if ts > tl * 1.5 else "多空均衡"))
    return {
        "symbol": symbol.upper(),
        "interval": iv,
        "source": "Coinalyze（跨 ~25 所彙整，免費層）",
        "period_count": len(history),
        "total_liquidation_usd": round(total, 2),
        "long_liquidation_usd": round(tl, 2),
        "short_liquidation_usd": round(ts, 2),
        "liquidation_bias": bias,
        "caveat": "免費彙整值於劇烈行情會偏低（Binance 2021 起節流 forceOrder）。",
        "history": history,
    }


def get_coinalyze_long_short_ratio(symbol: str = "BTC", interval: str = "1hour",
                                   limit: int = 24) -> Dict[str, Any]:
    """
    【LLM Tool】跨交易所彙整的多空帳戶比（long/short account ratio）。

    比 Binance 單所版更穩（不受 /futures/data 權重限流）、且為跨 ~25 所彙整。
    """
    iv = _norm_interval(interval)
    params = {"symbols": _agg_symbol(symbol), "interval": iv, **_window(iv, limit)}
    logger.info(f"抓取多空比（Coinalyze 跨所）：{symbol} interval={iv}")
    raw = _coinalyze_request("/long-short-ratio-history", params)
    records = raw[0].get("history", []) if isinstance(raw, list) and raw else []
    if not records:
        return {"symbol": symbol.upper(), "source": "Coinalyze", "error": "無多空比數據"}
    latest = records[-1]
    ratio = float(latest.get("r", 0) or 0)
    long_pct = float(latest.get("l", 0) or 0)
    short_pct = float(latest.get("s", 0) or 0)
    sentiment = ("散戶強烈偏多" if ratio > 1.5 else "散戶溫和偏多" if ratio > 1.1 else
                 "散戶強烈偏空" if ratio < 0.67 else "散戶溫和偏空" if ratio < 0.9 else "散戶多空平衡")
    return {
        "symbol": symbol.upper(),
        "interval": iv,
        "source": "Coinalyze（跨 ~25 所彙整，免費層）",
        "latest_ratio": round(ratio, 4),
        "long_account_pct": round(long_pct, 2),
        "short_account_pct": round(short_pct, 2),
        "sentiment_label": sentiment,
        "count": len(records),
        "history": [{"timestamp": int(r.get("t", 0)) * 1000,
                     "long_short_ratio": round(float(r.get("r", 0) or 0), 4),
                     "long_account_pct": round(float(r.get("l", 0) or 0), 2),
                     "short_account_pct": round(float(r.get("s", 0) or 0), 2)} for r in records],
    }


def get_coinalyze_predicted_funding(symbol: str = "BTC") -> Dict[str, Any]:
    """
    【LLM Tool】跨所預測資金費率（下一期）。正值＝多方將付費給空方（市場偏多、多頭擁擠）。

    Args:
        symbol : 幣種符號，例如 'BTC', 'ETH'
    """
    logger.info(f"抓取預測資金費（Coinalyze）：{symbol}")
    raw = _coinalyze_request("/predicted-funding-rate", {"symbols": _agg_symbol(symbol)})
    if not (isinstance(raw, list) and raw):
        return {"symbol": symbol.upper(), "source": "Coinalyze", "error": "無預測資金費數據"}
    # 註：Coinalyze value 已是『百分比』（與 funding-rate-history 同單位，實測=Binance rate×100），不可再 ×100。
    rate_pct = float(raw[0].get("value", 0) or 0)
    return {
        "symbol": symbol.upper(),
        "source": "Coinalyze（跨所預測，免費層）",
        "predicted_funding_rate": round(rate_pct / 100, 8),   # 分數
        "predicted_funding_rate_pct": round(rate_pct, 6),      # 百分比（原值）
        "sentiment": ("偏多（多頭擁擠）" if rate_pct > 0.03 else
                      "偏空（空頭擁擠）" if rate_pct < -0.01 else "中性"),
    }


def get_coinalyze_open_interest(symbol: str = "BTC", interval: str = "1hour",
                                limit: int = 1) -> Dict[str, Any]:
    """
    【LLM Tool】跨交易所彙整的持倉量（OI），把覆蓋從 3 所擴到 ~25 所。

    Args:
        symbol   : 幣種符號，例如 'BTC', 'ETH'
        interval : 時間間隔（預設 1hour）
        limit    : 回溯桶數（預設 1，取最新）
    """
    iv = _norm_interval(interval)
    sym = _agg_symbol(symbol)
    params = {"symbols": sym, "interval": iv, "convert_to_usd": "true", **_window(iv, max(limit, 2))}
    logger.info(f"抓取持倉量（Coinalyze 跨所）：{symbol} interval={iv}")
    raw = _coinalyze_request("/open-interest-history", params)

    records: List[Dict[str, Any]] = []
    if isinstance(raw, list) and raw:
        records = raw[0].get("history", []) if isinstance(raw[0], dict) else []
    if not records:
        return {"symbol": symbol.upper(), "source": "Coinalyze",
                "error": "無持倉量數據（可能符號不支援或免費層限制）。"}

    latest = records[-1]
    # OHLC 型：取 close(c) 作最新 OI（USD）
    latest_oi = float(latest.get("c", latest.get("o", 0)) or 0)
    return {
        "symbol": symbol.upper(),
        "interval": iv,
        "source": "Coinalyze（跨 ~25 所彙整，免費層）",
        "latest_oi_usd": round(latest_oi, 2),
        "count": len(records),
    }

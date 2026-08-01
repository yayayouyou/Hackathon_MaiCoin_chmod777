"""
skills/derivatives/binance_futures.py

幣安合約（Binance Futures）公開 API 封裝
=============================================
提供以下函數（皆不需要 API Key）：
  - get_binance_funding_rate        : 獲取最新與歷史資金費率
  - get_binance_open_interest       : 獲取即時持倉量 (Open Interest)
  - get_binance_open_interest_history: 獲取持倉量歷史統計
  - get_binance_long_short_ratio     : 獲取大戶/全球多空帳戶比率
"""

import time
import requests
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from loguru import logger

from skills._http import session_get

BINANCE_FUTURES_BASE_URL = "https://fapi.binance.com"

def _normalize_symbol(symbol: str) -> str:
    """將交易對名稱標準化（例如 BTC/USDT -> BTCUSDT）"""
    return symbol.replace("/", "").upper()

def _binance_request(endpoint: str, params: Optional[Dict[str, Any]] = None,
                     _retry_on_empty: bool = True) -> Any:
    """執行幣安合約公開 API GET 請求。

    註：/futures/data/ 的統計端點（持倉/多空比歷史）在 IP 權重過高時，會回
    『HTTP 200 + 空陣列』而非 429，共用層的狀態碼重試攔不到。故對這類端點的
    空回應額外做一次退避重試，讓免費多空/持倉 fallback 更穩定。
    """
    url = f"{BINANCE_FUTURES_BASE_URL}{endpoint}"
    logger.debug(f"Binance Futures 請求: {url} params: {params}")
    try:
        resp = session_get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Binance Futures API 請求失敗: {e}")
        raise RuntimeError(f"幣安 API 請求異常: {e}")

    if (_retry_on_empty and "/futures/data/" in endpoint
            and isinstance(data, list) and len(data) == 0):
        logger.warning(f"Binance {endpoint} 回空陣列（疑似權重限流），退避重試一次")
        time.sleep(0.6)
        return _binance_request(endpoint, params, _retry_on_empty=False)
    return data

def get_binance_funding_rate(symbol: str, limit: int = 100) -> Dict[str, Any]:
    """
    獲取幣安合約歷史資金費率。
    """
    normalized_symbol = _normalize_symbol(symbol)
    params = {"symbol": normalized_symbol, "limit": limit}
    raw_data = _binance_request("/fapi/v1/fundingRate", params)

    if not isinstance(raw_data, list) or len(raw_data) == 0:
        return {"symbol": symbol, "error": "無資金費率數據"}

    history = []
    total_rate = 0.0
    for item in raw_data:
        rate = float(item["fundingRate"])
        time_ms = int(item["fundingTime"])
        total_rate += rate
        history.append({
            "timestamp": time_ms,
            "funding_rate": rate,
            "funding_rate_pct": rate * 100,
            "datetime": datetime.fromtimestamp(time_ms / 1000, timezone.utc).isoformat()
        })

    latest_rate = history[-1]["funding_rate"]
    avg_rate = total_rate / len(history)

    # 簡單情緒標籤
    if latest_rate > 0.0003:
        sentiment = "極度偏多/多頭擁擠 (過熱)"
    elif latest_rate > 0.00005:
        sentiment = "偏多 (正常偏溫和)"
    elif latest_rate < -0.0003:
        sentiment = "極度偏空/空頭擁擠 (過冷)"
    elif latest_rate < -0.00005:
        sentiment = "偏空"
    else:
        sentiment = "中性"

    return {
        "symbol": symbol,
        "exchange": "Binance",
        "latest_rate": latest_rate,
        "latest_rate_pct": latest_rate * 100,
        "avg_rate": avg_rate,
        "avg_rate_pct": avg_rate * 100,
        "sentiment": sentiment,
        "history": history,
        "count": len(history)
    }

def get_binance_open_interest(symbol: str) -> Dict[str, Any]:
    """
    獲取幣安合約即時持倉量。
    """
    normalized_symbol = _normalize_symbol(symbol)
    params = {"symbol": normalized_symbol}
    raw_data = _binance_request("/fapi/v1/openInterest", params)

    oi = float(raw_data.get("openInterest", 0.0))
    time_ms = int(raw_data.get("time", 0))

    return {
        "symbol": symbol,
        "exchange": "Binance",
        "open_interest": oi,
        "timestamp": time_ms,
        "datetime": datetime.fromtimestamp(time_ms / 1000, timezone.utc).isoformat() if time_ms else None
    }

def get_binance_open_interest_history(symbol: str, period: str = "1h", limit: int = 30) -> Dict[str, Any]:
    """
    獲取幣安合約歷史持倉量與價值統計。
    支援 period: "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"
    """
    normalized_symbol = _normalize_symbol(symbol)
    params = {"symbol": normalized_symbol, "period": period, "limit": limit}
    raw_data = _binance_request("/futures/data/openInterestHist", params)

    if not isinstance(raw_data, list) or len(raw_data) == 0:
        return {"symbol": symbol, "error": "無歷史持倉數據"}

    history = []
    for item in raw_data:
        time_ms = int(item["timestamp"])
        oi = float(item["sumOpenInterest"])
        oi_usd = float(item["sumOpenInterestValue"])
        history.append({
            "timestamp": time_ms,
            "open_interest": oi,
            "open_interest_value_usd": oi_usd,
            "datetime": datetime.fromtimestamp(time_ms / 1000, timezone.utc).isoformat()
        })

    first_oi = history[0]["open_interest_value_usd"]
    last_oi = history[-1]["open_interest_value_usd"]
    change_pct = ((last_oi - first_oi) / first_oi * 100) if first_oi > 0 else 0.0

    if change_pct > 5.0:
        oi_trend = "上升"
    elif change_pct < -5.0:
        oi_trend = "下降"
    else:
        oi_trend = "震盪"

    return {
        "symbol": symbol,
        "exchange": "Binance",
        "period": period,
        "latest_oi_usd": last_oi,
        "first_oi_usd": first_oi,
        "oi_change_pct": change_pct,
        "oi_trend": oi_trend,
        "history": history,
        "count": len(history)
    }

def get_binance_long_short_ratio(symbol: str, period: str = "1h", limit: int = 30) -> Dict[str, Any]:
    """
    獲取幣安合約全球多空帳戶比率歷史統計。
    支援 period: "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"
    """
    normalized_symbol = _normalize_symbol(symbol)
    params = {"symbol": normalized_symbol, "period": period, "limit": limit}
    raw_data = _binance_request("/futures/data/globalLongShortAccountRatio", params)

    if not isinstance(raw_data, list) or len(raw_data) == 0:
        return {"symbol": symbol, "error": "無歷史多空比數據"}

    history = []
    total_ratio = 0.0
    for item in raw_data:
        time_ms = int(item["timestamp"])
        ratio = float(item["longShortRatio"])
        long_acc = float(item["longAccount"])
        short_acc = float(item["shortAccount"])
        total_ratio += ratio
        history.append({
            "timestamp": time_ms,
            "long_short_ratio": ratio,
            "long_account_pct": long_acc * 100,
            "short_account_pct": short_acc * 100,
            "datetime": datetime.fromtimestamp(time_ms / 1000, timezone.utc).isoformat()
        })

    latest_ratio = history[-1]["long_short_ratio"]
    avg_ratio = total_ratio / len(history)

    if latest_ratio > 1.5:
        sentiment = "散戶強烈偏多"
    elif latest_ratio > 1.1:
        sentiment = "散戶溫和偏多"
    elif latest_ratio < 0.7:
        sentiment = "散戶強烈偏空"
    elif latest_ratio < 0.9:
        sentiment = "散戶溫和偏空"
    else:
        sentiment = "散戶多空平衡"

    return {
        "symbol": symbol,
        "exchange": "Binance",
        "period": period,
        "latest_ratio": latest_ratio,
        "avg_ratio": avg_ratio,
        "sentiment_label": sentiment,
        "history": history,
        "count": len(history)
    }

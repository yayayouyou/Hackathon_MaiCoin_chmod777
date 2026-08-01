"""
skills/derivatives/bybit_derivatives.py

Bybit 合約公開 API 封裝
=============================================
提供以下函數（皆不需要 API Key）：
  - get_bybit_funding_rate          : 獲取歷史資金費率
  - get_bybit_open_interest_history : 獲取持倉量歷史統計
"""

import requests
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from loguru import logger

from skills._http import session_get

BYBIT_BASE_URL = "https://api.bybit.com"

def _normalize_symbol(symbol: str) -> str:
    """將交易對名稱標準化（例如 BTC/USDT -> BTCUSDT）"""
    return symbol.replace("/", "").upper()

def _bybit_request(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """執行 Bybit 公開 API GET 請求"""
    url = f"{BYBIT_BASE_URL}{endpoint}"
    logger.debug(f"Bybit 請求: {url} params: {params}")
    try:
        resp = session_get(url, params=params)
        resp.raise_for_status()
        body = resp.json()
        if body.get("retCode") != 0:
            raise RuntimeError(f"Bybit API 錯誤: {body.get('retMsg')}")
        return body.get("result", {})
    except requests.exceptions.RequestException as e:
        logger.error(f"Bybit API 請求失敗: {e}")
        raise RuntimeError(f"Bybit API 請求異常: {e}")

def get_bybit_funding_rate(symbol: str, limit: int = 100) -> Dict[str, Any]:
    """
    獲取 Bybit 合約歷史資金費率。
    """
    normalized_symbol = _normalize_symbol(symbol)
    params = {
        "category": "linear",
        "symbol": normalized_symbol,
        "limit": limit
    }
    result = _bybit_request("/v5/market/funding/history", params)
    raw_list = result.get("list", [])

    if not raw_list:
        return {"symbol": symbol, "error": "無資金費率數據"}

    history = []
    total_rate = 0.0
    for item in raw_list:
        rate = float(item["fundingRate"])
        time_ms = int(item["fundingRateTimestamp"])
        total_rate += rate
        history.append({
            "timestamp": time_ms,
            "funding_rate": rate,
            "funding_rate_pct": rate * 100,
            "datetime": datetime.fromtimestamp(time_ms / 1000, timezone.utc).isoformat()
        })

    # Bybit 回傳通常是由新到舊，我們將其反轉，使其按時間升序排列，與幣安一致
    history.reverse()

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
        "exchange": "Bybit",
        "latest_rate": latest_rate,
        "latest_rate_pct": latest_rate * 100,
        "avg_rate": avg_rate,
        "avg_rate_pct": avg_rate * 100,
        "sentiment": sentiment,
        "history": history,
        "count": len(history)
    }

def get_bybit_open_interest_history(symbol: str, interval: str = "1h", limit: int = 30) -> Dict[str, Any]:
    """
    獲取 Bybit 合約歷史持倉量。
    支援 interval: "5min", "15min", "30min", "1h", "4h", "1d"
    """
    normalized_symbol = _normalize_symbol(symbol)
    
    # 轉換 interval 時間格式為 Bybit 支持的格式
    interval_map = {
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d"
    }
    bybit_interval = interval_map.get(interval, interval)

    params = {
        "category": "linear",
        "symbol": normalized_symbol,
        "intervalTime": bybit_interval,
        "limit": limit
    }
    result = _bybit_request("/v5/market/open-interest", params)
    raw_list = result.get("list", [])

    if not raw_list:
        return {"symbol": symbol, "error": "無持倉量數據"}

    history = []
    for item in raw_list:
        time_ms = int(item["timestamp"])
        oi = float(item["openInterest"])
        history.append({
            "timestamp": time_ms,
            "open_interest": oi,
            "datetime": datetime.fromtimestamp(time_ms / 1000, timezone.utc).isoformat()
        })

    # Bybit 回傳通常是由新到舊，將其反轉為升序
    history.reverse()

    first_oi = history[0]["open_interest"]
    last_oi = history[-1]["open_interest"]
    change_pct = ((last_oi - first_oi) / first_oi * 100) if first_oi > 0 else 0.0

    if change_pct > 5.0:
        oi_trend = "上升"
    elif change_pct < -5.0:
        oi_trend = "下降"
    else:
        oi_trend = "震盪"

    return {
        "symbol": symbol,
        "exchange": "Bybit",
        "interval": interval,
        "latest_oi": last_oi,
        "first_oi": first_oi,
        "oi_change_pct": change_pct,
        "oi_trend": oi_trend,
        "history": history,
        "count": len(history)
    }

"""
skills/derivatives/okx_derivatives.py

OKX 合約公開 API 封裝
=============================================
提供以下函數（皆不需要 API Key）：
  - get_okx_funding_rate  : 獲取歷史與最新資金費率
  - get_okx_open_interest  : 獲取即時持倉量
"""

import requests
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from loguru import logger

from skills._http import session_get

OKX_BASE_URL = "https://www.okx.com"

def _to_okx_swap_inst_id(symbol: str) -> str:
    """
    將通用交易對符號轉換為 OKX Swap 合約代碼。
    例如: BTC/USDT -> BTC-USDT-SWAP
          BTCUSDT -> BTC-USDT-SWAP
          BTC-USDT -> BTC-USDT-SWAP
    """
    symbol_upper = symbol.upper()
    if symbol_upper.endswith("-SWAP"):
        return symbol_upper
    
    # 清理所有分隔符
    clean = symbol_upper.replace("/", "").replace("_", "").replace("-", "")
    
    if clean.endswith("USDT"):
        base = clean[:-4]
        return f"{base}-USDT-SWAP"
    elif clean.endswith("USD"):
        base = clean[:-3]
        return f"{base}-USD-SWAP"
    else:
        return f"{clean}-USDT-SWAP"

def _okx_request(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """執行 OKX 公開 API GET 請求"""
    url = f"{OKX_BASE_URL}{endpoint}"
    logger.debug(f"OKX 請求: {url} params: {params}")
    try:
        resp = session_get(url, params=params)
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") != "0":
            raise RuntimeError(f"OKX API 錯誤: {body.get('msg')}")
        return body.get("data", [])
    except requests.exceptions.RequestException as e:
        logger.error(f"OKX API 請求失敗: {e}")
        raise RuntimeError(f"OKX API 請求異常: {e}")

def get_okx_funding_rate(symbol: str, limit: int = 100) -> Dict[str, Any]:
    """
    獲取 OKX 合約歷史與最新資金費率。
    """
    inst_id = _to_okx_swap_inst_id(symbol)
    params = {"instId": inst_id, "limit": limit}
    raw_list = _okx_request("/api/v5/public/funding-rate-history", params)

    if not raw_list:
        return {"symbol": symbol, "error": "無資金費率數據"}

    history = []
    total_rate = 0.0
    for item in raw_list:
        rate = float(item["fundingRate"])
        time_ms = int(item["fundingTime"])
        total_rate += rate
        history.append({
            "timestamp": time_ms,
            "funding_rate": rate,
            "funding_rate_pct": rate * 100,
            "datetime": datetime.fromtimestamp(time_ms / 1000, timezone.utc).isoformat()
        })

    # OKX 回傳也是從新到舊，反轉為升序
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
        "instId": inst_id,
        "exchange": "OKX",
        "latest_rate": latest_rate,
        "latest_rate_pct": latest_rate * 100,
        "avg_rate": avg_rate,
        "avg_rate_pct": avg_rate * 100,
        "sentiment": sentiment,
        "history": history,
        "count": len(history)
    }

def get_okx_open_interest(symbol: str) -> Dict[str, Any]:
    """
    獲取 OKX 合約即時持倉量。
    """
    inst_id = _to_okx_swap_inst_id(symbol)
    params = {"instId": inst_id}
    raw_list = _okx_request("/api/v5/public/open-interest", params)

    if not raw_list:
        return {"symbol": symbol, "error": "無即時持倉數據"}

    item = raw_list[0]
    oi = float(item["oi"])
    time_ms = int(item.get("ts", 0))

    return {
        "symbol": symbol,
        "instId": inst_id,
        "exchange": "OKX",
        "open_interest": oi,
        "open_interest_ccy": item.get("oiCcy"),
        "timestamp": time_ms,
        "datetime": datetime.fromtimestamp(time_ms / 1000, timezone.utc).isoformat() if time_ms else None
    }

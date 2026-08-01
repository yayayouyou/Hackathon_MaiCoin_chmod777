"""
skills/market_intel/fng_client.py

加密貨幣恐懼與貪婪指數 (Fear & Greed Index) — Alternative.me 公開免費 API
===================================================
治本改版：原本抓失敗時回傳 fallback_value=50 / "Neutral"，且缺值默認 50 —— 這對
交易 agent 是危險的『靜默失敗當成有效數據』：模型會把捏造的「中性 50」當成真實市場情緒。
現在改為：抓失敗或空資料一律回 error（絕不捏造數值），並走共用 HTTP 韌性層。
"""
from typing import Dict, Any
from loguru import logger

from skills._http import fetch_json, FetchError

ALTERNATIVE_ME_FNG_URL = "https://api.alternative.me/fng/"


def get_crypto_fear_and_greed_index(limit: int = 1) -> Dict[str, Any]:
    """
    【LLM Tool】獲取加密貨幣市場最新的「恐懼與貪婪指數」(Fear & Greed Index)。
    數值 0-100：0-25 極度恐懼，46-54 中性，76-100 極度貪婪。

    Args:
        limit: 獲取的天數，預設 1（最新一天）。一般查詢建議 ≤100；回測可帶大值取更長歷史（上限 2000）。
    """
    limit = max(1, min(2000, limit))
    logger.info(f"請求 Alternative.me 恐懼與貪婪指數, limit: {limit}")

    try:
        raw = fetch_json(ALTERNATIVE_ME_FNG_URL, params={"limit": limit}, expect_keys=["data"])
    except FetchError as e:
        logger.error(f"恐懼與貪婪指數抓取失敗: {e}")
        return {"error": f"獲取恐懼與貪婪指數失敗（來源無回應，未提供任何數值）: {e}"}

    if (raw.get("metadata") or {}).get("error") is not None:
        return {"error": f"Alternative.me 業務錯誤: {raw['metadata']['error']}"}

    formatted = []
    for item in raw.get("data") or []:
        v = item.get("value")
        if v is None:              # 缺值就跳過，絕不以 50 頂替
            continue
        try:
            v = int(v)
        except (TypeError, ValueError):
            continue
        formatted.append({
            "value": v,
            "sentiment": item.get("value_classification", ""),
            "timestamp": int(item.get("timestamp") or 0),
        })

    if not formatted:              # 空資料回 error，不捏造中性 50
        return {"error": "恐懼與貪婪指數來源回傳空資料，暫時無法取得（未提供任何數值）"}

    latest = formatted[0]
    return {
        "name": "Crypto Fear and Greed Index",
        "latest_value": latest["value"],
        "latest_sentiment": latest["sentiment"],
        "latest_timestamp": latest["timestamp"],
        "history": formatted,
        "description": "0-25: 極度恐懼, 26-45: 恐懼, 46-54: 中性, 55-75: 貪婪, 76-100: 極度貪婪",
    }

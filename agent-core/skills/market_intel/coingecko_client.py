"""
skills/market_intel/coingecko_client.py

CoinGecko 公開數據 API 封裝
=============================================
提供以下公開行情與情報函數：
  - get_coingecko_coin_price    : 獲取指定代幣即時價格（可批量，例如 'bitcoin,ethereum'）
  - get_coingecko_global_stats  : 獲取加密貨幣全市場概覽（總市值、市值佔有率等）
  - get_coingecko_trending      : 獲取全網熱搜熱門代幣列表 (Trending)
"""

import os
import time
import threading
import requests
from typing import Optional, Dict, Any, List
from loguru import logger
from dotenv import load_dotenv

from skills._http import session_get

load_dotenv()

# CoinGecko Demo/Public Base URL
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"

# TTL 快取：慢變資料快取較久，省免費層額度（10k credits/月）並降延遲
_TTL_BY_ENDPOINT = {"/simple/price": 30, "/global": 120, "/search/trending": 300}
_DEFAULT_TTL = 60
_cache: Dict[str, Any] = {}
_cache_lock = threading.Lock()


def _is_placeholder_key(key: str) -> bool:
    """偵測 .env 內仍為範本佔位符（如 your_xxx_here）而非真實金鑰的情況。"""
    k = (key or "").strip().lower()
    if not k:
        return True
    return (k.startswith("your") or k.startswith("<") or
            k in ("changeme", "placeholder", "xxx", "api_key", "todo", "none"))


def _coingecko_request(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """執行 CoinGecko API GET（帶 TTL 快取 + API Key + 共用韌性層自動重試/限流）。"""
    cache_key = f"{endpoint}?{sorted((params or {}).items())}"
    ttl = _TTL_BY_ENDPOINT.get(endpoint, _DEFAULT_TTL)
    now = time.time()
    with _cache_lock:
        hit = _cache.get(cache_key)
        if hit and (now - hit[0]) < ttl:
            return hit[1]

    api_key = os.getenv("COINGECKO_API_KEY", "")
    headers = {"accept": "application/json"}
    # 佔位符也送出的話，/global、/market_chart 會回 401；沒金鑰就走免費公開層
    if not _is_placeholder_key(api_key):
        headers["x-cg-demo-api-key"] = api_key.strip()  # Demo key 走 header
    actual_params = params.copy() if params else {}

    url = f"{COINGECKO_BASE_URL}{endpoint}"
    logger.debug(f"CoinGecko 請求: {url} params: {actual_params}")

    try:
        resp = session_get(url, headers=headers, params=actual_params)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"CoinGecko API 請求失敗: {e}")
        raise RuntimeError(f"CoinGecko API 請求異常: {e}")

    with _cache_lock:
        _cache[cache_key] = (now, data)
    return data

def get_coingecko_coin_price(ids: str, vs_currencies: str = "usd") -> Dict[str, Any]:
    """
    【LLM Tool】獲取一個或多個加密貨幣的即時價格與 24 小時漲跌幅、市值等。
    
    Args:
        ids: 幣種 ID 清單（小寫，逗號分隔，使用 CoinGecko ID 而非符號），例如 'bitcoin,ethereum,solana'
        vs_currencies: 法幣或報價貨幣，例如 'usd', 'twd'，預設為 'usd'
    """
    params = {
        "ids": ids.lower(),
        "vs_currencies": vs_currencies.lower(),
        "include_market_cap": "true",
        "include_24hr_vol": "true",
        "include_24hr_change": "true",
        "include_last_updated_at": "true"
    }
    return _coingecko_request("/simple/price", params)

def get_coingecko_global_stats() -> Dict[str, Any]:
    """
    【LLM Tool】獲取加密貨幣全球市場統計指標（全球總市值、24小時交易量、BTC及ETH市佔率、24小時市值變動百分比等）。
    """
    raw_data = _coingecko_request("/global")
    data = raw_data.get("data", {})
    
    # 精簡數據以節省 token
    return {
        "active_cryptocurrencies": data.get("active_cryptocurrencies"),
        "upcoming_icos": data.get("upcoming_icos"),
        "ongoing_icos": data.get("ongoing_icos"),
        "markets": data.get("markets"),
        "total_market_cap_usd": data.get("total_market_cap", {}).get("usd"),
        "total_volume_usd": data.get("total_volume", {}).get("usd"),
        "market_cap_percentage": {
            "btc": data.get("market_cap_percentage", {}).get("btc"),
            "eth": data.get("market_cap_percentage", {}).get("eth"),
            "usdt": data.get("market_cap_percentage", {}).get("usdt")
        },
        "market_cap_change_percentage_24h_usd": data.get("market_cap_change_percentage_24h_usd")
    }

def get_coingecko_trending() -> List[Dict[str, Any]]:
    """
    【LLM Tool】獲取 CoinGecko 過去 24 小時最受用戶歡迎和熱搜的熱門代幣列表 (Trending)。
    """
    raw_data = _coingecko_request("/search/trending")
    coins = raw_data.get("coins", [])
    
    trending = []
    for c in coins:
        item = c.get("item", {})
        trending.append({
            "id": item.get("id"),
            "coin_id": item.get("coin_id"),
            "name": item.get("name"),
            "symbol": item.get("symbol"),
            "market_cap_rank": item.get("market_cap_rank"),
            "price_btc": item.get("price_btc"),
            "score": item.get("score")
        })
    return trending

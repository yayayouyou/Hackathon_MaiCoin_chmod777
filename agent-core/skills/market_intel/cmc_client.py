"""
skills/market_intel/cmc_client.py

CoinMarketCap API 封裝
=============================================
提供以下行情與排名指標函數 (需要 API Key)：
  - get_cmc_latest_quotes  : 獲取最新即時報價與市值指標（支持多幣種批次）
  - get_cmc_global_metrics : 獲取全球市場大盤數據（總市值、佔有率、主導度等）
"""

import os
import requests
from typing import Optional, Dict, Any, List
from loguru import logger
from dotenv import load_dotenv

from skills._http import session_get

load_dotenv()

CMC_BASE_URL = "https://pro-api.coinmarketcap.com"

# 免費替代：CoinGecko 提供等價的大盤/報價數據（免付費金鑰）
_CMC_FREE_ALT_HINT = ("免費替代：get_coingecko_global_stats（大盤總市值/主導度）、"
                      "get_coingecko_coin_price（即時報價/市值）。")


def _is_placeholder_key(key: str) -> bool:
    """偵測 .env 內仍為範本佔位符（如 your_xxx_here）而非真實金鑰的情況。"""
    k = (key or "").strip().lower()
    if not k:
        return True
    return (k.startswith("your") or k.startswith("<") or
            k in ("changeme", "placeholder", "xxx", "api_key", "todo", "none"))


def _cmc_request(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """執行 CoinMarketCap PRO API GET 請求"""
    api_key = os.getenv("COINMARKETCAP_API_KEY", "").strip()
    if _is_placeholder_key(api_key):
        raise EnvironmentError(
            "COINMARKETCAP_API_KEY 未設定（或仍為 .env 範本佔位符）！請填入真實的 CoinMarketCap API Key。\n"
            f"申請地址：https://pro.coinmarketcap.com/signup\n{_CMC_FREE_ALT_HINT}"
        )

    headers = {
        "Accepts": "application/json",
        "X-CMC_PRO_API_KEY": api_key
    }
    url = f"{CMC_BASE_URL}{endpoint}"
    logger.debug(f"CoinMarketCap 請求: {url} params: {params}")
    
    try:
        resp = session_get(url, headers=headers, params=params)
        resp.raise_for_status()
        body = resp.json()
        
        status = body.get("status", {})
        if status.get("error_code") != 0:
            raise RuntimeError(f"CMC API 錯誤 (code={status.get('error_code')}): {status.get('error_message')}")
            
        return body.get("data", {})
    except requests.exceptions.RequestException as e:
        logger.error(f"CoinMarketCap API 請求失敗: {e}")
        # 嘗試讀取業務錯誤
        try:
            err_body = e.response.json()
            err_msg = err_body.get("status", {}).get("error_message", str(e))
        except Exception:
            err_msg = str(e)
        raise RuntimeError(f"CoinMarketCap API 請求異常: {err_msg}。{_CMC_FREE_ALT_HINT}")

def get_cmc_latest_quotes(symbols: str, convert: str = "USD") -> Dict[str, Any]:
    """
    【LLM Tool】獲取一個或多個代幣符號的 CoinMarketCap 最新報價與市值指標（支持逗號分隔批量查詢）。
    
    Args:
        symbols: 代幣符號，例如 'BTC,ETH,SOL' (大寫，逗號分隔)
        convert: 報價法幣/加密貨幣，例如 'USD', 'TWD', 'BTC'，預設為 'USD'
    """
    # 本站有兩種 symbols 慣例並存（此處是逗號分隔字串，analyze_portfolio 是陣列），
    # LLM 很容易傳錯。收到 list/tuple 就接受並轉換，別讓它炸成看不懂的 AttributeError。
    if isinstance(symbols, (list, tuple)):
        symbols = ",".join(str(s) for s in symbols)
    # 順手容忍 'BTC/USDT' 這種交易對寫法 —— CMC 要的是純代幣符號
    syms = ",".join(str(s).strip().split("/")[0].upper()
                    for s in str(symbols).split(",") if str(s).strip())
    params = {
        "symbol": syms,
        "convert": str(convert).upper()
    }
    raw_data = _cmc_request("/v1/cryptocurrency/quotes/latest", params)
    
    # 結構化輸出以節省 token
    formatted = {}
    for sym, coin_info in raw_data.items():
        quote = coin_info.get("quote", {}).get(convert.upper(), {})
        formatted[sym] = {
            "name": coin_info.get("name"),
            "symbol": coin_info.get("symbol"),
            "cmc_rank": coin_info.get("cmc_rank"),
            "max_supply": coin_info.get("max_supply"),
            "circulating_supply": coin_info.get("circulating_supply"),
            "total_supply": coin_info.get("total_supply"),
            "price": quote.get("price"),
            "volume_24h": quote.get("volume_24h"),
            "percent_change_1h": quote.get("percent_change_1h"),
            "percent_change_24h": quote.get("percent_change_24h"),
            "percent_change_7d": quote.get("percent_change_7d"),
            "market_cap": quote.get("market_cap"),
            "last_updated": quote.get("last_updated")
        }
    return formatted

def get_cmc_global_metrics(convert: str = "USD") -> Dict[str, Any]:
    """
    【LLM Tool】獲取 CoinMarketCap 的加密貨幣全網全球宏觀指標（大盤總市值、24小時交易量、BTC主導度等）。
    
    Args:
        convert: 轉換貨幣，例如 'USD', 'TWD'
    """
    params = {"convert": convert.upper()}
    data = _cmc_request("/v1/global-metrics/quotes/latest", params)
    
    quote = data.get("quote", {}).get(convert.upper(), {})
    return {
        "active_cryptocurrencies": data.get("active_cryptocurrencies"),
        "total_cryptocurrencies": data.get("total_cryptocurrencies"),
        "active_exchanges": data.get("active_exchanges"),
        "btc_dominance": data.get("btc_dominance"),
        "eth_dominance": data.get("eth_dominance"),
        "total_market_cap": quote.get("total_market_cap"),
        "total_volume_24h": quote.get("total_volume_24h"),
        "market_cap_change_24h": quote.get("total_market_cap_yesterday_percentage_change"),
        "last_updated": data.get("last_updated")
    }

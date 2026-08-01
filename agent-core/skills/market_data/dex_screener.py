"""
skills/market_data/dex_screener.py

去中心化交易所 (DEX) 行情抓取工具 — 基於 DEX Screener API
======================================================
無須 API Key，支持查詢 Solana, Base, EVM 等鏈上所有去中心化配對的流動性與價格。
"""

from typing import Dict, Any, List
from loguru import logger

from skills._http import session_get

DEX_SCREENER_BASE_URL = "https://api.dexscreener.com/latest/dex"


def _to_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _liq_usd(pair: Dict[str, Any]) -> float:
    """安全取流動性 USD。DEX Screener 對新/低流動性池會回 liquidity:{usd:null}，
    直接 .get('usd', 0) 會拿到 None 而非 0，導致 sorted() 比較 None 崩潰、丟掉全部結果。"""
    return _to_float((pair.get("liquidity") or {}).get("usd"), 0.0)


def _clean_pair_data(pair: Dict[str, Any]) -> Dict[str, Any]:
    """簡化並提取 DEX 配對中最關鍵的行情數據，避免 token 冗餘"""
    return {
        "chainId": pair.get("chainId", ""),
        "dexId": pair.get("dexId", ""),
        "pairAddress": pair.get("pairAddress", ""),
        "baseToken": {
            "address": pair.get("baseToken", {}).get("address", ""),
            "name": pair.get("baseToken", {}).get("name", ""),
            "symbol": pair.get("baseToken", {}).get("symbol", "")
        },
        "quoteToken": {
            "symbol": pair.get("quoteToken", {}).get("symbol", "")
        },
        "priceNative": _to_float(pair.get("priceNative"), None),
        "priceUsd": _to_float(pair.get("priceUsd"), None),
        "txns": pair.get("txns", {}),
        "volume": pair.get("volume", {}),
        "priceChange": pair.get("priceChange", {}),
        "liquidity": {
            "usd": _liq_usd(pair),
            "base": _to_float((pair.get("liquidity") or {}).get("base"), 0.0),
            "quote": _to_float((pair.get("liquidity") or {}).get("quote"), 0.0)
        },
        "fdv": _to_float(pair.get("fdv"), 0.0),
        "pairCreatedAt": pair.get("pairCreatedAt", 0)
    }

def search_dex_pairs(query: str) -> Dict[str, Any]:
    """
    【LLM Tool】在去中心化交易所中搜尋代幣配對資訊（根據代幣名稱、符號或合約地址）。
    
    Args:
        query: 搜尋關鍵字，可以是代幣符號（如 'WIF'）、名稱（如 'dogwifhat'）或合約地址。
    """
    logger.info(f"正在 DEX Screener 搜尋配對交易池，關鍵字: {query}")
    url = f"{DEX_SCREENER_BASE_URL}/search"
    
    try:
        response = session_get(url, params={"q": query})
        response.raise_for_status()
        data = response.json()

        pairs = data.get("pairs", [])
        if not pairs:
            return {"query": query, "count": 0, "pairs": [], "message": "未找到匹配的 DEX 交易池"}

        # 僅保留前 8 個流動性最高/最相關的交易對，避免超出 context 限制
        sorted_pairs = sorted(pairs, key=_liq_usd, reverse=True)[:8]
        
        cleaned_pairs = [_clean_pair_data(p) for p in sorted_pairs]
        return {
            "query": query,
            "count": len(cleaned_pairs),
            "pairs": cleaned_pairs
        }
        
    except Exception as e:
        logger.error(f"DEX Screener 搜尋失敗: {e}")
        return {"error": f"DEX Screener 搜尋出錯: {str(e)}"}

def get_dex_token_info(token_address: str) -> Dict[str, Any]:
    """
    【LLM Tool】根據代幣合約地址獲取其在 DEX 上的配對池行情與價格。
    
    Args:
        token_address: 代幣合約地址（例如 Solana 的 'EKpQGSJtjMFqKZ9KQGWjh69d5189ocZ2WqiTaG2Spump' 代表 WIF）
    """
    logger.info(f"正在 DEX Screener 獲取代幣合約行情，地址: {token_address}")
    url = f"{DEX_SCREENER_BASE_URL}/tokens/{token_address}"
    
    try:
        response = session_get(url)
        response.raise_for_status()
        data = response.json()

        pairs = data.get("pairs", [])
        if not pairs:
            return {"token_address": token_address, "count": 0, "pairs": [], "message": "此合約地址未在 DEX 上找到活躍交易池"}

        # 依流動性排序，提取前 5 個池子
        sorted_pairs = sorted(pairs, key=_liq_usd, reverse=True)[:5]
        
        cleaned_pairs = [_clean_pair_data(p) for p in sorted_pairs]
        return {
            "token_address": token_address,
            "count": len(cleaned_pairs),
            "pairs": cleaned_pairs
        }
        
    except Exception as e:
        logger.error(f"DEX Screener 代幣查詢失敗: {e}")
        return {"error": f"DEX Screener 代幣查詢出錯: {str(e)}"}

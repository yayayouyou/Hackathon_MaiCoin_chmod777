"""
skills/market_intel/blockchain_client.py

Blockchain.com BTC 鏈上數據 API 封裝
=============================================
提供以下 BTC 鏈上公開指標函數（皆不需要 API Key）：
  - get_blockchain_btc_stats  : 獲取 BTC 全網即時統計 (算力、難度、出塊時間、礦工收益)
  - get_btc_unconfirmed_tx     : 獲取 BTC 網絡當前未確認交易數量 (Mempool 堵塞度)
"""

import requests
from typing import Dict, Any
from loguru import logger

from skills._http import session_get

BLOCKCHAIN_INFO_BASE = "https://blockchain.info"
BLOCKCHAIN_API_BASE = "https://api.blockchain.info"

def _blockchain_get(base_url: str, endpoint: str) -> Any:
    """執行 Blockchain.com 公開 API 請求"""
    url = f"{base_url}{endpoint}"
    logger.debug(f"Blockchain.com 請求: {url}")
    try:
        resp = session_get(url)
        resp.raise_for_status()
        
        # 判斷是否為純文字/數字返回值，或是 JSON
        content_type = resp.headers.get("Content-Type", "")
        if "application/json" in content_type:
            return resp.json()
        else:
            return resp.text.strip()
    except requests.exceptions.RequestException as e:
        logger.error(f"Blockchain.com API 請求失敗: {e}")
        raise RuntimeError(f"Blockchain.com API 請求異常: {e}")

def get_blockchain_btc_stats() -> Dict[str, Any]:
    """
    【LLM Tool】獲取比特幣 (BTC) 全網最新的鏈上即時數據。
    包含：算力 (hash_rate)、挖礦難度 (difficulty)、24小時區塊數量、區塊產出時間間隔、礦工總收益 (USD) 等。
    """
    data = _blockchain_get(BLOCKCHAIN_API_BASE, "/stats")
    
    # 整理格式
    return {
        "market_price_usd": data.get("market_price_usd"),
        "hash_rate_ghs": data.get("hash_rate"),                        # 單位: GH/s
        "hash_rate_ehs": data.get("hash_rate", 0) / 1000000000.0,       # 單位: EH/s
        "difficulty": data.get("difficulty"),
        "total_btc_sent": data.get("total_btc_sent"),
        "estimated_btc_sent": data.get("estimated_btc_sent"),
        "miners_revenue_usd": data.get("miners_revenue_usd"),
        "btc_mined_24h": data.get("btc_mined"),
        "minutes_between_blocks": data.get("minutes_between_blocks"),
        "blocks_mined_24h": data.get("n_blocks_mined"),
        "timestamp": data.get("timestamp")
    }

def get_btc_unconfirmed_tx() -> Dict[str, Any]:
    """
    【LLM Tool】獲取當前比特幣網絡記憶體池 (Mempool) 中未確認的交易總數。
    適用於：判斷網絡擁堵程度與預估鏈上手續費。若數值極高，代表網絡繁忙，交易需要較高 fee 才能被確認。
    """
    count_str = _blockchain_get(BLOCKCHAIN_INFO_BASE, "/q/unconfirmedcount")
    try:
        count = int(count_str)
    except (ValueError, TypeError):
        return {"error": "無法取得未確認交易數（來源回傳非數值）"}

    # 簡單分析擁擠程度
    if count > 150000:
        status = "極度擁堵 (手續費可能飆升)"
    elif count > 50000:
        status = "中度擁堵 (交易確認可能延遲)"
    else:
        status = "網絡暢通"
        
    return {
        "unconfirmed_transactions_count": count,
        "mempool_status": status
    }

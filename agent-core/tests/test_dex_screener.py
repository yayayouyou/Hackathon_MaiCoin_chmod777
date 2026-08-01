"""
tests/test_dex_screener.py

DEX Screener 行情查詢單元與整合測試
====================================
"""

import pytest
from unittest.mock import patch, MagicMock
from skills.market_data.dex_screener import search_dex_pairs, get_dex_token_info

# --- Mock 測試 ---

@patch("skills.market_data.dex_screener.session_get")
def test_search_dex_pairs_mock(mock_get):
    """測試搜尋 DEX 配對的 JSON 解析與結構簡化 (Mock)"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "pairs": [
            {
                "chainId": "solana",
                "dexId": "raydium",
                "pairAddress": "8sLbNZo1Tv4U7FM5C1B3nBWD8RXX8us8a32y6bUqpump",
                "baseToken": {
                    "address": "EKpQGSJtjMFqKZ9KQGWjh69d5189ocZ2WqiTaG2Spump",
                    "name": "dogwifhat",
                    "symbol": "WIF"
                },
                "quoteToken": {
                    "symbol": "SOL"
                },
                "priceNative": "0.015",
                "priceUsd": "2.10",
                "liquidity": {
                    "usd": 500000,
                    "base": 238000,
                    "quote": 262000
                },
                "fdv": 2100000000
            }
        ]
    }
    mock_get.return_value = mock_response

    res = search_dex_pairs("WIF")

    assert res["count"] == 1
    assert res["pairs"][0]["chainId"] == "solana"
    assert res["pairs"][0]["baseToken"]["symbol"] == "WIF"
    assert res["pairs"][0]["priceUsd"] == 2.10          # 現在轉為 float
    assert res["pairs"][0]["liquidity"]["usd"] == 500000


@patch("skills.market_data.dex_screener.session_get")
def test_null_liquidity_does_not_crash(mock_get):
    """回歸：新/低流動性池 liquidity:{usd:null} 不可讓排序崩潰而丟掉全部結果。"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "pairs": [
            {"chainId": "solana", "baseToken": {"symbol": "NEW"}, "quoteToken": {"symbol": "SOL"},
             "priceUsd": "0.001", "liquidity": {"usd": None}},          # ← null 流動性
            {"chainId": "solana", "baseToken": {"symbol": "BIG"}, "quoteToken": {"symbol": "SOL"},
             "priceUsd": "1.0", "liquidity": {"usd": 900000}},
            {"chainId": "solana", "baseToken": {"symbol": "NOLIQ"}, "quoteToken": {"symbol": "SOL"},
             "priceUsd": "0.5"},                                        # ← 完全沒 liquidity 欄位
        ]
    }
    mock_get.return_value = mock_response
    res = search_dex_pairs("X")
    assert "error" not in res
    assert res["count"] == 3                       # 三筆都保留、沒崩潰
    assert res["pairs"][0]["baseToken"]["symbol"] == "BIG"   # 高流動性排最前

@patch("skills.market_data.dex_screener.session_get")
def test_get_dex_token_info_mock(mock_get):
    """測試依合約地址查詢 DEX 行情的 JSON 解析與結構簡化 (Mock)"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "pairs": [
            {
                "chainId": "ethereum",
                "dexId": "uniswap",
                "pairAddress": "0x11b711a1a0b5f543e494a8c9b33a758784ea9c8b",
                "baseToken": {
                    "address": "0xdac17f958d2ee523a2206206994597c13d831ec7",
                    "name": "Tether USD",
                    "symbol": "USDT"
                },
                "quoteToken": {
                    "symbol": "WETH"
                },
                "priceNative": "0.0003",
                "priceUsd": "1.00",
                "liquidity": {
                    "usd": 12000000
                },
                "fdv": 120000000
            }
        ]
    }
    mock_get.return_value = mock_response
    
    res = get_dex_token_info("0xdac17f958d2ee523a2206206994597c13d831ec7")
    
    assert res["count"] == 1
    assert res["pairs"][0]["chainId"] == "ethereum"
    assert res["pairs"][0]["baseToken"]["symbol"] == "USDT"

# --- 真實整合測試 ---

def test_real_search_dex_pairs():
    """真實對接 DEX Screener API 搜尋 WIF"""
    res = search_dex_pairs("WIF")
    
    # 只要網絡正常，應成功返回結果（或空列表，但不應報錯）
    assert "error" not in res
    assert "pairs" in res
    if res["count"] > 0:
        assert res["pairs"][0]["baseToken"]["symbol"] == "WIF"
        assert float(res["pairs"][0]["priceUsd"]) > 0

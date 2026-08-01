"""
tests/test_mcp_server.py

MCP Server 整合與註冊單元測試
==================================
"""

import pytest
import asyncio
from mcp_server import mcp

@pytest.mark.asyncio
async def test_mcp_server_tools_registration():
    """驗證所有規劃的 19 個加密金融交易工具已成功註冊至 FastMCP 伺服器"""
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    
    expected_tools = [
        "fetch_ohlcv",
        "fetch_ticker",
        "fetch_orderbook",
        "fetch_coinglass_liquidation_heatmap",
        "fetch_coinglass_ahr999",
        "fetch_coinglass_altcoin_season",
        "fetch_coinglass_mayer_multiple",
        "fetch_coinglass_etf_flow",
        "fetch_coinglass_grayscale_stats",
        "fetch_aggregated_funding_rate",
        "fetch_aggregated_open_interest",
        "fetch_max_tickers",
        "fetch_max_accounts",
        "fetch_max_orders",
        "fetch_crypto_fear_and_greed_index",
        "fetch_blockchain_btc_stats",
        "fetch_btc_unconfirmed_tx",
        "execute_backtest",
        "execute_create_order",
        "execute_save_strategy",
        "execute_list_strategies",
        "execute_run_backtest_on_saved_strategy",
        "execute_search_dex_pairs",
        "execute_get_dex_token_info",
        "fetch_latest_crypto_news",
        "execute_fetch_reddit_sentiment",
        "execute_web_search",
        "execute_fetch_trump_truth_posts",
        "execute_fetch_twitter_user_tweets",
        "execute_run_twitter_mention_backtest"
    ]
    
    for tool in expected_tools:
        assert tool in tool_names, f"工具 {tool} 未成功註冊至 MCP"

@pytest.mark.asyncio
async def test_mcp_tool_execution_mock():
    """驗證 MCP 伺服器的 call_tool 調用邏輯"""
    # 測試 fetch_crypto_fear_and_greed_index 最新數據調用
    content, meta = await mcp.call_tool("fetch_crypto_fear_and_greed_index", arguments={"limit": 1})
    import json
    res = json.loads(content[0].text)
    
    assert "latest_value" in res
    assert "latest_sentiment" in res
    assert res["name"] == "Crypto Fear and Greed Index"

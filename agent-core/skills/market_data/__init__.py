"""
skills/market_data/__init__.py
統一對外暴露模塊一的所有公開函數，方便 import 使用。
"""

from .ccxt_fetcher import (
    get_ohlcv,
    get_ticker,
    get_orderbook,
    list_exchanges,
)
from .coinglass_client import (
    get_funding_rate,
    get_open_interest,
    get_liquidation_history,
    get_long_short_ratio,
)
from .coinglass_scraper import (
    get_coinglass_liquidation_chart,
    get_coinglass_open_interest_info,
    get_coinglass_home_stats,
    get_coinglass_ahr999,
    get_coinglass_altcoin_season,
    get_coinglass_mayer_multiple,
    get_coinglass_etf_flow,
    get_coinglass_grayscale_stats,
    get_coinglass_liquidation_heatmap,
)
from .dex_screener import (
    search_dex_pairs,
    get_dex_token_info,
)

__all__ = [
    # CCXT 行情
    "get_ohlcv",
    "get_ticker",
    "get_orderbook",
    "list_exchanges",
    # Coinglass 衍生品數據
    "get_funding_rate",
    "get_open_interest",
    "get_liquidation_history",
    "get_long_short_ratio",
    # Coinglass 免 Key 抓取工具
    "get_coinglass_liquidation_chart",
    "get_coinglass_open_interest_info",
    "get_coinglass_home_stats",
    "get_coinglass_ahr999",
    "get_coinglass_altcoin_season",
    "get_coinglass_mayer_multiple",
    "get_coinglass_etf_flow",
    "get_coinglass_grayscale_stats",
    "get_coinglass_liquidation_heatmap",
    # DEX Screener 去中心化行情
    "search_dex_pairs",
    "get_dex_token_info",
]

"""
mcp_server.py

Model Context Protocol (MCP) Server for Crypto Trading Skills
=============================================================
Exposes all analytical, market intelligence, trading, and execution tools
as standard MCP tools to be consumed by IDEs (Cursor, VS Code) or Claude Desktop.
"""

import os
import sys
import json
from typing import Optional, Dict, Any, List
from mcp.server.fastmcp import FastMCP

# Ensure the root directory of the project is in the system path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Initialize FastMCP Server
mcp = FastMCP("Crypto-Trading-Skills")

# 1. Market Data
from skills.market_data.ccxt_fetcher import get_ohlcv, get_ticker, get_orderbook
from skills.market_data.coinglass_scraper import (
    get_coinglass_liquidation_heatmap,
    get_coinglass_ahr999,
    get_coinglass_altcoin_season,
    get_coinglass_mayer_multiple,
    get_coinglass_etf_flow,
    get_coinglass_grayscale_stats
)
from skills.market_data.dex_screener import (
    search_dex_pairs,
    get_dex_token_info
)

# 2. Derivatives
from skills.derivatives.multi_exchange import get_aggregated_funding_rate, get_aggregated_open_interest

# 3. MAX Exchange
from skills.max_exchange.max_public import get_max_tickers
from skills.max_exchange.max_private import get_max_accounts, get_max_orders

# 4. Market Intel
from skills.market_intel.fng_client import get_crypto_fear_and_greed_index
from skills.market_intel.blockchain_client import get_blockchain_btc_stats, get_btc_unconfirmed_tx
from skills.market_intel.news_client import get_latest_crypto_news
from skills.market_intel import fetch_reddit_sentiment, search_web_duckduckgo, fetch_trump_truth_posts, fetch_twitter_user_tweets

# 4b. Gold (tokenized gold price + macro drivers + composite briefing)
from skills.gold import get_gold_price, get_gold_macro_context, analyze_gold_market

# 5. Analytics
from skills.analytics import (
    run_backtest,
    save_strategy,
    list_strategies,
    run_backtest_on_saved_strategy,
    run_twitter_mention_backtest
)

# 6. Execution
from skills.execution.order_executor import create_order

# 7. Education (beginner-friendly, offline)
from skills.education import (
    explain_crypto_term,
    get_max_guide,
    get_beginner_safety_checklist,
    get_max_fee_info,
)

# 8. Calculators (pure, deterministic)
from skills.calculators import (
    calculate_dca,
    calculate_position_size,
    calculate_pnl,
    calculate_average_down,
    calculate_target_sell_price,
)

# ──────────────────────────────────────────────
#  1. Market Data Tools
# ──────────────────────────────────────────────

@mcp.tool()
def fetch_ohlcv(exchange_id: str, symbol: str, timeframe: str = "1h", limit: int = 50) -> str:
    """
    Get historical K-line data (OHLCV) for a given exchange and symbol.
    """
    data = get_ohlcv(exchange_id, symbol, timeframe, limit)
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def fetch_ticker(exchange_id: str, symbol: str) -> str:
    """
    Get the latest ticker/price info for a given exchange and symbol.
    """
    data = get_ticker(exchange_id, symbol)
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def fetch_orderbook(exchange_id: str, symbol: str, limit: int = 20) -> str:
    """
    Get the orderbook depth for a given exchange and symbol.
    """
    data = get_orderbook(exchange_id, symbol, limit)
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def fetch_coinglass_liquidation_heatmap(symbol: str, range: str = "3d") -> str:
    """
    Get CoinGlass liquidation heatmap/levels for a symbol (e.g. BTC, Bybit_BTCUSDT). range can be '3d', '7d', '30d'.
    """
    data = get_coinglass_liquidation_heatmap(symbol, range)
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def fetch_coinglass_ahr999() -> str:
    """
    Get Bitcoin AHR999 accumulation index data.
    """
    data = get_coinglass_ahr999()
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def fetch_coinglass_altcoin_season() -> str:
    """
    Get Altcoin Season Index historical data.
    """
    data = get_coinglass_altcoin_season()
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def fetch_coinglass_mayer_multiple() -> str:
    """
    Get Mayer Multiple index data.
    """
    data = get_coinglass_mayer_multiple()
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def fetch_coinglass_etf_flow() -> str:
    """
    Get US spot Bitcoin ETF daily flow details (USD).
    """
    data = get_coinglass_etf_flow()
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def fetch_coinglass_grayscale_stats() -> str:
    """
    Get Grayscale trust premiums and holdings.
    """
    data = get_coinglass_grayscale_stats()
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def execute_search_dex_pairs(query: str) -> str:
    """
    Search for DEX token pairs by query (name, symbol, or address).
    """
    data = search_dex_pairs(query)
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def execute_get_dex_token_info(token_address: str) -> str:
    """
    Get all DEX pairs for a specific token address.
    """
    data = get_dex_token_info(token_address)
    return json.dumps(data, ensure_ascii=False)

# ──────────────────────────────────────────────
#  2. Derivatives Tools
# ──────────────────────────────────────────────

@mcp.tool()
def fetch_aggregated_funding_rate(symbol: str) -> str:
    """
    Compare funding rates of Binance, Bybit, and OKX for a symbol (e.g. BTC) and analyze arbitrage.
    """
    data = get_aggregated_funding_rate(symbol)
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def fetch_aggregated_open_interest(symbol: str) -> str:
    """
    Compare contract open interest (OI) of Binance, Bybit, and OKX for a symbol.
    """
    data = get_aggregated_open_interest(symbol)
    return json.dumps(data, ensure_ascii=False)

# ──────────────────────────────────────────────
#  3. MAX Exchange Tools
# ──────────────────────────────────────────────

@mcp.tool()
def fetch_max_tickers(market: Optional[str] = None) -> str:
    """
    Get tickers for MAX exchange (all or specific market like BTC/TWD).
    """
    data = get_max_tickers(market)
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def fetch_max_accounts() -> str:
    """
    Get MAX exchange account balances (requires MAX_API_KEY and MAX_API_SECRET set in env).
    """
    data = get_max_accounts()
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def fetch_max_orders(market: Optional[str] = None, state: Optional[str] = None, limit: int = 20) -> str:
    """
    Get active/historical orders on MAX exchange. state can be 'wait', 'done', 'cancel'.
    """
    data = get_max_orders(market, state, limit)
    return json.dumps(data, ensure_ascii=False)

# ──────────────────────────────────────────────
#  4. Market Intel Tools
# ──────────────────────────────────────────────

@mcp.tool()
def fetch_crypto_fear_and_greed_index(limit: int = 1) -> str:
    """
    Get Crypto Fear and Greed Index data. limit defines historical days.
    """
    data = get_crypto_fear_and_greed_index(limit)
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def fetch_blockchain_btc_stats() -> str:
    """
    Get real-time Bitcoin blockchain network stats (hashrate, difficulty, etc).
    """
    data = get_blockchain_btc_stats()
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def fetch_btc_unconfirmed_tx() -> str:
    """
    Get the count of unconfirmed transactions in the Bitcoin mempool to assess congestion.
    """
    data = get_btc_unconfirmed_tx()
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def fetch_latest_crypto_news(limit: int = 5) -> str:
    """
    Get the latest live crypto news headlines and summaries from CoinTelegraph.
    """
    data = get_latest_crypto_news(limit)
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def execute_fetch_reddit_sentiment(query: str, limit: int = 5) -> str:
    """
    Fetch raw Reddit cryptocurrency search posts related to a symbol.
    """
    data = fetch_reddit_sentiment(query, limit)
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def execute_web_search(query: str, max_results: int = 5) -> str:
    """
    Perform a keyless web search query on DuckDuckGo and return titles, links and snippets.
    """
    data = search_web_duckduckgo(query, max_results)
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def execute_fetch_trump_truth_posts(limit: int = 5) -> str:
    """
    Fetch Donald Trump's latest posts from Truth Social archives.
    """
    data = fetch_trump_truth_posts(limit)
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def execute_fetch_twitter_user_tweets(screen_name: str = "elonmusk", limit: int = 5) -> str:
    """
    Fetch X (Twitter) user profile tweets using public embed timeline endpoints.
    """
    data = fetch_twitter_user_tweets(screen_name, limit)
    return json.dumps(data, ensure_ascii=False)

# ──────────────────────────────────────────────
#  4b. Gold Tools (tokenized gold + macro drivers + briefing)
# ──────────────────────────────────────────────

@mcp.tool()
def fetch_gold_price(vs_currency: str = "usd") -> str:
    """
    Get real-time tokenized gold prices (PAXG, XAUT) — each pegged to 1 troy oz of gold — with 24h change and the inter-token spread.
    """
    data = get_gold_price(vs_currency)
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def fetch_gold_macro_context() -> str:
    """
    Get gold's macro drivers (10y real yield, USD index, policy rate, CPI YoY, London gold fix) with per-driver gold impact. Requires a free FRED_API_KEY; degrades gracefully with a setup hint if absent.
    """
    data = get_gold_macro_context()
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def analyze_gold(exchange_id: str = "binance", tokenized_symbol: str = "PAXG/USDT", corr_days: int = 30) -> str:
    """
    Composite gold market briefing: tokenized price + macro regime + gold-vs-BTC rolling correlation + tokenized premium. Advisory only, never auto-trades.
    """
    data = analyze_gold_market(exchange_id, tokenized_symbol, corr_days)
    return json.dumps(data, ensure_ascii=False)

# ──────────────────────────────────────────────
#  5. Analytics Tools
# ──────────────────────────────────────────────

@mcp.tool()
def execute_backtest(klines: List[List[Any]], strategy_name: str = "ma_crossover", strategy_params: Optional[Dict[str, Any]] = None, initial_capital: float = 10000.0) -> str:
    """
    Execute strategy backtest on historical K-line array. strategy_name can be 'ma_crossover' or 'rsi_reversal'.
    """
    data = run_backtest(klines, strategy_name, strategy_params, initial_capital)
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def execute_save_strategy(name: str, strategy_type: str, params: Dict[str, Any], description: str = "", symbol: str = "BTC/USDT", timeframe: str = "1h") -> str:
    """
    Save or update custom strategy configurations. strategy_type can be 'ma_crossover' or 'rsi_reversal'.
    """
    data = save_strategy(name, strategy_type, params, description, symbol, timeframe)
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def execute_list_strategies() -> str:
    """
    List all saved custom trading strategies.
    """
    data = list_strategies()
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def execute_run_backtest_on_saved_strategy(name: str, exchange_id: str = "binance", limit: int = 150) -> str:
    """
    Load a saved strategy and run a backtest automatically using fetched historical prices.
    """
    data = run_backtest_on_saved_strategy(name, exchange_id, limit)
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def execute_run_twitter_mention_backtest(symbol: str, screen_name: str = "elonmusk", keywords: Optional[List[str]] = None, hold_hours: int = 24, exchange_id: str = "binance") -> str:
    """
    Run an event-driven backtest simulating buying whenever a user mentions a token on Twitter and holding for hold_hours.
    """
    data = run_twitter_mention_backtest(symbol, screen_name, keywords, hold_hours, exchange_id)
    return json.dumps(data, ensure_ascii=False)

# ──────────────────────────────────────────────
#  6. Execution Tools
# ──────────────────────────────────────────────

@mcp.tool()
def execute_create_order(exchange_id: str, market: str, side: str, volume: float, price: Optional[float] = None, ord_type: str = "limit") -> str:
    """
    Create a buy/sell spot order with built-in risk checks (wind guard).
    """
    data = create_order(exchange_id, market, side, volume, price, ord_type)
    return json.dumps(data, ensure_ascii=False)

# ──────────────────────────────────────────────
#  7. Education Tools (beginner-friendly, offline)
# ──────────────────────────────────────────────

@mcp.tool()
def explain_term(term: str) -> str:
    """
    Explain a crypto/trading term in plain Traditional Chinese (e.g. 現貨, 合約, 爆倉, 資金費率, 私鑰).
    """
    return json.dumps(explain_crypto_term(term), ensure_ascii=False)

@mcp.tool()
def max_guide(topic: Optional[str] = None) -> str:
    """
    Get a plain-language MAX exchange how-to guide. topic: 開戶/台幣入金/台幣出金/買幣/手續費/api金鑰/安全設定.
    """
    return json.dumps(get_max_guide(topic), ensure_ascii=False)

@mcp.tool()
def beginner_safety_checklist(category: Optional[str] = None) -> str:
    """
    Beginner anti-scam and safety checklist. category: 詐騙/資產安全/心態 (empty = all).
    """
    return json.dumps(get_beginner_safety_checklist(category), ensure_ascii=False)

@mcp.tool()
def max_fee_info() -> str:
    """
    Structured MAX exchange fee info (maker/taker, deposit/withdraw, MAX Token discount, ways to save).
    """
    return json.dumps(get_max_fee_info(), ensure_ascii=False)

# ──────────────────────────────────────────────
#  8. Calculator Tools (pure, deterministic)
# ──────────────────────────────────────────────

@mcp.tool()
def calc_dca(amount_per_period: float, prices: List[float], fee_rate: float = 0.001, current_price: Optional[float] = None) -> str:
    """
    Dollar-cost-averaging (DCA) backtest: accumulate units/avg cost over a list of buy prices, optionally vs current price.
    """
    return json.dumps(calculate_dca(amount_per_period, prices, fee_rate, current_price), ensure_ascii=False)

@mcp.tool()
def calc_position_size(account_balance: float, risk_pct: float, entry_price: float, stop_loss_price: float, fee_rate: float = 0.001) -> str:
    """
    Risk-based spot position sizing: how many units to buy given a max risk % and stop-loss.
    """
    return json.dumps(calculate_position_size(account_balance, risk_pct, entry_price, stop_loss_price, fee_rate), ensure_ascii=False)

@mcp.tool()
def calc_pnl(entry_price: float, exit_price: float, volume: float, side: str = "buy", fee_rate: float = 0.001) -> str:
    """
    Compute trade PnL, ROI and breakeven price including round-trip fees.
    """
    return json.dumps(calculate_pnl(entry_price, exit_price, volume, side, fee_rate), ensure_ascii=False)

@mcp.tool()
def calc_average_down(current_units: float, current_avg_cost: float, add_price: float, add_amount: Optional[float] = None, add_units: Optional[float] = None, fee_rate: float = 0.001) -> str:
    """
    New average cost after adding to a position (provide add_amount or add_units).
    """
    return json.dumps(calculate_average_down(current_units, current_avg_cost, add_price, add_amount, add_units, fee_rate), ensure_ascii=False)

@mcp.tool()
def calc_target_sell_price(entry_price: float, target_net_roi_pct: float, fee_rate: float = 0.001) -> str:
    """
    Sell price needed to reach a target NET ROI (after round-trip fees).
    """
    return json.dumps(calculate_target_sell_price(entry_price, target_net_roi_pct, fee_rate), ensure_ascii=False)

if __name__ == "__main__":
    mcp.run()

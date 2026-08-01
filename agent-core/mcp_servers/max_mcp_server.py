"""
mcp_servers/max_mcp_server.py — MAX Exchange MCP Server（FastMCP）
=====================================================
把我們的旗艦工具（MAX 交易所 / 鏈上聰明錢 / AML 入金溯源 / 量化回測 / 社群背離）
開成標準 MCP 工具。定義一次、協定自動發現——解決我們「加工具要改 3 個地方」的痛，
同時是可對外開放的獨立作品，且符合 AgentCore Runtime 跑 MCP server 的合約。

wrapper 皆薄封裝，直接複用 skills/ 內既有函式與其文件字串（FastMCP 由型別+docstring
自動產生工具 schema）；工具名與原生同名，方便主 agent「吃自己的狗糧」經 MCP 呼叫。

執行：
  本地 stdio（給 Claude Desktop / 主 agent client 測）：
      .venv/bin/python -m mcp_servers.max_mcp_server
  遠端 streamable-http（AgentCore Runtime / 遠端 client，開 0.0.0.0:8000/mcp）：
      MCP_TRANSPORT=http .venv/bin/python -m mcp_servers.max_mcp_server
"""
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("MAX Exchange Trading Copilot")


# ── 行情 / 帳戶（部分需 MAX_API_KEY）───────────────────────────
@mcp.tool()
def get_max_tickers(market: str = "BTC/TWD") -> dict:
    """查 MAX 交易所某交易對的最新報價（last/buy/sell/vol）。market 如 'BTC/TWD'、'ETH/TWD'。"""
    from skills.max_exchange.max_public import get_max_tickers as _f
    return _f(market)


@mcp.tool()
def get_max_currencies(currency: Optional[str] = None) -> dict:
    """MAX 幣種資訊：可否質押/融資、各鏈提幣手續費/最低量/是否需 memo/存提狀態。帶 currency 查單一幣（如 'USDT'）。"""
    from skills.max_exchange.max_public import get_max_currencies as _f
    return _f(currency)


@mcp.tool()
def get_max_accounts(wallet_type: str = "spot") -> list:
    """【需授權】MAX 錢包餘額（可用/鎖定/質押/總額）。wallet_type：'spot' 現貨 或 'm' 融資。"""
    from skills.max_exchange.max_private import get_max_accounts as _f
    return _f(wallet_type)


@mcp.tool()
def get_max_member_info() -> dict:
    """【需授權】MAX 會員資訊：明確區分身份驗證等級(account_kyc_level)與 VIP 交易等級(vip_tier，決定手續費)，含 maker/taker 費率與升級門檻。"""
    from skills.max_exchange.max_private import get_max_member_info as _f
    return _f()


# ── 鏈上聰明錢 + 訊號驗證 + 一鍵盡職調查 ───────────────────────
@mcp.tool()
def get_smart_money_flow(query: str) -> dict:
    """查某代幣的鏈上資金流/買賣壓（看行動而非嘴巴）：DEX 聚合買賣筆數+量能，調和 6h/24h 標記背離。query 為代幣符號/名稱/合約地址。"""
    from skills.market_data.onchain_flow import get_smart_money_flow as _f
    return _f(query)


@mcp.tool()
def validate_smart_money_signal(token: str, hold_days: int = 5) -> dict:
    """驗證某代幣資金流入訊號的歷史有效性 → 分辨真訊號 vs 噪音：以歷史量能激增日做事件研究，看之後是否顯著上漲。需該幣在主流交易所有日線。"""
    from skills.market_data.onchain_flow import validate_smart_money_signal as _f
    return _f(token, hold_days=hold_days)


@mcp.tool()
def run_token_due_diligence(token: str, hold_days: int = 5) -> dict:
    """對某代幣一鍵盡職調查：整合當下買賣壓 + 訊號歷史有效性 + 基本面風險旗標（流動性/FDV/是否噪音），進場前避免追坑。"""
    from skills.market_data.onchain_flow import run_token_due_diligence as _f
    return _f(token, hold_days=hold_days)


# ── AML 入金來源溯源 ─────────────────────────────────────────
@mcp.tool()
def trace_deposit_source(limit: int = 10) -> dict:
    """【需授權】調查近期入金的鏈上來源：對站外加密入金用 txid 上鏈查發送地址+具名交易所標籤（如『來自 Binance』）/🚩新錢包 → 辨識來路不明資金。支援 EVM/Solana/Tron/BTC。"""
    from skills.market_data.chain_trace import trace_deposit_source as _f
    return _f(limit)


# ── 量化回測 + 社群背離 ──────────────────────────────────────
@mcp.tool()
def run_signal_backtest(signal: str, asset: str = "BTC", hold_days: int = 7) -> dict:
    """事件研究式回測：某訊號出現後 asset 之後 hold_days 天的異常報酬與統計顯著性。signal 如 'rsi_oversold'、'golden_cross'。"""
    from skills.analytics.event_study import run_signal_backtest as _f
    return _f(signal, asset=asset, hold_days=hold_days)


@mcp.tool()
def analyze_sentiment_divergence(asset: str = "BTC") -> dict:
    """比較菁英（川普/馬斯克事件訊號）vs 群眾（Reddit/新聞量化＋恐貪指數）對某資產的情緒，算背離度與解讀（背離常是反向/領先訊號）。"""
    from skills.market_intel.social_analysis import analyze_sentiment_divergence as _f
    return _f(asset)


def main() -> None:
    transport = os.getenv("MCP_TRANSPORT", "stdio").strip().lower()
    if transport in ("http", "streamable-http", "streamable_http"):
        mcp.settings.host = os.getenv("MCP_HOST", "0.0.0.0")
        mcp.settings.port = int(os.getenv("MCP_PORT", "8000"))
        mcp.run(transport="streamable-http")     # AgentCore Runtime 合約：0.0.0.0:8000/mcp
    else:
        mcp.run(transport="stdio")               # 本地 / Claude Desktop / 主 agent client


if __name__ == "__main__":
    main()

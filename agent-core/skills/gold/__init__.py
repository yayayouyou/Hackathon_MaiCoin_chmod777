"""
skills/gold/ — 黃金資料層 (Gold Data Layer)
===========================================
MAX 即將上線黃金交易對前的分析基礎。三塊互補：

  1) tokenized_gold — 代幣化黃金 PAXG / XAUT 即時報價（CoinGecko，免額外 Key）。
     這是「把黃金當加密資產交易」的最貼近路徑，與現有 BTC/ETH 工具同一套。
  2) macro          — 黃金總經驅動（FRED 為主：實質利率 / 美元指數 / CPI / 政策利率 /
     倫敦金定盤；Alpha Vantage 為輔）。回答「黃金為什麼漲跌」。需免費 Key，缺 Key 優雅降級。
  3) gold_analysis  — 綜合簡報：代幣化報價 + 總經脈絡 + 黃金vs BTC 滾動相關性 +
     代幣化溢價，產出結構化「黃金體制」判讀。僅供佐證、不自動下單。
"""
from skills.gold.tokenized_gold import get_gold_price
from skills.gold.macro import get_gold_macro_context
from skills.gold.gold_analysis import analyze_gold_market

__all__ = ["get_gold_price", "get_gold_macro_context", "analyze_gold_market"]

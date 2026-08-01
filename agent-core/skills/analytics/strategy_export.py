"""
skills/analytics/strategy_export.py — 策略匯出（TradingView Pine Script v6 / CSV）
=====================================================
把本專案內建的回測策略（雙均線交叉、RSI 逆勢）一鍵匯出成：
  - TradingView **Pine Script v6**：可直接貼到 TradingView 圖表驗證/掛單。
  - **CSV**：把某次回測的交易明細匯出成試算表，便於離線分析。

策略邏輯與 skills/analytics/backtester.py 的 run_backtest 對齊：
  - ma_crossover：快均線上穿慢均線做多，下穿平倉。
  - rsi_reversal：RSI 跌破 oversold 進場做多，突破 overbought 平倉。
注意：Pine 的 strategy.entry 預設「次一根開盤成交」，與我們修正後的回測（次一根 open）一致。
"""

import csv
import io
from typing import Dict, Any, List


def to_pine_script(strategy_name: str, params: Dict[str, Any] = None, symbol: str = "BTC/USDT") -> str:
    """產生 TradingView Pine Script v6 策略碼字串。未知策略回傳註解說明。"""
    p = params or {}
    sym = symbol.replace("/", "")

    if strategy_name == "ma_crossover":
        fast = int(p.get("fast_period", 10))
        slow = int(p.get("slow_period", 30))
        return f'''//@version=6
// MAIA 匯出 — 雙均線交叉策略 ({symbol})
strategy("MAIA MA Crossover {sym}", overlay=true, initial_capital=10000,
         default_qty_type=strategy.percent_of_equity, default_qty_value=100,
         commission_type=strategy.commission.percent, commission_value=0.1)

fastLen = input.int({fast}, "快均線週期")
slowLen = input.int({slow}, "慢均線週期")

fastMA = ta.sma(close, fastLen)
slowMA = ta.sma(close, slowLen)
plot(fastMA, "Fast MA", color=color.aqua)
plot(slowMA, "Slow MA", color=color.orange)

// 快線上穿慢線 → 做多；下穿 → 平倉（次一根開盤成交，杜絕前視）
if ta.crossover(fastMA, slowMA)
    strategy.entry("Long", strategy.long)
if ta.crossunder(fastMA, slowMA)
    strategy.close("Long")
'''

    if strategy_name == "rsi_reversal":
        rsi_len = int(p.get("rsi_period", 14))
        oversold = int(p.get("oversold", 30))
        overbought = int(p.get("overbought", 70))
        return f'''//@version=6
// MAIA 匯出 — RSI 逆勢超買超賣策略 ({symbol})
strategy("MAIA RSI Reversal {sym}", overlay=false, initial_capital=10000,
         default_qty_type=strategy.percent_of_equity, default_qty_value=100,
         commission_type=strategy.commission.percent, commission_value=0.1)

rsiLen = input.int({rsi_len}, "RSI 週期")
osLevel = input.int({oversold}, "超賣門檻")
obLevel = input.int({overbought}, "超買門檻")

r = ta.rsi(close, rsiLen)
plot(r, "RSI", color=color.purple)
hline(obLevel, "超買", color=color.red)
hline(osLevel, "超賣", color=color.green)

// RSI 跌破超賣 → 做多；突破超買 → 平倉
if ta.crossunder(r, osLevel)
    strategy.entry("Long", strategy.long)
if ta.crossover(r, obLevel)
    strategy.close("Long")
'''

    return f'// 無法匯出：未知策略 "{strategy_name}"（目前支援 ma_crossover / rsi_reversal）'


def backtest_to_csv(backtest_result: Dict[str, Any]) -> str:
    """把一次 run_backtest 的交易明細（recent_trades）匯出成 CSV 字串。"""
    trades: List[Dict[str, Any]] = backtest_result.get("recent_trades", []) or []
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["buy_time", "buy_price", "sell_time", "sell_price", "pnl_usd", "pnl_pct"])
    for t in trades:
        writer.writerow([
            t.get("buy_time", ""), t.get("buy_price", ""),
            t.get("sell_time", ""), t.get("sell_price", ""),
            round(float(t.get("pnl_usd", 0) or 0), 2),
            round(float(t.get("pnl_pct", 0) or 0), 3),
        ])
    return buf.getvalue()


def export_strategy(strategy_name: str, params: Dict[str, Any] = None,
                    fmt: str = "pine", symbol: str = "BTC/USDT",
                    backtest_result: Dict[str, Any] = None) -> Dict[str, Any]:
    """【LLM Tool / API】統一匯出入口。fmt='pine' 回傳 Pine Script；fmt='csv' 回傳交易明細 CSV。"""
    fmt = (fmt or "pine").lower()
    sym = symbol.replace("/", "").lower()
    if fmt == "csv":
        if not backtest_result:
            return {"error": "CSV 匯出需要提供 backtest_result（先跑一次回測）。"}
        return {"format": "csv", "filename": f"maia_{strategy_name}_{sym}_trades.csv",
                "content": backtest_to_csv(backtest_result)}
    if fmt == "pine":
        return {"format": "pine", "filename": f"maia_{strategy_name}_{sym}.pine",
                "content": to_pine_script(strategy_name, params, symbol)}
    return {"error": f"不支援的匯出格式 '{fmt}'（可選 pine / csv）。"}

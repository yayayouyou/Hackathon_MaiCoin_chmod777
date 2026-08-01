"""
skills/derivatives/multi_exchange.py

跨交易所衍生品數據聚合與套利分析引擎
=============================================
提供以下 LLM Tool 函數：
  - get_aggregated_funding_rate : 跨交易所資金費率聚合與套利分析
  - get_aggregated_open_interest : 跨交易所持倉量對比
"""

from typing import Dict, Any, List
from loguru import logger

from skills.derivatives.binance_futures import get_binance_funding_rate, get_binance_open_interest
from skills.derivatives.bybit_derivatives import get_bybit_funding_rate, get_bybit_open_interest_history
from skills.derivatives.okx_derivatives import get_okx_funding_rate, get_okx_open_interest

def get_aggregated_funding_rate(symbol: str = "BTC/USDT") -> Dict[str, Any]:
    """
    【LLM Tool】獲取並對比多個交易所（Binance, Bybit, OKX）的最新資金費率，並分析套利機會與市場情緒。
    symbol 未指定時預設 BTC/USDT（避免模型漏傳參數導致整個工具失敗）。
    """
    symbol = symbol or "BTC/USDT"   # 容錯：模型有時傳 None / 空字串
    results = {}
    errors = {}

    # 1. 抓取 Binance
    try:
        results["Binance"] = get_binance_funding_rate(symbol, limit=5)
    except Exception as e:
        logger.warning(f"聚合獲取 Binance 資金費率失敗: {e}")
        errors["Binance"] = str(e)

    # 2. 抓取 Bybit
    try:
        results["Bybit"] = get_bybit_funding_rate(symbol, limit=5)
    except Exception as e:
        logger.warning(f"聚合獲取 Bybit 資金費率失敗: {e}")
        errors["Bybit"] = str(e)

    # 3. 抓取 OKX
    try:
        results["OKX"] = get_okx_funding_rate(symbol, limit=5)
    except Exception as e:
        logger.warning(f"聚合獲取 OKX 資金費率失敗: {e}")
        errors["OKX"] = str(e)

    # 處理沒有任何數據的情況
    if not results:
        return {
            "symbol": symbol,
            "error": "無法從任何交易所獲取資金費率數據",
            "details": errors
        }

    # 4. 進行數據聚合與分析
    by_exchange = {}
    valid_rates = []
    
    for ex_name, ex_data in results.items():
        if "error" not in ex_data:
            rate = ex_data["latest_rate"]
            rate_pct = ex_data["latest_rate_pct"]
            by_exchange[ex_name] = {
                "latest_rate": rate,
                "latest_rate_pct": rate_pct,
                "avg_rate_pct": ex_data.get("avg_rate_pct", 0.0),
                "sentiment": ex_data.get("sentiment", "中性")
            }
            valid_rates.append((ex_name, rate))

    if not valid_rates:
        return {
            "symbol": symbol,
            "error": "獲取的數據皆無有效費率值",
            "details": errors
        }

    # 計算平均值、最大最小與價差 (Spread)
    avg_rate = sum(r[1] for r in valid_rates) / len(valid_rates)
    max_ex, max_val = max(valid_rates, key=lambda x: x[1])
    min_ex, min_val = min(valid_rates, key=lambda x: x[1])
    spread = max_val - min_val

    # 套利機會分析
    arbitrage_opp = "無明顯套利空間"
    # 一般資金費率每期 (8h) 超過 0.01% (即 0.0001) 或交易所間價差大於 0.00005 (0.005%) 就可以考慮套利
    if len(valid_rates) >= 2 and spread > 0.00005:
        arbitrage_opp = f"存在潛在跨所套利機會！建議在 {min_ex} 做多（費率較低/可收取資金費），同時在 {max_ex} 做空（費率較高/可收取資金費），賺取約 {spread * 100:.4f}% 的費率差。"

    # 綜合情緒分析
    if avg_rate > 0.0002:
        market_sentiment = "多頭情緒過熱 (高費率，多頭持續支付空頭費率)"
    elif avg_rate > 0.00005:
        market_sentiment = "多頭情緒溫和"
    elif avg_rate < -0.0002:
        market_sentiment = "空頭情緒過熱 (負費率，空頭持續支付多頭費率)"
    elif avg_rate < -0.00005:
        market_sentiment = "空頭情緒溫和"
    else:
        market_sentiment = "市場情緒中性 (多空費率均衡)"

    return {
        "symbol": symbol,
        "aggregated": {
            "avg_rate": avg_rate,
            "avg_rate_pct": avg_rate * 100,
            "max_rate": {"exchange": max_ex, "rate": max_val, "rate_pct": max_val * 100},
            "min_rate": {"exchange": min_ex, "rate": min_val, "rate_pct": min_val * 100},
            "spread": spread,
            "spread_pct": spread * 100,
            "consensus_sentiment": market_sentiment,
            "arbitrage_opportunity": arbitrage_opp
        },
        "by_exchange": by_exchange,
        "errors": errors if errors else None
    }

def get_aggregated_open_interest(symbol: str = "BTC/USDT") -> Dict[str, Any]:
    """
    【LLM Tool】獲取並對比多個交易所的即時持倉量 (Open Interest)。
    symbol 未指定時預設 BTC/USDT（避免模型漏傳參數導致整個工具失敗）。
    """
    symbol = symbol or "BTC/USDT"   # 容錯：模型有時傳 None / 空字串
    results = {}
    errors = {}

    # 1. 抓取 Binance 即時持倉
    try:
        results["Binance"] = get_binance_open_interest(symbol)
    except Exception as e:
        logger.warning(f"聚合獲取 Binance 持倉失敗: {e}")
        errors["Binance"] = str(e)

    # 2. 抓取 Bybit 持倉 (使用歷史持倉獲取最新的一筆作爲即時值)
    try:
        bybit_hist = get_bybit_open_interest_history(symbol, limit=1)
        if "error" not in bybit_hist:
            results["Bybit"] = {
                "open_interest": bybit_hist["latest_oi"],
                "timestamp": bybit_hist["history"][-1]["timestamp"] if bybit_hist.get("history") else None
            }
        else:
            results["Bybit"] = bybit_hist
    except Exception as e:
        logger.warning(f"聚合獲取 Bybit 持倉失敗: {e}")
        errors["Bybit"] = str(e)

    # 3. 抓取 OKX 即時持倉
    try:
        results["OKX"] = get_okx_open_interest(symbol)
    except Exception as e:
        logger.warning(f"聚合獲取 OKX 持倉失敗: {e}")
        errors["OKX"] = str(e)

    # 彙整輸出
    by_exchange = {}
    for ex_name, ex_data in results.items():
        if "error" not in ex_data:
            by_exchange[ex_name] = {
                "open_interest": ex_data["open_interest"],
                "unit": ex_data.get("open_interest_ccy", symbol.split("/")[0])
            }
        else:
            by_exchange[ex_name] = {"error": ex_data["error"]}

    return {
        "symbol": symbol,
        "by_exchange": by_exchange,
        "errors": errors if errors else None,
        "note": "注意：不同交易所的持倉量單位可能有所不同（合約張數 vs 基礎貨幣數量），請根據單位進行判斷。"
    }

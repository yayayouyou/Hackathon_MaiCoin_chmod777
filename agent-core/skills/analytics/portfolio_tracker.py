"""
skills/analytics/portfolio_tracker.py

投資組合追蹤器 (Portfolio Tracker)
=================================
追蹤與分析加密貨幣投資組合，計算多個資產間的皮爾森相關係數矩陣，
檢測是否過度集中並給出風險評估與調倉建議。
"""

import json
import pandas as pd
import numpy as np
from typing import List
from loguru import logger
from skills.market_data.ccxt_fetcher import get_ohlcv

def analyze_portfolio(symbols: List[str], timeframe: str = "1d") -> str:
    """
    【LLM Tool】追蹤與分析投資組合的相關性與集中度風險。
    """
    try:
        if not symbols or len(symbols) < 2:
            return json.dumps({"error": "請至少提供兩個交易對以分析投資組合相關性。"})
            
        prices_dict = {}
        limit = 30  # 抓取過去 30 天來算相關性
        
        for sym in symbols:
            # We use 'binance' by default for tracking correlation
            klines_json = get_ohlcv(exchange_id="binance", symbol=sym, timeframe=timeframe, limit=limit)
            if "error" in klines_json:
                logger.warning(f"無法獲取 {sym} 的資料，略過。")
                continue
                
            candles = klines_json.get("candles", [])
            
            if not candles:
                continue
                
            # 提取收盤價
            df = pd.DataFrame(candles)
            df["close"] = pd.to_numeric(df["close"])
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df.set_index("timestamp", inplace=True)
            prices_dict[sym] = df["close"]
            
        if len(prices_dict) < 2:
            return json.dumps({"error": "成功獲取資料的交易對不足兩個，無法分析。"})
            
        # 建立價格矩陣並計算每日報酬率
        portfolio_df = pd.DataFrame(prices_dict)
        returns_df = portfolio_df.pct_change().dropna()
        
        # 計算相關性矩陣
        corr_matrix = returns_df.corr()
        
        # 尋找高相關配對
        high_corr_pairs = []
        for i in range(len(corr_matrix.columns)):
            for j in range(i+1, len(corr_matrix.columns)):
                sym1 = corr_matrix.columns[i]
                sym2 = corr_matrix.columns[j]
                corr_val = corr_matrix.iloc[i, j]
                
                if corr_val > 0.8:
                    high_corr_pairs.append({
                        "pair": f"{sym1} & {sym2}",
                        "correlation": round(corr_val, 2),
                        "warning": "高度正相關，同漲同跌風險大"
                    })
                elif corr_val < -0.5:
                    high_corr_pairs.append({
                        "pair": f"{sym1} & {sym2}",
                        "correlation": round(corr_val, 2),
                        "warning": "顯著負相關，具備對沖效果"
                    })
                    
        # 計算投資組合的簡單歷史波動度 (年化)
        # 假設等權重
        weights = np.array([1.0/len(prices_dict)] * len(prices_dict))
        cov_matrix = returns_df.cov() * 365
        port_variance = np.dot(weights.T, np.dot(cov_matrix, weights))
        port_volatility = np.sqrt(port_variance)
        
        advice = "投資組合配置健康。"
        if high_corr_pairs:
            advice = "發現高度相關的資產對，您的投資組合可能缺乏多樣性 (Diversification)。建議考慮減少其中一個資產的比重，或加入具備負相關性的資產。"
        
        result = {
            "analyzed_symbols": list(prices_dict.keys()),
            "timeframe": timeframe,
            "annualized_volatility_pct": round(port_volatility * 100, 2),
            "correlation_matrix": corr_matrix.round(2).to_dict(),
            "high_correlation_alerts": high_corr_pairs,
            "rebalancing_advice": advice
        }
        
        return json.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"投資組合分析失敗: {e}")
        return json.dumps({"error": f"投資組合分析失敗: {e}"}, ensure_ascii=False)

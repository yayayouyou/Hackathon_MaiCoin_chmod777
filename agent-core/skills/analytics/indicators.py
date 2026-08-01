"""
skills/analytics/indicators.py

技術指標分析模組 — 基於 ta (Technical Analysis Library) 庫
=====================================================
提供以下計算函數：
  - calculate_indicators : 傳入 K 線數據，計算 MA, EMA, RSI, MACD, BB, ATR 等，並給出多空信號診斷。
"""

import pandas as pd
import ta
from typing import List, Dict, Any, Union
from loguru import logger

def calculate_indicators(klines: List[List[Any]]) -> Dict[str, Any]:
    """
    【LLM Tool】傳入 K 線列表數據，計算常用的技術指標，並產出綜合行情分析信號。
    
    Args:
        klines: K 線列表，格式為 [[timestamp, open, high, low, close, volume], ...]
                至少需要 30 根 K 線才能準確計算 RSI(14) 與 MACD(12, 26, 9) 等。
    """
    if not isinstance(klines, list) or len(klines) < 30:
        return {"error": "計算失敗。需要至少 30 根 K 線數據以計算技術指標。"}

    try:
        # 1. 建立 Pandas DataFrame
        df = pd.DataFrame(klines, columns=["timestamp", "open", "high", "low", "close", "volume"])
        
        # 2. 轉換為數值型態
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col])
        
        # 3. 計算技術指標
        # 趨勢指標：SMA, EMA
        df["sma_20"] = df["close"].rolling(window=20).mean()
        try:
            df["ema_10"] = ta.trend.ema_indicator(df["close"], window=10)
            df["ema_30"] = ta.trend.ema_indicator(df["close"], window=30)
        except TypeError:
            df["ema_10"] = ta.trend.ema_indicator(df["close"], n=10)
            df["ema_30"] = ta.trend.ema_indicator(df["close"], n=30)
        
        # 動量指標：RSI
        try:
            df["rsi_14"] = ta.momentum.rsi(df["close"], window=14)
        except TypeError:
            df["rsi_14"] = ta.momentum.rsi(df["close"], n=14)
        
        # 趨勢指標：MACD
        try:
            df["macd_line"] = ta.trend.macd(df["close"], window_fast=12, window_slow=26)
            df["macd_signal"] = ta.trend.macd_signal(df["close"], window_fast=12, window_slow=26, window_sign=9)
            df["macd_diff"] = ta.trend.macd_diff(df["close"], window_fast=12, window_slow=26, window_sign=9)
        except TypeError:
            df["macd_line"] = ta.trend.macd(df["close"], n_fast=12, n_slow=26)
            df["macd_signal"] = ta.trend.macd_signal(df["close"], n_fast=12, n_slow=26, n_sign=9)
            df["macd_diff"] = ta.trend.macd_diff(df["close"], n_fast=12, n_slow=26, n_sign=9)
        
        # 波動度指標：布林通道 (Bollinger Bands)
        try:
            df["bb_high"] = ta.volatility.bollinger_hband(df["close"], window=20, window_dev=2)
            df["bb_low"] = ta.volatility.bollinger_lband(df["close"], window=20, window_dev=2)
            df["bb_mid"] = ta.volatility.bollinger_mavg(df["close"], window=20)
        except TypeError:
            df["bb_high"] = ta.volatility.bollinger_hband(df["close"], n=20, ndev=2)
            df["bb_low"] = ta.volatility.bollinger_lband(df["close"], n=20, ndev=2)
            df["bb_mid"] = ta.volatility.bollinger_mavg(df["close"], n=20)
        
        # 波動度指標：真實波幅均值 (ATR)
        try:
            df["atr_14"] = ta.volatility.average_true_range(df["high"], df["low"], df["close"], window=14)
        except TypeError:
            df["atr_14"] = ta.volatility.average_true_range(df["high"], df["low"], df["close"], n=14)
        
        # 4. 取得最新一根 K 線的指標數值 (最後一筆)
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        latest_price = float(latest["close"])
        
        # RSI 診斷
        rsi_val = float(latest["rsi_14"])
        if rsi_val > 70:
            rsi_signal = "超買 (Overbought - 預警回调)"
        elif rsi_val < 30:
            rsi_signal = "超賣 (Oversold - 預警反彈)"
        else:
            rsi_signal = "中性 (Neutral)"
            
        # MACD 交叉診斷
        macd_line = float(latest["macd_line"])
        macd_sig = float(latest["macd_signal"])
        prev_macd_line = float(prev["macd_line"])
        prev_macd_sig = float(prev["macd_signal"])
        
        if macd_line > macd_sig and prev_macd_line <= prev_macd_sig:
            macd_signal = "黃金交叉 (Golden Cross - 看漲)"
        elif macd_line < macd_sig and prev_macd_line >= prev_macd_sig:
            macd_signal = "死亡交叉 (Death Cross - 看跌)"
        else:
            macd_signal = "無交叉 (多頭)" if macd_line > macd_sig else "無交叉 (空頭)"
            
        # 均線排列 (EMA 10 & EMA 30)
        ema_10 = float(latest["ema_10"])
        ema_30 = float(latest["ema_30"])
        if ema_10 > ema_30:
            ma_trend = "多頭排列 (EMA10 > EMA30 - 看漲)"
        else:
            ma_trend = "空頭排列 (EMA10 < EMA30 - 看跌)"
            
        # 布林通道位置
        bb_high = float(latest["bb_high"])
        bb_low = float(latest["bb_low"])
        bb_mid = float(latest["bb_mid"])
        if latest_price >= bb_high:
            bb_position = "觸碰上軌 (超買臨界/強勢看漲力道)"
        elif latest_price <= bb_low:
            bb_position = "觸碰下軌 (超賣臨界/強勢看跌力道)"
        else:
            bb_pct = (latest_price - bb_low) / (bb_high - bb_low) * 100 if (bb_high - bb_low) > 0 else 50.0
            bb_position = f"通道內部 (常態區間，距下軌 {bb_pct:.1f}%)"

        # 整理輸出
        return {
            "latest_values": {
                "price": latest_price,
                "sma_20": float(latest["sma_20"]),
                "ema_10": ema_10,
                "ema_30": ema_30,
                "rsi_14": rsi_val,
                "macd": {
                    "macd_line": macd_line,
                    "signal_line": macd_sig,
                    "histogram": float(latest["macd_diff"])
                },
                "bollinger_bands": {
                    "upper": bb_high,
                    "middle": bb_mid,
                    "lower": bb_low
                },
                "atr_14": float(latest["atr_14"])
            },
            "signals": {
                "rsi_diagnostic": rsi_signal,
                "macd_crossover": macd_signal,
                "moving_average_trend": ma_trend,
                "bollinger_position": bb_position
            },
            "note": "指標計算基於傳入的歷史 K 線，信號僅供大腦決策參考，不構成直接投資建議。"
        }
    except Exception as e:
        logger.error(f"技術指標計算失敗: {e}")
        return {"error": f"指標計算過程中發生異常: {str(e)}"}

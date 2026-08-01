"""
skills/analytics/regime_detector.py

市場體制偵測器 (Market Regime Detector)
=======================================
結合 CCXT 歷史 K 線與 TA 指標，判斷目前的市場狀態。
分類：
- Bullish Trend (牛市)
- Bearish Trend (熊市)
- Sideways/Range (震盪盤整)
- High Volatility/Extreme (極端波動)
"""

import json
from loguru import logger
from skills.market_data.ccxt_fetcher import get_ohlcv
from skills.analytics.indicators import calculate_indicators

def detect_market_regime(symbol: str, timeframe: str = "1d", exchange_id: str = "binance") -> str:
    """
    【LLM Tool】分析資產當前的市場體制 (Market Regime)。
    """
    try:
        # 獲取歷史 K 線，為了均線至少需要 200 根以上
        limit = 250
        klines_json = get_ohlcv(symbol=symbol, timeframe=timeframe, limit=limit, exchange_id=exchange_id)
        
        if "error" in klines_json:
            return json.dumps(klines_json)
            
        candles = klines_json.get("candles", [])
        
        if len(candles) < 200:
            return json.dumps({"error": f"資料筆數不足以判斷體制，需要至少 200 根 K 線，目前只有 {len(candles)} 根。"})
            
        # 轉換為 [[timestamp, open, high, low, close, volume], ...]
        klines = [
            [c["timestamp"], c["open"], c["high"], c["low"], c["close"], c["volume"]]
            for c in candles
        ]
        
        # 計算基礎指標 (EMA 10, EMA 30, RSI 14, ATR 14)
        indicators_res = calculate_indicators(klines)
        if "error" in indicators_res:
            return json.dumps(indicators_res)
            
        latest_vals = indicators_res["latest_values"]
        price = latest_vals["price"]
        ema_10 = latest_vals["ema_10"]
        ema_30 = latest_vals["ema_30"]
        rsi = latest_vals["rsi_14"]
        atr = latest_vals["atr_14"]
        
        # 計算 SMA 200 以判斷長期趨勢
        import pandas as pd
        df = pd.DataFrame(klines, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["close"] = pd.to_numeric(df["close"])
        sma_200 = df["close"].rolling(window=200).mean().iloc[-1]
        
        # 波動率特徵化 (ATR / Price)
        volatility_ratio = (atr / price) * 100
        
        # 判斷邏輯
        regime = "Unknown"
        advice = ""
        
        # 1. 先看是否為極端波動
        if volatility_ratio > 5.0 and (rsi > 80 or rsi < 20):
            regime = "High Volatility / Extreme (極端波動/超買賣)"
            advice = "市場處於極端狀態，風險極高。建議：觀望、減低槓桿或平倉。"
        # 2. 判斷多空趨勢
        elif price > sma_200 and ema_10 > ema_30:
            if rsi > 70:
                regime = "Bullish Trend (牛市趨勢) - 但有超買風險"
                advice = "長期與短期均為多頭。建議：持有或順勢做多，留意回調點。切勿逆勢做空。"
            else:
                regime = "Bullish Trend (牛市趨勢)"
                advice = "市場多頭排列，動能健康。建議：尋找支撐位做多 (Buy the dip)。"
        elif price < sma_200 and ema_10 < ema_30:
            if rsi < 30:
                regime = "Bearish Trend (熊市趨勢) - 但有超賣反彈機會"
                advice = "長期與短期均為空頭。建議：反彈逢高做空，不要輕易抄底。"
            else:
                regime = "Bearish Trend (熊市趨勢)"
                advice = "市場空頭排列。建議：順勢做空或觀望。"
        # 3. 震盪盤整
        else:
            regime = "Sideways / Range (震盪盤整)"
            advice = "趨勢不明確（價格可能穿梭於長短均線之間）。建議：採取網格交易策略或高拋低吸，避免盲目追高殺跌。"
            
        result = {
            "symbol": symbol,
            "timeframe": timeframe,
            "current_price": price,
            "volatility_ratio_pct": round(volatility_ratio, 2),
            "sma_200": float(sma_200),
            "ema_10": ema_10,
            "ema_30": ema_30,
            "rsi_14": rsi,
            "regime_detected": regime,
            "strategy_advice": advice
        }
        
        return json.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"市場體制偵測失敗: {e}")
        return json.dumps({"error": f"市場體制偵測失敗: {e}"}, ensure_ascii=False)

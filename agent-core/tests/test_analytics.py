"""
tests/test_analytics.py

技術分析與回測模組單元測試
=====================================
"""

import pytest
import numpy as np
from skills.analytics.indicators import calculate_indicators
from skills.analytics.backtester import run_backtest

# 產生虛擬 K 線數據：100 根，價格穩步上升，然後回調
def _generate_mock_klines(count: int = 100) -> list:
    klines = []
    base_time = 1700000000000
    price = 50000.0
    
    for i in range(count):
        # 模擬正弦波形價格波動
        wave = np.sin(i / 10.0) * 2000.0
        close_price = price + (i * 100.0) + wave
        open_price = close_price - 50.0
        high_price = max(open_price, close_price) + 100.0
        low_price = min(open_price, close_price) - 100.0
        vol = 10.0 + np.random.rand() * 5.0
        
        klines.append([
            base_time + (i * 3600000), # 每小時一根
            open_price,
            high_price,
            low_price,
            close_price,
            vol
        ])
    return klines

class TestAnalytics:
    def test_calculate_indicators_basic(self):
        klines = _generate_mock_klines(60)
        res = calculate_indicators(klines)
        
        assert "error" not in res
        assert "latest_values" in res
        assert "signals" in res
        
        latest = res["latest_values"]
        assert latest["sma_20"] > 0
        assert latest["rsi_14"] > 0
        assert latest["macd"]["macd_line"] is not None
        assert latest["bollinger_bands"]["upper"] > latest["bollinger_bands"]["lower"]
        assert latest["atr_14"] > 0

    def test_calculate_indicators_too_short(self):
        klines = _generate_mock_klines(20)
        res = calculate_indicators(klines)
        assert "error" in res
        assert "需要至少 30 根" in res["error"]

    def test_run_backtest_ma_crossover(self):
        klines = _generate_mock_klines(80)
        res = run_backtest(
            klines,
            strategy_name="ma_crossover",
            strategy_params={"fast_period": 5, "slow_period": 15},
            initial_capital=10000.0
        )
        
        assert "error" not in res
        assert res["strategy"] == "ma_crossover"
        assert "performance" in res
        assert res["performance"]["initial_capital_usd"] == 10000.0
        assert res["performance"]["final_value_usd"] > 0
        assert "win_rate_pct" in res["performance"]
        assert "max_drawdown_pct" in res["performance"]

    def test_run_backtest_rsi_reversal(self):
        klines = _generate_mock_klines(80)
        res = run_backtest(
            klines,
            strategy_name="rsi_reversal",
            strategy_params={"rsi_period": 14, "oversold": 40, "overbought": 60},
            initial_capital=10000.0
        )
        
        assert "error" not in res
        assert res["strategy"] == "rsi_reversal"
        assert "performance" in res
        assert res["performance"]["final_value_usd"] > 0

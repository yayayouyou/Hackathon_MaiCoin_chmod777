"""
tests/test_strategy_manager.py

交易策略持久化儲存與回測單元測試
==================================
"""

import os
import pytest
from skills.analytics.strategy_manager import (
    save_strategy,
    list_strategies,
    get_strategy,
    run_backtest_on_saved_strategy,
    STRATEGIES_FILE
)

@pytest.fixture(autouse=True)
def clean_strategies_file():
    """每個測試前後清理測試策略 JSON 文件以保證測試環境獨立"""
    # 備份原文件
    backup_file = STRATEGIES_FILE + ".bak"
    exists = os.path.exists(STRATEGIES_FILE)
    if exists:
        if os.path.exists(backup_file):
            os.remove(backup_file)
        os.rename(STRATEGIES_FILE, backup_file)
        
    yield
    
    # 恢復原文件
    if os.path.exists(STRATEGIES_FILE):
        os.remove(STRATEGIES_FILE)
    if exists and os.path.exists(backup_file):
        os.rename(backup_file, STRATEGIES_FILE)

def test_save_and_get_strategy():
    """測試保存與獲取策略配置"""
    res = save_strategy(
        name="test_ma",
        strategy_type="ma_crossover",
        params={"fast_period": 5, "slow_period": 20},
        description="測試用的均線策略",
        symbol="BTC/USDT",
        timeframe="1h"
    )
    
    assert res["status"] == "SUCCESS"
    assert res["strategy"]["name"] == "test_ma"
    assert res["strategy"]["params"]["fast_period"] == 5
    
    # 讀取剛才保存的策略
    strategy = get_strategy("test_ma")
    assert "error" not in strategy
    assert strategy["strategy_type"] == "ma_crossover"
    assert strategy["symbol"] == "BTC/USDT"

def test_list_strategies():
    """測試列出所有策略"""
    # 先保存兩個策略
    save_strategy("strat_1", "ma_crossover", {"fast_period": 10, "slow_period": 30})
    save_strategy("strat_2", "rsi_reversal", {"rsi_period": 14, "oversold": 30})
    
    strats = list_strategies()
    assert len(strats) == 2
    names = [s["name"] for s in strats]
    assert "strat_1" in names
    assert "strat_2" in names

def test_unsupported_strategy_type():
    """測試保存不支援的策略類型時返回錯誤"""
    res = save_strategy("invalid_strat", "arbitrary_type", {})
    assert "error" in res
    assert "不支援的策略類型" in res["error"]

def test_run_backtest_on_saved_strategy():
    """測試載入已保存策略並成功執行歷史數據回測"""
    # 儲存一個回測策略
    save_strategy(
        name="backtest_ma",
        strategy_type="ma_crossover",
        params={"fast_period": 5, "slow_period": 20},
        symbol="BTC/USDT",
        timeframe="1h"
    )
    
    # 在 Binance 執行回測，預設拉取 100 筆數據
    res = run_backtest_on_saved_strategy("backtest_ma", exchange_id="binance", limit=80)
    
    assert "performance" in res
    assert "error" not in res
    assert res["performance"]["total_trades"] >= 0
    assert "saved_strategy" in res
    assert res["saved_strategy"]["name"] == "backtest_ma"

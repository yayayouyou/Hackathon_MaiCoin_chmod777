"""
skills/analytics/strategy_manager.py

自定義策略存儲與管理模組 (Strategy Persistence & Management)
===========================================================
支持用戶保存自定義的均線或 RSI 策略配置，並能隨時載入運行歷史回測。
"""

import os
import json
import time
from typing import List, Dict, Any, Optional
from loguru import logger

from skills.analytics.backtester import run_backtest
from skills.market_data.ccxt_fetcher import get_ohlcv

# 策略持久化 JSON 儲存路徑
STRATEGIES_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 
    "strategies.json"
)

def _load_strategies_file() -> Dict[str, Any]:
    """讀取策略 JSON 存儲文件"""
    if not os.path.exists(STRATEGIES_FILE):
        return {}
    try:
        with open(STRATEGIES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"無法讀取策略文件: {e}")
        return {}

def _save_strategies_file(data: Dict[str, Any]) -> None:
    """寫入策略 JSON 存儲文件"""
    try:
        with open(STRATEGIES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"無法保存策略文件: {e}")

def save_strategy(
    name: str,
    strategy_type: str,
    params: Dict[str, Any],
    description: str = "",
    symbol: str = "BTC/USDT",
    timeframe: str = "1h"
) -> Dict[str, Any]:
    """
    【LLM Tool】保存或更新自定義的交易策略配置。
    
    Args:
        name: 策略名稱（唯一標識符，如 'my_rsi_strat'）
        strategy_type: 底層策略類型（可選: 'ma_crossover', 'rsi_reversal'）
        params: 策略參數 Dict（如雙均線週期、RSI 臨界值）
        description: 策略描述
        symbol: 預設交易對符號（如 'BTC/USDT'）
        timeframe: 預設時間週期（如 '1h'）
    """
    if strategy_type not in ["ma_crossover", "rsi_reversal"]:
        return {"error": f"不支援的策略類型: {strategy_type}。目前僅支持 'ma_crossover' 與 'rsi_reversal'"}
        
    data = _load_strategies_file()
    
    strategy = {
        "name": name,
        "strategy_type": strategy_type,
        "params": params,
        "description": description,
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "created_at": int(time.time())
    }
    
    data[name] = strategy
    _save_strategies_file(data)
    logger.info(f"成功保存自定義交易策略: {name} ({strategy_type})")
    
    return {"status": "SUCCESS", "message": f"策略 '{name}' 保存成功", "strategy": strategy}

def list_strategies() -> List[Dict[str, Any]]:
    """
    【LLM Tool】獲取所有已保存的自定義交易策略列表。
    """
    data = _load_strategies_file()
    return list(data.values())

def get_strategy(name: str) -> Dict[str, Any]:
    """
    【LLM Tool】獲取特定交易策略的詳細配置參數。
    """
    data = _load_strategies_file()
    if name not in data:
        return {"error": f"找不到名稱為 '{name}' 的策略"}
    return data[name]

def backtest_strategy(
    symbol: str = "BTC/USDT",
    strategy_name: str = "ma_crossover",
    strategy_params: Optional[Dict[str, Any]] = None,
    timeframe: str = "1d",
    limit: int = 120,
    exchange_id: str = "binance",
    initial_capital: float = 10000.0,
    fee_rate: float = 0.001,
) -> Dict[str, Any]:
    """
    【LLM Tool】一站式策略回測：只要給「交易對 + 策略」，系統自動抓 K 線並回測，
    你【不需要】先呼叫 get_ohlcv 再把整包 K 線陣列傳進來（那對模型很吃力、易逾時）。

    Args:
        symbol: 交易對，如 BTC/USDT、ETH/USDT
        strategy_name: 'ma_crossover' 或 'rsi_reversal'
        strategy_params: ma_crossover:{fast_period,slow_period}；rsi_reversal:{rsi_period,oversold,overbought}
        timeframe: K 線週期（1h/4h/1d…）；回測「過去三個月」建議 1d
        limit: 抓取 K 線根數（至少 30，建議 90~200）
    """
    from datetime import datetime, timezone
    try:
        klines = get_ohlcv(exchange_id=exchange_id, symbol=symbol, timeframe=timeframe, limit=limit)
    except Exception as e:  # noqa: BLE001
        return {"error": f"抓取 {symbol} K 線失敗: {e}"}
    if not klines or (isinstance(klines, dict) and "error" in klines):
        return {"error": f"抓取 {symbol} K 線失敗: {klines}"}
    raw_klines = []
    for c in klines.get("candles", []):
        try:
            dt = datetime.strptime(c["timestamp"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            raw_klines.append([int(dt.timestamp() * 1000), c["open"], c["high"], c["low"], c["close"], c["volume"]])
        except (KeyError, ValueError):
            continue
    if len(raw_klines) < 30:
        return {"error": f"僅取得 {len(raw_klines)} 根 K 線，回測至少需 30 根；請增大 limit 或改用較短 timeframe。"}
    res = run_backtest(klines=raw_klines, strategy_name=strategy_name,
                       strategy_params=strategy_params, initial_capital=initial_capital, fee_rate=fee_rate)
    if isinstance(res, dict) and "error" not in res:
        res["market"] = {"symbol": symbol, "timeframe": timeframe, "exchange": exchange_id, "bars": len(raw_klines)}
    return res


def run_backtest_on_saved_strategy(
    name: str,
    exchange_id: str = "binance",
    limit: int = 150
) -> Dict[str, Any]:
    """
    【LLM Tool】載入已保存的自定義策略配置，並自動抓取對應交易所最新行情數據執行回測。
    
    Args:
        name: 已保存的策略名稱
        exchange_id: 回測使用的交易所 ID (預設 'binance')
        limit: 獲取的歷史 K 線條數，預設 150
    """
    strategy = get_strategy(name)
    if "error" in strategy:
        return strategy
        
    symbol = strategy["symbol"]
    timeframe = strategy["timeframe"]
    strat_type = strategy["strategy_type"]
    params = strategy["params"]
    
    logger.info(f"載入自定義策略 '{name}'，正在獲取 {exchange_id} 上 {symbol} ({timeframe}) 的 {limit} 筆 K 線以執行回測...")
    
    try:
        # 1. 抓取行情數據
        klines = get_ohlcv(exchange_id=exchange_id, symbol=symbol, timeframe=timeframe, limit=limit)
        if not klines or (isinstance(klines, dict) and "error" in klines):
            return {"error": f"獲取行情數據失敗: {klines}"}
            
        # 將結構化 K 線轉換回 backtester 所期望的二維陣列格式
        from datetime import datetime, timezone
        raw_klines = []
        for c in klines.get("candles", []):
            dt = datetime.strptime(c["timestamp"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            ts_ms = int(dt.timestamp() * 1000)
            raw_klines.append([
                ts_ms,
                c["open"],
                c["high"],
                c["low"],
                c["close"],
                c["volume"]
            ])
            
        # 2. 執行回測
        backtest_res = run_backtest(
            klines=raw_klines,
            strategy_name=strat_type,
            strategy_params=params,
            initial_capital=10000.0
        )
        
        # 3. 附加自定義策略資訊
        if "error" not in backtest_res:
            backtest_res["saved_strategy"] = {
                "name": name,
                "description": strategy.get("description", ""),
                "symbol": symbol,
                "timeframe": timeframe
            }
        return backtest_res
        
    except Exception as e:
        logger.error(f"執行儲存策略回測失敗: {e}")
        return {"error": f"執行回測出錯: {str(e)}"}

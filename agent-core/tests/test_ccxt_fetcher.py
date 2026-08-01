"""
tests/test_ccxt_fetcher.py

CCXT 行情抓取模塊的單元測試
================================
測試策略：
  1. 公開 API 測試（無需 API Key）→ 直接對 Binance 真實 API 呼叫
  2. 參數驗證測試 → 確保無效輸入會拋出清楚的錯誤
  3. 輸出結構驗證 → 確保返回的 dict 欄位符合 LLM Schema 預期

注意：這些測試會發送真實 HTTP 請求，需要網路連線。
      如網路不通或交易所維護中，部分測試可能失敗。

執行方式：
    cd d:\\Skill_for_maicoin_agent
    python -m pytest tests/test_ccxt_fetcher.py -v
"""

import pytest
from skills.market_data.ccxt_fetcher import (
    get_ohlcv,
    get_ticker,
    get_orderbook,
    list_exchanges,
)


# ──────────────────────────────────────────────
#  基礎連線測試（公開 API，無需 Key）
# ──────────────────────────────────────────────

class TestGetOhlcv:
    """測試 get_ohlcv 函數"""

    def test_basic_btc_usdt(self):
        """正常情況：獲取 BTC/USDT 1小時 K 線"""
        result = get_ohlcv("binance", "BTC/USDT", timeframe="1h", limit=10)

        # 基本結構驗證
        assert result["exchange"] == "binance"
        assert result["symbol"]   == "BTC/USDT"
        assert result["timeframe"] == "1h"
        assert result["count"]    == 10
        assert len(result["candles"]) == 10

    def test_candle_structure(self):
        """驗證每根 K 線的欄位結構正確"""
        result = get_ohlcv("binance", "ETH/USDT", timeframe="4h", limit=5)
        
        for candle in result["candles"]:
            assert "timestamp" in candle
            assert "open"      in candle
            assert "high"      in candle
            assert "low"       in candle
            assert "close"     in candle
            assert "volume"    in candle
            # 基本價格關係：high >= low
            assert candle["high"] >= candle["low"]
            # 時間戳格式驗證（ISO 8601）
            assert "T" in candle["timestamp"]
            assert "Z" in candle["timestamp"]

    def test_summary_fields(self):
        """驗證返回的摘要欄位完整性"""
        result = get_ohlcv("binance", "BTC/USDT", limit=20)
        
        assert "latest_close"     in result
        assert "latest_volume"    in result
        assert "price_change_pct" in result
        assert "high_in_range"    in result
        assert "low_in_range"     in result
        assert "fetched_at"       in result
        
        # 價格必須為正
        assert result["latest_close"] > 0
        assert result["high_in_range"] >= result["low_in_range"]

    def test_limit_clamping(self):
        """測試 limit 邊界值被正確限制"""
        # limit 超過 500 應被截斷到 500
        result = get_ohlcv("binance", "BTC/USDT", limit=9999)
        assert result["count"] <= 500

        # limit 為 0 應被截斷到 1
        result = get_ohlcv("binance", "BTC/USDT", limit=0)
        assert result["count"] >= 1

    def test_different_timeframes(self):
        """測試不同時間週期均可正常工作"""
        for tf in ["5m", "15m", "1h", "4h", "1d"]:
            result = get_ohlcv("binance", "BTC/USDT", timeframe=tf, limit=3)
            assert result["count"] == 3, f"timeframe={tf} 返回數量異常"

    def test_invalid_timeframe_raises(self):
        """無效時間週期應拋出 ValueError"""
        with pytest.raises(ValueError, match="不支援的時間週期"):
            get_ohlcv("binance", "BTC/USDT", timeframe="99x")

    def test_invalid_symbol_raises(self):
        """無效交易對應拋出 ValueError"""
        with pytest.raises((ValueError, Exception)):
            get_ohlcv("binance", "FAKECOIN/USDT", limit=5)

    def test_okx_exchange(self):
        """測試 OKX 交易所也可正常使用"""
        result = get_ohlcv("okx", "BTC/USDT", timeframe="1h", limit=5)
        assert result["exchange"] == "okx"
        assert result["count"] > 0


class TestGetTicker:
    """測試 get_ticker 函數"""

    def test_basic_ticker(self):
        """正常情況：獲取 BTC/USDT Ticker"""
        result = get_ticker("binance", "BTC/USDT")

        assert result["exchange"]  == "binance"
        assert result["symbol"]    == "BTC/USDT"
        assert result["last_price"] > 0
        assert result["bid"]       > 0
        assert result["ask"]       > 0
        # ask >= bid（正常 Spread）
        assert result["ask"] >= result["bid"]

    def test_ticker_required_fields(self):
        """驗證 Ticker 返回所有必要欄位"""
        result = get_ticker("binance", "ETH/USDT")
        
        required_fields = [
            "exchange", "symbol", "last_price", "bid", "ask",
            "spread", "spread_pct", "volume_24h", "quote_volume_24h",
            "price_change_24h", "price_change_pct_24h",
            "high_24h", "low_24h", "timestamp"
        ]
        for field in required_fields:
            assert field in result, f"缺少欄位：{field}"

    def test_spread_calculation(self):
        """驗證 Spread 計算正確"""
        result = get_ticker("binance", "BTC/USDT")
        
        if result["bid"] and result["ask"]:
            expected_spread = round(result["ask"] - result["bid"], 8)
            assert abs(result["spread"] - expected_spread) < 0.01


class TestGetOrderbook:
    """測試 get_orderbook 函數"""

    def test_basic_orderbook(self):
        """正常情況：獲取 BTC/USDT Orderbook"""
        result = get_orderbook("binance", "BTC/USDT", depth=5)

        assert result["exchange"] == "binance"
        assert result["symbol"]   == "BTC/USDT"
        assert result["depth"]    == 5
        assert len(result["bids"]) > 0
        assert len(result["asks"]) > 0

    def test_bid_ask_ordering(self):
        """驗證 Orderbook 排序正確：買單從高到低，賣單從低到高"""
        result = get_orderbook("binance", "BTC/USDT", depth=10)
        
        bids = [b[0] for b in result["bids"]]
        asks = [a[0] for a in result["asks"]]
        
        # 買單應從高到低排序
        assert bids == sorted(bids, reverse=True), "買單排序錯誤"
        # 賣單應從低到高排序
        assert asks == sorted(asks), "賣單排序錯誤"
        # 最佳賣價 > 最佳買價
        assert result["best_ask"] > result["best_bid"]

    def test_depth_limit(self):
        """驗證 depth 邊界限制"""
        result = get_orderbook("binance", "BTC/USDT", depth=999)
        assert result["depth"] <= 50

    def test_volume_totals(self):
        """驗證總成交量欄位正確"""
        result = get_orderbook("binance", "BTC/USDT", depth=5)
        assert result["bid_total_volume"] > 0
        assert result["ask_total_volume"] > 0
        assert result["bid_ask_ratio"]    is not None


class TestListExchanges:
    """測試 list_exchanges 函數"""

    def test_returns_supported_list(self):
        """確認返回支援的交易所清單"""
        result = list_exchanges()
        
        assert "supported_in_this_system" in result
        assert "total_ccxt_exchanges"     in result
        assert "binance" in result["supported_in_this_system"]
        assert result["total_ccxt_exchanges"] > 0


class TestSchemas:
    """測試 JSON Schema 結構有效性"""

    def test_schema_import(self):
        """確認 schemas 可正常 import"""
        from skills.market_data.schemas import MARKET_DATA_TOOLS, MARKET_DATA_TOOL_MAP
        
        assert len(MARKET_DATA_TOOLS) == 21, "應有 21 個工具的 Schema"
        assert len(MARKET_DATA_TOOL_MAP) == 21, "應有 21 個工具映射"

    def test_schema_structure(self):
        """驗證每個 Schema 的基本結構符合 OpenAI Function Calling 格式"""
        from skills.market_data.schemas import MARKET_DATA_TOOLS
        
        for schema in MARKET_DATA_TOOLS:
            assert "type"     in schema,               f"缺少 type：{schema}"
            assert schema["type"] == "function",       f"type 應為 function"
            assert "function" in schema,               f"缺少 function 定義"
            assert "name"     in schema["function"],   f"缺少 function.name"
            assert "description" in schema["function"],f"缺少 function.description"
            assert "parameters"  in schema["function"],f"缺少 function.parameters"

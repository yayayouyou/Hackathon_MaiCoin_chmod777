"""
tests/test_derivatives.py

多交易所衍生品數據聚合模組單元測試
=====================================
"""

import pytest
from unittest.mock import patch, MagicMock
from skills.derivatives.binance_futures import (
    get_binance_funding_rate,
    get_binance_open_interest,
    get_binance_open_interest_history,
    get_binance_long_short_ratio
)
from skills.derivatives.bybit_derivatives import (
    get_bybit_funding_rate,
    get_bybit_open_interest_history
)
from skills.derivatives.okx_derivatives import (
    get_okx_funding_rate,
    get_okx_open_interest
)
from skills.derivatives.multi_exchange import (
    get_aggregated_funding_rate,
    get_aggregated_open_interest
)

# ──────────────────────────────────────────────
#  Binance Futures 測試
# ──────────────────────────────────────────────

class TestBinanceFutures:
    @patch("skills.derivatives.binance_futures.session_get")
    def test_get_binance_funding_rate_mock(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = [
            {"symbol": "BTCUSDT", "fundingRate": "0.000100", "fundingTime": 1700000000000},
            {"symbol": "BTCUSDT", "fundingRate": "0.000200", "fundingTime": 1700028800000}
        ]
        mock_get.return_value = mock_resp

        res = get_binance_funding_rate("BTC/USDT")
        assert res["symbol"] == "BTC/USDT"
        assert res["exchange"] == "Binance"
        assert res["latest_rate"] == 0.0002
        assert pytest.approx(res["avg_rate"]) == 0.00015
        assert "sentiment" in res

    @patch("skills.derivatives.binance_futures.session_get")
    def test_get_binance_open_interest_mock(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "symbol": "BTCUSDT",
            "openInterest": "15000.5",
            "time": 1700000000000
        }
        mock_get.return_value = mock_resp

        res = get_binance_open_interest("BTC/USDT")
        assert res["exchange"] == "Binance"
        assert res["open_interest"] == 15000.5

    @patch("skills.derivatives.binance_futures.session_get")
    def test_get_binance_open_interest_history_mock(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = [
            {"symbol": "BTCUSDT", "sumOpenInterest": "10000", "sumOpenInterestValue": "400000000", "timestamp": 1700000000000},
            {"symbol": "BTCUSDT", "sumOpenInterest": "11000", "sumOpenInterestValue": "440000000", "timestamp": 1700003600000}
        ]
        mock_get.return_value = mock_resp

        res = get_binance_open_interest_history("BTC/USDT", period="1h")
        assert res["exchange"] == "Binance"
        assert res["oi_change_pct"] == 10.0
        assert res["oi_trend"] == "上升"

    @patch("skills.derivatives.binance_futures.session_get")
    def test_get_binance_long_short_ratio_mock(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = [
            {"symbol": "BTCUSDT", "longShortRatio": "1.2", "longAccount": "0.545", "shortAccount": "0.455", "timestamp": 1700000000000}
        ]
        mock_get.return_value = mock_resp

        res = get_binance_long_short_ratio("BTC/USDT")
        assert res["latest_ratio"] == 1.2
        assert "sentiment_label" in res


# ──────────────────────────────────────────────
#  Bybit 測試
# ──────────────────────────────────────────────

class TestBybitDerivatives:
    @patch("skills.derivatives.bybit_derivatives.session_get")
    def test_get_bybit_funding_rate_mock(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "category": "linear",
                "list": [
                    {"symbol": "BTCUSDT", "fundingRate": "0.00015", "fundingRateTimestamp": "1700000000000"}
                ]
            }
        }
        mock_get.return_value = mock_resp

        res = get_bybit_funding_rate("BTC/USDT")
        assert res["exchange"] == "Bybit"
        assert res["latest_rate"] == 0.00015


# ──────────────────────────────────────────────
#  OKX 測試
# ──────────────────────────────────────────────

class TestOKXDerivatives:
    @patch("skills.derivatives.okx_derivatives.session_get")
    def test_get_okx_funding_rate_mock(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "code": "0",
            "msg": "",
            "data": [
                {"instId": "BTC-USDT-SWAP", "fundingRate": "0.00011", "fundingTime": "1700000000000"}
            ]
        }
        mock_get.return_value = mock_resp

        res = get_okx_funding_rate("BTC/USDT")
        assert res["exchange"] == "OKX"
        assert res["latest_rate"] == 0.00011


# ──────────────────────────────────────────────
#  多交易所聚合測試 (Multi-Exchange)
# ──────────────────────────────────────────────

class TestMultiExchangeAggregator:
    @patch("skills.derivatives.multi_exchange.get_binance_funding_rate")
    @patch("skills.derivatives.multi_exchange.get_bybit_funding_rate")
    @patch("skills.derivatives.multi_exchange.get_okx_funding_rate")
    def test_get_aggregated_funding_rate_mock(self, mock_okx, mock_bybit, mock_binance):
        # 模擬 Binance 回傳
        mock_binance.return_value = {"latest_rate": 0.0001, "latest_rate_pct": 0.01, "avg_rate_pct": 0.01, "sentiment": "偏多"}
        # 模擬 Bybit 回傳
        mock_bybit.return_value = {"latest_rate": 0.00018, "latest_rate_pct": 0.018, "avg_rate_pct": 0.018, "sentiment": "極度偏多"}
        # 模擬 OKX 回傳
        mock_okx.return_value = {"latest_rate": 0.00008, "latest_rate_pct": 0.008, "avg_rate_pct": 0.008, "sentiment": "中性"}

        res = get_aggregated_funding_rate("BTC/USDT")

        assert res["symbol"] == "BTC/USDT"
        assert "aggregated" in res
        assert res["aggregated"]["max_rate"]["exchange"] == "Bybit"
        assert res["aggregated"]["min_rate"]["exchange"] == "OKX"
        assert pytest.approx(res["aggregated"]["spread"], 0.000001) == 0.0001
        assert "Bybit" in res["by_exchange"]
        assert "OKX" in res["by_exchange"]


# ──────────────────────────────────────────────
#  真實 API 測試（非必要，僅在需要時手動調試）
# ──────────────────────────────────────────────

@pytest.mark.skip(reason="整合測試：會發送真實網路請求")
class TestRealDerivativesAPI:
    def test_real_binance_funding_rate(self):
        res = get_binance_funding_rate("BTC/USDT")
        assert "latest_rate" in res
        print(f"\nBinance BTC 最新費率: {res['latest_rate_pct']:.4f}%")

    def test_real_bybit_funding_rate(self):
        res = get_bybit_funding_rate("BTC/USDT")
        assert "latest_rate" in res
        print(f"\nBybit BTC 最新費率: {res['latest_rate_pct']:.4f}%")

    def test_real_okx_funding_rate(self):
        res = get_okx_funding_rate("BTC/USDT")
        assert "latest_rate" in res
        print(f"\nOKX BTC 最新費率: {res['latest_rate_pct']:.4f}%")

    def test_real_aggregated_funding_rate(self):
        res = get_aggregated_funding_rate("BTC/USDT")
        assert "aggregated" in res
        print(f"\n聚合最新費率: {res['aggregated']}")

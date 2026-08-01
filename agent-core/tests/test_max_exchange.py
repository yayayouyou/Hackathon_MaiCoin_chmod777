"""
tests/test_max_exchange.py

MAX 交易所模組單元測試
=====================================
"""

import pytest
import os
import base64
import json
from unittest.mock import patch, MagicMock
from skills.max_exchange.max_public import (
    get_max_markets,
    get_max_tickers,
    get_max_depth,
    get_max_klines,
    get_max_public_trades
)
from skills.max_exchange.max_private import (
    get_max_member_info,
    get_max_accounts,
    get_max_orders,
    get_max_order_history,
    get_max_my_trades,
    get_max_deposits,
    get_max_withdrawals
)

requires_max_api_key = pytest.mark.skipif(
    not (os.getenv("MAX_API_KEY") and os.getenv("MAX_API_SECRET")),
    reason="需要設定 MAX_API_KEY 與 MAX_API_SECRET 才能執行此測試",
)

# ──────────────────────────────────────────────
#  公開行情接口 Mock 測試
# ──────────────────────────────────────────────

class TestMaxPublicMock:
    @patch("skills.max_exchange.max_public.session_get")
    def test_get_max_markets_mock(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = [
            {"id": "btctwd", "name": "BTC/TWD", "base_unit": "btc", "quote_unit": "twd", "base_unit_precision": 8, "quote_unit_precision": 1, "min_base_amount": 0.0001}
        ]
        mock_get.return_value = mock_resp

        res = get_max_markets()
        assert len(res) == 1
        assert res[0]["id"] == "btctwd"
        assert res[0]["name"] == "BTC/TWD"
        assert res[0]["base_precision"] == 8

    @patch("skills.max_exchange.max_public.session_get")
    def test_get_max_tickers_mock(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        # MAX /api/v3/tickers?markets[]=btctwd 回傳的是「陣列」，帶 market 時取第一筆，
        # get_max_tickers 回傳「扁平的單一 ticker dict」(欄位含 last/buy/sell)。
        mock_resp.json.return_value = [
            {"market": "btctwd", "buy": "2000000.0", "sell": "2001000.0", "last": "2000500.0", "open": "1990000.0", "vol": "50.5"}
        ]
        mock_get.return_value = mock_resp

        res = get_max_tickers("BTC/TWD")
        assert isinstance(res, dict)
        assert res.get("market") == "btctwd"
        assert res["last"] == "2000500.0"

    @patch("skills.max_exchange.max_public.session_get")
    def test_get_max_depth_mock(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "timestamp": 1700000000,
            "bids": [["2000000.0", "0.5"], ["1999000.0", "1.0"]],
            "asks": [["2001000.0", "0.2"], ["2002000.0", "0.8"]]
        }
        mock_get.return_value = mock_resp

        res = get_max_depth("BTC/TWD", limit=2)
        assert res["market"] == "btctwd"
        assert res["total_bid_volume"] == 1.5
        assert res["total_ask_volume"] == 1.0


# ──────────────────────────────────────────────
#  私有接口 Mock 測試
# ──────────────────────────────────────────────

class TestMaxPrivateMock:
    @patch("skills.max_exchange.max_private.session_get")
    @patch.dict(os.environ, {"MAX_API_KEY": "test_access", "MAX_API_SECRET": "test_secret"})
    def test_get_max_member_info_mock(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "email": "user@example.com", "level": 3,
            "current_vip_level": {"level": 1, "maker_fee": 0.0005, "taker_fee": 0.0012},
            "next_vip_level": {"level": 2, "minimum_trading_volume": 5000000, "maker_fee": 0.0004, "taker_fee": 0.001},
        }
        mock_get.return_value = mock_resp

        res = get_max_member_info()
        assert res["email"] == "user@example.com"
        assert res["account_kyc_level"] == 3    # 身份驗證等級（非 VIP）
        assert res["vip_tier"] == 1             # VIP 交易等級（決定手續費）
        assert res["maker_fee_pct"] == 0.05     # 0.0005 → 0.05%
        assert res["next_vip_tier"] == 2

        # 驗證認證 Header 的生成與簽名
        headers = mock_get.call_args[1]["headers"]
        assert headers["X-MAX-ACCESSKEY"] == "test_access"
        assert "X-MAX-PAYLOAD" in headers
        assert "X-MAX-SIGNATURE" in headers

        # 驗證 Payload 內容
        payload_base64 = headers["X-MAX-PAYLOAD"]
        payload_decoded = base64.b64decode(payload_base64).decode("utf-8")
        payload_json = json.loads(payload_decoded)
        assert payload_json["path"] == "/api/v3/info"
        assert "nonce" in payload_json

    @patch("skills.max_exchange.max_private.session_get")
    @patch.dict(os.environ, {"MAX_API_KEY": "test_access", "MAX_API_SECRET": "test_secret"})
    def test_get_max_accounts_mock(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = [
            {"currency": "twd", "balance": "1000.5", "locked": "200.0"},
            {"currency": "btc", "balance": "0.0", "locked": "0.0"} # 小餘額過濾
        ]
        mock_get.return_value = mock_resp

        res = get_max_accounts()
        assert len(res) == 1
        assert res[0]["currency"] == "TWD"
        assert res[0]["balance"] == 1000.5
        assert res[0]["locked"] == 200.0
        assert res[0]["total"] == 1200.5

    @patch("skills.max_exchange.max_private.session_get")
    @patch.dict(os.environ, {"MAX_API_KEY": "test_access", "MAX_API_SECRET": "test_secret"})
    def test_get_max_orders_mock(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = [
            {"id": 12345, "market": "btctwd", "side": "buy", "price": "2000000.0", "volume": "0.01", "state": "wait"}
        ]
        mock_get.return_value = mock_resp

        res = get_max_orders("BTC/TWD", state="wait")
        assert len(res) == 1
        assert res[0]["id"] == 12345
        assert res[0]["side"] == "buy"

    @patch("skills.max_exchange.max_private.os.getenv", return_value="")
    def test_missing_api_key_raises(self, mock_getenv):
        """若 API 金鑰未設定，應拋出 EnvironmentError"""
        with pytest.raises(EnvironmentError, match="MAX_API_KEY"):
            get_max_member_info()


# ──────────────────────────────────────────────
#  真實 API 測試（非必要，僅在有 API 金鑰時執行）
# ──────────────────────────────────────────────

class TestMaxRealAPI:
    def test_real_max_markets(self):
        """不需金鑰的真實公開請求測試"""
        res = get_max_markets()
        assert len(res) > 0
        symbols = [m["id"] for m in res]
        assert "btctwd" in symbols
        print(f"\n✅ 成功獲取 MAX 交易對列表，總數: {len(res)}")

    def test_real_max_depth(self):
        """不需金鑰的真實公開深度請求"""
        res = get_max_depth("btctwd", limit=5)
        assert res["market"] == "btctwd"
        assert len(res["bids"]) <= 5
        print(f"\n✅ 成功獲取 BTC/TWD 即時買一報價: {res['bids'][0][0]} 賣一報價: {res['asks'][0][0]}")

    @requires_max_api_key
    def test_real_member_info(self):
        res = get_max_member_info()
        assert "email" in res
        print(f"\n✅ 成功讀取帳戶 Email: {res['email']}")

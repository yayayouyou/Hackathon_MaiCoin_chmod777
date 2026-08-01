"""
tests/test_market_intel.py

市場情報模組單元測試
=====================================
"""

import pytest
import os
from unittest.mock import patch, MagicMock
from skills.market_intel.coingecko_client import (
    get_coingecko_coin_price,
    get_coingecko_global_stats,
    get_coingecko_trending
)
from skills.market_intel.cmc_client import (
    get_cmc_latest_quotes,
    get_cmc_global_metrics
)
from skills.market_intel.blockchain_client import (
    get_blockchain_btc_stats,
    get_btc_unconfirmed_tx
)
from skills.market_intel.fng_client import (
    get_crypto_fear_and_greed_index
)

requires_cmc_key = pytest.mark.skipif(
    not os.getenv("COINMARKETCAP_API_KEY"),
    reason="需要設定 COINMARKETCAP_API_KEY 才能執行此測試",
)

# ──────────────────────────────────────────────
#  CoinGecko 測試
# ──────────────────────────────────────────────

class TestCoinGeckoMock:
    @patch("skills.market_intel.coingecko_client.session_get")
    def test_get_coingecko_coin_price_mock(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "bitcoin": {"usd": 65000.0, "usd_market_cap": 1280000000000.0, "usd_24h_change": 1.5}
        }
        mock_get.return_value = mock_resp

        res = get_coingecko_coin_price("bitcoin")
        assert "bitcoin" in res
        assert res["bitcoin"]["usd"] == 65000.0

    @patch("skills.market_intel.coingecko_client.session_get")
    def test_get_coingecko_global_stats_mock(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "data": {
                "active_cryptocurrencies": 10000,
                "total_market_cap": {"usd": 2500000000000.0},
                "total_volume": {"usd": 80000000000.0},
                "market_cap_percentage": {"btc": 55.4, "eth": 17.2}
            }
        }
        mock_get.return_value = mock_resp

        res = get_coingecko_global_stats()
        assert res["active_cryptocurrencies"] == 10000
        assert res["total_market_cap_usd"] == 2500000000000.0


# ──────────────────────────────────────────────
#  CoinMarketCap 測試
# ──────────────────────────────────────────────

class TestCMCMock:
    @patch("skills.market_intel.cmc_client.session_get")
    @patch.dict(os.environ, {"COINMARKETCAP_API_KEY": "test_cmc_key"})
    def test_get_cmc_latest_quotes_mock(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "status": {"error_code": 0, "error_message": None},
            "data": {
                "BTC": {
                    "name": "Bitcoin",
                    "symbol": "BTC",
                    "cmc_rank": 1,
                    "quote": {
                        "USD": {
                            "price": 64500.0,
                            "volume_24h": 25000000000.0,
                            "percent_change_24h": 2.1,
                            "market_cap": 1270000000000.0
                        }
                    }
                }
            }
        }
        mock_get.return_value = mock_resp

        res = get_cmc_latest_quotes("BTC")
        assert "BTC" in res
        assert res["BTC"]["name"] == "Bitcoin"
        assert res["BTC"]["price"] == 64500.0

    @patch("skills.market_intel.cmc_client.os.getenv", return_value="")
    def test_missing_api_key_raises(self, mock_getenv):
        with pytest.raises(EnvironmentError, match="COINMARKETCAP_API_KEY"):
            get_cmc_latest_quotes("BTC")


# ──────────────────────────────────────────────
#  Blockchain.com 測試
# ──────────────────────────────────────────────

class TestBlockchainMock:
    @patch("skills.market_intel.blockchain_client.session_get")
    def test_get_blockchain_btc_stats_mock(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.json.return_value = {
            "market_price_usd": 63000.0,
            "hash_rate": 600000000000000000.0,
            "difficulty": 83000000000
        }
        mock_get.return_value = mock_resp

        res = get_blockchain_btc_stats()
        assert res["market_price_usd"] == 63000.0
        assert res["difficulty"] == 83000000000

    @patch("skills.market_intel.blockchain_client.session_get")
    def test_get_btc_unconfirmed_tx_mock(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.text = "120000"
        mock_get.return_value = mock_resp

        res = get_btc_unconfirmed_tx()
        assert res["unconfirmed_transactions_count"] == 120000
        assert "mempool_status" in res


# ──────────────────────────────────────────────
#  恐懼與貪婪指數 Mock 測試
# ──────────────────────────────────────────────

class TestFearAndGreedMock:
    @patch("skills.market_intel.fng_client.fetch_json")
    def test_get_crypto_fear_and_greed_index_mock(self, mock_fj):
        mock_fj.return_value = {
            "name": "Fear and Greed Index",
            "data": [{"value": "75", "value_classification": "Greed", "timestamp": "1704585600"}],
            "metadata": {"error": None},
        }
        res = get_crypto_fear_and_greed_index(limit=1)
        assert res["name"] == "Crypto Fear and Greed Index"
        assert res["latest_value"] == 75
        assert res["latest_sentiment"] == "Greed"
        assert len(res["history"]) == 1

    @patch("skills.market_intel.fng_client.fetch_json")
    def test_fng_failure_does_not_fabricate_50(self, mock_fj):
        """治本重點：抓失敗絕不回捏造的中性 50。"""
        from skills._http import FetchError
        mock_fj.side_effect = FetchError("HTTP 503")
        res = get_crypto_fear_and_greed_index(limit=1)
        assert "error" in res
        assert "latest_value" not in res            # 無任何數值
        assert res.get("fallback_value") is None     # 無捏造 fallback

# ──────────────────────────────────────────────
#  真實公開 API 測試
# ──────────────────────────────────────────────

class TestRealMarketIntelAPI:
    def test_real_coingecko_price(self):
        res = get_coingecko_coin_price("bitcoin")
        assert "bitcoin" in res
        assert "usd" in res["bitcoin"]
        print(f"\n✅ CoinGecko 真實 BTC 幣價: {res['bitcoin']['usd']} USD")

    def test_real_blockchain_stats(self):
        res = get_blockchain_btc_stats()
        assert "market_price_usd" in res
        assert res["difficulty"] > 0
        print(f"\n✅ Blockchain.com 真實 BTC 全網算力: {res['hash_rate_ehs']:.2f} EH/s, 難度: {res['difficulty']:,}")

    def test_real_fear_and_greed_index(self):
        res = get_crypto_fear_and_greed_index(limit=3)
        assert "latest_value" in res
        assert res["latest_value"] >= 0 and res["latest_value"] <= 100
        assert len(res["history"]) == 3
        print(f"\n✅ Alternative.me 真實 Fear & Greed: {res['latest_value']} ({res['latest_sentiment']})")

"""
tests/test_coinglass.py

Coinglass API v4 模塊的單元測試
================================
注意：Coinglass 測試需要有效的 API Key 才能執行！
      如果沒有 API Key，僅能執行「無 Key 時的錯誤處理」測試。

      設定方式：在 .env 中填入 COINGLASS_API_KEY=your_key

執行：
    # 執行所有測試（需要 API Key）
    python -m pytest tests/test_coinglass.py -v
    
    # 只執行不需要 Key 的測試
    python -m pytest tests/test_coinglass.py -v -m "not requires_api_key"
"""

import os
import pytest
from unittest.mock import patch, MagicMock

# 標記需要 API Key 的測試
requires_api_key = pytest.mark.skipif(
    not os.getenv("COINGLASS_API_KEY"),
    reason="需要設定 COINGLASS_API_KEY 才能執行此測試",
)


class TestGetFundingRateWithMock:
    """使用 Mock 測試資金費率（不需要真實 API Key）"""

    def _make_mock_response(self, data: list) -> MagicMock:
        """建立模擬 HTTP 回應"""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "success": True,
            "data": data,
        }
        return mock_resp

    @patch("skills.market_data.coinglass_client.session_get")
    @patch.dict(os.environ, {"COINGLASS_API_KEY": "test_key_mock"})
    def test_funding_rate_basic(self, mock_get):
        """測試資金費率基本功能（Mock）"""
        from skills.market_data.coinglass_client import get_funding_rate

        # 模擬 API 回應
        mock_data = [
            {"t": 1704067200, "c": 0.0001},
            {"t": 1704096000, "c": 0.00015},
            {"t": 1704124800, "c": -0.00005},
        ]
        mock_get.return_value = self._make_mock_response(mock_data)

        result = get_funding_rate("BTC", "Binance", interval="8h", limit=3)

        assert result["symbol"]   == "BTC"
        assert result["exchange"] == "Binance"
        assert result["count"]    == 3
        assert "latest_rate"     in result
        assert "latest_rate_pct" in result
        assert "avg_rate_pct"    in result
        assert "sentiment"       in result
        assert len(result["history"]) == 3

    @patch("skills.market_data.coinglass_client.session_get")
    @patch.dict(os.environ, {"COINGLASS_API_KEY": "test_key_mock"})
    def test_sentiment_analysis(self, mock_get):
        """測試情緒分析邏輯"""
        from skills.market_data.coinglass_client import get_funding_rate

        # 高正費率 → 多頭擁擠
        mock_get.return_value = self._make_mock_response([
            {"t": 1704067200, "c": 0.0005},  # 0.05%，偏高
        ])
        result = get_funding_rate("BTC")
        assert "偏多" in result["sentiment"] or "過熱" in result["sentiment"]

        # 負費率 → 空頭
        mock_get.return_value = self._make_mock_response([
            {"t": 1704067200, "c": -0.0005},
        ])
        result = get_funding_rate("BTC")
        assert "偏空" in result["sentiment"] or "過冷" in result["sentiment"]

    @patch("skills.market_data.coinglass_client.os.getenv", return_value="")
    def test_missing_api_key_raises(self, mock_getenv):
        """沒有 API Key 時應拋出 EnvironmentError"""
        from skills.market_data.coinglass_client import get_funding_rate

        with pytest.raises(EnvironmentError, match="COINGLASS_API_KEY"):
            get_funding_rate("BTC")


class TestGetOpenInterestWithMock:
    """使用 Mock 測試持倉量"""

    @patch("skills.market_data.coinglass_client.session_get")
    @patch.dict(os.environ, {"COINGLASS_API_KEY": "test_key_mock"})
    def test_open_interest_basic(self, mock_get):
        """測試持倉量基本功能（Mock）"""
        from skills.market_data.coinglass_client import get_open_interest

        mock_data = [
            {"t": 1704067200, "c": 10000000000.0},
            {"t": 1704096000, "c": 10500000000.0},
            {"t": 1704124800, "c": 11000000000.0},
        ]
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"success": True, "data": mock_data}
        mock_get.return_value = mock_resp

        result = get_open_interest("BTC", "Binance", interval="1h", limit=3)

        assert result["symbol"]        == "BTC"
        assert result["count"]         == 3
        assert result["oi_change_pct"] > 0   # OI 從 100億 升到 110億，應為正
        assert result["oi_trend"]      == "上升"
        assert "history"               in result


class TestGetLiquidationWithMock:
    """使用 Mock 測試爆倉數據"""

    @patch("skills.market_data.coinglass_client.session_get")
    @patch.dict(os.environ, {"COINGLASS_API_KEY": "test_key_mock"})
    def test_liquidation_basic(self, mock_get):
        """測試爆倉數據基本功能（Mock）"""
        from skills.market_data.coinglass_client import get_liquidation_history

        mock_data = [
            {"t": 1704067200, "longLiquidationUsd": 5000000, "shortLiquidationUsd": 1000000},
            {"t": 1704096000, "longLiquidationUsd": 3000000, "shortLiquidationUsd": 500000},
        ]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"success": True, "data": mock_data}
        mock_get.return_value = mock_resp

        result = get_liquidation_history("BTC")

        assert result["symbol"] == "BTC"
        assert result["long_liquidation_usd"]  == 8_000_000
        assert result["short_liquidation_usd"] == 1_500_000
        assert result["liquidation_bias"]      == "多頭爆倉為主"


# ──────────────────────────────────────────────
#  需要真實 API Key 的整合測試
# ──────────────────────────────────────────────

class TestCoinglassIntegration:
    """真實 API 整合測試（需要 COINGLASS_API_KEY）"""

    @requires_api_key
    def test_real_funding_rate(self):
        """真實 API：獲取 BTC 資金費率"""
        from skills.market_data.coinglass_client import get_funding_rate

        result = get_funding_rate("BTC", "Binance", interval="8h", limit=5)

        assert result["count"] > 0
        assert result["symbol"] == "BTC"
        assert isinstance(result["latest_rate"], float)
        print(f"\n✅ BTC 最新資金費率：{result['latest_rate_pct']:.4f}% 情緒：{result['sentiment']}")


# ──────────────────────────────────────────────
#  免 Key Scraper 解密模組單元與真實測試
# ──────────────────────────────────────────────

class TestCoinglassScraperMock:
    @patch("skills.derivatives.coinalyze_client._coinalyze_request")
    def test_get_coinglass_liquidation_chart_delegates_to_coinalyze(self, mock_req):
        """治本：爆倉數據改用 Coinalyze 免費跨所彙整（不再 AES 抓取）。"""
        from skills.market_data.coinglass_scraper import get_coinglass_liquidation_chart
        mock_req.return_value = [{"symbol": "BTCUSDT_PERP.A", "history": [
            {"t": 1700000000, "l": 4_000_000, "s": 1_000_000}]}]
        res = get_coinglass_liquidation_chart("BTC", "1h")
        assert res["long_liquidation_usd"] == 4_000_000
        assert res["liquidation_bias"] == "多頭爆倉為主"
        assert "Coinalyze" in res["source"]

    @patch("skills.derivatives.multi_exchange.get_aggregated_open_interest")
    def test_get_coinglass_open_interest_info_local(self, mock_agg):
        """治本：持倉分佈改用直連交易所的免費彙整持倉量（不再 AES 抓取）。"""
        from skills.market_data.coinglass_scraper import get_coinglass_open_interest_info
        mock_agg.return_value = {
            "symbol": "BTC/USDT",
            "by_exchange": {
                "Binance": {"open_interest": 500000000, "unit": "BTC"},
                "OKX": {"open_interest": 800000000, "unit": "BTC"},
            },
        }
        res = get_coinglass_open_interest_info("BTC")
        # 依持倉量由大到小排序 → OKX 在前
        assert res[0]["exchangeName"] == "OKX"
        assert res[0]["openInterest"] == 800000000
        assert res[1]["exchangeName"] == "Binance"

    @patch("skills.market_data.onchain_indicators._coingecko_request")
    def test_get_coinglass_ahr999_local(self, mock_cg):
        """治本：AHR999 改由 CoinGecko 價格本地計算（不再 AES 抓取）。"""
        from skills.market_data.coinglass_scraper import get_coinglass_ahr999
        base = 1700000000000
        mock_cg.return_value = {"prices": [[base + i * 86400000, 50000.0] for i in range(260)]}
        res = get_coinglass_ahr999()
        assert "list" in res and res["latest_ahr999"] > 0
        assert all(k in res["list"][-1] for k in ("date", "ahr999", "value"))
        assert "本地計算" in res["source"]

    @patch("skills.market_data.onchain_indicators._coingecko_request")
    def test_get_coinglass_altcoin_season_local(self, mock_cg):
        """治本：山寨季指數改由 CoinGecko 前 100 幣 30 日漲跌本地計算（不再 AES 抓取）。"""
        from skills.market_data.coinglass_scraper import get_coinglass_altcoin_season
        f = "price_change_percentage_30d_in_currency"
        # BTC +5%；4 個山寨中 3 個跑贏 BTC（含 1 個穩定幣應被排除）
        mock_cg.return_value = [
            {"symbol": "btc", f: 5.0, "last_updated": "2026-07-11T00:00:00Z"},
            {"symbol": "eth", f: 10.0, "last_updated": "2026-07-11T00:00:00Z"},
            {"symbol": "sol", f: 20.0, "last_updated": "2026-07-11T00:00:00Z"},
            {"symbol": "xrp", f: 8.0, "last_updated": "2026-07-11T00:00:00Z"},
            {"symbol": "ada", f: 1.0, "last_updated": "2026-07-11T00:00:00Z"},
            {"symbol": "usdt", f: 0.0, "last_updated": "2026-07-11T00:00:00Z"},  # 穩定幣→排除
        ]
        res = get_coinglass_altcoin_season()
        # 4 個有效山寨（eth/sol/xrp/ada），3 個跑贏 BTC → 指數 75
        assert res["sample_size"] == 4
        assert res["outperformers"] == 3
        assert res["altcoin_season_index"] == 75
        assert res["list"][0]["altcoinIndex"] == 75

    @patch("skills.market_data.onchain_indicators._coingecko_request")
    def test_get_coinglass_mayer_multiple_local(self, mock_cg):
        """治本：Mayer 改由 CoinGecko 價格本地計算；常數價 → Mayer = 1。"""
        from skills.market_data.coinglass_scraper import get_coinglass_mayer_multiple
        base = 1700000000000
        mock_cg.return_value = {"prices": [[base + i * 86400000, 100.0] for i in range(260)]}
        res = get_coinglass_mayer_multiple()
        assert isinstance(res, list) and len(res) > 0
        assert abs(res[-1]["index"] - 1.0) < 1e-9
        assert all(k in res[-1] for k in ("timestamp", "index", "price"))

    # ETF flow / grayscale / liquidation heatmap 已改用免費第一方/本地計算來源，
    # 其單元測試移至 tests/test_free_exclusive.py（etf_flow store、grayscale、heatmap 數學）。


class TestCoinglassScraperReal:
    def test_real_coinglass_home_stats(self):
        """真實網路：免 Key 聚合全網大盤總覽（CoinGecko + 衍生品彙總）"""
        from skills.market_data.coinglass_scraper import get_coinglass_home_stats

        res = get_coinglass_home_stats()
        if isinstance(res, dict) and res.get("error"):
            pytest.skip(f"大盤聚合暫時失敗: {res['error']}")

        deriv = res.get("derivatives", {})
        if deriv.get("error"):
            pytest.skip(f"衍生品彙總暫時失敗: {deriv['error']}")
        assert deriv.get("total_open_interest_usd", 0) > 0
        print(f"\n✅ 免費聚合 全網總持倉: {deriv['total_open_interest_usd']:,.0f} USD")

    def test_real_coinglass_open_interest_info(self):
        """真實網路：免 Key 獲取代幣全網持倉分佈"""
        from skills.market_data.coinglass_scraper import get_coinglass_open_interest_info
        
        res = get_coinglass_open_interest_info("BTC")
        if isinstance(res, dict) and "error" in res:
            pytest.skip(f"CoinGlass 免 Key 數據拉取受限: {res['error']}")
            
        assert isinstance(res, list)
        assert len(res) > 0
        assert "exchangeName" in res[0]
        print(f"\n✅ 免 Key BTC 持倉分佈首家交易所: {res[0]['exchangeName']} 持倉: {res[0].get('openInterest', 0):,} USD")

    def test_real_coinglass_ahr999(self):
        """真實網路：免 Key 獲取 AHR999 囤幣指標"""
        from skills.market_data.coinglass_scraper import get_coinglass_ahr999
        
        res = get_coinglass_ahr999()
        if isinstance(res, dict) and "error" in res:
            pytest.skip(f"CoinGlass AHR999 拉取失敗: {res['error']}")
            
        assert "list" in res
        assert len(res["list"]) > 0
        print(f"\n✅ 免 Key 最新 AHR999 指數: {res['list'][-1]['ahr999']} 價格: {res['list'][-1]['value']}")

    def test_real_coinglass_altcoin_season(self):
        """真實網路：免 Key 獲取山寨幣季節指數"""
        from skills.market_data.coinglass_scraper import get_coinglass_altcoin_season
        
        res = get_coinglass_altcoin_season()
        if isinstance(res, dict) and res.get("error"):
            pytest.skip(f"山寨季指數拉取失敗: {res['error']}")

        assert isinstance(res, dict)
        assert 0 <= res["altcoin_season_index"] <= 100
        assert res["list"][0]["altcoinIndex"] == res["altcoin_season_index"]
        print(f"\n✅ 本地計算 山寨季指數: {res['altcoin_season_index']} ({res['classification']})")

    def test_real_coinglass_mayer_multiple(self):
        """真實網路：免 Key 獲取梅耶乘數"""
        from skills.market_data.coinglass_scraper import get_coinglass_mayer_multiple
        
        res = get_coinglass_mayer_multiple()
        if isinstance(res, dict) and "error" in res:
            pytest.skip(f"CoinGlass Mayer Multiple 拉取失敗: {res['error']}")
            
        assert isinstance(res, list)
        assert len(res) > 0
        print(f"\n✅ 免 Key 最新 Mayer 指數: {res[-1]['index']}")

    def test_real_coinglass_etf_flow(self):
        """真實網路：第一方 SoSoValue ETF 每日流向（需免費金鑰，否則優雅跳過）"""
        from skills.market_data.coinglass_scraper import get_coinglass_etf_flow

        res = get_coinglass_etf_flow("BTC")
        if isinstance(res, dict) and res.get("error"):
            pytest.skip(f"ETF flow 需免費 SoSoValue 金鑰或暫時失敗: {res['error']}")

        assert res.get("asset") == "BTC"
        assert isinstance(res.get("history"), list)
        print(f"\n✅ ETF 最新淨流入: {res.get('latest_net_flow_usd')} @ {res.get('latest_date')}")

    def test_real_coinglass_grayscale_stats(self):
        """真實網路：免 Key 本地計算灰度 OTC 折溢價"""
        from skills.market_data.coinglass_scraper import get_coinglass_grayscale_stats

        res = get_coinglass_grayscale_stats()
        if isinstance(res, dict) and res.get("error"):
            pytest.skip(f"灰度計算暫時失敗: {res['error']}")

        assert "otc_trusts" in res and "etf_now" in res
        print(f"\n✅ 灰度 OTC 有效折溢價數: {res.get('otc_count')}；ETF 類: {[e['ticker'] for e in res['etf_now']]}")

    def test_real_coinglass_liquidation_heatmap(self):
        """真實網路：免 Key 本地計算爆倉熱力圖（OI 限流時優雅跳過）"""
        from skills.market_data.coinglass_scraper import get_coinglass_liquidation_heatmap

        res = get_coinglass_liquidation_heatmap("BTC", "3d")
        if isinstance(res, dict) and res.get("error"):
            pytest.skip(f"熱力圖計算失敗: {res['error']}")
        if not res.get("data_available"):
            pytest.skip(f"OI 暫不可用（限流）：{res.get('caveat','')[:40]}")

        assert res["current_price"] > 0
        assert isinstance(res["levels"], list) and len(res["levels"]) > 0
        print(f"\n✅ 本地熱力圖 群落數: {len(res['levels'])} 現價: {res['current_price']}")




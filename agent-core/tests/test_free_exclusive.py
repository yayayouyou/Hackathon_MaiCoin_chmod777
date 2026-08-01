"""
tests/test_free_exclusive.py

原 CoinGlass 獨家數據『免費化』後的單元測試（不需真實金鑰/網路）：
  - Coinalyze 爆倉解析 + 佔位符金鑰偵測
  - market_overview 大盤聚合（逐腳降級）
  - liquidation_heatmap 本地投影數學
  - etf_flow 本地快照 store 併入
  - grayscale OTC 折溢價計算
"""

import os
import pytest
from unittest.mock import patch


# ────────────────────────────── Coinalyze ──────────────────────────────
class TestCoinalyze:
    def test_symbol_and_interval_mapping(self):
        from skills.derivatives.coinalyze_client import _agg_symbol, _norm_interval
        assert _agg_symbol("BTC") == "BTCUSDT_PERP.A"
        assert _agg_symbol("eth") == "ETHUSDT_PERP.A"
        assert _agg_symbol("BTC/USDT") == "BTCUSDT_PERP.A"
        assert _norm_interval("1h") == "1hour"
        assert _norm_interval("1d") == "daily"

    def test_placeholder_key_raises(self):
        from skills.derivatives.coinalyze_client import get_coinalyze_liquidations
        with patch.dict(os.environ, {"COINALYZE_API_KEY": "your_coinalyze_api_key_here"}):
            with pytest.raises(EnvironmentError, match="COINALYZE_API_KEY"):
                get_coinalyze_liquidations("BTC")

    @patch("skills.derivatives.coinalyze_client._coinalyze_request")
    def test_liquidation_parsing_and_bias(self, mock_req):
        from skills.derivatives.coinalyze_client import get_coinalyze_liquidations
        mock_req.return_value = [{
            "symbol": "BTCUSDT_PERP.A",
            "history": [
                {"t": 1700000000, "l": 5_000_000, "s": 1_000_000},
                {"t": 1700003600, "l": 3_000_000, "s": 500_000},
            ],
        }]
        r = get_coinalyze_liquidations("BTC")
        assert r["long_liquidation_usd"] == 8_000_000
        assert r["short_liquidation_usd"] == 1_500_000
        assert r["liquidation_bias"] == "多頭爆倉為主"
        assert r["period_count"] == 2
        # 前端毫秒時間戳
        assert r["history"][0]["timestamp"] == 1700000000 * 1000

    @patch("skills.derivatives.coinalyze_client._coinalyze_request")
    def test_long_short_ratio_parsing(self, mock_req):
        from skills.derivatives.coinalyze_client import get_coinalyze_long_short_ratio
        mock_req.return_value = [{"symbol": "BTCUSDT_PERP.A", "history": [
            {"t": 1700000000, "r": 1.10, "l": 52.4, "s": 47.6},
            {"t": 1700003600, "r": 1.27, "l": 55.9, "s": 44.1},
        ]}]
        r = get_coinalyze_long_short_ratio("BTC")
        assert r["latest_ratio"] == 1.27
        assert r["long_account_pct"] == 55.9
        assert r["short_account_pct"] == 44.1
        assert r["sentiment_label"] == "散戶溫和偏多"
        assert r["history"][-1]["timestamp"] == 1700003600 * 1000

    @patch("skills.derivatives.coinalyze_client._coinalyze_request")
    def test_predicted_funding_parsing(self, mock_req):
        # Coinalyze value 已是百分比（不可再 ×100）：0.05 = 0.05% → 偏多擁擠
        from skills.derivatives.coinalyze_client import get_coinalyze_predicted_funding
        mock_req.return_value = [{"symbol": "BTCUSDT_PERP.A", "value": 0.05, "update": 1}]
        r = get_coinalyze_predicted_funding("BTC")
        assert r["predicted_funding_rate_pct"] == 0.05      # 原值即百分比
        assert r["predicted_funding_rate"] == 0.0005        # 分數 = %/100
        assert "偏多" in r["sentiment"]

    @patch("skills.derivatives.coinalyze_client._coinalyze_request")
    def test_predicted_funding_low_is_neutral(self, mock_req):
        # 0.005% 是低費率 → 中性（修前 ×100 會誤判成 0.5% 偏多擁擠）
        from skills.derivatives.coinalyze_client import get_coinalyze_predicted_funding
        assert get_coinalyze_predicted_funding("BTC") is not None
        mock_req.return_value = [{"symbol": "BTCUSDT_PERP.A", "value": 0.005}]
        assert get_coinalyze_predicted_funding("BTC")["sentiment"] == "中性"

    @patch("skills.derivatives.coinalyze_client._coinalyze_request")
    def test_predicted_funding_negative_is_bearish(self, mock_req):
        from skills.derivatives.coinalyze_client import get_coinalyze_predicted_funding
        mock_req.return_value = [{"symbol": "BTCUSDT_PERP.A", "value": -0.05}]
        assert "偏空" in get_coinalyze_predicted_funding("BTC")["sentiment"]


# ────────────────────────────── market_overview ──────────────────────────────
class TestMarketOverview:
    def _cg(self, endpoint, params=None):
        if endpoint == "/global":
            return {"data": {
                "total_market_cap": {"usd": 2.3e12},
                "total_volume": {"usd": 5.5e10},
                "market_cap_percentage": {"btc": 56.3, "eth": 9.5},
                "market_cap_change_percentage_24h_usd": 0.5,
                "active_cryptocurrencies": 17000,
            }}
        if "derivatives/exchanges" in endpoint:
            return [{"open_interest_btc": 1_000_000, "trade_volume_24h_btc": 2_000_000},
                    {"open_interest_btc": 500_000, "trade_volume_24h_btc": 1_000_000}]
        return {}

    # 清掉 Coinalyze 金鑰 → 多空比/爆倉腳走 Binance mock / pending（否則有真金鑰會改用 Coinalyze）
    @patch.dict(os.environ, {"COINALYZE_API_KEY": "your_coinalyze_api_key_here"})
    @patch("skills.market_intel.fng_client.get_crypto_fear_and_greed_index",
           return_value={"latest_value": 26, "latest_sentiment": "Fear"})
    @patch("skills.derivatives.binance_futures.get_binance_long_short_ratio",
           return_value={"latest_ratio": 1.27, "sentiment_label": "散戶溫和偏多"})
    @patch("skills.market_data.market_overview.get_coingecko_coin_price",
           return_value={"bitcoin": {"usd": 64000}})
    def test_overview_aggregation(self, _px, _ls, _fng):
        with patch("skills.market_data.market_overview._coingecko_request", side_effect=self._cg):
            from skills.market_data.market_overview import get_global_derivatives_overview
            r = get_global_derivatives_overview()
        assert r["market"]["btc_dominance_pct"] == 56.3
        # 1.5M BTC OI × 64000
        assert r["derivatives"]["total_open_interest_btc"] == 1_500_000
        assert r["derivatives"]["total_open_interest_usd"] == round(1_500_000 * 64000, 2)
        assert r["long_short_btc"]["latest_ratio"] == 1.27
        assert r["fear_greed"]["value"] == 26
        # Coinalyze 未設金鑰 → pending 而非崩潰
        assert r["liquidations_24h_btc"].get("pending") is True

    @patch("skills.market_data.market_overview.get_coingecko_coin_price", return_value={})
    def test_leg_failure_isolated(self, _px):
        # /global 拋錯不應讓整包崩潰，其餘欄位仍在
        with patch("skills.market_data.market_overview._coingecko_request",
                   side_effect=RuntimeError("boom")):
            from skills.market_data.market_overview import get_global_derivatives_overview
            r = get_global_derivatives_overview()
        assert "error" in r["market"]
        assert "error" in r["derivatives"]
        assert "liquidations_24h_btc" in r  # 其餘鍵仍存在


# ────────────────────────────── liquidation_heatmap ──────────────────────────────
class TestLiquidationHeatmap:
    # 清掉 Coinalyze 金鑰，確保只走 mock 的 Binance OI 路徑（否則有真金鑰時會改用 Coinalyze）
    @patch.dict(os.environ, {"COINALYZE_API_KEY": "your_coinalyze_api_key_here"})
    @patch("skills.market_data.liquidation_heatmap.get_binance_open_interest_history")
    @patch("skills.market_data.liquidation_heatmap._fetch_klines")
    def test_new_longs_cluster_below_price(self, mock_klines, mock_oih):
        import skills.market_data.liquidation_heatmap as H
        # 6 根綠 K（收漲=新多），OI 穩定遞增
        mock_klines.return_value = [[i * 3600000, 100 + i, 101 + i, 99.5 + i, 100.5 + i] for i in range(6)]
        mock_oih.return_value = {"history": [
            {"timestamp": i * 3600000, "open_interest_value_usd": 100 + 10 * i} for i in range(6)]}
        r = H.get_liquidation_heatmap_local("BTC", period="1h", lookback=5)
        assert r["data_available"] is True
        assert r["levels"], "應產生爆倉群落"
        longs = [l for l in r["levels"] if l["long_liq_usd"] > 0]
        assert longs and all(l["price"] < r["current_price"] for l in longs)
        assert all(l["total_usd"] > 0 for l in r["levels"])

    @patch.dict(os.environ, {"COINALYZE_API_KEY": "your_coinalyze_api_key_here"})
    @patch("skills.market_data.liquidation_heatmap.get_binance_open_interest_history",
           return_value={"error": "無歷史持倉數據"})
    @patch("skills.market_data.liquidation_heatmap._fetch_klines")
    def test_oi_unavailable_graceful(self, mock_klines, _oih):
        import skills.market_data.liquidation_heatmap as H
        mock_klines.return_value = [[i * 3600000, 100, 101, 99, 100] for i in range(6)]
        r = H.get_liquidation_heatmap_local("BTC", lookback=5)
        assert r["data_available"] is False
        assert "OI 歷史暫不可用" in r["caveat"]


# ────────────────────────────── etf_flow store ──────────────────────────────
class TestEtfFlowStore:
    def test_store_merge_dedup_and_sort(self, tmp_path):
        import skills.market_intel.etf_flow as E
        store_file = tmp_path / "etf_store.json"
        with patch.object(E, "_STORE_PATH", str(store_file)):
            E._merge_store("BTC", [{"date": "2026-07-10", "net_flow_usd": 1e8},
                                   {"date": "2026-07-09", "net_flow_usd": -5e7}])
            # 同日覆蓋 + 新日併入
            merged = E._merge_store("BTC", [{"date": "2026-07-10", "net_flow_usd": 2e8},
                                            {"date": "2026-07-11", "net_flow_usd": 3e7}])
        dates = [r["date"] for r in merged]
        assert dates == ["2026-07-09", "2026-07-10", "2026-07-11"]  # 排序
        assert next(r for r in merged if r["date"] == "2026-07-10")["net_flow_usd"] == 2e8  # 覆蓋

    def test_no_key_no_store_graceful(self, tmp_path):
        import skills.market_intel.etf_flow as E
        empty = tmp_path / "empty.json"
        with patch.object(E, "_STORE_PATH", str(empty)):
            with patch.dict(os.environ, {"SOSOVALUE_API_KEY": "your_sosovalue_api_key_here"}):
                r = E.get_etf_flows("BTC")
        assert "error" in r and r.get("needs_free_key")

    def test_sosovalue_parses_real_response_shape(self):
        """SoSoValue 實測回傳：{code,data:[{date,total_net_inflow,...}]}（data 為 list）。"""
        import skills.market_intel.etf_flow as E

        class _Resp:
            status_code = 200
            def raise_for_status(self): pass
            def json(self):
                return {"code": 0, "message": "success", "data": [
                    {"date": "2026-07-09", "total_net_inflow": -9.53e7, "total_net_assets": 7.7e10},
                    {"date": "2026-07-10", "total_net_inflow": 9.04e7, "total_net_assets": 7.74e10}]}

        with patch.dict(os.environ, {"SOSOVALUE_API_KEY": "SOSO-real-key"}):
            with patch.object(E, "session_get", return_value=_Resp()):
                rows = E._sosovalue_fetch("BTC")
        assert len(rows) == 2
        assert rows[1]["date"] == "2026-07-10"
        assert rows[1]["net_flow_usd"] == 9.04e7
        assert rows[1]["net_assets_usd"] == 7.74e10


# ────────────────────────────── BTC treasuries ──────────────────────────────
class TestBtcTreasuries:
    def _soso(self, path):
        if path.endswith("/btc-treasuries"):
            return [{"ticker": "MSTR", "name": "Strategy", "list_location": "US"},
                    {"ticker": "MARA", "name": "MARA Holdings", "list_location": "US"}]
        if "MSTR" in path:
            return [{"date": "2026-07-05", "ticker": "MSTR", "btc_holding": "843775", "btc_acq": "-2225", "acq_cost": "-135200000"},
                    {"date": "2026-06-30", "ticker": "MSTR", "btc_holding": "846000", "btc_acq": "-1363", "acq_cost": "-80800000"}]
        if "MARA" in path:
            return [{"date": "2026-07-01", "ticker": "MARA", "btc_holding": "35303", "btc_acq": "300", "acq_cost": "18000000"}]
        return []

    def test_overview_ranks_and_nets(self):
        from skills.market_intel import btc_treasuries as T
        with patch.object(T, "_soso_get", side_effect=self._soso):
            r = T.get_btc_treasuries(top_n=8)
        assert r["tracked"] == 2
        assert r["top_holders"][0]["ticker"] == "MSTR"          # 依持幣排序
        assert r["top_holders"][0]["btc_holding"] == 843775
        # 近期淨：MSTR 兩筆減持 + MARA 一筆增持 → 淨負
        assert r["recent_net_btc"] < 0 and r["recent_bias"] == "整體減持"

    def test_single_company(self):
        from skills.market_intel import btc_treasuries as T
        with patch.object(T, "_soso_get", side_effect=self._soso):
            r = T.get_btc_treasuries("mstr")
        assert r["ticker"] == "MSTR"
        assert r["latest_holding_btc"] == 843775
        assert r["recent_bias"] == "近期減持"        # 最近皆賣出
        assert r["recent_events"][0]["action"] == "減持"

    def test_placeholder_key_graceful(self):
        from skills.market_intel import btc_treasuries as T
        T._cache.clear()
        with patch.dict(os.environ, {"SOSOVALUE_API_KEY": "your_sosovalue_api_key_here"}):
            r = T.get_btc_treasuries()
        assert r.get("needs_free_key") and "error" in r


# ────────────────────────────── grayscale ──────────────────────────────
class TestGrayscale:
    @patch("skills.market_data.grayscale._yahoo_price")
    @patch("skills.market_data.grayscale.get_coingecko_coin_price")
    def test_otc_premium_and_etf_split(self, mock_spot, mock_yahoo):
        from skills.market_data import grayscale as G
        # 現貨價：BCH=$600（其餘 ETF 不計算）
        mock_spot.return_value = {"bitcoin-cash": {"usd": 600}}
        # 市價（Yahoo）：BCHG 折價（市價低於 NAV）
        mock_yahoo.side_effect = lambda tk: {"BCHG": 1.8}.get(tk)
        r = G.get_grayscale_premiums()
        # OTC：BCHG 應有真實折溢價
        bchg = next((t for t in r["otc_trusts"] if t["ticker"] == "BCHG"), None)
        assert bchg and bchg["premium_discount_pct"] is not None
        assert bchg["state"] in ("溢價", "折價")
        # ETF（GBTC/ETHE）分開列、不硬算數字
        etf_tickers = {e["ticker"] for e in r["etf_now"]}
        assert {"GBTC", "ETHE"}.issubset(etf_tickers)

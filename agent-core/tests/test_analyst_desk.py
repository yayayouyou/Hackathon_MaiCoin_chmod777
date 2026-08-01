"""
tests/test_analyst_desk.py — 系統化分析師桌 + 企業增持事件回測 單元測試

測試各層評分、共振引擎、背離偵測、人格權重、財庫事件回測（不需網路）。
"""
from datetime import datetime, timezone
from unittest.mock import patch

from skills.analytics import analyst_desk as D


class TestLayers:
    def test_technical_uptrend_bullish(self):
        closes = [100 + i for i in range(100)]           # 嚴格上升
        L = D._technical_layer(closes)
        assert L["signal"] == "bullish" and L["ok"]

    def test_technical_downtrend_bearish(self):
        closes = [200 - i for i in range(100)]           # 嚴格下降
        L = D._technical_layer(closes)
        assert L["signal"] == "bearish"

    def test_technical_insufficient_data(self):
        L = D._technical_layer([1, 2, 3])
        assert not L["ok"] and L["signal"] == "neutral"

    def test_sentiment_extreme_fear_is_contrarian_bullish(self):
        with patch("skills.market_intel.fng_client.get_crypto_fear_and_greed_index",
                   return_value={"latest_value": 15, "latest_sentiment": "Extreme Fear"}):
            L = D._sentiment_layer()
        assert L["signal"] == "bullish"           # 極度恐懼 → 反向偏多

    def test_sentiment_extreme_greed_is_contrarian_bearish(self):
        with patch("skills.market_intel.fng_client.get_crypto_fear_and_greed_index",
                   return_value={"latest_value": 85, "latest_sentiment": "Extreme Greed"}):
            assert D._sentiment_layer()["signal"] == "bearish"


class TestConfluence:
    def _L(self, layer, signal, score):
        return {"layer": layer, "label": layer, "signal": signal, "strength": abs(int(score * 100)),
                "score": score, "evidence": [], "ok": True}

    def test_net_and_bias(self):
        layers = [self._L("macro", "bullish", 0.5), self._L("flows", "bullish", 0.4),
                  self._L("technical", "bullish", 0.6), self._L("sentiment", "neutral", 0.0),
                  self._L("positioning", "bearish", -0.2)]
        c = D._confluence(layers, D._PERSONA_WEIGHTS["default"])
        assert c["bias"] == "偏多" and c["bull_layers"] == 3 and c["bear_layers"] == 1

    def test_persona_weighting_changes_net(self):
        # 技術偏多、宏觀偏空：李佛摩(重技術)應比達利歐(重宏觀)更偏多
        layers = [self._L("technical", "bullish", 0.8), self._L("macro", "bearish", -0.8),
                  self._L("flows", "neutral", 0.0), self._L("positioning", "neutral", 0.0),
                  self._L("sentiment", "neutral", 0.0)]
        liv = D._confluence(layers, D._PERSONA_WEIGHTS["livermore"])
        dal = D._confluence(layers, D._PERSONA_WEIGHTS["dalio"])
        assert liv["net_score"] > dal["net_score"]

    def test_divergence_price_up_flows_down(self):
        layers = [self._L("technical", "bullish", 0.6), self._L("flows", "bearish", -0.5)]
        divs = D._divergences(layers)
        assert any("資金流偏空" in d or "派發" in d for d in divs)


class TestRunDesk:
    def test_run_desk_structure_and_persona_injection(self):
        # 全部外部呼叫以合成資料替代，驗證整體結構 + 人格帶入
        closes = [100 + i * 0.5 for i in range(200)]
        with patch("skills.market_data.ccxt_fetcher.get_ohlcv",
                   return_value={"candles": [{"close": c} for c in closes], "latest_close": closes[-1]}), \
             patch("skills.market_data.coinglass_scraper.get_coinglass_etf_flow", return_value={"error": "x"}), \
             patch("skills.market_intel.btc_treasuries.get_btc_treasuries", return_value={"error": "x"}), \
             patch("skills.market_intel.sosovalue_extras.get_crypto_sector_indices", return_value={"error": "x"}), \
             patch("skills.derivatives.multi_exchange.get_aggregated_funding_rate", return_value={"error": "x"}), \
             patch("skills.derivatives.coinalyze_client.get_coinalyze_long_short_ratio", return_value={"error": "x"}), \
             patch("skills.market_data.coinglass_scraper.get_coinglass_liquidation_chart", return_value={"error": "x"}), \
             patch("skills.market_intel.fng_client.get_crypto_fear_and_greed_index", return_value={"latest_value": 50}):
            r = D.run_analyst_desk("BTC", persona="livermore")
        assert r["symbol"] == "BTC" and r["persona"] == "livermore"
        assert r["weighting_style"] == "技術/動能優先"
        assert len(r["layers"]) == 5
        assert "bias" in r["confluence"] and r["thesis"] and r["invalidation"] and r["risk_note"]
        # 上升 K 線 → 技術層偏多
        tech = next(L for L in r["layers"] if L["layer"] == "technical")
        assert tech["signal"] == "bullish"


class TestTreasuryBacktest:
    def _klines(self):
        base, day = 1_700_000_000_000, 86_400_000
        # 200 根日線，價格自 100 緩升到 ~300（多頭）
        return [[base + i * day, 100 + i, 101 + i, 99 + i, 100.5 + i, 10.0] for i in range(200)]

    def test_event_study_rising_market(self):
        from skills.analytics import backtester as B
        k = self._klines()

        class _Ex:
            def fetch_ohlcv(self, sym, timeframe, limit): return k
        # 兩筆顯著增持（落在覆蓋範圍內）+ 一筆賣出(應被 min_btc 濾掉)
        def _d(i): return datetime.fromtimestamp(k[i][0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        events = [
            {"date": _d(40), "ticker": "MSTR", "btc_acq": "500", "btc_holding": "800000"},
            {"date": _d(90), "ticker": "MSTR", "btc_acq": "300", "btc_holding": "801000"},
            {"date": _d(120), "ticker": "MSTR", "btc_acq": "-50", "btc_holding": "800800"},  # 賣出→濾掉
        ]
        with patch("skills.market_intel.btc_treasuries._company_history", return_value=events), \
             patch("skills.market_data.ccxt_fetcher._create_exchange", return_value=_Ex()):
            r = B.backtest_treasury_impact(ticker="MSTR", hold_days=7, min_btc=100)
        assert r["events_tested"] == 2           # 賣出事件被排除
        assert r["avg_return_pct"] > 0           # 多頭市場 → 持有 7 日為正
        assert "verdict" in r and "avg_abnormal_return_pct" in r
        assert r["win_rate_pct"] == 100.0

    def test_no_significant_events(self):
        from skills.analytics import backtester as B
        events = [{"date": "2026-01-01", "ticker": "MSTR", "btc_acq": "10"}]  # < min_btc
        with patch("skills.market_intel.btc_treasuries._company_history", return_value=events):
            r = B.backtest_treasury_impact(ticker="MSTR", min_btc=100)
        assert r.get("events_matched") == 0


class TestEventStudyEngine:
    def _klines(self):
        base, day = 1_700_000_000_000, 86_400_000
        return [[base + i * day, 100 + i, 101 + i, 99 + i, 100.5 + i, 10.0] for i in range(200)]

    def test_engine_measures_forward_return(self):
        from skills.analytics import event_study as E
        k = self._klines()

        class _Ex:
            def fetch_ohlcv(self, s, timeframe, limit): return k
        events = [{"ts": k[50][0]}, {"ts": k[100][0]}]
        with patch("skills.market_data.ccxt_fetcher._create_exchange", return_value=_Ex()):
            r = E.run_event_study(events, asset="BTC", hold_days=7, signal="t", signal_label="測試")
        assert r["events_tested"] == 2 and r["win_rate_pct"] == 100.0 and r["avg_return_pct"] > 0
        assert "avg_abnormal_return_pct" in r and "verdict" in r

    def test_engine_dedups_same_candle(self):
        from skills.analytics import event_study as E
        k = self._klines()

        class _Ex:
            def fetch_ohlcv(self, s, timeframe, limit): return k
        events = [{"ts": k[50][0]}, {"ts": k[50][0]}]   # 同一根 K 線 → 只計一次
        with patch("skills.market_data.ccxt_fetcher._create_exchange", return_value=_Ex()):
            r = E.run_event_study(events, asset="BTC", hold_days=7)
        assert r["events_tested"] == 1

    def test_short_direction_flips_sign(self):
        from skills.analytics import event_study as E
        k = self._klines()   # 多頭市場

        class _Ex:
            def fetch_ohlcv(self, s, timeframe, limit): return k
        with patch("skills.market_data.ccxt_fetcher._create_exchange", return_value=_Ex()):
            r = E.run_event_study([{"ts": k[50][0]}], asset="BTC", hold_days=7, direction="short")
        assert r["avg_return_pct"] < 0    # 多頭市場放空 → 負報酬

    def test_unknown_signal_lists_available(self):
        from skills.analytics import event_study as E
        r = E.run_signal_backtest("nonexistent")
        assert "error" in r and "available_signals" in r and "extreme_fear" in r["available_signals"]

    def test_dispatch_to_treasury_adapter(self):
        from skills.analytics import event_study as E
        k = self._klines()

        class _Ex:
            def fetch_ohlcv(self, s, timeframe, limit): return k
        from datetime import datetime, timezone
        def _d(i): return datetime.fromtimestamp(k[i][0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        events = [{"date": _d(60), "ticker": "MSTR", "btc_acq": "500"}]
        with patch("skills.market_intel.btc_treasuries._company_history", return_value=events), \
             patch("skills.market_data.ccxt_fetcher._create_exchange", return_value=_Ex()):
            r = E.run_signal_backtest("treasury_accumulation", ticker="MSTR", threshold=100)
        assert r["signal"] == "treasury_accumulation" and r["events_tested"] == 1


class TestEventStudyRigor:
    def _klines(self):
        base, day = 1_700_000_000_000, 86_400_000
        return [[base + i * day, 100 + i, 101 + i, 99 + i, 100.5 + i, 10.0] for i in range(200)]

    def test_overlapping_events_collapse_to_independent(self):
        from skills.analytics import event_study as E
        k = self._klines()

        class _Ex:
            def fetch_ohlcv(self, s, timeframe, limit): return k
        # 連續 11 天觸發（candle 50..60），hold_days=7 → 應折疊成 2 個獨立事件(50, 57)
        events = [{"ts": k[i][0]} for i in range(50, 61)]
        with patch("skills.market_data.ccxt_fetcher._create_exchange", return_value=_Ex()):
            r = E.run_event_study(events, asset="BTC", hold_days=7, min_events=1)
        assert r["events_tested"] == 2
        assert r["events_clustered_overlapping"] == 9

    def test_min_sample_gate_blocks_conclusion(self):
        from skills.analytics import event_study as E
        k = self._klines()

        class _Ex:
            def fetch_ohlcv(self, s, timeframe, limit): return k
        events = [{"ts": k[50][0]}, {"ts": k[100][0]}]   # n=2 < min 5
        with patch("skills.market_data.ccxt_fetcher._create_exchange", return_value=_Ex()):
            r = E.run_event_study(events, asset="BTC", hold_days=7, min_events=5)
        assert r["low_sample"] is True and r["significant"] is False
        assert "樣本不足" in r["verdict"]
        assert "t_stat" in r and "p_value" in r

    def test_publish_lag_shifts_entry(self):
        from skills.analytics import event_study as E
        k = self._klines()

        class _Ex:
            def fetch_ohlcv(self, s, timeframe, limit): return k
        ev = [{"ts": k[50][0]}]
        with patch("skills.market_data.ccxt_fetcher._create_exchange", return_value=_Ex()):
            r0 = E.run_event_study(ev, asset="BTC", hold_days=7, publish_lag=0, min_events=1)
            r1 = E.run_event_study(ev, asset="BTC", hold_days=7, publish_lag=1, min_events=1)
        # T+1 進場 → entry 高一格（多頭市場），故進場價不同
        assert r0["sample_events"][0]["entry"] != r1["sample_events"][0]["entry"]

    def test_contract_btc_only_rejects_eth(self):
        from skills.analytics import event_study as E
        r = E.run_signal_backtest("mayer_deep", asset="ETH")
        assert "error" in r and "BTC" in r["error"]

    def test_contract_rejects_unaccepted_param(self):
        from skills.analytics import event_study as E
        r = E.run_signal_backtest("extreme_fear", ticker="MSTR")
        assert "error" in r and "ticker" in r["error"]


class TestCompositeBacktest:
    def _klines(self):
        base, day = 1_700_000_000_000, 86_400_000
        return [[base + i * day, 100 + i, 101 + i, 99 + i, 100.5 + i, 10.0] for i in range(200)]

    def _gen_factory(self, k, mapping):
        src = {"publish_lag": 0, "direction": "long", "asset_scope": "crypto-wide", "accepts": ["threshold", "ticker"], "kw": {}}
        def _gen(signal, asset, ticker=None, threshold=None):
            return ([{"ts": k[i][0]} for i in mapping[signal]], signal, src)
        return _gen

    def test_and_intersects_within_window(self):
        from skills.analytics import event_study as E
        k = self._klines()

        class _Ex:
            def fetch_ohlcv(self, *a, **kw): return k
        gen = self._gen_factory(k, {"A": [50, 60, 70], "B": [60, 70, 80]})
        with patch.object(E, "_generate_events", side_effect=gen), \
             patch("skills.market_data.ccxt_fetcher._create_exchange", return_value=_Ex()):
            r = E.run_composite_backtest(["A", "B"], mode="and", window_days=0, min_events=1)
        assert r["events_tested"] == 2          # 交集 60,70（獨立）
        assert r["composite"]["mode"] == "and"

    def test_or_unions(self):
        from skills.analytics import event_study as E
        k = self._klines()

        class _Ex:
            def fetch_ohlcv(self, *a, **kw): return k
        gen = self._gen_factory(k, {"A": [50, 60], "B": [70, 80]})
        with patch.object(E, "_generate_events", side_effect=gen), \
             patch("skills.market_data.ccxt_fetcher._create_exchange", return_value=_Ex()):
            r = E.run_composite_backtest(["A", "B"], mode="or", min_events=1)
        assert r["events_tested"] == 4          # 聯集 50,60,70,80

    def test_and_window_tolerance(self):
        from skills.analytics import event_study as E
        k = self._klines()

        class _Ex:
            def fetch_ohlcv(self, *a, **kw): return k
        # A 在 60、B 在 61（差1天）；window=0 無交集、window=1 有交集
        gen = self._gen_factory(k, {"A": [60], "B": [61]})
        with patch.object(E, "_generate_events", side_effect=gen), \
             patch("skills.market_data.ccxt_fetcher._create_exchange", return_value=_Ex()):
            r0 = E.run_composite_backtest(["A", "B"], mode="and", window_days=0, min_events=1)
            r1 = E.run_composite_backtest(["A", "B"], mode="and", window_days=1, min_events=1)
        assert r0.get("events_tested") is None    # 無交集 → message
        assert r1["events_tested"] == 1

    def test_needs_two_signals(self):
        from skills.analytics import event_study as E
        assert "至少需要 2" in E.run_composite_backtest(["extreme_fear"]).get("error", "")

    def test_bad_mode(self):
        from skills.analytics import event_study as E
        assert "mode" in E.run_composite_backtest(["extreme_fear", "high_funding"], mode="xor").get("error", "")

    def test_mixed_asset_scope_rejected(self):
        from skills.analytics import event_study as E
        # mayer_deep 是 BTC-only，用 ETH → 應在產生階段報錯
        r = E.run_composite_backtest(["mayer_deep", "extreme_fear"], asset="ETH")
        assert "error" in r and "BTC" in r["error"]


class TestBacktestHoleFixes:
    """守衛對抗式找漏洞修掉的問題（H2 對稱交集 / H3 hold_days / M1 window / L2 direction）。"""
    def _mock_gen(self, es, mapping):
        DAY = 86_400_000
        def src(): return {"direction": "long", "asset_scope": "crypto-wide", "publish_lag": 0, "accepts": ["threshold"], "kw": {}}
        def gen(sig, asset, ticker=None, threshold=None):
            return ([{"ts": d * DAY, "label": "x", "magnitude": 1.0} for d in mapping[sig]], sig, src())
        return gen

    def test_and_transitive_and_order_independent(self):
        from skills.analytics import event_study as es
        DAY = 86_400_000
        with patch.object(es, "_generate_events", side_effect=self._mock_gen(es, {"A": [100], "B": [101], "C": [99]})), \
             patch.object(es, "run_event_study", side_effect=lambda events, **kw: {"days": sorted(int(e["ts"]) // DAY for e in events)}):
            # B-C 相距 2 > window1 → 無共振，且四種順序一致
            for order in (["A", "B", "C"], ["B", "A", "C"], ["C", "A", "B"], ["A", "C", "B"]):
                assert es.run_composite_backtest(order, mode="and", window_days=1)["days"] == []
            # window2（span 2）→ 共振於群最早日 99，順序一致
            assert es.run_composite_backtest(["A", "B", "C"], mode="and", window_days=2)["days"] == [99]
            assert es.run_composite_backtest(["C", "B", "A"], mode="and", window_days=2)["days"] == [99]

    def test_hold_days_bad_type_returns_error(self):
        from skills.analytics import event_study as es
        for hd in ("7x", -3, 0):
            assert "error" in es.run_event_study([{"ts": 1}], hold_days=hd)
        # 浮點 7.5 應被容忍轉為 7（不崩、meta 記為整數 7）
        assert es.run_event_study([], hold_days=7.5)["hold_days"] == 7

    def test_window_days_bad_returns_error(self):
        from skills.analytics import event_study as es
        with patch.object(es, "_generate_events", side_effect=self._mock_gen(es, {"A": [1], "B": [1]})):
            assert "error" in es.run_composite_backtest(["A", "B"], window_days="x")
            assert "error" in es.run_composite_backtest(["A", "B"], window_days=-1)

    def test_engine_direction_normalized(self):
        from skills.analytics import event_study as es
        # 純引擎收到非法 direction 應正規化成 long（meta 一致）
        r = es.run_event_study([], direction="up")
        assert r["direction"] == "long"


class TestValidationDepth:
    """#1 回測驗證深度：Monte Carlo 排列檢定 + bootstrap 信賴區間（借鏡 Vibe-Trading）。"""
    def _noisy_klines(self, n=250):
        # 決定性偽隨機（無 random）：正弦疊加，讓報酬有分布可供排列/bootstrap
        base, day = 1_700_000_000_000, 86_400_000
        rows = []
        px = 100.0
        for i in range(n):
            px *= 1 + 0.02 * ((i * 7 % 11) - 5) / 10.0
            rows.append([base + i * day, px, px * 1.01, px * 0.99, px, 10.0])
        return rows

    def test_permutation_and_ci_present(self):
        from skills.analytics import event_study as E
        k = self._noisy_klines()

        class _Ex:
            def fetch_ohlcv(self, *a, **kw): return k
        events = [{"ts": k[i][0]} for i in range(20, 200, 15)]   # 夠多獨立事件
        with patch("skills.market_data.ccxt_fetcher._create_exchange", return_value=_Ex()):
            r = E.run_event_study(events, asset="BTC", hold_days=5, min_events=3)
        assert r["permutation_p"] is not None and 0.0 <= r["permutation_p"] <= 1.0
        assert isinstance(r["abnormal_ci90_pct"], list) and r["abnormal_ci90_pct"][0] <= r["abnormal_ci90_pct"][1]

    def test_permutation_is_deterministic(self):
        from skills.analytics import event_study as E
        k = self._noisy_klines()

        class _Ex:
            def fetch_ohlcv(self, *a, **kw): return k
        events = [{"ts": k[i][0]} for i in range(20, 200, 15)]
        with patch("skills.market_data.ccxt_fetcher._create_exchange", return_value=_Ex()):
            r1 = E.run_event_study(events, asset="BTC", hold_days=5, min_events=3)
            r2 = E.run_event_study(events, asset="BTC", hold_days=5, min_events=3)
        assert r1["permutation_p"] == r2["permutation_p"]           # 固定種子 → 可重現
        assert r1["abnormal_ci90_pct"] == r2["abnormal_ci90_pct"]

    def test_permutation_governs_significance(self):
        from skills.analytics import event_study as E
        k = self._noisy_klines()

        class _Ex:
            def fetch_ohlcv(self, *a, **kw): return k
        events = [{"ts": k[i][0]} for i in range(20, 200, 15)]
        with patch("skills.market_data.ccxt_fetcher._create_exchange", return_value=_Ex()):
            r = E.run_event_study(events, asset="BTC", hold_days=5, min_events=3)
        # 顯著性須與排列檢定 p 一致（排列 p 為主要依據）
        assert r["significant"] == (r["permutation_p"] < 0.05)


class TestPriceFactors:
    """#5 經典價量 alpha 因子事件源：動能突破 / RSI 超賣 / 波動突增。"""
    def _factor_klines(self):
        base, day = 1_700_000_000_000, 86_400_000
        rows, px = [], 100.0
        for i in range(300):
            # 前段緩漲觸發動能，中段插入超賣與波動事件
            drift = 0.03 if 40 <= i <= 70 else (-0.05 if i in (120, 121, 122) else 0.002)
            spike = 4.0 if i in (150, 180) else 1.0
            hi = px * (1 + 0.01 * spike)
            lo = px * (1 - 0.01 * spike)
            rows.append([base + i * day, px, hi, lo, px, 10.0])
            px *= 1 + drift
        return rows

    def test_factor_signals_registered(self):
        from skills.analytics import event_study as E
        for s in ("momentum_breakout", "oversold_rsi", "vol_spike"):
            assert s in E.SIGNALS

    def test_momentum_factor_generates_events(self):
        from skills.analytics import event_study as E
        oh = {"candles": [{"timestamp": r[0], "open": r[1], "high": r[2],
                           "low": r[3], "close": r[4], "vol": r[5]} for r in self._factor_klines()]}
        with patch("skills.market_data.ccxt_fetcher.get_ohlcv", return_value=oh):
            events, label = E._adapt_price_factor(asset="BTC", factor="momentum", threshold=10.0)
        assert len(events) >= 1 and "動能" in label

    def test_vol_spike_factor_detects_spike(self):
        from skills.analytics import event_study as E
        oh = {"candles": [{"timestamp": r[0], "open": r[1], "high": r[2],
                           "low": r[3], "close": r[4], "vol": r[5]} for r in self._factor_klines()]}
        with patch("skills.market_data.ccxt_fetcher.get_ohlcv", return_value=oh):
            events, label = E._adapt_price_factor(asset="BTC", factor="vol_spike", threshold=2.0)
        assert len(events) >= 1 and "波動" in label

    def test_price_factor_per_asset_gate(self):
        from skills.analytics import event_study as E
        r = E.run_signal_backtest("momentum_breakout", asset="DOGE")
        assert "error" in r and ("BTC" in r["error"] or "ETH" in r["error"])


class TestRunCard:
    """#6 run_card 可重現性紀錄。"""
    def test_same_config_same_run_id(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RUN_CARDS_DIR", str(tmp_path))
        import importlib
        from skills.analytics import run_card
        importlib.reload(run_card)
        params = {"signal": "vol_spike", "asset": "BTC", "hold_days": 7}
        res = {"events_tested": 10, "avg_abnormal_return_pct": -4.3, "permutation_p": 0.012, "significant": True}
        a = run_card.write_run_card("signal_backtest", params, res)
        b = run_card.write_run_card("signal_backtest", params, res)
        assert a["run_id"] == b["run_id"] and a["result_hash"] == b["result_hash"]
        assert (tmp_path / f"{a['run_id']}.json").exists()

    def test_diff_params_diff_id(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RUN_CARDS_DIR", str(tmp_path))
        import importlib
        from skills.analytics import run_card
        importlib.reload(run_card)
        res = {"events_tested": 10}
        a = run_card.write_run_card("signal_backtest", {"signal": "vol_spike", "hold_days": 7}, res)
        b = run_card.write_run_card("signal_backtest", {"signal": "vol_spike", "hold_days": 14}, res)
        assert a["run_id"] != b["run_id"]

    def test_result_hash_detects_drift(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RUN_CARDS_DIR", str(tmp_path))
        import importlib
        from skills.analytics import run_card
        importlib.reload(run_card)
        params = {"signal": "vol_spike", "hold_days": 7}
        a = run_card.write_run_card("signal_backtest", params, {"avg_abnormal_return_pct": -4.3})
        b = run_card.write_run_card("signal_backtest", params, {"avg_abnormal_return_pct": -2.1})
        assert a["run_id"] == b["run_id"] and a["result_hash"] != b["result_hash"]   # 同設定、結果漂移


class TestOhlcvGuard:
    """#3 OHLCV 髒資料閘門。"""
    def test_drops_invalid_bars(self):
        from skills.market_data.ohlcv_guard import clean_ohlcv
        dirty = [
            [1, 10, 12, 9, 11, 5],      # ok
            [2, 10, 8, 9, 11, 5],       # high<low
            [3, 10, 12, 9, 0, 5],       # close=0
            [4, 10, 12, 13, 11, 5],     # low>close
            [5, 20, 22, 19, 21, 5],     # ok
            [6, "x", 1, 1, 1, 1],       # 非數值
        ]
        clean, dropped = clean_ohlcv(dirty)
        assert len(clean) == 2 and dropped == 4

    def test_empty_and_none_safe(self):
        from skills.market_data.ohlcv_guard import clean_ohlcv
        assert clean_ohlcv([]) == ([], 0)
        assert clean_ohlcv(None) == ([], 0)

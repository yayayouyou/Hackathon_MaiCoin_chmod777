"""黃金資料層測試 — 代幣化報價、總經驅動(FRED/AV/無Key)、綜合簡報(相關性/溢價/容錯)、schema 接線。"""
import json
import pytest
from unittest.mock import patch, MagicMock

from skills.gold import tokenized_gold as tg
from skills.gold import macro as gm
from skills.gold import gold_analysis as ga
from skills.gold.schemas import GOLD_TOOLS, GOLD_TOOL_MAP


# ── 1) 代幣化報價 ─────────────────────────
class TestTokenizedGold:
    def _fake_cg(self, paxg=4000.0, xaut=3990.0):
        return {"pax-gold": {"usd": paxg, "usd_24h_change": -0.6, "usd_24h_vol": 9e7, "usd_market_cap": 1.8e9},
                "tether-gold": {"usd": xaut, "usd_24h_change": -0.5, "usd_24h_vol": 1.1e8, "usd_market_cap": 2.5e9}}

    def test_price_structure_and_spread(self):
        with patch.object(tg, "_coingecko_request", return_value=self._fake_cg(4000.0, 3990.0)):
            r = tg.get_gold_price()
        assert set(r["tokens"]) == {"PAXG", "XAUT"}
        assert r["tokens"]["PAXG"]["price"] == 4000.0
        # 價差 = (4000-3990)/均值*100 ≈ 0.2504%
        assert abs(r["paxg_xaut_spread_pct"] - 0.2504) < 0.01

    def test_error_propagates_as_dict(self):
        with patch.object(tg, "_coingecko_request", side_effect=RuntimeError("boom")):
            r = tg.get_gold_price()
        assert "error" in r

    def test_empty_response(self):
        with patch.object(tg, "_coingecko_request", return_value={}):
            r = tg.get_gold_price()
        assert "error" in r


# ── 2) 總經驅動 ─────────────────────────
def _obs(values):
    """values 由新到舊；回傳 FRED observations 格式（desc）。"""
    return {"observations": [{"date": f"2026-07-{(i % 28) + 1:02d}", "value": str(v)} for i, v in enumerate(values)]}


class TestMacro:
    def test_no_key_graceful(self, monkeypatch):
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        monkeypatch.delenv("ALPHAVANTAGE_API_KEY", raising=False)
        r = gm.get_gold_macro_context()
        assert r["available"] is False
        assert "how_to_enable" in r        # 給啟用指引，不報錯

    def test_fred_path_scores_tailwind(self, monkeypatch):
        monkeypatch.setenv("FRED_API_KEY", "x")

        def fake_fetch(url, params=None, expect_keys=None, **kw):
            sid = params["series_id"]
            if sid == "DFII10":       # 實質利率下降 → 對黃金順風
                return _obs([1.9] + [2.0] * 21 + [2.2] * 8)
            if sid == "DTWEXBGS":     # 美元指數下降 → 順風
                return _obs([118.0] + [119.0] * 21 + [121.0] * 8)
            if sid == "DFF":          # 政策利率持平 → 中性
                return _obs([4.33] * 30)
            if sid == "CPIAUCSL":     # CPI 走高且『加速』(YoY 6.5%>前月 5.4%) → 順風
                return _obs([326, 322, 318.5, 315.5, 313, 311, 309.5, 308.5, 308, 307.5, 307, 306.5, 306, 305.5])
            if sid == "GOLDPMGBD228NLBM":
                return _obs([4000.0] * 30)
            return _obs([1.0] * 30)

        with patch.object(gm, "fetch_json", side_effect=fake_fetch):
            r = gm.get_gold_macro_context()
        assert r["available"] is True and r["source"] == "FRED"
        assert r["drivers"]["DFII10"]["gold_impact"] == "gold_tailwind"
        assert r["drivers"]["DFII10"]["direction"] == "falling"
        assert r["drivers"]["DTWEXBGS"]["gold_impact"] == "gold_tailwind"
        assert r["macro_score"] >= 2 and r["gold_macro_read"] == "tailwind"
        assert r["london_gold_pm_usd_oz"] is None      # LBMA 定盤系列已停更、不再拉取

    def test_fred_headwind(self, monkeypatch):
        monkeypatch.setenv("FRED_API_KEY", "x")

        def fake_fetch(url, params=None, expect_keys=None, **kw):
            sid = params["series_id"]
            if sid == "DFII10":       # 實質利率上升 → 逆風
                return _obs([2.3] + [2.1] * 21 + [1.9] * 8)
            if sid == "DTWEXBGS":     # 美元走強 → 逆風
                return _obs([122.0] + [120.0] * 21 + [118.0] * 8)
            if sid == "DFF":
                return _obs([4.33] * 30)
            if sid == "CPIAUCSL":     # CPI 走低 → 逆風
                return _obs([310, 311, 312, 313, 314, 315, 316, 317, 318, 319, 320, 321, 322, 323])
            return _obs([1.0] * 30)

        with patch.object(gm, "fetch_json", side_effect=fake_fetch):
            r = gm.get_gold_macro_context()
        assert r["drivers"]["DFII10"]["gold_impact"] == "gold_headwind"
        assert r["macro_score"] <= -2 and r["gold_macro_read"] == "headwind"

    def test_per_series_resilience(self, monkeypatch):
        # 單一系列停更(400)不該讓整包歸零：DFF 失敗，其餘存活 → available True + 記錄失敗
        monkeypatch.setenv("FRED_API_KEY", "x")
        from skills._http import FetchError

        def fake_fetch(url, params=None, expect_keys=None, **kw):
            sid = params["series_id"]
            if sid == "DFF":
                raise FetchError("HTTP 400 @ api.stlouisfed.org")
            if sid == "DFII10":
                return _obs([1.9] + [2.0] * 21 + [2.2] * 8)   # 順風
            return _obs([1.0] * 30)

        with patch.object(gm, "fetch_json", side_effect=fake_fetch):
            r = gm.get_gold_macro_context()
        assert r["available"] is True
        assert "DFF" not in r["drivers"]                       # 失敗的系列被跳過
        assert any("DFF" in f for f in (r["partial_failures"] or []))

    def test_all_series_fail_reports_error(self, monkeypatch):
        monkeypatch.setenv("FRED_API_KEY", "x")
        from skills._http import FetchError
        with patch.object(gm, "fetch_json", side_effect=FetchError("HTTP 400")):
            r = gm.get_gold_macro_context()
        assert r["available"] is False
        assert "detail" in r                                   # 明確回報失敗、非誤報「未設定」

    def test_insufficient_data_when_few_drivers(self, monkeypatch):
        # 只有 1 個驅動成功(<3/4) → 不可用半套資料充當有把握的 'mixed'
        monkeypatch.setenv("FRED_API_KEY", "x")
        from skills._http import FetchError

        def fake(url, params=None, expect_keys=None, **kw):
            if params["series_id"] == "DFII10":
                return _obs([1.9] + [2.0] * 21 + [2.2] * 8)
            raise FetchError("HTTP 400")

        with patch.object(gm, "fetch_json", side_effect=fake):
            r = gm.get_gold_macro_context()
        assert r["available"] is True
        assert r["gold_macro_read"] == "insufficient_data"
        assert r["drivers_ok"] < 3

    def test_av_fallback_skips_dot_value(self, monkeypatch):
        # AV 最新月常為 "." → 應跳過取下一筆有效值，而非整個丟棄
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "y")

        def fake(url, params=None, **kw):
            return {"data": [{"date": "2026-07-01", "value": "."},
                             {"date": "2026-06-01", "value": "4.2"}]}

        with patch.object(gm, "fetch_json", side_effect=fake):
            r = gm.get_gold_macro_context()
        assert r["drivers"]["treasury_10y"]["value"] == 4.2

    def test_av_query_raises_on_ratelimit(self, monkeypatch):
        # AV 限流是 HTTP 200 帶 Information → 應拋 FetchError，不被當『無資料』
        from skills._http import FetchError
        with patch.object(gm, "fetch_json", return_value={"Information": "25 requests per day"}):
            with pytest.raises(FetchError):
                gm._av_query("TREASURY_YIELD", "y")

    def test_cpi_yoy_computation(self, monkeypatch):
        monkeypatch.setenv("FRED_API_KEY", "x")
        # 最新 315 / 12個月前 300 → YoY = +5.0%
        vals = [315, 314.5, 314, 313, 312, 311, 310, 309, 308, 307, 306, 305, 300, 299]
        with patch.object(gm, "fetch_json", return_value=_obs(vals)):
            c = gm._cpi_yoy("x")
        assert abs(c["value"] - 5.0) < 0.01

    def test_alphavantage_fallback_when_no_fred(self, monkeypatch):
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "y")

        def fake_fetch(url, params=None, **kw):
            return {"data": [{"date": "2026-06-01", "value": "4.2"}]}

        with patch.object(gm, "fetch_json", side_effect=fake_fetch):
            r = gm.get_gold_macro_context()
        assert r["source"] == "AlphaVantage(fallback)"
        assert r["drivers"]["treasury_10y"]["value"] == 4.2
        assert any("FRED_API_KEY" in c for c in r["caveats"])


# ── 3) 綜合簡報 ─────────────────────────
class _FakeEx:
    """gold 與 btc 依給定 close 序列回傳 OHLCV。"""
    def __init__(self, gold_closes, btc_closes):
        self.g, self.b = gold_closes, btc_closes

    def fetch_ohlcv(self, symbol, timeframe="1d", limit=1000):
        closes = self.g if symbol.upper().startswith(("PAXG", "XAUT")) else self.b
        return [[1_700_000_000_000 + i * 86400000, c, c, c, c, 1.0] for i, c in enumerate(closes)]


class TestGoldAnalysis:
    def _patch_parts(self, price=None, macro=None):
        price = price or {"tokens": {"PAXG": {"price": 4010.0}}}
        macro = macro or {"available": False}
        return (patch.object(ga, "get_gold_price", return_value=price),
                patch.object(ga, "get_gold_macro_context", return_value=macro))

    def test_correlation_risk_on_coupling(self):
        # 黃金與 BTC 同向 → 高正相關 → risk_on_coupling
        gold = [100 * (1 + 0.01 * (i % 5 - 2)) for i in range(31)]
        btc = [50000 * (1 + 0.01 * (i % 5 - 2)) for i in range(31)]
        pp, pm = self._patch_parts()
        with pp, pm, patch("skills.market_data.ccxt_fetcher._create_exchange", return_value=_FakeEx(gold, btc)):
            r = ga.analyze_gold_market(corr_days=30)
        c = r["gold_btc_correlation"]
        assert c["available"] and c["correlation"] > 0.8 and c["regime"] == "risk_on_coupling"

    def test_correlation_safe_haven_divergence(self):
        # 黃金與 BTC 反向 → 負相關 → safe_haven_divergence
        gold = [100 * (1 + 0.01 * (i % 5 - 2)) for i in range(31)]
        btc = [50000 * (1 - 0.01 * (i % 5 - 2)) for i in range(31)]
        pp, pm = self._patch_parts()
        with pp, pm, patch("skills.market_data.ccxt_fetcher._create_exchange", return_value=_FakeEx(gold, btc)):
            r = ga.analyze_gold_market(corr_days=30)
        assert r["gold_btc_correlation"]["regime"] == "safe_haven_divergence"

    def test_premium_computed_from_macro_fix(self):
        price = {"tokens": {"PAXG": {"price": 4040.0}}}
        macro = {"available": True, "london_gold_pm_usd_oz": {"value": 4000.0, "as_of": "2026-07-09"}}
        pp, pm = self._patch_parts(price, macro)
        varying = [100 + (i % 3) for i in range(31)]   # 非常數，避免 corrcoef 除以零警告
        with pp, pm, patch("skills.market_data.ccxt_fetcher._create_exchange", return_value=_FakeEx(varying, varying)):
            r = ga.analyze_gold_market()
        assert abs(r["tokenized_premium"]["premium_pct"] - 1.0) < 0.001   # (4040-4000)/4000 = 1%

    def test_graceful_when_correlation_fails(self):
        pp, pm = self._patch_parts()
        with pp, pm, patch("skills.market_data.ccxt_fetcher._create_exchange", side_effect=Exception("net down")):
            r = ga.analyze_gold_market()
        assert r["gold_btc_correlation"]["available"] is False   # 相關性掛掉但整體不崩
        assert "price" in r and "caveat" in r


# ── 4) Schema 接線 ─────────────────────────
class TestSchemas:
    def test_three_tools_present(self):
        names = {t["function"]["name"] for t in GOLD_TOOLS}
        assert names == {"get_gold_price", "get_gold_macro_context", "analyze_gold_market"}

    def test_tool_map_matches_schemas(self):
        assert set(GOLD_TOOL_MAP) == {t["function"]["name"] for t in GOLD_TOOLS}

    def test_registered_in_all_tools_and_callables(self):
        from agent.prompts import ALL_TOOLS
        from agent.ollama_agent import TOOL_CALLABLES
        for n in GOLD_TOOL_MAP:
            assert any(t["function"]["name"] == n for t in ALL_TOOLS)
            assert n in TOOL_CALLABLES and callable(TOOL_CALLABLES[n])

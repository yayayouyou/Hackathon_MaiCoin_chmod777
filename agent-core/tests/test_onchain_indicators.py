"""本地鏈上指標 (AHR999 / Mayer Multiple) 計算單元測試"""
from unittest.mock import patch

import pytest

from skills.market_data import onchain_indicators as oi

_BASE_TS = 1700000000000  # 固定起點（避免依賴當前時間）


def _series(prices):
    return {"prices": [[_BASE_TS + i * 86400000, float(p)] for i, p in enumerate(prices)]}


@patch("skills.market_data.onchain_indicators._coingecko_request")
def test_mayer_constant_price_equals_one(mock_cg):
    mock_cg.return_value = _series([100.0] * 260)
    out = oi.get_mayer_multiple_local(output_days=10)
    assert len(out) == 10
    # 常數價 → 現價 = SMA200 → Mayer = 1
    assert all(abs(x["index"] - 1.0) < 1e-9 for x in out)
    assert all(k in out[-1] for k in ("timestamp", "index", "price"))


@patch("skills.market_data.onchain_indicators._coingecko_request")
def test_mayer_rising_series_above_one(mock_cg):
    # 線性上升 → 現價高於自身 200 日均線 → Mayer > 1
    mock_cg.return_value = _series([100 + i for i in range(260)])
    out = oi.get_mayer_multiple_local(output_days=5)
    assert out[-1]["index"] > 1.0


@patch("skills.market_data.onchain_indicators._coingecko_request")
def test_ahr999_shape_and_positive(mock_cg):
    mock_cg.return_value = _series([50000.0] * 260)
    out = oi.get_ahr999_local(output_days=8)
    assert len(out) == 8
    assert all(k in out[-1] for k in ("date", "ahr999", "value"))
    assert out[-1]["ahr999"] > 0            # 應為正數
    assert out[-1]["value"] == 50000.0


def test_exp_growth_valuation_monotonic():
    # 幣齡越大，指數估值越高
    assert oi._exp_growth_valuation(6000) > oi._exp_growth_valuation(3000)


@patch("skills.market_data.onchain_indicators._coingecko_request")
def test_ahr999_matches_manual_formula(mock_cg):
    """對單一窗口手算 AHR999，確認公式實作正確。"""
    import math
    prices = [40000.0] * 199 + [60000.0]   # 剛好 200 天
    mock_cg.return_value = _series(prices)
    out = oi.get_ahr999_local(output_days=1)
    row = out[-1]
    gm = math.exp((199 * math.log(40000.0) + math.log(60000.0)) / 200)
    age = oi._coin_age_days(_BASE_TS + 199 * 86400000)
    expval = oi._exp_growth_valuation(age)
    expected = (60000.0 / gm) * (60000.0 / expval)
    assert abs(row["ahr999"] - round(expected, 4)) < 1e-3

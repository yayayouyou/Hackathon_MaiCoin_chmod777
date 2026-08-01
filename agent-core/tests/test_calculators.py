"""
tests/test_calculators.py

計算機技能單元測試（純數學，確定性）
"""

import pytest
from skills.calculators import (
    calculate_dca,
    calculate_position_size,
    calculate_pnl,
    calculate_average_down,
    calculate_target_sell_price,
)


class TestDCA:
    def test_basic_no_fee(self):
        r = calculate_dca(1000, [100, 100], fee_rate=0)
        assert r["periods"] == 2
        assert r["total_invested"] == 2000
        assert r["total_units"] == 20
        assert r["average_cost"] == 100

    def test_with_current_price_profit(self):
        r = calculate_dca(1000, [100, 100], fee_rate=0, current_price=200)
        assert r["current_value"] == 4000
        assert r["pnl"] == 2000
        assert r["roi_pct"] == 100
        assert "lump_sum_comparison" in r

    def test_fee_reduces_units(self):
        r = calculate_dca(1000, [100], fee_rate=0.01)
        # 1% 手續費：實際只買到 990/100 = 9.9 顆
        assert r["total_units"] == 9.9
        assert r["total_fees"] == 10

    def test_invalid_inputs(self):
        assert "error" in calculate_dca(0, [100])
        assert "error" in calculate_dca(1000, [])
        assert "error" in calculate_dca(1000, [100, -5])


class TestPositionSize:
    def test_basic(self):
        r = calculate_position_size(100000, 2, 1000000, 900000)
        assert r["max_loss_if_stopped"] == 2000
        assert r["suggested_units"] == 0.02
        assert r["position_value"] == 20000

    def test_capped_by_balance(self):
        r = calculate_position_size(1000, 50, 100, 99)
        # 風險反推部位遠大於本金 → 現貨受本金限制
        assert r["position_value"] <= 1000
        assert "⚠️" in r["note"]

    def test_stop_above_entry_error(self):
        assert "error" in calculate_position_size(100000, 2, 1000, 1100)

    def test_bad_risk_pct(self):
        assert "error" in calculate_position_size(100000, 0, 1000, 900)
        assert "error" in calculate_position_size(100000, 150, 1000, 900)


class TestPnL:
    def test_long_profit(self):
        r = calculate_pnl(100, 110, 1, side="buy", fee_rate=0.001)
        assert r["gross_pnl"] == 10
        assert r["net_pnl"] == 9.79
        assert r["roi_pct"] == 9.79
        assert r["breakeven_price"] == 100.2

    def test_short_profit(self):
        r = calculate_pnl(100, 90, 1, side="short", fee_rate=0)
        assert r["gross_pnl"] == 10
        assert r["net_pnl"] == 10

    def test_invalid(self):
        assert "error" in calculate_pnl(0, 110, 1)
        assert "error" in calculate_pnl(100, 110, 0)
        assert "error" in calculate_pnl(100, 110, 1, side="wtf")


class TestAverageDown:
    def test_by_amount(self):
        r = calculate_average_down(1, 100, 80, add_amount=80, fee_rate=0)
        assert r["after"]["units"] == 2
        assert r["after"]["avg_cost"] == 90
        assert r["avg_cost_drop_pct"] == 10

    def test_by_units(self):
        r = calculate_average_down(1, 100, 50, add_units=1, fee_rate=0)
        assert r["after"]["units"] == 2
        assert r["after"]["avg_cost"] == 75

    def test_requires_one_of(self):
        assert "error" in calculate_average_down(1, 100, 80)


class TestNumericCoercion:
    """LLM 常把數字傳成字串/帶逗號/樣板佔位；工具必須容錯，不可拋 TypeError。"""

    def test_string_numbers(self):
        r = calculate_position_size("100000", "1", "1000000", "900000")
        assert "error" not in r
        assert r["suggested_units"] == 0.01
        assert r["position_value"] == 10000

    def test_placeholder_returns_clean_error(self):
        # 這正是實測時模型傳的壞值，過去會拋 TypeError
        r = calculate_position_size(100000, 1, "{{current_btc_price}}", 900000)
        assert "error" in r and "entry_price" in r["error"]

    def test_comma_and_currency_strings(self):
        r = calculate_pnl("1,000,000", "1,100,000", "0.5", fee_rate=0)
        assert "error" not in r
        assert r["net_pnl"] == 50000

    def test_dca_string_prices(self):
        r = calculate_dca("1000", ["1,000,000", "950000"], fee_rate=0)
        assert "error" not in r
        assert r["periods"] == 2


class TestTargetSell:
    def test_no_fee(self):
        r = calculate_target_sell_price(100, 10, fee_rate=0)
        assert r["target_sell_price"] == 110
        assert r["required_price_rise_pct"] == 10

    def test_with_fee_higher(self):
        r = calculate_target_sell_price(100, 10, fee_rate=0.001)
        # 含來回手續費，需賣得比 110 略高
        assert r["target_sell_price"] > 110
        assert "error" not in r

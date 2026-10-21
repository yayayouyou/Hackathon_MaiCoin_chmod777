"""
tests/test_execution.py

交易執行與底層物理風控鎖單元測試
=====================================
"""

import pytest
from unittest.mock import patch, MagicMock
from skills.execution.risk_guard import validate_order
from skills.execution.order_executor import create_order, cancel_order, cancel_all_orders

# ──────────────────────────────────────────────
#  物理風控鎖安全規則校驗測試 (Risk Guard)
# ──────────────────────────────────────────────

class TestRiskGuard:
    def test_validate_order_success_twd(self):
        # 買入 0.01 BTC @ 2,000,000 TWD = 20,000 TWD (符合上限 50,000)
        passed, reason = validate_order(
            market="BTC/TWD",
            side="buy",
            volume=0.01,
            price=2000000.0,
            ord_type="limit",
            latest_ticker_price=2000000.0
        )
        assert passed is True
        assert "通過" in reason

    def test_validate_order_limit_exceeded_twd(self):
        # 買入 0.03 BTC @ 2,000,000 TWD = 60,000 TWD (超過上限 50,000)
        passed, reason = validate_order(
            market="BTC/TWD",
            side="buy",
            volume=0.03,
            price=2000000.0,
            ord_type="limit",
            latest_ticker_price=2000000.0
        )
        assert passed is False
        assert "超過上限" in reason

    def test_validate_order_limit_exceeded_usd(self):
        # 買入 0.5 ETH @ 3,100 USD = 1,550 USD (超過上限 1500 USD)
        passed, reason = validate_order(
            market="ETH/USDT",
            side="buy",
            volume=0.5,
            price=3100.0,
            ord_type="limit",
            latest_ticker_price=3100.0
        )
        assert passed is False
        assert "超過上限" in reason

    def test_validate_order_sell_price_deviation_too_high(self):
        # 委託賣出價 1,900,000 TWD，但市場價 2,000,000 TWD (偏離 5%，超過 3%)
        passed, reason = validate_order(
            market="BTC/TWD",
            side="sell",
            volume=0.01,
            price=1900000.0,
            ord_type="limit",
            latest_ticker_price=2000000.0
        )
        assert passed is False
        assert "偏離度" in reason

    @pytest.mark.parametrize("price", [1900000.0, 2100000.0])
    def test_validate_order_buy_price_deviation_allowed(self, price):
        # 買單掛低價（等回檔）或掛高價（願意追價）都不擋偏離度
        passed, reason = validate_order(
            market="BTC/TWD",
            side="buy",
            volume=0.01,
            price=price,
            ord_type="limit",
            latest_ticker_price=2000000.0
        )
        assert passed is True, reason

    def test_validate_order_exotic_quote_fail_closed(self):
        # H2: ethbtc（BTC 計價）以前被當 USD、上限失效約 5 個量級；現無安全匯率 → 直接拒
        passed, reason = validate_order(
            market="ETH/BTC", side="buy", volume=100, price=0.05,
            ord_type="limit", latest_ticker_price=0.05)
        assert passed is False
        assert ("計價幣別" in reason) or ("拒絕" in reason)

    def test_validate_order_nan_fails_closed(self):
        # M1: NaN 在比較中恆為 False，以前 fail-open 穿過所有檢查
        p1, _ = validate_order("BTC/TWD", "buy", float("nan"), 2000000.0, "limit", 2000000.0)
        assert p1 is False
        p2, _ = validate_order("BTC/TWD", "buy", 0.01, float("nan"), "limit", float("nan"))
        assert p2 is False

    def test_validate_order_usdt_converted_to_twd(self):
        # H2: 1300 USDT × 35 = 45,500 TWD < 50,000 → 通過（單位一致）
        p1, _ = validate_order("ETH/USDT", "buy", 0.5, 2600.0, "limit", 2600.0)
        assert p1 is True
        # 1600 USDT × 35 = 56,000 TWD > 50,000 → 攔截
        p2, r2 = validate_order("ETH/USDT", "buy", 0.5, 3200.0, "limit", 3200.0)
        assert p2 is False and "超過上限" in r2


# ──────────────────────────────────────────────
#  交易執行 Mock 測試
# ──────────────────────────────────────────────

# get_max_tickers(market) 回傳的是「扁平的單一 ticker dict」，不是 {market: {...}} 巢狀結構。
# 這正是先前 order_executor 解析錯誤的來源，測試改用真實 shape 才有意義。
REAL_MAX_TICKER = {
    "market": "btctwd",
    "at": 1783482595,
    "buy": "2000000.0",
    "sell": "2001000.0",
    "open": "1990000.0",
    "low": "1980000.0",
    "high": "2010000.0",
    "last": "2000500.0",
    "vol": "50.5",
}


@pytest.fixture(autouse=True)
def _arm_live_for_tests(tmp_path, monkeypatch):
    """實盤下單現在還要通過 live_guard（授權到期 / 停止開關 / 累計曝險）。

    這些測試的主題是「下單路徑本身」，不是授權機制（授權另有 test_live_guard.py 專測），
    所以這裡把授權補齊、台帳導到暫存目錄，避免互相干擾也不污染真實紀錄。
    """
    from skills.execution import live_guard
    import datetime as _dt
    monkeypatch.setattr(live_guard, "_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(live_guard, "KILL_SWITCH_PATH", str(tmp_path / "TRADING_HALTED"))
    monkeypatch.setattr(live_guard, "ORDER_LEDGER_PATH", str(tmp_path / "order_ledger.jsonl"))
    monkeypatch.setenv("LIVE_UNTIL", (_dt.date.today() + _dt.timedelta(days=1)).isoformat())
    monkeypatch.setenv("LIVE_MAX_NOTIONAL_TWD", "99999999")
    monkeypatch.setenv("LIVE_MAX_ORDERS", "9999")
    yield


class TestOrderExecutorMock:
    @patch("skills.execution.order_executor.get_max_tickers")
    @patch("skills.execution.order_executor._create_max_order_raw")
    def test_create_order_live_success(self, mock_create_raw, mock_tickers, monkeypatch):
        # 明確切到實盤模式測試真實下單路徑
        monkeypatch.setenv("RISK_MODE", "live")
        mock_tickers.return_value = dict(REAL_MAX_TICKER)
        mock_create_raw.return_value = {"id": 998877, "market": "btctwd", "price": "2000000.0", "volume": "0.01", "state": "wait"}

        res = create_order(
            exchange_id="max",
            market="BTC/TWD",
            side="buy",
            volume=0.01,
            price=2000000.0,
            ord_type="limit"
        )
        assert res["status"] == "SUCCESS"
        assert res["mode"] == "live"
        assert res["order"]["id"] == 998877
        mock_create_raw.assert_called_once()

    @patch("skills.execution.order_executor.get_max_tickers")
    @patch("skills.execution.order_executor._create_max_order_raw")
    def test_create_order_paper_default_simulates(self, mock_create_raw, mock_tickers, monkeypatch):
        # 預設 paper 模式：不得送出真實訂單，回傳模擬成交
        monkeypatch.setenv("RISK_MODE", "paper")
        mock_tickers.return_value = dict(REAL_MAX_TICKER)

        res = create_order(
            exchange_id="max",
            market="BTC/TWD",
            side="buy",
            volume=0.01,
            price=2000000.0,
            ord_type="limit"
        )
        assert res["status"] == "SUCCESS"
        assert res["mode"] == "paper"
        assert res["order"]["simulated"] is True
        # 模擬盤「絕對不能」呼叫真實下單 API
        mock_create_raw.assert_not_called()

    @patch("skills.execution.order_executor.get_max_tickers")
    @patch("skills.execution.order_executor._create_max_order_raw")
    def test_create_order_rejected_by_wind_guard(self, mock_create_raw, mock_tickers, monkeypatch):
        # 風控攔截發生在 paper/live 分流之前，任一模式都應被擋下
        monkeypatch.setenv("RISK_MODE", "live")
        mock_tickers.return_value = dict(REAL_MAX_TICKER)

        # 委託金額過大 (0.05 BTC = 100,000 TWD)
        res = create_order(
            exchange_id="max",
            market="BTC/TWD",
            side="buy",
            volume=0.05,
            price=2000000.0,
            ord_type="limit"
        )
        assert res["status"] == "REJECTED_BY_RISK_GUARD"
        assert "超過上限" in res["reason"]
        # 保證底層下單函數「絕對沒有」被調用！
        mock_create_raw.assert_not_called()

    BTC_RULES = {"min_base_amount": 0.0001, "min_quote_amount": 250.0,
                 "base_unit": "btc", "quote_unit": "twd", "base_precision": 8}

    @patch("skills.execution.order_executor.get_max_market_rules", return_value=BTC_RULES)
    @patch("skills.execution.order_executor.get_max_tickers")
    @patch("skills.execution.order_executor._create_max_order_raw")
    def test_create_order_below_exchange_minimum(self, mock_create_raw, mock_tickers, _rules, monkeypatch):
        # 100 TWD 的 BTC 低於 MAX 門檻（0.0001 BTC 且 ≥ 250 TWD）→ 先擋下並算出最少要下多少
        monkeypatch.setenv("RISK_MODE", "live")
        mock_tickers.return_value = dict(REAL_MAX_TICKER)
        res = create_order(exchange_id="max", market="BTC/TWD", side="buy",
                           volume=0.0000365, price=2000000.0, ord_type="limit")
        assert res["status"] == "REJECTED_BELOW_EXCHANGE_MINIMUM"
        assert res["details"]["min_volume"] == pytest.approx(0.000125)   # 250 TWD / 2,000,000 > 0.0001
        assert res["details"]["min_notional"] == pytest.approx(250.0)
        mock_create_raw.assert_not_called()

    @patch("skills.execution.order_executor.get_max_market_rules", return_value=BTC_RULES)
    @patch("skills.execution.order_executor.get_max_tickers")
    def test_create_order_at_exchange_minimum_passes(self, mock_tickers, _rules, monkeypatch):
        monkeypatch.setenv("RISK_MODE", "paper")
        mock_tickers.return_value = dict(REAL_MAX_TICKER)
        res = create_order(exchange_id="max", market="BTC/TWD", side="buy",
                           volume=0.000125, price=2000000.0, ord_type="limit")
        assert res["status"] == "SUCCESS"

    @patch("skills.execution.order_executor.get_max_market_rules", side_effect=RuntimeError("MAX down"))
    @patch("skills.execution.order_executor.get_max_tickers")
    def test_create_order_minimum_check_skipped_when_rules_unavailable(self, mock_tickers, _rules, monkeypatch):
        # 規格查不到不擋：交易所才是最終把關
        monkeypatch.setenv("RISK_MODE", "paper")
        mock_tickers.return_value = dict(REAL_MAX_TICKER)
        res = create_order(exchange_id="max", market="BTC/TWD", side="buy",
                           volume=0.0000365, price=2000000.0, ord_type="limit")
        assert res["status"] == "SUCCESS"

    @patch("skills.execution.order_executor.get_max_tickers")
    def test_create_order_handles_ticker_error(self, mock_tickers, monkeypatch):
        # get_max_tickers 找不到行情時回傳 {"error": ...}，下單應優雅失敗而非拋例外
        monkeypatch.setenv("RISK_MODE", "live")
        mock_tickers.return_value = {"error": "找不到 BTC/TWD 的行情數據"}

        res = create_order(
            exchange_id="max",
            market="BTC/TWD",
            side="buy",
            volume=0.01,
            price=2000000.0,
            ord_type="limit"
        )
        assert "error" in res

    @patch("skills.execution.order_executor.get_max_tickers")
    @patch("skills.execution.order_executor._create_max_order_raw")
    def test_frozen_paper_mode_overrides_live_env(self, mock_create_raw, mock_tickers, monkeypatch):
        # M2: 環境是 live，但核准凍結 mode=paper → 必須模擬，不得送真單
        monkeypatch.setenv("RISK_MODE", "live")
        mock_tickers.return_value = dict(REAL_MAX_TICKER)
        res = create_order("max", "BTC/TWD", "buy", 0.01, 2000000.0, "limit", mode="paper")
        assert res["mode"] == "paper" and res["order"]["simulated"] is True
        mock_create_raw.assert_not_called()

    @patch("skills.execution.order_executor.get_max_tickers")
    @patch("skills.execution.order_executor._create_max_order_raw")
    def test_frozen_live_mode_overrides_paper_env(self, mock_create_raw, mock_tickers, monkeypatch):
        # M2: 環境是 paper，但核准凍結 mode=live → 依凍結執行實盤
        monkeypatch.setenv("RISK_MODE", "paper")
        mock_tickers.return_value = dict(REAL_MAX_TICKER)
        mock_create_raw.return_value = {"id": 1, "state": "wait"}
        res = create_order("max", "BTC/TWD", "buy", 0.01, 2000000.0, "limit", mode="live")
        assert res["status"] == "SUCCESS" and res["mode"] == "live"
        mock_create_raw.assert_called_once()

    @patch("skills.execution.order_executor.get_max_tickers")
    @patch("skills.execution.order_executor._create_max_order_raw")
    def test_idempotency_key_passed_on_live(self, mock_create_raw, mock_tickers, monkeypatch):
        # M3: 實盤下單必附 client_oid 冪等鍵（防吞例外後重試重複）
        monkeypatch.setenv("RISK_MODE", "live")
        mock_tickers.return_value = dict(REAL_MAX_TICKER)
        mock_create_raw.return_value = {"id": 1, "state": "wait"}
        res = create_order("max", "BTC/TWD", "buy", 0.01, 2000000.0, "limit")
        assert mock_create_raw.call_args.kwargs["client_oid"].startswith("ag-")
        assert res["client_oid"].startswith("ag-")

    @patch("skills.execution.order_executor.get_max_tickers")
    @patch("skills.execution.order_executor._create_max_order_raw")
    def test_ambiguous_failure_is_unknown_not_failed(self, mock_create_raw, mock_tickers, monkeypatch):
        # M3: 送出後異常 → UNKNOWN（非 FAILED），避免『以為失敗盲目重試』造成重複單
        monkeypatch.setenv("RISK_MODE", "live")
        mock_tickers.return_value = dict(REAL_MAX_TICKER)
        mock_create_raw.side_effect = Exception("connection timeout")
        res = create_order("max", "BTC/TWD", "buy", 0.01, 2000000.0, "limit")
        assert res["status"] == "UNKNOWN"
        assert "client_oid" in res

    @patch("skills.execution.order_executor._cancel_max_order_raw")
    def test_cancel_order_mock(self, mock_cancel_raw):
        mock_cancel_raw.return_value = {"id": 998877, "state": "cancel"}
        res = cancel_order("max", 998877)

        assert res["status"] == "SUCCESS"
        assert res["canceled_order"]["id"] == 998877

    @patch("skills.execution.order_executor._cancel_all_max_orders_raw")
    def test_cancel_all_requires_confirmation_without_market(self, mock_raw):
        # L1: 未指定 market 且未確認 → 防呆拒絕，底層絕不被呼叫（防清空全帳戶）
        res = cancel_all_orders("max")
        assert res.get("requires_confirmation") is True
        mock_raw.assert_not_called()

    @patch("skills.execution.order_executor._cancel_all_max_orders_raw")
    def test_cancel_all_specific_market_allowed(self, mock_raw):
        mock_raw.return_value = [{"id": 1, "state": "cancel"}]
        res = cancel_all_orders("max", market="BTC/TWD")
        assert res["status"] == "SUCCESS"
        mock_raw.assert_called_once()

    @patch("skills.execution.order_executor._cancel_all_max_orders_raw")
    def test_cancel_all_confirmed_allowed(self, mock_raw):
        mock_raw.return_value = []
        res = cancel_all_orders("max", confirm_all_markets=True)
        assert res["status"] == "SUCCESS"
        mock_raw.assert_called_once()

    @patch("skills.execution.order_executor._cancel_all_max_orders_raw")
    def test_cancel_all_whitespace_market_still_gated(self, mock_raw):
        # L1 加固：空白 market("   ") 正規化為 None，不得繞過全帳戶防呆
        res = cancel_all_orders("max", market="   ")
        assert res.get("requires_confirmation") is True
        mock_raw.assert_not_called()

    @patch("skills.execution.order_executor._cancel_all_max_orders_raw")
    def test_cancel_all_slash_market_still_gated(self, mock_raw):
        # "/" 或 "_" 正規化後為空(與底層一致) → 不得被當指定市場繞過防呆
        for bad in ["/", "_", " / ", "//", "___"]:
            res = cancel_all_orders("max", market=bad)
            assert res.get("requires_confirmation") is True, bad
        mock_raw.assert_not_called()

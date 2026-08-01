"""回測成本模型：手續費與滑價分開建模（純函式、不需網路）。"""
import pytest

from skills.analytics.backtester import run_backtest

BASE_MS = 1_700_000_000_000
DAY = 86_400_000


def _trending_klines(n=200):
    """正弦波價格：保證多次完整來回（買進→賣出），且價格恆為正。

    注意：不要用線性下跌造測資 —— 跑久了價格會變負數，回測會吐出 -900%
    這種荒謬報酬，測到的是測資的 bug 不是程式的行為。
    """
    import math
    out = []
    for i in range(n):
        p = 100 + 25 * math.sin(i / 12.0)      # 週期約 75 根，200 根可產生多次交叉
        out.append([BASE_MS + i * DAY, p, p * 1.01, p * 0.99, p, 1000.0])
    return out


def test_slippage_reduces_return_versus_no_slippage():
    """滑價必須讓績效變差 —— 只算手續費會系統性高估策略表現。"""
    kl = _trending_klines()
    no_slip = run_backtest(kl, slippage_rate=0.0)
    with_slip = run_backtest(kl, slippage_rate=0.002)
    assert "error" not in no_slip and "error" not in with_slip
    if with_slip["performance"]["total_trades"] > 0:
        assert with_slip["performance"]["total_return_pct"] < no_slip["performance"]["total_return_pct"]


def test_cost_model_is_reported_with_results():
    """看到績效的人必須同時看得到它建立在什麼成本假設上。"""
    r = run_backtest(_trending_klines(), fee_rate=0.001, slippage_rate=0.0015)
    cm = r["cost_model"]
    assert cm["fee_rate"] == 0.001
    assert cm["slippage_rate"] == 0.0015
    assert cm["round_trip_cost_pct"] == pytest.approx((0.001 + 0.0015) * 2 * 100)


def test_slippage_moves_fill_price_against_the_trader():
    """滑價以價格滑移實作：買貴、賣便宜。成交價要真的偏離報價，
    否則交易紀錄與圖表標記顯示的就不是真實成交價。"""
    kl = _trending_klines()
    r = run_backtest(kl, fee_rate=0.0, slippage_rate=0.01)
    marks = (r.get("chart_data") or {}).get("marks") or []
    if not marks:
        pytest.skip("此段價格未產生交易")
    quote = {int(k[0]): float(k[1]) for k in kl}      # 時間 → 該根開盤價（報價）
    for m in marks:
        q = quote.get(m["t"])
        if q is None:
            continue
        if m["side"] == "buy":
            assert m["price"] > q            # 買進成交價高於報價
        else:
            assert m["price"] < q            # 賣出成交價低於報價


def test_fee_and_slippage_are_independent_knobs():
    """兩者性質不同，必須能分別調整；只調滑價也要看得到影響。"""
    kl = _trending_klines()
    base = run_backtest(kl, fee_rate=0.001, slippage_rate=0.0)
    more_slip = run_backtest(kl, fee_rate=0.001, slippage_rate=0.005)
    more_fee = run_backtest(kl, fee_rate=0.005, slippage_rate=0.0)
    if base["performance"]["total_trades"] > 0:
        assert more_slip["performance"]["total_return_pct"] < base["performance"]["total_return_pct"]
        assert more_fee["performance"]["total_return_pct"] < base["performance"]["total_return_pct"]


def test_walk_forward_uses_the_same_cost_assumptions():
    """分段樣本外驗證若用不同成本，就無法跟主回測比較 —— 等於拿兩把尺量。"""
    kl = _trending_klines(600)
    r = run_backtest(kl, slippage_rate=0.01)
    wf = (r.get("validation") or {}).get("walk_forward") or {}
    if not wf.get("n_folds"):
        pytest.skip("K 線不足以切段")
    cheap = run_backtest(kl, slippage_rate=0.0)
    wf_cheap = (cheap.get("validation") or {}).get("walk_forward") or {}
    # 高滑價的分段報酬總和不應該優於零滑價（同一組資料、同一策略）
    assert sum(wf["fold_returns_pct"]) <= sum(wf_cheap["fold_returns_pct"]) + 1e-9

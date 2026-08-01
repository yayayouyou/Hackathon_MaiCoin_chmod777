"""Shadow Account 行為分析：重點在「樣本不足時不下結論」。

行為偏誤最容易從少數幾筆交易「看出」根本不存在的模式，所以這裡測的
主要不是「算得對不對」，而是「什麼時候該閉嘴」。
"""
import pytest

from skills.analytics import shadow_account as sa

DAY = 86_400_000
BASE = 1_700_000_000_000


def _close(pnl, hold_days, proceeds=1000.0, ts=None):
    ts = ts or BASE + 100 * DAY
    return {"ts": ts, "currency": "BTC", "qty": 1.0,
            "proceeds_twd": proceeds, "cost_twd": proceeds - pnl, "pnl_twd": pnl,
            "pnl_pct": 1.0, "lots_used": [{"ts": ts - int(hold_days * DAY), "qty": 1.0,
                                           "unit_cost": 1.0, "basis": "known"}]}


def test_disposition_refuses_to_conclude_on_small_sample():
    """3 筆虧損就宣稱「你有/沒有處置效應」是編造，不是分析。"""
    rec = [_close(100, 30) for _ in range(6)] + [_close(-50, 1) for _ in range(3)]
    out = sa._disposition(rec)
    assert out["conclusion"] is None
    assert out["sample_ok"] is False
    assert "樣本僅 3 筆" in out["note"]
    # 但數字仍要給
    assert out["winners"]["median_hold_days"] == 30.0
    assert out["losers"]["median_hold_days"] == 1.0


def test_disposition_concludes_when_sample_is_enough():
    rec = [_close(100, 5) for _ in range(10)] + [_close(-50, 40) for _ in range(10)]
    out = sa._disposition(rec)
    assert out["sample_ok"] is True
    assert "處置效應傾向" in out["conclusion"]


def test_disposition_reports_no_bias_when_holds_are_similar():
    rec = [_close(100, 20) for _ in range(10)] + [_close(-50, 22) for _ in range(10)]
    out = sa._disposition(rec)
    assert out["sample_ok"] is True
    assert "未見明顯處置效應" in out["conclusion"]


def test_averaging_counts_only_deliberate_buys():
    """質押獎勵、入金會讓數量增加，但那不是「決定在低點加碼」。

    實測曾因為把 590 筆 MAX 獎勵算進去，樣本從 144 灌到 945，
    結論也從「尚均衡」翻成「明顯逢低加碼」—— 完全誤導。
    """
    evs = []
    for i in range(6):                       # 主動買進：價格遞減 → 都在均價之下
        evs.append({"uid": f"t{i}", "ts": BASE + i * DAY, "source": "trade", "currency": "BTC",
                    "delta": 1.0, "disposal": False, "price": 100 - i * 5,
                    "quote": "TWD", "quote_amount": (100 - i * 5)})
    for i in range(50):                      # 質押獎勵：不該被算成加碼決策
        evs.append({"uid": f"r{i}", "ts": BASE + (i + 10) * DAY, "source": "reward",
                    "currency": "BTC", "delta": 0.01, "disposal": False,
                    "price": None, "quote": None, "quote_amount": None})
    out = sa._averaging_down(evs)
    assert out["n"] <= 6, f"獎勵被算進加碼決策了：n={out['n']}"


def test_averaging_refuses_to_conclude_on_small_sample():
    evs = [{"uid": f"t{i}", "ts": BASE + i * DAY, "source": "trade", "currency": "BTC",
            "delta": 1.0, "disposal": False, "price": 100 - i,
            "quote": "TWD", "quote_amount": 100 - i} for i in range(4)]
    out = sa._averaging_down(evs)
    assert out["conclusion"] is None and out["sample_ok"] is False


def test_cost_drag_needs_positive_gross_to_be_meaningful():
    """毛利是負的時候，「手續費佔毛利幾%」沒有意義。"""
    book = {"fee_cost_twd": {"BTC": 500.0}}
    rec = [_close(-1000, 10)]
    out = sa._cost_drag(book, rec)
    assert out["conclusion"] is None
    assert "毛利非正" in out["note"]


def test_cost_drag_math_is_gross_minus_fees():
    book = {"fee_cost_twd": {"BTC": 300.0, "ETH": 200.0}}
    rec = [_close(1000, 10) for _ in range(25)]
    out = sa._cost_drag(book, rec)
    assert out["total_fees_twd"] == 500.0
    assert out["net_realized_twd"] == 25_000.0
    assert out["gross_before_fees_twd"] == 25_500.0
    assert out["sample_ok"] is True


def test_home_currency_is_excluded_from_behavior():
    """TWD 是家用幣，對自己沒有買賣行為可言。"""
    evs = [{"uid": f"d{i}", "ts": BASE + i * DAY, "source": "trade", "currency": "TWD",
            "delta": 1000.0, "disposal": False, "price": 1, "quote": "TWD",
            "quote_amount": 1000} for i in range(20)]
    out = sa._averaging_down(evs)
    assert out["n"] == 0


def test_empty_ledger_gives_actionable_error(monkeypatch):
    monkeypatch.setattr("skills.analytics.position_ledger.load_events", lambda: [])
    out = sa.analyze_trading_behavior()
    assert "error" in out and "對帳" in out["error"]

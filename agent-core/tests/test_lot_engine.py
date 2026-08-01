"""批次引擎測試（純函式；價格用預先注入的快取，不碰網路）。"""
import pytest

from skills.analytics import lot_engine
from skills.analytics.position_ledger import _ev

DAY = 86400000


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """把 TWD 估值固定住：BTC 恆 100 萬、TWD 恆 1，避免測試依賴行情。"""
    monkeypatch.setattr(lot_engine, "twd_price_at",
                        lambda cur, ts: 1.0 if cur == "TWD" else 1_000_000.0)
    monkeypatch.setattr(lot_engine, "spot_price",
                        lambda cur: 1.0 if cur == "TWD" else 1_200_000.0)


def _buy(uid, ts, qty, funds):
    return _ev(uid, ts, "trade", "BTC", qty, price=funds / qty, quote="TWD", quote_amount=funds)


def _sell(uid, ts, qty, funds):
    return _ev(uid, ts, "trade", "BTC", -qty, disposal=True,
               price=funds / qty, quote="TWD", quote_amount=funds)


def test_fifo_matches_oldest_lot_first():
    """先買便宜、再買貴，賣一顆應該平掉『最早』那批 → 獲利以最早成本計。"""
    evs = [_buy("b1", DAY, 1.0, 100.0), _buy("b2", 2 * DAY, 1.0, 300.0),
           _sell("s1", 3 * DAY, 1.0, 400.0)]
    r = lot_engine.build_lots(evs, method="fifo")
    assert len(r["realized"]) == 1
    rec = r["realized"][0]
    assert rec["cost_twd"] == pytest.approx(100.0)      # 平掉最早那批，不是最貴那批
    assert rec["pnl_twd"] == pytest.approx(300.0)
    assert rec["lots_used"][0]["ts"] == DAY


def test_average_uses_blended_cost():
    """同樣的交易改用移動平均，成本應為兩批的加權平均（200）。"""
    evs = [_buy("b1", DAY, 1.0, 100.0), _buy("b2", 2 * DAY, 1.0, 300.0),
           _sell("s1", 3 * DAY, 1.0, 400.0)]
    r = lot_engine.build_lots(evs, method="average")
    assert r["realized"][0]["cost_twd"] == pytest.approx(200.0)


def test_withdrawal_is_movement_not_disposal():
    """提幣只是把幣移走，不該產生已實現損益 —— 但要扣掉批次數量。"""
    evs = [_buy("b1", DAY, 1.0, 100.0),
           _ev("w1", 2 * DAY, "withdrawal", "BTC", -1.0)]
    r = lot_engine.build_lots(evs)
    assert r["realized"] == []
    assert not r["open_lots"].get("BTC")


def test_selling_more_than_known_lots_is_reported_not_invented():
    """賣超過可追溯的買入量時，多的部分列入 unmatched 並排除，不可假裝零成本獲利。"""
    evs = [_buy("b1", DAY, 1.0, 100.0), _sell("s1", 2 * DAY, 3.0, 900.0)]
    r = lot_engine.build_lots(evs)
    assert r["unmatched_qty"]["BTC"] == pytest.approx(2.0)
    rec = r["realized"][0]
    assert rec["qty"] == pytest.approx(1.0)             # 只認列配得到的 1 顆
    assert rec["proceeds_twd"] == pytest.approx(300.0)  # 收入按比例認列，不是全額 900


def test_reward_basis_policy_changes_cost():
    """獎勵成本政策：market 用收到當下市價、zero 視為零成本（賣出時全額算獲利）。"""
    evs = [_ev("r1", DAY, "reward", "BTC", 1.0),
           _sell("s1", 2 * DAY, 1.0, 1_500_000.0)]
    mkt = lot_engine.build_lots(evs, reward_basis="market")["realized"][0]
    zero = lot_engine.build_lots(evs, reward_basis="zero")["realized"][0]
    assert mkt["cost_twd"] == pytest.approx(1_000_000.0)
    assert zero["cost_twd"] == pytest.approx(0.0)
    assert zero["pnl_twd"] > mkt["pnl_twd"]


def test_align_to_exchange_trims_and_plugs_with_disclosure():
    """艙位數量必須對齊交易所；調整要被回報，不能默默改。"""
    lots = {"BTC": [{"ts": DAY, "qty": 2.0, "unit_cost": 100.0, "basis": "known"}]}
    adj = lot_engine._align_to_exchange(lots, {"BTC": 1.5})
    assert sum(l["qty"] for l in lots["BTC"]) == pytest.approx(1.5)
    assert adj[0]["action"] == "trim" and adj[0]["qty"] == pytest.approx(0.5)

    lots2 = {"ETH": [{"ts": DAY, "qty": 1.0, "unit_cost": 100.0, "basis": "known"}]}
    adj2 = lot_engine._align_to_exchange(lots2, {"ETH": 1.5})
    assert adj2[0]["action"] == "plug"
    assert any(l["basis"] == "unknown" for l in lots2["ETH"])


def test_home_currency_has_no_lots():
    """TWD 是家用幣，對自己沒有損益，不該建批次。"""
    r = lot_engine.build_lots([_ev("d1", DAY, "deposit", "TWD", 10000.0)])
    assert "TWD" not in r["open_lots"]

"""事件帳本核心邏輯測試（純函式、不需網路）。"""
from skills.analytics.position_ledger import _ev, replay


def test_replay_sums_deltas_per_currency():
    evs = [
        _ev("t1", 1, "trade", "BTC", 0.5, price=100.0, quote="TWD"),
        _ev("t2", 2, "trade", "BTC", -0.2, disposal=True, price=120.0, quote="TWD"),
        _ev("t3", 3, "reward", "MAX", 10.0),
    ]
    qty = replay(evs)
    assert abs(qty["BTC"] - 0.3) < 1e-12
    assert abs(qty["MAX"] - 10.0) < 1e-12


def test_replay_nets_transfer_legs_to_zero():
    """站內轉帳（spot↔m）兩腿相抵，不應憑空增減部位。"""
    qty = replay([_ev("z1", 1, "transfer", "TWD", -100.0),
                  _ev("z2", 1, "transfer", "TWD", 100.0)])
    assert abs(qty.get("TWD", 0.0)) < 1e-12


def test_uid_is_stable_and_unique_per_source():
    """去重靠 uid：同一筆重播兩次不能變成兩筆（append-only 存檔的正確性前提）。"""
    a = _ev("x", 1, "trade", "BTC", 1.0)
    b = _ev("x", 1, "trade", "BTC", 1.0)
    c = _ev("y", 1, "trade", "BTC", 1.0)
    assert a["uid"] == b["uid"] and a["uid"] != c["uid"]


def test_disposal_flag_marks_only_outflows_that_realize_pnl():
    """賣出/閃兌賣方是處分（要算已實現損益）；提幣只是移動、不是處分。"""
    sell = _ev("s", 1, "trade", "BTC", -1.0, disposal=True, price=100.0, quote="TWD")
    withdraw = _ev("w", 2, "withdrawal", "BTC", -1.0)
    assert sell["disposal"] is True
    assert withdraw["disposal"] is False

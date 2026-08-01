"""回測繪圖資料與 K 線格式相容性（純函式、不需網路）。"""
import pytest

from skills.analytics.backtester import _normalize_klines, _chart_payload

BASE_MS = 1_700_000_000_000
DAY = 86_400_000


def _arr(n=40):
    return [[BASE_MS + i * DAY, 100 + i, 105 + i, 95 + i, 100 + i, 1.0] for i in range(n)]


def _obj(n=40):
    import datetime as dt
    out = []
    for i in range(n):
        t = dt.datetime.fromtimestamp((BASE_MS + i * DAY) / 1000, dt.timezone.utc)\
                .replace(tzinfo=None).isoformat() + "Z"
        out.append({"timestamp": t, "open": 100 + i, "high": 105 + i,
                    "low": 95 + i, "close": 100 + i, "volume": 1.0})
    return out


def test_normalizes_both_kline_shapes_to_same_result():
    """get_max_klines 給陣列、get_ohlcv 給物件 —— 兩者必須正規化成同一種形狀，
    否則模型把 get_ohlcv 的輸出接到 run_backtest 就會崩。"""
    a, b = _normalize_klines(_arr()), _normalize_klines(_obj())
    assert len(a) == len(b) == 40
    assert [r[4] for r in a] == [r[4] for r in b]        # 收盤價一致
    assert all(isinstance(r[0], int) and r[0] > 10 ** 12 for r in a)   # 一律毫秒


def test_seconds_timestamps_are_upgraded_to_ms():
    """MAX 的 K 線用秒級時間戳；不轉毫秒的話圖表 x 軸會落到 1970 年。"""
    rows = _normalize_klines([[1_700_000_000, 1, 2, 0.5, 1.5, 1] for _ in range(3)])
    assert all(r[0] == 1_700_000_000_000 for r in rows)


def test_bad_rows_are_skipped_not_fatal():
    """單根壞資料不該讓整批回測失敗。"""
    rows = _normalize_klines(_arr(5) + [None, {}, [1, 2], "x"] + _arr(3))
    assert len(rows) == 8


def test_chart_payload_keeps_every_trade_mark():
    """價格線可以抽樣（畫面畫不下），但交易標記抽樣掉就是騙人 —— 必須全留。"""
    kl = _normalize_klines(_arr(1000))
    trades = [{"buy_time": BASE_MS + i * DAY, "buy_price": 100.0,
               "sell_time": BASE_MS + (i + 1) * DAY, "sell_price": 110.0, "pnl_pct": 10.0}
              for i in range(0, 40, 2)]
    cd = _chart_payload(kl, trades, max_points=100)
    assert len(cd["series"]) <= 102          # 有抽樣
    assert cd["sampled_every"] > 1
    assert len(cd["marks"]) == len(trades) * 2   # 標記一個都沒少
    assert cd["total_bars"] == 1000


def test_chart_payload_keeps_last_point():
    """末端一定要保留，否則最後一筆交易會落在價格線之外。"""
    kl = _normalize_klines(_arr(999))
    cd = _chart_payload(kl, [], max_points=100)
    assert cd["series"][-1]["t"] == kl[-1][0]


def test_marks_are_sorted_and_typed():
    kl = _normalize_klines(_arr(50))
    trades = [{"buy_time": BASE_MS + 10 * DAY, "buy_price": 110.0,
               "sell_time": BASE_MS + 5 * DAY, "sell_price": 105.0, "pnl_pct": -4.5}]
    cd = _chart_payload(kl, trades)
    ts = [m["t"] for m in cd["marks"]]
    assert ts == sorted(ts)
    sells = [m for m in cd["marks"] if m["side"] == "sell"]
    assert sells and sells[0]["pnl_pct"] == -4.5
    buys = [m for m in cd["marks"] if m["side"] == "buy"]
    assert buys and buys[0]["pnl_pct"] is None      # 買進沒有已實現損益

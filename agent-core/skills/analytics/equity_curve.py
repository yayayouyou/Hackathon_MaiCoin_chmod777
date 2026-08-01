"""
skills/analytics/equity_curve.py — 資產淨值時間序列（帳本重播的共用地基）

`lot_engine` 只給「某一時點」的艙位快照；要畫得出交易 DNA 面板的資產曲線，
需要的是**每一筆事件之後的淨值**。本模組就是那條曲線，外加把它壓成每日一點。

同時，這裡的 `replay_events()` 是 `dna_score` 與 `counterfactual` 共用的地基：
三個模組看的是同一次 FIFO 重播，不會各算各的而互相打架。

會計慣例（誠實揭露，可寫進簡報附註）：
  - 取得（買入 / 閃兌買進 / 入金 / 獎勵）→ 建立成本批次，成本＝當下 TWD 單價。
      · 入金是外部轉入，真實取得成本不可知，以「轉入當下市價」近似。
  - 處分（賣出 / 閃兌賣出腿，`disposal=True`）→ FIFO 對沖批次，實現損益＝(賣價−批次成本)×數量。
  - 轉移（提幣 / 錢包互轉 / 手續費）→ FIFO 消耗批次，**不實現損益**。
  - TWD → 視為計價基準，只統計現金流，不建批次、不計損益。
  - **本金（capital）只認主動買賣**：入金／獎勵進來的幣是外部免費取得，算「淨值」
      但**不算「本金需求」**——它一塊 TWD 都沒掏。見下方 `hold_capital` / `net_deployed`。

超賣防呆：找不到成本批次可對沖的數量進 `unmatched_qty`，**不硬湊零成本**
（與 `lot_engine` 同一個原則：寧可少算，不要憑空生出獲利）。
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from skills.analytics.csv_source import HOME_CCY, load_events_for_analysis

MS_PER_DAY = 86_400_000

# 這些 source 算「主動買賣」；其餘的增加（入金/獎勵/互轉）算外部轉入。
_TRADE_SOURCES = ("trade", "convert")


def _f(x, d=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _blank_stat(ccy: str) -> Dict[str, Any]:
    return {"currency": ccy, "bought_qty": 0.0, "bought_twd": 0.0,
            "sold_qty": 0.0, "sold_twd": 0.0, "deposited_qty": 0.0,
            "withdrawn_qty": 0.0, "realized_pnl_twd": 0.0,
            "remaining_qty": 0.0, "remaining_cost_twd": 0.0,
            "last_price": 0.0, "unmatched_qty": 0.0}


def replay_events(events: List[Dict[str, Any]],
                  price_lookup: Optional[Callable[[str, int], Optional[float]]] = None,
                  ) -> Dict[str, Any]:
    """走訪帳本事件，重建持倉／FIFO 成本／已實現損益／淨值曲線。

    Args:
        events: `csv_source.load_csv_events()` 或 `position_ledger.fetch_events()` 的事件
        price_lookup: 事件沒帶 `price` 時的價格查詢器（cur, ts)->TWD 單價。
                      給 None 就退回「該幣最後一次看到的價格」，並計入 missing_price_events。

    Returns:
        per_currency / realized / hold_days_samples / points / twd_deposit / twd_withdrawal
        / traded_notional_twd / hold_capital_peak_twd / actual_peak_capital_twd
        / missing_price_events
    """
    lots: Dict[str, Deque[Dict[str, float]]] = defaultdict(deque)
    stats: Dict[str, Dict[str, Any]] = {}
    last_price: Dict[str, float] = {}
    holdings: Dict[str, float] = defaultdict(float)
    realized: List[Dict[str, Any]] = []
    hold_days_samples: List[Tuple[str, float, float]] = []
    points: List[Dict[str, float]] = []
    twd_deposit = twd_withdrawal = 0.0
    traded_notional = 0.0
    missing_price = 0
    # 兩條資本曲線（counterfactual 的資本可行性檢查要用）。
    # ★ 兩條都**只認主動買賣**（`_TRADE_SOURCES`）：入金／獎勵／互轉進來的幣是外部免費取得，
    #   一塊 TWD 都沒掏，把它們算成「本金」會憑空灌大分母（主辦 CSV 上會灌 3.75 倍）。
    #   ── hold_capital  「買了就抱」情境：買進成本永不回收 → 單調遞增 → 峰值＝總買進金額
    #   ── net_deployed  實際情境：賣出把錢放回來 → 峰值＝真正壓在買進上的最大 TWD
    # 在這裡算而不是在 counterfactual 算，是因為價格在這一層才解析完成
    #（真實帳本的事件不帶 price，要靠 price_lookup 補）。
    hold_capital = 0.0
    net_deployed = 0.0
    actual_peak_capital = 0.0

    def _stat(ccy: str) -> Dict[str, Any]:
        if ccy not in stats:
            stats[ccy] = _blank_stat(ccy)
        return stats[ccy]

    def _record_equity(ts: int) -> None:
        """每一筆事件後的加密資產估值（TWD）。TWD 本身不計入——它是計價基準不是部位。"""
        value = sum(qty * last_price.get(ccy, 0.0)
                    for ccy, qty in holdings.items() if qty > 1e-12)
        points.append({"ts": int(ts), "value_twd": value})

    def _dispose_fifo(ccy: str, qty: float, ts: int) -> Tuple[float, float, float]:
        """FIFO 消耗批次 → (對沖成本, 數量加權持有天數, 未對沖數量)。"""
        remaining, cost, hold_qty_days, matched = qty, 0.0, 0.0, 0.0
        book = lots[ccy]
        while remaining > 1e-12 and book:
            lot = book[0]
            take = min(remaining, lot["qty"])
            cost += take * lot["cost"]
            hold_qty_days += take * (ts - lot["ts"]) / MS_PER_DAY
            matched += take
            lot["qty"] -= take
            remaining -= take
            if lot["qty"] <= 1e-12:
                book.popleft()
        return cost, (hold_qty_days / matched if matched > 1e-12 else 0.0), remaining

    for e in sorted(events, key=lambda x: x.get("ts") or 0):
        ccy = str(e.get("currency", "")).upper()
        ts = int(e.get("ts") or 0)
        delta = _f(e.get("delta"))
        source = e.get("source") or ""

        px = e.get("price")
        if px is None and ccy == HOME_CCY:
            px = 1.0
        if px is None and price_lookup is not None:
            try:
                px = price_lookup(ccy, ts)
            except Exception:  # noqa: BLE001
                px = None
        if px is None:
            missing_price += 1
            px = last_price.get(ccy, 0.0)
        px = _f(px)
        last_price[ccy] = px

        if ccy == HOME_CCY:
            # TWD 只記現金流：不建批次、不計損益（它是計價基準）
            if delta > 0:
                twd_deposit += delta
            elif delta < 0:
                twd_withdrawal += -delta
            _record_equity(ts)
            continue

        qty = abs(delta)
        notional = px * qty
        st = _stat(ccy)

        if source in _TRADE_SOURCES:        # 只有主動買賣才動用 TWD 本金
            if delta > 0:
                hold_capital += notional
            net_deployed += px * delta      # 買進為正、賣出把錢收回為負
            actual_peak_capital = max(actual_peak_capital, net_deployed)

        if delta > 0:
            lots[ccy].append({"qty": qty, "cost": px, "ts": ts})
            holdings[ccy] += qty
            if source in _TRADE_SOURCES:
                st["bought_qty"] += qty
                st["bought_twd"] += notional
                traded_notional += notional
            else:
                st["deposited_qty"] += qty

        elif delta < 0 and e.get("disposal"):
            cost, hold_wavg, residual = _dispose_fifo(ccy, qty, ts)
            matched = qty - residual
            proceeds = px * matched
            st["sold_qty"] += qty
            st["sold_twd"] += notional
            st["realized_pnl_twd"] += proceeds - cost
            st["unmatched_qty"] += residual
            holdings[ccy] -= matched
            if source in _TRADE_SOURCES:
                traded_notional += notional
            if matched > 1e-12:
                realized.append({"ts": ts, "currency": ccy, "qty": matched,
                                 "proceeds_twd": proceeds, "cost_twd": cost,
                                 "pnl_twd": proceeds - cost, "hold_days_wavg": hold_wavg})
                hold_days_samples.append((ccy, matched, hold_wavg))

        elif delta < 0:
            # 提幣 / 錢包互轉 / 手續費：成本隨幣離開，不實現損益
            _cost, _hold, residual = _dispose_fifo(ccy, qty, ts)
            matched = qty - residual
            st["withdrawn_qty"] += qty
            st["unmatched_qty"] += residual
            holdings[ccy] -= matched

        _record_equity(ts)

    # 收尾：填入剩餘持倉、成本、最新價
    for ccy, book in lots.items():
        st = _stat(ccy)
        st["remaining_qty"] = sum(l["qty"] for l in book)
        st["remaining_cost_twd"] = sum(l["qty"] * l["cost"] for l in book)
    for ccy, st in stats.items():
        st["last_price"] = last_price.get(ccy, 0.0)
        st["market_value_twd"] = st["remaining_qty"] * st["last_price"]
        st["unrealized_pnl_twd"] = st["market_value_twd"] - st["remaining_cost_twd"]
        st["avg_cost"] = (st["remaining_cost_twd"] / st["remaining_qty"]
                          if st["remaining_qty"] > 1e-12 else 0.0)

    return {
        "per_currency": stats,
        "realized": realized,
        "hold_days_samples": hold_days_samples,
        "points": points,
        "twd_deposit": twd_deposit,
        "twd_withdrawal": twd_withdrawal,
        "traded_notional_twd": traded_notional,
        # 續抱情境不賣 → 買進成本永不回收，累積投入單調遞增，峰值即**總買進金額**
        #（入金取得的幣是免費的，不列入本金需求）
        "hold_capital_peak_twd": hold_capital,
        # 實際情境壓在買進上的最大 TWD（買進累計 − 賣出回收，取全期最大值）
        "actual_peak_capital_twd": actual_peak_capital,
        "missing_price_events": missing_price,
        "total_market_value_twd": sum(s["market_value_twd"] for s in stats.values()),
        "total_cost_basis_twd": sum(s["remaining_cost_twd"] for s in stats.values()),
        "total_realized_pnl_twd": sum(s["realized_pnl_twd"] for s in stats.values()),
        "total_unrealized_pnl_twd": sum(s["unrealized_pnl_twd"] for s in stats.values()),
    }


def downsample_daily(points: List[Dict[str, float]]) -> List[Dict[str, Any]]:
    """把每筆事件的淨值曲線壓成「每日最後一筆」，縮小報告體積。

    一年一萬筆事件直接丟給前端或 LLM 都太大；每日一點足夠畫出曲線形狀。
    """
    by_day: Dict[str, Dict[str, Any]] = {}
    for pt in points:
        day = datetime.fromtimestamp(pt["ts"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        by_day[day] = {"date": day, "value_twd": round(pt["value_twd"], 2)}
    return list(by_day.values())


def _drawdown(daily: List[Dict[str, Any]]) -> Dict[str, Any]:
    """最大回撤（以每日淨值計）——曲線好不好看，這個數字最誠實。"""
    peak = 0.0
    worst = 0.0
    worst_date = None
    for pt in daily:
        peak = max(peak, pt["value_twd"])
        if peak > 0:
            dd = (pt["value_twd"] - peak) / peak
            if dd < worst:
                worst, worst_date = dd, pt["date"]
    return {"max_drawdown_pct": round(worst * 100, 2), "trough_date": worst_date}


# ── 對外入口（LLM Tool）────────────────────────────────────────────
def get_equity_curve(source: str = "demo", path: str = "", limit: int = 0) -> Dict[str, Any]:
    """【LLM Tool】加密資產淨值的每日時間序列（畫資產曲線用）。

    Args:
        source: 'demo'＝訪客示範帳戶 CSV 種子（預設）；'ledger'＝MAX 真實帳本
        path: source='demo' 時的 CSV 路徑，留空用預設示範帳戶
        limit: 只回最近幾天（0＝全部）
    """
    got = load_events_for_analysis(source=source, path=path)
    if got.get("error"):
        return {"error": got["error"], "source": got.get("source")}

    snap = replay_events(got["events"], price_lookup=got.get("price_lookup"))
    daily = downsample_daily(snap["points"])
    trimmed = daily[-limit:] if limit and limit > 0 else daily
    values = [p["value_twd"] for p in daily]

    return {
        "source": got["source"],
        "days": len(daily),
        "returned": len(trimmed),
        "curve": trimmed,
        "start_value_twd": round(values[0], 2) if values else 0.0,
        "end_value_twd": round(values[-1], 2) if values else 0.0,
        "peak_value_twd": round(max(values), 2) if values else 0.0,
        **_drawdown(daily),
        "events": len(snap["points"]),
        "missing_price_events": snap["missing_price_events"],
        "note": "曲線為**加密資產市值**（不含 TWD 現金餘額），以每日最後一筆事件的估值為當日值。"
                + ("　部分事件缺 TWD 單價，該幣估值可能偏低。"
                   if snap["missing_price_events"] else ""),
    }

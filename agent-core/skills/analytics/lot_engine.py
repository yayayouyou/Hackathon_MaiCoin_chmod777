"""
skills/analytics/lot_engine.py — 批次（Lot）引擎：未平艙位 + 未實現/已實現損益

接在 position_ledger（P1 對帳）之後：把事件帳本重播成一顆顆「買入批次」，
賣出時依 FIFO 或移動平均去平掉歷史批次，算出每筆的成本、報酬與持有天數。

三個關鍵設計（都是為了不說謊）：
1. **統一以 TWD 計價，用「當時」的日收盤價換算**，不是用現在的匯率回推過去。
   閃兌有 35 筆是用 USDT/BTC/ETH 等計價，不換算就無法跟 TWD 買的部位相比。
2. **成本來源分級**：交易/閃兌＝已知成本；獎勵＝依政策定價（預設用收到當下市價）；
   外部入金＝成本不可知，標記 unknown，不假裝是零成本（否則會憑空生出獲利）。
3. **賣超過帳本已知批次時不硬湊**：多出來的數量進 unmatched，排除在損益之外並回報，
   因為 API 給不出更早的買入紀錄（見 position_ledger 的對帳結論）。

「處分」才算損益：賣出、閃兌賣出腿。提幣只是資產移動、不是處分，只扣數量不算損益。
"""
import datetime as dt
from typing import Dict, Any, List, Optional
from loguru import logger

from skills.analytics.position_ledger import load_events, replay, _f

_HOME = "TWD"
_px_cache: Dict[str, Dict[int, float]] = {}
_spot_cache: Dict[str, tuple] = {}   # cur → (價格, 取得時間)


def _day(ts_ms: int) -> int:
    """事件時間 → 當日 00:00 的 epoch 秒（日K 對齊用）。"""
    d = dt.datetime.fromtimestamp(int(ts_ms or 0) / 1000).date()
    return int(dt.datetime(d.year, d.month, d.day).timestamp())


def _twd_series(currency: str) -> Dict[int, float]:
    """幣種 → {日期epoch: 當日 TWD 收盤價}（日K，快取）。"""
    cur = currency.upper()
    if cur in _px_cache:
        return _px_cache[cur]
    series: Dict[int, float] = {}
    try:
        from skills.max_exchange.max_public import get_max_klines
        for k in (get_max_klines(f"{cur}/TWD", limit=2000, period_minutes=1440) or []):
            series[_day(int(k[0]) * 1000)] = _f(k[4])
    except Exception as e:  # noqa: BLE001
        logger.warning(f"{cur}/TWD 日K 取得失敗，該幣估值降級：{e}")
    _px_cache[cur] = series
    return series


def twd_price_at(currency: str, ts_ms: int) -> Optional[float]:
    """指定時間點的 TWD 單價。找不到當日就往前找最近一日（假日/停牌）。"""
    cur = (currency or "").upper()
    if not cur:
        return None
    if cur == _HOME:
        return 1.0
    series = _twd_series(cur)
    if not series:
        return None
    target = _day(ts_ms)
    if target in series:
        return series[target]
    earlier = [d for d in series if d <= target]
    if earlier:
        return series[max(earlier)]
    return series[min(series)]      # 早於行情起點 → 用最早一筆，聊勝於無


def spot_price(currency: str, ttl: int = 60) -> Optional[float]:
    """目前 TWD 市價（未實現損益用）。快取 ttl 秒 —— 長時間執行的服務不能拿舊價算損益。"""
    import time
    cur = (currency or "").upper()
    if cur == _HOME:
        return 1.0
    hit = _spot_cache.get(cur)
    if hit and (time.time() - hit[1]) < ttl:
        return hit[0]
    px = None
    try:
        from skills.max_exchange.max_public import get_max_ticker
        t = get_max_ticker(f"{cur}/TWD") or {}
        px = _f(t.get("last") or t.get("close")) or None
    except Exception:  # noqa: BLE001
        px = None
    if not px:                       # 降級：用日K 最後一根收盤
        series = _twd_series(cur)
        px = series[max(series)] if series else None
    if px:
        import time as _t
        _spot_cache[cur] = (px, _t.time())
    return px


def _acquire_cost(e: Dict[str, Any], reward_basis: str) -> tuple:
    """取得事件 → (每單位 TWD 成本, 成本可信度)。"""
    qty, src, ts = _f(e.get("delta")), e.get("source"), e.get("ts")
    if qty <= 0:
        return 0.0, "unknown"
    if src in ("trade", "convert"):
        qa, quote = _f(e.get("quote_amount")), e.get("quote")
        if qa > 0 and quote:
            fx = twd_price_at(quote, ts)
            if fx:
                return qa * fx / qty, "known"
        px = twd_price_at(e.get("currency"), ts)     # 缺計價資訊 → 退回當日市價
        return (px or 0.0), ("market" if px else "unknown")
    if src == "reward":
        if reward_basis == "zero":
            return 0.0, "zero"                        # 視為零成本：賣出時全額算獲利
        px = twd_price_at(e.get("currency"), ts)      # 慣例：收到當下市價即成本
        return (px or 0.0), ("market" if px else "unknown")
    # 入金 / 錢包互轉：資產從外部進來，原始買價不可知
    px = twd_price_at(e.get("currency"), ts)
    return (px or 0.0), "unknown"


def build_lots(events: Optional[List[Dict[str, Any]]] = None, method: str = "fifo",
               reward_basis: str = "market") -> Dict[str, Any]:
    """重播事件成批次，回傳未平批次、已實現損益明細與無法配對的數量。

    method: 'fifo'（先進先出，預設）或 'average'（移動平均成本）
    reward_basis: 'market'（收到當下市價，預設）或 'zero'（零成本）
    """
    evs = sorted(events if events is not None else load_events(), key=lambda x: (x.get("ts") or 0))
    lots: Dict[str, List[Dict[str, Any]]] = {}
    realized: List[Dict[str, Any]] = []
    unmatched: Dict[str, float] = {}
    fees: Dict[str, float] = {}

    def _take(cur: str, qty: float) -> tuple:
        """從批次取出數量 → (實際取出量, 成本TWD, 用掉的批次明細)。不足就回報缺口。"""
        book = lots.setdefault(cur, [])
        got = cost = 0.0
        used: List[Dict[str, Any]] = []
        if method == "average" and book:
            tq = sum(l["qty"] for l in book)
            tc = sum(l["qty"] * l["unit_cost"] for l in book)
            avg = tc / tq if tq else 0.0
            take = min(qty, tq)
            for l in book:                                  # 依比例攤提
                l["qty"] -= take * (l["qty"] / tq) if tq else 0.0
            lots[cur] = [l for l in book if l["qty"] > 1e-12]
            got, cost = take, take * avg
            used = [{"unit_cost": avg, "qty": take, "ts": None, "basis": "average"}]
        else:
            while qty - got > 1e-12 and book:
                l = book[0]
                take = min(qty - got, l["qty"])
                got += take
                cost += take * l["unit_cost"]
                used.append({"unit_cost": l["unit_cost"], "qty": take,
                             "ts": l["ts"], "basis": l["basis"]})
                l["qty"] -= take
                if l["qty"] <= 1e-12:
                    book.pop(0)
        if qty - got > 1e-12:
            unmatched[cur] = unmatched.get(cur, 0.0) + (qty - got)
        return got, cost, used

    for e in evs:
        cur, delta, ts = e["currency"], _f(e.get("delta")), e.get("ts")
        if cur == _HOME or abs(delta) < 1e-15:
            continue                                  # 家用幣不建批次（TWD 對 TWD 無損益）
        if delta > 0:
            unit_cost, basis = _acquire_cost(e, reward_basis)
            lots.setdefault(cur, []).append({
                "ts": ts, "qty": delta, "unit_cost": unit_cost,
                "basis": basis, "source": e.get("source"), "note": e.get("note", ""),
            })
            continue

        qty = -delta
        if e.get("source") == "fee":                  # 手續費：扣數量、記成本，不算損益
            got, cost, _u = _take(cur, qty)
            fees[cur] = fees.get(cur, 0.0) + cost
            continue
        if not e.get("disposal"):                     # 提幣/轉出：移動而非處分
            _take(cur, qty)
            continue

        qa, quote = _f(e.get("quote_amount")), e.get("quote")
        fx = twd_price_at(quote, ts) if quote else None
        proceeds = qa * fx if (qa > 0 and fx) else (qty * (twd_price_at(cur, ts) or 0.0))
        got, cost, used = _take(cur, qty)
        if got > 1e-12:
            share = proceeds * (got / qty) if qty else 0.0   # 未配對部分不認列收入
            realized.append({
                "ts": ts, "currency": cur, "qty": round(got, 12),
                "proceeds_twd": round(share, 2), "cost_twd": round(cost, 2),
                "pnl_twd": round(share - cost, 2),
                "pnl_pct": round((share - cost) / cost * 100, 2) if cost > 0 else None,
                "lots_used": used, "note": e.get("note", ""),
                "basis_quality": "known" if all(u["basis"] in ("known", "average") for u in used) else "mixed",
            })

    open_lots = {c: [l for l in v if l["qty"] > 1e-12] for c, v in lots.items()}
    return {
        "method": method, "reward_basis": reward_basis,
        "open_lots": {c: v for c, v in open_lots.items() if v},
        "realized": realized,
        "unmatched_qty": {k: round(v, 12) for k, v in unmatched.items() if v > 1e-12},
        "fee_cost_twd": {k: round(v, 2) for k, v in fees.items() if v},
    }


def _align_to_exchange(open_lots: Dict[str, List[Dict[str, Any]]],
                       actual: Dict[str, float]) -> List[Dict[str, Any]]:
    """把批次數量對齊交易所實際餘額 —— 艙位頁的數字必須跟使用者在 MAX 上看到的一致。
    多出來的砍最舊批次（缺的支出多半發生在較早）；少的補一顆成本未知的批次。
    每次調整都回報，不默默修改。"""
    adjustments: List[Dict[str, Any]] = []
    for cur in set(open_lots) | set(actual):
        ls = open_lots.setdefault(cur, [])
        qty = sum(l["qty"] for l in ls)
        target = actual.get(cur, 0.0)          # 餘額 API 只回非零幣種 → 未列出即為 0
        diff = target - qty
        if abs(diff) <= max(1e-9, abs(target) * 1e-9):
            continue
        if diff < 0:                            # 帳本比實際多 → 砍最舊批次
            need = -diff
            ls.sort(key=lambda l: l["ts"] or 0)
            while need > 1e-12 and ls:
                take = min(need, ls[0]["qty"])
                ls[0]["qty"] -= take
                need -= take
                if ls[0]["qty"] <= 1e-12:
                    ls.pop(0)
            adjustments.append({"currency": cur, "action": "trim", "qty": round(-diff, 12),
                                "reason": "帳本數量高於交易所餘額（有 API 未公開的支出流水）"})
        else:                                   # 實際比帳本多 → 補未知成本批次
            ls.append({"ts": None, "qty": diff, "unit_cost": spot_price(cur) or 0.0,
                       "basis": "unknown", "source": "opening",
                       "note": "期初/來源不可考（以現價計入，不虛報損益）"})
            adjustments.append({"currency": cur, "action": "plug", "qty": round(diff, 12),
                                "reason": "交易所餘額高於帳本（API 歷史起點之前的取得）"})
    return adjustments


def get_open_positions(method: str = "fifo", reward_basis: str = "market",
                       align_to_exchange: bool = True) -> Dict[str, Any]:
    """【LLM Tool】目前未平艙位與未實現損益（依歷史買入批次計算成本）。

    每個幣種給：持有量、平均成本、現價、未實現損益與報酬率、成本可信度。
    預設把數量對齊交易所實際餘額（差異會列在 adjustments，不隱藏）。
    """
    book = build_lots(method=method, reward_basis=reward_basis)
    return summarize_positions(book, align_to_exchange=align_to_exchange)


def summarize_positions(book: Dict[str, Any], align_to_exchange: bool = True) -> Dict[str, Any]:
    """把 build_lots 的結果整理成艙位摘要（可重用同一份 book，不必重算）。"""
    method, reward_basis = book["method"], book["reward_basis"]
    ledger_qty = replay()
    actual, actual_ok = {}, False
    try:
        from skills.max_exchange.max_private import get_max_accounts
        rows = get_max_accounts() or []
        actual = {a["currency"]: _f(a.get("total")) for a in rows}
        actual_ok = bool(rows)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"取得實際餘額失敗，未平艙位僅以帳本呈現：{e}")

    # 只有在確定拿到餘額時才對齊，否則寧可顯示帳本原值也不要把部位歸零
    adjustments = _align_to_exchange(book["open_lots"], actual) if (align_to_exchange and actual_ok) else []

    positions = []
    tot_cost = tot_value = 0.0
    for cur, ls in book["open_lots"].items():
        qty = sum(l["qty"] for l in ls)
        if qty <= 1e-12:
            continue
        cost = sum(l["qty"] * l["unit_cost"] for l in ls)
        px = spot_price(cur)
        value = qty * px if px else None
        known_qty = sum(l["qty"] for l in ls if l["basis"] == "known")
        # 批次明細依「月份＋來源」分組 —— MAX 有 359 個未平批次（多是幾百筆微小獎勵），
        # 逐筆列出沒人看得完；分組後既看得到成本結構，又不會爆版面。
        groups: Dict[tuple, Dict[str, Any]] = {}
        for l in ls:
            period = dt.datetime.fromtimestamp(l["ts"] / 1000).strftime("%Y-%m") if l.get("ts") else "期初"
            g = groups.setdefault((period, l.get("source") or "—"),
                                  {"period": period, "source": l.get("source") or "—",
                                   "qty": 0.0, "cost": 0.0, "lots": 0, "basis": set()})
            g["qty"] += l["qty"]
            g["cost"] += l["qty"] * l["unit_cost"]
            g["lots"] += 1
            g["basis"].add(l["basis"])
        lot_groups = sorted(
            ({"period": g["period"], "source": g["source"], "qty": round(g["qty"], 12),
              "cost_twd": round(g["cost"], 2), "lots": g["lots"],
              "avg_cost_twd": round(g["cost"] / g["qty"], 6) if g["qty"] else 0.0,
              "unrealized_pnl_twd": round(g["qty"] * px - g["cost"], 2) if px else None,
              "basis": "known" if g["basis"] == {"known"} else ("unknown" if "unknown" in g["basis"] else "mixed")}
             for g in groups.values()),
            key=lambda x: x["cost_twd"], reverse=True)
        pos = {
            "lot_groups": lot_groups[:20],
            "currency": cur, "qty": round(qty, 12),
            "avg_cost_twd": round(cost / qty, 6) if qty else 0.0,
            "cost_twd": round(cost, 2),
            "price_twd": round(px, 6) if px else None,
            "value_twd": round(value, 2) if value is not None else None,
            "unrealized_pnl_twd": round(value - cost, 2) if value is not None else None,
            "unrealized_pnl_pct": round((value - cost) / cost * 100, 2) if (value is not None and cost > 0) else None,
            "lots": len(ls),
            "basis_known_pct": round(known_qty / qty * 100, 1) if qty else 0.0,
            "actual_qty": actual.get(cur),
            "qty_gap_vs_exchange": round(actual[cur] - qty, 12) if cur in actual else None,
        }
        positions.append(pos)
        tot_cost += cost
        if value is not None:
            tot_value += value
    positions.sort(key=lambda p: p["value_twd"] or 0, reverse=True)

    return {
        "positions": positions,
        "total_cost_twd": round(tot_cost, 2),
        "total_value_twd": round(tot_value, 2),
        "total_unrealized_pnl_twd": round(tot_value - tot_cost, 2),
        "total_unrealized_pnl_pct": round((tot_value - tot_cost) / tot_cost * 100, 2) if tot_cost > 0 else None,
        "method": method, "reward_basis": reward_basis,
        "unmatched_qty": book["unmatched_qty"],
        "adjustments": adjustments,
        "aligned_to_exchange": bool(adjustments) or (align_to_exchange and actual_ok),
        "ledger_qty": {k: v for k, v in ledger_qty.items() if abs(v) > 1e-12},
        "note": "數量以交易所餘額為準（adjustments 列出調整過的部分）。成本以『當時』日收盤價換算 TWD；"
                "basis_known_pct 為成本可追溯的比例；unmatched_qty 是賣出量超過可追溯買入量的部分"
                "（API 歷史起點之前的買入），已排除在損益外。",
    }


def get_realized_pnl(method: str = "fifo", reward_basis: str = "market",
                     currency: str = "", limit: int = 50) -> Dict[str, Any]:
    """【LLM Tool】已實現損益：每筆賣出配對到哪些歷史買入批次、賺賠多少。

    Args:
        currency: 只看某個幣（如 'BTC'），空字串＝全部
        limit: 回傳最近幾筆明細（預設 50）
    """
    return summarize_realized(build_lots(method=method, reward_basis=reward_basis),
                              currency=currency, limit=limit)


def summarize_realized(book: Dict[str, Any], currency: str = "", limit: int = 50) -> Dict[str, Any]:
    """把 build_lots 的結果整理成已實現損益摘要（可重用同一份 book）。"""
    method, reward_basis = book["method"], book["reward_basis"]
    rec = book["realized"]
    if currency:
        cur = currency.upper()
        rec = [r for r in rec if r["currency"] == cur]

    by_cur: Dict[str, Dict[str, float]] = {}
    for r in rec:
        s = by_cur.setdefault(r["currency"], {"pnl_twd": 0.0, "cost_twd": 0.0, "trades": 0, "wins": 0})
        s["pnl_twd"] += r["pnl_twd"]
        s["cost_twd"] += r["cost_twd"]
        s["trades"] += 1
        s["wins"] += 1 if r["pnl_twd"] >= 0 else 0
    summary = [{"currency": c, "realized_pnl_twd": round(v["pnl_twd"], 2),
                "cost_twd": round(v["cost_twd"], 2),
                "return_pct": round(v["pnl_twd"] / v["cost_twd"] * 100, 2) if v["cost_twd"] > 0 else None,
                "closes": v["trades"],
                "win_rate_pct": round(v["wins"] / v["trades"] * 100, 1) if v["trades"] else None}
               for c, v in by_cur.items()]
    summary.sort(key=lambda x: x["realized_pnl_twd"], reverse=True)

    detail = []
    for r in sorted(rec, key=lambda x: x["ts"] or 0, reverse=True)[:limit]:
        held = None
        srcs = [u["ts"] for u in r["lots_used"] if u.get("ts")]
        if srcs and r["ts"]:
            held = round((r["ts"] - min(srcs)) / 86400000, 1)
        detail.append({
            "time": dt.datetime.fromtimestamp((r["ts"] or 0) / 1000).strftime("%Y-%m-%d %H:%M"),
            "currency": r["currency"], "qty": r["qty"],
            "proceeds_twd": r["proceeds_twd"], "cost_twd": r["cost_twd"],
            "pnl_twd": r["pnl_twd"], "pnl_pct": r["pnl_pct"],
            "matched_lots": [
                {"買入日": dt.datetime.fromtimestamp(u["ts"] / 1000).strftime("%Y-%m-%d") if u.get("ts") else "移動平均",
                 "數量": round(u["qty"], 10), "成本單價": round(u["unit_cost"], 6), "成本來源": u["basis"]}
                for u in r["lots_used"]],
            "holding_days": held, "basis_quality": r["basis_quality"], "note": r["note"],
        })

    total = sum(r["pnl_twd"] for r in rec)
    return {
        "total_realized_pnl_twd": round(total, 2),
        "by_currency": summary, "recent": detail, "closes": len(rec),
        "method": method, "reward_basis": reward_basis,
        "unmatched_qty": book["unmatched_qty"],
        "fee_cost_twd": book["fee_cost_twd"],
        "note": "配對法可切換（fifo/average）；成本以成交當時日收盤價換算 TWD。"
                "unmatched_qty 為找不到對應買入批次的賣出量，已排除。",
    }

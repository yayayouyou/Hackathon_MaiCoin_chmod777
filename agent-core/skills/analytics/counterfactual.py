"""
skills/analytics/counterfactual.py — 反事實：主動買賣 vs「買了就抱」

`backtester` / `event_study` 回測的是**市場策略**（均線、RSI、事件研究）。
這裡回測的是**使用者自己的交易紀錄**：如果當初什麼都不做，只是買了就抱，會怎樣？

核心恆等式（可證明，不需重建現金帳）：
    設 acquired_qty = 累積(買 + 轉入)、last_price = 期末價。
    「買了就抱、永不賣」的加密淨值 = Σ acquired_qty × last_price
    實際加密淨值 = 剩餘部位市值 + 轉出部位仍持有 + 賣出換到的現金
                = HOLD 淨值 − Σ_sell qty × (last_price − sell_price)
    ⇒ sell_vs_hold = Σ_sell qty × (last_price − sell_price)
      正好等於「主動買賣相對於買了就抱，少賺（或多賺）的淨值」。

再加上估計手續費（原始 CSV 未含），即為主動交易的總成本。

────────────────────────────────────────────────────────────────
修正 2（搬遷時一併修掉的 bug）：**資本可行性**
────────────────────────────────────────────────────────────────
舊版直接把「買了就抱會多賺 26,937,347 TWD」當結論丟出去，卻沒問一句：
**那筆錢當初拿得出來嗎？** 「買了就抱」情境下沒有任何一塊錢從賣出回收，
所有**買進**成本必須同時在場，而實際交易是靠同一筆錢反覆周轉堆出來的。

主辦 CSV 實測（★ 這裡的數字被 tests/test_trading_dna.py 釘死，不是估計值）：

  · 續抱所需本金 = 全期買進累計 = **59,627,185 TWD**（單調遞增，峰值＝總額）。
  · 帳戶淨投入本金 = 24,274,547 TWD（入金 31,903,534 − 出金 7,628,987）。
  · 倍率 2.46× → 在 3× 門檻內 → `capital_feasible = True`。
  · 但實際壓在買進上的峰值資本只有 **79,775 TWD**：資本一年周轉約 8.7 次、
    平均持有 2.7 天。續抱要的是它的 747 倍。

⚠️ 曾經算錯的地方（別再犯）：舊版把**入金取得的幣**（市值 163,860,721，佔 73%）
也當成本金累加，得到 223,487,907 / 9.21× / `feasible=False`。入金是外部免費轉入，
一塊 TWD 都沒掏，而續抱情境同樣白拿這些幣（`hold_networth` 也把 `deposited_qty`
算成禮物）——把它算進分子等於憑空灌水 3.75 倍，而且足以翻轉旗標。

回傳因此多帶：
  - `hold_capital_required_twd`：續抱情境的峰值同時在場本金（＝全期買進累計）
  - `actual_peak_capital_twd`：實際情境壓在買進上的峰值 TWD（買進 − 賣出回收的最大值）
  - `net_capital_deployed_twd`：帳戶淨投入本金
  - `capital_feasible`：`hold_capital_required > 3 × 淨投入本金` 即為 False
  - `caveat`：分級警語。**倍率 > 1 就會明講「需要幾倍本金」**，不會因為旗標是 True
    就讓金額變成可以隨口引用的頭條。

**這個指標是次要參考，不是頭條數字。** 它證明的是「主動交易沒有超額報酬」的方向，
不是「你少賺了兩千七百萬」的絕對金額。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from skills.analytics.csv_source import load_events_for_analysis
from skills.analytics.equity_curve import _f, replay_events

# MAX 手續費：Maker 0.08% / Taker 0.16%。市價單多為 taker，取 taker 作保守估計。
DEFAULT_FEE_RATE = 0.0016

# 續抱情境所需本金超過淨投入本金的幾倍，就判定「執行不了」。
# 3 倍是刻意寬鬆的手挑門檻：留給「加碼、複投、部分獲利再投入」的合理空間，
# 超過就不是資金調度問題而是根本沒那麼多錢。
# ★ 沒有用任何真實帳本分布校準過，接真實帳本前請重新校準。
# ★ 不要為了讓某份資料得到想要的結論而回頭調這個數字：主辦 CSV 是 2.46×，
#   落在門檻內（True）。「續抱其實要 2.5 倍本金」這件事由 caveat 講清楚，
#   不是靠把門檻壓到 2× 硬換一個 False。
CAPITAL_FEASIBLE_MULTIPLE = 3.0

# 倍率超過這個值就算「本金要加碼才做得到」——旗標仍可能是 True，
# 但 caveat 必須把「需要幾倍本金」講出來，不能讓金額被當成隨手可引用的頭條。
CAPITAL_STRETCH_MULTIPLE = 1.0


def _verdict(svh: float, fee: float, active_cost: float, hold_nw: float) -> str:
    pct = (active_cost / hold_nw * 100.0) if hold_nw > 1e-6 else 0.0
    if active_cost > 0:
        return (
            f"若當初『買了就抱』，加密淨值會多約 {active_cost:,.0f} TWD"
            f"（約 {pct:.1f}%）：主動賣出的機會成本 {svh:,.0f} + 估計手續費 {fee:,.0f}。"
            f"主動交易並未帶來超額報酬，反而付出成本——這正是 AI 紀律層的價值。"
        )
    return (
        f"主動交易相對買了就抱多賺約 {-svh:,.0f} TWD，但仍付出估計手續費 {fee:,.0f}；"
        f"淨效益 {-active_cost:,.0f} TWD。"
    )


def _caveat(feasible: Optional[bool], required: float, net_capital: float,
            turnover: Optional[float]) -> str:
    """分級警語 —— 這段字串會被 LLM 直接唸出來，所以限制條件要寫在字串裡。

    三級：算不出（None）／要加碼才做得到（True 但倍率 > 1）／根本沒那麼多錢（False）。
    「旗標是 True」**不等於**「金額可以當頭條講」：倍率一旦大於 1，
    使用者當初就得多掏好幾倍的錢，這句話必須跟著金額一起出現。
    """
    if feasible is None:
        return ("無法判定資本可行性：這份帳本沒有 TWD 出入金紀錄，算不出淨投入本金。"
                "請把 sell_vs_hold 當方向性參考，不要當絕對金額宣稱。")
    multiple = required / net_capital if net_capital > 1e-6 else 0.0
    turn = f"、資本一年周轉約 {turnover:.1f} 次" if turnover else ""
    if feasible and multiple <= CAPITAL_STRETCH_MULTIPLE:
        return ("續抱情境所需本金不超過帳戶淨投入本金，資金上做得到，金額具參考性；"
                "但仍是事後回看的反事實，不代表當時判斷得出來。")
    if feasible:
        return (
            f"⚠️ 金額是上限估計，不要說成「你少賺了 XX 元」。"
            f"「買了就抱」需要 {required:,.0f} TWD 本金**同時在場**，"
            f"是這個帳戶淨投入本金 {net_capital:,.0f} TWD 的 {multiple:.1f} 倍——"
            f"也就是當初得多掏好幾倍的錢，而且整年一次都不能賣{turn}。"
            f"資金調度上勉強在合理範圍內，但這是事後回看的反事實，"
            f"請當成「主動交易沒有超額報酬」的方向性證據。"
        )
    return (
        f"⚠️ 僅供方法學示意，不可當絕對金額宣稱。"
        f"「買了就抱」需要 {required:,.0f} TWD 本金**同時在場**，"
        f"但這個帳戶的淨投入本金只有 {net_capital:,.0f} TWD"
        f"（差距 {multiple:.1f} 倍{turn}）——"
        f"實際獲利是靠同一筆錢快速周轉堆出來的，續抱情境根本執行不了。"
        f"請把這個數字當成「主動交易沒有超額報酬」的方向性證據，"
        f"不要說成「你少賺了 XX 元」。"
    )


def run_sell_vs_hold(snap: Dict[str, Any],
                     fee_rate: float = DEFAULT_FEE_RATE) -> Dict[str, Any]:
    """反事實比較的計算核心（`equity_curve.replay_events()` 的結果 → 結論 dict）。"""
    per_ccy = snap.get("per_currency") or {}
    traded_notional = _f(snap.get("traded_notional_twd"))
    fee_drag = traded_notional * fee_rate

    # 每幣 sell_vs_hold：賣掉的那些量，若當初沒賣，今天值多少
    agg: Dict[str, Dict[str, float]] = defaultdict(
        lambda: {"qty": 0.0, "proceeds": 0.0, "hold_val": 0.0})
    for r in (snap.get("realized") or []):
        last_price = _f((per_ccy.get(r["currency"]) or {}).get("last_price"))
        a = agg[r["currency"]]
        a["qty"] += r["qty"]
        a["proceeds"] += r["proceeds_twd"]
        a["hold_val"] += r["qty"] * last_price

    per_coin: List[Dict[str, Any]] = []
    total_svh = 0.0
    for ccy, a in agg.items():
        svh = a["hold_val"] - a["proceeds"]
        total_svh += svh
        per_coin.append({
            "currency": ccy,
            "sold_qty": round(a["qty"], 8),
            "avg_sell_price": round(a["proceeds"] / a["qty"], 4) if a["qty"] > 1e-12 else 0.0,
            "last_price": round(_f((per_ccy.get(ccy) or {}).get("last_price")), 4),
            "sell_vs_hold_twd": round(svh, 2),
        })
    per_coin.sort(key=lambda c: abs(c["sell_vs_hold_twd"]), reverse=True)

    # 買了就抱淨值 = Σ 取得數量 × 期末價
    hold_networth = sum((_f(s.get("bought_qty")) + _f(s.get("deposited_qty")))
                        * _f(s.get("last_price")) for s in per_ccy.values())
    actual_networth = hold_networth - total_svh
    active_cost = total_svh + fee_drag

    # ── 修正 2：資本可行性 ──
    # 續抱情境不賣 → 買進成本永不回收，峰值同時在場本金＝全期買進累計；
    # 實際交易靠賣出把錢放回來，峰值遠低於此（差距就是「資本周轉」的價值）。
    # 兩者都由 replay_events 只對主動買賣累加（入金取得的幣不花 TWD，不列入本金）。
    required = _f(snap.get("hold_capital_peak_twd"))
    actual_peak = _f(snap.get("actual_peak_capital_twd"))
    net_capital = _f(snap.get("twd_deposit")) - _f(snap.get("twd_withdrawal"))
    if net_capital > 1e-6:
        feasible: Optional[bool] = required <= CAPITAL_FEASIBLE_MULTIPLE * net_capital
        turnover: Optional[float] = traded_notional / net_capital
    else:
        feasible, turnover = None, None

    return {
        "fee_rate": fee_rate,
        "traded_notional_twd": round(traded_notional, 2),
        "fee_drag_twd": round(fee_drag, 2),
        "sell_vs_hold_twd": round(total_svh, 2),
        "hold_networth_twd": round(hold_networth, 2),
        "actual_networth_twd": round(actual_networth, 2),
        "active_cost_twd": round(active_cost, 2),
        "per_coin": per_coin,
        "verdict": _verdict(total_svh, fee_drag, active_cost, hold_networth),
        # ── 資本可行性（修正 2）──
        "hold_capital_required_twd": round(required, 2),
        "actual_peak_capital_twd": round(actual_peak, 2),
        "net_capital_deployed_twd": round(net_capital, 2),
        "capital_multiple_needed": round(required / net_capital, 2) if net_capital > 1e-6 else None,
        "capital_turnover_x": round(turnover, 2) if turnover is not None else None,
        "capital_feasible": feasible,
        "capital_feasible_rule": f"hold_capital_required > {CAPITAL_FEASIBLE_MULTIPLE:g} × 淨投入本金 → False",
        "caveat": _caveat(feasible, required, net_capital, turnover),
    }


# ── 對外入口（LLM Tool）────────────────────────────────────────────
def compare_sell_vs_hold(source: str = "demo", path: str = "",
                         fee_rate: float = DEFAULT_FEE_RATE) -> Dict[str, Any]:
    """【LLM Tool】反事實比較：使用者的實際買賣 vs「買了就抱」誰的淨值高。

    同時估算手續費侵蝕，並檢查續抱情境是否**在資本上做得到**
    （capital_feasible=false 時金額只能當方法學示意，必須連同 caveat 一起講）。

    Args:
        source: 'demo'＝訪客示範帳戶 CSV 種子（預設）；'ledger'＝MAX 真實帳本
        path: source='demo' 時的 CSV 路徑，留空用預設示範帳戶
        fee_rate: 手續費率，預設 0.0016（MAX taker 0.16%）
    """
    got = load_events_for_analysis(source=source, path=path)
    if got.get("error"):
        return {"error": got["error"], "source": got.get("source")}

    snap = replay_events(got["events"], price_lookup=got.get("price_lookup"))
    out = run_sell_vs_hold(snap, fee_rate=fee_rate)
    out["source"] = got["source"]
    out["note"] = ("假設揭露：手續費以固定費率估算（原始資料未含實際扣款）；"
                   "轉入視為外部取得、轉出視為仍持有。"
                   "sell_vs_hold 是**次要指標**，先看 capital_feasible 再決定怎麼引用金額。")
    return out

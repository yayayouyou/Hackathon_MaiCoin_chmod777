"""
skills/analytics/shadow_account.py — 從你自己的交易紀錄反推行為偏誤

接在 position_ledger（帳本）與 lot_engine（批次配對）之後：同一份資料，
從「你賺賠多少」換個角度看成「你**習慣怎麼交易**」。

四個行為指標：
  1. 處置效應   賺的抱不住、賠的捨不得砍（比較獲利與虧損部位的持有時間）
  2. 追漲殺跌   買在漲過一段之後、賣在跌過一段之後（看進出場前的價格變化）
  3. 成本拖累   手續費吃掉多少毛利（過度交易的客觀後果）
  4. 攤平傾向   在成本之下加碼的頻率與後果

**統計誠實是這個模組的核心設計**：行為偏誤最容易從少數幾筆交易「看出」
根本不存在的模式。因此每個指標都回報樣本數，且**樣本不足時只給數字、
不給結論**——寧可說「資料不夠」，也不要用三筆交易斷言使用者有心理偏誤。
"""
import statistics
from typing import Any, Dict, List, Optional

from loguru import logger

# 各指標「敢下結論」所需的最小樣本。低於此只報數字不下判斷。
MIN_N_DISPOSITION = 8      # 獲利、虧損兩組各自需要的筆數
MIN_N_TIMING = 20          # 進出場時機
MIN_N_AVERAGING = 10       # 攤平

# 金額太小的配對是尾差/塵埃，會嚴重稀釋統計（實測 43 筆平倉裡只有 9 筆 ≥100 TWD）
DUST_TWD = 100.0


def _f(x, d=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _hold_days(rec: Dict[str, Any]) -> Optional[float]:
    """一筆平倉的持有天數（以最早被平掉的批次起算）。"""
    used = [u.get("ts") for u in (rec.get("lots_used") or []) if u.get("ts")]
    if not used or not rec.get("ts"):
        return None
    return (rec["ts"] - min(used)) / 86_400_000


def _verdict(ok: bool, n: int, min_n: int, yes: str, no: str) -> Dict[str, Any]:
    """樣本足夠才下結論；否則明講資料不夠。"""
    if n < min_n:
        return {"conclusion": None, "sample_ok": False,
                "note": f"樣本僅 {n} 筆（需 ≥{min_n} 筆才足以判斷），只列數字不下結論。"}
    return {"conclusion": yes if ok else no, "sample_ok": True, "note": ""}


# ── 1. 處置效應 ────────────────────────────────────────────────────
def _disposition(realized: List[Dict[str, Any]]) -> Dict[str, Any]:
    """賺的抱不住、賠的捨不得砍？比較兩組的持有時間。

    經典的處置效應（Shefrin & Statman）：投資人傾向太早賣掉獲利部位、
    太久抱著虧損部位。這裡用「獲利平倉的持有天數 vs 虧損平倉的持有天數」
    當代理指標——若獲利明顯抱得比較短，就是這個模式。
    """
    wins = [(r, _hold_days(r)) for r in realized if r["pnl_twd"] > 0]
    loss = [(r, _hold_days(r)) for r in realized if r["pnl_twd"] < 0]
    wh = [h for _, h in wins if h is not None]
    lh = [h for _, h in loss if h is not None]
    n = min(len(wh), len(lh))
    out: Dict[str, Any] = {
        "metric": "處置效應（賺的抱不住、賠的捨不得砍）",
        "winners": {"n": len(wh), "median_hold_days": round(statistics.median(wh), 1) if wh else None},
        "losers": {"n": len(lh), "median_hold_days": round(statistics.median(lh), 1) if lh else None},
    }
    if wh and lh:
        wm, lm = statistics.median(wh), statistics.median(lh)
        out["ratio_loser_over_winner"] = round(lm / wm, 2) if wm > 0 else None
        # 虧損部位抱得比獲利久 1.5 倍以上才算明顯
        out.update(_verdict(lm > wm * 1.5, n, MIN_N_DISPOSITION,
                            f"有處置效應傾向：虧損部位中位持有 {lm:.1f} 天，"
                            f"獲利部位只有 {wm:.1f} 天（{lm/wm:.1f} 倍）。",
                            f"未見明顯處置效應：獲利中位 {wm:.1f} 天、虧損中位 {lm:.1f} 天，差距不大。"))
    else:
        out.update({"conclusion": None, "sample_ok": False,
                    "note": "獲利或虧損其中一組沒有可用的持有天數，無法比較。"})
    return out


# ── 2. 追漲殺跌 ────────────────────────────────────────────────────
def _timing(events: List[Dict[str, Any]], lookback_days: int = 7) -> Dict[str, Any]:
    """進出場前價格已經走了多少？追漲＝買在漲過之後，殺跌＝賣在跌過之後。"""
    from skills.analytics.lot_engine import twd_price_at

    buys: List[float] = []
    sells: List[float] = []
    back_ms = lookback_days * 86_400_000
    for e in events:
        cur = e.get("currency")
        if not cur or cur == "TWD" or e.get("source") not in ("trade", "convert"):
            continue
        ts = e.get("ts")
        if not ts:
            continue
        now_px = twd_price_at(cur, ts)
        then_px = twd_price_at(cur, ts - back_ms)
        if not now_px or not then_px or then_px <= 0:
            continue
        chg = (now_px / then_px - 1) * 100
        if _f(e.get("delta")) > 0:
            buys.append(chg)
        elif e.get("disposal"):
            sells.append(chg)

    out: Dict[str, Any] = {
        "metric": f"進出場時機（進出場前 {lookback_days} 天的價格變化）",
        "lookback_days": lookback_days,
        "buys": {"n": len(buys),
                 "median_prior_change_pct": round(statistics.median(buys), 2) if buys else None},
        "sells": {"n": len(sells),
                  "median_prior_change_pct": round(statistics.median(sells), 2) if sells else None},
    }
    if buys:
        chase = statistics.median(buys)
        up_share = sum(1 for b in buys if b > 0) / len(buys) * 100
        out["buys"]["bought_after_rise_pct"] = round(up_share, 1)
        out.update(_verdict(chase > 3 and up_share > 60, len(buys), MIN_N_TIMING,
                            f"偏向追漲：{up_share:.0f}% 的買進發生在前 {lookback_days} 天上漲之後，"
                            f"買進前中位漲幅 {chase:+.1f}%。",
                            f"買點分布尚均衡：{up_share:.0f}% 買在漲勢後，"
                            f"買進前中位變化 {chase:+.1f}%。"))
    else:
        out.update({"conclusion": None, "sample_ok": False, "note": "沒有可對應價格的買進事件。"})
    if sells:
        panic = statistics.median(sells)
        out["sells"]["sold_after_fall_pct"] = round(
            sum(1 for s in sells if s < 0) / len(sells) * 100, 1)
        out["sells"]["median_prior_change_pct"] = round(panic, 2)
    return out


# ── 3. 成本拖累 ────────────────────────────────────────────────────
def _cost_drag(book: Dict[str, Any], realized: List[Dict[str, Any]]) -> Dict[str, Any]:
    """手續費吃掉多少毛利。過度交易講再多，不如看它實際花了多少。"""
    fees = sum(_f(v) for v in (book.get("fee_cost_twd") or {}).values())
    net = sum(_f(r.get("pnl_twd")) for r in realized)
    gross = net + fees
    out = {
        "metric": "成本拖累（手續費 vs 毛利）",
        "total_fees_twd": round(fees, 2),
        "net_realized_twd": round(net, 2),
        "gross_before_fees_twd": round(gross, 2),
        "closes": len(realized),
        "fee_per_close_twd": round(fees / len(realized), 2) if realized else None,
    }
    if gross > 0:
        share = fees / gross * 100
        out["fees_as_pct_of_gross"] = round(share, 1)
        out.update(_verdict(share > 30, len(realized), MIN_N_TIMING,
                            f"成本拖累偏高：手續費 {fees:,.0f} TWD 吃掉毛利的 {share:.0f}%"
                            f"（毛利 {gross:,.0f} → 淨利 {net:,.0f}）。減少進出次數的效益會很直接。",
                            f"成本尚可控：手續費佔毛利 {share:.0f}%。"))
    else:
        out.update({"conclusion": None, "sample_ok": False,
                    "note": "毛利非正，手續費佔比無意義（先看策略本身是否有效）。"})
    return out


# ── 4. 攤平傾向 ────────────────────────────────────────────────────
def _averaging_down(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """在自己的平均成本之下加碼的頻率。

    攤平本身不是錯——錯的是「只在下跌時加碼、卻沒有對應的出場計畫」。
    這裡只客觀呈現次數與比例，不預設攤平就是壞事。
    """
    from skills.analytics.lot_engine import _acquire_cost

    pos: Dict[str, Dict[str, float]] = {}     # 幣 → {qty, cost}
    below = above = 0
    examples: List[Dict[str, Any]] = []
    for e in sorted(events, key=lambda x: x.get("ts") or 0):
        cur, delta = e.get("currency"), _f(e.get("delta"))
        if not cur or cur == "TWD" or abs(delta) < 1e-15:
            continue
        st = pos.setdefault(cur, {"qty": 0.0, "cost": 0.0})
        if delta > 0:
            unit, _basis = _acquire_cost(e, "market")
            # 只有「主動買進」才算加碼決策。質押獎勵、入金、錢包互轉都會讓
            # 數量增加，但那不是「你決定在低點加碼」——把它們算進去會讓
            # 攤平比例完全失真（實測 590 筆 MAX 獎勵一度把樣本灌到 945 筆）。
            is_decision = e.get("source") in ("trade", "convert")
            if is_decision and st["qty"] > 1e-12 and unit > 0:
                avg = st["cost"] / st["qty"]
                if unit < avg:
                    below += 1
                    if len(examples) < 5:
                        examples.append({"currency": cur, "ts": e.get("ts"),
                                         "buy_price": round(unit, 6),
                                         "avg_cost_then": round(avg, 6),
                                         "discount_pct": round((unit / avg - 1) * 100, 1)})
                else:
                    above += 1
            st["qty"] += delta
            st["cost"] += delta * unit
        else:
            take = min(-delta, st["qty"])
            if st["qty"] > 1e-12:
                st["cost"] -= st["cost"] * (take / st["qty"])
            st["qty"] -= take

    total = below + above
    out: Dict[str, Any] = {
        "metric": "攤平傾向（在自己均價之下加碼）",
        "adds_below_avg_cost": below, "adds_above_avg_cost": above, "n": total,
        "below_share_pct": round(below / total * 100, 1) if total else None,
        "examples": examples,
    }
    if total:
        share = below / total * 100
        out.update(_verdict(share > 65, total, MIN_N_AVERAGING,
                            f"明顯偏向逢低加碼：{below}/{total}（{share:.0f}%）的加碼發生在均價之下。"
                            "攤平本身不是錯，但要確認有對應的出場條件，否則會愈攤愈重。",
                            f"加碼分布尚均衡：{below}/{total}（{share:.0f}%）在均價之下。"))
    else:
        out.update({"conclusion": None, "sample_ok": False, "note": "沒有可判定的加碼事件。"})
    return out


# ── 對外入口 ───────────────────────────────────────────────────────
def analyze_trading_behavior(method: str = "fifo", min_trade_twd: float = DUST_TWD) -> Dict[str, Any]:
    """【LLM Tool】從你自己的交易帳本反推交易習慣與行為偏誤。

    分析處置效應（賺的抱不住／賠的捨不得砍）、追漲殺跌、手續費拖累、攤平傾向。
    每個指標都附樣本數；樣本不足時只列數字、不下結論。

    Args:
        method: 成本配對法 'fifo'（預設）或 'average'
        min_trade_twd: 小於此金額的平倉視為尾差排除（預設 100 TWD）
    """
    try:
        from skills.analytics.lot_engine import build_lots
        from skills.analytics.position_ledger import load_events, reconcile
    except ImportError as e:  # noqa: BLE001
        return {"error": f"分析模組載入失敗：{e}"}

    events = load_events()
    if not events:
        return {"error": "本地帳本是空的。請先執行資金對帳（reconcile_holdings）建立帳本。"}

    book = build_lots(events, method=method)
    all_rec = book["realized"]
    # 尾差會嚴重稀釋統計：實測 43 筆平倉裡只有 9 筆 ≥100 TWD，
    # 不濾掉的話「持有 0 天」的零星 USDT 會把持有時間中位數整個拉平。
    rec = [r for r in all_rec if abs(_f(r.get("proceeds_twd"))) >= min_trade_twd]

    try:
        conf = reconcile().get("confidence")
    except Exception:  # noqa: BLE001
        conf = None

    metrics = [
        _disposition(rec),
        _timing(events),
        _cost_drag(book, rec),
        _averaging_down(events),
    ]
    findings = [m["conclusion"] for m in metrics if m.get("conclusion")]
    weak = [m["metric"] for m in metrics if not m.get("sample_ok")]

    return {
        "metrics": metrics,
        "findings": findings,
        "insufficient_sample": weak,
        "sample": {
            "closes_total": len(all_rec), "closes_analyzed": len(rec),
            "dust_excluded": len(all_rec) - len(rec), "min_trade_twd": min_trade_twd,
            "events": len(events), "method": method,
        },
        "data_confidence": conf,
        "note": "行為偏誤很容易從少數幾筆交易『看出』其實不存在的模式，"
                "因此樣本不足的指標只列數字、不下結論。"
                + ("　另請注意：資金對帳目前為 partial，代表帳本歷史不完整，"
                   "結論的代表性會受影響。" if conf == "partial" else ""),
    }

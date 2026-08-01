"""
skills/analytics/dna_score.py — 交易 DNA：六軸 0–100 分數 + archetype 標籤

`shadow_account` 給的是「行為偏誤」的原始指標（處置效應、追漲殺跌…），
本模組給的是**產品外殼**：把指標壓成雷達圖畫得出來的六個軸，加一句人話標籤
（「高頻無 alpha 交易者」）。像素世界的交易 DNA 面板就是渲染這個。

────────────────────────────────────────────────────────────────
修正 1（搬遷時一併修掉的 bug）：**兩端飽和**
────────────────────────────────────────────────────────────────
舊版用線性映射 + `clamp(0, 100)`，實跑主辦 CSV 得到
「活躍度 100.0 / 紀律 0.0」——兩個軸貼死在量表兩端，雷達圖看起來像壞掉的儀表，
而且**失去解析度**：活躍度 100 的人和活躍度 300 的人畫出來一模一樣。

改成 logistic（S 型）映射：極端值平滑收斂到 5–95，中段保留鑑別度。
所有軸都保證落在開區間 (SCORE_FLOOR, SCORE_CEIL) 內，永遠不會出現 0 或 100。

────────────────────────────────────────────────────────────────
⚠️ 校準警語（重要，別讓下一個人踩到）
────────────────────────────────────────────────────────────────
下面所有 `*_MID_*` / `*_SCALE` / `ARCHETYPE_*` 常數，都是**針對主辦提供的那份
合成隨機 CSV** 調出來的。那份資料是隨機生成的：每月 384 筆、平均持有 2.7 天、
擇時技巧 ≈0，本來就不是真實散戶的分布。

**接上 MAX 真實帳本後，這些門檻必須重新校準**，否則所有使用者的 archetype
很可能全部落在同一格（例如全部變成「均衡型交易者」）。
校準方法：蒐集一批真實帳本 → 取每個原始指標的分布 → 用中位數當 `MID`、
用四分位距當 `SCALE`，讓母體的分數大致鋪滿 20–80 分。
係數刻意抽成模組層常數（不埋在算式裡）就是為了讓這件事一眼可做。
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from skills.analytics.csv_source import HOME_CCY, load_events_for_analysis
from skills.analytics.equity_curve import MS_PER_DAY, _TRADE_SOURCES, _f, replay_events

# ── 分數上下界：logistic 的漸近線 ─────────────────────────────
# 不用 0/100 當漸近線，是因為「滿分」與「零分」對行為量表沒有意義，
# 而且視覺上會讓雷達圖看起來像量表壞掉。
SCORE_FLOOR = 5.0
SCORE_CEIL = 95.0

# ── 六軸校準係數（★ 需用真實 MAX 帳本重新校準，見模組 docstring）────
# 活躍度：每月交易筆數，取對數尺度（跨度是數量級不是線性）
ACTIVITY_MID_TRADES_PER_MONTH = 30.0   # 每月 30 筆 → 50 分
ACTIVITY_LOG_SCALE = 0.9               # ln 尺度；×e^0.9≈2.5 倍筆數 ≈ +20 分

# 紀律（反過度交易）：單一活躍日的交易筆數，越低越好 → 反向
DISCIPLINE_MID_TRADES_PER_ACTIVE_DAY = 4.0   # 一天 4 筆 → 50 分
DISCIPLINE_SCALE = 2.5                       # 每多 2.5 筆/日 ≈ −20 分

# 擇時：趨勢中性的 timing_skill（賣在均價上方比例 − 買在均價上方比例）
TIMING_MID_SKILL = 0.0                 # 零技巧 → 50 分（與隨機無異）
TIMING_SCALE = 0.06                    # 每 6 個百分點 skill ≈ ±20 分

# 分散：持倉 HHI，越低越分散 → 反向
DIVERSIFICATION_MID_HHI = 0.35         # HHI 0.35（≈ 等權 3 個資產）→ 50 分
DIVERSIFICATION_SCALE = 0.12

# 持有耐心：量加權平均持有天數，取對數尺度（1 天 vs 3 天的差別遠大於 100 天 vs 102 天）
PATIENCE_MID_HOLD_DAYS = 21.0          # 抱三週 → 50 分
PATIENCE_LOG_SCALE = 0.8

# 風險控管：三個成分先合成一個 0–100 的原始姿態分，再過 logistic
RISK_W_CONCENTRATION = 55.0            # 不押單一資產
RISK_W_STABLE_BUFFER = 25.0            # 留穩定幣緩衝
RISK_W_NOT_CHASING = 20.0              # 不追高
RISK_CONTROL_MID = 50.0
RISK_CONTROL_SCALE = 18.0

# ── archetype / 標籤門檻（★ 同樣需要重新校準）─────────────────
ARCHETYPE_OVERTRADE_PER_ACTIVE_DAY = 5.0     # 活躍日均 ≥5 筆＝過度交易
ARCHETYPE_NO_ALPHA_SKILL_BAND = 0.03         # |timing_skill| < 3% ＝與隨機無異
ARCHETYPE_LONG_HOLD_DAYS = 60.0              # 平均持有 ≥60 天＝長期持有
ARCHETYPE_DIVERSIFIED_HHI = 0.30             # HHI < 0.30 ＝分散
ARCHETYPE_CONCENTRATED_WEIGHT = 0.50         # 首位資產 ≥50% ＝集中押注
ARCHETYPE_ACTIVE_TRADES_PER_MONTH = 40.0     # 每月 ≥40 筆＝活躍波段
TAG_CONCENTRATION_WEIGHT = 0.40              # 首位資產 ≥40% → 掛集中標籤
TAG_SHORT_HOLD_DAYS = 7.0                    # 平均持有 ≤7 天＝短線
TAG_STABLE_BUFFER_RATIO = 0.30               # 穩定幣 ≥30% → 有緩衝

# 擇時基準：與該幣前 N 天的觀察均價比較
TREND_WINDOW_DAYS = 14

STABLE_COINS = {"USDT", "USDC"}

# ── 樣本數閘門 ────────────────────────────────────────────────
# 少於這個買賣筆數就不判定「交易性格」：archetype / tags 全部來自比例類指標
#（活躍日均筆數、擇時勝率、持有天數），樣本太小時它們是雜訊不是性格。
# 最危險的情境是「剛綁定、只入金沒交易」的新帳號 —— 舊版會照樣吐出
# 「集中押注型 · 短線持有」這種憑空捏造的人格，且沒有任何旗標讓模型知道要閉嘴。
# 20 筆是手挑的下限（每個軸至少要有兩位數樣本才談得上分布），★ 需用真實帳本重新校準。
MIN_TRADES_FOR_ARCHETYPE = 20

# 六軸的固定順序（前端雷達圖依此順序連線，不要亂動）
AXES = ("活躍度", "紀律", "擇時", "分散", "持有耐心", "風險控管")


def _logistic(x: float, midpoint: float, scale: float, invert: bool = False) -> float:
    """把任意實數壓進 (SCORE_FLOOR, SCORE_CEIL) 的 S 型映射。

    midpoint 對應正中間分數 50；scale 越小越陡（鑑別度高但更容易飽和）。
    """
    if scale <= 0:
        scale = 1e-9
    z = (x - midpoint) / scale
    if invert:
        z = -z
    z = max(-40.0, min(40.0, z))        # 防 math.exp 溢位
    mid = (SCORE_FLOOR + SCORE_CEIL) / 2.0
    span = (SCORE_CEIL - SCORE_FLOOR) / 2.0
    return mid + span * math.tanh(z / 2.0)   # tanh(z/2) ≡ 2·sigmoid(z)−1


def _log_logistic(x: float, midpoint: float, log_scale: float) -> float:
    """對數尺度的 logistic：適合跨數量級的量（交易頻率、持有天數）。"""
    if x <= 0 or midpoint <= 0:
        return SCORE_FLOOR
    return _logistic(math.log(x / midpoint), 0.0, log_scale)


def compute_dna_scores(m: Dict[str, float]) -> Dict[str, float]:
    """原始指標 → 六軸 0–100 分數（logistic，永不飽和在 0 或 100）。

    注意語意：分數高**不等於**投資績效好。「活躍度」高只代表交易頻繁，
    它是一個描述性的軸；真正帶價值判斷的是紀律 / 擇時 / 分散 / 風險控管。
    """
    activity = _log_logistic(_f(m.get("trades_per_month")),
                             ACTIVITY_MID_TRADES_PER_MONTH, ACTIVITY_LOG_SCALE)
    discipline = _logistic(_f(m.get("trades_per_active_day")),
                           DISCIPLINE_MID_TRADES_PER_ACTIVE_DAY, DISCIPLINE_SCALE,
                           invert=True)
    timing = _logistic(_f(m.get("timing_skill")), TIMING_MID_SKILL, TIMING_SCALE)
    diversification = _logistic(_f(m.get("holdings_hhi")),
                                DIVERSIFICATION_MID_HHI, DIVERSIFICATION_SCALE,
                                invert=True)
    patience = _log_logistic(_f(m.get("avg_hold_days")),
                             PATIENCE_MID_HOLD_DAYS, PATIENCE_LOG_SCALE)
    risk_raw = ((1.0 - _f(m.get("top_asset_weight"))) * RISK_W_CONCENTRATION
                + _f(m.get("stable_ratio")) * RISK_W_STABLE_BUFFER
                + (1.0 - _f(m.get("chase_high_rate"))) * RISK_W_NOT_CHASING)
    risk_control = _logistic(risk_raw, RISK_CONTROL_MID, RISK_CONTROL_SCALE)

    return {
        "活躍度": round(activity, 1),
        "紀律": round(discipline, 1),
        "擇時": round(timing, 1),
        "分散": round(diversification, 1),
        "持有耐心": round(patience, 1),
        "風險控管": round(risk_control, 1),
    }


def derive_archetype(m: Dict[str, Any]) -> Tuple[str, List[str]]:
    """原始指標 → 主 archetype 標籤 + 提醒標籤。"""
    tpad = _f(m.get("trades_per_active_day"))
    skill = _f(m.get("timing_skill"))
    hold = _f(m.get("avg_hold_days"))
    hhi = _f(m.get("holdings_hhi"))
    top_w = _f(m.get("top_asset_weight"))
    tpm = _f(m.get("trades_per_month"))
    top_asset = str(m.get("top_asset") or "")

    tags: List[str] = []
    if tpad >= ARCHETYPE_OVERTRADE_PER_ACTIVE_DAY:
        tags.append("過度交易")
    # 趨勢中性判讀：避免把大盤上漲誤判成「追高」
    if skill <= -ARCHETYPE_NO_ALPHA_SKILL_BAND:
        tags.append("買賣時機偏弱")
    elif abs(skill) < ARCHETYPE_NO_ALPHA_SKILL_BAND:
        tags.append("擇時與隨機無異")
    else:
        tags.append("具擇時優勢")
    if top_w >= TAG_CONCENTRATION_WEIGHT and top_asset:
        tags.append(f"部位集中於 {top_asset.upper()}")
    if hold <= TAG_SHORT_HOLD_DAYS:
        tags.append("短線持有")
    elif hold >= ARCHETYPE_LONG_HOLD_DAYS:
        tags.append("長期持有")
    if _f(m.get("stable_ratio")) >= TAG_STABLE_BUFFER_RATIO:
        tags.append("留有穩定幣緩衝")

    if tpad >= ARCHETYPE_OVERTRADE_PER_ACTIVE_DAY and abs(skill) < ARCHETYPE_NO_ALPHA_SKILL_BAND:
        archetype = "高頻無 alpha 交易者"
    elif hold >= ARCHETYPE_LONG_HOLD_DAYS and hhi < ARCHETYPE_DIVERSIFIED_HHI:
        archetype = "分散型長期持有者"
    elif top_w >= ARCHETYPE_CONCENTRATED_WEIGHT:
        archetype = "集中押注型"
    elif tpm >= ARCHETYPE_ACTIVE_TRADES_PER_MONTH:
        archetype = "活躍波段交易者"
    else:
        archetype = "均衡型交易者"
    return archetype, tags


def _trailing_mean_prices(events: List[Dict[str, Any]]) -> Dict[int, float]:
    """每筆事件的「該幣前 N 天觀察到的均價」，當作擇時基準。

    刻意把**所有**帶價事件（含入出金）都納入歷史樣本：它們一樣是市場價格的觀察，
    只是不是使用者的主動決策。回傳 {事件索引: 前 N 日均價}；歷史不足者不列入。
    """
    hist: Dict[str, List[Tuple[int, float]]] = defaultdict(list)
    out: Dict[int, float] = {}
    window_ms = TREND_WINDOW_DAYS * MS_PER_DAY
    for i, e in enumerate(events):
        cur = str(e.get("currency", "")).upper()
        ts = int(e.get("ts") or 0)
        px = _f(e.get("price"))
        prev = hist[cur]
        lo = ts - window_ms
        prices = [p for (t, p) in prev if t >= lo]
        if prices:
            out[i] = sum(prices) / len(prices)
        prev.append((ts, px))
    return out


def behavior_metrics(events: List[Dict[str, Any]], snap: Dict[str, Any]) -> Dict[str, Any]:
    """帳本事件 + 重播結果 → 交易 DNA 的原始指標（每個數字都可回推來源）。"""
    evs = sorted(events, key=lambda x: x.get("ts") or 0)
    m: Dict[str, Any] = {
        "trade_count": 0, "buy_count": 0, "sell_count": 0, "active_days": 0,
        "span_days": 0, "trades_per_active_day": 0.0, "trades_per_month": 0.0,
        "busiest_day_trades": 0, "avg_hold_days": 0.0,
        "buy_above_mean_rate": 0.0, "sell_above_mean_rate": 0.0,
        "chase_high_rate": 0.0, "panic_sell_rate": 0.0,
        "timing_skill": 0.0, "timing_edge": 0.0,
        "win_rate": 0.0, "win_rate_value": 0.0,
        "holdings_hhi": 0.0, "top_asset": "", "top_asset_weight": 0.0,
        "assets_held": 0, "stable_ratio": 0.0, "volatile_ratio": 0.0,
    }
    if not evs:
        return m

    def _is_trade(e: Dict[str, Any]) -> bool:
        # 真實帳本的成交會拆 base/quote 兩腿；TWD 那腿不是「一筆交易」，排除避免翻倍
        return (e.get("source") in _TRADE_SOURCES
                and str(e.get("currency", "")).upper() != HOME_CCY)

    trades = [e for e in evs if _is_trade(e)]
    m["trade_count"] = len(trades)
    m["buy_count"] = sum(1 for e in trades if _f(e.get("delta")) > 0)
    m["sell_count"] = sum(1 for e in trades if e.get("disposal"))

    # ── 活躍度 ──
    by_day: Dict[Any, int] = defaultdict(int)
    for e in trades:
        by_day[datetime.fromtimestamp(int(e["ts"]) / 1000, tz=timezone.utc).date()] += 1
    m["active_days"] = len(by_day)
    m["busiest_day_trades"] = max(by_day.values()) if by_day else 0
    m["span_days"] = max(1, round((int(evs[-1]["ts"]) - int(evs[0]["ts"])) / MS_PER_DAY))
    m["trades_per_active_day"] = (m["trade_count"] / m["active_days"]) if m["active_days"] else 0.0
    m["trades_per_month"] = m["trade_count"] / (m["span_days"] / 30.0)

    # ── 持有耐心（量加權平均持有天數）──
    samples = snap.get("hold_days_samples") or []
    tot_qty = sum(q for (_c, q, _d) in samples)
    if tot_qty > 1e-12:
        m["avg_hold_days"] = sum(q * d for (_c, q, d) in samples) / tot_qty

    # ── 擇時 / 追高殺低（趨勢中性）──
    trailing = _trailing_mean_prices(evs)
    buy_above = buy_tot = sell_above = sell_tot = 0
    buy_notional = buy_qty = sell_notional = sell_qty = 0.0
    for i, e in enumerate(evs):
        if not _is_trade(e):
            continue
        px, qty = _f(e.get("price")), abs(_f(e.get("delta")))
        if _f(e.get("delta")) > 0:
            buy_notional += px * qty
            buy_qty += qty
            if i in trailing:
                buy_tot += 1
                if px > trailing[i]:
                    buy_above += 1
        elif e.get("disposal"):
            sell_notional += px * qty
            sell_qty += qty
            if i in trailing:
                sell_tot += 1
                if px > trailing[i]:
                    sell_above += 1
    m["buy_above_mean_rate"] = buy_above / buy_tot if buy_tot else 0.0
    m["sell_above_mean_rate"] = sell_above / sell_tot if sell_tot else 0.0
    m["chase_high_rate"] = m["buy_above_mean_rate"]
    m["panic_sell_rate"] = 1.0 - m["sell_above_mean_rate"]
    # 趨勢中性：賣得比買得更「相對高」才算有技巧（單看買在均價上方會被大盤走勢主導）
    m["timing_skill"] = m["sell_above_mean_rate"] - m["buy_above_mean_rate"]
    if buy_qty > 1e-12 and sell_qty > 1e-12:
        m["timing_edge"] = (sell_notional / sell_qty) / (buy_notional / buy_qty) - 1.0

    # ── 勝率 ──
    sells = snap.get("realized") or []
    if sells:
        m["win_rate"] = sum(1 for r in sells if r["pnl_twd"] > 0) / len(sells)
        win_val = sum(r["proceeds_twd"] for r in sells if r["pnl_twd"] > 0)
        tot_val = sum(r["proceeds_twd"] for r in sells)
        m["win_rate_value"] = win_val / tot_val if tot_val else 0.0

    # ── 集中度 / 風險偏好（以期末持倉市值計）──
    mv = {c: s["market_value_twd"] for c, s in (snap.get("per_currency") or {}).items()
          if s["market_value_twd"] > 1e-6}
    total_mv = sum(mv.values())
    if total_mv > 0:
        weights = {c: v / total_mv for c, v in mv.items()}
        m["holdings_hhi"] = sum(w * w for w in weights.values())
        m["top_asset"] = max(weights, key=weights.get)
        m["top_asset_weight"] = weights[m["top_asset"]]
        m["assets_held"] = len(weights)
        m["stable_ratio"] = sum(v for c, v in mv.items() if c in STABLE_COINS) / total_mv
        m["volatile_ratio"] = 1.0 - m["stable_ratio"]
    return m


# ── 對外入口（LLM Tool）────────────────────────────────────────────
def get_trading_dna_score(source: str = "demo", path: str = "") -> Dict[str, Any]:
    """【LLM Tool】交易 DNA：六軸 0–100 性格分數 + 一句話 archetype 標籤。

    六軸為 活躍度／紀律／擇時／分散／持有耐心／風險控管，用 logistic 映射，
    永遠落在 5–95 之間（不會出現貼死量表兩端的 0 或 100）。

    Args:
        source: 'demo'＝訪客示範帳戶 CSV 種子（預設）；'ledger'＝MAX 真實帳本
        path: source='demo' 時的 CSV 路徑，留空用預設示範帳戶
    """
    got = load_events_for_analysis(source=source, path=path)
    if got.get("error"):
        return {"error": got["error"], "source": got.get("source")}

    snap = replay_events(got["events"], price_lookup=got.get("price_lookup"))
    m = behavior_metrics(got["events"], snap)
    scores = compute_dna_scores(m)

    # 樣本閘門：筆數不夠就不給人格。旗標放在**頂層**而不是埋在 metrics 底下，
    # 模型才會看到（它不會主動去比對 metrics.trade_count 跟某個門檻）。
    insufficient = m["trade_count"] < MIN_TRADES_FOR_ARCHETYPE
    archetype, tags = (None, []) if insufficient else derive_archetype(m)

    return {
        "source": got["source"],
        "insufficient_data": insufficient,
        "archetype": archetype,
        "tags": tags,
        "axes": list(AXES),
        "scores": scores,
        "metrics": {
            "trade_count": m["trade_count"], "buy_count": m["buy_count"],
            "sell_count": m["sell_count"], "active_days": m["active_days"],
            "span_days": m["span_days"],
            "trades_per_active_day": round(m["trades_per_active_day"], 2),
            "trades_per_month": round(m["trades_per_month"], 1),
            "busiest_day_trades": m["busiest_day_trades"],
            "avg_hold_days": round(m["avg_hold_days"], 1),
            "buy_above_mean_rate": round(m["buy_above_mean_rate"], 3),
            "sell_above_mean_rate": round(m["sell_above_mean_rate"], 3),
            "timing_skill": round(m["timing_skill"], 4),
            "timing_edge": round(m["timing_edge"], 4),
            "win_rate": round(m["win_rate"], 3),
            "win_rate_value": round(m["win_rate_value"], 3),
            "holdings_hhi": round(m["holdings_hhi"], 3),
            "top_asset": m["top_asset"],
            "top_asset_weight": round(m["top_asset_weight"], 3),
            "assets_held": m["assets_held"],
            "stable_ratio": round(m["stable_ratio"], 3),
        },
        "calibration_note": "六軸係數是用主辦提供的**合成隨機 CSV** 調的；"
                            "接上真實 MAX 帳本後門檻需重新校準，否則 archetype 可能全部落在同一格。",
        "note": (
            f"⚠️ 交易筆數只有 {m['trade_count']} 筆（低於 {MIN_TRADES_FOR_ARCHETYPE} 筆門檻），"
            "**無法判定交易性格**：archetype 與標籤已置空，六軸分數只是樣本不足下的初步描述，"
            "不可以拿來宣稱這個人是哪一種交易者。請直接告訴使用者「交易紀錄還太少」。"
            if insufficient else
            "分數高不等於績效好——『活躍度』只是描述交易頻繁程度。"
            "帶價值判斷的是紀律／擇時／分散／風險控管四軸。"
            "擇時 ≈50 分代表進出場時機與隨機無異（沒有 alpha）。"
        ),
    }

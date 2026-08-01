"""
skills/analytics/event_study.py — 組合式事件研究回測引擎（Composable Event-Study）
=====================================================
回測是一個【通用接口】——吃「任一 skill 的訊號事件」，量測其對價格的前瞻影響。
新增回測想法 = 一個 event adapter + 一列 registry，而非一個新 skill。

分層：
  1. run_event_study(events, ...) — 純引擎：事件 → 前瞻報酬 vs 基準（異常報酬）
  2. event adapters（_EVENT_SOURCES registry）— 各 skill 訊號 → 事件
  3. run_signal_backtest(signal, ...) — 統一 LLM 接口，依 signal 派發

統計嚴謹性（經對抗式審查強化 + 借鏡 Vibe-Trading）：
  - 重疊持有窗『叢集折疊』→ 只留獨立事件，避免自相關灌水樣本。
  - 顯著性檢定：Monte Carlo 排列檢定（非參數、主要依據）+ t 統計/近似 p（次要）
    + 最小獨立樣本閘門 → 樣本不足不下結論；bootstrap 90% 信賴區間量化不確定性。
  - publish_lag：盤後才公布的訊號（ETF/財庫）於 T+lag 進場，去除前視偏誤。
  - baseline 排除事件窗，降低自我污染；髒 K 線在資料邊界被 ohlcv_guard 丟棄。
  - registry 契約：asset_scope / direction / publish_lag / accepts 被『強制驗證』，
    錯誤組合直接報錯而非靜默產出看似可信的無意義結果。
  - 經典價量 alpha 因子（momentum_breakout / oversold_rsi / vol_spike）亦為事件源。
  - 每次回測落地 run_card（config 雜湊 + 結果雜湊）→ 可稽核、可偵測結果漂移。
"""

import math
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger


# ──────────────────────────────────────────────
#  共用工具
# ──────────────────────────────────────────────
def _daily_klines(asset: str, exchange_id: str = "binance") -> Optional[pd.DataFrame]:
    from skills.market_data.ccxt_fetcher import _create_exchange, _normalize_symbol
    import ccxt
    coin = asset.upper().replace("/USDT", "").split("/")[0]
    try:
        k = _create_exchange(exchange_id).fetch_ohlcv(_normalize_symbol(f"{coin}/USDT"), timeframe="1d", limit=1000)
    except (ccxt.BaseError, Exception):  # noqa: BLE001
        return None
    if not k:
        return None
    from skills.market_data.ohlcv_guard import clean_ohlcv
    k, dropped = clean_ohlcv(k)   # 資料邊界：丟掉髒 K 線，避免污染回測統計
    if dropped:
        logger.warning(f"回測 {asset} 日線丟棄 {dropped} 根髒 K 線")
    if len(k) < 20:
        return None
    df = pd.DataFrame(k, columns=["ts", "open", "high", "low", "close", "vol"])
    df["ts"] = df["ts"].astype(np.int64)
    return df


def _unwrap(result: Any, list_key: str) -> List[Dict[str, Any]]:
    """統一 adapter 錯誤契約：資料源回 {error} 就依 needs_free_key re-raise；否則取 list_key。
    杜絕『資料源失敗被誤報成沒有事件』的 false-negative。"""
    if isinstance(result, dict) and result.get("error"):
        if result.get("needs_free_key"):
            raise EnvironmentError(result["error"])
        raise RuntimeError(result["error"])
    if isinstance(result, dict):
        return result.get(list_key) or []
    return result or []


def _norm_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _tstat_p(vals: List[float]) -> Tuple[float, float]:
    """單樣本 t 統計 + 近似雙尾 p（檢定平均是否顯著 ≠ 0）。"""
    n = len(vals)
    if n < 2:
        return 0.0, 1.0
    m = float(np.mean(vals))
    sd = float(np.std(vals, ddof=1))
    if sd == 0:
        return (math.copysign(math.inf, m) if m else 0.0), (0.0 if m else 1.0)
    t = m / (sd / math.sqrt(n))
    return t, 2 * (1 - _norm_cdf(abs(t)))


def _permutation_p(closes, hold_days: int, n: int, observed_abn: float, baseline: float,
                   iters: int = 1000) -> Optional[float]:
    """Monte Carlo 排列檢定：隨機挑 n 個進場點 iters 次，看『與隨機進場的差異』≥ 觀測值的比例（雙尾）。
    非參數、對報酬分布不作假設，比 t 檢定更穩健。固定種子 → 可重現。"""
    L = len(closes) - hold_days
    if L <= n or n < 1:
        return None
    fwd = np.array([(closes[i + hold_days] / closes[i] - 1) * 100 for i in range(L)])
    rng = np.random.default_rng(12345)
    obs = abs(observed_abn)
    hits = 0
    for _ in range(iters):
        idx = rng.choice(L, size=n, replace=False)
        rand_abn = float(fwd[idx].mean()) - baseline
        if abs(rand_abn) >= obs:
            hits += 1
    return round(hits / iters, 4)


def _bootstrap_ci(abn: List[float], iters: int = 2000) -> Tuple[Optional[float], Optional[float]]:
    """對事件異常報酬做 bootstrap 重抽 → 90% 信賴區間（5%/95% 分位）。固定種子 → 可重現。"""
    a = np.array(abn, dtype=float)
    if len(a) < 3:
        return None, None
    rng = np.random.default_rng(999)
    means = np.array([a[rng.integers(0, len(a), len(a))].mean() for _ in range(iters)])
    return round(float(np.percentile(means, 5)), 2), round(float(np.percentile(means, 95)), 2)


# ──────────────────────────────────────────────
#  1) 純引擎
# ──────────────────────────────────────────────
def run_event_study(events: List[Dict[str, Any]], asset: str = "BTC", hold_days: int = 7,
                    direction: str = "long", publish_lag: int = 0, min_events: int = 5,
                    signal: str = "custom", signal_label: str = "自訂事件", hypothesis: str = "") -> Dict[str, Any]:
    """
    純事件研究引擎：事件 → 其後 hold_days 天 asset 的前瞻報酬，對比隨機進場基準（異常報酬）。

    publish_lag：事件資訊於盤後才可知者（如 ETF/財庫），進場延到 T+lag 根 close（去前視偏誤）。
    重疊窗叢集折疊：只留彼此相距 ≥ hold_days 的獨立事件。min_events：獨立樣本下限，不足不下結論。
    """
    # 入口驗證（防 LLM 把數字序列化成字串、或傳負值/浮點導致越界/崩潰）
    try:
        hold_days, publish_lag = int(hold_days), int(publish_lag)
    except (TypeError, ValueError):
        return {"signal": signal, "error": "hold_days / publish_lag 需為整數。"}
    if hold_days < 1:
        return {"signal": signal, "error": "hold_days 需為正整數。"}
    if publish_lag < 0:
        return {"signal": signal, "error": "publish_lag 需為非負整數。"}
    direction = "short" if str(direction).lower() == "short" else "long"   # 正規化（非 short 一律 long）

    meta = {"signal": signal, "signal_label": signal_label, "asset": asset.upper(),
            "direction": direction, "hold_days": hold_days, "publish_lag": publish_lag}
    if not events:
        return {**meta, "message": f"未產生任何『{signal_label}』事件，無法回測。", "events_matched": 0}

    norm = []
    for e in events:
        ts = e.get("ts")
        if ts is None and e.get("date"):
            try:
                ts = int(datetime.strptime(str(e["date"])[:10], "%Y-%m-%d")
                         .replace(tzinfo=timezone.utc).timestamp() * 1000)
            except (ValueError, TypeError):
                continue
        if ts is None:
            continue
        norm.append({"ts": int(ts),
                     "date": e.get("date") or datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
                     "label": e.get("label", ""), "magnitude": e.get("magnitude")})
    if not norm:
        return {**meta, "message": "事件缺少有效時間戳。", "events_matched": 0}

    df = _daily_klines(asset)
    if df is None or len(df) < hold_days + 20:
        return {**meta, "error": f"{asset} 日線歷史不足，無法回測。"}
    cov_start, cov_end = int(df["ts"].iloc[0]), int(df["ts"].iloc[-1])
    closes = df["close"].astype(float).values
    sign = 1.0 if direction != "short" else -1.0

    trades, out_of_range, deduped, clustered = [], 0, 0, 0
    seen_entry, last_entry = set(), None
    excluded = set()   # 事件窗覆蓋的進場索引 → 從 baseline 剔除
    for ev in sorted(norm, key=lambda x: x["ts"]):
        if ev["ts"] < cov_start or ev["ts"] > cov_end:
            out_of_range += 1
            continue
        idx = df.index[df["ts"] >= ev["ts"]]
        if not len(idx):
            out_of_range += 1
            continue
        entry_i = int(idx[0]) + publish_lag        # T+lag 進場（去前視）
        if entry_i + hold_days >= len(df) or entry_i >= len(df):
            out_of_range += 1
            continue
        if entry_i in seen_entry:                  # 同一根進場 K 線多事件 → 計一次
            deduped += 1
            continue
        if last_entry is not None and entry_i - last_entry < hold_days:  # 重疊窗 → 叢集折疊
            clustered += 1
            continue
        entry, exit_ = float(closes[entry_i]), float(closes[entry_i + hold_days])
        if entry <= 0 or exit_ <= 0:               # 壞資料/0 收盤 → 跳過（避免除零/污染基準）
            out_of_range += 1
            continue
        seen_entry.add(entry_i)
        last_entry = entry_i
        for j in range(entry_i, min(entry_i + hold_days, len(closes))):
            excluded.add(j)
        # 存原始精度價格：低價迷因幣（如 PEPE ~2.8e-06）若 round(,2) 會變 0.0 → 後續除零/污染
        trades.append({"date": ev["date"], "label": ev["label"], "magnitude": ev["magnitude"],
                       "entry": entry, "exit": exit_})

    if not trades:
        return {**meta,
                "message": f"『{signal_label}』事件皆落在 {asset} 日線覆蓋範圍外（近 ~{len(df)} 天）或被重疊折疊，無法回測。",
                "events_matched": len(norm), "events_out_of_range": out_of_range}

    # baseline：全期任意進場、排除事件窗（降低自我污染）+ 過濾 0 收盤（防 inf 污染）
    base = [(closes[i + hold_days] / closes[i] - 1) * 100
            for i in range(len(closes) - hold_days)
            if i not in excluded and closes[i] > 0 and closes[i + hold_days] > 0]
    baseline = float(np.mean(base)) if base else 0.0

    for t in trades:
        ret = sign * (t["exit"] / t["entry"] - 1) * 100
        t["return_pct"] = round(ret, 2)
        t["abnormal_pct"] = round(ret - sign * baseline, 2)

    rets = [t["return_pct"] for t in trades]
    abn = [t["abnormal_pct"] for t in trades]
    n = len(trades)
    wins = sum(1 for r in rets if r > 0)
    avg_abn = float(np.mean(abn))
    tstat, pval = _tstat_p(abn)                                  # 用『獨立』樣本（已叢集折疊）
    perm_p = _permutation_p(closes, hold_days, n, avg_abn, baseline) if n >= 3 else None
    ci_lo, ci_hi = _bootstrap_ci(abn)                           # 90% 信賴區間

    low_sample = n < min_events
    # 顯著性以『排列檢定』為主（非參數、更穩健）；無法算時退回 t 檢定
    if perm_p is not None:
        significant = perm_p < 0.05
        sig_txt = f"排列檢定 p={perm_p:.3f}"
    else:
        significant = (abs(tstat) > 2.0) and (pval < 0.05)
        sig_txt = f"t={tstat:.2f}, p={pval:.2f}"
    if low_sample:
        verdict = f"獨立樣本不足（n={n} < {min_events}），不足以下結論——僅供參考。"
    elif not significant:
        verdict = f"事件後與隨機進場無統計顯著差異（{sig_txt}），無明確 edge。"
    else:
        up = avg_abn > 0
        word = ("上漲" if direction != "short" else "下跌")
        verdict = (f"顯著：事件後傾向{word}、且優於隨機進場（異常報酬 {avg_abn:+.2f}%, {sig_txt}）"
                   if up else
                   f"顯著：事件後反而偏弱於隨機進場（異常報酬 {avg_abn:+.2f}%, {sig_txt}）")

    return {
        **meta,
        "hypothesis": hypothesis or f"『{signal_label}』事件後 {hold_days} 天 {asset} 的價格表現？",
        "events_matched": len(norm),
        "events_tested": n,                     # 獨立事件數（叢集折疊後）
        "events_out_of_range": out_of_range,
        "events_deduped_same_candle": deduped,
        "events_clustered_overlapping": clustered,
        "avg_return_pct": round(float(np.mean(rets)), 2),
        "median_return_pct": round(float(np.median(rets)), 2),
        "win_rate_pct": round(wins / n * 100, 1),
        "baseline_avg_return_pct": round(baseline, 2),
        "avg_abnormal_return_pct": round(avg_abn, 2),
        "abnormal_std_pct": round(float(np.std(abn, ddof=1)) if n > 1 else 0.0, 2),
        "abnormal_ci90_pct": [ci_lo, ci_hi] if ci_lo is not None else None,   # bootstrap 90% 信賴區間
        "t_stat": round(tstat, 2),
        "p_value": round(pval, 3),
        "permutation_p": perm_p,                    # Monte Carlo 排列檢定 p（主要顯著性依據）
        "significant": bool(significant and not low_sample),
        "low_sample": bool(low_sample),
        "verdict": verdict,
        "best": max(trades, key=lambda t: t["return_pct"]),
        "worst": min(trades, key=lambda t: t["return_pct"]),
        "sample_events": trades[-8:],
        "caveat": "事件常集中特定市場環境(regime)，異常報酬仍可能含環境效應；統計觀察非因果、非投資建議。",
    }


# ──────────────────────────────────────────────
#  2) Event adapters — 各 skill 訊號 → 事件
# ──────────────────────────────────────────────
def _adapt_treasury(asset: str = "BTC", ticker: Optional[str] = None,
                    threshold: Optional[float] = None, **_) -> Tuple[List[Dict[str, Any]], str]:
    from skills.market_intel.btc_treasuries import _company_history, get_btc_treasuries
    min_btc = threshold if threshold is not None else 100.0
    if ticker:
        tickers = [ticker.upper()]
    else:
        tickers = [h["ticker"] for h in _unwrap(get_btc_treasuries(top_n=8), "top_holders")][:6] or ["MSTR"]
    events = []
    for tk in tickers:
        for r in _company_history(tk):
            try:
                acq = float(r.get("btc_acq"))
            except (TypeError, ValueError):
                continue
            if acq < min_btc:
                continue
            events.append({"date": str(r.get("date"))[:10], "label": f"{tk} +{acq:.0f}", "magnitude": acq})
    return events, f"企業財庫增持 ≥{min_btc:.0f} BTC（{'/'.join(tickers)}）"


def _adapt_fng(asset: str = "BTC", mode: str = "fear", threshold: Optional[float] = None, **_) -> Tuple[List[Dict[str, Any]], str]:
    from skills.market_intel.fng_client import get_crypto_fear_and_greed_index
    hist = _unwrap(get_crypto_fear_and_greed_index(limit=2000), "history")
    lo = threshold if threshold is not None else (25 if mode == "fear" else 75)
    events = []
    for h in hist:
        v, ts = h.get("value"), h.get("timestamp")
        if v is None or ts is None:
            continue
        v = float(v)
        if (v <= lo if mode == "fear" else v >= lo):
            events.append({"ts": int(ts) * 1000, "label": f"F&G {int(v)}", "magnitude": v})
    label = f"恐懼貪婪 {'≤'+str(lo)+'（極度恐懼）' if mode=='fear' else '≥'+str(lo)+'（極度貪婪）'}"
    return events, label


def _adapt_etf(asset: str = "BTC", mode: str = "inflow", threshold: Optional[float] = None, **_) -> Tuple[List[Dict[str, Any]], str]:
    from skills.market_intel.etf_flow import get_etf_flows
    hist = _unwrap(get_etf_flows(asset, days=400), "history")
    thr = threshold if threshold is not None else 0.0
    events = []
    for h in hist:
        f, d = h.get("net_flow_usd"), h.get("date")
        if f is None or not d:
            continue
        if (f > thr if mode == "inflow" else f < -abs(thr)):
            events.append({"date": str(d)[:10], "label": f"${f/1e6:.0f}M", "magnitude": f})
    return events, f"{asset.upper()} 現貨 ETF {'單日淨流入' if mode=='inflow' else '單日淨流出'}"


def _adapt_funding(asset: str = "BTC", mode: str = "high", threshold: Optional[float] = None, **_) -> Tuple[List[Dict[str, Any]], str]:
    from skills.derivatives.coinalyze_client import _coinalyze_request, _agg_symbol
    coin = asset.upper().replace("/USDT", "").split("/")[0]
    now = int(time.time())
    raw = _coinalyze_request("/funding-rate-history",
                             {"symbols": _agg_symbol(coin), "interval": "daily", "from": now - 365 * 86400, "to": now})
    recs = raw[0].get("history", []) if isinstance(raw, list) and raw else []
    # 註：Coinalyze funding c 已是『百分比』（實測與 Binance rate×100 一致），不可再 ×100。
    thr = threshold if threshold is not None else (0.03 if mode == "high" else -0.01)
    events = []
    for r in recs:
        c, t = r.get("c", r.get("close")), r.get("t")
        if c is None or t is None:
            continue
        pct = float(c)
        if (pct >= thr if mode == "high" else pct <= thr):
            events.append({"ts": int(t) * 1000, "label": f"{pct:.4f}%", "magnitude": pct})
    return events, f"{coin} 資金費率 {'偏高（多頭擁擠）' if mode=='high' else '為負（空頭擁擠）'}"


def _adapt_liquidation(asset: str = "BTC", mode: str = "long_cascade", threshold: Optional[float] = None, **_) -> Tuple[List[Dict[str, Any]], str]:
    """爆倉尖峰：以『滾動中位數×倍數』的相對基準偵測（因免費彙整在劇烈行情系統性偏低，不可用絕對美元門檻）。"""
    from skills.derivatives.coinalyze_client import _coinalyze_request, _agg_symbol
    coin = asset.upper().replace("/USDT", "").split("/")[0]
    now = int(time.time())
    raw = _coinalyze_request("/liquidation-history",
                             {"symbols": _agg_symbol(coin), "interval": "daily", "convert_to_usd": "true",
                              "from": now - 365 * 86400, "to": now})
    recs = raw[0].get("history", []) if isinstance(raw, list) and raw else []
    mult = threshold if threshold is not None else 3.0
    side_key = "l" if mode == "long_cascade" else "s"   # l=多單爆倉, s=空單爆倉
    series = [(int(r.get("t", 0)), float(r.get(side_key, 0) or 0)) for r in recs if r.get("t")]
    events = []
    win = 30
    for i in range(win, len(series)):
        window = [v for _, v in series[i - win:i] if v > 0]
        if len(window) < 10:
            continue
        med = float(np.median(window))
        ts, val = series[i]
        if med > 0 and val >= mult * med:
            events.append({"ts": ts * 1000, "label": f"${val/1e6:.0f}M", "magnitude": val})
    label = f"{coin} {'多單爆倉瀑布' if mode=='long_cascade' else '空單爆倉/軋空'}（≥{mult:.0f}× 30日中位）"
    return events, label


def _adapt_oi_surge(asset: str = "BTC", threshold: Optional[float] = None, **_) -> Tuple[List[Dict[str, Any]], str]:
    from skills.derivatives.coinalyze_client import _coinalyze_request, _agg_symbol
    coin = asset.upper().replace("/USDT", "").split("/")[0]
    now = int(time.time())
    raw = _coinalyze_request("/open-interest-history",
                             {"symbols": _agg_symbol(coin), "interval": "daily", "convert_to_usd": "true",
                              "from": now - 365 * 86400, "to": now})
    recs = raw[0].get("history", []) if isinstance(raw, list) and raw else []
    thr = threshold if threshold is not None else 10.0   # 單日 OI %變動門檻
    series = [(int(r.get("t", 0)), float(r.get("c", r.get("close", 0)) or 0)) for r in recs if r.get("t")]
    events = []
    for i in range(1, len(series)):
        prev, cur = series[i - 1][1], series[i][1]
        if prev <= 0:
            continue
        chg = (cur / prev - 1) * 100
        if chg >= thr:
            events.append({"ts": series[i][0] * 1000, "label": f"OI +{chg:.0f}%", "magnitude": chg})
    return events, f"{coin} 持倉量單日突增 ≥{thr:.0f}%"


def _adapt_valuation(asset: str = "BTC", metric: str = "mayer", threshold: Optional[float] = None, **_) -> Tuple[List[Dict[str, Any]], str]:
    from skills.market_data.onchain_indicators import get_mayer_multiple_local, get_ahr999_local
    # CoinGecko Demo tier 歷史上限約 365 天；get_*_local 內部再加 ~200 日均線窗，故 output_days 保守取 150
    if metric == "ahr999":
        data = get_ahr999_local(output_days=150) or []
        thr = threshold if threshold is not None else 0.45
        events = [{"date": str(d.get("date", "")).replace("/", "-"), "label": f"AHR999 {d.get('ahr999'):.2f}",
                   "magnitude": d.get("ahr999")}
                  for d in data if d.get("ahr999") is not None and d["ahr999"] < thr]
        return events, f"BTC AHR999 抄底區（< {thr}）"
    data = get_mayer_multiple_local(output_days=150) or []
    thr = threshold if threshold is not None else 0.8
    events = [{"ts": d.get("timestamp"), "label": f"Mayer {d.get('index'):.2f}", "magnitude": d.get("index")}
              for d in data if d.get("index") is not None and d["index"] < thr]
    return events, f"BTC Mayer 深值區（現價/200DMA < {thr}）"


def _adapt_price_factor(asset: str = "BTC", factor: str = "momentum",
                        threshold: Optional[float] = None, **_) -> Tuple[List[Dict[str, Any]], str]:
    """經典價量因子 → 事件（借鏡 alpha 因子庫）：動能突破 / RSI 超賣 / 波動突增，皆由該資產日線自算。"""
    from skills.market_data.ccxt_fetcher import get_ohlcv
    coin = asset.upper().replace("/USDT", "").split("/")[0]
    oh = get_ohlcv("binance", f"{coin}/USDT", "1d", 400)
    candles = oh.get("candles") or [] if isinstance(oh, dict) else []
    if len(candles) < 40:
        return [], f"{coin} 價量因子（K 線不足）"
    closes = np.array([float(c["close"]) for c in candles])
    highs = np.array([float(c["high"]) for c in candles])
    lows = np.array([float(c["low"]) for c in candles])
    tss = []
    for c in candles:
        try:
            tss.append(int(datetime.fromisoformat(str(c["timestamp"]).replace("Z", "+00:00")).timestamp() * 1000))
        except (ValueError, TypeError, KeyError):
            tss.append(0)
    events = []
    if factor == "momentum":
        win = 20
        thr = threshold if threshold is not None else 15.0
        for i in range(win, len(closes)):
            mom = (closes[i] / closes[i - win] - 1) * 100
            if mom >= thr:
                events.append({"ts": tss[i], "label": f"20d +{mom:.0f}%", "magnitude": mom})
        label = f"{coin} 20 日動能突破 ≥{thr:.0f}%"
    elif factor == "oversold":
        thr = threshold if threshold is not None else 30.0
        for i in range(15, len(closes)):
            gains = losses = 0.0
            for j in range(i - 13, i + 1):
                d = closes[j] - closes[j - 1]
                gains += max(d, 0.0)
                losses += max(-d, 0.0)
            rsi = 100.0 if losses == 0 else 100 - 100 / (1 + (gains / 14) / (losses / 14))
            if rsi <= thr:
                events.append({"ts": tss[i], "label": f"RSI {rsi:.0f}", "magnitude": rsi})
        label = f"{coin} RSI 超賣 ≤{thr:.0f}"
    else:  # vol_spike
        thr = threshold if threshold is not None else 2.0
        prev_close = np.roll(closes, 1)
        tr = np.maximum(highs - lows, np.abs(highs - prev_close))
        for i in range(21, len(closes)):
            avg = tr[i - 20:i].mean()
            if avg > 0 and tr[i] >= thr * avg:
                events.append({"ts": tss[i], "label": f"TR {tr[i]/avg:.1f}x", "magnitude": float(tr[i] / avg)})
        label = f"{coin} 波動突增 ≥{thr:.1f}× 20 日均幅"
    return events, label


# signal → adapter + 契約（direction 預設 / asset_scope / publish_lag / accepts）
_EVENT_SOURCES: Dict[str, Dict[str, Any]] = {
    "treasury_accumulation": {"fn": _adapt_treasury, "direction": "long", "asset_scope": "BTC-only", "publish_lag": 1, "accepts": ["ticker", "threshold"], "kw": {}},
    "extreme_fear":          {"fn": _adapt_fng, "direction": "long", "asset_scope": "crypto-wide", "publish_lag": 0, "accepts": ["threshold"], "kw": {"mode": "fear"}},
    "extreme_greed":         {"fn": _adapt_fng, "direction": "long", "asset_scope": "crypto-wide", "publish_lag": 0, "accepts": ["threshold"], "kw": {"mode": "greed"}},
    "etf_inflow":            {"fn": _adapt_etf, "direction": "long", "asset_scope": "per-asset", "publish_lag": 1, "accepts": ["threshold"], "kw": {"mode": "inflow"}},
    "etf_outflow":           {"fn": _adapt_etf, "direction": "long", "asset_scope": "per-asset", "publish_lag": 1, "accepts": ["threshold"], "kw": {"mode": "outflow"}},
    "high_funding":          {"fn": _adapt_funding, "direction": "long", "asset_scope": "per-asset", "publish_lag": 0, "accepts": ["threshold"], "kw": {"mode": "high"}},
    "negative_funding":      {"fn": _adapt_funding, "direction": "long", "asset_scope": "per-asset", "publish_lag": 0, "accepts": ["threshold"], "kw": {"mode": "low"}},
    "liquidation_long_flush": {"fn": _adapt_liquidation, "direction": "long", "asset_scope": "per-asset", "publish_lag": 0, "accepts": ["threshold"], "kw": {"mode": "long_cascade"}},
    "liquidation_short_squeeze": {"fn": _adapt_liquidation, "direction": "long", "asset_scope": "per-asset", "publish_lag": 0, "accepts": ["threshold"], "kw": {"mode": "short_squeeze"}},
    "oi_surge":              {"fn": _adapt_oi_surge, "direction": "long", "asset_scope": "per-asset", "publish_lag": 0, "accepts": ["threshold"], "kw": {}},
    "mayer_deep":            {"fn": _adapt_valuation, "direction": "long", "asset_scope": "BTC-only", "publish_lag": 0, "accepts": ["threshold"], "kw": {"metric": "mayer"}},
    "ahr999_bottom":         {"fn": _adapt_valuation, "direction": "long", "asset_scope": "BTC-only", "publish_lag": 0, "accepts": ["threshold"], "kw": {"metric": "ahr999"}},
    # 經典價量 alpha 因子（借鏡因子庫）：由該資產日線自算，測其後續是否有 edge
    "momentum_breakout":     {"fn": _adapt_price_factor, "direction": "long", "asset_scope": "per-asset", "publish_lag": 0, "accepts": ["threshold"], "kw": {"factor": "momentum"}},
    "oversold_rsi":          {"fn": _adapt_price_factor, "direction": "long", "asset_scope": "per-asset", "publish_lag": 0, "accepts": ["threshold"], "kw": {"factor": "oversold"}},
    "vol_spike":             {"fn": _adapt_price_factor, "direction": "long", "asset_scope": "per-asset", "publish_lag": 0, "accepts": ["threshold"], "kw": {"factor": "vol_spike"}},
}
SIGNALS = list(_EVENT_SOURCES.keys())
_PER_ASSET_OK = {"BTC", "BITCOIN", "ETH", "ETHEREUM"}


# ──────────────────────────────────────────────
#  3) 共用：驗證契約 + 產生事件
# ──────────────────────────────────────────────
class _SignalError(Exception):
    def __init__(self, msg: str, needs_key: bool = False):
        super().__init__(msg)
        self.msg = msg
        self.needs_key = needs_key


def _generate_events(signal: str, asset: str, ticker: Optional[str] = None,
                     threshold: Optional[float] = None) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any]]:
    """驗證契約(存在/asset_scope/accepts) → 呼叫 adapter → 回 (events, label, src)。失敗一律 raise _SignalError。"""
    src = _EVENT_SOURCES.get(signal)
    if not src:
        raise _SignalError(f"未知訊號 '{signal}'。可選：{', '.join(SIGNALS)}")
    coin = asset.upper().replace("/USDT", "").split("/")[0]
    scope = src["asset_scope"]
    if scope == "BTC-only" and coin not in ("BTC", "BITCOIN"):
        raise _SignalError(f"訊號 '{signal}' 僅適用 BTC（asset_scope=BTC-only），你傳了 {asset}。")
    if scope == "per-asset" and coin not in _PER_ASSET_OK:
        raise _SignalError(f"訊號 '{signal}' 目前僅支援 BTC/ETH，你傳了 {asset}。")
    for pname, pval in (("ticker", ticker), ("threshold", threshold)):
        if pval is not None and pname not in src["accepts"]:
            raise _SignalError(f"訊號 '{signal}' 不接受參數 '{pname}'（accepts={src['accepts']}）。")
    kw = dict(src["kw"])
    if ticker is not None:
        kw["ticker"] = ticker
    if threshold is not None:
        kw["threshold"] = threshold
    try:
        events, label = src["fn"](asset=asset, **kw)
    except EnvironmentError as e:
        raise _SignalError(str(e).splitlines()[0], needs_key=True)
    except _SignalError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.error(f"訊號事件產生失敗 [{signal}]: {e}")
        raise _SignalError(f"事件產生失敗: {e.__class__.__name__}: {str(e)[:80]}")
    return events, label, src


def _event_day(e: Dict[str, Any]) -> Optional[int]:
    """把事件正規化成 UTC 日序（days since epoch），供組合的日對齊/集合運算。"""
    ts = e.get("ts")
    if ts is None and e.get("date"):
        try:
            ts = int(datetime.strptime(str(e["date"])[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
        except (ValueError, TypeError):
            return None
    if ts is None:
        return None
    return int(int(ts) // 86_400_000)


# ──────────────────────────────────────────────
#  4) 統一 LLM 接口（單一訊號）
# ──────────────────────────────────────────────
def run_signal_backtest(signal: str, asset: str = "BTC", hold_days: int = 7,
                        ticker: Optional[str] = None, threshold: Optional[float] = None,
                        direction: Optional[str] = None, min_events: int = 5) -> Dict[str, Any]:
    """
    【組合式回測接口·單一訊號】把『任一訊號事件』回測其後價格影響——量測事件後 N 天報酬 vs 隨機進場基準
    （異常報酬），附 t 統計/顯著性與最小樣本閘門。新增回測想法只需加一個 event adapter。

    Args:
        signal    : 訊號名稱（見 enum）。asset：BTC-only 訊號限 BTC；ETF/資金費/爆倉可 BTC/ETH。
        hold_days : 事件後持有天數（預設 7）。direction：覆寫方向（貪婪/擁擠後可測 short）。
        ticker    : 僅 treasury_accumulation。threshold：覆寫門檻（單位依訊號）。
    """
    try:
        hold_days = int(hold_days)
    except (TypeError, ValueError):
        return {"error": "hold_days 需為正整數。", "signal": signal}
    if hold_days < 1:
        return {"error": "hold_days 需為正整數。", "signal": signal}
    try:
        events, label, src = _generate_events(signal, asset, ticker, threshold)
    except _SignalError as e:
        return {"error": e.msg, "needs_free_key": e.needs_key, "signal": signal,
                **({"available_signals": SIGNALS} if "未知訊號" in e.msg else {})}
    dir_ = direction if direction in ("long", "short") else src["direction"]
    try:
        res = run_event_study(events, asset=asset, hold_days=hold_days, direction=dir_,
                              publish_lag=src["publish_lag"], min_events=min_events,
                              signal=signal, signal_label=label,
                              hypothesis=f"『{label}』事件後 {hold_days} 天 {asset.upper()} 的價格表現？")
    except Exception as e:  # noqa: BLE001
        logger.error(f"回測引擎失敗 [{signal}]: {e}")
        return {"error": f"回測引擎失敗: {e.__class__.__name__}: {str(e)[:80]}", "signal": signal}
    if "error" not in res:
        from skills.analytics.run_card import write_run_card
        res["run_card"] = write_run_card("signal_backtest", {
            "signal": signal, "asset": asset, "hold_days": hold_days, "direction": dir_,
            "ticker": ticker, "threshold": threshold, "min_events": min_events,
        }, res)
    return res


# ──────────────────────────────────────────────
#  5) 組合式回測（多訊號共振 AND / 聯集 OR）
# ──────────────────────────────────────────────
def run_composite_backtest(signals: List[Any], asset: str = "BTC", hold_days: int = 7,
                           mode: str = "and", window_days: int = 1,
                           direction: Optional[str] = None, min_events: int = 5) -> Dict[str, Any]:
    """
    【組合式回測·多訊號】把『多個數據源的訊號組合』回測——例如「極度恐懼 且 ETF 淨流入」同時成立時買入。

    mode='and'（共振：所有訊號在 ±window_days 內同時觸發）或 'or'（聯集：任一觸發）。
    每個訊號沿用自己的觸發條件（絕對門檻/比例），可為字串或 {signal, threshold, ticker}。

    Args:
        signals     : 訊號清單（≥2 才有組合意義），如 ['extreme_fear','etf_inflow']。
        mode        : 'and' 共振 / 'or' 聯集。
        window_days : AND 模式下「同時」的日容忍（預設 ±1 天，因不同資料源公布時點略有差異）。
        asset/hold_days/direction/min_events：同單一訊號版。
    """
    specs = signals or []
    if len(specs) < 2:
        return {"error": "組合回測至少需要 2 個訊號；單一訊號請用 run_signal_backtest。"}
    if mode not in ("and", "or"):
        return {"error": f"mode 只能是 'and' 或 'or'，收到 '{mode}'。"}
    try:
        hold_days, window_days = int(hold_days), int(window_days)
    except (TypeError, ValueError):
        return {"error": "hold_days / window_days 需為整數。"}
    if hold_days < 1:
        return {"error": "hold_days 需為正整數。"}
    if window_days < 0:
        return {"error": "window_days 需為非負整數。"}

    per_signal: List[Dict[int, Dict[str, Any]]] = []   # 每訊號：day → 代表事件
    labels, dirs, max_lag = [], set(), 0
    for spec in specs:
        if isinstance(spec, str):
            sig, thr, tk = spec, None, None
        elif isinstance(spec, dict):
            sig, thr, tk = spec.get("signal"), spec.get("threshold"), spec.get("ticker")
        else:
            return {"error": f"訊號規格格式錯誤：{spec!r}"}
        try:
            events, label, src = _generate_events(sig, asset, tk, thr)
        except _SignalError as e:
            return {"error": f"[{sig}] {e.msg}", "needs_free_key": e.needs_key}
        max_lag = max(max_lag, src["publish_lag"])
        dirs.add(src["direction"])
        labels.append(label)
        by_day: Dict[int, Dict[str, Any]] = {}
        for e in events:
            d = _event_day(e)
            if d is not None and d not in by_day:
                by_day[d] = {"ts": d * 86_400_000, "label": e.get("label", ""), "magnitude": e.get("magnitude")}
        per_signal.append(by_day)

    combo_label = (" 或 " if mode == "or" else " 且 ").join(labels)
    if mode == "or":
        merged: Dict[int, Dict[str, Any]] = {}
        for bd in per_signal:
            for d, e in bd.items():
                merged.setdefault(d, e)
        combined = list(merged.values())
    else:  # and：對稱/傳遞交集——候選取全訊號日聯集；要求每訊號最近事件皆在 window 內、且群 max-min<=window。
        all_days = sorted(set().union(*[set(bd) for bd in per_signal])) if per_signal else []
        picked: Dict[int, Dict[str, Any]] = {}
        for d0 in all_days:
            matched, ok = [], True
            for bd in per_signal:
                if not bd:
                    ok = False
                    break
                near = min(bd, key=lambda od: abs(od - d0))
                if abs(near - d0) > window_days:
                    ok = False
                    break
                matched.append(near)
            if ok and (max(matched) - min(matched) <= window_days):
                key = min(matched)   # 以群最早日為代表 → 鄰近候選映到同一鍵，去重、順序無關
                picked.setdefault(key, {"ts": key * 86_400_000,
                                        "label": "＋".join(l[:8] for l in labels), "magnitude": None})
        combined = list(picked.values())

    # direction：顯式覆寫 > 各訊號預設一致採用 > 否則 long（並不硬編忽略 registry）
    if direction in ("long", "short"):
        dir_ = direction
    elif len(dirs) == 1:
        dir_ = dirs.pop()
    else:
        dir_ = "long"

    try:
        res = run_event_study(combined, asset=asset, hold_days=hold_days, direction=dir_,
                              publish_lag=max_lag, min_events=min_events,
                              signal="composite", signal_label=combo_label,
                              hypothesis=f"『{combo_label}』（{mode.upper()}）同時成立後 {hold_days} 天 {asset.upper()} 的表現？")
    except Exception as e:  # noqa: BLE001
        logger.error(f"組合回測引擎失敗: {e}")
        return {"error": f"組合回測引擎失敗: {e.__class__.__name__}: {str(e)[:80]}"}
    res["composite"] = {"mode": mode, "window_days": window_days, "signals": labels,
                        "per_signal_event_counts": [len(bd) for bd in per_signal]}
    if "error" not in res:
        from skills.analytics.run_card import write_run_card
        res["run_card"] = write_run_card("composite_backtest", {
            "signals": list(signals), "asset": asset, "hold_days": hold_days, "mode": mode,
            "window_days": window_days, "direction": dir_, "min_events": min_events,
        }, res)
    return res

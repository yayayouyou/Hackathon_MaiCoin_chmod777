"""
skills/market_data/liquidation_heatmap.py — 本地計算的爆倉熱力圖（免金鑰）
=====================================================
治本：CoinGlass 招牌的「預測爆倉熱力圖」本質是「持倉量(OI) × 假設槓桿分布」的推估——
人人（含 CoinGlass 自己）都是估算。我們用【既有免費資料】自算對標，移除對付費/逆向的依賴。

方法（沿用 minchillo4/btc-liquidation-heatmap、rektslug 的 MIT 方法論）：
  1. 逐 K 線取 OI 增量，只計正向（視為新開倉）；
  2. 依 K 線漲跌方向歸為『新多 / 新空』（啟發式，附註）；
  3. 套用槓桿分布桶（5/10/25/50/100x，權重偏 10–25x）；
  4. 爆倉價：多單 P×(1−1/N+mmr)、空單 P×(1+1/N−mmr)，BTC 維持保證金率 mmr≈0.004；
  5. 名目價值累積進約 N 個價格 bins；
  6. 按時間『順序』處理：價格掃過某 bin 即清零（視為已爆/已平）——剩餘 = 尚未觸發的爆倉群落。

資料來源（皆免金鑰）：Binance 期貨 K 線 /fapi/v1/klines + 持倉量歷史 /futures/data/openInterestHist。
輸出為『近似預測、非觀測』，UI 需明確標註；槓桿分布為假設值。
"""

from typing import Any, Dict, List

from loguru import logger

from skills._http import session_get
from skills.derivatives.binance_futures import get_binance_open_interest_history

_FAPI = "https://fapi.binance.com"


def _perp_symbol(symbol: str) -> str:
    """裸幣種/交易對 → Binance 永續合約符號（BTC / BTC/USDT -> BTCUSDT）。"""
    s = (symbol or "BTC").upper().replace("/", "").split("_")[-1]
    return s if s.endswith("USDT") else f"{s}USDT"

# 假設槓桿分布（權重和=1，偏 10–25x）；散戶實務常見區間
_LEVERAGE_WEIGHTS = {5: 0.10, 10: 0.25, 25: 0.30, 50: 0.20, 100: 0.15}
_MMR = 0.004  # BTCUSDT 低檔位維持保證金率（近似）

_PERIOD_SECONDS = {"5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "2h": 7200,
                   "4h": 14400, "6h": 21600, "12h": 43200, "1d": 86400}


def _fetch_klines(symbol_norm: str, interval: str, limit: int) -> List[List[float]]:
    """Binance 期貨 K 線（免金鑰）→ [[openTime_ms, o, h, l, c], ...]。"""
    resp = session_get(f"{_FAPI}/fapi/v1/klines",
                       params={"symbol": symbol_norm, "interval": interval, "limit": limit})
    resp.raise_for_status()
    rows = resp.json()
    out = []
    for k in rows if isinstance(rows, list) else []:
        out.append([int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4])])
    return out


def get_liquidation_heatmap_local(symbol: str = "BTC", period: str = "1h",
                                  lookback: int = 48, bins: int = 90,
                                  price_span_pct: float = 0.30) -> Dict[str, Any]:
    """
    【本地計算】爆倉熱力圖 / 爆倉價位群落（免金鑰，OI × 假設槓桿投影）。

    Args:
        symbol         : 幣種，例如 'BTC', 'ETH'
        period         : K 線週期（5m/15m/1h/4h/1d…；預設 1h）
        lookback       : 回溯 K 線數（預設 48）
        bins           : 價格分箱數（預設 90）
        price_span_pct : 熱力圖涵蓋現價 ±% 範圍（預設 ±30%）
    """
    sym = _perp_symbol(symbol)
    iv = period if period in _PERIOD_SECONDS else "1h"

    # 1) 價格 K 線（/fapi/v1/klines，免金鑰、非 /futures/data 不受權重節流）
    try:
        klines = _fetch_klines(sym, iv, lookback + 1)
    except Exception as e:  # noqa: BLE001
        logger.error(f"熱力圖 K 線抓取失敗: {e}")
        return {"error": f"K 線抓取失敗: {e.__class__.__name__}"}
    if len(klines) < 3:
        return {"error": "K 線資料不足，無法計算熱力圖。"}

    # 2) 持倉量歷史（優先 Coinalyze 跨所；否則 Binance /futures/data，免金鑰、含 retry-on-empty）
    #    按『索引』對齊 K 線（同週期、同 limit、皆最新在後），比逐一時間戳 exact-match 穩健。
    oi_vals: List[float] = []
    oi_source = "Binance openInterestHist"
    oi_note = None
    try:
        from skills.derivatives.coinalyze_client import get_coinalyze_open_interest  # noqa: F401
        import os
        if os.getenv("COINALYZE_API_KEY", "").strip() and not os.getenv("COINALYZE_API_KEY", "").strip().lower().startswith("your"):
            from skills.derivatives.coinalyze_client import _coinalyze_request, _agg_symbol, _norm_interval, _window
            iv_c = _norm_interval(iv)
            raw = _coinalyze_request("/open-interest-history",
                                     {"symbols": _agg_symbol(symbol), "interval": iv_c,
                                      "convert_to_usd": "true", **_window(iv_c, lookback + 1)})
            recs = raw[0].get("history", []) if isinstance(raw, list) and raw else []
            oi_vals = [float(r.get("c", r.get("o", 0)) or 0) for r in recs]
            oi_source = "Coinalyze 跨所 OI"
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Coinalyze OI 不可用，改用 Binance：{e.__class__.__name__}")
    if not oi_vals:
        try:
            oih = get_binance_open_interest_history(symbol, period=iv, limit=lookback + 1)
            hist = [] if oih.get("error") else (oih.get("history") or [])
            oi_vals = [float(h["open_interest_value_usd"]) for h in hist]
        except Exception as e:  # noqa: BLE001
            oi_vals = []
            logger.warning(f"OI 歷史抓取失敗: {e}")
    if len(oi_vals) < 3:
        oi_note = ("OI 歷史暫不可用（Binance /futures/data 限流或無資料）——無法投影爆倉群落；"
                   "可稍後重試，或設定免費 COINALYZE_API_KEY 改用跨所 OI。")

    current_price = klines[-1][4]
    lo = current_price * (1 - price_span_pct)
    hi = current_price * (1 + price_span_pct)
    bin_w = (hi - lo) / bins
    if bin_w <= 0:
        return {"error": "價格區間異常，無法分箱。"}

    def bin_idx(price: float) -> int:
        return max(0, min(bins - 1, int((price - lo) / bin_w)))

    long_bins = [0.0] * bins   # 多單爆倉名目（價格下方）
    short_bins = [0.0] * bins  # 空單爆倉名目（價格上方）

    # 按索引把 OI 對齊 K 線（尾端對齊；缺的補 None → 該根不投影）
    n = len(klines)
    if len(oi_vals) >= n:
        oi_aligned = oi_vals[-n:]
    elif oi_vals:
        oi_aligned = [None] * (n - len(oi_vals)) + oi_vals
    else:
        oi_aligned = [None] * n

    for i, k in enumerate(klines):
        ts, o, high, low, close = k
        # (a) 先清掃：本根 K 線掃過的價位視為已觸發/已平 → 清零該區間
        s_idx, e_idx = bin_idx(low), bin_idx(high)
        for b in range(min(s_idx, e_idx), max(s_idx, e_idx) + 1):
            long_bins[b] = 0.0
            short_bins[b] = 0.0
        # (b) 本根新開倉名目 = OI 正增量（無前一根或無 OI 則跳過，不假造）
        cur_oi, prev_oi = oi_aligned[i], (oi_aligned[i - 1] if i > 0 else None)
        if cur_oi is None or prev_oi is None:
            continue
        added = cur_oi - prev_oi
        if added <= 0:
            continue
        # (c) 方向：K 線收漲→新多為主；收跌→新空為主（啟發式）
        new_long = close >= o
        entry = close
        for lev, w in _LEVERAGE_WEIGHTS.items():
            notional = added * w
            if new_long:
                liq_price = entry * (1 - 1 / lev + _MMR)
                if lo <= liq_price <= hi:
                    long_bins[bin_idx(liq_price)] += notional
            else:
                liq_price = entry * (1 + 1 / lev - _MMR)
                if lo <= liq_price <= hi:
                    short_bins[bin_idx(liq_price)] += notional

    levels: List[Dict[str, Any]] = []
    for b in range(bins):
        lg, sh = long_bins[b], short_bins[b]
        if lg <= 0 and sh <= 0:
            continue
        price = lo + (b + 0.5) * bin_w
        levels.append({
            "price": round(price, 2),
            "side": "long" if lg >= sh else "short",
            "long_liq_usd": round(lg, 2),
            "short_liq_usd": round(sh, 2),
            "total_usd": round(lg + sh, 2),
        })
    levels.sort(key=lambda x: x["price"])
    top = sorted(levels, key=lambda x: x["total_usd"], reverse=True)[:8]

    return {
        "symbol": symbol.upper(),
        "current_price": round(current_price, 2),
        "period": iv,
        "lookback": lookback,
        "bins": bins,
        "source": f"本地計算（{oi_source} × 假設槓桿投影；免金鑰）",
        "oi_source": oi_source,
        "data_available": bool(levels),
        "methodology": "OI 正增量→依 K 線方向歸多/空→套 5/10/25/50/100x 槓桿→算爆倉價→價格掃過即清零",
        "caveat": "近似『預測』非觀測；槓桿分布為假設值，劇烈行情與真實爆倉會有偏差。"
                  + (f" 註：{oi_note}" if oi_note else ""),
        "levels": levels,
        "top_clusters": top,
    }

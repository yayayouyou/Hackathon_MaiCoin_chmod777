"""
skills/analytics/analyst_desk.py — 系統化分析師桌（Analyst Desk）
=====================================================
把散落的數據濃縮成『專業投研流程』：由上而下 5 層 → 各層系統化評分 → 共振/背離引擎
→ 論點 + 失效點 + 風險控管建議。人格（用戶策略）調各層權重。

  1. 宏觀/環境 (macro)      : 中期趨勢位置 + 波動（風險環境）
  2. 資金流   (flows)       : ETF 流向 + 企業財庫 + 板塊輪動（機構需求/廣度）
  3. 部位結構 (positioning) : 資金費率 + 跨所多空比 + 爆倉（槓桿擁擠，極端反向）
  4. 群眾情緒 (sentiment)   : 恐懼貪婪（極端反向）
  5. 技術/時機 (technical)  : 均線排列 + RSI（進出場時機）

設計哲學：量化-裁量混合桌——系統化『分析師』產出各層信號（快、可稽核），
再由 agent 以人格口吻做 PM 綜合敘事。共振＝高信心；背離＝alpha 警訊（如價漲但資金流出）。
"""

import statistics
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from loguru import logger

# 人格 → 各層權重（default/beginner 為均衡；其餘依風格加權）
_PERSONA_WEIGHTS: Dict[str, Dict[str, float]] = {
    "default":   {"macro": 1.0, "flows": 1.0, "positioning": 1.0, "sentiment": 1.0, "technical": 1.0},
    "beginner":  {"macro": 1.0, "flows": 1.0, "positioning": 1.0, "sentiment": 1.0, "technical": 1.0},
    "buffett":   {"macro": 1.3, "flows": 1.5, "positioning": 0.7, "sentiment": 0.8, "technical": 0.5},
    "dalio":     {"macro": 1.6, "flows": 1.3, "positioning": 1.0, "sentiment": 0.8, "technical": 0.6},
    "livermore": {"macro": 0.8, "flows": 0.7, "positioning": 1.2, "sentiment": 1.0, "technical": 1.6},
    "whale":     {"macro": 0.9, "flows": 1.3, "positioning": 1.6, "sentiment": 0.8, "technical": 0.9},
}
_WEIGHT_STYLE_ZH = {"default": "均衡", "beginner": "均衡", "buffett": "價值/資金流優先",
                    "dalio": "宏觀優先", "livermore": "技術/動能優先", "whale": "部位/籌碼優先"}


# ── 指標小工具 ─────────────────────────
def _sma(v: List[float], n: int) -> Optional[float]:
    return sum(v[-n:]) / n if len(v) >= n else None


def _rsi(closes: List[float], n: int = 14) -> Optional[float]:
    if len(closes) < n + 1:
        return None
    gains = losses = 0.0
    for i in range(-n, 0):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    if losses == 0:
        return 100.0
    rs = (gains / n) / (losses / n)
    return 100 - 100 / (1 + rs)


def _vol(closes: List[float]) -> Optional[float]:
    if len(closes) < 10:
        return None
    rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
    return statistics.pstdev(rets)


def _clamp(x: float) -> float:
    return max(-1.0, min(1.0, x))


def _layer(layer: str, label: str, score: float, evidence: List[str], ok: bool = True) -> Dict[str, Any]:
    score = _clamp(score)
    sig = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    return {"layer": layer, "label": label, "signal": sig, "strength": round(abs(score) * 100),
            "score": round(score, 3), "evidence": evidence[:3], "ok": ok}


def _neutral(layer: str, label: str, reason: str) -> Dict[str, Any]:
    return {"layer": layer, "label": label, "signal": "neutral", "strength": 0,
            "score": 0.0, "evidence": [reason], "ok": False}


# ── 各層分析師 ─────────────────────────
def _macro_layer(closes: List[float]) -> Dict[str, Any]:
    sma50 = _sma(closes, 50)
    if sma50 is None:
        return _neutral("macro", "宏觀/環境", "K 線不足，無法判斷環境")
    price = closes[-1]
    score, ev = 0.0, []
    if price > sma50 * 1.02:
        score += 0.45; ev.append("價格位於中期均線(SMA50)之上，環境偏多")
    elif price < sma50 * 0.98:
        score -= 0.45; ev.append("價格位於中期均線(SMA50)之下，環境偏空")
    else:
        ev.append("價格貼近中期均線，屬區間震盪環境")
    v = _vol(closes[-30:])
    if v is not None and v > 0.03:
        score *= 0.7; ev.append(f"近期波動偏高({v*100:.1f}%)，風險環境不穩，降低方向信心")
    return _layer("macro", "宏觀/環境", score, ev)


def _technical_layer(closes: List[float]) -> Dict[str, Any]:
    sma20, sma50 = _sma(closes, 20), _sma(closes, 50)
    if sma20 is None or sma50 is None:
        return _neutral("technical", "技術/時機", "K 線不足，無法計算技術指標")
    price = closes[-1]
    score, ev = 0.0, []
    if price > sma20 > sma50:
        score += 0.6; ev.append("多頭排列（價 > SMA20 > SMA50）")
    elif price < sma20 < sma50:
        score -= 0.6; ev.append("空頭排列（價 < SMA20 < SMA50）")
    else:
        ev.append("均線糾結，趨勢不明")
    rsi = _rsi(closes, 14)
    if rsi is not None:
        if rsi > 70:
            score -= 0.25; ev.append(f"RSI {rsi:.0f} 超買（追高風險）")
        elif rsi < 30:
            score += 0.25; ev.append(f"RSI {rsi:.0f} 超賣（潛在反彈）")
        elif rsi > 55:
            score += 0.15; ev.append(f"RSI {rsi:.0f} 偏強")
        elif rsi < 45:
            score -= 0.15; ev.append(f"RSI {rsi:.0f} 偏弱")
    return _layer("technical", "技術/時機", score, ev)


def _flows_layer(asset: str) -> Dict[str, Any]:
    from skills.market_data.coinglass_scraper import get_coinglass_etf_flow
    from skills.market_intel.btc_treasuries import get_btc_treasuries
    from skills.market_intel.sosovalue_extras import get_crypto_sector_indices
    score, ev, parts = 0.0, [], 0

    def _c(x):
        ax = abs(x)
        return f"{ax/1e9:.2f}B" if ax >= 1e9 else f"{ax/1e6:.0f}M" if ax >= 1e6 else f"{x:,.0f}"

    try:
        etf = get_coinglass_etf_flow(asset)
        cum = etf.get("cumulative_net_flow_usd")
        if not etf.get("error") and cum is not None:
            parts += 1
            if cum > 0:
                score += 0.4; ev.append(f"ETF {etf.get('window_days','')}日累積淨流入 ${_c(cum)}")
            else:
                score -= 0.4; ev.append(f"ETF 累積淨流出 -${_c(cum)}")
    except Exception:  # noqa: BLE001
        pass
    try:
        tr = get_btc_treasuries(top_n=6)
        net = tr.get("recent_net_btc")
        if not tr.get("error") and net is not None:
            parts += 1
            if net > 0:
                score += 0.3; ev.append(f"企業財庫近期增持 +{_c(net)} BTC")
            elif net < 0:
                score -= 0.3; ev.append(f"企業財庫近期減持 {_c(net)} BTC")
    except Exception:  # noqa: BLE001
        pass
    try:
        sec = get_crypto_sector_indices()
        rot = sec.get("rotation_read", "")
        if not sec.get("error") and rot:
            parts += 1
            if "risk-on" in rot:
                score += 0.2; ev.append("板塊 risk-on（資金追價、廣度轉強）")
            elif "risk-off" in rot:
                score -= 0.2; ev.append("板塊 risk-off（廣度轉弱）")
    except Exception:  # noqa: BLE001
        pass
    if parts == 0:
        return _neutral("flows", "資金流", "ETF/財庫/板塊資料暫不可用")
    return _layer("flows", "資金流", score, ev)


def _positioning_layer(coin: str) -> Dict[str, Any]:
    from skills.derivatives.multi_exchange import get_aggregated_funding_rate
    from skills.derivatives.coinalyze_client import get_coinalyze_long_short_ratio
    from skills.market_data.coinglass_scraper import get_coinglass_liquidation_chart
    score, ev, parts = 0.0, [], 0
    try:
        fund = get_aggregated_funding_rate(f"{coin}/USDT")
        avg = (fund.get("aggregated") or {}).get("avg_rate_pct")
        if not fund.get("error") and avg is not None:
            parts += 1
            if avg > 0.05:
                score -= 0.2; ev.append(f"資金費率偏高 {avg:.3f}%（多頭擁擠、過熱風險）")
            elif avg > 0.005:
                score += 0.2; ev.append(f"資金費率正常偏多 {avg:.3f}%")
            elif avg < -0.01:
                score += 0.15; ev.append(f"資金費率為負 {avg:.3f}%（空頭擁擠、潛在軋空）")
            else:
                ev.append(f"資金費率中性 {avg:.3f}%")
    except Exception:  # noqa: BLE001
        pass
    try:
        ls = get_coinalyze_long_short_ratio(coin)
        r = ls.get("latest_ratio")
        if not ls.get("error") and r is not None:
            parts += 1
            if r > 1.6:
                score -= 0.2; ev.append(f"散戶多空比 {r:.2f} 過度偏多（反向警示）")
            elif r < 0.7:
                score += 0.2; ev.append(f"散戶多空比 {r:.2f} 過度偏空（反向偏多）")
            else:
                ev.append(f"散戶多空比 {r:.2f} 中性")
    except Exception:  # noqa: BLE001
        pass
    try:
        liq = get_coinglass_liquidation_chart(coin)
        bias = liq.get("liquidation_bias", "")
        if not liq.get("error") and bias:
            parts += 1
            if "多頭爆倉" in bias:
                score += 0.1; ev.append("近期多頭爆倉為主（去槓桿後或止穩）")
            elif "空頭爆倉" in bias:
                score -= 0.05; ev.append("近期空頭爆倉為主")
    except Exception:  # noqa: BLE001
        pass
    if parts == 0:
        return _neutral("positioning", "部位結構", "資金費/多空/爆倉資料暫不可用")
    return _layer("positioning", "部位結構", score, ev)


def _sentiment_layer() -> Dict[str, Any]:
    from skills.market_intel.fng_client import get_crypto_fear_and_greed_index
    try:
        fng = get_crypto_fear_and_greed_index(1)
    except Exception:  # noqa: BLE001
        return _neutral("sentiment", "群眾情緒", "情緒資料暫不可用")
    if fng.get("error"):
        return _neutral("sentiment", "群眾情緒", "情緒資料暫不可用")
    v = fng.get("latest_value")
    score, ev = 0.0, []
    if v is None:
        return _neutral("sentiment", "群眾情緒", "恐懼貪婪指數無值")
    if v <= 25:
        score += 0.4; ev.append(f"恐懼貪婪 {v}（極度恐懼 → 反向偏多）")
    elif v >= 75:
        score -= 0.4; ev.append(f"恐懼貪婪 {v}（極度貪婪 → 反向偏空）")
    elif v < 45:
        score += 0.15; ev.append(f"恐懼貪婪 {v}（恐懼）")
    elif v > 55:
        score -= 0.1; ev.append(f"恐懼貪婪 {v}（貪婪）")
    else:
        ev.append(f"恐懼貪婪 {v}（中性）")
    return _layer("sentiment", "群眾情緒", score, ev)


# ── 共振 / 背離 / 綜合 ─────────────────────────
def _confluence(layers: List[Dict[str, Any]], weights: Dict[str, float]) -> Dict[str, Any]:
    tot_w = wscore = 0.0
    bull = bear = 0
    for L in layers:
        if not L["ok"]:
            continue
        w = weights.get(L["layer"], 1.0)
        tot_w += w
        wscore += w * L["score"]
        if L["signal"] == "bullish":
            bull += 1
        elif L["signal"] == "bearish":
            bear += 1
    net = wscore / tot_w if tot_w else 0.0
    bias = "偏多" if net > 0.12 else "偏空" if net < -0.12 else "中性"
    active = bull + bear
    agree = max(bull, bear) / active if active else 0.0
    if abs(net) >= 0.35 and agree >= 0.66:
        conv = "高"
    elif abs(net) < 0.12 or agree < 0.5:
        conv = "低"
    else:
        conv = "中"
    return {"net_score": round(net, 3), "bias": bias, "conviction": conv,
            "bull_layers": bull, "bear_layers": bear, "neutral_layers": sum(1 for L in layers if L["ok"] and L["signal"] == "neutral")}


def _divergences(layers: List[Dict[str, Any]]) -> List[str]:
    by = {L["layer"]: L for L in layers if L["ok"]}
    out = []
    tech, flows, pos, sent = by.get("technical"), by.get("flows"), by.get("positioning"), by.get("sentiment")
    if tech and flows:
        if tech["signal"] == "bullish" and flows["signal"] == "bearish":
            out.append("⚠ 價格/技術偏多、但資金流偏空 → 上漲缺機構承接，慎防派發")
        elif tech["signal"] == "bearish" and flows["signal"] == "bullish":
            out.append("價格/技術偏空、但資金流偏多 → 機構逢低承接，或為打底訊號")
    if pos and sent and pos["signal"] == "bearish" and sent["signal"] == "bearish":
        if any("擁擠" in e for e in pos["evidence"]) and any("貪婪" in e for e in sent["evidence"]):
            out.append("⚠ 槓桿多頭擁擠 + 情緒貪婪 → 局部見頂風險升高")
    return out


def run_analyst_desk(symbol: str = "BTC", persona: str = "default", timeframe: str = "4h") -> Dict[str, Any]:
    """
    【分析師桌】對單一標的跑完整 5 層系統化分析 + 共振/背離 + 論點/失效點/風控。

    Args:
        symbol    : 標的，如 'BTC','ETH'（或 'BTC/USDT'）
        persona   : 人格鍵，決定各層權重（default=均衡）
        timeframe : K 線週期（預設 4h）
    """
    coin = symbol.upper().replace("/USDT", "").split("/")[0].strip()
    asset = "ETH" if coin in ("ETH", "ETHEREUM") else "BTC" if coin in ("BTC", "BITCOIN") else coin
    weights = _PERSONA_WEIGHTS.get(persona, _PERSONA_WEIGHTS["default"])

    # 共用 K 線（宏觀 + 技術）
    closes: List[float] = []
    price = None
    try:
        from skills.market_data.ccxt_fetcher import get_ohlcv
        oh = get_ohlcv("binance", f"{coin}/USDT", timeframe, 200)
        closes = [float(c["close"]) for c in (oh.get("candles") or []) if c.get("close") is not None]
        price = oh.get("latest_close") or (closes[-1] if closes else None)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"分析桌 K 線抓取失敗: {e}")

    layers = [
        _macro_layer(closes) if closes else _neutral("macro", "宏觀/環境", "K 線不可用"),
        _flows_layer(asset),
        _positioning_layer(coin),
        _sentiment_layer(),
        _technical_layer(closes) if closes else _neutral("technical", "技術/時機", "K 線不可用"),
    ]
    conf = _confluence(layers, weights)
    divs = _divergences(layers)

    # 論點 / 失效點 / 風控（依共振與技術位階生成）
    lead = max((L for L in layers if L["ok"] and L["signal"] != "neutral"),
               key=lambda x: x["strength"] * weights.get(x["layer"], 1), default=None)
    lead_txt = f"，主導層為{lead['label']}（{lead['evidence'][0]}）" if lead else ""
    thesis = f"五層綜合為{conf['bias']}（信心{conf['conviction']}；{conf['bull_layers']}多/{conf['bear_layers']}空）{lead_txt}。"
    if divs:
        thesis += "存在背離，需降低確定性。"

    sma50 = _sma(closes, 50) if closes else None
    if sma50 and price:
        if conf["bias"] == "偏多":
            invalidation = f"跌破中期均線 SMA50 ≈ {sma50:,.0f}（約 {(sma50/price-1)*100:.1f}%）或 ETF 續大額流出，則多頭論點失效。"
        elif conf["bias"] == "偏空":
            invalidation = f"站回並守穩 SMA50 ≈ {sma50:,.0f}（約 {(sma50/price-1)*100:+.1f}%），則空頭論點失效。"
        else:
            invalidation = f"區間邊界：跌破 SMA50 ≈ {sma50:,.0f} 轉弱、站上則轉強。"
    else:
        invalidation = "資料不足以界定明確失效價位，建議等待更清晰結構。"

    if conf["conviction"] == "高" and not divs:
        risk_note = "共振度高：可依既有策略正常配置，務必設定停損於失效價位。"
    elif conf["conviction"] == "低" or divs:
        risk_note = "訊號分歧/背離：建議輕倉試單或觀望，等待各層共振再加碼。"
    else:
        risk_note = "中等共振：小幅參與、分批進場，嚴設停損。"

    return {
        "symbol": coin,
        "asset": asset,
        "price": round(price, 2) if price else None,
        "timeframe": timeframe,
        "persona": persona,
        "weighting_style": _WEIGHT_STYLE_ZH.get(persona, "均衡"),
        "layers": layers,
        "confluence": conf,
        "divergences": divs,
        "thesis": thesis,
        "invalidation": invalidation,
        "risk_note": risk_note,
        "framework": "由上而下 5 層 → 共振/背離 → 論點+失效點+風控（人格調權重）",
        "disclaimer": "系統化分析，非投資建議；務必自行判斷並嚴設風險。",
    }

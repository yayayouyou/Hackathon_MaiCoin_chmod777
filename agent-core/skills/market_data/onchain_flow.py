"""
skills/market_data/onchain_flow.py

鏈上資金流 / 聰明錢訊號（免費起手，可加 key 升級到錢包級）
======================================================
現實：真正「錢包級聰明錢」的免費來源都被擋（GMGN 走 Cloudflare、Birdeye/Nansen 要 key）。
本工具分兩層：
  1) 免費無 key：用 DexScreener 聚合買賣壓（買/賣筆數、量能、trending）→ 資金流向訊號。
     這是一階「有沒有異常買盤/累積」的可靠代理，不是個別錢包。
  2) 選配 BIRDEYE_API_KEY（免費申請）：加「錢包級 top traders / 聰明錢買家」。
之後可再接『事件研究』驗證這些流入是否真的領先價格。
"""
import os
from typing import Dict, Any, List, Optional
from loguru import logger

from skills._http import session_get
from skills.market_data.dex_screener import search_dex_pairs, DEX_SCREENER_BASE_URL, _to_float, _liq_usd

_BIRDEYE = "https://public-api.birdeye.so"


def _ratio(buys, sells):
    b, s = _to_float(buys), _to_float(sells)
    tot = b + s
    return round(b / tot, 3) if tot > 0 else None


def _side(r: Optional[float]) -> int:
    """買賣方向：+1 偏買 / -1 偏賣 / 0 均衡或無資料。"""
    if r is None:
        return 0
    return 1 if r >= 0.54 else (-1 if r <= 0.46 else 0)


def _reconcile(r6: Optional[float], r24: Optional[float], pc24: Optional[float]):
    """調和『近期(6h)』與『整體(24h)』買賣壓，避免只看單一時間尺度而誤判（Critic 建議）。
    回傳 (買賣壓標籤, 綜合訊號, 背離註記或 None)。"""
    if r6 is None and r24 is None:
        return "無資料", "鏈上交易太少，無法判斷資金流。", None
    recent = r6 if r6 is not None else r24
    overall = r24 if r24 is not None else r6
    sr, so = _side(recent), _side(overall)

    # 一致：兩個時間尺度同向 → 訊號較可信
    if sr == so == 1:
        if pc24 is not None and pc24 < 2:
            return "持續買盤", "6h 與 24h 買盤一致、價格還沒大動 → 累積跡象較明確，值得留意。", None
        if pc24 is not None and pc24 > 8:
            return "持續買盤", "6h 與 24h 買盤一致且價格已明顯上漲 → 趨勢確認，但追高風險升高。", None
        return "持續買盤", "6h 與 24h 買盤一致 → 買方主導。", None
    if sr == so == -1:
        return "持續賣壓", "6h 與 24h 賣壓一致 → 賣方主導（下跌/派發）。", None

    # 背離：近期與整體反向 → 明確標記，不再硬說「強力買盤」
    if sr == 1 and so == -1:
        note = f"背離：近 6h 轉買（買比 {recent:.0%}），但 24h 整體仍淨賣（買比 {overall:.0%}）"
        tail = "（價格尚未反應 → 可能是早期『偷偷累積』的起手，但未確立）" if (pc24 is not None and pc24 < 2) else ""
        return "轉折偏買（背離）", f"近期買盤轉強、但 24h 整體仍偏賣 → 短線轉強訊號、中期未確立{tail}，需觀察量能與價格是否跟上。", note
    if sr == -1 and so == 1:
        note = f"背離：近 6h 轉賣（買比 {recent:.0%}），但 24h 整體仍淨買（買比 {overall:.0%}）"
        return "轉折偏賣（背離）", "近期轉為賣出、但 24h 整體仍偏買 → 動能減弱/獲利了結跡象。", note

    # 一方中性
    if 1 in (sr, so):
        return "略偏買", "買盤略強但兩個時間尺度不夠一致，訊號偏弱。", None
    if -1 in (sr, so):
        return "略偏賣", "賣壓略強但不夠一致，訊號偏弱。", None
    return "均衡", "買賣大致均衡，無明顯資金流訊號。", None


def _boosted_addresses() -> set:
    """DexScreener 付費加熱(boosts) → 當作 trending 代理（免費）。失敗回空集合。"""
    try:
        r = session_get("https://api.dexscreener.com/token-boosts/latest/v1", timeout=(3.05, 10))
        r.raise_for_status()
        return {str(x.get("tokenAddress", "")).lower() for x in (r.json() or []) if x.get("tokenAddress")}
    except Exception:  # noqa: BLE001
        return set()


def _birdeye_top_traders(address: str, chain: str = "solana") -> Optional[List[Dict[str, Any]]]:
    """選配：有 BIRDEYE_API_KEY 才查『錢包級』最活躍交易者（聰明錢代理）。無 key/失敗回 None。"""
    key = os.getenv("BIRDEYE_API_KEY", "").strip()
    if not key:
        return None
    try:
        r = session_get(f"{_BIRDEYE}/defi/v2/tokens/top_traders",
                        params={"address": address, "limit": 10},
                        headers={"X-API-KEY": key, "x-chain": chain}, timeout=(3.05, 12))
        r.raise_for_status()
        items = (r.json() or {}).get("data", {}).get("items", [])
        out = []
        for t in items[:10]:
            out.append({
                "wallet": t.get("owner") or t.get("address"),
                "volume_usd": round(_to_float(t.get("volume")), 0),
                "trades": t.get("trade"),
                "buy_usd": round(_to_float(t.get("volumeBuy")), 0),
                "sell_usd": round(_to_float(t.get("volumeSell")), 0),
            })
        return out
    except Exception as e:  # noqa: BLE001
        logger.debug(f"Birdeye top traders 失敗（略過）：{e}")
        return None


def get_smart_money_flow(query: str) -> Dict[str, Any]:
    """
    【LLM Tool】查某代幣的『鏈上資金流 / 買賣壓』訊號（看行動而非嘴巴）。免費用 DexScreener 聚合
    買賣筆數+量能+trending 判斷是否有異常買盤/累積；若設了 BIRDEYE_API_KEY 另加錢包級聰明錢買家。
    適用：「聰明錢在買 X 嗎、鏈上有沒有人在偷偷累積 WIF、X 的買盤強不強」。

    Args:
        query: 代幣符號/名稱/合約地址（如 'WIF'、'dogwifhat' 或 Solana 合約地址）。
    """
    res = search_dex_pairs(query)
    pairs = res.get("pairs") or []
    if not pairs:
        return {"query": query, "message": res.get("message") or "DEX 上找不到此代幣的活躍交易池。"}

    # 取「量能 × 流動性」最高的主池：兼顧活躍度與深度，避免選到沒交易的死池或撞名的低流動性小幣
    # （純比量能會誤選撞名小池；純比流動性會選到沒交易的死池）。
    p = max(pairs, key=lambda x: _to_float((x.get("volume") or {}).get("h24"), 0.0) * _liq_usd(x))
    base = p.get("baseToken", {})
    addr = str(base.get("address", ""))
    chain = p.get("chainId")
    pc = p.get("priceChange", {}) or {}

    # 把「同一代幣、同一鏈」的所有池子加總 → 代幣層級的買賣壓（單一深池 txn 數常失真，加總較穩）
    same = [x for x in pairs if str(x.get("baseToken", {}).get("address", "")) == addr
            and x.get("chainId") == chain] or [p]
    flow = {}
    for tf in ("h1", "h6", "h24"):
        b = sum(_to_float((x.get("txns", {}).get(tf) or {}).get("buys")) for x in same)
        s = sum(_to_float((x.get("txns", {}).get(tf) or {}).get("sells")) for x in same)
        v = sum(_to_float((x.get("volume") or {}).get(tf)) for x in same)
        flow[tf] = {"buys": int(b), "sells": int(s), "buy_ratio": _ratio(b, s),
                    "volume_usd": round(v, 0), "price_change_pct": pc.get(tf)}

    liq = sum(_liq_usd(x) for x in same)
    vol = {tf: flow[tf]["volume_usd"] for tf in ("h1", "h6", "h24")}
    turnover = round(_to_float(vol.get("h24")) / liq, 2) if liq > 0 else None
    boosted = addr.lower() in _boosted_addresses() if addr else False

    # 綜合解讀：調和 6h(近期) 與 24h(整體) 買賣壓，背離時明確標記（避免只看單一尺度誤判）
    pc24 = _to_float(pc.get("h24"), None)
    pressure, signal, divergence = _reconcile(flow["h6"]["buy_ratio"], flow["h24"]["buy_ratio"], pc24)

    out: Dict[str, Any] = {
        "token": {"symbol": base.get("symbol"), "name": base.get("name"),
                  "address": addr, "chain": p.get("chainId")},
        "price_usd": p.get("priceUsd"), "liquidity_usd": round(liq, 0), "fdv": p.get("fdv"),
        "flow": flow, "buy_pressure": pressure, "divergence": divergence,
        "volume_turnover_h24": turnover, "trending_boosted": boosted,
        "signal": signal,
        "note": "此為 DEX『聚合』買賣壓（非個別錢包）；錢包級聰明錢需設 BIRDEYE_API_KEY（免費）。",
    }
    smart = _birdeye_top_traders(addr, chain="solana" if p.get("chainId") == "solana" else p.get("chainId"))
    if smart is not None:
        out["smart_money_top_traders"] = smart
    else:
        out["smart_money_top_traders"] = "（未設 BIRDEYE_API_KEY → 略過錢包級聰明錢；可免費申請 https://birdeye.so）"
    return out


def _current_brief(flow: Dict[str, Any]) -> Dict[str, Any]:
    return {"buy_pressure": flow.get("buy_pressure"), "divergence": flow.get("divergence"),
            "signal": flow.get("signal"), "price_usd": flow.get("price_usd")}


def run_token_due_diligence(token: str, hold_days: int = 5) -> Dict[str, Any]:
    """
    【LLM Tool】對某代幣做「一鍵盡職調查」：整合『當下鏈上買賣壓 + 訊號歷史有效性 + 基本面風險旗標』
    給出綜合判讀，一次看完避免追坑。內部串接 get_smart_money_flow + validate_smart_money_signal。
    適用：「幫我盡職調查 PEPE、這幣能不能碰、PEPE 綜合分析一下、進場前幫我看一遍」。

    Args:
        token: 代幣符號/名稱/合約地址
        hold_days: 訊號驗證的觀察天數（預設 5）
    """
    flow = get_smart_money_flow(token)
    if not flow.get("token"):
        return {"token": token, "message": flow.get("message") or "找不到此代幣。"}
    val = validate_smart_money_signal(token, hold_days=hold_days)

    liq = flow.get("liquidity_usd") or 0
    fdv = flow.get("fdv") or 0
    hv = val.get("historical_validation") or {}
    risk_flags: List[str] = []
    if liq and liq < 100_000:
        risk_flags.append(f"流動性偏低（${liq:,.0f}）→ 滑點大、rug 風險")
    if fdv and liq and fdv / max(liq, 1) > 200:
        risk_flags.append(f"FDV/流動性比過高（{fdv / liq:.0f}x）→ 估值虛高、易砸盤")
    if isinstance(hv, dict) and hv.get("significant") is False:
        risk_flags.append("資金流入訊號歷史上不顯著 → 別把當下買盤當真訊號")
    if isinstance(hv, dict) and isinstance(hv.get("avg_abnormal_return_pct"), (int, float)) and hv["avg_abnormal_return_pct"] < 0 and hv.get("significant"):
        risk_flags.append("放量後歷史上反而下跌（反指標）→ 當心出貨")

    summary = [f"買賣壓：{flow.get('buy_pressure')}" + (f"（{flow.get('divergence')}）" if flow.get("divergence") else "")]
    if val.get("verdict"):
        summary.append(f"訊號驗證：{val['verdict']}")
    summary.append("風險旗標：" + ("；".join(risk_flags) if risk_flags else "無明顯基本面紅旗"))

    return {
        "token": flow["token"],
        "fundamentals": {"price_usd": flow.get("price_usd"), "liquidity_usd": liq, "fdv": fdv,
                         "volume_turnover_h24": flow.get("volume_turnover_h24"),
                         "trending": flow.get("trending_boosted")},
        "current_flow": _current_brief(flow),
        "historical_validation": hv or val.get("message"),
        "validation_verdict": val.get("verdict"),
        "risk_flags": risk_flags,
        "summary": " ｜ ".join(summary),
        "note": "綜合鏈上資金流＋歷史驗證＋基本面風險；統計為觀察非因果、非投資建議。個別面向可另用 "
                "get_smart_money_flow / validate_smart_money_signal / analyze_crowd_sentiment 深入。",
    }


def validate_smart_money_signal(token: str, hold_days: int = 5, vol_mult: float = 2.5,
                                lookback_median: int = 30, min_events: int = 5) -> Dict[str, Any]:
    """
    【LLM Tool】驗證某代幣「資金流入訊號」的歷史有效性 → 分辨當下買盤是『真訊號』還是『噪音』。
    做法：以歷史『量能激增日』當聰明錢流入的可得代理（免費資料無法取得歷史錢包級流向），對其後
    hold_days 天做事件研究，看是否真的上漲且統計顯著。需該幣在主流交易所有日線（迷因幣可能沒有）。
    適用：「聰明錢在買 X，這訊號可靠嗎、歷史上 X 有量進場後真的漲嗎、這是真訊號還是噪音」。

    Args:
        token: 代幣符號/名稱/合約地址
        hold_days: 流入後觀察天數（預設 5）
        vol_mult: 當日量能達近期中位數幾倍算「激增」（預設 2.5）
    """
    flow = get_smart_money_flow(token)
    if not flow.get("token"):
        return {"token": token, "message": flow.get("message") or "找不到此代幣。"}
    sym = (flow["token"].get("symbol") or "").upper()

    from skills.analytics.event_study import _daily_klines, run_event_study
    df = _daily_klines(sym)
    if df is None:
        return {"token": sym, "current_flow": _current_brief(flow),
                "message": f"{sym} 在主流交易所查無日線（迷因幣常見）→ 無法回測驗證歷史有效性，只能看當下買賣壓。"}

    import numpy as np
    vols = df["vol"].astype(float).values
    ts = df["ts"].astype("int64").values
    events = []
    for i in range(lookback_median, len(vols)):        # 滾動中位數，量能≥mult×中位數即為激增日
        med = float(np.median(vols[i - lookback_median:i]))
        if med > 0 and vols[i] >= vol_mult * med:
            events.append({"ts": int(ts[i]), "label": f"量能 {vols[i] / med:.1f}x", "magnitude": round(vols[i] / med, 2)})
    if len(events) < min_events:
        return {"token": sym, "current_flow": _current_brief(flow),
                "message": f"{sym} 歷史量能激增事件太少（{len(events)} < {min_events}）→ 樣本不足以驗證。"}

    es = run_event_study(events, asset=sym, hold_days=hold_days, direction="long", min_events=min_events,
                         signal="smart_money_inflow", signal_label=f"{sym} 量能激增（聰明錢流入代理）")
    abn = es.get("avg_abnormal_return_pct")
    win = es.get("win_rate_pct")
    sig = bool(es.get("significant"))

    if abn is None:
        verdict = "資料不足以裁決。"
    elif sig and abn > 0:
        verdict = (f"✅ 真訊號：歷史上量能激增後 {hold_days} 天平均超額 +{abn}%（勝率 {win}%、統計顯著）"
                   f"→ 當下的買盤/流入值得重視。")
    elif sig and abn < 0:
        verdict = (f"⚠️ 反指標：量能激增後反而 {abn}%（顯著）→ 這幣的『放量』歷史上常是出貨/派發，"
                   f"當下買盤別追。")
    else:
        verdict = (f"🟡 偏噪音：量能激增後超額報酬 {abn}%（不顯著、勝率 {win}%）→ 這幣的『流入』歷史上"
                   f"沒有領先價格，當下買盤別過度解讀。")

    return {
        "token": sym,
        "current_flow": _current_brief(flow),
        "historical_validation": {
            "proxy": "歷史『量能激增日』（免費資料下對聰明錢流入的可得代理）",
            "events_tested": es.get("events_tested"), "hold_days": hold_days,
            "avg_abnormal_return_pct": abn, "win_rate_pct": win,
            "baseline_avg_return_pct": es.get("baseline_avg_return_pct"),
            "significant": sig, "permutation_p": es.get("permutation_p"),
        },
        "verdict": verdict,
        "note": "以量能激增當『流入』代理（免費資料所限，非錢包級）；統計為觀察非因果、非投資建議。",
    }

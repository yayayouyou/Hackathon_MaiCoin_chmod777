"""
skills/market_data/onchain_indicators.py — 本地計算的鏈上估值指標
=====================================================
治本：AHR999 與 Mayer Multiple 都是「公式固定、可由 BTC 日線價格算出」的公開指標，
不是 CoinGlass 獨家數據。原本靠 CoinGlass AES 逆向抓取（極脆弱，key 一換就死），
改為用可靠的 CoinGecko 日線價格『本地計算』，移除對逆向工程的依賴。

- Mayer Multiple = 現價 / 200 日均線（SMA200）
- AHR999 = (現價 / 200日幾何均值) × (現價 / 指數成長估值)
    指數成長估值 = 10^(5.84·log10(幣齡天數) − 17.01)，幣齡自 BTC 創世（2009-01-03）起算

輸出格式刻意對齊原 CoinGlass 回傳，UI 圖表與模型無需改動。
"""
import math
from datetime import datetime, timezone
from typing import List, Dict, Any

from skills.market_intel.coingecko_client import _coingecko_request

BTC_GENESIS = datetime(2009, 1, 3, tzinfo=timezone.utc)
_LOOKBACK = 200  # AHR999/Mayer 的均值窗口


def _btc_daily_prices(total_days: int = 260) -> List[tuple]:
    """回傳 [(timestamp_ms, price), ...] 的 BTC 日線價格（CoinGecko，帶快取）。"""
    raw = _coingecko_request(
        "/coins/bitcoin/market_chart",
        {"vs_currency": "usd", "days": str(total_days), "interval": "daily"},
    )
    prices = raw.get("prices") or []
    return [(int(ts), float(p)) for ts, p in prices if p]


def _coin_age_days(ts_ms: int) -> int:
    d = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    return max(1, (d - BTC_GENESIS).days)


def _exp_growth_valuation(age_days: int) -> float:
    """BTC 指數成長估值（AHR999 的分母之一）。"""
    return 10 ** (5.84 * math.log10(age_days) - 17.01)


def get_mayer_multiple_local(output_days: int = 90) -> List[Dict[str, Any]]:
    """本地計算 Mayer Multiple 時間序列（對齊 CoinGlass 陣列格式）。"""
    series = _btc_daily_prices(_LOOKBACK + output_days + 5)
    prices = [p for _, p in series]
    out: List[Dict[str, Any]] = []
    for i in range(_LOOKBACK - 1, len(series)):
        window = prices[i - _LOOKBACK + 1: i + 1]
        sma = sum(window) / _LOOKBACK
        ts, price = series[i]
        out.append({
            "timestamp": ts,
            "price": round(price, 2),
            "index": round(price / sma, 4) if sma else None,
        })
    return out[-output_days:]


# 山寨季指數計算時排除的穩定幣/包裝幣/質押衍生幣（不算「跑贏 BTC」的有效樣本）
_ALTSEASON_EXCLUDE = {
    "usdt", "usdc", "dai", "busd", "tusd", "usdd", "fdusd", "usde", "pyusd", "gusd",
    "usdp", "frax", "lusd", "eurc", "eurt", "usds", "usd1", "usdf",
    "wbtc", "weth", "steth", "wsteth", "weeth", "reth", "cbbtc", "cbeth", "wbeth",
    "lbtc", "solvbtc", "meth", "rseth", "ezeth", "weth", "beth", "tbtc", "susde",
}


# CoinGecko /coins/markets 支援的漲跌窗口（無 90d；山寨季經典用 90d，退而取最接近的 30d）
_CG_SUPPORTED_WINDOWS = [7, 14, 30, 200, 365]


def _snap_window(days: int) -> int:
    """把要求的天數對映到 CoinGecko 支援的最接近窗口。"""
    return min(_CG_SUPPORTED_WINDOWS, key=lambda w: abs(w - int(days or 30)))


def _iso_to_ms(iso: str) -> int:
    """把 CoinGecko 的 last_updated ISO 字串轉毫秒；失敗回 0。"""
    if not iso:
        return 0
    try:
        s = str(iso).replace("Z", "+00:00")
        return int(datetime.fromisoformat(s).timestamp() * 1000)
    except (ValueError, TypeError):
        return 0


def get_altcoin_season_local(top_n: int = 100, window_days: int = 30) -> Dict[str, Any]:
    """
    本地計算山寨幣季節指數（Altcoin Season Index）。

    治本：改用 CoinGecko 前 N 大幣種的漲跌『本地計算』，取代脆弱的 CoinGlass AES 逆向抓取。
    方法（對齊 blockchaincenter/CoinGlass 公開定義）：
      在過去 window_days 內，前 top_n 大市值幣種（排除穩定幣/包裝幣/質押衍生幣）中，
      有多少百分比『表現優於 BTC』。>75 為山寨季、<25 為比特幣季。

    註：CoinGecko 不提供 90 日窗口，預設取其支援中最接近實用的 30 日。
    回傳同時附上舊 CoinGlass 陣列相容欄位（list[].altcoinIndex），UI 無需改動。
    """
    win = _snap_window(window_days)
    field = f"price_change_percentage_{win}d_in_currency"
    raw = _coingecko_request(
        "/coins/markets",
        {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": min(max(top_n, 10), 250),
            "page": 1,
            "price_change_percentage": f"{win}d",
        },
    )
    rows = raw if isinstance(raw, list) else []
    # BTC 基準漲跌
    btc = next((r for r in rows if (r.get("symbol") or "").lower() == "btc"), None)
    if not btc or btc.get(field) is None:
        return {"error": f"山寨季指數計算失敗：CoinGecko 未回傳 BTC {win} 日漲跌基準。"}
    btc_change = float(btc[field])

    outperform = 0
    sample = 0
    for r in rows:
        sym = (r.get("symbol") or "").lower()
        if sym == "btc" or sym in _ALTSEASON_EXCLUDE:
            continue
        chg = r.get(field)
        if chg is None:
            continue
        sample += 1
        if float(chg) > btc_change:
            outperform += 1

    if sample == 0:
        return {"error": "山寨季指數計算失敗：有效樣本不足。"}

    index = round(outperform / sample * 100)
    if index >= 75:
        classification = "山寨季（Altcoin Season）"
    elif index <= 25:
        classification = "比特幣季（Bitcoin Season）"
    else:
        classification = "中性（無明顯季節）"

    latest_ts = _iso_to_ms(btc.get("last_updated"))

    return {
        "altcoin_season_index": index,
        "classification": classification,
        "sample_size": sample,
        "outperformers": outperform,
        "btc_change_pct": round(btc_change, 2),
        "window_days": win,
        "source": f"本地計算 (CoinGecko 前 {sample+1} 幣種 {win} 日漲跌)",
        "guide": "指數 >75 為山寨季（資金輪動至山寨）、<25 為比特幣季、25~75 為中性",
        # 舊 CoinGlass 陣列相容欄位（UI/模型若讀 list[].altcoinIndex 仍可用）
        "list": [{"altcoinIndex": index, "timestamp": latest_ts}],
    }


def get_ahr999_local(output_days: int = 90) -> List[Dict[str, Any]]:
    """本地計算 AHR999 時間序列（對齊 CoinGlass list 內元素格式）。"""
    series = _btc_daily_prices(_LOOKBACK + output_days + 5)
    prices = [p for _, p in series]
    out: List[Dict[str, Any]] = []
    for i in range(_LOOKBACK - 1, len(series)):
        window = prices[i - _LOOKBACK + 1: i + 1]
        geo_mean = math.exp(sum(math.log(x) for x in window) / _LOOKBACK)
        ts, price = series[i]
        expval = _exp_growth_valuation(_coin_age_days(ts))
        ahr = (price / geo_mean) * (price / expval) if (geo_mean and expval) else None
        out.append({
            "date": datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y/%m/%d"),
            "value": round(price, 2),
            "ahr999": round(ahr, 4) if ahr is not None else None,
        })
    return out[-output_days:]

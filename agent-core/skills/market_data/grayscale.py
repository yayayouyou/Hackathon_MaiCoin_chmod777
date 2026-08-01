"""
skills/market_data/grayscale.py — 灰度信託溢價/折價（本地計算，免金鑰）
=====================================================
治本：取代原本靠 CoinGlass AES 逆向抓取的灰度數據。改用『自行計算』：

  溢價/折價 = 市價 / NAV − 1
  NAV/股    = 每股持幣量(seed) × (1−年費)^(距種子年數) × 標的現貨價

資料來源（皆免金鑰、已驗證）：
  - 市價   : Yahoo Finance v8 chart（query1→query2 自動 failover；需瀏覽器 UA）
  - 現貨價 : CoinGecko simple/price（既有）
  - 種子值 : 各信託 SEC 10-Q 揭露的每股持幣量（dated；管理費逐日在鏈上衰減，季度性刷新）

定位：旗艦品項（GBTC/ETHE）已轉 ETF、溢價≈0 且流向已含在 ETF flow → 標註 is_etf。
      真正 alpha 在仍為封閉式 OTC 的信託（如 BCHG，標的無對應現貨 ETF，折溢價可達 ±數十%）。

擴充：要新增信託，於 _TRUSTS 補一列 dated 種子（從該信託最新 SEC 10-Q 的
      『Digital Asset Holdings per Share』或 NAV/share ÷ 當日標的價 推得）。
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from loguru import logger

from skills._http import session_get
from skills.market_intel.coingecko_client import get_coingecko_coin_price

# 每股持幣種子（coins_per_share）：值 + 種子日期 + 年費 + 標的 CoinGecko id + 是否已轉 ETF
# 種子取自各信託 SEC 10-Q 揭露（NAV/share ÷ 當日標的價）。approx 者以最近可得季報估算。
_TRUSTS: List[Dict[str, Any]] = [
    # 旗艦（已轉 ETF，溢價≈0；流向見 etf_flow）
    {"ticker": "GBTC", "name": "Grayscale Bitcoin Trust ETF", "coin_id": "bitcoin",
     "coins_per_share": 0.00089, "seed_date": "2025-06-30", "annual_fee": 0.015, "is_etf": True, "approx": True},
    {"ticker": "ETHE", "name": "Grayscale Ethereum Trust ETF", "coin_id": "ethereum",
     "coins_per_share": 0.00866, "seed_date": "2025-06-30", "annual_fee": 0.025, "is_etf": True, "approx": True},
    # 封閉式 OTC（真實折溢價；標的無對應現貨 ETF）
    {"ticker": "BCHG", "name": "Grayscale Bitcoin Cash Trust", "coin_id": "bitcoin-cash",
     "coins_per_share": 0.008223, "seed_date": "2026-03-31", "annual_fee": 0.025, "is_etf": False, "approx": False},
]

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"


def _yahoo_price(ticker: str) -> Optional[float]:
    """Yahoo v8 chart 市價；query1 遇 429/非 JSON 自動 failover 到 query2。"""
    for host in ("query1", "query2"):
        url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{ticker}"
        try:
            resp = session_get(url, params={"interval": "1d", "range": "5d"},
                               headers={"User-Agent": _UA})
            if resp.status_code != 200 or "json" not in (resp.headers.get("content-type") or ""):
                continue
            meta = (((resp.json().get("chart") or {}).get("result") or [{}])[0]).get("meta") or {}
            px = meta.get("regularMarketPrice")
            if px:
                return float(px)
        except (requests.RequestException, ValueError, KeyError, IndexError):
            continue
    return None


def _days_since(date_str: str) -> float:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - d).days)
    except (ValueError, TypeError):
        return 0.0


def _spot_prices(coin_ids: List[str]) -> Dict[str, float]:
    try:
        px = get_coingecko_coin_price(",".join(sorted(set(coin_ids))), "usd")
        return {cid: float((px.get(cid) or {}).get("usd") or 0) for cid in coin_ids}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"CoinGecko 現貨價抓取失敗: {e}")
        return {}


def get_grayscale_premiums() -> Dict[str, Any]:
    """【本地計算】灰度信託溢價/折價（市價 vs NAV），免金鑰。

    僅對『封閉式 OTC 信託』計算真實折溢價（有 alpha）；已轉 ETF 者的溢價由套利機制貼合
    NAV≈0，若用過時種子硬算反而造成假訊號，故只標註不計算（流向請用 etf_flow 工具）。
    """
    otc = [t for t in _TRUSTS if not t["is_etf"]]
    spots = _spot_prices([t["coin_id"] for t in otc])
    otc_results: List[Dict[str, Any]] = []
    for t in otc:
        spot = spots.get(t["coin_id"])
        market = _yahoo_price(t["ticker"])
        if not spot or not market:
            otc_results.append({"ticker": t["ticker"], "name": t["name"],
                                "error": "市價或現貨價暫不可用"})
            continue
        # 每股持幣量隨管理費逐日衰減
        cps = t["coins_per_share"] * ((1 - t["annual_fee"]) ** (_days_since(t["seed_date"]) / 365.0))
        nav_per_share = cps * spot
        premium_pct = round((market / nav_per_share - 1) * 100, 2) if nav_per_share else None
        otc_results.append({
            "ticker": t["ticker"],
            "name": t["name"],
            "market_price": round(market, 4),
            "nav_per_share": round(nav_per_share, 4),
            "premium_discount_pct": premium_pct,
            "state": ("溢價" if premium_pct and premium_pct > 0 else "折價") if premium_pct is not None else None,
            "coins_per_share_est": round(cps, 8),
            "seed_date": t["seed_date"],
            "seed_approx": t.get("approx", False),
        })

    etf_now = [{"ticker": t["ticker"], "name": t["name"],
                "note": "已轉 ETF，溢價由套利貼合 NAV≈0；資金流向請用 ETF flow 工具。"}
               for t in _TRUSTS if t["is_etf"]]

    valid = [r for r in otc_results if r.get("premium_discount_pct") is not None]
    return {
        "source": "本地計算（Yahoo 市價 × CoinGecko 現貨 × SEC 種子 × 費率衰減；免金鑰）",
        "otc_count": len(valid),
        "otc_trusts": otc_results,      # 封閉式 OTC：真實折溢價（alpha）
        "etf_now": etf_now,             # 已轉 ETF：溢價≈0，不硬算
        "guide": "封閉式 OTC 信託的折溢價才有 alpha；GBTC/ETHE 已轉 ETF（流向見 ETF flow 工具）。",
        "caveat": "OTC 之 NAV 以 dated 種子每股持幣量 × 費率衰減估算，季度性從 SEC 10-Q 刷新；溢價為近似值。"
                  "擴充信託請於 _TRUSTS 補該檔最新 10-Q 的每股持幣量。",
    }

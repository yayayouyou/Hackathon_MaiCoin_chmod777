"""
skills/gold/tokenized_gold.py — 代幣化黃金即時報價 (PAXG / XAUT)
=============================================================
把黃金當「加密資產」看：PAX Gold (PAXG) 與 Tether Gold (XAUT) 各錨定 1 金衡盎司實體黃金，
24/7 交易，與我們現有 BTC/ETH 工具同一套資料源（CoinGecko）。這是 MAX 黃金交易對最可能的形態，
因此列為黃金資料層的第一塊。複用既有 CoinGecko 韌性請求層（Key + TTL 快取 + 每主機限流）。
"""
from typing import Dict, Any
from loguru import logger

from skills.market_intel.coingecko_client import _coingecko_request

# CoinGecko 幣種 ID（皆錨定 1 金衡盎司黃金）
_GOLD_TOKENS = {"PAXG": "pax-gold", "XAUT": "tether-gold"}


def get_gold_price(vs_currency: str = "usd") -> Dict[str, Any]:
    """
    【LLM Tool｜黃金】獲取代幣化黃金 PAXG 與 XAUT 的即時報價、24 小時漲跌與市值。
    兩者各錨定 1 金衡盎司實體黃金，故單價 ≈ 黃金現貨每盎司價；並回傳兩者價差（偏離錨定的訊號）。

    Args:
        vs_currency: 報價貨幣，如 'usd'、'twd'，預設 'usd'。
    """
    vs = (vs_currency or "usd").lower().strip()
    ids = ",".join(_GOLD_TOKENS.values())
    try:
        data = _coingecko_request("/simple/price", {
            "ids": ids, "vs_currencies": vs,
            "include_24hr_change": "true", "include_24hr_vol": "true",
            "include_market_cap": "true", "include_last_updated_at": "true",
        })
    except Exception as e:  # noqa: BLE001
        logger.error(f"代幣化黃金報價抓取失敗: {e}")
        return {"error": f"代幣化黃金報價抓取失敗: {e}"}

    tokens: Dict[str, Any] = {}
    for sym, cg_id in _GOLD_TOKENS.items():
        row = data.get(cg_id) or {}
        price = row.get(vs)
        if price is None:
            continue
        tokens[sym] = {
            "price": price,
            "change_24h_pct": row.get(f"{vs}_24h_change"),
            "volume_24h": row.get(f"{vs}_24h_vol"),
            "market_cap": row.get(f"{vs}_market_cap"),
        }

    if not tokens:
        return {"error": "CoinGecko 未回傳任何代幣化黃金報價"}

    # 兩幣皆錨定 1 盎司 → 價差反映『代幣間的錨定偏離/流動性差』（一般 <0.3%）
    spread_pct = None
    if "PAXG" in tokens and "XAUT" in tokens:
        p, x = tokens["PAXG"]["price"], tokens["XAUT"]["price"]
        if p and x:
            spread_pct = round((p - x) / ((p + x) / 2) * 100, 4)

    return {
        "vs_currency": vs,
        "note": "PAXG 與 XAUT 各錨定 1 金衡盎司黃金；單價 ≈ 黃金現貨每盎司價。僅供佐證，不自動觸發交易。",
        "tokens": tokens,
        "paxg_xaut_spread_pct": spread_pct,
        "source": "CoinGecko",
    }

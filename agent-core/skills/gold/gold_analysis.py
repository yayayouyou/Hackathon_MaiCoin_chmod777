"""
skills/gold/gold_analysis.py — 黃金綜合簡報 (Gold Market Briefing)
================================================================
把黃金資料層三塊縫成一份結構化判讀，供 MAX 黃金交易對決策佐證：

  1) 代幣化報價（PAXG/XAUT）      — get_gold_price
  2) 總經體制（實質利率/美元…）    — get_gold_macro_context
  3) 黃金 vs BTC 滾動相關性        — 由 ccxt 日線計算（判斷『數位黃金』敘事此刻成不成立）
  4) 代幣化溢價                    — PAXG 相對倫敦金定盤的溢/折價（套利/流動性訊號）

每一塊獨立容錯：任一資料源掛掉，其餘照常回傳。結論僅供佐證，不自動觸發交易。
"""
from typing import Dict, Any, List, Optional
from loguru import logger

from skills.gold.tokenized_gold import get_gold_price
from skills.gold.macro import get_gold_macro_context


def _returns(closes: List[float]) -> List[float]:
    return [(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes)) if closes[i - 1]]


def _gold_btc_correlation(exchange_id: str, gold_symbol: str, days: int) -> Dict[str, Any]:
    """以日線報酬計算黃金(代幣)與 BTC 的皮爾森相關係數。"""
    try:
        import numpy as np
        from skills.market_data.ccxt_fetcher import _create_exchange
        ex = _create_exchange(exchange_id)
        n = days + 1
        g = ex.fetch_ohlcv(gold_symbol, "1d", limit=n)
        b = ex.fetch_ohlcv("BTC/USDT", "1d", limit=n)
        gc = _returns([c[4] for c in g])
        bc = _returns([c[4] for c in b])
        m = min(len(gc), len(bc))
        if m < 5:
            return {"available": False, "reason": "日線樣本不足"}
        corr = float(np.corrcoef(gc[-m:], bc[-m:])[0, 1])
        if corr >= 0.5:
            regime = "risk_on_coupling"       # 與 BTC 同漲同跌，分散效果弱
        elif corr <= -0.2:
            regime = "safe_haven_divergence"  # 與 BTC 背離，避險屬性顯現
        else:
            regime = "decoupled"              # 低相關，良好分散標的
        return {"available": True, "correlation": round(corr, 3), "window_days": m,
                "regime": regime, "gold_symbol": gold_symbol, "vs": "BTC/USDT"}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"黃金-BTC 相關性計算失敗: {e}")
        return {"available": False, "reason": f"{e.__class__.__name__}: {e}"}


def _tokenized_premium(price: Dict[str, Any], macro: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """PAXG 相對倫敦金定盤的溢/折價（定盤每倫敦交易日更新，故為近似）。"""
    fix = (macro or {}).get("london_gold_pm_usd_oz") or {}
    fix_val = fix.get("value")
    paxg = ((price or {}).get("tokens") or {}).get("PAXG") or {}
    paxg_px = paxg.get("price")
    if not fix_val or not paxg_px:
        return None
    prem = round((paxg_px - fix_val) / fix_val * 100, 3)
    return {"paxg_usd": paxg_px, "london_pm_fix_usd_oz": fix_val, "fix_as_of": fix.get("as_of"),
            "premium_pct": prem,
            "note": "正=代幣化溢價、負=折價；定盤每倫敦交易日更新故為近似參考。"}


def analyze_gold_market(exchange_id: str = "binance",
                        tokenized_symbol: str = "PAXG/USDT",
                        corr_days: int = 30) -> Dict[str, Any]:
    """
    【LLM Tool｜黃金】黃金市場綜合簡報：整合代幣化黃金 (PAXG/XAUT) 報價、總經驅動體制
    （實質利率/美元指數/CPI…）、黃金與 BTC 的滾動相關性（檢驗『數位黃金』敘事）、以及代幣化溢價，
    產出結構化判讀。適用：「幫我看一下黃金現在的狀況 / 該不該布局黃金」。僅供佐證、不自動下單。

    Args:
        exchange_id: 計算相關性用的行情交易所，預設 'binance'
        tokenized_symbol: 代幣化黃金交易對，預設 'PAXG/USDT'
        corr_days: 黃金-BTC 相關性回看天數，預設 30
    """
    price = get_gold_price()
    macro = get_gold_macro_context()
    corr = _gold_btc_correlation(exchange_id, tokenized_symbol, max(7, min(120, corr_days)))
    premium = _tokenized_premium(price, macro)

    # 綜合一句話判讀（總經體制 + 相關性 regime）
    macro_read = macro.get("gold_macro_read", "unknown") if macro.get("available") else "unknown"
    parts = []
    if macro_read == "tailwind":
        parts.append("總經順風（實質利率/美元偏軟）")
    elif macro_read == "headwind":
        parts.append("總經逆風（實質利率/美元偏強）")
    elif macro_read == "mixed":
        parts.append("總經訊號分歧")
    if corr.get("available"):
        parts.append({"risk_on_coupling": "此刻與 BTC 高度同向、分散效果弱",
                      "safe_haven_divergence": "此刻與 BTC 背離、避險屬性顯現",
                      "decoupled": "此刻與 BTC 低相關、為良好分散標的"}.get(corr["regime"], ""))
    headline = "；".join(p for p in parts if p) or "資料不足，無法形成綜合判讀"

    return {
        "asset": "GOLD (tokenized: PAXG/XAUT)",
        "headline": headline,
        "price": price,
        "macro": macro,
        "gold_btc_correlation": corr,
        "tokenized_premium": premium,
        "caveat": "黃金無現金流、由總經驅動；本簡報僅為佐證面，須配合價格與風控，不自動觸發交易。",
    }

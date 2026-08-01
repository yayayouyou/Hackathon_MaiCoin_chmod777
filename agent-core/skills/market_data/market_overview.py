"""
skills/market_data/market_overview.py — 全網衍生品/大盤總覽（全免費聚合）
=====================================================
治本：取代原本靠 CoinGlass AES 逆向抓取的首頁大盤統計，改用『既有免費來源聚合』：

  - 總市值 / BTC 主導度 / 24h 量 / 市值變動 : CoinGecko /global（已有 Demo key）
  - 全網衍生品總持倉量(OI) / 總成交量       : CoinGecko /derivatives/exchanges（免金鑰）
  - 市場多空比（BTC 代表）                  : Binance globalLongShortAccountRatio（免金鑰）
  - 恐懼與貪婪指數                          : alternative.me（免金鑰）
  - 24h 總爆倉（多/空）                     : Coinalyze（免費金鑰；未設金鑰則標註 pending）

每一腳獨立 try/except：單一來源失敗不影響其餘欄位（不整包崩、不靜默造假）。
"""

from typing import Any, Dict

from loguru import logger

from skills.market_intel.coingecko_client import _coingecko_request, get_coingecko_coin_price


def _global_stats() -> Dict[str, Any]:
    data = (_coingecko_request("/global") or {}).get("data", {})
    mcap = data.get("total_market_cap", {}) or {}
    vol = data.get("total_volume", {}) or {}
    dom = data.get("market_cap_percentage", {}) or {}
    return {
        "total_market_cap_usd": mcap.get("usd"),
        "total_volume_24h_usd": vol.get("usd"),
        "btc_dominance_pct": dom.get("btc"),
        "eth_dominance_pct": dom.get("eth"),
        "market_cap_change_24h_pct": data.get("market_cap_change_percentage_24h_usd"),
        "active_cryptocurrencies": data.get("active_cryptocurrencies"),
    }


def _derivatives_totals() -> Dict[str, Any]:
    """跨所彙總衍生品總 OI / 總量（CoinGecko /derivatives/exchanges，免金鑰）。"""
    rows = _coingecko_request("/derivatives/exchanges", {"per_page": 100, "page": 1})
    if not isinstance(rows, list) or not rows:
        return {"error": "無衍生品交易所彙總資料"}
    oi_btc = sum(float(x.get("open_interest_btc") or 0) for x in rows)
    vol_btc = sum(float(x.get("trade_volume_24h_btc") or 0) for x in rows)
    # BTC→USD
    btc_usd = None
    try:
        px = get_coingecko_coin_price("bitcoin", "usd")
        btc_usd = float((px.get("bitcoin") or {}).get("usd") or 0) or None
    except Exception:  # noqa: BLE001
        btc_usd = None
    return {
        "exchanges_counted": len(rows),
        "total_open_interest_btc": round(oi_btc, 2),
        "total_open_interest_usd": round(oi_btc * btc_usd, 2) if btc_usd else None,
        "total_derivatives_volume_24h_btc": round(vol_btc, 2),
        "total_derivatives_volume_24h_usd": round(vol_btc * btc_usd, 2) if btc_usd else None,
    }


def get_global_derivatives_overview() -> Dict[str, Any]:
    """【聚合】全網衍生品 + 大盤宏觀總覽，全免費來源、逐腳降級。"""
    out: Dict[str, Any] = {"source": "免費聚合（CoinGecko + Binance + alternative.me + Coinalyze）"}

    # 1) 大盤（CoinGecko /global）
    try:
        out["market"] = _global_stats()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"大盤 /global 失敗: {e}")
        out["market"] = {"error": f"大盤資料抓取失敗: {e.__class__.__name__}"}

    # 2) 衍生品總 OI / 量（CoinGecko /derivatives/exchanges）
    try:
        out["derivatives"] = _derivatives_totals()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"衍生品彙總失敗: {e}")
        out["derivatives"] = {"error": f"衍生品彙總抓取失敗: {e.__class__.__name__}"}

    # 3) 市場多空比（BTC 代表）：優先 Coinalyze 跨所（免限流），退回 Binance 單所
    out["long_short_btc"] = None
    try:
        from skills.derivatives.coinalyze_client import get_coinalyze_long_short_ratio
        cls = get_coinalyze_long_short_ratio("BTC", interval="1hour", limit=6)
        if not cls.get("error"):
            out["long_short_btc"] = {"latest_ratio": cls.get("latest_ratio"),
                                     "long_pct": cls.get("long_account_pct"),
                                     "short_pct": cls.get("short_account_pct"),
                                     "sentiment": cls.get("sentiment_label"),
                                     "source": "Coinalyze 跨所"}
    except EnvironmentError:
        pass  # 無 Coinalyze 金鑰 → 退回 Binance
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Coinalyze 多空比失敗，退回 Binance: {e}")
    if out["long_short_btc"] is None:
        try:
            from skills.derivatives.binance_futures import get_binance_long_short_ratio
            ls = get_binance_long_short_ratio("BTC", period="1h", limit=6)
            out["long_short_btc"] = ({"error": ls["error"]} if ls.get("error") else {
                "latest_ratio": ls.get("latest_ratio"),
                "sentiment": ls.get("sentiment_label"),
                "source": "Binance 單所"})
        except Exception as e:  # noqa: BLE001
            out["long_short_btc"] = {"error": f"多空比抓取失敗: {e.__class__.__name__}"}

    # 4) 恐懼與貪婪指數（alternative.me 免金鑰）
    try:
        from skills.market_intel.fng_client import get_crypto_fear_and_greed_index
        fng = get_crypto_fear_and_greed_index(limit=1)
        if isinstance(fng, dict) and fng.get("error"):
            out["fear_greed"] = {"error": fng["error"]}
        else:
            out["fear_greed"] = {
                "value": fng.get("latest_value"),
                "classification": fng.get("latest_sentiment"),
            }
    except Exception as e:  # noqa: BLE001
        out["fear_greed"] = {"error": f"恐懼貪婪指數抓取失敗: {e.__class__.__name__}"}

    # 5) 24h 總爆倉（Coinalyze 免費金鑰；未設金鑰則優雅標註）
    try:
        from skills.derivatives.coinalyze_client import get_coinalyze_liquidations
        liq = get_coinalyze_liquidations("BTC", interval="1hour", limit=24)
        out["liquidations_24h_btc"] = {
            "total_usd": liq.get("total_liquidation_usd"),
            "long_usd": liq.get("long_liquidation_usd"),
            "short_usd": liq.get("short_liquidation_usd"),
            "bias": liq.get("liquidation_bias"),
            "caveat": liq.get("caveat"),
        }
    except EnvironmentError as e:
        out["liquidations_24h_btc"] = {"pending": True, "note": str(e).splitlines()[0],
                                       "hint": "設定免費 COINALYZE_API_KEY 後即補上跨所爆倉。"}
    except Exception as e:  # noqa: BLE001
        out["liquidations_24h_btc"] = {"error": f"爆倉抓取失敗: {e.__class__.__name__}"}

    return out

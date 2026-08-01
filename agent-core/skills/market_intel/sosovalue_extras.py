"""
skills/market_intel/sosovalue_extras.py — SoSoValue 板塊指數 + 加密概念股
=====================================================
補齊分析漏斗的『資金流/廣度』層：

  - get_crypto_sector_indices : SoSoValue 自有加密板塊指數（DeFi/Layer1/AI/Meme/RWA/DePIN…）
      的 24h/7d/1m 表現 → 板塊輪動與風險偏好信號。
  - get_crypto_stocks         : 加密概念股（MSTR/COIN/礦股…）。省略 ticker 回各板塊市值/漲跌總覽
      （BTC Treasury / Mining / Exchange…）；給 ticker 回單一個股行情。

資料來源：SoSoValue OpenAPI（第一方，免費 Demo 金鑰，沿用 SOSOVALUE_API_KEY）。
共用 btc_treasuries 的 _soso_get（30 分鐘 TTL 快取 + 金鑰檢查），HTTP 已於 _http 限流層節流防 429。
"""

from typing import Any, Dict, List, Optional

from loguru import logger

from skills.market_intel.btc_treasuries import _soso_get, _fnum

# 最受關注的板塊指數（策展子集，控制免費額度）
_CURATED_INDICES = ["ssiLayer1", "ssiDeFi", "ssiAI", "ssiMeme", "ssiRWA", "ssiDePIN"]
_INDEX_ZH = {
    "ssiDeFi": "DeFi", "ssiLayer1": "Layer1 公鏈", "ssiAI": "AI", "ssiMeme": "迷因幣",
    "ssiRWA": "RWA 真實資產", "ssiDePIN": "DePIN", "ssiSocialFi": "SocialFi",
    "ssiCeFi": "CeFi", "ssiNFT": "NFT", "ssiMAG7": "加密七雄", "ssiGameFi": "GameFi",
}
_RISK_ON = {"ssiMeme", "ssiAI", "ssiDeFi", "ssiSocialFi", "ssiGameFi", "ssiNFT"}


def _pct(x) -> Optional[float]:
    """SoSoValue 的漲跌/ROI 多為小數（-0.011 = -1.1%），轉百分比。"""
    v = _fnum(x)
    return round(v * 100, 2) if v is not None else None


def get_crypto_sector_indices(top_n: int = 6) -> Dict[str, Any]:
    """
    【LLM Tool】加密板塊指數表現（DeFi/Layer1/AI/Meme/RWA/DePIN…）與板塊輪動信號。

    用途：判斷資金正輪動至哪些板塊、市場處於 risk-on（資金進迷因/AI/DeFi）或 risk-off。
    """
    try:
        slugs = _soso_get("/openapi/v1/indices")
    except EnvironmentError as e:
        return {"error": str(e).splitlines()[0], "needs_free_key": True}
    except Exception as e:  # noqa: BLE001
        return {"error": f"板塊指數列表抓取失敗: {e.__class__.__name__}"}
    if not isinstance(slugs, list) or not slugs:
        return {"error": "板塊指數暫無資料。"}

    picks = [s for s in _CURATED_INDICES if s in slugs][:top_n] or list(slugs)[:top_n]
    sectors: List[Dict[str, Any]] = []
    for slug in picks:
        try:
            snap = _soso_get(f"/openapi/v1/indices/{slug}/market-snapshot")
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(snap, dict):
            continue
        sectors.append({
            "slug": slug,
            "name": _INDEX_ZH.get(slug, slug),
            "change_24h_pct": _pct(snap.get("change_pct_24h")),
            "roi_7d_pct": _pct(snap.get("roi_7d")),
            "roi_1m_pct": _pct(snap.get("roi_1m")),
            "risk_on": slug in _RISK_ON,
        })
    if not sectors:
        return {"error": "板塊指數快照暫無資料。"}

    ranked = sorted(sectors, key=lambda x: (x["change_24h_pct"] if x["change_24h_pct"] is not None else -999), reverse=True)
    leader, laggard = ranked[0], ranked[-1]
    up = [s for s in sectors if (s["change_24h_pct"] or 0) > 0]
    risk_on_up = [s for s in up if s["risk_on"]]
    if len(up) >= max(1, len(sectors) * 0.6) and risk_on_up:
        rotation = "risk-on：資金輪動至風險性板塊（迷因/AI/DeFi 領漲）"
    elif not up:
        rotation = "risk-off：板塊全面回落"
    else:
        rotation = "板塊分歧（無明確輪動主線）"
    return {
        "source": "SoSoValue 板塊指數（第一方，免費）",
        "sectors": ranked,
        "leader": {"name": leader["name"], "change_24h_pct": leader["change_24h_pct"]},
        "laggard": {"name": laggard["name"], "change_24h_pct": laggard["change_24h_pct"]},
        "rotation_read": rotation,
        "guide": "板塊指數領漲＝資金輪動方向；風險板塊(迷因/AI)領漲多屬 risk-on、追價情緒濃。",
    }


def get_crypto_stocks(ticker: Optional[str] = None) -> Dict[str, Any]:
    """
    【LLM Tool】加密概念股（MSTR/COIN/礦股…）。省略 ticker → 各板塊市值/漲跌總覽；給 ticker → 單一個股。

    用途：從傳統股市對加密的定價（機構/散戶經由股票表態）讀出間接情緒與資金態度。
    """
    if ticker:
        tk = ticker.upper().strip()
        try:
            snap = _soso_get(f"/openapi/v1/crypto-stocks/{tk}/market-snapshot")
        except EnvironmentError as e:
            return {"error": str(e).splitlines()[0], "needs_free_key": True}
        except Exception as e:  # noqa: BLE001
            return {"error": f"個股行情抓取失敗: {e.__class__.__name__}"}
        if not isinstance(snap, dict) or not snap:
            return {"ticker": tk, "error": "查無此加密概念股（代號可能有誤）。"}
        price = _fnum(snap.get("price") or snap.get("last") or snap.get("close"))
        chg = _pct(snap.get("change_pct_24h") or snap.get("change_24h") or snap.get("change_percent"))
        return {
            "source": "SoSoValue 加密概念股（第一方，免費）",
            "ticker": tk,
            "price": price,
            "change_24h_pct": chg,
            "market_cap": _fnum(snap.get("market_cap") or snap.get("marketcap")),
        }

    # 板塊總覽（1 call）
    try:
        secs = _soso_get("/openapi/v1/crypto-stocks/sectors")
    except EnvironmentError as e:
        return {"error": str(e).splitlines()[0], "needs_free_key": True,
                "hint": "設定免費 SOSOVALUE_API_KEY 後即可讀加密概念股。"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"加密概念股板塊抓取失敗: {e.__class__.__name__}"}
    if not isinstance(secs, list) or not secs:
        return {"error": "加密概念股板塊暫無資料。"}

    out = []
    for s in secs:
        chg = _pct(s.get("change_pct_24h") or s.get("change_24h") or s.get("change") or s.get("change_percent"))
        out.append({
            "sector": s.get("sector_name") or s.get("sector_slug"),
            "total_marketcap": _fnum(s.get("total_marketcap")),
            "change_24h_pct": chg,
        })
    out = [x for x in out if x["total_marketcap"]]
    out.sort(key=lambda x: x["total_marketcap"], reverse=True)
    return {
        "source": "SoSoValue 加密概念股板塊（第一方，免費）",
        "sectors": out[:10],
        "guide": "BTC Treasury / Mining / Exchange 等板塊市值與漲跌＝股市對加密的間接定價與情緒。",
    }

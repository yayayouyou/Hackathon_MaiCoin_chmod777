"""
skills/gold/macro.py — 黃金總經驅動層 (Gold Macro Drivers)
=========================================================
回答「黃金為什麼漲跌」。黃金無現金流，價格主要由『機會成本 + 避險/通膨需求』驅動：

  - 實質利率 (10y TIPS, DFII10)  — 黃金最大單一驅動，『反向』：實質利率↑→持有黃金機會成本↑→利空。
  - 美元指數 (DTWEXBGS)          — 反向：美元走強→以美元計價的黃金相對變貴→利空。
  - 政策利率 (DFF)               — 反向（同機會成本邏輯）。
  - 通膨 (CPI YoY)               — 正向（通膨對沖需求）。
  - 倫敦金定盤 (GOLDPMGBD228NLBM) — 實體黃金現貨參考價（供代幣化溢價比對）。

主源 FRED（一把免費 Key 全包含黃金），輔源 Alpha Vantage（FRED 缺 Key 時的部分備援）。
缺 Key 時回傳 available=false + 啟用指引，而非崩潰。僅供佐證。
"""
import os
from typing import Dict, Any, List, Optional, Tuple
from loguru import logger
from dotenv import load_dotenv

from skills._http import fetch_json, FetchError

load_dotenv()

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
AV_BASE = "https://www.alphavantage.co/query"

# FRED series → (中文名, 對黃金的方向: -1 反向/1 正向, 單位)
_FRED_DRIVERS = {
    "DFII10":  ("10年期實質利率(TIPS)", -1, "%"),
    "DTWEXBGS": ("美元指數(廣義)",       -1, "index"),
    "DFF":     ("聯邦基金有效利率",       -1, "%"),
}
_FRED_CPI = "CPIAUCSL"            # CPI 水準（月），用來算 YoY
_FRED_GVZ = "GVZCLS"             # CBOE 黃金 ETF 波動率指數（黃金版 VIX，日更）— 情報用不計分
# 註：FRED 的倫敦金 LBMA 定盤系列 (GOLD*GBD228NLBM) 已停更會回 400，故不再拉取；
#     實體黃金現貨參考（供代幣化溢價）留待接入獨立金價源（Alpha Vantage/金屬 API）。


def _fred_obs(series_id: str, limit: int, api_key: str) -> List[Tuple[str, float]]:
    """回傳 FRED 觀測值 [(date, value)]（新→舊），略過缺值 '.'。"""
    data = fetch_json(FRED_BASE, params={
        "series_id": series_id, "api_key": api_key, "file_type": "json",
        "sort_order": "desc", "limit": limit,
    }, expect_keys=["observations"])
    out: List[Tuple[str, float]] = []
    for o in data.get("observations", []):
        v = o.get("value")
        if v in (None, ".", ""):
            continue
        try:
            out.append((o.get("date", ""), float(v)))
        except ValueError:
            continue
    return out


def _direction(change: Optional[float], eps: float = 1e-9) -> str:
    if change is None:
        return "unknown"
    if change > eps:
        return "rising"
    if change < -eps:
        return "falling"
    return "flat"


def _fred_driver(series_id: str, api_key: str, lookback: int = 22) -> Optional[Dict[str, Any]]:
    """最新值 + 約一個月變化 + 方向。lookback≈22 交易日。"""
    obs = _fred_obs(series_id, max(lookback + 5, 30), api_key)
    if not obs:
        return None
    latest_date, latest_val = obs[0]
    prev_val = obs[min(lookback, len(obs) - 1)][1] if len(obs) > 1 else None
    change = round(latest_val - prev_val, 4) if prev_val is not None else None
    return {"value": latest_val, "as_of": latest_date, "change_1m": change,
            "direction": _direction(change)}


def _cpi_yoy(api_key: str) -> Optional[Dict[str, Any]]:
    obs = _fred_obs(_FRED_CPI, 16, api_key)   # 多抓緩衝：最新月偶爾未發布，確保 YoY 與『加速方向』都算得出
    if len(obs) < 13:
        return None
    latest_date, latest = obs[0]
    year_ago = obs[12][1]
    yoy = round((latest / year_ago - 1) * 100, 2) if year_ago else None
    # 方向：與上個月的 YoY 比（是否加速）
    prev_yoy = round((obs[1][1] / obs[13][1] - 1) * 100, 2) if len(obs) >= 14 and obs[13][1] else None
    change = round(yoy - prev_yoy, 2) if (yoy is not None and prev_yoy is not None) else None
    return {"value": yoy, "as_of": latest_date, "change_1m": change,
            "direction": _direction(change), "unit": "% YoY"}


def _score_to_read(score: int) -> str:
    if score >= 2:
        return "tailwind"      # 總經順風（偏多黃金）
    if score <= -2:
        return "headwind"      # 總經逆風（偏空黃金）
    return "mixed"


def _from_fred(api_key: str) -> Dict[str, Any]:
    """逐系列容錯：單一系列失敗（如某 series 停更回 400）只跳過該項，不讓整包總經歸零。"""
    drivers: Dict[str, Any] = {}
    score = 0
    failed: List[str] = []
    for sid, (name, gold_sign, unit) in _FRED_DRIVERS.items():
        try:
            d = _fred_driver(sid, api_key)
        except FetchError as e:
            failed.append(f"{sid}({e})")
            continue
        if not d:
            continue
        # 對黃金的即時影響：方向 × 對黃金符號
        impact = "neutral"
        if d["direction"] in ("rising", "falling"):
            up = d["direction"] == "rising"
            bullish = (up and gold_sign > 0) or ((not up) and gold_sign < 0)
            impact = "gold_tailwind" if bullish else "gold_headwind"
            score += 1 if bullish else -1
        drivers[sid] = {**d, "name": name, "unit": unit, "gold_impact": impact}

    try:
        cpi = _cpi_yoy(api_key)
    except FetchError as e:
        cpi, _ = None, failed.append(f"{_FRED_CPI}({e})")
    if cpi:
        impact = "neutral"
        if cpi["direction"] in ("rising", "falling"):
            bullish = cpi["direction"] == "rising"   # 通膨升溫→對沖需求→偏多
            impact = "gold_tailwind" if bullish else "gold_headwind"
            score += 1 if bullish else -1
        drivers[_FRED_CPI] = {**cpi, "name": "CPI 年增率", "gold_impact": impact}

    if not drivers:
        raise FetchError(f"FRED 所有黃金總經系列皆抓取失敗: {'; '.join(failed)}")

    # 黃金波動率指數（GVZ，情報用；高波動=避險/不確定升溫，不納入順逆風計分）
    gvz = None
    try:
        gvz = _fred_driver(_FRED_GVZ, api_key)
    except FetchError:
        pass

    return {
        "available": True, "source": "FRED",
        "drivers": drivers,
        "gold_volatility_index": gvz,           # GVZ：黃金版 VIX
        "london_gold_pm_usd_oz": None,          # LBMA 定盤系列已停更；實體參考待接獨立金價源
        # 覆蓋率不足(可計分驅動 <3/4)時，不要用半套資料充當有把握的 'mixed'
        "gold_macro_read": ("insufficient_data" if len(drivers) < 3 else _score_to_read(score)),
        "macro_score": score,
        "drivers_ok": len(drivers),
        "partial_failures": failed or None,
        "note": "實質利率/美元指數/政策利率對黃金為『反向』，通膨為『正向』。僅為總經脈絡，非交易訊號。",
    }


def _av_query(function: str, api_key: str, **params) -> Dict[str, Any]:
    data = fetch_json(AV_BASE, params={"function": function, "apikey": api_key, **params})
    # AV 免費層限流/錯誤是 HTTP 200 帶 Information/Note/Error Message → 明確拋錯，別被當『無資料』
    if isinstance(data, dict):
        msg = data.get("Information") or data.get("Note") or data.get("Error Message")
        if msg:
            raise FetchError(f"AlphaVantage: {str(msg)[:120]}")
    return data


def _from_alphavantage(api_key: str) -> Dict[str, Any]:
    """FRED 缺 Key 時的部分備援：AV 能給 10y 公債殖利率 / CPI / 政策利率（無實質利率、無美元指數、無黃金）。"""
    drivers: Dict[str, Any] = {}
    try:
        ty = _av_query("TREASURY_YIELD", api_key, interval="monthly", maturity="10year")
        # 取第一筆『有值』的月份（最新月常未發布為 "."）
        pts = [p for p in ty.get("data", []) if p.get("value") not in (None, ".", "")]
        if pts:
            drivers["treasury_10y"] = {"value": float(pts[0]["value"]), "as_of": pts[0]["date"],
                                       "name": "10年期公債殖利率", "unit": "%"}
    except (FetchError, KeyError, ValueError, IndexError):
        pass
    return {
        "available": bool(drivers), "source": "AlphaVantage(fallback)",
        "drivers": drivers,
        "london_gold_pm_usd_oz": None,
        "gold_macro_read": "unknown",
        "caveats": ["Alpha Vantage 備援缺『實質利率/美元指數/實體黃金定盤』且免費層限流(~25次/日)；"
                    "建議設定 FRED_API_KEY 取得完整黃金總經。"],
    }


def get_gold_macro_context() -> Dict[str, Any]:
    """
    【LLM Tool｜黃金】獲取黃金的總經驅動脈絡：實質利率、美元指數、政策利率、CPI 年增與倫敦金定盤，
    各附『對黃金的方向影響 (順風/逆風)』與一個月趨勢，並彙整整體總經體制 (tailwind/headwind/mixed)。
    需免費 FRED_API_KEY（或部分備援 ALPHAVANTAGE_API_KEY）；缺 Key 時回傳啟用指引而非報錯。
    """
    fred_key = os.getenv("FRED_API_KEY", "").strip()
    av_key = os.getenv("ALPHAVANTAGE_API_KEY", "").strip()

    fetch_err = None
    if fred_key:
        try:
            return _from_fred(fred_key)
        except FetchError as e:
            fetch_err = f"FRED: {e}"
            logger.warning(f"FRED 抓取失敗，嘗試 Alpha Vantage 備援: {e}")

    if av_key:
        try:
            return _from_alphavantage(av_key)
        except FetchError as e:
            fetch_err = (fetch_err + f"；AV: {e}") if fetch_err else f"AV: {e}"
            logger.error(f"Alpha Vantage 總經抓取失敗: {e}")

    # 有設定金鑰但抓取失敗 → 明確回報（別誤報成「未設定」，方便排查無效/未啟用金鑰）
    if fred_key or av_key:
        return {
            "available": False,
            "reason": "已設定金鑰但總經抓取失敗（金鑰可能無效/未啟用，或來源暫時異常）",
            "detail": fetch_err,
            "how_to_check": "確認 FRED key 有效且已啟用（FRED 核發後即時生效）；HTTP 400 多為金鑰錯誤。",
            "note": "代幣化黃金報價 get_gold_price 不受影響、仍可正常使用。",
        }

    return {
        "available": False,
        "reason": "未設定 FRED_API_KEY（或 ALPHAVANTAGE_API_KEY）",
        "how_to_enable": "FRED 免費申請 https://fred.stlouisfed.org/docs/api/api_key.html ，"
                         "將 FRED_API_KEY 寫入 .env 即可取得完整黃金總經（實質利率/美元指數/CPI/政策利率/倫敦金）。",
        "note": "代幣化黃金報價 get_gold_price 不需此 Key、仍可正常使用。",
    }

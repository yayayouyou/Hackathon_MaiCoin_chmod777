"""
skills/market_data/coinglass_client.py

模塊一：衍生品數據抓取 — 基於 Coinglass Open API v4
=====================================================
提供以下 LLM Tool 函數：
  - get_funding_rate         : 獲取資金費率（歷史 OHLC）
  - get_open_interest        : 獲取持倉量（歷史 OHLC）
  - get_liquidation_history  : 獲取爆倉歷史數據
  - get_long_short_ratio     : 獲取多空比數據

API 文件：https://open-api-v4.coinglass.com/api/docs
認證方式：HTTP Header "CG-API-KEY"

注意：Coinglass API v4 需要付費方案的 API Key
      免費帳號僅能存取部分端點與有限數據量

作者：AI Crypto Trading Agent Project
"""

import os
from typing import Optional
from datetime import datetime, timezone

import requests
from loguru import logger
from dotenv import load_dotenv

from skills._http import session_get

load_dotenv()

# ──────────────────────────────────────────────
#  常數設定
# ──────────────────────────────────────────────
COINGLASS_BASE_URL = "https://open-api-v4.coinglass.com"
# ⚠️ 注意：API Key 不在模組層級讀取，改在每次請求時動態讀取
# 這樣 @patch.dict(os.environ, ...) 在測試中才能正確生效

# v4 支援的時間間隔（官方文件 2025：無 2h，含 8h/1w）
SUPPORTED_INTERVALS = ["1m", "3m", "5m", "15m", "30m", "1h", "4h", "6h", "8h", "12h", "1d", "1w"]
SUPPORTED_EXCHANGES_CG = ["Binance", "OKX", "Bybit", "Bitget", "Deribit", "CME", "All"]

# 免費替代工具（無 CoinGlass 付費金鑰時，引導 agent 改用直連交易所的免費彙整工具）
_FREE_ALT_HINT = ("免費替代：get_aggregated_funding_rate / get_aggregated_open_interest / "
                  "get_binance_long_short_ratio（直連交易所、免金鑰）。")


def _is_placeholder_key(key: str) -> bool:
    """偵測 .env 內仍為範本佔位符（如 your_xxx_here）而非真實金鑰的情況。"""
    k = (key or "").strip().lower()
    if not k:
        return True
    return (k.startswith("your") or k.startswith("<") or
            k in ("changeme", "placeholder", "xxx", "api_key", "todo", "none"))


def _ts_to_iso(ts) -> str:
    """把秒或毫秒時間戳統一轉成 ISO8601 UTC 字串（v4 用毫秒；舊格式用秒）。"""
    try:
        t = float(ts or 0)
    except (TypeError, ValueError):
        return ""
    if t > 1e12:      # 毫秒 → 秒
        t /= 1000.0
    if t <= 0:
        return ""
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ──────────────────────────────────────────────
#  HTTP 請求基礎工具
# ──────────────────────────────────────────────
def _cg_request(endpoint: str, params: dict) -> dict:
    """
    執行 Coinglass API v4 的 GET 請求。

    Args:
        endpoint : API 路徑，例如 '/api/futures/funding-rate/history'
        params   : 查詢參數 dict

    Returns:
        API 返回的 JSON data 字段

    Raises:
        EnvironmentError : API Key 未設定或仍為佔位符
        requests.HTTPError : HTTP 請求失敗
        RuntimeError : API 返回業務錯誤（含金鑰無效）
    """
    # 每次請求時動態讀取，確保 test patch 能生效
    api_key = os.getenv("COINGLASS_API_KEY", "").strip()
    if _is_placeholder_key(api_key):
        raise EnvironmentError(
            "COINGLASS_API_KEY 未設定（或仍為 .env 範本佔位符）！請填入真實的 Coinglass API Key。\n"
            f"申請地址：https://www.coinglass.com/pricing\n{_FREE_ALT_HINT}"
        )

    headers = {
        "accept": "application/json",
        "CG-API-KEY": api_key,
    }
    url = COINGLASS_BASE_URL + endpoint
    logger.debug(f"Coinglass 請求：{url} 參數：{params}")

    resp = session_get(url, headers=headers, params=params)
    resp.raise_for_status()

    body = resp.json()

    # Coinglass v4 的業務碼：成功為 code=="0"；金鑰無效/無權限時 HTTP 仍 200 但 code!=0。
    # ⚠️ 舊版只檢查 success 欄位，會把 {code:401,data:[]} 誤當成功→靜默回空，務必攔下。
    code = body.get("code")
    if code is not None and str(code) != "0":
        msg = body.get("msg") or body.get("message") or "未知錯誤"
        if str(code) in ("401", "403", "30001", "50001") or "key" in str(msg).lower():
            raise RuntimeError(
                f"CoinGlass API 金鑰無效或無存取權限（code={code}）：{msg}。{_FREE_ALT_HINT}")
        raise RuntimeError(f"CoinGlass API 業務錯誤（code={code}）：{msg}")
    # 舊版相容：部分端點以 success 欄位表示成敗
    if body.get("success") is False:
        raise RuntimeError(
            f"CoinGlass API 業務錯誤（code={body.get('code','unknown')}）："
            f"{body.get('msg', body.get('message', '未知錯誤'))}")

    return body.get("data", body)


# ──────────────────────────────────────────────
#  Tool 1：get_funding_rate — 資金費率
# ──────────────────────────────────────────────
def get_funding_rate(
    symbol: str,
    exchange: str = "Binance",
    interval: str = "8h",
    limit: int = 30,
) -> dict:
    """
    【LLM Tool】獲取指定交易對在特定交易所的資金費率歷史數據。

    資金費率反映多空雙方的借貸成本，是判斷市場情緒的重要指標：
    - 正費率（多方支付空方）：市場偏多，多頭擁擠
    - 負費率（空方支付多方）：市場偏空，空頭擁擠

    Args:
        symbol   : 幣種符號，例如 'BTC', 'ETH'（不含 USDT）
        exchange : 交易所名稱，例如 'Binance', 'OKX'（預設 'Binance'）
        interval : 數據時間間隔，例如 '8h', '1h', '1d'（預設 '8h'）
        limit    : 返回數量（預設 30）

    Returns:
        dict 結構如下：
        {
            "symbol": "BTC",
            "exchange": "Binance",
            "interval": "8h",
            "count": 30,
            "latest_rate": 0.0001,        # 最新資金費率（小數，0.0001 = 0.01%）
            "latest_rate_pct": 0.01,      # 最新費率（百分比）
            "avg_rate_pct": 0.008,        # 平均費率（百分比）
            "max_rate_pct": 0.05,         # 期間最高費率
            "min_rate_pct": -0.02,        # 期間最低費率
            "sentiment": "略偏多",         # 市場情緒簡析
            "history": [
                {
                    "timestamp": "2024-01-01T08:00:00Z",
                    "rate": 0.0001,
                    "rate_pct": 0.01
                },
                ...
            ]
        }
    """
    endpoint = "/api/futures/funding-rate/history"   # v4 現行路徑（原 camelCase 已 404）
    params = {
        "exchange": exchange,
        "symbol":   symbol.upper() + "USDT",   # Coinglass 用全名
        "interval": interval,
        "limit":    limit,
    }

    logger.info(f"抓取資金費率：{symbol} @ {exchange} interval={interval} x{limit}")
    raw = _cg_request(endpoint, params)

    # raw 可能是列表或帶 list 字段的 dict
    records = raw if isinstance(raw, list) else raw.get("list", raw.get("data", []))

    history = []
    rates = []
    for item in records:
        # v4 OHLC 格式：{time: ms, open/high/low/close}；相容舊 {t, c}
        ts   = item.get("time") or item.get("t") or item.get("timestamp") or 0
        rate = (item.get("close") if item.get("close") is not None else
                item.get("c") or item.get("fundingRate") or item.get("rate") or 0)
        rate = float(rate)
        rates.append(rate)
        history.append({
            "timestamp": _ts_to_iso(ts),
            "rate":      round(rate, 8),
            "rate_pct":  round(rate * 100, 6),
        })

    # 市場情緒簡析
    latest_rate = rates[-1] if rates else 0.0
    avg_rate    = sum(rates) / len(rates) if rates else 0.0

    if latest_rate > 0.0003:
        sentiment = "明顯偏多（多頭擁擠，注意風險）"
    elif latest_rate > 0.0001:
        sentiment = "略偏多"
    elif latest_rate < -0.0003:
        sentiment = "明顯偏空（空頭擁擠，注意風險）"
    elif latest_rate < -0.0001:
        sentiment = "略偏空"
    else:
        sentiment = "中性"

    result = {
        "symbol":          symbol.upper(),
        "exchange":        exchange,
        "interval":        interval,
        "count":           len(history),
        "latest_rate":     round(latest_rate, 8),
        "latest_rate_pct": round(latest_rate * 100, 6),
        "avg_rate_pct":    round(avg_rate * 100, 6),
        "max_rate_pct":    round(max(rates) * 100, 6) if rates else 0.0,
        "min_rate_pct":    round(min(rates) * 100, 6) if rates else 0.0,
        "sentiment":       sentiment,
        "history":         history,
    }
    logger.success(f"資金費率：{symbol}@{exchange} 最新={latest_rate*100:.4f}% 情緒={sentiment}")
    return result


# ──────────────────────────────────────────────
#  Tool 2：get_open_interest — 持倉量
# ──────────────────────────────────────────────
def get_open_interest(
    symbol: str,
    exchange: str = "Binance",
    interval: str = "1h",
    limit: int = 48,
) -> dict:
    """
    【LLM Tool】獲取指定交易對的持倉量（Open Interest）歷史數據。

    持倉量代表市場中未平倉合約的總價值，是衡量市場熱度的關鍵指標：
    - OI 上升 + 價格上升：多頭趨勢強烈
    - OI 上升 + 價格下降：空頭趨勢強烈
    - OI 下降：市場去槓桿，趨勢可能反轉

    Args:
        symbol   : 幣種符號，例如 'BTC', 'ETH'
        exchange : 交易所名稱（預設 'Binance'）
        interval : 數據間隔（預設 '1h'）
        limit    : 返回數量（預設 48，即最近 48 小時）

    Returns:
        dict 結構如下：
        {
            "symbol": "BTC",
            "exchange": "Binance",
            "interval": "1h",
            "count": 48,
            "latest_oi_usd": 12345678900.0,   # 最新 OI（USD）
            "latest_oi_token": 183234.5,       # 最新 OI（幣種數量）
            "oi_change_pct": 3.45,             # 期間 OI 變化百分比
            "history": [...]
        }
    """
    endpoint = "/api/futures/open-interest/history"   # v4 現行路徑（原 camelCase 已 404）
    params = {
        "exchange": exchange,
        "symbol":   symbol.upper() + "USDT",
        "interval": interval,
        "limit":    limit,
    }

    logger.info(f"抓取持倉量：{symbol} @ {exchange} interval={interval} x{limit}")
    raw = _cg_request(endpoint, params)
    records = raw if isinstance(raw, list) else raw.get("list", raw.get("data", []))

    history = []
    oi_usd_list = []
    for item in records:
        ts        = item.get("time") or item.get("t") or item.get("timestamp") or 0
        oi_usd    = float((item.get("close") if item.get("close") is not None else
                           item.get("c") or item.get("openInterest") or item.get("h", 0)))
        oi_token  = float(item.get("openInterestToken") or item.get("oiToken") or 0)
        oi_usd_list.append(oi_usd)
        history.append({
            "timestamp": _ts_to_iso(ts),
            "oi_usd":   round(oi_usd, 2),
            "oi_token": round(oi_token, 4),
        })

    first_oi  = oi_usd_list[0]  if oi_usd_list else 0
    latest_oi = oi_usd_list[-1] if oi_usd_list else 0
    oi_change = round((latest_oi - first_oi) / first_oi * 100, 2) if first_oi else 0.0

    result = {
        "symbol":          symbol.upper(),
        "exchange":        exchange,
        "interval":        interval,
        "count":           len(history),
        "latest_oi_usd":   round(latest_oi, 2),
        "oi_change_pct":   oi_change,
        "oi_trend":        "上升" if oi_change > 1 else ("下降" if oi_change < -1 else "持平"),
        "history":         history,
    }
    logger.success(f"持倉量：{symbol}@{exchange} 最新={latest_oi:,.0f} USD 變化={oi_change}%")
    return result


# ──────────────────────────────────────────────
#  Tool 3：get_liquidation_history — 爆倉數據
# ──────────────────────────────────────────────
def get_liquidation_history(
    symbol: str,
    exchange: str = "Binance",
    interval: str = "1h",
    limit: int = 24,
) -> dict:
    """
    【LLM Tool】獲取指定交易對的爆倉歷史數據。

    爆倉數據顯示在某時間段內被強制平倉的金額，是判斷短期波動風險的重要指標：
    - 大量多頭爆倉：快速下跌後可能出現反彈
    - 大量空頭爆倉：快速上漲後可能出現回調

    Args:
        symbol   : 幣種符號，例如 'BTC', 'ETH'
        exchange : 交易所名稱（預設 'Binance'）
        interval : 數據間隔（預設 '1h'）
        limit    : 返回數量（預設 24）

    Returns:
        dict with liquidation summary and history
    """
    endpoint = "/api/futures/liquidation/history"   # v4 路徑未變（仍有效）
    params = {
        "exchange": exchange,
        "symbol":   symbol.upper() + "USDT",
        "interval": interval,
        "limit":    limit,
    }

    logger.info(f"抓取爆倉數據：{symbol} @ {exchange} interval={interval} x{limit}")
    raw = _cg_request(endpoint, params)
    records = raw if isinstance(raw, list) else raw.get("list", raw.get("data", []))

    history = []
    total_long_liq = 0.0
    total_short_liq = 0.0

    for item in records:
        ts         = item.get("time") or item.get("t") or item.get("timestamp") or 0
        long_liq   = float(item.get("longLiquidationUsd") or item.get("aggregatedLongLiquidationUsd") or item.get("buyLiq") or 0)
        short_liq  = float(item.get("shortLiquidationUsd") or item.get("aggregatedShortLiquidationUsd") or item.get("sellLiq") or 0)
        total_long_liq  += long_liq
        total_short_liq += short_liq
        history.append({
            "timestamp":          _ts_to_iso(ts),
            "long_liquidation_usd":  round(long_liq, 2),
            "short_liquidation_usd": round(short_liq, 2),
            "total_usd":             round(long_liq + short_liq, 2),
        })

    total = total_long_liq + total_short_liq
    liq_bias = "多頭爆倉為主" if total_long_liq > total_short_liq * 1.5 else \
               ("空頭爆倉為主" if total_short_liq > total_long_liq * 1.5 else "多空均衡")

    result = {
        "symbol":               symbol.upper(),
        "exchange":             exchange,
        "interval":             interval,
        "period_count":         len(history),
        "total_liquidation_usd":    round(total, 2),
        "long_liquidation_usd":     round(total_long_liq, 2),
        "short_liquidation_usd":    round(total_short_liq, 2),
        "liquidation_bias":         liq_bias,
        "history":                  history,
    }
    logger.success(f"爆倉數據：{symbol}@{exchange} 總額={total:,.0f} USD 偏向={liq_bias}")
    return result


# ──────────────────────────────────────────────
#  Tool 4：get_long_short_ratio — 多空比
# ──────────────────────────────────────────────
def get_long_short_ratio(
    symbol: str,
    exchange: str = "Binance",
    interval: str = "1h",
    limit: int = 24,
) -> dict:
    """
    【LLM Tool】獲取指定交易對的全球帳戶多空比（Global Account Ratio）。

    多空比代表持多倉帳戶 vs 持空倉帳戶的數量比例：
    - 多空比 > 1：多方帳戶佔多數
    - 多空比 < 1：空方帳戶佔多數
    - 極端值往往是反向指標（群眾情緒過熱時需謹慎）

    Args:
        symbol   : 幣種符號，例如 'BTC', 'ETH'
        exchange : 交易所名稱（預設 'Binance'）
        interval : 數據間隔（預設 '1h'）
        limit    : 返回數量（預設 24）

    Returns:
        dict with long/short ratio summary and history
    """
    endpoint = "/api/futures/global-long-short-account-ratio/history"   # v4 現行路徑（原 camelCase 已 404）
    params = {
        "exchange": exchange,
        "symbol":   symbol.upper() + "USDT",
        "interval": interval,
        "limit":    limit,
    }

    logger.info(f"抓取多空比：{symbol} @ {exchange} interval={interval} x{limit}")
    raw = _cg_request(endpoint, params)
    records = raw if isinstance(raw, list) else raw.get("list", raw.get("data", []))

    history = []
    ratios = []
    for item in records:
        ts        = item.get("time") or item.get("t") or item.get("timestamp") or 0
        # v4 多為百分比字串（如 "52.3"）或比例；global_account_long_percent 等欄位相容
        long_pct  = float(item.get("global_account_long_percent") or item.get("longAccount") or item.get("longRatio") or 0)
        short_pct = float(item.get("global_account_short_percent") or item.get("shortAccount") or item.get("shortRatio") or 0)
        # 若為 0~1 的比例則轉百分比
        if 0 < long_pct <= 1 and 0 < short_pct <= 1:
            long_pct *= 100; short_pct *= 100
        ratio     = round(long_pct / short_pct, 4) if short_pct != 0 else 0
        ratios.append(ratio)
        history.append({
            "timestamp":   _ts_to_iso(ts),
            "long_pct":    round(long_pct, 2),
            "short_pct":   round(short_pct, 2),
            "long_short_ratio": ratio,
        })

    latest_ratio = ratios[-1] if ratios else 1.0
    avg_ratio    = sum(ratios) / len(ratios) if ratios else 1.0

    sentiment = "極度看多（可能過熱）" if latest_ratio > 2.0 else \
                ("看多" if latest_ratio > 1.2 else \
                ("極度看空（可能過冷）" if latest_ratio < 0.5 else \
                ("看空" if latest_ratio < 0.8 else "中性")))

    result = {
        "symbol":           symbol.upper(),
        "exchange":         exchange,
        "interval":         interval,
        "count":            len(history),
        "latest_ratio":     latest_ratio,
        "avg_ratio":        round(avg_ratio, 4),
        "sentiment":        sentiment,
        "history":          history,
    }
    logger.success(f"多空比：{symbol}@{exchange} 最新={latest_ratio} 情緒={sentiment}")
    return result

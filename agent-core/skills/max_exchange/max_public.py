"""
skills/max_exchange/max_public.py

MAX 交易所公開行情 API 封裝
=============================================
提供以下公開行情函數（不需要 API Key）：
  - get_max_markets        : 獲取 MAX 支持的所有交易對列表
  - get_max_tickers        : 獲取最新成交行情 (所有或單一交易對)
  - get_max_depth          : 獲取市場深度 (Order Book)
  - get_max_klines         : 獲取 K 線歷史數據 (K-lines)
  - get_max_public_trades  : 獲取公共歷史成交記錄
"""

import time
import requests  # 保留供 requests.exceptions 使用
from typing import Optional, List, Dict, Any
from loguru import logger

from skills._http import session_get

MAX_API_BASE_URL = "https://max-api.maicoin.com"

def _normalize_market_id(market: str) -> str:
    """將交易對名稱轉換為 MAX 格式（小寫、去斜線，例如 BTC/TWD -> btctwd，單一幣種如 BTC -> btctwd）"""
    m_id = market.replace("/", "").replace("_", "").lower()
    
    # 若輸入為單一幣種名（例如 btc, eth），預設補上台灣市場最常用的台幣交易對（twd）
    if len(m_id) in (3, 4):
        active_bases = ["btc", "eth", "max", "usdt", "sol", "doge", "xrp", "ltc", "trx", "bch", "ada", "link"]
        if m_id in active_bases:
            return f"{m_id}twd"
            
    return m_id

def _max_public_request(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """執行 MAX 公開 API GET 請求"""
    url = f"{MAX_API_BASE_URL}{endpoint}"
    logger.debug(f"MAX 公開 API 請求: {url} params: {params}")
    try:
        resp = session_get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"MAX API 請求失敗: {e}")
        raise RuntimeError(f"MAX API 請求異常: {e}")

def get_max_markets() -> List[Dict[str, Any]]:
    """
    【LLM Tool】獲取 MAX 交易所目前支持的所有交易對（Markets）及詳細配置資訊。
    """
    raw_markets = _max_public_request("/api/v3/markets")
    if not isinstance(raw_markets, list):
        return []
    
    # 精簡數據以節省 token
    markets = []
    for m in raw_markets:
        markets.append({
            "id": m.get("id"),              # 例如 "btctwd"
            "name": m.get("name"),          # 例如 "BTC/TWD"
            "base_unit": m.get("base_unit"),
            "quote_unit": m.get("quote_unit"),
            "base_precision": m.get("base_unit_precision"),
            "quote_precision": m.get("quote_unit_precision"),
            "min_base_amount": m.get("min_base_amount"),
            "min_quote_amount": m.get("min_quote_amount")
        })
    return markets

# 交易對規格（最低下單量）幾乎不變，快取 1 小時；下單前檢查用，不必每筆單都打 API
_MARKET_RULES_CACHE: Dict[str, Any] = {"ts": 0.0, "data": None}
_MARKET_RULES_TTL = 3600


def get_max_market_rules(market: str) -> Optional[Dict[str, Any]]:
    """回傳單一交易對的下單規格 {min_base_amount, min_quote_amount, base_unit, quote_unit, base_precision}；查無此對回 None。"""
    now = time.time()
    if not _MARKET_RULES_CACHE["data"] or now - _MARKET_RULES_CACHE["ts"] > _MARKET_RULES_TTL:
        raw = _max_public_request("/api/v3/markets")
        _MARKET_RULES_CACHE["data"] = {
            str(m.get("id")): {
                "min_base_amount": m.get("min_base_amount"),
                "min_quote_amount": m.get("min_quote_amount"),
                "base_unit": m.get("base_unit"),
                "quote_unit": m.get("quote_unit"),
                "base_precision": m.get("base_unit_precision"),
            }
            for m in (raw if isinstance(raw, list) else []) if m.get("id")
        }
        _MARKET_RULES_CACHE["ts"] = now
    return _MARKET_RULES_CACHE["data"].get(_normalize_market_id(market))

# 幣種 metadata 幾乎不變（新增幣/調整提幣費才變），快取 1 小時避免每次載入儀表板都打 API
_CURRENCIES_CACHE: Dict[str, Any] = {"ts": 0.0, "data": None}
_CURRENCIES_TTL = 3600


def get_max_currencies(currency: Optional[str] = None) -> Any:
    """
    【LLM Tool】獲取 MAX 幣種 metadata：可否質押(stakeable)、可否融資(m_wallet)、以及各
    區塊鏈網路的提幣手續費 / 最低提幣量 / 是否需 memo / 存提是否開放。
    帶 currency（如 'USDT'）只回該幣；不帶則回全部（dict，key 為幣種大寫）。結果快取 1 小時。
    """
    now = time.time()
    if not _CURRENCIES_CACHE["data"] or now - _CURRENCIES_CACHE["ts"] > _CURRENCIES_TTL:
        raw = _max_public_request("/api/v3/currencies")
        data: Dict[str, Any] = {}
        for c in (raw if isinstance(raw, list) else []):
            sym = str(c.get("currency", "")).upper()
            if not sym:
                continue
            stk = c.get("staking") or {}
            nets = []
            for n in (c.get("networks") or []):
                nets.append({
                    "network": n.get("network_protocol") or n.get("id"),
                    "withdrawal_fee": n.get("withdrawal_fee"),
                    "min_withdrawal_amount": n.get("min_withdrawal_amount"),
                    "withdrawal_enabled": n.get("withdrawal_enabled"),
                    "deposit_enabled": n.get("deposit_enabled"),
                    "need_memo": n.get("need_memo"),
                })
            data[sym] = {
                "currency": sym,
                "type": c.get("type"),
                "precision": c.get("precision"),
                "stakeable": bool(stk.get("stake_flag")),
                "m_wallet_supported": bool(c.get("m_wallet_supported")),
                "m_wallet_borrowable": bool(c.get("m_wallet_borrowable")),
                "networks": nets,
            }
        _CURRENCIES_CACHE["data"] = data
        _CURRENCIES_CACHE["ts"] = now
    data = _CURRENCIES_CACHE["data"] or {}
    if currency:
        return data.get(str(currency).upper())
    return data


def get_max_interest_rates(currency: Optional[str] = None) -> Any:
    """
    【LLM Tool】獲取 MAX 融資（M-Wallet 借幣）利率，並把「時利率」換算為日/年化(%)方便判讀。
    帶 currency（如 'USDT'）只回該幣；不帶則回全部。適合回答『借 USDT 利息多少 / 資金成本』。
    """
    raw = _max_public_request("/api/v3/wallet/m/interest_rates")
    out: Dict[str, Any] = {}
    for cur, v in (raw or {}).items():
        try:
            hourly = float((v or {}).get("hourly_interest_rate"))
        except (TypeError, ValueError, AttributeError):
            continue
        out[str(cur).upper()] = {
            "hourly_pct": round(hourly * 100, 6),
            "daily_pct": round(hourly * 24 * 100, 5),
            "annual_pct": round(hourly * 24 * 365 * 100, 3),   # 年化 APR
        }
    if currency:
        return out.get(str(currency).upper())
    return out


def get_max_index_prices(market: Optional[str] = None) -> Any:
    """
    【LLM Tool】獲取 MAX 指數/標記價格（跨交易所加權，為融資計價與清算基準）。可用來跟現貨價
    比較看溢價/折價。market 如 'BTC/USDT' 或 'btcusdt'；不帶則回全部（dict）。
    """
    raw = _max_public_request("/api/v3/wallet/m/index_prices")
    out: Dict[str, float] = {}
    for k, v in (raw or {}).items():
        try:
            out[str(k).lower()] = float(v)
        except (TypeError, ValueError):
            continue
    if market:
        mid = str(market).replace("/", "").replace("_", "").lower()
        return {mid: out[mid]} if mid in out else None
    return out


def get_max_tickers(market: Optional[str] = None) -> Any:
    """
    【LLM Tool】獲取 MAX 最新行情報價 (Ticker)。
    
    Args:
        market: 選填。交易對符號，例如 'BTC/TWD' 或 'btctwd'。如果不填，則返回所有交易對行情。
    """
    if market:
        market_id = _normalize_market_id(market)
        params = {"markets[]": [market_id]}
        raw_tickers = _max_public_request("/api/v3/tickers", params)
        if isinstance(raw_tickers, list) and len(raw_tickers) > 0:
            return raw_tickers[0]
        return {"error": f"找不到 {market} 的行情數據"}
    else:
        # 獲取所有交易對
        markets = get_max_markets()
        market_ids = [m["id"] for m in markets if m.get("id")]
        params = {"markets[]": market_ids}
        return _max_public_request("/api/v3/tickers", params)

def get_max_depth(market: str, limit: int = 20) -> Dict[str, Any]:
    """
    【LLM Tool】獲取 MAX 交易所特定交易對的買賣深度 (Order Book)。
    
    Args:
        market: 交易對符號，例如 'BTC/TWD' 或 'btctwd'
        limit: 返回深度條數，默認 20
    """
    market_id = _normalize_market_id(market)
    params = {"market": market_id, "limit": limit}
    raw_depth = _max_public_request("/api/v3/depth", params)
    
    # 計算買賣總累計
    bids = raw_depth.get("bids", [])
    asks = raw_depth.get("asks", [])
    
    total_bid_vol = sum(float(b[1]) for b in bids)
    total_ask_vol = sum(float(a[1]) for a in asks)
    
    return {
        "market": market_id,
        "timestamp": raw_depth.get("timestamp"),
        "total_bid_volume": total_bid_vol,
        "total_ask_volume": total_ask_vol,
        "bids": bids[:limit],
        "asks": asks[:limit]
    }

# 常見時間週期字串 → 分鐘（讓工具同時接受 '1h' 這類寫法，與 get_ohlcv 一致）
_TIMEFRAME_TO_MINUTES = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "6h": 360, "12h": 720,
    "1d": 1440, "3d": 4320, "1w": 10080,
}


def get_max_klines(
    market: str,
    limit: int = 100,
    period_minutes: Optional[int] = None,
    timeframe: Optional[str] = None,
) -> List[List[Any]]:
    """
    【LLM Tool】獲取 MAX 交易所特定交易對的 K 線歷史數據。

    Args:
        market: 交易對符號，例如 'BTC/TWD'
        limit: 獲取 K 線數量，預設 100
        period_minutes: K 線週期（分鐘），可選 [1,5,15,30,60,120,240,360,720,1440,4320,10080]
        timeframe: 也可用字串時間週期（如 '1h','4h','1d'），會自動換算為分鐘（與 get_ohlcv 一致）
    """
    period = period_minutes
    if period is None and timeframe:
        period = _TIMEFRAME_TO_MINUTES.get(str(timeframe).lower())
    if period is None:
        period = 60  # 預設 1 小時

    market_id = _normalize_market_id(market)
    params = {
        "market": market_id,
        "limit": limit,
        "period": period
    }
    raw_k = _max_public_request("/api/v3/k", params)
    return raw_k  # 格式: [[timestamp, open, high, low, close, volume], ...]

def get_max_public_trades(market: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    【LLM Tool】獲取 MAX 交易所近期公共成交歷史記錄。
    
    Args:
        market: 交易對符號，例如 'BTC/TWD'
        limit: 返回記錄條數，默認 50
    """
    market_id = _normalize_market_id(market)
    params = {"market": market_id, "limit": limit}
    return _max_public_request("/api/v3/trades", params)

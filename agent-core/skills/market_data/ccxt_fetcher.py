"""
skills/market_data/ccxt_fetcher.py

模塊一：行情數據抓取 — 基於 CCXT 庫
======================================
提供以下 LLM Tool 函數：
  - get_ohlcv       : 獲取 K 線（OHLCV）數據
  - get_ticker      : 獲取最新成交行情
  - get_orderbook   : 獲取 Orderbook 深度
  - list_exchanges  : 列出所有支援的交易所

所有輸出均已結構化精簡，適合直接餵給 LLM 分析。
LLM 不應接收超過需要的原始數據（減少 token 消耗 + 降低幻覺風險）。

作者：AI Crypto Trading Agent Project
"""

import os
import time
import threading
from typing import Optional
from datetime import datetime, timezone

import ccxt
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

# 交易所實例池：以 (exchange_id, private, market_type) 為鍵快取，避免每次呼叫都
# 重建實例 + 重載全市場（數百 KB、高權重）+ 重置 enableRateLimit 限流器狀態。
_exchange_pool: dict = {}
_pool_lock = threading.Lock()

# 常見報價幣，供無斜線 symbol 正規化（btcusdt → BTC/USDT）
_QUOTE_CURRENCIES = ("USDT", "USDC", "BUSD", "USD", "TWD", "EUR", "BTC", "ETH", "DAI")


def _normalize_symbol(symbol: str) -> str:
    """把 LLM 可能吐出的各種寫法正規化成 ccxt 需要的 'BASE/QUOTE'。"""
    s = (symbol or "").strip().upper().replace("-", "/").replace("_", "/")
    if "/" in s or not s:
        return s
    for q in _QUOTE_CURRENCIES:
        if s.endswith(q) and len(s) > len(q):
            return f"{s[:-len(q)]}/{q}"
    return s

# ──────────────────────────────────────────────
#  支援的交易所與時間週期常數
# ──────────────────────────────────────────────
SUPPORTED_EXCHANGES = ["binance", "okx", "bybit", "kraken", "coinbase", "max"]
SUPPORTED_TIMEFRAMES = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"]

# 各交易所 API Key 環境變數對照表
_EXCHANGE_ENV_MAP = {
    "binance": {"apiKey": "BINANCE_API_KEY", "secret": "BINANCE_SECRET"},
    "okx":     {"apiKey": "OKX_API_KEY", "secret": "OKX_SECRET", "password": "OKX_PASSPHRASE"},
    "bybit":   {"apiKey": "BYBIT_API_KEY", "secret": "BYBIT_SECRET"},
    "kraken":  {"apiKey": "KRAKEN_API_KEY", "secret": "KRAKEN_SECRET"},
    "coinbase":{"apiKey": "COINBASE_API_KEY", "secret": "COINBASE_SECRET"},
    "max":     {"apiKey": "MAX_API_KEY", "secret": "MAX_API_SECRET"},
}


# ──────────────────────────────────────────────
#  交易所實例工廠（帶 API Key 注入 + Rate Limit）
# ──────────────────────────────────────────────
def _create_exchange(exchange_id: str, use_private_api: bool = False,
                     market_type: str = "spot") -> ccxt.Exchange:
    """
    取得 CCXT 交易所實例（帶實例池快取）。

    - 以 (exchange_id, private, market_type) 為鍵快取，重複呼叫沿用同一實例：
      省去重載市場與重置限流器，enableRateLimit 的節流狀態得以跨呼叫累積（避免爆量被 ban）。
    - defaultType 於「建立時」寫入，避免快取實例被事後 mutate 而互相汙染。
    - 私有 API：從環境變數注入 API Key。

    Raises:
        ValueError: 不支援的交易所 ID
    """
    exchange_id = exchange_id.lower()
    if exchange_id not in ccxt.exchanges:
        raise ValueError(
            f"不支援的交易所：'{exchange_id}'。可用清單：{SUPPORTED_EXCHANGES}"
        )

    key = (exchange_id, bool(use_private_api), market_type)
    with _pool_lock:
        inst = _exchange_pool.get(key)
        if inst is not None:
            return inst

        exchange_class = getattr(ccxt, exchange_id)
        config = {"enableRateLimit": True}  # 必須啟用，避免被交易所封鎖
        if market_type in ("swap", "future"):
            config["options"] = {"defaultType": market_type}

        if use_private_api and exchange_id in _EXCHANGE_ENV_MAP:
            for ccxt_key, env_var in _EXCHANGE_ENV_MAP[exchange_id].items():
                value = os.getenv(env_var)
                if value:
                    config[ccxt_key] = value
                else:
                    logger.warning(f"私有 API 未設定：{env_var}（可能影響需認證的功能）")

        inst = exchange_class(config)
        _exchange_pool[key] = inst
        logger.debug(f"建立並快取交易所實例：{exchange_id} (private={use_private_api}, type={market_type})")
        return inst


# ──────────────────────────────────────────────
#  Tool 1：get_ohlcv — 獲取 K 線數據
# ──────────────────────────────────────────────
def get_ohlcv(
    exchange_id: str,
    symbol: str,
    timeframe: str = "1h",
    limit: int = 100,
    market_type: str = "spot",
) -> dict:
    """
    【LLM Tool】獲取加密貨幣 K 線（OHLCV）數據。

    輸出已精簡：只返回 LLM 分析所需的關鍵數字，
    避免傳遞過多 raw 數據消耗 token。

    Args:
        exchange_id : 交易所 ID，例如 'binance', 'okx', 'bybit'
        symbol      : 交易對，例如 'BTC/USDT', 'ETH/USDT'
        timeframe   : K 線週期，例如 '1h', '4h', '1d'（預設 '1h'）
        limit       : 返回數量（1~500，預設 100）
        market_type : 市場類型 'spot' | 'swap'（預設 'spot'）

    Returns:
        dict 結構如下：
        {
            "exchange": "binance",
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "market_type": "spot",
            "count": 100,
            "latest_close": 67523.5,
            "latest_volume": 1234.56,
            "price_change_pct": 2.34,      # 相較第一根的漲跌幅 %
            "high_in_range": 68100.0,
            "low_in_range": 65200.0,
            "candles": [                    # 精簡格式
                {
                    "timestamp": "2024-01-01T00:00:00Z",
                    "open": 67000.0,
                    "high": 67500.0,
                    "low": 66800.0,
                    "close": 67200.0,
                    "volume": 1234.5
                },
                ...
            ]
        }
    
    Raises:
        ValueError: 參數驗證失敗
        ccxt.NetworkError: 網路連線問題
        ccxt.ExchangeError: 交易所 API 錯誤
    """
    # ── 參數驗證 ──
    limit = max(1, min(500, limit))  # 強制限制範圍
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise ValueError(f"不支援的時間週期：'{timeframe}'。支援：{SUPPORTED_TIMEFRAMES}")
    if market_type not in ("spot", "swap", "future"):
        raise ValueError(f"不支援的市場類型：'{market_type}'。支援：spot, swap, future")

    symbol = _normalize_symbol(symbol)
    # market_type 於建立時寫入快取實例（不再事後 mutate）
    exchange = _create_exchange(exchange_id, use_private_api=False, market_type=market_type)

    logger.info(f"抓取 K 線：{exchange_id} {symbol} {timeframe} x{limit} [{market_type}]")

    try:
        raw_ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    except ccxt.BadSymbol as e:
        raise ValueError(f"交易對 '{symbol}' 在 {exchange_id} 不存在：{e}") from e
    except (ccxt.RateLimitExceeded, ccxt.DDoSProtection) as e:
        return {"error": f"{exchange_id} 觸發限流，請稍後再試：{e.__class__.__name__}"}
    except ccxt.NetworkError as e:
        raise ccxt.NetworkError(f"網路錯誤（{exchange_id}）：{e}") from e

    # 資料完整性閘門：丟掉髒 K 線（high<low / 非正價 / 非有限），避免污染下游分析
    from skills.market_data.ohlcv_guard import clean_ohlcv
    raw_ohlcv, _dropped = clean_ohlcv(raw_ohlcv)
    if _dropped:
        logger.warning(f"get_ohlcv {symbol}@{exchange_id} 丟棄 {_dropped} 根髒 K 線")

    if not raw_ohlcv:
        return {
            "exchange": exchange_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "count": 0,
            "candles": [],
            "error": "交易所返回空數據",
        }

    # ── 數據精簡 & 結構化 ──
    candles = []
    for row in raw_ohlcv:
        ts_ms, o, h, l, c, v = row
        candles.append({
            "timestamp": datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "open":   round(o, 6),
            "high":   round(h, 6),
            "low":    round(l, 6),
            "close":  round(c, 6),
            "volume": round(v, 4),
        })

    first_close = candles[0]["close"]
    last_close  = candles[-1]["close"]
    price_change_pct = round((last_close - first_close) / first_close * 100, 2) if first_close != 0 else 0.0
    highs  = [c["high"] for c in candles]
    lows   = [c["low"]  for c in candles]

    result = {
        "exchange":         exchange_id,
        "symbol":           symbol,
        "timeframe":        timeframe,
        "market_type":      market_type,
        "count":            len(candles),
        "latest_close":     last_close,
        "latest_volume":    candles[-1]["volume"],
        "price_change_pct": price_change_pct,
        "high_in_range":    max(highs),
        "low_in_range":     min(lows),
        "candles":          candles,
        "fetched_at":       datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    logger.success(
        f"K 線抓取完成：{symbol}@{exchange_id} "
        f"最新收盤={last_close} 漲跌={price_change_pct}%"
    )
    return result


# ──────────────────────────────────────────────
#  Tool 2：get_ticker — 獲取最新成交行情
# ──────────────────────────────────────────────
def get_ticker(exchange_id: str, symbol: str) -> dict:
    """
    【LLM Tool】獲取交易對的最新成交行情（Ticker）。

    Args:
        exchange_id : 交易所 ID，例如 'binance'
        symbol      : 交易對，例如 'BTC/USDT'

    Returns:
        dict 結構如下：
        {
            "exchange": "binance",
            "symbol": "BTC/USDT",
            "last_price": 67523.5,
            "bid": 67520.0,
            "ask": 67525.0,
            "spread": 5.0,
            "spread_pct": 0.0074,
            "volume_24h": 25678.34,
            "quote_volume_24h": 1734567890.0,
            "price_change_24h": 1523.5,
            "price_change_pct_24h": 2.31,
            "high_24h": 68100.0,
            "low_24h": 65500.0,
            "timestamp": "2024-01-01T00:00:00Z"
        }
    """
    symbol = _normalize_symbol(symbol)
    exchange = _create_exchange(exchange_id, use_private_api=False)
    logger.info(f"抓取 Ticker：{exchange_id} {symbol}")

    try:
        t = exchange.fetch_ticker(symbol)
    except ccxt.BadSymbol as e:
        raise ValueError(f"交易對 '{symbol}' 在 {exchange_id} 不存在：{e}") from e
    except (ccxt.RateLimitExceeded, ccxt.DDoSProtection) as e:
        return {"error": f"{exchange_id} 觸發限流，請稍後再試：{e.__class__.__name__}"}

    bid  = t.get("bid") or 0.0
    ask  = t.get("ask") or 0.0
    last = t.get("last") or 0.0
    spread     = round(ask - bid, 8) if bid and ask else None
    spread_pct = round(spread / bid * 100, 6) if bid and bid != 0 else None

    result = {
        "exchange":               exchange_id,
        "symbol":                 symbol,
        "last_price":             round(last, 6),
        "bid":                    round(bid, 6),
        "ask":                    round(ask, 6),
        "spread":                 spread,
        "spread_pct":             spread_pct,
        "volume_24h":             round(t.get("baseVolume") or 0, 4),
        "quote_volume_24h":       round(t.get("quoteVolume") or 0, 2),
        "price_change_24h":       round(t.get("change") or 0, 6),
        "price_change_pct_24h":   round(t.get("percentage") or 0, 4),
        "high_24h":               round(t.get("high") or 0, 6),
        "low_24h":                round(t.get("low") or 0, 6),
        "timestamp":              datetime.fromtimestamp(
                                      (t.get("timestamp") or time.time() * 1000) / 1000,
                                      tz=timezone.utc
                                  ).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    logger.success(f"Ticker：{symbol}@{exchange_id} 最新價={last}")
    return result


# ──────────────────────────────────────────────
#  Tool 3：get_orderbook — 獲取 Orderbook 深度
# ──────────────────────────────────────────────
def get_orderbook(exchange_id: str, symbol: str, depth: int = 10) -> dict:
    """
    【LLM Tool】獲取交易對的 Orderbook 掛單深度。

    Args:
        exchange_id : 交易所 ID
        symbol      : 交易對，例如 'BTC/USDT'
        depth       : 單邊掛單層數（預設 10，最多 50）

    Returns:
        dict 結構如下：
        {
            "exchange": "binance",
            "symbol": "BTC/USDT",
            "depth": 10,
            "best_bid": 67520.0,
            "best_ask": 67525.0,
            "spread": 5.0,
            "bid_total_volume": 12.345,  # 掛單總量（base）
            "ask_total_volume": 9.876,
            "bids": [[price, qty], ...],
            "asks": [[price, qty], ...],
            "timestamp": "2024-01-01T00:00:00Z"
        }
    """
    depth = max(1, min(50, depth))
    symbol = _normalize_symbol(symbol)
    exchange = _create_exchange(exchange_id, use_private_api=False)
    logger.info(f"抓取 Orderbook：{exchange_id} {symbol} depth={depth}")

    try:
        ob = exchange.fetch_order_book(symbol, limit=depth)
    except ccxt.BadSymbol as e:
        raise ValueError(f"交易對 '{symbol}' 在 {exchange_id} 不存在：{e}") from e
    except (ccxt.RateLimitExceeded, ccxt.DDoSProtection) as e:
        return {"error": f"{exchange_id} 觸發限流，請稍後再試：{e.__class__.__name__}"}

    bids = [[round(p, 6), round(q, 6)] for p, q in ob.get("bids", [])[:depth]]
    asks = [[round(p, 6), round(q, 6)] for p, q in ob.get("asks", [])[:depth]]

    best_bid = bids[0][0] if bids else None
    best_ask = asks[0][0] if asks else None
    spread   = round(best_ask - best_bid, 6) if best_bid and best_ask else None

    bid_total_vol = round(sum(q for _, q in bids), 4)
    ask_total_vol = round(sum(q for _, q in asks), 4)

    result = {
        "exchange":         exchange_id,
        "symbol":           symbol,
        "depth":            depth,
        "best_bid":         best_bid,
        "best_ask":         best_ask,
        "spread":           spread,
        "bid_total_volume": bid_total_vol,
        "ask_total_volume": ask_total_vol,
        "bid_ask_ratio":    round(bid_total_vol / ask_total_vol, 4) if ask_total_vol != 0 else None,
        "bids":             bids,
        "asks":             asks,
        "timestamp":        datetime.fromtimestamp(
                                (ob.get("timestamp") or time.time() * 1000) / 1000,
                                tz=timezone.utc
                            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    logger.success(f"Orderbook：{symbol}@{exchange_id} 買{best_bid} 賣{best_ask} 差價={spread}")
    return result


# ──────────────────────────────────────────────
#  Tool 4：list_exchanges — 列出支援的交易所
# ──────────────────────────────────────────────
def list_exchanges() -> dict:
    """
    【LLM Tool】列出此系統支援的所有交易所 ID。

    Returns:
        dict 結構如下：
        {
            "supported_in_this_system": ["binance", "okx", ...],
            "total_ccxt_exchanges": 100
        }
    """
    return {
        "supported_in_this_system": SUPPORTED_EXCHANGES,
        "total_ccxt_exchanges": len(ccxt.exchanges),
        "note": "如需使用其他交易所，請在 SUPPORTED_EXCHANGES 清單新增後重啟",
    }

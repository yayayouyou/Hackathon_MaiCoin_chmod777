"""
skills/market_data/coinglass_scraper.py

免 API Key 的 CoinGlass 公開數據抓取與解密模組
===================================================
藉由模擬 CoinGlass 官網前端的 CryptoJS AES-ECB 解密演算法，
繞過對 V4 API Key 的收費依賴，直接獲取高價值的即時合約與衍生品數據。
"""

import time
import base64
import json
import gzip
import requests
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from loguru import logger

from skills._http import session_get

# 歷史與通用 AES 密鑰映射表 (webpack 模組 12471 常數)
_KEY_TABLE = {
    "55": "170b070da9654622",
    "66": "d6537d845a964081",
    "77": "863f08689c97435b",
}

def _derive_key0(v: str, url: str) -> str:
    """計算第一層解密密鑰"""
    constant = _KEY_TABLE.get(v)
    if constant is None:
        constant = urlparse(url).path or url.split("?")[0]
    return base64.b64encode(constant.encode()).decode()[:16]

def _decrypt_payload(encrypted_body: str, user_token_b64: str, v: str, url: str) -> Any:
    """解密 CoinGlass 響應 Payload"""
    outer = json.loads(encrypted_body)
    payload = base64.b64decode(outer["data"])
    token = base64.b64decode(user_token_b64)
    
    key0 = _derive_key0(v, url)
    
    # Layer 1-2: 解密 token 得到實際 AES 密鑰
    step1 = unpad(AES.new(key0.encode(), AES.MODE_ECB).decrypt(token), 16)
    actual_key = gzip.decompress(step1).decode()
    
    # Layer 3-4: 解密資料 payload 得到原始 JSON
    step2 = unpad(AES.new(actual_key.encode(), AES.MODE_ECB).decrypt(payload), 16)
    plain = gzip.decompress(step2).decode()
    
    return json.loads(plain)

def _coinglass_public_request(url: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """發送 CoinGlass 公開請求並自動處理加密"""
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        "cache-ts-v2": str(int(time.time() * 1000)),
        "encryption": "true",
        "language": "en",
        "Origin": "https://www.coinglass.com",
        "Referer": "https://www.coinglass.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    }
    # 1) 網路/HTTP 階段：失敗屬「暫時性」（共用層已自動重試）
    try:
        resp = session_get(url, params=params or {}, headers=headers)
        resp.raise_for_status()
    except Exception as e:  # noqa: BLE001
        logger.error(f"CoinGlass 網路請求失敗: {url} | {e}")
        return {"error": f"CoinGlass 網路請求失敗（可能暫時性，稍後再試）: {e.__class__.__name__}"}

    user = resp.headers.get("user")
    v = resp.headers.get("v")
    if not user or not v:
        # 無加密標頭 = 明文回應（或被限流/維護擋下的錯誤信封）
        try:
            data = resp.json()
        except ValueError:
            return {"error": "CoinGlass 回應非預期格式（非 JSON）"}
        # 業務層錯誤信封（如 {"success":false,"code":"...","msg":"..."}) 沒有 'error' 鍵，
        # 不攔會被誤當有效數據 → 讓 drift canary 假『健康』。攔成錯誤（非解密漂移，多為限流/維護）。
        if isinstance(data, dict) and (data.get("success") is False or
                (("code" in data or "msg" in data) and "data" not in data)):
            return {"error": f"CoinGlass 回應錯誤信封（疑似限流/維護）：code={data.get('code')} msg={data.get('msg')}",
                    "drift_suspected": False}
        return data

    # 2) 解密階段：請求成功但解密失敗 = AES key/回應格式『漂移』，需維護（非暫時性）
    try:
        return _decrypt_payload(resp.text, user, v, url)
    except Exception as e:  # noqa: BLE001
        logger.error(f"⚠️ CoinGlass 解密失敗（疑似 AES key/格式漂移，需更新逆向邏輯）: {url} | {e}")
        return {
            "error": "CoinGlass 解密失敗：疑似其加密金鑰或回應格式已變更，此獨家數據暫時無法取得（需更新抓取邏輯，非暫時性錯誤）。",
            "drift_suspected": True,
        }


def coinglass_health() -> Dict[str, Any]:
    """
    漂移偵測 canary：實際打一個獨家端點，確認 CoinGlass 解密是否仍正常。
    可於啟動或定期呼叫，讓 AES key 被換時能『主動察覺』而非等使用者踩到。
    回傳 {ok, drift_suspected, detail}。
    """
    res = get_coinglass_home_stats()
    if isinstance(res, dict) and res.get("error"):
        return {"ok": False, "drift_suspected": bool(res.get("drift_suspected")),
                "detail": res["error"]}
    return {"ok": True, "drift_suspected": False, "detail": "CoinGlass 獨家數據解密正常"}

# ──────────────────────────────────────────────
#  免 Key 工具接口 (LLM Tools)
# ──────────────────────────────────────────────

def get_coinglass_liquidation_chart(symbol: str, interval: str = "1h") -> Any:
    """
    【LLM Tool】獲取特定代幣的歷史爆倉數據（多/空拆分，用於繪製爆倉走勢圖）。
    （治本：改用 Coinalyze 免費層跨 ~25 所彙整爆倉，取代脆弱的 CoinGlass AES 逆向抓取。
      需一次性免費註冊 COINALYZE_API_KEY。）

    Args:
        symbol: 代幣符號，例如 'BTC', 'ETH'
        interval: 時間間隔，可選：'1h', '4h', '12h', '1d'
    """
    from skills.derivatives.coinalyze_client import get_coinalyze_liquidations
    try:
        return get_coinalyze_liquidations(symbol, interval=interval, limit=48)
    except EnvironmentError as e:
        return {"error": str(e), "needs_free_key": True,
                "hint": "爆倉數據改用免費的 Coinalyze，請一次性註冊免費金鑰後即可取得。"}
    except Exception as e:  # noqa: BLE001
        logger.error(f"Coinalyze 爆倉抓取失敗: {e}")
        return {"error": f"爆倉數據抓取失敗: {e.__class__.__name__}: {str(e)[:80]}"}

def get_coinglass_open_interest_info(symbol: str) -> Any:
    """
    【LLM Tool】獲取特定代幣在各大合約交易所的持倉分佈數據 (Open Interest)。
    （治本：改用直連 Binance/Bybit/OKX 的免費彙整持倉量，取代脆弱的 CoinGlass AES 逆向抓取。）

    Args:
        symbol: 代幣符號，例如 'BTC', 'ETH'
    """
    from skills.derivatives.multi_exchange import get_aggregated_open_interest
    sym = symbol.upper().split("/")[0]
    try:
        agg = get_aggregated_open_interest(f"{sym}/USDT")
    except Exception as e:  # noqa: BLE001
        logger.error(f"持倉分佈彙整失敗: {e}")
        return {"error": f"持倉分佈抓取失敗（交易所無回應）: {e.__class__.__name__}"}
    # 對齊舊 CoinGlass 回傳（list of {exchangeName, openInterest}）
    out: List[Dict[str, Any]] = []
    for ex_name, ex_data in (agg.get("by_exchange") or {}).items():
        if isinstance(ex_data, dict) and "error" not in ex_data:
            out.append({
                "exchangeName": ex_name,
                "openInterest": ex_data.get("open_interest"),
                "unit": ex_data.get("unit"),
            })
    if not out:
        return {"error": "持倉分佈暫無有效數據（各交易所皆無回應）。"}
    out.sort(key=lambda x: (x.get("openInterest") or 0), reverse=True)
    return out

def get_coinglass_home_stats() -> Any:
    """
    【LLM Tool】獲取全球加密衍生品大盤宏觀指標 (總市值/主導度、總持倉量、總成交額、多空比率、恐懼貪婪、24h總爆倉)。
    （治本：改用免費來源聚合，取代脆弱的 CoinGlass AES 逆向抓取——CoinGecko /global 與 /derivatives/exchanges、
      Binance 多空比、alternative.me 恐懼貪婪、Coinalyze 爆倉；逐腳降級。）
    """
    from skills.market_data.market_overview import get_global_derivatives_overview
    try:
        return get_global_derivatives_overview()
    except Exception as e:  # noqa: BLE001
        logger.error(f"大盤總覽聚合失敗: {e}")
        return {"error": f"大盤總覽聚合失敗: {e.__class__.__name__}: {str(e)[:80]}"}

def get_coinglass_ahr999() -> Any:
    """
    【LLM Tool】獲取 AHR999 比特幣囤幣與逃頂指標的最新值與歷史數據。
    （治本：改由 CoinGecko 價格『本地計算』，公式固定、已對比 CoinGlass 驗證一致，
    不再依賴脆弱的 AES 逆向抓取。）
    """
    from skills.market_data.onchain_indicators import get_ahr999_local
    try:
        data = get_ahr999_local(output_days=90)
    except Exception as e:  # noqa: BLE001
        logger.error(f"AHR999 本地計算失敗: {e}")
        return {"error": f"AHR999 計算失敗（價格來源無回應）: {e.__class__.__name__}"}
    if not data:
        return {"error": "AHR999 計算無資料"}
    return {
        "list": data,
        "latest_ahr999": data[-1]["ahr999"],
        "latest_price": data[-1]["value"],
        "source": "本地計算 (CoinGecko 日線價格)",
        "guide": "AHR999 < 0.45 為抄底區、> 3.0 為逃頂區、0.45~1.2 為定投區間",
    }

def get_coinglass_altcoin_season() -> Any:
    """
    【LLM Tool】獲取山寨幣季節指數 (Altcoin Season Index)。
    （治本：改由 CoinGecko 前 100 大幣種 90 日漲跌『本地計算』，不再依賴脆弱的 AES 逆向抓取。
      指數 >75 為山寨季、<25 為比特幣季。）
    """
    from skills.market_data.onchain_indicators import get_altcoin_season_local
    try:
        return get_altcoin_season_local(top_n=100, window_days=90)
    except Exception as e:  # noqa: BLE001
        logger.error(f"山寨季指數本地計算失敗: {e}")
        return {"error": f"山寨季指數計算失敗（價格來源無回應）: {e.__class__.__name__}"}

def get_coinglass_mayer_multiple() -> Any:
    """
    【LLM Tool】獲取梅耶乘數 (Mayer Multiple = 現價/200日均線) 的最新值與歷史數據。
    （治本：改由 CoinGecko 價格『本地計算』，不再依賴脆弱的 AES 逆向抓取。）
    """
    from skills.market_data.onchain_indicators import get_mayer_multiple_local
    try:
        data = get_mayer_multiple_local(output_days=90)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Mayer Multiple 本地計算失敗: {e}")
        return {"error": f"Mayer 計算失敗（價格來源無回應）: {e.__class__.__name__}"}
    return data if data else {"error": "Mayer 計算無資料"}

def get_coinglass_etf_flow(asset: str = "BTC") -> Any:
    """
    【LLM Tool】獲取美國現貨 BTC/ETH ETF 每日資金流入流出與統計。
    （治本：改用第一方官方 SoSoValue OpenAPI + 本地每日快照，取代脆弱的 CoinGlass AES 逆向抓取。
      需一次性免費註冊 SOSOVALUE_API_KEY。）

    Args:
        asset: 'BTC' 或 'ETH'
    """
    from skills.market_intel.etf_flow import get_etf_flows
    try:
        return get_etf_flows(asset)
    except Exception as e:  # noqa: BLE001
        logger.error(f"ETF flow 抓取失敗: {e}")
        return {"error": f"ETF flow 抓取失敗: {e.__class__.__name__}: {str(e)[:80]}"}

def get_coinglass_grayscale_stats() -> Any:
    """
    【LLM Tool】獲取灰度信託 (Grayscale Trust) 溢價/折價與 NAV 估算。
    （治本：改用本地計算——Yahoo 市價 × CoinGecko 現貨 × SEC 種子每股持幣 × 費率衰減，
      取代脆弱的 CoinGlass AES 逆向抓取。旗艦 GBTC/ETHE 已轉 ETF 溢價≈0；封閉式 OTC 才有 alpha。）
    """
    from skills.market_data.grayscale import get_grayscale_premiums
    try:
        return get_grayscale_premiums()
    except Exception as e:  # noqa: BLE001
        logger.error(f"灰度溢價計算失敗: {e}")
        return {"error": f"灰度溢價計算失敗: {e.__class__.__name__}: {str(e)[:80]}"}

def get_coinglass_liquidation_heatmap(symbol: str, range: str = "3d") -> Any:
    """
    【LLM Tool】獲取 CoinGlass 爆倉地圖/爆倉熱力圖 (Liquidation Heatmap) 歷史數據與持倉群落。
    包含：
      - prices: 歷史 OHLCV 價格 K 線數據。
      - data: 爆倉集中價位群落 (價格、多空 side、累積強度 size 等)。
    """
    from skills.market_data.liquidation_heatmap import get_liquidation_heatmap_local
    # range → (K 線週期, 回溯根數)
    r = (range or "3d").lower()
    span_map = {"3d": ("1h", 72), "7d": ("4h", 42), "30d": ("1d", 30)}
    period, lookback = span_map.get(r, ("1h", 72))
    coin = symbol.split("_")[-1].replace("USDT", "") if "_" in symbol else symbol
    try:
        return get_liquidation_heatmap_local(coin, period=period, lookback=lookback)
    except Exception as e:  # noqa: BLE001
        logger.error(f"爆倉熱力圖本地計算失敗: {e}")
        return {"error": f"爆倉熱力圖計算失敗: {e.__class__.__name__}: {str(e)[:80]}"}



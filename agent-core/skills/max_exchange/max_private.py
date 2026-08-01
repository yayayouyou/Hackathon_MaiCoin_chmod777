"""
skills/max_exchange/max_private.py

MAX 交易所私有帳戶 API 封裝
=============================================
提供以下需要 API Key 的帳戶與交易歷史函數：
  - get_max_member_info    : 獲取會員個人資訊
  - get_max_accounts       : 獲取帳戶餘額列表
  - get_max_orders         : 獲取當前未平倉/歷史掛單
  - get_max_order_history  : 獲取歷史掛單 (可篩選)
  - get_max_my_trades      : 獲取個人交易歷史記錄
  - get_max_deposits       : 獲取充值/入金歷史
  - get_max_withdrawals    : 獲取提現/出金歷史
"""

import os
import time
import json
import base64
import hmac
import hashlib
import threading
import requests  # 保留供 requests.exceptions 使用
from typing import Optional, List, Dict, Any
from loguru import logger
from dotenv import load_dotenv

from skills._http import session_get, session_post, session_delete

load_dotenv()

MAX_API_BASE_URL = "https://max-api.maicoin.com"

# 單調遞增 nonce：同一毫秒送兩筆簽名請求時，int(time*1000) 會碰撞而被 MAX 以
# 「nonce 未遞增」拒絕。改用 max(now_ms, last+1) 保證嚴格遞增。
_nonce_lock = threading.Lock()
_last_nonce = 0


def _next_nonce() -> int:
    global _last_nonce
    with _nonce_lock:
        n = max(int(time.time() * 1000), _last_nonce + 1)
        _last_nonce = n
        return n

def _normalize_market_id(market: str) -> str:
    """將交易對名稱轉換為 MAX 格式（小寫、去斜線，例如 BTC/TWD -> btctwd）"""
    return market.replace("/", "").replace("_", "").lower()

def _max_private_request(endpoint: str, params: Optional[Dict[str, Any]] = None, method: str = "GET") -> Any:
    """
    執行 MAX 私有 API 請求（自動處理 HMAC-SHA256 簽名與 payload 編碼，支援 GET/POST/DELETE）。
    """
    access_key = os.getenv("MAX_API_KEY", "")
    secret_key = os.getenv("MAX_API_SECRET", "")
    
    if not access_key or not secret_key:
        raise EnvironmentError(
            "MAX_API_KEY 或 MAX_API_SECRET 未設定！請在 .env 文件中填入你的 MAX API 金鑰。\n"
            "申請地址：https://max.maicoin.com/apikeys"
        )
    
    # 建立基礎請求參數（含 nonce）
    req_params = params.copy() if params else {}
    req_params["nonce"] = _next_nonce()
    
    # 簽名 payload 必須包含 endpoint path 資訊
    params_to_sign = {**req_params, "path": endpoint}
    
    # Base64 編碼
    payload_json = json.dumps(params_to_sign)
    payload_base64 = base64.b64encode(payload_json.encode("utf-8")).decode("utf-8")
    
    # HMAC-SHA256 簽名
    signature = hmac.new(
        secret_key.encode("utf-8"),
        payload_base64.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    
    headers = {
        "X-MAX-ACCESSKEY": access_key,
        "X-MAX-PAYLOAD": payload_base64,
        "X-MAX-SIGNATURE": signature,
        "Content-Type": "application/json"
    }
    
    url = f"{MAX_API_BASE_URL}{endpoint}"
    logger.debug(f"MAX 私有 API 請求: {url} method: {method} params: {req_params}")
    
    try:
        method_upper = method.upper()
        if method_upper == "GET":
            resp = session_get(url, params=req_params, headers=headers)
        elif method_upper == "POST":
            # For POST requests, parameters are sent in the JSON body
            resp = session_post(url, json=req_params, headers=headers)
        elif method_upper == "DELETE":
            resp = session_delete(url, json=req_params, headers=headers)
        else:
            raise ValueError(f"不支援的 HTTP 方法: {method}")
            
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"MAX API 請求失敗: {e}")
        # 如果有詳細的錯誤返回，嘗試讀取
        try:
            err_detail = e.response.json()
            error_msg = f"MAX API 業務錯誤: {err_detail.get('error', {}).get('message', str(e))}"
        except Exception:
            error_msg = f"MAX API 請求異常: {e}"
        raise RuntimeError(error_msg)

def get_max_member_info() -> Dict[str, Any]:
    """
    【LLM Tool】獲取帳戶會員資訊，並「明確區分兩種等級」避免混淆：
      - account_kyc_level：身份驗證等級（Lv1-3，決定提領額度等，與手續費無關）
      - vip_tier         ：VIP 交易等級（這才決定手續費 maker/taker 費率）
    另回傳目前費率(%) 與升到下一級的門檻與屆時費率。
    """
    raw = _max_private_request("/api/v3/info")
    if not isinstance(raw, dict) or "error" in raw:
        return raw

    def _pct(x):
        try:
            return round(float(x) * 100, 4)   # 0.0008 → 0.08(%)
        except (TypeError, ValueError):
            return None

    cur = raw.get("current_vip_level") or {}
    nxt = raw.get("next_vip_level") or {}
    out: Dict[str, Any] = {
        "account_kyc_level": raw.get("level"),   # 身份驗證等級（非 VIP、與手續費無關）
        "vip_tier": cur.get("level"),            # VIP 交易等級（決定手續費）
        "maker_fee_pct": _pct(cur.get("maker_fee")),
        "taker_fee_pct": _pct(cur.get("taker_fee")),
    }
    if raw.get("email"):
        out["email"] = raw["email"]
    if nxt:
        out["next_vip_tier"] = nxt.get("level")
        out["next_vip_requirements"] = {
            "min_trading_volume": nxt.get("minimum_trading_volume"),
            "min_staking_volume": nxt.get("minimum_staking_volume"),
            "maker_fee_pct": _pct(nxt.get("maker_fee")),
            "taker_fee_pct": _pct(nxt.get("taker_fee")),
        }
    return out

def get_max_accounts(wallet_type: str = "spot") -> List[Dict[str, Any]]:
    """
    【LLM Tool】獲取指定錢包所有資產的餘額列表（僅返回餘額大於 0.000001 的幣種，精簡數據）。

    Args:
        wallet_type: 'spot'（現貨，預設）或 'm'（融資 M-Wallet）。
                     M-Wallet 另含 principal（融資本金）/ interest（應計利息）欄位。
    """
    wt = (wallet_type or "spot").lower()
    if wt not in ("spot", "m"):
        wt = "spot"
    raw_balances = _max_private_request(f"/api/v3/wallet/{wt}/accounts")
    if not isinstance(raw_balances, list):
        return []

    # 過濾小額或零餘額，節省 Token
    balances = []
    for asset in raw_balances:
        balance = float(asset.get("balance", 0.0) or 0.0)
        locked = float(asset.get("locked", 0.0) or 0.0)
        staked = float(asset.get("staked", 0.0) or 0.0)
        principal = float(asset.get("principal", 0.0) or 0.0)   # 融資本金（現貨恆 0）
        interest = float(asset.get("interest", 0.0) or 0.0)     # 應計利息（現貨恆 0）
        if any(v > 0.000001 for v in (balance, locked, staked, principal, interest)):
            row = {
                "currency": asset.get("currency", "").upper(),
                "balance": balance,     # 可動用
                "locked": locked,       # 掛單凍結
                "staked": staked,       # 質押中
                "total": balance + locked + staked,
            }
            if wt == "m":               # 融資錢包才帶借貸欄位
                row["principal"] = principal
                row["interest"] = interest
            balances.append(row)
    return balances


def get_max_ad_ratio() -> Dict[str, Any]:
    """
    【LLM Tool】獲取融資 M-Wallet 的「調整後負債比 (AD ratio)」與資產/負債（USDT 計價），
    用於評估融資帳戶的維持率/清算風險。無融資部位時 ad_ratio 會是很大的哨兵值（如 999）。
    回傳: {ad_ratio, asset_in_usdt, debt_in_usdt}
    """
    raw = _max_private_request("/api/v3/wallet/m/ad_ratio")
    if not isinstance(raw, dict):
        return {}
    def _f(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None
    return {
        "ad_ratio": _f(raw.get("ad_ratio")),
        "asset_in_usdt": _f(raw.get("asset_in_usdt")),
        "debt_in_usdt": _f(raw.get("debt_in_usdt")),
    }

def get_max_orders(market: Optional[str] = None, state: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """
    【LLM Tool】獲取掛單清單。MAX v3 已將訂單拆分為「未成交(open)」與「歷史(history)」兩個端點。

    Args:
        market: 選填。交易對符號，例如 'BTC/TWD'
        state: 選填。'wait'/None → 未成交掛單(open)；'done'/'cancel'/'finished' → 歷史訂單(history)
        limit: 返回訂單筆數，預設 20
    """
    finished_states = {"done", "cancel", "canceled", "finished", "convert"}
    if state and state.lower() in finished_states:
        return get_max_order_history(market=market, limit=limit)

    # 未成交掛單
    params: Dict[str, Any] = {}
    if market:
        params["market"] = _normalize_market_id(market)
    return _max_private_request("/api/v3/wallet/spot/orders/open", params)

def get_max_order(order_id: Optional[int] = None, client_oid: Optional[str] = None) -> Dict[str, Any]:
    """
    【LLM Tool】依 id 或自訂委託編號 (client_oid) 查詢「單一」訂單的最新狀態。

    Args:
        order_id: MAX 訂單 id
        client_oid: 下單時帶入的自訂委託編號
    """
    params: Dict[str, Any] = {}
    if order_id is not None:
        params["id"] = order_id
    if client_oid is not None:
        params["client_oid"] = client_oid
    return _max_private_request("/api/v3/order", params)

def get_max_order_history(market: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """
    【LLM Tool】獲取帳戶的歷史訂單記錄（已成交/已撤銷）。

    Args:
        market: 選填。交易對符號，例如 'BTC/TWD'
        limit: 返回記錄筆數，預設 50
    """
    params: Dict[str, Any] = {"limit": limit}
    if market:
        params["market"] = _normalize_market_id(market)
    return _max_private_request("/api/v3/wallet/spot/orders/history", params)

def get_max_my_trades(market: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """
    【LLM Tool】獲取帳戶現貨個人成交歷史記錄（My Trades）。

    Args:
        market: 選填。交易對符號，例如 'BTC/TWD'
        limit: 返回記錄筆數，預設 50
    """
    params: Dict[str, Any] = {"limit": limit}
    if market:
        params["market"] = _normalize_market_id(market)
    return _max_private_request("/api/v3/wallet/spot/trades", params)

def get_max_deposits(currency: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """
    【LLM Tool】獲取帳戶的法幣或加密貨幣入金/充值歷史記錄。
    
    Args:
        currency: 選填。幣種代碼，例如 'TWD', 'USDT', 'BTC'
        limit: 返回記錄筆數，預設 20
    """
    params = {"limit": limit}
    if currency:
        params["currency"] = currency.lower()
    return _max_private_request("/api/v3/deposits", params)

def get_max_withdrawals(currency: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """
    【LLM Tool】獲取帳戶的法幣或加密貨幣出金/提現歷史記錄。
    
    Args:
        currency: 選填。幣種代碼，例如 'TWD', 'USDT', 'BTC'
        limit: 返回記錄筆數，預設 20
    """
    params = {"limit": limit}
    if currency:
        params["currency"] = currency.lower()
    return _max_private_request("/api/v3/withdrawals", params)

# ──────────────────────────────────────────────
#  個人帳戶資訊：資金流水 / 閃兌 / 提幣白名單 / 站內轉帳（皆唯讀）
# ──────────────────────────────────────────────

def _to_float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _norm_ts_ms(ts):
    """MAX 各端點混用秒/毫秒時間戳，統一成毫秒（供前端一致格式化）。"""
    try:
        v = int(ts)
    except (TypeError, ValueError):
        return None
    return v * 1000 if v < 1_000_000_000_000 else v   # 10 位=秒 → 補成毫秒


def get_max_fund_transactions(kind: str = "deposit", currency: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """
    【LLM Tool】獲取資金異動記錄（比 get_max_deposits/withdrawals 更完整：含是否站內 is_internal、
    區塊鏈網路、txid、提幣手續費、對方地址）。
    kind: 'deposit' 入金 / 'withdrawal' 出金 / 'transfer' 錢包互轉（現貨↔融資）。
    """
    k = (kind or "deposit").lower().rstrip("s")
    if k not in ("deposit", "withdrawal", "transfer"):
        k = "deposit"
    raw = _max_private_request(f"/api/v3/fund_transactions/{k}s", {"limit": limit})
    out: List[Dict[str, Any]] = []
    for x in (raw if isinstance(raw, list) else []):
        cur = str(x.get("currency", "")).upper()
        if currency and cur != currency.upper():
            continue
        rec: Dict[str, Any] = {
            "type": k, "sn": x.get("sn"), "currency": cur,
            "amount": _to_float(x.get("amount")), "state": x.get("state"),
            "time_ms": _norm_ts_ms(x.get("created_at")), "is_internal": x.get("is_internal"),
        }
        if k == "transfer":
            fr, to = x.get("from") or {}, x.get("to") or {}
            rec["from"] = fr.get("wallet_type") if isinstance(fr, dict) else fr
            rec["to"] = to.get("wallet_type") if isinstance(to, dict) else to
        else:
            rec["network"] = x.get("network_protocol")
            rec["txid"] = x.get("txid")
            if k == "withdrawal":
                rec["fee"] = _to_float(x.get("fee"))
                rec["fee_currency"] = (str(x.get("fee_currency") or "").upper() or None)
                rec["to_address"] = x.get("to") or x.get("to_address")
                rec["label"] = x.get("label")
            else:
                rec["from"] = x.get("from")
        out.append(rec)
    return out


def get_max_converts(currency: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """【LLM Tool】獲取閃兌(convert)歷史：從哪個幣換到哪個幣、數量、手續費（含 TWD 計價）。currency 選填（比對來源或目標幣）。"""
    raw = _max_private_request("/api/v3/converts", {"limit": limit})
    out: List[Dict[str, Any]] = []
    for x in (raw if isinstance(raw, list) else []):
        fc, tc = str(x.get("from_currency", "")).upper(), str(x.get("to_currency", "")).upper()
        if currency and currency.upper() not in (fc, tc):
            continue
        out.append({
            "sn": x.get("sn"), "from_currency": fc, "from_amount": _to_float(x.get("from_amount")),
            "to_currency": tc, "to_amount": _to_float(x.get("to_amount")),
            "fee": _to_float(x.get("fee")), "fee_currency": (str(x.get("fee_currency") or "").upper() or None),
            "fee_in_twd": _to_float(x.get("fee_in_twd")), "time_ms": _norm_ts_ms(x.get("created_at")),
        })
    return out


def get_max_withdraw_addresses(currency: str, limit: int = 50) -> List[Dict[str, Any]]:
    """【LLM Tool】獲取指定幣種的提幣白名單地址（含備註標籤 extra_label、鏈別、是否站內）。currency 必填（如 'USDT'）。"""
    if not currency:
        return []
    raw = _max_private_request("/api/v3/withdraw_addresses", {"currency": currency.lower(), "limit": limit})
    out: List[Dict[str, Any]] = []
    for x in (raw if isinstance(raw, list) else []):
        out.append({
            "currency": str(x.get("currency", "")).upper(),
            "network": x.get("network_protocol"),
            "address": x.get("address"),
            "label": x.get("extra_label"),
            "is_internal": x.get("is_internal"),
            "time_ms": _norm_ts_ms(x.get("created_at")),
        })
    return out


def get_max_internal_transfers(side: str = "in", currency: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """【LLM Tool】獲取站內轉帳記錄（MAX 用戶之間）。side: 'in' 轉入 / 'out' 轉出（必填）。currency 選填。"""
    s = (side or "in").lower()
    if s not in ("in", "out"):
        s = "in"
    params: Dict[str, Any] = {"side": s, "limit": limit}
    if currency:
        params["currency"] = currency.lower()
    raw = _max_private_request("/api/v3/internal_transfers", params)
    out: List[Dict[str, Any]] = []
    for x in (raw if isinstance(raw, list) else []):
        out.append({
            "side": s, "uuid": x.get("uuid"), "currency": str(x.get("currency", "")).upper(),
            "amount": _to_float(x.get("amount")), "from": x.get("from"), "to": x.get("to"),
            "state": x.get("state"), "time_ms": _norm_ts_ms(x.get("created_at")),
        })
    return out


# ──────────────────────────────────────────────
#  下單與撤單原始 API 接口 (供 order_executor 調用)
# ──────────────────────────────────────────────

def _create_max_order_raw(
    market: str,
    side: str,
    volume: float,
    price: Optional[float] = None,
    ord_type: str = "limit",
    client_oid: Optional[str] = None,
) -> Dict[str, Any]:
    """
    執行 MAX 現貨下單請求 (無風控校驗，底層使用，由 order_executor 包裝)。
    v3 端點：POST /api/v3/wallet/spot/orders
    """
    market_id = _normalize_market_id(market)
    params: Dict[str, Any] = {
        "market": market_id,
        "side": side.lower(),
        "volume": str(volume),
        "ord_type": ord_type.lower()
    }
    if ord_type.lower() == "limit" and price is not None:
        params["price"] = str(price)
    if client_oid:
        params["client_oid"] = client_oid

    return _max_private_request("/api/v3/wallet/spot/orders", params, method="POST")

def _cancel_max_order_raw(order_id: Optional[int] = None, client_oid: Optional[str] = None) -> Dict[str, Any]:
    """
    執行 MAX 單筆撤單請求。v3 端點：DELETE /api/v3/order（依 id 或 client_oid）。
    """
    params: Dict[str, Any] = {}
    if order_id is not None:
        params["id"] = order_id
    if client_oid is not None:
        params["client_oid"] = client_oid
    return _max_private_request("/api/v3/order", params, method="DELETE")

def _cancel_all_max_orders_raw(market: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    執行 MAX 撤銷所有現貨活動訂單請求。v3 端點：DELETE /api/v3/wallet/spot/orders。
    """
    params: Dict[str, Any] = {}
    if market:
        params["market"] = _normalize_market_id(market)
    return _max_private_request("/api/v3/wallet/spot/orders", params, method="DELETE")

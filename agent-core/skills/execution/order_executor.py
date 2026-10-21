"""
skills/execution/order_executor.py

交易執行模組 — 包裝物理安全風控鎖
=============================================
提供以下交易下單/撤單 LLM Tool 函數：
  - create_order       : 下單執行（在調用底層 API 前，強制進行 risk_guard 物理風控校驗）
  - cancel_order       : 撤銷單筆訂單
  - cancel_all_orders  : 撤銷所有活動訂單
"""

import math
import os
import time
import uuid
import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from loguru import logger
from dotenv import load_dotenv

from skills.execution.risk_guard import validate_order, is_limit_like
from skills.execution import live_guard
from skills.max_exchange.max_public import get_max_tickers, get_max_market_rules
from skills.max_exchange.max_private import (
    _create_max_order_raw,
    _cancel_max_order_raw,
    _cancel_all_max_orders_raw
)

load_dotenv()

# 模擬盤手續費率（與 backtester 一致）
PAPER_FEE_RATE = 0.001


def get_risk_mode() -> str:
    """
    回傳目前交易模式：'paper'(模擬盤，預設) 或 'live'(實盤)。
    為安全預設，只有在環境變數明確設為 'live' 時才會送出真實訂單。
    """
    mode = os.getenv("RISK_MODE", "paper").strip().lower()
    return "live" if mode == "live" else "paper"


def prepare_and_validate_order(
    market: str,
    side: str,
    volume: float,
    price: Optional[float],
    ord_type: str
) -> Dict[str, Any]:
    """
    下單前置作業：查詢最新報價（修正 MAX ticker 為扁平 dict 的解析）並執行硬編碼物理風控鎖校驗。

    回傳：
      成功 -> {"ok": True, "latest_price": float}
      失敗 -> {"ok": False, "response": {...}}  （response 為要直接回給呼叫端的錯誤/攔截結果）
    """
    side_lower = side.lower()
    ord_type_lower = ord_type.lower()

    # 1. 查詢最新報價。get_max_tickers(market) 回傳「扁平的單一 ticker dict」
    #    （欄位含 last/buy/sell），或 {"error": ...}。切勿當成 {market: {...}} 巢狀結構。
    try:
        ticker_data = get_max_tickers(market)
    except Exception as e:
        logger.error(f"下單風控前查詢報價失敗: {e}")
        return {"ok": False, "response": {"error": f"下單失敗。無法獲取 {market} 的最新報價以進行安全校驗: {e}"}}

    if not isinstance(ticker_data, dict) or ticker_data.get("error"):
        err = ticker_data.get("error") if isinstance(ticker_data, dict) else "回傳格式異常"
        return {"ok": False, "response": {"error": f"下單失敗。無法獲取 {market} 的最新報價：{err}"}}

    def _to_float(val: Any) -> float:
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0.0

    latest_price = _to_float(ticker_data.get("last"))
    if latest_price <= 0.0:
        # 降級使用買一/賣一中位數
        buy_p = _to_float(ticker_data.get("buy"))
        sell_p = _to_float(ticker_data.get("sell"))
        if buy_p > 0 and sell_p > 0:
            latest_price = (buy_p + sell_p) / 2.0

    if latest_price <= 0.0:
        return {"ok": False, "response": {"error": f"下單失敗。無法獲取 {market} 的有效市場最新價格。"}}

    # 2. 進行底層硬編碼物理風控鎖校驗
    price_to_validate = price if price is not None else latest_price
    passed, reason = validate_order(
        market=market,
        side=side_lower,
        volume=volume,
        price=price_to_validate,
        ord_type=ord_type_lower,
        latest_ticker_price=latest_price
    )

    if not passed:
        logger.warning(f"交易遭風控鎖攔截！原因: {reason}")
        return {
            "ok": False,
            "response": {
                "status": "REJECTED_BY_RISK_GUARD",
                "reason": reason,
                "details": {
                    "market": market,
                    "side": side,
                    "volume": volume,
                    "price": price,
                    "latest_market_price": latest_price
                }
            }
        }

    # 3. 交易所最低下單量（MAX 逐交易對規定 min_base_amount 與 min_quote_amount）。
    #    低於門檻送出去也只會被 MAX 退件；先擋下並算出「最少要下多少」，模型才不會自己亂猜門檻。
    #    規格查不到（網路/新幣）就不擋 —— 這只是提早告知，真正的把關在交易所。
    try:
        rules = get_max_market_rules(market)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"查詢 {market} 最低下單量失敗，略過此檢查: {e}")
        rules = None
    if rules:
        min_base = _to_float(rules.get("min_base_amount"))
        min_quote = _to_float(rules.get("min_quote_amount"))
        notional = volume * price_to_validate
        if volume < min_base or notional < min_quote:
            precision = int(rules.get("base_precision") or 8)
            step = 10 ** -precision
            min_volume = max(min_base, min_quote / price_to_validate)
            min_volume = math.ceil(min_volume / step - 1e-9) * step
            base_u = str(rules.get("base_unit") or "").upper()
            quote_u = str(rules.get("quote_unit") or "").upper()
            reason = (f"低於 MAX 最低下單量：{market} 每筆至少 {min_base:g} {base_u} 且金額至少 "
                      f"{min_quote:g} {quote_u}。這筆是 {volume:g} {base_u} ≈ {notional:,.1f} {quote_u}；"
                      f"以委託價 {price_to_validate:,.1f} 計，最少要下 {min_volume:.{precision}f} {base_u}"
                      f"（≈ {min_volume * price_to_validate:,.0f} {quote_u}）。")
            logger.warning(reason)
            return {
                "ok": False,
                "response": {
                    "status": "REJECTED_BELOW_EXCHANGE_MINIMUM",
                    "reason": reason,
                    "details": {
                        "market": market,
                        "side": side,
                        "volume": volume,
                        "price": price,
                        "min_volume": round(min_volume, precision),
                        "min_notional": round(min_volume * price_to_validate, 2),
                        "latest_market_price": latest_price
                    }
                }
            }

    return {"ok": True, "latest_price": latest_price}


def _simulate_fill(
    market: str,
    side: str,
    volume: float,
    price: Optional[float],
    ord_type: str,
    latest_price: float
) -> Dict[str, Any]:
    """
    模擬盤 (paper) 撮合：不呼叫真實 MAX API，以最新價/委託價成交並套用手續費。
    回傳與實盤相同的 {"status": "SUCCESS", "order": {...}} 結構，讓下游程式對模式無感。
    """
    ord_type_lower = ord_type.lower()
    fill_price = price if (is_limit_like(ord_type_lower) and price is not None) else latest_price
    market_id = market.replace("/", "").replace("_", "").lower()
    side_lower = side.lower()
    now = datetime.now(timezone.utc).isoformat()

    # ── post_only 的模擬必須忠實，否則模擬盤會給出誤導的結果 ──
    #
    # post_only 的全部意義就是「不要立刻成交」。如果模擬盤照樣回「已成交」，
    # 使用者在 paper 測試時會以為單子成交了 —— 而實盤的同一筆要嘛掛在簿上等、
    # 要嘛被交易所整筆拒絕。那是最糟的一種模擬：讓人對真實行為建立錯誤的預期。
    #
    # 用 latest_price 當最佳買/賣價的近似（模擬盤不查訂單簿）。真實判定以
    # 對手方掛單為準，所以邊界附近的結果可能與實盤不同 —— 但方向是對的。
    if ord_type_lower == "post_only":
        crosses = (side_lower == "buy" and fill_price >= latest_price) or \
                  (side_lower == "sell" and fill_price <= latest_price)
        if crosses:
            logger.info(f"[PAPER] post_only 會立即成交 → 模擬交易所拒單：{side_lower} {volume} @ {fill_price}")
            return {
                "status": "REJECTED_POST_ONLY",
                "mode": "paper",
                "reason": (f"只掛單（post_only）遭拒：委託價 {fill_price} 會與市價 {latest_price} "
                           f"立即成交。買單要低於市價、賣單要高於市價才掛得上去。"),
                "order": {"market": market_id, "side": side_lower, "ord_type": ord_type_lower,
                          "volume": volume, "price": fill_price, "state": "cancel",
                          "simulated": True, "created_at": now},
            }
        # 掛得上去：狀態是「等待成交」，不是「已成交」。手續費要等真的成交才發生。
        logger.info(f"[PAPER] 模擬掛單（post_only，未成交）：{side_lower} {volume} @ {fill_price} ({market_id})")
        return {
            "status": "SUCCESS",
            "mode": "paper",
            "order": {
                "id": f"paper-{uuid.uuid4().hex[:12]}",
                "market": market_id, "side": side_lower, "ord_type": ord_type_lower,
                "volume": volume, "executed_volume": 0, "remaining_volume": volume,
                "price": fill_price, "avg_price": None,
                "notional": volume * fill_price, "fee": 0,
                "state": "wait", "simulated": True, "created_at": now,
            },
        }

    # limit / market 維持原本的「立刻全額成交」模擬。
    # （limit 其實也可能掛著不成交，但那是既有行為，agent 那側的既有測試依賴它，
    #   不在這一批改動的範圍內。post_only 是新型別，所以從一開始就做對。）
    notional = volume * fill_price
    fee = notional * PAPER_FEE_RATE
    order = {
        "id": f"paper-{uuid.uuid4().hex[:12]}",
        "market": market_id,
        "side": side_lower,
        "ord_type": ord_type_lower,
        "volume": volume,
        "executed_volume": volume,
        "price": fill_price,
        "avg_price": fill_price,
        "notional": notional,
        "fee": fee,
        "state": "done",
        "simulated": True,
        "created_at": now,
    }
    logger.info(f"[PAPER] 模擬成交：{side_lower} {volume} @ {fill_price} ({market_id})，手續費 {fee:.4f}")
    return {"status": "SUCCESS", "mode": "paper", "order": order}


def create_order(
    exchange_id: str,
    market: str,
    side: str,
    volume: float,
    price: Optional[float] = None,
    ord_type: str = "limit",
    mode: Optional[str] = None,
    client_oid: Optional[str] = None,
) -> Dict[str, Any]:
    """
    【LLM Tool - 交易執行】在指定交易所下單。下單前會自動查詢最新報價並執行硬編碼物理風控鎖安全校驗。

    交易模式由環境變數 RISK_MODE 決定：
      - 'paper' (預設)：模擬撮合，不會送出真實訂單。
      - 'live'         ：通過風控後送出真實 MAX 訂單。

    Args:
        exchange_id: 交易所 ID，目前僅支持現貨交易 'max'
        side: 交易方向，'buy' (買入) 或 'sell' (賣出)
        volume: 下單數量
        price: 限價型委託價格（limit / post_only）。市價單時不需填寫。
        ord_type: 委託類型：
          - 'limit'      限價單
          - 'market'     市價單（立即成交）
          - 'post_only'  只掛單／maker-only：**送出當下就會成交的話，交易所直接
                         拒絕整筆單**。要「掛著等，不要立刻成交」時用它，比自己
                         把限價設遠一點可靠 —— 後者在行情跳動時仍可能被吃掉。
    """
    ex_id_lower = exchange_id.lower()
    if ex_id_lower != "max":
        return {"error": f"下單失敗。目前系統僅支持 'max' 交易所的交易執行，暫不支持 '{exchange_id}'"}

    side_lower = side.lower()
    ord_type_lower = ord_type.lower()

    if is_limit_like(ord_type_lower) and price is None:
        return {"error": f"下單失敗。{ord_type_lower} 必須提供委託價格 (price)。"}

    # 1~2. 查詢報價 + 硬編碼物理風控鎖校驗（已修正 ticker shape）
    prep = prepare_and_validate_order(market, side_lower, volume, price, ord_type_lower)
    if not prep["ok"]:
        return prep["response"]

    latest_price = prep["latest_price"]

    # 3. 交易模式：核准路徑傳入的『凍結 mode』優先於環境變數（防 paper 核准被當 live 執行）；
    #    直接/自動路徑未傳 mode 時才讀環境（安全預設 paper）。
    effective_mode = mode if mode in ("paper", "live") else get_risk_mode()

    # 3.5 實盤總閘門（停止開關 → 授權到期 → 累計曝險）。
    #     只看 RISK_MODE 會漏掉這三者；且核准路徑凍結的 mode 也必須再過一次 ——
    #     核准當下合法不代表送出當下仍合法（可能已按下停止開關或已達累計上限）。
    if effective_mode == "live":
        # 換算名目金額為 TWD 以計算累計曝險。
        # **必須 fail-closed**：算不出金額就不能下單。曾經寫成「失敗以 0 計」，
        # 但 0 是最寬鬆的值 —— 換算一失敗就免費通過累計檢查，等於防線自己開門。
        # quote_convert.notional_to_twd 的契約本來就是「不可安全換算時回 None，
        # 由呼叫端 fail-closed」，這裡遵守它。
        try:
            from skills.execution.quote_convert import notional_to_twd
            notional_twd = notional_to_twd(volume * (price or latest_price), market)
        except Exception as e:  # noqa: BLE001
            logger.error(f"換算 TWD 名目金額時發生例外：{e}")
            notional_twd = None
        if notional_twd is None or notional_twd <= 0:
            msg = (f"風控攔截：無法將 {market} 的名目金額安全換算成 TWD，"
                   "因此無法檢查累計曝險上限。為避免防線失效，實盤下單已擋下。")
            logger.warning(msg)
            live_guard.record_decision("REJECTED_NO_VALUATION", market, side_lower, volume,
                                       price, 0.0, "live", msg)
            return {"status": "REJECTED_BY_LIVE_GUARD", "reason": msg,
                    "details": {"market": market, "side": side, "volume": volume, "price": price}}
        # 帶入凍結模式：核准當下的同意不該被之後改動的 RISK_MODE 改寫，
        # 但三道閘門（停手／授權／累計）一律照樣套用。
        allowed, gate_mode, gate_note = live_guard.preflight(
            market, side_lower, volume, price, notional_twd,
            intended_mode=mode if mode in ("paper", "live") else None)
        if not allowed:
            if gate_mode == "halted":
                logger.warning(f"實盤下單遭閘門攔截：{gate_note}")
                return {"status": "REJECTED_BY_LIVE_GUARD", "reason": gate_note,
                        "details": {"market": market, "side": side, "volume": volume,
                                    "price": price, "notional_twd": round(notional_twd, 2)}}
            # 授權過期/未授權 → 退回模擬盤，並讓使用者知道為什麼
            logger.warning(f"實盤未授權，改以模擬盤執行：{gate_note}")
            sim = _simulate_fill(market, side_lower, volume, price, ord_type_lower, latest_price)
            if isinstance(sim, dict):
                sim["downgraded_from_live"] = gate_note
            return sim
        logger.info(f"實盤閘門通過：{gate_note}")

    if effective_mode == "paper":
        return _simulate_fill(market, side_lower, volume, price, ord_type_lower, latest_price)

    # 實盤：附『冪等鍵』(client_oid)——吞例外後盲目重試時 MAX 可去重，防重複下單。
    # 加 60 秒時間桶：數秒內的重試會夾同一鍵去重；間隔>1 分鐘的『刻意重複單』(DCA/加碼)則放行。
    if not client_oid:
        bucket = int(time.time() // 60)
        raw = f"{market}|{side_lower}|{volume}|{price}|{ord_type_lower}|{effective_mode}|{bucket}"
        client_oid = "ag-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    try:
        order_res = _create_max_order_raw(
            market=market,
            side=side_lower,
            volume=volume,
            price=price,
            ord_type=ord_type_lower,
            client_oid=client_oid,
        )
        logger.info(f"訂單下達成功！OrderID: {order_res.get('id')} (client_oid={client_oid})")
        live_guard.record_decision("SUBMITTED", market, side_lower, volume, price,
                                   notional_twd, "live", order_id=order_res.get("id"),
                                   extra={"client_oid": client_oid})
        return {
            "status": "SUCCESS",
            "mode": "live",
            "order": order_res,
            "client_oid": client_oid,
        }
    except Exception as e:
        # 送出後才發生的異常（逾時等）無法確定訂單是否已成立 → 回 UNKNOWN 而非 FAILED，
        # 避免『以為失敗而盲目重試』造成重複下單；已附冪等鍵，重試亦不會重複。
        logger.error(f"下單執行發生異常（訂單狀態未知）: {e}")
        # 狀態未知＝可能已成立，累計曝險必須把它算進去（偏保守），否則出事時
        # 台帳會少記一筆、上限形同虛設。
        live_guard.record_decision("SUBMITTED", market, side_lower, volume, price,
                                   notional_twd, "live", reason=f"送出後異常，狀態未知：{e}",
                                   extra={"client_oid": client_oid, "uncertain": True})
        return {
            "status": "UNKNOWN",
            "reason": f"下單請求異常，訂單狀態未知（可能已送達交易所）: {str(e)}",
            "advice": "請先查詢該市場的最新訂單/成交狀態，確認未成交後再重試；系統已附冪等鍵，重試不會造成重複單。",
            "client_oid": client_oid,
        }

def cancel_order(exchange_id: str, order_id: int) -> Dict[str, Any]:
    """
    【LLM Tool - 交易執行】撤銷指定交易所的單筆活動訂單。
    
    Args:
        exchange_id: 交易所 ID，目前僅支持 'max'
        order_id: 訂單 ID
    """
    if exchange_id.lower() != "max":
        return {"error": f"撤單失敗。目前僅支持 'max' 交易所，暫不支持 '{exchange_id}'"}
        
    try:
        res = _cancel_max_order_raw(order_id)
        return {
            "status": "SUCCESS",
            "canceled_order": res
        }
    except Exception as e:
        logger.error(f"撤單執行失敗: {e}")
        return {
            "status": "FAILED",
            "reason": str(e)
        }

def cancel_all_orders(exchange_id: str, market: Optional[str] = None,
                      confirm_all_markets: bool = False) -> Dict[str, Any]:
    """
    【LLM Tool - 交易執行】撤銷指定交易所的所有活動訂單。

    Args:
        exchange_id: 交易所 ID，目前僅支持 'max'
        market: 選填。指定僅撤銷特定交易對的掛單，例如 'BTC/TWD'
        confirm_all_markets: 未指定 market 要撤銷『全市場』時的確認旗標，需明確為 True 才放行。
    """
    if exchange_id.lower() != "max":
        return {"error": f"撤銷所有掛單失敗。目前僅支持 'max' 交易所，暫不支持 '{exchange_id}'"}

    from skills.max_exchange.max_private import _normalize_market_id
    m = market.strip() if isinstance(market, str) else ""
    # 用『與底層相同』的正規化判斷是否真的有指定市場，避免 "   "/"/"/"_" 這類正規化後為空的值繞過防呆
    market_norm = _normalize_market_id(m) if m else ""
    # 全帳戶撤單防呆：未指定(或正規化後為空) market 會清掉『所有市場』的掛單（含止損/止盈保護單）；
    # 需明確 confirm_all_markets=True 才放行，避免單一幻覺/注入的呼叫清空整個帳戶。
    if not market_norm and not confirm_all_markets:
        return {"error": "全帳戶撤單防呆：未指定有效 market 將撤銷『所有市場』的所有掛單（含止損/止盈保護單）。"
                         "請指定 market（如 'BTC/TWD'），或明確設定 confirm_all_markets=true 以確認撤銷全部。",
                "requires_confirmation": True}

    try:
        res = _cancel_all_max_orders_raw(m if market_norm else None)   # 轉發去空白後的 market，避免空白填充導致合法撤單失敗
        return {
            "status": "SUCCESS",
            "canceled_orders_count": len(res),
            "canceled_orders": res
        }
    except Exception as e:
        logger.error(f"撤銷所有掛單失敗: {e}")
        return {
            "status": "FAILED",
            "reason": str(e)
        }

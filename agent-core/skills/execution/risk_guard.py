"""
skills/execution/risk_guard.py

交易執行底層硬編碼風控安全鎖 (Risk Guard)
=============================================
作為下單執行的最後一道物理防線，防止 LLM 幻覺或異常指令造成重大資產損失。
硬編碼規則：
  1. 單筆最大下單金額限制：法幣交易對最大 50,000 TWD；美元/穩定幣交易對最大 1,500 USDT/USD。
  2. 槓桿限制：不開放槓桿交易，僅限現貨實盤交易 (Leverage = 1x)。
  3. 滑點限制：限價單價格與當前市場 ticker 最新價格偏離度不得超過 3%。
"""

import math
from typing import Dict, Any, Tuple
from loguru import logger

from skills.execution.quote_convert import notional_to_twd

# 硬編碼風控參數
MAX_SINGLE_ORDER_LIMIT_TWD = 50000.0   # 單筆最大 5 萬台幣
MAX_SINGLE_ORDER_LIMIT_USDT = 1500.0   # 單筆最大 1500 美元
MAX_SLIPPAGE_TOLERANCE = 0.03          # 最大滑點偏離度 3%

def validate_order(
    market: str,
    side: str,
    volume: float,
    price: float,
    ord_type: str,
    latest_ticker_price: float
) -> Tuple[bool, str]:
    """
    【底層物理風控鎖】在下單前強制校驗風控規則，返還 (是否通過, 原因說明)。
    """
    market_id = market.replace("/", "").replace("_", "").lower()
    side_upper = side.upper()
    ord_type_lower = ord_type.lower()
    
    # 0. 基本參數校驗
    if side_upper not in ["BUY", "SELL"]:
        return False, f"風控攔截：不支援的交易方向 {side}"
    if ord_type_lower not in ["limit", "market"]:
        return False, f"風控攔截：不支援的訂單類型 {ord_type}"
    # 非有限數（NaN/Inf）在比較中恆為 False → 會『fail-open』穿過所有檢查，必須先擋
    def _bad(x: Any) -> bool:
        return not isinstance(x, (int, float)) or not math.isfinite(x) or x <= 0

    if _bad(volume):
        return False, "風控攔截：下單數量必須為有效正數"

    # 對於市價單，若無價格輸入，使用市場最新價做為估算價格
    est_price = price if ord_type_lower == "limit" else latest_ticker_price
    if _bad(est_price):
        return False, "風控攔截：估算價格異常（非有效正數）"
    if _bad(latest_ticker_price):
        return False, "風控攔截：市場最新價異常（非有效正數）"

    order_value = volume * est_price

    # 1. 換算成 TWD 再比『單一上限』：杜絕「非 TWD 對一律當 USD」造成的單位錯亂繞過
    #    （usdt 單被低估而繞過核准、btc 計價單被低估數個量級）。未知幣別/匯率不可得 → fail-closed。
    notional_twd = notional_to_twd(order_value, market_id)
    if notional_twd is None:
        return False, f"風控攔截：無法判定 {market_id} 的計價幣別或換算匯率，為資產安全拒絕下單。"
    if notional_twd > MAX_SINGLE_ORDER_LIMIT_TWD:
        err_msg = (f"風控攔截：單筆估算金額 ≈ {notional_twd:,.0f} TWD "
                   f"超過上限 {MAX_SINGLE_ORDER_LIMIT_TWD:,.0f} TWD！")
        logger.warning(err_msg)
        return False, err_msg
            
    # 2. 偏離度 (滑點) 校驗 (僅針對限價單)
    if ord_type_lower == "limit":
        price_deviation = abs(price - latest_ticker_price) / latest_ticker_price
        if price_deviation > MAX_SLIPPAGE_TOLERANCE:
            err_msg = f"風控攔截：限價單委託價格 {price} 與市場最新價 {latest_ticker_price} 偏離度達 {price_deviation*100:.2f}%，已超過最大容忍偏離值 {MAX_SLIPPAGE_TOLERANCE*100:.1f}%！"
            logger.warning(err_msg)
            return False, err_msg
            
    logger.info(f"風控通過：交易對={market_id}, 方向={side_upper}, 數量={volume}, 預估金額={order_value:,.2f}")
    return True, "風控校驗通過"

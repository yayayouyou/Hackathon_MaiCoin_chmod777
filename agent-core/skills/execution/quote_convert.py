"""
skills/execution/quote_convert.py — 計價幣別 → TWD 正規化名目金額
================================================================
風控與核准都需要『同一單位』的名目金額才能跟門檻比較。交易對的計價幣別可能是
TWD / USDT / USDC / USD / BTC / ETH…；若直接拿 volume×price（計價幣別的數字）去比 TWD
門檻，會單位錯亂：USDT 單被低估而繞過核准、BTC 計價單被低估數個量級而繞過風控上限。

設計原則：風控是『物理最後防線』，必須**確定性、不打網路**（否則會 flaky、且網路/匯率
波動會左右安全判斷）。因此：
  - TWD             → 匯率 1.0
  - 穩定幣(USDT/USDC/USD) → 固定『保守高估』匯率（不打網路；寧可誤攔＝fail-safe）
  - 其他(BTC/ETH…)/未知計價幣 → 無安全的固定匯率 → 回 None → 呼叫端 **fail-closed（拒絕下單）**

備註：BTC/ETH 計價的 exotic 對（如 MAX 的 ethbtc）在有專用即時匯率源前一律被擋，
這是刻意的安全預設（它正是原本繞過風控上限的破口）。
"""
from typing import Optional

# 尾碼比對（長→短優先，避免 usdt 被 usd 先吃掉）
_KNOWN_QUOTES = ("usdt", "usdc", "twd", "usd", "btc", "eth")
_STABLE_QUOTES = {"usdt", "usdc", "usd"}
# 穩定幣→TWD 的固定保守匯率：取歷史區間上界（實際約 30–33），高估→寧可誤攔（fail-safe），不打網路
_STABLE_TWD_RATE = 35.0


def quote_currency(market: str) -> Optional[str]:
    """由交易對推斷計價幣別；無法判定回 None。"""
    m = (market or "").replace("/", "").replace("_", "").lower()
    for q in _KNOWN_QUOTES:
        if len(m) > len(q) and m.endswith(q):
            return q
    return None


def rate_to_twd(quote: Optional[str]) -> Optional[float]:
    """計價幣別→TWD 匯率（確定性、不打網路）；無安全匯率回 None。"""
    if quote == "twd":
        return 1.0
    if quote in _STABLE_QUOTES:
        return _STABLE_TWD_RATE
    return None


def notional_to_twd(order_value: float, market: str) -> Optional[float]:
    """把（計價幣別的）名目金額換算成 TWD；未知/不可安全換算的計價幣回 None（呼叫端 fail-closed）。"""
    rate = rate_to_twd(quote_currency(market))
    if rate is None or rate <= 0:
        return None
    return order_value * rate

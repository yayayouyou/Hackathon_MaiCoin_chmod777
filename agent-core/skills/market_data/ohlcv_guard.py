"""
skills/market_data/ohlcv_guard.py — OHLCV 資料完整性閘門
=====================================================
在資料邊界丟掉『髒 K 線』，避免壞資料污染所有下游分析/回測（借鏡 Vibe-Trading 的 loader 邊界守衛）。

丟棄條件（違反 OHLC 基本不變式）：
  - 任一 O/H/L/C 非有限數或 ≤ 0
  - high < low
  - high < open 或 high < close（最高價卻低於開/收）
  - low > open 或 low > close（最低價卻高於開/收）
"""
import math
from typing import Any, List, Tuple


def clean_ohlcv(rows: List[List[Any]]) -> Tuple[List[List[Any]], int]:
    """輸入 [[ts,o,h,l,c,v], ...] → (乾淨列, 丟棄數)。"""
    out, dropped = [], 0
    for r in rows or []:
        try:
            o, h, l, c = float(r[1]), float(r[2]), float(r[3]), float(r[4])
        except (TypeError, ValueError, IndexError):
            dropped += 1
            continue
        if (not all(math.isfinite(x) and x > 0 for x in (o, h, l, c))
                or h < l or h < o or h < c or l > o or l > c):
            dropped += 1
            continue
        out.append(r)
    return out, dropped

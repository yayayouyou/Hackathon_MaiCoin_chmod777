"""
skills/analytics/csv_source.py — CSV 帳本來源（訪客示範帳戶的種子資料）

**定位**：主辦方已表示「用 MAX API 的真實資料比 CSV 更好」，CSV 不再是硬約束。
因此本模組**不是主資料源**，而是「還沒綁定 MAX 金鑰的訪客」看得到東西的種子帳本
——讓 demo 在沒有任何憑證、沒有網路的情況下也能跑出完整的交易 DNA 面板。
真實使用者一旦接上 MAX，資料應改走 `position_ledger.fetch_events()`。

**輸出形狀刻意對齊 `position_ledger.fetch_events()`**，好讓同一批下游模組
（equity_curve / dna_score / counterfactual）兩種來源都吃得下：

    {"uid", "ts", "source", "currency", "delta", "disposal",
     "price", "quote", "quote_amount", "note"}

對不齊的地方（CSV 給不出 / CSV 多給的），一律在此說明，不默默改形狀：

1. **uid**：CSV 沒有交易所流水號 → 合成 `csv:<列號>`（列號自 1 起、含表頭後的順序）。
2. **成交只有單邊**：`fetch_events()` 一筆成交會拆成 base / quote / fee 三個事件；
   CSV 每列只描述「一個資產的變動」，沒有 TWD 對手腿、也**沒有手續費欄位**。
   → 因此 counterfactual 的手續費只能用費率估算，不能用實際扣款。
3. **price 一律填滿**：`fetch_events()` 的入出金事件 `price=None`（要另外查行情）；
   CSV 每一列都自帶「該資產的 TWD 單價」→ 我們照填。這是**刻意多給**的資訊，
   讓離線重播完全不需要行情 API（`lot_engine.twd_price_at` 會發網路請求）。
4. **balance**：CSV 獨有的「該次完成後餘額」，`fetch_events()` 沒有這個概念。
   保留在事件的 `balance` 欄供資料健檢比對用，下游模組不依賴它。
5. **currency 大寫**：對齊 `_ev()` 的 `str(currency).upper()`。CSV 是小寫。
6. **source 對應**：buy/sell → `trade`（sell 帶 `disposal=True`）；
   deposit/withdrawal → `deposit`/`withdrawal`。CSV 沒有 reward/convert/transfer/fee。
"""
from __future__ import annotations

import csv
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List

from loguru import logger

# CSV 的動作字彙（MaiCoin 命題定義）
BUY = "buy"
SELL = "sell"
DEPOSIT = "deposit"
WITHDRAWAL = "withdrawal"

# 計價基準幣（法幣，不建成本批次、不計損益，price 恆為 1）。對齊 lot_engine._HOME。
HOME_CCY = "TWD"

_REQUIRED_COLUMNS = {"timestamp", "currency", "price", "action", "change", "balance"}

# 訪客示範帳戶的預設種子檔。**不寫死絕對路徑**：以本檔位置往上推到 repo 根，
# 並允許環境變數 MAIA_DEMO_CSV 覆蓋（容器 / AgentCore 佈署時掛在別的地方）。
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
DEFAULT_DEMO_CSV = os.path.join(
    _REPO_ROOT, "data_set", "MaiCoin_最近一年份出入金及交易紀錄.csv")


def resolve_csv_path(path: str = "") -> str:
    """決定要讀哪一份 CSV：明確參數 > 環境變數 MAIA_DEMO_CSV > 內建示範帳戶。"""
    return path or os.getenv("MAIA_DEMO_CSV") or DEFAULT_DEMO_CSV


def _to_event(row: Dict[str, str], idx: int) -> Dict[str, Any]:
    """一列 CSV → 一個帳本事件（形狀對齊 position_ledger._ev）。"""
    ts = int(row["timestamp"])
    ccy = str(row["currency"]).strip().upper()
    price = float(row["price"])
    action = str(row["action"]).strip().lower()
    change = float(row["change"])
    qty = abs(change)

    if action in (BUY, SELL):
        source, disposal = "trade", (action == SELL)
        # CSV 沒有對手腿，但買賣本來就是對 TWD 成交 → 補上 quote 資訊，
        # 讓事件能被 lot_engine._acquire_cost 這類「看 quote_amount」的邏輯讀懂。
        quote, quote_amount = HOME_CCY, round(price * qty, 8)
        note = f"{'買' if action == BUY else '賣'} {ccy}/{HOME_CCY}（CSV 種子）"
    else:
        source, disposal = action, False
        quote, quote_amount = None, None
        note = ("入金（CSV 種子）" if action == DEPOSIT
                else "出金/提幣（轉移非處分，CSV 種子）")

    return {
        "uid": f"csv:{idx}",
        "ts": ts,
        "source": source,
        "currency": ccy,
        "delta": round(change, 12),
        "disposal": disposal,
        "price": price,          # ← 與 fetch_events 的差異：入出金也填，見模組 docstring 第 3 點
        "quote": quote,
        "quote_amount": quote_amount,
        "note": note,
        "balance": float(row["balance"]),   # ← CSV 獨有，見第 4 點
    }


def load_csv_events(path: str = "") -> List[Dict[str, Any]]:
    """讀取 CSV → 依時間排序的帳本事件清單。純標準庫，零網路。"""
    target = resolve_csv_path(path)
    events: List[Dict[str, Any]] = []
    with open(target, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = _REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV 缺少必要欄位：{sorted(missing)}（檔案：{target}）")
        for i, row in enumerate(reader, start=1):
            events.append(_to_event(row, i))
    events.sort(key=lambda e: e["ts"])
    return events


def data_health(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """資料健檢：筆數、時間範圍、幣種/動作分布、餘額一致性。

    誠實揭露資料品質——主辦提供的 CSV 是**合成隨機資料**，餘額欄與累積變動量對不上的
    列數就是證據。簡報上把這個數字講出來，比假裝資料完美有說服力。
    """
    if not events:
        return {"count": 0, "note": "沒有任何事件。"}

    ccy_counts = Counter(e["currency"] for e in events)
    action_counts = Counter(
        ("buy" if (e["source"] == "trade" and not e["disposal"])
         else "sell" if e["source"] == "trade" else e["source"])
        for e in events)

    running: Dict[str, float] = defaultdict(float)
    inconsistent = 0
    checked = 0
    for e in events:
        running[e["currency"]] += e["delta"]
        if e.get("balance") is None:
            continue
        checked += 1
        if abs(running[e["currency"]] - e["balance"]) > 1e-3:
            inconsistent += 1

    def _iso(ts: int) -> str:
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()

    return {
        "count": len(events),
        "time_start": _iso(events[0]["ts"]),
        "time_end": _iso(events[-1]["ts"]),
        "currencies": dict(ccy_counts),
        "actions": dict(action_counts),
        "balance_checked_rows": checked,
        "balance_inconsistent_rows": inconsistent,
        "note": "balance_inconsistent_rows > 0 代表 CSV 的餘額欄與累積變動量對不上"
                "（主辦提供的是合成資料）。分析一律以 change/delta 為準，不採信 balance。",
    }


# ── 對外入口（LLM Tool）────────────────────────────────────────────
def load_demo_account_ledger(path: str = "", include_events: bool = False,
                             preview: int = 5) -> Dict[str, Any]:
    """【LLM Tool】載入訪客示範帳戶（CSV 種子）的交易帳本並做資料健檢。

    使用者還沒綁 MAX 金鑰時，用這份種子帳本讓交易 DNA 面板有東西可看。

    Args:
        path: CSV 路徑，留空＝環境變數 MAIA_DEMO_CSV 或內建示範帳戶
        include_events: 是否回傳全部事件（預設 False，1 萬筆會塞爆 context）
        preview: 回傳前幾筆事件當樣本（預設 5）
    """
    target = resolve_csv_path(path)
    if not os.path.exists(target):
        return {"error": f"找不到示範帳戶 CSV：{target}",
                "hint": "可用 path 參數或環境變數 MAIA_DEMO_CSV 指定，或改用 MAX 真實帳本。"}
    try:
        events = load_csv_events(target)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"示範帳戶 CSV 讀取失敗：{e}")
        return {"error": f"CSV 讀取失敗：{e}", "path": target}

    out: Dict[str, Any] = {
        "source": "demo_csv",
        "path": target,
        "health": data_health(events),
        "sample": events[:max(0, preview)],
        "note": "這是**訪客示範帳戶**的種子資料，不是使用者的真實帳本。"
                "接上 MAX 金鑰後請改用 reconcile_holdings / get_open_positions 取真實數字。",
    }
    if include_events:
        out["events"] = events
    return out


def load_events_for_analysis(source: str = "", path: str = "") -> Dict[str, Any]:
    """下游模組共用的取數入口：ledger＝MAX 真實帳本事件（預設）；demo＝CSV 種子。

    source 留空時：有給 path 就讀那份 CSV，否則走 ledger（主辦 CSV 已移出 repo，
    見 6ae0d9d）。
    回傳 {"events": [...], "source": ..., "price_lookup": callable|None}。
    ledger 模式的事件沒有 TWD 單價 → 掛上 lot_engine.twd_price_at 當價格查詢器
    （會走網路；抓不到就由 equity_curve 記進 missing_price_events，不亂編價格）。
    """
    source = source or ("demo" if path else "ledger")
    if source == "ledger":
        try:
            from skills.analytics.position_ledger import load_events
            from skills.analytics.lot_engine import twd_price_at
        except ImportError as e:  # noqa: BLE001
            return {"events": [], "source": "ledger", "price_lookup": None,
                    "error": f"帳本模組載入失敗：{e}"}
        events = load_events()
        if not events:
            return {"events": [], "source": "ledger", "price_lookup": None,
                    "error": "本地帳本是空的。請先執行 reconcile_holdings 建立帳本"
                             "（需已設定 MAX 金鑰）。"}
        return {"events": sorted(events, key=lambda e: e.get("ts") or 0),
                "source": "ledger", "price_lookup": twd_price_at}

    target = resolve_csv_path(path)
    if not os.path.exists(target):
        return {"events": [], "source": "demo", "price_lookup": None,
                "error": f"找不到示範帳戶 CSV：{target}"}
    try:
        return {"events": load_csv_events(target), "source": "demo",
                "price_lookup": None, "path": target}
    except Exception as e:  # noqa: BLE001
        return {"events": [], "source": "demo", "price_lookup": None,
                "error": f"CSV 讀取失敗：{e}"}

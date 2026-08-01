#!/usr/bin/env python3
"""
scripts/skill_healthcheck.py — 逐一實際呼叫每個註冊工具，回報誰活著、誰壞了、為什麼。

為什麼需要：工具數量已破百，而「有 schema、有路由、但呼叫會炸」的狀態從畫面上
看不出來 —— 使用者只會看到 agent 回答「查不到」。這支腳本直接打真實 API，把
沉默的失敗變成可見的清單。

用法：
    .venv/bin/python scripts/skill_healthcheck.py            # 全部（會打真實外部 API）
    .venv/bin/python scripts/skill_healthcheck.py --group max_exchange
    .venv/bin/python scripts/skill_healthcheck.py --only get_max_tickers,get_ohlcv
    .venv/bin/python scripts/skill_healthcheck.py --json out.json

分類：
    OK        有回傳且看起來有內容
    EMPTY     呼叫成功但沒資料（可能是正常的，例如沒有未成交掛單）
    NO_KEY    缺 API 金鑰／未授權 → 環境問題，不是程式壞
    RATE      被限流
    NET       連線／逾時
    ERROR     其他例外（這類最需要看）
    SKIP      刻意不呼叫（下單等會造成副作用的）
"""
import argparse
import json
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 會真的動到錢或改變狀態的工具：永遠不呼叫
SIDE_EFFECT = {
    "create_order", "cancel_order", "cancel_all_orders",
    "remember_about_me", "forget_about_me", "save_strategy",
}

# 需要「帳戶裡真實存在的 id」才有意義的工具：拿假 id 打必然回「找不到」，
# 那是正確行為而非壞掉。標記成 NEED_ID，不列入需要修的清單。
NEEDS_REAL_ID = {"get_max_order", "run_backtest_on_saved_strategy"}

# 慢但正常的工具（給更長的逾時）
SLOW = {
    "run_analyst_desk", "run_analysis", "run_backtest", "backtest_strategy",
    "run_signal_backtest", "run_composite_backtest", "run_twitter_mention_backtest",
    "run_backtest_on_saved_strategy", "run_token_due_diligence",
    "validate_smart_money_signal", "analyze_figure_sentiment", "analyze_crowd_sentiment",
    "analyze_sentiment_divergence", "analyze_influence_decay", "trace_deposit_source",
    "reconcile_holdings", "get_open_positions", "get_realized_pnl",
    "get_cost_basis_positions", "analyze_gold_market", "get_btc_treasuries",
}

# 依參數名稱推測合理的測試值。key 為參數名，value 為值。
ARG_HINTS: Dict[str, Any] = {
    "symbol": "BTC/USDT", "symbols": "BTC,ETH",   # 註：analyze_portfolio 的 symbols 是陣列，見 ARG_OVERRIDES
    "market": "BTC/TWD", "pair": "BTC/USDT",
    "currency": "BTC", "coin_id": "bitcoin", "token": "BTC",
    "exchange": "binance", "exchange_id": "binance",
    "timeframe": "1d", "interval": "1d", "period": "1d",
    "limit": 5, "days": 7, "lookback_days": 30, "period_minutes": 1440,
    "query": "bitcoin", "keyword": "bitcoin", "term": "資金費率",
    "username": "elonmusk", "handle": "elonmusk", "figure": "trump",
    "subreddit": "CryptoCurrency", "url": "https://example.com",
    "strategy_name": "ma_cross", "wallet_type": "spot", "side": "buy",
    "chain": "ethereum", "network": "ethereum", "address": "0x0000000000000000000000000000000000000000",
    "amount": 10000, "price": 100.0, "capital": 10000,
    "text": "BTC 要漲了", "sn": "", "order_id": 1, "id": 1,
    "reward_type": "", "kind": "deposit", "method": "fifo", "reward_basis": "market",
    "sync": False, "risk_pct": 1.0, "stop_loss_pct": 5.0,
    "asset": "BTC", "person": "elon", "code": "result = {'ok': True}",
    "name": "ma_cross", "token_address": "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984",
    "account_balance": 100000.0, "entry_price": 100000.0, "stop_loss_price": 95000.0,
    "current_units": 1.0, "current_avg_cost": 100000.0, "add_price": 90000.0,
    "add_amount": 50000.0, "amount_per_period": 10000.0,
    "prices": [900000, 950000, 1010000, 980000, 1030000],
    "target_profit_pct": 20.0, "cost_price": 100000.0, "units": 1.0,
}

# 少數工具的參數語意與同名參數不同，或需要真實資料才有意義 → 個別指定。
ARG_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "analyze_portfolio": {"symbols": ["BTC/USDT", "ETH/USDT"], "timeframe": "1d"},
    "get_max_order_history": {"market": "btctwd", "limit": 5},
    "get_max_order": {"order_id": 1},
    # 訊號名稱必須是引擎認得的（非任意字串）；兩個以上才構成「組合」
    "run_composite_backtest": {"signals": ["extreme_fear", "high_funding"], "asset": "BTC"},
    "calculate_average_down": {"current_units": 1.0, "current_avg_cost": 100000.0,
                               "add_price": 90000.0, "add_amount": 50000.0},
    # 需要足量 K 線的：limit 給到門檻以上，否則永遠是「資料不足」而非真的壞掉
    "backtest_strategy": {"symbol": "BTC/USDT", "timeframe": "1d", "limit": 200},
    "get_ohlcv": {"exchange_id": "binance", "symbol": "BTC/USDT", "timeframe": "1d", "limit": 200},
}


def build_args(schema: Dict[str, Any]) -> Dict[str, Any]:
    """從 JSON schema 產生一組合理的測試參數：必填一定給，選填只給 limit 之類的安全值。"""
    fn = schema.get("function", {})
    params = (fn.get("parameters") or {}).get("properties") or {}
    required = set((fn.get("parameters") or {}).get("required") or [])
    args: Dict[str, Any] = {}
    for name, spec in params.items():
        if name not in required and name not in ("limit", "days", "timeframe"):
            continue
        if name in ARG_HINTS:
            args[name] = ARG_HINTS[name]
            continue
        if "default" in spec:
            args[name] = spec["default"]
            continue
        if name not in required:
            continue
        t = spec.get("type")
        enum = spec.get("enum")
        if enum:
            args[name] = enum[0]
        elif t == "integer":
            args[name] = 5
        elif t == "number":
            args[name] = 1.0
        elif t == "boolean":
            args[name] = False
        elif t == "array":
            args[name] = []
        elif t == "object":
            args[name] = {}
        else:
            args[name] = ""
    return args


def classify(result: Any, err: BaseException | None) -> Tuple[str, str]:
    """把呼叫結果歸類成一個狀態碼 + 一句話說明。"""
    if err is not None:
        msg = f"{type(err).__name__}: {err}"
        low = msg.lower()
        if any(k in low for k in ("api key", "apikey", "unauthorized", "401", "403",
                                  "missing key", "credential", "金鑰", "未設定")):
            return "NO_KEY", msg[:160]
        if any(k in low for k in ("429", "rate limit", "too many requests", "限流")):
            return "RATE", msg[:160]
        if any(k in low for k in ("timeout", "timed out", "connection", "resolve",
                                  "unreachable", "network", "ssl")):
            return "NET", msg[:160]
        return "ERROR", msg[:160]

    # 工具慣例：回 dict 且帶 error 欄位 = 失敗（不拋例外）
    if isinstance(result, dict) and result.get("error"):
        msg = str(result.get("error"))[:160]
        low = msg.lower()
        if any(k in low for k in ("api key", "unauthorized", "401", "403", "金鑰")):
            return "NO_KEY", msg
        if any(k in low for k in ("429", "rate limit", "限流")):
            return "RATE", msg
        if any(k in low for k in ("timeout", "connection", "resolve", "network")):
            return "NET", msg
        return "ERROR", msg

    if result is None:
        return "EMPTY", "回傳 None"
    if isinstance(result, (list, tuple, dict, str)) and len(result) == 0:
        return "EMPTY", "回傳空容器"
    size = len(result) if isinstance(result, (list, tuple, dict, str)) else 1
    return "OK", f"{type(result).__name__}({size})"


def run_one(name: str, fn, args: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    t0 = time.time()
    if name in SIDE_EFFECT:
        return {"tool": name, "status": "SKIP", "detail": "會產生副作用，刻意不呼叫",
                "secs": 0.0, "args": args}
    result = err = None
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(fn, **args)
        try:
            result = fut.result(timeout=timeout)
        except FuturesTimeout:
            err = TimeoutError(f"超過 {timeout:.0f}s 未回應")
        except BaseException as e:  # noqa: BLE001
            err = e
    status, detail = classify(result, err)
    if status == "ERROR" and name in NEEDS_REAL_ID:
        status = "NEED_ID"   # 假 id 打不到東西是預期結果
    return {"tool": name, "status": status, "detail": detail,
            "secs": round(time.time() - t0, 1), "args": args}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="逗號分隔的工具名，只測這些")
    ap.add_argument("--group", help="只測名稱含此字串的工具")
    ap.add_argument("--timeout", type=float, default=25.0, help="單一工具逾時秒數")
    ap.add_argument("--json", help="把完整結果寫到這個檔")
    ap.add_argument("--workers", type=int, default=4, help="並行數")
    a = ap.parse_args()

    os.environ.setdefault("ROUTING_LOG", "0")
    from agent.ollama_agent import TOOL_CALLABLES
    from agent.prompts import ALL_TOOLS

    schemas = {t["function"]["name"]: t for t in ALL_TOOLS}
    names = sorted(TOOL_CALLABLES)
    if a.only:
        want = {x.strip() for x in a.only.split(",") if x.strip()}
        names = [n for n in names if n in want]
    if a.group:
        names = [n for n in names if a.group in n]

    print(f"檢查 {len(names)} 個工具（並行 {a.workers}、逾時 {a.timeout:.0f}s，慢工具放寬到 {a.timeout*4:.0f}s）\n")
    # 需要 K 線輸入的工具：先抓一份真實 K 線，否則只會得到「資料不足」這種假失敗
    klines: List[Any] = []
    if any(n in ("calculate_indicators", "run_backtest") for n in names):
        try:
            from skills.market_data.ccxt_fetcher import get_ohlcv
            got = get_ohlcv(exchange_id="binance", symbol="BTC/USDT", timeframe="1d", limit=200)
            if isinstance(got, list):
                klines = got
            elif isinstance(got, dict):
                for k in ("klines", "ohlcv", "data", "candles"):
                    if isinstance(got.get(k), list):
                        klines = got[k]
                        break
            print(f"（暖身取得 {len(klines)} 根 K 線）")
        except Exception as e:  # noqa: BLE001
            print(f"（暖身抓 K 線失敗，需要 K 線的工具會顯示資料不足：{e}）")

    jobs = []
    for n in names:
        schema = schemas.get(n)
        args = build_args(schema) if schema else {}
        args.update(ARG_OVERRIDES.get(n, {}))
        if "klines" in args and klines:
            args["klines"] = klines
        jobs.append((n, TOOL_CALLABLES[n], args, a.timeout * 4 if n in SLOW else a.timeout))

    rows: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for r in ex.map(lambda j: run_one(*j), jobs):
            rows.append(r)
            icon = {"OK": "✅", "EMPTY": "○", "NO_KEY": "🔑", "RATE": "⏳", "NEED_ID": "🔎",
                    "NET": "🌐", "ERROR": "❌", "SKIP": "—"}.get(r["status"], "?")
            print(f"  {icon} {r['status']:<7} {r['tool']:<38} {r['secs']:>5.1f}s  {r['detail'][:70]}")

    order = ["ERROR", "NET", "RATE", "NO_KEY", "NEED_ID", "EMPTY", "OK", "SKIP"]
    rows.sort(key=lambda r: (order.index(r["status"]) if r["status"] in order else 9, r["tool"]))
    counts: Dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    print("\n" + "=" * 70)
    print("統計：" + " · ".join(f"{k} {v}" for k, v in
                              sorted(counts.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 9)))
    bad = [r for r in rows if r["status"] in ("ERROR", "NET")]
    if bad:
        print(f"\n需要修的（{len(bad)}）：")
        for r in bad:
            print(f"  ❌ {r['tool']}\n     args={r['args']}\n     {r['detail']}")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n完整結果 → {a.json}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

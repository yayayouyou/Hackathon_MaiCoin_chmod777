"""
agent/strategy_bots.py — 策略機器人（Paper 模擬盤 MVP）

把一個「回測驗證過的策略」打包成一支**可自動運行的交易機器人**：runner 每隔
N 秒抓最新 MAX K 線 → 用**與回測同一套訊號邏輯**算出目標持倉 → 與機器人當前
paper 持倉不同就模擬成交、寫進 per-bot 台帳。

★ MVP 邊界（刻意的安全設計）：
  - **全程 paper**：只模擬成交、不呼叫 `create_order`、不碰真錢，因此完全繞開
    「一律人工確認」那道安全牆與實盤風控——自動化在這裡是安全的，因為它動不了
    真實資產。要升級成 live 才需要「機器人授權（限時/限額/可撤銷）＋ 每筆過
    risk_guard/live_guard」那套（見規劃 Phase 2），本檔不做。
  - **全域、單一 runner**：bots 存在一個 JSON、由一支 daemon 迴圈輪詢（骨架仿
    app.py 的 _threads_auto_sync_loop）。per-user 歸屬、DynamoDB 持久化留待後續。

訊號邏輯與 `skills/analytics/backtester.py` 一致（ma_crossover 比較快慢均線、
rsi_reversal 用超買超賣狀態機）——回測與實跑共用同一份定義，就是「統一策略 IR」
的雛形。
"""
from __future__ import annotations

import json
import os
import threading
import time
import secrets
from typing import Any, Dict, List, Optional

from loguru import logger

# ── 儲存 ────────────────────────────────────────────────────
_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "conversation_logs")
_BOTS_FILE = os.path.join(_DIR, "strategy_bots.json")
_LOCK = threading.RLock()

_FEE_RATE = 0.001            # paper 手續費（與回測預設一致）
_DEFAULT_CAPITAL = 100_000.0  # 每支 bot 起始 paper 資金（TWD）
_SUPPORTED = ("ma_crossover", "rsi_reversal")


def _load() -> Dict[str, Any]:
    try:
        with open(_BOTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save(bots: Dict[str, Any]) -> None:
    os.makedirs(_DIR, exist_ok=True)
    tmp = _BOTS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(bots, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _BOTS_FILE)


# ── 訊號評估（與 backtester 同一套邏輯，但只算「最新一根的目標持倉」）──
def _rsi_latest(closes: List[float], period: int = 14) -> float:
    """Wilder's RSI，回傳最新值。資料不足時回中性 50。"""
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def evaluate_target_position(
    closes: List[float], strategy_type: str, params: Dict[str, Any], cur_pos: int
) -> tuple[int, str]:
    """
    回傳 (target_pos, note)。target_pos 0=空手 / 1=持有。
    ma_crossover 是無狀態（快線>慢線就該持有）；rsi_reversal 是有狀態
    （用機器人「當前是否持倉」當狀態，這比回測 replay 更貼近實跑）。
    """
    if strategy_type == "ma_crossover":
        fast = int(params.get("fast_period", 10))
        slow = int(params.get("slow_period", 30))
        if len(closes) < slow:
            return cur_pos, f"資料不足（需 {slow} 根、目前 {len(closes)}）"
        fast_ma = sum(closes[-fast:]) / fast
        slow_ma = sum(closes[-slow:]) / slow
        target = 1 if fast_ma > slow_ma else 0
        return target, f"MA{fast}={fast_ma:,.0f} {'>' if target else '<='} MA{slow}={slow_ma:,.0f}"

    if strategy_type == "rsi_reversal":
        period = int(params.get("rsi_period", 14))
        oversold = float(params.get("oversold", 30))
        overbought = float(params.get("overbought", 70))
        rsi = _rsi_latest(closes, period)
        if cur_pos == 0 and rsi < oversold:
            return 1, f"RSI={rsi:.1f} < {oversold:.0f}（超賣進場）"
        if cur_pos == 1 and rsi > overbought:
            return 0, f"RSI={rsi:.1f} > {overbought:.0f}（超買出場）"
        return cur_pos, f"RSI={rsi:.1f}（維持）"

    return cur_pos, f"未知策略 {strategy_type}"


# ── paper 成交 ──────────────────────────────────────────────
def _paper_fill(bot: Dict[str, Any], side: str, price: float, reason: str) -> None:
    p = bot["paper"]
    ts = int(time.time() * 1000)
    if side == "buy" and p["cash"] > 0:
        gross = p["cash"]
        base = gross * (1 - _FEE_RATE) / price
        p["base"] = base
        p["avg_price"] = price
        p["cash"] = 0.0
        bot["trades"].append({"ts": ts, "side": "buy", "price": price,
                              "base": base, "quote": gross, "reason": reason})
    elif side == "sell" and p["base"] > 0:
        base = p["base"]
        gross = base * price
        net = gross * (1 - _FEE_RATE)
        p["realized_pnl"] += net - base * p["avg_price"]
        p["cash"] = net
        p["base"] = 0.0
        p["avg_price"] = 0.0
        bot["trades"].append({"ts": ts, "side": "sell", "price": price,
                              "base": base, "quote": gross, "reason": reason})
    bot["trades"] = bot["trades"][-100:]  # 只留最近 100 筆


def _latest_closes(bot: Dict[str, Any]) -> tuple[List[float], float]:
    """抓最新 MAX K 線，回 (closes 升冪, 最新收盤價)。"""
    from skills.max_exchange.max_public import get_max_klines
    slow = int(bot["params"].get("slow_period", 30))
    limit = max(slow + 10, int(bot["params"].get("rsi_period", 14)) + 10, 60)
    raw = get_max_klines(bot["market"], limit=limit, period_minutes=bot["period_minutes"])
    rows = [r for r in (raw or []) if isinstance(r, (list, tuple)) and len(r) >= 5]
    rows.sort(key=lambda r: r[0])  # 依 timestamp 升冪，最後一根為最新
    closes = [float(r[4]) for r in rows]
    return closes, (closes[-1] if closes else 0.0)


def _tick_bot(bot: Dict[str, Any]) -> None:
    """對單一 running bot 評估一次；有訊號翻轉就模擬成交。"""
    try:
        closes, price = _latest_closes(bot)
    except Exception as exc:  # noqa: BLE001
        bot["last_eval"] = {"ts": int(time.time() * 1000), "error": str(exc)[:120]}
        return
    if not closes or price <= 0:
        bot["last_eval"] = {"ts": int(time.time() * 1000), "error": "無 K 線資料"}
        return
    cur_pos = 1 if bot["paper"]["base"] > 0 else 0
    target, note = evaluate_target_position(closes, bot["strategy_type"], bot["params"], cur_pos)
    bot["last_eval"] = {"ts": int(time.time() * 1000), "price": price,
                        "target": target, "cur_pos": cur_pos, "note": note}
    if target != cur_pos:
        _paper_fill(bot, "buy" if target == 1 else "sell", price, note)


# ── runner（daemon 迴圈，仿 app.py 的 _threads_auto_sync_loop）──
_RUNNER_STOP = threading.Event()
_RUNNER_THREAD: Optional[threading.Thread] = None
_INTERVAL = float(os.getenv("STRATEGY_BOT_INTERVAL", "15"))  # 秒


def _runner_loop() -> None:
    logger.info("策略機器人 runner 已啟動（interval={}s）", _INTERVAL)
    while not _RUNNER_STOP.is_set():
        try:
            with _LOCK:
                bots = _load()
                dirty = False
                for bot in bots.values():
                    if bot.get("status") == "running":
                        _tick_bot(bot)
                        dirty = True
                if dirty:
                    _save(bots)
        except Exception:  # noqa: BLE001
            logger.exception("策略機器人 runner tick 失敗；稍後重試")
        if _RUNNER_STOP.wait(_INTERVAL):
            break
    logger.info("策略機器人 runner 已停止")


def start_runner() -> None:
    global _RUNNER_THREAD
    if _RUNNER_THREAD and _RUNNER_THREAD.is_alive():
        return
    _RUNNER_STOP.clear()
    _RUNNER_THREAD = threading.Thread(target=_runner_loop, name="strategy-bot-runner", daemon=True)
    _RUNNER_THREAD.start()


def stop_runner() -> None:
    _RUNNER_STOP.set()


# ── 對外檢視 ────────────────────────────────────────────────
def _public_view(bot: Dict[str, Any], with_trades: bool = False) -> Dict[str, Any]:
    p = bot["paper"]
    last_price = (bot.get("last_eval") or {}).get("price") or p["avg_price"] or 0.0
    unrealized = p["base"] * (last_price - p["avg_price"]) if p["base"] > 0 else 0.0
    equity = p["cash"] + p["base"] * last_price
    view = {
        "id": bot["id"],
        "name": bot["name"],
        "strategy_type": bot["strategy_type"],
        "params": bot["params"],
        "market": bot["market"],
        "period_minutes": bot["period_minutes"],
        "mode": bot["mode"],
        "status": bot["status"],
        "created_at": bot["created_at"],
        "position": "持有" if p["base"] > 0 else "空手",
        "initial_capital": bot["initial_capital"],
        "equity": round(equity, 2),
        "realized_pnl": round(p["realized_pnl"], 2),
        "unrealized_pnl": round(unrealized, 2),
        "total_pnl": round(p["realized_pnl"] + unrealized, 2),
        "return_pct": round((equity / bot["initial_capital"] - 1) * 100, 2) if bot["initial_capital"] else 0.0,
        "trade_count": len(bot["trades"]),
        "last_eval": bot.get("last_eval"),
    }
    if with_trades:
        view["trades"] = list(reversed(bot["trades"]))  # 最新在前
    return view


def list_bots() -> List[Dict[str, Any]]:
    with _LOCK:
        return [_public_view(b) for b in _load().values()]


def get_bot(bot_id: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        bot = _load().get(bot_id)
        return _public_view(bot, with_trades=True) if bot else None


def create_bot(
    name: str,
    strategy_type: str,
    params: Optional[Dict[str, Any]] = None,
    market: str = "btctwd",
    period_minutes: int = 5,
    initial_capital: float = _DEFAULT_CAPITAL,
) -> Dict[str, Any]:
    if strategy_type not in _SUPPORTED:
        return {"error": f"不支援的策略型別 {strategy_type}；目前支援 {list(_SUPPORTED)}"}
    bot = {
        "id": f"bot-{secrets.token_urlsafe(6)}",
        "name": (name or "未命名策略").strip()[:40],
        "strategy_type": strategy_type,
        "params": params or {},
        "market": str(market).lower().replace("/", ""),
        "period_minutes": int(period_minutes),
        "mode": "paper",
        "status": "stopped",
        "created_at": int(time.time() * 1000),
        "initial_capital": float(initial_capital),
        "paper": {"cash": float(initial_capital), "base": 0.0, "avg_price": 0.0, "realized_pnl": 0.0},
        "trades": [],
        "last_eval": None,
    }
    with _LOCK:
        bots = _load()
        bots[bot["id"]] = bot
        _save(bots)
    logger.info("建立策略機器人 {} ({} on {})", bot["id"], strategy_type, bot["market"])
    return _public_view(bot, with_trades=True)


def _set_status(bot_id: str, status: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        bots = _load()
        bot = bots.get(bot_id)
        if not bot:
            return None
        bot["status"] = status
        if status == "running":
            _tick_bot(bot)  # 立即評估一次，啟動當下就可能進場（demo 立刻看到動作）
        _save(bots)
        return _public_view(bot, with_trades=True)


def start_bot(bot_id: str) -> Optional[Dict[str, Any]]:
    return _set_status(bot_id, "running")


def stop_bot(bot_id: str) -> Optional[Dict[str, Any]]:
    return _set_status(bot_id, "stopped")


def delete_bot(bot_id: str) -> bool:
    with _LOCK:
        bots = _load()
        if bot_id not in bots:
            return False
        del bots[bot_id]
        _save(bots)
        return True


# ── LLM 工具：對話中把回測驗證過的策略打包成機器人 ──
def package_strategy_bot(
    name: str,
    strategy_type: str,
    params: Optional[Dict[str, Any]] = None,
    market: str = "btctwd",
    period_minutes: int = 5,
) -> Dict[str, Any]:
    """
    【LLM Tool】把一個（最好先用 backtest_strategy 驗證過的）策略打包成一支可在
    介面上啟動的**自動化 paper 交易機器人**。打包後機器人是「停止」狀態，等使用者
    在策略機器人面板按「啟動」才會開始自動跑（模擬盤）。

    Args:
        name: 機器人名稱（給人看的，如「BTC 雙均線 5/20」）
        strategy_type: 'ma_crossover' 或 'rsi_reversal'
        params: ma_crossover:{fast_period,slow_period}；rsi_reversal:{rsi_period,oversold,overbought}
        market: MAX 交易對，如 'btctwd'、'ethtwd'
        period_minutes: K 線週期（分鐘），如 5、15、60
    """
    res = create_bot(name=name, strategy_type=strategy_type, params=params,
                     market=market, period_minutes=period_minutes)
    if "error" in res:
        return res
    return {
        "status": "SUCCESS",
        "message": f"已把策略「{res['name']}」打包成 paper 交易機器人（{res['id']}），"
                   f"目前為停止狀態。請到左側『策略機器人』面板按啟動即可讓它自動模擬運行。",
        "bot": res,
    }

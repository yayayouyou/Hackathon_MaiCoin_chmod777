"""
skills/analytics/backtester.py

加密貨幣歷史數據策略回測引擎 (Vectorized Backtester)
=====================================================
提供以下回測函數：
  - run_backtest : 根據 K 線歷史與設定的策略（如均線交叉、RSI 逆勢），計算策略回測收益、勝率與最大回撤。
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from loguru import logger

def _walk_forward(klines, strategy_name, params, initial_capital, fee_rate, slippage_rate=0.001, n_folds: int = 4) -> Dict[str, Any]:
    """把 K 線切成 n_folds 段「連續的樣本外窗口」，各段獨立回測，檢查策略是否跨不同
    時間段都站得住（而非只在某一段運氣好 → 過擬合警訊）。每段需 ≥30 根才回測。"""
    n = len(klines)
    fold_size = n // max(1, n_folds)
    if fold_size < 30:
        return {"n_folds": 0, "note": "K 線不足，無法切成多段做 walk-forward（每段需 ≥30 根）"}
    fold_returns: List[float] = []
    for k in range(n_folds):
        seg = klines[k * fold_size:] if k == n_folds - 1 else klines[k * fold_size:(k + 1) * fold_size]
        r = run_backtest(seg, strategy_name, params, initial_capital, fee_rate, slippage_rate, _run_validation=False)
        if isinstance(r, dict) and "error" not in r:
            fold_returns.append(round(r["performance"]["total_return_pct"], 2))
    positives = sum(1 for x in fold_returns if x > 0)
    return {
        "n_folds": len(fold_returns),
        "fold_returns_pct": fold_returns,
        "folds_positive": positives,
        "consistency_pct": round(positives / len(fold_returns) * 100, 1) if fold_returns else 0.0,
    }


def _normalize_klines(klines: List[Any]) -> List[List[Any]]:
    """把兩種 K 線形態統一成 [[ts_ms, o, h, l, c, v], ...]。

    本專案有兩種來源並存：get_max_klines 給陣列、get_ohlcv 給物件
    （{timestamp, open, high, low, close, volume}，timestamp 是 ISO 字串）。
    模型很自然會把後者接到回測工具，不正規化就會崩在 k[0] 上、
    錯誤訊息還只顯示「異常: 0」，完全看不出原因。
    """
    out: List[List[Any]] = []
    for k in klines:
        try:
            if isinstance(k, dict):
                ts = k.get("timestamp", k.get("time", k.get("t", 0)))
                if isinstance(ts, str):
                    from datetime import datetime
                    ts = int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)
                out.append([int(ts), float(k.get("open", 0)), float(k.get("high", 0)),
                            float(k.get("low", 0)), float(k["close"]), float(k.get("volume", 0))])
            elif isinstance(k, (list, tuple)) and len(k) >= 5:
                ts = int(k[0])
                if ts < 10_000_000_000:      # 秒 → 毫秒（MAX 給秒級）
                    ts *= 1000
                out.append([ts, float(k[1]), float(k[2]), float(k[3]), float(k[4]),
                            float(k[5]) if len(k) > 5 else 0.0])
        except (TypeError, ValueError, KeyError, IndexError):
            continue      # 壞掉的單根跳過，不要整批失敗
    return out


def _chart_payload(klines: List[List[Any]], trade_pairs: List[Dict[str, Any]],
                   max_points: int = 400) -> Dict[str, Any]:
    """把 K 線與交易配對整理成前端畫圖要的最小資料集。

    價格線超過 max_points 就等距抽樣（畫面寬度撐死一千多像素，多畫沒有資訊量），
    但**交易標記一律全給** —— 標記是這張圖的重點，抽樣掉等於騙人。
    """
    try:
        pts = [(int(k[0]), float(k[4])) for k in klines if k and len(k) >= 5]
    except (TypeError, ValueError, IndexError):
        return {}
    if not pts:
        return {}
    step = max(1, len(pts) // max_points)
    sampled = pts[::step]
    if sampled[-1] != pts[-1]:
        sampled.append(pts[-1])       # 末端一定要保留，否則最後一筆交易會落在線外

    marks: List[Dict[str, Any]] = []
    for tp in (trade_pairs or []):
        for side, tk, pk in (("buy", "buy_time", "buy_price"), ("sell", "sell_time", "sell_price")):
            t, p = tp.get(tk), tp.get(pk)
            if t is None or p is None:
                continue
            ms = t
            if not isinstance(ms, (int, float)):
                try:
                    from datetime import datetime
                    ms = int(datetime.fromisoformat(str(t)).timestamp() * 1000)
                except (TypeError, ValueError):
                    continue
            marks.append({"side": side, "t": int(ms), "price": float(p),
                          "pnl_pct": tp.get("pnl_pct") if side == "sell" else None})
    return {
        "series": [{"t": t, "c": c} for t, c in sampled],
        "marks": sorted(marks, key=lambda m: m["t"]),
        "sampled_every": step,
        "total_bars": len(pts),
    }


def run_backtest(
    klines: List[List[Any]],
    strategy_name: str = "ma_crossover",
    strategy_params: Optional[Dict[str, Any]] = None,
    initial_capital: float = 10000.0,
    fee_rate: float = 0.001,      # 單邊交易手續費 0.1%
    slippage_rate: float = 0.001,  # 單邊滑價 0.1%（與手續費分開建模，見下方說明）
    _run_validation: bool = True,  # 內部用：walk-forward 分段回測時設 False，避免無限遞迴
) -> Dict[str, Any]:
    """
    【LLM Tool】傳入歷史 K 線，執行簡單回測，並返回績效報告與交易記錄。
    
    Args:
        klines: [[timestamp, open, high, low, close, volume], ...]
        strategy_name: 策略名稱，可選:
                       - 'ma_crossover' : 雙均線交叉策略 (快均線 vs 慢均線)
                       - 'rsi_reversal' : RSI 逆勢超買超賣策略 (RSI > 70 賣出, RSI < 30 買入)
        strategy_params: 策略參數 Dict，例如:
                         - 'ma_crossover': {"fast_period": 10, "slow_period": 30}
                         - 'rsi_reversal': {"rsi_period": 14, "oversold": 30, "overbought": 70}
        initial_capital: 初始本金，預設 10,000 USD
        fee_rate: 手續費率，預設 0.001 (0.1%)
        slippage_rate: 單邊滑價率，預設 0.001 (0.1%)

    成本模型：手續費與滑價**分開建模**，因為兩者性質不同 ——
    手續費是對成交金額收取的固定比例；滑價是「成交價偏離掛單當下報價」，
    會實際改變買到的數量。只算手續費會系統性高估策略績效，低流動性的
    TWD 交易對尤其明顯。滑價以價格滑移實作（買貴、賣便宜），因此交易
    紀錄與圖表標記上的價格就是真實成交價。
    """
    if not isinstance(klines, list) or len(klines) < 30:
        return {"error": "回測失敗。K 線長度不足，至少需要 30 根 K 線數據。"}

    klines = _normalize_klines(klines)
    if len(klines) < 30:
        return {"error": "回測失敗。K 線格式無法解析（需要 [ts,open,high,low,close,volume] "
                         "或含 timestamp/open/high/low/close 欄位的物件）。"}

    try:
        # 1. 建立 DataFrame
        df = pd.DataFrame(klines, columns=["timestamp", "open", "high", "low", "close", "volume"])
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col])
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
        
        # 2. 初始化信號 (0 = 無動作, 1 = 持有/做多, -1 = 空倉/平倉)
        df["signal"] = 0
        
        params = strategy_params or {}
        
        # 3. 根據選擇策略計算信號
        if strategy_name == "ma_crossover":
            fast = params.get("fast_period", 10)
            slow = params.get("slow_period", 30)
            
            # 使用簡單移動平均線
            df["fast_ma"] = df["close"].rolling(window=fast).mean()
            df["slow_ma"] = df["close"].rolling(window=slow).mean()
            
            # 當快線 > 慢線時持倉為 1，否則為 0
            df["position"] = np.where(df["fast_ma"] > df["slow_ma"], 1, 0)
            # 信號為持倉的變動 (1: 買入信號, -1: 賣出信號)
            df["signal"] = df["position"].diff().fillna(0)
            
        elif strategy_name == "rsi_reversal":
            import ta
            rsi_len = params.get("rsi_period", 14)
            oversold = params.get("oversold", 30)
            overbought = params.get("overbought", 70)
            
            df["rsi"] = ta.momentum.rsi(df["close"], window=rsi_len)
            
            # 當前持倉狀態狀態
            curr_pos = 0
            positions = []
            signals = []
            
            for index, row in df.iterrows():
                rsi_val = row["rsi"]
                sig = 0
                
                if pd.isna(rsi_val):
                    positions.append(0)
                    signals.append(0)
                    continue
                    
                if curr_pos == 0 and rsi_val < oversold:
                    curr_pos = 1  # 買入
                    sig = 1
                elif curr_pos == 1 and rsi_val > overbought:
                    curr_pos = 0  # 賣出
                    sig = -1
                    
                positions.append(curr_pos)
                signals.append(sig)
                
            df["position"] = positions
            df["signal"] = signals
        else:
            return {"error": f"不支援的策略: {strategy_name}"}

        # 4. 模擬交易與資產淨值 (Equity Curve) 計算
        capital = initial_capital
        position_units = 0.0
        trades = []
        equity = []
        
        # 遍歷 K 線模擬交易
        # 杜絕前視偏誤 (look-ahead bias)：訊號在第 i 根「收盤」才成立，現實中最快
        # 只能在「次一根」動作，故把訊號往後移一根，並以次一根的『開盤價』成交；
        # 淨值 (equity) 仍以當根收盤價 mark-to-market。
        df["signal"] = df["signal"].shift(1).fillna(0)

        for idx, row in df.iterrows():
            sig = row["signal"]
            quote_price = row["open"]   # 訊號已 shift → 以次一根開盤價成交（消除前視）
            # 滑價往不利方向套用：買進成交價更高、賣出成交價更低。
            # 直接改成交價（而非併進費率）才會連帶影響買到的數量，也讓交易紀錄
            # 與圖表標記顯示的是真實成交價。
            exec_price = (quote_price * (1 + slippage_rate) if sig == 1
                          else quote_price * (1 - slippage_rate) if sig == -1
                          else quote_price)
            mark_price = row["close"]   # 淨值以當根收盤價計價
            time_str = row["datetime"].isoformat()
            
            if sig == 1 and capital > 0:  # 買入信號
                # 計算購買數量 (扣除手續費)
                fee = capital * fee_rate
                invest_amount = capital - fee
                position_units = invest_amount / exec_price
                capital = 0.0
                trades.append({
                    "action": "BUY",
                    "price": exec_price,
                    "units": position_units,
                    "fee": fee,
                    "cost": invest_amount,
                    "datetime": time_str
                })
            elif sig == -1 and position_units > 0:  # 賣出信號
                # 賣出全部持倉
                sale_vol = position_units * exec_price
                fee = sale_vol * fee_rate
                capital = sale_vol - fee
                trades.append({
                    "action": "SELL",
                    "price": exec_price,
                    "units": position_units,
                    "fee": fee,
                    "revenue": sale_vol,
                    "datetime": time_str
                })
                position_units = 0.0
                
            # 計算當前總資產價值 (現金 + 持倉價值)
            current_value = capital + (position_units * mark_price)
            equity.append(current_value)
            
        df["equity"] = equity
        
        # 5. 計算績效統計指標
        final_value = equity[-1]
        total_return = (final_value - initial_capital) / initial_capital * 100
        
        # 基準收益 (Buy and Hold)
        start_price = df.iloc[0]["close"]
        end_price = df.iloc[-1]["close"]
        bh_return = (end_price - start_price) / start_price * 100
        
        # 最大回撤 (Max Drawdown)
        equity_series = pd.Series(equity)
        cum_max = equity_series.cummax()
        drawdowns = (equity_series - cum_max) / cum_max * 100
        max_dd = drawdowns.min()
        
        # 勝率計算
        wins = 0
        trade_pairs = []
        # 將買入和賣出組合成一次完整交易
        for i in range(0, len(trades) - 1, 2):
            if i+1 < len(trades):
                buy = trades[i]
                sell = trades[i+1]
                pnl = sell["revenue"] - buy["cost"] - buy["fee"] - sell["fee"]
                pnl_pct = pnl / buy["cost"] * 100
                trade_pairs.append({
                    "buy_price": buy["price"],
                    "sell_price": sell["price"],
                    "pnl_usd": pnl,
                    "pnl_pct": pnl_pct,
                    "buy_time": buy["datetime"],
                    "sell_time": sell["datetime"]
                })
                if pnl > 0:
                    wins += 1
                    
        total_trades = len(trade_pairs)
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0

        # ── 統計穩健性驗證（借鑑 Vibe-Trading rigor）：bootstrap 信賴區間 + walk-forward ──
        # 只在最外層跑；walk-forward 的分段回測以 _run_validation=False 呼叫，避免遞迴。
        validation = None
        if _run_validation:
            from skills.analytics.event_study import _bootstrap_ci   # 重用既有 bootstrap 實作
            trade_returns = [p["pnl_pct"] for p in trade_pairs]
            ci_lo, ci_hi = _bootstrap_ci(trade_returns) if len(trade_returns) >= 3 else (None, None)
            wf = _walk_forward(klines, strategy_name, params, initial_capital, fee_rate, slippage_rate)
            robust_edge = ci_lo is not None and ci_lo > 0          # 單筆報酬 90% CI 下界 > 0
            consistent = wf.get("consistency_pct", 0) >= 75        # ≥3/4 分段為正
            if total_trades < 5:
                verdict = "樣本不足：交易筆數過少，統計結論不可靠，勿據此下重注"
            elif robust_edge and consistent:
                verdict = "穩健：單筆報酬信賴區間為正且跨時間一致，edge 較可能為真"
            elif not robust_edge and not consistent:
                verdict = "存疑：信賴區間含 0 且跨時間不一致，較可能是過擬合／運氣"
            else:
                verdict = "中性：部分指標支持、部分不支持，需更多樣本佐證"
            validation = {
                "bootstrap_ci90_mean_trade_return_pct": {
                    "low": ci_lo, "high": ci_hi,
                    "note": "單筆交易報酬 bootstrap 重抽的 90% 信賴區間；下界>0 代表 edge 較穩健",
                },
                "walk_forward": wf,
                "verdict": verdict,
            }

        return {
            "strategy": strategy_name,
            "params": params,
            # 回測完給 MAIA 的「下一步」提示 —— 回測與策略機器人用**同一套**策略名與
            # 參數，所以回測完可以「原封不動」打包成自動 paper 機器人。把這段放進工具
            # 結果，MAIA 就會在回測結論後主動提示使用者「要不要打包成機器人」，而不是
            # 等使用者自己想到。這是「回測 → 一鍵自動化」那條 demo 動線的接點。
            "packageable_as_bot": {
                "strategy_type": strategy_name,
                "params": params,
                "suggestion": "這個策略可以一鍵打包成一支 24 小時自動運行的 paper 機器人"
                              "（自動進出場、即時回報損益）。想讓它自動跑的話，回覆"
                              "「幫我打包成機器人」就好，會沿用這次回測的策略與參數。",
            },
            "performance": {
                "initial_capital_usd": initial_capital,
                "final_value_usd": final_value,
                "total_return_pct": total_return,
                "buy_and_hold_return_pct": bh_return,
                "excess_vs_bh_pct": round(total_return - bh_return, 2),   # 超額報酬：勝過買入持有多少
                "max_drawdown_pct": max_dd,
                "total_trades": total_trades,
                "win_rate_pct": win_rate
            },
            "cost_model": {
                "fee_rate": fee_rate, "slippage_rate": slippage_rate,
                "round_trip_cost_pct": round((fee_rate + slippage_rate) * 2 * 100, 3),
                "note": "手續費與滑價分開建模；滑價以價格滑移套用（買貴賣便宜）。"
                        "來回總成本 = (手續費 + 滑價) × 2。",
            },
            "recent_trades": trade_pairs[-10:], # 僅返回最近 10 筆交易，節省 Token
            "total_recorded_trades": len(trade_pairs),
            "validation": validation,   # bootstrap CI + walk-forward；_run_validation=False 時為 None
            # 繪圖用（給前端畫「策略在哪買、哪賣」的價格圖）。
            # 刻意與 recent_trades 分開：那個是給模型讀的摘要（省 token、只留 10 筆），
            # 這個是給圖表用的完整序列 —— 圖上少畫幾筆交易會讓人誤判策略行為。
            # 只帶 t/close（不帶 OHLCV 全欄）把體積壓到約 1/5。
            "chart_data": _chart_payload(klines, trade_pairs) if _run_validation else None,
        }
    except Exception as e:
        logger.error(f"回測執行失敗: {e}")
        return {"error": f"策略回測過程中發生異常: {str(e)}"}


def run_twitter_mention_backtest(
    symbol: str,
    screen_name: str = "elonmusk",
    keywords: Optional[List[str]] = None,
    hold_hours: int = 24,
    exchange_id: str = "binance",
    fee_rate: float = 0.001,
    slippage_rate: float = 0.001,
) -> Dict[str, Any]:
    """
    【LLM Tool】事件驅動社交回測：當指定 X/Twitter 名人發推提及特定代幣（或關鍵字）時買入，並在持有 hold_hours 小時後賣出，計算歷史績效。
    
    Args:
        symbol: 交易對符號（如 'DOGE/USDT'）
        screen_name: 追蹤的推特帳號，如 'elonmusk'
        keywords: 自定義提及關鍵字列表，如果不填，會根據 symbol 的 Base 自動代入（如 DOGE 匹配 'doge', 'dogecoin'）
        hold_hours: 買入後的持倉小時數，預設持倉 24 小時後平倉
        exchange_id: 行情獲取的交易所，預設 'binance'
        fee_rate: 單邊手續費率，預設 0.001 (0.1%)
        slippage_rate: 單邊滑價率，預設 0.001 (0.1%)；與手續費分開建模，
                       淨報酬扣除 (手續費 + 滑價) × 2
    """
    from skills.market_intel.social_scraper import fetch_twitter_user_tweets
    import email.utils

    logger.info(f"事件研究回測: 名人={screen_name}, 代幣={symbol}, 主持有期={hold_hours}h")

    # 1. 抓取名人的 X 推文
    res_tweets = fetch_twitter_user_tweets(screen_name=screen_name, limit=100)
    if "error" in res_tweets:
        return res_tweets
    tweets = res_tweets.get("tweets") or res_tweets.get("posts") or []
    if not tweets:
        return {"error": f"未找到 {screen_name} 的任何推文或目前無法解析（X 常限流）。"}

    # 2. 匹配關鍵字
    base = symbol.split("/")[0].upper()
    terms = {base.lower()}
    terms |= set({"DOGE": ["dogecoin", "doge"], "BTC": ["bitcoin", "btc"],
                  "ETH": ["ethereum", "ether", "eth"]}.get(base, []))
    if keywords:
        terms |= {k.lower() for k in keywords}

    # 3. 找出提及事件（以推文 created_at 為事件時間）
    events = []
    for t in tweets:
        txt = (t.get("text") or "").lower()
        if any(term in txt for term in terms):
            try:
                dt = email.utils.parsedate_to_datetime(t.get("created_at"))
                events.append({"ts": int(dt.timestamp() * 1000), "time": dt.isoformat(),
                               "text": (t.get("text") or "")[:140]})
            except Exception:  # noqa: BLE001
                continue
    matched = len(events)
    if not events:
        return {"message": f"未在 {screen_name} 近期推文中找到提及 '{base}' 的內容。",
                "matched_events_count": 0}

    # 4. 原始 K 線（1h）— 標的 + BTC 基準（用於異常報酬）
    def _raw_klines(sym: str):
        from skills.market_data.ccxt_fetcher import _create_exchange, _normalize_symbol
        import ccxt
        try:
            return _create_exchange(exchange_id).fetch_ohlcv(_normalize_symbol(sym), timeframe="1h", limit=1000)
        except (ccxt.BaseError, Exception):  # noqa: BLE001
            return None

    sym_k = _raw_klines(symbol)
    if not sym_k or len(sym_k) < 50:
        return {"error": f"{symbol} 的 1h 歷史 K 線不足，無法回測。"}
    dfp = pd.DataFrame(sym_k, columns=["ts", "open", "high", "low", "close", "vol"])
    dfp["ts"] = dfp["ts"].astype(np.int64)

    is_btc = base == "BTC"
    dfb = None
    if not is_btc:
        bench_k = _raw_klines("BTC/USDT")
        if bench_k:
            dfb = pd.DataFrame(bench_k, columns=["ts", "open", "high", "low", "close", "vol"])
            dfb["ts"] = dfb["ts"].astype(np.int64)

    cov_start, cov_end = int(dfp["ts"].iloc[0]), int(dfp["ts"].iloc[-1])

    def _bench_ret(entry_ts: int, exit_ts: int):
        """BTC 基準在同一時間窗的（毛）報酬%。無基準回 None。"""
        if dfb is None:
            return None
        e = dfb.index[dfb["ts"] >= entry_ts]
        x = dfb.index[dfb["ts"] >= exit_ts]
        if not len(e) or not len(x):
            return None
        ep, xp = float(dfb.loc[e[0], "open"]), float(dfb.loc[x[0], "close"])
        return (xp - ep) / ep * 100 if ep else None

    try:
        hold_hours = max(1, int(hold_hours))   # 夾限：負/非法值會產生負索引導致 KeyError
    except (TypeError, ValueError):
        hold_hours = 24
    horizons = sorted({1, 4, hold_hours})
    per_h = {h: [] for h in horizons}       # 異常報酬（或無基準時的淨報酬）
    per_h_raw = {h: [] for h in horizons}   # 淨報酬
    used, dropped_outside = 0, 0
    sample_trades = []

    for ev in events:
        after = dfp.index[dfp["ts"] > ev["ts"]]   # 嚴格『推文之後』的下一根 → 用開盤進場，杜絕前視
        # 事件落在價格窗『之前』(ts<cov_start) 也要丟棄：否則 after[0]==0 會污染成『在第一根進場』的假事件
        if not len(after) or ev["ts"] < cov_start:
            if ev["ts"] < cov_start or ev["ts"] > cov_end:
                dropped_outside += 1
            continue
        ei = int(after[0])
        entry_ts, entry_price = int(dfp.loc[ei, "ts"]), float(dfp.loc[ei, "open"])
        row, any_h = {"tweet_time": ev["time"], "text": ev["text"],
                      "entry_open_price": round(entry_price, 8), "by_horizon": {}}, False
        for h in horizons:
            xi = ei + h
            if xi < 0 or xi >= len(dfp):
                continue
            exit_ts, exit_price = int(dfp.loc[xi, "ts"]), float(dfp.loc[xi, "close"])
            net = (exit_price - entry_price) / entry_price * 100 - (fee_rate + slippage_rate) * 2 * 100
            br = _bench_ret(entry_ts, exit_ts)
            abn = net - br if br is not None else net
            per_h_raw[h].append(net)
            per_h[h].append(abn)
            row["by_horizon"][f"{h}h"] = {"net_return_pct": round(net, 3),
                                          "abnormal_vs_btc_pct": round(abn, 3) if br is not None else None}
            any_h = True
        if any_h:
            used += 1
            if len(sample_trades) < 8:
                sample_trades.append(row)

    if used == 0:
        return {"error": "所有提及事件都落在價格資料涵蓋範圍外（僅約 41 天 1h 資料），無法回測。",
                "matched_events_count": matched, "events_outside_price_window": dropped_outside}

    def _agg(vals):
        a = np.array(vals, dtype=float)
        return {"n": int(a.size), "mean_pct": round(float(a.mean()), 3),
                "median_pct": round(float(np.median(a)), 3),
                "win_rate_pct": round(float((a > 0).mean() * 100), 1),
                "std_pct": round(float(a.std(ddof=1)), 3) if a.size > 1 else None}

    by_horizon = {f"{h}h": {"net": _agg(per_h_raw[h]),
                            "abnormal_vs_btc": (_agg(per_h[h]) if not is_btc else None)}
                  for h in horizons if per_h[h]}

    # 5. 排列檢定：把 N 次事件的平均（異常）報酬 vs『隨機進場』的分布，得 two-sided p 值
    perm = None
    prim = hold_hours
    if per_h.get(prim):
        observed = float(np.mean(per_h[prim]))
        rng = np.random.default_rng(42)  # 固定種子 → 結果可重現
        valid = np.arange(0, len(dfp) - prim)
        n = len(per_h[prim])
        null_means = np.empty(1000)
        for k in range(1000):
            idxs = rng.choice(valid, size=n, replace=True)
            rr = []
            for j in idxs:
                ep, xp = float(dfp.loc[j, "open"]), float(dfp.loc[j + prim, "close"])
                net = (xp - ep) / ep * 100 - (fee_rate + slippage_rate) * 2 * 100
                br = _bench_ret(int(dfp.loc[j, "ts"]), int(dfp.loc[j + prim, "ts"]))
                rr.append(net - br if br is not None else net)
            null_means[k] = np.mean(rr)
        p_val = round(float((np.abs(null_means) >= abs(observed)).mean()), 3)
        perm = {"metric": "abnormal_vs_btc" if not is_btc else "net_return",
                "observed_mean_pct": round(observed, 3), "p_value_two_sided": p_val,
                "null_samples": 1000}

    # 6. 誠實結論
    notes = []
    if used < 10:
        notes.append(f"⚠️ 樣本過小 (N={used})，結論僅為軼事，不足以證明統計顯著性；名人真正撼動市場的事件本就只有數十個、方差極大。")
    if perm:
        p = perm["p_value_two_sided"]
        if p > 0.1:
            notes.append(f"排列檢定 p={p}：與『隨機時點進場』無統計顯著差異 — 此 edge 很可能是運氣。")
        elif p <= 0.05:
            notes.append(f"排列檢定 p={p}：在此樣本上顯著異於隨機，但仍需更多樣本與『樣本外』驗證。")
        else:
            notes.append(f"排列檢定 p={p}：僅為弱訊號。")
    notes.append("方法：進場採『推文後下一根 K 線開盤』以杜絕前視偏誤；" +
                 ("報酬已扣除 BTC 大盤同窗表現（異常報酬）。" if not is_btc else "標的為 BTC，無大盤基準可扣，僅列淨報酬。"))
    notes.append("注意：模型不得用預訓練記憶（已知 2021-2024 行情）為此區間背書；社群訊號僅佐證，不自動觸發交易。")

    return {
        "screen_name": screen_name,
        "target_symbol": symbol,
        "benchmark": None if is_btc else "BTC/USDT",
        "search_terms": sorted(terms),
        "matched_events_count": matched,
        "events_used": used,
        "events_outside_price_window": dropped_outside,
        "price_coverage": {
            "from": pd.to_datetime(cov_start, unit="ms").isoformat(),
            "to": pd.to_datetime(cov_end, unit="ms").isoformat(),
            "candles": len(dfp), "timeframe": "1h",
        },
        "primary_horizon_h": prim,
        "by_horizon": by_horizon,
        "permutation_test": perm,
        "honesty_notes": notes,
        "sample_trades": sample_trades,
    }



def backtest_treasury_impact(ticker: Optional[str] = None, hold_days: int = 7,
                             min_btc: float = 100.0, exchange_id: str = "binance") -> Dict[str, Any]:
    """（相容包裝）企業財庫增持 → 價格 事件回測。內部改走通用 run_signal_backtest 引擎，
    企業增持只是諸多可組合訊號之一。"""
    from skills.analytics.event_study import run_signal_backtest
    return run_signal_backtest("treasury_accumulation", asset="BTC", hold_days=hold_days,
                               ticker=ticker, threshold=min_btc)

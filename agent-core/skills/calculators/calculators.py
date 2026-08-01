"""
skills/calculators/calculators.py

小白實用計算機技能 (Beginner Calculators)
=============================================
一組「純函數、可靠、可測」的理財試算工具，讓大腦在回答新手問題時
可以給出精確數字，而不是含糊估計。全部不依賴任何外部 API。

包含：
  - calculate_dca            : 定期定額（DCA）回溯試算
  - calculate_position_size  : 依風險比例計算合理下單數量（現貨）
  - calculate_pnl            : 損益 / 報酬率 / 保本價試算
  - calculate_average_down   : 加碼攤平後的新平均成本試算
  - calculate_target_sell_price : 想賺 X% 淨報酬該賣在多少（含來回手續費）

費率預設 0.001 (0.15% 吃單保守值可傳 0.0015；MAX 掛單 0.0005)。
所有金額單位由呼叫端自訂（TWD 或 USDT 皆可），函數只做數學。
"""

from typing import Any, Dict, List, Optional, Union

Number = Union[int, float]


def _r(x: Number, nd: int = 2) -> float:
    """四捨五入到 nd 位，避免浮點雜訊。"""
    try:
        return round(float(x), nd)
    except (TypeError, ValueError):
        return 0.0


def _err(msg: str) -> Dict[str, Any]:
    return {"error": msg}


def _num(x: Any) -> Optional[float]:
    """
    寬鬆地把輸入轉成 float。小型 LLM 常把數字傳成字串（"100000"）、帶逗號（"1,000,000"）、
    帶貨幣符號（"NT$50000"），甚至傳未替換的樣板佔位（"{{current_btc_price}}"）。
    能轉就回 float；無法辨識則回 None（讓呼叫端給出友善錯誤，而不是拋 TypeError）。
    """
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        s = x.strip().replace(",", "").replace("_", "").replace("$", "").replace("＄", "").replace("NT", "")
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _fee(x: Any, default: float = 0.001) -> float:
    """手續費率容錯：非數字時回退預設值。"""
    v = _num(x)
    return default if v is None else v


# ──────────────────────────────────────────────
#  1. 定期定額 DCA 回溯試算
# ──────────────────────────────────────────────
def calculate_dca(
    amount_per_period: Number,
    prices: List[Number],
    fee_rate: Number = 0.001,
    current_price: Optional[Number] = None,
) -> Dict[str, Any]:
    """
    【LLM Tool】定期定額 (Dollar-Cost Averaging) 回溯試算。

    模擬「每一期投入固定金額」在給定的一串歷史價格上分批買入，
    計算累積數量、平均成本、總手續費，並（若提供現價）計算目前損益，
    同時對比「一次全部買在第一期」的單筆投入結果。
    """
    amount_per_period = _num(amount_per_period)
    fee_rate = _fee(fee_rate)
    current_price = _num(current_price)
    if not isinstance(prices, list):
        prices = [prices] if prices is not None else []
    prices = [_num(p) for p in prices]
    if amount_per_period is None or amount_per_period <= 0:
        return _err("amount_per_period（每期投入金額）必須是大於 0 的數字")
    if not prices:
        return _err("prices 必須是至少一個價格的清單，例如 [900000, 950000, 1010000]")
    if any((p is None or p <= 0) for p in prices):
        return _err("prices 內所有價格都必須是大於 0 的數字")
    if fee_rate < 0 or fee_rate >= 1:
        return _err("fee_rate 應介於 0 與 1 之間（例如 0.001 = 0.1%）")

    periods = len(prices)
    total_invested = amount_per_period * periods
    total_fees = 0.0
    total_units = 0.0
    for p in prices:
        fee = amount_per_period * fee_rate
        net_spent = amount_per_period - fee
        total_fees += fee
        total_units += net_spent / p

    avg_cost = total_invested / total_units if total_units else 0.0

    result: Dict[str, Any] = {
        "periods": periods,
        "amount_per_period": _r(amount_per_period),
        "fee_rate": fee_rate,
        "total_invested": _r(total_invested),
        "total_fees": _r(total_fees),
        "total_units": _r(total_units, 8),
        "average_cost": _r(avg_cost),
    }

    # 單筆投入（lump-sum）對比：把全部資金一次買在第一期價格
    lump_units = (total_invested * (1 - fee_rate)) / prices[0]

    if current_price is not None and current_price > 0:
        cur_value = total_units * current_price
        pnl = cur_value - total_invested
        roi = (pnl / total_invested * 100) if total_invested else 0.0
        result.update({
            "current_price": _r(current_price),
            "current_value": _r(cur_value),
            "pnl": _r(pnl),
            "roi_pct": _r(roi),
        })
        lump_value = lump_units * current_price
        lump_pnl = lump_value - total_invested
        result["lump_sum_comparison"] = {
            "note": "若把同樣總金額一次買在第一期價格",
            "units": _r(lump_units, 8),
            "current_value": _r(lump_value),
            "pnl": _r(lump_pnl),
            "roi_pct": _r((lump_pnl / total_invested * 100) if total_invested else 0.0),
        }
        winner = "定期定額" if pnl >= lump_pnl else "單筆投入"
        result["summary"] = (
            f"分 {periods} 期共投入 {_r(total_invested):,.0f}，累積 {_r(total_units, 6)} 顆，"
            f"平均成本 {_r(avg_cost):,.2f}。以現價 {_r(current_price):,.2f} 計，"
            f"目前{'獲利' if pnl >= 0 else '虧損'} {_r(abs(pnl)):,.0f}（{_r(roi):+.2f}%）。"
            f"此情境下【{winner}】表現較好。"
        )
    else:
        result["summary"] = (
            f"分 {periods} 期共投入 {_r(total_invested):,.0f}，累積 {_r(total_units, 6)} 顆，"
            f"平均成本 {_r(avg_cost):,.2f}（含手續費 {_r(total_fees):,.0f}）。"
            "傳入 current_price 可再算目前損益與單筆投入對比。"
        )
    return result


# ──────────────────────────────────────────────
#  2. 部位大小 / 風險控管計算（現貨）
# ──────────────────────────────────────────────
def calculate_position_size(
    account_balance: Number,
    risk_pct: Number,
    entry_price: Number,
    stop_loss_price: Number,
    fee_rate: Number = 0.001,
) -> Dict[str, Any]:
    """
    【LLM Tool】依「單筆最多虧損總資金的百分之幾」反推合理下單數量（現貨、不含槓桿）。

    這是新手最該學的風控：先決定「這筆最多能虧多少」，再由停損距離反推能買幾顆。
    """
    account_balance = _num(account_balance)
    risk_pct = _num(risk_pct)
    entry_price = _num(entry_price)
    stop_loss_price = _num(stop_loss_price)
    fee_rate = _fee(fee_rate)
    if account_balance is None or account_balance <= 0:
        return _err("account_balance（總資金）必須是大於 0 的數字")
    if risk_pct is None or risk_pct <= 0 or risk_pct > 100:
        return _err("risk_pct（單筆風險%）必須是 0 到 100 的數字，建議 1~2")
    if entry_price is None or entry_price <= 0:
        return _err("entry_price（進場價）必須是大於 0 的數字。若要用目前市價，請先查行情拿到實際數字再帶入，不要傳佔位字串。")
    if stop_loss_price is None or stop_loss_price <= 0:
        return _err("stop_loss_price（停損價）必須是大於 0 的數字")
    if stop_loss_price >= entry_price:
        return _err("現貨做多情境下，stop_loss_price（停損價）必須低於 entry_price（進場價）")

    risk_amount = account_balance * (risk_pct / 100.0)
    per_unit_risk = entry_price - stop_loss_price
    units = risk_amount / per_unit_risk
    position_value = units * entry_price
    stop_distance_pct = per_unit_risk / entry_price * 100

    note = "部位大小由風險反推，符合現貨本金限制。"
    capped = False
    if position_value > account_balance:
        # 現貨不能借錢，部位不可超過本金
        capped = True
        units = (account_balance * (1 - fee_rate)) / entry_price
        position_value = units * entry_price
        actual_risk = units * per_unit_risk
        note = (
            f"⚠️ 依風險反推的部位（{_r(risk_amount / per_unit_risk * entry_price):,.0f}）已超過本金，"
            f"現貨無法加槓桿，已改為『全押本金』。此時實際最大虧損約 {_r(actual_risk):,.0f}，"
            f"低於你設定的風險上限，代表你的停損距離偏大或風險%偏小。"
        )

    return {
        "account_balance": _r(account_balance),
        "risk_pct": risk_pct,
        "max_loss_if_stopped": _r(risk_amount if not capped else units * per_unit_risk),
        "entry_price": _r(entry_price),
        "stop_loss_price": _r(stop_loss_price),
        "stop_distance_pct": _r(stop_distance_pct),
        "suggested_units": _r(units, 8),
        "position_value": _r(position_value),
        "position_pct_of_balance": _r(position_value / account_balance * 100),
        "note": note,
        "summary": (
            f"總資金 {_r(account_balance):,.0f}，單筆願承受 {risk_pct}% 風險（約 {_r(risk_amount):,.0f}）。"
            f"進場 {_r(entry_price):,.2f}、停損 {_r(stop_loss_price):,.2f}（跌 {_r(stop_distance_pct):.2f}%），"
            f"建議買約 {_r(units, 6)} 顆，部位價值 {_r(position_value):,.0f}。"
        ),
    }


# ──────────────────────────────────────────────
#  3. 損益 / 報酬率 / 保本價
# ──────────────────────────────────────────────
def calculate_pnl(
    entry_price: Number,
    exit_price: Number,
    volume: Number,
    side: str = "buy",
    fee_rate: Number = 0.001,
) -> Dict[str, Any]:
    """
    【LLM Tool】計算一筆交易的損益、報酬率與保本價（含買賣來回手續費）。
    side 可為 buy/long（做多、現貨）或 sell/short（做空）。
    """
    entry_price = _num(entry_price)
    exit_price = _num(exit_price)
    volume = _num(volume)
    fee_rate = _fee(fee_rate)
    if entry_price is None or entry_price <= 0:
        return _err("entry_price 必須是大於 0 的數字")
    if exit_price is None or exit_price <= 0:
        return _err("exit_price 必須是大於 0 的數字")
    if volume is None or volume <= 0:
        return _err("volume（數量）必須是大於 0 的數字")
    s = (side or "buy").lower()
    if s not in ("buy", "long", "sell", "short"):
        return _err("side 必須是 buy/long 或 sell/short")

    is_long = s in ("buy", "long")
    cost = entry_price * volume
    entry_fee = cost * fee_rate
    exit_fee = exit_price * volume * fee_rate
    gross = (exit_price - entry_price) * volume if is_long else (entry_price - exit_price) * volume
    net = gross - entry_fee - exit_fee
    roi = net / cost * 100 if cost else 0.0
    # 保本價（做多）：賣出淨額 = 買入含費成本
    breakeven = entry_price * (1 + fee_rate) / (1 - fee_rate) if is_long else entry_price * (1 - fee_rate) / (1 + fee_rate)

    return {
        "side": "做多/現貨" if is_long else "做空",
        "entry_price": _r(entry_price),
        "exit_price": _r(exit_price),
        "volume": _r(volume, 8),
        "cost": _r(cost),
        "total_fees": _r(entry_fee + exit_fee),
        "gross_pnl": _r(gross),
        "net_pnl": _r(net),
        "roi_pct": _r(roi),
        "breakeven_price": _r(breakeven),
        "summary": (
            f"{'做多' if is_long else '做空'} {_r(volume, 6)} 顆，進 {_r(entry_price):,.2f} 出 {_r(exit_price):,.2f}，"
            f"扣掉手續費 {_r(entry_fee + exit_fee):,.2f} 後淨{'賺' if net >= 0 else '賠'} {_r(abs(net)):,.2f}"
            f"（{_r(roi):+.2f}%）。保本價約 {_r(breakeven):,.2f}。"
        ),
    }


# ──────────────────────────────────────────────
#  4. 加碼攤平後新平均成本
# ──────────────────────────────────────────────
def calculate_average_down(
    current_units: Number,
    current_avg_cost: Number,
    add_price: Number,
    add_amount: Optional[Number] = None,
    add_units: Optional[Number] = None,
    fee_rate: Number = 0.001,
) -> Dict[str, Any]:
    """
    【LLM Tool】試算「再買一筆（加碼/攤平）」之後的新平均成本。
    add_amount（要再投入的金額）與 add_units（要再買的數量）擇一提供。
    """
    current_units = _num(current_units)
    current_avg_cost = _num(current_avg_cost)
    add_price = _num(add_price)
    add_amount = _num(add_amount)
    add_units = _num(add_units)
    fee_rate = _fee(fee_rate)
    if current_units is None or current_units < 0:
        return _err("current_units（目前持有數量）必須是不小於 0 的數字")
    if current_avg_cost is None or current_avg_cost <= 0:
        return _err("current_avg_cost（目前平均成本）必須是大於 0 的數字")
    if add_price is None or add_price <= 0:
        return _err("add_price（加碼價格）必須是大於 0 的數字")

    if add_amount is not None and add_amount > 0:
        money_added = add_amount
        units_added = (add_amount * (1 - fee_rate)) / add_price
    elif add_units is not None and add_units > 0:
        units_added = add_units
        money_added = add_units * add_price * (1 + fee_rate)
    else:
        return _err("請提供 add_amount（加碼金額）或 add_units（加碼數量）其中之一")

    prev_cost_total = current_units * current_avg_cost
    new_units = current_units + units_added
    new_avg = (prev_cost_total + money_added) / new_units if new_units else 0.0
    drop_pct = (current_avg_cost - new_avg) / current_avg_cost * 100 if current_avg_cost else 0.0

    return {
        "before": {"units": _r(current_units, 8), "avg_cost": _r(current_avg_cost)},
        "add": {"price": _r(add_price), "units_added": _r(units_added, 8), "money_added": _r(money_added)},
        "after": {"units": _r(new_units, 8), "avg_cost": _r(new_avg)},
        "avg_cost_drop_pct": _r(drop_pct),
        "summary": (
            f"原本 {_r(current_units, 6)} 顆、均價 {_r(current_avg_cost):,.2f}；"
            f"以 {_r(add_price):,.2f} 再買 {_r(units_added, 6)} 顆後，"
            f"新均價降到 {_r(new_avg):,.2f}（下降 {_r(drop_pct):.2f}%）。"
            "提醒：攤平只是降低均價，並不代表這筆投資變好，仍要看基本面與趨勢。"
        ),
    }


# ──────────────────────────────────────────────
#  5. 目標賣出價（想賺 X% 淨報酬）
# ──────────────────────────────────────────────
def calculate_target_sell_price(
    entry_price: Number,
    target_net_roi_pct: Number,
    fee_rate: Number = 0.001,
) -> Dict[str, Any]:
    """
    【LLM Tool】想要拿到指定「淨報酬率」（已扣買賣來回手續費），該賣在多少價位。
    """
    entry_price = _num(entry_price)
    target_net_roi_pct = _num(target_net_roi_pct)
    fee_rate = _fee(fee_rate)
    if entry_price is None or entry_price <= 0:
        return _err("entry_price 必須是大於 0 的數字")
    if target_net_roi_pct is None:
        return _err("target_net_roi_pct（目標淨報酬%）必填且需為數字，例如 10 代表 +10%")
    if fee_rate < 0 or fee_rate >= 1:
        return _err("fee_rate 應介於 0 與 1 之間")

    target = target_net_roi_pct / 100.0
    # 每 1 顆：買入含費成本 = entry*(1+fee)；賣出淨額 = sell*(1-fee)
    # 令 (sell*(1-fee) - entry*(1+fee)) / (entry*(1+fee)) = target
    sell = entry_price * (1 + fee_rate) * (1 + target) / (1 - fee_rate)
    rise_pct = (sell - entry_price) / entry_price * 100

    return {
        "entry_price": _r(entry_price),
        "target_net_roi_pct": target_net_roi_pct,
        "fee_rate": fee_rate,
        "target_sell_price": _r(sell),
        "required_price_rise_pct": _r(rise_pct),
        "summary": (
            f"進場價 {_r(entry_price):,.2f}，想淨賺 {target_net_roi_pct}%（已含來回手續費），"
            f"需賣在約 {_r(sell):,.2f}，即價格要漲約 {_r(rise_pct):.2f}%。"
        ),
    }

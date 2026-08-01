"""交易 DNA 面板（csv_source / equity_curve / dna_score / counterfactual）。

這批模組是從 `backend/maia/` 搬過來的，搬遷時修掉了兩個 bug。因此測試分三類：

1. **等價性錨點**：搬遷不能改變數字。關鍵數值直接寫死，來自搬遷前
   `python backend/analyze.py` 的實跑輸出（同一個 Python 直譯器下比對過 48 項全等）。
2. **修正 1 · 六軸不再飽和**：舊版線性 clamp 讓「活躍度 100.0 / 紀律 0.0」貼死量表兩端。
3. **修正 2 · capital_feasible**：舊版宣稱續抱多賺 2,693 萬，卻沒問「那筆錢拿得出來嗎」。
   續抱要 5,963 萬本金同時在場，是帳戶淨投入本金 2,427 萬的 2.46 倍 —— 旗標與 caveat
   就是不讓那句話被當成隨手可引用的絕對金額。
   ⚠️ 分子曾經算錯：把**入金取得的幣**（免費的，佔 73%）也當本金，得到 2.23 億 / 9.21×
   / False。這裡用等號釘死分子的定義，不是只鎖一個不等式，就是為了不讓它再漂回去。
4. **樣本閘門**：零交易帳本不得產出 archetype（live demo 最危險的情境）。
"""
import os

import pytest

from skills.analytics import counterfactual as cf
from skills.analytics import csv_source as cs
from skills.analytics import dna_score as ds
from skills.analytics import equity_curve as ec

# 搬遷前 backend/analyze.py 的實跑輸出（主辦提供的合成 CSV）
EXPECTED_ROWS = 10_000
EXPECTED_INCONSISTENT = 797
EXPECTED_TRADES = 4674
EXPECTED_ARCHETYPE = "高頻無 alpha 交易者"
EXPECTED_SELL_VS_HOLD = 26_598_877.24
EXPECTED_HOLD_NETWORTH = 267_137_035.55
EXPECTED_ACTIVE_COST = 26_937_347.22
EXPECTED_REALIZED_PNL = 253_449.05
EXPECTED_MARKET_VALUE = 1_638_513.55
EXPECTED_NET_CAPITAL = 24_274_547.0
EXPECTED_DAILY_POINTS = 365
# 續抱所需本金＝全期**買進**累計（直接讀 CSV 加總複驗過）。
# 入金取得的幣市值另有 163,860,721.36，兩者相加 223,487,907.26 就是舊版算錯的那個分子。
EXPECTED_HOLD_CAPITAL = 59_627_185.91
EXPECTED_ACTUAL_PEAK = 79_775.51      # 實際壓在買進上的峰值 TWD（買進 − 賣出回收）

_HAS_CSV = os.path.exists(cs.DEFAULT_DEMO_CSV)
needs_csv = pytest.mark.skipif(not _HAS_CSV, reason="主辦 CSV 不在 data_set/（例如只部署 agent-core）")


@pytest.fixture(scope="module")
def events():
    return cs.load_csv_events()


@pytest.fixture(scope="module")
def snap(events):
    return ec.replay_events(events)


# ── csv_source ────────────────────────────────────────────────
@needs_csv
def test_csv_loads_exact_row_count(events):
    """主辦那份 CSV 是 10,000 筆——少一筆都代表解析漏了列。"""
    assert len(events) == EXPECTED_ROWS


@needs_csv
def test_events_match_position_ledger_shape(events):
    """事件形狀要對得上 position_ledger.fetch_events()，否則下游模組沒辦法兩種來源共用。"""
    ledger_keys = {"uid", "ts", "source", "currency", "delta",
                   "disposal", "price", "quote", "quote_amount", "note"}
    for e in events[:50]:
        assert ledger_keys <= set(e), f"缺少帳本欄位：{ledger_keys - set(e)}"
        assert e["currency"] == e["currency"].upper()     # 對齊 _ev() 的大寫慣例
        assert isinstance(e["disposal"], bool)
    # 賣出＝處分、買入不是；買賣都要帶得出 TWD 對手腿資訊
    sells = [e for e in events if e["source"] == "trade" and e["delta"] < 0]
    buys = [e for e in events if e["source"] == "trade" and e["delta"] > 0]
    assert sells and buys
    assert all(e["disposal"] for e in sells)
    assert not any(e["disposal"] for e in buys)
    assert all(e["quote"] == "TWD" for e in sells + buys)


@needs_csv
def test_data_health_discloses_synthetic_data(events):
    """CSV 是合成資料，餘額欄對不上是事實——健檢要把它講出來而不是藏起來。"""
    h = cs.data_health(events)
    assert h["count"] == EXPECTED_ROWS
    assert h["balance_inconsistent_rows"] == EXPECTED_INCONSISTENT
    assert h["time_start"].startswith("2025-01-01")
    assert h["time_end"].startswith("2025-12-31")
    assert h["actions"]["buy"] + h["actions"]["sell"] == EXPECTED_TRADES


def test_path_is_a_parameter_not_hardcoded(tmp_path, monkeypatch):
    """資料源已改成『可換』：參數 > 環境變數 > 內建示範帳戶，路徑不寫死。"""
    assert cs.resolve_csv_path("/x/y.csv") == "/x/y.csv"
    monkeypatch.setenv("MAIA_DEMO_CSV", "/from/env.csv")
    assert cs.resolve_csv_path() == "/from/env.csv"
    assert cs.resolve_csv_path("/wins.csv") == "/wins.csv"
    monkeypatch.delenv("MAIA_DEMO_CSV")
    assert cs.resolve_csv_path() == cs.DEFAULT_DEMO_CSV


def test_missing_columns_are_rejected_loudly(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("timestamp,currency,price\n1,twd,1.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="缺少必要欄位"):
        cs.load_csv_events(str(bad))


def test_empty_health_does_not_crash():
    assert cs.data_health([])["count"] == 0


# ── equity_curve ──────────────────────────────────────────────
@needs_csv
def test_replay_reproduces_pre_migration_numbers(snap):
    """等價性錨點：搬遷不能改變帳務數字。"""
    assert round(snap["total_realized_pnl_twd"], 2) == EXPECTED_REALIZED_PNL
    assert round(snap["total_market_value_twd"], 2) == EXPECTED_MARKET_VALUE
    assert round(snap["twd_deposit"] - snap["twd_withdrawal"], 2) == EXPECTED_NET_CAPITAL
    assert snap["missing_price_events"] == 0        # CSV 每列自帶 TWD 單價 → 零網路
    assert len(snap["points"]) == EXPECTED_ROWS     # 每一筆事件後都記一點


@needs_csv
def test_daily_downsample_is_one_point_per_day(snap):
    daily = ec.downsample_daily(snap["points"])
    assert len(daily) == EXPECTED_DAILY_POINTS
    dates = [p["date"] for p in daily]
    assert dates == sorted(dates) and len(set(dates)) == len(dates)
    assert daily[0]["date"] == "2025-01-01" and daily[-1]["date"] == "2025-12-31"
    assert round(daily[-1]["value_twd"], 2) == EXPECTED_MARKET_VALUE


def test_replay_flags_missing_prices_instead_of_inventing_them():
    """真實 MAX 帳本的事件沒有 TWD 單價；查不到就要誠實計數，不能亂編價格。"""
    evs = [{"uid": "a", "ts": 1, "source": "deposit", "currency": "BTC",
            "delta": 1.0, "disposal": False, "price": None}]
    snap = ec.replay_events(evs)
    assert snap["missing_price_events"] == 1
    # 有價格查詢器就用它（真實帳本走 lot_engine.twd_price_at）
    snap2 = ec.replay_events(evs, price_lookup=lambda cur, ts: 100.0)
    assert snap2["missing_price_events"] == 0
    assert snap2["per_currency"]["BTC"]["market_value_twd"] == 100.0


def test_oversell_goes_to_unmatched_not_zero_cost():
    """賣超過可追溯批次時不硬湊零成本（與 lot_engine 同原則：寧可少算也不虛報獲利）。"""
    evs = [
        {"uid": "b", "ts": 1, "source": "trade", "currency": "BTC", "delta": 1.0,
         "disposal": False, "price": 100.0},
        {"uid": "s", "ts": 2, "source": "trade", "currency": "BTC", "delta": -3.0,
         "disposal": True, "price": 200.0},
    ]
    snap = ec.replay_events(evs)
    assert snap["per_currency"]["BTC"]["unmatched_qty"] == pytest.approx(2.0)
    assert snap["per_currency"]["BTC"]["realized_pnl_twd"] == pytest.approx(100.0)


# ── dna_score：修正 1（兩端飽和）────────────────────────────────
@needs_csv
def test_no_axis_saturates_at_zero_or_hundred(events, snap):
    """修正 1 的核心回歸：舊版實跑是「活躍度 100.0 / 紀律 0.0」，兩軸貼死量表兩端。"""
    scores = ds.compute_dna_scores(ds.behavior_metrics(events, snap))
    assert set(scores) == set(ds.AXES)
    for axis, v in scores.items():
        assert v != 0.0 and v != 100.0, f"{axis} 又貼死在量表端點：{v}"
        assert ds.SCORE_FLOOR <= v <= ds.SCORE_CEIL, f"{axis}={v} 超出 5–95"


@pytest.mark.parametrize("metrics", [
    {},                                                        # 全零
    {"trades_per_month": 1e9, "trades_per_active_day": 1e9,    # 荒謬地大
     "timing_skill": 50.0, "holdings_hhi": 1.0,
     "avg_hold_days": 1e9, "top_asset_weight": 1.0, "stable_ratio": 1.0,
     "chase_high_rate": 1.0},
    {"trades_per_month": -5, "trades_per_active_day": -5,      # 負值
     "timing_skill": -50.0, "holdings_hhi": -1.0,
     "avg_hold_days": -5, "top_asset_weight": -1.0, "stable_ratio": -1.0,
     "chase_high_rate": -1.0},
])
def test_logistic_never_saturates_even_on_absurd_inputs(metrics):
    """logistic 的漸近線是 5/95：任何極端輸入都不該炸掉、也不該跑到 0 或 100。"""
    for axis, v in ds.compute_dna_scores(metrics).items():
        assert ds.SCORE_FLOOR <= v <= ds.SCORE_CEIL, f"{axis}={v}"
        assert v not in (0.0, 100.0)


def test_logistic_midpoint_is_fifty():
    """校準常數的語意：MID 對應 50 分，才有辦法用真實帳本的中位數重新校準。"""
    mid = (ds.SCORE_FLOOR + ds.SCORE_CEIL) / 2
    assert ds.compute_dna_scores(
        {"trades_per_month": ds.ACTIVITY_MID_TRADES_PER_MONTH})["活躍度"] == pytest.approx(mid)
    assert ds.compute_dna_scores(
        {"trades_per_active_day": ds.DISCIPLINE_MID_TRADES_PER_ACTIVE_DAY})["紀律"] == pytest.approx(mid)
    assert ds.compute_dna_scores({"timing_skill": 0.0})["擇時"] == pytest.approx(mid)
    assert ds.compute_dna_scores(
        {"avg_hold_days": ds.PATIENCE_MID_HOLD_DAYS})["持有耐心"] == pytest.approx(mid)


def test_discipline_and_patience_point_the_right_way():
    """方向性：交易越頻繁紀律越低、抱越久耐心越高。改係數時這條會擋住符號寫反。"""
    calm = ds.compute_dna_scores({"trades_per_active_day": 1.0})["紀律"]
    frantic = ds.compute_dna_scores({"trades_per_active_day": 20.0})["紀律"]
    assert calm > frantic
    assert (ds.compute_dna_scores({"avg_hold_days": 90})["持有耐心"]
            > ds.compute_dna_scores({"avg_hold_days": 1})["持有耐心"])


@needs_csv
def test_archetype_matches_pre_migration(events, snap):
    m = ds.behavior_metrics(events, snap)
    archetype, tags = ds.derive_archetype(m)
    assert archetype == EXPECTED_ARCHETYPE
    assert "過度交易" in tags and "擇時與隨機無異" in tags
    assert m["trade_count"] == EXPECTED_TRADES
    assert round(m["avg_hold_days"], 1) == 2.7


def test_zero_trade_ledger_must_not_produce_an_archetype(tmp_path):
    """live demo 最危險的情境：評審當場綁一個只入金沒交易的新帳號問「我是什麼交易者」。

    舊版會憑空講出「集中押注型 · 短線持有」，六軸還給到紀律 79.9 / 分散 5.4，
    而 trade_count = 0 埋在 metrics 底下，模型根本不會去比對。
    """
    from agent.ollama_agent import TOOL_CALLABLES
    csv_path = tmp_path / "deposit_only.csv"
    csv_path.write_text(
        "timestamp,currency,price,action,change,balance\n"
        "1735690380000,twd,1.0,deposit,66770,66770\n"
        "1735790380000,btc,3000000.0,deposit,0.5,0.5\n",
        encoding="utf-8")

    out = TOOL_CALLABLES["get_trading_dna_score"](path=str(csv_path))
    assert out["metrics"]["trade_count"] == 0
    assert out["insufficient_data"] is True, "沒有旗標 → 模型不知道要說「資料不足」"
    assert out["archetype"] is None, f"零交易卻給了人格：{out['archetype']}"
    assert out["tags"] == []
    assert "無法判定交易性格" in out["note"]


def test_insufficient_data_flag_is_always_present(tmp_path):
    """旗標要**恆存在**：只有錯誤時才出現的欄位，模型不會養成檢查的習慣。"""
    from agent.ollama_agent import TOOL_CALLABLES
    empty = tmp_path / "header_only.csv"
    empty.write_text("timestamp,currency,price,action,change,balance\n", encoding="utf-8")
    assert TOOL_CALLABLES["get_trading_dna_score"](path=str(empty))["insufficient_data"] is True

    if _HAS_CSV:                                   # 資料夠的那一側必須是 False
        out = TOOL_CALLABLES["get_trading_dna_score"]()
        assert out["insufficient_data"] is False
        assert out["metrics"]["trade_count"] >= ds.MIN_TRADES_FOR_ARCHETYPE


def test_dna_schema_tells_the_model_what_insufficient_data_means():
    """旗標只有資料層有、模型端沒被告知，等於沒做。"""
    from skills.analytics.schemas import GET_TRADING_DNA_SCORE_SCHEMA
    desc = GET_TRADING_DNA_SCORE_SCHEMA["function"]["description"]
    assert "insufficient_data" in desc
    assert "不可以宣稱使用者的交易性格" in desc


def test_archetype_thresholds_are_named_constants():
    """係數必須是模組層具名常數（接真實帳本要重新校準時才改得動）。"""
    for name in ["ACTIVITY_MID_TRADES_PER_MONTH", "DISCIPLINE_MID_TRADES_PER_ACTIVE_DAY",
                 "TIMING_SCALE", "DIVERSIFICATION_MID_HHI", "PATIENCE_MID_HOLD_DAYS",
                 "RISK_CONTROL_MID", "ARCHETYPE_OVERTRADE_PER_ACTIVE_DAY",
                 "ARCHETYPE_LONG_HOLD_DAYS", "ARCHETYPE_CONCENTRATED_WEIGHT"]:
        assert isinstance(getattr(ds, name), float)
    assert "重新校準" in ds.__doc__


# ── counterfactual：修正 2（capital_feasible）────────────────────
@needs_csv
def test_sell_vs_hold_reproduces_pre_migration_numbers(events, snap):
    out = cf.run_sell_vs_hold(snap)
    assert out["sell_vs_hold_twd"] == EXPECTED_SELL_VS_HOLD
    assert out["hold_networth_twd"] == EXPECTED_HOLD_NETWORTH
    assert out["active_cost_twd"] == EXPECTED_ACTIVE_COST
    assert out["fee_rate"] == cf.DEFAULT_FEE_RATE


@needs_csv
def test_hold_capital_counts_only_what_actually_cost_money(events, snap):
    """修正 2 的核心回歸：分子＝**買進累計**，不是「所有加密流入」。

    用等號釘死而不是不等式。舊版寫 `> 3 × 淨投入本金`，等於把算錯的分子
    當成回歸基準鎖起來：日後有人把分子修對，那條會變紅，看起來像是修壞了。
    """
    out = cf.run_sell_vs_hold(snap)
    assert out["hold_capital_required_twd"] == pytest.approx(EXPECTED_HOLD_CAPITAL, rel=1e-9)
    assert out["net_capital_deployed_twd"] == EXPECTED_NET_CAPITAL
    assert out["capital_multiple_needed"] == pytest.approx(2.46, abs=0.01)
    assert out["capital_feasible"] is True     # 2.46× ≤ 3× → 資金調度上勉強在範圍內
    # 實際壓在買進上的峰值遠低於續抱所需 —— 獲利是靠周轉堆出來的
    assert out["actual_peak_capital_twd"] == pytest.approx(EXPECTED_ACTUAL_PEAK, rel=1e-9)
    assert out["actual_peak_capital_twd"] < out["hold_capital_required_twd"] / 10
    assert out["capital_turnover_x"] > 1


def test_free_deposits_do_not_inflate_the_capital_requirement():
    """外部免費轉入的幣不耗 TWD 本金 —— 把它算進分子會憑空翻轉旗標。

    這個形狀（TWD 入金 + 加密幣 deposit + 一筆很小的買進）正是舊測試集完全沒覆蓋、
    因此 32 個測試全過卻放過那個 bug 的漏洞：舊版在這裡會算出需要 1,000 萬本金
    （實際只掏 1,000 元）、capital_multiple_needed = 1000.1、feasible = False。
    """
    evs = [
        {"uid": "d0", "ts": 1, "source": "deposit", "currency": "TWD", "delta": 10_000.0,
         "disposal": False, "price": 1.0},
        {"uid": "d1", "ts": 2, "source": "deposit", "currency": "BTC", "delta": 10.0,
         "disposal": False, "price": 1_000_000.0},          # 白拿的十顆幣，一塊錢沒花
        {"uid": "b1", "ts": 3, "source": "trade", "currency": "BTC", "delta": 0.001,
         "disposal": False, "price": 1_000_000.0},          # 真正掏錢的只有這 1,000 元
        {"uid": "s1", "ts": 4, "source": "trade", "currency": "BTC", "delta": -1.0,
         "disposal": True, "price": 900_000.0},
    ]
    out = cf.run_sell_vs_hold(ec.replay_events(evs))
    assert out["hold_capital_required_twd"] == pytest.approx(1_000.0)
    assert out["capital_multiple_needed"] == pytest.approx(0.1)
    assert out["capital_feasible"] is True
    # 免費入金的幣仍然算進「續抱淨值」（它確實在手上），只是不算本金
    assert out["hold_networth_twd"] == pytest.approx(10.001 * 900_000.0)


@needs_csv
def test_caveat_still_blocks_the_headline_number_even_when_feasible(events, snap):
    """旗標 True 不等於金額可以隨口引用：倍率 > 1 就得講「要幾倍本金」。

    caveat 是最容易被 LLM 整句唸出去的欄位，限制條件必須寫在字串裡，
    不能只靠模型自律去讀另一個布林值。
    """
    out = cf.run_sell_vs_hold(snap)
    caveat = out["caveat"]
    assert out["capital_feasible"] is True
    assert isinstance(caveat, str) and len(caveat) >= 40
    assert "不要說成" in caveat and "少賺" in caveat
    assert "同時在場" in caveat
    assert "2.5 倍" in caveat                     # 倍率必須出現在字串裡
    assert f"{EXPECTED_HOLD_CAPITAL:,.0f}" in caveat   # 金額要對得上回傳欄位


def test_caveat_is_loudest_when_capital_is_truly_out_of_reach():
    """真的差太多（> 3×）時仍要出現「僅供方法學示意 / 不可當絕對金額宣稱」。"""
    evs = [
        {"uid": "d", "ts": 1, "source": "deposit", "currency": "TWD", "delta": 10_000.0,
         "disposal": False, "price": 1.0},
        {"uid": "b", "ts": 2, "source": "trade", "currency": "BTC", "delta": 1.0,
         "disposal": False, "price": 500_000.0},        # 買進 50 萬 ÷ 淨投入 1 萬 = 50×
        {"uid": "s", "ts": 3, "source": "trade", "currency": "BTC", "delta": -1.0,
         "disposal": True, "price": 400_000.0},
    ]
    out = cf.run_sell_vs_hold(ec.replay_events(evs))
    assert out["capital_feasible"] is False
    assert "僅供方法學示意" in out["caveat"]
    assert "不可當絕對金額宣稱" in out["caveat"]


def test_capital_feasible_true_when_capital_is_sufficient():
    """旗標不是永遠 False：本金足夠時要是 True，否則它沒有鑑別力。"""
    evs = [
        {"uid": "d", "ts": 1, "source": "deposit", "currency": "TWD", "delta": 1_000_000.0,
         "disposal": False, "price": 1.0},
        {"uid": "b", "ts": 2, "source": "trade", "currency": "BTC", "delta": 1.0,
         "disposal": False, "price": 100_000.0, "quote": "TWD", "quote_amount": 100_000.0},
        {"uid": "s", "ts": 3, "source": "trade", "currency": "BTC", "delta": -1.0,
         "disposal": True, "price": 120_000.0, "quote": "TWD", "quote_amount": 120_000.0},
    ]
    out = cf.run_sell_vs_hold(ec.replay_events(evs))
    assert out["capital_feasible"] is True
    assert out["hold_capital_required_twd"] == pytest.approx(100_000.0)
    assert out["net_capital_deployed_twd"] == pytest.approx(1_000_000.0)
    assert "僅供方法學示意" not in out["caveat"]
    assert "資金上做得到" in out["caveat"]     # 倍率 0.1× → 最寬鬆那一級


def test_capital_feasible_is_none_without_cash_flows():
    """沒有 TWD 出入金就算不出淨投入本金 —— 要回 None 並說明，不能瞎猜 True/False。"""
    evs = [{"uid": "b", "ts": 1, "source": "trade", "currency": "BTC", "delta": 1.0,
            "disposal": False, "price": 100.0}]
    out = cf.run_sell_vs_hold(ec.replay_events(evs))
    assert out["capital_feasible"] is None
    assert out["capital_turnover_x"] is None
    assert "無法判定資本可行性" in out["caveat"]


# ── 工具註冊與呼叫 ─────────────────────────────────────────────
TOOL_NAMES = ["load_demo_account_ledger", "get_equity_curve",
              "get_trading_dna_score", "compare_sell_vs_hold"]


def test_tools_are_registered_with_schema_and_callable():
    from agent.ollama_agent import TOOL_CALLABLES
    from agent.prompts import ALL_TOOLS
    names = [t["function"]["name"] for t in ALL_TOOLS]
    assert len(names) == len(set(names)), "ALL_TOOLS 有重複的工具名稱"
    for n in TOOL_NAMES:
        assert n in names, f"{n} 未註冊進 ALL_TOOLS"
        assert n in TOOL_CALLABLES and callable(TOOL_CALLABLES[n]), f"{n} 沒有可呼叫的實作"


def test_tools_are_reachable_through_the_router():
    """有 schema 但路由拿不到 = 模型永遠看不到這顆工具。

    下半段那批是驗證時實測**零命中**的問法，而且其中「回撤」是結構性不可救的：
    它命中 analytics（工具數已超過 _AUGMENT_BASE_MAX），語意增補區塊直接被跳過，
    所以就算接上 ollama、embedding 可用，光靠語意也永遠補不進來 —— 只能靠關鍵字/意圖表。
    """
    from agent.tool_router import select_tools
    for q, expect in [("我是什麼類型的交易者？", "get_trading_dna_score"),
                      ("幫我畫淨值曲線", "get_equity_curve"),
                      ("我如果都不賣會怎樣？", "compare_sell_vs_hold"),
                      ("我還沒綁帳號，先看範例", "load_demo_account_ledger"),
                      # ── 以下曾經全部零命中 ──
                      ("我最大回撤是多少", "get_equity_curve"),
                      ("我的資產這一年怎麼變化", "get_equity_curve"),
                      ("我的投資風格", "get_trading_dna_score"),
                      ("我哪一項最弱", "get_trading_dna_score"),
                      ("分析我的交易個性 archetype", "get_trading_dna_score"),
                      ("我這一年交易得怎麼樣", "get_trading_dna_score"),
                      ("頻繁進出到底有沒有賺到", "compare_sell_vs_hold")]:
        names = {t["function"]["name"] for t in select_tools(q)}
        assert expect in names, f"「{q}」路由不到 {expect}"


def test_new_tools_have_concept_expansion_for_semantic_retrieval():
    """關鍵字表擋不住沒想到的問法；語意檢索要生效，工具得先有概念/範例擴充。"""
    from agent.tool_concepts import TOOL_CONCEPTS
    for name in TOOL_NAMES:
        assert name in TOOL_CONCEPTS, f"{name} 沒有 document expansion，語意檢索會用一句描述硬比"
        assert TOOL_CONCEPTS[name]["concepts"] and TOOL_CONCEPTS[name]["examples"]


@needs_csv
@pytest.mark.parametrize("name", TOOL_NAMES)
def test_every_tool_runs_with_default_args(name):
    """四顆工具都要能用空參數呼叫、不丟例外、不回 error。"""
    from agent.ollama_agent import TOOL_CALLABLES
    out = TOOL_CALLABLES[name]()
    assert isinstance(out, dict)
    assert "error" not in out, out.get("error")


def test_tools_degrade_gracefully_without_data(monkeypatch):
    """找不到 CSV 時要回可讀的 error dict，不是往上炸例外（評審機器沒有資料也不能壞）。"""
    monkeypatch.setenv("MAIA_DEMO_CSV", "/nonexistent/nope.csv")
    from agent.ollama_agent import TOOL_CALLABLES
    for name in TOOL_NAMES:
        out = TOOL_CALLABLES[name]()
        assert isinstance(out, dict) and "error" in out, f"{name} 沒有優雅降級"


@needs_csv
def test_dna_tool_surfaces_calibration_warning():
    """係數是用合成資料調的，這件事必須跟著結果一起回去，不能只寫在註解裡。"""
    from agent.ollama_agent import TOOL_CALLABLES
    out = TOOL_CALLABLES["get_trading_dna_score"]()
    assert "重新校準" in out["calibration_note"]
    assert out["archetype"] == EXPECTED_ARCHETYPE
    assert out["axes"] == list(ds.AXES)


@needs_csv
def test_counterfactual_tool_carries_the_flag_and_caveat():
    from agent.ollama_agent import TOOL_CALLABLES
    out = TOOL_CALLABLES["compare_sell_vs_hold"]()
    assert out["capital_feasible"] is True
    assert out["hold_capital_required_twd"] == pytest.approx(EXPECTED_HOLD_CAPITAL, rel=1e-9)
    assert "不要說成" in out["caveat"]
    assert out["sell_vs_hold_twd"] == EXPECTED_SELL_VS_HOLD

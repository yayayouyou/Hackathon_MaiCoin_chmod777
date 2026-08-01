"""實盤四道防線：停止開關 / 授權到期 / 累計曝險 / 決策台帳。

這些是真錢的最後一道防線，測試重點放在 **fail-closed**：
不確定的狀況一律要擋，而不是放行。
"""
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from skills.execution import live_guard

_TZ = timezone(timedelta(hours=8))


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """把台帳與停止開關導到暫存目錄，別污染真實紀錄。"""
    monkeypatch.setattr(live_guard, "_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(live_guard, "KILL_SWITCH_PATH", str(tmp_path / "TRADING_HALTED"))
    monkeypatch.setattr(live_guard, "ORDER_LEDGER_PATH", str(tmp_path / "order_ledger.jsonl"))
    for k in ("RISK_MODE", "LIVE_UNTIL", "LIVE_MAX_NOTIONAL_TWD", "LIVE_MAX_ORDERS", "LIVE_WINDOW_HOURS"):
        monkeypatch.delenv(k, raising=False)
    yield


def _arm_live(monkeypatch, days=7):
    monkeypatch.setenv("RISK_MODE", "live")
    monkeypatch.setenv("LIVE_UNTIL", (datetime.now(_TZ) + timedelta(days=days)).date().isoformat())


# ── 停止開關 ──────────────────────────────────────────────
def test_kill_switch_blocks_even_when_fully_authorized(monkeypatch):
    """停止開關的意義就是「不管其他條件多合法都停手」。"""
    _arm_live(monkeypatch)
    assert live_guard.effective_risk_mode()[0] == "live"
    live_guard.engage_kill_switch("測試")
    mode, note = live_guard.effective_risk_mode()
    assert mode == "halted" and "停止" in note


def test_kill_switch_release_restores_live(monkeypatch):
    _arm_live(monkeypatch)
    live_guard.engage_kill_switch()
    live_guard.release_kill_switch()
    assert live_guard.effective_risk_mode()[0] == "live"


# ── 授權到期 ──────────────────────────────────────────────
def test_live_without_expiry_date_falls_back_to_paper(monkeypatch):
    """只設 RISK_MODE=live 不夠 —— 那是設一次就永久生效的旗標。"""
    monkeypatch.setenv("RISK_MODE", "live")
    mode, note = live_guard.effective_risk_mode()
    assert mode == "paper" and "LIVE_UNTIL" in note


def test_expired_authorization_falls_back_to_paper(monkeypatch):
    monkeypatch.setenv("RISK_MODE", "live")
    monkeypatch.setenv("LIVE_UNTIL", (datetime.now(_TZ) - timedelta(days=1)).date().isoformat())
    mode, note = live_guard.effective_risk_mode()
    assert mode == "paper" and "到期" in note


def test_unparseable_expiry_fails_closed(monkeypatch):
    """時間解析不出來時必須當作未授權，不可放行。"""
    monkeypatch.setenv("RISK_MODE", "live")
    monkeypatch.setenv("LIVE_UNTIL", "下禮拜五")
    mode, _ = live_guard.effective_risk_mode()
    assert mode == "paper"


def test_date_only_expiry_covers_the_whole_day(monkeypatch):
    """LIVE_UNTIL=今天 應該整天有效，而不是今天 00:00 就過期。"""
    monkeypatch.setenv("RISK_MODE", "live")
    monkeypatch.setenv("LIVE_UNTIL", datetime.now(_TZ).date().isoformat())
    assert live_guard.effective_risk_mode()[0] == "live"


# ── 累計曝險 ──────────────────────────────────────────────
def test_cumulative_blocks_many_individually_legal_orders(monkeypatch):
    """單筆上限擋不住連續下單——這正是模型跑進迴圈時的樣子。"""
    _arm_live(monkeypatch)
    monkeypatch.setenv("LIVE_MAX_NOTIONAL_TWD", "100000")
    for _ in range(2):
        live_guard.record_decision("SUBMITTED", "btctwd", "buy", 1, 1, 49_000, "live")
    ok, why = live_guard.check_cumulative(49_000)
    assert not ok and "累計上限" in why


def test_cumulative_order_count_limit(monkeypatch):
    _arm_live(monkeypatch)
    monkeypatch.setenv("LIVE_MAX_ORDERS", "3")
    monkeypatch.setenv("LIVE_MAX_NOTIONAL_TWD", "9999999")
    for _ in range(3):
        live_guard.record_decision("SUBMITTED", "btctwd", "buy", 1, 1, 10, "live")
    ok, why = live_guard.check_cumulative(10)
    assert not ok and "筆數上限" in why


def test_only_submitted_live_orders_count_toward_exposure(monkeypatch):
    """被擋下的、模擬盤的都不該算進曝險，否則上限會被無關紀錄吃掉。"""
    _arm_live(monkeypatch)
    live_guard.record_decision("REJECTED_CUMULATIVE", "btctwd", "buy", 1, 1, 90_000, "live")
    live_guard.record_decision("SUBMITTED", "btctwd", "buy", 1, 1, 90_000, "paper")
    assert live_guard.exposure_window()["notional_twd"] == 0.0


def test_old_orders_fall_out_of_the_rolling_window(monkeypatch, tmp_path):
    _arm_live(monkeypatch)
    old = (datetime.now(_TZ) - timedelta(hours=48)).isoformat()
    with open(live_guard.ORDER_LEDGER_PATH, "w", encoding="utf-8") as f:
        f.write(json.dumps({"ts": old, "decision": "SUBMITTED", "mode": "live",
                            "notional_twd": 500_000}) + "\n")
    assert live_guard.exposure_window(hours=24)["notional_twd"] == 0.0


# ── 台帳 ──────────────────────────────────────────────────
def test_rejected_decisions_are_recorded_too(monkeypatch):
    """只記成功的等於只留下一半的故事，事後無法重建當時發生什麼。"""
    _arm_live(monkeypatch)
    monkeypatch.setenv("LIVE_MAX_NOTIONAL_TWD", "1000")
    allowed, mode, note = live_guard.preflight("btctwd", "buy", 1.0, 1.0, 50_000)
    assert not allowed and mode == "halted"
    recs = live_guard._read_ledger()
    assert any(r["decision"] == "REJECTED_CUMULATIVE" for r in recs)


def test_halted_preflight_is_recorded(monkeypatch):
    _arm_live(monkeypatch)
    live_guard.engage_kill_switch("演練")
    allowed, mode, _ = live_guard.preflight("btctwd", "buy", 1.0, 1.0, 10.0)
    assert not allowed and mode == "halted"
    assert any(r["decision"] == "HALTED" for r in live_guard._read_ledger())


def test_paper_mode_preflight_is_not_recorded_as_rejection(monkeypatch):
    """模擬盤不是「被擋下」，是本來就走模擬，不該污染台帳。"""
    monkeypatch.setenv("RISK_MODE", "paper")
    allowed, mode, _ = live_guard.preflight("btctwd", "buy", 1.0, 1.0, 10.0)
    assert not allowed and mode == "paper"
    assert live_guard._read_ledger() == []


def test_preflight_passes_when_everything_is_in_order(monkeypatch):
    _arm_live(monkeypatch)
    allowed, mode, note = live_guard.preflight("btctwd", "buy", 0.001, 1_000_000, 1_000)
    assert allowed and mode == "live"
    assert "累計曝險" in note


# ── 凍結模式與閘門的互動（安全設計的核心）──────────────────
def test_frozen_live_still_subject_to_kill_switch(monkeypatch):
    """核准當下凍結 live，不代表送出當下仍可下單 —— 停止開關必須照樣擋。

    這是「使用者同意」與「當下安全」的分界：同意的是『下這一筆』，
    不是『無論之後發生什麼都下』。
    """
    monkeypatch.setenv("RISK_MODE", "paper")      # 環境已改回 paper
    live_guard.engage_kill_switch("演練")
    allowed, mode, _ = live_guard.preflight("btctwd", "buy", 1.0, 1.0, 10.0, intended_mode="live")
    assert not allowed and mode == "halted"


def test_frozen_live_still_needs_valid_authorization(monkeypatch):
    """授權過期後，凍結的 live 也不能送真單。"""
    monkeypatch.setenv("LIVE_UNTIL", (datetime.now(_TZ) - timedelta(days=1)).date().isoformat())
    allowed, mode, note = live_guard.preflight("btctwd", "buy", 1.0, 1.0, 10.0, intended_mode="live")
    assert not allowed and mode == "paper" and "到期" in note


def test_frozen_live_overrides_paper_env_when_all_gates_pass(monkeypatch):
    """反過來：環境變成 paper 但使用者核准的是 live，且三道閘門都通過 →
    尊重使用者當下的同意，照 live 執行（否則會變成『以為下了真單其實沒下』）。"""
    monkeypatch.setenv("RISK_MODE", "paper")
    monkeypatch.setenv("LIVE_UNTIL", (datetime.now(_TZ) + timedelta(days=1)).date().isoformat())
    allowed, mode, _ = live_guard.preflight("btctwd", "buy", 1.0, 1.0, 10.0, intended_mode="live")
    assert allowed and mode == "live"


def test_frozen_paper_never_becomes_live(monkeypatch):
    """凍結 paper 就是 paper，即使環境是 live —— 防止模擬盤核准被當實盤執行。"""
    monkeypatch.setenv("RISK_MODE", "live")
    monkeypatch.setenv("LIVE_UNTIL", (datetime.now(_TZ) + timedelta(days=1)).date().isoformat())
    allowed, mode, _ = live_guard.preflight("btctwd", "buy", 1.0, 1.0, 10.0, intended_mode="paper")
    assert not allowed and mode == "paper"

"""
交易核准互鎖 (agent/trade_approval.py) 與 agent 迴圈閘門 (_gate_order) 單元測試
"""
from unittest.mock import patch

import pytest

from agent import trade_approval as ta


ARGS = {"exchange_id": "max", "market": "BTC/TWD", "side": "buy",
        "volume": 0.01, "price": 2000000, "ord_type": "limit"}


# ── 計畫組裝與雜湊 ─────────────────────────
class TestPlanAndHash:
    def test_build_plan_normalizes_and_computes_notional(self):
        plan = ta.build_order_plan(ARGS, latest_price=2000000, mode="paper")
        assert plan["market"] == "btctwd"          # 正規化去掉斜線
        assert plan["side"] == "buy"
        assert plan["mode"] == "paper"
        assert plan["est_notional_twd"] == pytest.approx(20000.0)  # 0.01 * 2,000,000

    def test_market_order_uses_latest_price_for_notional(self):
        args = {**ARGS, "ord_type": "market", "price": None}
        plan = ta.build_order_plan(args, latest_price=2100000, mode="live")
        assert plan["est_fill_price"] == 2100000
        assert plan["est_notional_twd"] == pytest.approx(21000.0)

    def test_hash_stable_and_sensitive(self):
        p1 = ta.build_order_plan(ARGS, 2000000, "paper")
        p2 = ta.build_order_plan(ARGS, 9999999, "paper")   # 只差 latest_price（不入雜湊）
        assert ta.plan_hash(p1) == ta.plan_hash(p2)
        p3 = ta.build_order_plan({**ARGS, "volume": 0.02}, 2000000, "paper")
        assert ta.plan_hash(p1) != ta.plan_hash(p3)        # 數量不同 → 雜湊不同


# ── 政策 ─────────────────────────
class TestPolicy:
    def test_always_needs_approval(self, monkeypatch):
        monkeypatch.setenv("TRADE_APPROVAL", "always")
        plan = ta.build_order_plan(ARGS, 2000000, "paper")
        assert ta.needs_approval(plan) is True

    def test_off_never_needs_approval(self, monkeypatch):
        monkeypatch.setenv("TRADE_APPROVAL", "off")
        plan = ta.build_order_plan(ARGS, 2000000, "paper")
        assert ta.needs_approval(plan) is False

    def test_allowlist_threshold(self, monkeypatch):
        monkeypatch.setenv("TRADE_APPROVAL", "allowlist")
        monkeypatch.setenv("TRADE_AUTO_APPROVE_TWD", "5000")
        small = ta.build_order_plan({**ARGS, "volume": 0.001}, 2000000, "paper")  # 2,000 TWD
        big = ta.build_order_plan({**ARGS, "volume": 0.01}, 2000000, "paper")     # 20,000 TWD
        assert ta.needs_approval(small) is False   # 低於門檻自動核准
        assert ta.needs_approval(big) is True      # 超過門檻要核准


# ── 核准 / 執行 / 拒絕 生命週期 ─────────────────────────
class TestLifecycle:
    def test_approve_executes_with_frozen_plan(self):
        plan = ta.build_order_plan(ARGS, 2000000, "paper")
        token, _ = ta.register_pending(plan)
        captured = {}

        def executor(p):
            captured.update(p)
            return {"status": "SUCCESS", "mode": "paper", "order": {"id": "x", "simulated": True}}

        res = ta.approve_and_execute(token, executor)
        assert res["status"] == "SUCCESS"
        # executor 收到的是凍結計畫
        assert captured["market"] == "btctwd" and captured["volume"] == 0.01
        # 狀態轉為 executed，二次核准被拒
        res2 = ta.approve_and_execute(token, executor)
        assert res2["status"] == "ERROR"

    def test_reject_blocks_execution(self):
        plan = ta.build_order_plan(ARGS, 2000000, "paper")
        token, _ = ta.register_pending(plan)
        assert ta.reject(token)["status"] == "REJECTED"
        # 已拒絕的單不可再執行
        res = ta.approve_and_execute(token, lambda p: {"status": "SUCCESS"})
        assert res["status"] == "ERROR"

    def test_unknown_token(self):
        assert ta.approve_and_execute("appr-nope", lambda p: {})["status"] == "ERROR"
        assert ta.reject("appr-nope")["status"] == "ERROR"

    def test_hash_mismatch_blocks(self):
        plan = ta.build_order_plan(ARGS, 2000000, "paper")
        token, _ = ta.register_pending(plan)
        # 竄改凍結計畫（模擬 store 被外部改動）→ 雜湊不符，拒絕執行
        ta.STORE.get(token)["plan"]["volume"] = 999
        res = ta.approve_and_execute(token, lambda p: {"status": "SUCCESS"})
        assert res["status"] == "ERROR" and "不符" in res["reason"]


# ── agent 迴圈閘門 _gate_order ─────────────────────────
class TestGateOrder:
    def test_gate_pending_when_policy_always(self, monkeypatch):
        monkeypatch.setenv("TRADE_APPROVAL", "always")
        from agent.ollama_agent import _gate_order
        with patch("skills.execution.order_executor.prepare_and_validate_order",
                   return_value={"ok": True, "latest_price": 2000000}), \
             patch("skills.execution.order_executor.get_risk_mode", return_value="paper"):
            gate = _gate_order(ARGS)
        assert gate["kind"] == "pending"
        assert gate["token"].startswith("appr-")
        assert "plan" in gate and gate["plan"]["market"] == "btctwd"

    def test_gate_risk_rejected(self, monkeypatch):
        monkeypatch.setenv("TRADE_APPROVAL", "always")
        from agent.ollama_agent import _gate_order
        rejection = {"status": "REJECTED_BY_RISK_GUARD", "reason": "超過單筆上限"}
        with patch("skills.execution.order_executor.prepare_and_validate_order",
                   return_value={"ok": False, "response": rejection}):
            gate = _gate_order(ARGS)
        assert gate["kind"] == "risk_rejected"
        assert gate["result"]["status"] == "REJECTED_BY_RISK_GUARD"

    def test_gate_execute_when_policy_off(self, monkeypatch):
        monkeypatch.setenv("TRADE_APPROVAL", "off")
        from agent.ollama_agent import _gate_order
        with patch("skills.execution.order_executor.prepare_and_validate_order",
                   return_value={"ok": True, "latest_price": 2000000}), \
             patch("skills.execution.order_executor.get_risk_mode", return_value="paper"):
            gate = _gate_order(ARGS)
        assert gate["kind"] == "execute"

    def test_gate_limit_without_price_defers_to_executor(self, monkeypatch):
        monkeypatch.setenv("TRADE_APPROVAL", "always")
        from agent.ollama_agent import _gate_order
        gate = _gate_order({**ARGS, "ord_type": "limit", "price": None})
        assert gate["kind"] == "execute"  # 交給 create_order 回傳缺價錯誤


# ── H1：名目金額單位一致（USDT/exotic 計價換算）─────────────────────────
USDT_ARGS = {"exchange_id": "max", "market": "BTC/USDT", "side": "buy",
             "volume": 0.02, "price": 60000, "ord_type": "limit"}


class TestNotionalCurrency:
    def test_usdt_order_converted_to_twd(self):
        # 1200 USDT × 35 = 42,000 TWD（而非把 1200 當成 TWD）
        plan = ta.build_order_plan(USDT_ARGS, latest_price=60000, mode="live")
        assert plan["est_notional_quote"] == pytest.approx(1200.0)
        assert plan["est_notional_twd"] == pytest.approx(42000.0)

    def test_usdt_order_needs_approval_under_allowlist(self, monkeypatch):
        # 修正前：1200(誤當 TWD) < 5000 → 自動核准跳過人審；修正後：42,000 TWD > 5000 → 需人審
        monkeypatch.setenv("TRADE_APPROVAL", "allowlist")
        monkeypatch.setenv("TRADE_AUTO_APPROVE_TWD", "5000")
        plan = ta.build_order_plan(USDT_ARGS, 60000, "live")
        assert ta.needs_approval(plan) is True

    def test_exotic_quote_forces_approval(self, monkeypatch):
        # BTC 計價無安全換算 → est_notional_twd=inf → 一律需人審（fail-safe）
        monkeypatch.setenv("TRADE_APPROVAL", "allowlist")
        args = {**USDT_ARGS, "market": "ETH/BTC", "volume": 1, "price": 0.05}
        plan = ta.build_order_plan(args, 0.05, "live")
        assert plan["est_notional_twd"] == float("inf")
        assert ta.needs_approval(plan) is True

    def test_untrustworthy_notional_forces_approval(self, monkeypatch):
        # 加固：None/非有限/負值的 est_notional_twd 不得因 truthiness 誤自動核准
        monkeypatch.setenv("TRADE_APPROVAL", "allowlist")
        for nt in [None, float("nan"), float("inf"), -999999.0]:
            assert ta.needs_approval({"est_notional_twd": nt}) is True, nt


class TestToolArgSanitize:
    def test_undeclared_args_stripped(self):
        # M2 根因加固：注入 create_order 未宣告的 mode/client_oid 應被剝除
        from agent.ollama_agent import _sanitize_tool_args
        args = {"exchange_id": "max", "market": "BTC/TWD", "side": "buy", "volume": 0.01,
                "price": 2000000, "ord_type": "limit", "mode": "live", "client_oid": "x"}
        safe = _sanitize_tool_args("create_order", args)
        assert "mode" not in safe and "client_oid" not in safe
        assert safe["market"] == "BTC/TWD" and safe["side"] == "buy"   # 宣告參數保留


# ── L1：全帳戶撤單走核准互鎖 ─────────────────────────
class TestGateCancelAll:
    def test_full_account_cancel_needs_approval(self, monkeypatch):
        monkeypatch.setenv("TRADE_APPROVAL", "always")
        from agent.ollama_agent import _gate_cancel_all
        gate = _gate_cancel_all({"exchange_id": "max"})   # 無 market = 全帳戶
        assert gate["kind"] == "pending"
        assert gate["plan"]["kind"] == "cancel_all"

    def test_specific_market_cancel_executes_directly(self, monkeypatch):
        monkeypatch.setenv("TRADE_APPROVAL", "always")
        from agent.ollama_agent import _gate_cancel_all
        assert _gate_cancel_all({"exchange_id": "max", "market": "BTC/TWD"})["kind"] == "execute"

    def test_slash_market_still_needs_approval(self, monkeypatch):
        # "/" 正規化後為空 → 視為全帳戶 → 需核准（不得被當指定市場繞過）
        monkeypatch.setenv("TRADE_APPROVAL", "always")
        from agent.ollama_agent import _gate_cancel_all
        assert _gate_cancel_all({"exchange_id": "max", "market": "/"})["kind"] == "pending"

    def test_policy_off_executes(self, monkeypatch):
        monkeypatch.setenv("TRADE_APPROVAL", "off")
        from agent.ollama_agent import _gate_cancel_all
        assert _gate_cancel_all({"exchange_id": "max"})["kind"] == "execute"

    def test_cancel_all_plan_approve_flow(self):
        plan = ta.build_cancel_all_plan("max", "paper")
        token, _ = ta.register_pending(plan)
        captured = {}

        def ex(p):
            captured.update(p)
            return {"status": "SUCCESS"}

        res = ta.approve_and_execute(token, ex)
        assert res["status"] == "SUCCESS" and captured["kind"] == "cancel_all"


# ── M5：待核准 token 逾時 ─────────────────────────
class TestApprovalTTL:
    def test_pending_token_expires(self):
        plan = ta.build_order_plan(ARGS, 2000000, "paper")
        token, _ = ta.register_pending(plan)
        ta.STORE.get(token)["mono"] -= ta._APPROVAL_TTL_SEC + 10   # 倒回超過 TTL（用單調時鐘判斷）
        res = ta.approve_and_execute(token, lambda p: {"status": "SUCCESS"})
        assert res["status"] == "ERROR" and "逾時" in res["reason"]
        assert ta.STORE.get(token)["state"] == "expired"

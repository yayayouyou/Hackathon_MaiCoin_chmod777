"""
tests/test_analyst_sandbox.py — 唯讀分析沙盒的安全與功能測試

安全重點：金鑰不進沙盒、下單/私有 skill 不在白名單、import/open 被擋、逾時可殺。
"""
from unittest.mock import patch

from analyst_sandbox import broker
from analyst_sandbox.sandbox import run_analysis, _clean_env


# ────────────────────────── broker（父行程、in-process）──────────────────────────
class TestBroker:
    def test_whitelist_excludes_dangerous(self):
        wl = set(broker.whitelist())
        for banned in ("create_order", "cancel_order", "cancel_all_orders", "save_strategy",
                       "remember_about_me", "get_max_accounts", "get_max_my_trades", "run_analysis"):
            assert banned not in wl
        # 唯讀資料類應在
        assert "get_crypto_fear_and_greed_index" in wl
        assert "run_signal_backtest" in wl

    def test_execute_rejects_denied(self):
        r = broker.execute("create_order", {"market": "btctwd"})
        assert r["ok"] is False and "白名單" in r["error"]

    def test_execute_rejects_unknown(self):
        assert broker.execute("does_not_exist", {})["ok"] is False

    def test_sanitize_numpy_pandas(self):
        import numpy as np
        import pandas as pd
        s = broker._sanitize({"a": np.int64(5), "b": np.array([1.0, 2.0]), "c": pd.Series([1, 2])})
        assert s["a"] == 5 and s["b"] == [1.0, 2.0]

    def test_safe_kwargs_filters_objects(self):
        assert broker._safe_kwargs({"n": 5, "s": "x", "bad": object(), "lst": [1, 2]}) == {"n": 5, "s": "x", "lst": [1, 2]}


# ────────────────────────── clean env（無金鑰）──────────────────────────
class TestKeyIsolation:
    def test_clean_env_has_no_secrets(self):
        env = _clean_env("/tmp/x")
        assert not [k for k in env if any(s in k.upper() for s in ("KEY", "SECRET", "TOKEN", "PASSWORD"))]
        assert "COINALYZE_API_KEY" not in env and "SOSOVALUE_API_KEY" not in env


# ────────────────────────── sandbox 子行程（隔離）──────────────────────────
class TestSandboxExecution:
    def test_basic_compute(self):
        r = run_analysis("result = int(np.arange(10).sum())", timeout=10)
        assert r.get("ok") and r["result"] == 45

    def test_import_blocked(self):
        r = run_analysis("import os\nresult = 1", timeout=10)
        assert "error" in r and "不允許 import" in r["error"]

    def test_open_blocked(self):
        r = run_analysis("result = open('/etc/passwd').read()", timeout=10)
        assert "error" in r and ("open" in r["error"] or "not defined" in r["error"])

    def test_eval_blocked(self):
        r = run_analysis("result = eval('1+1')", timeout=10)
        assert "error" in r

    def test_safe_import_allowed(self):
        # 純運算庫可 import（datetime / collections）
        r = run_analysis("from collections import Counter\nresult = dict(Counter('aabbb'))", timeout=10)
        assert r.get("ok") and r["result"] == {"a": 2, "b": 3}

    def test_io_import_blocked(self):
        for mod in ("os", "socket", "subprocess", "requests", "pathlib"):
            r = run_analysis(f"import {mod}\nresult = 1", timeout=10)
            assert "error" in r and "不允許 import" in r["error"], mod

    def test_numpy_stats_capability(self):
        r = run_analysis("result = round(float(np.corrcoef([1,2,3,4,5],[2,4,5,4,5])[0,1]), 3)", timeout=10)
        assert r.get("ok") and abs(r["result"] - 0.775) < 0.01

    def test_preinjected_modules_usable_without_import(self):
        r = run_analysis("result = [datetime.date(2026,1,1).year, len(list(itertools.repeat(0,3)))]", timeout=10)
        assert r.get("ok") and r["result"] == [2026, 3]

    def test_empty_code_rejected(self):
        assert "error" in run_analysis("   ", timeout=5)

    def test_markdown_fence_tolerated(self):
        # 活體 E2E 發現：模型常把程式碼包在 ```python``` 圍欄 → 沙盒須寬容剝除
        r = run_analysis("```python\nresult = sum(range(10))\n```", timeout=8)
        assert r.get("ok") and r["result"] == 45

    def test_timeout_kills_infinite_loop(self):
        r = run_analysis("x=0\nwhile True:\n    x+=1", timeout=3)
        assert "error" in r  # 被逾時/資源上限中止，不掛住

    def test_call_skill_roundtrip_via_broker(self):
        # patch 父行程 broker.execute → 不打網路，驗證 RPC 往返
        with patch.object(broker, "execute", return_value={"ok": True, "data": {"value": 42}}):
            r = run_analysis("d = call_skill('get_ticker', symbol='BTC/USDT')\nresult = d['value'] * 2", timeout=10)
        assert r.get("ok") and r["result"] == 84
        assert r["skill_calls"] == 1

    def test_call_skill_denied_propagates(self):
        with patch.object(broker, "execute", return_value={"ok": False, "error": "不在白名單"}):
            r = run_analysis("result = call_skill('create_order')", timeout=10)
        assert "error" in r and "白名單" in r["error"]

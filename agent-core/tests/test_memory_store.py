"""分層使用者記憶 (agent/memory_store.py) 單元測試"""
import os
import json
import pytest

from agent import memory_store as ms


@pytest.fixture(autouse=True)
def isolated_mem(tmp_path, monkeypatch):
    """把記憶檔導向 tmp，避免污染真實使用者資料。"""
    monkeypatch.setattr(ms, "_MEM_DIR", str(tmp_path))
    monkeypatch.setattr(ms, "_PROFILE", str(tmp_path / "profile.json"))
    monkeypatch.setattr(ms, "_JOURNAL", str(tmp_path / "journal.jsonl"))
    yield


# ── 偏好 ─────────────────────────
class TestProfile:
    def test_remember_persists_and_dedupes(self):
        r1 = ms.remember_about_me("我只做現貨，單筆風險 2%")
        assert r1["status"] == "已記住"
        r2 = ms.remember_about_me("我只做現貨，單筆風險 2%")  # 重複
        assert r2["status"] == "已存在"
        assert len(ms.load_profile()["facts"]) == 1

    def test_remember_empty_rejected(self):
        assert "error" in ms.remember_about_me("   ")

    def test_forget(self):
        ms.remember_about_me("我偏好 MAX 交易所")
        ms.remember_about_me("我是新手")
        out = ms.forget_about_me("新手")
        assert out["removed"] == 1
        facts = [f["fact"] for f in ms.load_profile()["facts"]]
        assert "我偏好 MAX 交易所" in facts and "我是新手" not in facts

    def test_cap_30(self):
        for i in range(35):
            ms.remember_about_me(f"偏好第 {i} 條")
        assert len(ms.load_profile()["facts"]) == 30  # 上限汰舊


# ── 日誌 ─────────────────────────
class TestJournal:
    def test_append_and_recent(self):
        ms.append_journal("BTC 該不該進場", "綜合分析，建議評級：觀望", ["get_max_tickers", "get_ohlcv"])
        ms.append_journal("ETH 現價", "ETH 約 56,000 TWD", ["get_max_tickers"])
        recent = ms.recent_journal(5)
        assert len(recent) == 2
        assert recent[0]["rating"] == "觀望"          # 從決策文字擷取評級
        assert recent[1]["query"] == "ETH 現價"

    def test_recall_history_keyword(self):
        ms.append_journal("BTC 分析", "BTC 評級：買入", ["get_ohlcv"])
        ms.append_journal("DOGE 分析", "DOGE 評級：賣出", ["get_ohlcv"])
        out = ms.recall_history("DOGE")
        assert out["count"] == 1
        assert "DOGE" in out["history"][0]["query"]

    def test_journal_records_order(self):
        order = {"side": "buy", "volume": 0.001, "market": "btctwd"}
        ms.append_journal("幫我買一點 BTC", "已備妥訂單等待核准", ["create_order"], order=order)
        assert ms.recent_journal(1)[0]["order"]["side"] == "buy"


# ── context 注入 ─────────────────────────
class TestContext:
    def test_empty_when_no_memory(self):
        assert ms.build_memory_context() == ""

    def test_context_includes_facts_and_journal(self):
        ms.remember_about_me("我只做現貨")
        ms.append_journal("BTC 進場？", "評級：觀望，建議等回檔", ["get_max_tickers"])
        ctx = ms.build_memory_context()
        assert "<user_memory>" in ctx and "</user_memory>" in ctx
        assert "我只做現貨" in ctx
        assert "觀望" in ctx

    def test_extract_rating(self):
        assert ms._extract_rating("最終評級：強烈買入") == "強烈買入"
        assert ms._extract_rating("純知識性回答，無評級") is None

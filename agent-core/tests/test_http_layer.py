"""共用 HTTP 韌性層 (skills/_http.py) 單元測試"""
from unittest.mock import MagicMock

import pytest

from skills import _http


@pytest.fixture(autouse=True)
def _reset():
    _http.reset_state()
    yield
    _http.reset_state()


# ── Session 重用 ─────────────────────────
class TestSession:
    def test_singleton(self):
        assert _http.get_session() is _http.get_session()

    def test_default_ua_set(self):
        assert "Chrome" in _http.get_session().headers["User-Agent"]

    def test_retry_only_idempotent_methods(self):
        # 掛在 https adapter 上的 Retry 只允許 GET/HEAD → POST（下單）不會被自動重試
        adapter = _http.get_session().get_adapter("https://x")
        retry = adapter.max_retries
        assert "POST" not in retry.allowed_methods
        assert "GET" in retry.allowed_methods
        assert 429 in retry.status_forcelist and 503 in retry.status_forcelist


# ── 限流 ─────────────────────────
class TestThrottle:
    def test_enforces_min_interval(self, monkeypatch):
        clock = {"t": 100.0}
        slept = []
        monkeypatch.setattr(_http.time, "monotonic", lambda: clock["t"])
        def fake_sleep(s):
            slept.append(s); clock["t"] += s
        monkeypatch.setattr(_http.time, "sleep", fake_sleep)

        _http.set_min_interval("example.test", 2.0)
        _http._throttle("example.test")          # 首次：不睡
        assert slept == []
        _http._throttle("example.test")          # 立刻再呼叫：需睡滿 2s
        assert slept and abs(sum(slept) - 2.0) < 0.01

    def test_unlisted_host_not_throttled(self, monkeypatch):
        slept = []
        monkeypatch.setattr(_http.time, "sleep", lambda s: slept.append(s))
        _http._throttle("no-limit-host.test")
        _http._throttle("no-limit-host.test")
        assert slept == []


# ── fetch_json 杜絕靜默失敗 ─────────────────────────
class TestFetchJson:
    def _fake_resp(self, status=200, payload=None, text_json=True):
        r = MagicMock()
        r.status_code = status
        if text_json:
            r.json.return_value = payload
        else:
            r.json.side_effect = ValueError("no json")
        return r

    def test_ok(self, monkeypatch):
        monkeypatch.setattr(_http, "session_get", lambda url, **kw: self._fake_resp(200, {"a": 1}))
        assert _http.fetch_json("https://x/api") == {"a": 1}

    def test_http_error_raises(self, monkeypatch):
        monkeypatch.setattr(_http, "session_get", lambda url, **kw: self._fake_resp(403, None))
        with pytest.raises(_http.FetchError) as e:
            _http.fetch_json("https://x/api")
        assert "403" in str(e.value)

    def test_non_json_raises(self, monkeypatch):
        monkeypatch.setattr(_http, "session_get", lambda url, **kw: self._fake_resp(200, text_json=False))
        with pytest.raises(_http.FetchError):
            _http.fetch_json("https://x/api")

    def test_missing_expected_keys_raises(self, monkeypatch):
        monkeypatch.setattr(_http, "session_get", lambda url, **kw: self._fake_resp(200, {"a": 1}))
        with pytest.raises(_http.FetchError) as e:
            _http.fetch_json("https://x/api", expect_keys=["a", "b", "data"])
        assert "b" in str(e.value) and "data" in str(e.value)

    def test_network_exception_wrapped(self, monkeypatch):
        import requests
        def boom(url, **kw):
            raise requests.ConnectionError("down")
        monkeypatch.setattr(_http, "session_get", boom)
        with pytest.raises(_http.FetchError):
            _http.fetch_json("https://x/api")

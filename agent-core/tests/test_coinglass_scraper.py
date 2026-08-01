"""coinglass_scraper 明文分支：業務錯誤信封不可被當有效數據（否則 drift canary 假『健康』）。"""
from unittest.mock import patch, MagicMock

from skills.market_data.coinglass_scraper import _coinglass_public_request


def _resp(body):
    r = MagicMock()
    r.raise_for_status.return_value = None
    r.headers = {}                       # 無 user/v 加密標頭 → 走明文分支
    r.json.return_value = body
    return r


@patch("skills.market_data.coinglass_scraper.session_get")
def test_error_envelope_becomes_error(mock_get):
    # {"success": false, ...} 沒有 'error' 鍵，修正前會被當有效數據
    mock_get.return_value = _resp({"success": False, "code": "50001", "msg": "request limit"})
    res = _coinglass_public_request("https://x")
    assert "error" in res
    assert res.get("drift_suspected") is False    # 限流/維護，非解密漂移


@patch("skills.market_data.coinglass_scraper.session_get")
def test_code_msg_without_data_becomes_error(mock_get):
    mock_get.return_value = _resp({"code": "429", "msg": "too many requests"})
    res = _coinglass_public_request("https://x")
    assert "error" in res


@patch("skills.market_data.coinglass_scraper.session_get")
def test_valid_plaintext_still_passes(mock_get):
    mock_get.return_value = _resp({"success": True, "data": [1, 2, 3]})
    res = _coinglass_public_request("https://x")
    assert res.get("data") == [1, 2, 3]

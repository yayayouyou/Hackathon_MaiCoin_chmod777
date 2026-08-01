"""計價幣別 → TWD 換算：風控/核准單位一致性（確定性、不打網路）。"""
from skills.execution import quote_convert as qc


def test_quote_currency_parsing():
    assert qc.quote_currency("btctwd") == "twd"
    assert qc.quote_currency("BTC/USDT") == "usdt"
    assert qc.quote_currency("ethbtc") == "btc"
    assert qc.quote_currency("ethusdc") == "usdc"
    assert qc.quote_currency("btcusd") == "usd"
    assert qc.quote_currency("dogexyz") is None


def test_rate_to_twd_deterministic():
    assert qc.rate_to_twd("twd") == 1.0
    assert qc.rate_to_twd("usdt") == qc._STABLE_TWD_RATE
    assert qc.rate_to_twd("usdc") == qc._STABLE_TWD_RATE
    assert qc.rate_to_twd("btc") is None      # 無安全固定匯率 → fail-closed
    assert qc.rate_to_twd(None) is None


def test_notional_to_twd():
    assert qc.notional_to_twd(20000, "btctwd") == 20000                    # TWD 對維持原值
    assert qc.notional_to_twd(1000, "btcusdt") == 1000 * qc._STABLE_TWD_RATE
    assert qc.notional_to_twd(5, "ethbtc") is None                         # BTC 計價 → fail-closed

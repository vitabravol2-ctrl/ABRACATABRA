from pair_info_card import PairState, AlgoSettings, MarketBrain, RiskBrain, EntryBrain, ExitBrain


def test_market_brain_ok():
    st = PairState(price=100, bid=99.9, ask=100.1, spread_bps=2, change_24h=0.5, latency_ms=100)
    regime, reason, _ = MarketBrain().analyze(st, AlgoSettings())
    assert regime in {"FLAT", "TREND_UP", "TREND_DOWN"}
    assert reason.value == "MARKET_OK"


def test_risk_brain_balance_low():
    st = PairState(usdt_free=5)
    ok, _, reason = RiskBrain().approve(st, AlgoSettings(), trades_today=0)
    assert not ok
    assert reason.value == "BALANCE_LOW"


def test_entry_brain_wait_on_small_spread():
    st = PairState(spread_bps=0.1)
    decision, _, reason, _ = EntryBrain().decide(st, "FLAT", AlgoSettings())
    assert decision == "WAIT"
    assert reason.value == "SPREAD_TOO_SMALL"


def test_exit_brain_take_profit():
    settings = AlgoSettings()
    decision, reason, _ = ExitBrain().decide(100.0, 100.2, 100.2, 10, settings)
    assert decision == "SELL"
    assert reason.value == "TAKE_PROFIT_READY"

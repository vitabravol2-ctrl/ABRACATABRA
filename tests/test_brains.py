from pair_info_card import (
    PairState,
    AlgoSettings,
    MarketBrain,
    RiskBrain,
    EntryBrain,
    ExitBrain,
    OrderManager,
    DryRunEngine,
    TradingCore,
)


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


def test_trading_core_buy_sell_and_position():
    st = PairState(price=100.0, bid=99.9, ask=100.1)
    om = OrderManager(log_path="logs/test_orders_log.csv")
    dry = DryRunEngine(st, om)
    core = TradingCore(st, om, dry)

    buy_id = core.buy_limit("BTCUSDT", qty=0.01, price=100.0)
    assert buy_id is not None
    pos = core.get_position("BTCUSDT")
    assert pos["qty"] == 0.01
    assert st.current_position_btc == 0.01

    sell_id = core.sell_limit("BTCUSDT", qty=0.01, price=101.0)
    assert sell_id is not None
    pos2 = core.get_position("BTCUSDT")
    assert pos2["qty"] == 0
    assert st.realized_pnl > 0

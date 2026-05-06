from core.models import Tick, Trade


def build_trade(tick: Tick, impulse_low: float, tp_pct: float, sl_buffer_pct: float) -> Trade:
    entry_price = tick.ask
    return Trade(
        entry_time=tick.timestamp,
        entry_price=entry_price,
        tp_price=entry_price * (1 + tp_pct),
        sl_price=impulse_low * (1 - sl_buffer_pct),
    )


def finalize_trade(trade: Trade, tick: Tick, reason: str) -> Trade:
    trade.exit_time = tick.timestamp
    trade.exit_price = tick.mid
    trade.exit_reason = reason
    trade.pnl_pct = (trade.exit_price - trade.entry_price) / trade.entry_price
    return trade

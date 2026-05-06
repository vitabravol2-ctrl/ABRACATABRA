from config import Config
from core.fsm import LiquidityGrabFSM
from core.logger import BotLogger
from data.market_buffer import MarketBuffer
from data.mock_feed import MockFeed


def main() -> None:
    cfg = Config()
    logger = BotLogger()
    buffer = MarketBuffer(window_sec=cfg.rolling_window_sec)
    fsm = LiquidityGrabFSM(cfg=cfg, buffer=buffer, logger=logger)

    feed = MockFeed().generate()
    logger.log("SYSTEM", "START", f"Running mock feed for {cfg.symbol}. ticks={len(feed)}")
    for tick in feed:
        fsm.on_tick(tick)

    print("\n=== TRADES ===")
    total = 0.0
    for i, trade in enumerate(fsm.trades, start=1):
        total += trade.pnl_pct or 0.0
        print(
            f"#{i} entry={trade.entry_price:.2f} exit={trade.exit_price:.2f} "
            f"reason={trade.exit_reason} pnl={trade.pnl_pct:.4%}"
        )
    print(f"Total PnL: {total:.4%}")


if __name__ == "__main__":
    main()

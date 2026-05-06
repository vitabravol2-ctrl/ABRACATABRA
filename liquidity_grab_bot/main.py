import argparse

from config import Config
from core.fsm import LiquidityGrabFSM
from core.logger import BotLogger
from data.market_buffer import MarketBuffer
from data.mock_feed import MockFeed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Liquidity Grab Bot mock runner")
    parser.add_argument(
        "--scenario",
        default="success_tp",
        choices=["success_tp", "no_reclaim", "new_low_after_impulse", "spread_too_wide", "timeout_exit"],
        help="Mock scenario to run",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = Config()
    logger = BotLogger()
    buffer = MarketBuffer(window_sec=cfg.rolling_window_sec)
    fsm = LiquidityGrabFSM(cfg=cfg, buffer=buffer, logger=logger)

    feed = MockFeed().generate(scenario=args.scenario)
    logger.log("SYSTEM", "START", f"Scenario={args.scenario} symbol={cfg.symbol} ticks={len(feed)}")
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

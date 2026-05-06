import unittest

from config import Config
from core.fsm import LiquidityGrabFSM
from core.logger import BotLogger
from data.market_buffer import MarketBuffer
from data.mock_feed import MockFeed


class TestFSMScenarios(unittest.TestCase):
    def _run(self, scenario: str):
        cfg = Config()
        logger = BotLogger()
        fsm = LiquidityGrabFSM(cfg=cfg, buffer=MarketBuffer(window_sec=cfg.rolling_window_sec), logger=logger)
        for tick in MockFeed().generate(scenario=scenario):
            fsm.on_tick(tick)
        return fsm.trades

    def test_success_tp(self):
        trades = self._run("success_tp")
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].exit_reason, "TP")

    def test_no_reclaim(self):
        trades = self._run("no_reclaim")
        self.assertEqual(len(trades), 0)

    def test_new_low_after_impulse(self):
        trades = self._run("new_low_after_impulse")
        self.assertEqual(len(trades), 0)

    def test_spread_too_wide(self):
        trades = self._run("spread_too_wide")
        self.assertEqual(len(trades), 0)

    def test_timeout_exit(self):
        trades = self._run("timeout_exit")
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].exit_reason, "TIMEOUT")


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import datetime, timedelta

from config import Config
from core.detector import LiquidityGrabDetector


class TestDetector(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = Config()
        self.detector = LiquidityGrabDetector(self.cfg)

    def test_impulse_true_false(self) -> None:
        self.assertTrue(self.detector.impulse_confirmed(self.cfg.impulse_pct, 1.0))
        self.assertFalse(self.detector.impulse_confirmed(self.cfg.impulse_pct - 0.0001, 1.0))

    def test_bounce_true_false(self) -> None:
        high, low = 100.0, 99.0
        self.assertTrue(self.detector.bounce_confirmed(high, low, 99.5))
        self.assertFalse(self.detector.bounce_confirmed(high, low, 99.3))

    def test_reclaim_true_false(self) -> None:
        high, low = 100.0, 99.0
        reclaim = self.detector.reclaim_level(high, low)
        self.assertEqual(reclaim, 99.5)
        self.assertTrue(99.6 >= reclaim)
        self.assertFalse(99.4 >= reclaim)

    def test_hold_true_false(self) -> None:
        start = datetime(2026, 1, 1)
        self.assertFalse(self.detector.hold_confirmed(start, start + timedelta(seconds=1.0)))
        self.assertTrue(self.detector.hold_confirmed(start, start + timedelta(seconds=2.0)))

    def test_timeout_true_false(self) -> None:
        start = datetime(2026, 1, 1)
        self.assertFalse(self.detector.position_timed_out(start, start + timedelta(seconds=10.0)))
        self.assertTrue(self.detector.position_timed_out(start, start + timedelta(seconds=16.0)))


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import datetime, timedelta

from core.models import Tick
from data.market_buffer import MarketBuffer


class TestMarketBuffer(unittest.TestCase):
    def setUp(self) -> None:
        self.buffer = MarketBuffer(window_sec=5.0)
        self.base = datetime(2026, 1, 1, 0, 0, 0)

    def _tick(self, sec: float, mid: float, spread_pct: float = 0.0001) -> Tick:
        spread = mid * spread_pct
        return Tick(
            timestamp=self.base + timedelta(seconds=sec),
            bid=mid - spread / 2,
            ask=mid + spread / 2,
            mid=mid,
            volume=1.0,
        )

    def test_rolling_high_low(self) -> None:
        for sec, mid in [(0, 100.0), (1, 105.0), (2, 99.0), (3, 103.0)]:
            self.buffer.add_tick(self._tick(sec, mid))
        high, low = self.buffer.rolling_high_low()
        self.assertEqual(high, 105.0)
        self.assertEqual(low, 99.0)

    def test_drop_pct(self) -> None:
        for sec, mid in [(0, 100.0), (1, 98.0), (2, 97.0)]:
            self.buffer.add_tick(self._tick(sec, mid))
        self.assertAlmostEqual(self.buffer.drop_pct(), 0.03)

    def test_spread_pct(self) -> None:
        tick = self._tick(0, 100.0, spread_pct=0.0002)
        self.assertAlmostEqual(self.buffer.spread_pct(tick), 0.0002)

    def test_stale_detection(self) -> None:
        tick = self._tick(0, 100.0)
        self.buffer.add_tick(tick)
        fresh_now = tick.timestamp + timedelta(milliseconds=500)
        stale_now = tick.timestamp + timedelta(milliseconds=1200)
        self.assertFalse(self.buffer.is_stale(fresh_now, stale_ms=1000))
        self.assertTrue(self.buffer.is_stale(stale_now, stale_ms=1000))


if __name__ == "__main__":
    unittest.main()

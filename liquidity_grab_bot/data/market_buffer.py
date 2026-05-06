from collections import deque
from datetime import datetime, timedelta
from typing import Deque, Optional, Tuple

from core.models import Tick


class MarketBuffer:
    def __init__(self, window_sec: float) -> None:
        self.window = timedelta(seconds=window_sec)
        self.ticks: Deque[Tick] = deque()

    def add_tick(self, tick: Tick) -> None:
        self.ticks.append(tick)
        self._trim(tick.timestamp)

    def _trim(self, now: datetime) -> None:
        while self.ticks and now - self.ticks[0].timestamp > self.window:
            self.ticks.popleft()

    def rolling_high_low(self) -> Tuple[Optional[float], Optional[float]]:
        if not self.ticks:
            return None, None
        mids = [t.mid for t in self.ticks]
        return max(mids), min(mids)

    def drop_pct(self) -> float:
        high, low = self.rolling_high_low()
        if not high or not low:
            return 0.0
        return (high - low) / high

    def is_stale(self, now: datetime, stale_ms: int) -> bool:
        if not self.ticks:
            return True
        last = self.ticks[-1]
        return (now - last.timestamp).total_seconds() * 1000 > stale_ms

    @staticmethod
    def spread_pct(tick: Tick) -> float:
        if tick.mid == 0:
            return 0.0
        return (tick.ask - tick.bid) / tick.mid

    def last_tick(self) -> Optional[Tick]:
        return self.ticks[-1] if self.ticks else None

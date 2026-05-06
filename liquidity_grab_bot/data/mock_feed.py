from datetime import datetime, timedelta
from typing import List

from core.models import Tick


class MockFeed:
    def __init__(self, start_price: float = 100000.0) -> None:
        self.start_price = start_price

    def generate(self) -> List[Tick]:
        ticks: List[Tick] = []
        t = datetime.utcnow()

        sequence = [
            100000, 100002, 100001, 100003, 100004, 100003,  # normal
            99720,  # sharp drop (0.28%)
            99680,  # deeper drop (0.32%) impulse
            99830, 99870,  # bounce + reclaim
            99880, 99885, 99890, 99895, 99900, 99910, 99915, 99920, 99925,  # hold > 2 sec
            99980, 100040, 100120, 100220,  # move to TP
        ]

        for mid in sequence:
            spread = mid * 0.00008
            ticks.append(Tick(timestamp=t, bid=mid - spread / 2, ask=mid + spread / 2, mid=mid, volume=1.0))
            t += timedelta(seconds=0.25)

        return ticks

from datetime import datetime, timedelta
from typing import Callable, Dict, List

from core.models import Tick


class MockFeed:
    def __init__(self, start_price: float = 100000.0, step_sec: float = 0.25) -> None:
        self.start_price = start_price
        self.step = timedelta(seconds=step_sec)

    def generate(self, scenario: str = "success_tp") -> List[Tick]:
        scenarios: Dict[str, Callable[[], List[float]]] = {
            "success_tp": self.scenario_success_tp,
            "no_reclaim": self.scenario_no_reclaim,
            "new_low_after_impulse": self.scenario_new_low_after_impulse,
            "spread_too_wide": self.scenario_spread_too_wide,
            "timeout_exit": self.scenario_timeout_exit,
        }
        if scenario not in scenarios:
            available = ", ".join(sorted(scenarios.keys()))
            raise ValueError(f"Unknown scenario '{scenario}'. Available: {available}")

        return self._build_ticks(scenarios[scenario](), scenario)

    def _build_ticks(self, mids: List[float], scenario: str) -> List[Tick]:
        ticks: List[Tick] = []
        t = datetime.utcnow()
        for mid in mids:
            spread_pct = 0.00008
            if scenario == "spread_too_wide" and mid <= 99680:
                spread_pct = 0.0005
            spread = mid * spread_pct
            ticks.append(Tick(timestamp=t, bid=mid - spread / 2, ask=mid + spread / 2, mid=mid, volume=1.0))
            t += self.step
        return ticks

    def scenario_success_tp(self) -> List[float]:
        return [
            100000, 100002, 100001, 100003, 100004, 100003,
            99720, 99680,
            99830, 99870,
            99880, 99885, 99890, 99895, 99900, 99910, 99915, 99920, 99925,
            99980, 100040, 100120, 100220,
        ]

    def scenario_no_reclaim(self) -> List[float]:
        return [
            100000, 100002, 100001, 100003, 100004,
            99720, 99680,
            99780, 99800,
            99740, 99700, 99690, 99710, 99695,
        ]

    def scenario_new_low_after_impulse(self) -> List[float]:
        return [
            100000, 100002, 100001, 100003, 100004,
            99720, 99680,
            99830, 99870,
            99660, 99650, 99640,
        ]

    def scenario_spread_too_wide(self) -> List[float]:
        return [
            100000, 100002, 100001, 100003, 100004,
            99720, 99680, 99710, 99740, 99760, 99720,
        ]

    def scenario_timeout_exit(self) -> List[float]:
        return [
            100000, 100002, 100001, 100003, 100004, 100003,
            99720, 99680,
            99830, 99870,
            99880, 99885, 99890, 99895, 99900, 99910, 99915, 99920, 99925,
            99935, 99940, 99938, 99936, 99934, 99932, 99930, 99931, 99929,
            99930, 99928, 99927, 99929, 99930, 99931, 99930, 99928, 99927,
            99926, 99925, 99924, 99923, 99922, 99921, 99920, 99919, 99920,
            99921, 99922, 99921, 99920, 99919, 99918, 99917, 99916, 99915,
            99914, 99913, 99912, 99911, 99910, 99909, 99910, 99911, 99910,
            99909, 99908, 99907, 99906, 99905, 99906, 99907, 99908, 99907,
            99906, 99905, 99904, 99903, 99902, 99901, 99900, 99899, 99898,
            99899, 99900, 99901, 99900, 99899, 99898, 99897, 99896, 99895,
            99896, 99897, 99898, 99897, 99896, 99895, 99894, 99893, 99892,
            99891, 99890, 99889, 99888, 99887, 99888, 99889, 99890, 99889,
            99888, 99887, 99886, 99885, 99884, 99883, 99882, 99881, 99880,
        ]

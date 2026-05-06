from datetime import datetime

from config import Config


class LiquidityGrabDetector:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def impulse_confirmed(self, drop_pct: float, elapsed_sec: float) -> bool:
        return drop_pct >= self.cfg.impulse_pct and elapsed_sec <= self.cfg.impulse_max_seconds

    def bounce_confirmed(self, impulse_high: float, impulse_low: float, current_price: float) -> bool:
        drop = impulse_high - impulse_low
        if drop <= 0:
            return False
        retrace = (current_price - impulse_low) / drop
        return retrace >= self.cfg.bounce_retrace_pct

    def reclaim_level(self, impulse_high: float, impulse_low: float) -> float:
        drop = impulse_high - impulse_low
        return impulse_high - drop * self.cfg.reclaim_ratio

    def hold_confirmed(self, hold_start: datetime, now: datetime) -> bool:
        return (now - hold_start).total_seconds() >= self.cfg.hold_time_sec

    def post_impulse_timed_out(self, start: datetime, now: datetime) -> bool:
        return (now - start).total_seconds() > self.cfg.post_impulse_timeout_sec

    def position_timed_out(self, entry_time: datetime, now: datetime) -> bool:
        return (now - entry_time).total_seconds() > self.cfg.position_timeout_sec

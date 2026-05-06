from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    symbol: str = "BTCUSDT"

    impulse_pct: float = 0.003
    impulse_max_seconds: float = 2.0
    bounce_retrace_pct: float = 0.4
    reclaim_ratio: float = 0.5
    hold_time_sec: float = 2.0
    post_impulse_timeout_sec: float = 8.0

    tp_pct: float = 0.002
    sl_buffer_pct: float = 0.0005
    position_timeout_sec: float = 15.0

    max_spread_pct: float = 0.0003
    stale_ms: int = 1000

    require_volume_confirmation: bool = False
    rolling_window_sec: float = 5.0

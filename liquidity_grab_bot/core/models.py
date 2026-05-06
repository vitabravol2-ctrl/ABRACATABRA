from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Tick:
    timestamp: datetime
    bid: float
    ask: float
    mid: float
    volume: Optional[float] = None


@dataclass
class Trade:
    entry_time: datetime
    entry_price: float
    tp_price: float
    sl_price: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    pnl_pct: Optional[float] = None

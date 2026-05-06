from enum import Enum, auto
from typing import List, Optional

from config import Config
from core.detector import LiquidityGrabDetector
from core.logger import BotLogger
from core.models import Tick, Trade
from core.risk import build_trade, finalize_trade
from data.market_buffer import MarketBuffer


class State(Enum):
    INIT = auto()
    WAIT = auto()
    IMPULSE_DETECT = auto()
    POST_IMPULSE = auto()
    RECLAIM = auto()
    HOLD_CONFIRM = auto()
    ENTRY_READY = auto()
    IN_POSITION = auto()
    EXIT = auto()
    RESET = auto()


class LiquidityGrabFSM:
    def __init__(self, cfg: Config, buffer: MarketBuffer, logger: BotLogger) -> None:
        self.cfg = cfg
        self.buffer = buffer
        self.logger = logger
        self.detector = LiquidityGrabDetector(cfg)
        self.state = State.INIT
        self.trades: List[Trade] = []
        self.current_trade: Optional[Trade] = None
        self.impulse_high: Optional[float] = None
        self.impulse_low: Optional[float] = None
        self.impulse_start_tick: Optional[Tick] = None
        self.post_impulse_start = None
        self.hold_start = None
        self.exit_reason: Optional[str] = None
        self._transition(State.WAIT, "initialized")

    def _transition(self, new_state: State, msg: str) -> None:
        self.logger.log(self.state.name, "TRANSITION", f"{self.state.name} -> {new_state.name}: {msg}")
        self.state = new_state

    def on_tick(self, tick: Tick) -> None:
        self.buffer.add_tick(tick)

        if self.state == State.WAIT:
            if self.buffer.is_stale(tick.timestamp, self.cfg.stale_ms):
                self.logger.log(self.state.name, "STALE", "Stale data detected")
                return
            spread = self.buffer.spread_pct(tick)
            if spread > self.cfg.max_spread_pct:
                self.logger.log(self.state.name, "SPREAD", f"Spread too high: {spread:.6f}")
                return

            high, low = self.buffer.rolling_high_low()
            if high is None or low is None:
                return
            drop_pct = self.buffer.drop_pct()
            if drop_pct >= self.cfg.impulse_pct:
                self.impulse_high = high
                self.impulse_low = low
                self.impulse_start_tick = tick
                self._transition(State.IMPULSE_DETECT, f"drop={drop_pct:.4%}")

        if self.state == State.IMPULSE_DETECT:
            if not self.impulse_start_tick or self.impulse_high is None or self.impulse_low is None:
                self._transition(State.RESET, "missing impulse context")
            else:
                drop_pct = (self.impulse_high - self.impulse_low) / self.impulse_high
                elapsed = (tick.timestamp - self.impulse_start_tick.timestamp).total_seconds()
                if self.detector.impulse_confirmed(drop_pct, elapsed):
                    self.post_impulse_start = tick.timestamp
                    self._transition(State.POST_IMPULSE, f"impulse confirmed drop={drop_pct:.4%}")
                else:
                    self._transition(State.RESET, "impulse not confirmed")

        if self.state == State.POST_IMPULSE:
            if self.detector.post_impulse_timed_out(self.post_impulse_start, tick.timestamp):
                self._transition(State.RESET, "post-impulse timeout")
            elif self.detector.bounce_confirmed(self.impulse_high, self.impulse_low, tick.mid):
                self._transition(State.RECLAIM, "bounce confirmed")

        if self.state == State.RECLAIM:
            reclaim = self.detector.reclaim_level(self.impulse_high, self.impulse_low)
            if tick.mid < self.impulse_low:
                self._transition(State.RESET, "new low during reclaim")
            elif tick.mid >= reclaim:
                self.hold_start = tick.timestamp
                self._transition(State.HOLD_CONFIRM, f"reclaim level reached {reclaim:.2f}")

        if self.state == State.HOLD_CONFIRM:
            reclaim = self.detector.reclaim_level(self.impulse_high, self.impulse_low)
            spread = self.buffer.spread_pct(tick)
            if tick.mid < self.impulse_low:
                self._transition(State.RESET, "new low during hold")
            elif tick.mid < reclaim:
                self.hold_start = tick.timestamp
                self.logger.log(self.state.name, "HOLD", "Hold restarted below reclaim")
            elif spread > self.cfg.max_spread_pct:
                self.logger.log(self.state.name, "SPREAD", "Spread high; waiting")
            else:
                elapsed = (tick.timestamp - self.hold_start).total_seconds()
                self.logger.log(self.state.name, "HOLD", f"elapsed={elapsed:.2f}s reclaim={reclaim:.2f} mid={tick.mid:.2f}")
                if self.detector.hold_confirmed(self.hold_start, tick.timestamp):
                    self._transition(State.ENTRY_READY, "hold confirmed")

        if self.state == State.ENTRY_READY:
            self.current_trade = build_trade(tick, self.impulse_low, self.cfg.tp_pct, self.cfg.sl_buffer_pct)
            self.logger.log(self.state.name, "ENTRY", f"BUY @ {self.current_trade.entry_price:.2f}")
            self._transition(State.IN_POSITION, "virtual position opened")

        if self.state == State.IN_POSITION:
            if tick.mid >= self.current_trade.tp_price:
                self.exit_reason = "TP"
                self._transition(State.EXIT, "take-profit reached")
            elif tick.mid <= self.current_trade.sl_price:
                self.exit_reason = "SL"
                self._transition(State.EXIT, "stop-loss reached")
            elif self.detector.position_timed_out(self.current_trade.entry_time, tick.timestamp):
                self.exit_reason = "TIMEOUT"
                self._transition(State.EXIT, "position timeout")

        if self.state == State.EXIT:
            finished = finalize_trade(self.current_trade, tick, self.exit_reason)
            self.trades.append(finished)
            self.logger.log(self.state.name, "EXIT", f"{finished.exit_reason} pnl={finished.pnl_pct:.4%}")
            self._transition(State.RESET, "trade closed")

        if self.state == State.RESET:
            self.impulse_high = None
            self.impulse_low = None
            self.impulse_start_tick = None
            self.post_impulse_start = None
            self.hold_start = None
            self.current_trade = None
            self.exit_reason = None
            self._transition(State.WAIT, "context reset")

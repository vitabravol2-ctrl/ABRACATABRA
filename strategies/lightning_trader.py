from __future__ import annotations
from typing import Any, Dict
from .base_strategy import BaseStrategy


class LightningTraderStrategy(BaseStrategy):
    name = "Lightning Trader BTCUSDT"
    version = "0.3"
    description = "Momentum/spread dry-run strategy for BTCUSDT."
    risk_profile = "MEDIUM"
    compatible_symbols = ["BTCUSDT"]

    def default_settings(self) -> Dict[str, Any]:
        return {
            "market": {
                "candle_interval_fast": "1m",
                "candle_interval_slow": "5m",
                "order_book_depth": 20,
                "max_data_age_ms": 1500,
            },
            "entry": {
                "min_spread_bps": 1.0,
                "min_edge_bps": 2.0,
                "entry_order_type": "LIMIT",
                "entry_reprice_ms": 1500,
                "entry_timeout_ms": 8000,
            },
            "exit": {
                "take_profit_bps": 12.0,
                "emergency_exit_bps": 18.0,
                "trailing_enabled": True,
                "trailing_start_bps": 10.0,
                "trailing_step_bps": 4.0,
                "max_hold_seconds": 120,
            },
            "risk": {
                "max_order_usdt": 50.0,
                "max_daily_loss_usdt": 20.0,
                "max_trades_per_day": 20,
                "max_open_position_usdt": 250.0,
                "stop_after_errors": 5,
            },
        }

    def validate_settings(self, settings: Dict[str, Any]) -> tuple[bool, str]:
        return True, "ok"

    def analyze(self, snapshot: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        return {"decision": "WAIT", "reason": "delegated-to-engine"}

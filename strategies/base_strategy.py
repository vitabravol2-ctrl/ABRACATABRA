from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseStrategy(ABC):
    name: str = "Base Strategy"
    version: str = "0.1"
    description: str = "Abstract strategy"
    risk_profile: str = "MEDIUM"
    compatible_symbols = ["BTCUSDT"]

    @abstractmethod
    def default_settings(self) -> Dict[str, Any]:
        ...

    @abstractmethod
    def validate_settings(self, settings: Dict[str, Any]) -> tuple[bool, str]:
        ...

    @abstractmethod
    def analyze(self, snapshot: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        ...

    def on_start(self) -> None:
        pass

    def on_pause(self) -> None:
        pass

    def on_stop(self) -> None:
        pass

    def on_order_update(self) -> None:
        pass

    def get_status(self) -> str:
        return "IDLE"

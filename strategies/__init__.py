from .base_strategy import BaseStrategy
from .lightning_trader import LightningTraderStrategy
from .basic_scalper import BasicScalperStrategy
from .adaptive_grid import AdaptiveGridStrategy
from .martingale_scalper import MartingaleScalperStrategy


def build_strategy_catalog():
    return [
        LightningTraderStrategy(),
        BasicScalperStrategy(),
        AdaptiveGridStrategy(),
        MartingaleScalperStrategy(),
    ]

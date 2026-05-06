from .lightning_trader import LightningTraderStrategy


class BasicScalperStrategy(LightningTraderStrategy):
    name = "Basic Scalper"
    version = "0.1"
    description = "Simple spread scalper template."
    risk_profile = "LOW"

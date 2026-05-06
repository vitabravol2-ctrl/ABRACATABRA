import json
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen


API_BASE = "https://api.binance.com"
SYMBOL = "BTCUSDT"
ALGO_NAME = "BASIC SCALPER"
MAX_ORDER_USDT = 50
MAX_DAILY_LOSS_USDT = 20
MAX_TRADES_PER_DAY = 20


@dataclass
class PairState:
    price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    spread_abs: float = 0.0
    spread_pct: float = 0.0
    change_24h: float = 0.0
    volume_24h_btc: float = 0.0

    ws_ok: bool = False
    api_ok: bool = False
    latency_ms: int = 0
    last_update: str = "--:--:--"

    usdt_free: float = 1250.0
    btc_free: float = 0.0182
    est_value_usdt: float = 0.0

    algo_status: str = "IDLE / READY"
    algo_mode: str = "DRY-RUN"

    signal: str = "WAIT"
    reason: str = "collecting market data"

    error: Optional[str] = field(default=None)


def fmt_float(value: float, digits: int = 2) -> str:
    return f"{value:,.{digits}f}".replace(",", " ")


def fetch_json(path: str) -> dict:
    url = f"{API_BASE}{path}"
    req = Request(url, headers={"User-Agent": "PairInfoCard/1.0"})
    with urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


class MarketPoller(threading.Thread):
    def __init__(self, state: PairState):
        super().__init__(daemon=True)
        self.state = state
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            started = time.perf_counter()
            try:
                ticker = fetch_json(f"/api/v3/ticker/24hr?symbol={SYMBOL}")
                book = fetch_json(f"/api/v3/ticker/bookTicker?symbol={SYMBOL}")

                price = float(ticker.get("lastPrice", 0.0))
                bid = float(book.get("bidPrice", 0.0))
                ask = float(book.get("askPrice", 0.0))
                spread_abs = max(ask - bid, 0.0)
                spread_pct = (spread_abs / ask * 100.0) if ask else 0.0

                self.state.price = price
                self.state.bid = bid
                self.state.ask = ask
                self.state.spread_abs = spread_abs
                self.state.spread_pct = spread_pct
                self.state.change_24h = float(ticker.get("priceChangePercent", 0.0))
                self.state.volume_24h_btc = float(ticker.get("volume", 0.0))

                self.state.api_ok = True
                self.state.ws_ok = True
                self.state.error = None

                self.state.est_value_usdt = self.state.usdt_free + self.state.btc_free * price

                if spread_pct > 0.015:
                    self.state.signal = "WAIT"
                    self.state.reason = "spread too wide"
                elif abs(self.state.change_24h) > 5:
                    self.state.signal = "STOP"
                    self.state.reason = "high volatility guard"
                else:
                    self.state.signal = "WAIT"
                    self.state.reason = "no setup"

                self.state.last_update = datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S")
                self.state.latency_ms = int((time.perf_counter() - started) * 1000)
            except (URLError, HTTPError, TimeoutError, ValueError) as e:
                self.state.api_ok = False
                self.state.ws_ok = False
                self.state.error = str(e)
                self.state.signal = "STOP"
                self.state.reason = "data unavailable"

            time.sleep(1.0)


class PairInfoCardApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("BTCUSDT Spot Pair Info Card")
        self.root.geometry("760x490")
        self.root.configure(bg="#111827")

        self.state = PairState()
        self.poller = MarketPoller(self.state)
        self.poller.start()

        self.title_var = tk.StringVar(value="BTCUSDT  •  WS: ...  API: ...")
        self.market_var = tk.StringVar()
        self.connection_var = tk.StringVar()
        self.balance_var = tk.StringVar()
        self.algorithm_var = tk.StringVar()
        self.signal_var = tk.StringVar()
        self.risk_var = tk.StringVar()

        card = tk.Frame(root, bg="#0b1220", bd=0, highlightbackground="#2b3952", highlightthickness=1)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        self._section_title(card, self.title_var).pack(fill="x", padx=14, pady=(14, 8))
        self._separator(card)
        self._section_body(card, self.market_var).pack(fill="x", padx=14, pady=8)
        self._separator(card)
        self._section_body(card, self.connection_var).pack(fill="x", padx=14, pady=8)
        self._separator(card)
        self._section_body(card, self.balance_var).pack(fill="x", padx=14, pady=8)
        self._separator(card)
        self._section_body(card, self.algorithm_var).pack(fill="x", padx=14, pady=8)
        self._separator(card)
        self._section_body(card, self.signal_var).pack(fill="x", padx=14, pady=8)
        self._separator(card)
        self._section_body(card, self.risk_var).pack(fill="x", padx=14, pady=(8, 14))

        self.refresh_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _section_title(self, parent, var):
        return tk.Label(
            parent,
            textvariable=var,
            justify="left",
            anchor="w",
            font=("Segoe UI", 14, "bold"),
            bg="#0b1220",
            fg="#d6e3ff",
        )

    def _section_body(self, parent, var):
        return tk.Label(
            parent,
            textvariable=var,
            justify="left",
            anchor="w",
            font=("Consolas", 12),
            bg="#0b1220",
            fg="#c9d5f0",
        )

    def _separator(self, parent):
        sep = tk.Frame(parent, height=1, bg="#2b3952")
        sep.pack(fill="x", padx=12)

    def refresh_ui(self):
        st = self.state
        ws_mark = "🟢" if st.ws_ok else "🔴"
        api_mark = "🟢" if st.api_ok else "🔴"
        self.title_var.set(f"BTCUSDT  •  WS {ws_mark}  API {api_mark}")

        self.market_var.set(
            f"Market\n"
            f"Price: {fmt_float(st.price)}      Change 24h: {st.change_24h:+.2f}%\n"
            f"Bid:   {fmt_float(st.bid)}      Ask: {fmt_float(st.ask)}\n"
            f"Spread: {st.spread_abs:.2f} / {st.spread_pct:.5f}%\n"
            f"Volume 24h: {fmt_float(st.volume_24h_btc, 0)} BTC"
        )

        conn_error = f" | error: {st.error[:60]}" if st.error else ""
        self.connection_var.set(
            f"Connection\n"
            f"Last update: {st.last_update}      Latency: {st.latency_ms} ms{conn_error}"
        )

        self.balance_var.set(
            f"Balance\n"
            f"USDT free: {fmt_float(st.usdt_free)}     BTC free: {st.btc_free:.4f}\n"
            f"Est. value: {fmt_float(st.est_value_usdt)} USDT"
        )

        self.algorithm_var.set(
            f"Algorithm\n"
            f"Name: {ALGO_NAME}\n"
            f"Status: {st.algo_status}\n"
            f"Mode: {st.algo_mode}"
        )

        self.signal_var.set(
            f"Signal\n"
            f"Decision: {st.signal}\n"
            f"Reason: {st.reason}"
        )

        self.risk_var.set(
            f"Risk\n"
            f"Max order: {MAX_ORDER_USDT} USDT | Max daily loss: {MAX_DAILY_LOSS_USDT} USDT\n"
            f"Max trades/day: {MAX_TRADES_PER_DAY} | Stop: on API/WS failure"
        )

        self.root.after(500, self.refresh_ui)

    def on_close(self):
        self.poller.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = PairInfoCardApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

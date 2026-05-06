import csv
import json
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from tkinter import ttk, messagebox
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

API_BASE = "https://api.binance.com"
SYMBOL = "BTCUSDT"


class ReasonCode(str, Enum):
    MARKET_OK = "MARKET_OK"
    MARKET_DANGER = "MARKET_DANGER"
    DATA_STALE = "DATA_STALE"
    SPREAD_TOO_SMALL = "SPREAD_TOO_SMALL"
    EDGE_TOO_SMALL = "EDGE_TOO_SMALL"
    BALANCE_LOW = "BALANCE_LOW"
    RISK_LIMIT = "RISK_LIMIT"
    ENTRY_READY = "ENTRY_READY"
    ENTRY_CANCELLED = "ENTRY_CANCELLED"
    BUY_FILLED = "BUY_FILLED"
    SELL_PLACED = "SELL_PLACED"
    TAKE_PROFIT_READY = "TAKE_PROFIT_READY"
    EMERGENCY_EXIT = "EMERGENCY_EXIT"
    TRAILING_ACTIVE = "TRAILING_ACTIVE"
    POSITION_CLOSED = "POSITION_CLOSED"
    WAIT = "WAIT"


@dataclass
class PairState:
    price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    spread_abs: float = 0.0
    spread_bps: float = 0.0
    change_24h: float = 0.0
    volume_24h_btc: float = 0.0
    ws_ok: bool = False
    api_ok: bool = False
    latency_ms: int = 0
    last_update: str = "--:--:--"
    usdt_free: float = 1250.0
    btc_free: float = 0.0182
    algo_status: str = "DISABLED"
    algo_mode: str = "DRY-RUN"
    signal: str = "WAIT"
    reason: str = ReasonCode.WAIT.value
    current_position_btc: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl_today: float = 0.0
    error: Optional[str] = field(default=None)


@dataclass
class AlgoSettings:
    market: Dict[str, Any] = field(default_factory=lambda: {
        "symbol": "BTCUSDT",
        "candle_interval_fast": "1m",
        "candle_interval_slow": "5m",
        "order_book_depth": 20,
        "max_data_age_ms": 1500,
    })
    risk: Dict[str, Any] = field(default_factory=lambda: {
        "max_order_usdt": 50.0,
        "max_daily_loss_usdt": 20.0,
        "max_trades_per_day": 20,
        "max_open_position_usdt": 250.0,
        "stop_after_errors": 5,
        "emergency_exit_enabled": True,
    })
    entry: Dict[str, Any] = field(default_factory=lambda: {
        "min_spread_bps": 1.0,
        "min_edge_bps": 2.0,
        "entry_order_type": "LIMIT",
        "entry_reprice_ms": 1500,
        "entry_timeout_ms": 8000,
        "allow_buy_only_if_market_ok": True,
    })
    exit: Dict[str, Any] = field(default_factory=lambda: {
        "take_profit_bps": 12.0,
        "emergency_exit_bps": 18.0,
        "trailing_enabled": True,
        "trailing_start_bps": 10.0,
        "trailing_step_bps": 4.0,
        "max_hold_seconds": 120,
    })


def fetch_json(path: str) -> dict:
    req = Request(f"{API_BASE}{path}", headers={"User-Agent": "LightningTrader/0.1"})
    with urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


class TradeJournal:
    def __init__(self, json_path="trade_journal.json", csv_path="trade_journal.csv"):
        self.json_path = Path(json_path)
        self.csv_path = Path(csv_path)
        self.records: List[Dict[str, Any]] = []

    def log(self, step: int, message: str, reason: ReasonCode, extra: Optional[Dict[str, Any]] = None):
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "step": step,
            "message": message,
            "reason": reason.value,
            "extra": extra or {},
        }
        self.records.append(row)
        self.json_path.write_text(json.dumps(self.records[-300:], ensure_ascii=False, indent=2), encoding="utf-8")
        write_header = not self.csv_path.exists()
        with self.csv_path.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["ts", "step", "message", "reason", "extra"])
            if write_header:
                w.writeheader()
            w.writerow({**row, "extra": json.dumps(row["extra"], ensure_ascii=False)})


class MarketBrain:
    def analyze(self, state: PairState, settings: AlgoSettings) -> Tuple[str, ReasonCode, Dict[str, Any]]:
        regime = "FLAT"
        if state.latency_ms > settings.market["max_data_age_ms"]:
            return "DANGER", ReasonCode.DATA_STALE, {"latency_ms": state.latency_ms}
        if abs(state.change_24h) > 5:
            regime = "VOLATILE"
        if state.spread_bps > 15:
            regime = "DANGER"
            return regime, ReasonCode.MARKET_DANGER, {}
        if state.change_24h > 1:
            regime = "TREND_UP"
        elif state.change_24h < -1:
            regime = "TREND_DOWN"
        return regime, ReasonCode.MARKET_OK, {"spread_bps": state.spread_bps}


class RiskBrain:
    def approve(self, state: PairState, settings: AlgoSettings, trades_today: int) -> Tuple[bool, float, ReasonCode]:
        max_order = float(settings.risk["max_order_usdt"])
        if state.usdt_free < 10:
            return False, 0.0, ReasonCode.BALANCE_LOW
        if trades_today >= int(settings.risk["max_trades_per_day"]):
            return False, 0.0, ReasonCode.RISK_LIMIT
        size_usdt = min(max_order, state.usdt_free * 0.2)
        return True, size_usdt, ReasonCode.MARKET_OK


class EntryBrain:
    def decide(self, state: PairState, regime: str, settings: AlgoSettings) -> Tuple[str, Optional[float], ReasonCode, str]:
        if regime in {"DANGER", "VOLATILE"} and settings.entry["allow_buy_only_if_market_ok"]:
            return "WAIT", None, ReasonCode.MARKET_DANGER, "market regime not safe"
        if state.spread_bps < float(settings.entry["min_spread_bps"]):
            return "WAIT", None, ReasonCode.SPREAD_TOO_SMALL, "spread too small"
        edge = max(0.0, 8.0 - state.spread_bps)
        if edge < float(settings.entry["min_edge_bps"]):
            return "WAIT", None, ReasonCode.EDGE_TOO_SMALL, "edge below threshold"
        return "BUY", state.bid, ReasonCode.ENTRY_READY, "entry conditions met"


class ExitBrain:
    def decide(self, entry_price: float, last_price: float, highest_price: float, hold_sec: int, settings: AlgoSettings) -> Tuple[str, ReasonCode, Dict[str, Any]]:
        if entry_price <= 0:
            return "HOLD", ReasonCode.WAIT, {}
        pnl_bps = (last_price - entry_price) / entry_price * 10000
        if pnl_bps <= -float(settings.exit["emergency_exit_bps"]):
            return "EXIT_NOW", ReasonCode.EMERGENCY_EXIT, {"pnl_bps": pnl_bps}
        if pnl_bps >= float(settings.exit["take_profit_bps"]):
            return "SELL", ReasonCode.TAKE_PROFIT_READY, {"pnl_bps": pnl_bps}
        if settings.exit["trailing_enabled"] and highest_price > entry_price:
            trail_line = highest_price * (1 - float(settings.exit["trailing_step_bps"]) / 10000)
            if last_price < trail_line and pnl_bps > float(settings.exit["trailing_start_bps"]):
                return "SELL", ReasonCode.TRAILING_ACTIVE, {"trail_line": trail_line}
        if hold_sec > int(settings.exit["max_hold_seconds"]):
            return "EXIT_NOW", ReasonCode.ENTRY_CANCELLED, {"hold_sec": hold_sec}
        return "HOLD", ReasonCode.WAIT, {"pnl_bps": pnl_bps}


class OrderBrain:
    def __init__(self):
        self.active_order: Optional[Dict[str, Any]] = None

    def place_limit(self, side: str, price: float, qty_btc: float, mode: str) -> Tuple[bool, str]:
        oid = f"{side}-{int(time.time()*1000)}"
        if self.active_order and self.active_order.get("side") == side:
            return False, "duplicate prevented"
        self.active_order = {"id": oid, "side": side, "price": price, "qty": qty_btc, "mode": mode, "status": "NEW"}
        return True, oid

    def clear(self):
        self.active_order = None


class LightningTraderEngine:
    def __init__(self, state: PairState, settings: AlgoSettings):
        self.state = state
        self.settings = settings
        self.market = MarketBrain()
        self.risk = RiskBrain()
        self.entry = EntryBrain()
        self.exit = ExitBrain()
        self.order = OrderBrain()
        self.journal = TradeJournal()
        self.running = False
        self.paused = False
        self.live_locked = True
        self.trades_today = 0
        self.entry_price = 0.0
        self.entry_ts = 0.0
        self.highest_price = 0.0

    def start(self):
        self.running = True
        self.paused = False
        self.state.algo_status = "ENABLED"

    def pause(self):
        self.paused = True
        self.state.algo_status = "PAUSED"

    def stop(self):
        self.running = False
        self.paused = False
        self.order.clear()
        self.state.algo_status = "DISABLED"

    def step(self):
        if not self.running or self.paused:
            return
        regime, m_reason, snap = self.market.analyze(self.state, self.settings)
        self.journal.log(20, "market analyzed", m_reason, {"regime": regime, **snap})
        allowed, size_usdt, r_reason = self.risk.approve(self.state, self.settings, self.trades_today)
        if not allowed:
            self.state.signal, self.state.reason = "WAIT", r_reason.value
            self.journal.log(30, "risk rejected", r_reason)
            return

        if self.state.current_position_btc <= 0:
            decision, limit_price, e_reason, note = self.entry.decide(self.state, regime, self.settings)
            self.state.signal, self.state.reason = decision, e_reason.value
            self.journal.log(34, note, e_reason)
            if decision == "BUY" and limit_price:
                qty = round(size_usdt / limit_price, 6)
                ok, oid = self.order.place_limit("BUY", limit_price, qty, self.state.algo_mode)
                if ok:
                    self.state.current_position_btc = qty
                    self.entry_price = limit_price
                    self.entry_ts = time.time()
                    self.highest_price = limit_price
                    self.trades_today += 1
                    self.state.reason = ReasonCode.BUY_FILLED.value
                    self.journal.log(39, "buy filled (simulated)", ReasonCode.BUY_FILLED, {"oid": oid, "qty": qty})
        else:
            self.highest_price = max(self.highest_price, self.state.price)
            hold_sec = int(time.time() - self.entry_ts)
            decision, x_reason, extra = self.exit.decide(self.entry_price, self.state.price, self.highest_price, hold_sec, self.settings)
            self.state.signal, self.state.reason = decision, x_reason.value
            self.journal.log(45, "exit decision", x_reason, extra)
            if decision in {"SELL", "EXIT_NOW"}:
                ok, _ = self.order.place_limit("SELL", self.state.ask or self.state.price, self.state.current_position_btc, self.state.algo_mode)
                if ok:
                    pnl = (self.state.price - self.entry_price) * self.state.current_position_btc
                    self.state.realized_pnl_today += pnl
                    self.state.current_position_btc = 0
                    self.state.unrealized_pnl = 0
                    self.entry_price = 0.0
                    self.order.clear()
                    self.journal.log(49, "position closed", ReasonCode.POSITION_CLOSED, {"pnl": pnl})
            else:
                self.state.unrealized_pnl = (self.state.price - self.entry_price) * self.state.current_position_btc


class MarketPoller(threading.Thread):
    def __init__(self, state: PairState):
        super().__init__(daemon=True)
        self.state = state
        self._running = True

    def stop(self): self._running = False

    def run(self):
        while self._running:
            started = time.perf_counter()
            try:
                ticker = fetch_json(f"/api/v3/ticker/24hr?symbol={SYMBOL}")
                book = fetch_json(f"/api/v3/ticker/bookTicker?symbol={SYMBOL}")
                self.state.price = float(ticker.get("lastPrice", 0))
                self.state.bid = float(book.get("bidPrice", 0))
                self.state.ask = float(book.get("askPrice", 0))
                self.state.spread_abs = max(self.state.ask - self.state.bid, 0)
                self.state.spread_bps = (self.state.spread_abs / self.state.ask * 10000) if self.state.ask else 0
                self.state.change_24h = float(ticker.get("priceChangePercent", 0))
                self.state.volume_24h_btc = float(ticker.get("volume", 0))
                self.state.api_ok = self.state.ws_ok = True
                self.state.error = None
                self.state.last_update = datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S")
                self.state.latency_ms = int((time.perf_counter() - started) * 1000)
            except (URLError, HTTPError, TimeoutError, ValueError) as e:
                self.state.api_ok = self.state.ws_ok = False
                self.state.error = str(e)
                self.state.signal = "WAIT"
                self.state.reason = ReasonCode.DATA_STALE.value
            time.sleep(1)


class PairInfoCardApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Lightning Trader BTCUSDT v0.1")
        self.root.geometry("980x680")
        self.state = PairState()
        self.settings = AlgoSettings()
        self.engine = LightningTraderEngine(self.state, self.settings)
        self.poller = MarketPoller(self.state)
        self.poller.start()

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True)
        self.dashboard = tk.Text(nb, height=20)
        self.algos = tk.Frame(nb)
        self.settings_frame = tk.Text(nb)
        nb.add(self.dashboard, text="BTCUSDT Card")
        nb.add(self.algos, text="Algorithms")
        nb.add(self.settings_frame, text="Settings")

        self.log_box = tk.Text(self.algos, height=16, width=95)
        self.log_box.pack(padx=8, pady=8)
        controls = tk.Frame(self.algos)
        controls.pack()
        tk.Button(controls, text="Start", command=self.engine.start).pack(side="left", padx=4)
        tk.Button(controls, text="Pause", command=self.engine.pause).pack(side="left", padx=4)
        tk.Button(controls, text="Stop", command=self.engine.stop).pack(side="left", padx=4)
        tk.Button(controls, text="LIVE", command=self._live_warn).pack(side="left", padx=4)

        self._render_settings()
        self.refresh()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _live_warn(self):
        messagebox.showwarning("LIVE locked", "LIVE mode locked. Manual confirmation workflow not implemented.")

    def _render_settings(self):
        data = asdict(self.settings)
        lines = ["Lightning Trader BTCUSDT settings\n"]
        for grp, vals in data.items():
            lines.append(f"[{grp.upper()}]")
            for k, v in vals.items():
                lines.append(f"{k} = {v}")
            lines.append("")
        self.settings_frame.delete("1.0", tk.END)
        self.settings_frame.insert("1.0", "\n".join(lines))

    def refresh(self):
        self.engine.step()
        s = self.state
        text = (
            f"price={s.price:.2f} bid={s.bid:.2f} ask={s.ask:.2f} spread={s.spread_bps:.2f}bps\n"
            f"24h={s.change_24h:+.2f}% volume={s.volume_24h_btc:.0f} ws={s.ws_ok} api={s.api_ok} latency={s.latency_ms}ms\n"
            f"USDT={s.usdt_free:.2f} BTC={s.btc_free:.6f} algo={s.algo_status} mode={s.algo_mode}\n"
            f"decision={s.signal} reason={s.reason} pos={s.current_position_btc:.6f} uPnL={s.unrealized_pnl:.2f} rPnL={s.realized_pnl_today:.2f}\n"
        )
        self.dashboard.delete("1.0", tk.END)
        self.dashboard.insert("1.0", text)
        if self.engine.journal.records:
            last = self.engine.journal.records[-8:]
            self.log_box.delete("1.0", tk.END)
            for rec in last:
                self.log_box.insert(tk.END, f"{rec['ts']} [{rec['step']:02d}] {rec['reason']} {rec['message']}\n")
        self.root.after(1000, self.refresh)

    def on_close(self):
        self.engine.stop()
        self.poller.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    PairInfoCardApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

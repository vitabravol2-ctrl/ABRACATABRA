import csv
import json
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from strategies import build_strategy_catalog

API_BASE = "https://api.binance.com"


class ReasonCode(str, Enum):
    MARKET_OK = "MARKET_OK"
    MARKET_DANGER = "MARKET_DANGER"
    DATA_STALE = "DATA_STALE"
    SPREAD_TOO_SMALL = "SPREAD_TOO_SMALL"
    WAIT = "WAIT"


class StrategyCommand(str, Enum):
    WAIT = "WAIT"
    BUY_LIMIT = "BUY_LIMIT"
    SELL_LIMIT = "SELL_LIMIT"
    CANCEL_ALL = "CANCEL_ALL"
    EXIT_POSITION = "EXIT_POSITION"


@dataclass
class PairState:
    symbol: str = "BTCUSDT"
    price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    spread_bps: float = 0.0
    ws_ok: bool = False
    api_ok: bool = False
    latency_ms: int = 0
    market_state: str = "FLAT"
    selected_algo: str = "Lightning Trader BTCUSDT"
    algo_status: str = "STOPPED"
    decision: str = "WAIT"
    risk_level: str = "LOW"
    data_health: str = "LOST"
    position_state: str = "NONE"
    spread_state: str = "BAD"
    profit_state: str = "ZERO"
    reason: str = ReasonCode.WAIT.value
    current_position_btc: float = 0.0
    entry_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    last_command: str = StrategyCommand.WAIT.value
    last_order_status: str = "--"
    last_fill: str = "--"
    mode: str = "DRY-RUN"
    live_locked: bool = True
    updated_at: str = "--"


@dataclass
class AlgoSettings:
    market: Dict[str, Any] = field(default_factory=lambda: {
        "data_source_mode": "HYBRID",
        "max_data_age_ms": 1500,
        "max_latency_ms": 1500,
        "reconnect_enabled": True,
        "order_book_depth": 20,
        "candle_intervals": "1m,5m",
    })
    entry: Dict[str, Any] = field(default_factory=lambda: {"min_spread_bps": 1.0})
    risk: Dict[str, Any] = field(default_factory=lambda: {
        "max_order_usdt": 50.0,
        "max_daily_loss_usdt": 20.0,
        "max_trades_per_day": 20,
        "max_position_usdt": 250.0,
        "stop_after_errors": 5,
        "data_stale_blocks_trading": True,
    })


def fetch_json(path: str) -> dict:
    req = Request(f"{API_BASE}{path}", headers={"User-Agent": "LightningTrader/0.3"})
    with urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


class OrderManager:
    def __init__(self):
        self.active_orders: Dict[str, Dict[str, Any]] = {}
        self.history: List[Dict[str, Any]] = []

    def add_filled(self, order: Dict[str, Any]):
        order["status"] = "FILLED"
        self.history.append(order)


class DryRunEngine:
    def __init__(self, state: PairState):
        self.state = state
        self.position_qty = 0.0
        self.avg_entry = 0.0

    def buy(self, qty: float, price: float):
        cost_before = self.position_qty * self.avg_entry
        self.position_qty += qty
        self.avg_entry = (cost_before + qty * price) / self.position_qty if self.position_qty else 0.0
        self.state.current_position_btc = self.position_qty
        self.state.entry_price = self.avg_entry
        self.state.last_fill = f"BUY {qty:.6f} @ {price:.2f}"

    def sell_all(self, price: float):
        qty = self.position_qty
        pnl = (price - self.avg_entry) * qty
        self.state.realized_pnl += pnl
        self.position_qty = 0.0
        self.avg_entry = 0.0
        self.state.current_position_btc = 0.0
        self.state.entry_price = 0.0
        self.state.last_fill = f"SELL {qty:.6f} @ {price:.2f}"

    def update_unrealized(self):
        self.state.unrealized_pnl = (self.state.price - self.avg_entry) * self.position_qty if self.position_qty else 0.0


class LightningTraderEngine:
    def __init__(self, state: PairState, settings: AlgoSettings):
        self.state = state
        self.settings = settings
        self.running = False
        self.paused = False
        self.orders = OrderManager()
        self.dry_run = DryRunEngine(state)
        self.events: List[Dict[str, str]] = []
        self._order_seq = 0

    def add_event(self, level: str, module: str, code: str, message: str):
        self.events.append({"time": datetime.now().strftime("%H:%M:%S"), "level": level, "module": module, "code": code, "message": message})
        self.events = self.events[-30:]

    def start(self):
        if self.state.live_locked and self.state.mode != "DRY-RUN":
            self.add_event("ERROR", "SAFETY", "LIVE_LOCKED", "LIVE mode locked")
            return
        self.running = True
        self.paused = False
        self.state.algo_status = "RUNNING"
        self.add_event("OK", "CORE", "START", "Strategy started")

    def pause(self):
        self.paused = True
        self.state.algo_status = "PAUSED"
        self.add_event("WARNING", "CORE", "PAUSE", "Strategy paused")

    def stop(self):
        self.running = False
        self.paused = False
        self.state.algo_status = "STOPPED"
        self.add_event("OK", "CORE", "STOP", "Strategy stopped")

    def emergency_stop(self):
        self.stop()
        self.state.decision = "CANCEL"
        self.add_event("ERROR", "SAFETY", "E_STOP", "Emergency stop activated")

    def cancel_all(self):
        self.state.last_command = StrategyCommand.CANCEL_ALL.value
        self.add_event("ORDER", "CORE", "CANCEL_ALL", "Canceled all active orders")

    def step(self):
        if not self.running or self.paused:
            return
        self.state.data_health = "STALE" if self.state.latency_ms > self.settings.market["max_data_age_ms"] else "FRESH"
        self.state.market_state = "DANGER" if self.state.spread_bps > 15 else "FLAT"
        self.state.spread_state = "BAD" if self.state.spread_bps > 8 else "GOOD"
        self.state.risk_level = "BLOCKED" if self.state.data_health == "STALE" else "LOW"

        if self.state.market_state == "DANGER" or self.state.data_health == "STALE":
            self.state.decision = "WAIT"
            self.add_event("WARNING", "STRATEGY", "WAIT", "Market danger or stale data")
            return

        if self.state.current_position_btc == 0 and self.state.bid > 0:
            qty = 0.0005
            self._order_seq += 1
            self.dry_run.buy(qty, self.state.bid)
            self.orders.add_filled({"order_id": f"DRY-{self._order_seq:06d}", "symbol": self.state.symbol, "side": "BUY", "type": "LIMIT", "price": self.state.bid, "qty": qty, "filled": qty, "status": "FILLED", "source": self.state.mode})
            self.state.last_command = StrategyCommand.BUY_LIMIT.value
            self.state.last_order_status = "FILLED"
            self.state.decision = "BUY"
            self.add_event("ORDER", "DRYRUN", "BUY_LIMIT", f"qty={qty} price={self.state.bid:.2f}")
        elif self.state.current_position_btc > 0 and self.state.ask > 0:
            qty = self.state.current_position_btc
            self._order_seq += 1
            self.dry_run.sell_all(self.state.ask)
            self.orders.add_filled({"order_id": f"DRY-{self._order_seq:06d}", "symbol": self.state.symbol, "side": "SELL", "type": "LIMIT", "price": self.state.ask, "qty": qty, "filled": qty, "status": "FILLED", "source": self.state.mode})
            self.state.last_command = StrategyCommand.SELL_LIMIT.value
            self.state.last_order_status = "FILLED"
            self.state.decision = "SELL"
            self.add_event("ORDER", "DRYRUN", "SELL_LIMIT", f"qty={qty:.6f} price={self.state.ask:.2f}")

        self.dry_run.update_unrealized()
        self.state.position_state = "OPEN" if self.state.current_position_btc > 0 else "NONE"
        if self.state.unrealized_pnl > 0:
            self.state.profit_state = "POSITIVE"
        elif self.state.unrealized_pnl < 0:
            self.state.profit_state = "NEGATIVE"
        else:
            self.state.profit_state = "ZERO"


class MarketPoller(threading.Thread):
    def __init__(self, state: PairState, event_cb):
        super().__init__(daemon=True)
        self.state = state
        self._running = True
        self.event_cb = event_cb

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            started = time.perf_counter()
            try:
                t = fetch_json(f"/api/v3/ticker/24hr?symbol={self.state.symbol}")
                b = fetch_json(f"/api/v3/ticker/bookTicker?symbol={self.state.symbol}")
                self.state.price = float(t.get("lastPrice", 0))
                self.state.bid = float(b.get("bidPrice", 0))
                self.state.ask = float(b.get("askPrice", 0))
                self.state.spread_bps = ((self.state.ask - self.state.bid) / self.state.ask * 10000) if self.state.ask else 0
                self.state.api_ok = True
                self.state.ws_ok = True
                self.state.latency_ms = int((time.perf_counter() - started) * 1000)
            except (URLError, HTTPError, TimeoutError, ValueError):
                self.state.api_ok = False
                self.state.ws_ok = False
                self.event_cb("ERROR", "MARKET", "API", "Market API unavailable")
            self.state.updated_at = datetime.now().strftime("%H:%M:%S")
            time.sleep(1)


class PairInfoCardApp:
    COLORS = {"OK": "#32d74b", "WARNING": "#f2c94c", "ERROR": "#ff5f56", "NO": "#8e8e93", "ORDER": "#5ac8fa"}

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Lightning Trader v0.3 — Modern Pilot GUI")
        self.root.geometry("1500x950")
        self.state = PairState()
        self.settings = AlgoSettings()
        self.engine = LightningTraderEngine(self.state, self.settings)
        self.strategies = self._load_strategies()
        self._style()
        self._build_ui()
        self.poller = MarketPoller(self.state, self.engine.add_event)
        self.poller.start()
        self.update_snapshot()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _style(self):
        st = ttk.Style()
        st.theme_use("clam")

    def _load_strategies(self):
        return [s.name for s in build_strategy_catalog()]

    def _build_ui(self):
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True)
        self.cockpit = ttk.Frame(self.nb)
        self.orders_tab = ttk.Frame(self.nb)
        self.position_tab = ttk.Frame(self.nb)
        self.algos_tab = ttk.Frame(self.nb)
        self.settings_tab = ttk.Frame(self.nb)
        self.logs_tab = ttk.Frame(self.nb)
        for tab, name in [(self.cockpit, "Cockpit"), (self.orders_tab, "Orders"), (self.position_tab, "Position"), (self.algos_tab, "Algorithms"), (self.settings_tab, "Settings"), (self.logs_tab, "Logs")]:
            self.nb.add(tab, text=name)

        self._build_cockpit()
        self._build_orders()
        self._build_position()
        self._build_algorithms()
        self._build_settings()
        self._build_logs()

    def _build_cockpit(self):
        top = ttk.Frame(self.cockpit)
        top.pack(fill="x", padx=8, pady=8)
        self.top_vars = {k: tk.StringVar(value="--") for k in ["SYMBOL", "PRICE", "BID", "ASK", "SPREAD", "WS", "API", "LATENCY", "MODE", "CLOCK"]}
        for i, k in enumerate(self.top_vars):
            ttk.Label(top, text=f"{k}:").grid(row=0, column=i * 2, sticky="w", padx=3)
            ttk.Label(top, textvariable=self.top_vars[k]).grid(row=0, column=i * 2 + 1, sticky="w", padx=3)

        body = ttk.Frame(self.cockpit)
        body.pack(fill="both", expand=True, padx=8, pady=6)
        left = ttk.LabelFrame(body, text="Control Panel")
        center = ttk.LabelFrame(body, text="Flight Instruments")
        right = ttk.LabelFrame(body, text="Trade Panel")
        left.pack(side="left", fill="y", padx=4)
        center.pack(side="left", fill="both", expand=True, padx=4)
        right.pack(side="left", fill="y", padx=4)

        self.selected_algo = tk.StringVar(value=self.state.selected_algo)
        ttk.Label(left, text="Algorithm").pack(anchor="w", padx=6, pady=3)
        ttk.Combobox(left, textvariable=self.selected_algo, values=self.strategies, state="readonly", width=28).pack(padx=6)
        self.dryrun_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(left, text="Dry-run", variable=self.dryrun_var, command=self.toggle_mode).pack(anchor="w", padx=6, pady=3)
        self.live_label = ttk.Label(left, text="LIVE LOCKED", foreground="#ff5f56")
        self.live_label.pack(anchor="w", padx=6, pady=3)
        for txt, cmd in [("Connect", lambda: self.engine.add_event("OK", "CORE", "CONNECT", "Connection requested")), ("Start", self.engine.start), ("Pause", self.engine.pause), ("Stop", self.engine.stop)]:
            ttk.Button(left, text=txt, command=cmd).pack(fill="x", padx=6, pady=2)
        tk.Button(left, text="EMERGENCY STOP", bg="#8b0000", fg="white", command=self.confirm_emergency).pack(fill="x", padx=6, pady=6)

        self.instrument_vars = {}
        inst = ["Market State", "Decision", "Risk Level", "Data Health", "Position", "Spread", "Profit"]
        for i, name in enumerate(inst):
            frame = ttk.Frame(center, relief="ridge", borderwidth=2)
            frame.grid(row=i // 3, column=i % 3, padx=6, pady=6, sticky="nsew")
            center.grid_columnconfigure(i % 3, weight=1)
            ttk.Label(frame, text=name).pack(anchor="w", padx=8, pady=2)
            v = tk.StringVar(value="--")
            r = tk.StringVar(value="reason=--")
            ttk.Label(frame, textvariable=v, font=("Segoe UI", 16, "bold")).pack(anchor="center", pady=4)
            ttk.Label(frame, textvariable=r).pack(anchor="w", padx=8, pady=2)
            self.instrument_vars[name] = (v, r)

        self.trade_vars = {k: tk.StringVar(value="--") for k in ["Current Position", "Entry Price", "Position Size", "Current Price", "Unrealized PnL", "Realized PnL Today", "Active Orders", "Last Order Status", "Last Command", "Last Fill"]}
        for k, v in self.trade_vars.items():
            row = ttk.Frame(right)
            row.pack(fill="x", padx=6, pady=2)
            ttk.Label(row, text=f"{k}:").pack(side="left")
            ttk.Label(row, textvariable=v).pack(side="right")

        self.event_tree = ttk.Treeview(self.cockpit, columns=("time", "level", "module", "code", "message"), show="headings", height=10)
        for c in ("time", "level", "module", "code", "message"):
            self.event_tree.heading(c, text=c.upper())
            self.event_tree.column(c, width=120 if c != "message" else 650)
        self.event_tree.pack(fill="x", padx=8, pady=8)

    def _build_orders(self):
        cols = ("order_id", "symbol", "side", "type", "price", "qty", "filled", "status", "age", "source")
        self.orders_tree = ttk.Treeview(self.orders_tab, columns=cols, show="headings")
        for c in cols:
            self.orders_tree.heading(c, text=c)
            self.orders_tree.column(c, width=120)
        self.orders_tree.pack(fill="both", expand=True, padx=8, pady=8)
        actions = ttk.Frame(self.orders_tab)
        actions.pack(fill="x", padx=8, pady=6)
        ttk.Button(actions, text="Cancel selected", command=lambda: self.engine.add_event("ORDER", "CORE", "CANCEL_SELECTED", "Cancel selected requested")).pack(side="left", padx=4)
        ttk.Button(actions, text="Cancel all", command=self.confirm_cancel_all).pack(side="left", padx=4)
        ttk.Button(actions, text="Refresh", command=self.refresh_orders).pack(side="left", padx=4)

    def _build_position(self):
        self.position_vars = self._settings_form(self.position_tab, {"avg entry": "0", "qty": "0", "value": "0", "uPnL": "0", "rPnL": "0", "fees estimate": "0", "max hold time": "120", "exit target": "12bps", "emergency exit price": "--"})

    def _build_algorithms(self):
        self.algos_vars = self._settings_form(self.algos_tab, {"selected algorithm": self.state.selected_algo, "description": "pilot strategy", "version": "0.3", "status": "READY", "compatible symbols": "BTCUSDT", "risk profile": "LOW"})

    def _build_settings(self):
        nb = ttk.Notebook(self.settings_tab)
        nb.pack(fill="both", expand=True)
        tabs = {"App Settings": {"theme": "clam", "update_interval_ms": 1000, "log_limit": 30, "autosave_journal": True, "default_symbol": "BTCUSDT"},
                "Market Data Settings": self.settings.market,
                "Trading Core Settings": {"dry_run_default": True, "live_locked": True, "duplicate_order_protection": True, "order_timeout_ms": 8000, "cancel_on_stop": True, "cancel_on_error": True, "max_active_orders": 10},
                "Safety Settings": self.settings.risk,
                "Selected Algorithm Settings": {"settings_schema": "dynamic from strategy"},
                "API Settings": {"api_key_path": "config/api.key", "api_secret_path": "config/api.secret"}}
        self.settings_vars = {}
        for title, values in tabs.items():
            t = ttk.Frame(nb)
            nb.add(t, text=title)
            self.settings_vars[title] = self._settings_form(t, values)

    def _build_logs(self):
        self.logs_text = tk.Text(self.logs_tab, height=30)
        self.logs_text.pack(fill="both", expand=True, padx=8, pady=8)

    def _settings_form(self, tab, values: Dict[str, Any]):
        frm = ttk.Frame(tab)
        frm.pack(fill="both", expand=True, padx=8, pady=8)
        vars = {}
        for i, (k, v) in enumerate(values.items()):
            ttk.Label(frm, text=k).grid(row=i, column=0, sticky="w", pady=3)
            sv = tk.StringVar(value=str(v))
            ttk.Entry(frm, textvariable=sv, width=48).grid(row=i, column=1, sticky="w", pady=3)
            vars[k] = sv
        return vars

    def toggle_mode(self):
        self.state.mode = "DRY-RUN" if self.dryrun_var.get() else "LIVE"
        if self.state.mode == "LIVE":
            messagebox.showwarning("LIVE LOCKED", "LIVE mode requires additional confirmation and is locked.")
            self.dryrun_var.set(True)
            self.state.mode = "DRY-RUN"

    def confirm_emergency(self):
        if messagebox.askyesno("Confirm", "Activate Emergency Stop?"):
            self.engine.emergency_stop()

    def confirm_cancel_all(self):
        if messagebox.askyesno("Confirm", "Cancel all active orders?"):
            self.engine.cancel_all()

    def refresh_orders(self):
        for i in self.orders_tree.get_children():
            self.orders_tree.delete(i)
        for o in self.engine.orders.history[-100:]:
            self.orders_tree.insert("", tk.END, values=(o["order_id"], o["symbol"], o["side"], o["type"], f"{o['price']:.2f}", o["qty"], o["filled"], o["status"], "0s", o["source"]))

    def update_snapshot(self):
        self.state.selected_algo = self.selected_algo.get()
        self.engine.step()
        s = self.state
        self.top_vars["SYMBOL"].set(s.symbol)
        self.top_vars["PRICE"].set(f"{s.price:.2f}")
        self.top_vars["BID"].set(f"{s.bid:.2f}")
        self.top_vars["ASK"].set(f"{s.ask:.2f}")
        self.top_vars["SPREAD"].set(f"{s.spread_bps:.2f} bps")
        self.top_vars["WS"].set("OK" if s.ws_ok else "LOST")
        self.top_vars["API"].set("OK" if s.api_ok else "ERROR")
        self.top_vars["LATENCY"].set(f"{s.latency_ms}ms")
        self.top_vars["MODE"].set(f"{s.mode} / {'LOCKED' if s.live_locked else 'UNLOCKED'}")
        self.top_vars["CLOCK"].set(s.updated_at)

        updates = {
            "Market State": s.market_state,
            "Decision": s.decision,
            "Risk Level": s.risk_level,
            "Data Health": s.data_health,
            "Position": s.position_state,
            "Spread": s.spread_state,
            "Profit": s.profit_state,
        }
        for k, v in updates.items():
            self.instrument_vars[k][0].set(v)
            self.instrument_vars[k][1].set(f"reason={s.reason}")

        self.trade_vars["Current Position"].set("NO POSITION" if s.current_position_btc == 0 else "OPEN")
        self.trade_vars["Entry Price"].set(f"{s.entry_price:.2f}")
        self.trade_vars["Position Size"].set(f"{s.current_position_btc:.6f} BTC")
        self.trade_vars["Current Price"].set(f"{s.price:.2f}")
        self.trade_vars["Unrealized PnL"].set(f"{s.unrealized_pnl:+.2f}")
        self.trade_vars["Realized PnL Today"].set(f"{s.realized_pnl:+.2f}")
        self.trade_vars["Active Orders"].set(str(len(self.engine.orders.active_orders)))
        self.trade_vars["Last Order Status"].set(s.last_order_status)
        self.trade_vars["Last Command"].set(s.last_command)
        self.trade_vars["Last Fill"].set(s.last_fill)

        self.event_tree.delete(*self.event_tree.get_children())
        for ev in self.engine.events[-30:]:
            self.event_tree.insert("", tk.END, values=(ev["time"], ev["level"], ev["module"], ev["code"], ev["message"]))

        self.refresh_orders()
        self.logs_text.delete("1.0", tk.END)
        for ev in self.engine.events:
            self.logs_text.insert(tk.END, f"{ev['time']} | {ev['level']} | {ev['module']} | {ev['code']} | {ev['message']}\n")

        self.root.after(1000, self.update_snapshot)

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

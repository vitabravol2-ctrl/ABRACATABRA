import csv
import json
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from tkinter import ttk, messagebox
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from strategies import build_strategy_catalog

API_BASE = "https://api.binance.com"


class ReasonCode(str, Enum):
    MARKET_OK = "MARKET_OK"
    MARKET_DANGER = "MARKET_DANGER"
    DATA_STALE = "DATA_STALE"
    SPREAD_TOO_SMALL = "SPREAD_TOO_SMALL"
    EDGE_TOO_SMALL = "EDGE_TOO_SMALL"
    BALANCE_LOW = "BALANCE_LOW"
    RISK_LIMIT = "RISK_LIMIT"
    ENTRY_READY = "ENTRY_READY"
    BUY_FILLED = "BUY_FILLED"
    TAKE_PROFIT_READY = "TAKE_PROFIT_READY"
    EMERGENCY_EXIT = "EMERGENCY_EXIT"
    WAIT = "WAIT"


class StrategyCommand(str, Enum):
    WAIT = "WAIT"
    BUY_LIMIT = "BUY_LIMIT"
    SELL_LIMIT = "SELL_LIMIT"
    CANCEL_ORDER = "CANCEL_ORDER"
    CANCEL_ALL = "CANCEL_ALL"
    EXIT_POSITION = "EXIT_POSITION"


@dataclass
class PairState:
    symbol: str = "BTCUSDT"
    price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    spread_bps: float = 0.0
    change_24h: float = 0.0
    usdt_free: float = 1250.0
    ws_ok: bool = False
    api_ok: bool = False
    latency_ms: int = 0
    market_state: str = "FLAT"
    selected_algo: str = "Lightning Trader BTCUSDT"
    algo_status: str = "STOPPED"
    signal: str = "WAIT"
    current_position_btc: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    risk_level: str = "LOW"
    reason: str = ReasonCode.WAIT.value
    last_command: str = StrategyCommand.WAIT.value
    last_order_status: str = "--"
    dry_run_fill: str = "--"


@dataclass
class AlgoSettings:
    market: Dict[str, Any] = field(default_factory=lambda: {"candle_interval_fast": "1m", "candle_interval_slow": "5m", "order_book_depth": 20, "max_data_age_ms": 1500})
    entry: Dict[str, Any] = field(default_factory=lambda: {"min_spread_bps": 1.0, "min_edge_bps": 2.0, "entry_order_type": "LIMIT", "entry_reprice_ms": 1500, "entry_timeout_ms": 8000})
    exit: Dict[str, Any] = field(default_factory=lambda: {"take_profit_bps": 12.0, "emergency_exit_bps": 18.0, "trailing_enabled": True, "trailing_start_bps": 10.0, "trailing_step_bps": 4.0, "max_hold_seconds": 120})
    risk: Dict[str, Any] = field(default_factory=lambda: {"max_order_usdt": 50.0, "max_daily_loss_usdt": 20.0, "max_trades_per_day": 20, "max_open_position_usdt": 250.0, "stop_after_errors": 5})


def fetch_json(path: str) -> dict:
    req = Request(f"{API_BASE}{path}", headers={"User-Agent": "LightningTrader/0.3"})
    with urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


class TradeJournal:
    def __init__(self, json_path="journals/trade_journal.json", csv_path="journals/trade_journal.csv"):
        self.json_path = Path(json_path)
        self.csv_path = Path(csv_path)
        self.records: List[Dict[str, Any]] = []

    def log(self, message: str, reason: ReasonCode):
        row = {"ts": datetime.now(timezone.utc).isoformat(), "message": message, "reason": reason.value}
        self.records.append(row)
        self.json_path.write_text(json.dumps(self.records[-300:], ensure_ascii=False, indent=2), encoding="utf-8")
        new = not self.csv_path.exists()
        with self.csv_path.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["ts", "message", "reason"])
            if new:
                w.writeheader()
            w.writerow(row)


class MarketDataCore:
    def __init__(self, state: PairState):
        self.state = state
        self.pair_snapshot: Dict[str, float] = {"price": 0.0, "bid": 0.0, "ask": 0.0}

    def get_price_bid_ask(self) -> Dict[str, float]:
        return {"price": self.state.price, "bid": self.state.bid, "ask": self.state.ask}

    def get_balances(self) -> Dict[str, float]:
        return {"USDT_free": self.state.usdt_free, "BTC_position": self.state.current_position_btc}

    def get_open_orders(self, order_manager: "OrderManager") -> List[Dict[str, Any]]:
        return list(order_manager.active_orders.values())

    def update_pair_state(self):
        self.pair_snapshot = self.get_price_bid_ask()


class OrderManager:
    def __init__(self, log_path: str = "logs/orders_log.csv"):
        self.active_orders: Dict[str, Dict[str, Any]] = {}
        self._dedup_index: set[Tuple[str, str, float, float]] = set()
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _log(self, row: Dict[str, Any]):
        headers = ["ts", "event", "order_id", "symbol", "side", "qty", "price", "status"]
        is_new = not self.log_path.exists()
        with self.log_path.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=headers)
            if is_new:
                w.writeheader()
            w.writerow(row)

    def add_order(self, order: Dict[str, Any]) -> bool:
        dedup_key = (order["symbol"], order["side"], float(order["qty"]), float(order["price"]))
        if dedup_key in self._dedup_index:
            return False
        self._dedup_index.add(dedup_key)
        self.active_orders[order["order_id"]] = order
        self._log({"ts": datetime.now(timezone.utc).isoformat(), "event": "NEW", **order})
        return True

    def update_status(self, order_id: str, status: str):
        order = self.active_orders.get(order_id)
        if not order:
            return
        order["status"] = status
        self._log({"ts": datetime.now(timezone.utc).isoformat(), "event": "STATUS", **order})
        if status in {"FILLED", "CANCELED"}:
            dedup_key = (order["symbol"], order["side"], float(order["qty"]), float(order["price"]))
            self._dedup_index.discard(dedup_key)
            self.active_orders.pop(order_id, None)


class DryRunEngine:
    def __init__(self, state: PairState, order_manager: OrderManager):
        self.state = state
        self.order_manager = order_manager
        self.position_qty = 0.0
        self.avg_entry = 0.0
        self.realized_pnl = 0.0

    def simulate_buy(self, symbol: str, qty: float, price: float) -> Dict[str, Any]:
        cost_before = self.position_qty * self.avg_entry
        self.position_qty += qty
        self.avg_entry = (cost_before + qty * price) / self.position_qty if self.position_qty else 0.0
        self.state.current_position_btc = self.position_qty
        self.state.dry_run_fill = f"BUY {qty:.6f} {symbol} @ {price:.2f}"
        return {"filled_qty": qty, "fill_price": price}

    def simulate_sell(self, symbol: str, qty: float, price: float) -> Dict[str, Any]:
        qty = min(qty, self.position_qty)
        pnl = (price - self.avg_entry) * qty
        self.position_qty -= qty
        self.realized_pnl += pnl
        if self.position_qty == 0:
            self.avg_entry = 0.0
        self.state.current_position_btc = self.position_qty
        self.state.realized_pnl = self.realized_pnl
        self.state.dry_run_fill = f"SELL {qty:.6f} {symbol} @ {price:.2f}"
        return {"filled_qty": qty, "fill_price": price, "realized_pnl": pnl}

    def simulate_cancel(self, order_id: str):
        self.order_manager.update_status(order_id, "CANCELED")
        self.state.dry_run_fill = f"CANCEL {order_id}"

    def update_unrealized(self):
        self.state.unrealized_pnl = (self.state.price - self.avg_entry) * self.position_qty if self.position_qty else 0.0


class TradingCore:
    def __init__(self, state: PairState, order_manager: OrderManager, dry_run: DryRunEngine):
        self.state = state
        self.order_manager = order_manager
        self.dry_run = dry_run
        self._order_seq = 0
        self.live_locked = True

    def _new_order(self, symbol: str, side: str, qty: float, price: float) -> Dict[str, Any]:
        self._order_seq += 1
        return {"order_id": f"DRY-{self._order_seq:06d}", "symbol": symbol, "side": side, "qty": qty, "price": price, "status": "NEW"}

    def buy_limit(self, symbol: str, qty: float, price: float) -> Optional[str]:
        order = self._new_order(symbol, "BUY", qty, price)
        if not self.order_manager.add_order(order):
            return None
        self.order_manager.update_status(order["order_id"], "FILLED")
        self.dry_run.simulate_buy(symbol, qty, price)
        self.state.last_order_status = "FILLED"
        return order["order_id"]

    def sell_limit(self, symbol: str, qty: float, price: float) -> Optional[str]:
        order = self._new_order(symbol, "SELL", qty, price)
        if not self.order_manager.add_order(order):
            return None
        self.order_manager.update_status(order["order_id"], "FILLED")
        self.dry_run.simulate_sell(symbol, qty, price)
        self.state.last_order_status = "FILLED"
        return order["order_id"]

    def cancel_order(self, order_id: str):
        self.dry_run.simulate_cancel(order_id)
        self.state.last_order_status = "CANCELED"

    def cancel_all(self, symbol: str):
        ids = [oid for oid, o in self.order_manager.active_orders.items() if o["symbol"] == symbol]
        for oid in ids:
            self.cancel_order(oid)

    def get_order_status(self, order_id: str) -> str:
        order = self.order_manager.active_orders.get(order_id)
        return order["status"] if order else "UNKNOWN_OR_CLOSED"

    def get_position(self, symbol: str) -> Dict[str, float]:
        return {"symbol": symbol, "qty": self.dry_run.position_qty, "avg_entry": self.dry_run.avg_entry}


class MarketBrain:
    def analyze(self, state: PairState, settings: AlgoSettings) -> Tuple[str, ReasonCode, Dict[str, Any]]:
        if state.latency_ms > settings.market["max_data_age_ms"]:
            return "DANGER", ReasonCode.DATA_STALE, {}
        if state.spread_bps > 15:
            return "DANGER", ReasonCode.MARKET_DANGER, {}
        return "FLAT", ReasonCode.MARKET_OK, {}


class RiskBrain:
    def approve(self, state: PairState, settings: AlgoSettings, trades_today: int) -> Tuple[bool, float, ReasonCode]:
        if state.usdt_free < 10:
            return False, 0.0, ReasonCode.BALANCE_LOW
        if trades_today >= settings.risk["max_trades_per_day"]:
            return False, 0.0, ReasonCode.RISK_LIMIT
        return True, min(settings.risk["max_order_usdt"], state.usdt_free * 0.2), ReasonCode.MARKET_OK


class EntryBrain:
    def decide(self, state: PairState, regime: str, settings: AlgoSettings) -> Tuple[str, Optional[float], ReasonCode, str]:
        if regime == "DANGER" or state.spread_bps < settings.entry["min_spread_bps"]:
            return "WAIT", None, ReasonCode.SPREAD_TOO_SMALL, "No edge"
        return "BUY", state.bid, ReasonCode.ENTRY_READY, "Entry ready"


class ExitBrain:
    def decide(self, entry_price: float, last_price: float, highest_price: float, hold_sec: int, settings: AlgoSettings) -> Tuple[str, ReasonCode, Dict[str, Any]]:
        pnl_bps = (last_price - entry_price) / entry_price * 10000 if entry_price else 0
        if pnl_bps >= settings.exit["take_profit_bps"]:
            return "SELL", ReasonCode.TAKE_PROFIT_READY, {}
        if pnl_bps <= -settings.exit["emergency_exit_bps"]:
            return "EXIT_NOW", ReasonCode.EMERGENCY_EXIT, {}
        return "HOLD", ReasonCode.WAIT, {}


class LightningTraderEngine:
    def __init__(self, state: PairState, settings: AlgoSettings):
        self.state = state
        self.settings = settings
        self.market = MarketBrain(); self.risk = RiskBrain(); self.entry = EntryBrain(); self.exit = ExitBrain()
        self.journal = TradeJournal(); self.running = False; self.paused = False
        self.order_manager = OrderManager()
        self.dry_run = DryRunEngine(self.state, self.order_manager)
        self.trading = TradingCore(self.state, self.order_manager, self.dry_run)
        self.market_data = MarketDataCore(self.state)

    def start(self): self.running = True; self.paused = False; self.state.algo_status = "RUNNING"
    def pause(self): self.paused = True; self.state.algo_status = "PAUSED"
    def stop(self): self.running = False; self.paused = False; self.state.algo_status = "STOPPED"

    def step(self):
        if not self.running or self.paused:
            return
        regime, reason, _ = self.market.analyze(self.state, self.settings)
        self.state.market_state = regime
        self.state.signal = "WAIT" if regime == "DANGER" else "SCAN"
        self.state.reason = reason.value
        self.market_data.update_pair_state()
        self.dry_run.update_unrealized()
        if regime != "DANGER" and self.state.bid > 0 and self.state.current_position_btc == 0:
            buy_qty = min(0.0005, max(0.0, self.state.usdt_free / self.state.bid * 0.01))
            if buy_qty > 0:
                self.state.last_command = StrategyCommand.BUY_LIMIT.value
                self.trading.buy_limit(self.state.symbol, buy_qty, self.state.bid)
        elif self.state.current_position_btc > 0 and self.state.ask > 0:
            self.state.last_command = StrategyCommand.SELL_LIMIT.value
            self.trading.sell_limit(self.state.symbol, self.state.current_position_btc, self.state.ask)
        else:
            self.state.last_command = StrategyCommand.WAIT.value


class MarketPoller(threading.Thread):
    def __init__(self, state: PairState):
        super().__init__(daemon=True); self.state = state; self._running = True

    def stop(self): self._running = False

    def run(self):
        while self._running:
            started = time.perf_counter()
            try:
                t = fetch_json(f"/api/v3/ticker/24hr?symbol={self.state.symbol}")
                b = fetch_json(f"/api/v3/ticker/bookTicker?symbol={self.state.symbol}")
                self.state.price = float(t.get("lastPrice", 0)); self.state.bid = float(b.get("bidPrice", 0)); self.state.ask = float(b.get("askPrice", 0))
                self.state.spread_bps = ((self.state.ask - self.state.bid) / self.state.ask * 10000) if self.state.ask else 0
                self.state.api_ok = self.state.ws_ok = True
                self.state.latency_ms = int((time.perf_counter() - started) * 1000)
            except (URLError, HTTPError, TimeoutError, ValueError):
                self.state.api_ok = self.state.ws_ok = False
            time.sleep(1)


class PairInfoCardApp:
    def __init__(self, root: tk.Tk):
        self.root = root; self.root.title("Lightning Trader v0.3 — Multi Algorithm Cockpit"); self.root.geometry("1280x880")
        self.state = PairState(); self.settings = AlgoSettings(); self.engine = LightningTraderEngine(self.state, self.settings)
        self.strategies = self._load_strategies(); self.poller = MarketPoller(self.state); self.poller.start()
        self._build_ui(); self.update_snapshot(); self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _load_strategies(self):
        catalog = []
        for s in build_strategy_catalog():
            catalog.append({"name": s.name, "version": s.version, "status": "READY", "description": s.description, "risk_profile": s.risk_profile, "enabled": s.name != "Martingale Scalper placeholder", "compatible_symbols": s.compatible_symbols, "settings_schema": list(s.default_settings().keys())})
        catalog.append({"name": "Empty Strategy Template", "version": "0.1", "status": "TEMPLATE", "description": "Blank strategy slot", "risk_profile": "N/A", "enabled": True, "compatible_symbols": ["BTCUSDT"], "settings_schema": []})
        return catalog

    def _build_ui(self):
        nb = ttk.Notebook(self.root); nb.pack(fill="both", expand=True)
        self.cockpit = ttk.Frame(nb); self.algos_tab = ttk.Frame(nb); self.app_settings_tab = ttk.Frame(nb); self.algo_settings_tab = ttk.Frame(nb); self.safety_tab = ttk.Frame(nb)
        for t, n in [(self.cockpit, "Cockpit"), (self.algos_tab, "Algorithms"), (self.app_settings_tab, "App Settings"), (self.algo_settings_tab, "Algorithm Settings"), (self.safety_tab, "Safety Settings")]: nb.add(t, text=n)
        self.status_vars = {k: tk.StringVar(value="--") for k in ["SYMBOL", "PRICE", "BID / ASK", "SPREAD", "WS / API / LATENCY", "MARKET STATE", "SELECTED ALGO", "ALGO STATUS", "DECISION", "POSITION", "PNL", "RISK", "LAST COMMAND", "ACTIVE ORDERS", "ORDER STATUS", "DRY-RUN FILL"]}
        grid = ttk.LabelFrame(self.cockpit, text="Cockpit") ; grid.pack(fill="x", padx=10, pady=10)
        for i, k in enumerate(self.status_vars): ttk.Label(grid, text=k+":").grid(row=i, column=0, sticky="w", padx=4, pady=2); ttk.Label(grid, textvariable=self.status_vars[k]).grid(row=i, column=1, sticky="w")
        ctrl = ttk.Frame(self.cockpit); ctrl.pack(fill="x", padx=10, pady=8)
        for txt, cmd in [("CONNECT", lambda: None), ("START SELECTED ALGO", self.engine.start), ("PAUSE", self.engine.pause), ("STOP", self.engine.stop), ("DRY-RUN", lambda: None), ("LIVE LOCKED", self._live_warn)]:
            ttk.Button(ctrl, text=txt, command=cmd).pack(side="left", padx=4)

        cols = ("name", "version", "status", "description", "risk_profile", "enabled", "compatible_symbols", "settings_schema")
        self.tree = ttk.Treeview(self.algos_tab, columns=cols, show="headings", height=12)
        for c in cols: self.tree.heading(c, text=c); self.tree.column(c, width=120)
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)
        for s in self.strategies: self.tree.insert("", tk.END, values=tuple(str(s[c]) for c in cols))
        act = ttk.Frame(self.algos_tab); act.pack(fill="x", padx=8, pady=8)
        ttk.Button(act, text="Set Active", command=self.set_active_algo).pack(side="left")
        ttk.Button(act, text="Enable/Disable", command=self.toggle_algo).pack(side="left")
        ttk.Button(act, text="Start Selected", command=self.engine.start).pack(side="left")
        ttk.Button(act, text="Stop Selected", command=self.engine.stop).pack(side="left")

        self.app_vars = self._make_form(self.app_settings_tab, {
            "theme": "clam", "update_interval_ms": 1000, "log_limit": 200, "autosave_journal": True, "api_key_path": "./config/api.key", "default_symbol": "BTCUSDT", "data_source_mode": "HYBRID", "reconnect_enabled": True, "max_latency_ms": 1500
        })
        self.algo_vars = self._make_form(self.algo_settings_tab, {**self.settings.market, **self.settings.entry, **self.settings.exit, **self.settings.risk})
        self.safety_vars = self._make_form(self.safety_tab, {"dry_run_default": True, "live_locked": True, "single_active_algo": True})

    def _make_form(self, tab, values: Dict[str, Any]):
        frm = ttk.Frame(tab); frm.pack(fill="both", expand=True, padx=10, pady=10)
        vars = {}
        for i, (k, v) in enumerate(values.items()):
            ttk.Label(frm, text=k).grid(row=i, column=0, sticky="w", pady=2)
            sv = tk.StringVar(value=str(v)); ttk.Entry(frm, textvariable=sv, width=32).grid(row=i, column=1, sticky="w", pady=2)
            vars[k] = sv
        return vars

    def set_active_algo(self):
        sel = self.tree.selection()
        if sel:
            self.state.selected_algo = self.tree.item(sel[0])["values"][0]

    def toggle_algo(self):
        sel = self.tree.selection()
        if not sel: return
        item = self.tree.item(sel[0]); vals = list(item["values"]); vals[5] = "False" if str(vals[5]) == "True" else "True"; self.tree.item(sel[0], values=vals)

    def _live_warn(self):
        messagebox.showwarning("LIVE LOCKED", "LIVE mode is locked. DRY-RUN remains default.")

    def update_snapshot(self):
        self.engine.step(); s = self.state
        self.status_vars["SYMBOL"].set(s.symbol); self.status_vars["PRICE"].set(f"{s.price:.2f}")
        self.status_vars["BID / ASK"].set(f"{s.bid:.2f} / {s.ask:.2f}"); self.status_vars["SPREAD"].set(f"{s.spread_bps:.2f} bps")
        self.status_vars["WS / API / LATENCY"].set(f"{'OK' if s.ws_ok else 'LOST'} / {'OK' if s.api_ok else 'ERR'} / {s.latency_ms}ms")
        self.status_vars["MARKET STATE"].set(s.market_state); self.status_vars["SELECTED ALGO"].set(s.selected_algo); self.status_vars["ALGO STATUS"].set(s.algo_status)
        self.status_vars["DECISION"].set(s.signal); self.status_vars["POSITION"].set(f"{s.current_position_btc:.6f} BTC")
        self.status_vars["PNL"].set(f"uPnL {s.unrealized_pnl:+.2f} / rPnL {s.realized_pnl:+.2f} USDT"); self.status_vars["RISK"].set(s.risk_level)
        self.status_vars["LAST COMMAND"].set(s.last_command)
        self.status_vars["ACTIVE ORDERS"].set(str(len(self.engine.order_manager.active_orders)))
        self.status_vars["ORDER STATUS"].set(s.last_order_status)
        self.status_vars["DRY-RUN FILL"].set(s.dry_run_fill)
        self.root.after(int(self.app_vars["update_interval_ms"].get() or "1000"), self.update_snapshot)

    def on_close(self): self.engine.stop(); self.poller.stop(); self.root.destroy()


def main():
    root = tk.Tk(); PairInfoCardApp(root); root.mainloop()


if __name__ == "__main__":
    main()

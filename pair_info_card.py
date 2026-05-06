import csv
import json
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from tkinter import ttk, messagebox, filedialog
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
    algo_status: str = "STOPPED"
    algo_mode: str = "DRY-RUN"
    signal: str = "WAIT"
    reason: str = ReasonCode.WAIT.value
    decision_text: str = "Waiting for market snapshot"
    current_position_btc: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl_today: float = 0.0
    market_state: str = "FLAT"
    risk_level: str = "LOW"
    spread_state: str = "SMALL"
    data_health: str = "STALE"
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
    safety: Dict[str, Any] = field(default_factory=lambda: {
        "dry_run_default": True,
        "live_locked": True,
        "autosave_journal": True,
    })


def fetch_json(path: str) -> dict:
    req = Request(f"{API_BASE}{path}", headers={"User-Agent": "LightningTrader/0.2"})
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
        self.state.algo_status = "STOPPED"

    def set_dry_run(self):
        self.state.algo_mode = "DRY-RUN"

    def set_live_locked(self):
        self.state.algo_mode = "LIVE LOCKED"

    def step(self):
        if not self.running or self.paused:
            return
        regime, m_reason, snap = self.market.analyze(self.state, self.settings)
        self.state.market_state = regime
        self.journal.log(20, "market analyzed", m_reason, {"regime": regime, **snap})
        allowed, size_usdt, r_reason = self.risk.approve(self.state, self.settings, self.trades_today)
        if not allowed:
            self.state.signal, self.state.reason = "WAIT", r_reason.value
            self.state.decision_text = "Risk policy blocked entry"
            self.journal.log(30, "risk rejected", r_reason)
            return

        if self.state.current_position_btc <= 0:
            decision, limit_price, e_reason, note = self.entry.decide(self.state, regime, self.settings)
            self.state.signal, self.state.reason, self.state.decision_text = decision, e_reason.value, note
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
                    self.state.signal = "BUY"
                    self.state.decision_text = "Entry simulated and position opened"
                    self.journal.log(39, "buy filled (simulated)", ReasonCode.BUY_FILLED, {"oid": oid, "qty": qty})
        else:
            self.highest_price = max(self.highest_price, self.state.price)
            hold_sec = int(time.time() - self.entry_ts)
            decision, x_reason, extra = self.exit.decide(self.entry_price, self.state.price, self.highest_price, hold_sec, self.settings)
            self.state.signal, self.state.reason = decision, x_reason.value
            self.state.decision_text = f"Exit module decision after {hold_sec}s hold"
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

    def stop(self):
        self._running = False

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
                self.state.data_health = "FRESH"
            except (URLError, HTTPError, TimeoutError, ValueError) as e:
                self.state.api_ok = self.state.ws_ok = False
                self.state.error = str(e)
                self.state.signal = "WAIT"
                self.state.reason = ReasonCode.DATA_STALE.value
                self.state.data_health = "STALE"
            time.sleep(1)


class PairInfoCardApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Lightning Trader BTCUSDT v0.2 GUI Cockpit")
        self.root.geometry("1250x860")
        self.state = PairState()
        self.settings = AlgoSettings()
        self.engine = LightningTraderEngine(self.state, self.settings)
        self.poller = MarketPoller(self.state)
        self.poller.start()
        self._build_styles()
        self._build_ui()
        self._render_settings()
        self.update_snapshot()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Good.TLabel", foreground="#2ecc71")
        style.configure("Warn.TLabel", foreground="#f1c40f")
        style.configure("Danger.TLabel", foreground="#e74c3c")
        style.configure("Neutral.TLabel", foreground="#95a5a6")

    def _build_ui(self):
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True)
        self.cockpit = ttk.Frame(nb)
        self.logs_tab = ttk.Frame(nb)
        self.settings_tab = ttk.Frame(nb)
        nb.add(self.cockpit, text="BTCUSDT Cockpit")
        nb.add(self.logs_tab, text="Logs")
        nb.add(self.settings_tab, text="Settings")

        top = ttk.LabelFrame(self.cockpit, text="Status")
        top.pack(fill="x", padx=10, pady=8)
        self.status_vars = {k: tk.StringVar(value="--") for k in ["SYMBOL", "PRICE", "MODE", "ALGO", "WS", "API", "LATENCY"]}
        for i, k in enumerate(self.status_vars):
            ttk.Label(top, text=f"{k}:").grid(row=0, column=i * 2, padx=4, pady=4, sticky="w")
            ttk.Label(top, textvariable=self.status_vars[k]).grid(row=0, column=i * 2 + 1, padx=4, pady=4, sticky="w")

        indicators = ttk.LabelFrame(self.cockpit, text="Flight Indicators")
        indicators.pack(fill="x", padx=10, pady=8)
        self.indicators: Dict[str, ttk.Label] = {}
        names = ["Market State", "Decision", "Risk Level", "Spread", "Data Health", "Position", "Profit"]
        for i, name in enumerate(names):
            ttk.Label(indicators, text=f"{name}:").grid(row=i // 4, column=(i % 4) * 2, padx=5, pady=5, sticky="w")
            label = ttk.Label(indicators, text="--", style="Neutral.TLabel")
            label.grid(row=i // 4, column=(i % 4) * 2 + 1, padx=5, pady=5, sticky="w")
            self.indicators[name] = label

        central = ttk.LabelFrame(self.cockpit, text="Market & Position")
        central.pack(fill="x", padx=10, pady=8)
        self.central_vars = {k: tk.StringVar(value="--") for k in ["Price", "Bid", "Ask", "Spread bps", "24h %", "Volume", "Current Position", "uPnL", "rPnL Today"]}
        for i, k in enumerate(self.central_vars):
            frame = ttk.Frame(central)
            frame.grid(row=i // 3, column=i % 3, padx=10, pady=8, sticky="w")
            ttk.Label(frame, text=k, font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
            ttk.Label(frame, textvariable=self.central_vars[k], font=("TkDefaultFont", 14)).pack(anchor="w")

        decision = ttk.LabelFrame(self.cockpit, text="Decision Panel")
        decision.pack(fill="x", padx=10, pady=8)
        self.decision_var = tk.StringVar(value="WAIT")
        self.reason_var = tk.StringVar(value=ReasonCode.WAIT.value)
        self.text_var = tk.StringVar(value="Waiting for data")
        ttk.Label(decision, text="Decision:").grid(row=0, column=0, sticky="w", padx=5, pady=3)
        ttk.Label(decision, textvariable=self.decision_var).grid(row=0, column=1, sticky="w", padx=5, pady=3)
        ttk.Label(decision, text="Reason:").grid(row=1, column=0, sticky="w", padx=5, pady=3)
        ttk.Label(decision, textvariable=self.reason_var).grid(row=1, column=1, sticky="w", padx=5, pady=3)
        ttk.Label(decision, text="Text:").grid(row=2, column=0, sticky="w", padx=5, pady=3)
        ttk.Label(decision, textvariable=self.text_var).grid(row=2, column=1, sticky="w", padx=5, pady=3)

        control = ttk.LabelFrame(self.cockpit, text="Control")
        control.pack(fill="x", padx=10, pady=8)
        ttk.Button(control, text="CONNECT", command=lambda: None).pack(side="left", padx=5, pady=5)
        ttk.Button(control, text="START", command=self.engine.start).pack(side="left", padx=5, pady=5)
        ttk.Button(control, text="PAUSE", command=self.engine.pause).pack(side="left", padx=5, pady=5)
        ttk.Button(control, text="STOP", command=self.engine.stop).pack(side="left", padx=5, pady=5)
        ttk.Button(control, text="DRY-RUN", command=self.engine.set_dry_run).pack(side="left", padx=5, pady=5)
        ttk.Button(control, text="LIVE LOCKED", command=self._live_warn).pack(side="left", padx=5, pady=5)

        logs_boxes = ttk.Frame(self.logs_tab)
        logs_boxes.pack(fill="both", expand=True, padx=10, pady=10)
        self.log_widgets = {}
        for col, name in enumerate(["Decisions", "Errors", "Orders"]):
            frame = ttk.LabelFrame(logs_boxes, text=name)
            frame.grid(row=0, column=col, sticky="nsew", padx=4)
            logs_boxes.columnconfigure(col, weight=1)
            text = tk.Text(frame, height=28, wrap="word")
            text.pack(fill="both", expand=True)
            self.log_widgets[name] = text
        ttk.Button(self.logs_tab, text="Save Log", command=self.save_logs).pack(anchor="e", padx=12, pady=6)

    def _live_warn(self):
        self.engine.set_live_locked()
        messagebox.showwarning("LIVE locked", "LIVE mode locked. Manual confirmation workflow not implemented.")

    def _render_settings(self):
        grouped = asdict(self.settings)
        for child in self.settings_tab.winfo_children():
            child.destroy()
        grid = ttk.Frame(self.settings_tab)
        grid.pack(fill="both", expand=True, padx=10, pady=10)
        for i, grp in enumerate(["market", "risk", "entry", "exit", "safety"]):
            box = ttk.LabelFrame(grid, text=grp.upper())
            box.grid(row=i // 2, column=i % 2, sticky="nsew", padx=5, pady=5)
            grid.columnconfigure(i % 2, weight=1)
            vals = grouped[grp]
            for r, (k, v) in enumerate(vals.items()):
                ttk.Label(box, text=f"{k}:").grid(row=r, column=0, sticky="w", padx=5, pady=2)
                ttk.Label(box, text=str(v)).grid(row=r, column=1, sticky="w", padx=5, pady=2)

    def indicator_style(self, value: str, category: str) -> str:
        good = {
            "Market State": {"FLAT", "TREND_UP", "TREND_DOWN"},
            "Decision": {"BUY", "SELL", "EXIT"},
            "Risk Level": {"LOW"},
            "Spread": {"GOOD"},
            "Data Health": {"FRESH"},
            "Position": {"OPEN", "NONE"},
            "Profit": {"POSITIVE"},
        }
        warn = {"WAIT", "MID", "SMALL", "ZERO", "VOLATILE"}
        danger = {"DANGER", "HIGH", "BAD", "STALE", "NEGATIVE", "LOST", "ERROR", "STOPPED"}
        if value in good.get(category, set()):
            return "Good.TLabel"
        if value in danger:
            return "Danger.TLabel"
        if value in warn:
            return "Warn.TLabel"
        return "Neutral.TLabel"

    def update_snapshot(self):
        self.engine.step()
        s = self.state
        s.spread_state = "GOOD" if s.spread_bps >= 1.0 else "SMALL"
        if s.spread_bps > 15:
            s.spread_state = "BAD"
        s.risk_level = "LOW" if abs(s.unrealized_pnl) < 5 else ("MID" if abs(s.unrealized_pnl) < 20 else "HIGH")

        self.status_vars["SYMBOL"].set(SYMBOL)
        self.status_vars["PRICE"].set(f"{s.price:.2f}")
        self.status_vars["MODE"].set(s.algo_mode)
        self.status_vars["ALGO"].set(s.algo_status)
        self.status_vars["WS"].set("OK" if s.ws_ok else "LOST")
        self.status_vars["API"].set("OK" if s.api_ok else "ERROR")
        self.status_vars["LATENCY"].set(f"{s.latency_ms} ms")

        indicator_values = {
            "Market State": s.market_state,
            "Decision": "EXIT" if s.signal == "EXIT_NOW" else s.signal,
            "Risk Level": s.risk_level,
            "Spread": s.spread_state,
            "Data Health": s.data_health,
            "Position": "OPEN" if s.current_position_btc > 0 else "NONE",
            "Profit": "POSITIVE" if s.unrealized_pnl > 0 else ("NEGATIVE" if s.unrealized_pnl < 0 else "ZERO"),
        }
        for key, val in indicator_values.items():
            self.indicators[key].config(text=val, style=self.indicator_style(val, key))

        self.central_vars["Price"].set(f"{s.price:.2f}")
        self.central_vars["Bid"].set(f"{s.bid:.2f}")
        self.central_vars["Ask"].set(f"{s.ask:.2f}")
        self.central_vars["Spread bps"].set(f"{s.spread_bps:.2f}")
        self.central_vars["24h %"].set(f"{s.change_24h:+.2f}%")
        self.central_vars["Volume"].set(f"{s.volume_24h_btc:,.0f} BTC")
        self.central_vars["Current Position"].set(f"{s.current_position_btc:.6f} BTC")
        self.central_vars["uPnL"].set(f"{s.unrealized_pnl:+.2f} USDT")
        self.central_vars["rPnL Today"].set(f"{s.realized_pnl_today:+.2f} USDT")

        self.decision_var.set(indicator_values["Decision"])
        self.reason_var.set(s.reason)
        self.text_var.set(s.decision_text)

        self._refresh_logs()
        self.root.after(1000, self.update_snapshot)

    def _refresh_logs(self):
        records = self.engine.journal.records[-200:]
        decisions, errors, orders = [], [], []
        for rec in records:
            line = f"{rec['ts']} [{rec['step']:02d}] {rec['reason']} {rec['message']}"
            if "ERROR" in rec["reason"] or "DANGER" in rec["reason"]:
                errors.append(line)
            elif any(tag in rec["reason"] for tag in ["BUY", "SELL", "CLOSED", "PROFIT", "EXIT"]):
                orders.append(line)
            else:
                decisions.append(line)
        for name, rows in [("Decisions", decisions), ("Errors", errors), ("Orders", orders)]:
            box = self.log_widgets[name]
            box.delete("1.0", tk.END)
            if rows:
                box.insert("1.0", "\n".join(rows[-120:]))
            box.see(tk.END)

    def save_logs(self):
        target = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if not target:
            return
        output = []
        for name in ["Decisions", "Errors", "Orders"]:
            output.append(f"[{name}]")
            output.append(self.log_widgets[name].get("1.0", tk.END).strip())
            output.append("")
        Path(target).write_text("\n".join(output), encoding="utf-8")

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

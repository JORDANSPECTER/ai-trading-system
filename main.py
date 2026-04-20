import os
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

# =========================================================
# ELITE EXECUTION ENGINE - PHASE 2
# Trade lifecycle + duplicate guards + cooldown + risk lock
# =========================================================

ENGINE_STATE_FILE = "engine_state.json"
TRADE_LOG_FILE = "trade_log.json"
MAX_HISTORY = 500

# -----------------------------
# ENV CONFIG
# -----------------------------
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"
AUTO_EXECUTION_ENABLED = os.getenv("AUTO_EXECUTION_ENABLED", "false").lower() == "true"
ALLOW_CALLS = os.getenv("ALLOW_CALLS", "true").lower() == "true"
ALLOW_PUTS = os.getenv("ALLOW_PUTS", "true").lower() == "true"

MAX_TRADES_PER_DAY = int(os.getenv("MAX_TRADES_PER_DAY", "6"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "2"))
MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "500"))
COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "20"))
MIN_SIGNAL_SCORE = float(os.getenv("MIN_SIGNAL_SCORE", "80"))

DEFAULT_RISK_PER_TRADE = float(os.getenv("DEFAULT_RISK_PER_TRADE", "100"))
DEFAULT_STOP_PCT = float(os.getenv("DEFAULT_STOP_PCT", "0.25"))       # 25%
DEFAULT_TP1_PCT = float(os.getenv("DEFAULT_TP1_PCT", "0.30"))         # 30%
DEFAULT_TP2_PCT = float(os.getenv("DEFAULT_TP2_PCT", "0.60"))         # 60%
DEFAULT_TRAIL_AFTER_TP1 = os.getenv("DEFAULT_TRAIL_AFTER_TP1", "true").lower() == "true"

MARKET_OPEN_HOUR = int(os.getenv("MARKET_OPEN_HOUR", "9"))
MARKET_OPEN_MINUTE = int(os.getenv("MARKET_OPEN_MINUTE", "30"))
MARKET_CLOSE_HOUR = int(os.getenv("MARKET_CLOSE_HOUR", "16"))
MARKET_CLOSE_MINUTE = int(os.getenv("MARKET_CLOSE_MINUTE", "0"))

# -----------------------------
# HELPERS
# -----------------------------
def now_et_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default

def load_json_file(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json_file(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def append_trade_log(entry: Dict[str, Any]):
    log = load_json_file(TRADE_LOG_FILE, [])
    log.append(entry)
    log = log[-MAX_HISTORY:]
    save_json_file(TRADE_LOG_FILE, log)

def market_is_open() -> bool:
    now = datetime.now()
    open_dt = now.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0, microsecond=0)
    close_dt = now.replace(hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MINUTE, second=0, microsecond=0)
    return open_dt <= now <= close_dt and now.weekday() < 5

# -----------------------------
# ENGINE STATE
# -----------------------------
def default_engine_state():
    return {
        "date": today_str(),
        "daily_realized_pnl": 0.0,
        "daily_trade_count": 0,
        "engine_locked": False,
        "lock_reason": "",
        "cooldowns": {},          # key: symbol_side -> expiry_ts
        "open_positions": {},     # key: trade_id -> position dict
        "last_signal_ids": [],    # duplicate protection
        "last_reset": now_et_str()
    }

def load_engine_state():
    state = load_json_file(ENGINE_STATE_FILE, default_engine_state())

    if state.get("date") != today_str():
        state = default_engine_state()

    state.setdefault("daily_realized_pnl", 0.0)
    state.setdefault("daily_trade_count", 0)
    state.setdefault("engine_locked", False)
    state.setdefault("lock_reason", "")
    state.setdefault("cooldowns", {})
    state.setdefault("open_positions", {})
    state.setdefault("last_signal_ids", [])
    state.setdefault("last_reset", now_et_str())
    return state

def save_engine_state(state):
    save_json_file(ENGINE_STATE_FILE, state)

# -----------------------------
# ELITE ENGINE CLASS
# -----------------------------
class EliteExecutionEngine:
    def __init__(self):
        self.state = load_engine_state()

    # -------------------------
    # ENGINE CONTROL
    # -------------------------
    def reset_if_new_day(self):
        if self.state.get("date") != today_str():
            self.state = default_engine_state()
            save_engine_state(self.state)

    def lock_engine(self, reason: str):
        self.state["engine_locked"] = True
        self.state["lock_reason"] = reason
        save_engine_state(self.state)

    def unlock_engine(self):
        self.state["engine_locked"] = False
        self.state["lock_reason"] = ""
        save_engine_state(self.state)

    def engine_status(self) -> Dict[str, Any]:
        self.reset_if_new_day()
        return {
            "paper_trading": PAPER_TRADING,
            "auto_execution_enabled": AUTO_EXECUTION_ENABLED,
            "engine_locked": self.state["engine_locked"],
            "lock_reason": self.state["lock_reason"],
            "daily_realized_pnl": self.state["daily_realized_pnl"],
            "daily_trade_count": self.state["daily_trade_count"],
            "open_positions": len(self.state["open_positions"]),
            "cooldowns": self.state["cooldowns"],
        }

    # -------------------------
    # RULE CHECKS
    # -------------------------
    def is_duplicate_signal(self, signal_id: str) -> bool:
        if signal_id in self.state["last_signal_ids"]:
            return True
        self.state["last_signal_ids"].append(signal_id)
        self.state["last_signal_ids"] = self.state["last_signal_ids"][-100:]
        save_engine_state(self.state)
        return False

    def in_cooldown(self, symbol: str, side: str) -> bool:
        key = f"{symbol}_{side}"
        expiry = self.state["cooldowns"].get(key)
        if not expiry:
            return False
        return time.time() < expiry

    def set_cooldown(self, symbol: str, side: str, minutes: int = COOLDOWN_MINUTES):
        key = f"{symbol}_{side}"
        self.state["cooldowns"][key] = time.time() + minutes * 60
        save_engine_state(self.state)

    def count_open_positions(self) -> int:
        return len(self.state["open_positions"])

    def has_same_direction_open(self, symbol: str, side: str) -> bool:
        for pos in self.state["open_positions"].values():
            if pos["symbol"] == symbol and pos["side"] == side and pos["status"] == "OPEN":
                return True
        return False

    def can_take_trade(self, signal: Dict[str, Any]) -> (bool, str):
        self.reset_if_new_day()

        if self.state["engine_locked"]:
            return False, f"Engine locked: {self.state['lock_reason']}"

        if not AUTO_EXECUTION_ENABLED:
            return False, "Auto execution disabled"

        if not market_is_open():
            return False, "Market is closed"

        if self.state["daily_trade_count"] >= MAX_TRADES_PER_DAY:
            return False, "Max trades per day reached"

        if self.count_open_positions() >= MAX_OPEN_POSITIONS:
            return False, "Max open positions reached"

        if self.state["daily_realized_pnl"] <= -abs(MAX_DAILY_LOSS):
            self.lock_engine("Max daily loss breached")
            return False, "Max daily loss breached"

        symbol = signal.get("symbol", "").upper()
        side = signal.get("side", "").upper()
        score = safe_float(signal.get("score", 0))

        if score < MIN_SIGNAL_SCORE:
            return False, f"Signal below minimum score ({score} < {MIN_SIGNAL_SCORE})"

        if side == "CALL" and not ALLOW_CALLS:
            return False, "CALL trades disabled"

        if side == "PUT" and not ALLOW_PUTS:
            return False, "PUT trades disabled"

        if self.in_cooldown(symbol, side):
            return False, f"{symbol} {side} still in cooldown"

        if self.has_same_direction_open(symbol, side):
            return False, f"{symbol} {side} already open"

        return True, "OK"

    # -------------------------
    # POSITION SIZING
    # -------------------------
    def build_trade_plan(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        entry_price = safe_float(signal.get("entry_price", 0))
        stop_pct = safe_float(signal.get("stop_pct", DEFAULT_STOP_PCT))
        tp1_pct = safe_float(signal.get("tp1_pct", DEFAULT_TP1_PCT))
        tp2_pct = safe_float(signal.get("tp2_pct", DEFAULT_TP2_PCT))
        risk_dollars = safe_float(signal.get("risk_amount", DEFAULT_RISK_PER_TRADE))

        if entry_price <= 0:
            raise ValueError("Invalid entry_price")

        risk_per_contract = entry_price * stop_pct * 100
        contracts = max(1, int(risk_dollars // max(risk_per_contract, 0.01)))

        stop_price = round(entry_price * (1 - stop_pct), 2)
        tp1_price = round(entry_price * (1 + tp1_pct), 2)
        tp2_price = round(entry_price * (1 + tp2_pct), 2)

        return {
            "entry_price": round(entry_price, 2),
            "stop_price": stop_price,
            "tp1_price": tp1_price,
            "tp2_price": tp2_price,
            "contracts": contracts,
            "risk_dollars": round(risk_per_contract * contracts, 2),
            "trail_after_tp1": DEFAULT_TRAIL_AFTER_TP1
        }

    # -------------------------
    # ORDER SIMULATION / EXECUTION
    # -------------------------
    def place_trade(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        signal_id = str(signal.get("signal_id", "")).strip()
        symbol = signal.get("symbol", "").upper()
        side = signal.get("side", "").upper()

        if not signal_id:
            signal_id = f"{symbol}_{side}_{int(time.time())}"

        if self.is_duplicate_signal(signal_id):
            return {"ok": False, "reason": "Duplicate signal blocked"}

        allowed, reason = self.can_take_trade(signal)
        if not allowed:
            return {"ok": False, "reason": reason}

        plan = self.build_trade_plan(signal)
        trade_id = f"{symbol}_{side}_{int(time.time())}"

        position = {
            "trade_id": trade_id,
            "signal_id": signal_id,
            "symbol": symbol,
            "side": side,
            "grade": signal.get("grade", "N/A"),
            "score": safe_float(signal.get("score", 0)),
            "status": "OPEN",
            "opened_at": now_et_str(),
            "entry_price": plan["entry_price"],
            "current_price": plan["entry_price"],
            "stop_price": plan["stop_price"],
            "tp1_price": plan["tp1_price"],
            "tp2_price": plan["tp2_price"],
            "contracts": plan["contracts"],
            "risk_dollars": plan["risk_dollars"],
            "trail_after_tp1": plan["trail_after_tp1"],
            "tp1_hit": False,
            "tp2_hit": False,
            "exit_price": None,
            "realized_pnl": 0.0,
            "notes": signal.get("notes", ""),
            "mode": "PAPER" if PAPER_TRADING else "LIVE"
        }

        self.state["open_positions"][trade_id] = position
        self.state["daily_trade_count"] += 1
        save_engine_state(self.state)

        append_trade_log({
            "event": "OPEN",
            "time": now_et_str(),
            "trade_id": trade_id,
            "symbol": symbol,
            "side": side,
            "entry_price": plan["entry_price"],
            "contracts": plan["contracts"],
            "risk_dollars": plan["risk_dollars"],
            "mode": position["mode"]
        })

        return {
            "ok": True,
            "trade_id": trade_id,
            "position": position
        }

    # -------------------------
    # POSITION MANAGEMENT
    # -------------------------
    def update_position_price(self, trade_id: str, new_price: float) -> Dict[str, Any]:
        pos = self.state["open_positions"].get(trade_id)
        if not pos:
            return {"ok": False, "reason": "Trade not found"}

        if pos["status"] != "OPEN":
            return {"ok": False, "reason": "Trade already closed"}

        new_price = safe_float(new_price)
        if new_price <= 0:
            return {"ok": False, "reason": "Invalid price"}

        pos["current_price"] = round(new_price, 2)

        # TP1 logic
        if not pos["tp1_hit"] and new_price >= pos["tp1_price"]:
            pos["tp1_hit"] = True
            if pos["trail_after_tp1"]:
                pos["stop_price"] = round(pos["entry_price"], 2)

            append_trade_log({
                "event": "TP1_HIT",
                "time": now_et_str(),
                "trade_id": trade_id,
                "symbol": pos["symbol"],
                "side": pos["side"],
                "price": round(new_price, 2)
            })

        # TP2 logic
        if not pos["tp2_hit"] and new_price >= pos["tp2_price"]:
            pos["tp2_hit"] = True
            append_trade_log({
                "event": "TP2_HIT",
                "time": now_et_str(),
                "trade_id": trade_id,
                "symbol": pos["symbol"],
                "side": pos["side"],
                "price": round(new_price, 2)
            })

        # Stop logic
        if new_price <= pos["stop_price"]:
            return self.close_position(trade_id, new_price, "STOP_HIT")

        save_engine_state(self.state)
        return {"ok": True, "position": pos}

    def close_position(self, trade_id: str, exit_price: float, reason: str = "MANUAL_EXIT") -> Dict[str, Any]:
        pos = self.state["open_positions"].get(trade_id)
        if not pos:
            return {"ok": False, "reason": "Trade not found"}

        if pos["status"] != "OPEN":
            return {"ok": False, "reason": "Trade already closed"}

        exit_price = safe_float(exit_price)
        if exit_price <= 0:
            return {"ok": False, "reason": "Invalid exit price"}

        pnl_per_contract = (exit_price - pos["entry_price"]) * 100
        total_pnl = round(pnl_per_contract * pos["contracts"], 2)

        pos["status"] = "CLOSED"
        pos["closed_at"] = now_et_str()
        pos["exit_price"] = round(exit_price, 2)
        pos["realized_pnl"] = total_pnl
        pos["close_reason"] = reason

        self.state["daily_realized_pnl"] += total_pnl

        symbol = pos["symbol"]
        side = pos["side"]
        self.set_cooldown(symbol, side, COOLDOWN_MINUTES)

        append_trade_log({
            "event": "CLOSE",
            "time": now_et_str(),
            "trade_id": trade_id,
            "symbol": symbol,
            "side": side,
            "entry_price": pos["entry_price"],
            "exit_price": round(exit_price, 2),
            "contracts": pos["contracts"],
            "pnl": total_pnl,
            "reason": reason
        })

        if self.state["daily_realized_pnl"] <= -abs(MAX_DAILY_LOSS):
            self.lock_engine("Max daily loss breached after close")

        save_engine_state(self.state)
        return {"ok": True, "position": pos}

    # -------------------------
    # ADMIN / REPORTING
    # -------------------------
    def get_open_positions(self) -> List[Dict[str, Any]]:
        return list(self.state["open_positions"].values())

    def flatten_all_positions(self, exit_price_map: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        results = []
        exit_price_map = exit_price_map or {}

        for trade_id, pos in list(self.state["open_positions"].items()):
            if pos["status"] != "OPEN":
                continue

            exit_price = safe_float(exit_price_map.get(trade_id, pos["current_price"]), pos["current_price"])
            results.append(self.close_position(trade_id, exit_price, "FLATTEN_ALL"))

        return {"ok": True, "results": results}

    def get_trade_summary(self) -> Dict[str, Any]:
        open_positions = self.get_open_positions()
        open_positions = [p for p in open_positions if p["status"] == "OPEN"]

        return {
            "date": self.state["date"],
            "engine_locked": self.state["engine_locked"],
            "lock_reason": self.state["lock_reason"],
            "daily_realized_pnl": round(self.state["daily_realized_pnl"], 2),
            "daily_trade_count": self.state["daily_trade_count"],
            "open_positions_count": len(open_positions),
            "open_positions": open_positions
        }

# =========================================================
# GLOBAL ENGINE INSTANCE
# =========================================================
elite_engine = EliteExecutionEngine()

# =========================================================
# SIGNAL HANDLER
# Connect this to your alert classifier / decision engine
# =========================================================
def process_trade_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    """
    Expected signal example:
    {
        "signal_id": "QQQ_CALL_1713601111",
        "symbol": "QQQ",
        "side": "CALL",
        "grade": "A",
        "score": 92,
        "entry_price": 1.25,
        "risk_amount": 120,
        "stop_pct": 0.25,
        "tp1_pct": 0.30,
        "tp2_pct": 0.60,
        "notes": "VWAP reclaim + volume expansion"
    }
    """
    try:
        result = elite_engine.place_trade(signal)
        return result
    except Exception as e:
        return {"ok": False, "reason": f"process_trade_signal error: {str(e)}"}

# =========================================================
# MANUAL COMMAND HELPERS
# Use these with Telegram / Discord command center later
# =========================================================
def cmd_status():
    return elite_engine.engine_status()

def cmd_summary():
    return elite_engine.get_trade_summary()

def cmd_lock(reason="Manual lock"):
    elite_engine.lock_engine(reason)
    return {"ok": True, "message": f"Engine locked: {reason}"}

def cmd_unlock():
    elite_engine.unlock_engine()
    return {"ok": True, "message": "Engine unlocked"}

def cmd_flatten(exit_price_map=None):
    return elite_engine.flatten_all_positions(exit_price_map)

def cmd_close_trade(trade_id: str, exit_price: float):
    return elite_engine.close_position(trade_id, exit_price, "MANUAL_CLOSE")

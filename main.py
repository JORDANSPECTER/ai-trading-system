import os
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, List

# =========================================================
# FILES
# =========================================================
ENGINE_STATE_FILE = "engine_state.json"
TRADE_LOG_FILE = "trade_log.json"
MAX_HISTORY = 500

# =========================================================
# ENV CONFIG
# =========================================================
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"
AUTO_EXECUTION_ENABLED = os.getenv("AUTO_EXECUTION_ENABLED", "true").lower() == "true"
ALLOW_CALLS = os.getenv("ALLOW_CALLS", "true").lower() == "true"
ALLOW_PUTS = os.getenv("ALLOW_PUTS", "true").lower() == "true"

MAX_TRADES_PER_DAY = int(os.getenv("MAX_TRADES_PER_DAY", "6"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "2"))
MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "500"))
COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "20"))
MIN_SIGNAL_SCORE = float(os.getenv("MIN_SIGNAL_SCORE", "80"))

DEFAULT_RISK_PER_TRADE = float(os.getenv("DEFAULT_RISK_PER_TRADE", "100"))
DEFAULT_STOP_PCT = float(os.getenv("DEFAULT_STOP_PCT", "0.25"))
DEFAULT_TP1_PCT = float(os.getenv("DEFAULT_TP1_PCT", "0.30"))
DEFAULT_TP2_PCT = float(os.getenv("DEFAULT_TP2_PCT", "0.60"))
DEFAULT_TRAIL_AFTER_TP1 = os.getenv("DEFAULT_TRAIL_AFTER_TP1", "true").lower() == "true"

MARKET_OPEN_HOUR = int(os.getenv("MARKET_OPEN_HOUR", "9"))
MARKET_OPEN_MINUTE = int(os.getenv("MARKET_OPEN_MINUTE", "30"))
MARKET_CLOSE_HOUR = int(os.getenv("MARKET_CLOSE_HOUR", "16"))
MARKET_CLOSE_MINUTE = int(os.getenv("MARKET_CLOSE_MINUTE", "0"))

# =========================================================
# HELPERS
# =========================================================
def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def safe_float(value, default=0.0) -> float:
    try:
        return float(value)
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
    return now.weekday() < 5 and open_dt <= now <= close_dt

# =========================================================
# DEFAULT ENGINE STATE
# =========================================================
def default_engine_state() -> Dict[str, Any]:
    return {
        "date": today_str(),
        "daily_realized_pnl": 0.0,
        "daily_trade_count": 0,
        "engine_locked": False,
        "lock_reason": "",
        "cooldowns": {},
        "open_positions": {},
        "last_signal_ids": [],
        "last_reset": now_str()
    }

def load_engine_state() -> Dict[str, Any]:
    state = load_json_file(ENGINE_STATE_FILE, default_engine_state())

    if state.get("date") != today_str():
        state = default_engine_state()

    state.setdefault("date", today_str())
    state.setdefault("daily_realized_pnl", 0.0)
    state.setdefault("daily_trade_count", 0)
    state.setdefault("engine_locked", False)
    state.setdefault("lock_reason", "")
    state.setdefault("cooldowns", {})
    state.setdefault("open_positions", {})
    state.setdefault("last_signal_ids", [])
    state.setdefault("last_reset", now_str())

    return state

def save_engine_state(state: Dict[str, Any]):
    save_json_file(ENGINE_STATE_FILE, state)

# =========================================================
# ELITE EXECUTION ENGINE
# =========================================================
class EliteExecutionEngine:
    def __init__(self):
        self.state = load_engine_state()

    def reset_if_new_day(self):
        if self.state.get("date") != today_str():
            self.state = default_engine_state()
            save_engine_state(self.state)

    def engine_status(self) -> Dict[str, Any]:
        self.reset_if_new_day()
        return {
            "paper_trading": PAPER_TRADING,
            "auto_execution_enabled": AUTO_EXECUTION_ENABLED,
            "engine_locked": self.state["engine_locked"],
            "lock_reason": self.state["lock_reason"],
            "daily_realized_pnl": round(self.state["daily_realized_pnl"], 2),
            "daily_trade_count": self.state["daily_trade_count"],
            "open_positions_count": len([
                p for p in self.state["open_positions"].values()
                if p.get("status") == "OPEN"
            ]),
            "cooldowns": self.state["cooldowns"]
        }

    def lock_engine(self, reason: str):
        self.state["engine_locked"] = True
        self.state["lock_reason"] = reason
        save_engine_state(self.state)

    def unlock_engine(self):
        self.state["engine_locked"] = False
        self.state["lock_reason"] = ""
        save_engine_state(self.state)

    def is_duplicate_signal(self, signal_id: str) -> bool:
        if signal_id in self.state["last_signal_ids"]:
            return True
        self.state["last_signal_ids"].append(signal_id)
        self.state["last_signal_ids"] = self.state["last_signal_ids"][-100:]
        save_engine_state(self.state)
        return False

    def cooldown_key(self, symbol: str, side: str) -> str:
        return f"{symbol.upper()}_{side.upper()}"

    def in_cooldown(self, symbol: str, side: str) -> bool:
        key = self.cooldown_key(symbol, side)
        expiry = self.state["cooldowns"].get(key)
        if not expiry:
            return False
        return time.time() < expiry

    def set_cooldown(self, symbol: str, side: str, minutes: int = COOLDOWN_MINUTES):
        key = self.cooldown_key(symbol, side)
        self.state["cooldowns"][key] = time.time() + minutes * 60
        save_engine_state(self.state)

    def count_open_positions(self) -> int:
        return len([
            p for p in self.state["open_positions"].values()
            if p.get("status") == "OPEN"
        ])

    def has_same_direction_open(self, symbol: str, side: str) -> bool:
        for pos in self.state["open_positions"].values():
            if (
                pos.get("status") == "OPEN"
                and pos.get("symbol") == symbol.upper()
                and pos.get("side") == side.upper()
            ):
                return True
        return False

    def can_take_trade(self, signal: Dict[str, Any]) -> (bool, str):
        self.reset_if_new_day()

        if self.state["engine_locked"]:
            return False, f"Engine locked: {self.state['lock_reason']}"

        if not AUTO_EXECUTION_ENABLED:
            return False, "Auto execution disabled"

        symbol = signal.get("symbol", "").upper().strip()
        side = signal.get("side", "").upper().strip()
        score = safe_float(signal.get("score", 0))

        if not symbol:
            return False, "Missing symbol"

        if side not in ["CALL", "PUT"]:
            return False, "Invalid side"

        if not market_is_open():
            return False, "Market is closed"

        if self.state["daily_trade_count"] >= MAX_TRADES_PER_DAY:
            return False, "Max trades per day reached"

        if self.count_open_positions() >= MAX_OPEN_POSITIONS:
            return False, "Max open positions reached"

        if self.state["daily_realized_pnl"] <= -abs(MAX_DAILY_LOSS):
            self.lock_engine("Max daily loss breached")
            return False, "Max daily loss breached"

        if score < MIN_SIGNAL_SCORE:
            return False, f"Signal score too low ({score} < {MIN_SIGNAL_SCORE})"

        if side == "CALL" and not ALLOW_CALLS:
            return False, "CALLS disabled"

        if side == "PUT" and not ALLOW_PUTS:
            return False, "PUTS disabled"

        if self.in_cooldown(symbol, side):
            return False, f"{symbol} {side} in cooldown"

        if self.has_same_direction_open(symbol, side):
            return False, f"{symbol} {side} already open"

        return True, "OK"

    def build_trade_plan(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        entry_price = safe_float(signal.get("entry_price", 0))
        stop_pct = safe_float(signal.get("stop_pct", DEFAULT_STOP_PCT))
        tp1_pct = safe_float(signal.get("tp1_pct", DEFAULT_TP1_PCT))
        tp2_pct = safe_float(signal.get("tp2_pct", DEFAULT_TP2_PCT))
        risk_amount = safe_float(signal.get("risk_amount", DEFAULT_RISK_PER_TRADE))

        if entry_price <= 0:
            raise ValueError("Invalid entry_price")

        risk_per_contract = entry_price * stop_pct * 100
        contracts = max(1, int(risk_amount // max(risk_per_contract, 0.01)))

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

    def place_trade(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        symbol = signal.get("symbol", "").upper().strip()
        side = signal.get("side", "").upper().strip()
        signal_id = str(signal.get("signal_id", "")).strip()

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
            "opened_at": now_str(),
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
            "close_reason": "",
            "notes": signal.get("notes", ""),
            "mode": "PAPER" if PAPER_TRADING else "LIVE"
        }

        self.state["open_positions"][trade_id] = position
        self.state["daily_trade_count"] += 1
        save_engine_state(self.state)

        append_trade_log({
            "event": "OPEN",
            "time": now_str(),
            "trade_id": trade_id,
            "symbol": symbol,
            "side": side,
            "grade": position["grade"],
            "score": position["score"],
            "entry_price": position["entry_price"],
            "contracts": position["contracts"],
            "risk_dollars": position["risk_dollars"],
            "mode": position["mode"]
        })

        return {
            "ok": True,
            "trade_id": trade_id,
            "position": position
        }

    def update_position_price(self, trade_id: str, new_price: float) -> Dict[str, Any]:
        pos = self.state["open_positions"].get(trade_id)
        if not pos:
            return {"ok": False, "reason": "Trade not found"}

        if pos.get("status") != "OPEN":
            return {"ok": False, "reason": "Trade already closed"}

        new_price = safe_float(new_price)
        if new_price <= 0:
            return {"ok": False, "reason": "Invalid price"}

        pos["current_price"] = round(new_price, 2)

        if not pos["tp1_hit"] and new_price >= pos["tp1_price"]:
            pos["tp1_hit"] = True
            if pos["trail_after_tp1"]:
                pos["stop_price"] = round(pos["entry_price"], 2)

            append_trade_log({
                "event": "TP1_HIT",
                "time": now_str(),
                "trade_id": trade_id,
                "symbol": pos["symbol"],
                "side": pos["side"],
                "price": round(new_price, 2)
            })

        if not pos["tp2_hit"] and new_price >= pos["tp2_price"]:
            pos["tp2_hit"] = True

            append_trade_log({
                "event": "TP2_HIT",
                "time": now_str(),
                "trade_id": trade_id,
                "symbol": pos["symbol"],
                "side": pos["side"],
                "price": round(new_price, 2)
            })

        if new_price <= pos["stop_price"]:
            return self.close_position(trade_id, new_price, "STOP_HIT")

        save_engine_state(self.state)
        return {"ok": True, "position": pos}

    def close_position(self, trade_id: str, exit_price: float, reason: str = "MANUAL_CLOSE") -> Dict[str, Any]:
        pos = self.state["open_positions"].get(trade_id)
        if not pos:
            return {"ok": False, "reason": "Trade not found"}

        if pos.get("status") != "OPEN":
            return {"ok": False, "reason": "Trade already closed"}

        exit_price = safe_float(exit_price)
        if exit_price <= 0:
            return {"ok": False, "reason": "Invalid exit_price"}

        pnl_per_contract = (exit_price - pos["entry_price"]) * 100
        total_pnl = round(pnl_per_contract * pos["contracts"], 2)

        pos["status"] = "CLOSED"
        pos["closed_at"] = now_str()
        pos["exit_price"] = round(exit_price, 2)
        pos["realized_pnl"] = total_pnl
        pos["close_reason"] = reason

        self.state["daily_realized_pnl"] += total_pnl
        self.set_cooldown(pos["symbol"], pos["side"], COOLDOWN_MINUTES)

        append_trade_log({
            "event": "CLOSE",
            "time": now_str(),
            "trade_id": trade_id,
            "symbol": pos["symbol"],
            "side": pos["side"],
            "entry_price": pos["entry_price"],
            "exit_price": pos["exit_price"],
            "contracts": pos["contracts"],
            "pnl": total_pnl,
            "reason": reason
        })

        if self.state["daily_realized_pnl"] <= -abs(MAX_DAILY_LOSS):
            self.lock_engine("Max daily loss breached after close")

        save_engine_state(self.state)
        return {"ok": True, "position": pos}

    def get_open_positions(self) -> List[Dict[str, Any]]:
        return [
            p for p in self.state["open_positions"].values()
            if p.get("status") == "OPEN"
        ]

    def flatten_all_positions(self, exit_price_map: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        exit_price_map = exit_price_map or {}
        results = []

        for trade_id, pos in list(self.state["open_positions"].items()):
            if pos.get("status") != "OPEN":
                continue

            exit_price = safe_float(exit_price_map.get(trade_id, pos.get("current_price", pos.get("entry_price", 0))))
            if exit_price <= 0:
                exit_price = pos.get("entry_price", 0)

            results.append(self.close_position(trade_id, exit_price, "FLATTEN_ALL"))

        return {"ok": True, "results": results}

    def get_trade_summary(self) -> Dict[str, Any]:
        return {
            "date": self.state["date"],
            "engine_locked": self.state["engine_locked"],
            "lock_reason": self.state["lock_reason"],
            "daily_realized_pnl": round(self.state["daily_realized_pnl"], 2),
            "daily_trade_count": self.state["daily_trade_count"],
            "open_positions_count": len(self.get_open_positions()),
            "open_positions": self.get_open_positions()
        }

# =========================================================
# GLOBAL ENGINE
# =========================================================
elite_engine = EliteExecutionEngine()

# =========================================================
# SIGNAL ENTRY POINT
# =========================================================
def process_trade_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return elite_engine.place_trade(signal)
    except Exception as e:
        return {"ok": False, "reason": f"process_trade_signal error: {str(e)}"}

# =========================================================
# COMMAND HELPERS
# =========================================================
def cmd_status():
    return elite_engine.engine_status()

def cmd_summary():
    return elite_engine.get_trade_summary()

def cmd_lock(reason: str = "Manual lock"):
    elite_engine.lock_engine(reason)
    return {"ok": True, "message": f"Engine locked: {reason}"}

def cmd_unlock():
    elite_engine.unlock_engine()
    return {"ok": True, "message": "Engine unlocked"}

def cmd_flatten(exit_price_map: Optional[Dict[str, float]] = None):
    return elite_engine.flatten_all_positions(exit_price_map)

def cmd_close_trade(trade_id: str, exit_price: float):
    return elite_engine.close_position(trade_id, exit_price, "MANUAL_CLOSE")

# =========================================================
# REAL ALERT HOOK
# Replace this later with your actual bot logic
# =========================================================
def get_live_signal_from_your_system() -> Optional[Dict[str, Any]]:
    """
    Replace this with your real alert engine.
    Must return either:
      - signal dict
      - or None if no signal
    """
    return None

# =========================================================
# MAIN LOOP
# =========================================================
def run_engine_loop():
    print("Elite engine started...")
    while True:
        try:
            signal = get_live_signal_from_your_system()

            if signal:
                result = process_trade_signal(signal)
                print("SIGNAL RESULT:", result)

            time.sleep(5)

        except KeyboardInterrupt:
            print("Engine stopped by user.")
            break
        except Exception as e:
            print("MAIN LOOP ERROR:", str(e))
            time.sleep(5)

# =========================================================
# TEST BLOCK
# Only runs when you manually press Run
# =========================================================
if __name__ == "__main__":
    TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"

    if TEST_MODE:
        test_signal = {
            "signal_id": f"TEST_QQQ_CALL_{int(time.time())}",
            "symbol": "QQQ",
            "side": "CALL",
            "grade": "A",
            "score": 91,
            "entry_price": 1.45,
            "risk_amount": 100,
            "stop_pct": 0.25,
            "tp1_pct": 0.30,
            "tp2_pct": 0.60,
            "notes": "VWAP reclaim + squeeze + premium signal"
        }

        result = process_trade_signal(test_signal)
        print("TRADE RESULT:", result)
        print("ENGINE STATUS:", cmd_status())
        print("SUMMARY:", cmd_summary())

        if result.get("ok"):
            trade_id = result["trade_id"]

            print("\n--- SIMULATE PRICE MOVE TO TP1 ---")
            print(elite_engine.update_position_price(trade_id, 1.90))

            print("\n--- SIMULATE PRICE MOVE TO TP2 ---")
            print(elite_engine.update_position_price(trade_id, 2.35))

            print("\n--- MANUAL CLOSE ---")
            print(cmd_close_trade(trade_id, 2.10))

            print("\n--- FINAL SUMMARY ---")
            print(cmd_summary())
    else:
        run_engine_loop()

import os
import json
import time
import uuid
import math
import requests
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

# =========================================================
# FILES
# =========================================================
ENGINE_STATE_FILE = "engine_state.json"
TRADE_LOG_FILE = "trade_log.json"
BOT_RUNTIME_FILE = "bot_runtime.json"
MAX_HISTORY = 1000

# =========================================================
# ENV CONFIG
# =========================================================
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"
AUTO_EXECUTION_ENABLED = os.getenv("AUTO_EXECUTION_ENABLED", "true").lower() == "true"
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"

SCAN_SYMBOLS = [s.strip().upper() for s in os.getenv("SCAN_SYMBOLS", "QQQ,SPY").split(",") if s.strip()]
SCAN_INTERVAL = os.getenv("SCAN_INTERVAL", "5min")
SCAN_SECONDS = int(os.getenv("SCAN_SECONDS", "60"))
TELEGRAM_POLL_SECONDS = int(os.getenv("TELEGRAM_POLL_SECONDS", "2"))
MIN_BARS = int(os.getenv("MIN_BARS", "40"))

ALLOW_CALLS = os.getenv("ALLOW_CALLS", "true").lower() == "true"
ALLOW_PUTS = os.getenv("ALLOW_PUTS", "true").lower() == "true"

MIN_SIGNAL_SCORE = float(os.getenv("MIN_SIGNAL_SCORE", "80"))
FREE_MIN_SCORE = float(os.getenv("FREE_MIN_SCORE", "90"))
PREMIUM_MIN_SCORE = float(os.getenv("PREMIUM_MIN_SCORE", "80"))
SIGNAL_COOLDOWN_SECONDS = int(os.getenv("SIGNAL_COOLDOWN_SECONDS", "300"))

MAX_TRADES_PER_DAY = int(os.getenv("MAX_TRADES_PER_DAY", "6"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "2"))
MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "500"))
COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "20"))

DEFAULT_RISK_PER_TRADE = float(os.getenv("DEFAULT_RISK_PER_TRADE", "100"))
DEFAULT_STOP_PCT = float(os.getenv("DEFAULT_STOP_PCT", "0.25"))
DEFAULT_TP1_PCT = float(os.getenv("DEFAULT_TP1_PCT", "0.30"))
DEFAULT_TP2_PCT = float(os.getenv("DEFAULT_TP2_PCT", "0.60"))
DEFAULT_TRAIL_AFTER_TP1 = os.getenv("DEFAULT_TRAIL_AFTER_TP1", "true").lower() == "true"

# =========================================================
# AUTO SCALE / TRAIL CONFIG
# =========================================================
AUTO_SCALE_ENABLED = os.getenv("AUTO_SCALE_ENABLED", "true").lower() == "true"
TP1_SCALE_PCT = float(os.getenv("TP1_SCALE_PCT", "0.50"))   # close 50% at TP1
TP2_SCALE_PCT = float(os.getenv("TP2_SCALE_PCT", "0.50"))   # close 50% of remaining at TP2
SMART_TRAIL_ENABLED = os.getenv("SMART_TRAIL_ENABLED", "true").lower() == "true"
TRAIL_BEFORE_TP2_PCT = float(os.getenv("TRAIL_BEFORE_TP2_PCT", "0.10"))
TRAIL_AFTER_TP2_PCT = float(os.getenv("TRAIL_AFTER_TP2_PCT", "0.08"))
MIN_CONTRACTS_TO_SCALE = int(os.getenv("MIN_CONTRACTS_TO_SCALE", "2"))

# =========================================================
# LIVE POSITION MONITOR CONFIG
# =========================================================
POSITION_MONITOR_ENABLED = os.getenv("POSITION_MONITOR_ENABLED", "true").lower() == "true"
POSITION_MONITOR_SECONDS = int(os.getenv("POSITION_MONITOR_SECONDS", "5"))
OPTION_MARK_SOURCE = os.getenv("OPTION_MARK_SOURCE", "auto").strip().lower()   # auto, broker, estimate
OPTION_PRICE_SENSITIVITY = float(os.getenv("OPTION_PRICE_SENSITIVITY", "18"))
MIN_OPTION_PRICE = float(os.getenv("MIN_OPTION_PRICE", "0.05"))

MARKET_OPEN_HOUR = int(os.getenv("MARKET_OPEN_HOUR", "9"))
MARKET_OPEN_MINUTE = int(os.getenv("MARKET_OPEN_MINUTE", "30"))
MARKET_CLOSE_HOUR = int(os.getenv("MARKET_CLOSE_HOUR", "16"))
MARKET_CLOSE_MINUTE = int(os.getenv("MARKET_CLOSE_MINUTE", "0"))

TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()

DISCORD_FREE_WEBHOOK = os.getenv("DISCORD_FREE_WEBHOOK", "").strip()
DISCORD_PREMIUM_WEBHOOK = os.getenv("DISCORD_PREMIUM_WEBHOOK", "").strip()
DISCORD_DEBUG_WEBHOOK = os.getenv("DISCORD_DEBUG_WEBHOOK", "").strip()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "true").lower() == "true"
TELEGRAM_COMMANDS_ENABLED = os.getenv("TELEGRAM_COMMANDS_ENABLED", "true").lower() == "true"

SEND_FREE_ALERTS = os.getenv("SEND_FREE_ALERTS", "true").lower() == "true"
SEND_PREMIUM_ALERTS = os.getenv("SEND_PREMIUM_ALERTS", "true").lower() == "true"
SEND_TELEGRAM_ALERTS = os.getenv("SEND_TELEGRAM_ALERTS", "true").lower() == "true"
DEBUG_LOGGING = os.getenv("DEBUG_LOGGING", "true").lower() == "true"

# =========================================================
# BROKER ENV CONFIG
# =========================================================
BROKER_ENABLED = os.getenv("BROKER_ENABLED", "false").lower() == "true"
BROKER_NAME = os.getenv("BROKER_NAME", "stub").strip().lower()
BROKER_PAPER = os.getenv("BROKER_PAPER", "true").lower() == "true"
BROKER_BASE_URL = os.getenv("BROKER_BASE_URL", "").strip()
BROKER_API_KEY = os.getenv("BROKER_API_KEY", "").strip()
BROKER_API_SECRET = os.getenv("BROKER_API_SECRET", "").strip()

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

def safe_int(value, default=0) -> int:
    try:
        return int(value)
    except Exception:
        return default

def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))

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

def log_debug(message: str):
    print(f"[DEBUG {now_str()}] {message}", flush=True)
    if DEBUG_LOGGING and DISCORD_DEBUG_WEBHOOK:
        send_discord_message(DISCORD_DEBUG_WEBHOOK, f"```{message[:1800]}```")

# =========================================================
# RUNTIME STATE
# =========================================================
def default_runtime_state() -> Dict[str, Any]:
    return {
        "last_signal_times": {},
        "telegram_last_update_id": 0
    }

def load_runtime_state() -> Dict[str, Any]:
    state = load_json_file(BOT_RUNTIME_FILE, default_runtime_state())
    state.setdefault("last_signal_times", {})
    state.setdefault("telegram_last_update_id", 0)
    return state

def save_runtime_state(state: Dict[str, Any]):
    save_json_file(BOT_RUNTIME_FILE, state)

RUNTIME_STATE = load_runtime_state()

# =========================================================
# DISCORD / TELEGRAM
# =========================================================
def send_discord_message(webhook_url: str, content: str) -> bool:
    if not webhook_url:
        return False
    try:
        r = requests.post(webhook_url, json={"content": content[:1900]}, timeout=15)
        return 200 <= r.status_code < 300
    except Exception as e:
        print(f"Discord error: {e}", flush=True)
        return False

def send_telegram_message(text: str) -> bool:
    if not TELEGRAM_ENABLED or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text[:3900]}
        r = requests.post(url, json=payload, timeout=15)
        return 200 <= r.status_code < 300
    except Exception as e:
        print(f"Telegram send error: {e}", flush=True)
        return False

def get_telegram_updates() -> List[Dict[str, Any]]:
    if not TELEGRAM_ENABLED or not TELEGRAM_BOT_TOKEN or not TELEGRAM_COMMANDS_ENABLED:
        return []
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
        params = {
            "timeout": 1,
            "offset": RUNTIME_STATE.get("telegram_last_update_id", 0) + 1
        }
        r = requests.get(url, params=params, timeout=15)
        data = r.json()

        if not data.get("ok"):
            return []

        results = data.get("result", [])
        if results:
            RUNTIME_STATE["telegram_last_update_id"] = results[-1]["update_id"]
            save_runtime_state(RUNTIME_STATE)
        return results
    except Exception as e:
        print(f"Telegram update error: {e}", flush=True)
        return []

def send_trade_alert(message: str, channel: str = "premium"):
    print(f"[ALERT] {message}", flush=True)

    if channel == "free":
        if SEND_FREE_ALERTS and DISCORD_FREE_WEBHOOK:
            send_discord_message(DISCORD_FREE_WEBHOOK, message)
    elif channel == "premium":
        if SEND_PREMIUM_ALERTS and DISCORD_PREMIUM_WEBHOOK:
            send_discord_message(DISCORD_PREMIUM_WEBHOOK, message)
    elif channel == "debug":
        if DEBUG_LOGGING and DISCORD_DEBUG_WEBHOOK:
            send_discord_message(DISCORD_DEBUG_WEBHOOK, message)

    if SEND_TELEGRAM_ALERTS:
        send_telegram_message(message)

# =========================================================
# DATA FETCH
# =========================================================
def fetch_twelve_data_bars(symbol: str, interval: str = SCAN_INTERVAL, outputsize: int = 80) -> List[Dict[str, Any]]:
    if not TWELVE_DATA_API_KEY:
        raise ValueError("Missing TWELVE_DATA_API_KEY")

    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "format": "JSON",
        "apikey": TWELVE_DATA_API_KEY
    }

    r = requests.get(url, params=params, timeout=20)
    data = r.json()

    if "values" not in data:
        raise ValueError(f"Twelve Data error for {symbol}: {data}")

    values = list(reversed(data["values"]))
    bars = []
    for row in values:
        bars.append({
            "datetime": row.get("datetime"),
            "open": safe_float(row.get("open")),
            "high": safe_float(row.get("high")),
            "low": safe_float(row.get("low")),
            "close": safe_float(row.get("close")),
            "volume": safe_float(row.get("volume"))
        })
    return bars

def fetch_latest_underlying_price(symbol: str) -> float:
    bars = fetch_twelve_data_bars(symbol, interval=SCAN_INTERVAL, outputsize=2)
    if not bars:
        raise ValueError(f"No bars for {symbol}")
    return safe_float(bars[-1]["close"], 0.0)

# =========================================================
# INDICATORS
# =========================================================
def compute_vwap(bars: List[Dict[str, Any]]) -> float:
    cumulative_pv = 0.0
    cumulative_vol = 0.0
    for b in bars:
        typical = (b["high"] + b["low"] + b["close"]) / 3.0
        vol = max(b["volume"], 0.0)
        cumulative_pv += typical * vol
        cumulative_vol += vol
    if cumulative_vol == 0:
        return bars[-1]["close"]
    return cumulative_pv / cumulative_vol

def compute_rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0

    gains = []
    losses = []
    for i in range(1, period + 1):
        diff = closes[-i] - closes[-i - 1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def average_volume(bars: List[Dict[str, Any]], lookback: int = 10) -> float:
    recent = bars[-lookback:]
    vols = [b["volume"] for b in recent if b["volume"] > 0]
    if not vols:
        return 0.0
    return sum(vols) / len(vols)

def price_change_pct(a: float, b: float) -> float:
    if a == 0:
        return 0.0
    return ((b - a) / a) * 100.0

# =========================================================
# SIGNAL COOLDOWN
# =========================================================
def signal_cooldown_hit(symbol: str, side: str) -> bool:
    key = f"{symbol}_{side}"
    last_ts = RUNTIME_STATE["last_signal_times"].get(key, 0)
    return (time.time() - last_ts) < SIGNAL_COOLDOWN_SECONDS

def stamp_signal_time(symbol: str, side: str):
    key = f"{symbol}_{side}"
    RUNTIME_STATE["last_signal_times"][key] = time.time()
    save_runtime_state(RUNTIME_STATE)

# =========================================================
# GRADE HELPERS
# =========================================================
def grade_from_score(score: float) -> str:
    if score >= 95:
        return "A+"
    if score >= 90:
        return "A"
    if score >= 85:
        return "B+"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    return "D"

# =========================================================
# BROKER BRIDGE
# =========================================================
class BrokerBridge:
    def __init__(self):
        self.enabled = BROKER_ENABLED
        self.name = BROKER_NAME
        self.paper = BROKER_PAPER
        self.base_url = BROKER_BASE_URL
        self.api_key = BROKER_API_KEY
        self.api_secret = BROKER_API_SECRET

    def status(self) -> Dict[str, Any]:
        return {
            "broker_enabled": self.enabled,
            "broker_name": self.name,
            "broker_paper": self.paper,
            "broker_has_key": bool(self.api_key),
            "broker_has_secret": bool(self.api_secret),
            "broker_base_url": self.base_url or "not_set"
        }

    def submit_entry_order(self, position: Dict[str, Any]) -> Dict[str, Any]:
        if PAPER_TRADING or not self.enabled:
            broker_order_id = f"paper_entry_{uuid.uuid4().hex[:12]}"
            return {
                "ok": True,
                "broker_order_id": broker_order_id,
                "broker_status": "filled",
                "fill_price": position["entry_price"],
                "mode": "PAPER"
            }

        return {"ok": False, "reason": "Live broker submit not implemented"}

    def submit_partial_close_order(self, position: Dict[str, Any], exit_price: float, contracts_to_close: int, reason: str) -> Dict[str, Any]:
        if PAPER_TRADING or not self.enabled:
            broker_order_id = f"paper_partial_{uuid.uuid4().hex[:12]}"
            return {
                "ok": True,
                "broker_order_id": broker_order_id,
                "broker_status": "filled",
                "fill_price": round(exit_price, 2),
                "contracts_closed": contracts_to_close,
                "reason": reason,
                "mode": "PAPER"
            }

        return {"ok": False, "reason": "Live broker partial close not implemented"}

    def submit_close_order(self, position: Dict[str, Any], exit_price: float) -> Dict[str, Any]:
        if PAPER_TRADING or not self.enabled:
            broker_order_id = f"paper_close_{uuid.uuid4().hex[:12]}"
            return {
                "ok": True,
                "broker_order_id": broker_order_id,
                "broker_status": "filled",
                "fill_price": round(exit_price, 2),
                "mode": "PAPER"
            }

        return {"ok": False, "reason": "Live broker close not implemented"}

    def fetch_option_market_price(self, position: Dict[str, Any]) -> Dict[str, Any]:
        """
        Expected live broker endpoint example:
        GET {BROKER_BASE_URL}/option_price?symbol=QQQ&side=CALL&trade_id=...
        Returns:
        {
            "ok": true,
            "price": 1.42
        }
        """
        if not self.enabled or not self.base_url:
            return {"ok": False, "reason": "broker price endpoint unavailable"}

        try:
            url = f"{self.base_url.rstrip('/')}/option_price"
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            params = {
                "symbol": position.get("symbol"),
                "side": position.get("side"),
                "trade_id": position.get("trade_id"),
                "broker_order_id": position.get("broker_order_id", "")
            }

            r = requests.get(url, params=params, headers=headers, timeout=15)
            data = r.json()
            price = safe_float(data.get("price"), 0.0)

            if price > 0:
                return {"ok": True, "price": round(price, 2)}
            return {"ok": False, "reason": f"invalid broker price response: {data}"}
        except Exception as e:
            return {"ok": False, "reason": str(e)}

broker_bridge = BrokerBridge()

# =========================================================
# BOT LOGIC / SIGNAL ENGINE
# =========================================================
def analyze_symbol(symbol: str, bars: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if len(bars) < MIN_BARS:
        return None

    closes = [b["close"] for b in bars]
    last_bar = bars[-1]
    prev_bar = bars[-2]

    last_close = last_bar["close"]
    prev_close = prev_bar["close"]

    vwap = compute_vwap(bars[-30:])
    rsi = compute_rsi(closes, 14)
    avg_vol = average_volume(bars[:-1], 10)
    last_vol = last_bar["volume"]
    vol_ratio = (last_vol / avg_vol) if avg_vol > 0 else 1.0
    momentum_pct = price_change_pct(prev_close, last_close)

    call_score = 0.0
    put_score = 0.0
    notes_call = []
    notes_put = []

    if last_close > vwap:
        call_score += 28
        notes_call.append("price above VWAP")
    if prev_close <= vwap and last_close > vwap:
        call_score += 18
        notes_call.append("fresh VWAP reclaim")
    if 52 <= rsi <= 72:
        call_score += 18
        notes_call.append(f"RSI supportive ({round(rsi, 1)})")
    elif rsi > 72:
        call_score += 5
        notes_call.append(f"RSI strong but extended ({round(rsi, 1)})")
    if vol_ratio >= 1.2:
        call_score += 15
        notes_call.append(f"volume expansion x{round(vol_ratio, 2)}")
    if momentum_pct > 0:
        call_score += min(15, momentum_pct * 20)
        notes_call.append(f"positive momentum {round(momentum_pct, 2)}%")
    if last_bar["close"] > prev_bar["high"]:
        call_score += 10
        notes_call.append("broke previous candle high")

    if last_close < vwap:
        put_score += 28
        notes_put.append("price below VWAP")
    if prev_close >= vwap and last_close < vwap:
        put_score += 18
        notes_put.append("fresh VWAP rejection")
    if 28 <= rsi <= 48:
        put_score += 18
        notes_put.append(f"RSI bearish ({round(rsi, 1)})")
    elif rsi < 28:
        put_score += 5
        notes_put.append(f"RSI weak but extended ({round(rsi, 1)})")
    if vol_ratio >= 1.2:
        put_score += 15
        notes_put.append(f"volume expansion x{round(vol_ratio, 2)}")
    if momentum_pct < 0:
        put_score += min(15, abs(momentum_pct) * 20)
        notes_put.append(f"negative momentum {round(momentum_pct, 2)}%")
    if last_bar["close"] < prev_bar["low"]:
        put_score += 10
        notes_put.append("broke previous candle low")

    side = None
    score = 0.0
    notes = []

    if call_score >= put_score and ALLOW_CALLS:
        side = "CALL"
        score = min(99, round(call_score, 1))
        notes = notes_call
    elif ALLOW_PUTS:
        side = "PUT"
        score = min(99, round(put_score, 1))
        notes = notes_put

    if not side:
        return None
    if score < PREMIUM_MIN_SCORE:
        return None
    if signal_cooldown_hit(symbol, side):
        return None

    grade = grade_from_score(score)
    entry_price_proxy = max(0.50, round(abs(last_close * 0.0025), 2))

    return {
        "signal_id": f"{symbol}_{side}_{int(time.time())}",
        "symbol": symbol,
        "side": side,
        "grade": grade,
        "score": score,
        "entry_price": entry_price_proxy,
        "risk_amount": DEFAULT_RISK_PER_TRADE,
        "stop_pct": DEFAULT_STOP_PCT,
        "tp1_pct": DEFAULT_TP1_PCT,
        "tp2_pct": DEFAULT_TP2_PCT,
        "notes": " | ".join(notes),
        "manual": False,
        "meta": {
            "underlying_price": round(last_close, 2),
            "vwap": round(vwap, 2),
            "rsi": round(rsi, 2),
            "volume_ratio": round(vol_ratio, 2),
            "momentum_pct": round(momentum_pct, 3),
            "interval": SCAN_INTERVAL,
            "bar_time": last_bar["datetime"]
        }
    }

# =========================================================
# ENGINE STATE
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
            "open_positions_count": len([p for p in self.state["open_positions"].values() if p.get("status") == "OPEN"]),
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
        return len([p for p in self.state["open_positions"].values() if p.get("status") == "OPEN"])

    def has_same_direction_open(self, symbol: str, side: str) -> bool:
        for pos in self.state["open_positions"].values():
            if (
                pos.get("status") == "OPEN"
                and pos.get("symbol") == symbol.upper()
                and pos.get("side") == side.upper()
            ):
                return True
        return False

    def can_take_trade(self, signal: Dict[str, Any]) -> Tuple[bool, str]:
        self.reset_if_new_day()

        if self.state["engine_locked"]:
            return False, f"Engine locked: {self.state['lock_reason']}"

        if not AUTO_EXECUTION_ENABLED:
            return False, "Auto execution disabled"

        is_manual = signal.get("manual", False)
        if not market_is_open() and not TEST_MODE and not is_manual:
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

    def _append_scale_event(self, position: Dict[str, Any], contracts_closed: int, fill_price: float, reason: str, pnl_realized: float):
        position.setdefault("scale_events", [])
        position["scale_events"].append({
            "time": now_str(),
            "contracts_closed": contracts_closed,
            "fill_price": round(fill_price, 2),
            "reason": reason,
            "pnl_realized": round(pnl_realized, 2)
        })

    def _compute_smart_trailing_stop(self, pos: Dict[str, Any], current_price: float) -> float:
        if not SMART_TRAIL_ENABLED:
            return pos["stop_price"]

        current_stop = safe_float(pos["stop_price"], 0)

        if pos.get("tp2_hit"):
            candidate = round(current_price * (1 - TRAIL_AFTER_TP2_PCT), 2)
            return max(current_stop, candidate)

        if pos.get("tp1_hit"):
            candidate = round(current_price * (1 - TRAIL_BEFORE_TP2_PCT), 2)
            candidate = max(candidate, pos["entry_price"])
            return max(current_stop, candidate)

        return current_stop

    def _partial_close(self, trade_id: str, contracts_to_close: int, fill_price: float, reason: str) -> Dict[str, Any]:
        pos = self.state["open_positions"].get(trade_id)
        if not pos:
            return {"ok": False, "reason": "Trade not found"}

        if pos.get("status") != "OPEN":
            return {"ok": False, "reason": "Trade not open"}

        contracts_open = safe_int(pos.get("contracts_open", pos.get("contracts", 0)), 0)
        if contracts_open <= 0:
            return {"ok": False, "reason": "No contracts left"}

        contracts_to_close = min(max(1, contracts_to_close), contracts_open)

        broker_result = broker_bridge.submit_partial_close_order(pos, fill_price, contracts_to_close, reason)
        if not broker_result.get("ok"):
            return {"ok": False, "reason": broker_result.get("reason", "partial close failed")}

        actual_exit = round(safe_float(broker_result.get("fill_price", fill_price), fill_price), 2)
        pnl_per_contract = (actual_exit - pos["entry_price"]) * 100
        realized = round(pnl_per_contract * contracts_to_close, 2)

        pos["contracts_open"] = contracts_open - contracts_to_close
        pos["contracts_closed_total"] = safe_int(pos.get("contracts_closed_total", 0), 0) + contracts_to_close
        pos["realized_pnl"] = round(safe_float(pos.get("realized_pnl", 0.0), 0.0) + realized, 2)

        self.state["daily_realized_pnl"] += realized

        self._append_scale_event(pos, contracts_to_close, actual_exit, reason, realized)

        append_trade_log({
            "event": "PARTIAL_CLOSE",
            "time": now_str(),
            "trade_id": trade_id,
            "symbol": pos["symbol"],
            "side": pos["side"],
            "contracts_closed": contracts_to_close,
            "fill_price": actual_exit,
            "reason": reason,
            "realized_pnl": realized
        })

        send_trade_alert(
            f"💰 PARTIAL CLOSE\n"
            f"Trade: {trade_id}\n"
            f"{pos['symbol']} {pos['side']}\n"
            f"Reason: {reason}\n"
            f"Closed: {contracts_to_close}\n"
            f"Fill: {actual_exit}\n"
            f"Remaining: {pos['contracts_open']}\n"
            f"Realized: ${realized}",
            channel="premium"
        )

        if pos["contracts_open"] <= 0:
            pos["status"] = "CLOSED"
            pos["closed_at"] = now_str()
            pos["exit_price"] = actual_exit
            pos["close_reason"] = reason
            self.set_cooldown(pos["symbol"], pos["side"], COOLDOWN_MINUTES)

        save_engine_state(self.state)
        return {"ok": True, "position": pos, "contracts_closed": contracts_to_close, "fill_price": actual_exit, "realized_pnl": realized}

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
            "contracts_open": plan["contracts"],
            "contracts_closed_total": 0,
            "risk_dollars": plan["risk_dollars"],
            "trail_after_tp1": plan["trail_after_tp1"],
            "tp1_hit": False,
            "tp2_hit": False,
            "exit_price": None,
            "realized_pnl": 0.0,
            "close_reason": "",
            "notes": signal.get("notes", ""),
            "mode": "PAPER" if PAPER_TRADING else "LIVE",
            "manual": signal.get("manual", False),
            "broker_order_id": None,
            "broker_status": None,
            "scale_events": [],
            "meta": signal.get("meta", {}),
            "monitor": {
                "last_underlying_price": safe_float(signal.get("meta", {}).get("underlying_price"), 0.0),
                "last_option_price": plan["entry_price"],
                "last_monitor_update": now_str(),
                "price_source": "entry"
            }
        }

        broker_result = broker_bridge.submit_entry_order(position)
        if not broker_result.get("ok"):
            return {"ok": False, "reason": broker_result.get("reason", "broker entry failed")}

        position["broker_order_id"] = broker_result.get("broker_order_id")
        position["broker_status"] = broker_result.get("broker_status")

        fill_price = broker_result.get("fill_price")
        if fill_price is not None:
            position["entry_price"] = round(safe_float(fill_price, position["entry_price"]), 2)
            position["current_price"] = position["entry_price"]
            position["monitor"]["last_option_price"] = position["entry_price"]

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
            "mode": position["mode"],
            "manual": position["manual"],
            "broker_order_id": position["broker_order_id"],
            "broker_status": position["broker_status"]
        })

        send_trade_alert(
            f"🚀 OPEN TRADE\n"
            f"Trade: {trade_id}\n"
            f"{symbol} {side}\n"
            f"Grade: {position['grade']} ({position['score']})\n"
            f"Entry: {position['entry_price']}\n"
            f"Stop: {position['stop_price']}\n"
            f"TP1: {position['tp1_price']}\n"
            f"TP2: {position['tp2_price']}\n"
            f"Contracts: {position['contracts']}\n"
            f"Mode: {position['mode']}",
            channel="premium"
        )

        return {"ok": True, "trade_id": trade_id, "position": position}

    def update_position_price(self, trade_id: str, new_price: float) -> Dict[str, Any]:
        pos = self.state["open_positions"].get(trade_id)
        if not pos:
            return {"ok": False, "reason": "Trade not found"}

        if pos.get("status") != "OPEN":
            return {"ok": False, "reason": "Trade already closed"}

        new_price = safe_float(new_price)
        if new_price <= 0:
            return {"ok": False, "reason": "Invalid price"}

        prev_tp1 = bool(pos.get("tp1_hit"))
        prev_tp2 = bool(pos.get("tp2_hit"))
        old_stop = safe_float(pos.get("stop_price", 0.0), 0.0)

        pos["current_price"] = round(new_price, 2)

        # TP1
        if not pos["tp1_hit"] and new_price >= pos["tp1_price"]:
            pos["tp1_hit"] = True

            if pos["trail_after_tp1"]:
                pos["stop_price"] = round(max(pos["stop_price"], pos["entry_price"]), 2)

            if AUTO_SCALE_ENABLED and safe_int(pos.get("contracts_open", 0), 0) >= MIN_CONTRACTS_TO_SCALE:
                contracts_open = safe_int(pos["contracts_open"], 0)
                contracts_to_close = max(1, math.floor(contracts_open * TP1_SCALE_PCT))
                if contracts_to_close >= contracts_open:
                    contracts_to_close = max(1, contracts_open - 1) if contracts_open > 1 else 1

                self._partial_close(trade_id, contracts_to_close, new_price, "AUTO_TP1_SCALE")

            append_trade_log({
                "event": "TP1_HIT",
                "time": now_str(),
                "trade_id": trade_id,
                "symbol": pos["symbol"],
                "side": pos["side"],
                "price": round(new_price, 2)
            })

            send_trade_alert(
                f"🎯 TP1 HIT\n"
                f"Trade: {trade_id}\n"
                f"{pos['symbol']} {pos['side']}\n"
                f"Price: {round(new_price, 2)}\n"
                f"Stop moved to: {pos['stop_price']}",
                channel="premium"
            )

        # TP2
        if pos.get("status") == "OPEN" and not pos["tp2_hit"] and new_price >= pos["tp2_price"]:
            pos["tp2_hit"] = True

            if AUTO_SCALE_ENABLED and safe_int(pos.get("contracts_open", 0), 0) >= 1:
                contracts_open = safe_int(pos["contracts_open"], 0)
                contracts_to_close = max(1, math.floor(contracts_open * TP2_SCALE_PCT))
                if contracts_to_close > contracts_open:
                    contracts_to_close = contracts_open

                self._partial_close(trade_id, contracts_to_close, new_price, "AUTO_TP2_SCALE")

            append_trade_log({
                "event": "TP2_HIT",
                "time": now_str(),
                "trade_id": trade_id,
                "symbol": pos["symbol"],
                "side": pos["side"],
                "price": round(new_price, 2)
            })

            send_trade_alert(
                f"🏁 TP2 HIT\n"
                f"Trade: {trade_id}\n"
                f"{pos['symbol']} {pos['side']}\n"
                f"Price: {round(new_price, 2)}",
                channel="premium"
            )

        # refresh pos in case partial close updated state
        pos = self.state["open_positions"].get(trade_id)
        if not pos or pos.get("status") != "OPEN":
            save_engine_state(self.state)
            return {"ok": True, "position": pos}

        # smart trailing
        new_trail = self._compute_smart_trailing_stop(pos, new_price)
        if new_trail > safe_float(pos["stop_price"], 0):
            pos["stop_price"] = round(new_trail, 2)
            append_trade_log({
                "event": "TRAIL_STOP_UPDATE",
                "time": now_str(),
                "trade_id": trade_id,
                "symbol": pos["symbol"],
                "side": pos["side"],
                "new_stop": pos["stop_price"],
                "price": round(new_price, 2)
            })

            send_trade_alert(
                f"📈 TRAIL UPDATED\n"
                f"Trade: {trade_id}\n"
                f"{pos['symbol']} {pos['side']}\n"
                f"Price: {round(new_price, 2)}\n"
                f"Old Stop: {old_stop}\n"
                f"New Stop: {pos['stop_price']}",
                channel="premium"
            )

        # stop logic
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

        contracts_open = safe_int(pos.get("contracts_open", pos.get("contracts", 0)), 0)
        if contracts_open <= 0:
            pos["status"] = "CLOSED"
            save_engine_state(self.state)
            return {"ok": True, "position": pos}

        broker_result = broker_bridge.submit_close_order(pos, exit_price)
        if not broker_result.get("ok"):
            return {"ok": False, "reason": broker_result.get("reason", "broker close failed")}

        actual_exit = broker_result.get("fill_price", exit_price)
        actual_exit = round(safe_float(actual_exit, exit_price), 2)

        pnl_per_contract = (actual_exit - pos["entry_price"]) * 100
        realized = round(pnl_per_contract * contracts_open, 2)

        pos["contracts_closed_total"] = safe_int(pos.get("contracts_closed_total", 0), 0) + contracts_open
        pos["contracts_open"] = 0
        pos["status"] = "CLOSED"
        pos["closed_at"] = now_str()
        pos["exit_price"] = actual_exit
        pos["realized_pnl"] = round(safe_float(pos.get("realized_pnl", 0.0), 0.0) + realized, 2)
        pos["close_reason"] = reason
        pos["broker_close_order_id"] = broker_result.get("broker_order_id")
        pos["broker_close_status"] = broker_result.get("broker_status")

        self._append_scale_event(pos, contracts_open, actual_exit, reason, realized)

        self.state["daily_realized_pnl"] += realized
        self.set_cooldown(pos["symbol"], pos["side"], COOLDOWN_MINUTES)

        append_trade_log({
            "event": "CLOSE",
            "time": now_str(),
            "trade_id": trade_id,
            "symbol": pos["symbol"],
            "side": pos["side"],
            "entry_price": pos["entry_price"],
            "exit_price": pos["exit_price"],
            "contracts_closed": contracts_open,
            "pnl": realized,
            "reason": reason,
            "broker_close_order_id": pos.get("broker_close_order_id"),
            "broker_close_status": pos.get("broker_close_status")
        })

        if self.state["daily_realized_pnl"] <= -abs(MAX_DAILY_LOSS):
            self.lock_engine("Max daily loss breached after close")

        save_engine_state(self.state)

        icon = "⛔" if reason == "STOP_HIT" else "✅"
        send_trade_alert(
            f"{icon} CLOSE TRADE\n"
            f"Trade: {trade_id}\n"
            f"{pos['symbol']} {pos['side']}\n"
            f"Reason: {reason}\n"
            f"Exit: {actual_exit}\n"
            f"Contracts Closed: {contracts_open}\n"
            f"Realized: ${realized}\n"
            f"Day PnL: ${round(self.state['daily_realized_pnl'], 2)}",
            channel="premium"
        )

        return {"ok": True, "position": pos}

    def get_open_positions(self) -> List[Dict[str, Any]]:
        return [p for p in self.state["open_positions"].values() if p.get("status") == "OPEN"]

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

elite_engine = EliteExecutionEngine()

# =========================================================
# LIVE POSITION MONITOR
# =========================================================
def estimate_option_price_from_underlying(position: Dict[str, Any], underlying_price: float) -> float:
    entry_option = safe_float(position.get("entry_price"), 0.0)
    if entry_option <= 0:
        entry_option = MIN_OPTION_PRICE

    entry_underlying = safe_float(position.get("meta", {}).get("underlying_price"), 0.0)
    if entry_underlying <= 0:
        entry_underlying = safe_float(position.get("monitor", {}).get("last_underlying_price"), 0.0)

    if entry_underlying <= 0 or underlying_price <= 0:
        return max(MIN_OPTION_PRICE, round(safe_float(position.get("current_price", entry_option), entry_option), 2))

    move_pct = (underlying_price - entry_underlying) / entry_underlying

    if position.get("side") == "PUT":
        move_pct = -move_pct

    est = entry_option * (1 + (move_pct * OPTION_PRICE_SENSITIVITY))
    est = max(MIN_OPTION_PRICE, est)
    return round(est, 2)

def fetch_live_position_price(position: Dict[str, Any]) -> Tuple[bool, float, str]:
    source = OPTION_MARK_SOURCE

    if source in ["auto", "broker"]:
        broker_price = broker_bridge.fetch_option_market_price(position)
        if broker_price.get("ok"):
            return True, round(safe_float(broker_price["price"]), 2), "broker"
        if source == "broker":
            return False, 0.0, broker_price.get("reason", "broker price failed")

    try:
        underlying = fetch_latest_underlying_price(position["symbol"])
        est_option = estimate_option_price_from_underlying(position, underlying)
        return True, est_option, "estimate"
    except Exception as e:
        return False, 0.0, str(e)

def monitor_open_positions():
    if not POSITION_MONITOR_ENABLED:
        return

    open_positions = elite_engine.get_open_positions()
    if not open_positions:
        return

    for pos in open_positions:
        trade_id = pos.get("trade_id")
        if not trade_id:
            continue

        ok, live_price, source = fetch_live_position_price(pos)
        if not ok or live_price <= 0:
            log_debug(f"MONITOR PRICE FAIL [{trade_id}] -> {source}")
            continue

        pos["monitor"]["last_option_price"] = round(live_price, 2)
        pos["monitor"]["last_monitor_update"] = now_str()
        pos["monitor"]["price_source"] = source

        try:
            underlying = fetch_latest_underlying_price(pos["symbol"])
            pos["monitor"]["last_underlying_price"] = round(underlying, 2)
        except Exception:
            pass

        result = elite_engine.update_position_price(trade_id, live_price)

        if result.get("ok"):
            log_debug(
                f"MONITOR UPDATE [{trade_id}] "
                f"{pos['symbol']} {pos['side']} "
                f"price={live_price} source={source} "
                f"tp1={pos.get('tp1_hit')} tp2={pos.get('tp2_hit')} stop={pos.get('stop_price')}"
            )
        else:
            log_debug(f"MONITOR UPDATE FAIL [{trade_id}] -> {result.get('reason')}")

# =========================================================
# PAPER FILL CONTROL HELPERS
# =========================================================
def get_open_position_by_trade_id(trade_id: str) -> Optional[Dict[str, Any]]:
    pos = elite_engine.state["open_positions"].get(trade_id)
    if not pos:
        return None
    if pos.get("status") != "OPEN":
        return None
    return pos

def cmd_set_price(trade_id: str, price: float) -> Dict[str, Any]:
    return elite_engine.update_position_price(trade_id, price)

def cmd_hit_tp1(trade_id: str) -> Dict[str, Any]:
    pos = get_open_position_by_trade_id(trade_id)
    if not pos:
        return {"ok": False, "reason": "Trade not found or not open"}
    return elite_engine.update_position_price(trade_id, pos["tp1_price"])

def cmd_hit_tp2(trade_id: str) -> Dict[str, Any]:
    pos = get_open_position_by_trade_id(trade_id)
    if not pos:
        return {"ok": False, "reason": "Trade not found or not open"}
    return elite_engine.update_position_price(trade_id, pos["tp2_price"])

def cmd_hit_stop(trade_id: str) -> Dict[str, Any]:
    pos = get_open_position_by_trade_id(trade_id)
    if not pos:
        return {"ok": False, "reason": "Trade not found or not open"}
    return elite_engine.update_position_price(trade_id, pos["stop_price"])

# =========================================================
# COMMAND HELPERS
# =========================================================
def process_trade_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return elite_engine.place_trade(signal)
    except Exception as e:
        return {"ok": False, "reason": f"process_trade_signal error: {str(e)}"}

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

def cmd_positions_text() -> str:
    positions = elite_engine.get_open_positions()
    if not positions:
        return "No open positions."

    lines = ["Open Positions"]
    for p in positions[:10]:
        mon = p.get("monitor", {})
        lines.append(
            f"- {p['trade_id']} | {p['symbol']} {p['side']} | {p['grade']} | "
            f"Entry {p['entry_price']} | Current {p['current_price']} | Stop {p['stop_price']} | "
            f"TP1 {p['tp1_price']} | TP2 {p['tp2_price']} | OpenCtr {p.get('contracts_open')} | "
            f"ClosedCtr {p.get('contracts_closed_total')} | Realized {p.get('realized_pnl')} | "
            f"PriceSrc {mon.get('price_source', 'n/a')} | Broker {p.get('broker_status')}"
        )
    return "\n".join(lines)

def cmd_broker_status_text() -> str:
    s = broker_bridge.status()
    return (
        "Broker Status\n"
        f"Enabled: {s['broker_enabled']}\n"
        f"Name: {s['broker_name']}\n"
        f"Paper: {s['broker_paper']}\n"
        f"Has Key: {s['broker_has_key']}\n"
        f"Has Secret: {s['broker_has_secret']}\n"
        f"Base URL: {s['broker_base_url']}"
    )

# =========================================================
# TELEGRAM COMMAND CENTER
# =========================================================
def handle_telegram_command(text: str) -> Optional[str]:
    text = (text or "").strip()

    if text in ["/start", "/help"]:
        return (
            "UB Engine Command Center\n\n"
            "/ping - test bot\n"
            "/status - engine status\n"
            "/summary - summary\n"
            "/positions - open positions\n"
            "/brokerstatus - broker bridge status\n"
            "/lock - lock engine\n"
            "/unlock - unlock engine\n"
            "/flatten - close open positions\n"
            "/closeall - close open positions\n"
            "/close <trade_id> - close a specific trade\n"
            "/testcall - create test CALL signal\n"
            "/testput - create test PUT signal\n"
            "/setprice <trade_id> <price> - set current price\n"
            "/tp1 <trade_id> - simulate TP1 hit\n"
            "/tp2 <trade_id> - simulate TP2 hit\n"
            "/stop <trade_id> - simulate stop hit"
        )

    if text == "/ping":
        return "Bot is alive."

    if text == "/status":
        s = cmd_status()
        return (
            f"Status\n"
            f"Paper: {s['paper_trading']}\n"
            f"Auto Exec: {s['auto_execution_enabled']}\n"
            f"Locked: {s['engine_locked']}\n"
            f"Reason: {s['lock_reason']}\n"
            f"Daily PnL: {s['daily_realized_pnl']}\n"
            f"Daily Trades: {s['daily_trade_count']}\n"
            f"Open Positions: {s['open_positions_count']}"
        )

    if text == "/summary":
        s = cmd_summary()
        lines = [
            "Summary",
            f"Date: {s['date']}",
            f"Locked: {s['engine_locked']}",
            f"Daily PnL: {s['daily_realized_pnl']}",
            f"Daily Trades: {s['daily_trade_count']}",
            f"Open Positions: {s['open_positions_count']}"
        ]
        for p in s["open_positions"][:5]:
            lines.append(
                f"- {p['trade_id']} | {p['symbol']} {p['side']} | Entry {p['entry_price']} | Current {p['current_price']} | OpenCtr {p.get('contracts_open')}"
            )
        return "\n".join(lines)

    if text == "/positions":
        return cmd_positions_text()

    if text == "/brokerstatus":
        return cmd_broker_status_text()

    if text == "/lock":
        return cmd_lock("Telegram manual lock")["message"]

    if text == "/unlock":
        return cmd_unlock()["message"]

    if text in ["/flatten", "/closeall"]:
        result = cmd_flatten()
        return f"Close all sent. Closed: {len(result.get('results', []))}"

    if text.startswith("/close "):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            return "Usage: /close <trade_id>"
        trade_id = parts[1].strip()

        pos = elite_engine.state["open_positions"].get(trade_id)
        if not pos or pos.get("status") != "OPEN":
            return f"Trade not found or already closed: {trade_id}"

        exit_price = safe_float(pos.get("current_price", pos.get("entry_price", 0)))
        result = cmd_close_trade(trade_id, exit_price)
        return f"CLOSE RESULT: {result}"

    if text.startswith("/setprice "):
        parts = text.split()
        if len(parts) != 3:
            return "Usage: /setprice <trade_id> <price>"
        trade_id = parts[1].strip()
        price = safe_float(parts[2], -1)
        if price <= 0:
            return "Invalid price."
        result = cmd_set_price(trade_id, price)
        return f"SET PRICE RESULT: {result}"

    if text.startswith("/tp1 "):
        parts = text.split(maxsplit=1)
        if len(parts) != 2:
            return "Usage: /tp1 <trade_id>"
        result = cmd_hit_tp1(parts[1].strip())
        return f"TP1 RESULT: {result}"

    if text.startswith("/tp2 "):
        parts = text.split(maxsplit=1)
        if len(parts) != 2:
            return "Usage: /tp2 <trade_id>"
        result = cmd_hit_tp2(parts[1].strip())
        return f"TP2 RESULT: {result}"

    if text.startswith("/stop "):
        parts = text.split(maxsplit=1)
        if len(parts) != 2:
            return "Usage: /stop <trade_id>"
        result = cmd_hit_stop(parts[1].strip())
        return f"STOP RESULT: {result}"

    if text == "/testcall":
        signal = {
            "signal_id": f"TEST_QQQ_CALL_{int(time.time())}",
            "symbol": "QQQ",
            "side": "CALL",
            "grade": "A",
            "score": 95,
            "entry_price": 1.25,
            "risk_amount": 100,
            "stop_pct": 0.25,
            "tp1_pct": 0.30,
            "tp2_pct": 0.60,
            "notes": "Telegram test CALL",
            "manual": True,
            "meta": {"underlying_price": 500.0}
        }
        result = process_trade_signal(signal)
        return f"TEST CALL: {result}"

    if text == "/testput":
        signal = {
            "signal_id": f"TEST_SPY_PUT_{int(time.time())}",
            "symbol": "SPY",
            "side": "PUT",
            "grade": "A",
            "score": 95,
            "entry_price": 1.25,
            "risk_amount": 100,
            "stop_pct": 0.25,
            "tp1_pct": 0.30,
            "tp2_pct": 0.60,
            "notes": "Telegram test PUT",
            "manual": True,
            "meta": {"underlying_price": 500.0}
        }
        result = process_trade_signal(signal)
        return f"TEST PUT: {result}"

    return None

def poll_telegram_commands():
    updates = get_telegram_updates()
    if not updates:
        return

    for update in updates:
        message = update.get("message", {})
        text = message.get("text", "")
        chat = str(message.get("chat", {}).get("id", ""))

        print(f"[TELEGRAM CMD] Received: {text}", flush=True)

        if TELEGRAM_CHAT_ID and chat != TELEGRAM_CHAT_ID:
            print(f"[TELEGRAM CMD] Ignored wrong chat: {chat}", flush=True)
            continue

        reply = handle_telegram_command(text)
        print(f"[TELEGRAM CMD] Reply: {reply}", flush=True)

        if reply:
            send_telegram_message(reply)

# =========================================================
# SCAN
# =========================================================
def scan_once() -> List[Dict[str, Any]]:
    signals = []

    for symbol in SCAN_SYMBOLS:
        try:
            print(f"[SCAN] Pulling bars for {symbol}", flush=True)
            bars = fetch_twelve_data_bars(symbol, SCAN_INTERVAL, outputsize=max(MIN_BARS + 10, 60))
            signal = analyze_symbol(symbol, bars)

            if signal:
                print(f"[SCAN] SIGNAL FOUND -> {signal['symbol']} {signal['side']} {signal['grade']} {signal['score']}", flush=True)
                signals.append(signal)
            else:
                print(f"[SCAN] No qualifying signal for {symbol}", flush=True)

        except Exception as e:
            log_debug(f"SCAN ERROR [{symbol}]: {e}")

    return signals

def process_signals(signals: List[Dict[str, Any]]):
    for signal in signals:
        print(f"[PROCESS] Sending signal into engine -> {signal['symbol']} {signal['side']}", flush=True)
        result = process_trade_signal(signal)

        if result.get("ok"):
            stamp_signal_time(signal["symbol"], signal["side"])
            log_debug(f"EXECUTED: {signal['symbol']} {signal['side']} {signal['grade']} {signal['score']}")
        else:
            log_debug(f"BLOCKED: {signal['symbol']} {signal['side']} -> {result.get('reason')}")

# =========================================================
# MAIN LOOP
# =========================================================
def run_engine_loop():
    log_debug("Auto TP / scale-out / smart trail engine started.")
    print("=== ENGINE LOOP STARTED ===", flush=True)

    last_scan_ts = 0.0
    last_heartbeat_ts = 0.0
    last_position_monitor_ts = 0.0
    heartbeat_interval = 30

    while True:
        try:
            now_ts = time.time()

            if now_ts - last_heartbeat_ts >= heartbeat_interval:
                print(f"Loop heartbeat: {now_str()}", flush=True)
                last_heartbeat_ts = now_ts

            if TELEGRAM_COMMANDS_ENABLED:
                poll_telegram_commands()

            if POSITION_MONITOR_ENABLED and (now_ts - last_position_monitor_ts) >= POSITION_MONITOR_SECONDS:
                last_position_monitor_ts = now_ts
                monitor_open_positions()

            current_market_status = market_is_open()
            should_scan = (now_ts - last_scan_ts) >= SCAN_SECONDS

            if should_scan:
                last_scan_ts = now_ts
                print(f"[SCAN TIMER] Market open: {current_market_status} | TEST_MODE: {TEST_MODE}", flush=True)

                if current_market_status or TEST_MODE:
                    signals = scan_once()
                    print(f"[SCAN TIMER] Signals found: {len(signals)}", flush=True)
                    if signals:
                        process_signals(signals)
                else:
                    print("[SCAN TIMER] Market closed. Waiting for next scan window.", flush=True)

            time.sleep(TELEGRAM_POLL_SECONDS)

        except KeyboardInterrupt:
            log_debug("Engine stopped by user.")
            break
        except Exception as e:
            log_debug(f"MAIN LOOP ERROR: {e}")
            print(f"MAIN LOOP ERROR: {e}", flush=True)
            time.sleep(5)

# =========================================================
# TEST MODE
# =========================================================
def run_test_mode():
    print("Running TEST_MODE...", flush=True)

    test_signal = {
        "signal_id": f"TEST_QQQ_CALL_{int(time.time())}",
        "symbol": "QQQ",
        "side": "CALL",
        "grade": "A",
        "score": 95,
        "entry_price": 1.45,
        "risk_amount": 100,
        "stop_pct": 0.25,
        "tp1_pct": 0.30,
        "tp2_pct": 0.60,
        "notes": "VWAP reclaim + premium test",
        "manual": True,
        "meta": {"underlying_price": 500.0}
    }

    result = process_trade_signal(test_signal)
    print("TRADE RESULT:", result, flush=True)
    print("STATUS:", cmd_status(), flush=True)
    print("BROKER STATUS:", broker_bridge.status(), flush=True)
    print("SUMMARY:", cmd_summary(), flush=True)

# =========================================================
# ENTRY
# =========================================================
if __name__ == "__main__":
    print("=== UB ENGINE BOOTING ===", flush=True)
    print(f"TIME: {now_str()}", flush=True)
    print(f"TEST_MODE: {TEST_MODE}", flush=True)
    print(f"PAPER_TRADING: {PAPER_TRADING}", flush=True)
    print(f"AUTO_EXECUTION_ENABLED: {AUTO_EXECUTION_ENABLED}", flush=True)
    print(f"AUTO_SCALE_ENABLED: {AUTO_SCALE_ENABLED}", flush=True)
    print(f"SMART_TRAIL_ENABLED: {SMART_TRAIL_ENABLED}", flush=True)
    print(f"POSITION_MONITOR_ENABLED: {POSITION_MONITOR_ENABLED}", flush=True)
    print(f"POSITION_MONITOR_SECONDS: {POSITION_MONITOR_SECONDS}", flush=True)
    print(f"OPTION_MARK_SOURCE: {OPTION_MARK_SOURCE}", flush=True)
    print(f"OPTION_PRICE_SENSITIVITY: {OPTION_PRICE_SENSITIVITY}", flush=True)
    print(f"TP1_SCALE_PCT: {TP1_SCALE_PCT}", flush=True)
    print(f"TP2_SCALE_PCT: {TP2_SCALE_PCT}", flush=True)
    print(f"TRAIL_BEFORE_TP2_PCT: {TRAIL_BEFORE_TP2_PCT}", flush=True)
    print(f"TRAIL_AFTER_TP2_PCT: {TRAIL_AFTER_TP2_PCT}", flush=True)
    print(f"SCAN_SYMBOLS: {SCAN_SYMBOLS}", flush=True)
    print(f"SCAN_INTERVAL: {SCAN_INTERVAL}", flush=True)
    print(f"SCAN_SECONDS: {SCAN_SECONDS}", flush=True)
    print(f"TELEGRAM_POLL_SECONDS: {TELEGRAM_POLL_SECONDS}", flush=True)
    print(f"TELEGRAM_COMMANDS_ENABLED: {TELEGRAM_COMMANDS_ENABLED}", flush=True)
    print(f"BROKER_ENABLED: {BROKER_ENABLED}", flush=True)
    print(f"BROKER_NAME: {BROKER_NAME}", flush=True)
    print(f"BROKER_PAPER: {BROKER_PAPER}", flush=True)
    print(f"MARKET_IS_OPEN_NOW: {market_is_open()}", flush=True)

    if TEST_MODE:
        run_test_mode()
    else:
        run_engine_loop()

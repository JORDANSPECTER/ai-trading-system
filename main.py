import os
import json
import time
import requests
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

# =========================================================
# FILES
# =========================================================
ENGINE_STATE_FILE = "engine_state.json"
TRADE_LOG_FILE = "trade_log.json"
BOT_RUNTIME_FILE = "bot_runtime.json"
MAX_HISTORY = 500

# =========================================================
# ENV CONFIG
# =========================================================
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"
AUTO_EXECUTION_ENABLED = os.getenv("AUTO_EXECUTION_ENABLED", "true").lower() == "true"
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"

SCAN_SYMBOLS = [s.strip().upper() for s in os.getenv("SCAN_SYMBOLS", "QQQ,SPY").split(",") if s.strip()]
SCAN_INTERVAL = os.getenv("SCAN_INTERVAL", "5min")
SCAN_SECONDS = int(os.getenv("SCAN_SECONDS", "60"))
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
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text[:3900]
        }
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

    signal = {
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

    return signal

def build_alert_text(signal: Dict[str, Any], execution_result: Optional[Dict[str, Any]] = None) -> str:
    meta = signal.get("meta", {})
    lines = [
        f"🚨 {signal['symbol']} {signal['side']} SIGNAL",
        f"Grade: {signal['grade']} | Score: {signal['score']}",
        f"Underlying: {meta.get('underlying_price', 'N/A')} | VWAP: {meta.get('vwap', 'N/A')} | RSI: {meta.get('rsi', 'N/A')}",
        f"Vol Ratio: {meta.get('volume_ratio', 'N/A')} | Momentum: {meta.get('momentum_pct', 'N/A')}%",
        f"Entry Proxy: {signal.get('entry_price')} | Risk: ${signal.get('risk_amount')}",
        f"Notes: {signal.get('notes', '')}",
        f"Bar Time: {meta.get('bar_time', 'N/A')}"
    ]

    if execution_result:
        if execution_result.get("ok"):
            pos = execution_result.get("position", {})
            lines.append(
                f"Execution: OK | Mode: {pos.get('mode', 'PAPER')} | Contracts: {pos.get('contracts')} | "
                f"Stop: {pos.get('stop_price')} | TP1: {pos.get('tp1_price')} | TP2: {pos.get('tp2_price')}"
            )
        else:
            lines.append(f"Execution Blocked: {execution_result.get('reason', 'unknown')}")

    return "\n".join(lines)

def route_signal_alerts(signal: Dict[str, Any], execution_result: Optional[Dict[str, Any]] = None):
    text = build_alert_text(signal, execution_result)

    if SEND_PREMIUM_ALERTS and signal["score"] >= PREMIUM_MIN_SCORE and DISCORD_PREMIUM_WEBHOOK:
        send_discord_message(DISCORD_PREMIUM_WEBHOOK, text)

    if SEND_FREE_ALERTS and signal["score"] >= FREE_MIN_SCORE and DISCORD_FREE_WEBHOOK:
        send_discord_message(DISCORD_FREE_WEBHOOK, text)

    if SEND_TELEGRAM_ALERTS:
        send_telegram_message(text)

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

        if not market_is_open() and not TEST_MODE:
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
            "mode": "PAPER" if PAPER_TRADING else "LIVE",
            "meta": signal.get("meta", {})
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

# =========================================================
# GLOBAL ENGINE
# =========================================================
elite_engine = EliteExecutionEngine()

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

# =========================================================
# TELEGRAM COMMAND CENTER
# =========================================================
def handle_telegram_command(text: str) -> Optional[str]:
    text = (text or "").strip()

    if text in ["/start", "/help"]:
        return (
            "UB Engine Command Center\n\n"
            "/status - engine status\n"
            "/summary - open positions summary\n"
            "/lock - lock engine\n"
            "/unlock - unlock engine\n"
            "/flatten - close open positions\n"
            "/testcall - create test CALL signal\n"
            "/testput - create test PUT signal\n"
            "/ping - test bot"
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
            f"Summary",
            f"Date: {s['date']}",
            f"Locked: {s['engine_locked']}",
            f"Daily PnL: {s['daily_realized_pnl']}",
            f"Daily Trades: {s['daily_trade_count']}",
            f"Open Positions: {s['open_positions_count']}"
        ]
        for p in s["open_positions"][:5]:
            lines.append(
                f"- {p['symbol']} {p['side']} | {p['grade']} | Entry {p['entry_price']} | Current {p['current_price']}"
            )
        return "\n".join(lines)

    if text == "/lock":
        return cmd_lock("Telegram manual lock")["message"]

    if text == "/unlock":
        return cmd_unlock()["message"]

    if text == "/flatten":
        result = cmd_flatten()
        return f"Flatten sent. Closed: {len(result.get('results', []))}"

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
            "notes": "Telegram test CALL"
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
            "notes": "Telegram test PUT"
        }
        result = process_trade_signal(signal)
        return f"TEST PUT: {result}"

    return None

def poll_telegram_commands():
    updates = get_telegram_updates()
    for update in updates:
        message = update.get("message", {})
        text = message.get("text", "")
        chat = str(message.get("chat", {}).get("id", ""))

        if TELEGRAM_CHAT_ID and chat != TELEGRAM_CHAT_ID:
            continue

        reply = handle_telegram_command(text)
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
        route_signal_alerts(signal, result)

        if result.get("ok"):
            stamp_signal_time(signal["symbol"], signal["side"])
            log_debug(f"EXECUTED: {signal['symbol']} {signal['side']} {signal['grade']} {signal['score']}")
        else:
            log_debug(f"BLOCKED: {signal['symbol']} {signal['side']} -> {result.get('reason')}")

# =========================================================
# MAIN LOOP
# =========================================================
def run_engine_loop():
    log_debug("Elite merged engine started.")
    print("=== ENGINE LOOP STARTED ===", flush=True)

    while True:
        try:
            print(f"Loop heartbeat: {now_str()}", flush=True)

            if TELEGRAM_COMMANDS_ENABLED:
                print("[TELEGRAM] Polling commands...", flush=True)
                poll_telegram_commands()

            current_market_status = market_is_open()
            print(f"Market open: {current_market_status} | TEST_MODE: {TEST_MODE}", flush=True)

            if current_market_status or TEST_MODE:
                signals = scan_once()
                print(f"Signals found: {len(signals)}", flush=True)

                if signals:
                    process_signals(signals)
            else:
                print("Market closed. Waiting for next loop.", flush=True)

            time.sleep(SCAN_SECONDS)

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
        "meta": {
            "underlying_price": 450.0,
            "vwap": 449.2,
            "rsi": 61.4,
            "volume_ratio": 1.55,
            "momentum_pct": 0.42,
            "interval": SCAN_INTERVAL,
            "bar_time": now_str()
        }
    }

    result = process_trade_signal(test_signal)
    print("TRADE RESULT:", result, flush=True)
    print("STATUS:", cmd_status(), flush=True)
    print("SUMMARY:", cmd_summary(), flush=True)

    if result.get("ok"):
        trade_id = result["trade_id"]

        print("\n--- SIMULATE TP1 ---", flush=True)
        print(elite_engine.update_position_price(trade_id, 1.90), flush=True)

        print("\n--- SIMULATE TP2 ---", flush=True)
        print(elite_engine.update_position_price(trade_id, 2.35), flush=True)

        print("\n--- MANUAL CLOSE ---", flush=True)
        print(cmd_close_trade(trade_id, 2.10), flush=True)

        print("\n--- FINAL SUMMARY ---", flush=True)
        print(cmd_summary(), flush=True)

# =========================================================
# ENTRY
# =========================================================
if __name__ == "__main__":
    print("=== UB ENGINE BOOTING ===", flush=True)
    print(f"TIME: {now_str()}", flush=True)
    print(f"TEST_MODE: {TEST_MODE}", flush=True)
    print(f"PAPER_TRADING: {PAPER_TRADING}", flush=True)
    print(f"AUTO_EXECUTION_ENABLED: {AUTO_EXECUTION_ENABLED}", flush=True)
    print(f"SCAN_SYMBOLS: {SCAN_SYMBOLS}", flush=True)
    print(f"SCAN_INTERVAL: {SCAN_INTERVAL}", flush=True)
    print(f"SCAN_SECONDS: {SCAN_SECONDS}", flush=True)
    print(f"TELEGRAM_COMMANDS_ENABLED: {TELEGRAM_COMMANDS_ENABLED}", flush=True)
    print(f"MARKET_IS_OPEN_NOW: {market_is_open()}", flush=True)

    if TEST_MODE:
        run_test_mode()
    else:
        run_engine_loop()

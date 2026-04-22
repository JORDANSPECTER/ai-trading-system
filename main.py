import os
import sys
import json
import time
import math
import traceback
from copy import deepcopy
from datetime import datetime
from typing import Optional, Dict, Any, List

import requests


# =========================================================
# UNBIASED TRADES ELITE ENGINE
# FULL MAIN.PY
# DISCORD + TELEGRAM + SIGNAL PARSER + FILE DEBUG
# + PAPER + ALPACA + RISK POLICY + POSITION SIZING
# + PRE-TRADE VALIDATOR + PORTFOLIO RISK MANAGER
# + REGIME ENGINE
# + LIVE OPTIONS MODE UPDATE
# =========================================================


# =========================================================
# ENV VARS
# =========================================================
DISCORD_AI_WEBHOOK = os.getenv("DISCORD_AI_WEBHOOK", "").strip()
DISCORD_FREE_WEBHOOK = os.getenv("DISCORD_FREE_WEBHOOK", "").strip()
DISCORD_PREMIUM_WEBHOOK = os.getenv("DISCORD_PREMIUM_WEBHOOK", "").strip()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

BOT_NAME = os.getenv("BOT_NAME", "UnBiased Trades Engine").strip()

DEBUG_MODE = os.getenv("DEBUG_MODE", "true").lower() == "true"
RUN_TEST_ON_START = os.getenv("RUN_TEST_ON_START", "true").lower() == "true"
RUN_LOOP = os.getenv("RUN_LOOP", "true").lower() == "true"

POLL_SECONDS = int(os.getenv("POLL_SECONDS", "5"))
HEARTBEAT_MINUTES = int(os.getenv("HEARTBEAT_MINUTES", "30"))

SIGNAL_FILE = os.getenv("SIGNAL_FILE", "signal.json").strip()
STATE_FILE = os.getenv("STATE_FILE", "engine_state.json").strip()
POSITIONS_FILE = os.getenv("POSITIONS_FILE", "positions.json").strip()

ENABLE_TELEGRAM_COMMANDS = os.getenv("ENABLE_TELEGRAM_COMMANDS", "true").lower() == "true"
ENABLE_PAPER_EXECUTION = os.getenv("ENABLE_PAPER_EXECUTION", "true").lower() == "true"
ENABLE_DISCORD = os.getenv("ENABLE_DISCORD", "true").lower() == "true"
ENABLE_TELEGRAM_ALERTS = os.getenv("ENABLE_TELEGRAM_ALERTS", "true").lower() == "true"
ENABLE_HEARTBEAT = os.getenv("ENABLE_HEARTBEAT", "true").lower() == "true"

# =========================
# ALPACA
# =========================
ENABLE_ALPACA = os.getenv("ENABLE_ALPACA", "false").lower() == "true"
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "").strip()
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "").strip()
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").strip()
ALPACA_ORDER_TIMEOUT = int(os.getenv("ALPACA_ORDER_TIMEOUT", "20"))
ALPACA_SYNC_POSITIONS = os.getenv("ALPACA_SYNC_POSITIONS", "true").lower() == "true"
ALPACA_ENABLE_OPTIONS = os.getenv("ALPACA_ENABLE_OPTIONS", "true").lower() == "true"
ALPACA_LIVE_OPTIONS_APPROVED = os.getenv("ALPACA_LIVE_OPTIONS_APPROVED", "false").lower() == "true"
USE_ALPACA_OPTIONS_BUYING_POWER = os.getenv("USE_ALPACA_OPTIONS_BUYING_POWER", "true").lower() == "true"
LIVE_MODE = os.getenv("LIVE_MODE", "false").lower() == "true"

# =========================
# SIGNAL / EXECUTION DEFAULTS
# =========================
MAX_SIGNAL_AGE_SECONDS = int(os.getenv("MAX_SIGNAL_AGE_SECONDS", "180"))

DEFAULT_PAPER_QTY = int(os.getenv("DEFAULT_PAPER_QTY", "1"))
DEFAULT_LIVE_QTY = int(os.getenv("DEFAULT_LIVE_QTY", "1"))
DEFAULT_RISK_PER_TRADE = float(os.getenv("DEFAULT_RISK_PER_TRADE", "1.0"))

DEFAULT_SCALE1_PCT = float(os.getenv("DEFAULT_SCALE1_PCT", "0.50"))
DEFAULT_SCALE2_PCT = float(os.getenv("DEFAULT_SCALE2_PCT", "0.25"))
DEFAULT_TRAIL_PCT = float(os.getenv("DEFAULT_TRAIL_PCT", "0.20"))
DEFAULT_BREAK_EVEN_AFTER_TP1 = os.getenv("DEFAULT_BREAK_EVEN_AFTER_TP1", "true").lower() == "true"

ALLOW_LIVE_BUYS = os.getenv("ALLOW_LIVE_BUYS", "false").lower() == "true"
ALLOW_LIVE_SELLS = os.getenv("ALLOW_LIVE_SELLS", "true").lower() == "true"
REQUIRE_OPTION_SYMBOL = os.getenv("REQUIRE_OPTION_SYMBOL", "true").lower() == "true"

# =========================
# RISK LIMITS
# =========================
MAX_RISK_PER_TRADE_PCT = float(os.getenv("MAX_RISK_PER_TRADE_PCT", "0.005"))
MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", "0.02"))
MAX_PORTFOLIO_HEAT_PCT = float(os.getenv("MAX_PORTFOLIO_HEAT_PCT", "0.03"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "3"))
MAX_SAME_TICKER_POSITIONS = int(os.getenv("MAX_SAME_TICKER_POSITIONS", "1"))
MAX_CONSECUTIVE_LOSSES = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))

PAPER_ACCOUNT_EQUITY = float(os.getenv("PAPER_ACCOUNT_EQUITY", "25000"))
LIVE_ACCOUNT_EQUITY_FALLBACK = float(os.getenv("LIVE_ACCOUNT_EQUITY_FALLBACK", "25000"))

# =========================
# POSITION SIZING
# =========================
MIN_POSITION_QTY = int(os.getenv("MIN_POSITION_QTY", "1"))
MAX_POSITION_QTY = int(os.getenv("MAX_POSITION_QTY", "10"))
USE_SIGNAL_QTY_AS_MAX = os.getenv("USE_SIGNAL_QTY_AS_MAX", "false").lower() == "true"

CONFIDENCE_MULT_A_PLUS = float(os.getenv("CONFIDENCE_MULT_A_PLUS", "1.00"))
CONFIDENCE_MULT_A = float(os.getenv("CONFIDENCE_MULT_A", "1.00"))
CONFIDENCE_MULT_B = float(os.getenv("CONFIDENCE_MULT_B", "0.70"))
CONFIDENCE_MULT_C = float(os.getenv("CONFIDENCE_MULT_C", "0.40"))

# =========================
# PRE-TRADE VALIDATOR
# =========================
MIN_RR_RATIO = float(os.getenv("MIN_RR_RATIO", "1.2"))
REJECT_DUPLICATE_OPEN_SYMBOL = os.getenv("REJECT_DUPLICATE_OPEN_SYMBOL", "true").lower() == "true"
ENFORCE_NO_TRADE_WINDOW = os.getenv("ENFORCE_NO_TRADE_WINDOW", "false").lower() == "true"
NO_TRADE_START_HHMM = os.getenv("NO_TRADE_START_HHMM", "09:30").strip()
NO_TRADE_END_HHMM = os.getenv("NO_TRADE_END_HHMM", "09:33").strip()

# =========================
# PORTFOLIO RISK MANAGER
# =========================
MAX_PROJECTED_PORTFOLIO_HEAT_PCT = float(os.getenv("MAX_PROJECTED_PORTFOLIO_HEAT_PCT", "0.03"))
MAX_SYMBOL_PORTFOLIO_COUNT = int(os.getenv("MAX_SYMBOL_PORTFOLIO_COUNT", "1"))
MAX_DIRECTIONAL_INDEX_COUNT = int(os.getenv("MAX_DIRECTIONAL_INDEX_COUNT", "2"))
MAX_CORRELATED_THEME_COUNT = int(os.getenv("MAX_CORRELATED_THEME_COUNT", "2"))

CORRELATED_TICKERS = {
    "SPY", "QQQ", "IWM", "DIA", "NVDA", "TSLA", "AAPL", "MSFT", "META", "AMD"
}

# =========================
# REGIME ENGINE
# =========================
ENABLE_REGIME_ENGINE = os.getenv("ENABLE_REGIME_ENGINE", "true").lower() == "true"
ALLOWED_REGIMES = {
    part.strip().upper()
    for part in os.getenv("ALLOWED_REGIMES", "TREND,EXPANSION,NORMAL").split(",")
    if part.strip()
}
MIN_REGIME_SCORE = float(os.getenv("MIN_REGIME_SCORE", "0.50"))
BLOCK_CHOP_REGIME = os.getenv("BLOCK_CHOP_REGIME", "true").lower() == "true"
ALLOW_EVENT_REGIME = os.getenv("ALLOW_EVENT_REGIME", "false").lower() == "true"


# =========================================================
# GLOBALS
# =========================================================
GLOBAL_STATE = None
GLOBAL_POSITIONS = None


# =========================================================
# BASIC UTILS
# =========================================================
def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")


def epoch() -> int:
    return int(time.time())


def log(msg: str):
    print(f"[{now_ts()}] {msg}", flush=True)


def debug(msg: str):
    if DEBUG_MODE:
        log(f"DEBUG: {msg}")


def safe_float(v, default=0.0) -> float:
    try:
        if v is None or v == "":
            return float(default)
        return float(v)
    except Exception:
        return float(default)


def safe_int(v, default=0) -> int:
    try:
        if v is None or v == "":
            return int(default)
        return int(v)
    except Exception:
        return int(default)


def file_exists(path: str) -> bool:
    return os.path.exists(path)


def load_json_file(path: str, default):
    try:
        if not file_exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log(f"❌ Failed reading {path}: {e}")
        return default


def save_json_file(path: str, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        log(f"❌ Failed saving {path}: {e}")
        return False


def pct_change(entry: float, last: float) -> float:
    if entry <= 0:
        return 0.0
    return ((last - entry) / entry) * 100.0


def signal_hash(signal: Dict[str, Any]) -> str:
    try:
        key = json.dumps(signal, sort_keys=True)
        return str(abs(hash(key)))
    except Exception:
        return str(epoch())


def current_trade_day() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def current_hhmm() -> str:
    return datetime.now().strftime("%H:%M")


def hhmm_to_minutes(hhmm: str) -> int:
    parts = hhmm.split(":")
    if len(parts) != 2:
        return 0
    return int(parts[0]) * 60 + int(parts[1])


def is_now_in_no_trade_window() -> bool:
    if not ENFORCE_NO_TRADE_WINDOW:
        return False
    now_m = hhmm_to_minutes(current_hhmm())
    start_m = hhmm_to_minutes(NO_TRADE_START_HHMM)
    end_m = hhmm_to_minutes(NO_TRADE_END_HHMM)
    return start_m <= now_m <= end_m


def debug_file_lookup(path: str):
    try:
        cwd = os.getcwd()
        abs_path = os.path.abspath(path)

        log("📁 FILE DEBUG MODE")
        log(f"Working directory: {cwd}")
        log(f"Requested SIGNAL_FILE: {path}")
        log(f"Absolute SIGNAL_FILE path: {abs_path}")
        log(f"Exists?: {os.path.exists(path)}")
        log(f"Absolute exists?: {os.path.exists(abs_path)}")

        try:
            root_files = os.listdir(cwd)
            log(f"Files in working directory: {root_files}")
        except Exception as inner_e:
            log(f"❌ Could not list working directory files: {inner_e}")

        repo_guess = "/opt/render/project/src"
        if os.path.exists(repo_guess):
            try:
                repo_files = os.listdir(repo_guess)
                log(f"Files in /opt/render/project/src: {repo_files}")
            except Exception as inner_e:
                log(f"❌ Could not list /opt/render/project/src: {inner_e}")

    except Exception as e:
        log(f"❌ debug_file_lookup failed: {e}")


# =========================================================
# STATE
# =========================================================
def default_state() -> Dict[str, Any]:
    return {
        "engine_enabled": True,
        "paper_enabled": ENABLE_PAPER_EXECUTION,
        "discord_enabled": ENABLE_DISCORD,
        "telegram_enabled": ENABLE_TELEGRAM_ALERTS,
        "alpaca_enabled": ENABLE_ALPACA,
        "last_signal_hash": "",
        "last_signal_time": 0,
        "last_signal_file_mtime": 0,
        "last_heartbeat_time": 0,
        "last_telegram_update_id": 0,
        "signal_count": 0,
        "paper_trade_count": 0,
        "live_trade_count": 0,
        "boot_time": epoch(),
        "notes": "",
        "daily_realized_pnl_pct": 0.0,
        "consecutive_losses": 0,
        "last_trade_day": current_trade_day(),
        "kill_switch": False,
        "bot_paused": False,
        "last_mode": "LIVE" if LIVE_MODE else "PAPER"
    }


def load_state() -> Dict[str, Any]:
    state = load_json_file(STATE_FILE, default_state())
    merged = default_state()
    merged.update(state)
    return merged


def save_state(state: Dict[str, Any]):
    save_json_file(STATE_FILE, state)


def default_positions() -> Dict[str, Any]:
    return {
        "open_positions": [],
        "closed_positions": [],
        "last_position_id": 0
    }


def load_positions() -> Dict[str, Any]:
    positions = load_json_file(POSITIONS_FILE, default_positions())
    merged = default_positions()
    merged.update(positions)
    return merged


def save_positions(positions: Dict[str, Any]):
    save_json_file(POSITIONS_FILE, positions)


# =========================================================
# RISK HELPERS
# =========================================================
def reset_daily_risk_counters_if_needed(state: Dict[str, Any]):
    today = current_trade_day()
    if state.get("last_trade_day") != today:
        state["daily_realized_pnl_pct"] = 0.0
        state["consecutive_losses"] = 0
        state["last_trade_day"] = today
        save_state(state)


def get_account_equity() -> float:
    if ENABLE_ALPACA and GLOBAL_STATE and GLOBAL_STATE.get("alpaca_enabled", False) and alpaca_ready():
        acct = alpaca_get_account()
        if acct:
            equity = safe_float(acct.get("equity", LIVE_ACCOUNT_EQUITY_FALLBACK), LIVE_ACCOUNT_EQUITY_FALLBACK)
            return max(equity, 1.0)
    return max(PAPER_ACCOUNT_EQUITY, 1.0)


def get_options_buying_power() -> float:
    if ENABLE_ALPACA and GLOBAL_STATE and GLOBAL_STATE.get("alpaca_enabled", False) and alpaca_ready() and USE_ALPACA_OPTIONS_BUYING_POWER:
        acct = alpaca_get_account()
        if acct:
            obp = safe_float(acct.get("options_buying_power", 0), 0)
            if obp > 0:
                return obp
            buying_power = safe_float(acct.get("buying_power", 0), 0)
            return max(buying_power, 0)
    return get_account_equity()


def estimate_unit_risk(signal: Dict[str, Any]) -> float:
    entry = safe_float(signal.get("entry_contract", 0), 0)
    stop = safe_float(signal.get("stop_contract", 0), 0)
    if entry <= 0 or stop <= 0:
        return 0.0
    return max(entry - stop, 0.0)


def estimate_trade_risk_dollars(signal: Dict[str, Any]) -> float:
    qty = max(1, safe_int(signal.get("qty", 1), 1))
    unit_risk = estimate_unit_risk(signal)
    return qty * unit_risk * 100.0


def estimate_trade_notional_dollars(signal: Dict[str, Any]) -> float:
    qty = max(1, safe_int(signal.get("qty", 1), 1))
    entry = safe_float(signal.get("entry_contract", 0), 0)
    return qty * entry * 100.0


def estimate_open_position_risk_dollars(position: Dict[str, Any]) -> float:
    qty_open = max(0, safe_int(position.get("qty_open", 0), 0))
    entry = safe_float(position.get("entry_price", 0), 0)
    stop = safe_float(position.get("stop_price", 0), 0)
    if qty_open <= 0 or entry <= 0 or stop <= 0:
        return 0.0
    unit_risk = max(entry - stop, 0.0)
    return qty_open * unit_risk * 100.0


def portfolio_heat_pct() -> float:
    equity = get_account_equity()
    if equity <= 0:
        return 0.0
    total_open_risk = 0.0
    for p in GLOBAL_POSITIONS.get("open_positions", []):
        total_open_risk += estimate_open_position_risk_dollars(p)
    return total_open_risk / equity


def is_correlated_ticker(ticker: str) -> bool:
    return str(ticker).upper().strip() in CORRELATED_TICKERS


# =========================================================
# DISCORD
# =========================================================
def send_to_discord(webhook_url: str, message: str, label: str = "UNKNOWN") -> bool:
    if not ENABLE_DISCORD:
        debug(f"Discord disabled, skipped {label}")
        return False
    if not webhook_url:
        log(f"❌ Missing Discord webhook for {label}")
        return False
    try:
        payload = {"content": message[:2000]}
        r = requests.post(webhook_url, json=payload, timeout=15)
        if 200 <= r.status_code < 300:
            log(f"✅ Discord sent -> {label}")
            return True
        log(f"❌ Discord failed -> {label} | {r.status_code} | {r.text}")
        return False
    except Exception as e:
        log(f"❌ Discord exception -> {label}: {e}")
        return False


# =========================================================
# TELEGRAM
# =========================================================
def telegram_api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"


def send_to_telegram(message: str) -> bool:
    if not ENABLE_TELEGRAM_ALERTS:
        debug("Telegram alerts disabled")
        return False
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        debug("Telegram token/chat id missing")
        return False
    try:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message[:4096],
            "disable_web_page_preview": True,
        }
        r = requests.post(telegram_api_url("sendMessage"), data=payload, timeout=15)
        if 200 <= r.status_code < 300:
            log("✅ Telegram sent")
            return True
        log(f"❌ Telegram failed | {r.status_code} | {r.text}")
        return False
    except Exception as e:
        log(f"❌ Telegram exception: {e}")
        return False


def get_telegram_updates(offset: Optional[int] = None) -> List[Dict[str, Any]]:
    if not TELEGRAM_BOT_TOKEN:
        return []
    try:
        params = {"timeout": 1}
        if offset is not None:
            params["offset"] = offset
        r = requests.get(telegram_api_url("getUpdates"), params=params, timeout=20)
        if r.status_code != 200:
            debug(f"Telegram getUpdates failed: {r.status_code} {r.text}")
            return []
        data = r.json()
        if not data.get("ok"):
            debug(f"Telegram getUpdates not ok: {data}")
            return []
        return data.get("result", [])
    except Exception as e:
        log(f"❌ Telegram updates exception: {e}")
        return []


# =========================================================
# ALPACA HELPERS
# =========================================================
def alpaca_ready() -> bool:
    return bool(ALPACA_API_KEY and ALPACA_SECRET_KEY and ALPACA_BASE_URL)


def alpaca_headers() -> Dict[str, str]:
    return {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
        "Content-Type": "application/json",
    }


def alpaca_get(path: str, params: Optional[Dict[str, Any]] = None):
    url = f"{ALPACA_BASE_URL}{path}"
    return requests.get(url, headers=alpaca_headers(), params=params or {}, timeout=ALPACA_ORDER_TIMEOUT)


def alpaca_post(path: str, payload: Dict[str, Any]):
    url = f"{ALPACA_BASE_URL}{path}"
    return requests.post(url, headers=alpaca_headers(), json=payload, timeout=ALPACA_ORDER_TIMEOUT)


def alpaca_delete(path: str):
    url = f"{ALPACA_BASE_URL}{path}"
    return requests.delete(url, headers=alpaca_headers(), timeout=ALPACA_ORDER_TIMEOUT)


def alpaca_get_account() -> Optional[Dict[str, Any]]:
    if not alpaca_ready():
        return None
    try:
        r = alpaca_get("/v2/account")
        if r.status_code == 200:
            return r.json()
        log(f"❌ Alpaca account check failed | {r.status_code} | {r.text}")
        return None
    except Exception as e:
        log(f"❌ Alpaca account exception: {e}")
        return None


def alpaca_list_positions() -> List[Dict[str, Any]]:
    if not alpaca_ready():
        return []
    try:
        r = alpaca_get("/v2/positions")
        if r.status_code == 200:
            data = r.json()
            return data if isinstance(data, list) else []
        log(f"❌ Alpaca positions failed | {r.status_code} | {r.text}")
        return []
    except Exception as e:
        log(f"❌ Alpaca positions exception: {e}")
        return []


def alpaca_get_open_position(symbol: str) -> Optional[Dict[str, Any]]:
    if not alpaca_ready() or not symbol:
        return None
    try:
        r = alpaca_get(f"/v2/positions/{symbol}")
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None


def alpaca_submit_order(symbol: str, qty: int, side: str, order_type: str = "market", tif: str = "day", limit_price: Optional[float] = None, client_order_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not alpaca_ready():
        log("❌ Alpaca not configured")
        return None
    payload = {"symbol": symbol, "qty": str(int(qty)), "side": side, "type": order_type, "time_in_force": tif}
    if client_order_id:
        payload["client_order_id"] = client_order_id
    if order_type == "limit" and limit_price is not None:
        payload["limit_price"] = str(limit_price)
    try:
        r = alpaca_post("/v2/orders", payload)
        if r.status_code in (200, 201):
            data = r.json()
            log(f"✅ Alpaca order submitted | {side} {qty} {symbol}")
            return data
        log(f"❌ Alpaca submit failed | {r.status_code} | {r.text}")
        return None
    except Exception as e:
        log(f"❌ Alpaca submit exception: {e}")
        return None


def alpaca_close_position_market(symbol: str, qty: Optional[int] = None) -> Optional[Dict[str, Any]]:
    position = alpaca_get_open_position(symbol)
    if not position:
        log(f"❌ No Alpaca open position found for {symbol}")
        return None
    try:
        open_qty = int(float(position.get("qty", "0")))
    except Exception:
        open_qty = 0
    if open_qty <= 0:
        log(f"❌ Position qty invalid for {symbol}")
        return None
    sell_qty = open_qty if qty is None else min(open_qty, int(qty))
    return alpaca_submit_order(symbol=symbol, qty=sell_qty, side="sell", order_type="market", tif="day", client_order_id=f"ub-close-{symbol}-{epoch()}")


# =========================================================
# POSITION SIZER
# =========================================================
def confidence_size_multiplier(confidence: str) -> float:
    c = str(confidence).upper().strip()
    if c == "A+":
        return CONFIDENCE_MULT_A_PLUS
    if c == "A":
        return CONFIDENCE_MULT_A
    if c == "B":
        return CONFIDENCE_MULT_B
    return CONFIDENCE_MULT_C


def size_signal_by_stop(signal: Dict[str, Any]) -> Dict[str, Any]:
    entry = safe_float(signal.get("entry_contract", 0), 0)
    stop = safe_float(signal.get("stop_contract", 0), 0)
    unit_risk = max(entry - stop, 0.0)
    if entry <= 0 or stop <= 0 or unit_risk <= 0:
        return {"approved": False, "reject_reasons": ["invalid_entry_or_stop_for_sizing"], "risk_dollars": 0.0, "unit_risk": unit_risk, "unit_risk_dollars": 0.0, "raw_size": 0, "final_size": 0, "adjustments": []}
    equity = get_account_equity()
    confidence_mult = confidence_size_multiplier(signal.get("confidence", "C"))
    base_risk_dollars = equity * MAX_RISK_PER_TRADE_PCT
    adjusted_risk_dollars = base_risk_dollars * confidence_mult
    unit_risk_dollars = unit_risk * 100.0
    raw_size = math.floor(adjusted_risk_dollars / unit_risk_dollars) if unit_risk_dollars > 0 else 0
    adjustments = []
    final_size = raw_size
    if final_size > MAX_POSITION_QTY:
        final_size = MAX_POSITION_QTY
        adjustments.append("capped_by_max_position_qty")
    signal_qty_hint = safe_int(signal.get("qty", 0), 0)
    if USE_SIGNAL_QTY_AS_MAX and signal_qty_hint > 0 and final_size > signal_qty_hint:
        final_size = signal_qty_hint
        adjustments.append("capped_by_signal_qty_hint")
    options_bp = get_options_buying_power()
    est_notional = final_size * entry * 100.0
    if options_bp > 0 and est_notional > options_bp:
        bp_cap_qty = math.floor(options_bp / max(entry * 100.0, 1.0))
        final_size = max(0, min(final_size, bp_cap_qty))
        adjustments.append("capped_by_options_buying_power")
    if final_size < MIN_POSITION_QTY:
        final_size = 0
        adjustments.append("below_min_position_qty")
    return {
        "approved": final_size >= MIN_POSITION_QTY,
        "reject_reasons": [] if final_size >= MIN_POSITION_QTY else ["sized_qty_below_minimum"],
        "risk_dollars": round(adjusted_risk_dollars, 2),
        "unit_risk": round(unit_risk, 4),
        "unit_risk_dollars": round(unit_risk_dollars, 2),
        "raw_size": int(raw_size),
        "final_size": int(final_size),
        "confidence_multiplier": confidence_mult,
        "adjustments": adjustments,
    }


def apply_size_decision_to_signal(signal: Dict[str, Any], size_decision: Dict[str, Any]) -> Dict[str, Any]:
    sized_signal = deepcopy(signal)
    sized_signal["qty"] = int(size_decision["final_size"])
    sized_signal["size_decision"] = size_decision
    return sized_signal


# =========================================================
# PRE-TRADE VALIDATOR
# =========================================================
def validate_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    reasons = []
    required_fields = ["ticker", "symbol", "direction", "confidence", "entry_contract", "stop_contract", "tp1_contract", "timestamp"]
    for field in required_fields:
        value = signal.get(field)
        if value is None or value == "":
            reasons.append(f"missing_{field}")

    entry = safe_float(signal.get("entry_contract", 0), 0)
    stop = safe_float(signal.get("stop_contract", 0), 0)
    tp1 = safe_float(signal.get("tp1_contract", 0), 0)
    tp2 = safe_float(signal.get("tp2_contract", 0), 0)

    if entry <= 0:
        reasons.append("invalid_entry_contract")
    if stop <= 0:
        reasons.append("invalid_stop_contract")
    if entry > 0 and stop > 0 and stop >= entry:
        reasons.append("stop_not_below_entry")
    if not is_signal_fresh(signal):
        reasons.append("stale_signal")

    unit_risk = max(entry - stop, 0.0)
    if unit_risk <= 0:
        reasons.append("invalid_unit_risk")

    rr_candidates = []
    if tp1 > entry and unit_risk > 0:
        rr_candidates.append((tp1 - entry) / unit_risk)
    if tp2 > entry and unit_risk > 0:
        rr_candidates.append((tp2 - entry) / unit_risk)

    best_rr = max(rr_candidates) if rr_candidates else 0.0
    if best_rr < MIN_RR_RATIO:
        reasons.append("reward_to_risk_too_low")

    if REQUIRE_OPTION_SYMBOL and signal.get("asset_class") == "option":
        if signal.get("symbol") == signal.get("ticker"):
            reasons.append("missing_full_option_symbol")

    if REJECT_DUPLICATE_OPEN_SYMBOL:
        open_symbols = {p.get("symbol") for p in GLOBAL_POSITIONS.get("open_positions", [])}
        if signal.get("symbol") in open_symbols:
            reasons.append("duplicate_open_symbol")

    if is_now_in_no_trade_window():
        reasons.append("inside_no_trade_window")

    approved = len(reasons) == 0
    return {"approved": approved, "stage": "pretrade_validator", "reject_reasons": reasons, "reward_to_risk": round(best_rr, 4), "unit_risk": round(unit_risk, 4)}


# =========================================================
# RISK POLICY MANAGER
# =========================================================
def evaluate_risk_policy(signal: Dict[str, Any]) -> Dict[str, Any]:
    reasons = []
    reset_daily_risk_counters_if_needed(GLOBAL_STATE)

    if GLOBAL_STATE.get("kill_switch", False):
        reasons.append("kill_switch_active")
    if GLOBAL_STATE.get("bot_paused", False):
        reasons.append("bot_paused")
    if not GLOBAL_STATE.get("engine_enabled", True):
        reasons.append("engine_disabled")

    open_positions = GLOBAL_POSITIONS.get("open_positions", [])
    open_count = len(open_positions)
    if open_count >= MAX_OPEN_POSITIONS:
        reasons.append("max_open_positions_hit")

    ticker = str(signal.get("ticker", "")).upper().strip()
    same_ticker_count = sum(1 for p in open_positions if str(p.get("ticker", "")).upper().strip() == ticker)
    if same_ticker_count >= MAX_SAME_TICKER_POSITIONS:
        reasons.append("max_same_ticker_positions_hit")

    trade_risk_dollars = estimate_trade_risk_dollars(signal)
    equity = get_account_equity()
    risk_per_trade_pct = trade_risk_dollars / equity if equity > 0 else 0.0
    if risk_per_trade_pct > MAX_RISK_PER_TRADE_PCT:
        reasons.append("risk_per_trade_limit_hit")

    current_daily_loss_pct = abs(min(safe_float(GLOBAL_STATE.get("daily_realized_pnl_pct", 0.0), 0.0), 0.0))
    if current_daily_loss_pct >= MAX_DAILY_LOSS_PCT:
        reasons.append("max_daily_loss_hit")

    current_heat = portfolio_heat_pct()
    projected_heat = current_heat + risk_per_trade_pct
    if current_heat >= MAX_PORTFOLIO_HEAT_PCT:
        reasons.append("portfolio_heat_limit_hit")
    if projected_heat > MAX_PORTFOLIO_HEAT_PCT:
        reasons.append("projected_heat_limit_hit")

    consecutive_losses = safe_int(GLOBAL_STATE.get("consecutive_losses", 0), 0)
    if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
        reasons.append("max_consecutive_losses_hit")

    notional = estimate_trade_notional_dollars(signal)
    options_bp = get_options_buying_power()
    if options_bp > 0 and notional > options_bp:
        reasons.append("insufficient_options_buying_power")

    approved = len(reasons) == 0
    return {
        "approved": approved,
        "stage": "risk_policy",
        "reject_reasons": reasons,
        "risk_per_trade_pct": round(risk_per_trade_pct, 6),
        "portfolio_heat_pct": round(current_heat, 6),
        "projected_heat_pct": round(projected_heat, 6),
        "daily_realized_pnl_pct": round(safe_float(GLOBAL_STATE.get("daily_realized_pnl_pct", 0.0), 0.0), 6),
        "consecutive_losses": consecutive_losses,
        "trade_risk_dollars": round(trade_risk_dollars, 2),
        "options_buying_power": round(options_bp, 2),
        "notional_dollars": round(notional, 2),
        "same_ticker_count": same_ticker_count,
        "open_positions": open_count,
    }


# =========================================================
# PORTFOLIO RISK MANAGER
# =========================================================
def evaluate_portfolio_risk(signal: Dict[str, Any]) -> Dict[str, Any]:
    reasons = []
    open_positions = GLOBAL_POSITIONS.get("open_positions", [])
    new_ticker = str(signal.get("ticker", "")).upper().strip()
    new_symbol = str(signal.get("symbol", "")).strip()
    new_direction = str(signal.get("direction", "")).upper().strip()

    equity = get_account_equity()
    proposed_trade_risk = estimate_trade_risk_dollars(signal)
    proposed_trade_risk_pct = proposed_trade_risk / equity if equity > 0 else 0.0

    current_heat = portfolio_heat_pct()
    projected_heat = current_heat + proposed_trade_risk_pct
    if projected_heat > MAX_PROJECTED_PORTFOLIO_HEAT_PCT:
        reasons.append("projected_portfolio_heat_limit_hit")

    symbol_count = sum(1 for p in open_positions if p.get("symbol") == new_symbol)
    if symbol_count >= MAX_SYMBOL_PORTFOLIO_COUNT:
        reasons.append("symbol_portfolio_count_limit_hit")

    same_direction_index_count = sum(1 for p in open_positions if str(p.get("direction", "")).upper().strip() == new_direction and is_correlated_ticker(p.get("ticker", "")))
    if is_correlated_ticker(new_ticker) and same_direction_index_count >= MAX_DIRECTIONAL_INDEX_COUNT:
        reasons.append("directional_index_exposure_limit_hit")

    correlated_theme_count = sum(1 for p in open_positions if is_correlated_ticker(p.get("ticker", "")))
    if is_correlated_ticker(new_ticker) and correlated_theme_count >= MAX_CORRELATED_THEME_COUNT:
        reasons.append("correlated_theme_exposure_limit_hit")

    approved = len(reasons) == 0
    return {
        "approved": approved,
        "stage": "portfolio_risk",
        "reject_reasons": reasons,
        "portfolio_heat_pct": round(current_heat, 6),
        "projected_heat_pct": round(projected_heat, 6),
        "max_projected_heat_pct": MAX_PROJECTED_PORTFOLIO_HEAT_PCT,
        "symbol_portfolio_count": symbol_count,
        "same_direction_index_count": same_direction_index_count,
        "correlated_theme_count": correlated_theme_count,
    }


# =========================================================
# REGIME ENGINE
# =========================================================
def infer_regime_from_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    explicit_regime = str(signal.get("regime") or signal.get("market_regime") or signal.get("regime_hint") or "").upper().strip()

    text_blob = " ".join([
        str(signal.get("reason", "")),
        str(signal.get("public_reason", "")),
        str(signal.get("trigger", "")),
        str(signal.get("bias", "")),
        str(signal.get("entry", "")),
    ]).lower()

    tags = []
    if explicit_regime:
        regime = explicit_regime
        score = 0.90
        tags.append("explicit_regime")
    else:
        regime = "NORMAL"
        score = 0.55
        if any(k in text_blob for k in ["compression", "expansion", "squeeze", "breakout expansion"]):
            regime = "EXPANSION"
            score = 0.85
            tags.append("compression_expansion_language")
        if any(k in text_blob for k in ["trend", "trend day", "vwap reclaim", "higher low", "lower high", "break and hold", "retest hold"]):
            regime = "TREND"
            score = max(score, 0.80)
            tags.append("trend_language")
        if any(k in text_blob for k in ["chop", "range", "whipsaw", "inside range", "mean reversion chop"]):
            regime = "CHOP"
            score = 0.25
            tags.append("chop_language")
        if any(k in text_blob for k in ["cpi", "fomc", "powell", "fed", "event", "nfp", "earnings", "geopolitics", "news spike"]):
            regime = "EVENT"
            score = 0.40
            tags.append("event_language")

    regime = regime.upper().strip()
    if regime not in {"TREND", "EXPANSION", "NORMAL", "CHOP", "EVENT"}:
        regime = "NORMAL"

    return {"regime": regime, "regime_score": round(score, 4), "tags": tags}


def evaluate_regime(signal: Dict[str, Any]) -> Dict[str, Any]:
    if not ENABLE_REGIME_ENGINE:
        inferred = infer_regime_from_signal(signal)
        return {"approved": True, "stage": "regime_engine", "regime": inferred["regime"], "regime_score": inferred["regime_score"], "reject_reasons": [], "tags": inferred["tags"]}

    inferred = infer_regime_from_signal(signal)
    regime = inferred["regime"]
    regime_score = inferred["regime_score"]
    tags = inferred["tags"]
    reasons = []

    if regime_score < MIN_REGIME_SCORE:
        reasons.append("regime_score_too_low")
    if regime == "CHOP" and BLOCK_CHOP_REGIME:
        reasons.append("chop_regime_blocked")
    if regime == "EVENT" and not ALLOW_EVENT_REGIME:
        reasons.append("event_regime_blocked")
    if regime not in ALLOWED_REGIMES:
        reasons.append("regime_not_allowed")

    approved = len(reasons) == 0
    return {
        "approved": approved,
        "stage": "regime_engine",
        "regime": regime,
        "regime_score": regime_score,
        "reject_reasons": reasons,
        "tags": tags,
    }


def apply_regime_to_signal(signal: Dict[str, Any], regime_decision: Dict[str, Any]) -> Dict[str, Any]:
    enriched = deepcopy(signal)
    enriched["regime"] = regime_decision["regime"]
    enriched["regime_score"] = regime_decision["regime_score"]
    enriched["regime_tags"] = regime_decision.get("tags", [])
    return enriched


# =========================================================
# SIGNAL NORMALIZATION
# =========================================================
def normalize_confidence(conf) -> str:
    if conf is None:
        return "C"
    s = str(conf).upper().strip()
    if s in {"A+", "A", "B", "C"}:
        return s
    if "A" in s:
        return "A"
    if "B" in s:
        return "B"
    return "C"


def normalize_direction(direction: Any) -> str:
    if direction is None:
        return "CALL"
    s = str(direction).upper().strip()
    if s in {"CALL", "PUT"}:
        return s
    if s in {"C", "LONGCALL"}:
        return "CALL"
    if s in {"P", "LONGPUT"}:
        return "PUT"
    return "CALL"


def normalize_signal(raw: Dict[str, Any]) -> Dict[str, Any]:
    signal = dict(raw)
    signal["ticker"] = str(signal.get("ticker", "SPY")).upper().strip()
    signal["direction"] = normalize_direction(signal.get("direction", "CALL"))
    signal["confidence"] = normalize_confidence(signal.get("confidence", "C"))

    signal["price"] = safe_float(signal.get("price", 0))
    signal["contract_price"] = safe_float(signal.get("contract_price", signal.get("option_price", 0)))
    signal["entry_contract"] = safe_float(signal.get("entry_contract", signal["contract_price"]))
    signal["stop_contract"] = safe_float(signal.get("stop_contract", 0))
    signal["tp1_contract"] = safe_float(signal.get("tp1_contract", 0))
    signal["tp2_contract"] = safe_float(signal.get("tp2_contract", 0))
    signal["trail_pct"] = safe_float(signal.get("trail_pct", DEFAULT_TRAIL_PCT))

    signal["entry"] = str(signal.get("entry", "Watch confirmation"))
    signal["stop"] = str(signal.get("stop", "Risk-defined"))
    signal["target_1"] = str(signal.get("target_1", "Scale at first push"))
    signal["target_2"] = str(signal.get("target_2", "Runner target"))
    signal["reason"] = str(signal.get("reason", "No reason provided."))
    signal["public_reason"] = str(signal.get("public_reason", signal["reason"]))
    signal["trigger"] = str(signal.get("trigger", "No trigger provided."))
    signal["bias"] = str(signal.get("bias", "Neutral"))
    signal["timeframe"] = str(signal.get("timeframe", "5m / 15m"))
    signal["timestamp"] = safe_int(signal.get("timestamp", epoch()), epoch())
    signal["source"] = str(signal.get("source", "signal_file"))

    signal["qty"] = safe_int(signal.get("qty", DEFAULT_LIVE_QTY), DEFAULT_LIVE_QTY)
    signal["qty_hint"] = safe_int(signal.get("qty_hint", signal["qty"]), signal["qty"])
    signal["use_limit_entry"] = bool(signal.get("use_limit_entry", False))
    signal["limit_entry_price"] = safe_float(signal.get("limit_entry_price", signal["entry_contract"]))
    signal["asset_class"] = str(signal.get("asset_class", "option")).lower().strip()

    signal["symbol"] = str(signal.get("symbol", signal.get("contract_symbol", signal["ticker"]))).strip()
    signal["signal_id"] = str(signal.get("signal_id", signal_hash(signal)))
    return signal


def is_signal_fresh(signal: Dict[str, Any]) -> bool:
    ts = safe_int(signal.get("timestamp", 0), 0)
    if ts <= 0:
        return True
    return (epoch() - ts) <= MAX_SIGNAL_AGE_SECONDS


def load_live_signal() -> Optional[Dict[str, Any]]:
    debug_file_lookup(SIGNAL_FILE)
    if not SIGNAL_FILE:
        log("❌ SIGNAL_FILE env var is empty")
        return None
    if not file_exists(SIGNAL_FILE):
        log(f"❌ SIGNAL_FILE not found: {SIGNAL_FILE}")
        log(f"❌ Absolute path checked: {os.path.abspath(SIGNAL_FILE)}")
        return None
    try:
        with open(SIGNAL_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        log(f"✅ Loaded signal from {SIGNAL_FILE}")
        if not isinstance(raw, dict):
            log("❌ signal file is not a JSON object")
            return None
        signal = normalize_signal(raw)
        if not is_signal_fresh(signal):
            log("❌ Signal skipped: stale timestamp")
            return None
        return signal
    except Exception as e:
        log(f"❌ Failed loading signal file: {e}")
        return None


def signal_file_changed(state: Dict[str, Any]) -> bool:
    if not SIGNAL_FILE or not file_exists(SIGNAL_FILE):
        return False
    try:
        mtime = int(os.path.getmtime(SIGNAL_FILE))
        if mtime > safe_int(state.get("last_signal_file_mtime", 0), 0):
            state["last_signal_file_mtime"] = mtime
            save_state(state)
            return True
        return False
    except Exception as e:
        log(f"❌ Signal file watcher error: {e}")
        return False


# =========================================================
# ROUTING MESSAGES
# =========================================================
def build_risk_block_message(signal: Dict[str, Any], risk_decision: Dict[str, Any]) -> str:
    reasons = ", ".join(risk_decision.get("reject_reasons", [])) or "unknown"
    return (
        f"🚫 SIGNAL BLOCKED\nTicker: {signal['ticker']}\nSymbol: {signal['symbol']}\nReasons: {reasons}\n"
        f"Risk/Trade %: {round(risk_decision.get('risk_per_trade_pct', 0.0) * 100, 3)}\n"
        f"Portfolio Heat %: {round(risk_decision.get('portfolio_heat_pct', 0.0) * 100, 3)}\n"
        f"Projected Heat %: {round(risk_decision.get('projected_heat_pct', 0.0) * 100, 3)}\n"
        f"Options BP: {risk_decision.get('options_buying_power', 0.0)}\n"
        f"Notional: {risk_decision.get('notional_dollars', 0.0)}\n⏰ {now_ts()}"
    )


def build_size_block_message(signal: Dict[str, Any], size_decision: Dict[str, Any]) -> str:
    reasons = ", ".join(size_decision.get("reject_reasons", [])) or "unknown"
    adjustments = ", ".join(size_decision.get("adjustments", [])) or "none"
    return (
        f"🚫 SIZING BLOCKED SIGNAL\nTicker: {signal['ticker']}\nSymbol: {signal['symbol']}\nReasons: {reasons}\n"
        f"Risk Dollars: {size_decision.get('risk_dollars', 0.0)}\nUnit Risk: {size_decision.get('unit_risk', 0.0)}\n"
        f"Raw Size: {size_decision.get('raw_size', 0)}\nFinal Size: {size_decision.get('final_size', 0)}\n"
        f"Adjustments: {adjustments}\n⏰ {now_ts()}"
    )


def build_validation_block_message(signal: Dict[str, Any], validation_decision: Dict[str, Any]) -> str:
    reasons = ", ".join(validation_decision.get("reject_reasons", [])) or "unknown"
    return (
        f"🚫 VALIDATION BLOCKED SIGNAL\nTicker: {signal.get('ticker', 'N/A')}\nSymbol: {signal.get('symbol', 'N/A')}\n"
        f"Reasons: {reasons}\nReward/Risk: {validation_decision.get('reward_to_risk', 0.0)}\n"
        f"Unit Risk: {validation_decision.get('unit_risk', 0.0)}\n⏰ {now_ts()}"
    )


def build_portfolio_block_message(signal: Dict[str, Any], portfolio_decision: Dict[str, Any]) -> str:
    reasons = ", ".join(portfolio_decision.get("reject_reasons", [])) or "unknown"
    return (
        f"🚫 PORTFOLIO RISK BLOCKED SIGNAL\nTicker: {signal['ticker']}\nSymbol: {signal['symbol']}\nReasons: {reasons}\n"
        f"Current Heat %: {round(portfolio_decision.get('portfolio_heat_pct', 0.0) * 100, 3)}\n"
        f"Projected Heat %: {round(portfolio_decision.get('projected_heat_pct', 0.0) * 100, 3)}\n"
        f"Symbol Count: {portfolio_decision.get('symbol_portfolio_count', 0)}\n"
        f"Directional Index Count: {portfolio_decision.get('same_direction_index_count', 0)}\n"
        f"Correlated Theme Count: {portfolio_decision.get('correlated_theme_count', 0)}\n⏰ {now_ts()}"
    )


def build_regime_block_message(signal: Dict[str, Any], regime_decision: Dict[str, Any]) -> str:
    reasons = ", ".join(regime_decision.get("reject_reasons", [])) or "unknown"
    tags = ", ".join(regime_decision.get("tags", [])) or "none"
    return (
        f"🚫 REGIME BLOCKED SIGNAL\nTicker: {signal['ticker']}\nSymbol: {signal['symbol']}\n"
        f"Regime: {regime_decision.get('regime', 'N/A')}\nRegime Score: {regime_decision.get('regime_score', 0.0)}\n"
        f"Reasons: {reasons}\nTags: {tags}\n⏰ {now_ts()}"
    )


def build_ai_reasoning_message(signal: Dict[str, Any]) -> str:
    size_text = ""
    size_decision = signal.get("size_decision")
    if isinstance(size_decision, dict):
        size_text = f"\nSized Qty: {signal.get('qty', 'N/A')}\nRisk Dollars: {size_decision.get('risk_dollars', 'N/A')}\nUnit Risk: {size_decision.get('unit_risk', 'N/A')}"
    regime_text = ""
    if signal.get("regime"):
        regime_text = f"\nRegime: {signal.get('regime')}\nRegime Score: {signal.get('regime_score', 'N/A')}"
    return (
        f"🧠 AI REASONING ALERT\nTicker: {signal['ticker']}\nSymbol: {signal['symbol']}\nDirection: {signal['direction']}\n"
        f"Underlying Price: {signal['price']}\nContract Price: {signal['contract_price']}\nConfidence: {signal['confidence']}\n"
        f"Bias: {signal['bias']}\nTimeframe: {signal['timeframe']}\nTrigger: {signal['trigger']}\nSource: {signal['source']}"
        f"{regime_text}{size_text}\n\nReasoning:\n{signal['reason']}\n\n⏰ {now_ts()}"
    )


def build_free_message(signal: Dict[str, Any]) -> str:
    return (
        f"📊 FREE DAILY ALERT\nTicker: {signal['ticker']}\nDirection: {signal['direction']}\nUnderlying Price: {signal['price']}\n"
        f"Confidence: {signal['confidence']}\n\nSetup:\n{signal['public_reason']}\n\n⏰ {now_ts()}"
    )


def build_premium_message(signal: Dict[str, Any]) -> str:
    title = "💎 PREMIUM A SETUP" if signal["confidence"] in {"A", "A+"} else "⚠️ PREMIUM WATCH ALERT"
    size_line = f"Qty: {signal.get('qty', 'N/A')}\n"
    regime_line = f"Regime: {signal.get('regime')} ({signal.get('regime_score', 'N/A')})\n" if signal.get("regime") else ""
    return (
        f"{title}\nTicker: {signal['ticker']}\nSymbol: {signal['symbol']}\nDirection: {signal['direction']}\n"
        f"Underlying Price: {signal['price']}\nContract Entry: {signal['entry_contract']}\n{size_line}{regime_line}"
        f"Confidence: {signal['confidence']}\nEntry: {signal['entry']}\nStop: {signal['stop']}\n"
        f"Target 1: {signal['target_1']}\nTarget 2: {signal['target_2']}\n\nReason:\n{signal['reason']}\n\n⏰ {now_ts()}"
    )


def build_telegram_signal_message(signal: Dict[str, Any]) -> str:
    regime_line = f"Regime: {signal.get('regime')}\n" if signal.get("regime") else ""
    return (
        f"🚨 UB SIGNAL\n{signal['ticker']} | {signal['direction']} | {signal['confidence']}\nTradable Symbol: {signal['symbol']}\n"
        f"Underlying: {signal['price']}\nContract: {signal['entry_contract']}\nQty: {signal.get('qty', 'N/A')}\n"
        f"{regime_line}Trigger: {signal['trigger']}\nReason: {signal['public_reason']}\n⏰ {now_ts()}"
    )


def build_live_order_message(order: Dict[str, Any], side_note: str = "") -> str:
    status = order.get("status", "unknown")
    symbol = order.get("symbol", "N/A")
    qty = order.get("qty", "N/A")
    side = order.get("side", "N/A")
    oid = order.get("id", "N/A")
    line2 = f"\nNote: {side_note}" if side_note else ""
    return f"🟣 ALPACA ORDER\nOrder ID: {oid}\nSymbol: {symbol}\nSide: {side}\nQty: {qty}\nStatus: {status}{line2}\n⏰ {now_ts()}"


def build_position_open_message(position: Dict[str, Any]) -> str:
    return (
        f"🟢 POSITION OPENED\nID: {position['id']}\nMode: {position['mode']}\nTicker: {position['ticker']}\n"
        f"Symbol: {position['symbol']}\nDirection: {position['direction']}\nQty: {position['qty_open']}\n"
        f"Entry: {position['entry_price']}\nStop: {position['stop_price']}\nTP1: {position['tp1_price']}\n"
        f"TP2: {position['tp2_price']}\nTrail %: {position['trail_pct']}\n⏰ {now_ts()}"
    )


def build_position_update_message(position: Dict[str, Any], note: str) -> str:
    return (
        f"📈 POSITION UPDATE\nID: {position['id']}\nMode: {position['mode']}\n{position['ticker']} {position['direction']}\n"
        f"Symbol: {position['symbol']}\nLive: {position['last_price']}\nPnL %: {round(position['pnl_pct'], 2)}\n"
        f"Remaining Qty: {position['qty_open']}\nNote: {note}\n⏰ {now_ts()}"
    )


def build_position_close_message(position: Dict[str, Any], note: str) -> str:
    return (
        f"🔴 POSITION CLOSED\nID: {position['id']}\nMode: {position['mode']}\n{position['ticker']} {position['direction']}\n"
        f"Symbol: {position['symbol']}\nExit: {position['exit_price']}\nRealized PnL %: {round(position['realized_pnl_pct'], 2)}\n"
        f"Reason: {note}\n⏰ {now_ts()}"
    )


# =========================================================
# ROUTING
# =========================================================
def route_signal(signal: Dict[str, Any], state: Dict[str, Any]):
    ai_msg = build_ai_reasoning_message(signal)
    free_msg = build_free_message(signal)
    premium_msg = build_premium_message(signal)
    tg_msg = build_telegram_signal_message(signal)
    if state.get("discord_enabled", True):
        send_to_discord(DISCORD_AI_WEBHOOK, ai_msg, "AI")
        send_to_discord(DISCORD_FREE_WEBHOOK, free_msg, "FREE")
        send_to_discord(DISCORD_PREMIUM_WEBHOOK, premium_msg, "PREMIUM")
    if state.get("telegram_enabled", True):
        send_to_telegram(tg_msg)


# =========================================================
# POSITION STORE
# =========================================================
def next_position_id(positions: Dict[str, Any]) -> int:
    positions["last_position_id"] = safe_int(positions.get("last_position_id", 0), 0) + 1
    return positions["last_position_id"]


def make_local_position(signal: Dict[str, Any], mode: str, broker_order: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    entry = safe_float(signal.get("entry_contract", 0), 0)
    if entry <= 0:
        entry = safe_float(signal.get("contract_price", 0), 0)
    qty = safe_int(signal.get("qty", DEFAULT_LIVE_QTY), DEFAULT_LIVE_QTY)
    qty = max(1, qty)
    stop_price = safe_float(signal.get("stop_contract", 0), 0)
    tp1_price = safe_float(signal.get("tp1_contract", 0), 0)
    tp2_price = safe_float(signal.get("tp2_contract", 0), 0)
    if stop_price <= 0:
        stop_price = round(entry * 0.70, 4)
    if tp1_price <= 0:
        tp1_price = round(entry * 1.30, 4)
    if tp2_price <= 0:
        tp2_price = round(entry * 1.60, 4)
    order_id = broker_order.get("id") if broker_order else ""
    client_order_id = broker_order.get("client_order_id") if broker_order else ""
    return {
        "id": next_position_id(GLOBAL_POSITIONS),
        "signal_id": signal["signal_id"],
        "mode": mode,
        "broker_order_id": order_id,
        "client_order_id": client_order_id,
        "ticker": signal["ticker"],
        "symbol": signal["symbol"],
        "direction": signal["direction"],
        "confidence": signal["confidence"],
        "opened_at": epoch(),
        "status": "OPEN",
        "qty_total": qty,
        "qty_open": qty,
        "qty_closed": 0,
        "entry_price": entry,
        "last_price": entry,
        "stop_price": stop_price,
        "original_stop_price": stop_price,
        "tp1_price": tp1_price,
        "tp2_price": tp2_price,
        "tp1_hit": False,
        "tp2_hit": False,
        "scale1_pct": DEFAULT_SCALE1_PCT,
        "scale2_pct": DEFAULT_SCALE2_PCT,
        "trail_pct": safe_float(signal.get("trail_pct", DEFAULT_TRAIL_PCT), DEFAULT_TRAIL_PCT),
        "highest_price": entry,
        "lowest_price": entry,
        "pnl_pct": 0.0,
        "realized_pnl_pct": 0.0,
        "exit_price": 0.0,
        "closed_at": 0,
        "break_even_after_tp1": DEFAULT_BREAK_EVEN_AFTER_TP1,
        "notes": [],
    }


def save_new_position(position: Dict[str, Any]):
    GLOBAL_POSITIONS["open_positions"].append(position)
    save_positions(GLOBAL_POSITIONS)


def update_position_market_price(position: Dict[str, Any], new_price: float):
    if new_price <= 0:
        return
    position["last_price"] = new_price
    position["highest_price"] = max(position.get("highest_price", new_price), new_price)
    position["lowest_price"] = min(position.get("lowest_price", new_price), new_price)
    position["pnl_pct"] = pct_change(position["entry_price"], new_price)


def scale_out_local(position: Dict[str, Any], qty_to_close: int, fill_price: float, note: str) -> bool:
    qty_to_close = int(max(0, min(qty_to_close, position["qty_open"])))
    if qty_to_close <= 0:
        return False
    position["qty_open"] -= qty_to_close
    position["qty_closed"] += qty_to_close
    position["notes"].append(f"{note} | qty={qty_to_close} @ {fill_price}")
    return True


def finalize_close_position(position: Dict[str, Any], exit_price: float, note: str):
    position["status"] = "CLOSED"
    position["exit_price"] = round(exit_price, 4)
    position["closed_at"] = epoch()
    position["qty_closed"] = position["qty_total"]
    position["qty_open"] = 0
    position["realized_pnl_pct"] = pct_change(position["entry_price"], position["exit_price"])
    position["notes"].append(note)

    reset_daily_risk_counters_if_needed(GLOBAL_STATE)
    realized_pct_decimal = position["realized_pnl_pct"] / 100.0
    GLOBAL_STATE["daily_realized_pnl_pct"] = safe_float(GLOBAL_STATE.get("daily_realized_pnl_pct", 0.0), 0.0) + realized_pct_decimal
    if position["realized_pnl_pct"] < 0:
        GLOBAL_STATE["consecutive_losses"] = safe_int(GLOBAL_STATE.get("consecutive_losses", 0), 0) + 1
    else:
        GLOBAL_STATE["consecutive_losses"] = 0
    save_state(GLOBAL_STATE)

    GLOBAL_POSITIONS["open_positions"] = [p for p in GLOBAL_POSITIONS["open_positions"] if p["id"] != position["id"]]
    GLOBAL_POSITIONS["closed_positions"].append(position)
    save_positions(GLOBAL_POSITIONS)

    msg = build_position_close_message(position, note)
    send_to_telegram(msg)
    send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")


# =========================================================
# PAPER EXECUTION
# =========================================================
def open_paper_position(signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    position = make_local_position(signal, mode="PAPER")
    save_new_position(position)
    GLOBAL_STATE["paper_trade_count"] = safe_int(GLOBAL_STATE.get("paper_trade_count", 0), 0) + 1
    save_state(GLOBAL_STATE)
    msg = build_position_open_message(position)
    send_to_telegram(msg)
    send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
    return position


# =========================================================
# LIVE ALPACA EXECUTION
# =========================================================
def validate_live_signal_for_alpaca(signal: Dict[str, Any]) -> bool:
    if not GLOBAL_STATE.get("alpaca_enabled", False):
        log("❌ LIVE BLOCKED: alpaca mode disabled")
        return False
    if not ENABLE_ALPACA:
        log("❌ LIVE BLOCKED: ENABLE_ALPACA=false")
        return False
    if not LIVE_MODE and GLOBAL_STATE.get("paper_enabled", True):
        log("❌ LIVE BLOCKED: engine still in paper mode")
        return False
    if signal.get("asset_class") == "option":
        if not ALPACA_ENABLE_OPTIONS:
            log("❌ LIVE BLOCKED: ALPACA_ENABLE_OPTIONS=false")
            return False
        if not ALPACA_LIVE_OPTIONS_APPROVED:
            log("❌ LIVE BLOCKED: ALPACA_LIVE_OPTIONS_APPROVED=false")
            return False
    if REQUIRE_OPTION_SYMBOL and signal.get("asset_class") == "option":
        if signal["symbol"] == signal["ticker"]:
            log("❌ LIVE BLOCKED: option signal missing actual option contract symbol")
            return False
    if signal["qty"] <= 0:
        log("❌ LIVE BLOCKED: qty invalid")
        return False
    notional = estimate_trade_notional_dollars(signal)
    options_bp = get_options_buying_power()
    if options_bp > 0 and notional > options_bp:
        log("❌ LIVE BLOCKED: not enough options buying power")
        return False
    return True


def submit_live_entry(signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not ALLOW_LIVE_BUYS:
        log("❌ LIVE BUY BLOCKED: ALLOW_LIVE_BUYS=false")
        return None
    if not validate_live_signal_for_alpaca(signal):
        return None

    side = "buy"
    qty = signal["qty"]
    symbol = signal["symbol"]
    client_order_id = f"ub-entry-{symbol}-{epoch()}"

    if signal.get("use_limit_entry", False):
        limit_price = safe_float(signal.get("limit_entry_price", 0), 0)
        if limit_price <= 0:
            log("❌ LIVE LIMIT ENTRY BLOCKED: invalid limit price")
            return None
        order = alpaca_submit_order(symbol=symbol, qty=qty, side=side, order_type="limit", tif="day", limit_price=limit_price, client_order_id=client_order_id)
    else:
        order = alpaca_submit_order(symbol=symbol, qty=qty, side=side, order_type="market", tif="day", client_order_id=client_order_id)

    if order:
        GLOBAL_STATE["live_trade_count"] = safe_int(GLOBAL_STATE.get("live_trade_count", 0), 0) + 1
        save_state(GLOBAL_STATE)
        msg = build_live_order_message(order, "LIVE ENTRY SUBMITTED")
        send_to_telegram(msg)
        send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
    return order


def open_live_position(signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    order = submit_live_entry(signal)
    if not order:
        return None
    position = make_local_position(signal, mode="LIVE", broker_order=order)
    save_new_position(position)
    msg = build_position_open_message(position)
    send_to_telegram(msg)
    send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
    return position


def live_scale_out(position: Dict[str, Any], qty_to_close: int, note: str) -> bool:
    if not ALLOW_LIVE_SELLS:
        log("❌ LIVE SELL BLOCKED: ALLOW_LIVE_SELLS=false")
        return False
    qty_to_close = int(max(0, min(qty_to_close, position["qty_open"])))
    if qty_to_close <= 0:
        return False
    order = alpaca_submit_order(symbol=position["symbol"], qty=qty_to_close, side="sell", order_type="market", tif="day", client_order_id=f"ub-scale-{position['symbol']}-{epoch()}")
    if not order:
        return False
    scale_out_local(position, qty_to_close, position["last_price"], note)
    msg = build_live_order_message(order, note)
    send_to_telegram(msg)
    send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
    return True


def live_close_position(position: Dict[str, Any], note: str) -> bool:
    if not ALLOW_LIVE_SELLS:
        log("❌ LIVE SELL BLOCKED: ALLOW_LIVE_SELLS=false")
        return False
    order = alpaca_close_position_market(position["symbol"], qty=position["qty_open"])
    if not order:
        return False
    msg = build_live_order_message(order, note)
    send_to_telegram(msg)
    send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
    finalize_close_position(position, position["last_price"], note)
    return True


# =========================================================
# POSITION MANAGEMENT
# =========================================================
def manage_open_positions(incoming_signal: Optional[Dict[str, Any]] = None):
    if not GLOBAL_POSITIONS["open_positions"]:
        return

    for position in list(GLOBAL_POSITIONS["open_positions"]):
        live_price = safe_float(position.get("last_price", 0), 0)
        if incoming_signal and incoming_signal.get("symbol") == position.get("symbol"):
            incoming_contract = safe_float(incoming_signal.get("contract_price", 0), 0)
            if incoming_contract > 0:
                live_price = incoming_contract
        if live_price <= 0:
            continue

        update_position_market_price(position, live_price)

        if not position["tp1_hit"] and live_price >= position["tp1_price"]:
            qty1 = max(1, math.floor(position["qty_total"] * position["scale1_pct"]))
            qty1 = min(qty1, position["qty_open"])
            if position["mode"] == "LIVE":
                ok = live_scale_out(position, qty1, "TP1 HIT - live scale-out")
                if ok:
                    position["tp1_hit"] = True
                    if position.get("break_even_after_tp1", False):
                        position["stop_price"] = max(position["stop_price"], position["entry_price"])
                    msg = build_position_update_message(position, "TP1 HIT - live scale-out")
                    send_to_telegram(msg)
                    send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
            else:
                ok = scale_out_local(position, qty1, live_price, "TP1 HIT - paper scale-out")
                if ok:
                    position["tp1_hit"] = True
                    if position.get("break_even_after_tp1", False):
                        position["stop_price"] = max(position["stop_price"], position["entry_price"])
                    msg = build_position_update_message(position, "TP1 HIT - paper scale-out")
                    send_to_telegram(msg)
                    send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")

        if not position["tp2_hit"] and live_price >= position["tp2_price"]:
            qty2 = max(1, math.floor(position["qty_total"] * position["scale2_pct"]))
            qty2 = min(qty2, position["qty_open"])
            if position["mode"] == "LIVE":
                ok = live_scale_out(position, qty2, "TP2 HIT - live scale-out")
                if ok:
                    position["tp2_hit"] = True
                    msg = build_position_update_message(position, "TP2 HIT - live scale-out")
                    send_to_telegram(msg)
                    send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
            else:
                ok = scale_out_local(position, qty2, live_price, "TP2 HIT - paper scale-out")
                if ok:
                    position["tp2_hit"] = True
                    msg = build_position_update_message(position, "TP2 HIT - paper scale-out")
                    send_to_telegram(msg)
                    send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")

        entry_price = safe_float(position.get("entry_price", 0), 0)
        highest_price = safe_float(position.get("highest_price", live_price), live_price)
        trail_pct = safe_float(position.get("trail_pct", DEFAULT_TRAIL_PCT), DEFAULT_TRAIL_PCT)

        if highest_price > entry_price and trail_pct > 0:
            profit_open = highest_price - entry_price
            trail_buffer = profit_open * trail_pct
            trailed_stop = highest_price - trail_buffer
            if trailed_stop > position["stop_price"]:
                position["stop_price"] = round(trailed_stop, 4)

        if live_price <= position["stop_price"]:
            if position["mode"] == "LIVE":
                live_close_position(position, "STOP HIT / trailing stop")
            else:
                finalize_close_position(position, live_price, "STOP HIT / trailing stop")
            continue

        if position["qty_open"] <= 0:
            finalize_close_position(position, live_price, "All size scaled out")
            continue

    save_positions(GLOBAL_POSITIONS)


# =========================================================
# ALPACA POSITION SYNC
# =========================================================
def sync_live_positions_from_alpaca():
    if not ALPACA_SYNC_POSITIONS or not ENABLE_ALPACA or not GLOBAL_STATE.get("alpaca_enabled", False):
        return
    broker_positions = alpaca_list_positions()
    if not broker_positions:
        return
    local_live = [p for p in GLOBAL_POSITIONS["open_positions"] if p.get("mode") == "LIVE"]
    local_by_symbol = {p["symbol"]: p for p in local_live}
    for bp in broker_positions:
        symbol = str(bp.get("symbol", "")).strip()
        if not symbol or symbol not in local_by_symbol:
            continue
        local_pos = local_by_symbol[symbol]
        market_price = safe_float(bp.get("current_price", local_pos["last_price"]), local_pos["last_price"])
        qty = safe_int(bp.get("qty", local_pos["qty_open"]), local_pos["qty_open"])
        local_pos["qty_open"] = qty
        update_position_market_price(local_pos, market_price)
    save_positions(GLOBAL_POSITIONS)


# =========================================================
# SIGNAL HANDLER
# =========================================================
def should_route_signal(signal: Dict[str, Any]) -> bool:
    new_hash = signal_hash(signal)
    if new_hash == GLOBAL_STATE.get("last_signal_hash", ""):
        debug("Duplicate signal skipped")
        return False
    return True


def handle_new_signal(signal: Dict[str, Any]):
    if not GLOBAL_STATE.get("engine_enabled", True):
        debug("Engine disabled; signal ignored")
        return
    if GLOBAL_STATE.get("kill_switch", False):
        debug("Kill switch active; signal ignored")
        return
    if GLOBAL_STATE.get("bot_paused", False):
        debug("Bot paused; signal ignored")
        return
    if not should_route_signal(signal):
        manage_open_positions(signal)
        return

    validation_decision = validate_signal(signal)
    if not validation_decision["approved"]:
        log(f"🚫 VALIDATION BLOCKED SIGNAL: {validation_decision['reject_reasons']}")
        validation_msg = build_validation_block_message(signal, validation_decision)
        send_to_discord(DISCORD_AI_WEBHOOK, validation_msg, "AI")
        send_to_telegram(validation_msg)
        return

    regime_decision = evaluate_regime(signal)
    if not regime_decision["approved"]:
        log(f"🚫 REGIME BLOCKED SIGNAL: {regime_decision['reject_reasons']}")
        regime_msg = build_regime_block_message(signal, regime_decision)
        send_to_discord(DISCORD_AI_WEBHOOK, regime_msg, "AI")
        send_to_telegram(regime_msg)
        return

    regime_signal = apply_regime_to_signal(signal, regime_decision)

    size_decision = size_signal_by_stop(regime_signal)
    if not size_decision["approved"]:
        log(f"🚫 SIZING BLOCKED SIGNAL: {size_decision['reject_reasons']}")
        size_block_msg = build_size_block_message(regime_signal, size_decision)
        send_to_discord(DISCORD_AI_WEBHOOK, size_block_msg, "AI")
        send_to_telegram(size_block_msg)
        return

    sized_signal = apply_size_decision_to_signal(regime_signal, size_decision)

    risk_decision = evaluate_risk_policy(sized_signal)
    if not risk_decision["approved"]:
        log(f"🚫 RISK BLOCKED SIGNAL: {risk_decision['reject_reasons']}")
        reject_msg = build_risk_block_message(sized_signal, risk_decision)
        send_to_discord(DISCORD_AI_WEBHOOK, reject_msg, "AI")
        send_to_telegram(reject_msg)
        return

    portfolio_decision = evaluate_portfolio_risk(sized_signal)
    if not portfolio_decision["approved"]:
        log(f"🚫 PORTFOLIO BLOCKED SIGNAL: {portfolio_decision['reject_reasons']}")
        portfolio_msg = build_portfolio_block_message(sized_signal, portfolio_decision)
        send_to_discord(DISCORD_AI_WEBHOOK, portfolio_msg, "AI")
        send_to_telegram(portfolio_msg)
        return

    route_signal(sized_signal, GLOBAL_STATE)
    GLOBAL_STATE["last_signal_hash"] = signal_hash(signal)
    GLOBAL_STATE["last_signal_time"] = epoch()
    GLOBAL_STATE["signal_count"] = safe_int(GLOBAL_STATE.get("signal_count", 0), 0) + 1
    save_state(GLOBAL_STATE)

    if GLOBAL_STATE.get("alpaca_enabled", False) and ENABLE_ALPACA and not GLOBAL_STATE.get("paper_enabled", True):
        open_live_position(sized_signal)
    elif GLOBAL_STATE.get("paper_enabled", True):
        open_paper_position(sized_signal)

    manage_open_positions(sized_signal)


# =========================================================
# TELEGRAM COMMANDS
# =========================================================
def build_status_text() -> str:
    return (
        f"🤖 {BOT_NAME} STATUS\nEngine Enabled: {GLOBAL_STATE['engine_enabled']}\nPaper Enabled: {GLOBAL_STATE['paper_enabled']}\n"
        f"Discord Enabled: {GLOBAL_STATE['discord_enabled']}\nTelegram Enabled: {GLOBAL_STATE['telegram_enabled']}\n"
        f"Alpaca Enabled: {GLOBAL_STATE['alpaca_enabled']}\nKill Switch: {GLOBAL_STATE.get('kill_switch', False)}\n"
        f"Bot Paused: {GLOBAL_STATE.get('bot_paused', False)}\n"
        f"Daily Realized PnL %: {round(safe_float(GLOBAL_STATE.get('daily_realized_pnl_pct', 0.0), 0.0) * 100, 2)}\n"
        f"Consecutive Losses: {GLOBAL_STATE.get('consecutive_losses', 0)}\n"
        f"Portfolio Heat %: {round(portfolio_heat_pct() * 100, 2)}\n"
        f"Signals Routed: {GLOBAL_STATE['signal_count']}\nPaper Trades: {GLOBAL_STATE['paper_trade_count']}\n"
        f"Live Trades: {GLOBAL_STATE['live_trade_count']}\nOpen Positions: {len(GLOBAL_POSITIONS['open_positions'])}\n"
        f"Closed Positions: {len(GLOBAL_POSITIONS['closed_positions'])}\n⏰ {now_ts()}"
    )


def build_positions_text() -> str:
    if not GLOBAL_POSITIONS["open_positions"]:
        return f"📭 No open positions.\n⏰ {now_ts()}"
    lines = ["📌 OPEN POSITIONS"]
    for p in GLOBAL_POSITIONS["open_positions"]:
        lines.append(
            f"ID {p['id']} | {p['mode']} | {p['symbol']} | Entry {p['entry_price']} | Live {p['last_price']} | PnL {round(p['pnl_pct'], 2)}% | Qty {p['qty_open']}"
        )
    lines.append(f"⏰ {now_ts()}")
    return "\n".join(lines)


def parse_command(text: str) -> str:
    return str(text or "").strip().lower()


def close_all_open_positions():
    for position in list(GLOBAL_POSITIONS["open_positions"]):
        if position["mode"] == "LIVE":
            live_close_position(position, "Manual close all")
        else:
            finalize_close_position(position, position["last_price"], "Manual close all")
    send_to_telegram("✅ All open positions closed.")


def handle_telegram_command(text: str):
    cmd = parse_command(text)
    if cmd in {"/start", "/help", "help"}:
        send_to_telegram(
            "📘 COMMANDS\n/status\n/positions\n/engine_on\n/engine_off\n/paper_on\n/paper_off\n/alpaca_on\n/alpaca_off\n/discord_on\n/discord_off\n/telegram_on\n/telegram_off\n/kill_on\n/kill_off\n/pause_on\n/pause_off\n/test\n/heartbeat\n/sync\n/cancel_orders\n/close_all\n"
        )
        return

    if cmd == "/status":
        send_to_telegram(build_status_text())
        return
    if cmd == "/positions":
        send_to_telegram(build_positions_text())
        return
    if cmd == "/engine_on":
        GLOBAL_STATE["engine_enabled"] = True
        save_state(GLOBAL_STATE)
        send_to_telegram("✅ Engine enabled")
        return
    if cmd == "/engine_off":
        GLOBAL_STATE["engine_enabled"] = False
        save_state(GLOBAL_STATE)
        send_to_telegram("🛑 Engine disabled")
        return
    if cmd == "/paper_on":
        GLOBAL_STATE["paper_enabled"] = True
        GLOBAL_STATE["last_mode"] = "PAPER"
        save_state(GLOBAL_STATE)
        send_to_telegram("✅ Paper mode enabled")
        return
    if cmd == "/paper_off":
        GLOBAL_STATE["paper_enabled"] = False
        GLOBAL_STATE["last_mode"] = "LIVE"
        save_state(GLOBAL_STATE)
        send_to_telegram("🛑 Paper mode disabled")
        return
    if cmd == "/alpaca_on":
        GLOBAL_STATE["alpaca_enabled"] = True
        GLOBAL_STATE["paper_enabled"] = False
        GLOBAL_STATE["last_mode"] = "LIVE"
        save_state(GLOBAL_STATE)
        send_to_telegram("✅ Alpaca mode enabled")
        return
    if cmd == "/alpaca_off":
        GLOBAL_STATE["alpaca_enabled"] = False
        save_state(GLOBAL_STATE)
        send_to_telegram("🛑 Alpaca mode disabled")
        return
    if cmd == "/discord_on":
        GLOBAL_STATE["discord_enabled"] = True
        save_state(GLOBAL_STATE)
        send_to_telegram("✅ Discord routing enabled")
        return
    if cmd == "/discord_off":
        GLOBAL_STATE["discord_enabled"] = False
        save_state(GLOBAL_STATE)
        send_to_telegram("🛑 Discord routing disabled")
        return
    if cmd == "/telegram_on":
        GLOBAL_STATE["telegram_enabled"] = True
        save_state(GLOBAL_STATE)
        send_to_telegram("✅ Telegram alerts enabled")
        return
    if cmd == "/telegram_off":
        GLOBAL_STATE["telegram_enabled"] = False
        save_state(GLOBAL_STATE)
        send_to_telegram("🛑 Telegram alerts disabled")
        return
    if cmd == "/kill_on":
        GLOBAL_STATE["kill_switch"] = True
        save_state(GLOBAL_STATE)
        send_to_telegram("🛑 Kill switch enabled")
        return
    if cmd == "/kill_off":
        GLOBAL_STATE["kill_switch"] = False
        save_state(GLOBAL_STATE)
        send_to_telegram("✅ Kill switch disabled")
        return
    if cmd == "/pause_on":
        GLOBAL_STATE["bot_paused"] = True
        save_state(GLOBAL_STATE)
        send_to_telegram("⏸️ Bot paused")
        return
    if cmd == "/pause_off":
        GLOBAL_STATE["bot_paused"] = False
        save_state(GLOBAL_STATE)
        send_to_telegram("▶️ Bot resumed")
        return
    if cmd == "/sync":
        sync_live_positions_from_alpaca()
        send_to_telegram("🔄 Alpaca sync complete")
        return
    if cmd == "/cancel_orders":
        if not alpaca_ready():
            send_to_telegram("❌ Alpaca not configured")
            return
        resp = alpaca_delete("/v2/orders")
        if resp.status_code in (200, 204, 207):
            send_to_telegram("✅ Cancel all orders sent")
        else:
            send_to_telegram(f"❌ Cancel all orders failed | {resp.status_code}")
        return
    if cmd == "/close_all":
        close_all_open_positions()
        return
    if cmd == "/heartbeat":
        send_heartbeat(force=True)
        return
    if cmd == "/test":
        run_startup_tests()
        send_to_telegram("🧪 Test alerts triggered")
        return


def process_telegram_updates():
    if not ENABLE_TELEGRAM_COMMANDS or not TELEGRAM_BOT_TOKEN:
        return
    offset = safe_int(GLOBAL_STATE.get("last_telegram_update_id", 0), 0) + 1
    updates = get_telegram_updates(offset=offset)
    if not updates:
        return
    max_update_id = safe_int(GLOBAL_STATE.get("last_telegram_update_id", 0), 0)
    for update in updates:
        update_id = safe_int(update.get("update_id", 0), 0)
        max_update_id = max(max_update_id, update_id)
        message = update.get("message", {}) or {}
        text = message.get("text", "")
        if not text:
            continue
        debug(f"Telegram command: {text}")
        handle_telegram_command(text)
    GLOBAL_STATE["last_telegram_update_id"] = max_update_id
    save_state(GLOBAL_STATE)


# =========================================================
# HEARTBEAT + TESTS
# =========================================================
def send_heartbeat(force: bool = False):
    if not ENABLE_HEARTBEAT:
        return
    last = safe_int(GLOBAL_STATE.get("last_heartbeat_time", 0), 0)
    minutes_since = (epoch() - last) / 60 if last > 0 else 99999
    if force or minutes_since >= HEARTBEAT_MINUTES:
        send_to_telegram(build_status_text())
        GLOBAL_STATE["last_heartbeat_time"] = epoch()
        save_state(GLOBAL_STATE)


def run_startup_tests():
    log("🚀 Running startup tests...")
    ts = now_ts()
    if ENABLE_DISCORD:
        send_to_discord(DISCORD_AI_WEBHOOK, f"🧪 TEST ALERT\nAI webhook live\n⏰ {ts}", "AI")
        send_to_discord(DISCORD_FREE_WEBHOOK, f"🧪 TEST ALERT\nFREE webhook live\n⏰ {ts}", "FREE")
        send_to_discord(DISCORD_PREMIUM_WEBHOOK, f"🧪 TEST ALERT\nPREMIUM webhook live\n⏰ {ts}", "PREMIUM")
    if ENABLE_TELEGRAM_ALERTS:
        send_to_telegram(f"🧪 TEST ALERT\nTelegram live\n⏰ {ts}")
    if ENABLE_ALPACA and alpaca_ready():
        acct = alpaca_get_account()
        if acct:
            msg = f"🧪 ALPACA CHECK OK\nStatus: {acct.get('status', 'unknown')}\nBuying Power: {acct.get('buying_power', 'N/A')}\nOptions Buying Power: {acct.get('options_buying_power', 'N/A')}\nAccount Blocked: {acct.get('account_blocked', 'N/A')}\n⏰ {ts}"
            send_to_telegram(msg)
        else:
            send_to_telegram(f"❌ ALPACA CHECK FAILED\n⏰ {ts}")


# =========================================================
# FALLBACK SIGNAL
# =========================================================
def fallback_signal() -> Dict[str, Any]:
    return normalize_signal({
        "ticker": "QQQ",
        "direction": "CALL",
        "asset_class": "option",
        "symbol": "QQQ260421C00492000",
        "price": 492.18,
        "contract_price": 1.35,
        "entry_contract": 1.35,
        "stop_contract": 0.95,
        "tp1_contract": 1.75,
        "tp2_contract": 2.20,
        "confidence": "A",
        "reason": "VWAP reclaim with higher low and expansion through resistance.",
        "public_reason": "Strength building over support with bullish confirmation.",
        "trigger": "Break and hold over reclaim level",
        "bias": "Bullish",
        "timeframe": "5m / 15m",
        "timestamp": epoch(),
        "source": "fallback_boot_signal",
        "qty": 1,
    })


# =========================================================
# BOOT
# =========================================================
def boot():
    global GLOBAL_STATE, GLOBAL_POSITIONS
    GLOBAL_STATE = load_state()
    GLOBAL_POSITIONS = load_positions()
    log(f"🔥 {BOT_NAME} booting...")
    save_state(GLOBAL_STATE)
    save_positions(GLOBAL_POSITIONS)
    reset_daily_risk_counters_if_needed(GLOBAL_STATE)
    debug_file_lookup(SIGNAL_FILE)
    if RUN_TEST_ON_START:
        run_startup_tests()
    send_heartbeat(force=True)


# =========================================================
# LOOP
# =========================================================
def main_loop():
    boot()
    if not file_exists(SIGNAL_FILE):
        log(f"❌ No signal file found on boot: {SIGNAL_FILE}")
        log(f"❌ Absolute boot path checked: {os.path.abspath(SIGNAL_FILE)}")
        debug_file_lookup(SIGNAL_FILE)
        debug("Routing fallback test signal once.")
        sig = fallback_signal()
        handle_new_signal(sig)

    while True:
        try:
            process_telegram_updates()
            live_signal = None
            if signal_file_changed(GLOBAL_STATE):
                live_signal = load_live_signal()
                if live_signal:
                    handle_new_signal(live_signal)
            sync_live_positions_from_alpaca()
            manage_open_positions(live_signal)
            send_heartbeat(force=False)
            time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            log("🛑 Manual stop")
            break
        except Exception as e:
            log(f"💥 Loop error: {e}")
            traceback.print_exc()
            time.sleep(POLL_SECONDS)


def run_once():
    boot()
    sig = load_live_signal()
    if sig is None:
        log("No live signal found. Using fallback once.")
        sig = fallback_signal()
    handle_new_signal(sig)
    sync_live_positions_from_alpaca()
    manage_open_positions(sig)
    process_telegram_updates()
    send_heartbeat(force=False)


# =========================================================
# ENTRY
# =========================================================
if __name__ == "__main__":
    try:
        if RUN_LOOP:
            main_loop()
        else:
            run_once()
    except Exception as e:
        log(f"💥 Fatal error: {e}")
        traceback.print_exc()
        sys.exit(1)

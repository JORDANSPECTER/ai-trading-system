import os
import sys
import json
import time
import math
import hashlib
import tempfile
import traceback
import re
from copy import deepcopy
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

import requests

# =========================================================
# MACRO BRIDGE IMPORTS
# Safe import so main engine still runs even if macro_bridge fails
# =========================================================
try:
    from macro_bridge import build_macro_bridge_snapshot, load_last_macro_snapshot
    MACRO_BRIDGE_AVAILABLE = True
except Exception as macro_import_error:
    MACRO_BRIDGE_AVAILABLE = False
    build_macro_bridge_snapshot = None
    load_last_macro_snapshot = None
    print(f"[MACRO IMPORT WARNING] macro_bridge unavailable: {macro_import_error}", flush=True)

# =========================================================
# UNBIASED TRADES ELITE ENGINE - HARDENED MAIN.PY
# Added:
# - Atomic JSON writes + backup recovery
# - Schema-safe state loading
# - Order lifecycle store
# - Startup reconciliation and safety block
# - Partial fill / fill-aware local updates
# - Macro bridge integration
# - Step 9 Entry Lock / No Chasing system
# - Clearer trust boundaries:
#     broker = live truth
#     local files = cache + audit log
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
ORDERS_FILE = os.getenv("ORDERS_FILE", "orders.json").strip()
RECON_FILE = os.getenv("RECON_FILE", "reconciliation.json").strip()
MACRO_FILE = os.getenv("MACRO_FILE", "macro_store.json").strip()

ENABLE_TELEGRAM_COMMANDS = os.getenv("ENABLE_TELEGRAM_COMMANDS", "true").lower() == "true"
ENABLE_PAPER_EXECUTION = os.getenv("ENABLE_PAPER_EXECUTION", "true").lower() == "true"
ENABLE_DISCORD = os.getenv("ENABLE_DISCORD", "true").lower() == "true"
ENABLE_TELEGRAM_ALERTS = os.getenv("ENABLE_TELEGRAM_ALERTS", "true").lower() == "true"
ENABLE_HEARTBEAT = os.getenv("ENABLE_HEARTBEAT", "true").lower() == "true"

# MACRO BRIDGE
ENABLE_MACRO_BRIDGE = os.getenv("ENABLE_MACRO_BRIDGE", "true").lower() == "true"
MACRO_REFRESH_SECONDS = int(os.getenv("MACRO_REFRESH_SECONDS", "300"))
MACRO_SEND_TO_AI = os.getenv("MACRO_SEND_TO_AI", "true").lower() == "true"
MACRO_SEND_TO_TELEGRAM = os.getenv("MACRO_SEND_TO_TELEGRAM", "false").lower() == "true"
MACRO_SEND_ON_BOOT = os.getenv("MACRO_SEND_ON_BOOT", "true").lower() == "true"

# ALPACA
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

# SIGNAL / EXECUTION DEFAULTS
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

# RISK LIMITS
MAX_RISK_PER_TRADE_PCT = float(os.getenv("MAX_RISK_PER_TRADE_PCT", "0.005"))
MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", "0.02"))
MAX_PORTFOLIO_HEAT_PCT = float(os.getenv("MAX_PORTFOLIO_HEAT_PCT", "0.03"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "3"))
MAX_SAME_TICKER_POSITIONS = int(os.getenv("MAX_SAME_TICKER_POSITIONS", "1"))
MAX_CONSECUTIVE_LOSSES = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))
PAPER_ACCOUNT_EQUITY = float(os.getenv("PAPER_ACCOUNT_EQUITY", "25000"))
LIVE_ACCOUNT_EQUITY_FALLBACK = float(os.getenv("LIVE_ACCOUNT_EQUITY_FALLBACK", "25000"))

# POSITION SIZING
MIN_POSITION_QTY = int(os.getenv("MIN_POSITION_QTY", "1"))
MAX_POSITION_QTY = int(os.getenv("MAX_POSITION_QTY", "10"))
USE_SIGNAL_QTY_AS_MAX = os.getenv("USE_SIGNAL_QTY_AS_MAX", "false").lower() == "true"
CONFIDENCE_MULT_A_PLUS = float(os.getenv("CONFIDENCE_MULT_A_PLUS", "1.00"))
CONFIDENCE_MULT_A = float(os.getenv("CONFIDENCE_MULT_A", "1.00"))
CONFIDENCE_MULT_B = float(os.getenv("CONFIDENCE_MULT_B", "0.70"))
CONFIDENCE_MULT_C = float(os.getenv("CONFIDENCE_MULT_C", "0.40"))

# PRE-TRADE VALIDATOR
MIN_RR_RATIO = float(os.getenv("MIN_RR_RATIO", "1.2"))
REJECT_DUPLICATE_OPEN_SYMBOL = os.getenv("REJECT_DUPLICATE_OPEN_SYMBOL", "true").lower() == "true"
ENFORCE_NO_TRADE_WINDOW = os.getenv("ENFORCE_NO_TRADE_WINDOW", "false").lower() == "true"
NO_TRADE_START_HHMM = os.getenv("NO_TRADE_START_HHMM", "09:30").strip()
NO_TRADE_END_HHMM = os.getenv("NO_TRADE_END_HHMM", "09:33").strip()

# PORTFOLIO RISK
MAX_PROJECTED_PORTFOLIO_HEAT_PCT = float(os.getenv("MAX_PROJECTED_PORTFOLIO_HEAT_PCT", "0.03"))
MAX_SYMBOL_PORTFOLIO_COUNT = int(os.getenv("MAX_SYMBOL_PORTFOLIO_COUNT", "1"))
MAX_DIRECTIONAL_INDEX_COUNT = int(os.getenv("MAX_DIRECTIONAL_INDEX_COUNT", "2"))
MAX_CORRELATED_THEME_COUNT = int(os.getenv("MAX_CORRELATED_THEME_COUNT", "2"))

CORRELATED_TICKERS = {
    "SPY", "QQQ", "IWM", "DIA", "NVDA", "TSLA", "AAPL", "MSFT", "META", "AMD"
}

# REGIME
ENABLE_REGIME_ENGINE = os.getenv("ENABLE_REGIME_ENGINE", "true").lower() == "true"
ALLOWED_REGIMES = {
    p.strip().upper() for p in os.getenv("ALLOWED_REGIMES", "TREND,EXPANSION,NORMAL").split(",") if p.strip()
}
MIN_REGIME_SCORE = float(os.getenv("MIN_REGIME_SCORE", "0.50"))
BLOCK_CHOP_REGIME = os.getenv("BLOCK_CHOP_REGIME", "true").lower() == "true"
ALLOW_EVENT_REGIME = os.getenv("ALLOW_EVENT_REGIME", "false").lower() == "true"

# RECON / SAFETY
STRICT_STARTUP_RECON = os.getenv("STRICT_STARTUP_RECON", "true").lower() == "true"
BLOCK_NEW_TRADES_ON_RECON_MISMATCH = os.getenv("BLOCK_NEW_TRADES_ON_RECON_MISMATCH", "true").lower() == "true"
RECON_LOOKBACK_ORDERS = int(os.getenv("RECON_LOOKBACK_ORDERS", "50"))
MAX_ORDER_STALE_SECONDS = int(os.getenv("MAX_ORDER_STALE_SECONDS", "120"))


# =========================================================
# MARKET DATA / STEP 8 LIVE PRICE MANAGEMENT
ENABLE_MARKET_DATA = os.getenv("ENABLE_MARKET_DATA", "true").lower() == "true"
MARKET_DATA_FILE = os.getenv("MARKET_DATA_FILE", "market_prices.json").strip()
MARKET_DATA_PROVIDER = os.getenv("MARKET_DATA_PROVIDER", "auto").strip().lower()
MARKET_DATA_REFRESH_SECONDS = int(os.getenv("MARKET_DATA_REFRESH_SECONDS", "5"))
MARKET_DATA_STALE_SECONDS = int(os.getenv("MARKET_DATA_STALE_SECONDS", "20"))
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()
TWELVE_DATA_BASE_URL = os.getenv("TWELVE_DATA_BASE_URL", "https://api.twelvedata.com").strip().rstrip("/")
ALPACA_DATA_BASE_URL = os.getenv("ALPACA_DATA_BASE_URL", "https://data.alpaca.markets").strip().rstrip("/")
LIVE_PRICE_CACHE_SECONDS = int(os.getenv("LIVE_PRICE_CACHE_SECONDS", str(MARKET_DATA_REFRESH_SECONDS)))
AUTO_MANAGE_POSITIONS = os.getenv("AUTO_MANAGE_POSITIONS", "true").lower() == "true"
AUTO_TP_ENABLED = os.getenv("AUTO_TP_ENABLED", "true").lower() == "true"
AUTO_TRAILING_STOP_ENABLED = os.getenv("AUTO_TRAILING_STOP_ENABLED", "true").lower() == "true"
AUTO_BREAKEVEN_ENABLED = os.getenv("AUTO_BREAKEVEN_ENABLED", "true").lower() == "true"
TRAIL_ONLY_AFTER_TP1 = os.getenv("TRAIL_ONLY_AFTER_TP1", "false").lower() == "true"
SEND_PRICE_UPDATE_ALERTS = os.getenv("SEND_PRICE_UPDATE_ALERTS", "false").lower() == "true"
PRICE_UPDATE_ALERT_SECONDS = int(os.getenv("PRICE_UPDATE_ALERT_SECONDS", "60"))

# =========================================================
# STEP 9 ENTRY LOCK / NO CHASING SYSTEM
# =========================================================
ENABLE_ENTRY_LOCK = os.getenv("ENABLE_ENTRY_LOCK", "true").lower() == "true"
MAX_ENTRY_AGE_SECONDS = int(os.getenv("MAX_ENTRY_AGE_SECONDS", "60"))
MAX_ENTRY_SLIPPAGE_PCT = float(os.getenv("MAX_ENTRY_SLIPPAGE_PCT", "0.05"))
REQUIRE_PRICE_FOR_ENTRY_LOCK = os.getenv("REQUIRE_PRICE_FOR_ENTRY_LOCK", "false").lower() == "true"
REPRICE_ENTRY_TO_LIVE_PRICE = os.getenv("REPRICE_ENTRY_TO_LIVE_PRICE", "true").lower() == "true"
ENTRY_LOCK_RR_CHECK = os.getenv("ENTRY_LOCK_RR_CHECK", "true").lower() == "true"
MIN_LIVE_ENTRY_RR_RATIO = float(os.getenv("MIN_LIVE_ENTRY_RR_RATIO", str(MIN_RR_RATIO)))

# GLOBALS
# =========================================================
GLOBAL_STATE = None
GLOBAL_POSITIONS = None
GLOBAL_ORDERS = None
GLOBAL_RECON = None
GLOBAL_MACRO = None
DIRTY_STATE = False
DIRTY_POSITIONS = False
DIRTY_ORDERS = False
DIRTY_RECON = False
DIRTY_MACRO = False
MARKET_PRICE_CACHE = {}


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
        return int(float(v))
    except Exception:
        return int(default)


def file_exists(path: str) -> bool:
    return os.path.exists(path)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def signal_hash(signal: Dict[str, Any]) -> str:
    try:
        key = json.dumps(signal, sort_keys=True, default=str)
        return sha256_text(key)
    except Exception:
        return sha256_text(str(epoch()))


def current_trade_day() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def current_hhmm() -> str:
    return datetime.now().strftime("%H:%M")


def hhmm_to_minutes(hhmm: str) -> int:
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return 0


def is_now_in_no_trade_window() -> bool:
    if not ENFORCE_NO_TRADE_WINDOW:
        return False
    now_m = hhmm_to_minutes(current_hhmm())
    start_m = hhmm_to_minutes(NO_TRADE_START_HHMM)
    end_m = hhmm_to_minutes(NO_TRADE_END_HHMM)
    return start_m <= now_m <= end_m


def pct_change(entry: float, last: float) -> float:
    if entry <= 0:
        return 0.0
    return ((last - entry) / entry) * 100.0


def weighted_avg_price(old_qty: int, old_avg: float, fill_qty: int, fill_price: float) -> float:
    total_qty = old_qty + fill_qty
    if total_qty <= 0:
        return 0.0
    return ((old_qty * old_avg) + (fill_qty * fill_price)) / total_qty


def atomic_write_json(path: str, data: Any) -> bool:
    directory = os.path.dirname(path) or "."
    base = os.path.basename(path)
    tmp_fd = None
    tmp_path = None
    try:
        os.makedirs(directory, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(prefix=f".{base}.", suffix=".tmp", dir=directory)
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        if file_exists(path):
            backup = f"{path}.bak"
            try:
                with open(path, "r", encoding="utf-8") as src, open(backup, "w", encoding="utf-8") as dst:
                    dst.write(src.read())
            except Exception:
                pass
        os.replace(tmp_path, path)
        return True
    except Exception as e:
        log(f"❌ Atomic save failed for {path}: {e}")
        try:
            if tmp_path and file_exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        return False


def load_json_file(path: str, default: Any):
    candidates = [path, f"{path}.bak"]
    for candidate in candidates:
        try:
            if not file_exists(candidate):
                continue
            with open(candidate, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log(f"❌ Failed reading {candidate}: {e}")
    return deepcopy(default)


def save_json_file(path: str, data: Any) -> bool:
    return atomic_write_json(path, data)


def debug_file_lookup(path: str):
    try:
        cwd = os.getcwd()
        abs_path = os.path.abspath(path)
        log("📁 FILE DEBUG MODE")
        log(f"Working directory: {cwd}")
        log(f"Requested path: {path}")
        log(f"Absolute path: {abs_path}")
        log(f"Exists?: {os.path.exists(path)}")
        log(f"Absolute exists?: {os.path.exists(abs_path)}")
        try:
            log(f"Files in cwd: {os.listdir(cwd)}")
        except Exception as inner:
            log(f"❌ Could not list cwd: {inner}")
    except Exception as e:
        log(f"❌ debug_file_lookup failed: {e}")


# =========================================================
# DEFAULT STORES
# =========================================================
def default_state() -> Dict[str, Any]:
    return {
        "schema_version": 2,
        "engine_enabled": True,
        "paper_enabled": ENABLE_PAPER_EXECUTION,
        "discord_enabled": ENABLE_DISCORD,
        "telegram_enabled": ENABLE_TELEGRAM_ALERTS,
        "alpaca_enabled": ENABLE_ALPACA,
        "last_signal_hash": "",
        "last_signal_time": 0,
        "recent_signal_hashes": [],
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
        "last_mode": "LIVE" if LIVE_MODE else "PAPER",
        "reconciliation_required": False,
        "reconciliation_block_reason": "",
    }


def default_positions() -> Dict[str, Any]:
    return {
        "schema_version": 2,
        "open_positions": [],
        "closed_positions": [],
        "last_position_id": 0,
    }


def default_orders() -> Dict[str, Any]:
    return {
        "schema_version": 2,
        "orders": [],
        "last_local_order_id": 0,
    }


def default_recon() -> Dict[str, Any]:
    return {
        "schema_version": 2,
        "last_boot_reconciliation_at": 0,
        "last_boot_report": {},
        "last_runtime_reconciliation_at": 0,
    }


def default_macro_store() -> Dict[str, Any]:
    return {
        "schema_version": 2,
        "last_refresh_time": 0,
        "last_snapshot": {},
        "last_voice_script": "",
        "last_macro_state": {},
        "last_error": "",
    }


def safe_merge(default_obj: Dict[str, Any], loaded: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(default_obj)
    if isinstance(loaded, dict):
        merged.update(loaded)
    return merged


def load_state() -> Dict[str, Any]:
    return safe_merge(default_state(), load_json_file(STATE_FILE, default_state()))


def save_state(state: Dict[str, Any]):
    global GLOBAL_STATE
    GLOBAL_STATE = state
    mark_state_dirty()


def load_positions() -> Dict[str, Any]:
    data = safe_merge(default_positions(), load_json_file(POSITIONS_FILE, default_positions()))
    if not isinstance(data.get("open_positions"), list):
        data["open_positions"] = []
    if not isinstance(data.get("closed_positions"), list):
        data["closed_positions"] = []
    return data


def save_positions(positions: Dict[str, Any]):
    global GLOBAL_POSITIONS
    GLOBAL_POSITIONS = positions
    mark_positions_dirty()


def load_orders() -> Dict[str, Any]:
    data = safe_merge(default_orders(), load_json_file(ORDERS_FILE, default_orders()))
    if not isinstance(data.get("orders"), list):
        data["orders"] = []
    return data


def save_orders(orders: Dict[str, Any]):
    global GLOBAL_ORDERS
    GLOBAL_ORDERS = orders
    mark_orders_dirty()


def load_recon() -> Dict[str, Any]:
    return safe_merge(default_recon(), load_json_file(RECON_FILE, default_recon()))


def save_recon(recon: Dict[str, Any]):
    global GLOBAL_RECON
    GLOBAL_RECON = recon
    mark_recon_dirty()


def load_macro_store() -> Dict[str, Any]:
    global GLOBAL_MACRO
    if GLOBAL_MACRO is None or not isinstance(GLOBAL_MACRO, dict):
        GLOBAL_MACRO = safe_merge(default_macro_store(), load_json_file(MACRO_FILE, default_macro_store()))
    return GLOBAL_MACRO


def save_macro_store():
    global GLOBAL_MACRO, DIRTY_MACRO
    if GLOBAL_MACRO is None:
        GLOBAL_MACRO = safe_merge(default_macro_store(), load_json_file(MACRO_FILE, default_macro_store()))
    save_json_file(MACRO_FILE, GLOBAL_MACRO)
    DIRTY_MACRO = False


def ensure_globals_initialized():
    global GLOBAL_STATE, GLOBAL_POSITIONS, GLOBAL_ORDERS, GLOBAL_RECON, GLOBAL_MACRO
    if GLOBAL_STATE is None:
        GLOBAL_STATE = load_state()
    if GLOBAL_POSITIONS is None:
        GLOBAL_POSITIONS = load_positions()
    if GLOBAL_ORDERS is None:
        GLOBAL_ORDERS = load_orders()
    if GLOBAL_RECON is None:
        GLOBAL_RECON = load_recon()
    if GLOBAL_MACRO is None:
        GLOBAL_MACRO = safe_merge(default_macro_store(), load_json_file(MACRO_FILE, default_macro_store()))


def mark_state_dirty():
    global DIRTY_STATE
    DIRTY_STATE = True


def mark_positions_dirty():
    global DIRTY_POSITIONS
    DIRTY_POSITIONS = True


def mark_orders_dirty():
    global DIRTY_ORDERS
    DIRTY_ORDERS = True


def mark_recon_dirty():
    global DIRTY_RECON
    DIRTY_RECON = True


def mark_macro_dirty():
    global DIRTY_MACRO
    DIRTY_MACRO = True


def flush_dirty_stores(force: bool = False):
    global DIRTY_STATE, DIRTY_POSITIONS, DIRTY_ORDERS, DIRTY_RECON, DIRTY_MACRO
    ensure_globals_initialized()
    if force or DIRTY_STATE:
        save_json_file(STATE_FILE, GLOBAL_STATE)
        DIRTY_STATE = False
    if force or DIRTY_POSITIONS:
        save_json_file(POSITIONS_FILE, GLOBAL_POSITIONS)
        DIRTY_POSITIONS = False
    if force or DIRTY_ORDERS:
        save_json_file(ORDERS_FILE, GLOBAL_ORDERS)
        DIRTY_ORDERS = False
    if force or DIRTY_RECON:
        save_json_file(RECON_FILE, GLOBAL_RECON)
        DIRTY_RECON = False
    if force or DIRTY_MACRO:
        save_json_file(MACRO_FILE, GLOBAL_MACRO)
        DIRTY_MACRO = False

# =========================================================
# STATE HELPERS
# =========================================================
def reset_daily_risk_counters_if_needed(state: Dict[str, Any]):
    today = current_trade_day()
    if state.get("last_trade_day") != today:
        state["daily_realized_pnl_pct"] = 0.0
        state["consecutive_losses"] = 0
        state["last_trade_day"] = today
        save_state(state)


def append_recent_signal_hash(state: Dict[str, Any], sig_hash: str, max_keep: int = 50):
    hashes = state.get("recent_signal_hashes", [])
    if not isinstance(hashes, list):
        hashes = []
    hashes.append(sig_hash)
    state["recent_signal_hashes"] = hashes[-max_keep:]


def clear_reconciliation_block():
    ensure_globals_initialized()
    GLOBAL_STATE["reconciliation_required"] = False
    GLOBAL_STATE["reconciliation_block_reason"] = ""
    save_state(GLOBAL_STATE)


def set_reconciliation_block(reason: str):
    ensure_globals_initialized()
    GLOBAL_STATE["reconciliation_required"] = True
    GLOBAL_STATE["reconciliation_block_reason"] = reason
    save_state(GLOBAL_STATE)


# =========================================================
# MACRO BRIDGE HELPERS
# =========================================================
def get_macro_state_summary_text(macro_state: Dict[str, Any]) -> str:
    if not macro_state:
        return "No macro state available."

    drivers = macro_state.get("drivers", []) or []
    watch_items = macro_state.get("watch_items", []) or []
    events = macro_state.get("todays_high_impact_events", []) or []

    driver_text = ", ".join(drivers[:5]).replace("_", " ") if drivers else "none"
    watch_text = ", ".join(watch_items[:5]).replace("_", " ") if watch_items else "none"
    event_text = ", ".join(events[:5]) if events else "none"

    return (
        f"Risk State: {macro_state.get('risk_state', 'unknown')}\n"
        f"Macro Bias: {macro_state.get('macro_bias', 'unknown')}\n"
        f"Volatility State: {macro_state.get('volatility_state', 'unknown')}\n"
        f"Confidence: {macro_state.get('confidence', 'N/A')}\n"
        f"Drivers: {driver_text}\n"
        f"Watch Items: {watch_text}\n"
        f"High Impact Events: {event_text}"
    )


def build_macro_message(snapshot: Dict[str, Any]) -> str:
    if not snapshot:
        return f"🌎 MACRO UPDATE\nNo macro snapshot available.\n⏰ {now_ts()}"

    macro_state = snapshot.get("macro_state", {}) or {}
    voice_script = snapshot.get("voice_script", "") or ""
    summary = get_macro_state_summary_text(macro_state)

    return (
        f"🌎 MACRO BRIDGE UPDATE\n"
        f"{summary}\n\n"
        f"Voice Script:\n{voice_script}\n\n"
        f"⏰ {now_ts()}"
    )


def refresh_macro_bridge(force: bool = False, send_alerts: bool = False) -> Optional[Dict[str, Any]]:
    global GLOBAL_MACRO

    macro_store = load_macro_store()

    if not ENABLE_MACRO_BRIDGE:
        return macro_store.get("last_snapshot", {})

    if not MACRO_BRIDGE_AVAILABLE or build_macro_bridge_snapshot is None:
        macro_store["last_error"] = "macro_bridge import unavailable"
        mark_macro_dirty()
        save_macro_store()
        return macro_store.get("last_snapshot", {})

    last_refresh = safe_int(macro_store.get("last_refresh_time", 0), 0)
    if not force and (epoch() - last_refresh) < MACRO_REFRESH_SECONDS:
        return macro_store.get("last_snapshot", {})

    try:
        snapshot = build_macro_bridge_snapshot()
        if not isinstance(snapshot, dict):
            snapshot = {}

        macro_store["last_refresh_time"] = epoch()
        macro_store["last_snapshot"] = snapshot
        macro_store["last_voice_script"] = snapshot.get("voice_script", "")
        macro_store["last_macro_state"] = snapshot.get("macro_state", {})
        macro_store["last_error"] = ""
        mark_macro_dirty()
        save_macro_store()

        if send_alerts:
            msg = build_macro_message(snapshot)
            if MACRO_SEND_TO_AI:
                send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
            if MACRO_SEND_TO_TELEGRAM:
                send_to_telegram(msg)

        return snapshot

    except Exception as e:
        macro_store["last_error"] = str(e)
        mark_macro_dirty()
        save_macro_store()
        log(f"❌ Macro bridge refresh failed: {e}")

        try:
            if MACRO_BRIDGE_AVAILABLE and load_last_macro_snapshot:
                cached = load_last_macro_snapshot()
                if isinstance(cached, dict) and cached:
                    macro_store["last_snapshot"] = cached
                    macro_store["last_voice_script"] = cached.get("voice_script", "")
                    macro_store["last_macro_state"] = cached.get("macro_state", {})
                    mark_macro_dirty()
                    save_macro_store()
                    return cached
        except Exception:
            pass

        return macro_store.get("last_snapshot", {})


def get_latest_macro_snapshot() -> Dict[str, Any]:
    macro_store = load_macro_store()
    return macro_store.get("last_snapshot", {}) or {}


def get_latest_macro_state() -> Dict[str, Any]:
    macro_store = load_macro_store()
    return macro_store.get("last_macro_state", {}) or {}


def get_latest_macro_voice_script() -> str:
    macro_store = load_macro_store()
    return str(macro_store.get("last_voice_script", "") or "")


# =========================================================
# DISCORD / TELEGRAM
# =========================================================
def send_to_discord(webhook_url: str, message: str, label: str = "UNKNOWN") -> bool:
    if not ENABLE_DISCORD:
        return False
    if not webhook_url:
        log(f"❌ Missing Discord webhook for {label}")
        return False
    try:
        r = requests.post(webhook_url, json={"content": message[:2000]}, timeout=15)
        if 200 <= r.status_code < 300:
            log(f"✅ Discord sent -> {label}")
            return True
        log(f"❌ Discord failed -> {label} | {r.status_code} | {r.text}")
        return False
    except Exception as e:
        log(f"❌ Discord exception -> {label}: {e}")
        return False


def telegram_api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"


def send_to_telegram(message: str) -> bool:
    if not ENABLE_TELEGRAM_ALERTS:
        return False
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message[:4096], "disable_web_page_preview": True}
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
            return []
        data = r.json()
        if not data.get("ok"):
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
    return requests.get(f"{ALPACA_BASE_URL}{path}", headers=alpaca_headers(), params=params or {}, timeout=ALPACA_ORDER_TIMEOUT)


def alpaca_post(path: str, payload: Dict[str, Any]):
    return requests.post(f"{ALPACA_BASE_URL}{path}", headers=alpaca_headers(), json=payload, timeout=ALPACA_ORDER_TIMEOUT)


def alpaca_delete(path: str):
    return requests.delete(f"{ALPACA_BASE_URL}{path}", headers=alpaca_headers(), timeout=ALPACA_ORDER_TIMEOUT)


def alpaca_get_account() -> Optional[Dict[str, Any]]:
    if not alpaca_ready():
        return None
    try:
        r = alpaca_get("/v2/account")
        if r.status_code == 200:
            return r.json()
        log(f"❌ Alpaca account failed | {r.status_code} | {r.text}")
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
    except Exception:
        pass
    return None


def alpaca_list_orders(status: str = "open", limit: int = RECON_LOOKBACK_ORDERS) -> List[Dict[str, Any]]:
    if not alpaca_ready():
        return []
    try:
        r = alpaca_get("/v2/orders", params={"status": status, "limit": limit, "direction": "desc", "nested": "false"})
        if r.status_code == 200:
            data = r.json()
            return data if isinstance(data, list) else []
        log(f"❌ Alpaca list orders failed | {r.status_code} | {r.text}")
    except Exception as e:
        log(f"❌ Alpaca list orders exception: {e}")
    return []


def alpaca_get_order(order_id: str) -> Optional[Dict[str, Any]]:
    if not alpaca_ready() or not order_id:
        return None
    try:
        r = alpaca_get(f"/v2/orders/{order_id}")
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
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
            return r.json()
        log(f"❌ Alpaca submit failed | {r.status_code} | {r.text}")
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
        return None
    sell_qty = open_qty if qty is None else min(open_qty, int(qty))
    return alpaca_submit_order(symbol=symbol, qty=sell_qty, side="sell", order_type="market", tif="day", client_order_id=f"ub-close-{symbol}-{epoch()}")


def get_account_equity() -> float:
    if ENABLE_ALPACA and GLOBAL_STATE and GLOBAL_STATE.get("alpaca_enabled", False) and alpaca_ready():
        acct = alpaca_get_account()
        if acct:
            return max(safe_float(acct.get("equity", LIVE_ACCOUNT_EQUITY_FALLBACK), LIVE_ACCOUNT_EQUITY_FALLBACK), 1.0)
    return max(PAPER_ACCOUNT_EQUITY, 1.0)


def get_options_buying_power() -> float:
    if ENABLE_ALPACA and GLOBAL_STATE and GLOBAL_STATE.get("alpaca_enabled", False) and alpaca_ready() and USE_ALPACA_OPTIONS_BUYING_POWER:
        acct = alpaca_get_account()
        if acct:
            obp = safe_float(acct.get("options_buying_power", 0), 0)
            if obp > 0:
                return obp
            return max(safe_float(acct.get("buying_power", 0), 0), 0)
    return get_account_equity()


# =========================================================
# ORDER STORE / LIFECYCLE
# =========================================================
def next_local_order_id() -> int:
    GLOBAL_ORDERS["last_local_order_id"] = safe_int(GLOBAL_ORDERS.get("last_local_order_id", 0), 0) + 1
    return GLOBAL_ORDERS["last_local_order_id"]


def make_order_record(signal: Dict[str, Any], side: str, qty: int, mode: str, order_type: str, limit_price: Optional[float] = None) -> Dict[str, Any]:
    local_id = next_local_order_id()
    symbol = str(signal.get("symbol", "")).strip()
    client_order_id = f"ub-{side}-{symbol}-{epoch()}-{local_id}"
    return {
        "local_order_id": local_id,
        "signal_id": signal.get("signal_id", ""),
        "position_id": None,
        "ticker": signal.get("ticker", ""),
        "symbol": symbol,
        "side": side,
        "qty_requested": int(qty),
        "qty_filled": 0,
        "qty_remaining": int(qty),
        "avg_fill_price": 0.0,
        "mode": mode,
        "type": order_type,
        "limit_price": safe_float(limit_price, 0.0),
        "client_order_id": client_order_id,
        "broker_order_id": "",
        "status": "created",
        "created_at": epoch(),
        "updated_at": epoch(),
        "closed_at": 0,
        "notes": [],
    }


def save_order_record(order_record: Dict[str, Any]):
    GLOBAL_ORDERS["orders"].append(order_record)
    save_orders(GLOBAL_ORDERS)


def get_order_by_local_id(local_order_id: int) -> Optional[Dict[str, Any]]:
    for o in GLOBAL_ORDERS.get("orders", []):
        if safe_int(o.get("local_order_id", 0), 0) == safe_int(local_order_id, 0):
            return o
    return None


def get_order_by_broker_id(broker_order_id: str) -> Optional[Dict[str, Any]]:
    for o in GLOBAL_ORDERS.get("orders", []):
        if o.get("broker_order_id") == broker_order_id:
            return o
    return None


def get_orders_for_position(position_id: int) -> List[Dict[str, Any]]:
    return [o for o in GLOBAL_ORDERS.get("orders", []) if safe_int(o.get("position_id", 0), 0) == safe_int(position_id, 0)]


def update_order_status(order_record: Dict[str, Any], status: str, note: Optional[str] = None):
    order_record["status"] = status
    order_record["updated_at"] = epoch()
    if status in {"filled", "canceled", "rejected", "expired"}:
        order_record["closed_at"] = epoch()
    if status == "filled":
        order_record["qty_remaining"] = 0
    if note:
        order_record.setdefault("notes", []).append(note)
    save_orders(GLOBAL_ORDERS)


def apply_broker_order_snapshot(order_record: Dict[str, Any], broker_order: Dict[str, Any]):
    if not broker_order:
        return
    order_record["broker_order_id"] = broker_order.get("id", order_record.get("broker_order_id", ""))
    order_record["client_order_id"] = broker_order.get("client_order_id", order_record.get("client_order_id", ""))
    order_record["status"] = str(broker_order.get("status", order_record.get("status", "submitted"))).lower()
    order_record["qty_filled"] = safe_int(broker_order.get("filled_qty", order_record.get("qty_filled", 0)), order_record.get("qty_filled", 0))
    order_record["qty_remaining"] = max(0, safe_int(order_record.get("qty_requested", 0), 0) - safe_int(order_record.get("qty_filled", 0), 0))
    order_record["avg_fill_price"] = safe_float(broker_order.get("filled_avg_price", order_record.get("avg_fill_price", 0.0)), order_record.get("avg_fill_price", 0.0))
    order_record["updated_at"] = epoch()
    save_orders(GLOBAL_ORDERS)


def refresh_open_order_states():
    for order_record in GLOBAL_ORDERS.get("orders", []):
        status = str(order_record.get("status", "")).lower()
        broker_id = order_record.get("broker_order_id", "")
        if status in {"filled", "canceled", "rejected", "expired"}:
            continue
        if not broker_id:
            continue
        broker_order = alpaca_get_order(broker_id)
        if broker_order:
            apply_broker_order_snapshot(order_record, broker_order)


# =========================================================
# RISK HELPERS
# =========================================================
def estimate_unit_risk(signal: Dict[str, Any]) -> float:
    entry = safe_float(signal.get("entry_contract", 0), 0)
    stop = safe_float(signal.get("stop_contract", 0), 0)
    if entry <= 0 or stop <= 0:
        return 0.0
    return max(entry - stop, 0.0)


def estimate_trade_risk_dollars(signal: Dict[str, Any]) -> float:
    qty = max(1, safe_int(signal.get("qty", 1), 1))
    return qty * estimate_unit_risk(signal) * 100.0


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
    return qty_open * max(entry - stop, 0.0) * 100.0


def portfolio_heat_pct() -> float:
    equity = get_account_equity()
    if equity <= 0:
        return 0.0
    total_open_risk = sum(estimate_open_position_risk_dollars(p) for p in GLOBAL_POSITIONS.get("open_positions", []))
    return total_open_risk / equity


def is_correlated_ticker(ticker: str) -> bool:
    return str(ticker).upper().strip() in CORRELATED_TICKERS


# =========================================================
# POSITION SIZING / VALIDATION / RISK
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
    adjusted_risk_dollars = equity * MAX_RISK_PER_TRADE_PCT * confidence_size_multiplier(signal.get("confidence", "C"))
    unit_risk_dollars = unit_risk * 100.0
    raw_size = math.floor(adjusted_risk_dollars / unit_risk_dollars) if unit_risk_dollars > 0 else 0
    final_size = raw_size
    adjustments = []

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
        "confidence_multiplier": confidence_size_multiplier(signal.get("confidence", "C")),
        "adjustments": adjustments,
    }


def apply_size_decision_to_signal(signal: Dict[str, Any], size_decision: Dict[str, Any]) -> Dict[str, Any]:
    x = deepcopy(signal)
    x["qty"] = int(size_decision["final_size"])
    x["size_decision"] = size_decision
    return x


def validate_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    reasons = []
    required_fields = ["ticker", "symbol", "direction", "confidence", "entry_contract", "stop_contract", "tp1_contract", "timestamp"]
    for field in required_fields:
        if signal.get(field) in (None, ""):
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

    if REQUIRE_OPTION_SYMBOL and signal.get("asset_class") == "option" and signal.get("symbol") == signal.get("ticker"):
        reasons.append("missing_full_option_symbol")

    if REJECT_DUPLICATE_OPEN_SYMBOL:
        open_symbols = {p.get("symbol") for p in GLOBAL_POSITIONS.get("open_positions", [])}
        if signal.get("symbol") in open_symbols:
            reasons.append("duplicate_open_symbol")

    if is_now_in_no_trade_window():
        reasons.append("inside_no_trade_window")

    return {"approved": len(reasons) == 0, "stage": "pretrade_validator", "reject_reasons": reasons, "reward_to_risk": round(best_rr, 4), "unit_risk": round(unit_risk, 4)}


def evaluate_risk_policy(signal: Dict[str, Any]) -> Dict[str, Any]:
    reasons = []
    reset_daily_risk_counters_if_needed(GLOBAL_STATE)

    if GLOBAL_STATE.get("kill_switch", False):
        reasons.append("kill_switch_active")
    if GLOBAL_STATE.get("bot_paused", False):
        reasons.append("bot_paused")
    if not GLOBAL_STATE.get("engine_enabled", True):
        reasons.append("engine_disabled")
    if GLOBAL_STATE.get("reconciliation_required", False):
        reasons.append("reconciliation_block_active")

    open_positions = GLOBAL_POSITIONS.get("open_positions", [])
    if len(open_positions) >= MAX_OPEN_POSITIONS:
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

    if safe_int(GLOBAL_STATE.get("consecutive_losses", 0), 0) >= MAX_CONSECUTIVE_LOSSES:
        reasons.append("max_consecutive_losses_hit")

    notional = estimate_trade_notional_dollars(signal)
    options_bp = get_options_buying_power()
    if options_bp > 0 and notional > options_bp:
        reasons.append("insufficient_options_buying_power")

    return {
        "approved": len(reasons) == 0,
        "stage": "risk_policy",
        "reject_reasons": reasons,
        "risk_per_trade_pct": round(risk_per_trade_pct, 6),
        "portfolio_heat_pct": round(current_heat, 6),
        "projected_heat_pct": round(projected_heat, 6),
        "daily_realized_pnl_pct": round(safe_float(GLOBAL_STATE.get("daily_realized_pnl_pct", 0.0), 0.0), 6),
        "consecutive_losses": safe_int(GLOBAL_STATE.get("consecutive_losses", 0), 0),
        "trade_risk_dollars": round(trade_risk_dollars, 2),
        "options_buying_power": round(options_bp, 2),
        "notional_dollars": round(notional, 2),
        "same_ticker_count": same_ticker_count,
        "open_positions": len(open_positions),
    }


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

    return {
        "approved": len(reasons) == 0,
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
    text_blob = " ".join([str(signal.get("reason", "")), str(signal.get("public_reason", "")), str(signal.get("trigger", "")), str(signal.get("bias", "")), str(signal.get("entry", ""))]).lower()

    tags = []
    if explicit_regime:
        regime, score = explicit_regime, 0.90
        tags.append("explicit_regime")
    else:
        regime, score = "NORMAL", 0.55
        if any(k in text_blob for k in ["compression", "expansion", "squeeze", "breakout expansion"]):
            regime, score = "EXPANSION", 0.85
            tags.append("compression_expansion_language")
        if any(k in text_blob for k in ["trend", "trend day", "vwap reclaim", "higher low", "lower high", "break and hold", "retest hold"]):
            regime, score = "TREND", max(score, 0.80)
            tags.append("trend_language")
        if any(k in text_blob for k in ["chop", "range", "whipsaw", "inside range", "mean reversion chop"]):
            regime, score = "CHOP", 0.25
            tags.append("chop_language")
        if any(k in text_blob for k in ["cpi", "fomc", "powell", "fed", "event", "nfp", "earnings", "geopolitics", "news spike"]):
            regime, score = "EVENT", 0.40
            tags.append("event_language")

    if regime not in {"TREND", "EXPANSION", "NORMAL", "CHOP", "EVENT"}:
        regime = "NORMAL"
    return {"regime": regime, "regime_score": round(score, 4), "tags": tags}


def evaluate_regime(signal: Dict[str, Any]) -> Dict[str, Any]:
    inferred = infer_regime_from_signal(signal)
    if not ENABLE_REGIME_ENGINE:
        return {"approved": True, "stage": "regime_engine", "regime": inferred["regime"], "regime_score": inferred["regime_score"], "reject_reasons": [], "tags": inferred["tags"]}

    regime, regime_score, tags = inferred["regime"], inferred["regime_score"], inferred["tags"]
    reasons = []
    if regime_score < MIN_REGIME_SCORE:
        reasons.append("regime_score_too_low")
    if regime == "CHOP" and BLOCK_CHOP_REGIME:
        reasons.append("chop_regime_blocked")
    if regime == "EVENT" and not ALLOW_EVENT_REGIME:
        reasons.append("event_regime_blocked")
    if regime not in ALLOWED_REGIMES:
        reasons.append("regime_not_allowed")
    return {"approved": len(reasons) == 0, "stage": "regime_engine", "regime": regime, "regime_score": regime_score, "reject_reasons": reasons, "tags": tags}


def apply_regime_to_signal(signal: Dict[str, Any], regime_decision: Dict[str, Any]) -> Dict[str, Any]:
    x = deepcopy(signal)
    x["regime"] = regime_decision["regime"]
    x["regime_score"] = regime_decision["regime_score"]
    x["regime_tags"] = regime_decision.get("tags", [])
    return x


# =========================================================
# SIGNAL NORMALIZATION
# =========================================================
def normalize_confidence(conf) -> str:
    s = str(conf or "C").upper().strip()
    if s in {"A+", "A", "B", "C"}:
        return s
    if "A" in s:
        return "A"
    if "B" in s:
        return "B"
    return "C"


def normalize_direction(direction: Any) -> str:
    s = str(direction or "CALL").upper().strip()
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
    return True if ts <= 0 else (epoch() - ts) <= MAX_SIGNAL_AGE_SECONDS


def load_live_signal() -> Optional[Dict[str, Any]]:
    debug_file_lookup(SIGNAL_FILE)
    if not SIGNAL_FILE:
        return None
    if not file_exists(SIGNAL_FILE):
        log(f"❌ SIGNAL_FILE not found: {SIGNAL_FILE}")
        return None
    try:
        with open(SIGNAL_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
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
    except Exception as e:
        log(f"❌ Signal file watcher error: {e}")
    return False


# =========================================================
# MESSAGES
# =========================================================
def build_ai_reasoning_message(signal: Dict[str, Any]) -> str:
    size_decision = signal.get("size_decision", {}) if isinstance(signal.get("size_decision"), dict) else {}
    regime_text = f"\nRegime: {signal.get('regime')}\nRegime Score: {signal.get('regime_score', 'N/A')}" if signal.get("regime") else ""
    size_text = f"\nSized Qty: {signal.get('qty', 'N/A')}\nRisk Dollars: {size_decision.get('risk_dollars', 'N/A')}\nUnit Risk: {size_decision.get('unit_risk', 'N/A')}" if size_decision else ""

    macro_state = get_latest_macro_state()
    macro_text = ""
    if macro_state:
        macro_text = (
            f"\n\nMacro Context:"
            f"\nRisk State: {macro_state.get('risk_state', 'unknown')}"
            f"\nMacro Bias: {macro_state.get('macro_bias', 'unknown')}"
            f"\nVolatility State: {macro_state.get('volatility_state', 'unknown')}"
            f"\nMacro Drivers: {', '.join(macro_state.get('drivers', [])[:5]).replace('_', ' ') if macro_state.get('drivers') else 'none'}"
        )

    return (
        f"🧠 AI REASONING ALERT\nTicker: {signal['ticker']}\nSymbol: {signal['symbol']}\nDirection: {signal['direction']}\n"
        f"Underlying Price: {signal['price']}\nContract Price: {signal['contract_price']}\nConfidence: {signal['confidence']}\n"
        f"Bias: {signal['bias']}\nTimeframe: {signal['timeframe']}\nTrigger: {signal['trigger']}\nSource: {signal['source']}"
        f"{regime_text}{size_text}\n\nReasoning:\n{signal['reason']}"
        f"{macro_text}\n\n⏰ {now_ts()}"
    )


def build_free_message(signal: Dict[str, Any]) -> str:
    return (
        f"📊 FREE DAILY ALERT\nTicker: {signal['ticker']}\nDirection: {signal['direction']}\nUnderlying Price: {signal['price']}\n"
        f"Confidence: {signal['confidence']}\n\nSetup:\n{signal['public_reason']}\n\n⏰ {now_ts()}"
    )


def build_premium_message(signal: Dict[str, Any]) -> str:
    title = "💎 PREMIUM A SETUP" if signal["confidence"] in {"A", "A+"} else "⚠️ PREMIUM WATCH ALERT"
    regime_line = f"Regime: {signal.get('regime')} ({signal.get('regime_score', 'N/A')})\n" if signal.get("regime") else ""
    return (
        f"{title}\nTicker: {signal['ticker']}\nSymbol: {signal['symbol']}\nDirection: {signal['direction']}\n"
        f"Underlying Price: {signal['price']}\nContract Entry: {signal['entry_contract']}\nQty: {signal.get('qty', 'N/A')}\n{regime_line}"
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
    line2 = f"\nNote: {side_note}" if side_note else ""
    return (
        f"🟣 ORDER UPDATE\nLocal ID: {order.get('local_order_id', 'N/A')}\nBroker ID: {order.get('broker_order_id', 'N/A')}\n"
        f"Symbol: {order.get('symbol', 'N/A')}\nSide: {order.get('side', 'N/A')}\nQty Requested: {order.get('qty_requested', 'N/A')}\n"
        f"Qty Filled: {order.get('qty_filled', 'N/A')}\nAvg Fill: {order.get('avg_fill_price', 'N/A')}\nStatus: {order.get('status', 'unknown')}{line2}\n⏰ {now_ts()}"
    )


def build_position_open_message(position: Dict[str, Any]) -> str:
    return (
        f"🟢 POSITION OPENED\nID: {position['id']}\nMode: {position['mode']}\nTicker: {position['ticker']}\n"
        f"Symbol: {position['symbol']}\nDirection: {position['direction']}\nQty: {position['qty_open']}\n"
        f"Entry: {position['entry_price']}\nStop: {position['stop_price']}\nTP1: {position['tp1_price']}\nTP2: {position['tp2_price']}\nTrail %: {position['trail_pct']}\n⏰ {now_ts()}"
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


def build_block_message(title: str, signal: Dict[str, Any], reasons: List[str], extras: Optional[str] = None) -> str:
    msg = f"🚫 {title}\nTicker: {signal.get('ticker', 'N/A')}\nSymbol: {signal.get('symbol', 'N/A')}\nReasons: {', '.join(reasons) or 'unknown'}"
    if extras:
        msg += f"\n{extras}"
    msg += f"\n⏰ {now_ts()}"
    return msg


def build_reconciliation_message(report: Dict[str, Any]) -> str:
    mismatches = report.get("mismatches", [])
    details = "\n".join(f"- {m}" for m in mismatches[:20]) if mismatches else "- none"
    return f"🔄 STARTUP RECONCILIATION\nSafe: {report.get('safe_to_trade', False)}\nBroker Positions: {report.get('broker_position_count', 0)}\nBroker Orders: {report.get('broker_open_order_count', 0)}\nLocal Positions: {report.get('local_open_position_count', 0)}\nLocal Pending Orders: {report.get('local_pending_order_count', 0)}\nMismatches:\n{details}\n⏰ {now_ts()}"


def route_signal(signal: Dict[str, Any], state: Dict[str, Any]):
    if state.get("discord_enabled", True):
        send_to_discord(DISCORD_AI_WEBHOOK, build_ai_reasoning_message(signal), "AI")
        send_to_discord(DISCORD_FREE_WEBHOOK, build_free_message(signal), "FREE")
        send_to_discord(DISCORD_PREMIUM_WEBHOOK, build_premium_message(signal), "PREMIUM")
    if state.get("telegram_enabled", True):
        send_to_telegram(build_telegram_signal_message(signal))


# =========================================================
# POSITION STORE
# =========================================================
def next_position_id() -> int:
    GLOBAL_POSITIONS["last_position_id"] = safe_int(GLOBAL_POSITIONS.get("last_position_id", 0), 0) + 1
    return GLOBAL_POSITIONS["last_position_id"]


def make_local_position(signal: Dict[str, Any], mode: str) -> Dict[str, Any]:
    entry = safe_float(signal.get("entry_contract", 0), 0) or safe_float(signal.get("contract_price", 0), 0)
    qty = max(1, safe_int(signal.get("qty", DEFAULT_LIVE_QTY), DEFAULT_LIVE_QTY))
    stop_price = safe_float(signal.get("stop_contract", 0), 0) or round(entry * 0.70, 4)
    tp1_price = safe_float(signal.get("tp1_contract", 0), 0) or round(entry * 1.30, 4)
    tp2_price = safe_float(signal.get("tp2_contract", 0), 0) or round(entry * 1.60, 4)
    return {
        "id": next_position_id(),
        "signal_id": signal["signal_id"],
        "mode": mode,
        "broker_order_id": "",
        "client_order_id": "",
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
        "entry_filled": False if mode == "LIVE" else True,
        "avg_fill_price": 0.0 if mode == "LIVE" else entry,
        "filled_qty_total": 0 if mode == "LIVE" else qty,
        "pending_close_qty": 0,
    }


def save_new_position(position: Dict[str, Any]):
    GLOBAL_POSITIONS["open_positions"].append(position)
    save_positions(GLOBAL_POSITIONS)


def get_open_position_by_id(position_id: int) -> Optional[Dict[str, Any]]:
    for p in GLOBAL_POSITIONS.get("open_positions", []):
        if safe_int(p.get("id", 0), 0) == safe_int(position_id, 0):
            return p
    return None


def update_position_market_price(position: Dict[str, Any], new_price: float):
    if new_price <= 0:
        return
    position["last_price"] = new_price
    position["highest_price"] = max(position.get("highest_price", new_price), new_price)
    position["lowest_price"] = min(position.get("lowest_price", new_price), new_price)
    basis = safe_float(position.get("avg_fill_price", 0), 0) or safe_float(position.get("entry_price", 0), 0)
    position["pnl_pct"] = pct_change(basis, new_price)


def scale_out_local(position: Dict[str, Any], qty_to_close: int, fill_price: float, note: str) -> bool:
    available_qty = max(0, safe_int(position.get("qty_open", 0), 0) - safe_int(position.get("pending_close_qty", 0), 0))
    qty_to_close = int(max(0, min(qty_to_close, available_qty)))
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
    basis = safe_float(position.get("avg_fill_price", 0), 0) or safe_float(position.get("entry_price", 0), 0)
    position["realized_pnl_pct"] = pct_change(basis, position["exit_price"])
    position["notes"].append(note)

    reset_daily_risk_counters_if_needed(GLOBAL_STATE)
    realized_pct_decimal = position["realized_pnl_pct"] / 100.0
    GLOBAL_STATE["daily_realized_pnl_pct"] = safe_float(GLOBAL_STATE.get("daily_realized_pnl_pct", 0.0), 0.0) + realized_pct_decimal
    GLOBAL_STATE["consecutive_losses"] = safe_int(GLOBAL_STATE.get("consecutive_losses", 0), 0) + 1 if position["realized_pnl_pct"] < 0 else 0
    save_state(GLOBAL_STATE)

    GLOBAL_POSITIONS["open_positions"] = [p for p in GLOBAL_POSITIONS["open_positions"] if p["id"] != position["id"]]
    GLOBAL_POSITIONS["closed_positions"].append(position)
    save_positions(GLOBAL_POSITIONS)

    msg = build_position_close_message(position, note)
    send_to_telegram(msg)
    send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")


def recalc_position_from_fill(position: Dict[str, Any], fill_qty: int, fill_price: float):
    if fill_qty <= 0 or fill_price <= 0:
        return
    old_filled = safe_int(position.get("filled_qty_total", 0), 0)
    old_avg = safe_float(position.get("avg_fill_price", 0), 0)
    new_avg = weighted_avg_price(old_filled, old_avg, fill_qty, fill_price) if old_filled > 0 else fill_price
    position["filled_qty_total"] = old_filled + fill_qty
    position["avg_fill_price"] = round(new_avg, 4)
    position["entry_price"] = round(new_avg, 4)
    position["last_price"] = fill_price
    position["entry_filled"] = position["filled_qty_total"] > 0
    position["qty_total"] = max(position["qty_total"], position["filled_qty_total"])
    position["qty_open"] = max(position.get("qty_open", 0), position["filled_qty_total"] - position.get("qty_closed", 0))


# =========================================================
# EXECUTION
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
    if REQUIRE_OPTION_SYMBOL and signal.get("asset_class") == "option" and signal["symbol"] == signal["ticker"]:
        log("❌ LIVE BLOCKED: option signal missing actual option contract symbol")
        return False
    if signal["qty"] <= 0:
        return False
    if get_options_buying_power() > 0 and estimate_trade_notional_dollars(signal) > get_options_buying_power():
        log("❌ LIVE BLOCKED: not enough options buying power")
        return False
    return True


def open_paper_position(signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    position = make_local_position(signal, mode="PAPER")
    save_new_position(position)
    GLOBAL_STATE["paper_trade_count"] = safe_int(GLOBAL_STATE.get("paper_trade_count", 0), 0) + 1
    save_state(GLOBAL_STATE)
    msg = build_position_open_message(position)
    send_to_telegram(msg)
    send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
    return position


def submit_live_entry(signal: Dict[str, Any], position: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not ALLOW_LIVE_BUYS:
        log("❌ LIVE BUY BLOCKED: ALLOW_LIVE_BUYS=false")
        return None
    if not validate_live_signal_for_alpaca(signal):
        return None

    order_type = "limit" if signal.get("use_limit_entry", False) else "market"
    limit_price = safe_float(signal.get("limit_entry_price", 0), 0) if order_type == "limit" else None
    order_record = make_order_record(signal=signal, side="buy", qty=signal["qty"], mode="LIVE", order_type=order_type, limit_price=limit_price)
    order_record["position_id"] = position["id"]
    save_order_record(order_record)

    broker_order = alpaca_submit_order(
        symbol=signal["symbol"],
        qty=signal["qty"],
        side="buy",
        order_type=order_type,
        tif="day",
        limit_price=limit_price,
        client_order_id=order_record["client_order_id"],
    )
    if not broker_order:
        update_order_status(order_record, "rejected", "broker submit failed")
        return None

    apply_broker_order_snapshot(order_record, broker_order)
    update_order_status(order_record, order_record.get("status", "submitted"), "live entry submitted")
    position["broker_order_id"] = order_record.get("broker_order_id", "")
    position["client_order_id"] = order_record.get("client_order_id", "")
    save_positions(GLOBAL_POSITIONS)
    GLOBAL_STATE["live_trade_count"] = safe_int(GLOBAL_STATE.get("live_trade_count", 0), 0) + 1
    save_state(GLOBAL_STATE)
    msg = build_live_order_message(order_record, "LIVE ENTRY SUBMITTED")
    send_to_telegram(msg)
    send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
    return order_record


def open_live_position(signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    position = make_local_position(signal, mode="LIVE")
    save_new_position(position)
    order_record = submit_live_entry(signal, position)
    if not order_record:
        position["notes"].append("entry submit failed")
        save_positions(GLOBAL_POSITIONS)
        return None
    return position


def live_scale_out(position: Dict[str, Any], qty_to_close: int, note: str) -> bool:
    if not ALLOW_LIVE_SELLS:
        return False
    available_qty = max(0, safe_int(position.get("qty_open", 0), 0) - safe_int(position.get("pending_close_qty", 0), 0))
    qty_to_close = int(max(0, min(qty_to_close, available_qty)))
    if qty_to_close <= 0:
        return False
    signal_stub = {"signal_id": position.get("signal_id", ""), "ticker": position.get("ticker", ""), "symbol": position.get("symbol", "")}
    order_record = make_order_record(signal_stub, side="sell", qty=qty_to_close, mode="LIVE", order_type="market")
    order_record["position_id"] = position["id"]
    save_order_record(order_record)
    broker_order = alpaca_submit_order(symbol=position["symbol"], qty=qty_to_close, side="sell", order_type="market", tif="day", client_order_id=order_record["client_order_id"])
    if not broker_order:
        update_order_status(order_record, "rejected", "scale out submit failed")
        return False
    apply_broker_order_snapshot(order_record, broker_order)
    update_order_status(order_record, order_record.get("status", "submitted"), note)
    position["pending_close_qty"] = safe_int(position.get("pending_close_qty", 0), 0) + qty_to_close
    save_positions(GLOBAL_POSITIONS)
    msg = build_live_order_message(order_record, note)
    send_to_telegram(msg)
    send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
    return True


def live_close_position(position: Dict[str, Any], note: str) -> bool:
    if not ALLOW_LIVE_SELLS:
        return False
    qty_open = max(0, safe_int(position.get("qty_open", 0), 0) - safe_int(position.get("pending_close_qty", 0), 0))
    if qty_open <= 0:
        return False
    signal_stub = {"signal_id": position.get("signal_id", ""), "ticker": position.get("ticker", ""), "symbol": position.get("symbol", "")}
    order_record = make_order_record(signal_stub, side="sell", qty=qty_open, mode="LIVE", order_type="market")
    order_record["position_id"] = position["id"]
    save_order_record(order_record)
    broker_order = alpaca_close_position_market(position["symbol"], qty=qty_open)
    if not broker_order:
        update_order_status(order_record, "rejected", "live close submit failed")
        return False
    apply_broker_order_snapshot(order_record, broker_order)
    update_order_status(order_record, order_record.get("status", "submitted"), note)
    position["pending_close_qty"] = safe_int(position.get("pending_close_qty", 0), 0) + qty_open
    save_positions(GLOBAL_POSITIONS)
    msg = build_live_order_message(order_record, note)
    send_to_telegram(msg)
    send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
    return True


# =========================================================
# ORDER/POSITION RECONCILIATION
# =========================================================
def sync_live_positions_from_alpaca():
    ensure_globals_initialized()
    if not ALPACA_SYNC_POSITIONS or not ENABLE_ALPACA or not GLOBAL_STATE.get("alpaca_enabled", False):
        return
    broker_positions = alpaca_list_positions()
    if broker_positions is None:
        return
    local_live = [p for p in GLOBAL_POSITIONS["open_positions"] if p.get("mode") == "LIVE"]
    local_by_symbol = {p["symbol"]: p for p in local_live}

    for bp in broker_positions:
        symbol = str(bp.get("symbol", "")).strip()
        if not symbol:
            continue
        if symbol in local_by_symbol:
            local_pos = local_by_symbol[symbol]
            market_price = safe_float(bp.get("current_price", local_pos.get("last_price", 0)), local_pos.get("last_price", 0))
            qty = abs(safe_int(bp.get("qty", local_pos.get("qty_open", 0)), local_pos.get("qty_open", 0)))
            avg_entry = safe_float(bp.get("avg_entry_price", local_pos.get("avg_fill_price", local_pos.get("entry_price", 0))), local_pos.get("entry_price", 0))
            local_pos["avg_fill_price"] = avg_entry
            local_pos["entry_price"] = avg_entry
            local_pos["qty_open"] = qty
            local_pos["entry_filled"] = qty > 0
            local_pos["filled_qty_total"] = max(qty + safe_int(local_pos.get("qty_closed", 0), 0), safe_int(local_pos.get("filled_qty_total", 0), 0))
            update_position_market_price(local_pos, market_price)
        else:
            log(f"⚠️ Broker has open position not in local state: {symbol}")

    save_positions(GLOBAL_POSITIONS)


def reconcile_order_fills_into_positions():
    ensure_globals_initialized()
    refresh_open_order_states()
    positions_changed = False
    orders_changed = False
    for order in GLOBAL_ORDERS.get("orders", []):
        pid = safe_int(order.get("position_id", 0), 0)
        if pid <= 0:
            continue
        position = get_open_position_by_id(pid)
        if not position:
            continue
        status = str(order.get("status", "")).lower()
        filled_qty = safe_int(order.get("qty_filled", 0), 0)
        avg_fill = safe_float(order.get("avg_fill_price", 0), 0)
        last_applied = safe_int(order.get("applied_filled_qty", 0), 0)
        delta_fill = max(0, filled_qty - last_applied)
        if delta_fill <= 0:
            continue

        if str(order.get("side", "")).lower() == "buy":
            recalc_position_from_fill(position, delta_fill, avg_fill)
        else:
            scale_out_local(position, delta_fill, avg_fill or position.get("last_price", 0), f"sell fill applied from order {order.get('local_order_id')}")
            position["pending_close_qty"] = max(0, safe_int(position.get("pending_close_qty", 0), 0) - delta_fill)

        order["applied_filled_qty"] = filled_qty
        orders_changed = True
        positions_changed = True

        if status == "filled" and str(order.get("side", "")).lower() == "sell" and position.get("qty_open", 0) <= 0:
            finalize_close_position(position, avg_fill or position.get("last_price", 0), f"Order {order.get('local_order_id')} fully closed position")
            positions_changed = True
    if orders_changed:
        save_orders(GLOBAL_ORDERS)
    if positions_changed:
        save_positions(GLOBAL_POSITIONS)


def build_boot_reconciliation_report() -> Dict[str, Any]:
    ensure_globals_initialized()
    broker_positions = alpaca_list_positions() if ENABLE_ALPACA and GLOBAL_STATE.get("alpaca_enabled", False) and alpaca_ready() else []
    broker_orders = alpaca_list_orders(status="open") if ENABLE_ALPACA and GLOBAL_STATE.get("alpaca_enabled", False) and alpaca_ready() else []
    local_open_positions = GLOBAL_POSITIONS.get("open_positions", [])
    local_pending_orders = [o for o in GLOBAL_ORDERS.get("orders", []) if str(o.get("status", "")).lower() not in {"filled", "canceled", "rejected", "expired"}]

    broker_symbols = {str(p.get("symbol", "")).strip() for p in broker_positions if str(p.get("symbol", "")).strip()}
    local_live_symbols = {str(p.get("symbol", "")).strip() for p in local_open_positions if p.get("mode") == "LIVE"}
    broker_order_ids = {str(o.get("id", "")).strip() for o in broker_orders if str(o.get("id", "")).strip()}
    local_broker_order_ids = {str(o.get("broker_order_id", "")).strip() for o in local_pending_orders if str(o.get("broker_order_id", "")).strip()}

    mismatches = []
    for sym in sorted(broker_symbols - local_live_symbols):
        mismatches.append(f"broker position exists but local live position missing: {sym}")
    for sym in sorted(local_live_symbols - broker_symbols):
        mismatches.append(f"local live position exists but broker position missing: {sym}")
    for oid in sorted(broker_order_ids - local_broker_order_ids):
        mismatches.append(f"broker open order exists but local pending order missing: {oid}")
    for oid in sorted(local_broker_order_ids - broker_order_ids):
        mismatches.append(f"local pending order exists but broker open order missing: {oid}")

    safe_to_trade = len(mismatches) == 0
    report = {
        "generated_at": epoch(),
        "safe_to_trade": safe_to_trade,
        "broker_position_count": len(broker_positions),
        "broker_open_order_count": len(broker_orders),
        "local_open_position_count": len(local_open_positions),
        "local_pending_order_count": len(local_pending_orders),
        "mismatches": mismatches,
    }
    GLOBAL_RECON["last_boot_reconciliation_at"] = epoch()
    GLOBAL_RECON["last_boot_report"] = report
    save_recon(GLOBAL_RECON)
    return report


def startup_reconcile_and_gate():
    report = build_boot_reconciliation_report()
    msg = build_reconciliation_message(report)
    send_to_telegram(msg)
    send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
    if report.get("safe_to_trade", False):
        clear_reconciliation_block()
        return
    reason = "; ".join(report.get("mismatches", [])[:5]) or "startup reconciliation mismatch"
    if STRICT_STARTUP_RECON or BLOCK_NEW_TRADES_ON_RECON_MISMATCH:
        set_reconciliation_block(reason)
        log(f"🚫 Trading blocked by startup reconciliation: {reason}")


# =========================================================
# =========================================================
# STEP 8 MARKET PRICE FEED / LIVE POSITION PRICE UPDATES
# =========================================================
def load_market_prices(symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Step 10 market-data router.

    Priority:
    1) Live provider if configured/available (Twelve Data or Alpaca Data)
    2) MARKET_DATA_FILE fallback for testing/manual override

    This keeps Step 8 + Step 9 working even when a live provider fails.
    """
    if not ENABLE_MARKET_DATA:
        return {}

    prices = {}

    # 1) File fallback/manual override still supported.
    if MARKET_DATA_FILE and file_exists(MARKET_DATA_FILE):
        try:
            with open(MARKET_DATA_FILE, "r", encoding="utf-8") as f:
                file_data = json.load(f)
            if isinstance(file_data, dict):
                prices.update(file_data)
                debug(f"MARKET DATA FILE READ from {MARKET_DATA_FILE}: {file_data}")
            else:
                log(f"❌ MARKET_DATA_FILE must contain a JSON object: {MARKET_DATA_FILE}")
        except Exception as e:
            log(f"❌ Failed reading market data file {MARKET_DATA_FILE}: {e}")
    elif MARKET_DATA_FILE:
        debug(f"MARKET_DATA_FILE not found yet: {MARKET_DATA_FILE}")

    # 2) Live fetch for requested symbols. Live values overwrite file values.
    requested = []
    if symbols:
        for s in symbols:
            sym = str(s or "").strip()
            if sym and sym not in requested:
                requested.append(sym)

    if requested and MARKET_DATA_PROVIDER not in {"file", "manual", "off", "disabled"}:
        for sym in requested:
            # IMPORTANT STEP 10 FIX:
            # Option contracts like QQQ240426C00380000 should NOT be sent to stock quote endpoints.
            # Most providers reject those compact option symbols. For contract pricing, keep using
            # MARKET_DATA_FILE until a real options-chain/option-quote adapter is added. We can still
            # fetch the underlying ticker for context/debug without overwriting the contract price.
            underlying = get_underlying_from_option_symbol(sym)
            if underlying:
                if has_valid_file_price(prices, sym):
                    debug(f"OPTION CONTRACT PRICE READ FROM FILE | {sym}: {get_market_price_for_symbol(sym, prices)[0]}")
                else:
                    debug(f"OPTION CONTRACT DETECTED | {sym}. No file contract price found. Skipping stock quote endpoints and fetching underlying {underlying} only.")

                underlying_price = get_live_market_price(underlying)
                if underlying_price > 0:
                    prices[f"__UNDERLYING__:{sym}"] = {
                        "price": underlying_price,
                        "timestamp": epoch(),
                        "source": f"{MARKET_DATA_PROVIDER}:underlying:{underlying}",
                    }
                    debug(f"UNDERLYING LIVE MARKET DATA READ | {underlying} for {sym}: {underlying_price}")
                continue

            live_price = get_live_market_price(sym)
            if live_price > 0:
                prices[sym] = {"price": live_price, "timestamp": epoch(), "source": MARKET_DATA_PROVIDER}
                debug(f"LIVE MARKET DATA READ | {sym}: {live_price}")

    return prices


def cache_get_market_price(symbol: str) -> Tuple[float, int, str]:
    item = MARKET_PRICE_CACHE.get(str(symbol).upper().strip(), {})
    if not isinstance(item, dict):
        return 0.0, 0, ""
    price = safe_float(item.get("price", 0), 0)
    ts = safe_int(item.get("timestamp", 0), 0)
    source = str(item.get("source", ""))
    if price > 0 and ts > 0 and (epoch() - ts) <= LIVE_PRICE_CACHE_SECONDS:
        return price, ts, source
    return 0.0, 0, ""


def cache_set_market_price(symbol: str, price: float, source: str):
    if not symbol or price <= 0:
        return
    MARKET_PRICE_CACHE[str(symbol).upper().strip()] = {
        "price": round(float(price), 6),
        "timestamp": epoch(),
        "source": source,
    }


def parse_occ_option_symbol(symbol: str) -> Dict[str, Any]:
    """
    Parses compact OCC-style option symbols like QQQ240426C00380000.
    Returns metadata only. This does NOT mean the data vendor accepts that symbol.
    """
    raw = str(symbol or "").upper().strip()
    match = re.match(r"^([A-Z]{1,6})(\d{6})([CP])(\d{8})$", raw)
    if not match:
        return {}
    underlying, yymmdd, option_type, strike_raw = match.groups()
    try:
        strike = int(strike_raw) / 1000.0
    except Exception:
        strike = 0.0
    return {
        "symbol": raw,
        "underlying": underlying,
        "expiry_yymmdd": yymmdd,
        "option_type": "CALL" if option_type == "C" else "PUT",
        "strike": strike,
        "is_option_contract": True,
    }


def is_option_contract_symbol(symbol: str) -> bool:
    return bool(parse_occ_option_symbol(symbol))


def get_underlying_from_option_symbol(symbol: str) -> str:
    parsed = parse_occ_option_symbol(symbol)
    return str(parsed.get("underlying", "") or "").upper().strip()


def has_valid_file_price(prices: Dict[str, Any], symbol: str) -> bool:
    price, ts = get_market_price_for_symbol(symbol, prices)
    if price <= 0:
        return False
    if ts > 0 and market_price_is_stale(ts):
        return False
    return True


def extract_price_from_payload(payload: Any) -> float:
    """Flexible parser for Twelve Data / Alpaca / generic quote payloads."""
    if not isinstance(payload, dict):
        return 0.0

    for container_key in ("quotes", "snapshots", "data"):
        container = payload.get(container_key)
        if isinstance(container, dict) and container:
            for _, inner in container.items():
                p = extract_price_from_payload(inner)
                if p > 0:
                    return p

    for list_key in ("results", "bars", "trades"):
        values = payload.get(list_key)
        if isinstance(values, list) and values:
            p = extract_price_from_payload(values[0])
            if p > 0:
                return p

    for key in ("price", "last", "mark", "mid", "close", "c", "last_price", "ask_price", "bid_price", "ap", "bp", "p"):
        p = safe_float(payload.get(key), 0)
        if p > 0:
            return p

    for key in ("latestQuote", "latest_quote", "quote", "latestTrade", "latest_trade", "trade"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            bid = safe_float(nested.get("bp", nested.get("bid_price", nested.get("bid", 0))), 0)
            ask = safe_float(nested.get("ap", nested.get("ask_price", nested.get("ask", 0))), 0)
            if bid > 0 and ask > 0:
                return round((bid + ask) / 2.0, 6)
            p = extract_price_from_payload(nested)
            if p > 0:
                return p

    return 0.0


def fetch_twelve_data_price(symbol: str) -> float:
    """Fetches a quote/price from Twelve Data. Falls back safely if unsupported."""
    if not TWELVE_DATA_API_KEY or not symbol:
        return 0.0
    try:
        r = requests.get(
            f"{TWELVE_DATA_BASE_URL}/quote",
            params={"symbol": symbol, "apikey": TWELVE_DATA_API_KEY},
            timeout=10,
        )
        if r.status_code != 200:
            debug(f"Twelve Data quote failed for {symbol}: {r.status_code} {r.text[:200]}")
            return 0.0
        data = r.json()
        if isinstance(data, dict) and data.get("status") == "error":
            debug(f"Twelve Data returned error for {symbol}: {data}")
            return 0.0
        return extract_price_from_payload(data)
    except Exception as e:
        debug(f"Twelve Data exception for {symbol}: {e}")
        return 0.0


def alpaca_data_headers() -> Dict[str, str]:
    return {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
        "Content-Type": "application/json",
    }


def fetch_alpaca_data_price(symbol: str) -> float:
    """
    Attempts Alpaca Data price fetch with flexible endpoint fallbacks.
    If your Alpaca plan/endpoint does not support options data, this returns 0
    and the engine falls back to Twelve Data or market_prices.json.
    """
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY or not ALPACA_DATA_BASE_URL or not symbol:
        return 0.0

    candidate_requests = [
        ("/v1beta1/options/quotes/latest", {"symbols": symbol}),
        (f"/v1beta1/options/snapshots/{symbol}", {}),
        ("/v2/stocks/quotes/latest", {"symbols": symbol}),
        (f"/v2/stocks/{symbol}/quotes/latest", {}),
    ]

    for path, params in candidate_requests:
        try:
            r = requests.get(
                f"{ALPACA_DATA_BASE_URL}{path}",
                headers=alpaca_data_headers(),
                params=params,
                timeout=10,
            )
            if r.status_code != 200:
                debug(f"Alpaca data failed {path} for {symbol}: {r.status_code} {r.text[:200]}")
                continue
            price = extract_price_from_payload(r.json())
            if price > 0:
                return price
        except Exception as e:
            debug(f"Alpaca data exception {path} for {symbol}: {e}")
    return 0.0


def get_live_market_price(symbol: str) -> float:
    """Step 10 live price router with cache + provider fallback.

    Safety rule: this function prices equities/underlyings only. Compact OCC-style
    option contracts are intentionally not sent to stock quote endpoints.
    """
    symbol = str(symbol or "").strip().upper()
    if not symbol:
        return 0.0

    if is_option_contract_symbol(symbol):
        debug(f"Skipping live stock quote lookup for option contract symbol: {symbol}")
        return 0.0

    cached_price, _, cached_source = cache_get_market_price(symbol)
    if cached_price > 0:
        debug(f"Using cached live price for {symbol}: {cached_price} from {cached_source}")
        return cached_price

    if MARKET_DATA_PROVIDER == "auto":
        providers = ["alpaca", "twelvedata"]
    elif MARKET_DATA_PROVIDER in {"alpaca", "twelvedata"}:
        providers = [MARKET_DATA_PROVIDER]
    else:
        return 0.0

    for provider in providers:
        price = 0.0
        if provider == "alpaca":
            price = fetch_alpaca_data_price(symbol)
        elif provider == "twelvedata":
            price = fetch_twelve_data_price(symbol)
        if price > 0:
            cache_set_market_price(symbol, price, provider)
            return price

    return 0.0

def parse_market_price_value(value: Any) -> Tuple[float, int]:
    """Returns (price, timestamp). Timestamp can be 0 if not supplied."""
    if isinstance(value, dict):
        price = safe_float(value.get("price", value.get("last", value.get("mark", value.get("mid", 0)))), 0)
        ts = safe_int(value.get("timestamp", value.get("ts", value.get("updated_at", 0))), 0)
        return price, ts
    return safe_float(value, 0), 0


def get_market_price_for_symbol(symbol: str, prices: Dict[str, Any]) -> Tuple[float, int]:
    if not symbol or not isinstance(prices, dict):
        return 0.0, 0
    direct = prices.get(symbol)
    if direct is not None:
        return parse_market_price_value(direct)
    symbol_upper = str(symbol).upper().strip()
    for key, value in prices.items():
        if str(key).upper().strip() == symbol_upper:
            return parse_market_price_value(value)
    return 0.0, 0


def market_price_is_stale(ts: int) -> bool:
    if ts <= 0:
        return False
    return (epoch() - ts) > MARKET_DATA_STALE_SECONDS


def maybe_send_price_update(position: Dict[str, Any], old_price: float, new_price: float):
    if not SEND_PRICE_UPDATE_ALERTS:
        return
    last_alert = safe_int(position.get("last_price_alert_at", 0), 0)
    if (epoch() - last_alert) < PRICE_UPDATE_ALERT_SECONDS:
        return
    position["last_price_alert_at"] = epoch()
    note = f"Price update: {old_price} -> {new_price}"
    msg = build_position_update_message(position, note)
    send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
    send_to_telegram(msg)


def update_positions_from_market_prices() -> int:
    """
    Key Step 8 loop hook. Reads market_prices.json and updates open positions.
    Then manage_open_positions() can trigger TP1, TP2, breakeven, trailing stop, and closes.
    """
    ensure_globals_initialized()
    if not ENABLE_MARKET_DATA:
        debug("Market data disabled; skipping update_positions_from_market_prices")
        return 0
    open_positions = GLOBAL_POSITIONS.get("open_positions", [])
    if not open_positions:
        return 0
    symbols = [str(p.get("symbol", "")).strip() for p in open_positions if str(p.get("symbol", "")).strip()]
    prices = load_market_prices(symbols)
    if not prices:
        debug("No market prices loaded; open positions were not repriced")
        return 0
    updated = 0
    for position in open_positions:
        symbol = str(position.get("symbol", "")).strip()
        if not symbol:
            continue
        new_price, price_ts = get_market_price_for_symbol(symbol, prices)
        if new_price <= 0:
            debug(f"No valid market price found for open position symbol: {symbol}")
            continue
        if market_price_is_stale(price_ts):
            debug(f"Market price stale for {symbol}; ts={price_ts}; current={epoch()}")
            continue
        old_price = safe_float(position.get("last_price", 0), 0)
        if old_price != new_price:
            update_position_market_price(position, new_price)
            position["last_market_price_update_at"] = epoch()
            price_source = "live" if isinstance(prices.get(symbol), dict) and prices.get(symbol, {}).get("source") else MARKET_DATA_FILE
            position["last_market_price_source"] = price_source
            updated += 1
            log(f"📈 Updated position price | {symbol}: {old_price} -> {new_price} | source={price_source}")
            maybe_send_price_update(position, old_price, new_price)
    if updated > 0:
        save_positions(GLOBAL_POSITIONS)
    return updated


# POSITION MANAGEMENT
# =========================================================
def manage_open_positions(incoming_signal: Optional[Dict[str, Any]] = None):
    if not AUTO_MANAGE_POSITIONS:
        debug("AUTO_MANAGE_POSITIONS disabled; skipping manage_open_positions")
        return
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

        if position["mode"] == "LIVE" and not position.get("entry_filled", False):
            continue

        if AUTO_TP_ENABLED and not position["tp1_hit"] and live_price >= position["tp1_price"]:
            qty1 = min(max(1, math.floor(position["qty_total"] * position["scale1_pct"])), position["qty_open"])
            if qty1 > 0:
                ok = live_scale_out(position, qty1, "TP1 HIT - live scale-out") if position["mode"] == "LIVE" else scale_out_local(position, qty1, live_price, "TP1 HIT - paper scale-out")
                if ok:
                    position["tp1_hit"] = True
                    if AUTO_BREAKEVEN_ENABLED and position.get("break_even_after_tp1", False):
                        position["stop_price"] = max(position["stop_price"], position.get("avg_fill_price", position["entry_price"]))
                    msg = build_position_update_message(position, "TP1 HIT")
                    send_to_telegram(msg)
                    send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")

        if AUTO_TP_ENABLED and not position["tp2_hit"] and live_price >= position["tp2_price"]:
            qty2 = min(max(1, math.floor(position["qty_total"] * position["scale2_pct"])), position["qty_open"])
            if qty2 > 0:
                ok = live_scale_out(position, qty2, "TP2 HIT - live scale-out") if position["mode"] == "LIVE" else scale_out_local(position, qty2, live_price, "TP2 HIT - paper scale-out")
                if ok:
                    position["tp2_hit"] = True
                    msg = build_position_update_message(position, "TP2 HIT")
                    send_to_telegram(msg)
                    send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")

        entry_price = safe_float(position.get("avg_fill_price", 0), 0) or safe_float(position.get("entry_price", 0), 0)
        highest_price = safe_float(position.get("highest_price", live_price), live_price)
        trail_pct = safe_float(position.get("trail_pct", DEFAULT_TRAIL_PCT), DEFAULT_TRAIL_PCT)
        trailing_allowed = AUTO_TRAILING_STOP_ENABLED and (not TRAIL_ONLY_AFTER_TP1 or position.get("tp1_hit", False))
        if trailing_allowed and highest_price > entry_price and trail_pct > 0:
            profit_open = highest_price - entry_price
            trailed_stop = highest_price - (profit_open * trail_pct)
            if trailed_stop > position["stop_price"]:
                old_stop = position["stop_price"]
                position["stop_price"] = round(trailed_stop, 4)
                debug(f"Trailing stop raised for {position.get('symbol')}: {old_stop} -> {position['stop_price']}")

        if live_price <= position["stop_price"]:
            if position["mode"] == "LIVE":
                live_close_position(position, "STOP HIT / trailing stop")
            else:
                finalize_close_position(position, live_price, "STOP HIT / trailing stop")
            continue

        if position["mode"] == "PAPER" and position["qty_open"] <= 0:
            finalize_close_position(position, live_price, "All size scaled out")

    save_positions(GLOBAL_POSITIONS)



# =========================================================
# STEP 9 ENTRY LOCK / NO CHASING SYSTEM
# =========================================================
def evaluate_entry_lock(signal: Dict[str, Any]) -> Dict[str, Any]:
    """
    Blocks late/chasing entries before the engine opens a paper/live position.
    This protects the system from taking a signal after the option contract
    has already moved too far away from the planned entry.
    """
    if not ENABLE_ENTRY_LOCK:
        return {
            "approved": True,
            "stage": "entry_lock",
            "reject_reasons": [],
            "live_price": 0.0,
            "max_allowed_entry": 0.0,
            "signal_age_seconds": 0,
            "reward_to_risk_at_live_price": 0.0,
        }

    reasons = []
    entry = safe_float(signal.get("entry_contract", 0), 0)
    stop = safe_float(signal.get("stop_contract", 0), 0)
    tp1 = safe_float(signal.get("tp1_contract", 0), 0)
    ts = safe_int(signal.get("timestamp", 0), 0)
    signal_age = max(0, epoch() - ts) if ts > 0 else 0

    if ts > 0 and signal_age > MAX_ENTRY_AGE_SECONDS:
        reasons.append("entry_window_expired")

    signal_symbol = str(signal.get("symbol", "")).strip()
    prices = load_market_prices([signal_symbol] if signal_symbol else None)
    live_price, price_ts = get_market_price_for_symbol(signal_symbol, prices)

    if price_ts > 0 and market_price_is_stale(price_ts):
        reasons.append("live_price_stale")

    if live_price <= 0:
        if REQUIRE_PRICE_FOR_ENTRY_LOCK:
            reasons.append("missing_live_price_for_entry_lock")
        live_price = entry

    if entry <= 0:
        reasons.append("invalid_entry_for_entry_lock")

    max_allowed_entry = entry * (1.0 + MAX_ENTRY_SLIPPAGE_PCT) if entry > 0 else 0.0
    if entry > 0 and live_price > max_allowed_entry:
        reasons.append("YOU_ARE_CHASING_live_price_above_allowed_entry")

    rr_live = 0.0
    live_unit_risk = max(live_price - stop, 0.0)
    if ENTRY_LOCK_RR_CHECK:
        if stop <= 0:
            reasons.append("invalid_stop_for_live_entry")
        elif stop >= live_price:
            reasons.append("stop_not_below_live_entry")
        elif tp1 <= live_price:
            reasons.append("tp1_not_above_live_entry")
        elif live_unit_risk > 0:
            rr_live = (tp1 - live_price) / live_unit_risk
            if rr_live < MIN_LIVE_ENTRY_RR_RATIO:
                reasons.append("live_entry_reward_to_risk_too_low")

    return {
        "approved": len(reasons) == 0,
        "stage": "entry_lock",
        "reject_reasons": reasons,
        "live_price": round(live_price, 4),
        "max_allowed_entry": round(max_allowed_entry, 4),
        "signal_age_seconds": signal_age,
        "reward_to_risk_at_live_price": round(rr_live, 4),
    }


def apply_entry_lock_to_signal(signal: Dict[str, Any], entry_lock_decision: Dict[str, Any]) -> Dict[str, Any]:
    """Optionally reprices the signal to the live contract mark before sizing/execution."""
    x = deepcopy(signal)
    x["entry_lock_decision"] = entry_lock_decision
    live_price = safe_float(entry_lock_decision.get("live_price", 0), 0)
    if REPRICE_ENTRY_TO_LIVE_PRICE and live_price > 0:
        x["entry_contract"] = live_price
        x["contract_price"] = live_price
        x["live_entry_price"] = live_price
    return x

# =========================================================
# SIGNAL HANDLER
# =========================================================
def should_route_signal(signal: Dict[str, Any]) -> bool:
    new_hash = signal_hash(signal)
    if new_hash == GLOBAL_STATE.get("last_signal_hash", ""):
        return False
    recent_hashes = GLOBAL_STATE.get("recent_signal_hashes", [])
    if isinstance(recent_hashes, list) and new_hash in recent_hashes:
        return False
    return True


def handle_new_signal(signal: Dict[str, Any]):
    if not GLOBAL_STATE.get("engine_enabled", True) or GLOBAL_STATE.get("kill_switch", False) or GLOBAL_STATE.get("bot_paused", False):
        return
    if GLOBAL_STATE.get("reconciliation_required", False):
        msg = f"🚫 NEW TRADE BLOCKED\nReason: {GLOBAL_STATE.get('reconciliation_block_reason', 'reconciliation required')}\n⏰ {now_ts()}"
        send_to_telegram(msg)
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        return
    if not should_route_signal(signal):
        manage_open_positions(signal)
        return

    validation_decision = validate_signal(signal)
    if not validation_decision["approved"]:
        msg = build_block_message("VALIDATION BLOCKED SIGNAL", signal, validation_decision["reject_reasons"], f"Reward/Risk: {validation_decision.get('reward_to_risk', 0.0)}")
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_telegram(msg)
        return

    entry_lock_decision = evaluate_entry_lock(signal)
    if not entry_lock_decision["approved"]:
        extras = (
            f"Live Price: {entry_lock_decision.get('live_price')} | "
            f"Max Allowed: {entry_lock_decision.get('max_allowed_entry')} | "
            f"Signal Age: {entry_lock_decision.get('signal_age_seconds')}s | "
            f"Live RR: {entry_lock_decision.get('reward_to_risk_at_live_price')}"
        )
        msg = build_block_message("ENTRY LOCK BLOCKED SIGNAL", signal, entry_lock_decision["reject_reasons"], extras)
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_telegram(msg)
        return

    entry_locked_signal = apply_entry_lock_to_signal(signal, entry_lock_decision)

    regime_decision = evaluate_regime(entry_locked_signal)
    if not regime_decision["approved"]:
        msg = build_block_message("REGIME BLOCKED SIGNAL", signal, regime_decision["reject_reasons"], f"Regime: {regime_decision.get('regime')} | Score: {regime_decision.get('regime_score')}")
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_telegram(msg)
        return

    regime_signal = apply_regime_to_signal(entry_locked_signal, regime_decision)
    size_decision = size_signal_by_stop(regime_signal)
    if not size_decision["approved"]:
        msg = build_block_message("SIZING BLOCKED SIGNAL", regime_signal, size_decision["reject_reasons"], f"Raw Size: {size_decision.get('raw_size')} | Final Size: {size_decision.get('final_size')}")
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_telegram(msg)
        return

    sized_signal = apply_size_decision_to_signal(regime_signal, size_decision)
    risk_decision = evaluate_risk_policy(sized_signal)
    if not risk_decision["approved"]:
        msg = build_block_message("RISK BLOCKED SIGNAL", sized_signal, risk_decision["reject_reasons"], f"Risk %: {round(risk_decision.get('risk_per_trade_pct', 0.0)*100, 3)} | Heat %: {round(risk_decision.get('portfolio_heat_pct', 0.0)*100, 3)}")
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_telegram(msg)
        return

    portfolio_decision = evaluate_portfolio_risk(sized_signal)
    if not portfolio_decision["approved"]:
        msg = build_block_message("PORTFOLIO BLOCKED SIGNAL", sized_signal, portfolio_decision["reject_reasons"], f"Projected Heat %: {round(portfolio_decision.get('projected_heat_pct', 0.0)*100, 3)}")
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_telegram(msg)
        return

    route_signal(sized_signal, GLOBAL_STATE)
    sig_hash = signal_hash(signal)
    GLOBAL_STATE["last_signal_hash"] = sig_hash
    GLOBAL_STATE["last_signal_time"] = epoch()
    GLOBAL_STATE["signal_count"] = safe_int(GLOBAL_STATE.get("signal_count", 0), 0) + 1
    append_recent_signal_hash(GLOBAL_STATE, sig_hash)
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
    macro_state = get_latest_macro_state()
    macro_line = "No macro snapshot loaded"
    if macro_state:
        macro_line = (
            f"{macro_state.get('risk_state', 'unknown')} | "
            f"{macro_state.get('macro_bias', 'unknown')} | "
            f"vol={macro_state.get('volatility_state', 'unknown')}"
        )

    return (
        f"🤖 {BOT_NAME} STATUS\nEngine Enabled: {GLOBAL_STATE['engine_enabled']}\nPaper Enabled: {GLOBAL_STATE['paper_enabled']}\n"
        f"Discord Enabled: {GLOBAL_STATE['discord_enabled']}\nTelegram Enabled: {GLOBAL_STATE['telegram_enabled']}\n"
        f"Alpaca Enabled: {GLOBAL_STATE['alpaca_enabled']}\nKill Switch: {GLOBAL_STATE.get('kill_switch', False)}\n"
        f"Bot Paused: {GLOBAL_STATE.get('bot_paused', False)}\nRecon Block: {GLOBAL_STATE.get('reconciliation_required', False)}\n"
        f"Daily Realized PnL %: {round(safe_float(GLOBAL_STATE.get('daily_realized_pnl_pct', 0.0), 0.0) * 100, 2)}\n"
        f"Consecutive Losses: {GLOBAL_STATE.get('consecutive_losses', 0)}\nPortfolio Heat %: {round(portfolio_heat_pct() * 100, 2)}\n"
        f"Signals Routed: {GLOBAL_STATE['signal_count']}\nPaper Trades: {GLOBAL_STATE['paper_trade_count']}\nLive Trades: {GLOBAL_STATE['live_trade_count']}\n"
        f"Open Positions: {len(GLOBAL_POSITIONS['open_positions'])}\nClosed Positions: {len(GLOBAL_POSITIONS['closed_positions'])}\n"
        f"Tracked Orders: {len(GLOBAL_ORDERS['orders'])}\n"
        f"Macro: {macro_line}\n"
        f"⏰ {now_ts()}"
    )


def build_positions_text() -> str:
    if not GLOBAL_POSITIONS["open_positions"]:
        return f"📭 No open positions.\n⏰ {now_ts()}"
    lines = ["📌 OPEN POSITIONS"]
    for p in GLOBAL_POSITIONS["open_positions"]:
        lines.append(f"ID {p['id']} | {p['mode']} | {p['symbol']} | Entry {p['entry_price']} | AvgFill {p.get('avg_fill_price', 0)} | Live {p['last_price']} | PnL {round(p['pnl_pct'], 2)}% | Qty {p['qty_open']}")
    lines.append(f"⏰ {now_ts()}")
    return "\n".join(lines)


def build_orders_text() -> str:
    orders = GLOBAL_ORDERS.get("orders", [])[-10:]
    if not orders:
        return f"📭 No tracked orders.\n⏰ {now_ts()}"
    lines = ["🧾 RECENT ORDERS"]
    for o in orders:
        lines.append(f"Local {o.get('local_order_id')} | {o.get('symbol')} | {o.get('side')} | req {o.get('qty_requested')} | fill {o.get('qty_filled')} | {o.get('status')}")
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
    send_to_telegram("✅ All open positions close instructions sent.")


def handle_telegram_command(text: str):
    cmd = parse_command(text)
    if cmd in {"/start", "/help", "help"}:
        send_to_telegram("📘 COMMANDS\n/status\n/positions\n/orders\n/engine_on\n/engine_off\n/paper_on\n/paper_off\n/alpaca_on\n/alpaca_off\n/discord_on\n/discord_off\n/telegram_on\n/telegram_off\n/kill_on\n/kill_off\n/pause_on\n/pause_off\n/test\n/heartbeat\n/sync\n/recon\n/recon_clear\n/cancel_orders\n/close_all\n/macro\n/macro_push\n")
        return
    if cmd == "/status":
        send_to_telegram(build_status_text()); return
    if cmd == "/positions":
        send_to_telegram(build_positions_text()); return
    if cmd == "/orders":
        send_to_telegram(build_orders_text()); return
    if cmd == "/engine_on":
        GLOBAL_STATE["engine_enabled"] = True; save_state(GLOBAL_STATE); send_to_telegram("✅ Engine enabled"); return
    if cmd == "/engine_off":
        GLOBAL_STATE["engine_enabled"] = False; save_state(GLOBAL_STATE); send_to_telegram("🛑 Engine disabled"); return
    if cmd == "/paper_on":
        GLOBAL_STATE["paper_enabled"] = True; GLOBAL_STATE["last_mode"] = "PAPER"; save_state(GLOBAL_STATE); send_to_telegram("✅ Paper mode enabled"); return
    if cmd == "/paper_off":
        GLOBAL_STATE["paper_enabled"] = False; GLOBAL_STATE["last_mode"] = "LIVE"; save_state(GLOBAL_STATE); send_to_telegram("🛑 Paper mode disabled"); return
    if cmd == "/alpaca_on":
        GLOBAL_STATE["alpaca_enabled"] = True; GLOBAL_STATE["paper_enabled"] = False; GLOBAL_STATE["last_mode"] = "LIVE"; save_state(GLOBAL_STATE); send_to_telegram("✅ Alpaca mode enabled"); return
    if cmd == "/alpaca_off":
        GLOBAL_STATE["alpaca_enabled"] = False; save_state(GLOBAL_STATE); send_to_telegram("🛑 Alpaca mode disabled"); return
    if cmd == "/discord_on":
        GLOBAL_STATE["discord_enabled"] = True; save_state(GLOBAL_STATE); send_to_telegram("✅ Discord routing enabled"); return
    if cmd == "/discord_off":
        GLOBAL_STATE["discord_enabled"] = False; save_state(GLOBAL_STATE); send_to_telegram("🛑 Discord routing disabled"); return
    if cmd == "/telegram_on":
        GLOBAL_STATE["telegram_enabled"] = True; save_state(GLOBAL_STATE); send_to_telegram("✅ Telegram alerts enabled"); return
    if cmd == "/telegram_off":
        GLOBAL_STATE["telegram_enabled"] = False; save_state(GLOBAL_STATE); send_to_telegram("🛑 Telegram alerts disabled"); return
    if cmd == "/kill_on":
        GLOBAL_STATE["kill_switch"] = True; save_state(GLOBAL_STATE); send_to_telegram("🛑 Kill switch enabled"); return
    if cmd == "/kill_off":
        GLOBAL_STATE["kill_switch"] = False; save_state(GLOBAL_STATE); send_to_telegram("✅ Kill switch disabled"); return
    if cmd == "/pause_on":
        GLOBAL_STATE["bot_paused"] = True; save_state(GLOBAL_STATE); send_to_telegram("⏸️ Bot paused"); return
    if cmd == "/pause_off":
        GLOBAL_STATE["bot_paused"] = False; save_state(GLOBAL_STATE); send_to_telegram("▶️ Bot resumed"); return
    if cmd == "/sync":
        sync_live_positions_from_alpaca(); reconcile_order_fills_into_positions(); send_to_telegram("🔄 Sync complete"); return
    if cmd == "/recon":
        report = build_boot_reconciliation_report(); send_to_telegram(build_reconciliation_message(report)); return
    if cmd == "/recon_clear":
        clear_reconciliation_block(); send_to_telegram("✅ Reconciliation block cleared"); return
    if cmd == "/cancel_orders":
        if not alpaca_ready():
            send_to_telegram("❌ Alpaca not configured"); return
        resp = alpaca_delete("/v2/orders")
        send_to_telegram("✅ Cancel all orders sent" if resp.status_code in (200, 204, 207) else f"❌ Cancel all orders failed | {resp.status_code}")
        return
    if cmd == "/close_all":
        close_all_open_positions(); return
    if cmd == "/heartbeat":
        send_heartbeat(force=True); return
    if cmd == "/macro":
        snapshot = refresh_macro_bridge(force=True, send_alerts=False)
        send_to_telegram(build_macro_message(snapshot))
        return
    if cmd == "/macro_push":
        refresh_macro_bridge(force=True, send_alerts=True)
        send_to_telegram("✅ Macro bridge refreshed and pushed")
        return
    if cmd == "/test":
        run_startup_tests(); send_to_telegram("🧪 Test alerts triggered"); return


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
        text = (update.get("message", {}) or {}).get("text", "")
        if text:
            handle_telegram_command(text)
    GLOBAL_STATE["last_telegram_update_id"] = max_update_id
    save_state(GLOBAL_STATE)


# =========================================================
# HEARTBEAT + TESTS + FALLBACK
# =========================================================
def send_heartbeat(force: bool = False):
    if not ENABLE_HEARTBEAT:
        return
    last = safe_int(GLOBAL_STATE.get("last_heartbeat_time", 0), 0)
    minutes_since = (epoch() - last) / 60 if last > 0 else 99999
    if force or minutes_since >= HEARTBEAT_MINUTES:
        heartbeat_text = build_status_text()
        voice_script = get_latest_macro_voice_script()
        if voice_script:
            heartbeat_text += f"\n\nLatest Macro Voice:\n{voice_script}"
        send_to_telegram(heartbeat_text)
        GLOBAL_STATE["last_heartbeat_time"] = epoch()
        save_state(GLOBAL_STATE)


def run_startup_tests():
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
            send_to_telegram(f"🧪 ALPACA CHECK OK\nStatus: {acct.get('status', 'unknown')}\nBuying Power: {acct.get('buying_power', 'N/A')}\nOptions BP: {acct.get('options_buying_power', 'N/A')}\n⏰ {ts}")
        else:
            send_to_telegram(f"❌ ALPACA CHECK FAILED\n⏰ {ts}")


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
# BOOT + LOOP
# =========================================================
def boot():
    global GLOBAL_STATE, GLOBAL_POSITIONS, GLOBAL_ORDERS, GLOBAL_RECON, GLOBAL_MACRO
    GLOBAL_STATE = load_state()
    GLOBAL_POSITIONS = load_positions()
    GLOBAL_ORDERS = load_orders()
    GLOBAL_RECON = load_recon()
    GLOBAL_MACRO = default_macro_store()

    log(f"🔥 {BOT_NAME} booting...")
    reset_daily_risk_counters_if_needed(GLOBAL_STATE)
    save_state(GLOBAL_STATE)
    save_positions(GLOBAL_POSITIONS)
    save_orders(GLOBAL_ORDERS)
    save_recon(GLOBAL_RECON)
    save_macro_store()
    debug_file_lookup(SIGNAL_FILE)

    if RUN_TEST_ON_START:
        run_startup_tests()

    if ENABLE_ALPACA and GLOBAL_STATE.get("alpaca_enabled", False) and alpaca_ready():
        startup_reconcile_and_gate()

    if ENABLE_MACRO_BRIDGE:
        refresh_macro_bridge(force=True, send_alerts=MACRO_SEND_ON_BOOT)

    send_heartbeat(force=True)


def runtime_housekeeping():
    ensure_globals_initialized()
    refresh_macro_bridge(force=False, send_alerts=False)
    sync_live_positions_from_alpaca()
    reconcile_order_fills_into_positions()
    update_positions_from_market_prices()
    manage_open_positions(None)
    flush_dirty_stores(force=False)


def main_loop():
    boot()

    if not file_exists(SIGNAL_FILE):
        log(f"❌ No signal file found on boot: {SIGNAL_FILE}")
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
            runtime_housekeeping()
            if live_signal:
                manage_open_positions(live_signal)
            send_heartbeat(force=False)
            flush_dirty_stores(force=False)
            time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            log("🛑 Manual stop")
            break
        except Exception as e:
            log(f"💥 Loop error: {e}")
            traceback.print_exc()
            flush_dirty_stores(force=True)
            time.sleep(POLL_SECONDS)


def run_once():
    boot()
    sig = load_live_signal() or fallback_signal()
    handle_new_signal(sig)
    runtime_housekeeping()
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

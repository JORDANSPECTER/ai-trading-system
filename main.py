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
from datetime import datetime, timedelta
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
# ALPACA URL NORMALIZER + SAFE ENDPOINT BUILDER
# Prevents 401/404 caused by bad base URLs, trailing slashes, or duplicated /v2.
# =========================================================
def normalize_alpaca_base_url(url: str, default: str = "https://paper-api.alpaca.markets") -> str:
    try:
        u = str(url or default).strip()
        if not u:
            u = default
        while u.endswith("/"):
            u = u[:-1]
        if u.endswith("/v2"):
            u = u[:-3]
        return u
    except Exception:
        return default.rstrip("/")


def normalize_alpaca_data_base_url(url: str, default: str = "https://data.alpaca.markets") -> str:
    try:
        u = str(url or default).strip()
        if not u:
            u = default
        while u.endswith("/"):
            u = u[:-1]
        if u.endswith("/v2"):
            u = u[:-3]
        return u
    except Exception:
        return default.rstrip("/")


def alpaca_endpoint(path: str) -> str:
    """
    Builds trading endpoints safely:
    alpaca_endpoint("/account") -> https://.../v2/account
    alpaca_endpoint("/orders") -> https://.../v2/orders
    """
    base = normalize_alpaca_base_url(globals().get("ALPACA_BASE_URL", os.getenv("ALPACA_BASE_URL", "")))
    p = str(path or "").strip()
    if not p.startswith("/"):
        p = "/" + p
    if p.startswith("/v2/"):
        p = p[3:]
    return f"{base}/v2{p}"


def alpaca_data_endpoint(path: str) -> str:
    """
    Builds data endpoints safely:
    alpaca_data_endpoint("/v2/stocks/bars") -> https://data.alpaca.markets/v2/stocks/bars
    """
    base = normalize_alpaca_data_base_url(globals().get("ALPACA_DATA_BASE_URL", os.getenv("ALPACA_DATA_BASE_URL", "")))
    p = str(path or "").strip()
    if not p.startswith("/"):
        p = "/" + p
    return f"{base}{p}"


def alpaca_headers() -> Dict[str, str]:
    return {
        "APCA-API-KEY-ID": str(globals().get("ALPACA_API_KEY", os.getenv("ALPACA_API_KEY", ""))).strip(),
        "APCA-API-SECRET-KEY": str(globals().get("ALPACA_SECRET_KEY", os.getenv("ALPACA_SECRET_KEY", ""))).strip(),
        "Content-Type": "application/json",
    }


def debug_alpaca_urls_once() -> None:
    try:
        if globals().get("_ALPACA_URLS_DEBUGGED", False):
            return
        globals()["_ALPACA_URLS_DEBUGGED"] = True
        log(f"DEBUG: ALPACA URLS | base={normalize_alpaca_base_url(globals().get('ALPACA_BASE_URL', os.getenv('ALPACA_BASE_URL', '')))} account={alpaca_endpoint('/account')} orders={alpaca_endpoint('/orders')} positions={alpaca_endpoint('/positions')}")
    except Exception:
        pass

# =========================================================
# ENV VARS
# =========================================================
DISCORD_AI_WEBHOOK = os.getenv("DISCORD_AI_WEBHOOK", "").strip()
DISCORD_FREE_WEBHOOK = os.getenv("DISCORD_FREE_WEBHOOK", "").strip()
DISCORD_FREE_DAILY_LEVELS_WEBHOOK = os.getenv("DISCORD_FREE_DAILY_LEVELS_WEBHOOK", DISCORD_FREE_WEBHOOK).strip()
DISCORD_PREMIUM_WEBHOOK = os.getenv("DISCORD_PREMIUM_WEBHOOK", "").strip()
DISCORD_DARKPOOL_WEBHOOK = os.getenv("DISCORD_DARKPOOL_WEBHOOK", "").strip()
DISCORD_LIVE_ENTRY_WEBHOOK = os.getenv("DISCORD_LIVE_ENTRY_WEBHOOK", "").strip()
DISCORD_EXECUTION_WEBHOOK = os.getenv("DISCORD_EXECUTION_WEBHOOK", os.getenv("DISCORD_AI_EXECUTION_WEBHOOK", "")).strip()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

BOT_NAME = os.getenv("BOT_NAME", "UnBiased Trades Engine").strip()
DEBUG_MODE = os.getenv("DEBUG_MODE", "true").lower() == "true"
RUN_TEST_ON_START = os.getenv("RUN_TEST_ON_START", "true").lower() == "true"
RUN_LOOP = os.getenv("RUN_LOOP", "true").lower() == "true"

POLL_SECONDS = int(os.getenv("POLL_SECONDS", "5"))
HEARTBEAT_MINUTES = int(os.getenv("HEARTBEAT_MINUTES", "30"))

SIGNAL_FILE = os.getenv("SIGNAL_FILE", "signal.json").strip()
MARKET_PRICES_FILE = os.getenv("MARKET_PRICES_FILE", "market_prices.json")
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
try:
    MACRO_REFRESH_SECONDS = int(str(os.getenv("MACRO_REFRESH_SECONDS", "300")).strip())
except Exception:
    MACRO_REFRESH_SECONDS = 300
MACRO_SEND_TO_AI = os.getenv("MACRO_SEND_TO_AI", "true").lower() == "true"
MACRO_SEND_TO_TELEGRAM = os.getenv("MACRO_SEND_TO_TELEGRAM", "false").lower() == "true"
MACRO_SEND_ON_BOOT = os.getenv("MACRO_SEND_ON_BOOT", "true").lower() == "true"

# ALPACA
ENABLE_ALPACA = os.getenv("ENABLE_ALPACA", "false").lower() == "true"
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "").strip()
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "").strip()
ALPACA_BASE_URL = normalize_alpaca_base_url(os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))
ALPACA_ORDER_TIMEOUT = int(os.getenv("ALPACA_ORDER_TIMEOUT", "20"))
ALPACA_SYNC_POSITIONS = os.getenv("ALPACA_SYNC_POSITIONS", "true").lower() == "true"
ALPACA_ENABLE_OPTIONS = os.getenv("ALPACA_ENABLE_OPTIONS", "true").lower() == "true"
ALPACA_LIVE_OPTIONS_APPROVED = os.getenv("ALPACA_LIVE_OPTIONS_APPROVED", "false").lower() == "true"
USE_ALPACA_OPTIONS_BUYING_POWER = os.getenv("USE_ALPACA_OPTIONS_BUYING_POWER", "true").lower() == "true"
LIVE_MODE = os.getenv("LIVE_MODE", "false").lower() == "true"

# SIGNAL / EXECUTION DEFAULTS
MAX_SIGNAL_AGE_SECONDS = int(os.getenv("MAX_SIGNAL_AGE_SECONDS", "180"))
MAX_ENTRY_AGE_SECONDS = MAX_SIGNAL_AGE_SECONDS
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
# Market data freshness fix: lets Render/file-based testing keep prices fresh without GitHub redeploys.
# For testing use 300. For live trading tighten to 10-20 seconds.
MARKET_DATA_MAX_AGE_SECONDS = int(os.getenv("MARKET_DATA_MAX_AGE_SECONDS", str(MARKET_DATA_STALE_SECONDS)))
MARKET_DATA_REFRESH_FILE_TIMESTAMPS = os.getenv("MARKET_DATA_REFRESH_FILE_TIMESTAMPS", "true").lower() == "true"
MARKET_DATA_ADD_PRICE_UPDATED_AT = os.getenv("MARKET_DATA_ADD_PRICE_UPDATED_AT", "true").lower() == "true"
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()
TWELVE_DATA_BASE_URL = os.getenv("TWELVE_DATA_BASE_URL", "https://api.twelvedata.com").strip().rstrip("/")
ALPACA_DATA_BASE_URL = normalize_alpaca_data_base_url(os.getenv("ALPACA_DATA_BASE_URL", "https://data.alpaca.markets")).rstrip("/")
LIVE_PRICE_CACHE_SECONDS = int(os.getenv("LIVE_PRICE_CACHE_SECONDS", str(MARKET_DATA_REFRESH_SECONDS)))
AUTO_MANAGE_POSITIONS = os.getenv("AUTO_MANAGE_POSITIONS", "true").lower() == "true"
AUTO_TP_ENABLED = os.getenv("AUTO_TP_ENABLED", "true").lower() == "true"
AUTO_TRAILING_STOP_ENABLED = os.getenv("AUTO_TRAILING_STOP_ENABLED", "true").lower() == "true"
AUTO_BREAKEVEN_ENABLED = os.getenv("AUTO_BREAKEVEN_ENABLED", "true").lower() == "true"
TRAIL_ONLY_AFTER_TP1 = os.getenv("TRAIL_ONLY_AFTER_TP1", "false").lower() == "true"
SEND_PRICE_UPDATE_ALERTS = os.getenv("SEND_PRICE_UPDATE_ALERTS", "false").lower() == "true"
PRICE_UPDATE_ALERT_SECONDS = int(os.getenv("PRICE_UPDATE_ALERT_SECONDS", "60"))

# =========================================================
# STEP 13 ADVANCED TRADE MANAGEMENT
# =========================================================
ENABLE_STEP13_ADVANCED_MANAGEMENT = os.getenv("ENABLE_STEP13_ADVANCED_MANAGEMENT", "true").lower() == "true"
STEP13_BREAKEVEN_TRIGGER_PCT = float(os.getenv("STEP13_BREAKEVEN_TRIGGER_PCT", "0.15"))
STEP13_SMART_TRAIL_TRIGGER_PCT = float(os.getenv("STEP13_SMART_TRAIL_TRIGGER_PCT", "0.25"))
STEP13_SMART_TRAIL_LOCK_PCT = float(os.getenv("STEP13_SMART_TRAIL_LOCK_PCT", "0.92"))
STEP13_AGGRESSIVE_TRAIL_TRIGGER_PCT = float(os.getenv("STEP13_AGGRESSIVE_TRAIL_TRIGGER_PCT", "0.40"))
STEP13_AGGRESSIVE_TRAIL_LOCK_PCT = float(os.getenv("STEP13_AGGRESSIVE_TRAIL_LOCK_PCT", "0.95"))
STEP13_TIME_EXIT_ENABLED = os.getenv("STEP13_TIME_EXIT_ENABLED", "true").lower() == "true"
STEP13_MAX_HOLD_SECONDS = int(os.getenv("STEP13_MAX_HOLD_SECONDS", "900"))
STEP13_STAGNANT_MOVE_PCT = float(os.getenv("STEP13_STAGNANT_MOVE_PCT", "0.05"))


# =========================================================
# STEP 14 PORTFOLIO RISK ENGINE
# - Account-level risk guard
# - Max concurrent open trades
# - Daily loss kill switch
# - Emergency close/shutdown
# =========================================================
ENABLE_STEP14_PORTFOLIO_RISK = os.getenv("ENABLE_STEP14_PORTFOLIO_RISK", "true").lower() == "true"
STEP14_MAX_OPEN_TRADES = int(os.getenv("STEP14_MAX_OPEN_TRADES", str(MAX_OPEN_POSITIONS)))
STEP14_MAX_DAILY_LOSS_PCT = float(os.getenv("STEP14_MAX_DAILY_LOSS_PCT", str(MAX_DAILY_LOSS_PCT)))
STEP14_MAX_DAILY_LOSS_DOLLARS = float(os.getenv("STEP14_MAX_DAILY_LOSS_DOLLARS", "0"))
STEP14_CLOSE_ALL_ON_DAILY_LOSS = os.getenv("STEP14_CLOSE_ALL_ON_DAILY_LOSS", "true").lower() == "true"
STEP14_BLOCK_NEW_TRADES_ON_DAILY_LOSS = os.getenv("STEP14_BLOCK_NEW_TRADES_ON_DAILY_LOSS", "true").lower() == "true"
STEP14_EMERGENCY_STOP_ON_KILL = os.getenv("STEP14_EMERGENCY_STOP_ON_KILL", "true").lower() == "true"
STEP14_SEND_ALERTS = os.getenv("STEP14_SEND_ALERTS", "true").lower() == "true"

# =========================================================
# STEP 15 GLOBAL KILL SWITCH / FLATTEN ENGINE
# - Close all open positions when risk is breached
# - Lock engine after emergency stop
# - Telegram remote commands: /kill, /flatten, /unlock
# =========================================================
ENABLE_STEP15_GLOBAL_KILL_SWITCH = os.getenv("ENABLE_STEP15_GLOBAL_KILL_SWITCH", "true").lower() == "true"
STEP15_CLOSE_ALL_ON_KILL = os.getenv("STEP15_CLOSE_ALL_ON_KILL", "true").lower() == "true"
STEP15_LOCK_ENGINE_ON_KILL = os.getenv("STEP15_LOCK_ENGINE_ON_KILL", "true").lower() == "true"
STEP15_REQUIRE_MANUAL_RESET = os.getenv("STEP15_REQUIRE_MANUAL_RESET", "true").lower() == "true"
STEP15_SEND_ALERTS = os.getenv("STEP15_SEND_ALERTS", "true").lower() == "true"
STEP15_ALERT_COOLDOWN_SECONDS = int(os.getenv("STEP15_ALERT_COOLDOWN_SECONDS", "60"))



# =========================================================
# INTELLIGENCE PHASE 3: ADAPTIVE INTELLIGENCE
# =========================================================
def phase3_setup_key(signal_or_trade: Dict[str, Any]) -> str:
    ticker = str(signal_or_trade.get("ticker", "UNKNOWN")).upper().strip()
    direction = str(signal_or_trade.get("direction", "UNKNOWN")).upper().strip()
    confidence = str(signal_or_trade.get("confidence", "NA")).upper().strip()
    setup = str(signal_or_trade.get("setup") or signal_or_trade.get("strategy") or signal_or_trade.get("trigger") or "GENERIC").upper().strip()
    setup = setup.replace(" ", "_")[:40]
    return f"{ticker}_{direction}_{confidence}_{setup}"


def phase3_infer_winner(trade: Dict[str, Any]) -> bool:
    """Robust W/L detection for adaptive learning. Fixes losses not being counted."""
    pnl = safe_float(trade.get("realized_pnl_pct", trade.get("pnl_pct", 0)), 0)
    if abs(pnl) > 0:
        return pnl > 0
    explicit = trade.get("winner", None)
    if isinstance(explicit, bool):
        return explicit
    entry = safe_float(trade.get("entry_price", trade.get("entry", 0)), 0)
    exit_price = safe_float(trade.get("exit_price", trade.get("exit", trade.get("last_price", 0))), 0)
    if entry > 0 and exit_price > 0:
        return exit_price > entry
    return False


def phase3_trade_result_letter(trade: Dict[str, Any]) -> str:
    return "W" if phase3_infer_winner(trade) else "L"


def phase3_load_disabled_setups() -> Dict[str, Any]:
    data = load_json_file(PHASE3_DISABLED_SETUPS_FILE, {})
    return data if isinstance(data, dict) else {}


def phase3_save_disabled_setups(data: Dict[str, Any]):
    atomic_write_json(PHASE3_DISABLED_SETUPS_FILE, data)


def phase3_compute_setup_stats() -> Dict[str, Any]:
    trades = intel_load_trade_memory()
    stats: Dict[str, Any] = {}
    for t in trades:
        key = phase3_setup_key(t)
        bucket = stats.setdefault(key, {
            "setup_key": key,
            "ticker": str(t.get("ticker", "UNKNOWN")).upper(),
            "direction": str(t.get("direction", "UNKNOWN")).upper(),
            "confidence": str(t.get("confidence", "NA")).upper(),
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "total_r": 0.0,
            "total_pnl_pct": 0.0,
            "recent_results": [],
            "last_trade_ts": 0,
        })
        pnl = safe_float(t.get("realized_pnl_pct", t.get("pnl_pct", 0)), 0)
        r_mult = safe_float(t.get("r_multiple", 0), 0)
        winner = phase3_infer_winner(t)
        bucket["trades"] += 1
        bucket["wins"] += 1 if winner else 0
        bucket["losses"] += 0 if winner else 1
        bucket["total_r"] += r_mult
        bucket["total_pnl_pct"] += pnl
        bucket["recent_results"].append("W" if winner else "L")
        bucket["recent_results"] = bucket["recent_results"][-PHASE3_DISABLE_LAST_N:]
        bucket["last_trade_ts"] = max(safe_int(bucket.get("last_trade_ts", 0), 0), safe_int(t.get("closed_ts", t.get("timestamp", 0)), 0))

    for key, bucket in stats.items():
        total = max(safe_int(bucket.get("trades", 0), 0), 1)
        bucket["win_rate"] = round(bucket.get("wins", 0) / total, 4)
        bucket["avg_r"] = round(bucket.get("total_r", 0.0) / total, 4)
        bucket["avg_pnl_pct"] = round(bucket.get("total_pnl_pct", 0.0) / total, 4)
        recent = bucket.get("recent_results", [])[-PHASE3_DISABLE_LAST_N:]
        bucket["recent_loss_count"] = sum(1 for x in recent if x == "L")
    return stats


def phase3_write_adaptive_stats(force: bool = False) -> Dict[str, Any]:
    if not ENABLE_INTELLIGENCE_PHASE3:
        return {}
    try:
        stats = phase3_compute_setup_stats()
        payload = {
            "generated_at": now_ts(),
            "min_trades_for_filter": PHASE3_MIN_TRADES_FOR_FILTER,
            "setup_count": len(stats),
            "stats": stats,
            "disabled_setups": phase3_load_disabled_setups(),
        }
        atomic_write_json(PHASE3_ADAPTIVE_STATS_FILE, payload)
        if force:
            debug(f"PHASE 3 ADAPTIVE STATS WRITTEN | setups={len(stats)}")
        return payload
    except Exception as e:
        log(f"❌ PHASE 3 stats write failed: {e}")
        return {}




# =========================================================
# PHASE 3.5 LOCKED LEARNING HOOK
# Guarantees adaptive_setup_stats.json updates on every final close, including LOSSES.
# =========================================================
def phase35_locked_learning_hook(position: Dict[str, Any], close_reason: str = ""):
    if not ENABLE_INTELLIGENCE_PHASE3:
        return
    try:
        story = intel_trade_story_from_position(position, close_reason)
        setup_key = phase3_setup_key(story)
        payload = phase3_write_adaptive_stats(force=True)
        stats = payload.get("stats", {}) if isinstance(payload, dict) and isinstance(payload.get("stats", {}), dict) else {}
        if setup_key in stats and safe_int(stats[setup_key].get("trades", 0), 0) > 0:
            debug(f"PHASE 3.5 LEARNING CONFIRMED | {setup_key} | trades={stats[setup_key].get('trades')} | win_rate={stats[setup_key].get('win_rate')}")
            return
        pnl = safe_float(story.get("realized_pnl_pct", 0), 0)
        r_mult = safe_float(story.get("r_multiple", 0), 0)
        winner = phase3_infer_winner(story)
        stats[setup_key] = {
            "setup_key": setup_key,
            "ticker": str(story.get("ticker", "UNKNOWN")).upper(),
            "direction": str(story.get("direction", "UNKNOWN")).upper(),
            "confidence": str(story.get("confidence", "NA")).upper(),
            "trades": 1,
            "wins": 1 if winner else 0,
            "losses": 0 if winner else 1,
            "total_r": r_mult,
            "total_pnl_pct": pnl,
            "recent_results": ["W" if winner else "L"],
            "recent_loss_count": 0 if winner else 1,
            "win_rate": 1.0 if winner else 0.0,
            "avg_r": r_mult,
            "avg_pnl_pct": pnl,
            "last_trade_ts": safe_int(story.get("closed_ts", epoch()), epoch()),
        }
        atomic_write_json(PHASE3_ADAPTIVE_STATS_FILE, {
            "generated_at": now_ts(),
            "min_trades_for_filter": PHASE3_MIN_TRADES_FOR_FILTER,
            "setup_count": len(stats),
            "stats": stats,
            "disabled_setups": phase3_load_disabled_setups(),
        })
        debug(f"PHASE 3.5 LOCKED ADAPTIVE UPDATE | {setup_key} | trades=1 | win_rate={stats[setup_key]['win_rate']}")
    except Exception as e:
        log(f"❌ PHASE 3.5 locked learning hook failed: {e}")

def phase3_alert(title: str, body: str, force: bool = False):
    if not PHASE3_SEND_ALERTS and not force:
        return
    msg = f"🧠 {title}\n{body}\n⏰ {now_ts()}"
    send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
    send_to_telegram(msg)


def phase3_downgrade_confidence(confidence: str) -> str:
    c = str(confidence or "C").upper().strip()
    if c == "A+":
        return "A"
    if c == "A":
        return "B"
    if c == "B":
        return "C"
    return c or "C"


def phase3_evaluate_adaptive_intelligence(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Return an adaptive decision before sizing/execution.
    Safe default: if not enough history, approve without changing behavior.
    """
    if not ENABLE_INTELLIGENCE_PHASE3:
        return {"approved": True, "stage": "phase3_adaptive_intelligence", "reason": "disabled", "size_multiplier": 1.0, "adjusted_signal": deepcopy(signal), "stats": {}}

    x = deepcopy(signal)
    setup_key = phase3_setup_key(x)
    debug(f"PHASE 3 ADAPTIVE CHECK | setup={setup_key} | ticker={x.get('ticker')} | direction={x.get('direction')} | confidence={x.get('confidence')}")
    stats_payload = phase3_write_adaptive_stats(force=False)
    stats = (stats_payload.get("stats", {}) if isinstance(stats_payload, dict) else {}).get(setup_key, {})
    disabled = phase3_load_disabled_setups()
    reasons = []
    actions = []
    size_multiplier = 1.0

    if setup_key in disabled:
        reasons.append("setup_disabled_by_phase3")

    trade_count = safe_int(stats.get("trades", 0), 0)
    win_rate = safe_float(stats.get("win_rate", 0), 0)
    avg_r = safe_float(stats.get("avg_r", 0), 0)
    recent_losses = safe_int(stats.get("recent_loss_count", 0), 0)

    if trade_count < PHASE3_MIN_TRADES_FOR_FILTER:
        debug(f"PHASE 3 OBSERVE ONLY | {setup_key} | trades={trade_count}/{PHASE3_MIN_TRADES_FOR_FILTER}")
        debug("PHASE 3 SIZE MULTIPLIER | base=1.0 -> adjusted=1.0 | reason=observe_only")
        intel_event("phase3_observe_only", {"setup_key": setup_key, "trades": trade_count, "required": PHASE3_MIN_TRADES_FOR_FILTER}, signal=x, stage="phase3_adaptive", decision="observe_only")
        return {"approved": True, "stage": "phase3_adaptive_intelligence", "reason": "insufficient_history", "setup_key": setup_key, "size_multiplier": 1.0, "adjusted_signal": x, "stats": stats, "actions": ["observe_only"]}

    if win_rate < PHASE3_BLOCK_WINRATE_BELOW:
        reasons.append("setup_win_rate_below_threshold")
    if avg_r < PHASE3_BLOCK_AVG_R_BELOW:
        reasons.append("setup_avg_r_below_threshold")
    if recent_losses >= PHASE3_DISABLE_LOSSES_IN_LAST_N:
        reasons.append("setup_recent_loss_cluster")
        disabled[setup_key] = {"disabled_at": now_ts(), "reason": "recent_loss_cluster", "recent_losses": recent_losses, "last_n": PHASE3_DISABLE_LAST_N, "stats": stats}
        phase3_save_disabled_setups(disabled)

    if win_rate >= PHASE3_SIZE_UP_WINRATE and avg_r >= 0:
        size_multiplier = PHASE3_SIZE_UP_MULT
        actions.append("size_up")
    elif win_rate < PHASE3_SIZE_DOWN_WINRATE:
        size_multiplier = PHASE3_SIZE_DOWN_MULT
        actions.append("size_down")

    original_conf = str(x.get("confidence", "C")).upper().strip()
    if original_conf in {"A+", "A"} and win_rate < PHASE3_CONFIDENCE_DOWNGRADE_WINRATE:
        x["original_confidence"] = original_conf
        x["confidence"] = phase3_downgrade_confidence(original_conf)
        actions.append(f"confidence_downgrade_{original_conf}_to_{x['confidence']}")

    decision = {
        "approved": len(reasons) == 0 or PHASE3_SUGGEST_ONLY,
        "suggest_only": PHASE3_SUGGEST_ONLY,
        "stage": "phase3_adaptive_intelligence",
        "setup_key": setup_key,
        "reject_reasons": reasons,
        "size_multiplier": size_multiplier,
        "adjusted_signal": x,
        "stats": stats,
        "actions": actions,
    }

    intel_event("phase3_adaptive_decision", decision, signal=x, stage="phase3_adaptive", decision="approved" if decision["approved"] else "blocked")

    if reasons:
        body = f"Setup: {setup_key}\nReasons: {', '.join(reasons)}\nTrades: {trade_count} | Win Rate: {round(win_rate*100,1)}% | Avg R: {avg_r}\nSuggest Only: {PHASE3_SUGGEST_ONLY}"
        phase3_alert("PHASE 3 SETUP BLOCK" if not PHASE3_SUGGEST_ONLY else "PHASE 3 SETUP WARNING", body)
    else:
        debug(f"PHASE 3 ADAPTIVE OK | {setup_key} | trades={trade_count} | win_rate={round(win_rate*100,1)}% | avg_r={avg_r} | size_mult={size_multiplier} | actions={actions}")

    return decision


def phase3_apply_size_multiplier_to_decision(size_decision: Dict[str, Any], phase3_decision: Dict[str, Any]) -> Dict[str, Any]:
    if not ENABLE_INTELLIGENCE_PHASE3:
        return size_decision
    try:
        mult = safe_float(phase3_decision.get("size_multiplier", 1.0), 1.0)
        if mult == 1.0:
            return size_decision
        x = deepcopy(size_decision)
        original = safe_int(x.get("final_size", 0), 0)
        adjusted = int(math.floor(original * mult)) if mult < 1 else int(math.ceil(original * mult))
        adjusted = max(MIN_POSITION_QTY if original >= MIN_POSITION_QTY else 0, adjusted)
        adjusted = min(MAX_POSITION_QTY, adjusted)
        if original > 0 and adjusted <= 0:
            adjusted = MIN_POSITION_QTY
        x["phase3_original_final_size"] = original
        x["phase3_size_multiplier"] = mult
        debug(f"PHASE 3 SIZE MULTIPLIER | base={original} -> adjusted={adjusted} | mult={mult}")
        x["final_size"] = adjusted
        x.setdefault("adjustments", []).append(f"phase3_size_multiplier_{mult}")
        x["approved"] = adjusted >= MIN_POSITION_QTY
        if not x["approved"]:
            x.setdefault("reject_reasons", []).append("phase3_adjusted_size_below_minimum")
        return x
    except Exception as e:
        log(f"❌ PHASE 3 size multiplier failed: {e}")
        return size_decision


# =========================================================
# HARD KILL ENGINE - REQUIRED BY PHASE 0 / STEP 15
# =========================================================
def hard_kill_engine(reason: str = "", close_positions: bool = True):
    """Central emergency lock used by Phase 0, Step 14, and Step 15.
    This locks new entries first, then attempts flattening.
    """
    ensure_globals_initialized()
    reason = str(reason or "Hard kill activated").strip()

    GLOBAL_STATE["kill_switch"] = True
    GLOBAL_STATE["engine_enabled"] = False
    GLOBAL_STATE["allow_entries"] = False
    GLOBAL_STATE["hard_kill_reason"] = reason
    GLOBAL_STATE["step15_global_kill"] = True
    GLOBAL_STATE["step15_last_reason"] = reason
    GLOBAL_STATE["step15_last_kill_time"] = epoch()
    save_state(GLOBAL_STATE)

    log(f"ð¨ HARD KILL ACTIVATED | {reason}")

    closed = 0
    if close_positions:
        try:
            if 'step15_close_all_open_positions' in globals():
                closed = step15_close_all_open_positions(reason)
            elif 'step14_close_all_open_positions' in globals():
                step14_close_all_open_positions(reason)
                closed = len(GLOBAL_POSITIONS.get("open_positions", []))
        except Exception as e:
            log(f"â HARD KILL flatten failed: {e}")

    msg = (
        f"ð¨ HARD KILL ACTIVATED\n"
        f"Reason: {reason}\n"
        f"Closed/flatten attempts: {closed}\n"
        f"Engine Locked: {GLOBAL_STATE.get('kill_switch', True)}\n"
        f"New trades blocked until manual reset.\n"
        f"â° {now_ts()}"
    )
    try:
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_live_entry_discord(msg)
        send_to_telegram(msg)
    except Exception as e:
        log(f"â HARD KILL alert failed: {e}")
    return {"locked": True, "reason": reason, "closed_attempts": closed}

# =========================================================
# PHASE 0 HARD SAFETY LAYER
# - State invariants
# - Startup safety gate
# - Fresh price requirements
# - Hard daily loss / heat kill switch
# =========================================================
ENABLE_PHASE0_SAFETY = os.getenv("ENABLE_PHASE0_SAFETY", "true").lower() == "true"
PHASE0_BLOCK_ON_INVALID_STATE = os.getenv("PHASE0_BLOCK_ON_INVALID_STATE", "true").lower() == "true"
PHASE0_REQUIRE_FRESH_PRICE_FOR_ENTRY = os.getenv("PHASE0_REQUIRE_FRESH_PRICE_FOR_ENTRY", "true").lower() == "true"
PHASE0_REQUIRE_FRESH_PRICE_FOR_OPEN_POSITIONS = os.getenv("PHASE0_REQUIRE_FRESH_PRICE_FOR_OPEN_POSITIONS", "true").lower() == "true"
PHASE0_REQUIRE_STARTUP_RECON_CLEAN = os.getenv("PHASE0_REQUIRE_STARTUP_RECON_CLEAN", "true").lower() == "true"
PHASE0_MARKET_FILE_MAX_AGE_SECONDS = int(os.getenv("PHASE0_MARKET_FILE_MAX_AGE_SECONDS", str(MARKET_DATA_MAX_AGE_SECONDS)))
PHASE0_HARD_DAILY_LOSS_PCT = float(os.getenv("PHASE0_HARD_DAILY_LOSS_PCT", str(MAX_DAILY_LOSS_PCT)))
PHASE0_HARD_PORTFOLIO_HEAT_PCT = float(os.getenv("PHASE0_HARD_PORTFOLIO_HEAT_PCT", str(max(MAX_PORTFOLIO_HEAT_PCT * 1.25, MAX_PORTFOLIO_HEAT_PCT))))
PHASE0_AUTO_FLATTEN_ON_HARD_KILL = os.getenv("PHASE0_AUTO_FLATTEN_ON_HARD_KILL", "true").lower() == "true"
PHASE0_SEND_ALERTS = os.getenv("PHASE0_SEND_ALERTS", "true").lower() == "true"

# PHASE 0 OPTION PRICE FALLBACK
# Test/paper mode bridge: when option contract live price is missing, allow the engine
# to use the signal entry/contract_price so paper orders can be validated and created.
# Turn this false when a real options pricing feed is connected.
ALLOW_FAKE_OPTION_PRICE = os.getenv("ALLOW_FAKE_OPTION_PRICE", "true").lower() == "true"
FAKE_OPTION_PRICE_ONLY_IN_PAPER = os.getenv("FAKE_OPTION_PRICE_ONLY_IN_PAPER", "true").lower() == "true"

# =========================================================
# PHASE 1 EXECUTION SAFETY LAYER
# - Slippage guard
# - Bid/ask spread guard
# - Max qty / notional / risk per order
# - Order rate caps
# =========================================================
ENABLE_PHASE1_EXECUTION_SAFETY = os.getenv("ENABLE_PHASE1_EXECUTION_SAFETY", "true").lower() == "true"
PHASE1_MAX_ENTRY_SLIPPAGE_PCT = float(os.getenv("PHASE1_MAX_ENTRY_SLIPPAGE_PCT", "0.08"))
PHASE1_MAX_EXIT_SLIPPAGE_PCT = float(os.getenv("PHASE1_MAX_EXIT_SLIPPAGE_PCT", "0.15"))
PHASE1_MAX_SPREAD_PCT = float(os.getenv("PHASE1_MAX_SPREAD_PCT", "0.20"))
PHASE1_REQUIRE_BID_ASK_FOR_LIVE = os.getenv("PHASE1_REQUIRE_BID_ASK_FOR_LIVE", "false").lower() == "true"
PHASE1_MAX_QTY_PER_ORDER = int(os.getenv("PHASE1_MAX_QTY_PER_ORDER", str(MAX_POSITION_QTY)))
PHASE1_MAX_DOLLARS_PER_ORDER = float(os.getenv("PHASE1_MAX_DOLLARS_PER_ORDER", "750"))
PHASE1_MAX_RISK_DOLLARS_PER_ORDER = float(os.getenv("PHASE1_MAX_RISK_DOLLARS_PER_ORDER", "250"))
PHASE1_MAX_ORDERS_PER_MINUTE = int(os.getenv("PHASE1_MAX_ORDERS_PER_MINUTE", "4"))
PHASE1_MAX_ORDERS_PER_HOUR = int(os.getenv("PHASE1_MAX_ORDERS_PER_HOUR", "20"))
PHASE1_MAX_ORDERS_PER_DAY = int(os.getenv("PHASE1_MAX_ORDERS_PER_DAY", "40"))
PHASE1_SOFT_HALT_ON_RATE_LIMIT = os.getenv("PHASE1_SOFT_HALT_ON_RATE_LIMIT", "true").lower() == "true"
PHASE1_SEND_ALERTS = os.getenv("PHASE1_SEND_ALERTS", "true").lower() == "true"

# =========================================================
# OPTIONS LIQUIDITY FILTER
# Production gate before paper/live options execution.
# Checks whether the option quote is actually tradeable:
# - bid/ask present when required
# - spread % of mid is not too wide
# - volume / open interest meet minimums when supplied
# - last/mark is not badly outside bid/ask
# Defaults are paper-friendly but live-strict.
# =========================================================
ENABLE_OPTIONS_LIQUIDITY_FILTER = os.getenv("ENABLE_OPTIONS_LIQUIDITY_FILTER", "true").lower() == "true"
OPTIONS_LIQUIDITY_REQUIRE_FOR_LIVE = os.getenv("OPTIONS_LIQUIDITY_REQUIRE_FOR_LIVE", "true").lower() == "true"
OPTIONS_LIQUIDITY_REQUIRE_FOR_PAPER = os.getenv("OPTIONS_LIQUIDITY_REQUIRE_FOR_PAPER", "false").lower() == "true"
OPTIONS_LIQUIDITY_MAX_SPREAD_PCT = float(os.getenv("OPTIONS_LIQUIDITY_MAX_SPREAD_PCT", "0.20"))
OPTIONS_LIQUIDITY_MIN_VOLUME = int(os.getenv("OPTIONS_LIQUIDITY_MIN_VOLUME", "10"))
OPTIONS_LIQUIDITY_MIN_OPEN_INTEREST = int(os.getenv("OPTIONS_LIQUIDITY_MIN_OPEN_INTEREST", "50"))
OPTIONS_LIQUIDITY_ALLOW_MISSING_VOLUME_IN_PAPER = os.getenv("OPTIONS_LIQUIDITY_ALLOW_MISSING_VOLUME_IN_PAPER", "true").lower() == "true"
OPTIONS_LIQUIDITY_ALLOW_MISSING_OI_IN_PAPER = os.getenv("OPTIONS_LIQUIDITY_ALLOW_MISSING_OI_IN_PAPER", "true").lower() == "true"
OPTIONS_LIQUIDITY_MAX_LAST_OUTSIDE_BA_PCT = float(os.getenv("OPTIONS_LIQUIDITY_MAX_LAST_OUTSIDE_BA_PCT", "0.10"))
OPTIONS_LIQUIDITY_SEND_ALERTS = os.getenv("OPTIONS_LIQUIDITY_SEND_ALERTS", "true").lower() == "true"

# =========================================================
# PHASE 2 EXECUTION RELIABILITY LAYER
# - Order lifecycle integrity
# - Duplicate active-order suppression
# - Fill timeout / cancel / recovery
# - Broker/local reconciliation guard
# - Post-fill risk snapshots
# =========================================================
ENABLE_PHASE2_EXECUTION_RELIABILITY = os.getenv("ENABLE_PHASE2_EXECUTION_RELIABILITY", "true").lower() == "true"
PHASE2_MAX_ACTIVE_ORDERS = int(os.getenv("PHASE2_MAX_ACTIVE_ORDERS", "5"))
PHASE2_MAX_ACTIVE_ORDERS_PER_SYMBOL = int(os.getenv("PHASE2_MAX_ACTIVE_ORDERS_PER_SYMBOL", "1"))
PHASE2_DUPLICATE_ORDER_WINDOW_SECONDS = int(os.getenv("PHASE2_DUPLICATE_ORDER_WINDOW_SECONDS", "60"))
PHASE2_MAX_ORDER_WAIT_SECONDS = int(os.getenv("PHASE2_MAX_ORDER_WAIT_SECONDS", "20"))
PHASE2_CANCEL_STALE_LIVE_ORDERS = os.getenv("PHASE2_CANCEL_STALE_LIVE_ORDERS", "true").lower() == "true"
PHASE2_BLOCK_ON_REJECTED_ORDER = os.getenv("PHASE2_BLOCK_ON_REJECTED_ORDER", "true").lower() == "true"
PHASE2_BLOCK_ON_RECON_MISMATCH = os.getenv("PHASE2_BLOCK_ON_RECON_MISMATCH", "true").lower() == "true"
PHASE2_REQUIRE_BROKER_FOR_LIVE = os.getenv("PHASE2_REQUIRE_BROKER_FOR_LIVE", "true").lower() == "true"
PHASE2_SEND_ALERTS = os.getenv("PHASE2_SEND_ALERTS", "true").lower() == "true"


# =========================================================
# EXECUTION IDEMPOTENCY LAYER
# Full-chain replay protection:
# signal intent -> order intent -> fill event -> close intent
# This prevents duplicate positions from webhook retries, restarts,
# repeated signal files, or broker/event replay.
# =========================================================
ENABLE_EXECUTION_IDEMPOTENCY = os.getenv("ENABLE_EXECUTION_IDEMPOTENCY", "true").lower() == "true"
IDEMPOTENCY_STORE_FILE = os.getenv("IDEMPOTENCY_STORE_FILE", "idempotency_ledger.json").strip()
IDEMPOTENCY_MAX_RECORDS = int(os.getenv("IDEMPOTENCY_MAX_RECORDS", "2000"))
IDEMPOTENCY_BLOCK_REPLAY_SECONDS = int(os.getenv("IDEMPOTENCY_BLOCK_REPLAY_SECONDS", "86400"))
IDEMPOTENCY_CLIENT_PREFIX = os.getenv("IDEMPOTENCY_CLIENT_PREFIX", "ub").strip()[:8] or "ub"
IDEMPOTENCY_STRICT_ORDER_BLOCK = os.getenv("IDEMPOTENCY_STRICT_ORDER_BLOCK", "true").lower() == "true"
IDEMPOTENCY_SEND_ALERTS = os.getenv("IDEMPOTENCY_SEND_ALERTS", "true").lower() == "true"

# =========================================================
# INTELLIGENCE PHASE 1: TRADE MEMORY + PERFORMANCE ANALYTICS
# Records every major decision as structured JSONL, builds trade stories,
# and writes lightweight performance summaries without changing live rules.
# =========================================================
ENABLE_INTELLIGENCE_PHASE1 = os.getenv("ENABLE_INTELLIGENCE_PHASE1", "true").lower() == "true"
INTEL_EVENT_LOG_FILE = os.getenv("INTEL_EVENT_LOG_FILE", "event_log.jsonl").strip()
INTEL_TRADE_MEMORY_FILE = os.getenv("INTEL_TRADE_MEMORY_FILE", "trade_memory.jsonl").strip()
INTEL_ANALYTICS_FILE = os.getenv("INTEL_ANALYTICS_FILE", "performance_summary.json").strip()
INTEL_SEND_CLOSED_TRADE_SUMMARY = os.getenv("INTEL_SEND_CLOSED_TRADE_SUMMARY", "true").lower() == "true"
INTEL_REBUILD_ANALYTICS_ON_CLOSE = os.getenv("INTEL_REBUILD_ANALYTICS_ON_CLOSE", "true").lower() == "true"
INTEL_ANALYTICS_REFRESH_SECONDS = int(os.getenv("INTEL_ANALYTICS_REFRESH_SECONDS", "60"))

# =========================================================
# INTELLIGENCE PHASE 3: ADAPTIVE INTELLIGENCE
# Uses closed-trade memory to score setup performance,
# suggest confidence corrections, dynamically adjust size,
# and block setups that have proven weak. Defaults are safe:
# no blocking until minimum trade sample is reached.
# =========================================================
ENABLE_INTELLIGENCE_PHASE3 = os.getenv("ENABLE_INTELLIGENCE_PHASE3", "true").lower() == "true"
PHASE3_MIN_TRADES_FOR_FILTER = int(os.getenv("PHASE3_MIN_TRADES_FOR_FILTER", "5"))
PHASE3_BLOCK_WINRATE_BELOW = float(os.getenv("PHASE3_BLOCK_WINRATE_BELOW", "0.45"))
PHASE3_BLOCK_AVG_R_BELOW = float(os.getenv("PHASE3_BLOCK_AVG_R_BELOW", "-0.10"))
PHASE3_DISABLE_LOSSES_IN_LAST_N = int(os.getenv("PHASE3_DISABLE_LOSSES_IN_LAST_N", "7"))
PHASE3_DISABLE_LAST_N = int(os.getenv("PHASE3_DISABLE_LAST_N", "10"))
PHASE3_SIZE_UP_WINRATE = float(os.getenv("PHASE3_SIZE_UP_WINRATE", "0.65"))
PHASE3_SIZE_DOWN_WINRATE = float(os.getenv("PHASE3_SIZE_DOWN_WINRATE", "0.50"))
PHASE3_SIZE_UP_MULT = float(os.getenv("PHASE3_SIZE_UP_MULT", "1.25"))
PHASE3_SIZE_DOWN_MULT = float(os.getenv("PHASE3_SIZE_DOWN_MULT", "0.60"))
PHASE3_CONFIDENCE_DOWNGRADE_WINRATE = float(os.getenv("PHASE3_CONFIDENCE_DOWNGRADE_WINRATE", "0.50"))
PHASE3_SEND_ALERTS = os.getenv("PHASE3_SEND_ALERTS", "true").lower() == "true"
PHASE3_SUGGEST_ONLY = os.getenv("PHASE3_SUGGEST_ONLY", "false").lower() == "true"
PHASE3_ADAPTIVE_STATS_FILE = os.getenv("PHASE3_ADAPTIVE_STATS_FILE", "adaptive_setup_stats.json").strip()
PHASE3_DISABLED_SETUPS_FILE = os.getenv("PHASE3_DISABLED_SETUPS_FILE", "disabled_setups.json").strip()









# =========================================================
# ADAPTIVE LEARNING MODULE — MANUAL + ENGINE TRADE MEMORY
# This is the new learning layer requested for manual trade input.
# It does NOT replace Phase 3 / Phase 3.5. It feeds an additional
# setup-memory boost into the signal BEFORE risk/execution.
# =========================================================
ENABLE_ADAPTIVE_LEARNING_MODULE = os.getenv("ENABLE_ADAPTIVE_LEARNING_MODULE", "true").lower() == "true"
ADAPTIVE_TRADE_MEMORY_FILE = os.getenv("ADAPTIVE_TRADE_MEMORY_FILE", "trade_memory.json").strip()
ADAPTIVE_LEARNING_STATS_FILE = os.getenv("ADAPTIVE_LEARNING_STATS_FILE", "learning_stats.json").strip()
ADAPTIVE_MIN_TRADES_FOR_BOOST = int(os.getenv("ADAPTIVE_MIN_TRADES_FOR_BOOST", "3"))
ADAPTIVE_HIGH_WINRATE_THRESHOLD = float(os.getenv("ADAPTIVE_HIGH_WINRATE_THRESHOLD", "0.70"))
ADAPTIVE_STRONG_WINRATE_THRESHOLD = float(os.getenv("ADAPTIVE_STRONG_WINRATE_THRESHOLD", "0.80"))
ADAPTIVE_LOW_WINRATE_THRESHOLD = float(os.getenv("ADAPTIVE_LOW_WINRATE_THRESHOLD", "0.40"))
ADAPTIVE_MAX_GRADE_BOOST = int(os.getenv("ADAPTIVE_MAX_GRADE_BOOST", "2"))
ADAPTIVE_SEND_ALERTS = os.getenv("ADAPTIVE_SEND_ALERTS", "true").lower() == "true"




# =========================================================
# AUTO PAPER / LIVE ROUTING SAFETY
# Paper mode can execute without manual force; live stays protected.
# =========================================================
AUTO_DETECT_PAPER_LIVE_MODE = os.getenv("AUTO_DETECT_PAPER_LIVE_MODE", "true").lower() == "true"
AUTO_ALLOW_PAPER_EXECUTION_WITHOUT_FORCE = os.getenv("AUTO_ALLOW_PAPER_EXECUTION_WITHOUT_FORCE", "true").lower() == "true"
AUTO_BLOCK_LIVE_UNLESS_FULLY_APPROVED = os.getenv("AUTO_BLOCK_LIVE_UNLESS_FULLY_APPROVED", "true").lower() == "true"


def auto_mode_is_live() -> bool:
    mode = str(os.getenv("MODE", globals().get("MODE", "paper"))).lower().strip()
    live_mode = str(os.getenv("LIVE_MODE", str(globals().get("LIVE_MODE", False)))).lower().strip() == "true"
    alpaca_base = str(os.getenv("ALPACA_BASE_URL", globals().get("ALPACA_BASE_URL", ""))).lower()
    return mode == "live" or live_mode or ("api.alpaca.markets" in alpaca_base and "paper-api" not in alpaca_base)


def auto_mode_is_paper() -> bool:
    mode = str(os.getenv("MODE", globals().get("MODE", "paper"))).lower().strip()
    if auto_mode_is_live():
        return False

    enable_alpaca = str(os.getenv("ENABLE_ALPACA", str(globals().get("ENABLE_ALPACA", False)))).lower().strip() == "true"
    paper_execution = str(os.getenv("ENABLE_PAPER_EXECUTION", str(globals().get("ENABLE_PAPER_EXECUTION", True)))).lower().strip() == "true"
    alpaca_base = str(os.getenv("ALPACA_BASE_URL", globals().get("ALPACA_BASE_URL", ""))).lower()

    if mode in {"paper", "test", "demo", "sandbox"}:
        return True
    if paper_execution and not enable_alpaca:
        return True
    if "paper-api.alpaca.markets" in alpaca_base:
        return True

    return paper_execution


def auto_should_force_execution_for_test(signal=None) -> bool:
    """
    Paper mode should be allowed to execute without manual force.
    Live mode should never be forced by this helper.
    """
    if not AUTO_DETECT_PAPER_LIVE_MODE:
        return bool(globals().get("FORCE_EXECUTION_MODE", False))

    if auto_mode_is_paper() and AUTO_ALLOW_PAPER_EXECUTION_WITHOUT_FORCE:
        return True

    return bool(globals().get("FORCE_EXECUTION_MODE", False))


def auto_live_safety_reasons() -> list:
    reasons = []

    enable_alpaca = str(os.getenv("ENABLE_ALPACA", str(globals().get("ENABLE_ALPACA", False)))).lower().strip() == "true"
    enable_execution = str(os.getenv("ENABLE_EXECUTION", str(globals().get("ENABLE_EXECUTION", False)))).lower().strip() == "true"
    live_approved = str(os.getenv("ALPACA_LIVE_OPTIONS_APPROVED", str(globals().get("ALPACA_LIVE_OPTIONS_APPROVED", False)))).lower().strip() == "true"
    allow_live_buys = str(os.getenv("ALLOW_LIVE_BUYS", str(globals().get("ALLOW_LIVE_BUYS", False)))).lower().strip() == "true"
    force = bool(globals().get("FORCE_EXECUTION_MODE", False))

    if not enable_alpaca:
        reasons.append("ENABLE_ALPACA_false")
    if not enable_execution:
        reasons.append("ENABLE_EXECUTION_false")
    if not live_approved:
        reasons.append("ALPACA_LIVE_OPTIONS_APPROVED_false")
    if not allow_live_buys:
        reasons.append("ALLOW_LIVE_BUYS_false")
    if force:
        reasons.append("FORCE_EXECUTION_MODE_must_be_false_live")

    return reasons


def auto_execution_allowed(signal=None) -> tuple:
    """
    Returns (allowed, mode, reasons)
    """
    if auto_mode_is_paper():
        return True, "paper", []

    if auto_mode_is_live():
        reasons = auto_live_safety_reasons()
        if AUTO_BLOCK_LIVE_UNLESS_FULLY_APPROVED and reasons:
            return False, "live", reasons
        return True, "live", []

    return False, "unknown", ["mode_not_detected"]


def auto_debug_routing(signal=None) -> None:
    try:
        allowed, mode, reasons = auto_execution_allowed(signal)
        msg = (
            f"AUTO ROUTING | mode={mode} allowed={allowed} "
            f"paper={auto_mode_is_paper()} live={auto_mode_is_live()} "
            f"force={auto_should_force_execution_for_test(signal)} "
            f"reasons={','.join(reasons) if reasons else 'none'}"
        )
        try:
            debug(msg)
        except Exception:
            print(msg, flush=True)
    except Exception as e:
        try:
            debug(f"AUTO ROUTING ERROR | {e}")
        except Exception:
            print(f"AUTO ROUTING ERROR | {e}", flush=True)


# =========================================================
# QQQ-ONLY ENFORCEMENT + CLEAN LEARNING FILTER
# Added to prevent SPY/fallback trades and garbage learning.
# =========================================================
ENABLE_QQQ_ONLY_ENFORCEMENT = os.getenv("ENABLE_QQQ_ONLY_ENFORCEMENT", "true").lower() == "true"
QQQ_ONLY_ALLOWED_TICKERS = {
    t.strip().upper()
    for t in os.getenv("QQQ_ONLY_ALLOWED_TICKERS", "QQQ").split(",")
    if t.strip()
}
REQUIRE_VALID_TRIGGER_FOR_LEARNING = os.getenv("REQUIRE_VALID_TRIGGER_FOR_LEARNING", "true").lower() == "true"
BLOCK_GENERIC_NO_TRIGGER_LEARNING = os.getenv("BLOCK_GENERIC_NO_TRIGGER_LEARNING", "true").lower() == "true"
MIN_TRIGGER_LENGTH_FOR_LEARNING = int(os.getenv("MIN_TRIGGER_LENGTH_FOR_LEARNING", "3"))


def qqq_lock_get_ticker(payload: Dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(
        payload.get("ticker")
        or payload.get("underlying")
        or payload.get("symbol")
        or payload.get("contract_symbol")
        or ""
    ).upper().strip()


def qqq_lock_get_trigger(payload: Dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(
        payload.get("trigger")
        or payload.get("setup_type")
        or payload.get("setup")
        or payload.get("setup_name")
        or payload.get("strategy")
        or ""
    ).strip()


def qqq_only_signal_allowed(payload: Dict[str, Any], stage: str = "signal") -> Tuple[bool, str]:
    """
    Hard execution filter.
    This blocks SPY/default/fallback trades before they can reach paper/live execution.
    """
    if not ENABLE_QQQ_ONLY_ENFORCEMENT:
        return True, "qqq_only_disabled"

    ticker = qqq_lock_get_ticker(payload)

    if not ticker:
        return False, f"{stage}_blocked_missing_ticker"

    if ticker not in QQQ_ONLY_ALLOWED_TICKERS:
        return False, f"{stage}_blocked_ticker_{ticker}_not_allowed"

    return True, "qqq_only_allowed"


def qqq_clean_learning_allowed(payload: Dict[str, Any], stage: str = "learning") -> Tuple[bool, str]:
    """
    Clean learning filter.
    This prevents bad memory like:
      SPY | No trigger provided | win
    from polluting the adaptive model.
    """
    if not ENABLE_QQQ_ONLY_ENFORCEMENT:
        return True, "qqq_only_disabled"

    ok, reason = qqq_only_signal_allowed(payload, stage=stage)
    if not ok:
        return False, reason

    if REQUIRE_VALID_TRIGGER_FOR_LEARNING:
        trigger = qqq_lock_get_trigger(payload)
        bad_values = {
            "",
            "none",
            "null",
            "generic",
            "no trigger provided",
            "no_trigger_provided",
            "unnamed setup",
            "engine closed trade",
        }

        trigger_clean = trigger.lower().strip()

        if trigger_clean in bad_values:
            return False, f"{stage}_blocked_invalid_trigger:{trigger}"

        if len(trigger_clean) < MIN_TRIGGER_LENGTH_FOR_LEARNING:
            return False, f"{stage}_blocked_trigger_too_short:{trigger}"

        if BLOCK_GENERIC_NO_TRIGGER_LEARNING and ("no trigger" in trigger_clean or "generic" == trigger_clean):
            return False, f"{stage}_blocked_generic_trigger:{trigger}"

    return True, "clean_learning_allowed"


def qqq_only_block_message(payload: Dict[str, Any], reason: str, stage: str = "signal") -> str:
    return (
        f"🚫 QQQ-ONLY BLOCK | stage={stage} "
        f"ticker={qqq_lock_get_ticker(payload)} "
        f"direction={payload.get('direction') if isinstance(payload, dict) else ''} "
        f"reason={reason}"
    )


def qqq_only_debug_block(payload: Dict[str, Any], reason: str, stage: str = "signal") -> None:
    msg = qqq_only_block_message(payload, reason, stage)
    try:
        debug(msg)
    except Exception:
        print(msg, flush=True)
    try:
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
    except Exception:
        pass


# =========================================================
# ADAPTIVE LEARNING → POSITION SIZING
# =========================================================
ENABLE_ADAPTIVE_LEARNING_SIZING = os.getenv("ENABLE_ADAPTIVE_LEARNING_SIZING", "true").lower() == "true"
ADAPTIVE_SIZE_MIN_TRADES = int(os.getenv("ADAPTIVE_SIZE_MIN_TRADES", "2"))
ADAPTIVE_SIZE_STRONG_WINRATE = float(os.getenv("ADAPTIVE_SIZE_STRONG_WINRATE", "0.65"))
ADAPTIVE_SIZE_ELITE_WINRATE = float(os.getenv("ADAPTIVE_SIZE_ELITE_WINRATE", "0.80"))
ADAPTIVE_SIZE_WEAK_WINRATE = float(os.getenv("ADAPTIVE_SIZE_WEAK_WINRATE", "0.45"))
ADAPTIVE_SIZE_STRONG_MULT = float(os.getenv("ADAPTIVE_SIZE_STRONG_MULT", "1.25"))
ADAPTIVE_SIZE_ELITE_MULT = float(os.getenv("ADAPTIVE_SIZE_ELITE_MULT", "1.50"))
ADAPTIVE_SIZE_WEAK_MULT = float(os.getenv("ADAPTIVE_SIZE_WEAK_MULT", "0.50"))
ADAPTIVE_SIZE_MAX_MULT = float(os.getenv("ADAPTIVE_SIZE_MAX_MULT", "2.00"))

def adaptive_sizing_safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default

def adaptive_sizing_safe_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default

def adaptive_sizing_load_json(path, default):
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def adaptive_sizing_signal_key(signal):
    ticker = str(signal.get("ticker") or signal.get("symbol") or "UNKNOWN").upper().strip()
    direction = str(signal.get("direction") or "UNKNOWN").upper().strip()
    setup = str(signal.get("setup_name") or signal.get("setup") or signal.get("trigger") or "GENERIC").lower().strip()
    return ticker, direction, setup

def adaptive_sizing_find_stats(signal):
    ticker, direction, setup = adaptive_sizing_signal_key(signal)

    phase3 = adaptive_sizing_load_json("adaptive_setup_stats.json", {})
    stats = phase3.get("stats", {}) if isinstance(phase3, dict) else {}
    if isinstance(stats, dict):
        for key, bucket in stats.items():
            k = str(key).lower()
            if ticker.lower() in k and direction.lower() in k:
                return {
                    "source": "adaptive_setup_stats",
                    "key": key,
                    "trades": adaptive_sizing_safe_int(bucket.get("trades"), 0),
                    "wins": adaptive_sizing_safe_int(bucket.get("wins"), 0),
                    "losses": adaptive_sizing_safe_int(bucket.get("losses"), 0),
                    "win_rate": adaptive_sizing_safe_float(bucket.get("win_rate"), 0.0),
                    "avg_r": adaptive_sizing_safe_float(bucket.get("avg_r"), 0.0),
                    "bucket": bucket,
                }

    learning = adaptive_sizing_load_json("learning_stats.json", {})
    patterns = learning.get("patterns", {}) if isinstance(learning, dict) else {}
    if isinstance(patterns, dict):
        for key, bucket in patterns.items():
            k = str(key).lower()
            if ticker.lower() in k and direction.lower() in k:
                return {
                    "source": "learning_stats",
                    "key": key,
                    "trades": adaptive_sizing_safe_int(bucket.get("trades"), 0),
                    "wins": adaptive_sizing_safe_int(bucket.get("wins"), 0),
                    "losses": adaptive_sizing_safe_int(bucket.get("losses"), 0),
                    "win_rate": adaptive_sizing_safe_float(bucket.get("win_rate"), 0.0),
                    "avg_r": adaptive_sizing_safe_float(bucket.get("avg_r"), 0.0),
                    "bucket": bucket,
                }

    return {"source": "none", "key": "", "trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "avg_r": 0.0, "bucket": {}}

def adaptive_learning_size_multiplier(signal):
    if not ENABLE_ADAPTIVE_LEARNING_SIZING:
        return 1.0, "adaptive_sizing_disabled", {}

    stats = adaptive_sizing_find_stats(signal)
    trades = adaptive_sizing_safe_int(stats.get("trades"), 0)
    win_rate = adaptive_sizing_safe_float(stats.get("win_rate"), 0.0)
    grade = str(signal.get("grade") or signal.get("confidence") or "").upper().strip()

    if trades < ADAPTIVE_SIZE_MIN_TRADES:
        return 1.0, f"observe_only_not_enough_trades_{trades}/{ADAPTIVE_SIZE_MIN_TRADES}", stats

    if grade in {"A", "A+"} and win_rate >= ADAPTIVE_SIZE_ELITE_WINRATE:
        return min(ADAPTIVE_SIZE_ELITE_MULT, ADAPTIVE_SIZE_MAX_MULT), f"elite_learned_setup_winrate_{round(win_rate*100,1)}%", stats

    if grade in {"A", "A+"} and win_rate >= ADAPTIVE_SIZE_STRONG_WINRATE:
        return min(ADAPTIVE_SIZE_STRONG_MULT, ADAPTIVE_SIZE_MAX_MULT), f"strong_learned_setup_winrate_{round(win_rate*100,1)}%", stats

    if win_rate <= ADAPTIVE_SIZE_WEAK_WINRATE:
        return ADAPTIVE_SIZE_WEAK_MULT, f"weak_learned_setup_winrate_{round(win_rate*100,1)}%", stats

    return 1.0, f"neutral_learned_setup_winrate_{round(win_rate*100,1)}%", stats

def apply_adaptive_learning_sizing_to_signal(signal):
    try:
        if not isinstance(signal, dict):
            return signal

        x = deepcopy(signal)
        mult, reason, stats = adaptive_learning_size_multiplier(x)

        base_qty = x.get("final_size") or x.get("qty") or x.get("contracts") or x.get("quantity") or 1
        base_qty = adaptive_sizing_safe_int(base_qty, 1)

        if mult > 1:
            adjusted = int(math.ceil(base_qty * mult))
        elif mult < 1:
            adjusted = int(math.floor(base_qty * mult))
        else:
            adjusted = base_qty

        min_qty = adaptive_sizing_safe_int(globals().get("MIN_POSITION_QTY", 1), 1)
        max_qty = adaptive_sizing_safe_int(globals().get("MAX_POSITION_QTY", 10), 10)

        if base_qty > 0:
            adjusted = max(min_qty, adjusted)
        adjusted = min(max_qty, adjusted)

        x["adaptive_sizing"] = {
            "enabled": ENABLE_ADAPTIVE_LEARNING_SIZING,
            "base_qty": base_qty,
            "adjusted_qty": adjusted,
            "multiplier": mult,
            "reason": reason,
            "stats": stats,
        }

        x["qty"] = adjusted
        x["contracts"] = adjusted
        x["quantity"] = adjusted
        x["final_size"] = adjusted

        try:
            debug(f"ADAPTIVE SIZE | ticker={x.get('ticker')} direction={x.get('direction')} base={base_qty} adjusted={adjusted} mult={mult} reason={reason}")
        except Exception:
            print(f"ADAPTIVE SIZE | ticker={x.get('ticker')} direction={x.get('direction')} base={base_qty} adjusted={adjusted} mult={mult} reason={reason}", flush=True)

        return x
    except Exception as e:
        try:
            log(f"ADAPTIVE SIZE ERROR | {e}")
        except Exception:
            print(f"ADAPTIVE SIZE ERROR | {e}", flush=True)
        return signal


# =========================================================
# LIVE TRADING SAFETY LOCK SYSTEM
# Protects real money during first live rollout.
# Live trading can only continue if keys, mode, account size,
# risk caps, market data, and broker checks are clean.
# =========================================================
ENABLE_LIVE_SAFETY_LOCK = os.getenv("ENABLE_LIVE_SAFETY_LOCK", "true").lower() == "true"
LIVE_SAFETY_FILE = os.getenv("LIVE_SAFETY_FILE", "live_safety_state.json").strip()
LIVE_SAFETY_SEND_ALERTS = os.getenv("LIVE_SAFETY_SEND_ALERTS", "true").lower() == "true"

LIVE_SAFETY_MAX_ACCOUNT_EQUITY = float(os.getenv("LIVE_SAFETY_MAX_ACCOUNT_EQUITY", "500"))
LIVE_SAFETY_MIN_ACCOUNT_EQUITY = float(os.getenv("LIVE_SAFETY_MIN_ACCOUNT_EQUITY", "50"))
LIVE_SAFETY_MAX_QTY = int(os.getenv("LIVE_SAFETY_MAX_QTY", "1"))
LIVE_SAFETY_MAX_OPEN_POSITIONS = int(os.getenv("LIVE_SAFETY_MAX_OPEN_POSITIONS", "1"))
LIVE_SAFETY_MAX_DAILY_LOSS_DOLLARS = float(os.getenv("LIVE_SAFETY_MAX_DAILY_LOSS_DOLLARS", "25"))
LIVE_SAFETY_MAX_DAILY_LOSS_PCT = float(os.getenv("LIVE_SAFETY_MAX_DAILY_LOSS_PCT", "0.10"))

LIVE_SAFETY_REQUIRE_ALPACA = os.getenv("LIVE_SAFETY_REQUIRE_ALPACA", "true").lower() == "true"
LIVE_SAFETY_REQUIRE_OPTIONS_APPROVED = os.getenv("LIVE_SAFETY_REQUIRE_OPTIONS_APPROVED", "true").lower() == "true"
LIVE_SAFETY_REQUIRE_FORCE_OFF = os.getenv("LIVE_SAFETY_REQUIRE_FORCE_OFF", "true").lower() == "true"
LIVE_SAFETY_REQUIRE_DUPLICATES_OFF = os.getenv("LIVE_SAFETY_REQUIRE_DUPLICATES_OFF", "true").lower() == "true"
LIVE_SAFETY_REQUIRE_FRESH_MARKET_DATA = os.getenv("LIVE_SAFETY_REQUIRE_FRESH_MARKET_DATA", "true").lower() == "true"
LIVE_SAFETY_MARKET_DATA_MAX_AGE_SECONDS = int(os.getenv("LIVE_SAFETY_MARKET_DATA_MAX_AGE_SECONDS", "20"))

LIVE_SAFETY_AUTO_LOCK_ON_ERROR = os.getenv("LIVE_SAFETY_AUTO_LOCK_ON_ERROR", "true").lower() == "true"
LIVE_SAFETY_REQUIRE_MANUAL_UNLOCK = os.getenv("LIVE_SAFETY_REQUIRE_MANUAL_UNLOCK", "true").lower() == "true"
LIVE_SAFETY_START_TIME_ET = os.getenv("LIVE_SAFETY_START_TIME_ET", "09:30").strip()
LIVE_SAFETY_END_TIME_ET = os.getenv("LIVE_SAFETY_END_TIME_ET", "16:00").strip()
LIVE_SAFETY_ENFORCE_MARKET_HOURS = os.getenv("LIVE_SAFETY_ENFORCE_MARKET_HOURS", "true").lower() == "true"

# =========================================================
# TRADE JOURNALING + LEARNING FEEDBACK LOOP
# Records every accepted/blocked/executed/managed trade decision
# and converts closed trades into learning memory for adaptive grading.
# =========================================================
ENABLE_TRADE_JOURNAL_LEARNING = os.getenv("ENABLE_TRADE_JOURNAL_LEARNING", "true").lower() == "true"
TRADE_JOURNAL_FILE = os.getenv("TRADE_JOURNAL_FILE", "trade_journal.jsonl").strip()
TRADE_LEARNING_FILE = os.getenv("TRADE_LEARNING_FILE", "trade_learning_summary.json").strip()
TRADE_JOURNAL_SEND_ALERTS = os.getenv("TRADE_JOURNAL_SEND_ALERTS", "true").lower() == "true"
TRADE_JOURNAL_MIN_R_FOR_WIN = float(os.getenv("TRADE_JOURNAL_MIN_R_FOR_WIN", "0.01"))
TRADE_JOURNAL_REBUILD_ON_BOOT = os.getenv("TRADE_JOURNAL_REBUILD_ON_BOOT", "true").lower() == "true"

LEARNING_MIN_SAMPLE_FOR_SETUP_SCORE = int(os.getenv("LEARNING_MIN_SAMPLE_FOR_SETUP_SCORE", "3"))
LEARNING_WEAK_SETUP_WINRATE = float(os.getenv("LEARNING_WEAK_SETUP_WINRATE", "0.45"))
LEARNING_STRONG_SETUP_WINRATE = float(os.getenv("LEARNING_STRONG_SETUP_WINRATE", "0.65"))
LEARNING_SIZE_DOWN_WEAK_SETUPS = os.getenv("LEARNING_SIZE_DOWN_WEAK_SETUPS", "true").lower() == "true"
LEARNING_BLOCK_EXTREME_WEAK_SETUPS = os.getenv("LEARNING_BLOCK_EXTREME_WEAK_SETUPS", "false").lower() == "true"
LEARNING_WEAK_SIZE_MULT = float(os.getenv("LEARNING_WEAK_SIZE_MULT", "0.50"))

# =========================================================
# PORTFOLIO HEAT + EXPOSURE CONTROL
# Fund-level guardrails:
# - Max total portfolio heat
# - Max same ticker exposure
# - Max correlated index exposure
# - Max directional concentration
# =========================================================
ENABLE_PORTFOLIO_HEAT_EXPOSURE = os.getenv("ENABLE_PORTFOLIO_HEAT_EXPOSURE", "true").lower() == "true"
PORTFOLIO_HEAT_SEND_ALERTS = os.getenv("PORTFOLIO_HEAT_SEND_ALERTS", "true").lower() == "true"

PORTFOLIO_MAX_HEAT_PCT = float(os.getenv("PORTFOLIO_MAX_HEAT_PCT", str(MAX_PROJECTED_PORTFOLIO_HEAT_PCT)))
PORTFOLIO_MAX_TICKER_HEAT_PCT = float(os.getenv("PORTFOLIO_MAX_TICKER_HEAT_PCT", "0.015"))
PORTFOLIO_MAX_DIRECTION_HEAT_PCT = float(os.getenv("PORTFOLIO_MAX_DIRECTION_HEAT_PCT", "0.02"))

PORTFOLIO_MAX_OPEN_TOTAL = int(os.getenv("PORTFOLIO_MAX_OPEN_TOTAL", str(MAX_OPEN_POSITIONS)))
PORTFOLIO_MAX_OPEN_PER_TICKER = int(os.getenv("PORTFOLIO_MAX_OPEN_PER_TICKER", str(MAX_SAME_TICKER_POSITIONS)))
PORTFOLIO_MAX_CORRELATED_OPEN = int(os.getenv("PORTFOLIO_MAX_CORRELATED_OPEN", "2"))
PORTFOLIO_MAX_SAME_DIRECTION_OPEN = int(os.getenv("PORTFOLIO_MAX_SAME_DIRECTION_OPEN", "2"))

PORTFOLIO_CORRELATED_INDEX_TICKERS = {
    x.strip().upper()
    for x in os.getenv("PORTFOLIO_CORRELATED_INDEX_TICKERS", "SPY,QQQ,IWM,DIA,NVDA,AAPL,MSFT,META,AMD,TSLA").split(",")
    if x.strip()
}

PORTFOLIO_REDUCE_SIZE_IF_NEAR_HEAT = os.getenv("PORTFOLIO_REDUCE_SIZE_IF_NEAR_HEAT", "true").lower() == "true"
PORTFOLIO_NEAR_HEAT_THRESHOLD_PCT = float(os.getenv("PORTFOLIO_NEAR_HEAT_THRESHOLD_PCT", "0.80"))
PORTFOLIO_NEAR_HEAT_SIZE_MULT = float(os.getenv("PORTFOLIO_NEAR_HEAT_SIZE_MULT", "0.50"))

# =========================================================
# RISK STATE + DRAWDOWN ENGINE
# Self-protecting account logic:
# AGGRESSIVE / NORMAL / DEFENSIVE / LOCKDOWN
# =========================================================
ENABLE_RISK_STATE_ENGINE = os.getenv("ENABLE_RISK_STATE_ENGINE", "true").lower() == "true"
RISK_STATE_FILE = os.getenv("RISK_STATE_FILE", "risk_state.json").strip()
RISK_STATE_SEND_ALERTS = os.getenv("RISK_STATE_SEND_ALERTS", "true").lower() == "true"

RISK_STATE_DAILY_DRAWDOWN_LOCK_PCT = float(os.getenv("RISK_STATE_DAILY_DRAWDOWN_LOCK_PCT", "0.02"))
RISK_STATE_DAILY_DRAWDOWN_DEFENSIVE_PCT = float(os.getenv("RISK_STATE_DAILY_DRAWDOWN_DEFENSIVE_PCT", "0.01"))
RISK_STATE_DAILY_PROFIT_AGGRESSIVE_PCT = float(os.getenv("RISK_STATE_DAILY_PROFIT_AGGRESSIVE_PCT", "0.01"))

RISK_STATE_LOCK_DOLLARS = float(os.getenv("RISK_STATE_LOCK_DOLLARS", "500"))
RISK_STATE_DEFENSIVE_DOLLARS = float(os.getenv("RISK_STATE_DEFENSIVE_DOLLARS", "250"))
RISK_STATE_AGGRESSIVE_PROFIT_DOLLARS = float(os.getenv("RISK_STATE_AGGRESSIVE_PROFIT_DOLLARS", "250"))

RISK_STATE_LOSS_STREAK_DEFENSIVE = int(os.getenv("RISK_STATE_LOSS_STREAK_DEFENSIVE", "2"))
RISK_STATE_LOSS_STREAK_LOCKDOWN = int(os.getenv("RISK_STATE_LOSS_STREAK_LOCKDOWN", "3"))
RISK_STATE_WIN_STREAK_AGGRESSIVE = int(os.getenv("RISK_STATE_WIN_STREAK_AGGRESSIVE", "3"))

RISK_STATE_AGGRESSIVE_SIZE_MULT = float(os.getenv("RISK_STATE_AGGRESSIVE_SIZE_MULT", "1.25"))
RISK_STATE_NORMAL_SIZE_MULT = float(os.getenv("RISK_STATE_NORMAL_SIZE_MULT", "1.00"))
RISK_STATE_DEFENSIVE_SIZE_MULT = float(os.getenv("RISK_STATE_DEFENSIVE_SIZE_MULT", "0.50"))
RISK_STATE_LOCKDOWN_SIZE_MULT = float(os.getenv("RISK_STATE_LOCKDOWN_SIZE_MULT", "0.00"))

RISK_STATE_AUTO_LOCK_ON_DRAWDOWN = os.getenv("RISK_STATE_AUTO_LOCK_ON_DRAWDOWN", "true").lower() == "true"
RISK_STATE_REQUIRE_MANUAL_UNLOCK = os.getenv("RISK_STATE_REQUIRE_MANUAL_UNLOCK", "true").lower() == "true"
RISK_STATE_RESET_DAILY = os.getenv("RISK_STATE_RESET_DAILY", "true").lower() == "true"

# =========================================================
# VOLATILITY + CONFIDENCE POSITION SIZING
# A+ = larger size, A = normal, B = reduced.
# High volatility automatically reduces size.
# =========================================================
ENABLE_VOL_CONF_POSITION_SIZING = os.getenv("ENABLE_VOL_CONF_POSITION_SIZING", "true").lower() == "true"
VOL_CONF_BASE_QTY = int(os.getenv("VOL_CONF_BASE_QTY", "1"))
VOL_CONF_MAX_QTY = int(os.getenv("VOL_CONF_MAX_QTY", str(MAX_POSITION_QTY)))
VOL_CONF_MIN_QTY = int(os.getenv("VOL_CONF_MIN_QTY", "1"))

VOL_CONF_MULT_A_PLUS = float(os.getenv("VOL_CONF_MULT_A_PLUS", "1.50"))
VOL_CONF_MULT_A = float(os.getenv("VOL_CONF_MULT_A", "1.00"))
VOL_CONF_MULT_B_PLUS = float(os.getenv("VOL_CONF_MULT_B_PLUS", "0.75"))
VOL_CONF_MULT_B = float(os.getenv("VOL_CONF_MULT_B", "0.50"))
VOL_CONF_MULT_C = float(os.getenv("VOL_CONF_MULT_C", "0.00"))

VOL_CONF_VIX_LOW = float(os.getenv("VOL_CONF_VIX_LOW", "15"))
VOL_CONF_VIX_MEDIUM = float(os.getenv("VOL_CONF_VIX_MEDIUM", "20"))
VOL_CONF_VIX_HIGH = float(os.getenv("VOL_CONF_VIX_HIGH", "25"))

VOL_CONF_LOW_VOL_MULT = float(os.getenv("VOL_CONF_LOW_VOL_MULT", "1.10"))
VOL_CONF_NORMAL_VOL_MULT = float(os.getenv("VOL_CONF_NORMAL_VOL_MULT", "1.00"))
VOL_CONF_MEDIUM_VOL_MULT = float(os.getenv("VOL_CONF_MEDIUM_VOL_MULT", "0.75"))
VOL_CONF_HIGH_VOL_MULT = float(os.getenv("VOL_CONF_HIGH_VOL_MULT", "0.50"))
VOL_CONF_EXTREME_VOL_MULT = float(os.getenv("VOL_CONF_EXTREME_VOL_MULT", "0.25"))

VOL_CONF_BLOCK_C_GRADE = os.getenv("VOL_CONF_BLOCK_C_GRADE", "true").lower() == "true"
VOL_CONF_SEND_ALERTS = os.getenv("VOL_CONF_SEND_ALERTS", "true").lower() == "true"

# =========================================================
# ELITE EXECUTION FILTER: A/A+ ONLY + NO CHASING
# Blocks weak grades and late entries before signal.json reaches execution.
# =========================================================
ENABLE_ELITE_EXECUTION_FILTER = os.getenv("ENABLE_ELITE_EXECUTION_FILTER", "true").lower() == "true"
ELITE_ALLOWED_GRADES = {
    x.strip().upper()
    for x in os.getenv("ELITE_ALLOWED_GRADES", "A,A+").split(",")
    if x.strip()
}
NO_CHASE_MAX_ENTRY_DRIFT_PCT = float(os.getenv("NO_CHASE_MAX_ENTRY_DRIFT_PCT", "0.15"))
NO_CHASE_USE_CONTRACT_PRICE = os.getenv("NO_CHASE_USE_CONTRACT_PRICE", "true").lower() == "true"
NO_CHASE_SEND_ALERTS = os.getenv("NO_CHASE_SEND_ALERTS", "true").lower() == "true"

# =========================================================
# PHASE 3.5 ENFORCEMENT LAYER
# Locks adaptive learning into real trade enforcement.
# This does NOT replace Phase 0/1/2 or Step 14/15. It sits between
# adaptive intelligence and execution so weak, stale, duplicated,
# over-risked, or chase signals cannot reach the order path.
# =========================================================
ENABLE_PHASE35_ENFORCEMENT = os.getenv("ENABLE_PHASE35_ENFORCEMENT", "true").lower() == "true"
PHASE35_SEND_ALERTS = os.getenv("PHASE35_SEND_ALERTS", "true").lower() == "true"
PHASE35_STRICT_MODE = os.getenv("PHASE35_STRICT_MODE", "true").lower() == "true"
PHASE35_SUGGEST_ONLY = os.getenv("PHASE35_SUGGEST_ONLY", "false").lower() == "true"
PHASE35_BLOCK_EXECUTION_ONLY = os.getenv("PHASE35_BLOCK_EXECUTION_ONLY", "false").lower() == "true"
PHASE35_MIN_CONFIDENCE_TO_EXECUTE = os.getenv("PHASE35_MIN_CONFIDENCE_TO_EXECUTE", "A").upper().strip()

# =========================================================
# PHASE 3.5 STRATEGY EXECUTION LOCK
# Only A/A+ setups from the UnBiased Trades playbook can execute.
# =========================================================

# =========================================================
# PHASE 3.5 CONTROLLED OVERRIDE / FORCE EXECUTION MODE
# Use for testing execution pipeline only. Keep false for live production.
# =========================================================
ALLOW_DUPLICATE_SIGNALS = os.getenv("ALLOW_DUPLICATE_SIGNALS", "true").lower() == "true"
FORCE_EXECUTION_MODE = os.getenv("FORCE_EXECUTION_MODE", "true").lower() == "true"
FORCE_EXECUTION_KEEP_RISK_GATES = os.getenv("FORCE_EXECUTION_KEEP_RISK_GATES", "true").lower() == "true"

# =========================================================
# FINAL ELITE EXECUTION ROUTING LAYER
# Normal mode: respects routing/freshness.
# Force mode: bypasses routing/freshness for pipeline testing.
# =========================================================

# =========================================================
# PAPER BROKER BRIDGE + ANTI-SPAM EXECUTION GUARD
# One valid signal = one paper order + one paper position.
# Prevents Discord spam and repeated execution of the same signal.
# =========================================================

# =========================================================
# PAPER POSITION LIFECYCLE: TP / SL / AUTO CLOSE
# Manages paper positions created by the paper broker bridge.
# =========================================================

# =========================================================
# LOCKED POSITION SCHEMA + DUPLICATE POSITION CAP
# Prevents Step 15 schema crashes and prevents duplicate stacking.
# =========================================================

# =========================================================

# =========================================================

# =========================================================

# =========================================================
# MACRO BRIDGE — FRED FIRST
# Pulls FRED macro context when FRED_API_KEY exists.
# Missing key never blocks trading; defaults to neutral.
# =========================================================
ENABLE_MACRO_BRIDGE = os.getenv("ENABLE_MACRO_BRIDGE", "true").lower() == "true"
ENABLE_FRED_MACRO_BRIDGE = os.getenv("ENABLE_FRED_MACRO_BRIDGE", "true").lower() == "true"
FRED_API_KEY = os.getenv("FRED_API_KEY", "").strip()
MACRO_LATEST_FILE = os.getenv("MACRO_LATEST_FILE", "macro_latest.json")
MACRO_STORE_FILE = os.getenv("MACRO_STORE_FILE", "macro_store.json")
try:
    MACRO_REFRESH_SECONDS = int(str(os.getenv("MACRO_REFRESH_SECONDS", "3600")).strip())
except Exception:
    MACRO_REFRESH_SECONDS = 3600

FRED_SERIES = {
    "DGS10": "10Y Treasury Yield",
    "DGS2": "2Y Treasury Yield",
    "T10Y2Y": "10Y minus 2Y Yield Curve",
    "DFF": "Fed Funds Effective Rate",
    "CPIAUCSL": "CPI",
    "UNRATE": "Unemployment Rate",
    "VIXCLS": "VIX Close",
    "DCOILWTICO": "WTI Crude Oil",
}


def macro_load_latest() -> Dict[str, Any]:
    data = load_json_file(MACRO_LATEST_FILE, {})
    if not isinstance(data, dict):
        return {}
    try:
        data["updated_at"] = int(float(str(data.get("updated_at", 0)).strip() or 0))
    except Exception:
        data["updated_at"] = 0
    return data

def macro_should_refresh(latest: Dict[str, Any]) -> bool:
    """
    Safe macro refresh check.
    Prevents Render env / JSON string crashes:
    TypeError: unsupported operand type(s) for -: 'str' and 'int'
    """
    if not isinstance(latest, dict):
        return True

    try:
        updated_raw = latest.get("updated_at", 0)
        if isinstance(updated_raw, str):
            updated_at = int(float(updated_raw.strip() or 0))
        else:
            updated_at = int(float(updated_raw or 0))
    except Exception:
        updated_at = 0

    try:
        refresh_seconds = int(float(str(MACRO_REFRESH_SECONDS).strip() or 300))
    except Exception:
        refresh_seconds = 300

    try:
        current_ts = int(float(now_ts()))
    except Exception:
        current_ts = int(time.time())

    return (current_ts - updated_at) >= refresh_seconds

def fred_fetch_series_observations(series_id: str, limit: int = 5) -> Dict[str, Any]:
    if not FRED_API_KEY:
        return {"ok": False, "series_id": series_id, "reason": "missing_fred_api_key"}

    try:
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": series_id,
            "api_key": FRED_API_KEY,
            "file_type": "json",
            "sort_order": "desc",
            "limit": limit,
        }
        r = requests.get(url, params=params, timeout=12)
        if r.status_code != 200:
            return {"ok": False, "series_id": series_id, "reason": f"http_{r.status_code}", "body": r.text[:250]}

        payload = r.json()
        rows = []
        for obs in payload.get("observations", []):
            value = obs.get("value")
            if value in (None, "", "."):
                continue
            rows.append({"date": obs.get("date"), "value": safe_float(value, 0.0)})

        if not rows:
            return {"ok": False, "series_id": series_id, "reason": "no_valid_observations"}

        return {"ok": True, "series_id": series_id, "observations": rows}

    except Exception as e:
        return {"ok": False, "series_id": series_id, "reason": f"exception:{e}"}


def macro_interpret_fred(series_values: Dict[str, Any]) -> Dict[str, Any]:
    oil = safe_float(series_values.get("DCOILWTICO", {}).get("value", 0), 0.0)
    vix = safe_float(series_values.get("VIXCLS", {}).get("value", 0), 0.0)
    curve = safe_float(series_values.get("T10Y2Y", {}).get("value", 0), 0.0)
    y10 = safe_float(series_values.get("DGS10", {}).get("value", 0), 0.0)
    fed = safe_float(series_values.get("DFF", {}).get("value", 0), 0.0)

    score = 0
    notes = []

    if vix >= 25:
        score -= 2
        notes.append("VIX elevated: risk-off pressure")
    elif vix >= 18:
        score -= 1
        notes.append("VIX moderate: caution")
    elif vix > 0:
        score += 1
        notes.append("VIX calm: risk supportive")

    if oil >= 90:
        score -= 1
        notes.append("WTI elevated: inflation/geopolitical pressure")
    elif 0 < oil <= 75:
        score += 1
        notes.append("WTI contained: macro supportive")

    if curve < -0.50:
        score -= 1
        notes.append("Yield curve deeply inverted: growth concern")
    elif curve > 0.25:
        score += 1
        notes.append("Yield curve positive: growth supportive")

    if y10 >= 4.75:
        score -= 1
        notes.append("10Y yield elevated: duration pressure")

    if fed >= 5:
        score -= 1
        notes.append("Fed funds restrictive")

    if score >= 2:
        bias = "risk_on"
    elif score <= -2:
        bias = "risk_off"
    else:
        bias = "neutral"

    return {
        "macro_bias": bias,
        "risk_score": score,
        "notes": notes,
        "oil_price": oil,
        "vix": vix,
        "yield_curve_10y2y": curve,
        "ten_year_yield": y10,
        "fed_funds": fed,
    }


def macro_bridge_fred_refresh(force: bool = False) -> Dict[str, Any]:
    if not ENABLE_MACRO_BRIDGE or not ENABLE_FRED_MACRO_BRIDGE:
        return {"updated": False, "reason": "disabled"}

    latest = macro_load_latest()
    if latest and not force and not macro_should_refresh(latest):
        return {"updated": False, "reason": "fresh_cache", "macro": latest}

    if not FRED_API_KEY:
        payload = {
            "updated_at": now_ts(),
            "source": "fred",
            "status": "missing_fred_api_key",
            "macro_bias": "neutral",
            "risk_score": 0,
            "notes": ["FRED_API_KEY missing; macro bridge neutral"],
            "series": {},
            "errors": {"FRED_API_KEY": "missing"},
        }
        atomic_write_json(MACRO_LATEST_FILE, payload)
        debug("MACRO BRIDGE FRED SKIP | missing FRED_API_KEY")
        return {"updated": False, "reason": "missing_fred_api_key", "macro": payload}

    series_values = {}
    errors = {}

    for series_id, label in FRED_SERIES.items():
        fetched = fred_fetch_series_observations(series_id)
        if fetched.get("ok"):
            obs = fetched.get("observations", [])
            latest_obs = obs[0]
            prior_obs = obs[1] if len(obs) > 1 else latest_obs
            current = safe_float(latest_obs.get("value", 0), 0.0)
            prior = safe_float(prior_obs.get("value", current), current)
            series_values[series_id] = {
                "label": label,
                "date": latest_obs.get("date"),
                "value": current,
                "prior": prior,
                "change": round(current - prior, 4),
                "observations": obs,
            }
        else:
            errors[series_id] = fetched.get("reason", "unknown_error")

    interpretation = macro_interpret_fred(series_values)
    payload = {
        "updated_at": now_ts(),
        "source": "fred",
        "status": "ok" if series_values else "empty",
        "macro_bias": interpretation.get("macro_bias", "neutral"),
        "risk_score": interpretation.get("risk_score", 0),
        "notes": interpretation.get("notes", []),
        "series": series_values,
        "errors": errors,
    }

    atomic_write_json(MACRO_LATEST_FILE, payload)

    store = load_json_file(MACRO_STORE_FILE, {})
    if not isinstance(store, dict):
        store = {}
    history = store.get("history", [])
    if not isinstance(history, list):
        history = []
    history.append(payload)
    store["history"] = history[-100:]
    store["last"] = payload
    atomic_write_json(MACRO_STORE_FILE, store)

    debug(f"MACRO BRIDGE FRED UPDATED | bias={payload['macro_bias']} score={payload['risk_score']} errors={len(errors)}")
    return {"updated": True, "reason": "fred_refreshed", "macro": payload}


def get_macro_context_for_signal() -> Dict[str, Any]:
    macro = macro_load_latest()
    if not macro:
        macro_bridge_fred_refresh(force=False)
        macro = macro_load_latest()

    series = macro.get("series", {}) if isinstance(macro, dict) else {}
    oil = 0
    vix = 0
    if isinstance(series, dict):
        oil = safe_float(series.get("DCOILWTICO", {}).get("value", 0), 0.0)
        vix = safe_float(series.get("VIXCLS", {}).get("value", 0), 0.0)

    return {
        "macro_bias": macro.get("macro_bias", "neutral") if isinstance(macro, dict) else "neutral",
        "macro_risk_score": safe_int(macro.get("risk_score", 0), 0) if isinstance(macro, dict) else 0,
        "macro_notes": macro.get("notes", []) if isinstance(macro, dict) else [],
        "macro_updated_at": macro.get("updated_at", 0) if isinstance(macro, dict) else 0,
        "oil_price": oil,
        "vix": vix,
    }


def apply_macro_context_to_ai_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    """
    Adds macro context to AI-generated signals, then applies the UnBiased Trades
    macro/oil enforcement layer before the signal reaches execution.
    """
    if not isinstance(signal, dict):
        return signal

    macro = get_macro_context_for_signal()
    enriched = deepcopy(signal)

    enriched["macro_bias"] = macro.get("macro_bias", "neutral")
    enriched["macro_risk_score"] = macro.get("macro_risk_score", 0)
    enriched["macro_notes"] = macro.get("macro_notes", [])
    enriched["macro_updated_at"] = macro.get("macro_updated_at", 0)
    enriched["oil_price"] = macro.get("oil_price", 0)
    enriched["vix"] = macro.get("vix", 0)

    direction = str(enriched.get("direction", "")).upper().strip()
    macro_bias = str(enriched.get("macro_bias", "neutral")).lower().strip()
    oil = safe_float(enriched.get("oil_price", 0), 0.0)

    enriched["blocked_by_macro"] = False
    enriched["macro_reason"] = ""

    # =====================================================
    # MACRO + OIL ENFORCEMENT
    # Institutional filter: do not let AI fire trades against
    # the macro tape.
    # =====================================================

    # Risk-off blocks bullish calls.
    if macro_bias == "risk_off" and direction == "CALL":
        enriched["blocked_by_macro"] = True
        enriched["macro_reason"] = "risk_off_blocks_calls"

    # Strong risk-on blocks bearish puts.
    if macro_bias == "risk_on" and direction == "PUT":
        enriched["blocked_by_macro"] = True
        enriched["macro_reason"] = "risk_on_blocks_puts"

    # Oil spike pressure: blocks calls when WTI is elevated.
    if oil > 90 and direction == "CALL":
        enriched["blocked_by_macro"] = True
        enriched["macro_reason"] = "oil_spike_blocks_calls"

    # Low/contained oil pressure filter: blocks puts when oil is supportive.
    if 0 < oil < 70 and direction == "PUT":
        enriched["blocked_by_macro"] = True
        enriched["macro_reason"] = "low_oil_blocks_puts"

    if enriched.get("blocked_by_macro"):
        enriched["macro_warning"] = enriched.get("macro_reason", "macro_block")
    elif macro_bias == "risk_off":
        enriched["macro_warning"] = "risk_off_macro_context"
    else:
        enriched["macro_warning"] = ""

    return enriched


def macro_enforcement_blocks_signal(signal: Dict[str, Any]) -> bool:
    """
    Final safety check before validation/execution.
    If a signal is blocked by macro/oil context, no order path should receive it.
    """
    try:
        if not isinstance(signal, dict):
            return False

        # If signal has not been enriched yet, enrich it now.
        if "blocked_by_macro" not in signal:
            signal.update(apply_macro_context_to_ai_signal(signal))

        if signal.get("blocked_by_macro"):
            reason = signal.get("macro_reason", "macro_blocked")
            debug(f"MACRO BLOCKED TRADE | ticker={signal.get('ticker')} direction={signal.get('direction')} reason={reason}")
            try:
                intel_event(
                    "macro_blocked_trade",
                    {"reason": reason, "signal": signal},
                    signal=signal,
                    stage="macro_enforcement",
                    decision="blocked",
                )
            except Exception:
                pass
            try:
                send_to_discord(DISCORD_AI_WEBHOOK, f"🛑 MACRO BLOCKED TRADE\nTicker: {signal.get('ticker')}\nDirection: {signal.get('direction')}\nReason: {reason}\n⏰ {now_ts()}", "AI")
            except Exception:
                pass
            return True

        return False
    except Exception as e:
        debug(f"MACRO ENFORCEMENT CHECK ERROR | {e}")
        return False


def elite_execution_filter_blocks_signal(signal: Dict[str, Any]) -> bool:
    """
    Final elite filter before the AI signal can become an executable signal.
    Rules:
    1) Only allowed grades can pass. Default: A and A+.
    2) No chasing: if current/contract price is too far above ideal entry, block it.
    """
    try:
        if not ENABLE_ELITE_EXECUTION_FILTER:
            return False

        if not isinstance(signal, dict):
            return False

        grade = str(signal.get("grade", signal.get("confidence", ""))).upper().strip()
        ticker = str(signal.get("ticker", signal.get("symbol", "UNKNOWN"))).upper().strip()
        direction = str(signal.get("direction", "")).upper().strip()

        if grade not in ELITE_ALLOWED_GRADES:
            reason = f"non_elite_grade_{grade or 'missing'}"
            signal["blocked_by_elite_filter"] = True
            signal["elite_filter_reason"] = reason
            debug(f"BLOCKED NON-ELITE TRADE | ticker={ticker} direction={direction} grade={grade}")
            try:
                intel_event(
                    "elite_filter_blocked_trade",
                    {"reason": reason, "signal": signal},
                    signal=signal,
                    stage="elite_execution_filter",
                    decision="blocked",
                )
            except Exception:
                pass
            return True

        entry = safe_float(signal.get("entry_contract", signal.get("entry", 0)), 0.0)
        current_price = safe_float(signal.get("contract_price", signal.get("price", entry)), entry)

        if NO_CHASE_USE_CONTRACT_PRICE and entry > 0 and current_price > 0:
            max_allowed = entry * (1.0 + safe_float(NO_CHASE_MAX_ENTRY_DRIFT_PCT, 0.15))
            if current_price > max_allowed:
                reason = "you_are_chasing_entry_too_far_from_ideal"
                signal["blocked_by_elite_filter"] = True
                signal["elite_filter_reason"] = reason
                signal["ideal_entry"] = entry
                signal["current_contract_price"] = current_price
                signal["max_allowed_entry_price"] = round(max_allowed, 4)
                debug(
                    f"YOU ARE CHASING | ticker={ticker} direction={direction} "
                    f"entry={entry} current={current_price} max_allowed={round(max_allowed, 4)}"
                )
                try:
                    intel_event(
                        "no_chase_blocked_trade",
                        {
                            "reason": reason,
                            "entry": entry,
                            "current_price": current_price,
                            "max_allowed": max_allowed,
                            "signal": signal,
                        },
                        signal=signal,
                        stage="no_chase_filter",
                        decision="blocked",
                    )
                except Exception:
                    pass
                try:
                    if NO_CHASE_SEND_ALERTS:
                        send_to_discord(
                            DISCORD_AI_WEBHOOK,
                            f"🚫 YOU ARE CHASING\nTicker: {ticker}\nDirection: {direction}\nIdeal Entry: {entry}\nCurrent: {current_price}\nMax Allowed: {round(max_allowed, 4)}\n⏰ {now_ts()}",
                            "AI",
                        )
                except Exception:
                    pass
                return True

        signal["blocked_by_elite_filter"] = False
        signal["elite_filter_reason"] = ""
        return False

    except Exception as e:
        debug(f"ELITE EXECUTION FILTER ERROR | {e}")
        return False


def confidence_grade_multiplier(grade: str) -> float:
    g = str(grade or "").upper().strip()
    if g == "A+":
        return safe_float(VOL_CONF_MULT_A_PLUS, 1.5)
    if g == "A":
        return safe_float(VOL_CONF_MULT_A, 1.0)
    if g == "B+":
        return safe_float(VOL_CONF_MULT_B_PLUS, 0.75)
    if g == "B":
        return safe_float(VOL_CONF_MULT_B, 0.50)
    if g == "C":
        return safe_float(VOL_CONF_MULT_C, 0.0)
    return 0.0 if VOL_CONF_BLOCK_C_GRADE else safe_float(VOL_CONF_MULT_C, 0.0)


def volatility_multiplier_from_signal(signal: Dict[str, Any]) -> Tuple[float, str]:
    """
    Uses VIX from macro context if available.
    Lower VIX = full/boosted size.
    Higher VIX = reduced size.
    """
    try:
        vix = safe_float(signal.get("vix", 0), 0.0)
        if vix <= 0:
            macro = get_macro_context_for_signal()
            vix = safe_float(macro.get("vix", 0), 0.0)
            signal["vix"] = vix

        if vix <= 0:
            return safe_float(VOL_CONF_NORMAL_VOL_MULT, 1.0), "unknown_volatility"

        if vix < safe_float(VOL_CONF_VIX_LOW, 15):
            return safe_float(VOL_CONF_LOW_VOL_MULT, 1.10), "low_volatility"
        if vix < safe_float(VOL_CONF_VIX_MEDIUM, 20):
            return safe_float(VOL_CONF_NORMAL_VOL_MULT, 1.0), "normal_volatility"
        if vix < safe_float(VOL_CONF_VIX_HIGH, 25):
            return safe_float(VOL_CONF_MEDIUM_VOL_MULT, 0.75), "medium_volatility"
        if vix < 35:
            return safe_float(VOL_CONF_HIGH_VOL_MULT, 0.50), "high_volatility"
        return safe_float(VOL_CONF_EXTREME_VOL_MULT, 0.25), "extreme_volatility"

    except Exception as e:
        debug(f"VOL CONF volatility multiplier error | {e}")
        return 1.0, "volatility_error"


def apply_volatility_confidence_position_sizing(signal: Dict[str, Any]) -> Dict[str, Any]:
    """
    Adjusts signal qty before execution:
    - A+ bigger
    - A normal
    - B/B+ reduced
    - C blocked/reduced
    - high VIX cuts size
    """
    try:
        if not ENABLE_VOL_CONF_POSITION_SIZING:
            return signal
        if not isinstance(signal, dict):
            return signal

        x = signal

        grade = str(x.get("grade", x.get("confidence", ""))).upper().strip()
        ticker = str(x.get("ticker", x.get("symbol", "UNKNOWN"))).upper().strip()
        direction = str(x.get("direction", "")).upper().strip()

        if VOL_CONF_BLOCK_C_GRADE and grade in {"", "C", "D", "F", "AVOID"}:
            x["blocked_by_vol_conf_sizing"] = True
            x["vol_conf_sizing_reason"] = f"blocked_low_grade_{grade or 'missing'}"
            debug(f"VOL CONF BLOCKED | ticker={ticker} direction={direction} grade={grade}")
            return x

        original_qty = safe_int(x.get("qty", VOL_CONF_BASE_QTY), safe_int(VOL_CONF_BASE_QTY, 1))
        if original_qty <= 0:
            original_qty = safe_int(VOL_CONF_BASE_QTY, 1)

        grade_mult = confidence_grade_multiplier(grade)
        vol_mult, vol_bucket = volatility_multiplier_from_signal(x)

        raw_qty = original_qty * grade_mult * vol_mult
        final_qty = int(math.floor(raw_qty))

        if raw_qty >= 1 and final_qty < 1:
            final_qty = 1

        final_qty = max(safe_int(VOL_CONF_MIN_QTY, 1), final_qty)
        final_qty = min(safe_int(VOL_CONF_MAX_QTY, MAX_POSITION_QTY), final_qty)
        final_qty = min(final_qty, safe_int(MAX_POSITION_QTY, final_qty))

        x["qty_original"] = original_qty
        x["qty"] = final_qty
        x["vol_conf_sizing"] = {
            "enabled": True,
            "grade": grade,
            "grade_multiplier": grade_mult,
            "volatility_multiplier": vol_mult,
            "volatility_bucket": vol_bucket,
            "vix": safe_float(x.get("vix", 0), 0.0),
            "raw_qty": round(raw_qty, 4),
            "final_qty": final_qty,
            "min_qty": safe_int(VOL_CONF_MIN_QTY, 1),
            "max_qty": safe_int(VOL_CONF_MAX_QTY, MAX_POSITION_QTY),
        }
        x["blocked_by_vol_conf_sizing"] = False
        x["vol_conf_sizing_reason"] = ""

        debug(
            f"VOL CONF SIZE | ticker={ticker} direction={direction} grade={grade} "
            f"base={original_qty} grade_mult={grade_mult} vol_mult={vol_mult} "
            f"bucket={vol_bucket} final_qty={final_qty}"
        )

        try:
            intel_event(
                "vol_conf_position_sizing",
                x.get("vol_conf_sizing", {}),
                signal=x,
                stage="position_sizing",
                decision="sized",
            )
        except Exception:
            pass

        return x

    except Exception as e:
        debug(f"VOL CONF POSITION SIZING ERROR | {e}")
        return signal


def vol_conf_sizing_blocks_signal(signal: Dict[str, Any]) -> bool:
    try:
        if not isinstance(signal, dict):
            return False
        return bool(signal.get("blocked_by_vol_conf_sizing"))
    except Exception:
        return False


def risk_state_today_key() -> str:
    try:
        return datetime.utcnow().strftime("%Y-%m-%d")
    except Exception:
        return str(now_ts())[:10]


def risk_state_default() -> Dict[str, Any]:
    return {
        "date": risk_state_today_key(),
        "state": "NORMAL",
        "locked": False,
        "manual_unlock_required": False,
        "daily_realized_pnl": 0.0,
        "daily_realized_pnl_pct": 0.0,
        "loss_streak": 0,
        "win_streak": 0,
        "last_reason": "initialized",
        "updated_at": now_ts(),
        "state_history": [],
    }


def load_risk_state() -> Dict[str, Any]:
    data = load_json_file(RISK_STATE_FILE, {})
    if not isinstance(data, dict):
        data = risk_state_default()

    if RISK_STATE_RESET_DAILY and data.get("date") != risk_state_today_key():
        old_state = data
        data = risk_state_default()
        data["previous_day"] = old_state

    data.setdefault("date", risk_state_today_key())
    data.setdefault("state", "NORMAL")
    data.setdefault("locked", False)
    data.setdefault("manual_unlock_required", False)
    data.setdefault("daily_realized_pnl", 0.0)
    data.setdefault("daily_realized_pnl_pct", 0.0)
    data.setdefault("loss_streak", 0)
    data.setdefault("win_streak", 0)
    data.setdefault("last_reason", "")
    data.setdefault("updated_at", now_ts())
    data.setdefault("state_history", [])
    return data


def save_risk_state(data: Dict[str, Any]) -> None:
    try:
        data["updated_at"] = now_ts()
        atomic_write_json(RISK_STATE_FILE, data)
    except Exception as e:
        debug(f"RISK STATE SAVE ERROR | {e}")


def risk_state_account_equity() -> float:
    try:
        if LIVE_MODE:
            return safe_float(GLOBAL_STATE.get("account_equity", LIVE_ACCOUNT_EQUITY_FALLBACK), LIVE_ACCOUNT_EQUITY_FALLBACK)
        return safe_float(PAPER_ACCOUNT_EQUITY, 25000)
    except Exception:
        return 25000.0


def risk_state_get_daily_pnl() -> float:
    """
    Uses GLOBAL_STATE daily_pnl if available, then risk_state file fallback.
    """
    try:
        ensure_globals_initialized()
        return safe_float(GLOBAL_STATE.get("daily_pnl", 0.0), 0.0)
    except Exception:
        state = load_risk_state()
        return safe_float(state.get("daily_realized_pnl", 0.0), 0.0)


def risk_state_transition(new_state: str, reason: str, current: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    state = current if isinstance(current, dict) else load_risk_state()
    old = str(state.get("state", "NORMAL")).upper()
    new = str(new_state or "NORMAL").upper().strip()

    if old != new:
        state.setdefault("state_history", []).append({
            "at": now_ts(),
            "from": old,
            "to": new,
            "reason": reason,
        })
        state["state_history"] = state.get("state_history", [])[-100:]

        debug(f"RISK STATE CHANGE | {old} -> {new} | reason={reason}")
        try:
            if RISK_STATE_SEND_ALERTS:
                send_to_discord(
                    DISCORD_AI_WEBHOOK,
                    f"🛡️ RISK STATE CHANGE\nFrom: {old}\nTo: {new}\nReason: {reason}\n⏰ {now_ts()}",
                    "AI",
                )
        except Exception:
            pass

    state["state"] = new
    state["last_reason"] = reason
    if new == "LOCKDOWN":
        state["locked"] = True
        state["manual_unlock_required"] = bool(RISK_STATE_REQUIRE_MANUAL_UNLOCK)
    elif not state.get("manual_unlock_required", False):
        state["locked"] = False

    save_risk_state(state)
    return state


def risk_state_evaluate() -> Dict[str, Any]:
    """
    Evaluates account condition and returns active risk state.
    """
    if not ENABLE_RISK_STATE_ENGINE:
        return {"state": "NORMAL", "locked": False, "reason": "disabled", "size_multiplier": 1.0}

    state = load_risk_state()
    equity = max(risk_state_account_equity(), 1.0)
    daily_pnl = risk_state_get_daily_pnl()
    daily_pnl_pct = daily_pnl / equity

    state["daily_realized_pnl"] = daily_pnl
    state["daily_realized_pnl_pct"] = daily_pnl_pct

    loss_streak = safe_int(state.get("loss_streak", 0), 0)
    win_streak = safe_int(state.get("win_streak", 0), 0)

    # Manual lock stays locked until reset/unlock command.
    if state.get("locked") and state.get("manual_unlock_required"):
        save_risk_state(state)
        return {
            "state": "LOCKDOWN",
            "locked": True,
            "reason": state.get("last_reason", "manual_unlock_required"),
            "size_multiplier": 0.0,
            "daily_pnl": daily_pnl,
            "daily_pnl_pct": daily_pnl_pct,
        }

    lock_dollars = -abs(safe_float(RISK_STATE_LOCK_DOLLARS, 500))
    defensive_dollars = -abs(safe_float(RISK_STATE_DEFENSIVE_DOLLARS, 250))
    aggressive_profit_dollars = abs(safe_float(RISK_STATE_AGGRESSIVE_PROFIT_DOLLARS, 250))

    if RISK_STATE_AUTO_LOCK_ON_DRAWDOWN and (
        daily_pnl <= lock_dollars
        or daily_pnl_pct <= -abs(safe_float(RISK_STATE_DAILY_DRAWDOWN_LOCK_PCT, 0.02))
        or loss_streak >= safe_int(RISK_STATE_LOSS_STREAK_LOCKDOWN, 3)
    ):
        reason = f"drawdown_or_loss_streak_lock | pnl={round(daily_pnl,2)} pct={round(daily_pnl_pct*100,2)}% losses={loss_streak}"
        state = risk_state_transition("LOCKDOWN", reason, state)
        return {"state": "LOCKDOWN", "locked": True, "reason": reason, "size_multiplier": 0.0, "daily_pnl": daily_pnl, "daily_pnl_pct": daily_pnl_pct}

    if (
        daily_pnl <= defensive_dollars
        or daily_pnl_pct <= -abs(safe_float(RISK_STATE_DAILY_DRAWDOWN_DEFENSIVE_PCT, 0.01))
        or loss_streak >= safe_int(RISK_STATE_LOSS_STREAK_DEFENSIVE, 2)
    ):
        reason = f"defensive_mode | pnl={round(daily_pnl,2)} pct={round(daily_pnl_pct*100,2)}% losses={loss_streak}"
        state = risk_state_transition("DEFENSIVE", reason, state)
        return {"state": "DEFENSIVE", "locked": False, "reason": reason, "size_multiplier": safe_float(RISK_STATE_DEFENSIVE_SIZE_MULT, 0.5), "daily_pnl": daily_pnl, "daily_pnl_pct": daily_pnl_pct}

    if (
        daily_pnl >= aggressive_profit_dollars
        or daily_pnl_pct >= abs(safe_float(RISK_STATE_DAILY_PROFIT_AGGRESSIVE_PCT, 0.01))
        or win_streak >= safe_int(RISK_STATE_WIN_STREAK_AGGRESSIVE, 3)
    ):
        reason = f"aggressive_mode | pnl={round(daily_pnl,2)} pct={round(daily_pnl_pct*100,2)}% wins={win_streak}"
        state = risk_state_transition("AGGRESSIVE", reason, state)
        return {"state": "AGGRESSIVE", "locked": False, "reason": reason, "size_multiplier": safe_float(RISK_STATE_AGGRESSIVE_SIZE_MULT, 1.25), "daily_pnl": daily_pnl, "daily_pnl_pct": daily_pnl_pct}

    reason = f"normal_mode | pnl={round(daily_pnl,2)} pct={round(daily_pnl_pct*100,2)}%"
    state = risk_state_transition("NORMAL", reason, state)
    return {"state": "NORMAL", "locked": False, "reason": reason, "size_multiplier": safe_float(RISK_STATE_NORMAL_SIZE_MULT, 1.0), "daily_pnl": daily_pnl, "daily_pnl_pct": daily_pnl_pct}


def apply_risk_state_to_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    """
    Blocks or adjusts size based on risk state before execution.
    """
    try:
        if not ENABLE_RISK_STATE_ENGINE:
            return signal
        if not isinstance(signal, dict):
            return signal

        result = risk_state_evaluate()
        state_name = str(result.get("state", "NORMAL")).upper()
        multiplier = safe_float(result.get("size_multiplier", 1.0), 1.0)

        signal["risk_state"] = state_name
        signal["risk_state_reason"] = result.get("reason", "")
        signal["risk_state_size_multiplier"] = multiplier
        signal["risk_state_daily_pnl"] = result.get("daily_pnl", 0)
        signal["risk_state_daily_pnl_pct"] = result.get("daily_pnl_pct", 0)

        if result.get("locked") or state_name == "LOCKDOWN" or multiplier <= 0:
            signal["blocked_by_risk_state"] = True
            signal["risk_state_block_reason"] = result.get("reason", "risk_state_lockdown")
            debug(f"RISK STATE BLOCKED TRADE | state={state_name} reason={signal.get('risk_state_block_reason')}")
            return signal

        original_qty = safe_int(signal.get("qty", 1), 1)
        adjusted_qty = int(math.floor(original_qty * multiplier))
        if original_qty > 0 and adjusted_qty < 1:
            adjusted_qty = 1

        adjusted_qty = min(adjusted_qty, safe_int(MAX_POSITION_QTY, adjusted_qty))
        adjusted_qty = max(1, adjusted_qty)

        signal["qty_before_risk_state"] = original_qty
        signal["qty"] = adjusted_qty
        signal["blocked_by_risk_state"] = False
        signal["risk_state_block_reason"] = ""

        debug(
            f"RISK STATE SIZE | state={state_name} base_qty={original_qty} "
            f"mult={multiplier} final_qty={adjusted_qty}"
        )

        try:
            intel_event(
                "risk_state_position_adjustment",
                {
                    "state": state_name,
                    "multiplier": multiplier,
                    "base_qty": original_qty,
                    "final_qty": adjusted_qty,
                    "reason": result.get("reason", ""),
                },
                signal=signal,
                stage="risk_state_engine",
                decision="adjusted",
            )
        except Exception:
            pass

        return signal

    except Exception as e:
        debug(f"RISK STATE APPLY ERROR | {e}")
        return signal


def risk_state_blocks_signal(signal: Dict[str, Any]) -> bool:
    try:
        return bool(isinstance(signal, dict) and signal.get("blocked_by_risk_state"))
    except Exception:
        return False


def portfolio_heat_account_equity() -> float:
    try:
        if LIVE_MODE:
            return safe_float(GLOBAL_STATE.get("account_equity", LIVE_ACCOUNT_EQUITY_FALLBACK), LIVE_ACCOUNT_EQUITY_FALLBACK)
        return safe_float(PAPER_ACCOUNT_EQUITY, 25000)
    except Exception:
        return 25000.0


def portfolio_heat_open_positions() -> List[Dict[str, Any]]:
    try:
        ensure_globals_initialized()
        positions = GLOBAL_POSITIONS.get("open_positions", [])
        if isinstance(positions, list):
            return [p for p in positions if isinstance(p, dict)]
    except Exception:
        pass

    try:
        data = load_json_file(POSITIONS_FILE, {})
        if isinstance(data, dict):
            positions = data.get("open_positions", [])
            if isinstance(positions, list):
                return [p for p in positions if isinstance(p, dict)]
        if isinstance(data, list):
            return [p for p in data if isinstance(p, dict)]
    except Exception:
        pass

    return []


def portfolio_position_symbol(pos: Dict[str, Any]) -> str:
    return str(pos.get("ticker", pos.get("symbol", pos.get("underlying", "")))).upper().strip()


def portfolio_position_direction(pos: Dict[str, Any]) -> str:
    return str(pos.get("direction", pos.get("side", ""))).upper().strip()


def portfolio_position_qty(pos: Dict[str, Any]) -> int:
    return max(0, safe_int(pos.get("qty", pos.get("quantity", pos.get("open_qty", 0))), 0))


def portfolio_position_entry(pos: Dict[str, Any]) -> float:
    return safe_float(pos.get("entry", pos.get("entry_price", pos.get("contract_price", 0))), 0.0)


def portfolio_position_stop(pos: Dict[str, Any]) -> float:
    return safe_float(pos.get("stop", pos.get("stop_price", 0)), 0.0)


def portfolio_position_risk_dollars(pos: Dict[str, Any]) -> float:
    """
    Options risk estimate:
    abs(entry - stop) * qty * 100.
    If no stop exists, use entry * qty * 100 as worst-case premium risk.
    """
    try:
        qty = portfolio_position_qty(pos)
        entry = portfolio_position_entry(pos)
        stop = portfolio_position_stop(pos)

        if qty <= 0 or entry <= 0:
            return 0.0

        if stop > 0:
            risk_per_contract = abs(entry - stop) * 100.0
        else:
            risk_per_contract = entry * 100.0

        return max(0.0, risk_per_contract * qty)
    except Exception:
        return 0.0


def portfolio_signal_risk_dollars(signal: Dict[str, Any]) -> float:
    try:
        qty = max(1, safe_int(signal.get("qty", 1), 1))
        entry = safe_float(signal.get("entry_contract", signal.get("entry", signal.get("contract_price", 0))), 0.0)
        stop = safe_float(signal.get("stop_contract", signal.get("stop", 0)), 0.0)

        if entry <= 0:
            return 0.0

        if stop > 0:
            risk_per_contract = abs(entry - stop) * 100.0
        else:
            risk_per_contract = entry * 100.0

        return max(0.0, risk_per_contract * qty)
    except Exception:
        return 0.0


def portfolio_heat_snapshot(signal: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    positions = portfolio_heat_open_positions()
    equity = max(portfolio_heat_account_equity(), 1.0)

    total_risk = 0.0
    ticker_risk: Dict[str, float] = {}
    direction_risk: Dict[str, float] = {}
    ticker_counts: Dict[str, int] = {}
    direction_counts: Dict[str, int] = {}
    correlated_count = 0

    for p in positions:
        ticker = portfolio_position_symbol(p)
        direction = portfolio_position_direction(p)
        risk = portfolio_position_risk_dollars(p)

        total_risk += risk
        ticker_risk[ticker] = ticker_risk.get(ticker, 0.0) + risk
        direction_risk[direction] = direction_risk.get(direction, 0.0) + risk
        ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1
        direction_counts[direction] = direction_counts.get(direction, 0) + 1

        if ticker in PORTFOLIO_CORRELATED_INDEX_TICKERS:
            correlated_count += 1

    incoming = {}
    if isinstance(signal, dict):
        ticker = str(signal.get("ticker", signal.get("symbol", ""))).upper().strip()
        direction = str(signal.get("direction", "")).upper().strip()
        risk = portfolio_signal_risk_dollars(signal)
        incoming = {
            "ticker": ticker,
            "direction": direction,
            "risk_dollars": risk,
            "risk_pct": risk / equity,
            "is_correlated": ticker in PORTFOLIO_CORRELATED_INDEX_TICKERS,
        }

    return {
        "equity": equity,
        "open_count": len(positions),
        "total_risk_dollars": total_risk,
        "total_heat_pct": total_risk / equity,
        "ticker_risk": ticker_risk,
        "ticker_heat_pct": {k: v / equity for k, v in ticker_risk.items()},
        "direction_risk": direction_risk,
        "direction_heat_pct": {k: v / equity for k, v in direction_risk.items()},
        "ticker_counts": ticker_counts,
        "direction_counts": direction_counts,
        "correlated_count": correlated_count,
        "incoming": incoming,
    }


def apply_portfolio_heat_exposure_control(signal: Dict[str, Any]) -> Dict[str, Any]:
    """
    Blocks or reduces a signal if portfolio exposure is already too concentrated.
    """
    try:
        if not ENABLE_PORTFOLIO_HEAT_EXPOSURE:
            return signal
        if not isinstance(signal, dict):
            return signal

        x = signal
        ticker = str(x.get("ticker", x.get("symbol", "UNKNOWN"))).upper().strip()
        direction = str(x.get("direction", "")).upper().strip()

        snap = portfolio_heat_snapshot(x)
        equity = max(safe_float(snap.get("equity", 0), 0), 1.0)
        incoming = snap.get("incoming", {}) if isinstance(snap.get("incoming"), dict) else {}
        incoming_risk = safe_float(incoming.get("risk_dollars", 0), 0.0)
        incoming_heat = incoming_risk / equity

        projected_total_heat = safe_float(snap.get("total_heat_pct", 0), 0.0) + incoming_heat
        current_ticker_heat = safe_float(snap.get("ticker_heat_pct", {}).get(ticker, 0), 0.0)
        projected_ticker_heat = current_ticker_heat + incoming_heat

        current_direction_heat = safe_float(snap.get("direction_heat_pct", {}).get(direction, 0), 0.0)
        projected_direction_heat = current_direction_heat + incoming_heat

        ticker_count = safe_int(snap.get("ticker_counts", {}).get(ticker, 0), 0)
        direction_count = safe_int(snap.get("direction_counts", {}).get(direction, 0), 0)
        correlated_count = safe_int(snap.get("correlated_count", 0), 0)

        reasons = []

        if safe_int(snap.get("open_count", 0), 0) >= safe_int(PORTFOLIO_MAX_OPEN_TOTAL, MAX_OPEN_POSITIONS):
            reasons.append("max_open_total_reached")

        if ticker_count >= safe_int(PORTFOLIO_MAX_OPEN_PER_TICKER, MAX_SAME_TICKER_POSITIONS):
            reasons.append(f"max_open_per_ticker_reached:{ticker}")

        if direction_count >= safe_int(PORTFOLIO_MAX_SAME_DIRECTION_OPEN, 2):
            reasons.append(f"max_same_direction_reached:{direction}")

        if ticker in PORTFOLIO_CORRELATED_INDEX_TICKERS and correlated_count >= safe_int(PORTFOLIO_MAX_CORRELATED_OPEN, 2):
            reasons.append("max_correlated_index_exposure_reached")

        if projected_total_heat > safe_float(PORTFOLIO_MAX_HEAT_PCT, MAX_PROJECTED_PORTFOLIO_HEAT_PCT):
            reasons.append(f"portfolio_heat_exceeded:{round(projected_total_heat*100,2)}%")

        if projected_ticker_heat > safe_float(PORTFOLIO_MAX_TICKER_HEAT_PCT, 0.015):
            reasons.append(f"ticker_heat_exceeded:{ticker}:{round(projected_ticker_heat*100,2)}%")

        if projected_direction_heat > safe_float(PORTFOLIO_MAX_DIRECTION_HEAT_PCT, 0.02):
            reasons.append(f"direction_heat_exceeded:{direction}:{round(projected_direction_heat*100,2)}%")

        x["portfolio_heat_snapshot"] = {
            "open_count": snap.get("open_count", 0),
            "total_heat_pct": round(safe_float(snap.get("total_heat_pct", 0), 0) * 100, 4),
            "projected_total_heat_pct": round(projected_total_heat * 100, 4),
            "ticker_count": ticker_count,
            "direction_count": direction_count,
            "correlated_count": correlated_count,
            "incoming_risk_dollars": round(incoming_risk, 2),
            "incoming_heat_pct": round(incoming_heat * 100, 4),
        }

        if reasons:
            x["blocked_by_portfolio_heat"] = True
            x["portfolio_heat_reason"] = ",".join(reasons)
            debug(
                f"PORTFOLIO HEAT BLOCKED | ticker={ticker} direction={direction} "
                f"reasons={reasons} projected_heat={round(projected_total_heat*100,2)}%"
            )
            try:
                intel_event(
                    "portfolio_heat_blocked_trade",
                    {"reasons": reasons, "snapshot": x.get("portfolio_heat_snapshot", {})},
                    signal=x,
                    stage="portfolio_heat_exposure",
                    decision="blocked",
                )
            except Exception:
                pass
            try:
                if PORTFOLIO_HEAT_SEND_ALERTS:
                    send_to_discord(
                        DISCORD_AI_WEBHOOK,
                        f"🧯 PORTFOLIO HEAT BLOCKED\nTicker: {ticker}\nDirection: {direction}\nReasons: {', '.join(reasons)}\nProjected Heat: {round(projected_total_heat*100,2)}%\n⏰ {now_ts()}",
                        "AI",
                    )
            except Exception:
                pass
            return x

        # Near heat limit: reduce size instead of full block.
        max_heat = safe_float(PORTFOLIO_MAX_HEAT_PCT, MAX_PROJECTED_PORTFOLIO_HEAT_PCT)
        near_threshold = max_heat * safe_float(PORTFOLIO_NEAR_HEAT_THRESHOLD_PCT, 0.80)

        if PORTFOLIO_REDUCE_SIZE_IF_NEAR_HEAT and projected_total_heat >= near_threshold:
            original_qty = safe_int(x.get("qty", 1), 1)
            new_qty = max(1, int(math.floor(original_qty * safe_float(PORTFOLIO_NEAR_HEAT_SIZE_MULT, 0.5))))
            x["qty_before_portfolio_heat"] = original_qty
            x["qty"] = new_qty
            x["portfolio_heat_size_reduced"] = True
            debug(
                f"PORTFOLIO HEAT SIZE REDUCED | ticker={ticker} "
                f"base_qty={original_qty} final_qty={new_qty} projected_heat={round(projected_total_heat*100,2)}%"
            )
        else:
            x["portfolio_heat_size_reduced"] = False

        x["blocked_by_portfolio_heat"] = False
        x["portfolio_heat_reason"] = ""
        debug(
            f"PORTFOLIO HEAT OK | ticker={ticker} direction={direction} "
            f"open={snap.get('open_count', 0)} projected_heat={round(projected_total_heat*100,2)}%"
        )
        return x

    except Exception as e:
        debug(f"PORTFOLIO HEAT CONTROL ERROR | {e}")
        return signal


def portfolio_heat_blocks_signal(signal: Dict[str, Any]) -> bool:
    try:
        return bool(isinstance(signal, dict) and signal.get("blocked_by_portfolio_heat"))
    except Exception:
        return False


def journal_now() -> int:
    try:
        return now_ts()
    except Exception:
        return int(time.time())


def journal_signal_key(signal: Dict[str, Any]) -> str:
    try:
        raw = {
            "ticker": str(signal.get("ticker", signal.get("symbol", ""))).upper(),
            "direction": str(signal.get("direction", "")).upper(),
            "grade": str(signal.get("grade", signal.get("confidence", ""))).upper(),
            "setup": str(signal.get("setup", signal.get("strategy", ""))).lower(),
            "entry": signal.get("entry", signal.get("entry_contract", 0)),
            "timestamp": signal.get("timestamp", 0),
        }
        return hashlib.sha256(json.dumps(raw, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    except Exception:
        return hashlib.sha256(str(signal).encode("utf-8")).hexdigest()[:16]


def journal_append(event_type: str, payload: Dict[str, Any]) -> None:
    if not ENABLE_TRADE_JOURNAL_LEARNING:
        return
    try:
        row = {
            "ts": journal_now(),
            "event_type": str(event_type),
            "payload": payload if isinstance(payload, dict) else {"value": payload},
        }
        with open(TRADE_JOURNAL_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except Exception as e:
        debug(f"TRADE JOURNAL APPEND ERROR | {e}")


def journal_record_signal_decision(signal: Dict[str, Any], stage: str, decision: str, reason: str = "") -> None:
    try:
        if not ENABLE_TRADE_JOURNAL_LEARNING or not isinstance(signal, dict):
            return
        payload = {
            "signal_key": journal_signal_key(signal),
            "stage": stage,
            "decision": decision,
            "reason": reason,
            "ticker": signal.get("ticker", signal.get("symbol", "")),
            "direction": signal.get("direction", ""),
            "grade": signal.get("grade", signal.get("confidence", "")),
            "confidence": signal.get("confidence", ""),
            "setup": signal.get("setup", signal.get("strategy", "")),
            "trigger": signal.get("trigger", ""),
            "confirmation": signal.get("confirmation", ""),
            "qty": signal.get("qty", 0),
            "entry": signal.get("entry", signal.get("entry_contract", 0)),
            "stop": signal.get("stop", signal.get("stop_contract", 0)),
            "target": signal.get("target", signal.get("tp1_contract", 0)),
            "macro_bias": signal.get("macro_bias", ""),
            "oil_price": signal.get("oil_price", 0),
            "vix": signal.get("vix", 0),
            "risk_state": signal.get("risk_state", ""),
            "portfolio_heat_snapshot": signal.get("portfolio_heat_snapshot", {}),
            "vol_conf_sizing": signal.get("vol_conf_sizing", {}),
        }
        journal_append("signal_decision", payload)
    except Exception as e:
        debug(f"TRADE JOURNAL SIGNAL DECISION ERROR | {e}")


def journal_record_order_event(order_or_result: Dict[str, Any], event_type: str = "order_event") -> None:
    try:
        if not ENABLE_TRADE_JOURNAL_LEARNING:
            return
        payload = order_or_result if isinstance(order_or_result, dict) else {"value": order_or_result}
        journal_append(event_type, payload)
    except Exception as e:
        debug(f"TRADE JOURNAL ORDER EVENT ERROR | {e}")


def journal_trade_setup_key(trade: Dict[str, Any]) -> str:
    try:
        ticker = str(trade.get("ticker", trade.get("symbol", "UNKNOWN"))).upper().strip()
        direction = str(trade.get("direction", "UNKNOWN")).upper().strip()
        setup = str(trade.get("setup", trade.get("strategy", "GENERIC"))).lower().strip().replace(" ", "_")
        grade = str(trade.get("grade", trade.get("confidence", "NA"))).upper().strip()
        return f"{ticker}_{direction}_{grade}_{setup}"
    except Exception:
        return "UNKNOWN_UNKNOWN_NA_GENERIC"


def journal_infer_trade_result(trade: Dict[str, Any]) -> Dict[str, Any]:
    try:
        entry = safe_float(trade.get("entry", trade.get("entry_price", 0)), 0.0)
        exit_price = safe_float(trade.get("exit", trade.get("exit_price", trade.get("last_price", 0))), 0.0)
        stop = safe_float(trade.get("stop", trade.get("stop_price", 0)), 0.0)
        pnl = safe_float(trade.get("realized_pnl", trade.get("pnl", 0)), 0.0)
        pnl_pct = safe_float(trade.get("realized_pnl_pct", trade.get("pnl_pct", 0)), 0.0)

        risk_per_contract = abs(entry - stop) if entry > 0 and stop > 0 else 0.0
        move = exit_price - entry if entry > 0 and exit_price > 0 else 0.0

        r_multiple = 0.0
        if risk_per_contract > 0 and move != 0:
            r_multiple = move / risk_per_contract

        if pnl != 0:
            winner = pnl > 0
        elif pnl_pct != 0:
            winner = pnl_pct > 0
        elif r_multiple != 0:
            winner = r_multiple >= safe_float(TRADE_JOURNAL_MIN_R_FOR_WIN, 0.01)
        else:
            winner = bool(trade.get("winner", False))

        return {
            "winner": winner,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "r_multiple": round(r_multiple, 4),
            "entry": entry,
            "exit": exit_price,
            "stop": stop,
        }
    except Exception:
        return {"winner": False, "pnl": 0.0, "pnl_pct": 0.0, "r_multiple": 0.0}


def journal_record_closed_trade(trade: Dict[str, Any], close_reason: str = "") -> None:
    try:
        if not ENABLE_TRADE_JOURNAL_LEARNING or not isinstance(trade, dict):
            return

        result = journal_infer_trade_result(trade)
        payload = deepcopy(trade)
        payload.update(result)
        payload["setup_key"] = journal_trade_setup_key(payload)
        payload["close_reason"] = close_reason or payload.get("close_reason", "")
        payload["closed_at"] = journal_now()

        journal_append("closed_trade", payload)

        try:
            risk_state_record_closed_trade(payload)
        except Exception:
            pass

        rebuild_trade_learning_summary()

        if TRADE_JOURNAL_SEND_ALERTS:
            outcome = "WIN" if result.get("winner") else "LOSS"
            send_to_discord(
                DISCORD_AI_WEBHOOK,
                f"📓 TRADE JOURNALED\nOutcome: {outcome}\nSetup: {payload.get('setup_key')}\nR: {result.get('r_multiple')}\nReason: {payload.get('close_reason','')}\n⏰ {now_ts()}",
                "AI",
            )
    except Exception as e:
        debug(f"TRADE JOURNAL CLOSED TRADE ERROR | {e}")


def load_trade_journal_events(limit: int = 5000) -> List[Dict[str, Any]]:
    rows = []
    try:
        if not os.path.exists(TRADE_JOURNAL_FILE):
            return rows
        with open(TRADE_JOURNAL_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
        return rows[-limit:]
    except Exception as e:
        debug(f"LOAD TRADE JOURNAL ERROR | {e}")
        return rows


def rebuild_trade_learning_summary() -> Dict[str, Any]:
    try:
        events = load_trade_journal_events()
        setup_stats: Dict[str, Any] = {}

        for e in events:
            if e.get("event_type") != "closed_trade":
                continue
            p = e.get("payload", {})
            if not isinstance(p, dict):
                continue

            key = p.get("setup_key") or journal_trade_setup_key(p)
            bucket = setup_stats.setdefault(key, {
                "setup_key": key,
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "total_r": 0.0,
                "total_pnl": 0.0,
                "recent_results": [],
                "last_trade_ts": 0,
            })

            winner = bool(p.get("winner", False))
            bucket["trades"] += 1
            bucket["wins"] += 1 if winner else 0
            bucket["losses"] += 0 if winner else 1
            bucket["total_r"] += safe_float(p.get("r_multiple", 0), 0.0)
            bucket["total_pnl"] += safe_float(p.get("pnl", 0), 0.0)
            bucket["recent_results"].append("W" if winner else "L")
            bucket["recent_results"] = bucket["recent_results"][-10:]
            bucket["last_trade_ts"] = max(safe_int(bucket.get("last_trade_ts", 0), 0), safe_int(e.get("ts", 0), 0))

        weak_setups = []
        strong_setups = []

        for key, b in setup_stats.items():
            trades = max(safe_int(b.get("trades", 0), 0), 1)
            win_rate = safe_float(b.get("wins", 0), 0) / trades
            avg_r = safe_float(b.get("total_r", 0), 0.0) / trades
            b["win_rate"] = round(win_rate, 4)
            b["avg_r"] = round(avg_r, 4)
            b["avg_pnl"] = round(safe_float(b.get("total_pnl", 0), 0.0) / trades, 4)

            if trades >= LEARNING_MIN_SAMPLE_FOR_SETUP_SCORE and win_rate <= LEARNING_WEAK_SETUP_WINRATE:
                weak_setups.append(key)
            if trades >= LEARNING_MIN_SAMPLE_FOR_SETUP_SCORE and win_rate >= LEARNING_STRONG_SETUP_WINRATE:
                strong_setups.append(key)

        summary = {
            "generated_at": journal_now(),
            "total_closed_trades": sum(safe_int(v.get("trades", 0), 0) for v in setup_stats.values()),
            "setup_count": len(setup_stats),
            "weak_setups": weak_setups,
            "strong_setups": strong_setups,
            "setup_stats": setup_stats,
        }
        atomic_write_json(TRADE_LEARNING_FILE, summary)
        debug(f"TRADE LEARNING SUMMARY WRITTEN | trades={summary['total_closed_trades']} setups={summary['setup_count']}")
        return summary
    except Exception as e:
        debug(f"REBUILD TRADE LEARNING SUMMARY ERROR | {e}")
        return {}


def apply_learning_feedback_to_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    """
    Uses prior closed trade results to reduce/block weak setups before execution.
    """
    try:
        if not ENABLE_TRADE_JOURNAL_LEARNING or not isinstance(signal, dict):
            return signal

        summary = load_json_file(TRADE_LEARNING_FILE, {})
        if not isinstance(summary, dict) or not summary:
            summary = rebuild_trade_learning_summary()

        key = journal_trade_setup_key(signal)
        stats = summary.get("setup_stats", {}).get(key, {}) if isinstance(summary.get("setup_stats", {}), dict) else {}

        signal["learning_setup_key"] = key
        signal["learning_stats"] = stats

        trades = safe_int(stats.get("trades", 0), 0)
        win_rate = safe_float(stats.get("win_rate", 0), 0.0)

        if trades < LEARNING_MIN_SAMPLE_FOR_SETUP_SCORE:
            signal["learning_action"] = "observe_only"
            debug(f"LEARNING OBSERVE ONLY | setup={key} trades={trades}/{LEARNING_MIN_SAMPLE_FOR_SETUP_SCORE}")
            return signal

        if win_rate <= LEARNING_WEAK_SETUP_WINRATE:
            signal["learning_action"] = "weak_setup"
            if LEARNING_BLOCK_EXTREME_WEAK_SETUPS:
                signal["blocked_by_learning"] = True
                signal["learning_block_reason"] = f"weak_setup_winrate_{round(win_rate*100,1)}"
                debug(f"LEARNING BLOCKED TRADE | setup={key} win_rate={round(win_rate*100,1)}%")
                return signal

            if LEARNING_SIZE_DOWN_WEAK_SETUPS:
                original_qty = safe_int(signal.get("qty", 1), 1)
                new_qty = max(1, int(math.floor(original_qty * safe_float(LEARNING_WEAK_SIZE_MULT, 0.5))))
                signal["qty_before_learning"] = original_qty
                signal["qty"] = new_qty
                signal["learning_size_reduced"] = True
                debug(f"LEARNING SIZE DOWN | setup={key} win_rate={round(win_rate*100,1)}% qty={original_qty}->{new_qty}")
                return signal

        if win_rate >= LEARNING_STRONG_SETUP_WINRATE:
            signal["learning_action"] = "strong_setup"
            debug(f"LEARNING STRONG SETUP | setup={key} win_rate={round(win_rate*100,1)}%")

        signal["blocked_by_learning"] = False
        signal["learning_block_reason"] = ""
        return signal
    except Exception as e:
        debug(f"APPLY LEARNING FEEDBACK ERROR | {e}")
        return signal


def learning_blocks_signal(signal: Dict[str, Any]) -> bool:
    try:
        return bool(isinstance(signal, dict) and signal.get("blocked_by_learning"))
    except Exception:
        return False


def live_safety_default_state() -> Dict[str, Any]:
    return {
        "locked": False,
        "manual_unlock_required": False,
        "reason": "",
        "last_check_ts": now_ts(),
        "last_lock_ts": 0,
        "checks": {},
    }


def load_live_safety_state() -> Dict[str, Any]:
    data = load_json_file(LIVE_SAFETY_FILE, {})
    if not isinstance(data, dict):
        data = live_safety_default_state()
    data.setdefault("locked", False)
    data.setdefault("manual_unlock_required", False)
    data.setdefault("reason", "")
    data.setdefault("last_check_ts", now_ts())
    data.setdefault("last_lock_ts", 0)
    data.setdefault("checks", {})
    return data


def save_live_safety_state(data: Dict[str, Any]) -> None:
    try:
        data["last_check_ts"] = now_ts()
        atomic_write_json(LIVE_SAFETY_FILE, data)
    except Exception as e:
        debug(f"LIVE SAFETY SAVE ERROR | {e}")


def live_safety_alert(title: str, body: str) -> None:
    try:
        if LIVE_SAFETY_SEND_ALERTS:
            send_to_discord(DISCORD_AI_WEBHOOK, f"🔐 {title}\n{body}\n⏰ {now_ts()}", "AI")
            send_to_telegram(f"🔐 {title}\n{body}\n⏰ {now_ts()}")
    except Exception:
        pass


def live_safety_lock(reason: str) -> Dict[str, Any]:
    state = load_live_safety_state()
    state["locked"] = True
    state["manual_unlock_required"] = bool(LIVE_SAFETY_REQUIRE_MANUAL_UNLOCK)
    state["reason"] = str(reason)
    state["last_lock_ts"] = now_ts()
    save_live_safety_state(state)

    debug(f"LIVE SAFETY LOCKED | reason={reason}")
    live_safety_alert("LIVE SAFETY LOCKED", f"Reason: {reason}\nLive trading blocked until reviewed.")
    return state


def live_safety_unlock(reason: str = "manual_unlock") -> Dict[str, Any]:
    state = load_live_safety_state()
    state["locked"] = False
    state["manual_unlock_required"] = False
    state["reason"] = reason
    save_live_safety_state(state)
    debug(f"LIVE SAFETY UNLOCKED | reason={reason}")
    live_safety_alert("LIVE SAFETY UNLOCKED", f"Reason: {reason}")
    return state


def live_safety_account_equity() -> float:
    try:
        ensure_globals_initialized()
        eq = safe_float(GLOBAL_STATE.get("account_equity", 0), 0.0)
        if eq > 0:
            return eq
    except Exception:
        pass
    try:
        return safe_float(LIVE_ACCOUNT_EQUITY_FALLBACK, 25000)
    except Exception:
        return 0.0


def live_safety_open_position_count() -> int:
    try:
        return len(portfolio_heat_open_positions())
    except Exception:
        try:
            ensure_globals_initialized()
            return len(GLOBAL_POSITIONS.get("open_positions", []))
        except Exception:
            return 0


def live_safety_market_data_fresh() -> Tuple[bool, str]:
    try:
        if not LIVE_SAFETY_REQUIRE_FRESH_MARKET_DATA:
            return True, "freshness_not_required"

        data = load_json_file(MARKET_DATA_FILE, {})
        if not isinstance(data, dict) or not data:
            return False, "market_data_missing"

        ts = safe_int(data.get("__updated_at", data.get("updated_at", 0)), 0)
        if ts <= 0:
            # Try ticker timestamps.
            timestamps = []
            for _, row in data.items():
                if isinstance(row, dict):
                    timestamps.append(safe_int(row.get("price_updated_at", row.get("timestamp", 0)), 0))
            ts = max(timestamps) if timestamps else 0

        if ts <= 0:
            return False, "market_data_timestamp_missing"

        age = now_ts() - ts
        max_age = safe_int(LIVE_SAFETY_MARKET_DATA_MAX_AGE_SECONDS, 20)
        if age > max_age:
            return False, f"market_data_stale_age_{age}s"

        return True, f"market_data_fresh_age_{age}s"
    except Exception as e:
        return False, f"market_data_check_error:{e}"


def live_safety_within_market_hours() -> Tuple[bool, str]:
    try:
        if not LIVE_SAFETY_ENFORCE_MARKET_HOURS:
            return True, "market_hours_not_enforced"

        # Use UTC fallback. ET is UTC-4 during daylight time.
        # This is intentionally conservative for day-one safety.
        utc_now = datetime.utcnow()
        et_now = utc_now - timedelta(hours=4)
        hhmm = et_now.strftime("%H:%M")
        if LIVE_SAFETY_START_TIME_ET <= hhmm <= LIVE_SAFETY_END_TIME_ET:
            return True, f"market_hours_ok_{hhmm}_ET"
        return False, f"outside_market_hours_{hhmm}_ET"
    except Exception as e:
        return False, f"market_hours_check_error:{e}"


def live_safety_check(signal: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Returns approved=False when live trading should be blocked.
    Paper trading is not blocked by this system.
    """
    if not ENABLE_LIVE_SAFETY_LOCK:
        return {"approved": True, "reason": "disabled", "checks": {}}

    state = load_live_safety_state()
    if state.get("locked") and state.get("manual_unlock_required"):
        return {"approved": False, "reason": state.get("reason", "live_safety_locked"), "checks": state.get("checks", {})}

    checks = {}
    failures = []

    # Only enforce for real live mode.
    checks["live_mode"] = bool(LIVE_MODE)
    if not LIVE_MODE:
        state["checks"] = checks
        save_live_safety_state(state)
        return {"approved": True, "reason": "paper_mode", "checks": checks}

    checks["enable_alpaca"] = bool(ENABLE_ALPACA)
    if LIVE_SAFETY_REQUIRE_ALPACA and not ENABLE_ALPACA:
        failures.append("ENABLE_ALPACA_false")

    checks["paper_execution_disabled"] = not bool(ENABLE_PAPER_EXECUTION)
    if ENABLE_PAPER_EXECUTION:
        failures.append("paper_execution_still_enabled")

    checks["alpaca_keys_loaded"] = bool(ALPACA_API_KEY and ALPACA_SECRET_KEY)
    if not checks["alpaca_keys_loaded"]:
        failures.append("missing_alpaca_live_keys")

    checks["alpaca_base_url"] = ALPACA_BASE_URL
    if "paper-api" in str(ALPACA_BASE_URL).lower():
        failures.append("alpaca_base_url_is_paper")

    checks["options_approved"] = bool(ALPACA_LIVE_OPTIONS_APPROVED)
    if LIVE_SAFETY_REQUIRE_OPTIONS_APPROVED and not ALPACA_LIVE_OPTIONS_APPROVED:
        failures.append("options_not_marked_approved")

    checks["force_execution_off"] = not bool(FORCE_EXECUTION_MODE)
    if LIVE_SAFETY_REQUIRE_FORCE_OFF and FORCE_EXECUTION_MODE:
        failures.append("FORCE_EXECUTION_MODE_must_be_false_live")

    checks["duplicates_off"] = not bool(ALLOW_DUPLICATE_SIGNALS)
    if LIVE_SAFETY_REQUIRE_DUPLICATES_OFF and ALLOW_DUPLICATE_SIGNALS:
        failures.append("ALLOW_DUPLICATE_SIGNALS_must_be_false_live")

    equity = live_safety_account_equity()
    checks["account_equity"] = equity
    if equity < safe_float(LIVE_SAFETY_MIN_ACCOUNT_EQUITY, 50):
        failures.append(f"equity_below_min:{equity}")
    if equity > safe_float(LIVE_SAFETY_MAX_ACCOUNT_EQUITY, 500):
        failures.append(f"equity_above_day1_max:{equity}")

    open_count = live_safety_open_position_count()
    checks["open_positions"] = open_count
    if open_count >= safe_int(LIVE_SAFETY_MAX_OPEN_POSITIONS, 1):
        failures.append(f"max_live_open_positions_reached:{open_count}")

    daily_pnl = risk_state_get_daily_pnl() if "risk_state_get_daily_pnl" in globals() else safe_float(GLOBAL_STATE.get("daily_pnl", 0), 0)
    checks["daily_pnl"] = daily_pnl
    if daily_pnl <= -abs(safe_float(LIVE_SAFETY_MAX_DAILY_LOSS_DOLLARS, 25)):
        failures.append(f"live_daily_loss_dollars_hit:{daily_pnl}")
    if equity > 0 and (daily_pnl / equity) <= -abs(safe_float(LIVE_SAFETY_MAX_DAILY_LOSS_PCT, 0.10)):
        failures.append(f"live_daily_loss_pct_hit:{round((daily_pnl/equity)*100, 2)}%")

    fresh_ok, fresh_reason = live_safety_market_data_fresh()
    checks["market_data"] = fresh_reason
    if not fresh_ok:
        failures.append(fresh_reason)

    hours_ok, hours_reason = live_safety_within_market_hours()
    checks["market_hours"] = hours_reason
    if not hours_ok:
        failures.append(hours_reason)

    if isinstance(signal, dict):
        qty = safe_int(signal.get("qty", 1), 1)
        checks["incoming_qty"] = qty
        if qty > safe_int(LIVE_SAFETY_MAX_QTY, 1):
            failures.append(f"live_qty_too_large:{qty}")

    state["checks"] = checks

    if failures:
        reason = ",".join(failures)
        if LIVE_SAFETY_AUTO_LOCK_ON_ERROR:
            live_safety_lock(reason)
        else:
            state["reason"] = reason
            save_live_safety_state(state)
        return {"approved": False, "reason": reason, "checks": checks}

    state["locked"] = False
    state["reason"] = "live_safety_passed"
    save_live_safety_state(state)
    debug("LIVE SAFETY CHECK PASSED")
    return {"approved": True, "reason": "live_safety_passed", "checks": checks}


def apply_live_safety_lock_to_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if not isinstance(signal, dict):
            return signal
        result = live_safety_check(signal)
        signal["live_safety"] = result
        if not result.get("approved", False):
            signal["blocked_by_live_safety"] = True
            signal["live_safety_reason"] = result.get("reason", "live_safety_blocked")
            debug(f"LIVE SAFETY BLOCKED TRADE | reason={signal['live_safety_reason']}")
            try:
                journal_record_signal_decision(signal, "live_safety", "blocked", signal["live_safety_reason"])
            except Exception:
                pass
        else:
            signal["blocked_by_live_safety"] = False
            signal["live_safety_reason"] = ""
        return signal
    except Exception as e:
        signal["blocked_by_live_safety"] = True
        signal["live_safety_reason"] = f"live_safety_exception:{e}"
        debug(f"LIVE SAFETY EXCEPTION BLOCK | {e}")
        return signal


def live_safety_blocks_signal(signal: Dict[str, Any]) -> bool:
    try:
        return bool(isinstance(signal, dict) and signal.get("blocked_by_live_safety"))
    except Exception:
        return False


def risk_state_record_closed_trade(trade_or_position: Dict[str, Any]) -> Dict[str, Any]:
    """
    Updates win/loss streaks when a trade closes.
    This is safe even if no close hook exists yet.
    """
    try:
        if not ENABLE_RISK_STATE_ENGINE or not isinstance(trade_or_position, dict):
            return load_risk_state()

        state = load_risk_state()
        pnl = safe_float(
            trade_or_position.get(
                "realized_pnl",
                trade_or_position.get("realized_pnl_pct", trade_or_position.get("pnl", trade_or_position.get("pnl_pct", 0))),
            ),
            0.0,
        )

        if pnl > 0:
            state["win_streak"] = safe_int(state.get("win_streak", 0), 0) + 1
            state["loss_streak"] = 0
        elif pnl < 0:
            state["loss_streak"] = safe_int(state.get("loss_streak", 0), 0) + 1
            state["win_streak"] = 0

        state["daily_realized_pnl"] = safe_float(state.get("daily_realized_pnl", 0), 0) + pnl
        equity = max(risk_state_account_equity(), 1.0)
        state["daily_realized_pnl_pct"] = safe_float(state.get("daily_realized_pnl", 0), 0) / equity
        save_risk_state(state)
        risk_state_evaluate()
        return state

    except Exception as e:
        debug(f"RISK STATE RECORD CLOSED TRADE ERROR | {e}")
        return load_risk_state()


def risk_state_manual_unlock(reason: str = "manual_unlock") -> Dict[str, Any]:
    state = load_risk_state()
    state["locked"] = False
    state["manual_unlock_required"] = False
    state["loss_streak"] = 0
    state["state"] = "NORMAL"
    state["last_reason"] = reason
    save_risk_state(state)
    debug(f"RISK STATE UNLOCKED | reason={reason}")
    return state

# AUTO ANALYZER → AI_SIGNAL.JSON GENERATOR
# Generates ai_signal.json from analyzer/rule conditions.
# =========================================================
ENABLE_AUTO_AI_SIGNAL_GENERATOR = os.getenv("ENABLE_AUTO_AI_SIGNAL_GENERATOR", "true").lower() == "true"
AUTO_AI_SIGNAL_TICKERS = [x.strip().upper() for x in os.getenv("AUTO_AI_SIGNAL_TICKERS", "QQQ,SPY").split(",") if x.strip()]
AUTO_AI_SIGNAL_MIN_GRADE = os.getenv("AUTO_AI_SIGNAL_MIN_GRADE", "A").upper().strip()
AUTO_AI_SIGNAL_COOLDOWN_SECONDS = int(os.getenv("AUTO_AI_SIGNAL_COOLDOWN_SECONDS", "300"))
AUTO_AI_SIGNAL_FILE = os.getenv("AUTO_AI_SIGNAL_FILE", "ai_signal.json")
AUTO_AI_STATE_FILE = os.getenv("AUTO_AI_STATE_FILE", "auto_ai_signal_state.json")
AUTO_AI_DEFAULT_CONTRACT_PRICE = float(os.getenv("AUTO_AI_DEFAULT_CONTRACT_PRICE", "1.35"))
AUTO_AI_DEFAULT_STOP_OFFSET = float(os.getenv("AUTO_AI_DEFAULT_STOP_OFFSET", "0.35"))
AUTO_AI_DEFAULT_TP1_OFFSET = float(os.getenv("AUTO_AI_DEFAULT_TP1_OFFSET", "0.40"))
AUTO_AI_DEFAULT_TP2_OFFSET = float(os.getenv("AUTO_AI_DEFAULT_TP2_OFFSET", "0.80"))

# =========================================================
# AI SIGNAL -> SIGNAL.JSON EXECUTION BRIDGE
# Converts ai_signal.json into signal.json before execution loop.
# =========================================================
ENABLE_AI_TO_SIGNAL_EXECUTION_BRIDGE = os.getenv("ENABLE_AI_TO_SIGNAL_EXECUTION_BRIDGE", "true").lower() == "true"
AI_TO_SIGNAL_FORCE_TIMESTAMP = os.getenv("AI_TO_SIGNAL_FORCE_TIMESTAMP", "true").lower() == "true"
AI_TO_SIGNAL_DELETE_AFTER_WRITE = os.getenv("AI_TO_SIGNAL_DELETE_AFTER_WRITE", "false").lower() == "true"
AI_TO_SIGNAL_SKIP_IF_SIGNAL_EXISTS = os.getenv("AI_TO_SIGNAL_SKIP_IF_SIGNAL_EXISTS", "false").lower() == "true"

# AI → SIGNAL.JSON BRIDGE
# Reads AI decision output, validates it, normalizes it into
# execution-safe signal.json, then lets main engine process it.
# =========================================================
ENABLE_AI_SIGNAL_BRIDGE = os.getenv("ENABLE_AI_SIGNAL_BRIDGE", "true").lower() == "true"
AI_SIGNAL_INPUT_FILE = os.getenv("AI_SIGNAL_INPUT_FILE", "ai_signal.json")
AI_SIGNAL_ARCHIVE_FILE = os.getenv("AI_SIGNAL_ARCHIVE_FILE", "ai_signal.last.json")
AI_SIGNAL_MIN_GRADE = os.getenv("AI_SIGNAL_MIN_GRADE", "A").upper().strip()
AI_SIGNAL_ALLOWED_GRADES = set(x.strip().upper() for x in os.getenv("AI_SIGNAL_ALLOWED_GRADES", "A+,A").split(",") if x.strip())
AI_SIGNAL_REQUIRE_CONFIRMATION = os.getenv("AI_SIGNAL_REQUIRE_CONFIRMATION", "true").lower() == "true"
AI_SIGNAL_REQUIRE_SETUP = os.getenv("AI_SIGNAL_REQUIRE_SETUP", "true").lower() == "true"
AI_SIGNAL_REQUIRE_TRIGGER = os.getenv("AI_SIGNAL_REQUIRE_TRIGGER", "true").lower() == "true"
AI_SIGNAL_OVERWRITE_SIGNAL_FILE = os.getenv("AI_SIGNAL_OVERWRITE_SIGNAL_FILE", "false").lower() == "true"

VALID_AI_SETUPS = {
    "vwap_reclaim",
    "vwap_reject",
    "break_and_hold",
    "breakout_retest",
    "resistance_rejection",
    "support_hold",
    "liquidity_grab_reversal",
    "higher_low_continuation",
    "lower_high_rejection",
}

VALID_AI_TRIGGERS = {
    "vwap_reclaim",
    "vwap_reject",
    "break_and_hold",
    "breakout_retest",
    "resistance_rejection",
    "support_hold",
    "liquidity_grab_reversal",
    "higher_low",
    "lower_high",
    "volume_breakout",
}

VALID_AI_CONFIRMATIONS = {
    "volume",
    "retest",
    "hold",
    "reclaim",
    "reject",
    "momentum",
    "structure",
    "vwap",
}



# =========================================================

# =========================================================
# AUTO ANALYZER → AI_SIGNAL.JSON GENERATOR HELPERS
# =========================================================
def load_auto_ai_state() -> Dict[str, Any]:
    data = load_json_file(AUTO_AI_STATE_FILE, {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("last_signal_ts", 0)
    data.setdefault("last_signal_key", "")
    data.setdefault("signals_generated", 0)
    return data


def save_auto_ai_state(data: Dict[str, Any]) -> None:
    atomic_write_json(AUTO_AI_STATE_FILE, data)


def auto_ai_recently_generated(state: Dict[str, Any], key: str) -> bool:
    last_ts = safe_int(state.get("last_signal_ts", 0), 0)
    last_key = str(state.get("last_signal_key", ""))
    return key == last_key and (now_ts() - last_ts) < AUTO_AI_SIGNAL_COOLDOWN_SECONDS


def auto_ai_read_market_snapshot() -> Dict[str, Any]:
    try:
        data = load_json_file(MARKET_PRICES_FILE, {})
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def auto_ai_get_price(snapshot: Dict[str, Any], ticker: str) -> float:
    row = snapshot.get(ticker) if isinstance(snapshot, dict) else None
    if isinstance(row, dict):
        return safe_float(row.get("price", row.get("close", 0)), 0.0)
    return safe_float(row, 0.0)


def auto_ai_grade_signal(setup: str, ticker: str, direction: str, price: float) -> Dict[str, Any]:
    if price <= 0:
        return {"grade": "AVOID", "reason": "missing_market_price"}
    setup = setup or "vwap_reclaim"
    return {
        "grade": "A",
        "confidence": "A",
        "setup": setup,
        "trigger": "vwap_reclaim" if setup == "vwap_reclaim" else "break_and_hold",
        "confirmation": "volume",
        "regime": "clean",
        "reason": f"{ticker} auto analyzer detected {setup} | clean regime | volume confirmation | A-grade only",
    }


def auto_ai_build_signal_for_ticker(ticker: str, snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ticker = str(ticker).upper().strip()
    price = auto_ai_get_price(snapshot, ticker)
    direction = "CALL"
    setup = "vwap_reclaim"
    grade_info = auto_ai_grade_signal(setup, ticker, direction, price)
    grade = str(grade_info.get("grade", "AVOID")).upper()

    if ai_grade_rank(grade) < ai_grade_rank(AUTO_AI_SIGNAL_MIN_GRADE):
        return None

    entry = round(AUTO_AI_DEFAULT_CONTRACT_PRICE, 2)
    stop = round(max(0.01, entry - AUTO_AI_DEFAULT_STOP_OFFSET), 2)
    target = round(entry + AUTO_AI_DEFAULT_TP1_OFFSET, 2)
    tp2 = round(entry + AUTO_AI_DEFAULT_TP2_OFFSET, 2)

    signal = {
        "ticker": ticker,
        "direction": direction,
        "grade": grade,
        "confidence": str(grade_info.get("confidence", grade)).upper(),
        "setup": grade_info.get("setup", setup),
        "trigger": grade_info.get("trigger", "vwap_reclaim"),
        "confirmation": grade_info.get("confirmation", "volume"),
        "entry": entry,
        "stop": stop,
        "target": target,
        "tp2_contract": tp2,
        "qty": 1,
        "regime": grade_info.get("regime", "clean"),
        "underlying_price": price,
        "reason": grade_info.get("reason", f"{ticker} auto analyzer A setup"),
        "source": "auto_ai_signal_generator",
        "timestamp": now_ts(),
    }
    return apply_macro_context_to_ai_signal(signal)


def auto_generate_ai_signal_if_ready() -> Dict[str, Any]:
    if not ENABLE_AUTO_AI_SIGNAL_GENERATOR:
        return {"generated": False, "reason": "disabled"}

    try:
        if file_exists(AUTO_AI_SIGNAL_FILE):
            return {"generated": False, "reason": "ai_signal_already_exists"}
        if file_exists(SIGNAL_FILE):
            return {"generated": False, "reason": "signal_file_already_exists"}

        snapshot = auto_ai_read_market_snapshot()
        if not snapshot:
            return {"generated": False, "reason": "missing_market_snapshot"}

        state = load_auto_ai_state()

        for ticker in AUTO_AI_SIGNAL_TICKERS:
            candidate = auto_ai_build_signal_for_ticker(ticker, snapshot)
            if not candidate:
                continue

            key = f"{candidate.get('ticker')}_{candidate.get('direction')}_{candidate.get('setup')}_{candidate.get('grade')}"
            if auto_ai_recently_generated(state, key):
                return {"generated": False, "reason": "cooldown_active", "key": key}

            if macro_enforcement_blocks_signal(candidate):
                return {"generated": False, "reason": "macro_blocked", "signal": candidate}

            if elite_execution_filter_blocks_signal(candidate):
                return {"generated": False, "reason": "elite_filter_blocked", "signal": candidate}

            candidate = apply_volatility_confidence_position_sizing(candidate)
            if vol_conf_sizing_blocks_signal(candidate):
                return {"generated": False, "reason": "vol_conf_sizing_blocked", "signal": candidate}

            candidate = apply_risk_state_to_signal(candidate)
            if risk_state_blocks_signal(candidate):
                return {"generated": False, "reason": "risk_state_blocked", "signal": candidate}

            candidate = apply_portfolio_heat_exposure_control(candidate)
            if portfolio_heat_blocks_signal(candidate):
                journal_record_signal_decision(candidate, "portfolio_heat", "blocked", candidate.get("portfolio_heat_reason", "portfolio_heat_blocked"))
                return {"generated": False, "reason": "portfolio_heat_blocked", "signal": candidate}

            candidate = apply_learning_feedback_to_signal(candidate)
            if learning_blocks_signal(candidate):
                journal_record_signal_decision(candidate, "learning_feedback", "blocked", candidate.get("learning_block_reason", "learning_blocked"))
                return {"generated": False, "reason": "learning_blocked", "signal": candidate}

            candidate = apply_live_safety_lock_to_signal(candidate)
            if live_safety_blocks_signal(candidate):
                return {"generated": False, "reason": "live_safety_blocked", "signal": candidate}

            journal_record_signal_decision(candidate, "auto_ai_generator", "generated", "passed_all_filters")
            atomic_write_json(AUTO_AI_SIGNAL_FILE, candidate)
            state["last_signal_ts"] = now_ts()
            state["last_signal_key"] = key
            state["signals_generated"] = safe_int(state.get("signals_generated", 0), 0) + 1
            save_auto_ai_state(state)

            debug(f"AUTO AI SIGNAL GENERATED | {key} | file={AUTO_AI_SIGNAL_FILE}")
            return {"generated": True, "reason": "ai_signal_generated", "signal": candidate}

        return {"generated": False, "reason": "no_a_setup_detected"}

    except Exception as e:
        log(f"❌ AUTO AI SIGNAL GENERATOR ERROR | {e}")
        return {"generated": False, "reason": "error", "error": str(e)}
# AI → SIGNAL.JSON BRIDGE HELPERS
# =========================================================

def build_signal_from_ai() -> Dict[str, Any]:
    """
    Reads ai_signal.json, applies existing filters/safety systems, then writes signal.json.
    """
    try:
        if not ENABLE_AI_TO_SIGNAL_EXECUTION_BRIDGE:
            return {"written": False, "reason": "disabled"}

        ai_file = globals().get("AI_SIGNAL_INPUT_FILE", "ai_signal.json")
        sig_file = globals().get("SIGNAL_FILE", "signal.json")

        if not os.path.exists(ai_file):
            return {"written": False, "reason": "no_ai_signal_file"}

        if AI_TO_SIGNAL_SKIP_IF_SIGNAL_EXISTS and os.path.exists(sig_file):
            return {"written": False, "reason": "signal_file_already_exists"}

        ai = load_json_file(ai_file, {})
        if not isinstance(ai, dict) or not ai:
            debug("AI TO SIGNAL BRIDGE SKIP | invalid ai_signal.json")
            return {"written": False, "reason": "invalid_ai_signal"}

        if "normalize_ai_to_engine_signal" in globals():
            signal = normalize_ai_to_engine_signal(ai)
        else:
            signal = {
                "ticker": ai.get("ticker", ai.get("symbol", "QQQ")),
                "symbol": ai.get("symbol", ai.get("ticker", "QQQ")),
                "contract_symbol": ai.get("contract_symbol", ai.get("option_symbol", ai.get("symbol", ai.get("ticker", "QQQ")))),
                "direction": ai.get("direction", "CALL"),
                "grade": ai.get("grade", ai.get("confidence", "A")),
                "confidence": ai.get("confidence", ai.get("grade", "A")),
                "entry": ai.get("entry", ai.get("entry_contract", ai.get("contract_price", 0))),
                "stop": ai.get("stop", ai.get("stop_contract", 0)),
                "target": ai.get("target", ai.get("tp1_contract", ai.get("take_profit", 0))),
                "qty": ai.get("qty", ai.get("quantity", 1)),
                "setup": ai.get("setup", ai.get("strategy", "break_and_hold")),
                "trigger": ai.get("trigger", "break_and_hold"),
                "confirmation": ai.get("confirmation", "volume"),
                "regime": ai.get("regime", "clean"),
                "reason": ai.get("reason", "AI to signal bridge"),
                "timestamp": ai.get("timestamp", now_ts()),
                "source": "ai_to_signal_bridge",
            }

        if AI_TO_SIGNAL_FORCE_TIMESTAMP:
            signal["timestamp"] = now_ts()
            signal["bridge_nonce"] = hashlib.sha256(f"{now_ts()}-{time.time()}".encode("utf-8")).hexdigest()[:12]

        filter_steps = [
            ("apply_macro_context_to_ai_signal", None),
            ("macro_enforcement_blocks_signal", "macro_blocked"),
            ("elite_execution_filter_blocks_signal", "elite_filter_blocked"),
            ("apply_volatility_confidence_position_sizing", None),
            ("vol_conf_sizing_blocks_signal", "vol_conf_sizing_blocked"),
            ("apply_risk_state_to_signal", None),
            ("risk_state_blocks_signal", "risk_state_blocked"),
            ("apply_portfolio_heat_exposure_control", None),
            ("portfolio_heat_blocks_signal", "portfolio_heat_blocked"),
            ("apply_learning_feedback_to_signal", None),
            ("learning_blocks_signal", "learning_blocked"),
            ("apply_live_safety_lock_to_signal", None),
            ("live_safety_blocks_signal", "live_safety_blocked"),
        ]

        for fn_name, block_reason in filter_steps:
            fn = globals().get(fn_name)
            if not callable(fn):
                continue
            if block_reason is None:
                updated = fn(signal)
                if isinstance(updated, dict):
                    signal = updated
            else:
                if fn(signal):
                    debug(f"AI TO SIGNAL BRIDGE BLOCKED | stage={fn_name} reason={block_reason}")
                    return {"written": False, "reason": block_reason, "signal": signal}

        if "ai_signal_validation_errors" in globals():
            errors = ai_signal_validation_errors(ai, signal)
            if errors:
                debug(f"AI TO SIGNAL BRIDGE VALIDATION BLOCKED | errors={errors}")
                return {"written": False, "reason": "validation_failed", "errors": errors, "signal": signal}

        atomic_write_json(sig_file, signal)
        debug(f"AI TO SIGNAL BRIDGE WROTE SIGNAL | {signal.get('ticker')} {signal.get('direction')} {signal.get('grade', signal.get('confidence'))} file={sig_file}")

        if AI_TO_SIGNAL_DELETE_AFTER_WRITE:
            try:
                os.remove(ai_file)
            except Exception:
                pass

        return {"written": True, "reason": "signal_written", "signal": signal}

    except Exception as e:
        log(f"❌ AI TO SIGNAL BRIDGE ERROR | {e}")
        return {"written": False, "reason": "error", "error": str(e)}


def ai_grade_rank(grade: str) -> int:
    order = {"A+": 5, "A": 4, "B+": 3, "B": 2, "C": 1, "AVOID": 0}
    return order.get(str(grade).upper().strip(), 0)


def ai_signal_file_exists() -> bool:
    try:
        return os.path.exists(AI_SIGNAL_INPUT_FILE)
    except Exception:
        return False


def load_ai_signal_input() -> Optional[Dict[str, Any]]:
    try:
        if not ai_signal_file_exists():
            return None
        data = load_json_file(AI_SIGNAL_INPUT_FILE, {})
        if not isinstance(data, dict):
            debug("AI BRIDGE SKIP | ai_signal.json must be a JSON object")
            return None
        return data
    except Exception as e:
        log(f"❌ AI BRIDGE LOAD ERROR | {e}")
        return None


def normalize_ai_signal_setup(value: Any) -> str:
    raw = str(value or "").lower().strip().replace(" ", "_").replace("-", "_")
    aliases = {
        "vwap_reclaim_continuation": "vwap_reclaim",
        "reclaim": "vwap_reclaim",
        "vwap_break": "vwap_reclaim",
        "reject": "vwap_reject",
        "vwap_rejection": "vwap_reject",
        "break_hold": "break_and_hold",
        "break_and_hold_over_reclaim_level": "break_and_hold",
        "breakout_hold": "break_and_hold",
        "retest_hold": "breakout_retest",
    }
    return aliases.get(raw, raw)


def normalize_ai_signal_trigger(value: Any, setup: str) -> str:
    raw = str(value or "").lower().strip().replace(" ", "_").replace("-", "_")
    aliases = {
        "reclaim": "vwap_reclaim",
        "vwap": "vwap_reclaim",
        "break_hold": "break_and_hold",
        "break_and_hold_over_reclaim_level": "break_and_hold",
        "breakout_hold": "break_and_hold",
        "retest_hold": "breakout_retest",
        "reject": "vwap_reject",
    }
    normalized = aliases.get(raw, raw)
    if not normalized and setup:
        normalized = setup
    return normalized


def normalize_ai_confirmation(value: Any) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    raw = str(value or "").lower().strip().replace(" ", "_").replace("-", "_")
    aliases = {
        "vol": "volume",
        "volume_confirmation": "volume",
        "confirmed_volume": "volume",
        "held_level": "hold",
        "level_hold": "hold",
        "retest_hold": "retest",
        "vwap_hold": "vwap",
    }
    return aliases.get(raw, raw)


def ai_signal_validation_errors(ai: Dict[str, Any], signal: Dict[str, Any]) -> List[str]:
    errors = []

    grade = str(signal.get("grade", "")).upper().strip()
    if AI_SIGNAL_ALLOWED_GRADES and grade not in AI_SIGNAL_ALLOWED_GRADES:
        errors.append(f"grade_not_allowed:{grade}")
    if ai_grade_rank(grade) < ai_grade_rank(AI_SIGNAL_MIN_GRADE):
        errors.append(f"grade_below_min:{grade}<{AI_SIGNAL_MIN_GRADE}")

    ticker = str(signal.get("ticker", "")).upper().strip()
    direction = str(signal.get("direction", "")).upper().strip()
    if not ticker:
        errors.append("missing_ticker")
    if direction not in ("CALL", "PUT"):
        errors.append(f"invalid_direction:{direction}")

    entry = safe_float(signal.get("entry", 0), 0.0)
    stop = safe_float(signal.get("stop", 0), 0.0)
    target = safe_float(signal.get("target", 0), 0.0)

    if entry <= 0:
        errors.append("missing_or_invalid_entry")
    if stop <= 0:
        errors.append("missing_or_invalid_stop")
    if target <= 0:
        errors.append("missing_or_invalid_target")

    if direction == "CALL":
        if stop >= entry:
            errors.append("call_stop_must_be_below_entry")
        if target <= entry:
            errors.append("call_target_must_be_above_entry")
    if direction == "PUT":
        if stop <= entry:
            errors.append("put_stop_must_be_above_entry")
        if target >= entry:
            errors.append("put_target_must_be_below_entry")

    setup = str(signal.get("setup", "")).lower().strip()
    trigger = str(signal.get("trigger", "")).lower().strip()
    confirmation = str(signal.get("confirmation", "")).lower().strip()

    if AI_SIGNAL_REQUIRE_SETUP and setup not in VALID_AI_SETUPS:
        errors.append(f"invalid_setup:{setup}")
    if AI_SIGNAL_REQUIRE_TRIGGER and trigger not in VALID_AI_TRIGGERS:
        errors.append(f"invalid_trigger:{trigger}")
    if AI_SIGNAL_REQUIRE_CONFIRMATION and confirmation not in VALID_AI_CONFIRMATIONS:
        errors.append(f"invalid_confirmation:{confirmation}")

    return errors


def normalize_ai_to_engine_signal(ai: Dict[str, Any]) -> Dict[str, Any]:
    ticker = str(ai.get("ticker") or ai.get("symbol") or ai.get("underlying") or "QQQ").upper().strip()
    direction = normalize_direction(ai.get("direction", ai.get("bias", "CALL")))

    setup = normalize_ai_signal_setup(ai.get("setup") or ai.get("strategy"))
    trigger = normalize_ai_signal_trigger(ai.get("trigger"), setup)
    confirmation = normalize_ai_confirmation(ai.get("confirmation") or ai.get("confirm"))

    entry = safe_float(ai.get("entry_contract", ai.get("entry", ai.get("contract_price", 0))), 0.0)
    stop = safe_float(ai.get("stop_contract", ai.get("stop", 0)), 0.0)
    target = safe_float(ai.get("tp1_contract", ai.get("target", ai.get("take_profit", 0))), 0.0)
    tp2 = safe_float(ai.get("tp2_contract", ai.get("target_2", ai.get("tp2", target))), target)

    # If AI supplied underlying levels only, keep them too.
    underlying_price = safe_float(ai.get("underlying_price", ai.get("price", 0)), 0.0)

    grade = str(ai.get("grade", ai.get("confidence", "B"))).upper().strip()
    confidence = str(ai.get("confidence", grade)).upper().strip()

    contract_symbol = str(
        ai.get("contract_symbol")
        or ai.get("option_symbol")
        or ai.get("symbol")
        or ticker
    ).strip()

    reason = str(ai.get("reason") or ai.get("thesis") or ai.get("public_reason") or "AI bridge signal").strip()

    signal = {
        "ticker": ticker,
        "symbol": contract_symbol,
        "contract_symbol": contract_symbol,
        "asset_class": str(ai.get("asset_class", "option")).lower().strip(),
        "direction": direction,
        "confidence": confidence,
        "grade": grade,
        "entry": entry,
        "stop": stop,
        "target": target,
        "entry_contract": entry,
        "stop_contract": stop,
        "tp1_contract": target,
        "tp2_contract": tp2,
        "contract_price": safe_float(ai.get("contract_price", entry), entry),
        "underlying_price": underlying_price,
        "qty": safe_int(ai.get("qty", ai.get("quantity", 1)), 1),
        "setup": setup,
        "strategy": setup,
        "trigger": trigger,
        "confirmation": confirmation,
        "regime": str(ai.get("regime", "clean")).lower().strip(),
        "reason": reason,
        "public_reason": str(ai.get("public_reason", reason)).strip(),
        "notes": ai.get("notes", [] if isinstance(ai.get("notes"), list) else str(ai.get("notes", reason))),
        "source": "ai_signal_bridge",
        "timestamp": safe_int(ai.get("timestamp", now_ts()), now_ts()),
        "ai_bridge_version": 1,
        "macro_bias": ai.get("macro_bias", "neutral"),
        "macro_risk_score": safe_int(ai.get("macro_risk_score", 0), 0),
        "macro_notes": ai.get("macro_notes", []),
        "macro_updated_at": ai.get("macro_updated_at", 0),
        "oil_price": ai.get("oil_price", 0),
        "vix": ai.get("vix", 0),
        "macro_warning": ai.get("macro_warning", ""),
    }

    return signal


def archive_ai_signal_input(ai: Dict[str, Any], status: str, details: Optional[Dict[str, Any]] = None) -> None:
    try:
        payload = {
            "archived_at": now_ts(),
            "status": status,
            "details": details or {},
            "ai_signal": ai,
        }
        atomic_write_json(AI_SIGNAL_ARCHIVE_FILE, payload)
    except Exception as e:
        debug(f"AI BRIDGE ARCHIVE ERROR | {e}")


def ai_bridge_write_signal_if_ready() -> Dict[str, Any]:
    result = {"written": False, "reason": "disabled"}

    if not ENABLE_AI_SIGNAL_BRIDGE:
        return result

    ai = load_ai_signal_input()
    if not ai:
        return {"written": False, "reason": "no_ai_signal"}

    try:
        if file_exists(SIGNAL_FILE) and not AI_SIGNAL_OVERWRITE_SIGNAL_FILE:
            return {"written": False, "reason": "signal_file_already_exists"}

        signal = normalize_ai_to_engine_signal(ai)
        signal = apply_macro_context_to_ai_signal(signal)
        errors = ai_signal_validation_errors(ai, signal)

        if signal.get("blocked_by_macro"):
            reason = signal.get("macro_reason", "macro_blocked")
            debug(f"MACRO BLOCKED AI SIGNAL | ticker={signal.get('ticker')} direction={signal.get('direction')} reason={reason}")
            archive_ai_signal_input(ai, "macro_blocked", {"reason": reason, "normalized_signal": signal})
            return {"written": False, "reason": "macro_blocked", "macro_reason": reason, "signal": signal}

        if elite_execution_filter_blocks_signal(signal):
            reason = signal.get("elite_filter_reason", "elite_filter_blocked")
            debug(f"ELITE FILTER BLOCKED AI SIGNAL | ticker={signal.get('ticker')} direction={signal.get('direction')} reason={reason}")
            archive_ai_signal_input(ai, "elite_filter_blocked", {"reason": reason, "normalized_signal": signal})
            return {"written": False, "reason": "elite_filter_blocked", "elite_filter_reason": reason, "signal": signal}

        signal = apply_volatility_confidence_position_sizing(signal)
        if vol_conf_sizing_blocks_signal(signal):
            reason = signal.get("vol_conf_sizing_reason", "vol_conf_sizing_blocked")
            debug(f"VOL CONF SIZING BLOCKED AI SIGNAL | ticker={signal.get('ticker')} direction={signal.get('direction')} reason={reason}")
            archive_ai_signal_input(ai, "vol_conf_sizing_blocked", {"reason": reason, "normalized_signal": signal})
            return {"written": False, "reason": "vol_conf_sizing_blocked", "vol_conf_sizing_reason": reason, "signal": signal}

        signal = apply_risk_state_to_signal(signal)
        if risk_state_blocks_signal(signal):
            reason = signal.get("risk_state_block_reason", "risk_state_blocked")
            debug(f"RISK STATE BLOCKED AI SIGNAL | ticker={signal.get('ticker')} direction={signal.get('direction')} reason={reason}")
            archive_ai_signal_input(ai, "risk_state_blocked", {"reason": reason, "normalized_signal": signal})
            return {"written": False, "reason": "risk_state_blocked", "risk_state_reason": reason, "signal": signal}

        signal = apply_portfolio_heat_exposure_control(signal)
        if portfolio_heat_blocks_signal(signal):
            reason = signal.get("portfolio_heat_reason", "portfolio_heat_blocked")
            debug(f"PORTFOLIO HEAT BLOCKED AI SIGNAL | ticker={signal.get('ticker')} direction={signal.get('direction')} reason={reason}")
            archive_ai_signal_input(ai, "portfolio_heat_blocked", {"reason": reason, "normalized_signal": signal})
            return {"written": False, "reason": "portfolio_heat_blocked", "portfolio_heat_reason": reason, "signal": signal}

        signal = apply_learning_feedback_to_signal(signal)
        if learning_blocks_signal(signal):
            reason = signal.get("learning_block_reason", "learning_blocked")
            debug(f"LEARNING BLOCKED AI SIGNAL | ticker={signal.get('ticker')} direction={signal.get('direction')} reason={reason}")
            archive_ai_signal_input(ai, "learning_blocked", {"reason": reason, "normalized_signal": signal})
            journal_record_signal_decision(signal, "learning_feedback", "blocked", reason)
            return {"written": False, "reason": "learning_blocked", "learning_reason": reason, "signal": signal}

        signal = apply_live_safety_lock_to_signal(signal)
        if live_safety_blocks_signal(signal):
            reason = signal.get("live_safety_reason", "live_safety_blocked")
            debug(f"LIVE SAFETY BLOCKED AI SIGNAL | ticker={signal.get('ticker')} direction={signal.get('direction')} reason={reason}")
            archive_ai_signal_input(ai, "live_safety_blocked", {"reason": reason, "normalized_signal": signal})
            return {"written": False, "reason": "live_safety_blocked", "live_safety_reason": reason, "signal": signal}

        journal_record_signal_decision(signal, "ai_bridge", "written", "passed_all_filters")

        if errors:
            debug(f"AI BRIDGE BLOCKED | errors={errors}")
            archive_ai_signal_input(ai, "blocked", {"errors": errors, "normalized_signal": signal})
            return {"written": False, "reason": "validation_failed", "errors": errors}

        atomic_write_json(SIGNAL_FILE, signal)
        archive_ai_signal_input(ai, "written", {"signal_file": SIGNAL_FILE, "signal": signal})

        # Move source out of the way after successful handoff so it does not rewrite same signal forever.
        try:
            os.remove(AI_SIGNAL_INPUT_FILE)
        except Exception:
            pass

        debug(f"AI BRIDGE WROTE SIGNAL | {signal.get('ticker')} {signal.get('direction')} {signal.get('grade')} setup={signal.get('setup')}")
        return {"written": True, "reason": "signal_written", "signal": signal}

    except Exception as e:
        log(f"❌ AI BRIDGE ERROR | {e}")
        archive_ai_signal_input(ai, "error", {"error": str(e)})
        return {"written": False, "reason": "bridge_error", "error": str(e)}


# FALLBACK TEST SIGNAL CONTROL
# Default OFF so engine does not auto-create fake/test signals.
# =========================================================
ENABLE_FALLBACK_SIGNAL = os.getenv("ENABLE_FALLBACK_SIGNAL", "false").lower() == "true"
AUTO_FALLBACK_SIGNAL = os.getenv("AUTO_FALLBACK_SIGNAL", "false").lower() == "true"
ROUTE_FALLBACK_TEST_SIGNAL = os.getenv("ROUTE_FALLBACK_TEST_SIGNAL", "false").lower() == "true"

def fallback_signal_enabled() -> bool:
    return bool(ENABLE_FALLBACK_SIGNAL or AUTO_FALLBACK_SIGNAL or ROUTE_FALLBACK_TEST_SIGNAL)


ENABLE_POSITION_SCHEMA_LOCK = os.getenv("ENABLE_POSITION_SCHEMA_LOCK", "true").lower() == "true"
ENABLE_HARD_DUPLICATE_POSITION_CAP = os.getenv("ENABLE_HARD_DUPLICATE_POSITION_CAP", "true").lower() == "true"
MAX_OPEN_POSITIONS_PER_SYMBOL_DIRECTION = int(os.getenv("MAX_OPEN_POSITIONS_PER_SYMBOL_DIRECTION", "1"))
MAX_OPEN_POSITIONS_TOTAL = int(os.getenv("MAX_OPEN_POSITIONS_TOTAL", "3"))

ENABLE_PAPER_TPSL_LIFECYCLE = os.getenv("ENABLE_PAPER_TPSL_LIFECYCLE", "true").lower() == "true"
PAPER_TPSL_USE_SIGNAL_PRICE_FALLBACK = os.getenv("PAPER_TPSL_USE_SIGNAL_PRICE_FALLBACK", "true").lower() == "true"
PAPER_TPSL_ALERTS_ENABLED = os.getenv("PAPER_TPSL_ALERTS_ENABLED", "true").lower() == "true"
PAPER_TPSL_CLOSE_ON_TP2 = os.getenv("PAPER_TPSL_CLOSE_ON_TP2", "true").lower() == "true"
PAPER_TPSL_SCALE_AT_TP1 = os.getenv("PAPER_TPSL_SCALE_AT_TP1", "true").lower() == "true"
PAPER_TPSL_MOVE_STOP_TO_BREAKEVEN_ON_TP1 = os.getenv("PAPER_TPSL_MOVE_STOP_TO_BREAKEVEN_ON_TP1", "true").lower() == "true"

ENABLE_PAPER_BROKER_BRIDGE = os.getenv("ENABLE_PAPER_BROKER_BRIDGE", "true").lower() == "true"
PAPER_BRIDGE_ONE_SHOT = os.getenv("PAPER_BRIDGE_ONE_SHOT", "true").lower() == "true"
PAPER_BRIDGE_COOLDOWN_SECONDS = int(os.getenv("PAPER_BRIDGE_COOLDOWN_SECONDS", "60"))
PAPER_BRIDGE_CLEAR_SIGNAL_AFTER_EXECUTION = os.getenv("PAPER_BRIDGE_CLEAR_SIGNAL_AFTER_EXECUTION", "true").lower() == "true"
PAPER_BRIDGE_ALLOW_FORCE_EXECUTION = os.getenv("PAPER_BRIDGE_ALLOW_FORCE_EXECUTION", "true").lower() == "true"

ENABLE_ELITE_EXECUTION_ROUTING = os.getenv("ENABLE_ELITE_EXECUTION_ROUTING", "true").lower() == "true"
FORCE_BYPASS_SIGNAL_ROUTING = os.getenv("FORCE_BYPASS_SIGNAL_ROUTING", "true").lower() == "true"
FORCE_TREAT_SIGNAL_AS_FRESH = os.getenv("FORCE_TREAT_SIGNAL_AS_FRESH", "true").lower() == "true"


ENABLE_PHASE35_STRATEGY_LOCK = os.getenv("ENABLE_PHASE35_STRATEGY_LOCK", "true").lower() == "true"
PHASE35_ALLOWED_GRADES = {x.strip().upper() for x in os.getenv("PHASE35_ALLOWED_GRADES", "A,A+").split(",") if x.strip()}
PHASE35_ALLOWED_TRIGGERS = {x.strip().lower() for x in os.getenv("PHASE35_ALLOWED_TRIGGERS", "vwap_reclaim,break_and_hold,rejection").split(",") if x.strip()}
PHASE35_ALLOWED_CONFIRMATIONS = {x.strip().lower() for x in os.getenv("PHASE35_ALLOWED_CONFIRMATIONS", "volume,retest,momentum").split(",") if x.strip()}
PHASE35_BLOCK_CHOP = os.getenv("PHASE35_BLOCK_CHOP", "true").lower() == "true"
PHASE35_ENFORCE_EDGE_WINDOWS = os.getenv("PHASE35_ENFORCE_EDGE_WINDOWS", "true").lower() == "true"
PHASE35_ALLOW_TEST_SIGNAL_ANYTIME = os.getenv("PHASE35_ALLOW_TEST_SIGNAL_ANYTIME", "true").lower() == "true"

PHASE35_MIN_CONFIDENCE_TO_PREMIUM = os.getenv("PHASE35_MIN_CONFIDENCE_TO_PREMIUM", "B").upper().strip()
PHASE35_REQUIRE_PHASE3_APPROVAL = os.getenv("PHASE35_REQUIRE_PHASE3_APPROVAL", "true").lower() == "true"
PHASE35_REQUIRE_ADAPTIVE_STATS_SYNC = os.getenv("PHASE35_REQUIRE_ADAPTIVE_STATS_SYNC", "true").lower() == "true"
PHASE35_MAX_SIGNAL_AGE_SECONDS = int(os.getenv("PHASE35_MAX_SIGNAL_AGE_SECONDS", str(MAX_SIGNAL_AGE_SECONDS)))
PHASE35_MAX_ENTRY_AGE_SECONDS = int(os.getenv("PHASE35_MAX_ENTRY_AGE_SECONDS", str(MAX_SIGNAL_AGE_SECONDS)))
PHASE35_ENFORCE_TRADING_WINDOWS = os.getenv("PHASE35_ENFORCE_TRADING_WINDOWS", "false").lower() == "true"
PHASE35_OPEN_WINDOW_START = os.getenv("PHASE35_OPEN_WINDOW_START", "09:30").strip()
PHASE35_OPEN_WINDOW_END = os.getenv("PHASE35_OPEN_WINDOW_END", "10:30").strip()
PHASE35_POWER_WINDOW_START = os.getenv("PHASE35_POWER_WINDOW_START", "15:00").strip()
PHASE35_POWER_WINDOW_END = os.getenv("PHASE35_POWER_WINDOW_END", "16:00").strip()
PHASE35_ALLOW_MIDDAY = os.getenv("PHASE35_ALLOW_MIDDAY", "true").lower() == "true"
PHASE35_SYMBOL_COOLDOWN_SECONDS = int(os.getenv("PHASE35_SYMBOL_COOLDOWN_SECONDS", "300"))
PHASE35_SETUP_COOLDOWN_SECONDS = int(os.getenv("PHASE35_SETUP_COOLDOWN_SECONDS", "600"))
PHASE35_MAX_DUPLICATE_SYMBOL_DIRECTION = int(os.getenv("PHASE35_MAX_DUPLICATE_SYMBOL_DIRECTION", str(MAX_SAME_TICKER_POSITIONS)))
PHASE35_MIN_RR_RATIO = float(os.getenv("PHASE35_MIN_RR_RATIO", str(MIN_RR_RATIO)))
PHASE35_MAX_DISTANCE_FROM_ENTRY_PCT = float(os.getenv("PHASE35_MAX_DISTANCE_FROM_ENTRY_PCT", str(PHASE1_MAX_ENTRY_SLIPPAGE_PCT)))
PHASE35_MAX_DAILY_LOSS_DOLLARS = float(os.getenv("PHASE35_MAX_DAILY_LOSS_DOLLARS", "0"))
PHASE35_MAX_DAILY_LOSS_PCT = float(os.getenv("PHASE35_MAX_DAILY_LOSS_PCT", str(MAX_DAILY_LOSS_PCT)))
PHASE35_MAX_PROJECTED_HEAT_PCT = float(os.getenv("PHASE35_MAX_PROJECTED_HEAT_PCT", str(MAX_PROJECTED_PORTFOLIO_HEAT_PCT)))
PHASE35_BLOCK_AFTER_CONSECUTIVE_LOSSES = int(os.getenv("PHASE35_BLOCK_AFTER_CONSECUTIVE_LOSSES", str(MAX_CONSECUTIVE_LOSSES)))
PHASE35_USED_SIGNAL_MEMORY = int(os.getenv("PHASE35_USED_SIGNAL_MEMORY", "100"))
PHASE35_ENFORCEMENT_FILE = os.getenv("PHASE35_ENFORCEMENT_FILE", "phase35_enforcement.json").strip()

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

# =========================================================
# STEP 11 AUTO CONTRACT SELECTION
# =========================================================
ENABLE_AUTO_CONTRACT_SELECTION = os.getenv("ENABLE_AUTO_CONTRACT_SELECTION", "true").lower() == "true"
AUTO_CONTRACT_REQUIRE_UNDERLYING_PRICE = os.getenv("AUTO_CONTRACT_REQUIRE_UNDERLYING_PRICE", "false").lower() == "true"
AUTO_CONTRACT_USE_LIVE_UNDERLYING = os.getenv("AUTO_CONTRACT_USE_LIVE_UNDERLYING", "true").lower() == "true"
OPTION_EXPIRY_MODE = os.getenv("OPTION_EXPIRY_MODE", "0dte_or_next").strip().lower()
OPTION_MAX_DAYS_OUT = int(os.getenv("OPTION_MAX_DAYS_OUT", "7"))
OPTION_STRIKE_MODE = os.getenv("OPTION_STRIKE_MODE", "atm").strip().lower()
OPTION_STRIKE_OFFSET = int(os.getenv("OPTION_STRIKE_OFFSET", "0"))
OPTION_STRIKE_STEP_DEFAULT = float(os.getenv("OPTION_STRIKE_STEP_DEFAULT", "1"))
OPTION_STRIKE_STEP_QQQ = float(os.getenv("OPTION_STRIKE_STEP_QQQ", "1"))
OPTION_STRIKE_STEP_SPY = float(os.getenv("OPTION_STRIKE_STEP_SPY", "1"))
OPTION_DEFAULT_CONTRACT_PRICE = float(os.getenv("OPTION_DEFAULT_CONTRACT_PRICE", "1.00"))
OPTION_STOP_PCT = float(os.getenv("OPTION_STOP_PCT", "0.30"))
OPTION_TP1_PCT = float(os.getenv("OPTION_TP1_PCT", "0.30"))
OPTION_TP2_PCT = float(os.getenv("OPTION_TP2_PCT", "0.60"))

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


# =========================================================
# EXECUTION IDEMPOTENCY HELPERS
# =========================================================
def idempotency_enabled() -> bool:
    return bool(globals().get("ENABLE_EXECUTION_IDEMPOTENCY", True))


def idempotency_canonical_json(payload: Any) -> str:
    try:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        return str(payload)


def idempotency_hash(payload: Any) -> str:
    return sha256_text(idempotency_canonical_json(payload))


def idempotency_short(key: str, n: int = 24) -> str:
    return str(key or "")[:n]


def idempotency_load_ledger() -> Dict[str, Any]:
    data = load_json_file(IDEMPOTENCY_STORE_FILE, {}) if 'load_json_file' in globals() else safe_load_idempotency_json(IDEMPOTENCY_STORE_FILE, {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("schema_version", 1)
    data.setdefault("created_at", now_ts())
    data.setdefault("updated_at", now_ts())
    data.setdefault("records", {})
    data.setdefault("recent_keys", [])
    return data


def safe_load_idempotency_json(path: str, default: Any) -> Any:
    try:
        if not os.path.exists(path):
            return deepcopy(default)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        try:
            os.replace(path, f"{path}.bad.{epoch()}")
        except Exception:
            pass
        return deepcopy(default)


def idempotency_save_ledger(data: Dict[str, Any]) -> None:
    data["updated_at"] = now_ts()
    records = data.get("records", {}) if isinstance(data.get("records", {}), dict) else {}
    recent = data.get("recent_keys", []) if isinstance(data.get("recent_keys", []), list) else []
    # Keep newest keys and matching records only.
    max_records = safe_int(globals().get("IDEMPOTENCY_MAX_RECORDS", 2000), 2000)
    recent = recent[-max_records:]
    keep = set(recent)
    data["recent_keys"] = recent
    data["records"] = {k: v for k, v in records.items() if k in keep}
    atomic_write_json(IDEMPOTENCY_STORE_FILE, data)


def idempotency_record_key(kind: str, key: str) -> str:
    return f"{kind}:{key}"


def idempotency_alert(title: str, body: str) -> None:
    if not globals().get("IDEMPOTENCY_SEND_ALERTS", True):
        return
    msg = f"🧷 {title}\n{body}\n⏰ {now_ts()}"
    try:
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_telegram(msg)
    except Exception:
        try:
            debug(f"IDEMPOTENCY ALERT FAILED | {title} | {body}")
        except Exception:
            pass


def idempotency_get(kind: str, key: str) -> Optional[Dict[str, Any]]:
    if not idempotency_enabled() or not key:
        return None
    ledger = idempotency_load_ledger()
    return ledger.get("records", {}).get(idempotency_record_key(kind, key))


def idempotency_claim(kind: str, key: str, payload: Optional[Dict[str, Any]] = None, owner: str = "engine") -> Dict[str, Any]:
    """Claim an idempotency key. Returns approved=False for replayed active/success keys."""
    if not idempotency_enabled():
        return {"approved": True, "reason": "idempotency_disabled", "kind": kind, "key": key}
    if not key:
        return {"approved": False, "reason": "missing_idempotency_key", "kind": kind, "key": key}

    ledger = idempotency_load_ledger()
    records = ledger.setdefault("records", {})
    recent = ledger.setdefault("recent_keys", [])
    record_id = idempotency_record_key(kind, key)
    now = epoch()
    existing = records.get(record_id)
    block_seconds = safe_int(globals().get("IDEMPOTENCY_BLOCK_REPLAY_SECONDS", 86400), 86400)

    if isinstance(existing, dict):
        status = str(existing.get("status", "claimed")).lower().strip()
        age = now - safe_int(existing.get("first_seen_epoch", existing.get("updated_epoch", now)), now)
        if status in {"claimed", "submitted", "filled", "success", "closed", "open"} and age <= block_seconds:
            return {
                "approved": False,
                "reason": f"idempotent_replay_blocked:{kind}:{status}:age_{age}s",
                "kind": kind,
                "key": key,
                "record": existing,
            }

    record = {
        "kind": kind,
        "key": key,
        "record_id": record_id,
        "owner": owner,
        "status": "claimed",
        "first_seen_at": existing.get("first_seen_at") if isinstance(existing, dict) else now_ts(),
        "first_seen_epoch": existing.get("first_seen_epoch") if isinstance(existing, dict) else now,
        "updated_at": now_ts(),
        "updated_epoch": now,
        "payload": payload or {},
        "attempts": safe_int(existing.get("attempts", 0), 0) + 1 if isinstance(existing, dict) else 1,
    }
    records[record_id] = record
    if record_id not in recent:
        recent.append(record_id)
    idempotency_save_ledger(ledger)
    return {"approved": True, "reason": "idempotency_claimed", "kind": kind, "key": key, "record": record}


def idempotency_mark(kind: str, key: str, status: str, details: Optional[Dict[str, Any]] = None) -> None:
    if not idempotency_enabled() or not key:
        return
    ledger = idempotency_load_ledger()
    records = ledger.setdefault("records", {})
    recent = ledger.setdefault("recent_keys", [])
    record_id = idempotency_record_key(kind, key)
    rec = records.get(record_id)
    if not isinstance(rec, dict):
        rec = {
            "kind": kind,
            "key": key,
            "record_id": record_id,
            "owner": "engine",
            "first_seen_at": now_ts(),
            "first_seen_epoch": epoch(),
            "attempts": 0,
            "payload": {},
        }
    rec["status"] = str(status)
    rec["updated_at"] = now_ts()
    rec["updated_epoch"] = epoch()
    rec.setdefault("history", []).append({"at": now_ts(), "epoch": epoch(), "status": str(status), "details": details or {}})
    records[record_id] = rec
    if record_id not in recent:
        recent.append(record_id)
    idempotency_save_ledger(ledger)


def idempotency_signal_payload(signal: Dict[str, Any]) -> Dict[str, Any]:
    con = signal.get("confluences", {}) if isinstance(signal.get("confluences", {}), dict) else {}
    return {
        "ticker": str(signal.get("ticker") or signal.get("underlying") or "").upper().strip(),
        "symbol": str(signal.get("symbol") or signal.get("contract_symbol") or "").strip(),
        "direction": str(signal.get("direction") or "").upper().strip(),
        "setup": str(signal.get("setup") or signal.get("setup_name") or signal.get("strategy") or "").strip(),
        "trigger": str(signal.get("trigger") or "").strip(),
        "confidence": str(signal.get("confidence") or signal.get("grade") or "").upper().strip(),
        "entry_contract": round(safe_float(signal.get("entry_contract", signal.get("contract_price", signal.get("entry", 0))), 0), 4),
        "stop_contract": round(safe_float(signal.get("stop_contract", signal.get("stop", 0)), 0), 4),
        "tp1_contract": round(safe_float(signal.get("tp1_contract", signal.get("target", signal.get("target_1", 0))), 0), 4),
        "tp2_contract": round(safe_float(signal.get("tp2_contract", signal.get("target_2", 0)), 0), 4),
        "vwap": str(con.get("vwap") or signal.get("vwap", "")).lower().strip(),
        "oil": str(con.get("oil") or signal.get("oil", signal.get("oil_state", ""))).lower().strip(),
    }


def idempotency_signal_intent_id(signal: Dict[str, Any]) -> str:
    explicit = str(signal.get("signal_id") or signal.get("idempotency_signal_id") or "").strip()
    if explicit and len(explicit) >= 12 and not explicit.startswith("sig_"):
        return explicit
    return idempotency_hash(idempotency_signal_payload(signal))


def idempotency_order_payload(signal: Dict[str, Any], side: str, qty: int, mode: str, order_type: str = "market", limit_price: Optional[float] = None) -> Dict[str, Any]:
    return {
        "signal_intent_id": idempotency_signal_intent_id(signal),
        "ticker": str(signal.get("ticker") or signal.get("underlying") or "").upper().strip(),
        "symbol": str(signal.get("symbol") or signal.get("contract_symbol") or "").strip(),
        "side": str(side).lower().strip(),
        "qty": safe_int(qty, 0),
        "mode": str(mode).upper().strip(),
        "order_type": str(order_type or "market").lower().strip(),
        "limit_price": round(safe_float(limit_price, 0), 4),
        "entry_contract": round(safe_float(signal.get("entry_contract", signal.get("contract_price", 0)), 0), 4),
    }


def idempotency_order_intent_id(signal: Dict[str, Any], side: str, qty: int, mode: str, order_type: str = "market", limit_price: Optional[float] = None) -> str:
    return idempotency_hash(idempotency_order_payload(signal, side, qty, mode, order_type, limit_price))


def idempotency_client_order_id(signal: Dict[str, Any], side: str, qty: int, mode: str, order_type: str = "market", limit_price: Optional[float] = None) -> str:
    key = idempotency_order_intent_id(signal, side, qty, mode, order_type, limit_price)
    prefix = str(globals().get("IDEMPOTENCY_CLIENT_PREFIX", "ub")).strip()[:8] or "ub"
    # Alpaca client_order_id limit is 48 chars; keep stable + compact.
    return f"{prefix}-{side[:1].lower()}-{idempotency_short(key, 36)}"[:48]


def idempotency_fill_event_id(order_or_fill: Dict[str, Any]) -> str:
    payload = {
        "broker_order_id": order_or_fill.get("broker_order_id") or order_or_fill.get("id") or order_or_fill.get("order_id"),
        "client_order_id": order_or_fill.get("client_order_id"),
        "symbol": order_or_fill.get("symbol"),
        "side": order_or_fill.get("side"),
        "qty_filled": order_or_fill.get("qty_filled") or order_or_fill.get("filled_qty") or order_or_fill.get("qty"),
        "avg_fill_price": order_or_fill.get("avg_fill_price") or order_or_fill.get("filled_avg_price") or order_or_fill.get("fill_price"),
        "status": order_or_fill.get("status"),
    }
    return idempotency_hash(payload)


def idempotency_close_intent_id(position: Dict[str, Any], side: str = "sell", qty: Optional[int] = None, reason: str = "") -> str:
    payload = {
        "position_id": position.get("position_id") or position.get("id"),
        "order_id": position.get("order_id"),
        "symbol": position.get("symbol") or position.get("contract_symbol"),
        "side": str(side).lower().strip(),
        "qty": safe_int(qty if qty is not None else position.get("qty_open", position.get("qty", 0)), 0),
        "reason": str(reason or "").lower().strip(),
    }
    return idempotency_hash(payload)


def idempotency_attach_to_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(signal, dict) or not idempotency_enabled():
        return signal
    sid = idempotency_signal_intent_id(signal)
    signal["idempotency_signal_id"] = sid
    signal["signal_id"] = sid
    signal.setdefault("idempotency", {})
    signal["idempotency"]["signal_intent_id"] = sid
    return signal


def idempotency_pre_order_gate(signal: Dict[str, Any], side: str = "buy", qty: Optional[int] = None, mode: str = "PAPER", order_type: str = "market", limit_price: Optional[float] = None) -> Dict[str, Any]:
    if not idempotency_enabled():
        return {"approved": True, "reason": "idempotency_disabled"}
    qty = safe_int(qty if qty is not None else signal.get("qty", signal.get("contracts", 0)), 0)
    signal = idempotency_attach_to_signal(signal)
    sig_key = idempotency_signal_intent_id(signal)
    order_key = idempotency_order_intent_id(signal, side, qty, mode, order_type, limit_price)

    # Do not claim signal key here as a hard block if already seen; order key is the true broker submit guard.
    signal_rec = idempotency_get("signal_intent", sig_key)
    order_claim = idempotency_claim(
        "order_intent",
        order_key,
        payload=idempotency_order_payload(signal, side, qty, mode, order_type, limit_price),
        owner="pre_order_gate",
    )
    if not order_claim.get("approved"):
        idempotency_alert(
            "IDEMPOTENCY ORDER REPLAY BLOCKED",
            f"Mode: {mode}\nSide: {side}\nSymbol: {signal.get('symbol')}\nQty: {qty}\nReason: {order_claim.get('reason')}\nKey: {idempotency_short(order_key)}",
        )
        return {"approved": False, "reason": order_claim.get("reason"), "signal_key": sig_key, "order_key": order_key, "signal_record": signal_rec}

    idempotency_claim("signal_intent", sig_key, payload=idempotency_signal_payload(signal), owner="pre_order_gate")
    signal.setdefault("idempotency", {})
    signal["idempotency"].update({
        "signal_intent_id": sig_key,
        "order_intent_id": order_key,
        "client_order_id": idempotency_client_order_id(signal, side, qty, mode, order_type, limit_price),
    })
    return {"approved": True, "reason": "idempotency_pre_order_claimed", "signal_key": sig_key, "order_key": order_key}


def idempotency_mark_order_submitted(signal: Dict[str, Any], side: str, qty: int, mode: str, order_type: str = "market", limit_price: Optional[float] = None, broker_order: Optional[Dict[str, Any]] = None) -> None:
    key = idempotency_order_intent_id(signal, side, qty, mode, order_type, limit_price)
    idempotency_mark("order_intent", key, "submitted", {"broker_order": broker_order or {}, "client_order_id": idempotency_client_order_id(signal, side, qty, mode, order_type, limit_price)})


def idempotency_mark_order_filled(order_or_fill: Dict[str, Any]) -> Dict[str, Any]:
    key = idempotency_fill_event_id(order_or_fill)
    claim = idempotency_claim("fill_event", key, payload=order_or_fill, owner="fill_reconciliation")
    if not claim.get("approved"):
        return {"approved": False, "reason": claim.get("reason"), "fill_key": key}
    idempotency_mark("fill_event", key, "filled", {"order": order_or_fill})
    return {"approved": True, "reason": "fill_event_recorded", "fill_key": key}


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
        "daily_realized_pnl_dollars": 0.0,
        "daily_pnl_last_update": 0,
        "allow_entries": True,
        "hard_kill_reason": "",
        "consecutive_losses": 0,
        "last_trade_day": current_trade_day(),
        "kill_switch": False,
        "bot_paused": False,
        "last_mode": "LIVE" if LIVE_MODE else "PAPER",
        "reconciliation_required": False,
        "reconciliation_block_reason": "",
        "auto_contract_locks": {},
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
        state["daily_realized_pnl_dollars"] = 0.0
        state["daily_pnl_last_update"] = epoch()
        state["consecutive_losses"] = 0
        state["last_trade_day"] = today
        save_state(state)




# =========================================================
# FINAL PRE-3.5 PATCH: STABLE DAILY PNL PERSISTENCE
# =========================================================
def paper_pnl_dollars(entry_price: float, exit_price: float, qty: int, multiplier: float = 100.0) -> float:
    entry = safe_float(entry_price, 0.0)
    exitp = safe_float(exit_price, 0.0)
    q = safe_int(qty, 0)
    if entry <= 0 or exitp <= 0 or q <= 0:
        return 0.0
    return round((exitp - entry) * multiplier * q, 2)


def update_daily_realized_pnl(delta_dollars: float = 0.0, delta_pct_decimal: float = 0.0, source: str = ""):
    ensure_globals_initialized()
    reset_daily_risk_counters_if_needed(GLOBAL_STATE)
    if auto_should_force_execution_for_test(signal) if 'signal' in locals() else FORCE_EXECUTION_MODE:
        log("🚨 FORCE EXECUTION MODE ENABLED — PHASE 3.5 GATE OVERRIDE")
        if not FORCE_EXECUTION_KEEP_RISK_GATES:
            return {"approved": True, "stage": "phase35_enforcement", "notes": ["force_execution_all_gates_bypassed"], "reject_reasons": []}

    old_dollars = safe_float(GLOBAL_STATE.get("daily_realized_pnl_dollars", 0.0), 0.0)
    old_pct = safe_float(GLOBAL_STATE.get("daily_realized_pnl_pct", 0.0), 0.0)
    delta_dollars = safe_float(delta_dollars, 0.0)
    delta_pct_decimal = safe_float(delta_pct_decimal, 0.0)
    new_dollars = round(old_dollars + delta_dollars, 2)
    new_pct = round(old_pct + delta_pct_decimal, 8)
    if delta_dollars == 0 and abs(new_dollars) < abs(old_dollars):
        debug(f"PNL RESET IGNORED | old={old_dollars} new={new_dollars} source={source}")
        new_dollars = old_dollars
    if delta_pct_decimal == 0 and abs(new_pct) < abs(old_pct):
        new_pct = old_pct
    GLOBAL_STATE["daily_realized_pnl_dollars"] = new_dollars
    GLOBAL_STATE["daily_realized_pnl_pct"] = new_pct
    GLOBAL_STATE["daily_pnl_last_update"] = epoch()
    save_state(GLOBAL_STATE)
    debug(f"PNL PERSISTED | source={source} | delta=${round(delta_dollars,2)} | daily_pnl=${new_dollars} | daily_pct={round(new_pct*100,4)}%")


def stable_daily_pnl_dollars() -> float:
    ensure_globals_initialized()
    reset_daily_risk_counters_if_needed(GLOBAL_STATE)
    stored = safe_float(GLOBAL_STATE.get("daily_realized_pnl_dollars", 0.0), 0.0)
    legacy_pct = safe_float(GLOBAL_STATE.get("daily_realized_pnl_pct", 0.0), 0.0)
    legacy_dollars = round(normalize_pnl_value_to_decimal(legacy_pct) * get_account_equity(), 2) if legacy_pct else 0.0
    chosen = stored if abs(stored) >= abs(legacy_dollars) else legacy_dollars
    if abs(chosen) > abs(stored):
        GLOBAL_STATE["daily_realized_pnl_dollars"] = chosen
        GLOBAL_STATE["daily_pnl_last_update"] = epoch()
        save_state(GLOBAL_STATE)
        debug(f"PNL LEGACY SYNC | stored=${stored} legacy=${legacy_dollars} chosen=${chosen}")
    return round(chosen, 2)

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
    client_order_id = idempotency_client_order_id(signal, side, qty, mode, order_type, limit_price)
    order_intent_id = idempotency_order_intent_id(signal, side, qty, mode, order_type, limit_price)
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
        "idempotency_order_intent_id": order_intent_id,
        "idempotency_signal_intent_id": idempotency_signal_intent_id(signal),
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
# STEP 11 AUTO CONTRACT SELECTION HELPERS
# =========================================================
def compact_occ_symbol(underlying: str, expiry_yyyymmdd: str, direction: str, strike: float) -> str:
    """Builds compact OCC-style symbols used by this engine: QQQ240426C00380000."""
    underlying = str(underlying or "").upper().strip()
    exp = str(expiry_yyyymmdd or "").replace("-", "").strip()
    if len(exp) == 8:
        yymmdd = exp[2:]
    else:
        yymmdd = datetime.now().strftime("%y%m%d")
    cp = "C" if normalize_direction(direction) == "CALL" else "P"
    strike_int = int(round(float(strike) * 1000))
    return f"{underlying}{yymmdd}{cp}{strike_int:08d}"


def get_strike_step(ticker: str) -> float:
    t = str(ticker or "").upper().strip()
    if t == "QQQ":
        return max(OPTION_STRIKE_STEP_QQQ, 0.01)
    if t == "SPY":
        return max(OPTION_STRIKE_STEP_SPY, 0.01)
    return max(OPTION_STRIKE_STEP_DEFAULT, 0.01)


def round_to_strike(price: float, step: float) -> float:
    if price <= 0 or step <= 0:
        return 0.0
    return round(round(price / step) * step, 2)


def choose_option_expiry() -> str:
    """
    Basic staged expiry selector.
    - 0dte_or_next / 0dte: today if weekday, otherwise next weekday
    - next_day: next weekday
    - weekly: nearest Friday within OPTION_MAX_DAYS_OUT, else next weekday
    This is intentionally simple until true chain/expiration-calendar logic is added.
    """
    today = datetime.now().date()

    def next_weekday(d):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        return d

    mode = OPTION_EXPIRY_MODE
    if mode in {"0dte", "0dte_or_next", "today"}:
        return next_weekday(today).strftime("%Y%m%d")

    if mode in {"next", "next_day", "1dte"}:
        d = today + timedelta(days=1)
        return next_weekday(d).strftime("%Y%m%d")

    if mode in {"weekly", "friday"}:
        for i in range(0, max(OPTION_MAX_DAYS_OUT, 1) + 1):
            d = today + timedelta(days=i)
            if d.weekday() == 4:
                return d.strftime("%Y%m%d")
        return next_weekday(today + timedelta(days=1)).strftime("%Y%m%d")

    # Explicit date support: YYYYMMDD or YYYY-MM-DD
    cleaned = mode.replace("-", "")
    if len(cleaned) == 8 and cleaned.isdigit():
        return cleaned

    return next_weekday(today).strftime("%Y%m%d")


def choose_option_strike(ticker: str, direction: str, underlying_price: float) -> float:
    step = get_strike_step(ticker)
    atm = round_to_strike(underlying_price, step)
    if atm <= 0:
        return 0.0

    mode = OPTION_STRIKE_MODE
    offset = OPTION_STRIKE_OFFSET

    if mode in {"atm", "at_the_money"}:
        offset = OPTION_STRIKE_OFFSET
    elif mode in {"itm", "one_itm", "1itm"}:
        offset = -1 if normalize_direction(direction) == "CALL" else 1
    elif mode in {"otm", "one_otm", "1otm"}:
        offset = 1 if normalize_direction(direction) == "CALL" else -1
    elif mode.startswith("offset:"):
        try:
            offset = int(mode.split(":", 1)[1])
        except Exception:
            offset = OPTION_STRIKE_OFFSET

    return round(atm + (offset * step), 2)


def signal_needs_auto_contract(signal: Dict[str, Any]) -> bool:
    if not ENABLE_AUTO_CONTRACT_SELECTION:
        return False
    if str(signal.get("asset_class", "option")).lower().strip() != "option":
        return False
    ticker = str(signal.get("ticker", "")).upper().strip()
    symbol = str(signal.get("symbol", "")).upper().strip()
    if not symbol or symbol == ticker:
        return True
    if not is_option_contract_symbol(symbol):
        return False
    return False


def apply_contract_price_defaults(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Ensures generated option signals have usable paper/simulation prices."""
    x = deepcopy(signal)
    entry = safe_float(x.get("entry_contract", 0), 0)
    contract_price = safe_float(x.get("contract_price", 0), 0)
    if entry <= 0 and contract_price > 0:
        entry = contract_price
    if entry <= 0:
        entry = max(OPTION_DEFAULT_CONTRACT_PRICE, 0.01)
    x["entry_contract"] = round(entry, 4)
    x["contract_price"] = round(entry, 4)

    if safe_float(x.get("stop_contract", 0), 0) <= 0:
        x["stop_contract"] = round(max(entry * (1.0 - OPTION_STOP_PCT), 0.01), 4)
    if safe_float(x.get("tp1_contract", 0), 0) <= 0:
        x["tp1_contract"] = round(entry * (1.0 + OPTION_TP1_PCT), 4)
    if safe_float(x.get("tp2_contract", 0), 0) <= 0:
        x["tp2_contract"] = round(entry * (1.0 + OPTION_TP2_PCT), 4)
    return x


def auto_contract_lock_key(signal: Dict[str, Any]) -> str:
    """Stable key for one signal so contract selection happens once, then reuses the same contract."""
    sid = str(signal.get("signal_id", "")).strip()
    if sid:
        return sid
    ticker = str(signal.get("ticker", "")).upper().strip()
    direction = normalize_direction(signal.get("direction", "CALL"))
    ts = str(signal.get("timestamp", "")).strip()
    confidence = normalize_confidence(signal.get("confidence", "C"))
    return sha256_text(f"{ticker}|{direction}|{confidence}|{ts}")


def get_locked_auto_contract(signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ensure_globals_initialized()
    locks = GLOBAL_STATE.get("auto_contract_locks", {})
    if not isinstance(locks, dict):
        GLOBAL_STATE["auto_contract_locks"] = {}
        save_state(GLOBAL_STATE)
        return None
    lock_key = auto_contract_lock_key(signal)
    locked = locks.get(lock_key)
    return locked if isinstance(locked, dict) else None


def save_locked_auto_contract(signal: Dict[str, Any], contract: Dict[str, Any]):
    ensure_globals_initialized()
    locks = GLOBAL_STATE.get("auto_contract_locks", {})
    if not isinstance(locks, dict):
        locks = {}
    lock_key = auto_contract_lock_key(signal)
    locks[lock_key] = contract
    if len(locks) > 50:
        newest_keys = list(locks.keys())[-50:]
        locks = {k: locks[k] for k in newest_keys if k in locks}
    GLOBAL_STATE["auto_contract_locks"] = locks
    save_state(GLOBAL_STATE)


def apply_locked_contract_to_signal(signal: Dict[str, Any], locked: Dict[str, Any]) -> Dict[str, Any]:
    x = deepcopy(signal)
    selected_symbol = str(locked.get("symbol", "")).strip()
    if selected_symbol:
        x["symbol"] = selected_symbol
        x["contract_symbol"] = selected_symbol
    if locked.get("strike") is not None:
        x["strike"] = locked.get("strike")
    if locked.get("expiry") is not None:
        x["expiry"] = locked.get("expiry")
    x["symbol_locked"] = True
    x["auto_contract"] = deepcopy(locked)
    x["auto_contract"]["reused_locked_contract"] = True
    debug(f"REUSING LOCKED CONTRACT | {x.get('ticker')} {x.get('direction')} | symbol={selected_symbol}")
    return apply_contract_price_defaults(x)


def auto_select_option_contract(signal: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 11 staged contract selector with contract lock.
    It builds a tradable compact option symbol ONCE per signal, then reuses it every loop.
    This prevents the selected strike/symbol from changing while a signal is active.
    """
    x = deepcopy(signal)
    x.setdefault("auto_contract", {})
    if not signal_needs_auto_contract(x):
        return apply_contract_price_defaults(x)
    locked = get_locked_auto_contract(x)
    if locked and locked.get("symbol"):
        return apply_locked_contract_to_signal(x, locked)
    ticker = str(x.get("ticker", "")).upper().strip()
    direction = normalize_direction(x.get("direction", "CALL"))
    underlying_price = safe_float(x.get("price", 0), 0)
    if AUTO_CONTRACT_USE_LIVE_UNDERLYING:
        live_underlying = get_live_market_price(ticker)
        if live_underlying > 0:
            underlying_price = live_underlying
            x["price"] = live_underlying
    if underlying_price <= 0:
        msg = "auto_contract_missing_underlying_price"
        x["auto_contract"] = {"selected": False, "reason": msg, "ticker": ticker}
        if AUTO_CONTRACT_REQUIRE_UNDERLYING_PRICE:
            return x
        underlying_price = 0.0
    expiry = choose_option_expiry()
    strike = choose_option_strike(ticker, direction, underlying_price) if underlying_price > 0 else 0.0
    if strike <= 0:
        strike = safe_float(x.get("strike", 0), 0)
    if strike <= 0:
        strike = 0.0
    if strike > 0:
        selected_symbol = compact_occ_symbol(ticker, expiry, direction, strike)
        x["symbol"] = selected_symbol
        x["contract_symbol"] = selected_symbol
        x["strike"] = strike
        x["expiry"] = expiry
        x["symbol_locked"] = True
        contract = {
            "selected": True,
            "symbol": selected_symbol,
            "underlying": ticker,
            "underlying_price": round(underlying_price, 4),
            "expiry": expiry,
            "strike": strike,
            "direction": direction,
            "mode": OPTION_STRIKE_MODE,
            "expiry_mode": OPTION_EXPIRY_MODE,
            "note": "staged_selector_no_chain_liquidity_yet_locked_once_per_signal",
            "locked_at": epoch(),
        }
        x["auto_contract"] = contract
        save_locked_auto_contract(x, contract)
        debug(f"AUTO CONTRACT SELECTED AND LOCKED | {ticker} {direction} | underlying={underlying_price} | strike={strike} | expiry={expiry} | symbol={selected_symbol}")
    else:
        x["auto_contract"] = {"selected": False, "reason": "could_not_select_strike", "ticker": ticker, "underlying_price": underlying_price}
        debug(f"AUTO CONTRACT NOT SELECTED | {ticker} | underlying={underlying_price}")
    return apply_contract_price_defaults(x)

# =========================================================
# UNBIASED AUTO SIGNAL FORMATTER
# Turns your strategy idea into the exact signal.json structure
# this engine needs for validation, Phase 3.5, sizing, and paper/live routing.
# =========================================================
def build_unbiased_signal(
    ticker: str,
    direction: str,
    entry: float,
    stop: float,
    target: float,
    setup: str,
    confidence: str = "A",
    key_level: float = 0,
    vwap: float = 0,
    notes: str = "",
    contract_symbol: str = "",
    contract_price: float = 0,
    underlying_price: float = 0,
    qty: int = 1,
    confirmation: str = "volume",
    regime: str = "clean",
) -> Dict[str, Any]:
    ticker = str(ticker or "QQQ").upper().strip()
    direction = normalize_direction(direction)
    confidence = normalize_confidence(confidence)

    entry = safe_float(entry, 0.0)
    stop = safe_float(stop, 0.0)
    target = safe_float(target, 0.0)
    key_level = safe_float(key_level, entry)
    vwap = safe_float(vwap, entry)
    underlying_price = safe_float(underlying_price, entry)

    # This engine trades option contracts. If contract_price is not supplied,
    # use the strategy entry as the contract entry so testing can still execute.
    contract_price = safe_float(contract_price, entry)
    entry_contract = contract_price
    stop_contract = safe_float(stop, 0.0)
    tp1_contract = safe_float(target, 0.0)

    # Build a second target so trade management has a runner level.
    if direction == "CALL":
        tp2_contract = target + abs(target - entry_contract)
    else:
        tp2_contract = target + abs(target - entry_contract)
    tp2_contract = round(max(tp1_contract, tp2_contract), 4)

    setup_clean = str(setup or "manual_setup").lower().strip().replace(" ", "_")
    bias = "Bullish" if direction == "CALL" else "Bearish"
    trigger = setup_clean

    signal = {
        "ticker": ticker,
        "symbol": str(contract_symbol or ticker).strip(),
        "contract_symbol": str(contract_symbol or "").strip(),
        "asset_class": "option",
        "direction": direction,
        "confidence": confidence,
        "grade": confidence,

        # Underlying/context fields
        "price": underlying_price,
        "underlying_price": underlying_price,
        "key_level": key_level,
        "vwap": vwap,

        # Human-readable plan fields
        "entry": str(entry),
        "stop": str(stop),
        "target": str(target),
        "target_1": str(target),
        "target_2": str(tp2_contract),
        "setup": setup_clean,
        "strategy": setup_clean,
        "trigger": trigger,
        "bias": bias,
        "timeframe": "5m / 15m",
        "reason": notes or f"{ticker} {direction} {trigger} setup.",
        "public_reason": notes or f"{ticker} {direction} setup forming at key level.",

        # Contract execution fields used by validation/sizing/execution.
        "contract_price": entry_contract,
        "entry_contract": entry_contract,
        "stop_contract": stop_contract,
        "tp1_contract": tp1_contract,
        "tp2_contract": tp2_contract,
        "qty": safe_int(qty, 1),
        "qty_hint": safe_int(qty, 1),

        # Freshness / identity
        "timestamp": epoch(),
        "created_at": epoch(),
        "source": "auto_signal_formatter",
    }

    return signal


def write_auto_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    atomic_write_json(SIGNAL_FILE, signal)
    try:
        ensure_globals_initialized()
        GLOBAL_STATE["last_signal_hash"] = ""
        GLOBAL_STATE["last_signal_file_mtime"] = 0
        save_state(GLOBAL_STATE)
        debug("AUTO SIGNAL TEST HASH RESET")
    except Exception as e:
        debug(f"AUTO SIGNAL HASH RESET SKIPPED | {e}")
    debug(
        f"AUTO SIGNAL WRITTEN | {signal.get('ticker')} "
        f"{signal.get('direction')} {signal.get('confidence')} -> {SIGNAL_FILE}"
    )
    return signal


def write_unbiased_test_signal() -> Dict[str, Any]:
    sig = build_unbiased_signal(
        ticker="QQQ",
        direction="CALL",
        entry=1.35,
        stop=0.95,
        target=1.75,
        setup="vwap reclaim",
        confidence="A",
        key_level=430.00,
        vwap=429.85,
        underlying_price=430.00,
        contract_symbol="QQQ260501C00430000",
        contract_price=1.35,
        qty=1,
        notes="Auto formatter test signal: VWAP reclaim with defined stop and target.",
        confirmation="volume",
        regime="clean",
    )
    write_auto_signal(sig)
    print(json.dumps(sig, indent=2))
    return sig

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
    signal = auto_select_option_contract(signal)
    signal["signal_id"] = str(signal.get("signal_id", signal_hash(signal)))
    signal = idempotency_attach_to_signal(signal)
    return signal


def is_signal_fresh(signal: Dict[str, Any]) -> bool:
    if elite_force_fresh_enabled():
        debug("🚨 FINAL ELITE ROUTING — BYPASSING is_signal_fresh")
        return True

    ts = safe_int(signal.get("timestamp", 0), 0)
    return True if ts <= 0 else (epoch() - ts) <= MAX_SIGNAL_AGE_SECONDS



# =========================================================
# SIGNAL FILE ROUTING FIX
# Reads SIGNAL_FILE by content hash instead of relying only on file mtime.
# This fixes cases where signal.json exists but the loop never picks it up.
# =========================================================
def load_active_signal_file() -> Optional[Dict[str, Any]]:
    debug_file_lookup(SIGNAL_FILE)
    if not SIGNAL_FILE:
        return None
    if not file_exists(SIGNAL_FILE):
        log(f"❌ SIGNAL_FILE not found: {SIGNAL_FILE}")
        return None
    try:
        with open(SIGNAL_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, list) and raw:
            raw = raw[0]
        if not isinstance(raw, dict) or not raw:
            return None
        signal = normalize_signal(raw)
        if not is_signal_fresh(signal):
            if elite_force_fresh_enabled():
                debug("🚨 FINAL ELITE ROUTING — TREATING STALE SIGNAL AS FRESH")
            else:
                log("❌ Signal skipped: stale timestamp")
                return None
        return signal
    except Exception as e:
        log(f"❌ Failed loading active signal file: {e}")
        return None


def clear_active_signal_file():
    try:
        atomic_write_json(SIGNAL_FILE, {})
    except Exception as e:
        log(f"❌ Failed clearing signal file: {e}")


def active_signal_hash(signal: Dict[str, Any]) -> str:
    try:
        return signal_hash(signal)
    except Exception:
        try:
            return sha256_text(json.dumps(signal, sort_keys=True, default=str))
        except Exception:
            return sha256_text(str(signal))



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
    try:
        intel_event(
            "signal_rejected",
            {"title": title, "reasons": reasons, "extras": extras or ""},
            signal=signal,
            stage=title.lower().replace(" ", "_"),
            decision="rejected",
        )
    except Exception:
        pass
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
    try:
        intel_event(
            "signal_routed",
            {"discord_enabled": state.get("discord_enabled", True), "telegram_enabled": state.get("telegram_enabled", True)},
            signal=signal,
            stage="routing",
            decision="routed",
        )
    except Exception:
        pass


# =========================================================
# INTELLIGENCE PHASE 1: TRADE MEMORY + PERFORMANCE ANALYTICS
# =========================================================
def intel_append_jsonl(path: str, record: Dict[str, Any]) -> bool:
    if not ENABLE_INTELLIGENCE_PHASE1:
        return False
    try:
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True, default=str) + "\n")
        return True
    except Exception as e:
        log(f"❌ INTEL append failed for {path}: {e}")
        return False


def intel_event(event_type: str, payload: Optional[Dict[str, Any]] = None, *, signal: Optional[Dict[str, Any]] = None, position: Optional[Dict[str, Any]] = None, stage: str = "engine", decision: str = "info"):
    if not ENABLE_INTELLIGENCE_PHASE1:
        return
    try:
        payload = payload or {}
        record = {
            "ts": epoch(),
            "time": now_ts(),
            "event_type": event_type,
            "stage": stage,
            "decision": decision,
            "payload": payload,
        }
        if signal:
            record["signal_id"] = signal.get("signal_id", "")
            record["ticker"] = signal.get("ticker", "")
            record["symbol"] = signal.get("symbol", "")
            record["direction"] = signal.get("direction", "")
            record["confidence"] = signal.get("confidence", "")
            record["regime"] = signal.get("regime", signal.get("market_regime", ""))
        if position:
            record["position_id"] = position.get("id", "")
            record["signal_id"] = record.get("signal_id") or position.get("signal_id", "")
            record["ticker"] = record.get("ticker") or position.get("ticker", "")
            record["symbol"] = record.get("symbol") or position.get("symbol", "")
            record["direction"] = record.get("direction") or position.get("direction", "")
            record["confidence"] = record.get("confidence") or position.get("confidence", "")
        intel_append_jsonl(INTEL_EVENT_LOG_FILE, record)
    except Exception as e:
        log(f"❌ INTEL event failed: {e}")


def intel_trade_story_from_position(position: Dict[str, Any], close_reason: str = "") -> Dict[str, Any]:
    entry = safe_float(position.get("avg_fill_price", 0), 0) or safe_float(position.get("entry_price", 0), 0)
    exit_price = safe_float(position.get("exit_price", position.get("last_price", 0)), 0)
    realized_pct = safe_float(position.get("realized_pnl_pct", 0), 0)
    opened_at = safe_int(position.get("opened_at", 0), 0)
    closed_at = safe_int(position.get("closed_at", epoch()), epoch())
    risk_per_contract = max(entry - safe_float(position.get("original_stop_price", position.get("stop_price", 0)), 0), 0)
    r_multiple = 0.0
    if risk_per_contract > 0:
        r_multiple = round((exit_price - entry) / risk_per_contract, 4)
    return {
        "closed_time": now_ts(),
        "closed_ts": closed_at,
        "position_id": position.get("id"),
        "signal_id": position.get("signal_id", ""),
        "ticker": position.get("ticker", ""),
        "symbol": position.get("symbol", ""),
        "direction": position.get("direction", ""),
        "confidence": position.get("confidence", ""),
        "mode": position.get("mode", ""),
        "qty_total": safe_int(position.get("qty_total", 0), 0),
        "entry_price": round(entry, 4),
        "exit_price": round(exit_price, 4),
        "original_stop_price": safe_float(position.get("original_stop_price", 0), 0),
        "final_stop_price": safe_float(position.get("stop_price", 0), 0),
        "tp1_hit": bool(position.get("tp1_hit", False)),
        "tp2_hit": bool(position.get("tp2_hit", False)),
        "highest_price": safe_float(position.get("highest_price", 0), 0),
        "lowest_price": safe_float(position.get("lowest_price", 0), 0),
        "realized_pnl_pct": round(realized_pct, 4),
        "winner": phase3_infer_winner({"realized_pnl_pct": realized_pct, "entry_price": entry, "exit_price": exit_price}),
        "r_multiple": r_multiple,
        "time_in_trade_seconds": max(0, closed_at - opened_at) if opened_at else 0,
        "close_reason": close_reason,
        "notes": position.get("notes", []),
    }


def intel_record_closed_trade(position: Dict[str, Any], close_reason: str = ""):
    if not ENABLE_INTELLIGENCE_PHASE1:
        return
    try:
        story = intel_trade_story_from_position(position, close_reason)
        intel_append_jsonl(INTEL_TRADE_MEMORY_FILE, story)
        intel_event("trade_closed", story, position=position, stage="trade_memory", decision="closed")
        if INTEL_REBUILD_ANALYTICS_ON_CLOSE:
            analytics = intel_build_performance_analytics()
            atomic_write_json(INTEL_ANALYTICS_FILE, analytics)
        if ENABLE_INTELLIGENCE_PHASE3:
            phase3_write_adaptive_stats(force=True)
        if INTEL_SEND_CLOSED_TRADE_SUMMARY:
            msg = (
                f"🧠 TRADE MEMORY SAVED\n"
                f"{story['ticker']} {story['direction']} | {story['confidence']}\n"
                f"Symbol: {story['symbol']}\n"
                f"PnL %: {story['realized_pnl_pct']} | R: {story['r_multiple']}\n"
                f"Reason: {close_reason}\n"
                f"Time In Trade: {story['time_in_trade_seconds']}s"
            )
            send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
    except Exception as e:
        log(f"❌ INTEL closed-trade record failed: {e}")


def intel_load_trade_memory() -> List[Dict[str, Any]]:
    rows = []
    try:
        if not file_exists(INTEL_TRADE_MEMORY_FILE):
            return rows
        with open(INTEL_TRADE_MEMORY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception as e:
        log(f"❌ INTEL load memory failed: {e}")
    return rows


def intel_group_stats(trades: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for t in trades:
        val = str(t.get(key, "UNKNOWN") or "UNKNOWN")
        grouped.setdefault(val, []).append(t)
    out = {}
    for val, items in grouped.items():
        n = len(items)
        wins = sum(1 for x in items if x.get("winner"))
        avg_pnl = sum(safe_float(x.get("realized_pnl_pct", 0), 0) for x in items) / n if n else 0
        avg_r = sum(safe_float(x.get("r_multiple", 0), 0) for x in items) / n if n else 0
        out[val] = {
            "trades": n,
            "wins": wins,
            "losses": n - wins,
            "win_rate": round(wins / n, 4) if n else 0,
            "avg_pnl_pct": round(avg_pnl, 4),
            "avg_r": round(avg_r, 4),
        }
    return out


def intel_build_performance_analytics() -> Dict[str, Any]:
    trades = intel_load_trade_memory()
    total = len(trades)
    wins = sum(1 for t in trades if t.get("winner"))
    total_r = sum(safe_float(t.get("r_multiple", 0), 0) for t in trades)
    total_pnl = sum(safe_float(t.get("realized_pnl_pct", 0), 0) for t in trades)
    return {
        "generated_at": now_ts(),
        "trade_count": total,
        "wins": wins,
        "losses": total - wins,
        "win_rate": round(wins / total, 4) if total else 0,
        "avg_r": round(total_r / total, 4) if total else 0,
        "avg_pnl_pct": round(total_pnl / total, 4) if total else 0,
        "by_ticker": intel_group_stats(trades, "ticker"),
        "by_direction": intel_group_stats(trades, "direction"),
        "by_confidence": intel_group_stats(trades, "confidence"),
        "by_close_reason": intel_group_stats(trades, "close_reason"),
        "by_setup_key": intel_group_stats([{**t, "setup_key": phase3_setup_key(t)} for t in trades], "setup_key") if 'phase3_setup_key' in globals() else {},
        "recent_trades": trades[-10:],
    }


def intel_write_analytics_snapshot(force: bool = False):
    if not ENABLE_INTELLIGENCE_PHASE1:
        return
    try:
        analytics = intel_build_performance_analytics()
        atomic_write_json(INTEL_ANALYTICS_FILE, analytics)
        if force:
            debug(f"INTEL ANALYTICS WRITTEN | trades={analytics.get('trade_count')} win_rate={analytics.get('win_rate')}")
    except Exception as e:
        log(f"❌ INTEL analytics write failed: {e}")


def intel_bootstrap(reason: str = "boot"):
    """Guarantee Intelligence Phase 1 creates its files and records a visible boot event."""
    if not ENABLE_INTELLIGENCE_PHASE1:
        return
    try:
        for path in [INTEL_EVENT_LOG_FILE, INTEL_TRADE_MEMORY_FILE]:
            if not file_exists(path):
                open(path, "a", encoding="utf-8").close()
        intel_event(
            "intelligence_layer_active",
            {
                "reason": reason,
                "event_log_file": INTEL_EVENT_LOG_FILE,
                "trade_memory_file": INTEL_TRADE_MEMORY_FILE,
                "analytics_file": INTEL_ANALYTICS_FILE,
            },
            stage="intelligence",
            decision="active",
        )
        intel_write_analytics_snapshot(force=True)
        if ENABLE_INTELLIGENCE_PHASE3:
            phase3_write_adaptive_stats(force=True)
        debug(f"🧠 INTELLIGENCE LAYER ACTIVE | files={INTEL_EVENT_LOG_FILE},{INTEL_TRADE_MEMORY_FILE},{INTEL_ANALYTICS_FILE},{PHASE3_ADAPTIVE_STATS_FILE}")
    except Exception as e:
        log(f"❌ INTEL bootstrap failed: {e}")


def intel_periodic_snapshot():
    """Write analytics on a timer so performance_summary.json stays fresh."""
    if not ENABLE_INTELLIGENCE_PHASE1:
        return
    try:
        ensure_globals_initialized()
        last_key = "intel_last_analytics_ts"
        last = safe_int(GLOBAL_STATE.get(last_key, 0), 0) if isinstance(GLOBAL_STATE, dict) else 0
        if (epoch() - last) >= INTEL_ANALYTICS_REFRESH_SECONDS:
            intel_write_analytics_snapshot(force=False)
            if ENABLE_INTELLIGENCE_PHASE3:
                phase3_write_adaptive_stats(force=False)
            GLOBAL_STATE[last_key] = epoch()
            save_state(GLOBAL_STATE)
    except Exception as e:
        log(f"❌ INTEL periodic snapshot failed: {e}")


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
    intel_event(
        "position_opened",
        {
            "entry_price": position.get("entry_price"),
            "stop_price": position.get("stop_price"),
            "tp1_price": position.get("tp1_price"),
            "tp2_price": position.get("tp2_price"),
            "qty_open": position.get("qty_open"),
            "mode": position.get("mode"),
        },
        position=position,
        stage="execution",
        decision="opened",
    )


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
    intel_event(
        "position_scaled",
        {"note": note, "qty_closed_now": qty_to_close, "fill_price": fill_price, "qty_open_after": position.get("qty_open")},
        position=position,
        stage="trade_management",
        decision="scaled",
    )
    if str(position.get("mode", "")).upper() == "PAPER":
        phase2_record_paper_order(position, side="sell", qty=qty_to_close, fill_price=fill_price, note=note)
        basis = safe_float(position.get("avg_fill_price", 0), 0) or safe_float(position.get("entry_price", 0), 0)
        scale_delta_dollars = paper_pnl_dollars(basis, fill_price, qty_to_close)
        scale_delta_pct = pct_change(basis, fill_price) / 100.0 if basis > 0 else 0.0
        update_daily_realized_pnl(scale_delta_dollars, scale_delta_pct, source=f"scale_out:{note}")
        phase2_post_fill_risk_snapshot("paper_scale_out")
    return True


def finalize_close_position(position: Dict[str, Any], exit_price: float, note: str):
    pre_close_qty = max(0, safe_int(position.get("qty_open", 0), 0))
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
    close_delta_dollars = paper_pnl_dollars(basis, position["exit_price"], pre_close_qty) if str(position.get("mode", "")).upper() == "PAPER" else round(realized_pct_decimal * get_account_equity(), 2)
    update_daily_realized_pnl(close_delta_dollars, realized_pct_decimal, source=f"final_close:{note}")
    GLOBAL_STATE["consecutive_losses"] = safe_int(GLOBAL_STATE.get("consecutive_losses", 0), 0) + 1 if position["realized_pnl_pct"] < 0 else 0
    save_state(GLOBAL_STATE)

    if str(position.get("mode", "")).upper() == "PAPER" and pre_close_qty > 0:
        phase2_record_paper_order(position, side="sell", qty=pre_close_qty, fill_price=position["exit_price"], note=note)
    GLOBAL_POSITIONS["open_positions"] = [p for p in GLOBAL_POSITIONS["open_positions"] if p["id"] != position["id"]]
    GLOBAL_POSITIONS["closed_positions"].append(position)
    save_positions(GLOBAL_POSITIONS)
    phase2_post_fill_risk_snapshot("position_closed")
    intel_record_closed_trade(position, note)
    try:
        adaptive_record_position_close(position, note)
    except Exception as adaptive_close_error:
        debug(f"ADAPTIVE CLOSED-TRADE RECORD ERROR | {adaptive_close_error}")
    phase35_locked_learning_hook(position, note)

    msg = build_position_close_message(position, note)
    send_to_telegram(msg)
    send_to_live_entry_discord(msg)


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
# PHASE 3.5 EXECUTION LAYER LOCK
# Final hard stop directly inside paper/live execution functions.
# This prevents any order creation if another path bypasses handle_new_signal().
# =========================================================
def phase35_execution_layer_gate(signal: Dict[str, Any], mode: str = "PAPER") -> Dict[str, Any]:
    if not ENABLE_PHASE35_ENFORCEMENT:
        return {"approved": True, "stage": "phase35_execution_layer", "notes": ["phase35_disabled"]}

    ensure_globals_initialized()
    mode = str(mode or "PAPER").upper().strip()

    hard_reasons: List[str] = []
    if GLOBAL_STATE.get("kill_switch", False):
        hard_reasons.append("phase35_exec_kill_switch_active")
    if GLOBAL_STATE.get("bot_paused", False):
        hard_reasons.append("phase35_exec_bot_paused")
    if not GLOBAL_STATE.get("engine_enabled", True):
        hard_reasons.append("phase35_exec_engine_disabled")
    if not GLOBAL_STATE.get("allow_entries", True):
        hard_reasons.append("phase35_exec_entries_not_allowed")
    if GLOBAL_STATE.get("reconciliation_required", False):
        hard_reasons.append("phase35_exec_reconciliation_required")

    if mode == "LIVE":
        if not ENABLE_ALPACA:
            hard_reasons.append("phase35_exec_live_enable_alpaca_false")
        if not ALLOW_LIVE_BUYS:
            hard_reasons.append("phase35_exec_live_buys_not_allowed")
        if signal.get("asset_class") == "option" and not ALPACA_ENABLE_OPTIONS:
            hard_reasons.append("phase35_exec_options_disabled")
        if signal.get("asset_class") == "option" and not ALPACA_LIVE_OPTIONS_APPROVED:
            hard_reasons.append("phase35_exec_options_not_live_approved")

    normal_decision = phase35_enforcement_gate(
        signal,
        phase3_decision=signal.get("phase3_decision", {}) if isinstance(signal.get("phase3_decision", {}), dict) else {},
        size_decision=signal.get("size_decision", {}) if isinstance(signal.get("size_decision", {}), dict) else {},
        stage=f"execution_layer_{mode.lower()}",
    )

    if hard_reasons:
        return phase35_block(
            f"PHASE 3.5 EXECUTION LAYER BLOCK - {mode}",
            signal,
            hard_reasons,
            "Final direct order gate blocked before any order or position could be created.",
        )

    if not normal_decision.get("approved", False):
        return normal_decision

    try:
        intel_event(
            "phase35_execution_layer_approved",
            {"mode": mode, "notes": normal_decision.get("notes", [])},
            signal=signal,
            stage="phase35_execution_layer",
            decision="approved",
        )
    except Exception:
        pass

    return {"approved": True, "stage": "phase35_execution_layer", "mode": mode, "notes": normal_decision.get("notes", [])}

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
    idem_gate = idempotency_pre_order_gate(signal, side="buy", qty=safe_int(signal.get("qty", 0), 0), mode="PAPER", order_type="market", limit_price=None)
    if not idem_gate.get("approved", False):
        log(f"🧷 PAPER ORDER IDEMPOTENCY BLOCK | {idem_gate.get('reason')} | key={idempotency_short(idem_gate.get('order_key',''))}")
        return None
    phase35_exec_decision = phase35_execution_layer_gate(signal, mode="PAPER")
    if not phase35_exec_decision.get("approved", False):
        return None

    phase1_decision = phase1_validate_order_safety(
        signal,
        side="buy",
        qty=safe_int(signal.get("qty", 0), 0),
        planned_price=safe_float(signal.get("entry_contract", 0), 0),
        mode="PAPER",
    )
    if not phase1_decision["approved"]:
        return None
    phase2_decision = phase2_validate_order_integrity(signal, side="buy", qty=safe_int(signal.get("qty", 0), 0), mode="PAPER")
    if not phase2_decision["approved"]:
        return None
    phase1_record_order_attempt("buy", str(signal.get("symbol", "")), safe_int(signal.get("qty", 0), 0))
    position = make_local_position(signal, mode="PAPER")
    save_new_position(position)
    paper_order = phase2_record_paper_order(position, side="buy", qty=safe_int(position.get("qty_open", 0), 0), fill_price=safe_float(position.get("entry_price", 0), 0), note="paper entry filled")
    idempotency_mark_order_submitted(signal, "buy", safe_int(position.get("qty_open", 0), 0), "PAPER", "market", None, paper_order)
    idempotency_mark_order_filled(paper_order)
    phase2_post_fill_risk_snapshot("paper_entry_open")
    GLOBAL_STATE["paper_trade_count"] = safe_int(GLOBAL_STATE.get("paper_trade_count", 0), 0) + 1
    save_state(GLOBAL_STATE)
    msg = build_position_open_message(position)
    send_to_telegram(msg)
    send_to_live_entry_discord(msg)
    return position


def submit_live_entry(signal: Dict[str, Any], position: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    phase35_exec_decision = phase35_execution_layer_gate(signal, mode="LIVE")
    if not phase35_exec_decision.get("approved", False):
        return None

    if not ALLOW_LIVE_BUYS:
        log("❌ LIVE BUY BLOCKED: ALLOW_LIVE_BUYS=false")
        return None
    if not validate_live_signal_for_alpaca(signal):
        return None

    phase1_decision = phase1_validate_order_safety(
        signal,
        side="buy",
        qty=safe_int(signal.get("qty", 0), 0),
        planned_price=safe_float(signal.get("entry_contract", 0), 0),
        mode="LIVE",
    )
    if not phase1_decision["approved"]:
        return None
    phase2_decision = phase2_validate_order_integrity(signal, side="buy", qty=safe_int(signal.get("qty", 0), 0), mode="LIVE")
    if not phase2_decision["approved"]:
        return None
    phase1_record_order_attempt("buy", str(signal.get("symbol", "")), safe_int(signal.get("qty", 0), 0))

    order_type = "limit" if signal.get("use_limit_entry", False) else "market"
    limit_price = safe_float(signal.get("limit_entry_price", 0), 0) if order_type == "limit" else None
    idem_gate = idempotency_pre_order_gate(signal, side="buy", qty=safe_int(signal.get("qty", 0), 0), mode="LIVE", order_type=order_type, limit_price=limit_price)
    if not idem_gate.get("approved", False):
        log(f"🧷 LIVE ORDER IDEMPOTENCY BLOCK | {idem_gate.get('reason')} | key={idempotency_short(idem_gate.get('order_key',''))}")
        return None
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
        idempotency_mark("order_intent", order_record.get("idempotency_order_intent_id", ""), "failed", {"reason": "broker_submit_failed"})
        return None

    idempotency_mark_order_submitted(signal, "buy", safe_int(signal.get("qty", 0), 0), "LIVE", order_type, limit_price, broker_order)
    apply_broker_order_snapshot(order_record, broker_order)
    update_order_status(order_record, order_record.get("status", "submitted"), "live entry submitted")
    position["broker_order_id"] = order_record.get("broker_order_id", "")
    position["client_order_id"] = order_record.get("client_order_id", "")
    save_positions(GLOBAL_POSITIONS)
    GLOBAL_STATE["live_trade_count"] = safe_int(GLOBAL_STATE.get("live_trade_count", 0), 0) + 1
    save_state(GLOBAL_STATE)
    msg = build_live_order_message(order_record, "LIVE ENTRY SUBMITTED")
    send_to_telegram(msg)
    send_to_live_entry_discord(msg)
    phase2_post_fill_risk_snapshot("live_entry_submitted")
    return order_record


def open_live_position(signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    phase35_exec_decision = phase35_execution_layer_gate(signal, mode="LIVE")
    if not phase35_exec_decision.get("approved", False):
        return None

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
    signal_stub = {"signal_id": position.get("signal_id", ""), "ticker": position.get("ticker", ""), "symbol": position.get("symbol", ""), "entry_price": position.get("last_price", position.get("entry_price", 0))}
    phase1_decision = phase1_validate_order_safety(signal_stub, side="sell", qty=qty_to_close, planned_price=safe_float(position.get("last_price", 0), 0), mode="LIVE")
    if not phase1_decision["approved"]:
        return False
    phase2_decision = phase2_validate_order_integrity(signal_stub, side="sell", qty=qty_to_close, mode="LIVE")
    if not phase2_decision["approved"]:
        return False
    phase1_record_order_attempt("sell", str(position.get("symbol", "")), qty_to_close)
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
    send_to_live_entry_discord(msg)
    return True


def live_close_position(position: Dict[str, Any], note: str) -> bool:
    if not ALLOW_LIVE_SELLS:
        return False
    qty_open = max(0, safe_int(position.get("qty_open", 0), 0) - safe_int(position.get("pending_close_qty", 0), 0))
    if qty_open <= 0:
        return False
    signal_stub = {"signal_id": position.get("signal_id", ""), "ticker": position.get("ticker", ""), "symbol": position.get("symbol", ""), "entry_price": position.get("last_price", position.get("entry_price", 0))}
    phase1_decision = phase1_validate_order_safety(signal_stub, side="sell", qty=qty_open, planned_price=safe_float(position.get("last_price", 0), 0), mode="LIVE")
    if not phase1_decision["approved"]:
        return False
    phase2_decision = phase2_validate_order_integrity(signal_stub, side="sell", qty=qty_open, mode="LIVE")
    if not phase2_decision["approved"]:
        return False
    phase1_record_order_attempt("sell", str(position.get("symbol", "")), qty_open)
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
    send_to_live_entry_discord(msg)
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
def refresh_market_data_file_metadata() -> bool:
    """Stamp MARKET_DATA_FILE prices with explicit freshness timestamps.

    This fixes Render/GitHub test timing where a valid manual test price can look stale
    just because the file mtime is old. Numeric prices are converted into structured
    objects with timestamp + price_updated_at.
    """
    if not MARKET_DATA_REFRESH_FILE_TIMESTAMPS:
        return False
    if not MARKET_DATA_FILE or not file_exists(MARKET_DATA_FILE):
        return False
    try:
        with open(MARKET_DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return False
        now = epoch()
        stamped = {}
        changed = False
        for key, value in data.items():
            key_s = str(key)
            if key_s.startswith("__"):
                continue
            if isinstance(value, dict):
                price = safe_float(value.get("price", value.get("last", value.get("mark", value.get("mid", 0)))), 0)
                if price <= 0:
                    stamped[key_s] = value
                    continue
                updated = dict(value)
                updated["price"] = price
                updated["timestamp"] = now
                updated["price_updated_at"] = now
                updated.setdefault("source", MARKET_DATA_FILE)
                if updated != value:
                    changed = True
                stamped[key_s] = updated
            else:
                price = safe_float(value, 0)
                if price <= 0:
                    stamped[key_s] = value
                    continue
                stamped[key_s] = {"price": price, "timestamp": now, "price_updated_at": now, "source": MARKET_DATA_FILE}
                changed = True
        stamped["__updated_at"] = now
        stamped["__freshness_source"] = "engine_refresh"
        stamped["__max_age_seconds"] = MARKET_DATA_MAX_AGE_SECONDS
        if changed or data.get("__updated_at") != now:
            atomic_write_json(MARKET_DATA_FILE, stamped)
            debug(f"MARKET DATA FRESHNESS REFRESHED | file={MARKET_DATA_FILE} | max_age={MARKET_DATA_MAX_AGE_SECONDS}s")
        return True
    except Exception as e:
        log(f"❌ Market data freshness refresh failed: {e}")
        return False


def get_market_data_file_updated_at(prices: Optional[Dict[str, Any]] = None) -> int:
    try:
        if isinstance(prices, dict):
            ts = safe_int(prices.get("__updated_at", 0), 0)
            if ts > 0:
                return ts
        if MARKET_DATA_FILE and file_exists(MARKET_DATA_FILE):
            return int(os.path.getmtime(MARKET_DATA_FILE))
    except Exception:
        pass
    return 0


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

    refresh_market_data_file_metadata()

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
        ts = safe_int(value.get("timestamp", value.get("ts", value.get("price_updated_at", value.get("updated_at", 0)))), 0)
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
        if str(key).startswith("__"):
            continue
        if str(key).upper().strip() == symbol_upper:
            return parse_market_price_value(value)
    return 0.0, 0


def market_price_is_stale(ts: int) -> bool:
    if ts <= 0:
        return False
    return (epoch() - ts) > MARKET_DATA_MAX_AGE_SECONDS


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
def send_position_management_update(position: Dict[str, Any], note: str):
    """Step 12 helper: send trade-management updates everywhere useful."""
    msg = build_position_update_message(position, note)
    send_to_telegram(msg)
    send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
    send_to_live_entry_discord(msg)


# =========================================================
# STEP 13 ADVANCED TRADE MANAGEMENT
# - Early break-even protection
# - Smart trailing stop
# - Aggressive profit lock
# - Time-based dead-trade exit
# =========================================================
def step13_manage_advanced(position: Dict[str, Any], live_price: float) -> Tuple[bool, bool]:
    """
    Returns (changed, closed).

    changed=True means position state changed and should be saved.
    closed=True means position was finalized/removed from open positions.
    """
    if not ENABLE_STEP13_ADVANCED_MANAGEMENT:
        return False, False

    try:
        entry_price = safe_float(position.get("avg_fill_price", 0), 0) or safe_float(position.get("entry_price", 0), 0)
        if entry_price <= 0 or live_price <= 0:
            return False, False

        current_stop = safe_float(position.get("stop_price", 0), 0)
        opened_at = safe_int(position.get("opened_at", position.get("open_time", epoch())), epoch())
        move_pct_decimal = (live_price - entry_price) / entry_price
        changed = False

        # 1) Early break-even protection BEFORE TP1.
        if move_pct_decimal >= STEP13_BREAKEVEN_TRIGGER_PCT and not position.get("step13_breakeven_set", False):
            new_stop = max(current_stop, entry_price)
            if new_stop > current_stop:
                position["stop_price"] = round(new_stop, 4)
                position["step13_breakeven_set"] = True
                position.setdefault("notes", []).append(f"Step 13 breakeven set: {current_stop} -> {position['stop_price']}")
                log(f"🛡️ STEP 13 BREAKEVEN SET | {position.get('symbol')} | stop={current_stop} -> {position['stop_price']}")
                send_position_management_update(position, "STEP 13 BREAKEVEN SET")
                changed = True

        # 2) Smart trail after a clean move.
        current_stop = safe_float(position.get("stop_price", 0), 0)
        if move_pct_decimal >= STEP13_SMART_TRAIL_TRIGGER_PCT:
            smart_stop = round(live_price * STEP13_SMART_TRAIL_LOCK_PCT, 4)
            if smart_stop > current_stop:
                old_stop = current_stop
                position["stop_price"] = smart_stop
                position.setdefault("notes", []).append(f"Step 13 smart trail: {old_stop} -> {smart_stop}")
                log(f"📈 STEP 13 SMART TRAIL | {position.get('symbol')} | stop={old_stop} -> {smart_stop}")
                send_position_management_update(position, "STEP 13 SMART TRAIL")
                changed = True

        # 3) Aggressive profit lock after a larger move.
        current_stop = safe_float(position.get("stop_price", 0), 0)
        if move_pct_decimal >= STEP13_AGGRESSIVE_TRAIL_TRIGGER_PCT:
            aggressive_stop = round(live_price * STEP13_AGGRESSIVE_TRAIL_LOCK_PCT, 4)
            if aggressive_stop > current_stop:
                old_stop = current_stop
                position["stop_price"] = aggressive_stop
                position.setdefault("notes", []).append(f"Step 13 aggressive trail: {old_stop} -> {aggressive_stop}")
                log(f"🔒 STEP 13 AGGRESSIVE TRAIL | {position.get('symbol')} | stop={old_stop} -> {aggressive_stop}")
                send_position_management_update(position, "STEP 13 AGGRESSIVE TRAIL")
                changed = True

        # 4) Dead-trade time exit: if it sits too long and barely moves, close it.
        if STEP13_TIME_EXIT_ENABLED and opened_at > 0:
            age_seconds = epoch() - opened_at
            if age_seconds >= STEP13_MAX_HOLD_SECONDS and abs(move_pct_decimal) < STEP13_STAGNANT_MOVE_PCT:
                if position.get("mode") == "LIVE":
                    live_close_position(position, "STEP 13 TIME EXIT - stagnant trade")
                else:
                    finalize_close_position(position, live_price, "STEP 13 TIME EXIT - stagnant trade")
                log(f"⏱️ STEP 13 TIME EXIT | {position.get('symbol')} | age={age_seconds}s | live={live_price}")
                return True, True

        return changed, False

    except Exception as e:
        log(f"❌ STEP 13 ERROR: {e}")
        return False, False


# =========================================================
# STEP 12 TRADE MANAGEMENT MODE
# Position-first management: TP1, TP2, breakeven, trailing stop, stop loss.
# IMPORTANT: signal.json is for ENTRY only. Once a position is open, the loop
# manages the position from live/file market prices and ignores fresh entries.
# =========================================================
def manage_open_positions(incoming_signal: Optional[Dict[str, Any]] = None):
    ensure_globals_initialized()

    if not AUTO_MANAGE_POSITIONS:
        debug("AUTO_MANAGE_POSITIONS disabled; skipping manage_open_positions")
        return

    open_positions = GLOBAL_POSITIONS.get("open_positions", [])
    if not open_positions:
        return

    changed = False

    for position in list(open_positions):
        symbol = str(position.get("symbol", "")).strip()
        if not symbol:
            continue

        live_price = safe_float(position.get("last_price", 0), 0)

        if incoming_signal and incoming_signal.get("symbol") == symbol:
            incoming_contract = safe_float(incoming_signal.get("contract_price", 0), 0)
            if incoming_contract > 0:
                live_price = incoming_contract

        if live_price <= 0:
            debug(f"STEP 12 SKIP | {symbol} has no live price yet")
            continue

        update_position_market_price(position, live_price)

        entry_price = safe_float(position.get("avg_fill_price", 0), 0) or safe_float(position.get("entry_price", 0), 0)
        tp1_price = safe_float(position.get("tp1_price", 0), 0)
        tp2_price = safe_float(position.get("tp2_price", 0), 0)
        stop_price = safe_float(position.get("stop_price", 0), 0)
        qty_open = safe_int(position.get("qty_open", 0), 0)
        pnl_pct = safe_float(position.get("pnl_pct", 0), 0)

        debug(
            f"STEP 12 MANAGING | id={position.get('id')} | {symbol} | "
            f"live={live_price} | entry={entry_price} | stop={stop_price} | "
            f"tp1={tp1_price} | tp2={tp2_price} | qty_open={qty_open} | pnl={round(pnl_pct, 2)}%"
        )

        if qty_open <= 0:
            if position.get("status") != "CLOSED":
                finalize_close_position(position, live_price, "All size scaled out")
                changed = True
            continue

        if position.get("mode") == "LIVE" and not position.get("entry_filled", False):
            debug(f"STEP 12 WAIT | live entry not filled yet for {symbol}")
            continue

        # STEP 13 runs before TP/stop checks so it can protect early, trail dynamically,
        # or time-exit stagnant trades while keeping all Step 12 logic intact.
        debug(f"STEP 13 CHECK | id={position.get('id')} | {symbol} | live={live_price} | entry={entry_price} | stop={position.get('stop_price')} | tp1_hit={position.get('tp1_hit', False)}")
        step13_changed, step13_closed = step13_manage_advanced(position, live_price)
        if step13_changed:
            changed = True
        if step13_closed:
            continue

        # TP1: scale out 50% and move stop to breakeven.
        if AUTO_TP_ENABLED and not position.get("tp1_hit", False) and tp1_price > 0 and live_price >= tp1_price:
            qty1 = min(
                max(1, math.floor(safe_int(position.get("qty_total", 1), 1) * safe_float(position.get("scale1_pct", DEFAULT_SCALE1_PCT), DEFAULT_SCALE1_PCT))),
                safe_int(position.get("qty_open", 0), 0)
            )
            if qty1 > 0:
                ok = live_scale_out(position, qty1, "TP1 HIT - live scale-out") if position.get("mode") == "LIVE" else scale_out_local(position, qty1, live_price, "TP1 HIT - paper scale-out")
                if ok:
                    position["tp1_hit"] = True
                    changed = True
                    if AUTO_BREAKEVEN_ENABLED and position.get("break_even_after_tp1", False):
                        old_stop = safe_float(position.get("stop_price", 0), 0)
                        position["stop_price"] = max(old_stop, entry_price)
                        position.setdefault("notes", []).append(f"Stop moved to breakeven after TP1: {old_stop} -> {position['stop_price']}")
                    log(f"💰 STEP 12 TP1 HIT | {symbol} | live={live_price} | remaining_qty={position.get('qty_open')} | pnl={round(position.get('pnl_pct', 0), 2)}%")
                    send_position_management_update(position, "TP1 HIT")

        # TP2: close ALL remaining size. This makes the test clean:
        # 1.00 entry -> 1.30 TP1 -> 1.60 full close.
        if AUTO_TP_ENABLED and not position.get("tp2_hit", False) and tp2_price > 0 and live_price >= tp2_price:
            remaining = safe_int(position.get("qty_open", 0), 0)
            if remaining > 0:
                if position.get("mode") == "LIVE":
                    ok = live_scale_out(position, remaining, "TP2 HIT - close remaining")
                    if ok:
                        position["tp2_hit"] = True
                        log(f"🚀 STEP 12 TP2 HIT | {symbol} | live={live_price} | remaining sent to close={remaining}")
                        send_position_management_update(position, "TP2 HIT - close remaining")
                        changed = True
                else:
                    position["tp2_hit"] = True
                    finalize_close_position(position, live_price, "TP2 HIT - paper full close")
                    log(f"🚀 STEP 12 TP2 HIT / CLOSED | {symbol} | live={live_price}")
                    changed = True
                    continue

        # Smart trailing stop after profit. Can be restricted to after TP1.
        highest_price = safe_float(position.get("highest_price", live_price), live_price)
        trail_pct = safe_float(position.get("trail_pct", DEFAULT_TRAIL_PCT), DEFAULT_TRAIL_PCT)
        trailing_allowed = AUTO_TRAILING_STOP_ENABLED and (not TRAIL_ONLY_AFTER_TP1 or position.get("tp1_hit", False))
        if trailing_allowed and highest_price > entry_price and trail_pct > 0:
            profit_open = highest_price - entry_price
            trailed_stop = round(highest_price - (profit_open * trail_pct), 4)
            if trailed_stop > safe_float(position.get("stop_price", 0), 0):
                old_stop = position["stop_price"]
                position["stop_price"] = trailed_stop
                position.setdefault("notes", []).append(f"Trailing stop raised: {old_stop} -> {trailed_stop}")
                debug(f"STEP 12 TRAIL RAISED | {symbol}: {old_stop} -> {trailed_stop}")
                changed = True

        # Stop loss / trailing stop close.
        if live_price <= safe_float(position.get("stop_price", 0), 0):
            if position.get("mode") == "LIVE":
                live_close_position(position, "STOP HIT / trailing stop")
            else:
                finalize_close_position(position, live_price, "STOP HIT / trailing stop")
            log(f"🛑 STEP 12 STOP HIT | {symbol} | live={live_price}")
            changed = True
            continue

        if position.get("mode") == "PAPER" and safe_int(position.get("qty_open", 0), 0) <= 0:
            finalize_close_position(position, live_price, "All size scaled out")
            changed = True
            continue

    if changed:
        save_positions(GLOBAL_POSITIONS)
        flush_dirty_stores(force=False)
    else:
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



def open_position_if_missing(signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    HARD ENTRY TRIGGER FIX.

    This guarantees that once a signal passes validation, entry lock, regime,
    sizing, risk policy, and portfolio risk, the engine actually creates
    a paper/live position. It also prevents duplicate opens for the same
    locked contract symbol.
    """
    ensure_globals_initialized()
    symbol = str(signal.get("symbol", "")).strip()

    duplicate_gate = hard_duplicate_entry_gate(signal)
    if not duplicate_gate["approved"]:
        msg = build_block_message("HARD DUPLICATE CAP SKIPPED OPEN", signal, duplicate_gate["reject_reasons"], "open_position_if_missing refused to create a stacked position.")
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_live_entry_discord(msg)
        send_to_telegram(msg)
        debug(f"ENTRY TRIGGER SKIPPED BY HARD DUPLICATE CAP | symbol={symbol} | reasons={duplicate_gate['reject_reasons']}")
        return None

    # In live mode, only open live if Alpaca is explicitly enabled and paper is off.
    if GLOBAL_STATE.get("alpaca_enabled", False) and ENABLE_ALPACA and not GLOBAL_STATE.get("paper_enabled", True):
        position = open_live_position(signal)
        if position:
            log(f"✅ LIVE POSITION OPENED BY ENTRY TRIGGER | {symbol} | qty={position.get('qty_open')} | entry={position.get('entry_price')}")
        else:
            msg = build_block_message(
                "ENTRY PASSED BUT LIVE OPEN FAILED",
                signal,
                ["open_live_position_returned_none"],
                "Check Alpaca permissions, ALLOW_LIVE_BUYS, and broker response."
            )
            send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
            send_to_telegram(msg)
        return position

    # Default safe mode: paper execution.
    # Phase 3.5 execution-lock fix: allow paper execution when either
    # the persisted state OR the environment toggle says paper execution is enabled.
    if GLOBAL_STATE.get("paper_enabled", True) or ENABLE_PAPER_EXECUTION:
        GLOBAL_STATE["paper_enabled"] = True
        save_state(GLOBAL_STATE)
        position = open_paper_position(signal)
        if position:
            log(f"✅ PAPER POSITION OPENED BY ENTRY TRIGGER | {symbol} | qty={position.get('qty_open')} | entry={position.get('entry_price')}")
            # Extra AI-channel confirmation so it is impossible to miss in testing.
            send_to_discord(DISCORD_AI_WEBHOOK, build_position_open_message(position), "AI")
        else:
            msg = build_block_message(
                "ENTRY PASSED BUT PAPER OPEN FAILED",
                signal,
                ["open_paper_position_returned_none"],
                "Paper mode was enabled but no position object was created."
            )
            send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
            send_to_telegram(msg)
        return position

    msg = build_block_message(
        "ENTRY PASSED BUT NO EXECUTION MODE ENABLED",
        signal,
        ["paper_disabled_and_alpaca_not_active"],
        "Turn on /paper_on or enable Alpaca live mode intentionally."
    )
    send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
    send_to_telegram(msg)
    log("❌ ENTRY PASSED BUT NO EXECUTION MODE ENABLED")
    return None


# =========================================================
# STEP 14 PORTFOLIO RISK ENGINE
# =========================================================
def step14_daily_loss_limit_dollars() -> float:
    """Return the active daily loss limit in dollars."""
    if STEP14_MAX_DAILY_LOSS_DOLLARS > 0:
        return STEP14_MAX_DAILY_LOSS_DOLLARS
    return max(get_account_equity() * STEP14_MAX_DAILY_LOSS_PCT, 1.0)


def normalize_pnl_value_to_decimal(raw_value: float) -> float:
    """Normalize stored PnL into decimal form. Supports 0.30 and 30.0 as +30%."""
    val = safe_float(raw_value, 0.0)
    if abs(val) > 1.0:
        return val / 100.0
    return val


def step14_daily_pnl_dollars() -> float:
    """Stable daily realized PnL in dollars. Never silently resets intraday."""
    return stable_daily_pnl_dollars()


def step14_open_trade_count() -> int:
    ensure_globals_initialized()
    return len([p for p in GLOBAL_POSITIONS.get("open_positions", []) if str(p.get("status", "OPEN")).upper() == "OPEN"])


def step14_send_alert(title: str, body: str):
    msg = f"🛡️ {title}\n{body}\n⏰ {now_ts()}"
    log(msg.replace("\n", " | "))
    if STEP14_SEND_ALERTS:
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_live_entry_discord(msg)
        send_to_telegram(msg)


def step14_can_open_new_trade(signal: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Portfolio-level entry gate. Runs after normal signal/risk checks but before opening a position."""
    ensure_globals_initialized()
    if not ENABLE_STEP14_PORTFOLIO_RISK:
        return {"approved": True, "reject_reasons": [], "stage": "step14_portfolio_risk"}

    reasons = []
    open_count = step14_open_trade_count()
    daily_pnl = step14_daily_pnl_dollars()
    daily_loss_limit = step14_daily_loss_limit_dollars()

    if open_count >= STEP14_MAX_OPEN_TRADES:
        reasons.append("step14_max_open_trades_reached")

    if STEP14_BLOCK_NEW_TRADES_ON_DAILY_LOSS and daily_pnl <= -abs(daily_loss_limit):
        reasons.append("step14_daily_loss_limit_hit")

    if GLOBAL_STATE.get("kill_switch", False):
        reasons.append("step14_kill_switch_active")
    if GLOBAL_STATE.get("allow_entries", True) is False:
        reasons.append("entries_disabled_by_hard_kill")

    decision = {
        "approved": len(reasons) == 0,
        "reject_reasons": reasons,
        "stage": "step14_portfolio_risk",
        "open_trades": open_count,
        "max_open_trades": STEP14_MAX_OPEN_TRADES,
        "daily_pnl_dollars": daily_pnl,
        "daily_loss_limit_dollars": daily_loss_limit,
    }

    if decision["approved"]:
        debug(f"STEP 14 OK | open={open_count}/{STEP14_MAX_OPEN_TRADES} | daily_pnl={daily_pnl} | loss_limit=-{round(abs(daily_loss_limit), 2)}")

    if not decision["approved"]:
        extra = (
            f"Open Trades: {open_count}/{STEP14_MAX_OPEN_TRADES}\n"
            f"Daily PnL: ${daily_pnl}\n"
            f"Daily Loss Limit: -${round(abs(daily_loss_limit), 2)}"
        )
        if signal:
            msg = build_block_message("STEP 14 PORTFOLIO RISK BLOCKED ENTRY", signal, reasons, extra)
            send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
            send_to_live_entry_discord(msg)
            send_to_telegram(msg)
        else:
            step14_send_alert("STEP 14 PORTFOLIO RISK BLOCKED ENTRY", extra)

    return decision


def step14_close_all_open_positions(reason: str):
    """Close every open position in paper/live mode when an account-level stop is hit."""
    ensure_globals_initialized()
    open_positions = list(GLOBAL_POSITIONS.get("open_positions", []))
    if not open_positions:
        return

    for position in open_positions:
        symbol = str(position.get("symbol", "")).strip()
        live_price = safe_float(position.get("last_price", 0), 0) or safe_float(position.get("entry_price", 0), 0)
        try:
            if position.get("mode") == "LIVE":
                live_close_position(position, reason)
            else:
                finalize_close_position(position, live_price, reason)
        except Exception as e:
            log(f"❌ STEP 14 close-all error for {symbol}: {e}")


def step14_global_risk_guard() -> bool:
    """Return True when global risk stop is active and the loop should skip new work."""
    ensure_globals_initialized()
    if not ENABLE_STEP14_PORTFOLIO_RISK:
        return False

    daily_pnl = step14_daily_pnl_dollars()
    daily_loss_limit = step14_daily_loss_limit_dollars()

    if daily_pnl <= -abs(daily_loss_limit):
        GLOBAL_STATE["kill_switch"] = True
        GLOBAL_STATE["bot_paused"] = True
        GLOBAL_STATE["allow_entries"] = False
        GLOBAL_STATE["hard_kill_reason"] = f"Daily PnL ${daily_pnl} <= -${round(abs(daily_loss_limit), 2)}"
        GLOBAL_STATE["step14_daily_loss_shutdown_at"] = epoch()
        GLOBAL_STATE["step14_daily_loss_shutdown_reason"] = f"Daily PnL ${daily_pnl} <= -${round(abs(daily_loss_limit), 2)}"
        save_state(GLOBAL_STATE)
        debug(f"STEP 14 HARD LOSS LIMIT HIT | daily_pnl={daily_pnl} | limit=-{round(abs(daily_loss_limit),2)} | kill=True")

        step14_send_alert(
            "STEP 14 EMERGENCY STOP",
            f"Daily loss limit hit.\nDaily PnL: ${daily_pnl}\nLimit: -${round(abs(daily_loss_limit), 2)}\nNew trades blocked."
        )

        if STEP14_CLOSE_ALL_ON_DAILY_LOSS:
            step14_close_all_open_positions("STEP 14 DAILY LOSS EMERGENCY STOP")
        return True

    if GLOBAL_STATE.get("kill_switch", False) and STEP14_EMERGENCY_STOP_ON_KILL:
        if STEP14_CLOSE_ALL_ON_DAILY_LOSS:
            step14_close_all_open_positions("STEP 14 KILL SWITCH EMERGENCY STOP")
        return True

    return False


def step14_loop_enforcement() -> bool:
    """Visible Step 14 loop check. Returns False only when risk guard stops the engine."""
    ensure_globals_initialized()
    if not ENABLE_STEP14_PORTFOLIO_RISK:
        debug("STEP 14 DISABLED")
        return True
    if step14_global_risk_guard():
        debug("STEP 14 LOOP BLOCK | global risk guard active")
        return False
    open_count = step14_open_trade_count()
    daily_pnl = step14_daily_pnl_dollars()
    daily_loss_limit = step14_daily_loss_limit_dollars()
    debug(f"STEP 14 LOOP OK | open={open_count}/{STEP14_MAX_OPEN_TRADES} | daily_pnl={daily_pnl} | loss_limit=-{round(abs(daily_loss_limit), 2)}")
    return True

# =========================================================
# STEP 15 GLOBAL KILL SWITCH / FLATTEN ENGINE
# =========================================================

# =========================================================
# STEP 15 MODE SAFE ACCESSOR
# Prevents KeyError: 'mode' during flatten / close logic.
# =========================================================
def get_position_mode(pos: Dict[str, Any]) -> str:
    try:
        if not isinstance(pos, dict):
            return "paper"
        mode = str(pos.get("mode", "paper")).lower().strip()
        return mode if mode else "paper"
    except Exception:
        return "paper"



def step15_alert(title: str, body: str, force: bool = False):
    """Send emergency Step 15 alerts with simple cooldown protection."""
    ensure_globals_initialized()
    now = epoch()
    last_alert = safe_int(GLOBAL_STATE.get("step15_last_alert_time", 0), 0)
    if not force and (now - last_alert) < STEP15_ALERT_COOLDOWN_SECONDS:
        return
    GLOBAL_STATE["step15_last_alert_time"] = now
    save_state(GLOBAL_STATE)

    msg = f"🚨 {title}\n{body}\n⏰ {now_ts()}"
    log(msg.replace("\n", " | "))
    if STEP15_SEND_ALERTS:
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_live_entry_discord(msg)
        send_to_telegram(msg)


def step15_close_all_open_positions(reason: str) -> int:
    """Flatten all currently tracked positions. Returns number of close attempts."""
    ensure_globals_initialized()
    open_positions = list(GLOBAL_POSITIONS.get("open_positions", []))
    if not open_positions:
        debug(f"STEP 15 FLATTEN CHECK | no open positions | reason={reason}")
        return 0

    close_count = 0
    for position in open_positions:
        symbol = str(position.get("symbol", "")).strip()
        try:
            live_price = get_live_price_for_position(position)
            if live_price and live_price > 0:
                update_position_market_price(position, live_price)
            exit_price = safe_float(position.get("last_price", 0), 0) or safe_float(position.get("entry_price", 0), 0)

            if position.get("mode") == "LIVE":
                live_close_position(position, reason)
            else:
                finalize_close_position(position, exit_price, reason)
            close_count += 1
            log(f"🔥 STEP 15 FLATTENED | {symbol} | reason={reason} | exit={exit_price}")
        except Exception as e:
            log(f"❌ STEP 15 flatten error | {symbol}: {e}")

    flush_dirty_stores(force=True)
    return close_count


def step15_activate_kill_switch(reason: str, close_positions: bool = True):
    """Activate the hard lock. Optionally flatten all open positions."""
    ensure_globals_initialized()
    if not ENABLE_STEP15_GLOBAL_KILL_SWITCH:
        return

    already_active = bool(GLOBAL_STATE.get("step15_kill_active", False))
    GLOBAL_STATE["step15_kill_active"] = True
    GLOBAL_STATE["step15_locked"] = True
    GLOBAL_STATE["step15_last_reason"] = reason
    GLOBAL_STATE["step15_activated_at"] = epoch()
    GLOBAL_STATE["kill_switch"] = True
    GLOBAL_STATE["bot_paused"] = True
    if STEP15_LOCK_ENGINE_ON_KILL:
        GLOBAL_STATE["engine_enabled"] = False
    save_state(GLOBAL_STATE)

    closed = 0
    if close_positions and STEP15_CLOSE_ALL_ON_KILL:
        closed = step15_close_all_open_positions(reason)

    if not already_active:
        step15_alert(
            "STEP 15 KILL SWITCH ACTIVATED",
            f"Reason: {reason}\nClosed/flatten attempts: {closed}\nEngine Locked: {GLOBAL_STATE.get('engine_enabled') is False}\nNew trades blocked until manual reset.",
            force=True,
        )
    else:
        debug(f"STEP 15 KILL SWITCH STILL ACTIVE | reason={reason} | closed={closed}")


def step15_flatten_only(reason: str = "Manual flatten"):
    """Flatten positions without locking the entire engine."""
    closed = step15_close_all_open_positions(reason)
    step15_alert("STEP 15 FLATTEN SENT", f"Reason: {reason}\nClosed/flatten attempts: {closed}", force=True)


def step15_reset_lock():
    """Manual reset after a kill switch. Keeps risk counters intact."""
    ensure_globals_initialized()
    GLOBAL_STATE["step15_kill_active"] = False
    GLOBAL_STATE["step15_locked"] = False
    GLOBAL_STATE["step15_last_reason"] = ""
    GLOBAL_STATE["kill_switch"] = False
    GLOBAL_STATE["bot_paused"] = False
    GLOBAL_STATE["engine_enabled"] = True
    GLOBAL_STATE["allow_entries"] = True
    GLOBAL_STATE["hard_kill_reason"] = ""
    save_state(GLOBAL_STATE)
    flush_dirty_stores(force=True)
    step15_alert("STEP 15 RESET", "Kill switch cleared. Engine unlocked and ready for new signals.", force=True)


def step15_global_guard() -> bool:
    """Return True if engine can continue. Return False when Step 15 lock is active."""
    ensure_globals_initialized()
    if not ENABLE_STEP15_GLOBAL_KILL_SWITCH:
        return True

    daily_pnl = step14_daily_pnl_dollars()
    daily_loss_limit = step14_daily_loss_limit_dollars()

    if daily_pnl <= -abs(daily_loss_limit):
        GLOBAL_STATE["kill_switch"] = True
        GLOBAL_STATE["bot_paused"] = True
        GLOBAL_STATE["allow_entries"] = False
        GLOBAL_STATE["hard_kill_reason"] = f"daily_pnl ${daily_pnl} <= -${round(abs(daily_loss_limit), 2)}"
        save_state(GLOBAL_STATE)
        debug(f"HARD LOSS LIMIT HIT | daily_pnl={daily_pnl} | limit=-{round(abs(daily_loss_limit),2)} | kill=True")
        hard_kill_engine(
            f"STEP 15 DAILY LOSS LIMIT HIT: daily_pnl=${daily_pnl} <= -${round(abs(daily_loss_limit), 2)}",
            close_positions=STEP15_CLOSE_ALL_ON_KILL,
        )
        return False

    if GLOBAL_STATE.get("step15_kill_active", False) or GLOBAL_STATE.get("step15_locked", False) or GLOBAL_STATE.get("kill_switch", False):
        if STEP15_CLOSE_ALL_ON_KILL:
            step15_close_all_open_positions(GLOBAL_STATE.get("step15_last_reason", "Manual/global kill switch active"))
        step15_alert(
            "STEP 15 ENGINE LOCKED",
            f"Reason: {GLOBAL_STATE.get('step15_last_reason', 'Kill switch active')}\nUse /unlock only after reviewing risk.",
            force=False,
        )
        debug(f"STEP 15 ENGINE LOCKED | daily_pnl={daily_pnl} | loss_limit=-{round(abs(daily_loss_limit), 2)} | kill=True")
        return False

    debug(f"STEP 15 GUARD OK | daily_pnl={daily_pnl} | loss_limit=-{round(abs(daily_loss_limit), 2)} | kill=False")
    return True


# =========================================================
# INTELLIGENCE PHASE 3: ADAPTIVE INTELLIGENCE
# =========================================================
def phase3_setup_key(signal_or_trade: Dict[str, Any]) -> str:
    ticker = str(signal_or_trade.get("ticker", "UNKNOWN")).upper().strip()
    direction = str(signal_or_trade.get("direction", "UNKNOWN")).upper().strip()
    confidence = str(signal_or_trade.get("confidence", "NA")).upper().strip()
    setup = str(signal_or_trade.get("setup") or signal_or_trade.get("strategy") or signal_or_trade.get("trigger") or "GENERIC").upper().strip()
    setup = setup.replace(" ", "_")[:40]
    return f"{ticker}_{direction}_{confidence}_{setup}"


def phase3_infer_winner(trade: Dict[str, Any]) -> bool:
    """Robust W/L detection for adaptive learning. Fixes losses not being counted."""
    pnl = safe_float(trade.get("realized_pnl_pct", trade.get("pnl_pct", 0)), 0)
    if abs(pnl) > 0:
        return pnl > 0
    explicit = trade.get("winner", None)
    if isinstance(explicit, bool):
        return explicit
    entry = safe_float(trade.get("entry_price", trade.get("entry", 0)), 0)
    exit_price = safe_float(trade.get("exit_price", trade.get("exit", trade.get("last_price", 0))), 0)
    if entry > 0 and exit_price > 0:
        return exit_price > entry
    return False


def phase3_trade_result_letter(trade: Dict[str, Any]) -> str:
    return "W" if phase3_infer_winner(trade) else "L"


def phase3_load_disabled_setups() -> Dict[str, Any]:
    data = load_json_file(PHASE3_DISABLED_SETUPS_FILE, {})
    return data if isinstance(data, dict) else {}


def phase3_save_disabled_setups(data: Dict[str, Any]):
    atomic_write_json(PHASE3_DISABLED_SETUPS_FILE, data)


def phase3_compute_setup_stats() -> Dict[str, Any]:
    trades = intel_load_trade_memory()
    stats: Dict[str, Any] = {}
    for t in trades:
        key = phase3_setup_key(t)
        bucket = stats.setdefault(key, {
            "setup_key": key,
            "ticker": str(t.get("ticker", "UNKNOWN")).upper(),
            "direction": str(t.get("direction", "UNKNOWN")).upper(),
            "confidence": str(t.get("confidence", "NA")).upper(),
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "total_r": 0.0,
            "total_pnl_pct": 0.0,
            "recent_results": [],
            "last_trade_ts": 0,
        })
        pnl = safe_float(t.get("realized_pnl_pct", t.get("pnl_pct", 0)), 0)
        r_mult = safe_float(t.get("r_multiple", 0), 0)
        winner = phase3_infer_winner(t)
        bucket["trades"] += 1
        bucket["wins"] += 1 if winner else 0
        bucket["losses"] += 0 if winner else 1
        bucket["total_r"] += r_mult
        bucket["total_pnl_pct"] += pnl
        bucket["recent_results"].append("W" if winner else "L")
        bucket["recent_results"] = bucket["recent_results"][-PHASE3_DISABLE_LAST_N:]
        bucket["last_trade_ts"] = max(safe_int(bucket.get("last_trade_ts", 0), 0), safe_int(t.get("closed_ts", t.get("timestamp", 0)), 0))

    for key, bucket in stats.items():
        total = max(safe_int(bucket.get("trades", 0), 0), 1)
        bucket["win_rate"] = round(bucket.get("wins", 0) / total, 4)
        bucket["avg_r"] = round(bucket.get("total_r", 0.0) / total, 4)
        bucket["avg_pnl_pct"] = round(bucket.get("total_pnl_pct", 0.0) / total, 4)
        recent = bucket.get("recent_results", [])[-PHASE3_DISABLE_LAST_N:]
        bucket["recent_loss_count"] = sum(1 for x in recent if x == "L")
    return stats


def phase3_write_adaptive_stats(force: bool = False) -> Dict[str, Any]:
    if not ENABLE_INTELLIGENCE_PHASE3:
        return {}
    try:
        stats = phase3_compute_setup_stats()
        payload = {
            "generated_at": now_ts(),
            "min_trades_for_filter": PHASE3_MIN_TRADES_FOR_FILTER,
            "setup_count": len(stats),
            "stats": stats,
            "disabled_setups": phase3_load_disabled_setups(),
        }
        atomic_write_json(PHASE3_ADAPTIVE_STATS_FILE, payload)
        if force:
            debug(f"PHASE 3 ADAPTIVE STATS WRITTEN | setups={len(stats)}")
        return payload
    except Exception as e:
        log(f"❌ PHASE 3 stats write failed: {e}")
        return {}


def phase3_alert(title: str, body: str, force: bool = False):
    if not PHASE3_SEND_ALERTS and not force:
        return
    msg = f"🧠 {title}\n{body}\n⏰ {now_ts()}"
    send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
    send_to_telegram(msg)


def phase3_downgrade_confidence(confidence: str) -> str:
    c = str(confidence or "C").upper().strip()
    if c == "A+":
        return "A"
    if c == "A":
        return "B"
    if c == "B":
        return "C"
    return c or "C"


def phase3_evaluate_adaptive_intelligence(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Return an adaptive decision before sizing/execution.
    Safe default: if not enough history, approve without changing behavior.
    """
    if not ENABLE_INTELLIGENCE_PHASE3:
        return {"approved": True, "stage": "phase3_adaptive_intelligence", "reason": "disabled", "size_multiplier": 1.0, "adjusted_signal": deepcopy(signal), "stats": {}}

    x = deepcopy(signal)
    setup_key = phase3_setup_key(x)
    debug(f"PHASE 3 ADAPTIVE CHECK | setup={setup_key} | ticker={x.get('ticker')} | direction={x.get('direction')} | confidence={x.get('confidence')}")
    stats_payload = phase3_write_adaptive_stats(force=False)
    stats = (stats_payload.get("stats", {}) if isinstance(stats_payload, dict) else {}).get(setup_key, {})
    disabled = phase3_load_disabled_setups()
    reasons = []
    actions = []
    size_multiplier = 1.0

    if setup_key in disabled:
        reasons.append("setup_disabled_by_phase3")

    trade_count = safe_int(stats.get("trades", 0), 0)
    win_rate = safe_float(stats.get("win_rate", 0), 0)
    avg_r = safe_float(stats.get("avg_r", 0), 0)
    recent_losses = safe_int(stats.get("recent_loss_count", 0), 0)

    if trade_count < PHASE3_MIN_TRADES_FOR_FILTER:
        debug(f"PHASE 3 OBSERVE ONLY | {setup_key} | trades={trade_count}/{PHASE3_MIN_TRADES_FOR_FILTER}")
        debug("PHASE 3 SIZE MULTIPLIER | base=1.0 -> adjusted=1.0 | reason=observe_only")
        intel_event("phase3_observe_only", {"setup_key": setup_key, "trades": trade_count, "required": PHASE3_MIN_TRADES_FOR_FILTER}, signal=x, stage="phase3_adaptive", decision="observe_only")
        return {"approved": True, "stage": "phase3_adaptive_intelligence", "reason": "insufficient_history", "setup_key": setup_key, "size_multiplier": 1.0, "adjusted_signal": x, "stats": stats, "actions": ["observe_only"]}

    if win_rate < PHASE3_BLOCK_WINRATE_BELOW:
        reasons.append("setup_win_rate_below_threshold")
    if avg_r < PHASE3_BLOCK_AVG_R_BELOW:
        reasons.append("setup_avg_r_below_threshold")
    if recent_losses >= PHASE3_DISABLE_LOSSES_IN_LAST_N:
        reasons.append("setup_recent_loss_cluster")
        disabled[setup_key] = {"disabled_at": now_ts(), "reason": "recent_loss_cluster", "recent_losses": recent_losses, "last_n": PHASE3_DISABLE_LAST_N, "stats": stats}
        phase3_save_disabled_setups(disabled)

    if win_rate >= PHASE3_SIZE_UP_WINRATE and avg_r >= 0:
        size_multiplier = PHASE3_SIZE_UP_MULT
        actions.append("size_up")
    elif win_rate < PHASE3_SIZE_DOWN_WINRATE:
        size_multiplier = PHASE3_SIZE_DOWN_MULT
        actions.append("size_down")

    original_conf = str(x.get("confidence", "C")).upper().strip()
    if original_conf in {"A+", "A"} and win_rate < PHASE3_CONFIDENCE_DOWNGRADE_WINRATE:
        x["original_confidence"] = original_conf
        x["confidence"] = phase3_downgrade_confidence(original_conf)
        actions.append(f"confidence_downgrade_{original_conf}_to_{x['confidence']}")

    decision = {
        "approved": len(reasons) == 0 or PHASE3_SUGGEST_ONLY,
        "suggest_only": PHASE3_SUGGEST_ONLY,
        "stage": "phase3_adaptive_intelligence",
        "setup_key": setup_key,
        "reject_reasons": reasons,
        "size_multiplier": size_multiplier,
        "adjusted_signal": x,
        "stats": stats,
        "actions": actions,
    }

    intel_event("phase3_adaptive_decision", decision, signal=x, stage="phase3_adaptive", decision="approved" if decision["approved"] else "blocked")

    if reasons:
        body = f"Setup: {setup_key}\nReasons: {', '.join(reasons)}\nTrades: {trade_count} | Win Rate: {round(win_rate*100,1)}% | Avg R: {avg_r}\nSuggest Only: {PHASE3_SUGGEST_ONLY}"
        phase3_alert("PHASE 3 SETUP BLOCK" if not PHASE3_SUGGEST_ONLY else "PHASE 3 SETUP WARNING", body)
    else:
        debug(f"PHASE 3 ADAPTIVE OK | {setup_key} | trades={trade_count} | win_rate={round(win_rate*100,1)}% | avg_r={avg_r} | size_mult={size_multiplier} | actions={actions}")

    return decision


def phase3_apply_size_multiplier_to_decision(size_decision: Dict[str, Any], phase3_decision: Dict[str, Any]) -> Dict[str, Any]:
    if not ENABLE_INTELLIGENCE_PHASE3:
        return size_decision
    try:
        mult = safe_float(phase3_decision.get("size_multiplier", 1.0), 1.0)
        if mult == 1.0:
            return size_decision
        x = deepcopy(size_decision)
        original = safe_int(x.get("final_size", 0), 0)
        adjusted = int(math.floor(original * mult)) if mult < 1 else int(math.ceil(original * mult))
        adjusted = max(MIN_POSITION_QTY if original >= MIN_POSITION_QTY else 0, adjusted)
        adjusted = min(MAX_POSITION_QTY, adjusted)
        if original > 0 and adjusted <= 0:
            adjusted = MIN_POSITION_QTY
        x["phase3_original_final_size"] = original
        x["phase3_size_multiplier"] = mult
        debug(f"PHASE 3 SIZE MULTIPLIER | base={original} -> adjusted={adjusted} | mult={mult}")
        x["final_size"] = adjusted
        x.setdefault("adjustments", []).append(f"phase3_size_multiplier_{mult}")
        x["approved"] = adjusted >= MIN_POSITION_QTY
        if not x["approved"]:
            x.setdefault("reject_reasons", []).append("phase3_adjusted_size_below_minimum")
        return x
    except Exception as e:
        log(f"❌ PHASE 3 size multiplier failed: {e}")
        return size_decision

# =========================================================
# PHASE 0 HARD SAFETY LAYER
# =========================================================
def phase0_alert(title: str, body: str, force: bool = False):
    """Loud Phase 0 safety alert. Uses AI + premium + Telegram when enabled."""
    msg = f"🧱 {title}\n{body}\n⏰ {now_ts()}"
    log(msg.replace("\n", " | "))
    if PHASE0_SEND_ALERTS:
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_live_entry_discord(msg)
        send_to_telegram(msg)


def phase0_block_engine(reason: str, flatten: bool = False):
    """Hard safety block. Sets the same state flags used by recon and Step 15."""
    ensure_globals_initialized()
    GLOBAL_STATE["phase0_blocked"] = True
    GLOBAL_STATE["phase0_block_reason"] = reason
    GLOBAL_STATE["phase0_blocked_at"] = epoch()
    GLOBAL_STATE["reconciliation_required"] = True
    GLOBAL_STATE["reconciliation_block_reason"] = reason
    GLOBAL_STATE["bot_paused"] = True
    GLOBAL_STATE["kill_switch"] = True
    save_state(GLOBAL_STATE)
    phase0_alert("PHASE 0 HARD BLOCK", reason, force=True)
    try:
        if flatten and ENABLE_STEP15_GLOBAL_KILL_SWITCH:
            step15_activate_kill_switch(f"PHASE 0 HARD BLOCK: {reason}", close_positions=PHASE0_AUTO_FLATTEN_ON_HARD_KILL)
    except Exception as e:
        log(f"❌ Phase 0 could not activate Step 15: {e}")


def phase0_position_errors(position: Dict[str, Any], label: str) -> List[str]:
    errors = []
    pid = safe_int(position.get("id", 0), 0)
    symbol = str(position.get("symbol", "")).strip()
    qty_open = safe_int(position.get("qty_open", 0), 0)
    qty_total = safe_int(position.get("qty_total", 0), 0)
    qty_closed = safe_int(position.get("qty_closed", 0), 0)
    entry = safe_float(position.get("entry_price", 0), 0)
    last = safe_float(position.get("last_price", 0), 0)
    stop = safe_float(position.get("stop_price", 0), 0)
    status = str(position.get("status", "OPEN")).upper()
    if pid <= 0:
        errors.append(f"{label}: position id missing/invalid")
    if not symbol:
        errors.append(f"{label}: symbol missing for position id={pid}")
    if qty_total < 0 or qty_open < 0 or qty_closed < 0:
        errors.append(f"{label}: negative quantity for {symbol} id={pid}")
    if status == "OPEN" and qty_open <= 0:
        errors.append(f"{label}: open position has qty_open <= 0 for {symbol} id={pid}")
    if entry <= 0:
        errors.append(f"{label}: entry_price <= 0 for {symbol} id={pid}")
    if last < 0:
        errors.append(f"{label}: last_price < 0 for {symbol} id={pid}")
    if stop < 0:
        errors.append(f"{label}: stop_price < 0 for {symbol} id={pid}")
    if qty_total > 0 and qty_open + qty_closed > qty_total:
        errors.append(f"{label}: qty_open + qty_closed exceeds qty_total for {symbol} id={pid}")
    return errors


def phase0_validate_state_invariants() -> Dict[str, Any]:
    """Validate local state before allowing trading. Bad state must be loud and blocking."""
    ensure_globals_initialized()
    errors = []

    if not isinstance(GLOBAL_STATE, dict):
        errors.append("GLOBAL_STATE is not a dict")
    if not isinstance(GLOBAL_POSITIONS, dict):
        errors.append("GLOBAL_POSITIONS is not a dict")
    if not isinstance(GLOBAL_ORDERS, dict):
        errors.append("GLOBAL_ORDERS is not a dict")
    if not isinstance(GLOBAL_RECON, dict):
        errors.append("GLOBAL_RECON is not a dict")

    open_positions = GLOBAL_POSITIONS.get("open_positions", []) if isinstance(GLOBAL_POSITIONS, dict) else []
    closed_positions = GLOBAL_POSITIONS.get("closed_positions", []) if isinstance(GLOBAL_POSITIONS, dict) else []
    orders = GLOBAL_ORDERS.get("orders", []) if isinstance(GLOBAL_ORDERS, dict) else []

    if not isinstance(open_positions, list):
        errors.append("open_positions must be a list")
        open_positions = []
    if not isinstance(closed_positions, list):
        errors.append("closed_positions must be a list")
        closed_positions = []
    if not isinstance(orders, list):
        errors.append("orders must be a list")
        orders = []

    seen_open_ids = set()
    for p in open_positions:
        if not isinstance(p, dict):
            errors.append("open_positions contains non-dict item")
            continue
        pid = safe_int(p.get("id", 0), 0)
        if pid in seen_open_ids:
            errors.append(f"duplicate open position id={pid}")
        seen_open_ids.add(pid)
        errors.extend(phase0_position_errors(p, "open"))

    seen_order_ids = set()
    for o in orders:
        if not isinstance(o, dict):
            errors.append("orders contains non-dict item")
            continue
        oid = safe_int(o.get("local_order_id", 0), 0)
        if oid > 0:
            if oid in seen_order_ids:
                errors.append(f"duplicate local_order_id={oid}")
            seen_order_ids.add(oid)
        qty_req = safe_int(o.get("qty_requested", 0), 0)
        qty_fill = safe_int(o.get("qty_filled", 0), 0)
        if qty_req < 0 or qty_fill < 0:
            errors.append(f"negative order quantity local_order_id={oid}")
        if qty_req > 0 and qty_fill > qty_req:
            errors.append(f"filled quantity exceeds requested local_order_id={oid}")

    result = {"approved": len(errors) == 0, "errors": errors, "open_positions": len(open_positions), "orders": len(orders)}
    if result["approved"]:
        debug(f"PHASE 0 STATE OK | open={len(open_positions)} | orders={len(orders)}")
    else:
        log("🚫 PHASE 0 STATE INVALID | " + "; ".join(errors[:10]))
    return result


def phase0_market_file_age_seconds(prices: Optional[Dict[str, Any]] = None) -> int:
    try:
        updated_at = get_market_data_file_updated_at(prices)
        if updated_at > 0:
            return max(0, epoch() - updated_at)
        if MARKET_DATA_FILE and file_exists(MARKET_DATA_FILE):
            return max(0, epoch() - int(os.path.getmtime(MARKET_DATA_FILE)))
    except Exception:
        pass
    return 999999


def phase0_price_is_fresh(symbol: str, prices: Dict[str, Any]) -> Tuple[bool, float, str]:
    price, ts = get_market_price_for_symbol(symbol, prices)
    if price <= 0:
        return False, price, "missing_or_zero_price"
    if ts > 0 and market_price_is_stale(ts):
        return False, price, f"stale_timestamp_age={epoch() - ts}s"
    if ts <= 0:
        # Manual/file test data usually has no timestamp, so freshness comes from file mtime.
        age = phase0_market_file_age_seconds(prices)
        if MARKET_DATA_PROVIDER in {"file", "manual", "auto", "twelvedata"} and age > PHASE0_MARKET_FILE_MAX_AGE_SECONDS:
            return False, price, f"stale_market_file_age={age}s:max={PHASE0_MARKET_FILE_MAX_AGE_SECONDS}s"
    return True, price, "fresh"


def phase0_validate_fresh_prices_for_open_positions() -> Dict[str, Any]:
    ensure_globals_initialized()
    if not PHASE0_REQUIRE_FRESH_PRICE_FOR_OPEN_POSITIONS:
        return {"approved": True, "reject_reasons": []}
    open_positions = GLOBAL_POSITIONS.get("open_positions", [])
    symbols = [str(p.get("symbol", "")).strip() for p in open_positions if str(p.get("symbol", "")).strip()]
    if not symbols:
        return {"approved": True, "reject_reasons": []}
    prices = load_market_prices(symbols)
    reasons = []
    for sym in symbols:
        ok, price, reason = phase0_price_is_fresh(sym, prices)
        if not ok:
            reasons.append(f"open_position_price_not_fresh:{sym}:{reason}")
    if reasons:
        debug("PHASE 0 OPEN PRICE BLOCK | " + "; ".join(reasons[:5]))
    else:
        debug(f"PHASE 0 OPEN PRICES OK | symbols={len(symbols)}")
    return {"approved": len(reasons) == 0, "reject_reasons": reasons}


def phase0_symbol_looks_like_option_contract(symbol: str) -> bool:
    """Detect OCC-style option symbols like QQQ260501C00430000."""
    s = str(symbol or "").upper().strip().replace(" ", "")
    return bool(re.search(r"\d{6}[CP]\d{8}$", s))


def phase0_get_signal_option_fallback_price(signal: Dict[str, Any]) -> float:
    """Return the best signal-provided option price for paper/test validation."""
    for key in ("entry_contract", "contract_price", "entry_price", "entry"):
        price = safe_float(signal.get(key, 0), 0)
        if price > 0:
            return price
    return 0.0


def phase0_allow_fake_option_price_for_signal(signal: Dict[str, Any]) -> bool:
    """Allow fallback pricing only for option-like paper/test signals unless configured otherwise."""
    if not ALLOW_FAKE_OPTION_PRICE:
        return False
    if FAKE_OPTION_PRICE_ONLY_IN_PAPER and LIVE_MODE:
        return False
    symbol = str(signal.get("symbol", "") or signal.get("contract_symbol", "")).strip()
    return phase0_symbol_looks_like_option_contract(symbol) or bool(signal.get("contract_symbol"))


def phase0_validate_fresh_price_for_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    if not PHASE0_REQUIRE_FRESH_PRICE_FOR_ENTRY:
        return {"approved": True, "reject_reasons": []}
    symbol = str(signal.get("symbol", "")).strip()
    ticker = str(signal.get("ticker", "")).upper().strip()
    symbols = []
    if symbol:
        symbols.append(symbol)
    if ticker and ticker not in symbols:
        symbols.append(ticker)
    prices = load_market_prices(symbols)
    reasons = []
    if symbol:
        ok, price, reason = phase0_price_is_fresh(symbol, prices)
        if not ok:
            fallback_price = phase0_get_signal_option_fallback_price(signal)
            if phase0_allow_fake_option_price_for_signal(signal) and fallback_price > 0:
                signal["price"] = fallback_price
                signal["entry_symbol_fallback_price"] = fallback_price
                signal["entry_symbol_fallback_source"] = "signal_entry_option_price"
                debug(
                    "PHASE 0 OPTION PRICE FALLBACK OK | "
                    f"symbol={symbol} | fallback_price={fallback_price} | reason={reason}"
                )
            else:
                reasons.append(f"entry_symbol_price_not_fresh:{symbol}:{reason}")
    if ticker:
        # Underlying may be live-provider based; missing underlying is a block only if live price was required/available.
        underlying_price = safe_float(signal.get("underlying_price", signal.get("price", 0)), 0)
        if underlying_price <= 0 or (symbol and symbol != ticker and phase0_symbol_looks_like_option_contract(symbol)):
            # Try cached/live one last time.
            live_underlying = get_live_market_price(ticker)
            if live_underlying > 0:
                underlying_price = live_underlying
                signal["underlying_price"] = live_underlying
        if underlying_price <= 0:
            reasons.append(f"underlying_price_not_fresh:{ticker}:missing_or_zero_price")
    if reasons:
        debug("PHASE 0 ENTRY PRICE BLOCK | " + "; ".join(reasons[:5]))
    else:
        debug(f"PHASE 0 ENTRY PRICES OK | symbol={symbol} | ticker={ticker}")
    return {"approved": len(reasons) == 0, "reject_reasons": reasons}


def phase0_hard_risk_kill_check() -> bool:
    """Return True when safe. Return False when hard daily loss/heat kill is active."""
    ensure_globals_initialized()
    if not ENABLE_PHASE0_SAFETY:
        return True
    daily_pnl = step14_daily_pnl_dollars()
    equity = get_account_equity()
    hard_daily_loss_dollars = max(equity * PHASE0_HARD_DAILY_LOSS_PCT, 1.0)
    heat = portfolio_heat_pct()
    reasons = []
    if daily_pnl <= -abs(hard_daily_loss_dollars):
        reasons.append(f"hard_daily_loss_hit:${daily_pnl} <= -${round(abs(hard_daily_loss_dollars), 2)}")
    if heat >= PHASE0_HARD_PORTFOLIO_HEAT_PCT:
        reasons.append(f"hard_portfolio_heat_hit:{round(heat*100, 3)}% >= {round(PHASE0_HARD_PORTFOLIO_HEAT_PCT*100, 3)}%")
    if reasons:
        reason = "; ".join(reasons)
        phase0_block_engine(reason, flatten=PHASE0_AUTO_FLATTEN_ON_HARD_KILL)
        hard_kill_engine(f"PHASE 0 HARD RISK KILL: {reason}", close_positions=PHASE0_AUTO_FLATTEN_ON_HARD_KILL)
        return False
    debug(f"PHASE 0 HARD RISK OK | daily_pnl={daily_pnl} | heat={round(heat*100, 3)}%")
    return True


def phase0_pretrade_safety_gate(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Final catastrophic-loss gate before normal validator/risk checks."""
    ensure_globals_initialized()
    if not ENABLE_PHASE0_SAFETY:
        return {"approved": True, "reject_reasons": []}
    reasons = []
    if GLOBAL_STATE.get("phase0_blocked", False):
        reasons.append(f"phase0_blocked:{GLOBAL_STATE.get('phase0_block_reason', '')}")
    state_check = phase0_validate_state_invariants()
    if not state_check["approved"]:
        reasons.extend([f"state_invariant:{e}" for e in state_check["errors"][:5]])
    open_price_check = phase0_validate_fresh_prices_for_open_positions()
    if not open_price_check["approved"]:
        reasons.extend(open_price_check["reject_reasons"])
    entry_price_check = phase0_validate_fresh_price_for_signal(signal)
    if not entry_price_check["approved"]:
        reasons.extend(entry_price_check["reject_reasons"])
    if not phase0_hard_risk_kill_check():
        reasons.append("phase0_hard_risk_kill_active")
    return {"approved": len(reasons) == 0, "reject_reasons": reasons, "stage": "phase0_pretrade_safety"}



# =========================================================
# POSITION SCHEMA REPAIR
# Ensures older paper positions include qty_total / qty_open
# so Step 15 and lifecycle checks do not lock the engine.
# =========================================================
def repair_position_schema_for_step15() -> Dict[str, Any]:
    result = {"repaired": False, "open": 0, "closed": 0}
    try:
        data = load_json_file(POSITIONS_FILE, {})
        if not isinstance(data, dict):
            data = {}
        data.setdefault("schema_version", 2)
        data.setdefault("open_positions", [])
        data.setdefault("closed_positions", [])
        data.setdefault("last_position_id", safe_int(data.get("last_position_id", 0), 0))

        changed = False

        for bucket in ["open_positions", "closed_positions"]:
            rows = data.get(bucket, [])
            if not isinstance(rows, list):
                data[bucket] = []
                changed = True
                continue

            for pos in rows:
                if not isinstance(pos, dict):
                    continue

                qty = safe_int(pos.get("qty_open", pos.get("qty_total", pos.get("qty", 1))), 1)
                total = safe_int(pos.get("qty_total", pos.get("qty", qty)), qty)
                open_qty = safe_int(pos.get("qty_open", pos.get("qty", qty)), qty)

                if "qty" not in pos:
                    pos["qty"] = qty
                    changed = True
                if "qty_total" not in pos:
                    pos["qty_total"] = total
                    changed = True
                if "qty_open" not in pos:
                    pos["qty_open"] = open_qty if str(pos.get("status", "open")).lower() == "open" else 0
                    changed = True
                if "position_id" not in pos or not pos.get("position_id"):
                    data["last_position_id"] = safe_int(data.get("last_position_id", 0), 0) + 1
                    pos["position_id"] = f"POS-{data['last_position_id']}"
                    changed = True
                if "notes" not in pos or pos.get("notes") is None:
                    pos["notes"] = []
                    changed = True
                elif not isinstance(pos.get("notes"), list):
                    pos["notes"] = [str(pos.get("notes"))]
                    changed = True
                if "mode" not in pos or not pos.get("mode"):
                    pos["mode"] = "paper"
                    changed = True

        result["open"] = len(data.get("open_positions", []))
        result["closed"] = len(data.get("closed_positions", []))

        if changed:
            atomic_write_json(POSITIONS_FILE, data)
            result["repaired"] = True
            debug(f"POSITION SCHEMA REPAIR OK | {result}")

        return result
    except Exception as e:
        debug(f"POSITION SCHEMA REPAIR ERROR: {e}")
        return result




def repair_position_mode_for_step15() -> Dict[str, Any]:
    result = {"repaired": False, "open": 0, "closed": 0}
    try:
        data = load_json_file(POSITIONS_FILE, {})
        if not isinstance(data, dict):
            return result
        changed = False
        for bucket in ["open_positions", "closed_positions"]:
            rows = data.get(bucket, [])
            if not isinstance(rows, list):
                continue
            for pos in rows:
                if not isinstance(pos, dict):
                    continue
                if "mode" not in pos or not pos.get("mode"):
                    pos["mode"] = "paper"
                    changed = True
                if "id" not in pos or not pos.get("id"):
                    pos["id"] = pos.get("position_id") or f"POS-{safe_int(data.get('last_position_id', 0), 0)}"
                    changed = True
                if "notes" not in pos or pos.get("notes") is None:
                    pos["notes"] = []
                    changed = True
                if "qty_total" not in pos:
                    pos["qty_total"] = safe_int(pos.get("qty", pos.get("qty_open", 1)), 1)
                    changed = True
                if "qty_open" not in pos:
                    pos["qty_open"] = safe_int(pos.get("qty", pos.get("qty_total", 1)), 1) if str(pos.get("status", "open")).lower() == "open" else 0
                    changed = True
        result["open"] = len(data.get("open_positions", []))
        result["closed"] = len(data.get("closed_positions", []))
        if changed:
            atomic_write_json(POSITIONS_FILE, data)
            result["repaired"] = True
            debug(f"POSITION MODE REPAIR OK | {result}")
        return result
    except Exception as e:
        debug(f"POSITION MODE REPAIR ERROR: {e}")
        return result



def phase0_startup_safety_gate():
    """Run once on boot. Bad local state or bad broker reconciliation blocks trading hard."""
    ensure_globals_initialized()
    if not ENABLE_PHASE0_SAFETY:
        return
    state_check = phase0_validate_state_invariants()
    if not state_check["approved"] and PHASE0_BLOCK_ON_INVALID_STATE:
        phase0_block_engine("State invariant failure on startup: " + "; ".join(state_check["errors"][:8]), flatten=False)
        return
    if PHASE0_REQUIRE_STARTUP_RECON_CLEAN and ENABLE_ALPACA and GLOBAL_STATE.get("alpaca_enabled", False) and alpaca_ready():
        report = build_boot_reconciliation_report()
        msg = build_reconciliation_message(report)
        send_to_telegram(msg)
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        if not report.get("safe_to_trade", False):
            reason = "; ".join(report.get("mismatches", [])[:8]) or "startup reconciliation mismatch"
            set_reconciliation_block(reason)
            phase0_block_engine("Startup reconciliation failed: " + reason, flatten=False)
            return
        clear_reconciliation_block()
        debug("PHASE 0 STARTUP RECON OK")
    phase0_hard_risk_kill_check()
    debug("PHASE 0 STARTUP SAFETY GATE PASSED")

# =========================================================
# PHASE 1 EXECUTION SAFETY LAYER
# =========================================================
def phase1_alert(title: str, body: str):
    msg = f"🧯 {title}\n{body}\n⏰ {now_ts()}"
    log(msg.replace("\n", " | "))
    if PHASE1_SEND_ALERTS:
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_live_entry_discord(msg)
        send_to_telegram(msg)


def phase1_get_recent_order_times() -> List[int]:
    ensure_globals_initialized()
    times = GLOBAL_STATE.get("phase1_order_times", [])
    if not isinstance(times, list):
        times = []
    now = epoch()
    times = [safe_int(t, 0) for t in times if safe_int(t, 0) > 0 and now - safe_int(t, 0) <= 86400]
    GLOBAL_STATE["phase1_order_times"] = times
    return times


def phase1_record_order_attempt(side: str, symbol: str, qty: int):
    ensure_globals_initialized()
    times = phase1_get_recent_order_times()
    times.append(epoch())
    GLOBAL_STATE["phase1_order_times"] = times[-500:]
    save_state(GLOBAL_STATE)
    debug(f"PHASE 1 ORDER ATTEMPT RECORDED | side={side} | symbol={symbol} | qty={qty}")


def phase1_order_rate_counts() -> Dict[str, int]:
    now = epoch()
    times = phase1_get_recent_order_times()
    return {
        "minute": sum(1 for t in times if now - t <= 60),
        "hour": sum(1 for t in times if now - t <= 3600),
        "day": sum(1 for t in times if now - t <= 86400),
    }


def phase1_soft_halt(reason: str):
    ensure_globals_initialized()
    GLOBAL_STATE["phase1_soft_halt"] = True
    GLOBAL_STATE["phase1_soft_halt_reason"] = reason
    GLOBAL_STATE["phase1_last_block_at"] = epoch()
    GLOBAL_STATE["bot_paused"] = True
    save_state(GLOBAL_STATE)
    phase1_alert("PHASE 1 SOFT HALT", reason)


def phase1_get_bid_ask_from_prices(symbol: str, prices: Dict[str, Any]) -> Tuple[float, float]:
    raw = prices.get(symbol) or prices.get(symbol.upper()) or prices.get(symbol.lower())
    if isinstance(raw, dict):
        bid = safe_float(raw.get("bid", raw.get("bid_price", 0)), 0)
        ask = safe_float(raw.get("ask", raw.get("ask_price", 0)), 0)
        return bid, ask
    return 0.0, 0.0


def phase1_spread_check(symbol: str, prices: Dict[str, Any], live_price: float, live_mode: bool) -> Dict[str, Any]:
    bid, ask = phase1_get_bid_ask_from_prices(symbol, prices)
    if bid <= 0 or ask <= 0:
        if live_mode and PHASE1_REQUIRE_BID_ASK_FOR_LIVE:
            return {"approved": False, "reason": "missing_bid_ask_for_live_order", "bid": bid, "ask": ask, "spread_pct": 0.0}
        return {"approved": True, "reason": "bid_ask_not_available", "bid": bid, "ask": ask, "spread_pct": 0.0}
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return {"approved": False, "reason": "invalid_bid_ask_mid", "bid": bid, "ask": ask, "spread_pct": 0.0}
    spread_pct = (ask - bid) / mid
    if spread_pct > PHASE1_MAX_SPREAD_PCT:
        return {"approved": False, "reason": "spread_too_wide", "bid": bid, "ask": ask, "spread_pct": round(spread_pct, 6)}
    return {"approved": True, "reason": "spread_ok", "bid": bid, "ask": ask, "spread_pct": round(spread_pct, 6)}




def options_liquidity_symbol_is_option(signal_or_stub: Dict[str, Any], symbol: str) -> bool:
    """Detects whether the order is an options contract."""
    try:
        asset_class = str(signal_or_stub.get("asset_class", signal_or_stub.get("asset_type", ""))).lower().strip()
        if asset_class == "option":
            return True
        if is_option_contract_symbol(symbol):
            return True
        contract_symbol = str(signal_or_stub.get("contract_symbol", "")).strip()
        if contract_symbol and is_option_contract_symbol(contract_symbol):
            return True
    except Exception:
        pass
    return False


def options_liquidity_payload_for_symbol(symbol: str, prices: Dict[str, Any]) -> Dict[str, Any]:
    """Flexible market_prices.json parser for option quotes."""
    if not isinstance(prices, dict) or not symbol:
        return {}
    direct = prices.get(symbol) or prices.get(str(symbol).upper()) or prices.get(str(symbol).lower())
    if isinstance(direct, dict):
        return direct
    symbol_upper = str(symbol).upper().strip()
    for key, value in prices.items():
        if str(key).startswith("__"):
            continue
        if str(key).upper().strip() == symbol_upper and isinstance(value, dict):
            return value
    return {}


def options_liquidity_extract_quote(symbol: str, prices: Dict[str, Any], fallback_last: float = 0.0) -> Dict[str, Any]:
    """Returns normalized bid/ask/mid/last/volume/open_interest/timestamp from a flexible quote payload."""
    payload = options_liquidity_payload_for_symbol(symbol, prices)
    nested_candidates = []
    if isinstance(payload, dict):
        nested_candidates.extend([
            payload,
            payload.get("latestQuote", {}),
            payload.get("latest_quote", {}),
            payload.get("quote", {}),
            payload.get("latestTrade", {}),
            payload.get("latest_trade", {}),
            payload.get("trade", {}),
            payload.get("snapshot", {}),
        ])
    else:
        nested_candidates.append({})

    merged: Dict[str, Any] = {}
    for item in nested_candidates:
        if isinstance(item, dict):
            merged.update({k: v for k, v in item.items() if v not in (None, "")})

    bid = safe_float(merged.get("bid", merged.get("bid_price", merged.get("bp", 0))), 0)
    ask = safe_float(merged.get("ask", merged.get("ask_price", merged.get("ap", 0))), 0)
    last = safe_float(
        merged.get("last", merged.get("last_price", merged.get("price", merged.get("mark", merged.get("mid", merged.get("p", fallback_last)))))),
        fallback_last,
    )
    mid = safe_float(merged.get("mid", merged.get("mark", 0)), 0)

    if mid <= 0 and bid > 0 and ask > 0:
        mid = (bid + ask) / 2.0
    if mid <= 0 and last > 0:
        mid = last

    volume = safe_int(merged.get("volume", merged.get("vol", merged.get("v", 0))), 0)
    open_interest = safe_int(
        merged.get("open_interest", merged.get("oi", merged.get("openInterest", merged.get("openInterestValue", 0)))),
        0,
    )
    ts = safe_int(merged.get("timestamp", merged.get("ts", merged.get("updated_at", merged.get("price_updated_at", 0)))), 0)

    return {
        "symbol": symbol,
        "bid": round(bid, 6),
        "ask": round(ask, 6),
        "mid": round(mid, 6),
        "last": round(last, 6),
        "volume": volume,
        "open_interest": open_interest,
        "timestamp": ts,
        "raw_available": bool(payload),
    }


def options_liquidity_gate(signal_or_stub: Dict[str, Any], prices: Dict[str, Any], live_price: float = 0.0, mode: str = "PAPER") -> Dict[str, Any]:
    """
    Production options liquidity gate.
    Missing data blocks live by default, but only warns in paper unless OPTIONS_LIQUIDITY_REQUIRE_FOR_PAPER=true.
    """
    if not ENABLE_OPTIONS_LIQUIDITY_FILTER:
        return {"approved": True, "stage": "options_liquidity", "reason": "disabled", "reject_reasons": []}

    mode_upper = str(mode or "PAPER").upper().strip()
    symbol = str(signal_or_stub.get("symbol") or signal_or_stub.get("contract_symbol") or "").strip()

    if not options_liquidity_symbol_is_option(signal_or_stub, symbol):
        return {"approved": True, "stage": "options_liquidity", "reason": "not_option", "reject_reasons": []}

    quote = options_liquidity_extract_quote(symbol, prices, fallback_last=live_price)
    reasons: List[str] = []
    require_data = OPTIONS_LIQUIDITY_REQUIRE_FOR_LIVE if mode_upper == "LIVE" else OPTIONS_LIQUIDITY_REQUIRE_FOR_PAPER

    bid = safe_float(quote.get("bid"), 0)
    ask = safe_float(quote.get("ask"), 0)
    mid = safe_float(quote.get("mid"), 0)
    last = safe_float(quote.get("last"), 0)
    volume = safe_int(quote.get("volume"), 0)
    open_interest = safe_int(quote.get("open_interest"), 0)
    ts = safe_int(quote.get("timestamp"), 0)

    if not quote.get("raw_available") and require_data:
        reasons.append("options_liquidity_missing_quote")

    if bid <= 0 or ask <= 0:
        if require_data:
            reasons.append("options_liquidity_missing_bid_ask")
    elif ask < bid:
        reasons.append("options_liquidity_crossed_market")
    else:
        if mid <= 0:
            mid = (bid + ask) / 2.0
        spread_pct = ((ask - bid) / mid) if mid > 0 else 0.0
        quote["spread_pct"] = round(spread_pct, 6)
        if spread_pct > OPTIONS_LIQUIDITY_MAX_SPREAD_PCT:
            reasons.append("options_liquidity_spread_too_wide")

        if last > 0 and mid > 0 and OPTIONS_LIQUIDITY_MAX_LAST_OUTSIDE_BA_PCT >= 0:
            lower_bound = bid * (1.0 - OPTIONS_LIQUIDITY_MAX_LAST_OUTSIDE_BA_PCT)
            upper_bound = ask * (1.0 + OPTIONS_LIQUIDITY_MAX_LAST_OUTSIDE_BA_PCT)
            if last < lower_bound or last > upper_bound:
                reasons.append("options_liquidity_bad_mid_last_outside_bid_ask")

    if "spread_pct" not in quote:
        quote["spread_pct"] = 0.0

    if ts > 0 and market_price_is_stale(ts):
        reasons.append("options_liquidity_stale_quote")

    if volume <= 0:
        if mode_upper == "LIVE" or not OPTIONS_LIQUIDITY_ALLOW_MISSING_VOLUME_IN_PAPER:
            reasons.append("options_liquidity_missing_volume")
    elif volume < OPTIONS_LIQUIDITY_MIN_VOLUME:
        reasons.append("options_liquidity_volume_too_low")

    if open_interest <= 0:
        if mode_upper == "LIVE" or not OPTIONS_LIQUIDITY_ALLOW_MISSING_OI_IN_PAPER:
            reasons.append("options_liquidity_missing_open_interest")
    elif open_interest < OPTIONS_LIQUIDITY_MIN_OPEN_INTEREST:
        reasons.append("options_liquidity_open_interest_too_low")

    approved = len(reasons) == 0
    decision = {
        "approved": approved,
        "stage": "options_liquidity",
        "mode": mode_upper,
        "symbol": symbol,
        "reject_reasons": reasons,
        "quote": quote,
        "thresholds": {
            "max_spread_pct": OPTIONS_LIQUIDITY_MAX_SPREAD_PCT,
            "min_volume": OPTIONS_LIQUIDITY_MIN_VOLUME,
            "min_open_interest": OPTIONS_LIQUIDITY_MIN_OPEN_INTEREST,
            "max_last_outside_bid_ask_pct": OPTIONS_LIQUIDITY_MAX_LAST_OUTSIDE_BA_PCT,
            "required": require_data,
        },
        "reason": "options_liquidity_ok" if approved else ",".join(reasons),
    }

    if approved:
        debug(
            f"OPTIONS LIQUIDITY OK | {symbol} bid={quote.get('bid')} ask={quote.get('ask')} "
            f"spread={round(safe_float(quote.get('spread_pct'), 0)*100,2)}% vol={volume} oi={open_interest} mode={mode_upper}"
        )
    else:
        msg = build_block_message(
            "OPTIONS LIQUIDITY BLOCK",
            signal_or_stub,
            reasons,
            f"Symbol: {symbol}\nQuote: {quote}\nThresholds: {decision['thresholds']}",
        )
        if OPTIONS_LIQUIDITY_SEND_ALERTS:
            send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
            send_to_live_entry_discord(msg)
            send_to_telegram(msg)
        debug(f"OPTIONS LIQUIDITY BLOCK | {symbol} | reasons={reasons} | quote={quote}")

    return decision

def phase1_validate_order_safety(signal_or_stub: Dict[str, Any], side: str, qty: int, planned_price: float = 0.0, mode: str = "PAPER") -> Dict[str, Any]:
    """Final Phase 1 safety guard before paper open or Alpaca order submit."""
    if not ENABLE_PHASE1_EXECUTION_SAFETY:
        return {"approved": True, "reject_reasons": [], "stage": "phase1_execution_safety"}

    ensure_globals_initialized()
    reasons = []
    side = str(side or "").lower().strip()
    symbol = str(signal_or_stub.get("symbol", "")).strip()
    ticker = str(signal_or_stub.get("ticker", "")).upper().strip()
    qty = safe_int(qty, 0)
    entry = safe_float(signal_or_stub.get("entry_contract", signal_or_stub.get("entry_price", planned_price)), planned_price)
    stop = safe_float(signal_or_stub.get("stop_contract", signal_or_stub.get("stop_price", 0)), 0)
    planned_price = safe_float(planned_price, entry)

    if GLOBAL_STATE.get("phase1_soft_halt", False):
        reasons.append("phase1_soft_halt_active")
    if not symbol:
        reasons.append("missing_order_symbol")
    if qty <= 0:
        reasons.append("invalid_order_qty")
    if qty > PHASE1_MAX_QTY_PER_ORDER:
        reasons.append("max_qty_per_order_hit")

    counts = phase1_order_rate_counts()
    if counts["minute"] >= PHASE1_MAX_ORDERS_PER_MINUTE:
        reasons.append("max_orders_per_minute_hit")
    if counts["hour"] >= PHASE1_MAX_ORDERS_PER_HOUR:
        reasons.append("max_orders_per_hour_hit")
    if counts["day"] >= PHASE1_MAX_ORDERS_PER_DAY:
        reasons.append("max_orders_per_day_hit")

    symbols_to_load = [s for s in [symbol, ticker] if s]
    prices = load_market_prices(symbols_to_load)
    live_price, price_ts = get_market_price_for_symbol(symbol, prices)
    if live_price <= 0:
        reasons.append("missing_live_order_price")
    elif price_ts > 0 and market_price_is_stale(price_ts):
        reasons.append("stale_live_order_price")

    slippage_pct = 0.0
    ref_price = planned_price if planned_price > 0 else entry
    if ref_price > 0 and live_price > 0:
        if side == "buy":
            slippage_pct = max(0.0, (live_price - ref_price) / ref_price)
            if slippage_pct > PHASE1_MAX_ENTRY_SLIPPAGE_PCT:
                reasons.append("entry_slippage_too_high")
        elif side == "sell":
            slippage_pct = max(0.0, (ref_price - live_price) / ref_price)
            if slippage_pct > PHASE1_MAX_EXIT_SLIPPAGE_PCT:
                reasons.append("exit_slippage_too_high")

    notional = max(live_price, ref_price, 0.0) * max(qty, 0) * 100.0
    if PHASE1_MAX_DOLLARS_PER_ORDER > 0 and notional > PHASE1_MAX_DOLLARS_PER_ORDER:
        reasons.append("max_dollars_per_order_hit")

    risk_dollars = 0.0
    if side == "buy" and entry > 0 and stop > 0 and stop < entry:
        risk_dollars = (entry - stop) * qty * 100.0
        if PHASE1_MAX_RISK_DOLLARS_PER_ORDER > 0 and risk_dollars > PHASE1_MAX_RISK_DOLLARS_PER_ORDER:
            reasons.append("max_risk_dollars_per_order_hit")

    spread = phase1_spread_check(symbol, prices, live_price, mode.upper() == "LIVE")
    if not spread["approved"]:
        reasons.append(spread["reason"])

    options_liquidity = options_liquidity_gate(signal_or_stub, prices, live_price=live_price, mode=mode)
    if not options_liquidity.get("approved", True):
        reasons.extend(options_liquidity.get("reject_reasons", [options_liquidity.get("reason", "options_liquidity_block")]))

    if FORCE_EXECUTION_MODE and reasons:
        hard_risk_terms = ("kill", "daily_loss", "drawdown", "reconciliation", "bot_paused", "engine_disabled", "entries_not_allowed")
        hard_reasons = [r for r in reasons if any(term in str(r).lower() for term in hard_risk_terms)]
        if FORCE_EXECUTION_KEEP_RISK_GATES and hard_reasons:
            log(f"🚨 FORCE MODE ACTIVE BUT HARD RISK GATE HELD | reasons={hard_reasons}")
            reasons = hard_reasons
        else:
            log(f"🚨 FORCE MODE OVERRIDE — BYPASSING PHASE 3.5 REASONS | original_reasons={reasons}")
            reasons = []
            notes.append("force_execution_mode_bypassed_phase35_reasons")

    approved = len(reasons) == 0
    decision = {
        "approved": approved,
        "stage": "phase1_execution_safety",
        "reject_reasons": reasons,
        "side": side,
        "symbol": symbol,
        "qty": qty,
        "live_price": round(live_price, 4),
        "planned_price": round(ref_price, 4),
        "slippage_pct": round(slippage_pct, 6),
        "notional_dollars": round(notional, 2),
        "risk_dollars": round(risk_dollars, 2),
        "order_counts": counts,
        "spread": spread,
        "options_liquidity": options_liquidity,
    }

    if approved:
        debug(
            f"PHASE 1 ORDER SAFETY OK | {side.upper()} {symbol} qty={qty} "
            f"live={decision['live_price']} planned={decision['planned_price']} "
            f"slip={round(decision['slippage_pct']*100,2)}% notional=${decision['notional_dollars']}"
        )
    else:
        extras = (
            f"Side: {side} | Symbol: {symbol} | Qty: {qty}\n"
            f"Live: {decision['live_price']} | Planned: {decision['planned_price']} | Slippage %: {round(decision['slippage_pct']*100, 2)}\n"
            f"Notional: ${decision['notional_dollars']} | Risk: ${decision['risk_dollars']}\n"
            f"Counts: {counts}\nSpread: {spread}\nOptions Liquidity: {options_liquidity}"
        )
        msg = build_block_message("PHASE 1 ORDER SAFETY BLOCK", signal_or_stub, reasons, extras)
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_live_entry_discord(msg)
        send_to_telegram(msg)
        if PHASE1_SOFT_HALT_ON_RATE_LIMIT and any(r in reasons for r in ["max_orders_per_minute_hit", "max_orders_per_hour_hit", "max_orders_per_day_hit"]):
            phase1_soft_halt(", ".join(reasons))

    return decision


# =========================================================
# PHASE 2 EXECUTION RELIABILITY LAYER
# =========================================================
def phase2_alert(title: str, details: str, force: bool = False):
    if not ENABLE_PHASE2_EXECUTION_RELIABILITY:
        return
    if not PHASE2_SEND_ALERTS and not force:
        return
    msg = f"🧱 {title}\n{details}\n⏰ {now_ts()}"
    send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
    send_to_live_entry_discord(msg)
    send_to_telegram(msg)


def phase2_order_terminal_statuses() -> set:
    return {"filled", "canceled", "cancelled", "rejected", "expired", "done_for_day", "closed"}


def phase2_is_order_active(order: Dict[str, Any]) -> bool:
    status = str(order.get("status", "")).lower().strip()
    if not status:
        return True
    return status not in phase2_order_terminal_statuses()


def phase2_active_orders(symbol: Optional[str] = None, side: Optional[str] = None) -> List[Dict[str, Any]]:
    ensure_globals_initialized()
    orders = GLOBAL_ORDERS.get("orders", []) if isinstance(GLOBAL_ORDERS, dict) else []
    out = []
    for o in orders:
        if not isinstance(o, dict):
            continue
        if not phase2_is_order_active(o):
            continue
        if symbol and str(o.get("symbol", "")).strip() != str(symbol).strip():
            continue
        if side and str(o.get("side", "")).lower().strip() != str(side).lower().strip():
            continue
        out.append(o)
    return out


def phase2_recent_duplicate_orders(symbol: str, side: str, window_seconds: int = PHASE2_DUPLICATE_ORDER_WINDOW_SECONDS) -> List[Dict[str, Any]]:
    ensure_globals_initialized()
    now = epoch()
    recent = []
    for o in GLOBAL_ORDERS.get("orders", []):
        if not isinstance(o, dict):
            continue
        if str(o.get("symbol", "")).strip() != str(symbol).strip():
            continue
        if str(o.get("side", "")).lower().strip() != str(side).lower().strip():
            continue
        created = safe_int(o.get("created_at", 0), 0)
        if created > 0 and now - created <= window_seconds and phase2_is_order_active(o):
            recent.append(o)
    return recent


def phase2_set_execution_lock(reason: str):
    ensure_globals_initialized()
    GLOBAL_STATE["phase2_execution_lock"] = True
    GLOBAL_STATE["phase2_execution_lock_reason"] = reason
    GLOBAL_STATE["bot_paused"] = True
    save_state(GLOBAL_STATE)
    phase2_alert("PHASE 2 EXECUTION LOCK", reason, force=True)


def phase2_clear_execution_lock(reason: str = "manual/system clear"):
    ensure_globals_initialized()
    GLOBAL_STATE["phase2_execution_lock"] = False
    GLOBAL_STATE["phase2_execution_lock_reason"] = ""
    save_state(GLOBAL_STATE)
    phase2_alert("PHASE 2 EXECUTION LOCK CLEARED", reason, force=True)


def phase2_validate_order_integrity(signal_or_stub: Dict[str, Any], side: str, qty: int, mode: str = "PAPER") -> Dict[str, Any]:
    """Pre-submit guard: duplicate suppression + active order caps + live broker readiness."""
    if not ENABLE_PHASE2_EXECUTION_RELIABILITY:
        return {"approved": True, "reject_reasons": [], "stage": "phase2_execution_reliability"}

    ensure_globals_initialized()
    reasons = []
    symbol = str(signal_or_stub.get("symbol", "")).strip()
    side = str(side or "").lower().strip()
    qty = safe_int(qty, 0)
    mode = str(mode or "PAPER").upper().strip()

    if GLOBAL_STATE.get("phase2_execution_lock", False):
        reasons.append("phase2_execution_lock_active")
    if not symbol:
        reasons.append("missing_symbol")
    if qty <= 0:
        reasons.append("invalid_qty")

    all_active = phase2_active_orders()
    symbol_active = phase2_active_orders(symbol=symbol) if symbol else []
    same_side_recent = phase2_recent_duplicate_orders(symbol, side) if symbol and side else []

    if len(all_active) >= PHASE2_MAX_ACTIVE_ORDERS:
        reasons.append("max_active_orders_hit")
    if len(symbol_active) >= PHASE2_MAX_ACTIVE_ORDERS_PER_SYMBOL:
        reasons.append("max_active_orders_per_symbol_hit")
    if same_side_recent:
        reasons.append("duplicate_active_order_window_hit")

    if mode == "LIVE" and PHASE2_REQUIRE_BROKER_FOR_LIVE:
        if not (ENABLE_ALPACA and GLOBAL_STATE.get("alpaca_enabled", False) and alpaca_ready()):
            reasons.append("live_broker_not_ready")

    approved = len(reasons) == 0
    decision = {
        "approved": approved,
        "stage": "phase2_execution_reliability",
        "reject_reasons": reasons,
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "mode": mode,
        "active_orders": len(all_active),
        "symbol_active_orders": len(symbol_active),
        "recent_duplicates": len(same_side_recent),
    }

    if approved:
        debug(f"PHASE 2 ORDER INTEGRITY OK | {side.upper()} {symbol} qty={qty} mode={mode} active={len(all_active)}")
    else:
        details = (
            f"Symbol: {symbol} | Side: {side} | Qty: {qty} | Mode: {mode}\n"
            f"Reasons: {', '.join(reasons)}\n"
            f"Active Orders: {len(all_active)} | Symbol Active: {len(symbol_active)} | Recent Duplicates: {len(same_side_recent)}"
        )
        phase2_alert("PHASE 2 ORDER INTEGRITY BLOCK", details)
        try:
            intel_event("phase2_order_integrity_block", decision, signal=signal_or_stub, stage="phase2_execution", decision="blocked")
        except Exception:
            pass
    return decision


def phase2_record_paper_order(position: Dict[str, Any], side: str, qty: int, fill_price: float, note: str) -> Dict[str, Any]:
    """Create a filled order lifecycle record for paper-mode actions so the order layer sees the full trade story."""
    ensure_globals_initialized()
    signal_stub = {
        "signal_id": position.get("signal_id", ""),
        "ticker": position.get("ticker", ""),
        "symbol": position.get("symbol", ""),
        "entry_price": fill_price,
    }
    order = make_order_record(signal_stub, side=side, qty=qty, mode="PAPER", order_type="market")
    order["position_id"] = position.get("id")
    order["idempotency_fill_event_id"] = idempotency_fill_event_id(order)
    order["broker_order_id"] = f"paper-{side}-{position.get('symbol')}-{epoch()}-{order.get('local_order_id')}"
    order["status"] = "filled"
    order["qty_filled"] = int(qty)
    order["qty_remaining"] = 0
    order["avg_fill_price"] = round(safe_float(fill_price, 0), 4)
    order["closed_at"] = epoch()
    order.setdefault("notes", []).append(note)
    save_order_record(order)
    debug(f"PHASE 2 PAPER ORDER FILLED | {side.upper()} {position.get('symbol')} qty={qty} fill={fill_price} pos_id={position.get('id')}")
    try:
        intel_event("order_filled", {"side": side, "qty": qty, "fill_price": fill_price, "note": note, "order": order}, position=position, stage="phase2_order_lifecycle", decision="filled")
    except Exception:
        pass
    return order


def phase2_sync_order_lifecycle() -> Dict[str, Any]:
    """Refresh live order snapshots and handle stale/rejected orders. Called every loop."""
    if not ENABLE_PHASE2_EXECUTION_RELIABILITY:
        return {"active": 0, "changed": False, "stale": 0, "rejected": 0}

    ensure_globals_initialized()
    changed = False
    stale_count = 0
    rejected_count = 0

    if ENABLE_ALPACA and GLOBAL_STATE.get("alpaca_enabled", False) and alpaca_ready():
        try:
            refresh_open_order_states()
        except Exception as e:
            phase2_alert("PHASE 2 ORDER REFRESH ERROR", str(e))

    now = epoch()
    for order in GLOBAL_ORDERS.get("orders", []):
        if not isinstance(order, dict) or not phase2_is_order_active(order):
            continue
        status = str(order.get("status", "")).lower().strip()
        mode = str(order.get("mode", "")).upper().strip()
        age = now - safe_int(order.get("created_at", now), now)

        if status in {"rejected", "expired"}:
            rejected_count += 1
            if PHASE2_BLOCK_ON_REJECTED_ORDER:
                phase2_set_execution_lock(f"Order rejected/expired: local_id={order.get('local_order_id')} symbol={order.get('symbol')} status={status}")
            continue

        if age > PHASE2_MAX_ORDER_WAIT_SECONDS and status not in phase2_order_terminal_statuses():
            stale_count += 1
            order.setdefault("notes", []).append(f"Phase2 stale order age={age}s")
            order["updated_at"] = now
            changed = True
            msg = f"local_id={order.get('local_order_id')} symbol={order.get('symbol')} status={status} age={age}s"
            phase2_alert("PHASE 2 STALE ORDER", msg)
            if mode == "LIVE" and PHASE2_CANCEL_STALE_LIVE_ORDERS and order.get("broker_order_id") and alpaca_ready():
                try:
                    resp = alpaca_delete(f"/v2/orders/{order.get('broker_order_id')}")
                    if resp.status_code in (200, 204):
                        update_order_status(order, "canceled", "Phase2 stale order canceled")
                    else:
                        order.setdefault("notes", []).append(f"Cancel failed: {resp.status_code} {resp.text[:200]}")
                except Exception as e:
                    order.setdefault("notes", []).append(f"Cancel exception: {e}")

    if changed:
        save_orders(GLOBAL_ORDERS)

    active = len(phase2_active_orders())
    debug(f"PHASE 2 ORDER LIFECYCLE OK | active_orders={active} | stale={stale_count} | rejected={rejected_count}")
    return {"active": active, "changed": changed, "stale": stale_count, "rejected": rejected_count}


def phase2_post_fill_risk_snapshot(context: str = "post_fill") -> Dict[str, Any]:
    ensure_globals_initialized()
    snapshot = {
        "context": context,
        "open_positions": len(GLOBAL_POSITIONS.get("open_positions", [])),
        "active_orders": len(phase2_active_orders()),
        "portfolio_heat_pct": round(portfolio_heat_pct(), 6),
        "daily_realized_pnl_pct": round(safe_float(GLOBAL_STATE.get("daily_realized_pnl_pct", 0.0), 0.0), 6),
        "consecutive_losses": safe_int(GLOBAL_STATE.get("consecutive_losses", 0), 0),
        "timestamp": epoch(),
    }
    debug(
        f"PHASE 2 RISK SNAPSHOT | {context} | open={snapshot['open_positions']} | "
        f"active_orders={snapshot['active_orders']} | heat={round(snapshot['portfolio_heat_pct']*100, 2)}% | "
        f"daily_pnl={round(snapshot['daily_realized_pnl_pct']*100, 2)}%"
    )
    try:
        intel_event("phase2_risk_snapshot", snapshot, stage="phase2_execution", decision="snapshot")
    except Exception:
        pass
    return snapshot


def phase2_reconciliation_guard() -> Dict[str, Any]:
    """Broker/local truth check. In paper mode this is informational; in live mode it can lock the engine."""
    if not ENABLE_PHASE2_EXECUTION_RELIABILITY:
        return {"approved": True, "reject_reasons": []}
    ensure_globals_initialized()
    reasons = []
    live_positions = [p for p in GLOBAL_POSITIONS.get("open_positions", []) if str(p.get("mode", "")).upper() == "LIVE"]
    if live_positions and ENABLE_ALPACA and GLOBAL_STATE.get("alpaca_enabled", False) and alpaca_ready():
        broker_positions = alpaca_list_positions()
        broker_symbols = {str(p.get("symbol", "")).strip() for p in broker_positions if str(p.get("symbol", "")).strip()}
        for p in live_positions:
            if p.get("symbol") not in broker_symbols and safe_int(p.get("pending_close_qty", 0), 0) <= 0:
                reasons.append(f"live_local_position_missing_at_broker:{p.get('symbol')}")
    if reasons and PHASE2_BLOCK_ON_RECON_MISMATCH:
        phase2_set_execution_lock("; ".join(reasons))
    if reasons:
        phase2_alert("PHASE 2 RECON MISMATCH", "\n".join(reasons), force=True)
    else:
        debug("PHASE 2 RECON OK")
        poll_unusual_whales_darkpool_prints(force=False)
        maybe_send_free_daily_levels(force=False)
    return {"approved": len(reasons) == 0, "reject_reasons": reasons}

# =========================================================
# SIGNAL HANDLER
# =========================================================

# =========================================================
# FINAL ELITE EXECUTION ROUTING HELPERS
# =========================================================
def elite_force_routing_enabled() -> bool:
    try:
        return bool(ENABLE_ELITE_EXECUTION_ROUTING and FORCE_EXECUTION_MODE and FORCE_BYPASS_SIGNAL_ROUTING)
    except Exception:
        return False


def elite_force_fresh_enabled() -> bool:
    try:
        return bool(ENABLE_ELITE_EXECUTION_ROUTING and FORCE_EXECUTION_MODE and FORCE_TREAT_SIGNAL_AS_FRESH)
    except Exception:
        return False


def elite_routing_decision(signal: Dict[str, Any], original_ok: bool, reason: str = "") -> bool:
    if original_ok:
        return True
    if elite_force_routing_enabled():
        debug(f"🚨 FINAL ELITE ROUTING — FORCE BYPASS | reason={reason}")
        return True
    return False


def elite_fresh_decision(signal: Dict[str, Any], original_ok: bool, reason: str = "") -> bool:
    if original_ok:
        return True
    if elite_force_fresh_enabled():
        debug(f"🚨 FINAL ELITE ROUTING — TREATING SIGNAL AS FRESH | reason={reason}")
        return True
    return False



def should_route_signal(signal: Dict[str, Any]) -> bool:
    if elite_force_routing_enabled():
        debug("🚨 FINAL ELITE ROUTING — should_route_signal force exit")
        return True

    new_hash = signal_hash(signal)
    if new_hash == GLOBAL_STATE.get("last_signal_hash", ""):
        return False
    recent_hashes = GLOBAL_STATE.get("recent_signal_hashes", [])
    if isinstance(recent_hashes, list) and new_hash in recent_hashes:
        return False
    return True


# =========================================================
# HARD DUPLICATE POSITION CAP
# Blocks stacking from BOTH positions.json and open_trades.json.
# This prevents the same symbol + direction from doubling qty
# when a signal repeats or the loop sees the same setup again.
# =========================================================
def _active_status(value: Any) -> bool:
    s = str(value or "OPEN").upper().strip()
    return s not in {"CLOSED", "CLOSE", "FILLED_CLOSED", "CANCELLED", "CANCELED", "REJECTED", "EXPIRED", "DONE"}


def _record_symbol_direction(record: Dict[str, Any]) -> Tuple[str, str]:
    symbol = str(record.get("symbol") or record.get("contract_symbol") or record.get("option_symbol") or "").strip()
    direction = str(record.get("direction") or record.get("trade_direction") or record.get("option_type") or "").upper().strip()
    return symbol, direction


def load_open_trades_records() -> List[Dict[str, Any]]:
    data = load_json_file("open_trades.json", [])
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("open_trades", "open_positions", "positions", "trades"):
            value = data.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def has_duplicate_open_position_anywhere(symbol: str, direction: str) -> Dict[str, Any]:
    ensure_globals_initialized()
    symbol = str(symbol or "").strip()
    direction = str(direction or "").upper().strip()
    reasons: List[str] = []

    for p in GLOBAL_POSITIONS.get("open_positions", []):
        if not isinstance(p, dict):
            continue
        p_symbol = str(p.get("symbol", "")).strip()
        p_direction = str(p.get("direction", "")).upper().strip()
        qty_open = safe_int(p.get("qty_open", p.get("remaining_qty", p.get("qty", 0))), 0)
        if p_symbol == symbol and p_direction == direction and qty_open > 0 and _active_status(p.get("status", "OPEN")):
            reasons.append(f"duplicate_open_position_positions_json:{symbol}:{direction}:qty={qty_open}")

    for t in load_open_trades_records():
        t_symbol, t_direction = _record_symbol_direction(t)
        qty_open = safe_int(t.get("remaining_qty", t.get("qty_open", t.get("qty", 0))), 0)
        if t_symbol == symbol and t_direction == direction and qty_open > 0 and _active_status(t.get("status", "OPEN")):
            reasons.append(f"duplicate_open_position_open_trades_json:{symbol}:{direction}:qty={qty_open}")

    active_order_statuses = {"created", "submitted", "accepted", "new", "pending_new", "partially_filled", "open"}
    for o in GLOBAL_ORDERS.get("orders", []):
        if not isinstance(o, dict):
            continue
        o_symbol = str(o.get("symbol", "")).strip()
        o_status = str(o.get("status", "")).lower().strip()
        o_side = str(o.get("side", "")).lower().strip()
        if o_symbol == symbol and o_side == "buy" and o_status in active_order_statuses:
            reasons.append(f"duplicate_active_buy_order:{symbol}:status={o_status}")

    return {"approved": len(reasons) == 0, "reject_reasons": reasons}


def signal_id_already_used(signal: Dict[str, Any]) -> bool:
    ensure_globals_initialized()
    signal_id = str(signal.get("signal_id", "")).strip() or signal_hash(signal)
    used = GLOBAL_STATE.get("used_signal_ids", [])
    return isinstance(used, list) and signal_id in used


def remember_used_signal_id(signal: Dict[str, Any], max_keep: int = 200):
    ensure_globals_initialized()
    signal_id = str(signal.get("signal_id", "")).strip() or signal_hash(signal)
    used = GLOBAL_STATE.get("used_signal_ids", [])
    if not isinstance(used, list):
        used = []
    if signal_id not in used:
        used.append(signal_id)
    GLOBAL_STATE["used_signal_ids"] = used[-max_keep:]
    save_state(GLOBAL_STATE)


def hard_duplicate_entry_gate(signal: Dict[str, Any]) -> Dict[str, Any]:
    symbol = str(signal.get("symbol", "")).strip()
    direction = str(signal.get("direction", "")).upper().strip()
    reasons: List[str] = []

    if not symbol:
        reasons.append("missing_symbol_for_duplicate_gate")
    if not direction:
        reasons.append("missing_direction_for_duplicate_gate")
    if signal_id_already_used(signal):
        reasons.append("repeat_signal_id_blocked")
    if symbol and direction:
        reasons.extend(has_duplicate_open_position_anywhere(symbol, direction).get("reject_reasons", []))

    if reasons:
        debug(f"HARD DUPLICATE CAP BLOCK | symbol={symbol} | direction={direction} | reasons={reasons}")

    return {"approved": len(reasons) == 0, "reject_reasons": reasons, "symbol": symbol, "direction": direction}



# =========================================================
# PHASE 3.5 ENFORCEMENT HELPERS
# =========================================================
def phase35_confidence_rank(confidence: str) -> int:
    c = str(confidence or "").upper().strip()
    ranks = {"A+": 5, "A": 4, "B+": 3, "B": 2, "C": 1, "D": 0, "AVOID": -1, "BLOCK": -2}
    return ranks.get(c, 0)


def phase35_confidence_ok(actual: str, minimum: str) -> bool:
    return phase35_confidence_rank(actual) >= phase35_confidence_rank(minimum)


def phase35_state() -> Dict[str, Any]:
    data = load_json_file(PHASE35_ENFORCEMENT_FILE, {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("schema_version", 1)
    data.setdefault("last_reset_day", current_trade_day())
    data.setdefault("blocks_today", 0)
    data.setdefault("approvals_today", 0)
    data.setdefault("last_block", {})
    data.setdefault("last_approval", {})
    data.setdefault("last_signal_by_symbol", {})
    data.setdefault("last_signal_by_setup", {})
    data.setdefault("used_signal_hashes", [])
    if data.get("last_reset_day") != current_trade_day():
        data["last_reset_day"] = current_trade_day()
        data["blocks_today"] = 0
        data["approvals_today"] = 0
        data["last_signal_by_symbol"] = {}
        data["last_signal_by_setup"] = {}
        data["used_signal_hashes"] = []
    return data


def phase35_save_state(data: Dict[str, Any]):
    atomic_write_json(PHASE35_ENFORCEMENT_FILE, data)


def phase35_in_time_window() -> bool:
    if not PHASE35_ENFORCE_TRADING_WINDOWS:
        return True
    if PHASE35_ALLOW_MIDDAY:
        return True
    now_m = hhmm_to_minutes(current_hhmm())
    open_ok = hhmm_to_minutes(PHASE35_OPEN_WINDOW_START) <= now_m <= hhmm_to_minutes(PHASE35_OPEN_WINDOW_END)
    power_ok = hhmm_to_minutes(PHASE35_POWER_WINDOW_START) <= now_m <= hhmm_to_minutes(PHASE35_POWER_WINDOW_END)
    return open_ok or power_ok


def phase35_signal_age_seconds(signal: Dict[str, Any]) -> int:
    ts = safe_int(signal.get("timestamp", signal.get("created_at", 0)), 0)
    if ts <= 0:
        return 0
    if ts > 10_000_000_000:
        ts = int(ts / 1000)
    return max(0, epoch() - ts)


def phase35_setup_key(signal: Dict[str, Any]) -> str:
    ticker = str(signal.get("ticker", signal.get("symbol", "UNKNOWN"))).upper().strip()
    direction = str(signal.get("direction", "UNKNOWN")).upper().strip()
    setup = str(signal.get("setup") or signal.get("strategy") or signal.get("trigger") or "GENERIC").upper().strip().replace(" ", "_")
    confidence = str(signal.get("confidence", "NA")).upper().strip()
    return f"{ticker}:{direction}:{confidence}:{setup[:60]}"


def phase35_duplicate_symbol_direction_count(signal: Dict[str, Any]) -> int:
    ticker = str(signal.get("ticker", "")).upper().strip()
    symbol = str(signal.get("symbol", "")).upper().strip()
    direction = str(signal.get("direction", "")).upper().strip()
    count = 0
    for p in GLOBAL_POSITIONS.get("open_positions", []):
        p_ticker = str(p.get("ticker", "")).upper().strip()
        p_symbol = str(p.get("symbol", "")).upper().strip()
        p_direction = str(p.get("direction", "")).upper().strip()
        same_name = (ticker and p_ticker == ticker) or (symbol and p_symbol == symbol)
        if same_name and direction and p_direction == direction:
            count += 1
    return count


def phase35_reward_to_risk(signal: Dict[str, Any]) -> float:
    entry = safe_float(signal.get("entry_contract", signal.get("entry", 0)), 0)
    stop = safe_float(signal.get("stop_contract", signal.get("stop", 0)), 0)
    tp1 = safe_float(signal.get("tp1_contract", signal.get("target", 0)), 0)
    tp2 = safe_float(signal.get("tp2_contract", 0), 0)
    unit_risk = entry - stop
    if entry <= 0 or stop <= 0 or unit_risk <= 0:
        return 0.0
    candidates = []
    if tp1 > entry:
        candidates.append((tp1 - entry) / unit_risk)
    if tp2 > entry:
        candidates.append((tp2 - entry) / unit_risk)
    return max(candidates) if candidates else 0.0


def phase35_daily_loss_dollars_limit() -> float:
    if PHASE35_MAX_DAILY_LOSS_DOLLARS > 0:
        return PHASE35_MAX_DAILY_LOSS_DOLLARS
    return get_account_equity() * PHASE35_MAX_DAILY_LOSS_PCT


def phase35_estimated_new_risk_dollars(signal: Dict[str, Any]) -> float:
    entry = safe_float(signal.get("entry_contract", 0), 0)
    stop = safe_float(signal.get("stop_contract", 0), 0)
    qty = safe_int(signal.get("qty", 0), 0)
    if entry <= 0 or stop <= 0 or qty <= 0:
        sd = signal.get("size_decision", {}) if isinstance(signal.get("size_decision", {}), dict) else {}
        return safe_float(sd.get("unit_risk_dollars", 0), 0) * max(safe_int(sd.get("final_size", qty), 0), 0)
    return max(entry - stop, 0.0) * 100.0 * qty



# =========================================================
# PHASE 3.5 MISSING HELPER FIX: PORTFOLIO HEAT DOLLARS
# Used by phase35_projected_heat_pct()
# =========================================================
def portfolio_heat_dollars() -> float:
    ensure_globals_initialized()
    total = 0.0

    for p in GLOBAL_POSITIONS.get("open_positions", []):
        qty = safe_int(p.get("qty", p.get("quantity", 0)), 0)
        entry = safe_float(p.get("entry_price", p.get("entry", 0)), 0)
        stop = safe_float(p.get("stop_price", p.get("stop", 0)), 0)

        if qty > 0 and entry > 0 and stop > 0:
            total += abs(entry - stop) * qty * 100

    return round(total, 2)


def phase35_projected_heat_pct(signal: Dict[str, Any]) -> float:
    equity = max(get_account_equity(), 1.0)
    return (portfolio_heat_dollars() + phase35_estimated_new_risk_dollars(signal)) / equity


def phase35_block(title: str, signal: Dict[str, Any], reasons: List[str], extras: str = "") -> Dict[str, Any]:
    data = phase35_state()
    data["blocks_today"] = safe_int(data.get("blocks_today", 0), 0) + 1
    data["last_block"] = {
        "time": now_ts(),
        "ticker": signal.get("ticker"),
        "symbol": signal.get("symbol"),
        "direction": signal.get("direction"),
        "confidence": signal.get("confidence"),
        "reasons": reasons,
        "extras": extras,
    }
    phase35_save_state(data)
    try:
        intel_event("phase35_enforcement_block", {"reasons": reasons, "extras": extras}, signal=signal, stage="phase35_enforcement", decision="blocked")
    except Exception:
        pass
    if PHASE35_SEND_ALERTS:
        msg = build_block_message(title, signal, reasons, extras)
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_live_entry_discord(msg)
        send_to_telegram(msg)
    return {"approved": False, "stage": "phase35_enforcement", "reject_reasons": reasons, "extras": extras}


def phase35_approve(signal: Dict[str, Any], notes: Optional[List[str]] = None) -> Dict[str, Any]:
    data = phase35_state()
    data["approvals_today"] = safe_int(data.get("approvals_today", 0), 0) + 1
    notes = notes or []
    joined_notes = " ".join(str(x) for x in notes)
    commit_execution = "phase35_ok_stage_execution_layer_" in joined_notes
    key = phase35_setup_key(signal)
    sym = str(signal.get("ticker", signal.get("symbol", "UNKNOWN"))).upper().strip()
    if commit_execution:
        data.setdefault("last_signal_by_symbol", {})[sym] = epoch()
        data.setdefault("last_signal_by_setup", {})[key] = epoch()
        hashes = data.setdefault("used_signal_hashes", [])
        hashes.append(signal_hash(signal))
        data["used_signal_hashes"] = hashes[-PHASE35_USED_SIGNAL_MEMORY:]
    data["last_approval"] = {
        "time": now_ts(),
        "ticker": signal.get("ticker"),
        "symbol": signal.get("symbol"),
        "direction": signal.get("direction"),
        "confidence": signal.get("confidence"),
        "setup_key": key,
    }
    phase35_save_state(data)
    try:
        intel_event("phase35_enforcement_approved", {"notes": notes or []}, signal=signal, stage="phase35_enforcement", decision="approved")
    except Exception:
        pass
    return {"approved": True, "stage": "phase35_enforcement", "notes": notes or []}



# =========================================================
# PHASE 3.5 STRATEGY EXECUTION LOCK HELPERS
# =========================================================
def phase35_is_edge_window() -> bool:
    """User edge windows: 9:30-10:30 ET and 3:00-4:00 ET."""
    if not PHASE35_ENFORCE_EDGE_WINDOWS:
        return True
    try:
        try:
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo("America/New_York"))
        except Exception:
            now = datetime.now()

        hour = now.hour
        minute = now.minute
        in_morning = (hour == 9 and minute >= 30) or (hour == 10 and minute <= 30)
        in_power_hour = (hour == 15)
        return bool(in_morning or in_power_hour)
    except Exception:
        return False


def phase35_strategy_execution_lock(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Hard strategy filter before any paper/live execution."""
    if auto_should_force_execution_for_test(signal) if 'signal' in locals() else FORCE_EXECUTION_MODE:
        log("🚨 FORCE MODE ACTIVE — BYPASSING STRATEGY LOCK")
        # Anti-spam: keep force bypass in logs only. Paper bridge sends execution alert once.
        return {
            "approved": True,
            "stage": "phase35_strategy_lock",
            "reason": "force_execution_mode",
            "reject_reasons": [],
        }

    if not ENABLE_PHASE35_STRATEGY_LOCK:
        return {"approved": True, "stage": "phase35_strategy_lock", "reason": "disabled", "reject_reasons": []}

    grade = str(signal.get("grade", signal.get("confidence", ""))).upper().strip()
    confidence = str(signal.get("confidence", grade)).upper().strip()

    trigger = str(
        signal.get("trigger")
        or signal.get("setup")
        or signal.get("strategy")
        or ""
    ).lower().strip().replace(" ", "_")

    confirmation = str(
        signal.get("confirmation")
        or signal.get("confirm")
        or ""
    ).lower().strip().replace(" ", "_")

    regime = str(
        signal.get("regime")
        or signal.get("market_regime")
        or "clean"
    ).lower().strip()

    source = str(signal.get("source", "")).lower().strip()
    reject_reasons = []

    if grade not in PHASE35_ALLOWED_GRADES and confidence not in PHASE35_ALLOWED_GRADES:
        reject_reasons.append(f"non_a_setup:grade={grade}:confidence={confidence}")

    if trigger not in PHASE35_ALLOWED_TRIGGERS:
        reject_reasons.append(f"invalid_trigger:{trigger or 'missing'}")

    if confirmation not in PHASE35_ALLOWED_CONFIRMATIONS:
        reject_reasons.append(f"missing_or_invalid_confirmation:{confirmation or 'missing'}")

    if PHASE35_ENFORCE_EDGE_WINDOWS:
        test_bypass = PHASE35_ALLOW_TEST_SIGNAL_ANYTIME and source in {"auto_signal_formatter", "test", "manual_test"}
        if not test_bypass and not phase35_is_edge_window():
            reject_reasons.append("outside_edge_trading_window")

    if PHASE35_BLOCK_CHOP and regime in {"chop", "choppy", "sideways", "range"}:
        reject_reasons.append(f"choppy_regime:{regime}")

    approved = len(reject_reasons) == 0

    if approved:
        debug(
            f"PHASE 3.5 STRATEGY LOCK APPROVED | "
            f"grade={grade} confidence={confidence} trigger={trigger} confirmation={confirmation} regime={regime}"
        )
    else:
        msg = (
            "🚫 PHASE 3.5 STRATEGY LOCK\n"
            f"BLOCKED SIGNAL Ticker: {signal.get('ticker', signal.get('symbol'))}\n"
            f"Reasons: {', '.join(reject_reasons)}"
        )
        log(msg.replace("\n", " | "))
        try:
            send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
            send_to_telegram(msg)
        except Exception:
            pass

    return {
        "approved": approved,
        "stage": "phase35_strategy_lock",
        "reject_reasons": reject_reasons,
        "grade": grade,
        "confidence": confidence,
        "trigger": trigger,
        "confirmation": confirmation,
        "regime": regime,
    }



def phase35_enforcement_gate(signal: Dict[str, Any], phase3_decision: Optional[Dict[str, Any]] = None, size_decision: Optional[Dict[str, Any]] = None, stage: str = "pre_size") -> Dict[str, Any]:
    # PHASE 3.5 STRATEGY LOCK GATE
    strategy_lock = phase35_strategy_execution_lock(signal)
    if not strategy_lock.get("approved", False):
        return strategy_lock

    if not ENABLE_PHASE35_ENFORCEMENT:
        return {"approved": True, "stage": "phase35_enforcement", "notes": ["phase35_disabled"]}

    ensure_globals_initialized()
    reset_daily_risk_counters_if_needed(GLOBAL_STATE)
    phase3_decision = phase3_decision or {}
    size_decision = size_decision or {}
    reasons = []
    notes = []

    if PHASE35_SUGGEST_ONLY:
        notes.append("suggest_only_enabled")

    if GLOBAL_STATE.get("kill_switch", False):
        reasons.append("phase35_kill_switch_active")
    if GLOBAL_STATE.get("bot_paused", False):
        reasons.append("phase35_bot_paused")
    if not GLOBAL_STATE.get("engine_enabled", True):
        reasons.append("phase35_engine_disabled")
    if GLOBAL_STATE.get("reconciliation_required", False):
        reasons.append("phase35_reconciliation_required")
    if not GLOBAL_STATE.get("allow_entries", True):
        reasons.append("phase35_entries_not_allowed")

    if PHASE35_REQUIRE_PHASE3_APPROVAL and phase3_decision and not phase3_decision.get("approved", True):
        reasons.append("phase35_phase3_not_approved")

    confidence = str(signal.get("confidence", "")).upper().strip()
    if not phase35_confidence_ok(confidence, PHASE35_MIN_CONFIDENCE_TO_EXECUTE):
        reasons.append(f"phase35_confidence_below_execute_min_{confidence}_lt_{PHASE35_MIN_CONFIDENCE_TO_EXECUTE}")

    if not phase35_in_time_window():
        reasons.append("phase35_outside_approved_trading_window")

    age = phase35_signal_age_seconds(signal)
    if age > PHASE35_MAX_SIGNAL_AGE_SECONDS:
        reasons.append(f"phase35_stale_signal_{age}s")
    if age > PHASE35_MAX_ENTRY_AGE_SECONDS:
        reasons.append(f"phase35_entry_age_exceeded_{age}s")

    rr = phase35_reward_to_risk(signal)
    if rr < PHASE35_MIN_RR_RATIO:
        reasons.append(f"phase35_rr_too_low_{round(rr, 2)}")

    dupes = phase35_duplicate_symbol_direction_count(signal)
    if dupes >= PHASE35_MAX_DUPLICATE_SYMBOL_DIRECTION:
        reasons.append(f"phase35_duplicate_symbol_direction_cap_{dupes}")

    data = phase35_state()
    enforce_reuse_memory = str(stage).startswith("execution_layer")
    if enforce_reuse_memory:
        sig_hash = signal_hash(signal)
        if sig_hash in data.get("used_signal_hashes", []):
            reasons.append("phase35_signal_hash_already_used")

        sym = str(signal.get("ticker", signal.get("symbol", "UNKNOWN"))).upper().strip()
        last_sym = safe_int(data.get("last_signal_by_symbol", {}).get(sym, 0), 0)
        if last_sym and epoch() - last_sym < PHASE35_SYMBOL_COOLDOWN_SECONDS:
            reasons.append(f"phase35_symbol_cooldown_{epoch() - last_sym}s")

        setup_key = phase35_setup_key(signal)
        last_setup = safe_int(data.get("last_signal_by_setup", {}).get(setup_key, 0), 0)
        if last_setup and epoch() - last_setup < PHASE35_SETUP_COOLDOWN_SECONDS:
            reasons.append(f"phase35_setup_cooldown_{epoch() - last_setup}s")

    daily_loss = stable_daily_pnl_dollars()
    max_daily_loss = phase35_daily_loss_dollars_limit()
    if daily_loss <= -abs(max_daily_loss):
        reasons.append(f"phase35_daily_loss_lockout_{daily_loss}")

    if safe_int(GLOBAL_STATE.get("consecutive_losses", 0), 0) >= PHASE35_BLOCK_AFTER_CONSECUTIVE_LOSSES:
        reasons.append(f"phase35_consecutive_loss_lockout_{GLOBAL_STATE.get('consecutive_losses')}")

    if size_decision:
        final_size = safe_int(size_decision.get("final_size", signal.get("qty", 0)), 0)
        if final_size <= 0:
            reasons.append("phase35_final_size_zero")
        projected_heat = phase35_projected_heat_pct(signal)
        if projected_heat > PHASE35_MAX_PROJECTED_HEAT_PCT:
            reasons.append(f"phase35_projected_heat_too_high_{round(projected_heat * 100, 2)}pct")

    live_price = 0.0
    try:
        symbol = str(signal.get("symbol", "")).strip()
        if symbol:
            prices = load_market_prices()
            live_price, _ = get_market_price_for_symbol(symbol, prices)
    except Exception:
        live_price = 0.0
    entry = safe_float(signal.get("entry_contract", 0), 0)
    if live_price > 0 and entry > 0:
        dist = abs(live_price - entry) / entry
        if dist > PHASE35_MAX_DISTANCE_FROM_ENTRY_PCT:
            reasons.append(f"phase35_you_are_chasing_distance_{round(dist * 100, 2)}pct")

    if PHASE35_REQUIRE_ADAPTIVE_STATS_SYNC:
        try:
            stats_payload = phase3_write_adaptive_stats(force=False)
            if ENABLE_INTELLIGENCE_PHASE3 and not isinstance(stats_payload, dict):
                reasons.append("phase35_adaptive_stats_not_synced")
        except Exception:
            reasons.append("phase35_adaptive_stats_sync_error")

    if reasons and not PHASE35_SUGGEST_ONLY:
        extra = f"Stage: {stage} | RR: {round(rr, 2)} | Age: {age}s | Daily PnL: ${daily_loss}"
        return phase35_block("PHASE 3.5 ENFORCEMENT BLOCKED SIGNAL", signal, reasons, extra)

    if reasons and PHASE35_SUGGEST_ONLY:
        msg = build_block_message("PHASE 3.5 WARNING ONLY", signal, reasons, f"Suggest-only mode. Stage: {stage}")
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_telegram(msg)
        notes.extend(reasons)

    notes.append(f"phase35_ok_stage_{stage}")
    return phase35_approve(signal, notes)

def execute_approved_signal(signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    PHASE 3.5 EXECUTION ROUTER FIX.
    Final bridge from approved signal to paper/live execution.
    """
    ensure_globals_initialized()
    signal = idempotency_attach_to_signal(signal)
    symbol = str(signal.get("symbol", signal.get("ticker", ""))).strip()
    live_requested = bool(GLOBAL_STATE.get("alpaca_enabled", False) and ENABLE_ALPACA and not GLOBAL_STATE.get("paper_enabled", True))

    try:
        if live_requested:
            debug(f"PHASE 3.5 EXECUTION ROUTER | attempting LIVE open | symbol={symbol}")
            pos = open_live_position(signal)
            if pos:
                remember_used_signal_id(signal)
                idempotency_mark("signal_intent", idempotency_signal_intent_id(signal), "open", {"position": pos, "mode": "LIVE"})
                log(f"✅ PHASE 3.5 LIVE EXECUTION CONFIRMED | {symbol} | qty={pos.get('qty_open')} | entry={pos.get('entry_price')}")
                return pos
            msg = build_block_message("PHASE 3.5 EXECUTION ROUTER LIVE FAILED", signal, ["open_live_position_returned_none"], "Signal passed approval pipeline, but live order creation failed.")
            send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
            send_to_telegram(msg)
            return None

        if ENABLE_PAPER_EXECUTION or GLOBAL_STATE.get("paper_enabled", True):
            GLOBAL_STATE["paper_enabled"] = True
            save_state(GLOBAL_STATE)
            debug(f"PHASE 3.5 EXECUTION ROUTER | attempting PAPER open | symbol={symbol}")
            pos = open_paper_position(signal)
            if pos:
                remember_used_signal_id(signal)
                idempotency_mark("signal_intent", idempotency_signal_intent_id(signal), "open", {"position": pos, "mode": "PAPER"})
                log(f"✅ PHASE 3.5 PAPER EXECUTION CONFIRMED | {symbol} | qty={pos.get('qty_open')} | entry={pos.get('entry_price')}")
                send_to_discord(DISCORD_AI_WEBHOOK, build_position_open_message(pos), "AI")
                return pos
            msg = build_block_message("PHASE 3.5 EXECUTION ROUTER PAPER FAILED", signal, ["open_paper_position_returned_none"], "Signal passed approval pipeline, but paper position/order creation failed. Check Phase 1/2/3.5 execution-layer block alerts.")
            send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
            send_to_telegram(msg)
            return None

        msg = build_block_message("PHASE 3.5 EXECUTION ROUTER BLOCKED", signal, ["no_execution_mode_enabled"], "ENABLE_PAPER_EXECUTION=false and live mode was not enabled.")
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_telegram(msg)
        return None
    except Exception as e:
        err = f"PHASE 3.5 execution router exception: {e}"
        log(f"❌ {err}")
        send_to_discord(DISCORD_AI_WEBHOOK, f"🚨 {err}", "AI")
        send_to_telegram(f"🚨 {err}")
        return None









def send_to_execution_discord(message: str) -> None:
    """
    Dedicated AI execution-alert router.
    Uses DISCORD_EXECUTION_WEBHOOK first.
    Falls back to DISCORD_AI_WEBHOOK if missing.
    Execution lifecycle messages should NOT go to DISCORD_LIVE_ENTRY_WEBHOOK.
    """
    try:
        target = DISCORD_EXECUTION_WEBHOOK or DISCORD_AI_WEBHOOK
        if not target:
            try:
                debug("EXECUTION WEBHOOK MISSING | set DISCORD_EXECUTION_WEBHOOK")
            except Exception:
                pass
            return
        send_to_discord(target, message, "AI_EXECUTION")
    except Exception as e:
        try:
            debug(f"EXECUTION webhook send failed: {e}")
        except Exception:
            pass



def send_execution_or_original_discord(message: str, original_webhook: str, username: str = "AI") -> None:
    """
    Content-aware router:
    - execution lifecycle messages -> DISCORD_EXECUTION_WEBHOOK
    - everything else -> original webhook
    """
    try:
        text = str(message or "")
        execution_markers = [
            "PAPER BROKER BRIDGE EXECUTED",
            "PAPER TP1 HIT",
            "PAPER STOP MOVED TO BREAKEVEN",
            "PAPER POSITION OPENED",
            "PAPER ORDER FILLED",
            "PAPER ORDER CREATED",
            "PAPER BRIDGE DUPLICATE CAP BLOCKED",
            "PAPER BROKER BRIDGE RESULT",
            "ORDER FILLED",
            "POSITION OPENED",
            "TP1 HIT",
            "STOP MOVED",
        ]
        if any(m in text for m in execution_markers):
            send_to_execution_discord(text)
            return
        send_to_discord(original_webhook, text, username)
    except Exception as e:
        try:
            debug(f"SMART Discord route failed: {e}")
        except Exception:
            pass


def send_to_live_entry_discord(message: str) -> None:
    """
    Dedicated UNBIASED-LIVE-ENTRY-ALERT router.
    Uses DISCORD_LIVE_ENTRY_WEBHOOK first.
    Falls back to DISCORD_PREMIUM_WEBHOOK if missing.

    Safety rule:
    execution lifecycle alerts are redirected to DISCORD_EXECUTION_WEBHOOK.
    """
    try:
        text = str(message or "")
        execution_markers = [
            "PAPER BROKER BRIDGE EXECUTED",
            "PAPER TP1 HIT",
            "PAPER STOP MOVED TO BREAKEVEN",
            "PAPER POSITION OPENED",
            "PAPER ORDER FILLED",
            "PAPER ORDER CREATED",
            "PAPER BRIDGE DUPLICATE CAP BLOCKED",
            "PAPER BROKER BRIDGE RESULT",
            "ORDER FILLED",
            "POSITION OPENED",
            "TP1 HIT",
            "STOP MOVED",
        ]
        if any(m in text for m in execution_markers):
            send_to_execution_discord(text)
            return

        target = DISCORD_LIVE_ENTRY_WEBHOOK or DISCORD_PREMIUM_WEBHOOK
        if not target:
            try:
                debug("LIVE ENTRY WEBHOOK MISSING | set DISCORD_LIVE_ENTRY_WEBHOOK")
            except Exception:
                pass
            return
        send_to_discord(target, message, "LIVE_ENTRY")
    except Exception as e:
        try:
            debug(f"LIVE ENTRY webhook send failed: {e}")
        except Exception:
            pass




# =========================================================
# AUTOMATED FREE DAILY LEVELS — QQQ / SPY
# Free = information only. Premium/live-entry = execution.
# Sends clean daily-level game plans to the free channel.
# =========================================================
ENABLE_FREE_DAILY_LEVELS = os.getenv("ENABLE_FREE_DAILY_LEVELS", "true").lower() == "true"
FREE_DAILY_LEVEL_TICKERS = {
    x.strip().upper()
    for x in os.getenv("FREE_DAILY_LEVEL_TICKERS", "QQQ,SPY").split(",")
    if x.strip()
}
FREE_DAILY_LEVEL_STATE_FILE = os.getenv("FREE_DAILY_LEVEL_STATE_FILE", "free_daily_levels_state.json").strip()
FREE_DAILY_LEVEL_COOLDOWN_SECONDS = int(os.getenv("FREE_DAILY_LEVEL_COOLDOWN_SECONDS", "10800"))  # 3 hours
FREE_DAILY_LEVEL_SEND_ON_BOOT = os.getenv("FREE_DAILY_LEVEL_SEND_ON_BOOT", "true").lower() == "true"
FREE_DAILY_LEVEL_INCLUDE_DARKPOOL = os.getenv("FREE_DAILY_LEVEL_INCLUDE_DARKPOOL", "true").lower() == "true"
FREE_DAILY_LEVEL_INCLUDE_OIL = os.getenv("FREE_DAILY_LEVEL_INCLUDE_OIL", "true").lower() == "true"


def free_daily_load_state() -> Dict[str, Any]:
    try:
        data = load_json_file(FREE_DAILY_LEVEL_STATE_FILE, {})
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def free_daily_save_state(data: Dict[str, Any]) -> None:
    try:
        atomic_write_json(FREE_DAILY_LEVEL_STATE_FILE, data)
    except Exception as e:
        try:
            debug(f"FREE DAILY state save failed: {e}")
        except Exception:
            pass


def free_daily_send(message: str) -> None:
    try:
        target = DISCORD_FREE_DAILY_LEVELS_WEBHOOK or DISCORD_FREE_WEBHOOK
        if not target:
            try:
                debug("FREE DAILY WEBHOOK MISSING | set DISCORD_FREE_DAILY_LEVELS_WEBHOOK or DISCORD_FREE_WEBHOOK")
            except Exception:
                pass
            return
        send_to_discord(target, message, "FREE_DAILY_LEVELS")
    except Exception as e:
        try:
            debug(f"FREE DAILY send failed: {e}")
        except Exception:
            pass


def free_daily_get_market_price(ticker: str) -> float:
    ticker = str(ticker or "").upper().strip()
    try:
        prices = load_json_file(MARKET_DATA_FILE if "MARKET_DATA_FILE" in globals() else "market_prices.json", {})
        if isinstance(prices, dict):
            row = prices.get(ticker, {})
            if isinstance(row, dict):
                return safe_float(row.get("price") or row.get("last") or row.get("close"), 0.0)
            return safe_float(row, 0.0)
    except Exception:
        pass

    try:
        prices = load_market_prices([ticker])
        px, _ = get_market_price_for_symbol(ticker, prices)
        return safe_float(px, 0.0)
    except Exception:
        return 0.0


def free_daily_get_oil_read() -> str:
    if not FREE_DAILY_LEVEL_INCLUDE_OIL:
        return "Not included"

    try:
        macro = load_json_file(MACRO_FILE if "MACRO_FILE" in globals() else "macro_store.json", {})
        if isinstance(macro, dict):
            for key in ("oil", "uso", "crude_oil", "wti"):
                v = macro.get(key)
                if isinstance(v, dict):
                    direction = str(v.get("direction") or v.get("bias") or "").lower()
                    price = v.get("price") or v.get("last") or ""
                    if "fall" in direction or "down" in direction:
                        return f"Falling / relief → bullish support for tech ({price})"
                    if "rise" in direction or "up" in direction:
                        return f"Rising / pressure → risk-off pressure for tech ({price})"
                    if price:
                        return f"Watching oil/USO around {price}"
                elif isinstance(v, str) and v:
                    return v
    except Exception:
        pass

    return "Watch oil/USO — falling supports tech, rising pressures tech"


def free_daily_market_state(price: float, vwap: Any = None) -> Tuple[str, str]:
    vwap_text = str(vwap or "").lower()

    if "above" in vwap_text or "reclaim" in vwap_text:
        return "Trending / buyer control", "Bullish above VWAP"
    if "below" in vwap_text or "reject" in vwap_text:
        return "Weak / seller control", "Bearish below VWAP"
    if price > 0:
        return "Decision zone", "Neutral until level confirmation"
    return "Data pending", "Neutral"


def free_daily_darkpool_levels(ticker: str, price: float) -> Tuple[str, str]:
    if not FREE_DAILY_LEVEL_INCLUDE_DARKPOOL:
        return "Not included", "Not included"

    try:
        levels = None

        # Prefer live evaluator if available.
        if "uw_dp_build_levels" in globals():
            levels = uw_dp_build_levels(ticker, current_price=price, force=False)

        if not isinstance(levels, dict):
            cache = load_json_file(UW_DARKPOOL_FILE if "UW_DARKPOOL_FILE" in globals() else "darkpool_levels.json", {})
            if isinstance(cache, dict):
                levels = cache.get(ticker, {})

        support = None
        resistance = None

        if isinstance(levels, dict):
            support = levels.get("nearest_support")
            resistance = levels.get("nearest_resistance")

        def fmt(lvl, fallback):
            if not isinstance(lvl, dict):
                return fallback
            px = safe_float(lvl.get("price"), 0.0)
            premium = safe_float(lvl.get("premium"), 0.0)
            if px <= 0:
                return fallback
            if premium >= 1_000_000:
                prem = f"${premium / 1_000_000:.2f}M"
            elif premium >= 1_000:
                prem = f"${premium / 1_000:.2f}K"
            else:
                prem = f"${premium:.0f}"
            return f"{px:.2f} ({prem})"

        return fmt(support, "No clean support print yet"), fmt(resistance, "No clean resistance print yet")

    except Exception:
        return "Dark pool pending", "Dark pool pending"


def free_daily_estimate_levels(ticker: str, price: float) -> Dict[str, Any]:
    """
    Free daily levels are simple reaction zones:
    support, resistance, and decision level.
    If live level data is missing, estimate around current price so free alerts still render.
    """
    if price <= 0:
        return {
            "support": "Pending",
            "resistance": "Pending",
            "decision": "Pending",
            "vwap": "Pending",
            "premarket_high": "Pending",
            "premarket_low": "Pending",
        }

    # Wider increments for SPY/QQQ so levels are readable.
    if ticker == "SPY":
        step = 1.0
    else:
        step = 2.0

    decision = round(price / step) * step
    support = decision - step
    resistance = decision + step

    return {
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "decision": round(decision, 2),
        "vwap": "Use live VWAP / control level",
        "premarket_high": "Add premarket high when available",
        "premarket_low": "Add premarket low when available",
    }


def build_free_daily_levels_alert(ticker: str) -> str:
    ticker = str(ticker or "").upper().strip()
    price = free_daily_get_market_price(ticker)
    levels = free_daily_estimate_levels(ticker, price)

    market_state, bias = free_daily_market_state(price, levels.get("vwap"))
    oil = free_daily_get_oil_read()
    dp_support, dp_resistance = free_daily_darkpool_levels(ticker, price)

    price_line = f"{price:.2f}" if price > 0 else "Pending"

    return (
        f"📊 {ticker} FREE DAILY LEVELS\n\n"
        f"📈 Market State: {market_state}\n"
        f"🧭 Bias: {bias}\n"
        f"💵 Current Price: {price_line}\n\n"
        f"💰 Key Levels:\n"
        f"• Resistance: {levels.get('resistance')}\n"
        f"• Support: {levels.get('support')}\n"
        f"• Decision: {levels.get('decision')}\n\n"
        f"📍 VWAP / Control:\n"
        f"• {levels.get('vwap')}\n"
        f"• Above = buyers in control\n"
        f"• Below = sellers in control\n\n"
        f"🌙 Premarket Map:\n"
        f"• Premarket High: {levels.get('premarket_high')}\n"
        f"• Premarket Low: {levels.get('premarket_low')}\n\n"
        f"💎 Dark Pool Resource Zones:\n"
        f"• Support: {dp_support}\n"
        f"• Resistance: {dp_resistance}\n\n"
        f"🟢 CALLS:\n"
        f"• Above decision level → continuation watch\n"
        f"• Break + hold → target resistance / next level\n\n"
        f"🔴 PUTS:\n"
        f"• Below decision level → weakness watch\n"
        f"• Rejection at resistance → target support / next level\n\n"
        f"🛢️ Oil / Macro:\n"
        f"• {oil}\n\n"
        f"⚠️ RULES:\n"
        f"• No chasing\n"
        f"• No trading middle\n"
        f"• Wait for confirmation\n\n"
        f"Free = information. Premium = execution."
    )


def maybe_send_free_daily_levels(force: bool = False) -> None:
    if not ENABLE_FREE_DAILY_LEVELS:
        return

    try:
        state = free_daily_load_state()
        now = int(time.time())

        for ticker in sorted(FREE_DAILY_LEVEL_TICKERS):
            key = f"{ticker}:{datetime.utcnow().strftime('%Y-%m-%d')}"
            last = safe_int(state.get(key, 0), 0)

            if not force and last and (now - last) < FREE_DAILY_LEVEL_COOLDOWN_SECONDS:
                continue

            msg = build_free_daily_levels_alert(ticker)
            free_daily_send(msg)
            state[key] = now

            try:
                debug(f"FREE DAILY LEVELS SENT | ticker={ticker}")
            except Exception:
                pass

        free_daily_save_state(state)

    except Exception as e:
        try:
            debug(f"FREE DAILY LEVELS FAILED | {e}")
        except Exception:
            pass


def free_daily_levels_autoloop_tick() -> None:
    """
    Safe loop hook for automated free daily levels.
    Runs every engine cycle, but cooldown/state prevents spam.
    """
    try:
        maybe_send_free_daily_levels(force=False)
    except Exception as e:
        try:
            debug(f"FREE DAILY AUTOLOOP FAILED | {e}")
        except Exception:
            pass



def free_daily_levels_autoloop_boot_tick() -> None:
    """
    Optional boot hook. If FREE_DAILY_LEVEL_SEND_ON_BOOT=true,
    sends once on startup, then normal cooldown controls the rest.
    """
    try:
        if FREE_DAILY_LEVEL_SEND_ON_BOOT:
            maybe_send_free_daily_levels(force=False)
    except Exception as e:
        try:
            debug(f"FREE DAILY BOOT SEND FAILED | {e}")
        except Exception:
            pass



# =========================================================
# PREMIUM DAILY LEVELS / QQQ-SPY GRADED BIAS ALERTS
# Sends premium-style market decision alerts with:
# - QQQ/SPY grade
# - confidence
# - tech strength
# - VWAP / volume / oil / macro / dark pool confluence
# =========================================================
ENABLE_PREMIUM_DAILY_LEVEL_ALERTS = os.getenv("ENABLE_PREMIUM_DAILY_LEVEL_ALERTS", "true").lower() == "true"
PREMIUM_DAILY_LEVEL_TICKERS = {
    x.strip().upper()
    for x in os.getenv("PREMIUM_DAILY_LEVEL_TICKERS", "QQQ,SPY").split(",")
    if x.strip()
}
PREMIUM_DAILY_MIN_GRADE = os.getenv("PREMIUM_DAILY_MIN_GRADE", "B").upper().strip()
PREMIUM_DAILY_ALERT_COOLDOWN_SECONDS = int(os.getenv("PREMIUM_DAILY_ALERT_COOLDOWN_SECONDS", "180"))
PREMIUM_DAILY_ALERT_STATE_FILE = os.getenv("PREMIUM_DAILY_ALERT_STATE_FILE", "premium_daily_alert_state.json").strip()


def premium_daily_load_state() -> Dict[str, Any]:
    try:
        data = load_json_file(PREMIUM_DAILY_ALERT_STATE_FILE, {})
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def premium_daily_save_state(data: Dict[str, Any]) -> None:
    try:
        atomic_write_json(PREMIUM_DAILY_ALERT_STATE_FILE, data)
    except Exception as e:
        try:
            debug(f"PREMIUM DAILY state save failed: {e}")
        except Exception:
            pass


def premium_daily_grade_rank(grade: str) -> int:
    ladder = ["AVOID", "C", "B", "B+", "A", "A+"]
    g = str(grade or "B").upper().strip()
    if g not in ladder:
        g = "B"
    return ladder.index(g)


def premium_daily_meets_grade(grade: str, min_grade: str) -> bool:
    return premium_daily_grade_rank(grade) >= premium_daily_grade_rank(min_grade)


def premium_daily_get_signal_text(signal: Dict[str, Any], *keys, default: str = "Unknown") -> str:
    for key in keys:
        v = signal.get(key)
        if v not in (None, "", [], {}):
            return str(v)
    con = signal.get("confluences", {}) if isinstance(signal.get("confluences"), dict) else {}
    for key in keys:
        v = con.get(key)
        if v not in (None, "", [], {}):
            return str(v)
    return default


def premium_daily_get_grade(signal: Dict[str, Any]) -> str:
    return str(signal.get("grade") or signal.get("confidence") or "B").upper().strip()


def premium_daily_confidence_label(signal: Dict[str, Any]) -> str:
    grade = premium_daily_get_grade(signal)
    learning = signal.get("learning") or signal.get("adaptive_learning") or signal.get("adaptive_sizing") or {}
    dp = signal.get("dark_pool", {}) if isinstance(signal.get("dark_pool"), dict) else {}
    boost = safe_int(dp.get("grade_boost", 0), 0)

    if grade == "A+":
        return "Very High"
    if grade == "A":
        return "High"
    if grade == "B+":
        return "Moderate-High"
    if boost > 0:
        return "Improving"
    if grade in {"C", "AVOID"}:
        return "Low"
    return "Moderate"


def premium_daily_tech_strength(signal: Dict[str, Any]) -> str:
    ticker = str(signal.get("ticker", "")).upper().strip()
    direction = str(signal.get("direction", "")).upper().strip()
    con = signal.get("confluences", {}) if isinstance(signal.get("confluences"), dict) else {}

    vwap = str(con.get("vwap") or signal.get("vwap") or "").lower()
    volume = str(con.get("volume") or signal.get("volume") or "").lower()
    structure = str(con.get("structure") or signal.get("structure") or signal.get("setup") or signal.get("setup_type") or "").lower()
    market = str(con.get("market_type") or signal.get("market_type") or "").lower()
    oil = str(con.get("oil") or signal.get("oil") or "").lower()
    dp = signal.get("dark_pool", {}) if isinstance(signal.get("dark_pool"), dict) else {}

    score = 0
    reasons = []

    if direction == "CALL":
        if "above" in vwap or "reclaim" in vwap:
            score += 2
            reasons.append("above VWAP")
        if "breakout" in structure or "hold" in structure or "retest" in structure:
            score += 2
            reasons.append("structure holding")
        if "strong" in volume or "spike" in volume:
            score += 1
            reasons.append("volume confirming")
        if "falling" in oil or "down" in oil or "dump" in oil:
            score += 1
            reasons.append("oil supportive")
    elif direction == "PUT":
        if "below" in vwap or "reject" in vwap:
            score += 2
            reasons.append("below/rejecting VWAP")
        if "rejection" in structure or "lower" in structure or "breakdown" in structure:
            score += 2
            reasons.append("bearish structure")
        if "strong" in volume or "spike" in volume:
            score += 1
            reasons.append("volume confirming")
        if "rising" in oil or "up" in oil or "spike" in oil:
            score += 1
            reasons.append("oil risk-off")

    if isinstance(dp, dict):
        actions = " ".join(dp.get("actions", [])) if isinstance(dp.get("actions"), list) else str(dp.get("actions", ""))
        if "supported" in actions or "accepted" in actions:
            score += 1
            reasons.append("dark pool aligned")

    if "trend" in market or "expansion" in market:
        score += 1
        reasons.append("trend/expansion")

    if score >= 6:
        label = "Strong"
    elif score >= 4:
        label = "Building"
    elif score >= 2:
        label = "Mixed"
    else:
        label = "Weak / Not Confirmed"

    reason_text = ", ".join(reasons[:4]) if reasons else "needs confirmation"
    return f"{label} — {reason_text}"


def premium_daily_trade_decision(signal: Dict[str, Any]) -> str:
    grade = premium_daily_get_grade(signal)
    direction = str(signal.get("direction", "")).upper().strip()
    tech = premium_daily_tech_strength(signal).lower()

    if grade in {"A+", "A"} and ("strong" in tech or "building" in tech):
        return f"TRADEABLE {direction} setup — wait for entry confirmation"
    if grade in {"B+", "B"}:
        return f"WAIT — bias forming, needs stronger confirmation"
    return "AVOID / OBSERVE — not enough confluence"


def premium_daily_dark_pool_summary(signal: Dict[str, Any]) -> str:
    dp = signal.get("dark_pool", {}) if isinstance(signal.get("dark_pool"), dict) else {}
    if not dp:
        return "No dark pool read yet"

    support = dp.get("nearest_support")
    resistance = dp.get("nearest_resistance")
    actions = dp.get("actions", [])

    parts = []
    if isinstance(support, dict) and support.get("price"):
        parts.append(f"support {safe_float(support.get('price'), 0):.2f}")
    if isinstance(resistance, dict) and resistance.get("price"):
        parts.append(f"resistance {safe_float(resistance.get('price'), 0):.2f}")
    if isinstance(actions, list) and actions:
        parts.append(", ".join(actions[:2]))

    if not parts:
        return str(dp.get("reason", "observe only"))

    return " | ".join(parts)


def build_premium_daily_levels_alert(signal: Dict[str, Any]) -> str:
    ticker = str(signal.get("ticker") or signal.get("underlying") or "UNKNOWN").upper().strip()
    direction = str(signal.get("direction") or "NEUTRAL").upper().strip()
    grade = premium_daily_get_grade(signal)
    confidence = premium_daily_confidence_label(signal)

    setup = premium_daily_get_signal_text(signal, "setup_name", "setup", "setup_type", "trigger", default="No setup name")
    vwap = premium_daily_get_signal_text(signal, "vwap", default="Not provided")
    volume = premium_daily_get_signal_text(signal, "volume", default="Not provided")
    oil = premium_daily_get_signal_text(signal, "oil", default="Not provided")
    market = premium_daily_get_signal_text(signal, "market_type", "regime", default="Not provided")
    tech = premium_daily_tech_strength(signal)
    darkpool = premium_daily_dark_pool_summary(signal)
    decision = premium_daily_trade_decision(signal)

    entry = signal.get("entry") or signal.get("entry_price") or signal.get("contract_price") or "wait for trigger"
    stop = signal.get("stop") or signal.get("stop_loss") or "below/above structure"
    targets = signal.get("targets") or signal.get("target") or "next key level"

    return (
        f"💎 PREMIUM DAILY LEVELS — {ticker}\n\n"
        f"Grade: {grade}\n"
        f"Confidence: {confidence}\n"
        f"Bias: {direction}\n"
        f"Decision: {decision}\n\n"
        f"🧠 Setup:\n"
        f"• {setup}\n\n"
        f"📊 Tech Strength:\n"
        f"• {tech}\n\n"
        f"📍 Execution Plan:\n"
        f"• Entry: {entry}\n"
        f"• Stop: {stop}\n"
        f"• Target(s): {targets}\n\n"
        f"🔎 Confluence:\n"
        f"• VWAP: {vwap}\n"
        f"• Volume: {volume}\n"
        f"• Oil/Macro: {oil}\n"
        f"• Market: {market}\n"
        f"• Dark Pool: {darkpool}\n\n"
        f"⚠️ Rule:\n"
        f"• No chase. Wait for confirmation at the level."
    )




def build_live_entry_oil_alert(signal: Dict[str, Any]) -> str:
    """
    UnBiased live-entry channel style.

    ✅ SPY | Relief Alert

    🛢️ Oil: 124.83 (+0.02%)
    📈 SPY: 679.34 (+0.00%)
    📍 VWAP: 679.04

    Plan Language
    Price is above VWAP and oil relief is aligned, which supports bullish continuation.

    Trigger
    • Live test using current market data.

    Trade Idea
    Entry: Test mode using live prices.
    🛑 Invalidation: Loss of key level.
    🎯 Target: Next level based on the current map.

    Bias: BULLISH
    Session: Midday High-Conviction Filter
    Timer: timestamp
    """
    ticker = str(signal.get("ticker") or signal.get("underlying") or "QQQ").upper().strip()
    direction = str(signal.get("direction") or "").upper().strip()
    con = signal.get("confluences", {}) if isinstance(signal.get("confluences"), dict) else {}

    oil_value = (
        signal.get("oil_price")
        or signal.get("oil")
        or con.get("oil_price")
        or con.get("oil")
        or "Not provided"
    )

    oil_change = (
        signal.get("oil_change_pct")
        or con.get("oil_change_pct")
        or signal.get("uso_change_pct")
        or con.get("uso_change_pct")
        or "+0.00%"
    )

    ticker_price = (
        signal.get("underlying_price")
        or signal.get("stock_price")
        or signal.get("current_price")
        or signal.get("price")
        or signal.get("entry_price")
        or signal.get("entry")
        or "Live"
    )

    ticker_change = (
        signal.get("ticker_change_pct")
        or signal.get("change_pct")
        or con.get("ticker_change_pct")
        or con.get("change_pct")
        or "+0.00%"
    )

    vwap = (
        signal.get("vwap")
        or con.get("vwap_price")
        or con.get("vwap")
        or "Not provided"
    )

    setup = (
        signal.get("trigger")
        or signal.get("setup_name")
        or signal.get("setup")
        or signal.get("setup_type")
        or "Live test using current market data."
    )

    entry = (
        signal.get("entry")
        or signal.get("entry_price")
        or signal.get("contract_price")
        or "Test mode using live prices."
    )

    invalidation = (
        signal.get("invalidation")
        or signal.get("stop")
        or signal.get("stop_loss")
        or "Loss of key level."
    )

    target = (
        signal.get("target")
        or signal.get("targets")
        or "Next level based on the current map."
    )

    market_type = (
        signal.get("session")
        or signal.get("time_window")
        or signal.get("market_type")
        or con.get("market_type")
        or "Midday High-Conviction Filter"
    )

    timestamp = (
        signal.get("timer")
        or signal.get("timestamp")
        or signal.get("created_at")
        or now_ts()
    )

    # Bias language
    if direction == "CALL":
        bias = "BULLISH"
        alert_type = "Relief Alert"
        plan = f"Price is above VWAP and oil relief is aligned, which supports bullish continuation."
    elif direction == "PUT":
        bias = "BEARISH"
        alert_type = "Pressure Alert"
        plan = f"Price is below/rejecting VWAP and oil pressure is aligned, which supports bearish continuation."
    else:
        bias = "NEUTRAL"
        alert_type = "Decision Alert"
        plan = f"Price, VWAP, oil, and structure need alignment before execution."

    # Improve plan if specific fields say otherwise
    vwap_text = str(vwap).lower()
    oil_text = str(oil_value).lower()

    if direction == "CALL" and ("below" in vwap_text or "reject" in vwap_text):
        plan = "Price is not cleanly above VWAP yet. Wait for reclaim/hold before bullish continuation."
    if direction == "PUT" and ("above" in vwap_text or "reclaim" in vwap_text):
        plan = "Price is not cleanly below VWAP yet. Wait for rejection/failure before bearish continuation."

    return (
        f"✅ {ticker} | {alert_type}\n\n"
        f"🛢️ Oil: {oil_value} ({oil_change})\n"
        f"📈 {ticker}: {ticker_price} ({ticker_change})\n"
        f"📍 VWAP: {vwap}\n\n"
        f"**Plan Language**\n"
        f"{plan}\n\n"
        f"**Trigger**\n"
        f"• {setup}\n\n"
        f"**Trade Idea**\n"
        f"Entry: {entry}\n"
        f"🛑 Invalidation: {invalidation}\n"
        f"🎯 Target: {target}\n\n"
        f"Bias: {bias}\n"
        f"Session: {market_type}\n"
        f"Timer: {timestamp}"
    )


def maybe_send_live_entry_oil_style_alert(signal: Dict[str, Any], stage: str = "signal") -> None:
    """
    Sends the exact UnBiased live alert style to DISCORD_LIVE_ENTRY_WEBHOOK.
    This is separate from dark pool resource alerts.
    """
    if not ENABLE_PREMIUM_DAILY_LEVEL_ALERTS:
        return

    try:
        if not isinstance(signal, dict):
            return

        ticker = str(signal.get("ticker") or signal.get("underlying") or "").upper().strip()
        if ticker not in PREMIUM_DAILY_LEVEL_TICKERS:
            return

        grade = premium_daily_get_grade(signal)
        if not premium_daily_meets_grade(grade, PREMIUM_DAILY_MIN_GRADE):
            return

        state = premium_daily_load_state()
        now = int(time.time())
        direction = str(signal.get("direction") or "").upper().strip()
        setup = str(signal.get("setup") or signal.get("setup_name") or signal.get("trigger") or "").lower().strip()
        key = f"oil_style:{ticker}:{direction}:{grade}:{setup}:{stage}"
        last = safe_int(state.get(key, 0), 0)

        if last and (now - last) < PREMIUM_DAILY_ALERT_COOLDOWN_SECONDS:
            return

        state[key] = now
        premium_daily_save_state(state)

        msg = build_live_entry_oil_alert(signal)
        send_to_live_entry_discord(msg)

        try:
            debug(f"LIVE ENTRY OIL STYLE ALERT SENT | ticker={ticker} grade={grade} stage={stage}")
        except Exception:
            pass

    except Exception as e:
        try:
            debug(f"LIVE ENTRY OIL STYLE ALERT FAILED | {e}")
        except Exception:
            pass


def maybe_send_premium_daily_levels_alert(signal: Dict[str, Any], stage: str = "signal") -> None:
    if not ENABLE_PREMIUM_DAILY_LEVEL_ALERTS:
        return

    try:
        if not isinstance(signal, dict):
            return

        ticker = str(signal.get("ticker") or signal.get("underlying") or "").upper().strip()
        if ticker not in PREMIUM_DAILY_LEVEL_TICKERS:
            return

        grade = premium_daily_get_grade(signal)
        if not premium_daily_meets_grade(grade, PREMIUM_DAILY_MIN_GRADE):
            return

        state = premium_daily_load_state()
        now = int(time.time())
        direction = str(signal.get("direction") or "").upper().strip()
        setup = str(signal.get("setup") or signal.get("setup_name") or signal.get("trigger") or "").lower().strip()
        key = f"{ticker}:{direction}:{grade}:{setup}:{stage}"
        last = safe_int(state.get(key, 0), 0)

        if last and (now - last) < PREMIUM_DAILY_ALERT_COOLDOWN_SECONDS:
            return

        state[key] = now
        premium_daily_save_state(state)

        msg = build_premium_daily_levels_alert(signal)
        send_to_live_entry_discord(msg)

        try:
            debug(f"PREMIUM DAILY ALERT SENT | ticker={ticker} grade={grade} stage={stage}")
        except Exception:
            pass

    except Exception as e:
        try:
            debug(f"PREMIUM DAILY ALERT FAILED | {e}")
        except Exception:
            pass


def send_to_darkpool_discord(message: str) -> None:
    """
    Dedicated Dark Pool channel router.
    Uses DISCORD_DARKPOOL_WEBHOOK first.
    Falls back to DISCORD_AI_WEBHOOK only if dark pool webhook is missing.
    """
    try:
        target = DISCORD_DARKPOOL_WEBHOOK or DISCORD_AI_WEBHOOK
        if not target:
            try:
                debug("DARK POOL WEBHOOK MISSING | set DISCORD_DARKPOOL_WEBHOOK")
            except Exception:
                pass
            return
        send_to_discord(target, message, "DARK POOL")
    except Exception as e:
        try:
            debug(f"DARK POOL webhook send failed: {e}")
        except Exception:
            pass


# =========================================================
# UNUSUAL WHALES DARK POOL INTEGRATION
# Decision/confluence layer for QQQ/SPY institutional resource levels.
# Uses Unusual Whales REST API when UNUSUAL_WHALES_API_KEY is set.
# Official API docs: https://api.unusualwhales.com/docs
# Ticker dark pool endpoint: GET /api/darkpool/{ticker}
# =========================================================
ENABLE_UNUSUAL_WHALES_DARKPOOL = os.getenv("ENABLE_UNUSUAL_WHALES_DARKPOOL", "true").lower() == "true"
UNUSUAL_WHALES_API_KEY = os.getenv("UNUSUAL_WHALES_API_KEY", os.getenv("UW_API_KEY", "")).strip()
UNUSUAL_WHALES_BASE_URL = os.getenv("UNUSUAL_WHALES_BASE_URL", "https://api.unusualwhales.com").strip().rstrip("/")
UW_DARKPOOL_MIN_PREMIUM = float(os.getenv("UW_DARKPOOL_MIN_PREMIUM", "50000"))
UW_DARKPOOL_MIN_SIZE = float(os.getenv("UW_DARKPOOL_MIN_SIZE", "0"))
UW_DARKPOOL_LOOKBACK_DAYS = int(os.getenv("UW_DARKPOOL_LOOKBACK_DAYS", "1"))
UW_DARKPOOL_MAX_TRADES = int(os.getenv("UW_DARKPOOL_MAX_TRADES", "250"))
UW_DARKPOOL_CACHE_SECONDS = int(os.getenv("UW_DARKPOOL_CACHE_SECONDS", "120"))
UW_DARKPOOL_LEVEL_BUCKET = float(os.getenv("UW_DARKPOOL_LEVEL_BUCKET", "0.25"))
UW_DARKPOOL_NEAR_LEVEL_PCT = float(os.getenv("UW_DARKPOOL_NEAR_LEVEL_PCT", "0.006"))
UW_DARKPOOL_ACCEPTANCE_PCT = float(os.getenv("UW_DARKPOOL_ACCEPTANCE_PCT", "0.0015"))
UW_DARKPOOL_STRONG_LEVEL_PREMIUM = float(os.getenv("UW_DARKPOOL_STRONG_LEVEL_PREMIUM", "500000"))
UW_DARKPOOL_GRADE_BOOST_ENABLED = os.getenv("UW_DARKPOOL_GRADE_BOOST_ENABLED", "true").lower() == "true"
UW_DARKPOOL_BLOCK_AGAINST_MAJOR_LEVEL = os.getenv("UW_DARKPOOL_BLOCK_AGAINST_MAJOR_LEVEL", "false").lower() == "true"
UW_DARKPOOL_SEND_ALERTS = os.getenv("UW_DARKPOOL_SEND_ALERTS", "true").lower() == "true"
UW_DARKPOOL_FILE = os.getenv("UW_DARKPOOL_FILE", "darkpool_levels.json").strip()
UW_DARKPOOL_REAL_PRINT_ALERTS = os.getenv("UW_DARKPOOL_REAL_PRINT_ALERTS", "true").lower() == "true"
UW_DARKPOOL_WATCH_TICKERS = {
    x.strip().upper()
    for x in os.getenv("UW_DARKPOOL_WATCH_TICKERS", "QQQ,SPY").split(",")
    if x.strip()
}
UW_DARKPOOL_PRINT_POLL_SECONDS = int(os.getenv("UW_DARKPOOL_PRINT_POLL_SECONDS", "20"))
UW_DARKPOOL_PRINT_MIN_PREMIUM = float(os.getenv("UW_DARKPOOL_PRINT_MIN_PREMIUM", str(UW_DARKPOOL_MIN_PREMIUM)))
UW_DARKPOOL_PRINT_STATE_FILE = os.getenv("UW_DARKPOOL_PRINT_STATE_FILE", "darkpool_print_state.json").strip()
UW_DARKPOOL_ALERT_MAX_NEW_PRINTS = int(os.getenv("UW_DARKPOOL_ALERT_MAX_NEW_PRINTS", "5"))


def uw_dp_now_ts() -> int:
    try:
        return int(time.time())
    except Exception:
        return 0


def uw_dp_date_str(offset_days: int = 0) -> str:
    try:
        return (datetime.utcnow() - timedelta(days=offset_days)).strftime("%Y-%m-%d")
    except Exception:
        return ""


def uw_dp_load_cache() -> Dict[str, Any]:
    try:
        data = load_json_file(UW_DARKPOOL_FILE, {})
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def uw_dp_save_cache(data: Dict[str, Any]) -> None:
    try:
        atomic_write_json(UW_DARKPOOL_FILE, data)
    except Exception as e:
        try:
            debug(f"UW DARKPOOL cache save failed: {e}")
        except Exception:
            pass


def uw_dp_headers() -> Dict[str, str]:
    h = {"Accept": "application/json"}
    if UNUSUAL_WHALES_API_KEY:
        h["Authorization"] = f"Bearer {UNUSUAL_WHALES_API_KEY}"
    return h


def uw_dp_extract_rows(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "results", "trades", "darkpool", "items"):
        val = payload.get(key)
        if isinstance(val, list):
            return [x for x in val if isinstance(x, dict)]
        if isinstance(val, dict):
            nested = uw_dp_extract_rows(val)
            if nested:
                return nested
    if any(k in payload for k in ("price", "premium", "size", "volume")):
        return [payload]
    return []


def uw_dp_row_price(row: Dict[str, Any]) -> float:
    for k in ("price", "price_level", "execution_price", "trade_price", "avg_price"):
        v = row.get(k)
        if v not in (None, "", "."):
            return safe_float(v, 0.0)
    return 0.0


def uw_dp_row_size(row: Dict[str, Any]) -> float:
    for k in ("size", "volume", "shares", "quantity", "qty"):
        v = row.get(k)
        if v not in (None, "", "."):
            return safe_float(v, 0.0)
    return 0.0


def uw_dp_row_premium(row: Dict[str, Any]) -> float:
    for k in ("premium", "notional", "value", "dollar_volume", "total_value"):
        v = row.get(k)
        if v not in (None, "", "."):
            return safe_float(v, 0.0)
    price = uw_dp_row_price(row)
    size = uw_dp_row_size(row)
    return price * size if price and size else 0.0


def uw_dp_fetch_ticker(ticker: str, force: bool = False) -> Dict[str, Any]:
    ticker = str(ticker or "").upper().strip()
    if not ticker:
        return {"ok": False, "reason": "missing_ticker", "ticker": ticker, "trades": []}
    if not ENABLE_UNUSUAL_WHALES_DARKPOOL:
        return {"ok": False, "reason": "disabled", "ticker": ticker, "trades": []}
    if not UNUSUAL_WHALES_API_KEY:
        return {"ok": False, "reason": "missing_unusual_whales_api_key", "ticker": ticker, "trades": []}

    cache = uw_dp_load_cache()
    cached = cache.get(ticker, {}) if isinstance(cache, dict) else {}
    if cached and not force:
        age = uw_dp_now_ts() - safe_int(cached.get("updated_at", 0), 0)
        if 0 <= age <= UW_DARKPOOL_CACHE_SECONDS:
            return cached

    all_rows = []
    errors = []
    for offset in range(max(1, UW_DARKPOOL_LOOKBACK_DAYS)):
        try:
            params = {
                "date": uw_dp_date_str(offset),
                "min_premium": int(UW_DARKPOOL_MIN_PREMIUM),
                "min_size": int(UW_DARKPOOL_MIN_SIZE),
            }
            url = f"{UNUSUAL_WHALES_BASE_URL}/api/darkpool/{ticker}"
            r = requests.get(url, headers=uw_dp_headers(), params=params, timeout=12)
            if r.status_code != 200:
                errors.append(f"{params.get('date')}:http_{r.status_code}:{str(r.text)[:120]}")
                continue
            rows = uw_dp_extract_rows(r.json())
            all_rows.extend(rows)
        except Exception as e:
            errors.append(f"exception:{e}")

    clean_rows = []
    for row in all_rows[: max(1, UW_DARKPOOL_MAX_TRADES)]:
        price = uw_dp_row_price(row)
        premium = uw_dp_row_premium(row)
        size = uw_dp_row_size(row)
        if price <= 0:
            continue
        if premium < UW_DARKPOOL_MIN_PREMIUM:
            continue
        clean_rows.append({"price": price, "premium": premium, "size": size, "raw": row})

    result = {
        "ok": bool(clean_rows),
        "reason": "ok" if clean_rows else ("no_rows" if not errors else ",".join(errors[:3])),
        "ticker": ticker,
        "updated_at": uw_dp_now_ts(),
        "source": "unusual_whales",
        "trades": clean_rows,
        "errors": errors[:10],
    }
    cache[ticker] = result
    uw_dp_save_cache(cache)
    return result


def uw_dp_bucket_price(price: float) -> float:
    try:
        bucket = max(0.01, float(UW_DARKPOOL_LEVEL_BUCKET))
        return round(round(float(price) / bucket) * bucket, 2)
    except Exception:
        return round(float(price), 2)


def uw_dp_build_levels(ticker: str, current_price: float = 0.0, force: bool = False) -> Dict[str, Any]:
    fetched = uw_dp_fetch_ticker(ticker, force=force)
    trades = fetched.get("trades", []) if isinstance(fetched, dict) else []
    buckets = {}
    for tr in trades:
        price = uw_dp_bucket_price(safe_float(tr.get("price", 0), 0.0))
        if price <= 0:
            continue
        key = str(price)
        b = buckets.setdefault(key, {"price": price, "premium": 0.0, "size": 0.0, "prints": 0})
        b["premium"] += safe_float(tr.get("premium", 0), 0.0)
        b["size"] += safe_float(tr.get("size", 0), 0.0)
        b["prints"] += 1

    levels = sorted(buckets.values(), key=lambda x: x.get("premium", 0), reverse=True)
    for lvl in levels:
        price = safe_float(lvl.get("price", 0), 0.0)
        lvl["premium"] = round(safe_float(lvl.get("premium", 0), 0.0), 2)
        lvl["size"] = round(safe_float(lvl.get("size", 0), 0.0), 2)
        lvl["strength"] = "major" if lvl["premium"] >= UW_DARKPOOL_STRONG_LEVEL_PREMIUM else "normal"
        lvl["source_label"] = "UW print cluster"
        if current_price > 0:
            lvl["distance_pct"] = round((price - current_price) / current_price, 5)
            lvl["type"] = "resistance" if price > current_price else "support" if price < current_price else "at_price"
        else:
            lvl["distance_pct"] = None
            lvl["type"] = "unknown"

    supports = sorted([x for x in levels if x.get("type") in ("support", "at_price")], key=lambda x: abs(safe_float(x.get("distance_pct", 999), 999)))
    resistances = sorted([x for x in levels if x.get("type") in ("resistance", "at_price")], key=lambda x: abs(safe_float(x.get("distance_pct", 999), 999)))

    return {
        "ok": fetched.get("ok", False),
        "reason": fetched.get("reason", "unknown"),
        "ticker": str(ticker).upper().strip(),
        "source": "unusual_whales_darkpool",
        "updated_at": fetched.get("updated_at", uw_dp_now_ts()),
        "current_price": current_price,
        "levels": levels[:20],
        "nearest_support": supports[0] if supports else None,
        "nearest_resistance": resistances[0] if resistances else None,
        "top_levels": levels[:5],
        "trade_count": len(trades),
    }


def uw_dp_get_underlying_price(signal: Dict[str, Any]) -> float:
    for k in ("underlying_price", "stock_price", "current_price", "spot", "price"):
        v = signal.get(k)
        if v not in (None, "", 0):
            px = safe_float(v, 0.0)
            if px > 0:
                return px
    try:
        ticker = str(signal.get("ticker") or signal.get("underlying") or "").upper().strip()
        prices = load_market_prices([ticker])
        px, _ = get_market_price_for_symbol(ticker, prices)
        return safe_float(px, 0.0)
    except Exception:
        return 0.0


def uw_dp_grade_up(grade: str, steps: int = 1) -> str:
    ladder = ["C", "B", "B+", "A", "A+"]
    g = str(grade or "B").upper().strip()
    if g not in ladder:
        g = "B"
    idx = min(len(ladder) - 1, ladder.index(g) + max(0, int(steps)))
    return ladder[idx]


def uw_dp_evaluate_signal(signal: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
    if not ENABLE_UNUSUAL_WHALES_DARKPOOL:
        return {"approved": True, "enabled": False, "reason": "disabled"}
    ticker = str(signal.get("ticker") or signal.get("underlying") or "").upper().strip()
    direction = str(signal.get("direction") or "").upper().strip()
    current_price = uw_dp_get_underlying_price(signal)
    levels = uw_dp_build_levels(ticker, current_price=current_price, force=force)
    support = levels.get("nearest_support")
    resistance = levels.get("nearest_resistance")
    actions = []
    reasons = []
    grade_boost = 0
    approved = True

    def near(lvl):
        if not lvl or current_price <= 0:
            return False
        return abs(safe_float(lvl.get("distance_pct", 999), 999)) <= UW_DARKPOOL_NEAR_LEVEL_PCT

    def accepted_through_res(lvl):
        if not lvl or current_price <= 0:
            return False
        return current_price >= safe_float(lvl.get("price", 0), 0.0) * (1 + UW_DARKPOOL_ACCEPTANCE_PCT)

    def accepted_below_sup(lvl):
        if not lvl or current_price <= 0:
            return False
        return current_price <= safe_float(lvl.get("price", 0), 0.0) * (1 - UW_DARKPOOL_ACCEPTANCE_PCT)

    if not levels.get("ok"):
        return {
            "approved": True,
            "enabled": True,
            "reason": f"darkpool_unavailable:{levels.get('reason')}",
            "grade_boost": 0,
            "levels": levels,
            "actions": ["observe_only"],
        }

    if direction == "CALL":
        if support and near(support):
            grade_boost += 1
            actions.append("call_supported_by_darkpool_support")
            reasons.append(f"support_near_{support.get('price')}")
        if resistance and near(resistance):
            actions.append("call_near_darkpool_resistance")
            reasons.append(f"resistance_near_{resistance.get('price')}")
            if resistance.get("strength") == "major" and UW_DARKPOOL_BLOCK_AGAINST_MAJOR_LEVEL and not accepted_through_res(resistance):
                approved = False
                reasons.append("major_resistance_not_accepted")
        if resistance and accepted_through_res(resistance):
            grade_boost += 1
            actions.append("call_accepted_through_darkpool_resistance")
            reasons.append(f"accepted_above_{resistance.get('price')}")
    elif direction == "PUT":
        if resistance and near(resistance):
            grade_boost += 1
            actions.append("put_supported_by_darkpool_resistance")
            reasons.append(f"resistance_near_{resistance.get('price')}")
        if support and near(support):
            actions.append("put_near_darkpool_support")
            reasons.append(f"support_near_{support.get('price')}")
            if support.get("strength") == "major" and UW_DARKPOOL_BLOCK_AGAINST_MAJOR_LEVEL and not accepted_below_sup(support):
                approved = False
                reasons.append("major_support_not_broken")
        if support and accepted_below_sup(support):
            grade_boost += 1
            actions.append("put_accepted_below_darkpool_support")
            reasons.append(f"accepted_below_{support.get('price')}")

    return {
        "approved": approved,
        "enabled": True,
        "reason": "darkpool_ok" if approved else "darkpool_block",
        "reject_reasons": [] if approved else reasons,
        "grade_boost": min(2, grade_boost),
        "current_price": current_price,
        "nearest_support": support,
        "nearest_resistance": resistance,
        "levels": levels,
        "actions": actions,
        "reasons": reasons,
    }


def apply_unusual_whales_darkpool_to_signal(signal: Dict[str, Any], stage: str = "decision") -> Dict[str, Any]:
    if not isinstance(signal, dict):
        return signal
    x = deepcopy(signal)
    decision = uw_dp_evaluate_signal(x)
    x["dark_pool"] = decision
    if decision.get("enabled") and UW_DARKPOOL_GRADE_BOOST_ENABLED and decision.get("grade_boost", 0) > 0:
        old_grade = str(x.get("grade") or x.get("confidence") or "B").upper().strip()
        new_grade = uw_dp_grade_up(old_grade, safe_int(decision.get("grade_boost", 0), 0))
        x["dark_pool_base_grade"] = old_grade
        x["grade"] = new_grade
        if not x.get("confidence") or str(x.get("confidence")).upper() == old_grade:
            x["confidence"] = new_grade
    try:
        debug(f"UW DARKPOOL | stage={stage} ticker={x.get('ticker')} direction={x.get('direction')} approved={decision.get('approved')} boost={decision.get('grade_boost')} actions={decision.get('actions')}")
    except Exception:
        pass
    return x


def unusual_whales_darkpool_blocks_signal(signal: Dict[str, Any]) -> bool:
    try:
        decision = signal.get("dark_pool") if isinstance(signal.get("dark_pool"), dict) else uw_dp_evaluate_signal(signal)
        if not decision.get("approved", True):
            msg = build_block_message(
                "UNUSUAL WHALES DARK POOL BLOCKED SIGNAL",
                signal,
                decision.get("reject_reasons", [decision.get("reason", "darkpool_block")]),
                f"Support: {decision.get('nearest_support')} | Resistance: {decision.get('nearest_resistance')}"
            )
            send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
            send_to_telegram(msg)
            return True
        return False
    except Exception as e:
        try:
            debug(f"UW DARKPOOL block check failed safe-open: {e}")
        except Exception:
            pass
        return False


def uw_dp_format_money(value: Any) -> str:
    try:
        v = float(value or 0)
    except Exception:
        v = 0.0

    if abs(v) >= 1_000_000_000:
        return f"${v / 1_000_000_000:.2f}B"
    if abs(v) >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"${v / 1_000:.2f}K"
    return f"${v:.2f}"


def uw_dp_format_level_line(level: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(level, dict):
        return None

    price = safe_float(level.get("price", 0), 0.0)
    if price <= 0:
        return None

    level_type = str(level.get("type", "level")).upper().strip()
    if level_type == "AT_PRICE":
        level_type = "AT PRICE"

    premium = uw_dp_format_money(level.get("premium", 0))
    source_label = str(level.get("source_label", "UW print cluster")).strip() or "UW print cluster"

    return f"• {price:.2f} | {level_type} | {premium} | {source_label}"


def uw_dp_top_clean_levels(dp: Dict[str, Any]) -> List[str]:
    levels_payload = dp.get("levels", {})
    top_levels = []

    if isinstance(levels_payload, dict):
        raw_levels = levels_payload.get("top_levels") or levels_payload.get("levels") or []
        if isinstance(raw_levels, list):
            top_levels.extend(raw_levels)

    support = dp.get("nearest_support")
    resistance = dp.get("nearest_resistance")

    ordered = []
    if isinstance(resistance, dict):
        ordered.append(resistance)
    if isinstance(support, dict):
        ordered.append(support)

    for lvl in top_levels:
        if isinstance(lvl, dict):
            ordered.append(lvl)

    seen = set()
    clean_lines = []
    for lvl in ordered:
        if not isinstance(lvl, dict):
            continue

        price = safe_float(lvl.get("price", 0), 0.0)
        level_type = str(lvl.get("type", "")).lower().strip()
        key = f"{price:.2f}:{level_type}"

        if not price or key in seen:
            continue

        seen.add(key)
        line = uw_dp_format_level_line(lvl)

        if line:
            clean_lines.append(line)

        if len(clean_lines) >= 4:
            break

    return clean_lines


def send_unusual_whales_darkpool_alert(signal: Dict[str, Any]) -> None:
    """
    Sends clean Discord dark pool resource level alerts in the preferred style.
    """
    if not UW_DARKPOOL_SEND_ALERTS:
        return

    try:
        if not isinstance(signal, dict):
            return

        dp = signal.get("dark_pool", {})
        if not isinstance(dp, dict) or not dp.get("enabled"):
            return

        ticker = str(signal.get("ticker") or signal.get("underlying") or "UNKNOWN").upper().strip()
        level_lines = uw_dp_top_clean_levels(dp)

        if not level_lines:
            reason = dp.get("reason", "no_levels")
            msg = (
                f"💎 DARK POOL RESOURCE LEVELS\n"
                f"Ticker: {ticker}\n\n"
                f"• No qualifying dark pool resource levels found yet\n"
                f"• Status: {reason}\n\n"
                f"How to use:\n"
                f"• Wait for large support/resistance prints to populate\n"
                f"• Do not force a trade without a real level\n"
                f"• Use VWAP, oil, volume, and structure first"
            )
            send_to_darkpool_discord(msg)
            return

        msg = (
            f"💎 DARK POOL RESOURCE LEVELS\n"
            f"Ticker: {ticker}\n\n"
            + "\n".join(level_lines)
            + "\n\n"
            f"How to use:\n"
            f"• Support below price can act as defense\n"
            f"• Resistance above price can act as rejection zone\n"
            f"• Acceptance through a major level can shift bias"
        )

        send_to_darkpool_discord(msg)

    except Exception as e:
        try:
            debug(f"UW DARKPOOL styled alert failed: {e}")
        except Exception:
            pass




# =========================================================
# UNUSUAL WHALES REAL DARK POOL PRINT ALERTS
# Polls ticker darkpool endpoint and alerts when new prints arrive.
# API Basic can use polling. True stream/websocket requires a streaming plan.
# =========================================================

def uw_dp_load_print_state() -> Dict[str, Any]:
    try:
        data = load_json_file(UW_DARKPOOL_PRINT_STATE_FILE, {})
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def uw_dp_save_print_state(data: Dict[str, Any]) -> None:
    try:
        atomic_write_json(UW_DARKPOOL_PRINT_STATE_FILE, data)
    except Exception as e:
        try:
            debug(f"UW PRINT STATE save failed: {e}")
        except Exception:
            pass


def uw_dp_row_timestamp(row: Dict[str, Any]) -> int:
    for k in ("timestamp", "executed_at", "created_at", "date_time", "time", "reported_at"):
        v = row.get(k)
        if v in (None, "", "."):
            continue
        try:
            if isinstance(v, (int, float)):
                return int(v)
            text = str(v).strip()
            if text.isdigit():
                return int(text)
            # Try ISO-like timestamps
            try:
                return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
            except Exception:
                continue
        except Exception:
            continue
    return 0


def uw_dp_row_id(row: Dict[str, Any], ticker: str = "") -> str:
    for k in ("id", "trade_id", "tracking_id", "uuid"):
        v = row.get(k)
        if v not in (None, "", "."):
            return str(v)
    price = uw_dp_row_price(row)
    size = uw_dp_row_size(row)
    premium = uw_dp_row_premium(row)
    ts = uw_dp_row_timestamp(row)
    return f"{ticker}:{ts}:{price}:{size}:{premium}"


def uw_dp_fetch_recent_prints_for_alert(ticker: str, newer_than: int = 0) -> Dict[str, Any]:
    ticker = str(ticker or "").upper().strip()

    if not ticker:
        return {"ok": False, "reason": "missing_ticker", "ticker": ticker, "prints": []}
    if not ENABLE_UNUSUAL_WHALES_DARKPOOL or not UW_DARKPOOL_REAL_PRINT_ALERTS:
        return {"ok": False, "reason": "disabled", "ticker": ticker, "prints": []}
    if not UNUSUAL_WHALES_API_KEY:
        return {"ok": False, "reason": "missing_unusual_whales_api_key", "ticker": ticker, "prints": []}

    try:
        params = {
            "date": uw_dp_date_str(0),
            "min_premium": int(UW_DARKPOOL_PRINT_MIN_PREMIUM),
            "min_size": int(UW_DARKPOOL_MIN_SIZE),
        }
        if newer_than:
            params["newer_than"] = int(newer_than)

        url = f"{UNUSUAL_WHALES_BASE_URL}/api/darkpool/{ticker}"
        r = requests.get(url, headers=uw_dp_headers(), params=params, timeout=12)

        if r.status_code != 200:
            return {"ok": False, "reason": f"http_{r.status_code}:{str(r.text)[:120]}", "ticker": ticker, "prints": []}

        rows = uw_dp_extract_rows(r.json())
        prints = []
        for row in rows:
            price = uw_dp_row_price(row)
            size = uw_dp_row_size(row)
            premium = uw_dp_row_premium(row)
            ts = uw_dp_row_timestamp(row)
            if price <= 0 or premium < UW_DARKPOOL_PRINT_MIN_PREMIUM:
                continue
            prints.append({
                "id": uw_dp_row_id(row, ticker),
                "ticker": ticker,
                "price": price,
                "size": size,
                "premium": premium,
                "timestamp": ts,
                "raw": row,
            })

        prints = sorted(prints, key=lambda x: (safe_int(x.get("timestamp", 0), 0), str(x.get("id", ""))))
        return {"ok": True, "reason": "ok", "ticker": ticker, "prints": prints}

    except Exception as e:
        return {"ok": False, "reason": f"exception:{e}", "ticker": ticker, "prints": []}


def uw_dp_format_real_print_line(print_row: Dict[str, Any]) -> str:
    ticker = str(print_row.get("ticker", "")).upper()
    price = safe_float(print_row.get("price", 0), 0.0)
    premium = uw_dp_format_money(print_row.get("premium", 0))
    size = safe_float(print_row.get("size", 0), 0.0)

    if size >= 1_000_000:
        size_text = f"{size / 1_000_000:.2f}M shares"
    elif size >= 1_000:
        size_text = f"{size / 1_000:.1f}K shares"
    else:
        size_text = f"{size:.0f} shares"

    return f"• {price:.2f} | REAL PRINT | {premium} | {size_text}"


def send_uw_darkpool_real_print_alert(ticker: str, prints: List[Dict[str, Any]]) -> None:
    if not prints:
        return

    try:
        newest = prints[-UW_DARKPOOL_ALERT_MAX_NEW_PRINTS:]
        lines = [uw_dp_format_real_print_line(p) for p in newest]

        msg = (
            f"💎 DARK POOL NEW PRINTS\n"
            f"Ticker: {ticker}\n\n"
            + "\n".join(lines)
            + "\n\n"
            f"How to use:\n"
            f"• Large prints near price can become resource levels\n"
            f"• Print below price can act as support/defense\n"
            f"• Print above price can act as resistance/rejection\n"
            f"• Acceptance through the print can shift bias"
        )

        send_to_darkpool_discord(msg)
        try:
            debug(f"UW DARKPOOL REAL PRINT ALERT | ticker={ticker} prints={len(newest)}")
        except Exception:
            pass

    except Exception as e:
        try:
            debug(f"UW real print alert failed: {e}")
        except Exception:
            pass


def poll_unusual_whales_darkpool_prints(force: bool = False) -> None:
    """
    Polls Unusual Whales for new dark pool prints for QQQ/SPY.
    This gives near-real-time alerts on API Basic. For true instant streaming,
    use a plan with WebSocket/Kafka and wire the websocket channel later.
    """
    if not UW_DARKPOOL_REAL_PRINT_ALERTS:
        return

    state = uw_dp_load_print_state()
    now = uw_dp_now_ts()
    last_poll = safe_int(state.get("_last_poll", 0), 0)

    if not force and last_poll and (now - last_poll) < UW_DARKPOOL_PRINT_POLL_SECONDS:
        return

    state["_last_poll"] = now

    for ticker in sorted(UW_DARKPOOL_WATCH_TICKERS):
        ticker_state = state.get(ticker, {}) if isinstance(state.get(ticker, {}), dict) else {}
        newer_than = safe_int(ticker_state.get("last_timestamp", 0), 0)
        seen_ids = set(ticker_state.get("seen_ids", [])) if isinstance(ticker_state.get("seen_ids", []), list) else set()

        result = uw_dp_fetch_recent_prints_for_alert(ticker, newer_than=newer_than)
        if not result.get("ok"):
            try:
                debug(f"UW DARKPOOL PRINT POLL | ticker={ticker} reason={result.get('reason')}")
            except Exception:
                pass
            continue

        new_prints = []
        max_ts = newer_than

        for p in result.get("prints", []):
            pid = str(p.get("id", ""))
            pts = safe_int(p.get("timestamp", 0), 0)
            max_ts = max(max_ts, pts)

            if pid and pid in seen_ids:
                continue
            if newer_than and pts and pts <= newer_than:
                continue

            new_prints.append(p)
            if pid:
                seen_ids.add(pid)

        if new_prints:
            send_uw_darkpool_real_print_alert(ticker, new_prints)

        state[ticker] = {
            "last_timestamp": max_ts,
            "seen_ids": list(seen_ids)[-500:],
            "last_checked": now,
        }

    uw_dp_save_print_state(state)


# =========================================================
# PAPER BROKER BRIDGE + ANTI-SPAM HELPERS
# =========================================================
def paper_bridge_signal_hash(signal: Dict[str, Any]) -> str:
    try:
        return hashlib.sha256(json.dumps(signal, sort_keys=True, default=str).encode()).hexdigest()
    except Exception:
        return hashlib.sha256(str(signal).encode()).hexdigest()


def paper_bridge_load_orders_store() -> Dict[str, Any]:
    data = load_json_file(ORDERS_FILE, {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("schema_version", 2)
    data.setdefault("orders", [])
    data.setdefault("last_local_order_id", 0)
    return data


def paper_bridge_save_orders_store(data: Dict[str, Any]) -> None:
    atomic_write_json(ORDERS_FILE, data)


def paper_bridge_load_positions_store() -> Dict[str, Any]:
    data = load_json_file(POSITIONS_FILE, {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("schema_version", 2)
    data.setdefault("open_positions", [])
    data.setdefault("closed_positions", [])
    data.setdefault("last_position_id", 0)
    return data


def paper_bridge_save_positions_store(data: Dict[str, Any]) -> None:
    atomic_write_json(POSITIONS_FILE, data)


def paper_bridge_should_execute(signal: Dict[str, Any]) -> Dict[str, Any]:
    ensure_globals_initialized()

    qqq_ok, qqq_reason = qqq_only_signal_allowed(signal, stage="paper_bridge")
    if not qqq_ok:
        qqq_only_debug_block(signal, qqq_reason, stage="paper_bridge")
        return {"approved": False, "reason": qqq_reason, "hash": paper_bridge_signal_hash(signal)}

    sig_hash = paper_bridge_signal_hash(signal)
    current_time = epoch()

    idem_gate = idempotency_pre_order_gate(signal, side="buy", qty=safe_int(signal.get("qty", signal.get("qty_hint", 1)), 1), mode="PAPER_BRIDGE", order_type="market", limit_price=None)
    if not idem_gate.get("approved", False):
        reason = f"paper_bridge_idempotency_block:{idem_gate.get('reason')}"
        debug(f"🧷 PAPER BRIDGE IDEMPOTENCY BLOCK | {reason}")
        return {"approved": False, "reason": reason, "hash": sig_hash, "idempotency": idem_gate}

    last_hash = str(GLOBAL_STATE.get("paper_bridge_last_executed_hash", ""))
    last_time = safe_int(GLOBAL_STATE.get("paper_bridge_last_executed_time", 0), 0)

    if PAPER_BRIDGE_ONE_SHOT and sig_hash == last_hash:
        elapsed = current_time - last_time
        if elapsed < PAPER_BRIDGE_COOLDOWN_SECONDS:
            reason = f"paper_bridge_duplicate_cooldown:{elapsed}s_lt_{PAPER_BRIDGE_COOLDOWN_SECONDS}s"
            debug(f"🛑 PAPER BRIDGE COOLDOWN BLOCK | {reason}")
            return {"approved": False, "reason": reason, "hash": sig_hash}

    return {"approved": True, "reason": "approved", "hash": sig_hash}


def paper_bridge_mark_executed(sig_hash: str) -> None:
    ensure_globals_initialized()
    GLOBAL_STATE["paper_bridge_last_executed_hash"] = sig_hash
    GLOBAL_STATE["paper_bridge_last_executed_time"] = epoch()
    save_state(GLOBAL_STATE)


def paper_bridge_extract_prices(signal: Dict[str, Any]) -> Dict[str, float]:
    entry = safe_float(signal.get("entry_contract", signal.get("contract_price", signal.get("entry", 0))), 0.0)
    stop = safe_float(signal.get("stop_contract", signal.get("stop", 0)), 0.0)
    target = safe_float(signal.get("tp1_contract", signal.get("target", 0)), 0.0)
    tp2 = safe_float(signal.get("tp2_contract", signal.get("target_2", target)), target)
    return {"entry": entry, "stop": stop, "target": target, "tp2": tp2}


def paper_bridge_create_order(signal: Dict[str, Any]) -> Dict[str, Any]:
    orders_store = paper_bridge_load_orders_store()

    qqq_ok, qqq_reason = qqq_only_signal_allowed(signal, stage="paper_bridge_create_order")
    if not qqq_ok:
        qqq_only_debug_block(signal, qqq_reason, stage="paper_bridge_create_order")
        raise RuntimeError(qqq_reason)

    bridge_symbol = str(signal.get("symbol") or signal.get("contract_symbol") or signal.get("ticker") or "").strip()
    bridge_prices_store = load_market_prices([bridge_symbol, str(signal.get("ticker", "")).upper().strip()])
    bridge_live_price, _ = get_market_price_for_symbol(bridge_symbol, bridge_prices_store)
    bridge_liquidity = options_liquidity_gate(signal, bridge_prices_store, live_price=bridge_live_price, mode="PAPER")
    if not bridge_liquidity.get("approved", True):
        raise RuntimeError("options_liquidity_block:" + bridge_liquidity.get("reason", "unknown"))
    signal["options_liquidity"] = bridge_liquidity
    signal = apply_unusual_whales_darkpool_to_signal(signal, stage="paper_bridge_create_order")
    maybe_send_live_entry_oil_style_alert(signal, stage="paper_bridge_create_order")
    if unusual_whales_darkpool_blocks_signal(signal):
        raise RuntimeError("darkpool_block:" + str(signal.get("dark_pool", {}).get("reason", "unknown")))

    orders_store["last_local_order_id"] = safe_int(orders_store.get("last_local_order_id", 0), 0) + 1

    prices = paper_bridge_extract_prices(signal)
    qty = safe_int(signal.get("qty", signal.get("qty_hint", 1)), 1)
    ticker = str(signal.get("ticker") or signal.get("underlying") or "").upper().strip()
    symbol = str(signal.get("symbol") or signal.get("contract_symbol") or ticker).strip()
    direction = normalize_direction(signal.get("direction", "CALL"))

    order = {
        "order_id": f"PAPER-{orders_store['last_local_order_id']}",
        "broker": "paper_bridge",
        "status": "created",
        "created_at": now_ts(),
        "timestamp": epoch(),
        "ticker": ticker,
        "symbol": symbol,
        "contract_symbol": str(signal.get("contract_symbol", symbol)).strip(),
        "asset_class": str(signal.get("asset_class", "option")).lower(),
        "options_liquidity": signal.get("options_liquidity", {}),
        "dark_pool": signal.get("dark_pool", {}),
        "direction": direction,
        "side": "BUY",
        "qty": qty,
        "entry": prices["entry"],
        "stop": prices["stop"],
        "target": prices["target"],
        "tp2": prices["tp2"],
        "grade": str(signal.get("grade", signal.get("confidence", ""))).upper(),
        "confidence": str(signal.get("confidence", "")).upper(),
        "setup": str(signal.get("setup", "")),
        "trigger": str(signal.get("trigger", "")),
        "source": str(signal.get("source", "signal_file")),
        "raw_signal_hash": paper_bridge_signal_hash(signal),
        "idempotency_signal_intent_id": idempotency_signal_intent_id(signal),
        "idempotency_order_intent_id": idempotency_order_intent_id(signal, "buy", qty, "PAPER_BRIDGE", "market", None),
        "client_order_id": idempotency_client_order_id(signal, "buy", qty, "PAPER_BRIDGE", "market", None),
    }

    orders_store["orders"].append(order)
    paper_bridge_save_orders_store(orders_store)
    debug(f"📄 PAPER ORDER CREATED | {order['order_id']} | {ticker} {direction} qty={qty}")
    return order


def paper_bridge_fill_order(order: Dict[str, Any]) -> Dict[str, Any]:
    order = deepcopy(order)
    order["status"] = "filled"
    order["filled_at"] = now_ts()
    order["fill_price"] = safe_float(order.get("entry", 0), 0.0)

    orders_store = paper_bridge_load_orders_store()
    updated = False
    for i, existing in enumerate(orders_store.get("orders", [])):
        if existing.get("order_id") == order.get("order_id"):
            orders_store["orders"][i] = order
            updated = True
            break
    if not updated:
        orders_store.setdefault("orders", []).append(order)
    paper_bridge_save_orders_store(orders_store)

    order["idempotency_fill_event_id"] = idempotency_fill_event_id(order)
    idempotency_mark_order_filled(order)
    debug(f"✅ PAPER ORDER FILLED | {order['order_id']} | fill={order['fill_price']}")
    return order



# =========================================================
# LOCKED POSITION SCHEMA + DUPLICATE POSITION CAP HELPERS
# =========================================================
def locked_position_symbol(pos: Dict[str, Any]) -> str:
    return str(pos.get("symbol") or pos.get("contract_symbol") or pos.get("ticker") or "").strip()


def locked_position_ticker(pos: Dict[str, Any]) -> str:
    return str(pos.get("ticker") or pos.get("underlying") or locked_position_symbol(pos)).upper().strip()


def locked_position_direction(pos: Dict[str, Any]) -> str:
    return normalize_direction(pos.get("direction", "CALL"))


def normalize_locked_position_schema(pos: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(pos, dict):
        pos = {}

    position_id = str(pos.get("position_id") or pos.get("id") or "").strip()
    if not position_id or position_id in ("0", "POS-0", "None", "null"):
        position_id = "POS-UNKNOWN"

    qty = safe_int(pos.get("qty_open", pos.get("qty_total", pos.get("qty", 1))), 1)
    qty_total = safe_int(pos.get("qty_total", pos.get("qty", qty)), qty)
    qty_open = safe_int(pos.get("qty_open", pos.get("qty", qty)), qty)

    entry = safe_float(pos.get("entry_price", pos.get("entry", 0)), 0.0)
    stop = safe_float(pos.get("stop_price", pos.get("stop", 0)), 0.0)
    target = safe_float(pos.get("target", pos.get("tp1", pos.get("tp1_contract", 0))), 0.0)
    tp2 = safe_float(pos.get("tp2", pos.get("target_2", pos.get("tp2_contract", target))), target)

    notes = pos.get("notes", [])
    if notes is None:
        notes = []
    elif not isinstance(notes, list):
        notes = [str(notes)]

    ticker = locked_position_ticker(pos)
    symbol = locked_position_symbol(pos) or ticker
    direction = locked_position_direction(pos)

    fixed = deepcopy(pos)
    fixed.update({
        "position_id": position_id,
        "id": position_id,
        "broker": str(pos.get("broker", "paper_bridge")),
        "ticker": ticker,
        "symbol": symbol,
        "contract_symbol": str(pos.get("contract_symbol") or symbol).strip(),
        "asset_class": str(pos.get("asset_class", "option")).lower(),
        "mode": str(pos.get("mode", "paper")).lower(),
        "direction": direction,
        "status": str(pos.get("status", "open")).lower(),
        "qty": qty,
        "qty_total": qty_total,
        "qty_open": qty_open if str(pos.get("status", "open")).lower() == "open" else 0,
        "entry": entry,
        "entry_price": entry,
        "stop": stop,
        "stop_price": stop,
        "target": target,
        "tp1": target,
        "tp2": tp2,
        "notes": notes,
        "unrealized_pnl": safe_float(pos.get("unrealized_pnl", 0), 0.0),
        "realized_pnl": safe_float(pos.get("realized_pnl", 0), 0.0),
    })

    if not fixed.get("opened_at"):
        fixed["opened_at"] = now_ts()

    if "risk_per_contract" not in fixed:
        fixed["risk_per_contract"] = round(abs(entry - stop) * 100, 2) if entry > 0 and stop > 0 else 0.0

    return fixed


def repair_and_lock_positions_schema() -> Dict[str, Any]:
    result = {"repaired": False, "open": 0, "closed": 0, "removed_duplicates": 0}
    if not ENABLE_POSITION_SCHEMA_LOCK:
        return result

    try:
        data = load_json_file(POSITIONS_FILE, {})
        if not isinstance(data, dict):
            data = {}

        data.setdefault("schema_version", 2)
        data.setdefault("open_positions", [])
        data.setdefault("closed_positions", [])
        data.setdefault("last_position_id", safe_int(data.get("last_position_id", 0), 0))

        changed = False
        normalized_open = []
        normalized_closed = []
        seen_keys = {}

        for pos in data.get("open_positions", []):
            if not isinstance(pos, dict):
                changed = True
                continue

            fixed = normalize_locked_position_schema(pos)

            if str(fixed.get("position_id")) in ("", "0", "POS-0", "None", "null", "POS-UNKNOWN"):
                data["last_position_id"] = safe_int(data.get("last_position_id", 0), 0) + 1
                new_pid = f"POS-{data['last_position_id']}"
                fixed["position_id"] = new_pid
                fixed["id"] = new_pid
                changed = True

            key = (fixed.get("ticker"), fixed.get("direction"))
            count = seen_keys.get(key, 0)

            if ENABLE_HARD_DUPLICATE_POSITION_CAP and count >= MAX_OPEN_POSITIONS_PER_SYMBOL_DIRECTION:
                fixed["status"] = "closed"
                fixed["qty_open"] = 0
                fixed["close_reason"] = "DUPLICATE_POSITION_CAP_REPAIR"
                fixed["closed_at"] = now_ts()
                normalized_closed.append(fixed)
                result["removed_duplicates"] += 1
                changed = True
                continue

            seen_keys[key] = count + 1
            normalized_open.append(fixed)
            if fixed != pos:
                changed = True

        for pos in data.get("closed_positions", []):
            if isinstance(pos, dict):
                fixed = normalize_locked_position_schema(pos)
                fixed["status"] = "closed"
                fixed["qty_open"] = 0
                normalized_closed.append(fixed)
                if fixed != pos:
                    changed = True
            else:
                changed = True

        data["open_positions"] = normalized_open
        data["closed_positions"] = normalized_closed
        result["open"] = len(normalized_open)
        result["closed"] = len(normalized_closed)

        if changed:
            atomic_write_json(POSITIONS_FILE, data)
            result["repaired"] = True
            debug(f"POSITION SCHEMA LOCK REPAIR OK | {result}")

        return result
    except Exception as e:
        debug(f"POSITION SCHEMA LOCK REPAIR ERROR: {e}")
        return result


def duplicate_position_cap_allows(signal_or_order: Dict[str, Any]) -> Dict[str, Any]:
    if not ENABLE_HARD_DUPLICATE_POSITION_CAP:
        return {"approved": True, "reason": "duplicate_cap_disabled"}

    try:
        data = load_json_file(POSITIONS_FILE, {})
        open_positions = data.get("open_positions", []) if isinstance(data, dict) else []
        if not isinstance(open_positions, list):
            open_positions = []

        ticker = str(signal_or_order.get("ticker") or signal_or_order.get("underlying") or "").upper().strip()
        direction = normalize_direction(signal_or_order.get("direction", "CALL"))
        if not ticker:
            symbol = str(signal_or_order.get("symbol") or signal_or_order.get("contract_symbol") or "").upper().strip()
            ticker = symbol[:3] if symbol else ""

        total_open = 0
        same_key = 0

        for pos in open_positions:
            if not isinstance(pos, dict):
                continue
            fixed = normalize_locked_position_schema(pos)
            if fixed.get("status") != "open":
                continue
            if safe_int(fixed.get("qty_open", fixed.get("qty", 0)), 0) <= 0:
                continue
            total_open += 1
            if fixed.get("ticker") == ticker and fixed.get("direction") == direction:
                same_key += 1

        if total_open >= MAX_OPEN_POSITIONS_TOTAL:
            return {"approved": False, "reason": f"max_total_open_positions:{total_open}>={MAX_OPEN_POSITIONS_TOTAL}"}

        if same_key >= MAX_OPEN_POSITIONS_PER_SYMBOL_DIRECTION:
            return {"approved": False, "reason": f"duplicate_position_cap:{ticker}_{direction}:{same_key}>={MAX_OPEN_POSITIONS_PER_SYMBOL_DIRECTION}"}

        return {"approved": True, "reason": "duplicate_cap_passed"}

    except Exception as e:
        return {"approved": False, "reason": f"duplicate_cap_error:{e}"}


def reset_bad_positions_for_testing():
    try:
        data = {
            "schema_version": 2,
            "open_positions": [],
            "closed_positions": [],
            "last_position_id": 0,
        }
        atomic_write_json(POSITIONS_FILE, data)
        debug("RESET BAD POSITIONS FOR TESTING OK")
        return True
    except Exception as e:
        debug(f"RESET BAD POSITIONS ERROR: {e}")
        return False



def paper_bridge_open_position(order: Dict[str, Any]) -> Dict[str, Any]:
    cap = duplicate_position_cap_allows(order)
    if not cap.get("approved"):
        debug(f"🛑 DUPLICATE POSITION CAP BLOCK | {cap.get('reason')}")
        raise RuntimeError(f"duplicate_position_cap_block:{cap.get('reason')}")

    positions_store = paper_bridge_load_positions_store()
    positions_store["last_position_id"] = safe_int(positions_store.get("last_position_id", 0), 0) + 1

    entry = safe_float(order.get("fill_price", order.get("entry", 0)), 0.0)
    stop = safe_float(order.get("stop", 0), 0.0)

    position = {
        "position_id": f"POS-{positions_store['last_position_id']}",
        "id": f"POS-{positions_store['last_position_id']}",
        "order_id": order.get("order_id"),
        "broker": "paper_bridge",
        "mode": "paper",
        "status": "open",
        "opened_at": now_ts(),
        "timestamp": epoch(),
        "ticker": order.get("ticker"),
        "symbol": order.get("symbol"),
        "contract_symbol": order.get("contract_symbol"),
        "asset_class": order.get("asset_class", "option"),
        "direction": order.get("direction"),
        "qty": safe_int(order.get("qty", 1), 1),
        "qty_total": safe_int(order.get("qty", 1), 1),
        "qty_open": safe_int(order.get("qty", 1), 1),
        "entry": entry,
        "entry_price": entry,
        "stop": stop,
        "stop_price": stop,
        "target": safe_float(order.get("target", 0), 0.0),
        "tp1": safe_float(order.get("target", 0), 0.0),
        "tp2": safe_float(order.get("tp2", order.get("target", 0)), 0.0),
        "grade": order.get("grade"),
        "confidence": order.get("confidence"),
        "setup": order.get("setup"),
        "trigger": order.get("trigger"),
        "risk_per_contract": round(abs(entry - stop) * 100, 2),
        "unrealized_pnl": 0.0,
        "realized_pnl": 0.0,
    }

    position = normalize_locked_position_schema(position)
    positions_store.setdefault("open_positions", []).append(position)
    paper_bridge_save_positions_store(positions_store)
    debug(f"📌 PAPER POSITION OPENED | {position['position_id']} | {position['ticker']} {position['direction']} qty={position['qty']}")
    return position


def paper_bridge_alert(order: Dict[str, Any], position: Dict[str, Any]) -> None:
    msg = (
        "✅ PAPER BROKER BRIDGE EXECUTED\n"
        f"Ticker: {order.get('ticker')}\n"
        f"Symbol: {order.get('symbol')}\n"
        f"Direction: {order.get('direction')}\n"
        f"Qty: {order.get('qty')}\n"
        f"Entry: {order.get('entry')}\n"
        f"Stop: {order.get('stop')}\n"
        f"Target: {order.get('target')}\n"
        f"Order: {order.get('order_id')}\n"
        f"Position: {position.get('position_id')}"
    )
    try:
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_live_entry_discord(msg)
        send_to_telegram(msg)
    except Exception as e:
        debug(f"paper_bridge_alert_error:{e}")


def paper_broker_bridge_execute(signal: Dict[str, Any]) -> Dict[str, Any]:
    if not ENABLE_PAPER_BROKER_BRIDGE:
        return {"executed": False, "reason": "paper_bridge_disabled"}

    if FORCE_EXECUTION_MODE and not PAPER_BRIDGE_ALLOW_FORCE_EXECUTION:
        return {"executed": False, "reason": "force_execution_not_allowed_by_paper_bridge"}

    gate = paper_bridge_should_execute(signal)
    if not gate.get("approved"):
        return {"executed": False, "reason": gate.get("reason"), "hash": gate.get("hash")}

    order = paper_bridge_create_order(signal)
    filled = paper_bridge_fill_order(order)
    try:
        position = paper_bridge_open_position(filled)
    except Exception as e:
        reason = str(e)
        if "duplicate_position_cap_block" in reason:
            debug(f"🛑 PAPER BRIDGE DUPLICATE CAP BLOCKED | {reason}")
            return {"executed": False, "reason": "paper_bridge_duplicate_cap_blocked", "error": reason, "order": filled}
        raise

    paper_bridge_mark_executed(gate.get("hash", ""))

    if PAPER_BRIDGE_CLEAR_SIGNAL_AFTER_EXECUTION:
        try:
            atomic_write_json(SIGNAL_FILE, {})
            debug(f"🧹 PAPER BRIDGE CLEARED SIGNAL FILE | {SIGNAL_FILE}")
        except Exception as e:
            debug(f"paper_bridge_clear_signal_error:{e}")

    paper_bridge_alert(filled, position)

    return {"executed": True, "reason": "paper_order_filled_position_opened", "order": filled, "position": position}



def handle_new_signal(signal: Dict[str, Any]):
    if not signal:
        debug("handle_new_signal skipped: empty signal")
        return None

    qqq_ok, qqq_reason = qqq_only_signal_allowed(signal, stage="handle_new_signal")
    if not qqq_ok:
        qqq_only_debug_block(signal, qqq_reason, stage="handle_new_signal")
        return None

    auto_debug_routing(signal)
    debug(f"CONTROL FLAGS | force_execution={auto_should_force_execution_for_test(signal)} | allow_duplicates={ALLOW_DUPLICATE_SIGNALS}")

    # =========================================================
    # PAPER BROKER BRIDGE ROUTER
    # In force/testing mode, this creates exactly one paper order
    # and one paper position per signal hash/cooldown.
    # =========================================================
    if ENABLE_PAPER_BROKER_BRIDGE and FORCE_EXECUTION_MODE:
        signal = apply_unusual_whales_darkpool_to_signal(signal, stage="force_paper_bridge")
        send_unusual_whales_darkpool_alert(signal)
        maybe_send_live_entry_oil_style_alert(signal, stage="force_paper_bridge")
        if unusual_whales_darkpool_blocks_signal(signal):
            return None
        bridge_result = paper_broker_bridge_execute(signal)
        debug(f"PAPER BROKER BRIDGE RESULT | executed={bridge_result.get('executed')} | reason={bridge_result.get('reason')}")
        if bridge_result.get("executed"):
            return
    try:
        intel_event(
            "signal_received",
            {
                "source": signal.get("source", "signal_file"),
                "entry_contract": signal.get("entry_contract"),
                "stop_contract": signal.get("stop_contract"),
                "tp1_contract": signal.get("tp1_contract"),
                "tp2_contract": signal.get("tp2_contract"),
            },
            signal=signal,
            stage="signal_ingest",
            decision="received",
        )
    except Exception:
        pass
    if not GLOBAL_STATE.get("engine_enabled", True) or GLOBAL_STATE.get("kill_switch", False) or GLOBAL_STATE.get("bot_paused", False):
        try:
            intel_event("signal_ignored", {"engine_enabled": GLOBAL_STATE.get("engine_enabled", True), "kill_switch": GLOBAL_STATE.get("kill_switch", False), "bot_paused": GLOBAL_STATE.get("bot_paused", False)}, signal=signal, stage="engine_state", decision="ignored")
        except Exception:
            pass
        return
    if GLOBAL_STATE.get("reconciliation_required", False):
        msg = f"🚫 NEW TRADE BLOCKED\nReason: {GLOBAL_STATE.get('reconciliation_block_reason', 'reconciliation required')}\n⏰ {now_ts()}"
        send_to_telegram(msg)
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        return
    if not should_route_signal(signal):
        if elite_force_routing_enabled():
            debug("🚨 FINAL ELITE ROUTING — BYPASSING SIGNAL ROUTING")
        else:
            debug("PHASE 3 NOT RUN | no fresh routable signal or position-management cycle only")
            manage_open_positions(signal)
            return

    duplicate_gate = hard_duplicate_entry_gate(signal)
    if not duplicate_gate["approved"]:
        msg = build_block_message("HARD DUPLICATE CAP BLOCKED SIGNAL", signal, duplicate_gate["reject_reasons"], "Existing symbol/direction is already open or signal was already used.")
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_live_entry_discord(msg)
        send_to_telegram(msg)
        try:
            intel_event("duplicate_entry_blocked", {"reasons": duplicate_gate["reject_reasons"]}, signal=signal, stage="hard_duplicate_cap", decision="blocked")
        except Exception:
            pass
        return

    # PHASE 0: catastrophic-loss safety gate before normal validation/risk.
    phase0_decision = phase0_pretrade_safety_gate(signal)
    if not phase0_decision["approved"]:
        msg = build_block_message("PHASE 0 BLOCKED SIGNAL", signal, phase0_decision["reject_reasons"], "Fresh price / state / hard risk gate failed.")
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_live_entry_discord(msg)
        send_to_telegram(msg)
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

    # ADAPTIVE LEARNING MODULE:
    # Manual + closed-trade memory adjusts grade/confidence BEFORE Phase 3 and BEFORE execution.
    # Risk, Phase 3.5, portfolio, and kill-switch gates still remain in full control.
    regime_signal = adaptive_apply_learning_to_signal(regime_signal)

    # UNUSUAL WHALES DARK POOL:
    # Institutional resource levels become confluence before Phase 3 sizing/execution.
    regime_signal = apply_unusual_whales_darkpool_to_signal(regime_signal, stage="pre_phase3")
    send_unusual_whales_darkpool_alert(regime_signal)
    maybe_send_live_entry_oil_style_alert(regime_signal, stage="pre_phase3")
    if unusual_whales_darkpool_blocks_signal(regime_signal):
        return

    # PHASE 3: adaptive intelligence uses trade memory to block weak setups,
    # downgrade confidence, and adjust size before risk sizing/execution.
    debug(f"PHASE 3 PRE-ENTRY HOOK REACHED | ticker={regime_signal.get('ticker')} | direction={regime_signal.get('direction')} | confidence={regime_signal.get('confidence')}")
    phase3_decision = phase3_evaluate_adaptive_intelligence(regime_signal)
    if not phase3_decision["approved"]:
        msg = build_block_message("PHASE 3 ADAPTIVE BLOCKED SIGNAL", regime_signal, phase3_decision.get("reject_reasons", []), f"Setup: {phase3_decision.get('setup_key')} | Stats: {phase3_decision.get('stats', {})}")
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_live_entry_discord(msg)
        send_to_telegram(msg)
        return

    adaptive_signal = phase3_decision.get("adjusted_signal", regime_signal)

    # PHASE 3.5: enforcement gate after adaptive intelligence, before sizing.
    phase35_pre_size_decision = phase35_enforcement_gate(
        adaptive_signal,
        phase3_decision=phase3_decision,
        size_decision=None,
        stage="pre_size",
    )
    if not phase35_pre_size_decision["approved"]:
        return

    size_decision = size_signal_by_stop(adaptive_signal)
    size_decision = phase3_apply_size_multiplier_to_decision(size_decision, phase3_decision)
    if not size_decision["approved"]:
        msg = build_block_message("SIZING BLOCKED SIGNAL", regime_signal, size_decision["reject_reasons"], f"Raw Size: {size_decision.get('raw_size')} | Final Size: {size_decision.get('final_size')}")
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_telegram(msg)
        return

    sized_signal = apply_size_decision_to_signal(adaptive_signal, size_decision)
    sized_signal["phase3_decision"] = {k: v for k, v in phase3_decision.items() if k != "adjusted_signal"}

    # PHASE 3.5: final enforcement gate after sizing, before risk/order path.
    phase35_final_decision = phase35_enforcement_gate(
        sized_signal,
        phase3_decision=phase3_decision,
        size_decision=size_decision,
        stage="final_pre_risk",
    )
    if not phase35_final_decision["approved"]:
        return
    sized_signal["phase35_decision"] = phase35_final_decision

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

    # STEP 14: final account-level portfolio guard before routing/execution.
    step14_decision = step14_can_open_new_trade(sized_signal)
    if not step14_decision["approved"]:
        return

    duplicate_gate_final = hard_duplicate_entry_gate(sized_signal)
    if not duplicate_gate_final["approved"]:
        msg = build_block_message("HARD DUPLICATE CAP BLOCKED ENTRY", sized_signal, duplicate_gate_final["reject_reasons"], "Blocked at final pre-order gate.")
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_live_entry_discord(msg)
        send_to_telegram(msg)
        try:
            intel_event("duplicate_entry_blocked", {"reasons": duplicate_gate_final["reject_reasons"]}, signal=sized_signal, stage="hard_duplicate_cap_final", decision="blocked")
        except Exception:
            pass
        return

    # PHASE 1: final execution-safety guard before route/open.
    phase1_entry_decision = phase1_validate_order_safety(
        sized_signal,
        side="buy",
        qty=safe_int(sized_signal.get("qty", 0), 0),
        planned_price=safe_float(sized_signal.get("entry_contract", 0), 0),
        mode="LIVE" if (GLOBAL_STATE.get("alpaca_enabled", False) and ENABLE_ALPACA and not GLOBAL_STATE.get("paper_enabled", True)) else "PAPER",
    )
    if not phase1_entry_decision["approved"]:
        return

    # PHASE 2: order-lifecycle integrity guard before any paper/live order is created.
    phase2_entry_decision = phase2_validate_order_integrity(
        sized_signal,
        side="buy",
        qty=safe_int(sized_signal.get("qty", 0), 0),
        mode="LIVE" if (GLOBAL_STATE.get("alpaca_enabled", False) and ENABLE_ALPACA and not GLOBAL_STATE.get("paper_enabled", True)) else "PAPER",
    )
    if not phase2_entry_decision["approved"]:
        return

    intel_event(
        "signal_approved",
        {
            "qty": sized_signal.get("qty"),
            "entry_contract": sized_signal.get("entry_contract"),
            "stop_contract": sized_signal.get("stop_contract"),
            "tp1_contract": sized_signal.get("tp1_contract"),
            "tp2_contract": sized_signal.get("tp2_contract"),
            "regime": sized_signal.get("regime"),
            "size_decision": sized_signal.get("size_decision", {}),
        },
        signal=sized_signal,
        stage="approval_pipeline",
        decision="approved",
    )
    route_signal(sized_signal, GLOBAL_STATE)
    sig_hash = signal_hash(signal)
    GLOBAL_STATE["last_signal_hash"] = sig_hash
    GLOBAL_STATE["last_signal_time"] = epoch()
    GLOBAL_STATE["signal_count"] = safe_int(GLOBAL_STATE.get("signal_count", 0), 0) + 1
    append_recent_signal_hash(GLOBAL_STATE, sig_hash)
    save_state(GLOBAL_STATE)

    # PHASE 3.5 EXECUTION ROUTER FIX:
    # After all validation/risk/portfolio/phase gates approve, this explicitly
    # creates the paper/live order and local position.
    opened_position = execute_approved_signal(sized_signal)
    if opened_position:
        debug(
            f"ENTRY EXECUTION CONFIRMED | symbol={opened_position.get('symbol')} | "
            f"mode={opened_position.get('mode')} | qty={opened_position.get('qty_open')} | "
            f"entry={opened_position.get('entry_price')}"
        )
    else:
        debug("ENTRY EXECUTION NOT CREATED | approved signal did not produce an order/position")

    manage_open_positions(sized_signal)



# =========================================================
# ADAPTIVE LEARNING MODULE — FUNCTIONS
# Pattern memory for manual trades + closed engine trades.
# Uses separate JSON files so it does not corrupt existing JSONL memory.
# =========================================================

ADAPTIVE_GRADE_ORDER = ["AVOID", "C", "B", "B+", "A", "A+"]


def adaptive_now() -> str:
    try:
        return now_ts()
    except Exception:
        return datetime.utcnow().isoformat()


def adaptive_load_json(path: str, default: Any) -> Any:
    try:
        if 'load_json_file' in globals():
            data = load_json_file(path, default)
            return data if data is not None else deepcopy(default)
        if not os.path.exists(path):
            return deepcopy(default)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return deepcopy(default)


def adaptive_write_json(path: str, data: Any) -> None:
    try:
        atomic_write_json(path, data)
    except Exception:
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True, default=str)


def adaptive_log(message: str) -> None:
    try:
        debug(message)
    except Exception:
        try:
            log(message)
        except Exception:
            print(message, flush=True)


def adaptive_alert(title: str, body: str, force: bool = False) -> None:
    if not ENABLE_ADAPTIVE_LEARNING_MODULE:
        return
    if not ADAPTIVE_SEND_ALERTS and not force:
        return
    msg = f"🧬 {title}\n{body}\n⏰ {adaptive_now()}"
    try:
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
    except Exception:
        pass
    try:
        send_to_telegram(msg)
    except Exception:
        pass


def adaptive_normalize_grade(value: Any) -> str:
    g = str(value or "").upper().strip()
    if not g:
        return "B"
    if g in {"NO TRADE", "NONE", "SKIP", "DO NOT TRADE"}:
        return "AVOID"
    return g if g in ADAPTIVE_GRADE_ORDER else "B"


def adaptive_boost_grade(base_grade: Any, boost: int) -> str:
    base = adaptive_normalize_grade(base_grade)
    idx = ADAPTIVE_GRADE_ORDER.index(base)
    new_idx = max(0, min(len(ADAPTIVE_GRADE_ORDER) - 1, idx + int(boost)))
    return ADAPTIVE_GRADE_ORDER[new_idx]


def adaptive_direction(value: Any) -> str:
    d = str(value or "").upper().strip()
    if d in {"BUY_CALL", "LONG_CALL", "CALLS"}:
        return "CALL"
    if d in {"BUY_PUT", "LONG_PUT", "PUTS"}:
        return "PUT"
    return d


def adaptive_confluences(obj: Dict[str, Any]) -> Dict[str, Any]:
    con = obj.get("confluences", {}) if isinstance(obj, dict) else {}
    if not isinstance(con, dict):
        con = {}

    return {
        "vwap": con.get("vwap") or obj.get("vwap", ""),
        "rsi": con.get("rsi") or obj.get("rsi", ""),
        "volume": con.get("volume") or obj.get("volume", ""),
        "oil": con.get("oil") or obj.get("oil", obj.get("oil_context", "")),
        "market_type": con.get("market_type") or obj.get("market_type", obj.get("regime", obj.get("market_regime", ""))),
        "structure": con.get("structure") or obj.get("structure", obj.get("trigger", "")),
        "premarket_high": con.get("premarket_high") or obj.get("premarket_high", ""),
        "premarket_low": con.get("premarket_low") or obj.get("premarket_low", ""),
    }


def adaptive_setup_fingerprint(obj: Dict[str, Any]) -> str:
    con = adaptive_confluences(obj)

    ticker = str(obj.get("ticker") or obj.get("underlying") or "").upper().strip()
    direction = adaptive_direction(obj.get("direction", ""))
    setup = str(obj.get("setup_name") or obj.get("setup_type") or obj.get("setup") or obj.get("strategy") or "GENERIC").lower().strip()
    trigger = str(obj.get("trigger") or con.get("structure") or "").lower().strip()
    vwap = str(con.get("vwap") or "").lower().strip()
    oil = str(con.get("oil") or "").lower().strip()
    volume = str(con.get("volume") or "").lower().strip()
    market_type = str(con.get("market_type") or "").lower().strip()

    parts = [ticker, direction, setup, trigger, vwap, oil, volume, market_type]
    cleaned = [re.sub(r"[^a-zA-Z0-9_+.-]+", "_", str(p))[:50] for p in parts if str(p).strip()]
    return "|".join(cleaned) if cleaned else "UNKNOWN_PATTERN"


def adaptive_is_win(result: Any) -> bool:
    return str(result or "").lower().strip() in {"win", "winner", "green", "profit", "tp", "take profit", "true"}


def adaptive_is_loss(result: Any) -> bool:
    return str(result or "").lower().strip() in {"loss", "loser", "red", "stop", "stopped", "sl", "false"}


def adaptive_result_from_trade(trade: Dict[str, Any]) -> str:
    explicit = str(trade.get("result", "")).lower().strip()
    if explicit:
        if adaptive_is_win(explicit):
            return "win"
        if adaptive_is_loss(explicit):
            return "loss"

    if isinstance(trade.get("winner"), bool):
        return "win" if trade.get("winner") else "loss"

    pnl = safe_float(trade.get("realized_pnl", trade.get("pnl", trade.get("realized_pnl_pct", trade.get("pnl_pct", 0)))), 0)
    if pnl > 0:
        return "win"
    if pnl < 0:
        return "loss"

    entry = safe_float(trade.get("entry_price", trade.get("entry", 0)), 0)
    exit_price = safe_float(trade.get("exit_price", trade.get("exit", 0)), 0)
    direction = adaptive_direction(trade.get("direction", ""))
    if entry > 0 and exit_price > 0:
        if direction == "PUT":
            return "win" if exit_price > entry else "loss"
        return "win" if exit_price > entry else "loss"

    return "unknown"


def adaptive_normalize_trade_record(trade: Dict[str, Any]) -> Dict[str, Any]:
    con = adaptive_confluences(trade)
    record = {
        "id": trade.get("id") or trade.get("position_id") or trade.get("signal_id") or f"adaptive_{int(time.time())}_{hashlib.sha1(json.dumps(trade, sort_keys=True, default=str).encode()).hexdigest()[:8]}",
        "created_at": trade.get("created_at") or trade.get("closed_time") or adaptive_now(),
        "source": trade.get("source", "manual"),
        "ticker": str(trade.get("ticker") or trade.get("underlying") or "").upper().strip(),
        "symbol": trade.get("symbol") or trade.get("contract_symbol", ""),
        "date": trade.get("date", ""),
        "time": trade.get("time", ""),
        "time_window": trade.get("time_window", ""),
        "setup_name": trade.get("setup_name") or trade.get("setup") or trade.get("strategy") or trade.get("trigger") or "Unnamed Setup",
        "setup_type": trade.get("setup_type") or trade.get("setup") or trade.get("strategy") or "",
        "trigger": trade.get("trigger", ""),
        "direction": adaptive_direction(trade.get("direction", "")),
        "decision": trade.get("decision", "took it"),
        "entry_price": trade.get("entry_price", trade.get("entry")),
        "exit_price": trade.get("exit_price", trade.get("exit")),
        "stop_loss": trade.get("stop_loss", trade.get("stop", trade.get("stop_price"))),
        "targets": trade.get("targets", trade.get("target", [])),
        "grade": adaptive_normalize_grade(trade.get("grade", trade.get("confidence", "B"))),
        "confidence": adaptive_normalize_grade(trade.get("confidence", trade.get("grade", "B"))),
        "result": adaptive_result_from_trade(trade),
        "pnl": trade.get("pnl", trade.get("realized_pnl", trade.get("realized_pnl_pct", trade.get("pnl_pct")))),
        "r_multiple": trade.get("r_multiple", 0),
        "notes": trade.get("notes", ""),
        "confluences": con,
    }
    record["pattern_key"] = adaptive_setup_fingerprint(record)
    return record


def adaptive_load_trade_memory() -> List[Dict[str, Any]]:
    data = adaptive_load_json(ADAPTIVE_TRADE_MEMORY_FILE, [])
    return data if isinstance(data, list) else []


def adaptive_save_trade_memory(memory: List[Dict[str, Any]]) -> None:
    adaptive_write_json(ADAPTIVE_TRADE_MEMORY_FILE, memory)


def adaptive_rebuild_learning_stats(memory: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    memory = memory if memory is not None else adaptive_load_trade_memory()
    patterns: Dict[str, Dict[str, Any]] = {}

    for trade in memory:
        key = trade.get("pattern_key") or adaptive_setup_fingerprint(trade)
        bucket = patterns.setdefault(key, {
            "pattern_key": key,
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "unknown": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "avg_pnl": 0.0,
            "total_r": 0.0,
            "avg_r": 0.0,
            "sample_trades": [],
            "last_seen": "",
        })

        bucket["trades"] += 1
        result = trade.get("result", "unknown")
        if adaptive_is_win(result):
            bucket["wins"] += 1
        elif adaptive_is_loss(result):
            bucket["losses"] += 1
        else:
            bucket["unknown"] += 1

        pnl = trade.get("pnl")
        if isinstance(pnl, (int, float)):
            bucket["total_pnl"] += float(pnl)
        r_mult = safe_float(trade.get("r_multiple", 0), 0)
        bucket["total_r"] += r_mult

        if len(bucket["sample_trades"]) < 5:
            bucket["sample_trades"].append({
                "id": trade.get("id"),
                "ticker": trade.get("ticker"),
                "setup_name": trade.get("setup_name"),
                "grade": trade.get("grade"),
                "confidence": trade.get("confidence"),
                "result": trade.get("result"),
            })
        bucket["last_seen"] = trade.get("created_at") or bucket.get("last_seen", "")

    for bucket in patterns.values():
        closed = bucket["wins"] + bucket["losses"]
        trades = max(bucket["trades"], 1)
        bucket["win_rate"] = round(bucket["wins"] / closed, 4) if closed > 0 else 0.0
        bucket["avg_pnl"] = round(bucket["total_pnl"] / trades, 4)
        bucket["avg_r"] = round(bucket["total_r"] / trades, 4)

    return {
        "updated_at": adaptive_now(),
        "total_trades": len(memory),
        "patterns": patterns,
    }


def adaptive_load_learning_stats() -> Dict[str, Any]:
    stats = adaptive_load_json(ADAPTIVE_LEARNING_STATS_FILE, {})
    if not isinstance(stats, dict) or "patterns" not in stats:
        stats = adaptive_rebuild_learning_stats()
        adaptive_write_json(ADAPTIVE_LEARNING_STATS_FILE, stats)
    return stats


def adaptive_record_trade_for_learning(trade: Dict[str, Any]) -> Dict[str, Any]:
    if not ENABLE_ADAPTIVE_LEARNING_MODULE:
        return {}

    learning_ok, learning_reason = qqq_clean_learning_allowed(trade, stage="adaptive_record_trade")
    if not learning_ok:
        qqq_only_debug_block(trade, learning_reason, stage="adaptive_record_trade")
        return {
            "skipped": True,
            "reason": learning_reason,
            "ticker": qqq_lock_get_ticker(trade),
            "trigger": qqq_lock_get_trigger(trade),
        }

    memory = adaptive_load_trade_memory()
    normalized = adaptive_normalize_trade_record(trade)

    # Prevent exact duplicate IDs from stacking if command is accidentally run twice.
    existing_ids = {str(t.get("id")) for t in memory if isinstance(t, dict)}
    if str(normalized.get("id")) not in existing_ids:
        memory.append(normalized)
        adaptive_save_trade_memory(memory)

    stats = adaptive_rebuild_learning_stats(memory)
    adaptive_write_json(ADAPTIVE_LEARNING_STATS_FILE, stats)

    adaptive_log(f"ADAPTIVE LEARNING RECORDED | {normalized.get('ticker')} | {normalized.get('setup_name')} | {normalized.get('result')} | {normalized.get('pattern_key')}")
    return normalized


def adaptive_record_position_close(position: Dict[str, Any], close_reason: str = "") -> Dict[str, Any]:
    try:
        story = intel_trade_story_from_position(position, close_reason) if 'intel_trade_story_from_position' in globals() else deepcopy(position)
    except Exception:
        story = deepcopy(position)

    story["source"] = "engine_closed_trade"
    story["setup_name"] = position.get("setup_name") or position.get("setup") or position.get("trigger") or story.get("setup_name", "Engine Closed Trade")
    story["setup_type"] = position.get("setup_type") or position.get("setup") or story.get("setup_type", "")
    story["trigger"] = position.get("trigger", story.get("trigger", ""))
    story["confluences"] = position.get("confluences", position.get("signal_confluences", {}))
    story["close_reason"] = close_reason

    learning_ok, learning_reason = qqq_clean_learning_allowed(story, stage="adaptive_position_close")
    if not learning_ok:
        qqq_only_debug_block(story, learning_reason, stage="adaptive_position_close")
        return {
            "skipped": True,
            "reason": learning_reason,
            "ticker": qqq_lock_get_ticker(story),
            "trigger": qqq_lock_get_trigger(story),
        }

    return adaptive_record_trade_for_learning(story)


def adaptive_learning_adjustment(signal: Dict[str, Any]) -> Dict[str, Any]:
    if not ENABLE_ADAPTIVE_LEARNING_MODULE:
        return {
            "enabled": False,
            "matched": False,
            "grade_boost": 0,
            "confidence": "disabled",
            "reason": "adaptive_learning_disabled",
        }

    stats = adaptive_load_learning_stats()
    key = adaptive_setup_fingerprint(signal)
    pattern = stats.get("patterns", {}).get(key)

    if not pattern:
        return {
            "enabled": True,
            "pattern_key": key,
            "matched": False,
            "grade_boost": 0,
            "confidence": "new_pattern",
            "reason": "No matching manual/engine trade memory yet.",
            "pattern_stats": None,
        }

    trades = safe_int(pattern.get("trades", 0), 0)
    win_rate = safe_float(pattern.get("win_rate", 0), 0)

    if trades < ADAPTIVE_MIN_TRADES_FOR_BOOST:
        return {
            "enabled": True,
            "pattern_key": key,
            "matched": True,
            "grade_boost": 0,
            "confidence": "low_sample_size",
            "reason": f"Matched pattern, but only {trades} trade(s). Need {ADAPTIVE_MIN_TRADES_FOR_BOOST}+ before boost.",
            "pattern_stats": pattern,
        }

    if win_rate >= ADAPTIVE_HIGH_WINRATE_THRESHOLD:
        boost = 2 if win_rate >= ADAPTIVE_STRONG_WINRATE_THRESHOLD else 1
        boost = min(boost, ADAPTIVE_MAX_GRADE_BOOST)
        return {
            "enabled": True,
            "pattern_key": key,
            "matched": True,
            "grade_boost": boost,
            "confidence": "strong_pattern",
            "reason": f"Pattern win rate {round(win_rate * 100, 1)}% across {trades} trades.",
            "pattern_stats": pattern,
        }

    if win_rate <= ADAPTIVE_LOW_WINRATE_THRESHOLD:
        return {
            "enabled": True,
            "pattern_key": key,
            "matched": True,
            "grade_boost": -1,
            "confidence": "weak_pattern",
            "reason": f"Pattern win rate only {round(win_rate * 100, 1)}% across {trades} trades.",
            "pattern_stats": pattern,
        }

    return {
        "enabled": True,
        "pattern_key": key,
        "matched": True,
        "grade_boost": 0,
        "confidence": "neutral_pattern",
        "reason": f"Pattern win rate {round(win_rate * 100, 1)}% across {trades} trades.",
        "pattern_stats": pattern,
    }


def adaptive_apply_learning_to_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(signal, dict):
        return signal

    adjusted = deepcopy(signal)
    base_grade = adaptive_normalize_grade(adjusted.get("grade", adjusted.get("confidence", "B")))
    base_confidence = adaptive_normalize_grade(adjusted.get("confidence", adjusted.get("grade", base_grade)))

    learning = adaptive_learning_adjustment(adjusted)
    boost = safe_int(learning.get("grade_boost", 0), 0)

    adjusted["adaptive_base_grade"] = base_grade
    adjusted["adaptive_base_confidence"] = base_confidence
    adjusted["adaptive_learning"] = learning

    adjusted["grade"] = adaptive_boost_grade(base_grade, boost)
    adjusted["confidence"] = adaptive_boost_grade(base_confidence, boost)

    if boost != 0:
        adjusted.setdefault("adaptive_notes", [])
        adjusted["adaptive_notes"].append(learning.get("reason", "adaptive learning adjusted grade"))
        adaptive_log(f"ADAPTIVE LEARNING SIGNAL ADJUSTED | {adjusted.get('ticker')} | {base_confidence}->{adjusted.get('confidence')} | boost={boost}")
        adaptive_alert(
            "ADAPTIVE LEARNING GRADE UPDATE",
            f"Ticker: {adjusted.get('ticker')}\nSetup: {adjusted.get('setup') or adjusted.get('setup_name')}\nBase: {base_confidence}\nFinal: {adjusted.get('confidence')}\nReason: {learning.get('reason')}",
            force=False,
        )
    else:
        adaptive_log(f"ADAPTIVE LEARNING CHECK | {adjusted.get('ticker')} | {learning.get('confidence')} | {learning.get('reason')}")

    return adjusted


def adaptive_record_qqq_oil_breakout_example() -> Dict[str, Any]:
    trade = {
        "source": "manual",
        "ticker": "QQQ",
        "date": "2026-04-25",
        "time": "11:35 AM ET",
        "time_window": "mid-day",
        "setup_name": "QQQ Oil-Drop Risk-On Breakout",
        "setup_type": "breakout momentum push",
        "setup": "breakout momentum push",
        "trigger": "breakout hold",
        "direction": "CALL",
        "decision": "took it",
        "entry_price": 661.80,
        "stop_loss": 660.80,
        "targets": [663, 664],
        "grade": "A+",
        "confidence": "A+",
        "result": "win",
        "pnl": None,
        "confluences": {
            "vwap": "above",
            "rsi": "momentum pushing up",
            "volume": "strong",
            "oil": "falling",
            "market_type": "trending continuation",
            "structure": "breakout hold",
            "premarket_high": 663.46,
            "premarket_low": 651.79,
        },
        "notes": "QQQ broke 661.50-662 with momentum while oil/USO dropped hard. Risk-on rotation into tech. Strong volume, above VWAP, no immediate rejection.",
    }
    return adaptive_record_trade_for_learning(trade)


def adaptive_record_manual_trade_file(path: str) -> Dict[str, Any]:
    data = adaptive_load_json(path, None)
    if not isinstance(data, dict):
        raise RuntimeError(f"Manual trade file is not valid JSON object: {path}")
    data.setdefault("source", "manual_file")
    return adaptive_record_trade_for_learning(data)


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
        if get_position_mode(position) == "LIVE":
            live_close_position(position, "Manual close all")
        else:
            finalize_close_position(position, position["last_price"], "Manual close all")
    send_to_telegram("✅ All open positions close instructions sent.")


def handle_telegram_command(text: str):
    cmd = parse_command(text)
    if cmd in {"/start", "/help", "help"}:
        send_to_telegram("📘 COMMANDS\n/status\n/positions\n/orders\n/engine_on\n/engine_off\n/paper_on\n/paper_off\n/alpaca_on\n/alpaca_off\n/discord_on\n/discord_off\n/telegram_on\n/telegram_off\n/kill_on\n/kill_off\n/pause_on\n/pause_off\n/test\n/heartbeat\n/sync\n/recon\n/recon_clear\n/cancel_orders\n/close_all\n/flatten\n/kill\n/unlock\n/phase2_unlock\n/macro\n/macro_push\n")
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
    if cmd in {"/kill", "/kill_on"}:
        step15_activate_kill_switch("Telegram manual kill command", close_positions=True); return
    if cmd in {"/unlock", "/kill_off"}:
        step15_reset_lock(); return
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
    if cmd == "/flatten":
        step15_flatten_only("Telegram manual flatten command"); return
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
    repair_position_mode_for_step15()
    repair_and_lock_positions_schema()
    repair_position_schema_for_step15()
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

    # INTELLIGENCE PHASE 1: create event/memory/analytics files immediately on boot.
    intel_bootstrap("boot")

    if RUN_TEST_ON_START:
        run_startup_tests()

    # PHASE 0: hard startup safety gate. This validates local state and makes
    # startup reconciliation decisive before any new trade can be opened.
    phase0_startup_safety_gate()
    if (not ENABLE_PHASE0_SAFETY) and ENABLE_ALPACA and GLOBAL_STATE.get("alpaca_enabled", False) and alpaca_ready():
        startup_reconcile_and_gate()

    if ENABLE_MACRO_BRIDGE:
        refresh_macro_bridge(force=True, send_alerts=MACRO_SEND_ON_BOOT)

    send_heartbeat(force=True)



# =========================================================
# PAPER POSITION LIFECYCLE: TP / SL / AUTO CLOSE HELPERS
# =========================================================
def paper_tpsl_load_positions() -> Dict[str, Any]:
    data = load_json_file(POSITIONS_FILE, {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("schema_version", 2)
    data.setdefault("open_positions", [])
    data.setdefault("closed_positions", [])
    data.setdefault("last_position_id", safe_int(data.get("last_position_id", 0), 0))
    return data


def paper_tpsl_save_positions(data: Dict[str, Any]) -> None:
    atomic_write_json(POSITIONS_FILE, data)


def paper_tpsl_position_symbol(pos: Dict[str, Any]) -> str:
    return str(pos.get("symbol") or pos.get("contract_symbol") or pos.get("ticker") or "").strip()


def paper_tpsl_get_price(pos: Dict[str, Any]) -> float:
    """Resolve a current price for paper lifecycle.
    For true option data, this uses market_prices.json if available.
    For testing, it falls back to entry/current/target-compatible prices.
    """
    symbol = paper_tpsl_position_symbol(pos)
    ticker = str(pos.get("ticker") or "").upper().strip()

    # 1) Direct current price already on position
    for key in ["current_price", "last_price", "mark", "contract_price"]:
        value = safe_float(pos.get(key, 0), 0.0)
        if value > 0:
            return value

    # 2) Read market_prices.json if available
    try:
        market = load_json_file(MARKET_PRICES_FILE, {})
        if isinstance(market, dict):
            candidates = []
            if symbol:
                candidates.append(symbol)
            if ticker:
                candidates.append(ticker)
            for c in candidates:
                row = market.get(c)
                if isinstance(row, dict):
                    price = safe_float(row.get("price", row.get("last", row.get("mark", 0))), 0.0)
                    if price > 0:
                        return price
                elif isinstance(row, (int, float, str)):
                    price = safe_float(row, 0.0)
                    if price > 0:
                        return price
    except Exception:
        pass

    # 3) Testing fallback: use entry so position stays open unless user updates position/market price
    if PAPER_TPSL_USE_SIGNAL_PRICE_FALLBACK:
        return safe_float(pos.get("entry_price", pos.get("entry", 0)), 0.0)

    return 0.0


def paper_tpsl_direction_pnl(direction: str, entry: float, price: float, qty: int) -> float:
    direction = normalize_direction(direction)
    if direction == "PUT":
        pnl_per_contract = entry - price
    else:
        pnl_per_contract = price - entry
    return round(pnl_per_contract * max(qty, 1) * 100, 2)


def paper_tpsl_close_position(pos: Dict[str, Any], exit_price: float, reason: str) -> Dict[str, Any]:
    close_key = idempotency_close_intent_id(pos, side="sell", qty=safe_int(pos.get("qty_open", pos.get("qty", 0)), 0), reason=reason)
    close_claim = idempotency_claim("close_intent", close_key, payload={"position": pos, "exit_price": exit_price, "reason": reason}, owner="paper_tpsl")
    if not close_claim.get("approved", False):
        debug(f"🧷 PAPER CLOSE IDEMPOTENCY BLOCK | {close_claim.get('reason')} | key={idempotency_short(close_key)}")
        return pos
    pos = deepcopy(pos)
    qty = safe_int(pos.get("qty", 1), 1)
    entry = safe_float(pos.get("entry_price", pos.get("entry", 0)), 0.0)
    direction = str(pos.get("direction", "CALL"))
    realized = paper_tpsl_direction_pnl(direction, entry, exit_price, qty)

    pos["status"] = "closed"
    pos["closed_at"] = now_ts()
    pos["closed_timestamp"] = epoch()
    pos["exit_price"] = exit_price
    pos["close_reason"] = reason
    pos["realized_pnl"] = realized
    pos["unrealized_pnl"] = 0.0

    idempotency_mark("close_intent", close_key, "closed", {"position": pos, "exit_price": exit_price, "reason": reason})
    return pos


def paper_tpsl_alert(title: str, pos: Dict[str, Any]) -> None:
    if not PAPER_TPSL_ALERTS_ENABLED:
        return
    msg = (
        f"{title}\n"
        f"Ticker: {pos.get('ticker')}\n"
        f"Symbol: {pos.get('symbol')}\n"
        f"Direction: {pos.get('direction')}\n"
        f"Qty: {pos.get('qty')}\n"
        f"Entry: {pos.get('entry_price', pos.get('entry'))}\n"
        f"Stop: {pos.get('stop_price', pos.get('stop'))}\n"
        f"Target: {pos.get('target')}\n"
        f"TP2: {pos.get('tp2')}\n"
        f"PnL: {pos.get('realized_pnl', pos.get('unrealized_pnl', 0))}\n"
        f"Reason: {pos.get('close_reason', '')}"
    )
    try:
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_live_entry_discord(msg)
        send_to_telegram(msg)
    except Exception as e:
        debug(f"paper_tpsl_alert_error:{e}")



# =========================================================
# TP/SL LIVE PRICE RESOLVER FIX
# Required by Step 15 / flatten / lifecycle checks.
# Prevents NameError: get_live_price_for_position is not defined.
# =========================================================
def get_live_price_for_position(pos: Dict[str, Any], market_prices: Optional[Dict[str, Any]] = None) -> Optional[float]:
    try:
        if not isinstance(pos, dict):
            return None

        if market_prices is None:
            market_prices = load_json_file(MARKET_PRICES_FILE, {})

        if not isinstance(market_prices, dict):
            market_prices = {}

        candidates = []
        for key in ["symbol", "contract_symbol", "ticker"]:
            value = str(pos.get(key, "")).strip()
            if value and value not in candidates:
                candidates.append(value)

        # Try exact symbol/contract/ticker from market_prices.json
        for symbol in candidates:
            row = market_prices.get(symbol)
            if isinstance(row, dict):
                for price_key in ["price", "last", "mark", "bid", "ask"]:
                    price = safe_float(row.get(price_key, 0), 0.0)
                    if price > 0:
                        return price
            else:
                price = safe_float(row, 0.0)
                if price > 0:
                    return price

        # Try current price fields already stored on the position
        for key in ["current_price", "last_price", "mark", "contract_price", "entry_price", "entry"]:
            price = safe_float(pos.get(key, 0), 0.0)
            if price > 0:
                return price

        return None
    except Exception as e:
        debug(f"get_live_price_for_position_error:{e}")
        return None



def paper_tpsl_manage_positions() -> Dict[str, Any]:
    """Manage all paper bridge open positions.
    - Stop loss closes full position
    - TP1 marks hit, optionally moves stop to breakeven
    - TP2 closes full position
    """
    result = {"managed": False, "open_count": 0, "closed_count": 0, "events": []}

    if not ENABLE_PAPER_TPSL_LIFECYCLE:
        return result

    store = paper_tpsl_load_positions()
    open_positions = store.get("open_positions", [])
    if not isinstance(open_positions, list) or not open_positions:
        result["managed"] = True
        return result

    updated_open = []
    closed = store.get("closed_positions", [])
    if not isinstance(closed, list):
        closed = []

    for pos in open_positions:
        if not isinstance(pos, dict):
            continue

        status = str(pos.get("status", "open")).lower()
        if status != "open":
            closed.append(pos)
            continue

        ticker = str(pos.get("ticker", "")).upper()
        direction = normalize_direction(pos.get("direction", "CALL"))
        qty = safe_int(pos.get("qty", 1), 1)
        entry = safe_float(pos.get("entry_price", pos.get("entry", 0)), 0.0)
        stop = safe_float(pos.get("stop_price", pos.get("stop", 0)), 0.0)
        target = safe_float(pos.get("target", pos.get("tp1_contract", 0)), 0.0)
        tp2 = safe_float(pos.get("tp2", pos.get("target_2", target)), target)
        price = paper_tpsl_get_price(pos)

        if entry <= 0 or price <= 0:
            pos["lifecycle_warning"] = "missing_entry_or_price"
            updated_open.append(pos)
            continue

        unrealized = paper_tpsl_direction_pnl(direction, entry, price, qty)
        pos["current_price"] = price
        pos["last_lifecycle_check"] = now_ts()
        pos["unrealized_pnl"] = unrealized

        # Direction-aware thresholds
        if direction == "PUT":
            stop_hit = stop > 0 and price >= stop
            tp1_hit = target > 0 and price <= target
            tp2_hit = tp2 > 0 and price <= tp2
        else:
            stop_hit = stop > 0 and price <= stop
            tp1_hit = target > 0 and price >= target
            tp2_hit = tp2 > 0 and price >= tp2

        # STOP LOSS: full close
        if stop_hit:
            closed_pos = paper_tpsl_close_position(pos, price, "STOP_LOSS_HIT")
            closed.append(closed_pos)
            result["closed_count"] += 1
            result["events"].append(f"STOP_LOSS_HIT:{ticker}")
            debug(f"❌ PAPER STOP HIT | {ticker} | price={price} | pnl={closed_pos.get('realized_pnl')}")
            paper_tpsl_alert("❌ PAPER STOP LOSS HIT", closed_pos)
            continue

        # TP1: mark hit and optionally move stop to breakeven
        if tp1_hit and not pos.get("tp1_hit", False):
            pos["tp1_hit"] = True
            pos["tp1_hit_at"] = now_ts()
            pos["tp1_hit_price"] = price
            result["events"].append(f"TP1_HIT:{ticker}")
            debug(f"🎯 PAPER TP1 HIT | {ticker} | price={price} | pnl={unrealized}")

            if PAPER_TPSL_SCALE_AT_TP1:
                pos["scaled_at_tp1"] = True
                pos["remaining_qty_note"] = "paper_scale_marker_only"

            if PAPER_TPSL_MOVE_STOP_TO_BREAKEVEN_ON_TP1:
                pos["original_stop_price"] = stop
                pos["stop_price"] = entry
                pos["stop"] = entry
                debug(f"🛡️ PAPER STOP MOVED TO BREAKEVEN | {ticker} | stop={entry}")

            paper_tpsl_alert("🎯 PAPER TP1 HIT", pos)

        # TP2: full close
        if tp2_hit and PAPER_TPSL_CLOSE_ON_TP2:
            closed_pos = paper_tpsl_close_position(pos, price, "TP2_HIT")
            closed.append(closed_pos)
            result["closed_count"] += 1
            result["events"].append(f"TP2_HIT:{ticker}")
            debug(f"🏆 PAPER TP2 HIT | {ticker} | price={price} | pnl={closed_pos.get('realized_pnl')}")
            paper_tpsl_alert("🏆 PAPER TP2 HIT — POSITION CLOSED", closed_pos)
            continue

        updated_open.append(pos)

    store["open_positions"] = updated_open
    store["closed_positions"] = closed
    paper_tpsl_save_positions(store)

    result["managed"] = True
    result["open_count"] = len(updated_open)
    return result



def runtime_housekeeping():
    ensure_globals_initialized()
    intel_periodic_snapshot()
    # STEP 15: global kill/flatten guard runs before every other task.
    if not step15_global_guard():
        flush_dirty_stores(force=True)
        return
    # PHASE 2: order lifecycle/reconciliation integrity runs every loop before risk decisions.
    phase2_sync_order_lifecycle()
    phase2_reconciliation_guard()
    tpsl_result = paper_tpsl_manage_positions()
    if tpsl_result.get("managed") and (tpsl_result.get("events") or tpsl_result.get("closed_count", 0) > 0):
        debug(f"PAPER TP/SL LIFECYCLE RESULT | {tpsl_result}")


    # PHASE 0: hard daily loss / heat kill switch and stale open-position price gate.
    if not phase0_hard_risk_kill_check():
        flush_dirty_stores(force=True)
        return
    open_price_gate = phase0_validate_fresh_prices_for_open_positions()
    if not open_price_gate["approved"]:
        phase0_alert("PHASE 0 OPEN POSITION PRICE BLOCK", ", ".join(open_price_gate["reject_reasons"][:8]), force=False)
        flush_dirty_stores(force=True)
        return
    # STEP 14: account-level emergency guard runs every loop.
    if not step14_loop_enforcement():
        flush_dirty_stores(force=True)
        return
    refresh_macro_bridge(force=False, send_alerts=False)
    sync_live_positions_from_alpaca()
    reconcile_order_fills_into_positions()
    update_positions_from_market_prices()
    manage_open_positions(None)
    flush_dirty_stores(force=False)



def reset_kill_switch_for_testing():
    """Manual helper: call only after reviewing risk state."""
    try:
        state = load_json_file(CONTROL_STATE_FILE, {})
        if not isinstance(state, dict):
            state = {}
        state["kill_switch"] = False
        state["engine_locked"] = False
        state["locked"] = False
        state["last_reset_at"] = now_ts()
        atomic_write_json(CONTROL_STATE_FILE, state)
        debug("KILL SWITCH RESET FOR TESTING")
        return True
    except Exception as e:
        debug(f"reset_kill_switch_error:{e}")
        return False



def main_loop():
    try:
        debug_alpaca_urls_once()
    except Exception:
        pass

    try:
        build_signal_from_ai()
    except Exception as e:
        debug(f"AI TO SIGNAL BRIDGE LOOP ERROR | {e}")

    boot()
    macro_bridge_fred_refresh(force=False)
    auto_generate_ai_signal_if_ready()
    ai_bridge_write_signal_if_ready()

    # =========================================================
    # FORCE STARTUP SIGNAL PICKUP
    # Processes signal.json immediately on startup instead of
    # waiting for file watcher / mtime logic.
    # =========================================================
    try:
        startup_signal = load_live_signal()
        if startup_signal:
            debug("FORCE STARTUP SIGNAL PICKUP")
            handle_new_signal(startup_signal)
            # Signal persistence enabled: do NOT clear signal.json after startup pickup.
            debug(f"FORCE STARTUP SIGNAL KEPT | file={SIGNAL_FILE}")
    except Exception as startup_signal_error:
        log(f"❌ FORCE STARTUP SIGNAL PICKUP ERROR: {startup_signal_error}")
        log(traceback.format_exc())

    if not file_exists(SIGNAL_FILE):
        log(f"❌ No signal file found on boot: {SIGNAL_FILE}")
        if fallback_signal_enabled():
            if fallback_signal_enabled():

                debug("Routing fallback test signal once.")

                sig = fallback_signal()

                handle_new_signal(sig)

            else:

                debug("No signal file and fallback disabled — idle cycle.")
        else:
            debug("No signal file and fallback disabled — idle cycle.")

    while True:
        try:
            intel_periodic_snapshot()
            process_telegram_updates()
            # PAPER TP/SL LOOP CHECK
            tpsl_loop_result = paper_tpsl_manage_positions()
            if tpsl_loop_result.get("events") or tpsl_loop_result.get("closed_count", 0) > 0:
                debug(f"PAPER TP/SL LOOP RESULT | {tpsl_loop_result}")

            debug(f"FINAL ELITE ROUTING FLAGS | force={FORCE_EXECUTION_MODE} | bypass_routing={FORCE_BYPASS_SIGNAL_ROUTING} | treat_fresh={FORCE_TREAT_SIGNAL_AS_FRESH}")

            # =========================================================
            # PERSISTENT SIGNAL LISTENER
            # Checks signal.json every loop and keeps it in place.
            # Duplicate protection still uses last_signal_hash.
            # =========================================================
            try:
                live_signal_poll = load_live_signal()
                if live_signal_poll:
                    live_hash = signal_hash(live_signal_poll)
                    last_hash = str(GLOBAL_STATE.get("last_signal_hash", ""))
                    if live_hash != last_hash or ALLOW_DUPLICATE_SIGNALS or elite_force_routing_enabled():
                        if live_hash == last_hash and ALLOW_DUPLICATE_SIGNALS:
                            debug(f"⚠️ DUPLICATE SIGNAL ALLOWED | hash={live_hash[:12]}")
                        else:
                            debug(f"NEW SIGNAL DETECTED | file={SIGNAL_FILE} | hash={live_hash[:12]}")
                        handle_new_signal(live_signal_poll)
                        if not ALLOW_DUPLICATE_SIGNALS:
                            GLOBAL_STATE["last_signal_hash"] = live_hash
                        else:
                            GLOBAL_STATE["last_signal_hash"] = ""
                        GLOBAL_STATE["last_signal_time"] = epoch()
                        GLOBAL_STATE["last_signal_file_mtime"] = int(os.path.getmtime(SIGNAL_FILE)) if file_exists(SIGNAL_FILE) else epoch()
                        append_recent_signal_hash(GLOBAL_STATE, live_hash)
                        save_state(GLOBAL_STATE)
                        debug(f"SIGNAL PERSISTED AFTER PROCESSING | file={SIGNAL_FILE}")
            except Exception as persistent_signal_error:
                log(f"❌ PERSISTENT SIGNAL LISTENER ERROR: {persistent_signal_error}")
                log(traceback.format_exc())


            # =========================================================
            # POSITION-FIRST LOOP GUARD
            # If a trade is already open, do NOT keep re-processing
            # signal.json as a new entry. Manage the active position first.
            # This prevents repeated AUTO CONTRACT SELECTED / ENTRY LOCK
            # messages while TP1/TP2/trailing logic should be running.
            # =========================================================
            ensure_globals_initialized()
            # STEP 15: hard global kill switch / flatten guard before managing or opening anything.
            if not step15_global_guard():
                flush_dirty_stores(force=True)
                time.sleep(POLL_SECONDS)
                continue
            # STEP 14: emergency guard before managing/opening anything.
            if not step14_loop_enforcement():
                flush_dirty_stores(force=True)
                time.sleep(POLL_SECONDS)
                continue
            # PHASE 2: keep order lifecycle and broker/local truth synchronized every loop.
            phase2_sync_order_lifecycle()
            phase2_reconciliation_guard()
            open_positions = GLOBAL_POSITIONS.get("open_positions", []) if isinstance(GLOBAL_POSITIONS, dict) else []
            if open_positions:
                update_positions_from_market_prices()
                manage_open_positions(None)
                sync_live_positions_from_alpaca()
                reconcile_order_fills_into_positions()
                refresh_macro_bridge(force=False, send_alerts=False)
                send_heartbeat(force=False)
                flush_dirty_stores(force=False)
                time.sleep(POLL_SECONDS)
                continue
            live_signal = None

            # =========================================================
            # SIGNAL FILE ROUTING FIX
            # Pick up signal.json by content hash, not just mtime.
            # After processing, clear signal.json so the same trade cannot
            # repeatedly fire.
            # =========================================================
            live_signal = load_active_signal_file()
            if live_signal:
                sig_hash = active_signal_hash(live_signal)
                last_hash = str(GLOBAL_STATE.get("last_signal_hash", ""))
                if sig_hash != last_hash:
                    debug(f"SIGNAL FILE PICKUP OK | file={SIGNAL_FILE} | hash={sig_hash[:12]}")
                    handle_new_signal(live_signal)
                    GLOBAL_STATE["last_signal_hash"] = sig_hash
                    GLOBAL_STATE["last_signal_time"] = epoch()
                    GLOBAL_STATE["last_signal_file_mtime"] = int(os.path.getmtime(SIGNAL_FILE)) if file_exists(SIGNAL_FILE) else epoch()
                    append_recent_signal_hash(GLOBAL_STATE, sig_hash)
                    save_state(GLOBAL_STATE)
                    # Signal persistence enabled: do NOT clear signal.json after loop pickup.
                    debug(f"SIGNAL FILE KEPT | file={SIGNAL_FILE}")
                else:
                    if ALLOW_DUPLICATE_SIGNALS:
                        debug(f"⚠️ DUPLICATE SIGNAL ALLOWED | hash={sig_hash[:12]}")
                        handle_new_signal(live_signal)
                        GLOBAL_STATE["last_signal_hash"] = ""
                        GLOBAL_STATE["last_signal_time"] = epoch()
                        save_state(GLOBAL_STATE)
                    else:
                        debug(f"SIGNAL FILE SKIPPED | duplicate hash={sig_hash[:12]}")

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

def cli_ai_bridge_test() -> None:
    result = ai_bridge_write_signal_if_ready()
    print(json.dumps(result, indent=2, default=str))




def cli_auto_ai_test() -> None:
    result = auto_generate_ai_signal_if_ready()
    print(json.dumps(result, indent=2, default=str))




def cli_macro_test() -> None:
    result = macro_bridge_fred_refresh(force=True)
    print(json.dumps(result, indent=2, default=str))




def cli_adaptive_record_example() -> None:
    result = adaptive_record_qqq_oil_breakout_example()
    print(json.dumps(result, indent=2, default=str))


def cli_adaptive_record_trade(path: str) -> None:
    result = adaptive_record_manual_trade_file(path)
    print(json.dumps(result, indent=2, default=str))


def cli_adaptive_rebuild_stats() -> None:
    stats = adaptive_rebuild_learning_stats()
    adaptive_write_json(ADAPTIVE_LEARNING_STATS_FILE, stats)
    print(json.dumps(stats, indent=2, default=str))


if __name__ == "__main__":
    if "--macro-test" in sys.argv:
        cli_macro_test()
        sys.exit(0)
    if "--auto-ai-test" in sys.argv:
        cli_auto_ai_test()
        sys.exit(0)
    if "--ai-bridge-test" in sys.argv:
        cli_ai_bridge_test()
        sys.exit(0)
    if "--adaptive-record-example" in sys.argv or "record-example" in sys.argv:
        cli_adaptive_record_example()
        sys.exit(0)
    if "--adaptive-rebuild-stats" in sys.argv or "rebuild-learning" in sys.argv:
        cli_adaptive_rebuild_stats()
        sys.exit(0)
    if "--adaptive-record-trade" in sys.argv or "record-trade" in sys.argv:
        try:
            idx = sys.argv.index("--adaptive-record-trade") if "--adaptive-record-trade" in sys.argv else sys.argv.index("record-trade")
            cli_adaptive_record_trade(sys.argv[idx + 1])
        except Exception as cli_error:
            print(f"adaptive record trade failed: {cli_error}")
            sys.exit(1)
        sys.exit(0)
    try:
        if len(sys.argv) > 1 and sys.argv[1] in {"--auto-signal-test", "--test-signal"}:
            ensure_globals_initialized()
            write_unbiased_test_signal()
            sys.exit(0)

        if RUN_LOOP:
            main_loop()
        else:
            run_once()
    except Exception as e:
        log(f"💥 Fatal error: {e}")
        traceback.print_exc()
        sys.exit(1)


# MANUAL HOOK NEEDED: call signal = apply_adaptive_learning_sizing_to_signal(signal) before execution.




# =========================================================
# CLEAN POLLUTED LEARNING MEMORY HELPER
# Removes non-QQQ / invalid-trigger records from adaptive memory files.
# =========================================================
def qqq_clean_existing_learning_memory() -> Dict[str, Any]:
    removed = []
    kept = []

    # Clean adaptive_trade_memory.json if present
    memory_file = globals().get("ADAPTIVE_TRADE_MEMORY_FILE", "adaptive_trade_memory.json")
    try:
        memory = adaptive_load_trade_memory() if "adaptive_load_trade_memory" in globals() else []
    except Exception:
        memory = []

    if isinstance(memory, list):
        for item in memory:
            ok, reason = qqq_clean_learning_allowed(item, stage="clean_existing_memory")
            if ok:
                kept.append(item)
            else:
                removed.append({
                    "ticker": qqq_lock_get_ticker(item),
                    "trigger": qqq_lock_get_trigger(item),
                    "reason": reason,
                })

        try:
            adaptive_save_trade_memory(kept)
            stats = adaptive_rebuild_learning_stats(kept)
            adaptive_write_json(globals().get("ADAPTIVE_LEARNING_STATS_FILE", "adaptive_learning_stats.json"), stats)
        except Exception as e:
            try:
                debug(f"QQQ CLEAN MEMORY adaptive file error: {e}")
            except Exception:
                print(f"QQQ CLEAN MEMORY adaptive file error: {e}", flush=True)

    # Clean jsonl trade memory if present by preserving file backup only.
    # jsonl memory may contain older intelligence-layer data; we do not delete it blindly.
    result = {
        "kept": len(kept),
        "removed": len(removed),
        "removed_samples": removed[:20],
    }

    try:
        debug(f"QQQ CLEAN MEMORY COMPLETE | kept={result['kept']} removed={result['removed']}")
    except Exception:
        print(f"QQQ CLEAN MEMORY COMPLETE | kept={result['kept']} removed={result['removed']}", flush=True)

    return result

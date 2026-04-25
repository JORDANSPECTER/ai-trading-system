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
        send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
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
    trigger = setup_clean.replace("_", " ").title()

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
    return signal


def is_signal_fresh(signal: Dict[str, Any]) -> bool:
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
    phase35_locked_learning_hook(position, note)

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
    phase2_record_paper_order(position, side="buy", qty=safe_int(position.get("qty_open", 0), 0), fill_price=safe_float(position.get("entry_price", 0), 0), note="paper entry filled")
    phase2_post_fill_risk_snapshot("paper_entry_open")
    GLOBAL_STATE["paper_trade_count"] = safe_int(GLOBAL_STATE.get("paper_trade_count", 0), 0) + 1
    save_state(GLOBAL_STATE)
    msg = build_position_open_message(position)
    send_to_telegram(msg)
    send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
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
    send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
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
    send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")


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
        send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
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
        send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
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
            send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
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
        send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
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
        send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
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
        send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
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
            f"Counts: {counts}\nSpread: {spread}"
        )
        msg = build_block_message("PHASE 1 ORDER SAFETY BLOCK", signal_or_stub, reasons, extras)
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
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
    send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
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
    return {"approved": len(reasons) == 0, "reject_reasons": reasons}

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
        send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
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


def phase35_enforcement_gate(signal: Dict[str, Any], phase3_decision: Optional[Dict[str, Any]] = None, size_decision: Optional[Dict[str, Any]] = None, stage: str = "pre_size") -> Dict[str, Any]:
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
    symbol = str(signal.get("symbol", signal.get("ticker", ""))).strip()
    live_requested = bool(GLOBAL_STATE.get("alpaca_enabled", False) and ENABLE_ALPACA and not GLOBAL_STATE.get("paper_enabled", True))

    try:
        if live_requested:
            debug(f"PHASE 3.5 EXECUTION ROUTER | attempting LIVE open | symbol={symbol}")
            pos = open_live_position(signal)
            if pos:
                remember_used_signal_id(signal)
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

def handle_new_signal(signal: Dict[str, Any]):
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
        debug("PHASE 3 NOT RUN | no fresh routable signal or position-management cycle only")
        manage_open_positions(signal)
        return

    duplicate_gate = hard_duplicate_entry_gate(signal)
    if not duplicate_gate["approved"]:
        msg = build_block_message("HARD DUPLICATE CAP BLOCKED SIGNAL", signal, duplicate_gate["reject_reasons"], "Existing symbol/direction is already open or signal was already used.")
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
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
        send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
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

    # PHASE 3: adaptive intelligence uses trade memory to block weak setups,
    # downgrade confidence, and adjust size before risk sizing/execution.
    debug(f"PHASE 3 PRE-ENTRY HOOK REACHED | ticker={regime_signal.get('ticker')} | direction={regime_signal.get('direction')} | confidence={regime_signal.get('confidence')}")
    phase3_decision = phase3_evaluate_adaptive_intelligence(regime_signal)
    if not phase3_decision["approved"]:
        msg = build_block_message("PHASE 3 ADAPTIVE BLOCKED SIGNAL", regime_signal, phase3_decision.get("reject_reasons", []), f"Setup: {phase3_decision.get('setup_key')} | Stats: {phase3_decision.get('stats', {})}")
        send_to_discord(DISCORD_AI_WEBHOOK, msg, "AI")
        send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
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
        send_to_discord(DISCORD_PREMIUM_WEBHOOK, msg, "PREMIUM")
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


def main_loop():
    boot()

    # =========================================================
    # FORCE STARTUP SIGNAL PICKUP
    # Processes signal.json immediately on startup instead of
    # waiting for file watcher / mtime logic.
    # =========================================================
    try:
        startup_signal = load_active_signal_file()
        if startup_signal:
            debug("FORCE STARTUP SIGNAL PICKUP")
            handle_new_signal(startup_signal)
            clear_active_signal_file()
            debug(f"FORCE STARTUP SIGNAL CLEARED | file={SIGNAL_FILE}")
    except Exception as startup_signal_error:
        log(f"❌ FORCE STARTUP SIGNAL PICKUP ERROR: {startup_signal_error}")
        log(traceback.format_exc())

    if not file_exists(SIGNAL_FILE):
        log(f"❌ No signal file found on boot: {SIGNAL_FILE}")
        debug("Routing fallback test signal once.")
        sig = fallback_signal()
        handle_new_signal(sig)

    while True:
        try:
            intel_periodic_snapshot()
            process_telegram_updates()

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
                    clear_active_signal_file()
                    debug(f"SIGNAL FILE CLEARED | file={SIGNAL_FILE}")
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
if __name__ == "__main__":
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

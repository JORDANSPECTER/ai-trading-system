# reason_codes.py
from __future__ import annotations

from enum import Enum
from typing import TypedDict, Optional, Dict, Any


class Severity(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    BLOCK = "BLOCK"
    CRITICAL = "CRITICAL"


class ReasonCode(str, Enum):
    # General engine state
    ENGINE_OK = "ENGINE_OK"
    BOT_PAUSED = "BOT_PAUSED"
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"
    ENGINE_DISABLED = "ENGINE_DISABLED"

    # Market data
    MARKET_DATA_FRESH = "MARKET_DATA_FRESH"
    MARKET_DATA_STALE = "MARKET_DATA_STALE"
    MARKET_DATA_MISSING = "MARKET_DATA_MISSING"

    # Broker / Alpaca
    BROKER_OK = "BROKER_OK"
    BROKER_UNAVAILABLE = "BROKER_UNAVAILABLE"
    BROKER_POSITION_MISMATCH = "BROKER_POSITION_MISMATCH"
    BROKER_ORDER_MISMATCH = "BROKER_ORDER_MISMATCH"
    FOREIGN_ORDER_DETECTED = "FOREIGN_ORDER_DETECTED"
    FOREIGN_POSITION_DETECTED = "FOREIGN_POSITION_DETECTED"

    # Signal validation
    SIGNAL_VALID = "SIGNAL_VALID"
    SIGNAL_MISSING_FIELD = "SIGNAL_MISSING_FIELD"
    SIGNAL_STALE = "SIGNAL_STALE"
    SIGNAL_BAD_RR = "SIGNAL_BAD_RR"
    DUPLICATE_OPEN_SYMBOL = "DUPLICATE_OPEN_SYMBOL"
    NO_TRADE_WINDOW = "NO_TRADE_WINDOW"

    # Regime
    REGIME_ALLOWED = "REGIME_ALLOWED"
    REGIME_BLOCKED = "REGIME_BLOCKED"
    REGIME_SCORE_TOO_LOW = "REGIME_SCORE_TOO_LOW"
    CHOP_REGIME = "CHOP_REGIME"
    EVENT_REGIME = "EVENT_REGIME"

    # Risk
    RISK_APPROVED = "RISK_APPROVED"
    MAX_DAILY_LOSS_REACHED = "MAX_DAILY_LOSS_REACHED"
    MAX_PORTFOLIO_HEAT_REACHED = "MAX_PORTFOLIO_HEAT_REACHED"
    MAX_OPEN_POSITIONS_REACHED = "MAX_OPEN_POSITIONS_REACHED"
    MAX_CONSECUTIVE_LOSSES_REACHED = "MAX_CONSECUTIVE_LOSSES_REACHED"
    BUYING_POWER_INSUFFICIENT = "BUYING_POWER_INSUFFICIENT"

    # Execution
    EXECUTION_APPROVED = "EXECUTION_APPROVED"
    SPREAD_TOO_WIDE = "SPREAD_TOO_WIDE"
    SLIPPAGE_TOO_HIGH = "SLIPPAGE_TOO_HIGH"
    ORDER_RATE_LIMIT = "ORDER_RATE_LIMIT"
    ORDER_IDEMPOTENCY_REPLAY = "ORDER_IDEMPOTENCY_REPLAY"
    ORDER_SUBMIT_ATTEMPT = "ORDER_SUBMIT_ATTEMPT"
    ORDER_ACKED = "ORDER_ACKED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_REJECTED = "ORDER_REJECTED"
    ORDER_TIMEOUT = "ORDER_TIMEOUT"

    # Storage / observability
    TRACE_WRITE_FAILED = "TRACE_WRITE_FAILED"
    STATE_WRITE_FAILED = "STATE_WRITE_FAILED"
    STORAGE_OK = "STORAGE_OK"

    # Learning
    SETUP_OBSERVE_ONLY = "SETUP_OBSERVE_ONLY"
    SETUP_SIZE_UP = "SETUP_SIZE_UP"
    SETUP_SIZE_DOWN = "SETUP_SIZE_DOWN"
    SETUP_DISABLED = "SETUP_DISABLED"


class Reason(TypedDict, total=False):
    code: str
    severity: str
    message: str
    subsystem: str
    metadata: Dict[str, Any]
    timestamp: str


def make_reason(
    code: ReasonCode | str,
    severity: Severity | str = Severity.INFO,
    message: str = "",
    subsystem: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    timestamp: str = "",
) -> Reason:
    return {
        "code": str(code.value if isinstance(code, ReasonCode) else code),
        "severity": str(severity.value if isinstance(severity, Severity) else severity),
        "message": message,
        "subsystem": subsystem,
        "metadata": metadata or {},
        "timestamp": timestamp,
    }

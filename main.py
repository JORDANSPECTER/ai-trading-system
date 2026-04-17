# ============================================================
# AI TRADING SYSTEM — CLEAN FOUNDATION BUILD
# VERSION: V2
# ============================================================

import os
import time
import math
import requests
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Tuple

# ============================================================
# CONFIG
# ============================================================

SYSTEM_CONFIG = {
    "symbols_allowed": ["SPY", "QQQ"],
    "heartbeat_seconds": 1800,          # 30 min
    "loop_sleep_seconds": 60,           # 1 min
    "opening_no_trade_end": (9, 35),
    "morning_end": (11, 0),
    "midday_end": (14, 59),
    "power_hour_end": (16, 15),
    "volume_boost_threshold": 1.20,
    "chase_distance_pct": 0.0035,
    "time_stop_minutes": 10,
    "hard_drawdown_pct": -25.0,
}

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured. Message:", message)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"Telegram send error: {e}")


# ============================================================
# HELPERS
# ============================================================

def now_local() -> datetime:
    return datetime.now()

def time_to_minutes(hour: int, minute: int) -> int:
    return hour * 60 + minute

def dt_to_minutes(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute

def get_session_phase(dt: datetime) -> str:
    current = dt_to_minutes(dt)

    open_start = time_to_minutes(9, 30)
    open_no_trade_end = time_to_minutes(*SYSTEM_CONFIG["opening_no_trade_end"])
    morning_end = time_to_minutes(*SYSTEM_CONFIG["morning_end"])
    midday_end = time_to_minutes(*SYSTEM_CONFIG["midday_end"])
    power_hour_end = time_to_minutes(*SYSTEM_CONFIG["power_hour_end"])
    power_hour_start = time_to_minutes(15, 0)

    if open_start <= current < open_no_trade_end:
        return "OPENING_NO_TRADE"
    if open_no_trade_end <= current <= morning_end:
        return "MORNING_PRIORITY"
    if morning_end < current <= midday_end:
        return "MIDDAY"
    if power_hour_start <= current <= power_hour_end:
        return "POWER_HOUR"
    return "OFF_HOURS"

def safe_pct_distance(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return abs(a - b) / abs(b)

def volume_ratio(current_volume: float, average_volume: float) -> float:
    if average_volume <= 0:
        return 0.0
    return current_volume / average_volume

def is_volume_boosted(current_volume: float, average_volume: float) -> bool:
    return volume_ratio(current_volume, average_volume) >= SYSTEM_CONFIG["volume_boost_threshold"]

def clean_levels(levels: List[float]) -> List[float]:
    cleaned = []
    for x in levels:
        if isinstance(x, (int, float)) and x > 0:
            cleaned.append(round(float(x), 2))
    return sorted(list(set(cleaned)))

def nearest_level(price: float, levels: List[float]) -> Optional[float]:
    valid = clean_levels(levels)
    if not valid:
        return None
    return min(valid, key=lambda x: abs(x - price))

def minutes_since_open(dt: datetime) -> int:
    market_open = time_to_minutes(9, 30)
    current = dt_to_minutes(dt)
    return max(0, current - market_open)

def build_alert_id(symbol: str) -> str:
    return f"{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


# ============================================================
# DATA MODELS
# ============================================================

@dataclass
class RawMarketData:
    symbol: str
    price: float
    vwap: float
    volume: float
    avg_volume: float
    rsi: float
    timestamp: datetime

    oil_price: float = 0.0
    oil_change: float = 0.0
    oil_trend: str = "neutral"      # rising / falling / stabilizing / neutral
    macro_bias: str = "neutral"     # bullish / bearish / neutral

    vix: float = 0.0
    breadth: float = 0.0

    prior_day_high: float = 0.0
    prior_day_low: float = 0.0
    premarket_high: float = 0.0
    premarket_low: float = 0.0

    key_supports: List[float] = field(default_factory=list)
    key_resistances: List[float] = field(default_factory=list)
    big_print_levels: List[float] = field(default_factory=list)


@dataclass
class DataQualityReport:
    is_valid: bool
    confidence_score: float
    issues: List[str] = field(default_factory=list)


@dataclass
class MarketContext:
    symbol: str
    current_price: float
    vwap: float
    rsi: float

    prior_day_high: float
    prior_day_low: float
    premarket_high: float
    premarket_low: float

    key_supports: List[float] = field(default_factory=list)
    key_resistances: List[float] = field(default_factory=list)
    big_print_levels: List[float] = field(default_factory=list)

    current_volume: float = 0.0
    average_volume: float = 0.0

    oil_change_dollars: float = 0.0
    oil_trend: str = "neutral"
    macro_bias: str = "neutral"

    session_phase: str = "UNKNOWN"
    minutes_since_open: int = 0

    distance_from_vwap_pct: float = 0.0
    distance_to_support_pct: float = 0.0
    distance_to_resistance_pct: float = 0.0
    location_score: float = 0.0


@dataclass
class StructureState:
    higher_lows: bool = False
    lower_highs: bool = False

    above_vwap: bool = False
    below_vwap: bool = False
    vwap_reclaimed: bool = False
    vwap_rejected: bool = False
    vwap_held: bool = False

    breakout_with_volume: bool = False
    rejection_at_level: bool = False
    retest_hold: bool = False
    failed_bounce: bool = False
    liquidity_grab_reversal: bool = False

    holding_key_level: bool = False
    accepted_above_level: bool = False
    accepted_below_level: bool = False

    momentum_strong: bool = False
    momentum_fading: bool = False


@dataclass
class BotDecision:
    action: str
    grade: str
    confidence: float

    entry_type: str
    reasons: List[str]
    warnings: List[str]

    stop_reference: str
    target_reference: str

    size_fraction: float
    chasing: bool

    time_window: str
    execution_status: str
    execution_notes: List[str]

    alert_id: str = ""


@dataclass
class TradeOutcome:
    symbol: str
    entry_price: float
    exit_price: float
    pnl_percent: float
    max_favorable_excursion: float
    max_adverse_excursion: float
    outcome_label: str
    failure_reason: str
    timestamp: datetime


# ============================================================
# DATA VALIDATION
# ============================================================

def validate_raw_data(raw: RawMarketData) -> DataQualityReport:
    issues = []
    score = 1.0

    if raw.symbol not in SYSTEM_CONFIG["symbols_allowed"]:
        issues.append(f"Unsupported symbol: {raw.symbol}")
        score -= 0.40

    if raw.price <= 0:
        issues.append("Invalid price")
        score -= 0.50

    if raw.vwap <= 0:
        issues.append("Invalid VWAP")
        score -= 0.30

    if raw.volume < 0:
        issues.append("Invalid volume")
        score -= 0.20

    if raw.avg_volume < 0:
        issues.append("Invalid average volume")
        score -= 0.20

    if not isinstance(raw.timestamp, datetime):
        issues.append("Invalid timestamp")
        score -= 0.30

    if raw.rsi < 0 or raw.rsi > 100:
        issues.append("RSI out of range")
        score -= 0.20

    score = max(0.0, min(1.0, score))
    return DataQualityReport(
        is_valid=(len(issues) == 0),
        confidence_score=score,
        issues=issues
    )


# ============================================================
# CONTEXT BUILDER
# ============================================================

def build_market_context(raw: RawMarketData) -> MarketContext:
    supports = clean_levels(raw.key_supports + [raw.premarket_low, raw.prior_day_low])
    resistances = clean_levels(raw.key_resistances + [raw.premarket_high, raw.prior_day_high])
    big_prints = clean_levels(raw.big_print_levels)

    nearest_support = None
    valid_supports = [x for x in supports if x < raw.price]
    if valid_supports:
        nearest_support = max(valid_supports)

    nearest_resistance = None
    valid_resistances = [x for x in resistances if x > raw.price]
    if valid_resistances:
        nearest_resistance = min(valid_resistances)

    distance_to_support_pct = safe_pct_distance(raw.price, nearest_support) if nearest_support else 0.0
    distance_to_resistance_pct = safe_pct_distance(raw.price, nearest_resistance) if nearest_resistance else 0.0
    distance_from_vwap_pct = safe_pct_distance(raw.price, raw.vwap)

    location_score = 0.5
    if nearest_resistance and nearest_support:
        room_up = nearest_resistance - raw.price
        room_down = raw.price - nearest_support
        total_room = room_up + room_down
        if total_room > 0:
            location_score = room_up / total_room

    return MarketContext(
        symbol=raw.symbol,
        current_price=raw.price,
        vwap=raw.vwap,
        rsi=raw.rsi,
        prior_day_high=raw.prior_day_high,
        prior_day_low=raw.prior_day_low,
        premarket_high=raw.premarket_high,
        premarket_low=raw.premarket_low,
        key_supports=supports,
        key_resistances=resistances,
        big_print_levels=big_prints,
        current_volume=raw.volume,
        average_volume=raw.avg_volume,
        oil_change_dollars=raw.oil_change,
        oil_trend=raw.oil_trend,
        macro_bias=raw.macro_bias,
        session_phase=get_session_phase(raw.timestamp),
        minutes_since_open=minutes_since_open(raw.timestamp),
        distance_from_vwap_pct=distance_from_vwap_pct,
        distance_to_support_pct=distance_to_support_pct,
        distance_to_resistance_pct=distance_to_resistance_pct,
        location_score=location_score
    )


# ============================================================
# STRUCTURE BUILDER
# ============================================================

def build_structure_state(ctx: MarketContext) -> StructureState:
    above_vwap = ctx.current_price > ctx.vwap
    below_vwap = ctx.current_price < ctx.vwap

    boosted = is_volume_boosted(ctx.current_volume, ctx.average_volume)

    holding_key_level = False
    accepted_above_level = False
    accepted_below_level = False
    rejection_at_level = False

    all_levels = clean_levels(
        ctx.key_supports + ctx.key_resistances + ctx.big_print_levels +
        [ctx.prior_day_high, ctx.prior_day_low, ctx.premarket_high, ctx.premarket_low]
    )
    near = nearest_level(ctx.current_price, all_levels)

    if near:
        dist = safe_pct_distance(ctx.current_price, near)
        if dist <= 0.0015:
            holding_key_level = True
        if ctx.current_price > near and dist <= 0.0025:
            accepted_above_level = True
        if ctx.current_price < near and dist <= 0.0025:
            accepted_below_level = True
        if dist <= 0.0015 and below_vwap:
            rejection_at_level = True

    higher_lows = above_vwap and ctx.rsi >= 50
    lower_highs = below_vwap and ctx.rsi <= 50

    vwap_reclaimed = above_vwap and ctx.distance_from_vwap_pct <= 0.003
    vwap_rejected = below_vwap and ctx.distance_from_vwap_pct <= 0.003
    vwap_held = above_vwap and ctx.distance_from_vwap_pct <= 0.0025

    breakout_with_volume = boosted and (
        ctx.current_price > ctx.premarket_high or
        ctx.current_price > ctx.prior_day_high or
        ctx.current_price < ctx.premarket_low or
        ctx.current_price < ctx.prior_day_low
    )

    retest_hold = above_vwap and holding_key_level
    failed_bounce = below_vwap and rejection_at_level
    liquidity_grab_reversal = False

    momentum_strong = boosted and ((above_vwap and ctx.rsi > 55) or (below_vwap and ctx.rsi < 45))
    momentum_fading = not boosted and (abs(ctx.current_price - ctx.vwap) < max(0.15, ctx.current_price * 0.0008))

    return StructureState(
        higher_lows=higher_lows,
        lower_highs=lower_highs,
        above_vwap=above_vwap,
        below_vwap=below_vwap,
        vwap_reclaimed=vwap_reclaimed,
        vwap_rejected=vwap_rejected,
        vwap_held=vwap_held,
        breakout_with_volume=breakout_with_volume,
        rejection_at_level=rejection_at_level,
        retest_hold=retest_hold,
        failed_bounce=failed_bounce,
        liquidity_grab_reversal=liquidity_grab_reversal,
        holding_key_level=holding_key_level,
        accepted_above_level=accepted_above_level,
        accepted_below_level=accepted_below_level,
        momentum_strong=momentum_strong,
        momentum_fading=momentum_fading
    )


# ============================================================
# DECISION ENGINE
# ============================================================

def oil_bias(ctx: MarketContext) -> str:
    if ctx.oil_change_dollars >= 2.0:
        return "bearish_pressure"
    if ctx.oil_change_dollars >= 1.0 and ctx.oil_trend == "rising":
        return "bearish_pressure"
    if ctx.oil_change_dollars <= -1.0:
        return "bullish_relief"
    if ctx.oil_trend in {"falling", "stabilizing"} and ctx.oil_change_dollars < 1.0:
        return "bullish_relief"
    return "neutral"

def detect_chasing(ctx: MarketContext) -> bool:
    levels = clean_levels(
        ctx.key_supports + ctx.key_resistances + ctx.big_print_levels +
        [ctx.prior_day_high, ctx.prior_day_low, ctx.premarket_high, ctx.premarket_low]
    )
    near = nearest_level(ctx.current_price, levels)
    if not near:
        return False
    return safe_pct_distance(ctx.current_price, near) > SYSTEM_CONFIG["chase_distance_pct"]

def determine_stop_reference(ctx: MarketContext, action: str) -> str:
    if action == "CALL":
        if ctx.key_supports:
            below = [x for x in ctx.key_supports if x < ctx.current_price]
            if below:
                return f"Below support {max(below):.2f}"
        return f"Below VWAP {ctx.vwap:.2f}"

    if action == "PUT":
        if ctx.key_resistances:
            above = [x for x in ctx.key_resistances if x > ctx.current_price]
            if above:
                return f"Above resistance {min(above):.2f}"
        return f"Above VWAP {ctx.vwap:.2f}"

    return "N/A"

def determine_target_reference(ctx: MarketContext, action: str) -> str:
    if action == "CALL":
        targets = [x for x in clean_levels(ctx.key_resistances + ctx.big_print_levels + [ctx.premarket_high, ctx.prior_day_high]) if x > ctx.current_price]
        if targets:
            return f"Target {min(targets):.2f}"
        return "Trail into strength"

    if action == "PUT":
        targets = [x for x in clean_levels(ctx.key_supports + ctx.big_print_levels + [ctx.premarket_low, ctx.prior_day_low]) if x < ctx.current_price]
        if targets:
            return f"Target {max(targets):.2f}"
        return "Trail into weakness"

    return "N/A"

def make_hybrid_decision(ctx: MarketContext, st: StructureState) -> BotDecision:
    reasons = []
    warnings = []
    execution_notes = []
    session = ctx.session_phase

    score_call = 0
    score_put = 0

    if session == "OPENING_NO_TRADE":
        return BotDecision(
            action="AVOID",
            grade="AVOID",
            confidence=0.0,
            entry_type="No Trade",
            reasons=["Avoid the first few minutes after the open while price discovery clears."],
            warnings=[],
            stop_reference="N/A",
            target_reference="N/A",
            size_fraction=0.0,
            chasing=False,
            time_window=session,
            execution_status="AVOID",
            execution_notes=["Opening filter active."],
            alert_id=build_alert_id(ctx.symbol)
        )

    if session == "MORNING_PRIORITY":
        score_call += 1
        score_put += 1
        reasons.append("Morning priority window is active.")
    elif session == "POWER_HOUR":
        score_call += 1
        score_put += 1
        reasons.append("Power hour is active.")
    elif session == "MIDDAY":
        score_call -= 1
        score_put -= 1
        warnings.append("Midday lowers setup quality.")
    else:
        score_call -= 2
        score_put -= 2
        warnings.append("Outside priority session window.")

    # CALL scoring
    if st.above_vwap:
        score_call += 1
        reasons.append("Price is above VWAP.")
    if st.vwap_reclaimed:
        score_call += 2
        reasons.append("VWAP reclaim supports calls.")
    if st.vwap_held:
        score_call += 1
        reasons.append("VWAP is holding as support.")
    if st.higher_lows:
        score_call += 1
        reasons.append("Higher lows support bullish continuation.")
    if st.breakout_with_volume and st.above_vwap:
        score_call += 1
        reasons.append("Breakout with volume supports upside.")
    if st.retest_hold:
        score_call += 2
        reasons.append("Retest hold supports a cleaner long entry.")
    if st.accepted_above_level:
        score_call += 1
        reasons.append("Accepted above a key level.")
    if st.momentum_strong and st.above_vwap:
        score_call += 1
        reasons.append("Momentum is strong for calls.")

    # PUT scoring
    if st.below_vwap:
        score_put += 1
        reasons.append("Price is below VWAP.")
    if st.vwap_rejected:
        score_put += 2
        reasons.append("VWAP rejection supports puts.")
    if st.lower_highs:
        score_put += 1
        reasons.append("Lower highs support downside.")
    if st.rejection_at_level:
        score_put += 2
        reasons.append("Rejection at level supports puts.")
    if st.failed_bounce:
        score_put += 2
        reasons.append("Failed bounce supports a short entry.")
    if st.accepted_below_level:
        score_put += 1
        reasons.append("Accepted below a key level.")
    if st.breakout_with_volume and st.below_vwap:
        score_put += 1
        reasons.append("Breakdown with volume supports downside.")
    if st.momentum_strong and st.below_vwap:
        score_put += 1
        reasons.append("Momentum is strong for puts.")

    # macro filter
    oil_state = oil_bias(ctx)
    if oil_state == "bullish_relief":
        score_call += 1
        reasons.append("Oil relief supports upside.")
    elif oil_state == "bearish_pressure":
        score_call -= 1
        score_put += 1
        reasons.append("Oil pressure supports downside.")
    else:
        reasons.append("Oil is neutral.")

    if ctx.macro_bias == "bullish":
        score_call += 1
    elif ctx.macro_bias == "bearish":
        score_put += 1

    # location penalty
    if ctx.distance_to_resistance_pct and ctx.distance_to_resistance_pct < 0.002 and st.above_vwap:
        score_call -= 1
        warnings.append("Long is close to resistance.")
    if ctx.distance_to_support_pct and ctx.distance_to_support_pct < 0.002 and st.below_vwap:
        score_put -= 1
        warnings.append("Short is close to support.")

    # determine action
    if score_call >= score_put and score_call >= 4:
        action = "CALL"
        raw_score = score_call
        entry_type = "Bullish continuation / reclaim / retest hold"
    elif score_put > score_call and score_put >= 4:
        action = "PUT"
        raw_score = score_put
        entry_type = "Bearish rejection / failed bounce / breakdown"
    else:
        action = "AVOID"
        raw_score = max(score_call, score_put)
        entry_type = "No clear edge"

    chasing = False
    if action in {"CALL", "PUT"}:
        chasing = detect_chasing(ctx)
        if chasing:
            warnings.append("YOU ARE CHASING. Entry is too extended.")
            raw_score -= 2

    if action == "AVOID" or raw_score < 4:
        grade = "AVOID"
        confidence = 0.20
    elif raw_score >= 9:
        grade = "A+"
        confidence = 0.95
    elif raw_score >= 7:
        grade = "A"
        confidence = 0.87
    elif raw_score >= 5:
        grade = "B+"
        confidence = 0.77
    else:
        grade = "B"
        confidence = 0.66

    if action == "AVOID":
        execution_status = "AVOID"
        execution_notes.append("No clean edge.")
        size_fraction = 0.0
    else:
        if chasing and grade in {"B", "B+"}:
            execution_status = "BLOCKED"
            execution_notes.append("Blocked because entry is too extended.")
            size_fraction = 0.0
        elif chasing and grade in {"A", "A+"}:
            execution_status = "REDUCED"
            execution_notes.append("Strong setup but extended. Reduce size.")
            size_fraction = 0.50
        elif session == "MIDDAY":
            execution_status = "REDUCED"
            execution_notes.append("Midday trade. Reduce size.")
            size_fraction = 0.50
        else:
            execution_status = "READY"
            execution_notes.append("Trade is executable.")
            size_fraction = 1.0 if grade in {"A+", "A"} else 0.70

    return BotDecision(
        action=action,
        grade=grade,
        confidence=confidence,
        entry_type=entry_type,
        reasons=reasons,
        warnings=warnings,
        stop_reference=determine_stop_reference(ctx, action),
        target_reference=determine_target_reference(ctx, action),
        size_fraction=size_fraction,
        chasing=chasing,
        time_window=session,
        execution_status=execution_status,
        execution_notes=execution_notes,
        alert_id=build_alert_id(ctx.symbol)
    )


# ============================================================
# TRADE MANAGEMENT
# ============================================================

def manage_open_trade(
    minutes_in_trade: int,
    pnl_percent: float,
    momentum_fading: bool
) -> Dict[str, object]:
    result = {
        "close_trade": False,
        "take_partial": False,
        "partial_size": 0.0,
        "move_stop_to_breakeven": False,
        "notes": []
    }

    if minutes_in_trade >= SYSTEM_CONFIG["time_stop_minutes"] and pnl_percent <= 0:
        result["close_trade"] = True
        result["notes"].append("Time-stop triggered: trade did not work fast enough.")
        return result

    if pnl_percent <= SYSTEM_CONFIG["hard_drawdown_pct"]:
        result["close_trade"] = True
        result["notes"].append("Hard drawdown stop triggered.")
        return result

    if 20 <= pnl_percent < 50:
        result["take_partial"] = True
        result["partial_size"] = 0.25
        result["notes"].append("Take first partial into strength.")
    elif 50 <= pnl_percent < 100:
        result["take_partial"] = True
        result["partial_size"] = 0.25
        result["move_stop_to_breakeven"] = True
        result["notes"].append("Take second partial and protect the rest.")
    elif pnl_percent >= 100:
        result["take_partial"] = True
        result["partial_size"] = 0.30
        result["move_stop_to_breakeven"] = True
        result["notes"].append("Large winner. Continue scaling out.")

    if momentum_fading and pnl_percent > 0:
        result["notes"].append("Momentum is fading. Do not overstay the trade.")

    return result


# ============================================================
# ALERT FORMATTER
# ============================================================

def format_telegram_alert(decision: BotDecision, ctx: MarketContext) -> str:
    icon = {
        "CALL": "🟢",
        "PUT": "🔴",
        "AVOID": "⚪"
    }.get(decision.action, "⚪")

    lines = [
        f"{icon} {ctx.symbol} AI DECISION",
        f"Action: {decision.action}",
        f"Grade: {decision.grade}",
        f"Confidence: {decision.confidence:.2f}",
        f"Entry Type: {decision.entry_type}",
        f"Time Window: {decision.time_window}",
        f"Execution: {decision.execution_status}",
        f"Size: {decision.size_fraction:.2f}",
        f"Stop: {decision.stop_reference}",
        f"Target: {decision.target_reference}",
    ]

    if decision.warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend([f"- {w}" for w in decision.warnings[:3]])

    if decision.execution_notes:
        lines.append("")
        lines.append("Execution Notes:")
        lines.extend([f"- {n}" for n in decision.execution_notes[:3]])

    return "\n".join(lines)


# ============================================================
# ANTI-SPAM STATE
# ============================================================

LAST_ALERT_STATE: Dict[str, Tuple[str, str]] = {}

def should_send_alert(symbol: str, decision: BotDecision) -> bool:
    current_state = (decision.action, decision.grade)
    previous_state = LAST_ALERT_STATE.get(symbol)

    if previous_state != current_state:
        LAST_ALERT_STATE[symbol] = current_state
        return True

    return False


# ============================================================
# PLACEHOLDER DATA FEED
# REPLACE THIS LATER WITH TWELVE DATA / LIVE API
# ============================================================

def get_mock_raw_market_data(symbol: str) -> RawMarketData:
    current_time = now_local()

    if symbol == "QQQ":
        return RawMarketData(
            symbol="QQQ",
            price=527.35,
            vwap=526.90,
            volume=1_500_000,
            avg_volume=1_100_000,
            rsi=61.0,
            timestamp=current_time,
            oil_price=81.50,
            oil_change=1.85,
            oil_trend="stabilizing",
            macro_bias="neutral",
            prior_day_high=528.10,
            prior_day_low=522.40,
            premarket_high=527.60,
            premarket_low=525.80,
            key_supports=[526.50, 525.80],
            key_resistances=[527.60, 528.10, 529.00],
            big_print_levels=[527.00]
        )

    return RawMarketData(
        symbol="SPY",
        price=513.20,
        vwap=512.85,
        volume=1_300_000,
        avg_volume=1_000_000,
        rsi=59.0,
        timestamp=current_time,
        oil_price=81.50,
        oil_change=1.85,
        oil_trend="stabilizing",
        macro_bias="neutral",
        prior_day_high=514.00,
        prior_day_low=509.90,
        premarket_high=513.35,
        premarket_low=511.80,
        key_supports=[512.40, 511.80],
        key_resistances=[513.35, 514.00, 514.80],
        big_print_levels=[513.00]
    )


# ============================================================
# MAIN AI LOOP
# ============================================================

def run_symbol(symbol: str) -> None:
    raw = get_mock_raw_market_data(symbol)
    quality = validate_raw_data(raw)

    if not quality.is_valid:
        send_telegram(
            f"⚠️ {symbol} data validation failed\n"
            f"Confidence: {quality.confidence_score:.2f}\n"
            f"Issues: {', '.join(quality.issues)}"
        )
        return

    ctx = build_market_context(raw)
    st = build_structure_state(ctx)
    decision = make_hybrid_decision(ctx, st)

    if should_send_alert(symbol, decision):
        send_telegram(format_telegram_alert(decision, ctx))
    else:
        print(f"No state change for {symbol}. No alert sent.")


def run() -> None:
    send_telegram("✅ AI TRADING SYSTEM ONLINE")

    last_heartbeat = time.time()

    while True:
        try:
            for symbol in SYSTEM_CONFIG["symbols_allowed"]:
                run_symbol(symbol)

            current_time = time.time()
            if current_time - last_heartbeat >= SYSTEM_CONFIG["heartbeat_seconds"]:
                send_telegram("💓 AI SYSTEM STILL RUNNING")
                last_heartbeat = current_time

        except Exception as e:
            send_telegram(f"⚠️ SYSTEM ERROR: {str(e)}")

        time.sleep(SYSTEM_CONFIG["loop_sleep_seconds"])


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    run()
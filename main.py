# =========================================================
# AI TRADING SYSTEM — CLEAN MASTER BUILD
# TOP SECTION (CORRECTED)
# =========================================================

import os
import time
import json
import traceback
import requests

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Tuple


# =========================================================
# ENV VARIABLES
# These must be set in GitHub Secrets / Variables
# =========================================================

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()

SYMBOL = os.getenv("SYMBOL", "QQQ").strip().upper()
SECONDARY_SYMBOL = os.getenv("SECONDARY_SYMBOL", "SPY").strip().upper()
OIL_SYMBOL = os.getenv("OIL_SYMBOL", "USO").strip().upper()

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "900"))

ENABLE_DISCORD_ALERTS = os.getenv("ENABLE_DISCORD_ALERTS", "true").lower() == "true"
ENABLE_TELEGRAM_ALERTS = os.getenv("ENABLE_TELEGRAM_ALERTS", "true").lower() == "true"
ENABLE_HEARTBEAT = os.getenv("ENABLE_HEARTBEAT", "true").lower() == "true"

MAX_CHASE_DISTANCE_PCT = float(os.getenv("MAX_CHASE_DISTANCE_PCT", "0.35"))
MIN_SCORE_FOR_ALERT = int(os.getenv("MIN_SCORE_FOR_ALERT", "55"))


# =========================================================
# RUNTIME STATE
# =========================================================

BOT_ACTIVE = True
LAST_HEARTBEAT_TS = 0.0
LAST_ALERT_SIGNATURE = ""
LAST_TELEGRAM_UPDATE_ID = 0


# =========================================================
# LOGGING
# =========================================================

def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


# =========================================================
# STARTUP / ENV CHECKS
# =========================================================

def validate_env() -> None:
    log("Checking environment variables...")

    log(f"DISCORD_WEBHOOK_URL: {'OK' if DISCORD_WEBHOOK_URL else 'MISSING'}")
    log(f"TELEGRAM_BOT_TOKEN: {'OK' if TELEGRAM_BOT_TOKEN else 'MISSING'}")
    log(f"TELEGRAM_CHAT_ID: {'OK' if TELEGRAM_CHAT_ID else 'MISSING'}")
    log(f"TWELVE_DATA_API_KEY: {'OK' if TWELVE_DATA_API_KEY else 'MISSING'}")

    log(f"SYMBOL: {SYMBOL}")
    log(f"SECONDARY_SYMBOL: {SECONDARY_SYMBOL}")
    log(f"OIL_SYMBOL: {OIL_SYMBOL}")
    log(f"POLL_INTERVAL: {POLL_INTERVAL}")
    log(f"HEARTBEAT_INTERVAL: {HEARTBEAT_INTERVAL}")


# =========================================================
# TEST HELPERS
# =========================================================

def test_twelve_data(symbol: str = None) -> None:
    symbol = symbol or SYMBOL

    if not TWELVE_DATA_API_KEY:
        log("Twelve Data test skipped: missing API key")
        return

    try:
        url = "https://api.twelvedata.com/quote"
        params = {
            "symbol": symbol,
            "apikey": TWELVE_DATA_API_KEY
        }
        r = requests.get(url, params=params, timeout=15)
        data = r.json()

        log(f"Twelve Data test for {symbol}:")
        log(json.dumps(data, indent=2)[:1000])

    except Exception as e:
        log(f"Twelve Data test failed: {e}")


def send_discord_test() -> None:
    if not DISCORD_WEBHOOK_URL:
        log("Discord test skipped: missing webhook")
        return

    try:
        payload = {"content": "🧪 Discord test working from main.py"}
        r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=15)
        log(f"Discord status: {r.status_code}")
        log(r.text[:300])
    except Exception as e:
        log(f"Discord test failed: {e}")


def send_telegram_test() -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("Telegram test skipped: missing token or chat id")
        return

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": "🧪 Telegram test working from main.py"
        }
        r = requests.post(url, data=payload, timeout=15)
        log(f"Telegram status: {r.status_code}")
        log(r.text[:300])
    except Exception as e:
        log(f"Telegram test failed: {e}")

# =========================================================
# ENV VARIABLES
# =========================================================

import os
import requests
import json
from datetime import datetime

DISCORD_WEBHOOK_URL = os.getenv("https://discord.com/api/webhooks/1494042156069949533/sxnwJnv036sXgcMy4vWnz1lFuK_hmi4p7OJk1Mbuaa83azTq9WugFPAPMMpWf1at21Wu", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("8288769897:AAGoa0PFwm_Z4fFc4_ZMuKuAu_UPJymnY8E", "").strip()
TELEGRAM_CHAT_ID = os.getenv("8661143355", "").strip()
TWELVE_DATA_API_KEY = os.getenv("b8760b201df4466b8082bc17c1ab1e9b", "").strip()

SYMBOL = os.getenv("SYMBOL", "QQQ").strip().upper()
SECONDARY_SYMBOL = os.getenv("SECONDARY_SYMBOL", "SPY").strip().upper()
OIL_SYMBOL = os.getenv("OIL_SYMBOL", "USO").strip().upper()

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))


# =========================================================
# LOGGING + ENV CHECK
# =========================================================

def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def validate_env() -> None:
    log("Checking environment variables...")

    log(f"TWELVE_DATA_API_KEY: {'OK' if TWELVE_DATA_API_KEY else 'MISSING'}")
    log(f"DISCORD_WEBHOOK_URL: {'OK' if DISCORD_WEBHOOK_URL else 'MISSING'}")
    log(f"TELEGRAM_BOT_TOKEN: {'OK' if TELEGRAM_BOT_TOKEN else 'MISSING'}")
    log(f"TELEGRAM_CHAT_ID: {'OK' if TELEGRAM_CHAT_ID else 'MISSING'}")

    log(f"Primary symbol: {SYMBOL}")
    log(f"Secondary symbol: {SECONDARY_SYMBOL}")
    log(f"Oil symbol: {OIL_SYMBOL}")


# =========================================================
# TEST: TWELVE DATA
# =========================================================

def test_twelve_data(symbol: str = SYMBOL) -> None:
    if not TWELVE_DATA_API_KEY:
        log("Twelve Data test skipped (no API key)")
        return

    try:
        url = "https://api.twelvedata.com/quote"
        params = {
            "symbol": symbol,
            "apikey": TWELVE_DATA_API_KEY
        }

        r = requests.get(url, params=params, timeout=10)
        data = r.json()

        log(f"{symbol} DATA:")
        log(json.dumps(data, indent=2)[:800])

    except Exception as e:
        log(f"Twelve Data error: {e}")


# =========================================================
# TEST: DISCORD
# =========================================================

def send_discord_test() -> None:
    if not DISCORD_WEBHOOK_URL:
        log("Discord skipped (no webhook)")
        return

    try:
        payload = {"content": "🧪 Discord test working"}
        r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)

        log(f"Discord status: {r.status_code}")

    except Exception as e:
        log(f"Discord error: {e}")


# =========================================================
# TEST: TELEGRAM
# =========================================================

def send_telegram_test() -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("Telegram skipped (missing token/chat id)")
        return

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": "🧪 Telegram test working"
        }

        r = requests.post(url, data=payload, timeout=10)

        log(f"Telegram status: {r.status_code}")

    except Exception as e:
        log(f"Telegram error: {e}")


# =========================================================
# STARTUP TEST RUN
# =========================================================

if __name__ == "__main__":
    log("🚀 SYSTEM STARTING")
    validate_env()
    test_twelve_data()
    send_discord_test()
    send_telegram_test()

# =========================================================
# AI TRADING SYSTEM — CLEAN MASTER BUILD
# Alert Engine + Discord + Telegram + Twelve Data
# =========================================================

import os
import time
import json
import traceback
import requests

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Tuple

# =========================================================
# ENV VARIABLES
# =========================================================

DISCORD_WEBHOOK_URL = os.getenv("https://discord.com/api/webhooks/1494042156069949533/sxnwJnv036sXgcMy4vWnz1lFuK_hmi4p7OJk1Mbuaa83azTq9WugFPAPMMpWf1at21Wu", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("8288769897:AAGoa0PFwm_Z4fFc4_ZMuKuAu_UPJymnY8E", "").strip()
TELEGRAM_CHAT_ID = os.getenv("8661143355", "").strip()
TWELVE_DATA_API_KEY = os.getenv("b8760b201df4466b8082bc17c1ab1e9b", "").strip()

SYMBOL = os.getenv("SYMBOL", "QQQ").strip().upper()
SECONDARY_SYMBOL = os.getenv("SECONDARY_SYMBOL", "SPY").strip().upper()
OIL_SYMBOL = os.getenv("OIL_SYMBOL", "USO").strip().upper()

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "900"))

ENABLE_DISCORD_ALERTS = os.getenv("ENABLE_DISCORD_ALERTS", "true").lower() == "true"
ENABLE_TELEGRAM_ALERTS = os.getenv("ENABLE_TELEGRAM_ALERTS", "true").lower() == "true"
ENABLE_HEARTBEAT = os.getenv("ENABLE_HEARTBEAT", "true").lower() == "true"

MAX_CHASE_DISTANCE_PCT = float(os.getenv("MAX_CHASE_DISTANCE_PCT", "0.35"))
MIN_SCORE_FOR_ALERT = int(os.getenv("MIN_SCORE_FOR_ALERT", "55"))

# =========================================================
# RUNTIME STATE
# =========================================================

BOT_ACTIVE = True
LAST_HEARTBEAT_TS = 0.0
LAST_ALERT_SIGNATURE = ""
LAST_TELEGRAM_UPDATE_ID = 0

# =========================================================
# LOGGING
# =========================================================

def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def safe_float(value, default=0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


# =========================================================
# DATA MODELS
# =========================================================

@dataclass
class MarketSnapshot:
    symbol: str
    last_price: float
    open_price: float
    high_price: float
    low_price: float
    prev_close: float
    volume: float
    timestamp: str = ""


@dataclass
class MarketContext:
    symbol: str
    current_price: float
    secondary_price: float
    oil_price: float

    symbol_day_change_pct: float
    secondary_day_change_pct: float
    oil_day_change_pct: float
    oil_day_change_dollars: float

    vwap: float
    rsi: float

    prior_day_high: float
    prior_day_low: float
    premarket_high: float
    premarket_low: float

    key_supports: List[float] = field(default_factory=list)
    key_resistances: List[float] = field(default_factory=list)
    big_print_levels: List[float] = field(default_factory=list)

    macro_bias: str = "neutral"
    oil_trend: str = "neutral"


@dataclass
class StructureState:
    above_vwap: bool = False
    below_vwap: bool = False
    vwap_reclaimed: bool = False
    vwap_rejected: bool = False

    breakout_with_volume: bool = False
    rejection_at_level: bool = False
    retest_hold: bool = False
    failed_bounce: bool = False

    higher_low: bool = False
    lower_high: bool = False

    near_support: bool = False
    near_resistance: bool = False
    near_big_print: bool = False

    stretched_up: bool = False
    stretched_down: bool = False


@dataclass
class BotDecision:
    symbol: str
    bias: str
    grade: str
    action: str
    confidence: int
    score: int
    entry_zone: str
    stop_zone: str
    target_zone: str
    premium_message: str
    free_message: str
    reasons: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    chase_blocked: bool = False
    timestamp: str = ""


# =========================================================
# ENV VALIDATION
# =========================================================

def validate_env() -> None:
    log("Validating environment variables...")

    if not TWELVE_DATA_API_KEY:
        log("WARNING: TWELVE_DATA_API_KEY missing")
    if not DISCORD_WEBHOOK_URL:
        log("WARNING: DISCORD_WEBHOOK_URL missing")
    if not TELEGRAM_BOT_TOKEN:
        log("WARNING: TELEGRAM_BOT_TOKEN missing")
    if not TELEGRAM_CHAT_ID:
        log("WARNING: TELEGRAM_CHAT_ID missing")

    log("Environment validation complete.")


# =========================================================
# TWELVE DATA HELPERS
# =========================================================

def twelve_price(symbol: str) -> Optional[MarketSnapshot]:
    url = "https://api.twelvedata.com/quote"
    params = {
        "symbol": symbol,
        "apikey": TWELVE_DATA_API_KEY,
    }

    try:
        r = requests.get(url, params=params, timeout=20)
        data = r.json()

        if "code" in data and data.get("status") == "error":
            log(f"Twelve Data quote error for {symbol}: {data}")
            return None

        last_price = safe_float(data.get("close") or data.get("price"))
        open_price = safe_float(data.get("open"))
        high_price = safe_float(data.get("high"))
        low_price = safe_float(data.get("low"))
        prev_close = safe_float(data.get("previous_close"))
        volume = safe_float(data.get("volume"))

        return MarketSnapshot(
            symbol=symbol,
            last_price=last_price,
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            prev_close=prev_close,
            volume=volume,
            timestamp=str(data.get("datetime", "")),
        )
    except Exception as e:
        log(f"Error getting quote for {symbol}: {e}")
        return None


def twelve_time_series(symbol: str, interval: str = "5min", outputsize: int = 30) -> List[Dict]:
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": TWELVE_DATA_API_KEY,
    }

    try:
        r = requests.get(url, params=params, timeout=20)
        data = r.json()

        if "code" in data and data.get("status") == "error":
            log(f"Twelve Data time_series error for {symbol}: {data}")
            return []

        values = data.get("values", [])
        values.reverse()  # oldest -> newest
        return values
    except Exception as e:
        log(f"Error getting time series for {symbol}: {e}")
        return []


# =========================================================
# CALC HELPERS
# =========================================================

def percent_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return ((current - previous) / previous) * 100.0


def calc_rsi_from_closes(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0

    gains = []
    losses = []

    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        if delta >= 0:
            gains.append(delta)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(delta))

    recent_gains = gains[-period:]
    recent_losses = losses[-period:]

    avg_gain = sum(recent_gains) / period
    avg_loss = sum(recent_losses) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calc_vwap_from_bars(bars: List[Dict]) -> float:
    if not bars:
        return 0.0

    cumulative_pv = 0.0
    cumulative_volume = 0.0

    for bar in bars:
        high_ = safe_float(bar.get("high"))
        low_ = safe_float(bar.get("low"))
        close_ = safe_float(bar.get("close"))
        vol_ = safe_float(bar.get("volume"), 1.0)

        typical_price = (high_ + low_ + close_) / 3.0
        cumulative_pv += typical_price * vol_
        cumulative_volume += vol_

    if cumulative_volume == 0:
        return 0.0

    return cumulative_pv / cumulative_volume


def avg_volume(bars: List[Dict], lookback: int = 10) -> float:
    if not bars:
        return 0.0
    vols = [safe_float(x.get("volume")) for x in bars[-lookback:]]
    return sum(vols) / max(len(vols), 1)


def nearest_level(price: float, levels: List[float]) -> float:
    if not levels:
        return 0.0
    return min(levels, key=lambda x: abs(x - price))


def distance_pct(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return abs((a - b) / b) * 100.0


# =========================================================
# LEVEL BUILDERS
# =========================================================

def build_key_levels(primary: MarketSnapshot, bars: List[Dict]) -> Tuple[List[float], List[float], float, float]:
    if not bars:
        return [primary.low_price], [primary.high_price], primary.high_price, primary.low_price

    highs = [safe_float(x.get("high")) for x in bars]
    lows = [safe_float(x.get("low")) for x in bars]

    premarket_high = max(highs) if highs else primary.high_price
    premarket_low = min(lows) if lows else primary.low_price

    supports = sorted({
        round(primary.low_price, 2),
        round(primary.prev_close, 2),
        round(premarket_low, 2),
    })

    resistances = sorted({
        round(primary.high_price, 2),
        round(primary.open_price, 2),
        round(premarket_high, 2),
    })

    return supports, resistances, premarket_high, premarket_low


def build_synthetic_big_print_levels(primary: MarketSnapshot) -> List[float]:
    if primary.prev_close == 0:
        return []

    return sorted({
        round(primary.prev_close, 2),
        round(primary.open_price, 2),
    })


# =========================================================
# CONTEXT BUILDER
# =========================================================

def classify_oil_trend(day_change_pct: float, day_change_dollars: float) -> str:
    if day_change_dollars >= 2.0 or day_change_pct >= 2.0:
        return "strong_up"
    if day_change_dollars <= -2.0 or day_change_pct <= -2.0:
        return "strong_down"
    if day_change_dollars > 0:
        return "up"
    if day_change_dollars < 0:
        return "down"
    return "neutral"


def infer_macro_bias(symbol_change: float, oil_change: float) -> str:
    if oil_change >= 2.0 and symbol_change < 0:
        return "risk_off"
    if oil_change <= -1.0 and symbol_change > 0:
        return "risk_on"
    return "neutral"


def build_market_context() -> Optional[MarketContext]:
    primary = twelve_price(SYMBOL)
    secondary = twelve_price(SECONDARY_SYMBOL)
    oil = twelve_price(OIL_SYMBOL)
    bars = twelve_time_series(SYMBOL, interval="5min", outputsize=30)

    if not primary or not secondary or not oil:
        log("Failed to build full market context.")
        return None

    closes = [safe_float(x.get("close")) for x in bars if x.get("close") is not None]
    vwap = calc_vwap_from_bars(bars)
    rsi = calc_rsi_from_closes(closes)

    supports, resistances, premarket_high, premarket_low = build_key_levels(primary, bars)
    big_print_levels = build_synthetic_big_print_levels(primary)

    symbol_day_change_pct = percent_change(primary.last_price, primary.prev_close)
    secondary_day_change_pct = percent_change(secondary.last_price, secondary.prev_close)
    oil_day_change_pct = percent_change(oil.last_price, oil.prev_close)
    oil_day_change_dollars = oil.last_price - oil.prev_close

    oil_trend = classify_oil_trend(oil_day_change_pct, oil_day_change_dollars)
    macro_bias = infer_macro_bias(symbol_day_change_pct, oil_day_change_dollars)

    return MarketContext(
        symbol=SYMBOL,
        current_price=primary.last_price,
        secondary_price=secondary.last_price,
        oil_price=oil.last_price,
        symbol_day_change_pct=symbol_day_change_pct,
        secondary_day_change_pct=secondary_day_change_pct,
        oil_day_change_pct=oil_day_change_pct,
        oil_day_change_dollars=oil_day_change_dollars,
        vwap=vwap,
        rsi=rsi,
        prior_day_high=primary.high_price,
        prior_day_low=primary.low_price,
        premarket_high=premarket_high,
        premarket_low=premarket_low,
        key_supports=supports,
        key_resistances=resistances,
        big_print_levels=big_print_levels,
        macro_bias=macro_bias,
        oil_trend=oil_trend,
    )


# =========================================================
# STRUCTURE DETECTION
# =========================================================

def detect_structure(context: MarketContext, bars: List[Dict]) -> StructureState:
    st = StructureState()

    price = context.current_price
    vwap = context.vwap

    st.above_vwap = price > vwap if vwap else False
    st.below_vwap = price < vwap if vwap else False

    if len(bars) >= 3:
        c1 = safe_float(bars[-3].get("close"))
        c2 = safe_float(bars[-2].get("close"))
        c3 = safe_float(bars[-1].get("close"))

        h1 = safe_float(bars[-3].get("high"))
        h2 = safe_float(bars[-2].get("high"))
        h3 = safe_float(bars[-1].get("high"))

        l1 = safe_float(bars[-3].get("low"))
        l2 = safe_float(bars[-2].get("low"))
        l3 = safe_float(bars[-1].get("low"))

        st.higher_low = l3 > l2 >= l1
        st.lower_high = h3 < h2 <= h1

        st.vwap_reclaimed = c2 < vwap and c3 > vwap if vwap else False
        st.vwap_rejected = c2 > vwap and c3 < vwap if vwap else False

        avg_vol = avg_volume(bars[:-1], lookback=10)
        last_vol = safe_float(bars[-1].get("volume"))
        st.breakout_with_volume = last_vol > (avg_vol * 1.25 if avg_vol else 0)

    nearest_support = nearest_level(price, context.key_supports)
    nearest_resistance = nearest_level(price, context.key_resistances)
    nearest_print = nearest_level(price, context.big_print_levels)

    st.near_support = distance_pct(price, nearest_support) <= 0.20 if nearest_support else False
    st.near_resistance = distance_pct(price, nearest_resistance) <= 0.20 if nearest_resistance else False
    st.near_big_print = distance_pct(price, nearest_print) <= 0.20 if nearest_print else False

    st.retest_hold = st.above_vwap and st.near_support
    st.rejection_at_level = st.below_vwap and st.near_resistance
    st.failed_bounce = st.lower_high and st.below_vwap

    st.stretched_up = context.rsi >= 70
    st.stretched_down = context.rsi <= 30

    return st


# =========================================================
# DECISION ENGINE
# =========================================================

def build_long_reasoning(context: MarketContext, st: StructureState) -> Tuple[int, List[str], List[str]]:
    score = 0
    reasons = []
    blockers = []

    if st.above_vwap:
        score += 15
        reasons.append("Price is above VWAP.")
    else:
        blockers.append("Price is not above VWAP for long bias.")

    if st.vwap_reclaimed:
        score += 15
        reasons.append("VWAP reclaim confirmed.")
    if st.retest_hold:
        score += 12
        reasons.append("Retest hold near support.")
    if st.higher_low:
        score += 12
        reasons.append("Higher low structure present.")
    if st.breakout_with_volume:
        score += 12
        reasons.append("Breakout candle has volume.")
    if st.near_big_print:
        score += 6
        reasons.append("Price is near an important print/level.")
    if context.macro_bias == "risk_on":
        score += 8
        reasons.append("Macro backdrop is leaning risk-on.")
    if context.oil_trend in ["down", "strong_down"]:
        score += 10
        reasons.append("Oil pressure is easing, supportive for index upside.")
    if st.stretched_up:
        score -= 10
        blockers.append("RSI is stretched up.")
    if context.current_price >= context.premarket_high:
        score += 8
        reasons.append("Price is challenging or above premarket high.")

    return score, reasons, blockers


def build_short_reasoning(context: MarketContext, st: StructureState) -> Tuple[int, List[str], List[str]]:
    score = 0
    reasons = []
    blockers = []

    if st.below_vwap:
        score += 15
        reasons.append("Price is below VWAP.")
    else:
        blockers.append("Price is not below VWAP for short bias.")

    if st.vwap_rejected:
        score += 15
        reasons.append("VWAP rejection confirmed.")
    if st.rejection_at_level:
        score += 12
        reasons.append("Rejection at resistance.")
    if st.failed_bounce:
        score += 12
        reasons.append("Failed bounce / lower high structure.")
    if st.breakout_with_volume:
        score += 8
        reasons.append("Momentum candle has volume.")
    if st.near_big_print:
        score += 6
        reasons.append("Price is near an important print/level.")
    if context.macro_bias == "risk_off":
        score += 8
        reasons.append("Macro backdrop is leaning risk-off.")
    if context.oil_trend in ["up", "strong_up"]:
        score += 10
        reasons.append("Oil pressure is rising, bearish for index upside.")
    if st.stretched_down:
        score -= 10
        blockers.append("RSI is stretched down.")
    if context.current_price <= context.premarket_low:
        score += 8
        reasons.append("Price is challenging or below premarket low.")

    return score, reasons, blockers


def detect_chase(context: MarketContext, st: StructureState, bias: str) -> Tuple[bool, str]:
    price = context.current_price

    if bias == "bullish":
        ref = nearest_level(price, context.key_supports + [context.vwap] + context.big_print_levels)
        d = distance_pct(price, ref) if ref else 0.0
        if d > MAX_CHASE_DISTANCE_PCT and st.stretched_up:
            return True, f"Long setup is extended {d:.2f}% away from support/VWAP."
    elif bias == "bearish":
        ref = nearest_level(price, context.key_resistances + [context.vwap] + context.big_print_levels)
        d = distance_pct(price, ref) if ref else 0.0
        if d > MAX_CHASE_DISTANCE_PCT and st.stretched_down:
            return True, f"Short setup is extended {d:.2f}% away from resistance/VWAP."

    return False, ""


def score_to_grade(score: int) -> str:
    if score >= 85:
        return "A+"
    if score >= 75:
        return "A"
    if score >= 65:
        return "B+"
    if score >= 55:
        return "B"
    return "AVOID"


def build_zones(context: MarketContext, bias: str) -> Tuple[str, str, str]:
    if bias == "bullish":
        entry = f"{nearest_level(context.current_price, context.key_supports + [context.vwap]):.2f} - {context.current_price:.2f}"
        stop = f"Below {nearest_level(context.current_price, context.key_supports):.2f}"
        target = f"{nearest_level(context.current_price, context.key_resistances):.2f} / {context.premarket_high:.2f}"
        return entry, stop, target

    entry = f"{context.current_price:.2f} - {nearest_level(context.current_price, context.key_resistances + [context.vwap]):.2f}"
    stop = f"Above {nearest_level(context.current_price, context.key_resistances):.2f}"
    target = f"{nearest_level(context.current_price, context.key_supports):.2f} / {context.premarket_low:.2f}"
    return entry, stop, target


def make_decision(context: MarketContext, st: StructureState) -> BotDecision:
    long_score, long_reasons, long_blockers = build_long_reasoning(context, st)
    short_score, short_reasons, short_blockers = build_short_reasoning(context, st)

    if long_score >= short_score:
        bias = "bullish"
        score = long_score
        reasons = long_reasons
        blockers = long_blockers
    else:
        bias = "bearish"
        score = short_score
        reasons = short_reasons
        blockers = short_blockers

    chase_blocked, chase_reason = detect_chase(context, st, bias)
    if chase_blocked:
        blockers.append(f"YOU ARE CHASING: {chase_reason}")
        score -= 12

    grade = score_to_grade(score)

    if chase_blocked and grade in ["B+", "B"]:
        grade = "AVOID"

    if score < MIN_SCORE_FOR_ALERT:
        grade = "AVOID"

    if bias == "bullish":
        action = "CALL IDEA" if grade != "AVOID" else "WAIT / NO CALL"
    else:
        action = "PUT IDEA" if grade != "AVOID" else "WAIT / NO PUT"

    entry_zone, stop_zone, target_zone = build_zones(context, bias)
    confidence = max(1, min(99, score))

    premium_message = format_premium_alert(
        context=context,
        bias=bias,
        grade=grade,
        action=action,
        score=score,
        entry_zone=entry_zone,
        stop_zone=stop_zone,
        target_zone=target_zone,
        reasons=reasons,
        blockers=blockers,
    )

    free_message = format_free_alert(
        context=context,
        bias=bias,
        grade=grade,
        action=action,
        reasons=reasons,
    )

    return BotDecision(
        symbol=context.symbol,
        bias=bias,
        grade=grade,
        action=action,
        confidence=confidence,
        score=score,
        entry_zone=entry_zone,
        stop_zone=stop_zone,
        target_zone=target_zone,
        premium_message=premium_message,
        free_message=free_message,
        reasons=reasons,
        blockers=blockers,
        chase_blocked=chase_blocked,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


# =========================================================
# FORMATTERS
# =========================================================

def format_free_alert(context: MarketContext, bias: str, grade: str, action: str, reasons: List[str]) -> str:
    headline = "BULLISH" if bias == "bullish" else "BEARISH"
    top_reasons = reasons[:3] if reasons else ["Monitoring structure and key levels."]

    lines = [
        f"📊 {context.symbol} FREE ALERT",
        f"Bias: {headline}",
        f"Grade: {grade}",
        f"Action: {action}",
        f"Price: {context.current_price:.2f}",
        f"VWAP: {context.vwap:.2f}",
        f"Oil: {context.oil_price:.2f} ({context.oil_day_change_dollars:+.2f})",
        "",
        "Why it matters:",
    ]

    for r in top_reasons:
        lines.append(f"• {r}")

    lines.append("")
    lines.append("UnBiased Trades 313")
    return "\n".join(lines)


def format_premium_alert(
    context: MarketContext,
    bias: str,
    grade: str,
    action: str,
    score: int,
    entry_zone: str,
    stop_zone: str,
    target_zone: str,
    reasons: List[str],
    blockers: List[str],
) -> str:
    headline = "BULLISH" if bias == "bullish" else "BEARISH"

    lines = [
        f"💎 {context.symbol} PREMIUM ALERT",
        f"Bias: {headline}",
        f"Grade: {grade}",
        f"Action: {action}",
        f"Score: {score}",
        f"Price: {context.current_price:.2f}",
        f"VWAP: {context.vwap:.2f}",
        f"RSI: {context.rsi:.1f}",
        f"{SECONDARY_SYMBOL}: {context.secondary_price:.2f} ({context.secondary_day_change_pct:+.2f}%)",
        f"{OIL_SYMBOL}: {context.oil_price:.2f} ({context.oil_day_change_dollars:+.2f} / {context.oil_day_change_pct:+.2f}%)",
        f"Macro Bias: {context.macro_bias}",
        f"Oil Trend: {context.oil_trend}",
        "",
        f"Entry Zone: {entry_zone}",
        f"Stop Zone: {stop_zone}",
        f"Target Zone: {target_zone}",
        "",
        "Reasons:",
    ]

    if reasons:
        for r in reasons:
            lines.append(f"• {r}")
    else:
        lines.append("• No strong reasons currently.")

    if blockers:
        lines.append("")
        lines.append("Blockers / Risks:")
        for b in blockers:
            lines.append(f"• {b}")

    lines.append("")
    lines.append("Levels:")
    lines.append(f"• Supports: {', '.join([f'{x:.2f}' for x in context.key_supports])}")
    lines.append(f"• Resistances: {', '.join([f'{x:.2f}' for x in context.key_resistances])}")
    lines.append(f"• Big Prints: {', '.join([f'{x:.2f}' for x in context.big_print_levels])}")

    lines.append("")
    lines.append("UnBiased Trades 313 | Where information becomes execution.")
    return "\n".join(lines)


# =========================================================
# DISCORD
# =========================================================

def send_to_discord(message: str) -> bool:
    if not ENABLE_DISCORD_ALERTS or not DISCORD_WEBHOOK_URL:
        return False

    try:
        payload = {"content": message[:1900]}
        r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=20)
        ok = 200 <= r.status_code < 300
        if not ok:
            log(f"Discord send failed: {r.status_code} {r.text}")
        return ok
    except Exception as e:
        log(f"Discord error: {e}")
        return False


# =========================================================
# TELEGRAM
# =========================================================

def telegram_api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"


def send_to_telegram(message: str, chat_id: Optional[str] = None) -> bool:
    if not ENABLE_TELEGRAM_ALERTS or not TELEGRAM_BOT_TOKEN:
        return False

    try:
        payload = {
            "chat_id": chat_id or TELEGRAM_CHAT_ID,
            "text": message[:4000],
        }
        r = requests.post(telegram_api_url("sendMessage"), data=payload, timeout=20)
        ok = 200 <= r.status_code < 300
        if not ok:
            log(f"Telegram send failed: {r.status_code} {r.text}")
        return ok
    except Exception as e:
        log(f"Telegram error: {e}")
        return False


def get_telegram_updates() -> List[Dict]:
    global LAST_TELEGRAM_UPDATE_ID

    if not TELEGRAM_BOT_TOKEN:
        return []

    try:
        params = {
            "timeout": 1,
            "offset": LAST_TELEGRAM_UPDATE_ID + 1,
        }
        r = requests.get(telegram_api_url("getUpdates"), params=params, timeout=15)
        data = r.json()

        if not data.get("ok"):
            return []

        updates = data.get("result", [])
        if updates:
            LAST_TELEGRAM_UPDATE_ID = max(u["update_id"] for u in updates)
        return updates
    except Exception as e:
        log(f"Failed to get Telegram updates: {e}")
        return []


def process_telegram_commands() -> None:
    global BOT_ACTIVE

    updates = get_telegram_updates()

    for update in updates:
        message = update.get("message", {})
        text = (message.get("text") or "").strip().lower()
        chat_id = str(message.get("chat", {}).get("id", TELEGRAM_CHAT_ID))

        if not text.startswith("/"):
            continue

        if text == "/start":
            send_to_telegram("✅ Bot connected. Commands: /status /heartbeat /test /kill /resume", chat_id)

        elif text == "/status":
            status_msg = (
                f"🤖 System Status\n"
                f"BOT_ACTIVE: {BOT_ACTIVE}\n"
                f"SYMBOL: {SYMBOL}\n"
                f"SECONDARY_SYMBOL: {SECONDARY_SYMBOL}\n"
                f"OIL_SYMBOL: {OIL_SYMBOL}\n"
                f"POLL_INTERVAL: {POLL_INTERVAL}\n"
                f"HEARTBEAT_INTERVAL: {HEARTBEAT_INTERVAL}"
            )
            send_to_telegram(status_msg, chat_id)

        elif text == "/heartbeat":
            send_heartbeat(force=True, telegram_chat_id=chat_id)

        elif text == "/test":
            send_to_telegram("🧪 Telegram test alert working.", chat_id)
            send_to_discord("🧪 Discord test alert working.")

        elif text == "/kill":
            BOT_ACTIVE = False
            send_to_telegram("🛑 Bot paused. Use /resume to restart alerts.", chat_id)

        elif text == "/resume":
            BOT_ACTIVE = True
            send_to_telegram("✅ Bot resumed.", chat_id)


# =========================================================
# HEARTBEAT
# =========================================================

def send_heartbeat(force: bool = False, telegram_chat_id: Optional[str] = None) -> None:
    global LAST_HEARTBEAT_TS

    now = time.time()
    if not force and (now - LAST_HEARTBEAT_TS < HEARTBEAT_INTERVAL):
        return

    LAST_HEARTBEAT_TS = now

    message = (
        f"💓 HEARTBEAT\n"
        f"System online\n"
        f"BOT_ACTIVE: {BOT_ACTIVE}\n"
        f"Primary: {SYMBOL}\n"
        f"Secondary: {SECONDARY_SYMBOL}\n"
        f"Oil: {OIL_SYMBOL}\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    if ENABLE_DISCORD_ALERTS:
        send_to_discord(message)
    if ENABLE_TELEGRAM_ALERTS:
        send_to_telegram(message, telegram_chat_id)


# =========================================================
# ALERT FILTERS
# =========================================================

def decision_signature(decision: BotDecision) -> str:
    return f"{decision.symbol}|{decision.bias}|{decision.grade}|{decision.action}|{decision.entry_zone}|{decision.target_zone}"


def should_send_alert(decision: BotDecision) -> bool:
    global LAST_ALERT_SIGNATURE

    if decision.grade == "AVOID":
        return False

    sig = decision_signature(decision)
    if sig == LAST_ALERT_SIGNATURE:
        return False

    LAST_ALERT_SIGNATURE = sig
    return True


# =========================================================
# MAIN ANALYSIS PASS
# =========================================================

def run_analysis_cycle() -> None:
    if not BOT_ACTIVE:
        log("Bot paused. Skipping analysis cycle.")
        return

    context = build_market_context()
    if not context:
        log("No context available this cycle.")
        return

    bars = twelve_time_series(SYMBOL, interval="5min", outputsize=30)
    st = detect_structure(context, bars)
    decision = make_decision(context, st)

    log(
        f"Decision | symbol={decision.symbol} bias={decision.bias} "
        f"grade={decision.grade} score={decision.score} action={decision.action}"
    )

    if should_send_alert(decision):
        if ENABLE_DISCORD_ALERTS:
            send_to_discord(decision.premium_message)
        if ENABLE_TELEGRAM_ALERTS:
            send_to_telegram(decision.premium_message)
    else:
        log("No new alert sent.")


# =========================================================
# MAIN LOOP
# =========================================================

def main() -> None:
    log("🚀 SYSTEM STARTING")
    validate_env()

    try:
        context = build_market_context()

        if context:
            bars = twelve_time_series(SYMBOL, interval="5min", outputsize=30)
            st = detect_structure(context, bars)
            decision = make_decision(context, st)

            log(f"Decision: {decision.grade} | {decision.bias} | {decision.action}")

            send_to_discord(decision.premium_message)
            send_to_telegram(decision.premium_message)

        else:
            log("❌ Failed to build market context")

    except Exception as e:
        log(f"Fatal run error: {e}")
        log(traceback.format_exc())

    log("✅ Run complete. Exiting.")

# =========================================================
# ENTRY
# =========================================================

if __name__ == "__main__":
    main()

# =========================================================
# AI TRADING SYSTEM — LIVE DATA VERSION
# =========================================================

import os
import time
import json
import math
import traceback
import requests

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Tuple


# =========================================================
# ENV VARIABLES
# =========================================================

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")

SYMBOL = os.getenv("SYMBOL", "QQQ")
SECONDARY_SYMBOL = os.getenv("SECONDARY_SYMBOL", "SPY")
OIL_SYMBOL = os.getenv("OIL_SYMBOL", "USO")

HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "900"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))

ENABLE_DISCORD_ALERTS = os.getenv("ENABLE_DISCORD_ALERTS", "true").lower() == "true"
ENABLE_TELEGRAM_ALERTS = os.getenv("ENABLE_TELEGRAM_ALERTS", "true").lower() == "true"
ENABLE_HEARTBEAT = os.getenv("ENABLE_HEARTBEAT", "true").lower() == "true"


# =========================================================
# BASIC TEST / LOGGING HELPERS
# =========================================================

def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def validate_env() -> None:
    log("Validating environment variables...")

    if not DISCORD_WEBHOOK_URL:
        log("WARNING: DISCORD_WEBHOOK_URL is missing")

    if not TELEGRAM_BOT_TOKEN:
        log("WARNING: TELEGRAM_BOT_TOKEN is missing")

    if not TELEGRAM_CHAT_ID:
        log("WARNING: TELEGRAM_CHAT_ID is missing")

    if not TWELVE_DATA_API_KEY:
        log("WARNING: TWELVE_DATA_API_KEY is missing")

    log("Environment validation complete.")

# ============================================================
# AI TRADING SYSTEM — LIVE DATA VERSION
# ============================================================

import os
import time
import requests
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Tuple


# ============================================================
# CONFIG
# ============================================================

SYSTEM_CONFIG = {
    "symbols_allowed": ["SPY", "QQQ"],
    "heartbeat_seconds": 1800,
    "loop_sleep_seconds": 60,
    "opening_no_trade_end": (9, 35),
    "morning_end": (11, 0),
    "midday_end": (14, 59),
    "power_hour_end": (16, 15),
    "volume_boost_threshold": 1.15,
    "chase_distance_pct": 0.0035,
    "time_stop_minutes": 10,
    "hard_drawdown_pct": -25.0,
    "request_timeout": 15,
}

TELEGRAM_BOT_TOKEN = os.getenv("8636128819:AAFT9ibrwatP7O6wsTQi7wJVeQcuNqMLv4I")
TELEGRAM_CHAT_ID = os.getenv("8661143355")
TWELVE_DATA_API_KEY = os.getenv("b8760b201df4466b8082bc17c1ab1e9b")


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured.")
        print(message)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:
        requests.post(
            url,
            data=payload,
            timeout=SYSTEM_CONFIG["request_timeout"]
        )
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
    power_hour_start = time_to_minutes(15, 0)
    power_hour_end = time_to_minutes(*SYSTEM_CONFIG["power_hour_end"])

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
# TWELVE DATA HELPERS
# ============================================================

def twelve_get(endpoint: str, params: Dict[str, str]) -> Optional[dict]:
    if not TWELVE_DATA_API_KEY:
        print("TWELVE_DATA_API_KEY not configured.")
        return None

    url = f"https://api.twelvedata.com/{endpoint}"
    payload = dict(params)
    payload["apikey"] = TWELVE_DATA_API_KEY

    try:
        response = requests.get(
            url,
            params=payload,
            timeout=SYSTEM_CONFIG["request_timeout"]
        )
        data = response.json()

        if isinstance(data, dict) and data.get("status") == "error":
            print(f"Twelve Data API error on {endpoint}: {data}")
            return None

        return data
    except Exception as e:
        print(f"Twelve Data request failed ({endpoint}): {e}")
        return None


def fetch_price(symbol: str) -> Optional[float]:
    data = twelve_get("price", {"symbol": symbol})
    if not data or "price" not in data:
        return None
    try:
        return float(data["price"])
    except Exception:
        return None


def fetch_quote(symbol: str) -> Optional[dict]:
    return twelve_get("quote", {"symbol": symbol})


def fetch_rsi(symbol: str, interval: str = "5min") -> float:
    data = twelve_get("rsi", {"symbol": symbol, "interval": interval, "outputsize": "1"})
    if not data or "values" not in data or not data["values"]:
        return 50.0
    try:
        return float(data["values"][0]["rsi"])
    except Exception:
        return 50.0


def fetch_vwap(symbol: str, interval: str = "1min") -> Optional[float]:
    data = twelve_get("vwap", {"symbol": symbol, "interval": interval, "outputsize": "1"})
    if not data or "values" not in data or not data["values"]:
        return None
    try:
        return float(data["values"][0]["vwap"])
    except Exception:
        return None


def fetch_intraday_series(symbol: str, interval: str = "5min", outputsize: int = 30) -> List[dict]:
    data = twelve_get(
        "time_series",
        {
            "symbol": symbol,
            "interval": interval,
            "outputsize": str(outputsize),
            "format": "JSON"
        }
    )
    if not data or "values" not in data:
        return []
    return data["values"]


def fetch_oil_price() -> Optional[float]:
    # Crude oil futures symbol commonly used by Twelve Data
    return fetch_price("CL=F")


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
# LIVE DATA BUILDERS
# ============================================================

LAST_OIL_PRICE: Optional[float] = None


def derive_high_low_context_from_series(series: List[dict]) -> Dict[str, float]:
    if not series:
        return {
            "prior_day_high": 0.0,
            "prior_day_low": 0.0,
            "premarket_high": 0.0,
            "premarket_low": 0.0,
        }

    highs = []
    lows = []

    for row in series:
        try:
            highs.append(float(row["high"]))
            lows.append(float(row["low"]))
        except Exception:
            continue

    if not highs or not lows:
        return {
            "prior_day_high": 0.0,
            "prior_day_low": 0.0,
            "premarket_high": 0.0,
            "premarket_low": 0.0,
        }

    day_high = max(highs)
    day_low = min(lows)

    recent_slice = series[:8] if len(series) >= 8 else series
    recent_highs = []
    recent_lows = []

    for row in recent_slice:
        try:
            recent_highs.append(float(row["high"]))
            recent_lows.append(float(row["low"]))
        except Exception:
            continue

    return {
        "prior_day_high": day_high,
        "prior_day_low": day_low,
        "premarket_high": max(recent_highs) if recent_highs else day_high,
        "premarket_low": min(recent_lows) if recent_lows else day_low,
    }


def infer_volume_stats_from_quote(quote: Optional[dict]) -> Tuple[float, float]:
    if not quote:
        return 0.0, 0.0

    current_volume = 0.0
    average_volume = 0.0

    try:
        current_volume = float(quote.get("volume", 0.0) or 0.0)
    except Exception:
        current_volume = 0.0

    try:
        average_volume = float(quote.get("average_volume", 0.0) or 0.0)
    except Exception:
        average_volume = 0.0

    return current_volume, average_volume


def infer_supports_and_resistances(price: float, day_high: float, day_low: float) -> Tuple[List[float], List[float]]:
    supports = [day_low]
    resistances = [day_high]

    midpoint = (day_high + day_low) / 2 if day_high > 0 and day_low > 0 else 0.0
    if midpoint > 0:
        if midpoint < price:
            supports.append(midpoint)
        else:
            resistances.append(midpoint)

    supports = clean_levels([x for x in supports if x < price or abs(x - price) < 0.01])
    resistances = clean_levels([x for x in resistances if x > price or abs(x - price) < 0.01])
    return supports, resistances


def build_live_raw_market_data(symbol: str) -> Optional[RawMarketData]:
    global LAST_OIL_PRICE

    quote = fetch_quote(symbol)
    price = fetch_price(symbol)
    vwap = fetch_vwap(symbol)
    rsi = fetch_rsi(symbol)
    series = fetch_intraday_series(symbol, interval="5min", outputsize=30)
    oil_price = fetch_oil_price()

    if price is None or vwap is None:
        print(f"Missing live data for {symbol}.")
        return None

    current_volume, average_volume = infer_volume_stats_from_quote(quote)
    hl_context = derive_high_low_context_from_series(series)

    oil_change = 0.0
    oil_trend = "neutral"

    if oil_price is not None and LAST_OIL_PRICE is not None:
        oil_change = oil_price - LAST_OIL_PRICE
        if oil_change > 0.20:
            oil_trend = "rising"
        elif oil_change < -0.20:
            oil_trend = "falling"
        else:
            oil_trend = "stabilizing"
    elif oil_price is not None:
        oil_trend = "stabilizing"

    if oil_price is not None:
        LAST_OIL_PRICE = oil_price

    supports, resistances = infer_supports_and_resistances(
        price=price,
        day_high=hl_context["prior_day_high"],
        day_low=hl_context["prior_day_low"]
    )

    big_print_levels: List[float] = []
    if vwap:
        big_print_levels = clean_levels([vwap])

    return RawMarketData(
        symbol=symbol,
        price=price,
        vwap=vwap,
        volume=current_volume,
        avg_volume=average_volume,
        rsi=rsi,
        timestamp=now_local(),
        oil_price=oil_price or 0.0,
        oil_change=oil_change,
        oil_trend=oil_trend,
        macro_bias="neutral",
        prior_day_high=hl_context["prior_day_high"],
        prior_day_low=hl_context["prior_day_low"],
        premarket_high=hl_context["premarket_high"],
        premarket_low=hl_context["premarket_low"],
        key_supports=supports,
        key_resistances=resistances,
        big_print_levels=big_print_levels
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
        below = [x for x in ctx.key_supports if x < ctx.current_price]
        if below:
            return f"Below support {max(below):.2f}"
        return f"Below VWAP {ctx.vwap:.2f}"

    if action == "PUT":
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

    if ctx.distance_to_resistance_pct and ctx.distance_to_resistance_pct < 0.002 and st.above_vwap:
        score_call -= 1
        warnings.append("Long is close to resistance.")
    if ctx.distance_to_support_pct and ctx.distance_to_support_pct < 0.002 and st.below_vwap:
        score_put -= 1
        warnings.append("Short is close to support.")

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
# MAIN AI LOOP
# ============================================================

def run_symbol(symbol: str) -> None:
    raw = build_live_raw_market_data(symbol)
    if raw is None:
        print(f"Could not build live raw data for {symbol}.")
        return

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


def run() -> None:
    send_telegram("✅ AI TRADING SYSTEM ONLINE")

    last_heartbeat = time.time()

    
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

# =========================
# LIVE DATA ENGINE
# =========================

TWELVE_API_KEY = os.getenv("TWELVE_DATA_API_KEY")


def fetch_price(symbol):
    try:
        url = f"https://api.twelvedata.com/price?symbol={symbol}&apikey={TWELVE_API_KEY}"
        r = requests.get(url).json()
        return float(r["price"])
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return None


def fetch_vwap(symbol):
    try:
        url = f"https://api.twelvedata.com/vwap?symbol={symbol}&interval=1min&apikey={TWELVE_API_KEY}"
        r = requests.get(url).json()
        return float(r["values"][0]["vwap"])
    except Exception as e:
        print(f"VWAP error {symbol}: {e}")
        return None


def fetch_rsi(symbol):
    try:
        url = f"https://api.twelvedata.com/rsi?symbol={symbol}&interval=5min&apikey={TWELVE_API_KEY}"
        r = requests.get(url).json()
        return float(r["values"][0]["rsi"])
    except Exception as e:
        print(f"RSI error {symbol}: {e}")
        return 50


def fetch_oil_price():
    try:
        url = f"https://api.twelvedata.com/price?symbol=CL=F&apikey={TWELVE_API_KEY}"
        r = requests.get(url).json()
        return float(r["price"])
    except:
        return None

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
  if __name__ == "__main__":
    log("🚀 SYSTEM STARTING")
    validate_env()

    context = build_market_context()

    if context:
        bars = twelve_time_series(SYMBOL, interval="5min", outputsize=30)
        st = detect_structure(context, bars)
        decision = make_decision(context, st)

        log(f"Decision: {decision.grade} | {decision.bias} | {decision.action}")

        send_to_discord(decision.premium_message)
        send_to_telegram(decision.premium_message)
    else:
        log("❌ Failed to build market context")

    log("✅ Run complete. Exiting.")

if __name__ == "__main__":
    main()

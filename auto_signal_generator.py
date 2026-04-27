# =========================================================
# UnBiased Trades — REAL QQQ STRATEGY SIGNAL GENERATOR
# QQQ ONLY | VWAP + LEVELS + OIL + NO CHASING
# Writes: ai_signal.json
# =========================================================

import os
import json
import time
from datetime import datetime, timezone

SIGNAL_FILE = os.getenv("SIGNAL_FILE", "ai_signal.json").strip()
MARKET_FILE = os.getenv("MARKET_DATA_FILE", "market_prices.json").strip()
STATE_FILE = "auto_signal_generator_state.json"
MACRO_FILE = os.getenv("MACRO_FILE", "macro_snapshot.json").strip()
LEVELS_FILE = os.getenv("LEVELS_FILE", "darkpool_levels.json").strip()

ENABLE_AUTO_SIGNAL_GENERATOR = os.getenv("ENABLE_AUTO_SIGNAL_GENERATOR", "true").lower() == "true"
AUTO_SIGNAL_COOLDOWN_SECONDS = int(os.getenv("AUTO_SIGNAL_COOLDOWN_SECONDS", "300"))

TICKER = "QQQ"

MIN_PRICE = float(os.getenv("AUTO_QQQ_MIN_PRICE", "100"))
VWAP_BUFFER = float(os.getenv("AUTO_VWAP_BUFFER", "0.15"))
LEVEL_BUFFER = float(os.getenv("AUTO_LEVEL_BUFFER", "0.75"))
CHASE_DISTANCE = float(os.getenv("AUTO_CHASE_DISTANCE", "1.25"))

DEFAULT_STOP_DISTANCE = float(os.getenv("AUTO_STOP_DISTANCE", "1.50"))
DEFAULT_TARGET_1 = float(os.getenv("AUTO_TARGET_1", "1.50"))
DEFAULT_TARGET_2 = float(os.getenv("AUTO_TARGET_2", "3.00"))

ALLOW_CALLS = os.getenv("AUTO_ALLOW_CALLS", "true").lower() == "true"
ALLOW_PUTS = os.getenv("AUTO_ALLOW_PUTS", "true").lower() == "true"


def load_json(path, default):
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def now_ts():
    return int(time.time())


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def safe_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def cooldown_ready(force=False):
    if force:
        return True

    state = load_json(STATE_FILE, {})
    last_signal_ts = int(state.get("last_signal_ts", 0) or 0)

    if last_signal_ts <= 0:
        return True

    return now_ts() - last_signal_ts >= AUTO_SIGNAL_COOLDOWN_SECONDS


def get_market_item(ticker="QQQ"):
    data = load_json(MARKET_FILE, {})
    item = data.get(ticker)

    if isinstance(item, dict):
        return item

    return {}


def get_price():
    item = get_market_item("QQQ")

    price = safe_float(
        item.get("price")
        or item.get("last")
        or item.get("close")
        or item.get("mark")
    )

    if price and price > MIN_PRICE:
        return price

    data = load_json(MARKET_FILE, {})
    price = safe_float(data.get("price"))
    if price and price > MIN_PRICE:
        return price

    return None


def get_vwap():
    item = get_market_item("QQQ")
    return safe_float(
        item.get("vwap")
        or item.get("VWAP")
        or item.get("session_vwap")
    )


def get_volume_state():
    item = get_market_item("QQQ")
    volume = safe_float(item.get("volume"), 0)
    avg_volume = safe_float(item.get("avg_volume") or item.get("average_volume"), 0)

    if volume and avg_volume and volume >= avg_volume * 1.2:
        return "strong"

    if volume:
        return "normal"

    return "unknown"


def get_level_context(price):
    levels_data = load_json(LEVELS_FILE, {})
    levels = []

    if isinstance(levels_data, dict):
        raw = (
            levels_data.get("QQQ")
            or levels_data.get("levels")
            or levels_data.get("darkpool_levels")
            or []
        )
    elif isinstance(levels_data, list):
        raw = levels_data
    else:
        raw = []

    if isinstance(raw, dict):
        raw = list(raw.values())

    for x in raw:
        if isinstance(x, dict):
            level = safe_float(
                x.get("price")
                or x.get("level")
                or x.get("strike")
                or x.get("value")
            )
        else:
            level = safe_float(x)

        if level and level > MIN_PRICE:
            levels.append(level)

    if not levels:
        return {
            "nearest_level": None,
            "above_level": None,
            "below_level": None,
            "distance": None,
            "level_state": "no_levels_loaded",
        }

    nearest = min(levels, key=lambda lvl: abs(lvl - price))
    below = max([lvl for lvl in levels if lvl <= price], default=None)
    above = min([lvl for lvl in levels if lvl >= price], default=None)

    distance = abs(price - nearest)

    if distance <= LEVEL_BUFFER:
        state = "at_key_level"
    elif below and price > below:
        state = "above_support"
    elif above and price < above:
        state = "below_resistance"
    else:
        state = "neutral"

    return {
        "nearest_level": nearest,
        "above_level": above,
        "below_level": below,
        "distance": round(distance, 2),
        "level_state": state,
    }


def get_oil_bias():
    macro = load_json(MACRO_FILE, {})

    oil = macro.get("oil", {}) if isinstance(macro, dict) else {}
    oil_state = str(
        oil.get("trend")
        or oil.get("direction")
        or oil.get("state")
        or macro.get("oil_trend", "")
    ).lower()

    macro_bias = str(macro.get("macro_bias", "")).lower()
    risk_env = str(macro.get("risk_environment", "")).lower()

    if "fall" in oil_state or oil_state in {"down", "bearish", "weak"}:
        return "bullish_for_qqq"

    if "rise" in oil_state or oil_state in {"up", "bullish", "strong"}:
        return "bearish_for_qqq"

    if macro_bias == "bullish" or risk_env == "risk_on":
        return "bullish_for_qqq"

    if macro_bias == "bearish" or risk_env == "risk_off":
        return "bearish_for_qqq"

    return "neutral"


def is_chasing(price, vwap, direction):
    if not vwap:
        return False, "no_vwap_chase_check"

    distance = abs(price - vwap)

    if direction == "CALL" and price > vwap and distance > CHASE_DISTANCE:
        return True, f"call_chasing_price_{round(distance, 2)}_above_vwap"

    if direction == "PUT" and price < vwap and distance > CHASE_DISTANCE:
        return True, f"put_chasing_price_{round(distance, 2)}_below_vwap"

    return False, "not_chasing"


def score_strategy(price, vwap, level_ctx, oil_bias):
    if not vwap:
        return None

    volume_state = get_volume_state()
    level_state = level_ctx.get("level_state")

    call_score = 0
    put_score = 0
    call_reasons = []
    put_reasons = []

    if price > vwap + VWAP_BUFFER:
        call_score += 2
        call_reasons.append("price_above_vwap")
    elif price < vwap - VWAP_BUFFER:
        put_score += 2
        put_reasons.append("price_below_vwap")

    if level_state in {"above_support", "at_key_level"}:
        call_score += 1
        call_reasons.append(level_state)

    if level_state in {"below_resistance", "at_key_level"}:
        put_score += 1
        put_reasons.append(level_state)

    if oil_bias == "bullish_for_qqq":
        call_score += 2
        call_reasons.append("oil_macro_bullish_for_qqq")
    elif oil_bias == "bearish_for_qqq":
        put_score += 2
        put_reasons.append("oil_macro_bearish_for_qqq")
    else:
        call_reasons.append("oil_macro_neutral")
        put_reasons.append("oil_macro_neutral")

    if volume_state == "strong":
        call_score += 1
        put_score += 1

    if call_score >= put_score and call_score >= 3 and ALLOW_CALLS:
        chasing, chase_reason = is_chasing(price, vwap, "CALL")
        if chasing:
            return None

        return {
            "direction": "CALL",
            "score": call_score,
            "grade": "A" if call_score >= 5 else "B",
            "reasons": call_reasons + [chase_reason],
            "setup": "VWAP_RECLAIM_LEVEL_HOLD_OIL_CONFIRMATION",
        }

    if put_score > call_score and put_score >= 3 and ALLOW_PUTS:
        chasing, chase_reason = is_chasing(price, vwap, "PUT")
        if chasing:
            return None

        return {
            "direction": "PUT",
            "score": put_score,
            "grade": "A" if put_score >= 5 else "B",
            "reasons": put_reasons + [chase_reason],
            "setup": "VWAP_REJECT_LEVEL_FAIL_OIL_CONFIRMATION",
        }

    return None


def build_signal(price, vwap, decision, level_ctx, oil_bias):
    direction = decision["direction"]
    grade = decision["grade"]

    if direction == "CALL":
        stop = round(price - DEFAULT_STOP_DISTANCE, 2)
        targets = [
            round(price + DEFAULT_TARGET_1, 2),
            round(price + DEFAULT_TARGET_2, 2),
        ]
    else:
        stop = round(price + DEFAULT_STOP_DISTANCE, 2)
        targets = [
            round(price - DEFAULT_TARGET_1, 2),
            round(price - DEFAULT_TARGET_2, 2),
        ]

    return {
        "ticker": "QQQ",
        "symbol": "QQQ",
        "underlying": "QQQ",

        "direction": direction,
        "side": direction,

        "entry": round(price, 2),
        "entry_price": round(price, 2),
        "stop": stop,
        "stop_loss": stop,
        "targets": targets,
        "target": targets[0],

        "confidence": grade,
        "grade": grade,
        "score": decision["score"],

        "setup": decision["setup"],
        "setup_type": "real_qqq_strategy_generator",
        "trigger": "vwap_levels_oil_strategy",

        "vwap": round(vwap, 2) if vwap else None,
        "level_context": level_ctx,
        "oil_bias": oil_bias,
        "strategy_reasons": decision["reasons"],

        "session": "auto",
        "time_window": "strategy_signal",
        "trade_reason": "QQQ signal generated from VWAP + key levels + oil/macro confirmation + no-chasing filter.",

        "timestamp": now_ts(),
        "created_at": now_iso(),
        "source": "auto_signal_generator",

        "force_execution": True,
        "paper_only": True,
    }


def generate_signal(force=False):
    print("[AUTO SIGNAL DEBUG] REAL QQQ STRATEGY loaded | VWAP + LEVELS + OIL", flush=True)

    if not ENABLE_AUTO_SIGNAL_GENERATOR:
        print("[AUTO SIGNAL] disabled", flush=True)
        return None

    if not cooldown_ready(force=force):
        print("[AUTO SIGNAL] cooldown active", flush=True)
        return None

    price = get_price()
    if price is None:
        print("[AUTO SIGNAL] skipped: no valid QQQ price", flush=True)
        return None

    vwap = get_vwap()
    if not vwap:
        print("[AUTO SIGNAL] skipped: no VWAP loaded yet", flush=True)
        return None

    level_ctx = get_level_context(price)
    oil_bias = get_oil_bias()

    decision = score_strategy(price, vwap, level_ctx, oil_bias)

    if not decision:
        print(
            f"[AUTO SIGNAL] no trade | price={round(price,2)} vwap={round(vwap,2)} "
            f"level={level_ctx.get('level_state')} oil={oil_bias}",
            flush=True,
        )
        return None

    signal = build_signal(price, vwap, decision, level_ctx, oil_bias)
    save_json(SIGNAL_FILE, signal)

    save_json(STATE_FILE, {
        "last_signal_ts": now_ts(),
        "last_ticker": "QQQ",
        "last_direction": signal["direction"],
        "last_entry": signal["entry"],
        "last_grade": signal["grade"],
        "last_score": signal["score"],
        "last_setup": signal["setup"],
        "last_signal_file": SIGNAL_FILE,
    })

    print(
        f"[AUTO SIGNAL] Generated QQQ {signal['direction']} "
        f"grade={signal['grade']} score={signal['score']} "
        f"entry={signal['entry']} stop={signal['stop']} targets={signal['targets']}",
        flush=True,
    )

    return signal


if __name__ == "__main__":
    result = generate_signal(force=True)
    if result:
        print(json.dumps(result, indent=2))
    else:
        print("No signal generated")

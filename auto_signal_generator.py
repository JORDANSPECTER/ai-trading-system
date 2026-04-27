# =========================================================
# UnBiased Trades — REAL QQQ STRATEGY GENERATOR
# VWAP + LEVELS + OIL + SESSION FILTER + NO CHASING
# =========================================================

import os, json, time
from datetime import datetime, timezone

SIGNAL_FILE = os.getenv("SIGNAL_FILE", "ai_signal.json")
MARKET_FILE = os.getenv("MARKET_DATA_FILE", "market_prices.json")
MACRO_FILE = os.getenv("MACRO_FILE", "macro_snapshot.json")
LEVELS_FILE = os.getenv("LEVELS_FILE", "darkpool_levels.json")
STATE_FILE = "auto_signal_generator_state.json"

ENABLE_AUTO_SIGNAL_GENERATOR = os.getenv("ENABLE_AUTO_SIGNAL_GENERATOR", "true").lower() == "true"
AUTO_SIGNAL_COOLDOWN_SECONDS = int(os.getenv("AUTO_SIGNAL_COOLDOWN_SECONDS", "60"))

TICKER = "QQQ"

VWAP_BUFFER = float(os.getenv("AUTO_VWAP_BUFFER", "0.15"))
LEVEL_BUFFER = float(os.getenv("AUTO_LEVEL_BUFFER", "0.75"))
CHASE_DISTANCE = float(os.getenv("AUTO_CHASE_DISTANCE", "1.25"))

STOP_DISTANCE = float(os.getenv("AUTO_STOP_DISTANCE", "1.50"))
TARGET_1 = float(os.getenv("AUTO_TARGET_1", "1.50"))
TARGET_2 = float(os.getenv("AUTO_TARGET_2", "3.00"))

MIN_SCORE_TO_SIGNAL = int(os.getenv("AUTO_MIN_SCORE_TO_SIGNAL", "4"))


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


def safe_float(x, default=None):
    try:
        return float(x)
    except Exception:
        return default


def get_market():
    data = load_json(MARKET_FILE, {})
    return data.get("QQQ", {}) if isinstance(data, dict) else {}


def get_price():
    q = get_market()
    price = safe_float(q.get("price") or q.get("last") or q.get("close"))
    return price if price and price > 100 else None


def get_vwap():
    q = get_market()
    return safe_float(q.get("vwap") or q.get("session_vwap"))


def get_volume_state():
    q = get_market()
    vol = safe_float(q.get("volume"), 0)
    last_vol = safe_float(q.get("last_candle_volume"), 0)

    if last_vol and vol and last_vol > 0:
        return "active"

    return "unknown"


def get_levels(price):
    data = load_json(LEVELS_FILE, {})
    raw = []

    if isinstance(data, dict):
        raw = data.get("QQQ") or data.get("levels") or data.get("darkpool_levels") or []
    elif isinstance(data, list):
        raw = data

    if isinstance(raw, dict):
        raw = list(raw.values())

    levels = []
    for x in raw:
        if isinstance(x, dict):
            lvl = safe_float(x.get("price") or x.get("level") or x.get("value"))
        else:
            lvl = safe_float(x)

        if lvl and lvl > 100:
            levels.append(lvl)

    if not levels:
        return {
            "nearest": None,
            "support": None,
            "resistance": None,
            "state": "no_levels_loaded"
        }

    support = max([x for x in levels if x <= price], default=None)
    resistance = min([x for x in levels if x >= price], default=None)
    nearest = min(levels, key=lambda x: abs(x - price))

    return {
        "nearest": nearest,
        "support": support,
        "resistance": resistance,
        "state": "levels_loaded"
    }


def get_oil_bias():
    macro = load_json(MACRO_FILE, {})
    oil = macro.get("oil", {}) if isinstance(macro, dict) else {}

    text = str(
        oil.get("trend")
        or oil.get("direction")
        or oil.get("state")
        or macro.get("oil_trend", "")
    ).lower()

    risk = str(macro.get("risk_environment", "")).lower()
    bias = str(macro.get("macro_bias", "")).lower()

    if "fall" in text or text in {"down", "weak", "bearish"}:
        return "bullish_for_qqq"

    if "rise" in text or text in {"up", "strong", "bullish"}:
        return "bearish_for_qqq"

    if risk == "risk_on" or bias == "bullish":
        return "bullish_for_qqq"

    if risk == "risk_off" or bias == "bearish":
        return "bearish_for_qqq"

    return "neutral"


def session_name():
    now = datetime.now()
    hhmm = now.strftime("%H:%M")

    if "09:30" <= hhmm <= "10:30":
        return "open"
    if "15:00" <= hhmm <= "16:00":
        return "power_hour"
    if "10:31" <= hhmm <= "14:59":
        return "midday"

    return "off_hours"


def cooldown_ready():
    state = load_json(STATE_FILE, {})
    last = int(state.get("last_signal_ts", 0) or 0)
    return last <= 0 or now_ts() - last >= AUTO_SIGNAL_COOLDOWN_SECONDS


def chasing(price, vwap, direction):
    dist = abs(price - vwap)

    if direction == "CALL" and price > vwap and dist > CHASE_DISTANCE:
        return True

    if direction == "PUT" and price < vwap and dist > CHASE_DISTANCE:
        return True

    return False


def score_trade(price, vwap, levels, oil_bias):
    score_call = 0
    score_put = 0
    call_reasons = []
    put_reasons = []

    support = levels.get("support")
    resistance = levels.get("resistance")

    if price > vwap + VWAP_BUFFER:
        score_call += 2
        call_reasons.append("VWAP reclaim / holding above VWAP")

    if price < vwap - VWAP_BUFFER:
        score_put += 2
        put_reasons.append("VWAP rejection / holding below VWAP")

    if support and abs(price - support) <= LEVEL_BUFFER:
        score_call += 2
        call_reasons.append(f"holding support level {support}")

    if resistance and abs(price - resistance) <= LEVEL_BUFFER:
        score_put += 2
        put_reasons.append(f"rejecting resistance level {resistance}")

    if oil_bias == "bullish_for_qqq":
        score_call += 2
        call_reasons.append("oil/macro bullish for QQQ")

    if oil_bias == "bearish_for_qqq":
        score_put += 2
        put_reasons.append("oil/macro bearish for QQQ")

    sess = session_name()
    if sess in {"open", "power_hour"}:
        score_call += 1
        score_put += 1

    if score_call >= score_put:
        direction = "CALL"
        score = score_call
        reasons = call_reasons
        setup = "VWAP_RECLAIM_LEVEL_HOLD_OIL_CONFIRMATION"
    else:
        direction = "PUT"
        score = score_put
        reasons = put_reasons
        setup = "VWAP_REJECT_LEVEL_FAIL_OIL_CONFIRMATION"

    if score < MIN_SCORE_TO_SIGNAL:
        return None

    if chasing(price, vwap, direction):
        print(f"[AUTO SIGNAL] blocked: YOU ARE CHASING {direction}", flush=True)
        return None

    return {
        "direction": direction,
        "score": score,
        "grade": "A+" if score >= 6 else "A",
        "setup": setup,
        "reasons": reasons,
    }


def build_signal(price, vwap, decision, levels, oil_bias):
    direction = decision["direction"]

    if direction == "CALL":
        stop = round(price - STOP_DISTANCE, 2)
        targets = [round(price + TARGET_1, 2), round(price + TARGET_2, 2)]
    else:
        stop = round(price + STOP_DISTANCE, 2)
        targets = [round(price - TARGET_1, 2), round(price - TARGET_2, 2)]

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

        "confidence": decision["grade"],
        "grade": decision["grade"],
        "score": decision["score"],

        "setup": decision["setup"],
        "setup_type": "real_qqq_vwap_levels_oil",
        "trigger": "vwap_levels_oil_confirmation",

        "vwap": round(vwap, 2),
        "oil_bias": oil_bias,
        "level_context": levels,
        "strategy_reasons": decision["reasons"],

        "session": session_name(),
        "time_window": session_name(),
        "trade_reason": "QQQ setup generated from VWAP + key levels + oil/macro confirmation with anti-chasing filter.",

        "timestamp": now_ts(),
        "created_at": now_iso(),
        "source": "auto_signal_generator",

        "force_execution": True,
        "paper_only": True
    }


def generate_signal(force=False):
    print("[AUTO SIGNAL DEBUG] REAL QQQ STRATEGY | VWAP + LEVELS + OIL loaded", flush=True)

    if not ENABLE_AUTO_SIGNAL_GENERATOR:
        return None

    if not force and not cooldown_ready():
        print("[AUTO SIGNAL] cooldown active", flush=True)
        return None

    price = get_price()
    vwap = get_vwap()

    if not price:
        print("[AUTO SIGNAL] skipped: no QQQ price", flush=True)
        return None

    if not vwap:
        print("[AUTO SIGNAL] skipped: no VWAP", flush=True)
        return None

    levels = get_levels(price)
    oil_bias = get_oil_bias()

    decision = score_trade(price, vwap, levels, oil_bias)

    if not decision:
        print(
            f"[AUTO SIGNAL] no trade | price={round(price,2)} vwap={round(vwap,2)} "
            f"levels={levels.get('state')} oil={oil_bias}",
            flush=True,
        )
        return None

    signal = build_signal(price, vwap, decision, levels, oil_bias)
    save_json(SIGNAL_FILE, signal)

    save_json(STATE_FILE, {
        "last_signal_ts": now_ts(),
        "last_ticker": "QQQ",
        "last_direction": signal["direction"],
        "last_entry": signal["entry"],
        "last_grade": signal["grade"],
        "last_score": signal["score"],
        "last_setup": signal["setup"],
    })

    print(
        f"[AUTO SIGNAL] Generated QQQ {signal['direction']} "
        f"grade={signal['grade']} score={signal['score']} "
        f"entry={signal['entry']} vwap={signal['vwap']}",
        flush=True,
    )

    return signal


if __name__ == "__main__":
    sig = generate_signal(force=True)
    if sig:
        print(json.dumps(sig, indent=2))
    else:
        print("No signal generated")

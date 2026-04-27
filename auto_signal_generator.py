# =========================================================
# UnBiased Trades — QQQ ONLY AUTO SIGNAL GENERATOR
# OPEN SESSION LOCK: 9:30–10:30 AM ET
# FIXED PATH + UNIQUE SIGNAL ID + SMART SCORE BOOST
# HARD LOCK: QQQ only, no SPY
# =========================================================

import os
import json
import time
from datetime import datetime, timezone

try:
    import pytz
except Exception:
    pytz = None


SIGNAL_FILE = "/opt/render/project/src/ai_signal.json"
MARKET_FILE = "/opt/render/project/src/market_prices.json"
STATE_FILE = "/opt/render/project/src/auto_signal_generator_state.json"

TICKER = "QQQ"

ENABLE_AUTO_SIGNAL_GENERATOR = os.getenv("ENABLE_AUTO_SIGNAL_GENERATOR", "true").lower() == "true"
AUTO_SIGNAL_COOLDOWN_SECONDS = int(os.getenv("AUTO_SIGNAL_COOLDOWN_SECONDS", "60"))

AUTO_REQUIRE_OPEN_SESSION = os.getenv("AUTO_REQUIRE_OPEN_SESSION", "true").lower() == "true"

STOP_DISTANCE = float(os.getenv("AUTO_STOP_DISTANCE", "1.50"))
TARGET_1 = float(os.getenv("AUTO_TARGET_1", "1.50"))
TARGET_2 = float(os.getenv("AUTO_TARGET_2", "3.00"))


def now_ts():
    return int(time.time())


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def eastern_now():
    if pytz:
        eastern = pytz.timezone("US/Eastern")
        return datetime.now(eastern)
    return datetime.now()


def is_open_session():
    now = eastern_now()
    start = now.replace(hour=9, minute=30, second=0, microsecond=0)
    end = now.replace(hour=10, minute=30, second=0, microsecond=0)
    return start <= now <= end


def load_json(path, default=None):
    if default is None:
        default = {}
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
    last = int(state.get("last_signal_ts", 0) or 0)

    if last <= 0:
        return True

    return now_ts() - last >= AUTO_SIGNAL_COOLDOWN_SECONDS


def get_market_data():
    data = load_json(MARKET_FILE, {})
    qqq = data.get("QQQ", {})
    return qqq if isinstance(qqq, dict) else {}


def get_price():
    q = get_market_data()
    price = safe_float(q.get("price") or q.get("last") or q.get("close"))
    return price if price and price > 100 else None


def get_vwap(price):
    q = get_market_data()
    vwap = safe_float(q.get("vwap") or q.get("session_vwap") or q.get("close"))
    return vwap if vwap and vwap > 100 else price


def get_premarket_levels(price):
    q = get_market_data()

    pm_high = safe_float(
        q.get("premarket_high")
        or q.get("pm_high")
        or q.get("pre_market_high")
    )

    pm_low = safe_float(
        q.get("premarket_low")
        or q.get("pm_low")
        or q.get("pre_market_low")
    )

    if not pm_high:
        pm_high = round(price + 1.50, 2)

    if not pm_low:
        pm_low = round(price - 1.50, 2)

    return pm_high, pm_low


def decide_direction(price, vwap, pm_high, pm_low):
    if price > pm_high:
        return "CALL", "BREAK_AND_HOLD_PREMARKET_HIGH", "A"

    if price < pm_low:
        return "PUT", "BREAK_AND_HOLD_PREMARKET_LOW", "A"

    if price > vwap:
        return "CALL", "VWAP_TREND_CONTINUATION", "B+"

    if price < vwap:
        return "PUT", "VWAP_TREND_CONTINUATION", "B+"

    return None, None, None


def calculate_score(price, vwap, pm_high, pm_low, direction, grade):
    base_score = 60

    if grade == "A":
        base_score += 10

    if direction == "CALL" and price > vwap:
        base_score += 5

    if direction == "PUT" and price < vwap:
        base_score += 5

    if price > pm_high:
        base_score += 10

    if price < pm_low:
        base_score += 10

    if is_open_session():
        base_score += 5

    return min(base_score, 90)


def build_signal(price, vwap, pm_high, pm_low, direction, setup, grade):
    if direction == "CALL":
        stop = round(price - STOP_DISTANCE, 2)
        targets = [round(price + TARGET_1, 2), round(price + TARGET_2, 2)]
    else:
        stop = round(price + STOP_DISTANCE, 2)
        targets = [round(price - TARGET_1, 2), round(price - TARGET_2, 2)]

    score = calculate_score(price, vwap, pm_high, pm_low, direction, grade)
    unique_id = f"QQQ-{direction}-{setup}-{now_ts()}-{time.time()}"

    return {
        "signal_id": unique_id,
        "id": unique_id,
        "nonce": time.time(),

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
        "score": score,
        "execution_score": score,

        "setup": setup,
        "setup_type": "qqq_open_session_vwap_premarket_generator",
        "trigger": setup,

        "vwap": round(vwap, 2),
        "premarket_high": pm_high,
        "premarket_low": pm_low,
        "pm_high": pm_high,
        "pm_low": pm_low,

        "session": "open" if is_open_session() else "off_hours",
        "time_window": "open" if is_open_session() else "off_hours",
        "trade_reason": "QQQ-only open-session signal generated from premarket levels and VWAP trend continuation.",

        "execution_override": True,
        "force_execution": True,
        "paper_only": True,

        "timestamp": now_ts(),
        "created_at": now_iso(),
        "source": "auto_signal_generator",
    }


def generate_signal(force=False):
    print("[AUTO SIGNAL DEBUG] QQQ ONLY generator loaded | open session lock enabled", flush=True)

    if not ENABLE_AUTO_SIGNAL_GENERATOR:
        print("[AUTO SIGNAL] disabled", flush=True)
        return None

    if AUTO_REQUIRE_OPEN_SESSION and not is_open_session() and not force:
        print("[AUTO SIGNAL] blocked: outside open session 9:30–10:30 ET", flush=True)
        return None

    if not cooldown_ready(force=force):
        print("[AUTO SIGNAL] cooldown active", flush=True)
        return None

    price = get_price()
    if not price:
        print("[AUTO SIGNAL] skipped: no valid QQQ price", flush=True)
        return None

    vwap = get_vwap(price)
    pm_high, pm_low = get_premarket_levels(price)

    direction, setup, grade = decide_direction(price, vwap, pm_high, pm_low)

    if not direction:
        print(
            f"[AUTO SIGNAL] no trade | ticker=QQQ price={price} vwap={vwap} "
            f"pm_high={pm_high} pm_low={pm_low}",
            flush=True,
        )
        return None

    signal = build_signal(price, vwap, pm_high, pm_low, direction, setup, grade)

    if signal.get("ticker") != "QQQ":
        print("[GENERATOR BLOCK] Non-QQQ prevented", flush=True)
        return None

    save_json(SIGNAL_FILE, signal)

    save_json(STATE_FILE, {
        "last_signal_ts": now_ts(),
        "last_ticker": "QQQ",
        "last_direction": direction,
        "last_entry": signal["entry"],
        "last_setup": setup,
        "last_grade": grade,
        "last_score": signal["score"],
        "last_signal_id": signal["signal_id"],
        "session": signal["session"],
    })

    print(
        f"[AUTO SIGNAL] GENERATED QQQ {direction} | setup={setup} "
        f"grade={grade} score={signal['score']} entry={signal['entry']} "
        f"vwap={signal['vwap']} pm_high={pm_high} pm_low={pm_low} "
        f"session={signal['session']} signal_id={signal['signal_id']}",
        flush=True,
    )

    return signal


if __name__ == "__main__":
    print("[AUTO SIGNAL LOOP STARTED]", flush=True)

    while True:
        try:
            generate_signal(force=False)
        except Exception as e:
            print(f"[AUTO SIGNAL ERROR] {e}", flush=True)

        time.sleep(10)

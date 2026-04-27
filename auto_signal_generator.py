# =========================================================
# UNBIASED TRADES — AUTO SIGNAL GENERATOR
# QQQ ONLY / PAPER TEST DRIVER
# Writes fresh ai_signal.json so main.py never reads stale SPY
# =========================================================

import os
import json
import time
from datetime import datetime

SIGNAL_FILE = os.getenv("SIGNAL_FILE", "ai_signal.json").strip()
MARKET_FILE = os.getenv("MARKET_DATA_FILE", "market_prices.json").strip()

AUTO_SIGNAL_ENABLED = os.getenv("ENABLE_AUTO_SIGNAL_GENERATOR", "true").lower() == "true"
AUTO_SIGNAL_COOLDOWN_SECONDS = int(os.getenv("AUTO_SIGNAL_COOLDOWN_SECONDS", "300"))

# HARD LOCK TO QQQ
AUTO_SIGNAL_TICKER = "QQQ"

AUTO_SIGNAL_DIRECTION = os.getenv("AUTO_SIGNAL_DIRECTION", "CALL").upper().strip()
if AUTO_SIGNAL_DIRECTION not in {"CALL", "PUT"}:
    AUTO_SIGNAL_DIRECTION = "CALL"

STATE_FILE = "auto_signal_generator_state.json"


def load_json(path, default):
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"[AUTO SIGNAL ERROR] save failed: {e}", flush=True)
        return False


def get_market_price(ticker="QQQ"):
    data = load_json(MARKET_FILE, {})

    item = data.get(ticker)
    if isinstance(item, dict):
        price = item.get("price") or item.get("last") or item.get("close")
        try:
            price = float(price)
            if price > 100:
                return price
        except Exception:
            pass

    # fallback for some older market file formats
    try:
        price = float(data.get("price"))
        if price > 100:
            return price
    except Exception:
        pass

    return None


def cooldown_ready():
    state = load_json(STATE_FILE, {})
    last_ts = int(state.get("last_signal_ts", 0) or 0)
    now = int(time.time())

    if last_ts <= 0:
        return True

    return (now - last_ts) >= AUTO_SIGNAL_COOLDOWN_SECONDS


def build_signal(price):
    now = int(time.time())

    if AUTO_SIGNAL_DIRECTION == "CALL":
        entry = round(price, 2)
        stop = round(price - 1.50, 2)
        targets = [
            round(price + 1.50, 2),
            round(price + 3.00, 2),
        ]
        trade_reason = "QQQ auto paper CALL test signal"
    else:
        entry = round(price, 2)
        stop = round(price + 1.50, 2)
        targets = [
            round(price - 1.50, 2),
            round(price - 3.00, 2),
        ]
        trade_reason = "QQQ auto paper PUT test signal"

    return {
        "ticker": "QQQ",
        "symbol": "QQQ",
        "underlying": "QQQ",

        "direction": AUTO_SIGNAL_DIRECTION,
        "side": AUTO_SIGNAL_DIRECTION,

        "entry": entry,
        "entry_price": entry,
        "stop": stop,
        "stop_loss": stop,
        "targets": targets,
        "target": targets[0],

        "confidence": "B",
        "grade": "B",

        "setup": "AUTO_QQQ_PAPER_TEST",
        "setup_type": "auto_signal_generator",
        "trigger": "fresh_auto_generated_qqq_signal",

        "time_window": "paper_test",
        "session": "auto",
        "trade_reason": trade_reason,

        "timestamp": now,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "source": "auto_signal_generator",

        "force_execution": True,
        "paper_only": True,
    }


def generate_signal(force=False):
    if not AUTO_SIGNAL_ENABLED:
        print("[AUTO SIGNAL] disabled", flush=True)
        return None

    if not force and not cooldown_ready():
        return None

    price = get_market_price("QQQ")

    if price is None:
        print("[AUTO SIGNAL] skipped: no valid QQQ price", flush=True)
        return None

    signal = build_signal(price)

    ok = save_json(SIGNAL_FILE, signal)
    if not ok:
        return None

    save_json(STATE_FILE, {
        "last_signal_ts": int(time.time()),
        "last_ticker": "QQQ",
        "last_direction": AUTO_SIGNAL_DIRECTION,
        "last_entry": signal["entry"],
        "last_signal_file": SIGNAL_FILE,
    })

    print(
        f"[AUTO SIGNAL] Generated QQQ {AUTO_SIGNAL_DIRECTION} "
        f"entry={signal['entry']} stop={signal['stop']} targets={signal['targets']}",
        flush=True,
    )

    return signal


if __name__ == "__main__":
    sig = generate_signal(force=True)
    if sig:
        print(json.dumps(sig, indent=2))
    else:
        print("No signal generated")

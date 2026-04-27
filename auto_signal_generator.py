import json
import time
import os

SIGNAL_FILE = "ai_signal.json"
MARKET_FILE = "market_prices.json"

def load_json(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return {}

def save_signal(signal):
    with open(SIGNAL_FILE, "w") as f:
        json.dump(signal, f)

def safe_float(x):
    try:
        return float(x)
    except:
        return None

def generate_signal():
    data = load_json(MARKET_FILE)
    q = data.get("QQQ", {})

    price = safe_float(q.get("price"))
    vwap = safe_float(q.get("vwap") or q.get("session_vwap") or q.get("close"))

    pm_high = safe_float(q.get("premarket_high") or q.get("pm_high"))
    pm_low = safe_float(q.get("premarket_low") or q.get("pm_low"))

    if not price or not vwap:
        print("[AUTO SIGNAL] missing price or vwap")
        return

    # fallback levels
    if not pm_high or not pm_low:
        pm_high = price + 1.5
        pm_low = price - 1.5

    signal = None

    # =========================
    # 1. BREAKOUT
    # =========================
    if price > pm_high:
        signal = {
            "ticker": "QQQ",
            "direction": "CALL",
            "entry_type": "BREAKOUT",
            "confidence": "A"
        }

    elif price < pm_low:
        signal = {
            "ticker": "QQQ",
            "direction": "PUT",
            "entry_type": "BREAKDOWN",
            "confidence": "A"
        }

    # =========================
    # 2. VWAP TREND (NEW FIX 🔥)
    # =========================
    elif price > vwap:
        signal = {
            "ticker": "QQQ",
            "direction": "CALL",
            "entry_type": "VWAP_TREND",
            "confidence": "B+"
        }

    elif price < vwap:
        signal = {
            "ticker": "QQQ",
            "direction": "PUT",
            "entry_type": "VWAP_TREND",
            "confidence": "B+"
        }

    # =========================
    # OUTPUT
    # =========================
    if signal:
        save_signal(signal)
        print(f"[AUTO SIGNAL] GENERATED: {signal}", flush=True)
    else:
        print("[AUTO SIGNAL] no trade", flush=True)


if __name__ == "__main__":
    print("[AUTO SIGNAL LOOP STARTED]", flush=True)

    while True:
        try:
            generate_signal()
        except Exception as e:
            print(f"[AUTO SIGNAL ERROR] {e}", flush=True)

        time.sleep(10)

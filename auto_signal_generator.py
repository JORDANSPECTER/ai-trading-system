import json
import time
import os

MARKET_FILE = "market_prices.json"
SIGNAL_FILE = "ai_signal.json"

def load_json(path, default=None):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def get_price(ticker):
    data = load_json(MARKET_FILE, {})
    item = data.get(ticker, {})
    try:
        return float(item.get("price"))
    except Exception:
        return None

def generate_signal():
    ticker = os.getenv("AUTO_SIGNAL_TICKER", "QQQ").upper()
    price = get_price(ticker)

    if not price or price < 100:
        return None

    direction = os.getenv("AUTO_SIGNAL_DIRECTION", "CALL").upper()

    if direction == "CALL":
        entry = price
        stop = round(price - 1.50, 2)
        targets = [round(price + 1.50, 2), round(price + 3.00, 2)]
    else:
        entry = price
        stop = round(price + 1.50, 2)
        targets = [round(price - 1.50, 2), round(price - 3.00, 2)]

    signal = {
        "ticker": ticker,
        "direction": direction,
        "entry": round(entry, 2),
        "stop": stop,
        "targets": targets,
        "confidence": "B",
        "grade": "B",
        "setup": "AUTO_GENERATED_TEST_SIGNAL",
        "trigger": "auto_price_signal",
        "timestamp": int(time.time()),
        "source": "auto_signal_generator"
    }

    save_json(SIGNAL_FILE, signal)
    return signal

if __name__ == "__main__":
    sig = generate_signal()
    if sig:
        print("✅ Auto signal generated")
        print(json.dumps(sig, indent=2))
    else:
        print("❌ No signal generated")

import os
import traceback
from datetime import datetime
import requests


# ======================
# ENV
# ======================

DISCORD_WEBHOOK_FREE = os.getenv("DISCORD_WEBHOOK_FREE", "").strip()
DISCORD_WEBHOOK_PREMIUM = os.getenv("DISCORD_WEBHOOK_PREMIUM", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()

SYMBOL = os.getenv("SYMBOL", "QQQ").upper()
SECONDARY_SYMBOL = os.getenv("SECONDARY_SYMBOL", "SPY").upper()
OIL_SYMBOL = os.getenv("OIL_SYMBOL", "USO").upper()


# ======================
# HELPERS
# ======================

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def to_float(v):
    try:
        return float(v)
    except:
        return 0.0


# ======================
# API
# ======================

def get_quote(symbol):
    url = "https://api.twelvedata.com/quote"
    params = {"symbol": symbol, "apikey": TWELVE_DATA_API_KEY}
    r = requests.get(url, params=params, timeout=20)
    data = r.json()

    if "close" not in data and "price" not in data:
        raise Exception(f"Bad API response: {data}")

    return data


# ======================
# SEND FUNCTIONS (DEBUG ENABLED)
# ======================

def send_discord(webhook_url, msg, label):
    if not webhook_url:
        log(f"{label}: ❌ Missing webhook")
        return

    try:
        payload = {"content": msg[:1900]}
        r = requests.post(webhook_url, json=payload, timeout=20)

        log(f"{label}: status {r.status_code}")
        log(f"{label}: response {r.text[:200]}")

        if not (200 <= r.status_code < 300):
            raise Exception(f"{label} FAILED: {r.status_code}")

    except Exception as e:
        log(f"{label}: ERROR {e}")


def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg[:4000]}
    r = requests.post(url, data=payload, timeout=20)
    log(f"Telegram: {r.status_code}")


# ======================
# MESSAGE BUILDERS
# ======================

def build_free(q, s, o):
    return f"""📡 FREE ALERT

{SYMBOL}: {q:.2f}
{SECONDARY_SYMBOL}: {s:.2f}
{OIL_SYMBOL}: {o:.2f}

Bias: WATCH
Setup: Developing

Where information becomes execution.
"""


def build_premium(q, s, o):
    return f"""💎 PREMIUM ALERT

{SYMBOL}: {q:.2f}
{SECONDARY_SYMBOL}: {s:.2f}
{OIL_SYMBOL}: {o:.2f}

Bias: DEVELOPING EDGE
Action: WAIT FOR CONFIRMATION
Grade: B
Setup: STRUCTURE FORMING

Where information becomes execution.
"""


# ======================
# MAIN
# ======================

def main():
    log("Bot starting")

    try:
        qqq = get_quote(SYMBOL)
        spy = get_quote(SECONDARY_SYMBOL)
        oil = get_quote(OIL_SYMBOL)

        q = to_float(qqq.get("price") or qqq.get("close"))
        s = to_float(spy.get("price") or spy.get("close"))
        o = to_float(oil.get("price") or oil.get("close"))

        free_msg = build_free(q, s, o)
        premium_msg = build_premium(q, s, o)

        log("Sending alerts...")

        send_discord(DISCORD_WEBHOOK_FREE, free_msg, "FREE")
        send_discord(DISCORD_WEBHOOK_PREMIUM, premium_msg, "PREMIUM")
        send_telegram(premium_msg)

        log("Done")

    except Exception as e:
        log(f"ERROR: {e}")
        log(traceback.format_exc())


if __name__ == "__main__":
    main()

import os
import json
import traceback
from datetime import datetime

import requests


# ======================
# ENV
# ======================

DISCORD_WEBHOOK_URL = os.getenv("https://discord.com/api/webhooks/1494042156069949533/sxnwJnv036sXgcMy4vWnz1lFuK_hmi4p7OJk1Mbuaa83azTq9WugFPAPMMpWf1at21Wu", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("8636128819:AAFT9ibrwatP7O6wsTQi7wJVeQcuNqMLv4I", "").strip()
TELEGRAM_CHAT_ID = os.getenv("8661143355", "").strip()
TWELVE_DATA_API_KEY = os.getenv("b8760b201df4466b8082bc17c1ab1e9b", "").strip()

SYMBOL = os.getenv("SYMBOL", "QQQ").strip().upper()
SECONDARY_SYMBOL = os.getenv("SECONDARY_SYMBOL", "SPY").strip().upper()
OIL_SYMBOL = os.getenv("OIL_SYMBOL", "USO").strip().upper()


# ======================
# HELPERS
# ======================

def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def get_price(symbol: str) -> float:
    url = "https://api.twelvedata.com/price"
    params = {"symbol": symbol, "apikey": TWELVE_DATA_API_KEY}

    r = requests.get(url, params=params, timeout=20)
    data = r.json()

    log(f"TwelveData raw for {symbol}: {json.dumps(data)[:300]}")

    if "price" not in data:
        raise Exception(f"Bad API response for {symbol}: {data}")

    return float(data["price"])


def send_discord(msg: str) -> None:
    if not DISCORD_WEBHOOK_URL:
        raise Exception("DISCORD_WEBHOOK_URL missing")

    payload = {"content": msg[:1900]}
    r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=20)

    log(f"Discord status: {r.status_code}")
    log(f"Discord response: {r.text[:500]}")

    if not (200 <= r.status_code < 300):
        raise Exception(f"Discord failed: {r.status_code} | {r.text}")


def send_telegram(msg: str) -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise Exception("TELEGRAM_BOT_TOKEN missing")

    if not TELEGRAM_CHAT_ID:
        raise Exception("TELEGRAM_CHAT_ID missing")

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg[:4000],
    }

    r = requests.post(url, data=payload, timeout=20)

    log(f"Telegram status: {r.status_code}")
    log(f"Telegram response: {r.text[:500]}")

    if not (200 <= r.status_code < 300):
        raise Exception(f"Telegram failed: {r.status_code} | {r.text}")


def validate_env() -> None:
    log(f"DISCORD_WEBHOOK_URL loaded: {bool(DISCORD_WEBHOOK_URL)}")
    log(f"TELEGRAM_BOT_TOKEN loaded: {bool(TELEGRAM_BOT_TOKEN)}")
    log(f"TELEGRAM_CHAT_ID loaded: {bool(TELEGRAM_CHAT_ID)}")
    log(f"TWELVE_DATA_API_KEY loaded: {bool(TWELVE_DATA_API_KEY)}")
    log(f"SYMBOL={SYMBOL}")
    log(f"SECONDARY_SYMBOL={SECONDARY_SYMBOL}")
    log(f"OIL_SYMBOL={OIL_SYMBOL}")


# ======================
# MAIN
# ======================

def main() -> None:
    log("Starting bot")
    validate_env()

    try:
        qqq = get_price(SYMBOL)
        spy = get_price(SECONDARY_SYMBOL)
        oil = get_price(OIL_SYMBOL)

        message = (
            f"📊 Market Snapshot\n"
            f"{SYMBOL}: {qqq}\n"
            f"{SECONDARY_SYMBOL}: {spy}\n"
            f"{OIL_SYMBOL}: {oil}"
        )

        log("Final message:")
        log(message)

        send_discord(message)
        send_telegram(message)

        log("Both send calls completed")

    except Exception as e:
        log(f"ERROR: {e}")
        log(traceback.format_exc())
        raise

    log("Finished run")


if __name__ == "__main__":
    main()

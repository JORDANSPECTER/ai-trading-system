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

SYMBOL = os.getenv("SYMBOL", "QQQ")
SECONDARY_SYMBOL = os.getenv("SECONDARY_SYMBOL", "SPY")
OIL_SYMBOL = os.getenv("OIL_SYMBOL", "USO")


# ======================
# HELPERS
# ======================

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def get_price(symbol):
    url = "https://api.twelvedata.com/price"
    params = {"symbol": symbol, "apikey": TWELVE_DATA_API_KEY}

    r = requests.get(url, params=params)
    data = r.json()

    if "price" not in data:
        raise Exception(f"Bad API response: {data}")

    return float(data["price"])


def send_discord(msg):
    if not DISCORD_WEBHOOK_URL:
        return

    requests.post(DISCORD_WEBHOOK_URL, json={"content": msg})


def send_telegram(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})


# ======================
# MAIN
# ======================

def main():
    log("Starting bot")

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

        log(message)

        send_discord(message)
        send_telegram(message)

    except Exception as e:
        log(f"ERROR: {e}")
        log(traceback.format_exc())

    log("Finished run")


if __name__ == "__main__":
    main()

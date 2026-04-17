import os
import traceback
from datetime import datetime

import requests


# ======================
# ENV
# ======================

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()

SYMBOL = os.getenv("SYMBOL", "QQQ").strip().upper()
SECONDARY_SYMBOL = os.getenv("SECONDARY_SYMBOL", "SPY").strip().upper()
OIL_SYMBOL = os.getenv("OIL_SYMBOL", "USO").strip().upper()


# ======================
# HELPERS
# ======================

def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def get_quote(symbol: str) -> dict:
    url = "https://api.twelvedata.com/quote"
    params = {"symbol": symbol, "apikey": TWELVE_DATA_API_KEY}

    r = requests.get(url, params=params, timeout=20)
    data = r.json()

    if "close" not in data and "price" not in data:
        raise Exception(f"Bad API response for {symbol}: {data}")

    return data


def to_float(value, default=0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def send_discord(msg: str) -> None:
    payload = {"content": msg[:1900]}
    r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=20)
    log(f"Discord status: {r.status_code}")


def send_telegram(msg: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg[:4000]}
    r = requests.post(url, data=payload, timeout=20)
    log(f"Telegram status: {r.status_code}")


# ======================
# BIAS LOGIC
# ======================

def build_signal_message(qqq_data: dict, spy_data: dict, oil_data: dict) -> str:
    qqq = to_float(qqq_data.get("close") or qqq_data.get("price"))
    spy = to_float(spy_data.get("close") or spy_data.get("price"))
    oil = to_float(oil_data.get("close") or oil_data.get("price"))

    qqq_prev = to_float(qqq_data.get("previous_close"))
    spy_prev = to_float(spy_data.get("previous_close"))
    oil_prev = to_float(oil_data.get("previous_close"))

    qqq_change = qqq - qqq_prev
    spy_change = spy - spy_prev
    oil_change = oil - oil_prev

    reasons = []
    bias = "NEUTRAL"
    action = "WAIT"

    if qqq_change > 0 and spy_change > 0:
        reasons.append("QQQ and SPY are both green on the day.")
    if qqq_change < 0 and spy_change < 0:
        reasons.append("QQQ and SPY are both red on the day.")
    if oil_change > 0:
        reasons.append("Oil is pushing higher.")
    if oil_change < 0:
        reasons.append("Oil is easing lower.")

    if qqq_change > 0 and spy_change > 0 and oil_change <= 0:
        bias = "BULLISH"
        action = "CALL IDEA"
        reasons.append("Index strength is aligned while oil pressure is not rising.")
    elif qqq_change < 0 and spy_change < 0 and oil_change > 0:
        bias = "BEARISH"
        action = "PUT IDEA"
        reasons.append("Index weakness is aligned with rising oil pressure.")
    elif qqq_change > 0 and spy_change > 0:
        bias = "SLIGHTLY BULLISH"
        action = "WAIT FOR CONFIRMATION"
    elif qqq_change < 0 and spy_change < 0:
        bias = "SLIGHTLY BEARISH"
        action = "WAIT FOR CONFIRMATION"

    reason_text = "\n".join([f"• {r}" for r in reasons]) if reasons else "• No strong alignment yet."

    return (
        f"📡 UnBiased Trades Bot\n\n"
        f"{SYMBOL}: {qqq:.2f} ({qqq_change:+.2f})\n"
        f"{SECONDARY_SYMBOL}: {spy:.2f} ({spy_change:+.2f})\n"
        f"{OIL_SYMBOL}: {oil:.2f} ({oil_change:+.2f})\n\n"
        f"Bias: {bias}\n"
        f"Action: {action}\n\n"
        f"Reasons:\n{reason_text}\n\n"
        f"Where information becomes execution."
    )


# ======================
# MAIN
# ======================

def main() -> None:
    log("Starting signal bot")

    try:
        qqq_data = get_quote(SYMBOL)
        spy_data = get_quote(SECONDARY_SYMBOL)
        oil_data = get_quote(OIL_SYMBOL)

        message = build_signal_message(qqq_data, spy_data, oil_data)

        log("Built signal message")
        log(message)

        send_discord(message)
        send_telegram(message)

        log("Alerts sent successfully")

    except Exception as e:
        log(f"ERROR: {e}")
        log(traceback.format_exc())
        raise

    log("Finished run")


if __name__ == "__main__":
    main()

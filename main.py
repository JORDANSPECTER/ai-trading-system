import os
from datetime import datetime

# =========================
# ENV VARIABLES
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

DISCORD_WEBHOOK_PREMIUM = os.getenv("DISCORD_WEBHOOK_PREMIUM")
DISCORD_WEBHOOK_FREE = os.getenv("DISCORD_WEBHOOK_FREE")

# =========================
# SEND FUNCTIONS
# =========================
import requests

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload)


def send_discord(webhook, message):
    if not webhook:
        print("Discord webhook missing")
        return

    requests.post(webhook, json={"content": message})


def send_discord_premium(message):
    send_discord(DISCORD_WEBHOOK_PREMIUM, message)


def send_discord_free(message):
    send_discord(DISCORD_WEBHOOK_FREE, message)

# =========================
# FORMATTERS
# =========================

def format_telegram_alert(decision, context):
    return f"""
🚨 {context.symbol} TRADE ALERT

Grade: {decision.grade}
Price: {context.current_price}

Entry Logic:
{chr(10).join(decision.reasons)}

Time: {datetime.now().strftime('%H:%M:%S')}
"""


def format_discord_premium_alert(decision, context):
    return f"""
💎 PREMIUM EXECUTION — {context.symbol}

Grade: {decision.grade}
Price: {context.current_price}

Trigger Level: {context.trigger_level}

{chr(10).join(decision.reasons)}

⚡ This is an ACTIVE trade setup.
"""


def format_discord_free_teaser(decision, context):
    return f"""
📊 MARKET INSIGHT — {context.symbol}

A high-quality setup is developing.

Key Level: {context.trigger_level}

Join premium for execution access.
"""


def format_discord_watchlist_alert(decision, context):
    return f"""
💎 PREMIUM WATCHLIST — {context.symbol}

Grade: {decision.grade}

This is NOT an execution trade yet.

→ Structure is developing  
→ Waiting for confirmation  
→ Key level: {context.trigger_level}

Patience > forcing entries.
"""


def format_discord_educational_alert(decision, context):
    return f"""
📘 MARKET CONTEXT — {context.symbol}

Current Structure:
{chr(10).join(decision.reasons)}

This is not a confirmed setup yet.
"""


# =========================
# CORE ROUTING LOGIC (STATE 3)
# =========================

def route_alerts(decision, context):
    grade = decision.grade

    # =========================
    # A+ / A → FULL EXECUTION
    # =========================
    if grade in ["A+", "A"]:
        send_telegram(format_telegram_alert(decision, context))

        send_discord_premium(
            format_discord_premium_alert(decision, context)
        )

        send_discord_free(
            format_discord_free_teaser(decision, context)
        )

    # =========================
    # B / C → INFORMATION ONLY
    # =========================
    elif grade in ["B+", "B", "C"]:
        send_discord_premium(
            format_discord_watchlist_alert(decision, context)
        )

        send_discord_free(
            format_discord_educational_alert(decision, context)
        )

    # =========================
    # AVOID → SILENT
    # =========================
    elif grade == "AVOID":
        print(f"[AVOID] No alert sent for {context.symbol}")


# =========================
# TEST FUNCTION (RUN THIS)
# =========================
def send_test_alert():
    class DummyDecision:
        grade = "B"
        reasons = [
            "Price near key level",
            "VWAP not fully confirmed",
            "Momentum building"
        ]

    class DummyContext:
        symbol = "QQQ"
        current_price = 615.25
        trigger_level = 616.00

    decision = DummyDecision()
    context = DummyContext()

    route_alerts(decision, context)


# =========================
# RUN TEST
# =========================
if __name__ == "__main__":
    send_test_alert()

import os
import requests
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
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram send failed: {e}")


def send_discord(webhook, message):
    if not webhook:
        print("Discord webhook missing")
        return
    try:
        requests.post(webhook, json={"content": message}, timeout=10)
    except Exception as e:
        print(f"Discord send failed: {e}")


def send_discord_premium(message):
    send_discord(DISCORD_WEBHOOK_PREMIUM, message)


def send_discord_free(message):
    send_discord(DISCORD_WEBHOOK_FREE, message)

# =========================
# ENTRY DISCIPLINE ENGINE
# =========================
def get_attr(obj, name, default=None):
    return getattr(obj, name, default)


def evaluate_entry_timing(decision, context):
    """
    Returns timing profile used to block chasing and downgrade late entries.
    """

    current_price = float(get_attr(context, "current_price", 0.0) or 0.0)
    trigger_level = float(get_attr(context, "trigger_level", current_price) or current_price)

    # Optional fields your real system can provide
    entry_zone_high = float(get_attr(context, "entry_zone_high", trigger_level) or trigger_level)
    entry_zone_low = float(get_attr(context, "entry_zone_low", trigger_level) or trigger_level)
    atr_push = float(get_attr(context, "atr_push", 0.0) or 0.0)
    extension_pct = float(get_attr(context, "extension_pct", 0.0) or 0.0)
    bars_since_breakout = int(get_attr(context, "bars_since_breakout", 0) or 0)
    momentum_confirmed = bool(get_attr(context, "momentum_confirmed", False))
    retest_hold = bool(get_attr(context, "retest_hold", False))
    breakout_with_volume = bool(get_attr(context, "breakout_with_volume", False))
    near_key_level = bool(get_attr(context, "near_key_level", True))
    above_vwap = bool(get_attr(context, "above_vwap", False))
    below_vwap = bool(get_attr(context, "below_vwap", False))

    if trigger_level == 0:
        distance_from_trigger_pct = 0.0
    else:
        distance_from_trigger_pct = abs(current_price - trigger_level) / abs(trigger_level) * 100

    if entry_zone_high == entry_zone_low == trigger_level:
        within_entry_zone = distance_from_trigger_pct <= 0.20
    else:
        within_entry_zone = entry_zone_low <= current_price <= entry_zone_high

    chasing_reasons = []

    if not within_entry_zone:
        chasing_reasons.append("Price is outside preferred entry zone.")

    if distance_from_trigger_pct > 0.35:
        chasing_reasons.append(f"Price is extended {distance_from_trigger_pct:.2f}% from trigger.")

    if extension_pct > 0.40:
        chasing_reasons.append(f"Extension is elevated at {extension_pct:.2f}%.")

    if bars_since_breakout >= 3 and not retest_hold:
        chasing_reasons.append(f"Entry is late: {bars_since_breakout} bars after breakout without clean retest.")

    if atr_push > 0.35:
        chasing_reasons.append(f"Move already expanded {atr_push:.2f} ATR from trigger.")

    if not near_key_level:
        chasing_reasons.append("Price is no longer near the key decision level.")

    is_chasing = len(chasing_reasons) > 0

    timing_label = "IDEAL"
    if is_chasing:
        timing_label = "LATE"
    elif breakout_with_volume and momentum_confirmed:
        timing_label = "CONFIRMED"
    elif retest_hold:
        timing_label = "RETEST"

    directional_alignment = above_vwap or below_vwap

    premium_execution_allowed = (
        not is_chasing
        and directional_alignment
        and (
            retest_hold
            or (breakout_with_volume and momentum_confirmed)
        )
    )

    b_grade_execution_allowed = (
        not is_chasing
        and momentum_confirmed
        and directional_alignment
        and (
            retest_hold
            or breakout_with_volume
        )
    )

    return {
        "is_chasing": is_chasing,
        "timing_label": timing_label,
        "premium_execution_allowed": premium_execution_allowed,
        "b_grade_execution_allowed": b_grade_execution_allowed,
        "distance_from_trigger_pct": round(distance_from_trigger_pct, 3),
        "chasing_reasons": chasing_reasons,
    }


def apply_state_4_discipline(decision, context):
    """
    Modifies routing behavior based on entry quality.
    Does not have to rewrite your whole AI grade engine — it adds a discipline layer on top.
    """
    timing = evaluate_entry_timing(decision, context)

    original_grade = get_attr(decision, "grade", "C")
    reasons = list(get_attr(decision, "reasons", []))

    if timing["is_chasing"]:
        reasons.append("YOU ARE CHASING: entry is extended from the intended trigger zone.")
        for r in timing["chasing_reasons"]:
            reasons.append(r)

    # Block B-grade execution unless momentum confirms
    if original_grade in ["B+", "B"] and not timing["b_grade_execution_allowed"]:
        reasons.append("B-grade blocked from premium execution until momentum confirms.")
        execution_grade = "WATCHLIST"
    # A/A+ can still downgrade to watchlist if chasing
    elif original_grade in ["A+", "A"] and not timing["premium_execution_allowed"]:
        reasons.append("High-grade setup downgraded to watchlist because entry timing is no longer clean.")
        execution_grade = "WATCHLIST"
    else:
        execution_grade = original_grade

    return {
        "original_grade": original_grade,
        "execution_grade": execution_grade,
        "timing": timing,
        "reasons": reasons
    }

# =========================
# FORMATTERS
# =========================
def format_telegram_alert(decision, context, discipline):
    timing = discipline["timing"]
    return f"""
🚨 {context.symbol} TRADE ALERT

Grade: {discipline['execution_grade']}
Original Grade: {discipline['original_grade']}
Timing: {timing['timing_label']}
Price: {context.current_price}
Trigger: {context.trigger_level}

Entry Logic:
{chr(10).join(['- ' + r for r in discipline['reasons']])}

Time: {datetime.now().strftime('%H:%M:%S')}
""".strip()


def format_discord_premium_alert(decision, context, discipline):
    timing = discipline["timing"]
    return f"""
💎 PREMIUM EXECUTION — {context.symbol}

Grade: {discipline['execution_grade']}
Original Grade: {discipline['original_grade']}
Timing: {timing['timing_label']}

Price: {context.current_price}
Trigger Level: {context.trigger_level}
Distance From Trigger: {timing['distance_from_trigger_pct']}%

{chr(10).join(['• ' + r for r in discipline['reasons']])}

⚡ Clean execution conditions are present.
""".strip()


def format_discord_watchlist_alert(decision, context, discipline):
    timing = discipline["timing"]
    chasing_block = ""
    if timing["is_chasing"]:
        chasing_block = "\n🚫 YOU ARE CHASING\nDo not force premium execution here."

    return f"""
💎 PREMIUM WATCHLIST — {context.symbol}

Original Grade: {discipline['original_grade']}
Execution Status: {discipline['execution_grade']}
Timing: {timing['timing_label']}

Price: {context.current_price}
Trigger Level: {context.trigger_level}
Distance From Trigger: {timing['distance_from_trigger_pct']}%
{chasing_block}

{chr(10).join(['• ' + r for r in discipline['reasons']])}

Patience > forcing entries.
Wait for reclaim, retest, or momentum confirmation.
""".strip()


def format_discord_free_teaser(decision, context, discipline):
    timing = discipline["timing"]
    return f"""
📊 MARKET INSIGHT — {context.symbol}

A strong setup is active.
Timing: {timing['timing_label']}
Key Level: {context.trigger_level}

Join premium for execution access.
""".strip()


def format_discord_educational_alert(decision, context, discipline):
    timing = discipline["timing"]
    return f"""
📘 MARKET CONTEXT — {context.symbol}

Timing: {timing['timing_label']}
Price: {context.current_price}
Key Level: {context.trigger_level}

{chr(10).join(['• ' + r for r in discipline['reasons'][:5]])}

This is informational, not confirmed execution.
""".strip()

# =========================
# ROUTING LOGIC
# =========================
def route_alerts(decision, context):
    discipline = apply_state_4_discipline(decision, context)
    execution_grade = discipline["execution_grade"]

    # A+ / A with clean timing only
    if execution_grade in ["A+", "A"]:
        send_telegram(format_telegram_alert(decision, context, discipline))
        send_discord_premium(format_discord_premium_alert(decision, context, discipline))
        send_discord_free(format_discord_free_teaser(decision, context, discipline))

    # Watchlist path (downgraded from chase / late entry / weak momentum)
    elif execution_grade == "WATCHLIST":
        send_discord_premium(format_discord_watchlist_alert(decision, context, discipline))
        send_discord_free(format_discord_educational_alert(decision, context, discipline))

    # B / C still informational only
    elif execution_grade in ["B+", "B", "C"]:
        send_discord_premium(format_discord_watchlist_alert(decision, context, discipline))
        send_discord_free(format_discord_educational_alert(decision, context, discipline))

    elif execution_grade == "AVOID":
        print(f"[AVOID] No alert sent for {context.symbol}")

# =========================
# TEST FUNCTION
# =========================
def send_test_alert():
    class DummyDecision:
        grade = "A"
        reasons = [
            "VWAP reclaimed",
            "Breakout candle printed with volume",
            "Key level triggered"
        ]

    class DummyContext:
        symbol = "QQQ"
        current_price = 616.85
        trigger_level = 616.00

        # Optional timing fields
        entry_zone_low = 615.90
        entry_zone_high = 616.20
        atr_push = 0.42
        extension_pct = 0.48
        bars_since_breakout = 4
        momentum_confirmed = False
        retest_hold = False
        breakout_with_volume = True
        near_key_level = False
        above_vwap = True
        below_vwap = False

    decision = DummyDecision()
    context = DummyContext()

    route_alerts(decision, context)

# =========================
# MAIN
# =========================
if __name__ == "__main__":
    send_test_alert()

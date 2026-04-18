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
# HELPERS
# =========================
def get_attr(obj, name, default=None):
    return getattr(obj, name, default)


def fmt_price(x):
    try:
        return f"{float(x):.2f}"
    except Exception:
        return str(x)


# =========================
# STATE 4 - ENTRY DISCIPLINE
# =========================
def evaluate_entry_timing(decision, context):
    current_price = float(get_attr(context, "current_price", 0.0) or 0.0)
    trigger_level = float(get_attr(context, "trigger_level", current_price) or current_price)

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
    timing = evaluate_entry_timing(decision, context)

    original_grade = get_attr(decision, "grade", "C")
    reasons = list(get_attr(decision, "reasons", []))

    if timing["is_chasing"]:
        reasons.append("YOU ARE CHASING: entry is extended from the intended trigger zone.")
        for r in timing["chasing_reasons"]:
            reasons.append(r)

    if original_grade in ["B+", "B"] and not timing["b_grade_execution_allowed"]:
        reasons.append("B-grade blocked from premium execution until momentum confirms.")
        execution_grade = "WATCHLIST"
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
# STATE 5 - SIZE ENGINE
# =========================
def calculate_confidence_and_size(decision, context, discipline):
    original_grade = discipline["original_grade"]
    execution_grade = discipline["execution_grade"]
    timing = discipline["timing"]

    breakout_with_volume = bool(get_attr(context, "breakout_with_volume", False))
    momentum_confirmed = bool(get_attr(context, "momentum_confirmed", False))
    retest_hold = bool(get_attr(context, "retest_hold", False))
    above_vwap = bool(get_attr(context, "above_vwap", False))
    below_vwap = bool(get_attr(context, "below_vwap", False))
    near_key_level = bool(get_attr(context, "near_key_level", True))
    oil_aligned = bool(get_attr(context, "oil_aligned", True))
    market_breadth_aligned = bool(get_attr(context, "market_breadth_aligned", True))
    sector_aligned = bool(get_attr(context, "sector_aligned", True))
    big_print_aligned = bool(get_attr(context, "big_print_aligned", True))

    confidence_score = 0

    if original_grade == "A+":
        confidence_score += 30
    elif original_grade == "A":
        confidence_score += 25
    elif original_grade == "B+":
        confidence_score += 18
    elif original_grade == "B":
        confidence_score += 14
    elif original_grade == "C":
        confidence_score += 8

    if execution_grade == "WATCHLIST":
        confidence_score -= 18

    if timing["timing_label"] == "IDEAL":
        confidence_score += 15
    elif timing["timing_label"] == "CONFIRMED":
        confidence_score += 12
    elif timing["timing_label"] == "RETEST":
        confidence_score += 14
    elif timing["timing_label"] == "LATE":
        confidence_score -= 20

    if breakout_with_volume:
        confidence_score += 8
    if momentum_confirmed:
        confidence_score += 10
    if retest_hold:
        confidence_score += 12
    if above_vwap or below_vwap:
        confidence_score += 8

    if near_key_level:
        confidence_score += 8
    else:
        confidence_score -= 8

    confidence_score += 4 if oil_aligned else -4
    confidence_score += 4 if market_breadth_aligned else -4
    confidence_score += 4 if sector_aligned else -4
    confidence_score += 5 if big_print_aligned else -5

    if timing["is_chasing"]:
        confidence_score -= 15

    confidence_score = max(0, min(100, confidence_score))

    if execution_grade in ["A+", "A"] and confidence_score >= 80:
        size_label = "AGGRESSIVE"
        risk_multiplier = 1.25
    elif execution_grade in ["A+", "A", "B+", "B"] and confidence_score >= 60:
        size_label = "NORMAL"
        risk_multiplier = 1.00
    elif execution_grade == "WATCHLIST":
        size_label = "NO EXECUTION"
        risk_multiplier = 0.00
    else:
        size_label = "SMALL"
        risk_multiplier = 0.50

    if timing["is_chasing"]:
        size_label = "NO EXECUTION"
        risk_multiplier = 0.00

    size_notes = []

    if size_label == "AGGRESSIVE":
        size_notes.append("Multiple conditions are aligned.")
        size_notes.append("Timing is clean enough for higher conviction sizing.")
    elif size_label == "NORMAL":
        size_notes.append("Setup is valid, but not peak conviction.")
    elif size_label == "SMALL":
        size_notes.append("Reduce exposure due to weaker alignment.")
    elif size_label == "NO EXECUTION":
        size_notes.append("Do not size into this move.")
        size_notes.append("Wait for a reclaim, retest, or better timing.")

    return {
        "confidence_score": confidence_score,
        "size_label": size_label,
        "risk_multiplier": risk_multiplier,
        "size_notes": size_notes
    }


# =========================
# STATE 6 - STOP + SCALE OUT ENGINE
# =========================
def build_trade_management_plan(decision, context, discipline, sizing):
    current_price = float(get_attr(context, "current_price", 0.0) or 0.0)
    trigger_level = float(get_attr(context, "trigger_level", current_price) or current_price)

    direction = get_attr(context, "direction", None)
    if not direction:
        if bool(get_attr(context, "above_vwap", False)):
            direction = "LONG"
        elif bool(get_attr(context, "below_vwap", False)):
            direction = "SHORT"
        else:
            direction = "LONG"

    support_1 = get_attr(context, "support_1", None)
    support_2 = get_attr(context, "support_2", None)
    resistance_1 = get_attr(context, "resistance_1", None)
    resistance_2 = get_attr(context, "resistance_2", None)
    atr_push = float(get_attr(context, "atr_push", 0.20) or 0.20)

    entry_reference = trigger_level if trigger_level else current_price

    if direction == "LONG":
        invalidation = support_1 if support_1 is not None else (entry_reference - max(0.25, atr_push * 0.8))
        trim_1 = resistance_1 if resistance_1 is not None else (entry_reference + max(0.35, atr_push * 1.0))
        trim_2 = resistance_2 if resistance_2 is not None else (entry_reference + max(0.60, atr_push * 1.6))
        runner_target = trim_2 + max(0.30, atr_push * 1.0)
        breakeven_trigger = trim_1
    else:
        invalidation = resistance_1 if resistance_1 is not None else (entry_reference + max(0.25, atr_push * 0.8))
        trim_1 = support_1 if support_1 is not None else (entry_reference - max(0.35, atr_push * 1.0))
        trim_2 = support_2 if support_2 is not None else (entry_reference - max(0.60, atr_push * 1.6))
        runner_target = trim_2 - max(0.30, atr_push * 1.0)
        breakeven_trigger = trim_1

    size_label = sizing["size_label"]
    execution_grade = discipline["execution_grade"]

    if size_label == "AGGRESSIVE":
        trim_plan = [
            "Take 25% off at Trim 1",
            "Take 35% off at Trim 2",
            "Leave 40% for runner"
        ]
    elif size_label == "NORMAL":
        trim_plan = [
            "Take 33% off at Trim 1",
            "Take 33% off at Trim 2",
            "Leave 34% for runner"
        ]
    elif size_label == "SMALL":
        trim_plan = [
            "Take 50% off at Trim 1",
            "Take 30% off at Trim 2",
            "Leave 20% for runner"
        ]
    else:
        trim_plan = [
            "No execution plan active",
            "Wait for better location",
            "Do not force a position here"
        ]

    move_stop_rule = f"Move stop to breakeven once price reaches {fmt_price(breakeven_trigger)}."

    management_notes = []

    if execution_grade == "WATCHLIST":
        management_notes.append("Execution downgraded to watchlist. Management plan is informational only.")

    if discipline["timing"]["is_chasing"]:
        management_notes.append("Late/chasing conditions detected. Avoid forcing entry.")
    else:
        management_notes.append("Entry timing is acceptable for structured trade management.")

    if direction == "LONG":
        management_notes.append("Bias remains valid while price holds above invalidation.")
    else:
        management_notes.append("Bias remains valid while price stays below invalidation.")

    return {
        "direction": direction,
        "entry_reference": round(entry_reference, 2),
        "invalidation": round(float(invalidation), 2),
        "trim_1": round(float(trim_1), 2),
        "trim_2": round(float(trim_2), 2),
        "runner_target": round(float(runner_target), 2),
        "breakeven_trigger": round(float(breakeven_trigger), 2),
        "trim_plan": trim_plan,
        "move_stop_rule": move_stop_rule,
        "management_notes": management_notes
    }


# =========================
# FORMATTERS
# =========================
def format_trade_management_block(plan):
    return "\n".join([
        f"Direction: {plan['direction']}",
        f"Invalidation: {fmt_price(plan['invalidation'])}",
        f"Trim 1: {fmt_price(plan['trim_1'])}",
        f"Trim 2: {fmt_price(plan['trim_2'])}",
        f"Runner Target: {fmt_price(plan['runner_target'])}",
        f"Break-even Trigger: {fmt_price(plan['breakeven_trigger'])}",
        "",
        "Scale-Out Plan:",
        *[f"- {x}" for x in plan["trim_plan"]],
        "",
        f"Stop Rule: {plan['move_stop_rule']}",
        *[f"- {x}" for x in plan["management_notes"]],
    ])


def format_telegram_alert(decision, context, discipline, sizing, management):
    timing = discipline["timing"]
    return f"""
🚨 {context.symbol} TRADE ALERT

Grade: {discipline['execution_grade']}
Original Grade: {discipline['original_grade']}
Timing: {timing['timing_label']}
Confidence: {sizing['confidence_score']}/100
Size: {sizing['size_label']}
Risk Multiplier: {sizing['risk_multiplier']}x

Price: {fmt_price(context.current_price)}
Trigger: {fmt_price(context.trigger_level)}

Entry Logic:
{chr(10).join(['- ' + r for r in discipline['reasons']])}

Size Notes:
{chr(10).join(['- ' + r for r in sizing['size_notes']])}

Trade Plan:
{format_trade_management_block(management)}

Time: {datetime.now().strftime('%H:%M:%S')}
""".strip()


def format_discord_premium_alert(decision, context, discipline, sizing, management):
    timing = discipline["timing"]
    return f"""
💎 PREMIUM EXECUTION — {context.symbol}

Grade: {discipline['execution_grade']}
Original Grade: {discipline['original_grade']}
Timing: {timing['timing_label']}
Confidence: {sizing['confidence_score']}/100

📏 Size: {sizing['size_label']}
⚖️ Risk Multiplier: {sizing['risk_multiplier']}x

Price: {fmt_price(context.current_price)}
Trigger Level: {fmt_price(context.trigger_level)}
Distance From Trigger: {timing['distance_from_trigger_pct']}%

{chr(10).join(['• ' + r for r in discipline['reasons']])}

{chr(10).join(['• ' + r for r in sizing['size_notes']])}

🎯 TRADE PLAN
{format_trade_management_block(management)}

⚡ Clean execution conditions are present.
""".strip()


def format_discord_watchlist_alert(decision, context, discipline, sizing, management):
    timing = discipline["timing"]
    chasing_block = ""
    if timing["is_chasing"]:
        chasing_block = "\n🚫 YOU ARE CHASING\nDo not force premium execution here."

    return f"""
💎 PREMIUM WATCHLIST — {context.symbol}

Original Grade: {discipline['original_grade']}
Execution Status: {discipline['execution_grade']}
Timing: {timing['timing_label']}
Confidence: {sizing['confidence_score']}/100

📏 Size: {sizing['size_label']}

Price: {fmt_price(context.current_price)}
Trigger Level: {fmt_price(context.trigger_level)}
Distance From Trigger: {timing['distance_from_trigger_pct']}%
{chasing_block}

{chr(10).join(['• ' + r for r in discipline['reasons']])}

{chr(10).join(['• ' + r for r in sizing['size_notes']])}

🎯 MANAGEMENT VIEW
{format_trade_management_block(management)}

Patience > forcing entries.
Wait for reclaim, retest, or momentum confirmation.
""".strip()


def format_discord_free_teaser(decision, context, discipline, sizing):
    timing = discipline["timing"]
    return f"""
📊 MARKET INSIGHT — {context.symbol}

A strong setup is active.
Timing: {timing['timing_label']}
Confidence: {sizing['confidence_score']}/100
Key Level: {fmt_price(context.trigger_level)}

Join premium for execution access.
""".strip()


def format_discord_educational_alert(decision, context, discipline, sizing, management):
    timing = discipline["timing"]
    return f"""
📘 MARKET CONTEXT — {context.symbol}

Timing: {timing['timing_label']}
Confidence: {sizing['confidence_score']}/100
Suggested Size: {sizing['size_label']}

Price: {fmt_price(context.current_price)}
Key Level: {fmt_price(context.trigger_level)}

{chr(10).join(['• ' + r for r in discipline['reasons'][:5]])}

Management Levels:
• Invalidation: {fmt_price(management['invalidation'])}
• Trim 1: {fmt_price(management['trim_1'])}
• Trim 2: {fmt_price(management['trim_2'])}
• Runner: {fmt_price(management['runner_target'])}

This is informational, not confirmed execution.
""".strip()


# =========================
# ROUTING LOGIC
# =========================
def route_alerts(decision, context):
    discipline = apply_state_4_discipline(decision, context)
    sizing = calculate_confidence_and_size(decision, context, discipline)
    management = build_trade_management_plan(decision, context, discipline, sizing)

    execution_grade = discipline["execution_grade"]
    size_label = sizing["size_label"]

    if execution_grade in ["A+", "A"] and size_label in ["AGGRESSIVE", "NORMAL"]:
        send_telegram(format_telegram_alert(decision, context, discipline, sizing, management))
        send_discord_premium(format_discord_premium_alert(decision, context, discipline, sizing, management))
        send_discord_free(format_discord_free_teaser(decision, context, discipline, sizing))

    elif execution_grade == "WATCHLIST" or size_label == "NO EXECUTION":
        send_discord_premium(format_discord_watchlist_alert(decision, context, discipline, sizing, management))
        send_discord_free(format_discord_educational_alert(decision, context, discipline, sizing, management))

    elif execution_grade in ["B+", "B", "C"]:
        send_discord_premium(format_discord_watchlist_alert(decision, context, discipline, sizing, management))
        send_discord_free(format_discord_educational_alert(decision, context, discipline, sizing, management))

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
        current_price = 616.10
        trigger_level = 616.00

        entry_zone_low = 615.95
        entry_zone_high = 616.20
        atr_push = 0.12
        extension_pct = 0.08
        bars_since_breakout = 1
        momentum_confirmed = True
        retest_hold = True
        breakout_with_volume = True
        near_key_level = True
        above_vwap = True
        below_vwap = False

        oil_aligned = True
        market_breadth_aligned = True
        sector_aligned = True
        big_print_aligned = True

        direction = "LONG"
        support_1 = 615.70
        support_2 = 615.20
        resistance_1 = 616.60
        resistance_2 = 617.15

    decision = DummyDecision()
    context = DummyContext()
    route_alerts(decision, context)


# =========================
# MAIN
# =========================
if __name__ == "__main__":
    send_test_alert()

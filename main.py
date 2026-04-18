import os
import csv
import requests
from datetime import datetime, timedelta

# =========================
# ENV VARIABLES
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

DISCORD_WEBHOOK_PREMIUM = os.getenv("DISCORD_WEBHOOK_PREMIUM")
DISCORD_WEBHOOK_FREE = os.getenv("DISCORD_WEBHOOK_FREE")

# =========================
# FILE PATHS
# =========================
TRADE_LOG_FILE = "trade_log.csv"
CLOSED_TRADE_LOG_FILE = "closed_trade_log.csv"

# =========================
# GLOBAL TRADE STORE
# =========================
OPEN_TRADES = {}

# =========================
# SEND FUNCTIONS
# =========================
def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured")
        print("TELEGRAM_TOKEN exists:", bool(TELEGRAM_TOKEN))
        print("TELEGRAM_CHAT_ID exists:", bool(TELEGRAM_CHAT_ID))
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:
        r = requests.post(url, json=payload, timeout=10)
        print("Telegram status:", r.status_code)
        print("Telegram response:", r.text)
    except Exception as e:
        print(f"Telegram send failed: {e}")


def send_discord(webhook, message):
    if not webhook:
        print("Discord webhook missing")
        return
    try:
        r = requests.post(webhook, json={"content": message}, timeout=10)
        print("Discord status:", r.status_code)
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


def safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def pct_change(entry, current):
    try:
        entry = float(entry)
        current = float(current)
        if entry == 0:
            return 0.0
        return ((current - entry) / entry) * 100
    except Exception:
        return 0.0


def file_exists(path):
    return os.path.exists(path)


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_dt(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None

# =========================
# CSV / JOURNAL LOGGING
# =========================
def append_csv_row(path, fieldnames, row):
    file_already_exists = file_exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_already_exists:
            writer.writeheader()
        writer.writerow(row)


def log_open_trade(symbol, context, discipline, sizing, management, options_plan):
    row = {
        "timestamp": now_str(),
        "symbol": symbol,
        "direction": management["direction"],
        "execution_grade": discipline["execution_grade"],
        "original_grade": discipline["original_grade"],
        "timing_label": discipline["timing"]["timing_label"],
        "confidence_score": sizing["confidence_score"],
        "size_label": sizing["size_label"],
        "risk_multiplier": sizing["risk_multiplier"],
        "entry_underlying": safe_float(get_attr(context, "current_price", 0.0)),
        "trigger_level": safe_float(get_attr(context, "trigger_level", 0.0)),
        "entry_contract_price": safe_float(get_attr(context, "contract_price", 0.0)),
        "contract_type": options_plan["contract_type"],
        "contract_style": options_plan["contract_style"],
        "expiry_guidance": options_plan["expiry_guidance"],
        "moneyness": options_plan["moneyness"],
        "preferred_delta": options_plan["preferred_delta"],
        "invalidation": management["invalidation"],
        "trim_1": management["trim_1"],
        "trim_2": management["trim_2"],
        "runner_target": management["runner_target"],
        "breakeven_trigger": management["breakeven_trigger"],
        "reasons": " | ".join(discipline["reasons"]),
        "size_notes": " | ".join(sizing["size_notes"]),
        "options_notes": " | ".join(options_plan["reasons"]),
        "options_blockers": " | ".join(options_plan["blockers"]),
    }

    append_csv_row(TRADE_LOG_FILE, list(row.keys()), row)


def log_closed_trade(closed_row):
    append_csv_row(CLOSED_TRADE_LOG_FILE, list(closed_row.keys()), closed_row)

# =========================
# STATE 4 - ENTRY DISCIPLINE
# =========================
def evaluate_entry_timing(decision, context):
    current_price = safe_float(get_attr(context, "current_price", 0.0))
    trigger_level = safe_float(get_attr(context, "trigger_level", current_price))

    entry_zone_high = safe_float(get_attr(context, "entry_zone_high", trigger_level))
    entry_zone_low = safe_float(get_attr(context, "entry_zone_low", trigger_level))
    atr_push = safe_float(get_attr(context, "atr_push", 0.0))
    extension_pct = safe_float(get_attr(context, "extension_pct", 0.0))
    bars_since_breakout = int(get_attr(context, "bars_since_breakout", 0) or 0)
    momentum_confirmed = bool(get_attr(context, "momentum_confirmed", False))
    retest_hold = bool(get_attr(context, "retest_hold", False))
    breakout_with_volume = bool(get_attr(context, "breakout_with_volume", False))
    near_key_level = bool(get_attr(context, "near_key_level", True))
    above_vwap = bool(get_attr(context, "above_vwap", False))
    below_vwap = bool(get_attr(context, "below_vwap", False))

    distance_from_trigger_pct = 0.0
    if trigger_level != 0:
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
        not is_chasing and directional_alignment and (retest_hold or (breakout_with_volume and momentum_confirmed))
    )

    b_grade_execution_allowed = (
        not is_chasing and momentum_confirmed and directional_alignment and (retest_hold or breakout_with_volume)
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
    current_price = safe_float(get_attr(context, "current_price", 0.0))
    trigger_level = safe_float(get_attr(context, "trigger_level", current_price))

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
    atr_push = safe_float(get_attr(context, "atr_push", 0.20), 0.20)

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
        trim_plan = ["Take 25% off at Trim 1", "Take 35% off at Trim 2", "Leave 40% for runner"]
    elif size_label == "NORMAL":
        trim_plan = ["Take 33% off at Trim 1", "Take 33% off at Trim 2", "Leave 34% for runner"]
    elif size_label == "SMALL":
        trim_plan = ["Take 50% off at Trim 1", "Take 30% off at Trim 2", "Leave 20% for runner"]
    else:
        trim_plan = ["No execution plan active", "Wait for better location", "Do not force a position here"]

    move_stop_rule = f"Move stop to breakeven once price reaches {fmt_price(breakeven_trigger)}."

    management_notes = []
    if execution_grade == "WATCHLIST":
        management_notes.append("Execution downgraded to watchlist. Management plan is informational only.")
    if discipline["timing"]["is_chasing"]:
        management_notes.append("Late/chasing conditions detected. Avoid forcing entry.")
    else:
        management_notes.append("Entry timing is acceptable for structured trade management.")

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
# STATE 7 - OPTIONS CONTRACT ENGINE
# =========================
def build_options_contract_plan(decision, context, discipline, sizing, management):
    direction = management["direction"]
    symbol = str(get_attr(context, "symbol", "QQQ")).upper()
    execution_grade = discipline["execution_grade"]
    confidence_score = sizing["confidence_score"]
    size_label = sizing["size_label"]
    timing_label = discipline["timing"]["timing_label"]

    dte = int(get_attr(context, "dte", 0) or 0)
    option_spread_pct = safe_float(get_attr(context, "option_spread_pct", 0.0))
    option_volume_ok = bool(get_attr(context, "option_volume_ok", True))
    option_open_interest_ok = bool(get_attr(context, "option_open_interest_ok", True))
    iv_is_elevated = bool(get_attr(context, "iv_is_elevated", False))
    fast_move_expected = bool(get_attr(context, "fast_move_expected", True))
    contract_price = safe_float(get_attr(context, "contract_price", 0.0))
    contract_delta = get_attr(context, "contract_delta", None)

    reasons = []
    blockers = []

    if option_spread_pct > 12:
        blockers.append(f"Option spread too wide at {option_spread_pct:.1f}%.")
    if not option_volume_ok:
        blockers.append("Option volume is weak.")
    if not option_open_interest_ok:
        blockers.append("Open interest is weak.")

    contract_style = "BALANCED"
    expiry_guidance = "Use nearest liquid expiry."
    moneyness = "ATM"
    contract_type = "CALL" if direction == "LONG" else "PUT"
    options_execution_allowed = True

    if execution_grade == "WATCHLIST" or size_label == "NO EXECUTION":
        options_execution_allowed = False
        blockers.append("Underlying setup is not approved for execution.")

    if discipline["timing"]["is_chasing"]:
        options_execution_allowed = False
        blockers.append("Underlying timing is late/chasing for options execution.")

    if blockers:
        options_execution_allowed = False

    if confidence_score >= 85 and timing_label in ["IDEAL", "RETEST"] and fast_move_expected and not iv_is_elevated:
        contract_style = "AGGRESSIVE"
        moneyness = "SLIGHT OTM"
        expiry_guidance = "0DTE allowed if liquidity is strong."
        reasons.append("High-conviction setup allows more aggressive contract selection.")
    elif confidence_score >= 65 and timing_label in ["IDEAL", "CONFIRMED", "RETEST"]:
        contract_style = "BALANCED"
        moneyness = "ATM"
        expiry_guidance = "0DTE or next expiry is acceptable if spreads are clean."
        reasons.append("Balanced contract selection fits current setup quality.")
    else:
        contract_style = "SAFE"
        moneyness = "ATM or slight ITM"
        expiry_guidance = "Prefer next expiry over 0DTE."
        reasons.append("Safer contract profile is preferred due to lower conviction or weaker timing.")

    if iv_is_elevated and contract_style == "AGGRESSIVE":
        contract_style = "BALANCED"
        moneyness = "ATM"
        expiry_guidance = "Prefer ATM with cleaner pricing because IV is elevated."
        reasons.append("Downgraded from aggressive contract due to elevated IV.")

    if confidence_score < 60:
        contract_style = "SAFE"
        moneyness = "ATM or slight ITM"
        expiry_guidance = "Prefer next expiry. Avoid lottery contracts."
        reasons.append("Avoid cheap far OTM contracts on weaker setups.")

    if dte == 0 and confidence_score < 70:
        reasons.append("0DTE is only acceptable on strong alignment. Use caution here.")

    if contract_price > 0:
        if contract_price < 0.20 and contract_style != "AGGRESSIVE":
            reasons.append("Very cheap premium often behaves like lottery pricing. Avoid forcing it.")
        elif contract_price > 3.50 and confidence_score < 75:
            reasons.append("Premium is already expensive relative to current conviction.")

    if contract_delta is not None:
        try:
            delta_val = abs(float(contract_delta))
            if contract_style == "SAFE":
                preferred_delta = "0.55 to 0.70"
            elif contract_style == "BALANCED":
                preferred_delta = "0.40 to 0.60"
            else:
                preferred_delta = "0.25 to 0.45"
            reasons.append(f"Current observed delta: {delta_val:.2f}. Preferred delta zone: {preferred_delta}.")
        except Exception:
            preferred_delta = "0.40 to 0.60"
    else:
        if contract_style == "SAFE":
            preferred_delta = "0.55 to 0.70"
        elif contract_style == "BALANCED":
            preferred_delta = "0.40 to 0.60"
        else:
            preferred_delta = "0.25 to 0.45"

    if symbol in ["QQQ", "SPY"]:
        reasons.append(f"{symbol} is liquid enough for short-dated contracts when spreads are clean.")
    else:
        reasons.append("Use extra caution on non-index names because options can move less cleanly.")

    if not options_execution_allowed:
        contract_style = "NO EXECUTION"
        expiry_guidance = "Do not enter options yet."
        moneyness = "WAIT"
        preferred_delta = "WAIT"

    return {
        "contract_type": contract_type,
        "contract_style": contract_style,
        "expiry_guidance": expiry_guidance,
        "moneyness": moneyness,
        "preferred_delta": preferred_delta,
        "options_execution_allowed": options_execution_allowed,
        "reasons": reasons,
        "blockers": blockers
    }

# =========================
# STATE 8 - LIVE TRADE MANAGER
# =========================
def register_open_trade(symbol, context, discipline, sizing, management, options_plan):
    OPEN_TRADES[symbol] = {
        "symbol": symbol,
        "opened_at": now_str(),
        "direction": management["direction"],
        "entry_underlying": safe_float(get_attr(context, "current_price", 0.0)),
        "entry_contract_price": safe_float(get_attr(context, "contract_price", 0.0)),
        "execution_grade": discipline["execution_grade"],
        "original_grade": discipline["original_grade"],
        "timing_label": discipline["timing"]["timing_label"],
        "confidence_score": sizing["confidence_score"],
        "size_label": sizing["size_label"],
        "contract_type": options_plan["contract_type"],
        "contract_style": options_plan["contract_style"],
        "trim_1": management["trim_1"],
        "trim_2": management["trim_2"],
        "runner_target": management["runner_target"],
        "breakeven_trigger": management["breakeven_trigger"],
        "invalidation": management["invalidation"],
        "trim_1_hit": False,
        "trim_2_hit": False,
        "runner_hit": False,
        "breakeven_sent": False,
        "closed": False,
    }

    log_open_trade(symbol, context, discipline, sizing, management, options_plan)


def evaluate_open_trade(symbol, current_underlying_price, current_contract_price=None, close_trade=False):
    if symbol not in OPEN_TRADES:
        print(f"No open trade tracked for {symbol}")
        return None

    trade = OPEN_TRADES[symbol]
    if trade["closed"]:
        print(f"Trade for {symbol} already closed")
        return None

    direction = trade["direction"]
    entry_underlying = trade["entry_underlying"]
    entry_contract = trade["entry_contract_price"]

    current_underlying_price = safe_float(current_underlying_price)
    current_contract_price = safe_float(current_contract_price, entry_contract)

    if direction == "LONG":
        underlying_pnl_pct = pct_change(entry_underlying, current_underlying_price)
    else:
        underlying_pnl_pct = pct_change(entry_underlying, current_underlying_price) * -1

    contract_pnl_pct = 0.0
    if entry_contract > 0:
        contract_pnl_pct = pct_change(entry_contract, current_contract_price)

    alerts = []

    if direction == "LONG":
        if (not trade["trim_1_hit"]) and current_underlying_price >= trade["trim_1"]:
            trade["trim_1_hit"] = True
            alerts.append(f"✅ {symbol} Trim 1 hit at {fmt_price(trade['trim_1'])}")
        if (not trade["trim_2_hit"]) and current_underlying_price >= trade["trim_2"]:
            trade["trim_2_hit"] = True
            alerts.append(f"✅ {symbol} Trim 2 hit at {fmt_price(trade['trim_2'])}")
        if (not trade["runner_hit"]) and current_underlying_price >= trade["runner_target"]:
            trade["runner_hit"] = True
            alerts.append(f"🏁 {symbol} Runner target hit at {fmt_price(trade['runner_target'])}")
        if (not trade["breakeven_sent"]) and current_underlying_price >= trade["breakeven_trigger"]:
            trade["breakeven_sent"] = True
            alerts.append(f"🛡️ {symbol} Move stop to breakeven now")
        if current_underlying_price <= trade["invalidation"]:
            alerts.append(f"❌ {symbol} invalidation lost at {fmt_price(trade['invalidation'])}")
            close_trade = True
    else:
        if (not trade["trim_1_hit"]) and current_underlying_price <= trade["trim_1"]:
            trade["trim_1_hit"] = True
            alerts.append(f"✅ {symbol} Trim 1 hit at {fmt_price(trade['trim_1'])}")
        if (not trade["trim_2_hit"]) and current_underlying_price <= trade["trim_2"]:
            trade["trim_2_hit"] = True
            alerts.append(f"✅ {symbol} Trim 2 hit at {fmt_price(trade['trim_2'])}")
        if (not trade["runner_hit"]) and current_underlying_price <= trade["runner_target"]:
            trade["runner_hit"] = True
            alerts.append(f"🏁 {symbol} Runner target hit at {fmt_price(trade['runner_target'])}")
        if (not trade["breakeven_sent"]) and current_underlying_price <= trade["breakeven_trigger"]:
            trade["breakeven_sent"] = True
            alerts.append(f"🛡️ {symbol} Move stop to breakeven now")
        if current_underlying_price >= trade["invalidation"]:
            alerts.append(f"❌ {symbol} invalidation lost at {fmt_price(trade['invalidation'])}")
            close_trade = True

    if close_trade:
        trade["closed"] = True

        win_loss = "WIN" if contract_pnl_pct > 0 else "LOSS"
        closed_row = {
            "closed_at": now_str(),
            "symbol": symbol,
            "direction": direction,
            "execution_grade": trade["execution_grade"],
            "original_grade": trade["original_grade"],
            "timing_label": trade["timing_label"],
            "confidence_score": trade["confidence_score"],
            "size_label": trade["size_label"],
            "contract_type": trade["contract_type"],
            "contract_style": trade["contract_style"],
            "entry_underlying": entry_underlying,
            "exit_underlying": current_underlying_price,
            "underlying_pnl_pct": round(underlying_pnl_pct, 2),
            "entry_contract_price": entry_contract,
            "exit_contract_price": current_contract_price,
            "contract_pnl_pct": round(contract_pnl_pct, 2),
            "result": win_loss,
            "trim_1_hit": trade["trim_1_hit"],
            "trim_2_hit": trade["trim_2_hit"],
            "runner_hit": trade["runner_hit"],
        }
        log_closed_trade(closed_row)

    summary = {
        "symbol": symbol,
        "direction": direction,
        "entry_underlying": entry_underlying,
        "current_underlying": current_underlying_price,
        "underlying_pnl_pct": round(underlying_pnl_pct, 2),
        "entry_contract": entry_contract,
        "current_contract": current_contract_price,
        "contract_pnl_pct": round(contract_pnl_pct, 2),
        "alerts": alerts,
        "trim_1_hit": trade["trim_1_hit"],
        "trim_2_hit": trade["trim_2_hit"],
        "runner_hit": trade["runner_hit"],
        "breakeven_sent": trade["breakeven_sent"],
        "closed": trade["closed"],
    }

    return summary

# =========================
# REPORT / DASHBOARD ENGINE
# =========================
def load_closed_trades():
    if not file_exists(CLOSED_TRADE_LOG_FILE):
        return []

    rows = []
    with open(CLOSED_TRADE_LOG_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def filter_rows_by_days(rows, days):
    cutoff = datetime.now() - timedelta(days=days)
    out = []
    for row in rows:
        dt = parse_dt(row.get("closed_at", ""))
        if dt and dt >= cutoff:
            out.append(row)
    return out


def summarize_bucket(rows, key_name):
    bucket = {}
    for row in rows:
        key = row.get(key_name, "UNKNOWN")
        pnl = safe_float(row.get("contract_pnl_pct", 0.0))
        if key not in bucket:
            bucket[key] = {"count": 0, "wins": 0, "losses": 0, "pnl": 0.0}
        bucket[key]["count"] += 1
        bucket[key]["pnl"] += pnl
        if row.get("result") == "WIN":
            bucket[key]["wins"] += 1
        else:
            bucket[key]["losses"] += 1
    return bucket


def find_best_and_worst(bucket):
    if not bucket:
        return None, None
    items = list(bucket.items())
    best = max(items, key=lambda x: x[1]["pnl"])
    worst = min(items, key=lambda x: x[1]["pnl"])
    return best, worst


def build_stats(rows):
    if not rows:
        return None

    total_trades = len(rows)
    wins = sum(1 for r in rows if r.get("result") == "WIN")
    losses = total_trades - wins
    total_contract_pnl = round(sum(safe_float(r.get("contract_pnl_pct", 0.0)) for r in rows), 2)
    avg_contract_pnl = round(total_contract_pnl / total_trades, 2) if total_trades else 0.0
    win_rate = round((wins / total_trades) * 100, 2) if total_trades else 0.0

    top_winner = max(rows, key=lambda r: safe_float(r.get("contract_pnl_pct", 0.0)))
    top_loser = min(rows, key=lambda r: safe_float(r.get("contract_pnl_pct", 0.0)))

    by_grade = summarize_bucket(rows, "execution_grade")
    by_symbol = summarize_bucket(rows, "symbol")
    by_style = summarize_bucket(rows, "contract_style")

    best_grade, worst_grade = find_best_and_worst(by_grade)
    best_symbol, worst_symbol = find_best_and_worst(by_symbol)
    best_style, worst_style = find_best_and_worst(by_style)

    return {
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_contract_pnl": total_contract_pnl,
        "avg_contract_pnl": avg_contract_pnl,
        "top_winner": top_winner,
        "top_loser": top_loser,
        "by_grade": by_grade,
        "by_symbol": by_symbol,
        "by_style": by_style,
        "best_grade": best_grade,
        "worst_grade": worst_grade,
        "best_symbol": best_symbol,
        "worst_symbol": worst_symbol,
        "best_style": best_style,
        "worst_style": worst_style,
    }


def build_dashboard_snapshot(rows, label="ALL TIME"):
    stats = build_stats(rows)
    if not stats:
        return f"📊 UNBIASED BOT DASHBOARD — {label}\nNo closed trades logged yet."

    return f"""
📊 UNBIASED BOT DASHBOARD — {label}

Trades: {stats['total_trades']}
Wins: {stats['wins']}
Losses: {stats['losses']}
Win Rate: {stats['win_rate']}%
Total Contract PnL: {stats['total_contract_pnl']}%
Average Contract PnL: {stats['avg_contract_pnl']}%

Top Winner:
- {stats['top_winner'].get('symbol')} | {stats['top_winner'].get('execution_grade')} | {stats['top_winner'].get('contract_pnl_pct')}%

Top Loser:
- {stats['top_loser'].get('symbol')} | {stats['top_loser'].get('execution_grade')} | {stats['top_loser'].get('contract_pnl_pct')}%

Best Grade:
- {stats['best_grade'][0]} | total PnL {round(stats['best_grade'][1]['pnl'], 2)}%

Worst Grade:
- {stats['worst_grade'][0]} | total PnL {round(stats['worst_grade'][1]['pnl'], 2)}%

Best Symbol:
- {stats['best_symbol'][0]} | total PnL {round(stats['best_symbol'][1]['pnl'], 2)}%

Worst Symbol:
- {stats['worst_symbol'][0]} | total PnL {round(stats['worst_symbol'][1]['pnl'], 2)}%

Best Contract Style:
- {stats['best_style'][0]} | total PnL {round(stats['best_style'][1]['pnl'], 2)}%

Worst Contract Style:
- {stats['worst_style'][0]} | total PnL {round(stats['worst_style'][1]['pnl'], 2)}%
""".strip()


def build_weekly_report():
    rows = filter_rows_by_days(load_closed_trades(), 7)
    stats = build_stats(rows)
    if not stats:
        return "📬 WEEKLY REPORT\nNo closed trades in the last 7 days."

    grade_lines = []
    for grade, data in stats["by_grade"].items():
        grade_lines.append(
            f"- {grade}: {data['count']} trades | W {data['wins']} / L {data['losses']} | total {round(data['pnl'], 2)}%"
        )

    symbol_lines = []
    for symbol, data in stats["by_symbol"].items():
        symbol_lines.append(
            f"- {symbol}: {data['count']} trades | W {data['wins']} / L {data['losses']} | total {round(data['pnl'], 2)}%"
        )

    return f"""
📬 UNBIASED BOT WEEKLY REPORT

Period: Last 7 Days
Closed Trades: {stats['total_trades']}
Wins: {stats['wins']}
Losses: {stats['losses']}
Win Rate: {stats['win_rate']}%
Total Contract PnL: {stats['total_contract_pnl']}%
Average Contract PnL: {stats['avg_contract_pnl']}%

Best Grade:
- {stats['best_grade'][0]} | total PnL {round(stats['best_grade'][1]['pnl'], 2)}%

Worst Grade:
- {stats['worst_grade'][0]} | total PnL {round(stats['worst_grade'][1]['pnl'], 2)}%

Best Symbol:
- {stats['best_symbol'][0]} | total PnL {round(stats['best_symbol'][1]['pnl'], 2)}%

Worst Symbol:
- {stats['worst_symbol'][0]} | total PnL {round(stats['worst_symbol'][1]['pnl'], 2)}%

By Grade:
{chr(10).join(grade_lines)}

By Symbol:
{chr(10).join(symbol_lines)}

Top Winner:
- {stats['top_winner'].get('symbol')} | {stats['top_winner'].get('execution_grade')} | {stats['top_winner'].get('contract_pnl_pct')}%

Top Loser:
- {stats['top_loser'].get('symbol')} | {stats['top_loser'].get('execution_grade')} | {stats['top_loser'].get('contract_pnl_pct')}%
""".strip()


def build_daily_report():
    rows = filter_rows_by_days(load_closed_trades(), 1)
    stats = build_stats(rows)
    if not stats:
        return "🗓️ DAILY REPORT\nNo closed trades in the last 24 hours."

    return f"""
🗓️ UNBIASED BOT DAILY REPORT

Period: Last 24 Hours
Closed Trades: {stats['total_trades']}
Wins: {stats['wins']}
Losses: {stats['losses']}
Win Rate: {stats['win_rate']}%
Total Contract PnL: {stats['total_contract_pnl']}%
Average Contract PnL: {stats['avg_contract_pnl']}%

Best Symbol:
- {stats['best_symbol'][0]} | total PnL {round(stats['best_symbol'][1]['pnl'], 2)}%

Best Grade:
- {stats['best_grade'][0]} | total PnL {round(stats['best_grade'][1]['pnl'], 2)}%

Top Winner:
- {stats['top_winner'].get('symbol')} | {stats['top_winner'].get('contract_pnl_pct')}%

Top Loser:
- {stats['top_loser'].get('symbol')} | {stats['top_loser'].get('contract_pnl_pct')}%
""".strip()


def build_email_ready_weekly_body():
    return f"""
UNBIASED BOT WEEKLY PERFORMANCE REPORT

Generated: {now_str()}

{build_weekly_report()}

{build_dashboard_snapshot(filter_rows_by_days(load_closed_trades(), 7), label="LAST 7 DAYS")}
""".strip()

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


def format_options_block(options_plan):
    lines = [
        f"Contract Type: {options_plan['contract_type']}",
        f"Contract Style: {options_plan['contract_style']}",
        f"Expiry Guidance: {options_plan['expiry_guidance']}",
        f"Moneyness: {options_plan['moneyness']}",
        f"Preferred Delta: {options_plan['preferred_delta']}",
    ]

    if options_plan["reasons"]:
        lines.append("")
        lines.append("Options Notes:")
        lines.extend([f"- {x}" for x in options_plan["reasons"]])

    if options_plan["blockers"]:
        lines.append("")
        lines.append("Options Blockers:")
        lines.extend([f"- {x}" for x in options_plan["blockers"]])

    return "\n".join(lines)


def format_telegram_alert(decision, context, discipline, sizing, management, options_plan):
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

Options Plan:
{format_options_block(options_plan)}

Time: {now_str()}
""".strip()


def format_discord_premium_alert(decision, context, discipline, sizing, management, options_plan):
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

🧠 OPTIONS PLAN
{format_options_block(options_plan)}

⚡ Clean execution conditions are present.
""".strip()


def format_discord_watchlist_alert(decision, context, discipline, sizing, management, options_plan):
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

🧠 OPTIONS VIEW
{format_options_block(options_plan)}

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


def format_discord_educational_alert(decision, context, discipline, sizing, management, options_plan):
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

Options View:
• Type: {options_plan['contract_type']}
• Style: {options_plan['contract_style']}
• Moneyness: {options_plan['moneyness']}

This is informational, not confirmed execution.
""".strip()


def format_live_management_update(summary):
    lines = [
        f"📈 LIVE TRADE UPDATE — {summary['symbol']}",
        f"Direction: {summary['direction']}",
        f"Underlying Entry: {fmt_price(summary['entry_underlying'])}",
        f"Underlying Now: {fmt_price(summary['current_underlying'])}",
        f"Underlying PnL: {summary['underlying_pnl_pct']}%",
    ]

    if summary["entry_contract"] > 0:
        lines.extend([
            f"Contract Entry: {fmt_price(summary['entry_contract'])}",
            f"Contract Now: {fmt_price(summary['current_contract'])}",
            f"Contract PnL: {summary['contract_pnl_pct']}%",
        ])

    lines.append("")
    lines.append("Status:")
    lines.append(f"- Trim 1 hit: {summary['trim_1_hit']}")
    lines.append(f"- Trim 2 hit: {summary['trim_2_hit']}")
    lines.append(f"- Runner hit: {summary['runner_hit']}")
    lines.append(f"- Breakeven sent: {summary['breakeven_sent']}")
    lines.append(f"- Closed: {summary['closed']}")

    if summary["alerts"]:
        lines.append("")
        lines.append("Triggered Alerts:")
        lines.extend([f"- {a}" for a in summary["alerts"]])

    return "\n".join(lines)

# =========================
# ROUTING LOGIC
# =========================
def route_alerts(decision, context):
    discipline = apply_state_4_discipline(decision, context)
    sizing = calculate_confidence_and_size(decision, context, discipline)
    management = build_trade_management_plan(decision, context, discipline, sizing)
    options_plan = build_options_contract_plan(decision, context, discipline, sizing, management)

    execution_grade = discipline["execution_grade"]
    size_label = sizing["size_label"]
    options_allowed = options_plan["options_execution_allowed"]

    print("=== ROUTE DEBUG ===")
    print("execution_grade:", execution_grade)
    print("size_label:", size_label)
    print("options_allowed:", options_allowed)
    print("===================")

    symbol = str(get_attr(context, "symbol", "QQQ")).upper()

    if execution_grade in ["A+", "A"] and size_label in ["AGGRESSIVE", "NORMAL"] and options_allowed:
        register_open_trade(symbol, context, discipline, sizing, management, options_plan)
        send_telegram(format_telegram_alert(decision, context, discipline, sizing, management, options_plan))
        send_discord_premium(format_discord_premium_alert(decision, context, discipline, sizing, management, options_plan))
        send_discord_free(format_discord_free_teaser(decision, context, discipline, sizing))

    elif execution_grade == "WATCHLIST" or size_label == "NO EXECUTION" or not options_allowed:
        send_discord_premium(format_discord_watchlist_alert(decision, context, discipline, sizing, management, options_plan))
        send_discord_free(format_discord_educational_alert(decision, context, discipline, sizing, management, options_plan))

    elif execution_grade in ["B+", "B", "C"]:
        send_discord_premium(format_discord_watchlist_alert(decision, context, discipline, sizing, management, options_plan))
        send_discord_free(format_discord_educational_alert(decision, context, discipline, sizing, management, options_plan))

    elif execution_grade == "AVOID":
        print(f"[AVOID] No alert sent for {symbol}")

# =========================
# LIVE MANAGER ROUTE
# =========================
def send_live_trade_update(symbol, current_underlying_price, current_contract_price=None, close_trade=False):
    summary = evaluate_open_trade(symbol, current_underlying_price, current_contract_price, close_trade=close_trade)
    if not summary:
        return

    msg = format_live_management_update(summary)
    send_telegram(msg)
    send_discord_premium(msg)

# =========================
# REPORT ROUTES
# =========================
def send_performance_summary():
    msg = build_dashboard_snapshot(load_closed_trades(), label="ALL TIME")
    send_telegram(msg)
    send_discord_premium(msg)


def send_daily_report():
    msg = build_daily_report()
    send_telegram(msg)
    send_discord_premium(msg)


def send_weekly_report():
    msg = build_weekly_report()
    send_telegram(msg)
    send_discord_premium(msg)


def print_email_ready_weekly_body():
    body = build_email_ready_weekly_body()
    print("\n=== EMAIL READY WEEKLY BODY ===\n")
    print(body)
    print("\n===============================\n")

# =========================
# TESTS
# =========================
def test_telegram_only():
    send_telegram("✅ UNBIASED BOT TELEGRAM TEST MESSAGE")


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

        dte = 0
        option_spread_pct = 4.5
        option_volume_ok = True
        option_open_interest_ok = True
        iv_is_elevated = False
        fast_move_expected = True
        contract_price = 1.45
        contract_delta = 0.49

    route_alerts(DummyDecision(), DummyContext())


def test_live_manager():
    send_live_trade_update("QQQ", 616.65, 1.92)
    send_live_trade_update("QQQ", 617.18, 2.45)
    send_live_trade_update("QQQ", 617.55, 2.90, close_trade=True)


def test_reports():
    send_performance_summary()
    send_daily_report()
    send_weekly_report()
    print_email_ready_weekly_body()

# =========================
# MAIN
# =========================
# =========================
# STATE 10.1 - COMMAND ROUTER
# =========================

BOT_MODE = os.getenv("BOT_MODE", "test_all").strip().lower()

def run_trade_alert_mode():
    send_test_alert()

def run_live_update_mode():
    test_live_manager()

def run_daily_report_mode():
    send_daily_report()

def run_weekly_report_mode():
    send_weekly_report()

def run_dashboard_mode():
    send_performance_summary()

def run_test_all_mode():
    test_telegram_only()
    send_test_alert()
    test_live_manager()
    test_reports()

def run_bot_mode():
    print(f"BOT_MODE = {BOT_MODE}")

    if BOT_MODE == "trade_alert":
        run_trade_alert_mode()
    elif BOT_MODE == "live_update":
        run_live_update_mode()
    elif BOT_MODE == "daily_report":
        run_daily_report_mode()
    elif BOT_MODE == "weekly_report":
        run_weekly_report_mode()
    elif BOT_MODE == "dashboard":
        run_dashboard_mode()
    else:
        run_test_all_mode()
# =========================
# STATE 11 - LOG BACKUP + PERSISTENCE + COMMAND ROUTER
# =========================

BOT_MODE = os.getenv("BOT_MODE", "test_all").strip().lower()


def run_trade_alert_mode():
    send_test_alert()


def run_live_update_mode():
    test_live_manager()


def run_daily_report_mode():
    send_daily_report()


def run_weekly_report_mode():
    send_weekly_report()


def run_dashboard_mode():
    send_performance_summary()


def run_test_all_mode():
    test_telegram_only()
    send_test_alert()
    test_live_manager()
    test_reports()


def run_bot_mode():
    print(f"BOT_MODE = {BOT_MODE}")

    if BOT_MODE == "trade_alert":
        run_trade_alert_mode()
    elif BOT_MODE == "live_update":
        run_live_update_mode()
    elif BOT_MODE == "daily_report":
        run_daily_report_mode()
    elif BOT_MODE == "weekly_report":
        run_weekly_report_mode()
    elif BOT_MODE == "dashboard":
        run_dashboard_mode()
    else:
        run_test_all_mode()


def save_logs_to_artifact_folder():
    """
    Copies logs into an artifacts folder so GitHub Actions can upload them.
    """
    folder = "artifacts"
    os.makedirs(folder, exist_ok=True)

    files_to_save = [TRADE_LOG_FILE, CLOSED_TRADE_LOG_FILE]

    for f in files_to_save:
        if os.path.exists(f):
            try:
                with open(f, "r", encoding="utf-8") as src:
                    data = src.read()

                with open(os.path.join(folder, f), "w", encoding="utf-8") as dst:
                    dst.write(data)

                print(f"Saved {f} to artifacts/")
            except Exception as e:
                print(f"Error saving {f}: {e}")
        else:
            print(f"{f} not found — nothing to save")


def load_logs_if_exist():
    """
    Ensures CSV files exist so system doesn't break on first run.
    """
    for f in [TRADE_LOG_FILE, CLOSED_TRADE_LOG_FILE]:
        if not os.path.exists(f):
            with open(f, "w", encoding="utf-8") as file:
                file.write("")
            print(f"Created empty {f}")


def end_of_run_cleanup():
    """
    Runs at end of every execution
    """
    print("\n=== END OF RUN CLEANUP ===")
    save_logs_to_artifact_folder()
    print("Logs prepared for upload")


if __name__ == "__main__":
    load_logs_if_exist()
    run_bot_mode()
    end_of_run_cleanup()

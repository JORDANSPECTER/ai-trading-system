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

SYMBOL = os.getenv("SYMBOL", "QQQ").strip().upper()
SECONDARY_SYMBOL = os.getenv("SECONDARY_SYMBOL", "SPY").strip().upper()
OIL_SYMBOL = os.getenv("OIL_SYMBOL", "USO").strip().upper()


# ======================
# HELPERS
# ======================

def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def to_float(value, default=0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


# ======================
# DATA FETCH
# ======================

def get_quote(symbol: str) -> dict:
    url = "https://api.twelvedata.com/quote"
    params = {"symbol": symbol, "apikey": TWELVE_DATA_API_KEY}

    r = requests.get(url, params=params, timeout=20)
    data = r.json()

    if "close" not in data and "price" not in data:
        raise Exception(f"Bad API response for {symbol}: {data}")

    return data


def get_time_series(symbol: str, interval: str = "5min", outputsize: int = 40) -> list:
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": TWELVE_DATA_API_KEY,
    }

    r = requests.get(url, params=params, timeout=20)
    data = r.json()

    if "values" not in data:
        raise Exception(f"Bad time series response for {symbol}: {data}")

    values = data["values"]
    values.reverse()
    return values


# ======================
# CANDLE HELPERS
# ======================

def candle_open(bar: dict) -> float:
    return to_float(bar.get("open"))


def candle_close(bar: dict) -> float:
    return to_float(bar.get("close"))


def candle_high(bar: dict) -> float:
    return to_float(bar.get("high"))


def candle_low(bar: dict) -> float:
    return to_float(bar.get("low"))


def candle_volume(bar: dict) -> float:
    return to_float(bar.get("volume"))


# ======================
# ALERT SENDERS
# ======================

def send_discord(webhook_url: str, msg: str, label: str) -> None:
    if not webhook_url:
        log(f"{label}: Missing Discord webhook, skipping.")
        return

    payload = {"content": msg[:1900]}
    r = requests.post(webhook_url, json=payload, timeout=20)

    log(f"{label}: Discord status {r.status_code}")
    log(f"{label}: Discord response {r.text[:200]}")

    if not (200 <= r.status_code < 300):
        raise Exception(f"{label}: Discord failed {r.status_code} | {r.text}")


def send_telegram(msg: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("Telegram credentials missing, skipping.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg[:4000]}
    r = requests.post(url, data=payload, timeout=20)

    log(f"Telegram status: {r.status_code}")

    if not (200 <= r.status_code < 300):
        raise Exception(f"Telegram failed {r.status_code} | {r.text}")


# ======================
# INDICATORS
# ======================

def calc_vwap(bars: list) -> float:
    total_pv = 0.0
    total_vol = 0.0

    for bar in bars:
        high_ = candle_high(bar)
        low_ = candle_low(bar)
        close_ = candle_close(bar)
        vol_ = candle_volume(bar)

        typical_price = (high_ + low_ + close_) / 3.0
        total_pv += typical_price * vol_
        total_vol += vol_

    if total_vol == 0:
        return 0.0

    return total_pv / total_vol


def calc_rsi(closes: list, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0

    gains = []
    losses = []

    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(change))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


# ======================
# LEVELS
# ======================

def round_level(price: float) -> float:
    return round(price, 2)


def nearest_level(price: float, levels: list) -> float:
    if not levels:
        return 0.0
    return min(levels, key=lambda x: abs(x - price))


def distance_pct(price: float, level: float) -> float:
    if level == 0:
        return 999.0
    return abs(price - level) / level * 100.0


def build_key_levels(quote: dict, bars: list) -> dict:
    day_high = round_level(to_float(quote.get("high")))
    day_low = round_level(to_float(quote.get("low")))
    prev_close = round_level(to_float(quote.get("previous_close")))
    open_price = round_level(to_float(quote.get("open")))

    highs = [candle_high(b) for b in bars[-12:]] if bars else []
    lows = [candle_low(b) for b in bars[-12:]] if bars else []

    recent_high = round_level(max(highs)) if highs else day_high
    recent_low = round_level(min(lows)) if lows else day_low

    supports = sorted(list(set([day_low, prev_close, recent_low])))
    resistances = sorted(list(set([day_high, open_price, recent_high])))

    return {
        "day_high": day_high,
        "day_low": day_low,
        "prev_close": prev_close,
        "open_price": open_price,
        "recent_high": recent_high,
        "recent_low": recent_low,
        "supports": supports,
        "resistances": resistances,
    }


# ======================
# STRUCTURE / SETUPS
# ======================

def detect_structure(bars: list, current_price: float, vwap: float, levels: dict) -> dict:
    if len(bars) < 4:
        return {
            "trend": "UNKNOWN",
            "setup": "NOT ENOUGH DATA",
            "volume_signal": "UNKNOWN",
            "near_support": False,
            "near_resistance": False,
            "nearest_support": 0.0,
            "nearest_resistance": 0.0,
        }

    b1, b2, b3, b4 = bars[-4], bars[-3], bars[-2], bars[-1]

    h2, h3, h4 = candle_high(b2), candle_high(b3), candle_high(b4)
    l2, l3, l4 = candle_low(b2), candle_low(b3), candle_low(b4)
    c4 = candle_close(b4)
    v2, v3, v4 = candle_volume(b2), candle_volume(b3), candle_volume(b4)

    higher_lows = l4 > l3 >= l2
    lower_highs = h4 < h3 <= h2
    breakout = c4 > h3
    breakdown = c4 < l3
    strong_volume = v4 > max(v2, v3)

    supports = levels["supports"] + [vwap]
    resistances = levels["resistances"] + [vwap]

    nearest_support_val = nearest_level(current_price, supports)
    nearest_resistance_val = nearest_level(current_price, resistances)

    near_support = distance_pct(current_price, nearest_support_val) <= 0.20
    near_resistance = distance_pct(current_price, nearest_resistance_val) <= 0.20

    above_vwap = current_price > vwap
    below_vwap = current_price < vwap

    if higher_lows and breakout and above_vwap:
        trend = "BULLISH"
        setup = "BREAK AND HOLD"
    elif higher_lows and near_support and above_vwap:
        trend = "BULLISH"
        setup = "RETEST HOLD"
    elif lower_highs and breakdown and below_vwap:
        trend = "BEARISH"
        setup = "BREAKDOWN AND HOLD"
    elif lower_highs and near_resistance and below_vwap:
        trend = "BEARISH"
        setup = "REJECTION"
    elif lower_highs and below_vwap:
        trend = "BEARISH LEAN"
        setup = "FAILED BOUNCE"
    elif higher_lows and above_vwap:
        trend = "BULLISH LEAN"
        setup = "WAIT FOR BREAK CONFIRMATION"
    else:
        trend = "CHOPPY"
        setup = "NO CLEAN STRUCTURE"

    volume_signal = "STRONG" if strong_volume else "NORMAL"

    return {
        "trend": trend,
        "setup": setup,
        "volume_signal": volume_signal,
        "near_support": near_support,
        "near_resistance": near_resistance,
        "nearest_support": nearest_support_val,
        "nearest_resistance": nearest_resistance_val,
    }


def build_trade_plan(structure: dict, levels: dict, vwap: float) -> dict:
    plan = {
        "entry": "WAIT",
        "stop": "N/A",
        "target": "N/A",
    }

    support = levels["recent_low"]
    resistance = levels["recent_high"]

    if structure["setup"] == "BREAK AND HOLD":
        plan["entry"] = f"Break above {resistance:.2f} and hold"
        plan["stop"] = f"Below {vwap:.2f}"
        plan["target"] = f"{resistance + 1:.2f}+"
    elif structure["setup"] == "RETEST HOLD":
        plan["entry"] = f"Hold above {support:.2f} after retest"
        plan["stop"] = f"Below {support:.2f}"
        plan["target"] = f"{resistance:.2f}"
    elif structure["setup"] == "REJECTION":
        plan["entry"] = f"Reject at {resistance:.2f}"
        plan["stop"] = f"Above {resistance:.2f}"
        plan["target"] = f"{support:.2f}"
    elif structure["setup"] == "FAILED BOUNCE":
        plan["entry"] = f"Lower high below {vwap:.2f}"
        plan["stop"] = "Above VWAP"
        plan["target"] = f"{support:.2f}"
    elif structure["setup"] == "BREAKDOWN AND HOLD":
        plan["entry"] = f"Break below {support:.2f} and hold"
        plan["stop"] = f"Above {vwap:.2f}"
        plan["target"] = f"{support - 1:.2f}"

    return plan


def grade_trade(structure: dict, vwap: float, rsi: float, current_price: float) -> tuple[str, bool]:
    score = 0
    chase = False

    above_vwap = current_price > vwap
    below_vwap = current_price < vwap

    setup = structure.get("setup", "")
    volume_signal = structure.get("volume_signal", "NORMAL")

    bullish_setups = ["BREAK AND HOLD", "RETEST HOLD", "WAIT FOR BREAK CONFIRMATION"]
    bearish_setups = ["BREAKDOWN AND HOLD", "REJECTION", "FAILED BOUNCE"]

    if setup == "BREAK AND HOLD":
        score += 4
    elif setup == "RETEST HOLD":
        score += 4
    elif setup == "BREAKDOWN AND HOLD":
        score += 4
    elif setup == "REJECTION":
        score += 4
    elif setup == "FAILED BOUNCE":
        score += 3
    elif setup == "WAIT FOR BREAK CONFIRMATION":
        score += 3
    elif setup == "NO CLEAN STRUCTURE":
        score += 0

    if setup in bullish_setups and above_vwap:
        score += 3
    elif setup in bearish_setups and below_vwap:
        score += 3
    else:
        score += 1

    if volume_signal == "STRONG":
        score += 2
    else:
        score += 1

    if setup in bullish_setups:
        if 45 <= rsi <= 72:
            score += 3
        elif 35 <= rsi <= 78:
            score += 2
        elif rsi > 78:
            chase = True
        else:
            score += 1

    elif setup in bearish_setups:
        if 28 <= rsi <= 58:
            score += 3
        elif 22 <= rsi <= 70:
            score += 2
        elif rsi < 22:
            chase = True
        else:
            score += 1

    if chase:
        return "AVOID", True

    if score >= 11:
        return "A+", False
    elif score >= 9:
        return "A", False
    elif score >= 7:
        return "B", False
    else:
        return "C", False


# ======================
# MESSAGE BUILDERS
# ======================

def build_premium_context(
    qqq_data: dict,
    spy_data: dict,
    oil_data: dict,
    structure: dict,
    vwap: float,
    rsi: float,
    levels: dict,
) -> dict:
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

    above_vwap = qqq > vwap
    below_vwap = qqq < vwap

    if qqq_change > 0 and spy_change > 0:
        reasons.append("QQQ and SPY are both green on the day.")
    if qqq_change < 0 and spy_change < 0:
        reasons.append("QQQ and SPY are both red on the day.")
    if oil_change > 0:
        reasons.append("Oil is pushing higher.")
    if oil_change < 0:
        reasons.append("Oil is easing lower.")

    if above_vwap:
        reasons.append("Price is above VWAP.")
    if below_vwap:
        reasons.append("Price is below VWAP.")

    reasons.append(f"Setup: {structure['setup']}")
    reasons.append(f"Volume Signal: {structure['volume_signal']}")
    reasons.append(f"Nearest Support: {structure['nearest_support']:.2f}")
    reasons.append(f"Nearest Resistance: {structure['nearest_resistance']:.2f}")
    reasons.append(f"RSI: {rsi:.1f}")

    grade, chase = grade_trade(structure, vwap, rsi, qqq)

    reasons.append(
        f"Grade Engine Input -> setup={structure['setup']}, "
        f"volume={structure['volume_signal']}, "
        f"above_vwap={qqq > vwap}, "
        f"below_vwap={qqq < vwap}"
    )

    if grade in ["A+", "A"]:
        if structure["trend"] in ["BULLISH", "BULLISH LEAN"]:
            bias = "BULLISH"
            action = "CALL IDEA"
            reasons.append("High-quality bullish alignment.")
        elif structure["trend"] in ["BEARISH", "BEARISH LEAN"]:
            bias = "BEARISH"
            action = "PUT IDEA"
            reasons.append("High-quality bearish alignment.")

    elif grade == "B":
        if structure["trend"] in ["BULLISH", "BULLISH LEAN"]:
            bias = "BULLISH"
            action = "CALL IDEA (LOWER QUALITY)"
            reasons.append("Usable bullish setup, but not ideal.")
        elif structure["trend"] in ["BEARISH", "BEARISH LEAN"]:
            bias = "BEARISH"
            action = "PUT IDEA (LOWER QUALITY)"
            reasons.append("Usable bearish setup, but not ideal.")
        else:
            bias = "MIXED"
            action = "WAIT FOR CONFIRMATION"
            reasons.append("Setup is only partially aligned.")

    elif grade == "AVOID":
        if structure["trend"] in ["BULLISH", "BULLISH LEAN"]:
            bias = "BULLISH"
        elif structure["trend"] in ["BEARISH", "BEARISH LEAN"]:
            bias = "BEARISH"
        else:
            bias = "MIXED"

        action = "🚨 YOU ARE CHASING — WAIT"
        reasons.append("Setup is extended. Wait for retest or reset.")

    else:
        if structure["setup"] == "NO CLEAN STRUCTURE":
            bias = "NEUTRAL"
            action = "WAIT"
            reasons.append("No clean setup yet.")
        else:
            bias = "MIXED"
            action = "WAIT FOR CONFIRMATION"
            reasons.append("Conditions are not fully aligned.")

    plan = build_trade_plan(structure, levels, vwap)

    return {
        "qqq": qqq,
        "spy": spy,
        "oil": oil,
        "qqq_change": qqq_change,
        "spy_change": spy_change,
        "oil_change": oil_change,
        "bias": bias,
        "action": action,
        "grade": grade,
        "reasons": reasons,
        "plan": plan,
    }


def build_premium_message(
    qqq_data: dict,
    spy_data: dict,
    oil_data: dict,
    structure: dict,
    vwap: float,
    rsi: float,
    levels: dict,
) -> tuple[str, str]:
    ctx = build_premium_context(
        qqq_data=qqq_data,
        spy_data=spy_data,
        oil_data=oil_data,
        structure=structure,
        vwap=vwap,
        rsi=rsi,
        levels=levels,
    )

    reason_text = "\n".join([f"• {r}" for r in ctx["reasons"]])

    message = (
        f"💎 UnBiased Trades Premium Alert\n\n"
        f"{SYMBOL}: {ctx['qqq']:.2f} ({ctx['qqq_change']:+.2f})\n"
        f"{SECONDARY_SYMBOL}: {ctx['spy']:.2f} ({ctx['spy_change']:+.2f})\n"
        f"{OIL_SYMBOL}: {ctx['oil']:.2f} ({ctx['oil_change']:+.2f})\n\n"
        f"Bias: {ctx['bias']}\n"
        f"Action: {ctx['action']}\n"
        f"Grade: {ctx['grade']}\n"
        f"Setup: {structure['setup']}\n"
        f"Volume: {structure['volume_signal']}\n"
        f"VWAP: {vwap:.2f}\n"
        f"RSI: {rsi:.1f}\n"
        f"Day High: {levels['day_high']:.2f}\n"
        f"Day Low: {levels['day_low']:.2f}\n"
        f"Prev Close: {levels['prev_close']:.2f}\n\n"
        f"Entry: {ctx['plan']['entry']}\n"
        f"Invalidation: {ctx['plan']['stop']}\n"
        f"Target: {ctx['plan']['target']}\n\n"
        f"Reasons:\n{reason_text}\n\n"
        f"Where information becomes execution."
    )

    return message, ctx["grade"]


def build_free_message(
    qqq_data: dict,
    spy_data: dict,
    oil_data: dict,
    structure: dict,
) -> str:
    qqq = to_float(qqq_data.get("close") or qqq_data.get("price"))
    spy = to_float(spy_data.get("close") or spy_data.get("price"))
    oil = to_float(oil_data.get("close") or oil_data.get("price"))

    qqq_prev = to_float(qqq_data.get("previous_close"))
    spy_prev = to_float(spy_data.get("previous_close"))
    oil_prev = to_float(oil_data.get("previous_close"))

    qqq_change = qqq - qqq_prev
    spy_change = spy - spy_prev
    oil_change = oil - oil_prev

    bias = "NEUTRAL"

    if qqq_change > 0 and spy_change > 0 and structure["trend"] in ["BULLISH", "BULLISH LEAN"]:
        bias = "BULLISH"
    elif qqq_change < 0 and spy_change < 0 and structure["trend"] in ["BEARISH", "BEARISH LEAN"]:
        bias = "BEARISH"
    elif structure["trend"] == "CHOPPY":
        bias = "CHOPPY"
    else:
        bias = "MIXED"

    return (
        f"📡 UnBiased Trades Free Alert\n\n"
        f"{SYMBOL}: {qqq:.2f} ({qqq_change:+.2f})\n"
        f"{SECONDARY_SYMBOL}: {spy:.2f} ({spy_change:+.2f})\n"
        f"{OIL_SYMBOL}: {oil:.2f} ({oil_change:+.2f})\n\n"
        f"Bias: {bias}\n"
        f"Setup: {structure['setup']}\n"
        f"Volume: {structure['volume_signal']}\n\n"
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

        bars = get_time_series(SYMBOL, interval="5min", outputsize=40)

        closes = [candle_close(bar) for bar in bars]
        current_price = to_float(qqq_data.get("close") or qqq_data.get("price"))
        vwap = calc_vwap(bars)
        rsi = calc_rsi(closes)
        levels = build_key_levels(qqq_data, bars)
        structure = detect_structure(bars, current_price, vwap, levels)

        free_message = build_free_message(
            qqq_data=qqq_data,
            spy_data=spy_data,
            oil_data=oil_data,
            structure=structure,
        )

        premium_message, grade = build_premium_message(
            qqq_data=qqq_data,
            spy_data=spy_data,
            oil_data=oil_data,
            structure=structure,
            vwap=vwap,
            rsi=rsi,
            levels=levels,
        )

        log("Built free + premium messages")
        log(f"Premium grade detected: {grade}")

        send_discord(DISCORD_WEBHOOK_FREE, free_message, "FREE")
        send_telegram(premium_message)

        if grade in ["A+", "A"]:
            send_discord(DISCORD_WEBHOOK_PREMIUM, premium_message, "PREMIUM")
            log(f"Premium Discord alert sent for grade {grade}")
        else:
            log(f"Premium Discord alert blocked because grade was {grade}")

        log("Alerts processed successfully")

    except Exception as e:
        log(f"ERROR: {e}")
        log(traceback.format_exc())
        raise

    log("Finished run")


if __name__ == "__main__":
    main()

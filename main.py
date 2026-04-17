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


def to_float(value, default=0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


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


# ======================
# PREMIUM SIGNAL LOGIC
# ======================

def build_premium_message(
    qqq_data: dict,
    spy_data: dict,
    oil_data: dict,
    structure: dict,
    vwap: float,
    rsi: float,
    levels: dict,
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

    reasons = []
    bias = "NEUTRAL"
    action = "WAIT"
    grade = "C"

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

    if (
        qqq_change > 0
        and spy_change > 0
        and oil_change <= 0
        and structure["setup"] in ["BREAK AND HOLD", "RETEST HOLD", "WAIT FOR BREAK CONFIRMATION"]
        and above_vwap
    ):
        bias = "BULLISH"
        action = "CALL IDEA"
        grade = "A" if structure["setup"] in ["BREAK AND HOLD", "RETEST HOLD"] and structure["volume_signal"] == "STRONG" else "B+"
        reasons.append("Bullish alignment across market direction, VWAP, and structure.")

        if rsi >= 75:
            action = "AVOID CHASING"
            grade = "C"
            reasons.append("Upside is stretched. Wait for pullback or retest.")

    elif (
        qqq_change < 0
        and spy_change < 0
        and oil_change > 0
        and structure["setup"] in ["BREAKDOWN AND HOLD", "REJECTION", "FAILED BOUNCE"]
        and below_vwap
    ):
        bias = "BEARISH"
        action = "PUT IDEA"
        grade = "A" if structure["setup"] in ["BREAKDOWN AND HOLD", "REJECTION"] and structure["volume_signal"] == "STRONG" else "B+"
        reasons.append("Bearish alignment across market direction, VWAP, and structure.")

        if rsi <= 25:
            action = "AVOID CHASING"
            grade = "C"
            reasons.append("Downside is stretched. Wait for bounce then reject.")

    elif structure["setup"] == "NO CLEAN STRUCTURE":
        bias = "NEUTRAL"
        action = "WAIT"
        grade = "C"
        reasons.append("No clean setup yet.")
    else:
        bias = "MIXED"
        action = "WAIT FOR CONFIRMATION"
        grade = "C"
        reasons.append("Conditions are not fully aligned.")

    reason_text = "\n".join([f"• {r}" for r in reasons])

    return (
        f"💎 UnBiased Trades Premium Alert\n\n"
        f"{SYMBOL}: {qqq:.2f} ({qqq_change:+.2f})\n"
        f"{SECONDARY_SYMBOL}: {spy:.2f} ({spy_change:+.2f})\n"
        f"{OIL_SYMBOL}: {oil:.2f} ({oil_change:+.2f})\n\n"
        f"Bias: {bias}\n"
        f"Action: {action}\n"
        f"Grade: {grade}\n"
        f"Setup: {structure['setup']}\n"
        f"Volume: {structure['volume_signal']}\n"
        f"VWAP: {vwap:.2f}\n"
        f"RSI: {rsi:.1f}\n"
        f"Day High: {levels['day_high']:.2f}\n"
        f"Day Low: {levels['day_low']:.2f}\n"
        f"Prev Close: {levels['prev_close']:.2f}\n\n"
        f"Reasons:\n{reason_text}\n\n"
        f"Where information becomes execution."
    )


# ======================
# FREE ALERT LOGIC
# ======================

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

        premium_message = build_premium_message(
            qqq_data=qqq_data,
            spy_data=spy_data,
            oil_data=oil_data,
            structure=structure,
            vwap=vwap,
            rsi=rsi,
            levels=levels,
        )

        log("Built free + premium messages")
        log("FREE MESSAGE:")
        log(free_message)
        log("PREMIUM MESSAGE:")
        log(premium_message)

        send_discord(free_message)
        send_telegram(premium_message)

        log("Alerts sent successfully")

    except Exception as e:
        log(f"ERROR: {e}")
        log(traceback.format_exc())
        raise

    log("Finished run")


if __name__ == "__main__":
    main()

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


def get_time_series(symbol: str, interval: str = "5min", outputsize: int = 30) -> list:
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


def candle_close(bar: dict) -> float:
    return to_float(bar.get("close"))


def candle_high(bar: dict) -> float:
    return to_float(bar.get("high"))


def candle_low(bar: dict) -> float:
    return to_float(bar.get("low"))


def candle_volume(bar: dict) -> float:
    return to_float(bar.get("volume"))


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
# STRUCTURE LOGIC
# ======================

def detect_structure(bars: list) -> dict:
    if len(bars) < 3:
        return {
            "trend": "UNKNOWN",
            "setup": "NOT ENOUGH DATA",
            "volume_signal": "UNKNOWN",
        }

    b1, b2, b3 = bars[-3], bars[-2], bars[-1]

    c1, c2, c3 = candle_close(b1), candle_close(b2), candle_close(b3)
    h1, h2, h3 = candle_high(b1), candle_high(b2), candle_high(b3)
    l1, l2, l3 = candle_low(b1), candle_low(b2), candle_low(b3)
    v1, v2, v3 = candle_volume(b1), candle_volume(b2), candle_volume(b3)

    higher_lows = l3 > l2 >= l1
    lower_highs = h3 < h2 <= h1
    breakout = c3 > h2
    breakdown = c3 < l2
    strong_volume = v3 > max(v1, v2)

    if higher_lows and breakout:
        trend = "BULLISH"
        setup = "BULLISH CONTINUATION"
    elif lower_highs and breakdown:
        trend = "BEARISH"
        setup = "BEARISH CONTINUATION"
    elif higher_lows:
        trend = "BULLISH LEAN"
        setup = "WAIT FOR BREAK CONFIRMATION"
    elif lower_highs:
        trend = "BEARISH LEAN"
        setup = "WAIT FOR BREAKDOWN CONFIRMATION"
    else:
        trend = "CHOPPY"
        setup = "NO CLEAN STRUCTURE"

    volume_signal = "STRONG" if strong_volume else "NORMAL"

    return {
        "trend": trend,
        "setup": setup,
        "volume_signal": volume_signal,
    }


# ======================
# SIGNAL LOGIC
# ======================

def build_signal_message(qqq_data: dict, spy_data: dict, oil_data: dict, structure: dict, vwap: float, rsi: float) -> str:
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
    grade = "B"

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

    reasons.append(f"5m Structure: {structure['setup']}")
    reasons.append(f"5m Volume Signal: {structure['volume_signal']}")
    reasons.append(f"RSI: {rsi:.1f}")

    if rsi >= 75:
        reasons.append("Market is stretched to the upside.")
    elif rsi <= 25:
        reasons.append("Market is stretched to the downside.")

    if (
        qqq_change > 0
        and spy_change > 0
        and oil_change <= 0
        and structure["trend"] in ["BULLISH", "BULLISH LEAN"]
        and above_vwap
    ):
        bias = "BULLISH"
        action = "CALL IDEA"
        grade = "A" if structure["volume_signal"] == "STRONG" else "B+"
        reasons.append("Market direction, VWAP, and structure are aligned for upside.")

        if rsi >= 75:
            action = "AVOID CHASING"
            grade = "C"
            reasons.append("Bullish setup is extended. Wait for retest instead.")

    elif (
        qqq_change < 0
        and spy_change < 0
        and oil_change > 0
        and structure["trend"] in ["BEARISH", "BEARISH LEAN"]
        and below_vwap
    ):
        bias = "BEARISH"
        action = "PUT IDEA"
        grade = "A" if structure["volume_signal"] == "STRONG" else "B+"
        reasons.append("Market direction, VWAP, and structure are aligned for downside.")

        if rsi <= 25:
            action = "AVOID CHASING"
            grade = "C"
            reasons.append("Bearish setup is extended. Wait for bounce/reject instead.")

    elif structure["trend"] == "CHOPPY":
        bias = "NEUTRAL"
        action = "WAIT"
        grade = "C"
        reasons.append("No clean 5m structure yet.")
    else:
        bias = "MIXED"
        action = "WAIT FOR CONFIRMATION"
        grade = "C"
        reasons.append("Market conditions are not fully aligned yet.")

    reason_text = "\n".join([f"• {r}" for r in reasons])

    return (
        f"📡 UnBiased Trades Bot\n\n"
        f"{SYMBOL}: {qqq:.2f} ({qqq_change:+.2f})\n"
        f"{SECONDARY_SYMBOL}: {spy:.2f} ({spy_change:+.2f})\n"
        f"{OIL_SYMBOL}: {oil:.2f} ({oil_change:+.2f})\n\n"
        f"Bias: {bias}\n"
        f"Action: {action}\n"
        f"Grade: {grade}\n"
        f"Structure: {structure['setup']}\n"
        f"Volume: {structure['volume_signal']}\n"
        f"VWAP: {vwap:.2f}\n"
        f"RSI: {rsi:.1f}\n\n"
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

        bars = get_time_series(SYMBOL, interval="5min", outputsize=30)
        structure = detect_structure(bars)

        closes = [candle_close(bar) for bar in bars]
        vwap = calc_vwap(bars)
        rsi = calc_rsi(closes)

        message = build_signal_message(qqq_data, spy_data, oil_data, structure, vwap, rsi)

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

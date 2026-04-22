import os
import json
import time
import math
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests


# ============================================================
# CONFIG
# ============================================================

TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
FRED_API_KEY = os.getenv("FRED_API_KEY", "")
TRADING_ECONOMICS_API_KEY = os.getenv("TRADING_ECONOMICS_API_KEY", "")  # optional starter use

MACRO_CACHE_FILE = os.getenv("MACRO_CACHE_FILE", "macro_latest.json")
REQUEST_TIMEOUT = int(os.getenv("MACRO_REQUEST_TIMEOUT", "12"))

# Symbol map - adjust as needed for your provider/account support.
SYMBOLS = {
    "SPY": "SPY",
    "QQQ": "QQQ",
    "XLE": "XLE",
    "XLK": "XLK",
    "XLF": "XLF",
    "AAPL": "AAPL",
    "MSFT": "MSFT",
    "NVDA": "NVDA",
    "WTI": "USO",      # starter proxy; replace with direct WTI symbol if supported in your Twelve Data plan
    "DXY": "UUP",      # starter proxy; replace with direct DXY symbol if supported
    "VIX_PROXY": "UVIX"  # starter proxy; can replace later with true VIX source
}

FRED_SERIES = {
    "DGS10": "10Y Treasury Yield",
    "DGS2": "2Y Treasury Yield",
    "T10Y2Y": "10Y-2Y Spread",
    "FEDFUNDS": "Fed Funds Rate",
    "UNRATE": "Unemployment Rate",
    "BAMLH0A0HYM2": "High Yield OAS",
    "NFCI": "Financial Conditions Index"
}


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("macro_bridge")


# ============================================================
# HELPERS
# ============================================================

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return ((current - previous) / previous) * 100.0


def bp_change(current: float, previous: float) -> float:
    # basis points for rates
    return (current - previous) * 100.0


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def read_json_file(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read cache file {path}: {e}")
        return {}


def write_json_file(path: str, data: Dict[str, Any]) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to write cache file {path}: {e}")


def requests_get(url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.warning(f"GET failed for {url} | params={params} | error={e}")
        return None


# ============================================================
# API CLIENTS
# ============================================================

class TwelveDataClient:
    BASE_URL = "https://api.twelvedata.com"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def get_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            logger.warning("Missing TWELVE_DATA_API_KEY")
            return None

        url = f"{self.BASE_URL}/quote"
        params = {
            "symbol": symbol,
            "apikey": self.api_key
        }
        return requests_get(url, params)

    def get_time_series(self, symbol: str, interval: str = "1day", outputsize: int = 2) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            logger.warning("Missing TWELVE_DATA_API_KEY")
            return None

        url = f"{self.BASE_URL}/time_series"
        params = {
            "symbol": symbol,
            "interval": interval,
            "outputsize": outputsize,
            "apikey": self.api_key
        }
        return requests_get(url, params)


class FredClient:
    BASE_URL = "https://api.stlouisfed.org/fred"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def get_latest_observation(self, series_id: str) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            logger.warning("Missing FRED_API_KEY")
            return None

        url = f"{self.BASE_URL}/series/observations"
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 2
        }
        return requests_get(url, params)


class TradingEconomicsClient:
    BASE_URL = "https://api.tradingeconomics.com"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def get_calendar_today_us(self) -> Optional[Any]:
        if not self.api_key:
            logger.warning("Missing TRADING_ECONOMICS_API_KEY")
            return None

        url = f"{self.BASE_URL}/calendar/country/united states"
        params = {
            "c": self.api_key,
            "f": "json"
        }
        return requests_get(url, params)


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_twelve_quote(
    raw: Dict[str, Any],
    factor: str,
    label: str,
    category: str,
    previous_close_override: Optional[float] = None
) -> Optional[Dict[str, Any]]:
    if not raw:
        return None

    price = safe_float(raw.get("close") or raw.get("price"))
    prev_close = safe_float(
        previous_close_override if previous_close_override is not None else raw.get("previous_close")
    )

    change_pct_1d = pct_change(price, prev_close) if prev_close else safe_float(raw.get("percent_change"))
    change_abs_1d = price - prev_close if prev_close else safe_float(raw.get("change"))

    return {
        "factor": factor,
        "label": label,
        "category": category,
        "value": price,
        "unit": "price",
        "change_abs_1d": round(change_abs_1d, 4),
        "change_pct_1d": round(change_pct_1d, 4),
        "timestamp": now_iso(),
        "source": "twelve_data",
        "priority": "high" if factor in {"wti_proxy", "spy", "qqq"} else "medium"
    }


def normalize_fred_series(raw: Dict[str, Any], series_id: str, label: str, category: str) -> Optional[Dict[str, Any]]:
    if not raw or "observations" not in raw:
        return None

    observations = raw.get("observations", [])
    usable = [obs for obs in observations if obs.get("value") not in (".", None, "")]
    if not usable:
        return None

    current = safe_float(usable[0].get("value"))
    previous = safe_float(usable[1].get("value")) if len(usable) > 1 else current

    unit = "percent" if series_id in {"DGS10", "DGS2", "T10Y2Y", "FEDFUNDS", "UNRATE", "BAMLH0A0HYM2"} else "index"

    return {
        "factor": series_id.lower(),
        "label": label,
        "category": category,
        "value": current,
        "unit": unit,
        "change_abs_1d": round(current - previous, 4),
        "change_pct_1d": round(pct_change(current, previous), 4) if previous else 0.0,
        "change_bp_1d": round(bp_change(current, previous), 2) if unit == "percent" else 0.0,
        "timestamp": now_iso(),
        "source": "fred",
        "priority": "high" if series_id in {"DGS10", "DGS2"} else "medium"
    }


def normalize_calendar_events(raw: Any) -> List[Dict[str, Any]]:
    events = []
    if not raw or not isinstance(raw, list):
        return events

    for item in raw[:25]:
        country = str(item.get("Country", "")).lower()
        if "united states" not in country:
            continue

        events.append({
            "event_type": "economic_calendar",
            "country": item.get("Country"),
            "title": item.get("Event"),
            "category": item.get("Category"),
            "importance": item.get("Importance"),
            "actual": item.get("Actual"),
            "forecast": item.get("Forecast"),
            "previous": item.get("Previous"),
            "date": item.get("Date"),
            "reference": item.get("Reference"),
            "source": "trading_economics"
        })

    return events


# ============================================================
# DATA FETCH
# ============================================================

def fetch_market_factors(td: TwelveDataClient) -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}

    symbol_plan = [
        ("SPY", "spy", "SPY", "equities"),
        ("QQQ", "qqq", "QQQ", "equities"),
        ("XLE", "xle", "XLE", "sectors"),
        ("XLK", "xlk", "XLK", "sectors"),
        ("XLF", "xlf", "XLF", "sectors"),
        ("AAPL", "aapl", "AAPL", "leaders"),
        ("MSFT", "msft", "MSFT", "leaders"),
        ("NVDA", "nvda", "NVDA", "leaders"),
        ("WTI", "wti_proxy", "WTI Proxy", "macro"),
        ("DXY", "dxy_proxy", "DXY Proxy", "macro"),
        ("VIX_PROXY", "vix_proxy", "VIX Proxy", "volatility"),
    ]

    for key, factor, label, category in symbol_plan:
        provider_symbol = SYMBOLS[key]
        raw = td.get_quote(provider_symbol)
        norm = normalize_twelve_quote(raw, factor, label, category)
        if norm:
            results[factor] = norm

    return results


def fetch_fred_factors(fred: FredClient) -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}

    category_map = {
        "DGS10": "rates",
        "DGS2": "rates",
        "T10Y2Y": "rates",
        "FEDFUNDS": "policy",
        "UNRATE": "labor",
        "BAMLH0A0HYM2": "credit",
        "NFCI": "financial_conditions"
    }

    for series_id, label in FRED_SERIES.items():
        raw = fred.get_latest_observation(series_id)
        norm = normalize_fred_series(raw, series_id, label, category_map.get(series_id, "macro"))
        if norm:
            results[norm["factor"]] = norm

    return results


def fetch_calendar(te: TradingEconomicsClient) -> List[Dict[str, Any]]:
    raw = te.get_calendar_today_us()
    return normalize_calendar_events(raw)


# ============================================================
# STATE ENGINE
# ============================================================

def derive_sector_rotation(market: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    xle = market.get("xle", {})
    xlk = market.get("xlk", {})
    xlf = market.get("xlf", {})

    xle_chg = safe_float(xle.get("change_pct_1d"))
    xlk_chg = safe_float(xlk.get("change_pct_1d"))
    xlf_chg = safe_float(xlf.get("change_pct_1d"))

    return {
        "xle_change_pct_1d": xle_chg,
        "xlk_change_pct_1d": xlk_chg,
        "xlf_change_pct_1d": xlf_chg,
        "xlk_vs_xle_relative": round(xlk_chg - xle_chg, 4),
        "dominant_sector": (
            "xle" if xle_chg > xlk_chg and xle_chg > xlf_chg else
            "xlk" if xlk_chg > xle_chg and xlk_chg > xlf_chg else
            "xlf"
        )
    }


def derive_leader_strength(market: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    leaders = ["aapl", "msft", "nvda"]
    values = [safe_float(market.get(k, {}).get("change_pct_1d")) for k in leaders]
    avg_change = sum(values) / len(values) if values else 0.0

    return {
        "leader_avg_change_pct_1d": round(avg_change, 4),
        "leader_strength_state": (
            "strong" if avg_change > 1.0 else
            "weak" if avg_change < -1.0 else
            "mixed"
        )
    }


def score_macro_state(
    market: Dict[str, Dict[str, Any]],
    fred_data: Dict[str, Dict[str, Any]],
    calendar_events: List[Dict[str, Any]]
) -> Dict[str, Any]:
    score = 0
    drivers: List[str] = []
    watch_items: List[str] = []

    wti_change = safe_float(market.get("wti_proxy", {}).get("change_pct_1d"))
    dxy_change = safe_float(market.get("dxy_proxy", {}).get("change_pct_1d"))
    vix_change = safe_float(market.get("vix_proxy", {}).get("change_pct_1d"))
    spy_change = safe_float(market.get("spy", {}).get("change_pct_1d"))
    qqq_change = safe_float(market.get("qqq", {}).get("change_pct_1d"))

    dgs10_bp = safe_float(fred_data.get("dgs10", {}).get("change_bp_1d"))
    dgs2_bp = safe_float(fred_data.get("dgs2", {}).get("change_bp_1d"))
    t10y2y = safe_float(fred_data.get("t10y2y", {}).get("value"))
    hy_oas = safe_float(fred_data.get("bamlh0a0hym2", {}).get("value"))

    sector = derive_sector_rotation(market)
    leader = derive_leader_strength(market)

    # Oil pressure
    if wti_change >= 2.0:
        score -= 2
        drivers.append("oil_up_strong")
    elif wti_change <= -2.0:
        score += 1
        drivers.append("oil_down_relief")

    # Dollar pressure
    if dxy_change >= 0.5:
        score -= 1
        drivers.append("dollar_up")
    elif dxy_change <= -0.5:
        score += 1
        drivers.append("dollar_down")

    # Volatility pressure
    if vix_change >= 8.0:
        score -= 2
        drivers.append("volatility_rising")
    elif vix_change <= -8.0:
        score += 1
        drivers.append("volatility_falling")

    # Rates pressure
    if dgs2_bp >= 5:
        score -= 2
        drivers.append("2y_yield_up")
    elif dgs2_bp <= -5:
        score += 1
        drivers.append("2y_yield_down")

    if dgs10_bp >= 5:
        score -= 1
        drivers.append("10y_yield_up")
    elif dgs10_bp <= -5:
        score += 1
        drivers.append("10y_yield_down")

    # Curve / credit
    if t10y2y < 0:
        score -= 1
        drivers.append("curve_inverted")

    if hy_oas > 4.0:
        score -= 1
        drivers.append("credit_stress_elevated")

    # Sector rotation
    if sector["xlk_vs_xle_relative"] < -1.0:
        score -= 1
        drivers.append("energy_beating_tech")
    elif sector["xlk_vs_xle_relative"] > 1.0:
        score += 1
        drivers.append("tech_beating_energy")

    # Mega-cap leadership
    if leader["leader_strength_state"] == "strong":
        score += 1
        drivers.append("mega_caps_strong")
    elif leader["leader_strength_state"] == "weak":
        score -= 1
        drivers.append("mega_caps_weak")

    # Market tape context
    if spy_change < -0.75:
        watch_items.append("SPY_under_pressure")
    if qqq_change < -1.0:
        watch_items.append("QQQ_under_pressure")
    if spy_change > 0.75:
        watch_items.append("SPY_showing_strength")
    if qqq_change > 1.0:
        watch_items.append("QQQ_showing_strength")

    # Calendar events
    high_impact_titles = {"cpi", "ppi", "fomc", "fed", "non farm payrolls", "gdp", "jobless claims"}
    todays_high_impact = []
    for evt in calendar_events:
        title = str(evt.get("title", "")).lower()
        importance = str(evt.get("importance", "")).lower()
        if any(k in title for k in high_impact_titles) or importance in {"3", "high"}:
            todays_high_impact.append(evt.get("title"))

    if todays_high_impact:
        watch_items.append("high_impact_calendar_today")
        drivers.append("economic_event_risk")

    # Final labels
    if score <= -5:
        risk_state = "risk_off"
        macro_bias = "bearish_equities"
    elif score >= 3:
        risk_state = "risk_on"
        macro_bias = "bullish_equities"
    else:
        risk_state = "mixed"
        macro_bias = "neutral_to_mixed"

    volatility_state = (
        "elevated" if vix_change >= 8.0 else
        "calm" if vix_change <= -8.0 else
        "normal"
    )

    confidence = clamp(abs(score) / 7.0, 0.25, 0.95)

    return {
        "risk_state": risk_state,
        "macro_bias": macro_bias,
        "volatility_state": volatility_state,
        "score": score,
        "confidence": round(confidence, 2),
        "drivers": drivers,
        "watch_items": watch_items,
        "sector_rotation": sector,
        "leader_strength": leader,
        "todays_high_impact_events": todays_high_impact[:8]
    }


# ============================================================
# LLM BRIEFING PAYLOAD
# ============================================================

def build_llm_payload(
    market: Dict[str, Dict[str, Any]],
    fred_data: Dict[str, Dict[str, Any]],
    calendar_events: List[Dict[str, Any]],
    state: Dict[str, Any]
) -> Dict[str, Any]:
    return {
        "timestamp": now_iso(),
        "macro_state": state,
        "market_snapshot": {
            "spy_change_pct_1d": safe_float(market.get("spy", {}).get("change_pct_1d")),
            "qqq_change_pct_1d": safe_float(market.get("qqq", {}).get("change_pct_1d")),
            "wti_change_pct_1d": safe_float(market.get("wti_proxy", {}).get("change_pct_1d")),
            "dxy_change_pct_1d": safe_float(market.get("dxy_proxy", {}).get("change_pct_1d")),
            "vix_proxy_change_pct_1d": safe_float(market.get("vix_proxy", {}).get("change_pct_1d")),
            "xle_change_pct_1d": safe_float(market.get("xle", {}).get("change_pct_1d")),
            "xlk_change_pct_1d": safe_float(market.get("xlk", {}).get("change_pct_1d")),
            "aapl_change_pct_1d": safe_float(market.get("aapl", {}).get("change_pct_1d")),
            "msft_change_pct_1d": safe_float(market.get("msft", {}).get("change_pct_1d")),
            "nvda_change_pct_1d": safe_float(market.get("nvda", {}).get("change_pct_1d"))
        },
        "rates_snapshot": {
            "us_10y": safe_float(fred_data.get("dgs10", {}).get("value")),
            "us_2y": safe_float(fred_data.get("dgs2", {}).get("value")),
            "curve_10y_2y": safe_float(fred_data.get("t10y2y", {}).get("value")),
            "high_yield_oas": safe_float(fred_data.get("bamlh0a0hym2", {}).get("value"))
        },
        "calendar_today": calendar_events[:10],
        "llm_instruction": (
            "Create a concise market update in my style. "
            "Focus on market tone, risk state, oil, yields, dollar, volatility, "
            "sector rotation, and major events today. "
            "Keep it actionable for SPY and QQQ traders. "
            "Mention whether conditions favor calls, puts, or patience."
        )
    }


def build_voice_script(llm_payload: Dict[str, Any]) -> str:
    macro = llm_payload["macro_state"]
    snap = llm_payload["market_snapshot"]
    rates = llm_payload["rates_snapshot"]

    lines = []
    lines.append(
        f"Market tone is {macro['risk_state'].replace('_', ' ')} with a {macro['macro_bias'].replace('_', ' ')} bias."
    )

    lines.append(
        f"SPY is {snap['spy_change_pct_1d']:.2f}% on the day, QQQ is {snap['qqq_change_pct_1d']:.2f}%, "
        f"while oil is moving {snap['wti_change_pct_1d']:.2f}% and the dollar proxy is at {snap['dxy_change_pct_1d']:.2f}%."
    )

    lines.append(
        f"The 2-year yield is {rates['us_2y']:.2f} and the 10-year yield is {rates['us_10y']:.2f}, "
        f"with volatility in a {macro['volatility_state']} state."
    )

    if macro.get("drivers"):
        lines.append("Main drivers right now: " + ", ".join(macro["drivers"][:5]).replace("_", " ") + ".")

    if macro.get("todays_high_impact_events"):
        lines.append("Key event risk today: " + ", ".join(macro["todays_high_impact_events"][:4]) + ".")

    if macro["risk_state"] == "risk_off":
        lines.append("That keeps pressure on equities unless price reclaims key levels and confirms through VWAP.")
    elif macro["risk_state"] == "risk_on":
        lines.append("That supports upside continuation if price accepts above key levels and holds momentum.")
    else:
        lines.append("That suggests a mixed tape, so patience and confirmation matter more than guessing.")

    return " ".join(lines)


# ============================================================
# MAIN BUILD
# ============================================================

def build_macro_bridge_snapshot() -> Dict[str, Any]:
    td = TwelveDataClient(TWELVE_DATA_API_KEY)
    fred = FredClient(FRED_API_KEY)
    te = TradingEconomicsClient(TRADING_ECONOMICS_API_KEY)

    market = fetch_market_factors(td)
    fred_data = fetch_fred_factors(fred)
    calendar_events = fetch_calendar(te)

    state = score_macro_state(market, fred_data, calendar_events)
    llm_payload = build_llm_payload(market, fred_data, calendar_events, state)
    voice_script = build_voice_script(llm_payload)

    output = {
        "timestamp": now_iso(),
        "market_factors": market,
        "fred_factors": fred_data,
        "calendar_events": calendar_events,
        "macro_state": state,
        "llm_payload": llm_payload,
        "voice_script": voice_script
    }

    write_json_file(MACRO_CACHE_FILE, output)
    return output


# ============================================================
# OPTIONAL HELPERS FOR MAIN.PY
# ============================================================

def get_macro_state_only() -> Dict[str, Any]:
    data = build_macro_bridge_snapshot()
    return data.get("macro_state", {})


def get_voice_script_only() -> str:
    data = build_macro_bridge_snapshot()
    return data.get("voice_script", "")


def load_last_macro_snapshot() -> Dict[str, Any]:
    return read_json_file(MACRO_CACHE_FILE)


# ============================================================
# RUN DIRECT
# ============================================================

if __name__ == "__main__":
    snapshot = build_macro_bridge_snapshot()
    print(json.dumps(snapshot, indent=2))
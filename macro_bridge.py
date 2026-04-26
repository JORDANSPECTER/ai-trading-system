# =========================================================
# UNBIASED TRADES - MACRO BRIDGE
# FRED + TRADING ECONOMICS SNAPSHOT
# Writes: macro_snapshot.json
# =========================================================

import os
import json
import time
import traceback
from datetime import datetime, timezone

import requests


MACRO_FILE = "macro_snapshot.json"

FRED_API_KEY = os.getenv("FRED_API_KEY", "").strip()
TRADING_ECONOMICS_API_KEY = os.getenv("TRADING_ECONOMICS_API_KEY", "").strip()

REQUEST_TIMEOUT = 12


# =========================================================
# SAFE JSON WRITE
# =========================================================

def write_json(path, data):
    tmp_path = path + ".tmp"
    bak_path = path + ".bak"

    try:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as old:
                    old_data = old.read()
                with open(bak_path, "w", encoding="utf-8") as bak:
                    bak.write(old_data)
            except Exception:
                pass

        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        os.replace(tmp_path, path)
        return True

    except Exception:
        traceback.print_exc()
        return False


# =========================================================
# HELPERS
# =========================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def safe_float(value):
    try:
        return float(value)
    except Exception:
        return None


def fred_latest(series_id):
    if not FRED_API_KEY:
        return None

    url = "https://api.stlouisfed.org/fred/series/observations"

    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 1,
    }

    try:
        r = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()

        observations = data.get("observations", [])
        if not observations:
            return None

        obs = observations[0]
        value = safe_float(obs.get("value"))

        return {
            "series_id": series_id,
            "date": obs.get("date"),
            "value": value,
        }

    except Exception:
        return None


def trading_economics_indicator(country, indicator):
    if not TRADING_ECONOMICS_API_KEY:
        return None

    url = f"https://api.tradingeconomics.com/historical/country/{country}/indicator/{indicator}"

    params = {
        "c": TRADING_ECONOMICS_API_KEY,
        "format": "json",
    }

    try:
        r = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()

        if not isinstance(data, list) or not data:
            return None

        latest = data[-1]

        return {
            "country": country,
            "indicator": indicator,
            "date": latest.get("DateTime") or latest.get("date"),
            "value": safe_float(latest.get("Value") or latest.get("value")),
        }

    except Exception:
        return None


# =========================================================
# CLASSIFIERS
# =========================================================

def classify_rates(fed_funds):
    value = fed_funds.get("value") if fed_funds else None

    if value is None:
        return "unknown"

    if value >= 5:
        return "restrictive"
    if value >= 3:
        return "moderately_restrictive"
    return "loose"


def classify_inflation(cpi):
    value = cpi.get("value") if cpi else None

    if value is None:
        return "unknown"

    if value >= 4:
        return "hot"
    if value >= 2.5:
        return "elevated"
    return "cooling"


def classify_macro_bias(rates_state, inflation_state):
    if rates_state == "unknown" and inflation_state == "unknown":
        return "neutral"

    if rates_state in ["restrictive", "moderately_restrictive"] and inflation_state in ["hot", "elevated"]:
        return "bearish"

    if inflation_state == "cooling":
        return "bullish"

    return "neutral"


def classify_risk_environment(macro_bias):
    if macro_bias == "bullish":
        return "risk_on"
    if macro_bias == "bearish":
        return "risk_off"
    return "mixed"


# =========================================================
# BUILD SNAPSHOT
# =========================================================

def get_macro_snapshot():
    errors = []

    fred_data = {}

    fred_series = {
        "fed_funds_rate": "FEDFUNDS",
        "cpi": "CPIAUCSL",
        "unemployment": "UNRATE",
        "ten_year_yield": "DGS10",
        "dxy_proxy": "DTWEXBGS",
        "vix_proxy": "VIXCLS",
        "oil_wti": "DCOILWTICO",
    }

    for name, series_id in fred_series.items():
        result = fred_latest(series_id)
        fred_data[name] = result

        if result is None:
            errors.append(f"FRED failed: {name} / {series_id}")

        time.sleep(0.2)

    te_data = {}

    te_indicators = {
        "interest_rate": "Interest Rate",
        "inflation_rate": "Inflation Rate",
        "unemployment_rate": "Unemployment Rate",
        "gdp_growth": "GDP Growth Rate",
    }

    for name, indicator in te_indicators.items():
        result = trading_economics_indicator("united states", indicator)
        te_data[name] = result

        if result is None:
            errors.append(f"Trading Economics failed: {name}")

        time.sleep(0.2)

    rates_state = classify_rates(fred_data.get("fed_funds_rate"))
    inflation_state = classify_inflation(te_data.get("inflation_rate") or fred_data.get("cpi"))
    macro_bias = classify_macro_bias(rates_state, inflation_state)
    risk_environment = classify_risk_environment(macro_bias)

    oil_value = None
    oil_data = fred_data.get("oil_wti")
    if oil_data:
        oil_value = oil_data.get("value")

    snapshot = {
        "loaded": True,
        "timestamp_utc": now_iso(),

        "macro_bias": macro_bias,
        "risk_environment": risk_environment,

        "rates_state": rates_state,
        "inflation_state": inflation_state,

        "oil": {
            "source": "FRED DCOILWTICO",
            "value": oil_value,
            "state": "loaded" if oil_value is not None else "unknown",
            "note": "Oil trend direction should be handled by main.py using current vs prior snapshot.",
        },

        "fred": fred_data,
        "trading_economics": te_data,

        "engine_summary": {
            "macro_loaded": True,
            "macro_bias": macro_bias,
            "risk_environment": risk_environment,
            "rates_state": rates_state,
            "inflation_state": inflation_state,
            "oil_value": oil_value,
            "errors_count": len(errors),
        },

        "errors": errors,
    }

    write_json(MACRO_FILE, snapshot)

    return snapshot


# =========================================================
# LOAD SNAPSHOT
# =========================================================

def load_macro_snapshot():
    try:
        if not os.path.exists(MACRO_FILE):
            return None

        with open(MACRO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:
        return None


# =========================================================
# RUN DIRECTLY
# =========================================================

if __name__ == "__main__":
    snap = get_macro_snapshot()

    if snap:
        print("✅ Macro snapshot created")
        print(json.dumps(snap.get("engine_summary", {}), indent=2))
    else:
        print("❌ Macro snapshot failed")

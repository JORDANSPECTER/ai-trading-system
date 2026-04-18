import os
import time
import csv
import json
import requests
from pathlib import Path
from zoneinfo import ZoneInfo
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime, date, timedelta

# =========================================================
# CONFIG
# =========================================================
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
DISCORD_WEBHOOK_FREE = os.getenv("DISCORD_WEBHOOK_FREE", "")
DISCORD_WEBHOOK_EXECUTION = os.getenv("DISCORD_WEBHOOK_EXECUTION", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_PAPER = os.getenv("ALPACA_PAPER", "true").lower() == "true"

LIVE_TRADING = os.getenv("LIVE_TRADING", "false").lower() == "true"
RUN_ONCE = os.getenv("RUN_ONCE", "true").lower() == "true"
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "60"))
WATCHLIST = [x.strip().upper() for x in os.getenv("WATCHLIST", "QQQ,SPY").split(",") if x.strip()]

# =========================================================
# EXECUTION ENGINE
# =========================================================
A_PLUS_ONLY_MODE = os.getenv("A_PLUS_ONLY_MODE", "false").lower() == "true"
ALLOW_B_MICRO_SIZE = os.getenv("ALLOW_B_MICRO_SIZE", "true").lower() == "true"

DEFAULT_ORDER_QTY = int(os.getenv("DEFAULT_ORDER_QTY", "1"))
B_MICRO_QTY = int(os.getenv("B_MICRO_QTY", "1"))

CHASE_DISTANCE_PCT = float(os.getenv("CHASE_DISTANCE_PCT", "0.15"))
MIN_RSI_CALL = float(os.getenv("MIN_RSI_CALL", "55"))
MAX_RSI_PUT = float(os.getenv("MAX_RSI_PUT", "45"))
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.75"))

# =========================================================
# ELITE RISK / MANAGEMENT
# =========================================================
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", "2"))
MAX_NEW_TRADES_PER_DAY = int(os.getenv("MAX_NEW_TRADES_PER_DAY", "4"))
ENTRY_CUTOFF_HOUR_ET = int(os.getenv("ENTRY_CUTOFF_HOUR_ET", "15"))
ENTRY_CUTOFF_MINUTE_ET = int(os.getenv("ENTRY_CUTOFF_MINUTE_ET", "0"))
FORCE_EXIT_HOUR_ET = int(os.getenv("FORCE_EXIT_HOUR_ET", "15"))
FORCE_EXIT_MINUTE_ET = int(os.getenv("FORCE_EXIT_MINUTE_ET", "45"))

CALL_TP_UNDERLYING_PCT = float(os.getenv("CALL_TP_UNDERLYING_PCT", "0.35"))
CALL_SL_UNDERLYING_PCT = float(os.getenv("CALL_SL_UNDERLYING_PCT", "0.20"))
PUT_TP_UNDERLYING_PCT = float(os.getenv("PUT_TP_UNDERLYING_PCT", "0.35"))
PUT_SL_UNDERLYING_PCT = float(os.getenv("PUT_SL_UNDERLYING_PCT", "0.20"))
BREAK_EVEN_TRIGGER_PCT = float(os.getenv("BREAK_EVEN_TRIGGER_PCT", "0.20"))
MAX_HOLD_MINUTES = int(os.getenv("MAX_HOLD_MINUTES", "120"))
COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "20"))

# =========================================================
# FILES
# =========================================================
OPEN_TRADES_FILE = os.getenv("OPEN_TRADES_FILE", "open_trades.json")
TRADE_LOG_FILE = os.getenv("TRADE_LOG_FILE", "trade_log.csv")

# =========================================================
# OPTIONS SETTINGS / PRICING ENGINE
# =========================================================
OPTIONS_DTE_FALLBACK_DAYS = int(os.getenv("OPTIONS_DTE_FALLBACK_DAYS", "5"))
OPTIONS_STRIKE_STEP_BUFFER = float(os.getenv("OPTIONS_STRIKE_STEP_BUFFER", "0.0"))

OPTION_QUOTE_FEED = os.getenv("OPTION_QUOTE_FEED", "indicative")
MAX_OPTION_SPREAD_ABS = float(os.getenv("MAX_OPTION_SPREAD_ABS", "0.30"))
MAX_OPTION_SPREAD_PCT = float(os.getenv("MAX_OPTION_SPREAD_PCT", "20"))
BUY_LIMIT_SPREAD_FACTOR = float(os.getenv("BUY_LIMIT_SPREAD_FACTOR", "0.85"))
SELL_LIMIT_SPREAD_FACTOR = float(os.getenv("SELL_LIMIT_SPREAD_FACTOR", "0.15"))
MIN_OPTION_ASK = float(os.getenv("MIN_OPTION_ASK", "0.05"))
MIN_OPTION_BID = float(os.getenv("MIN_OPTION_BID", "0.01"))
ALLOW_MARKET_ORDERS_DURING_RTH = os.getenv("ALLOW_MARKET_ORDERS_DURING_RTH", "false").lower() == "true"

# =========================================================
# CONSTANTS
# =========================================================
GRADE_ORDER = {"C": 1, "B": 2, "A": 3, "A+": 4}
BULLISH_CONFIRM_BONUS = 15
BEARISH_CONFIRM_BONUS = 15
CONFLICT_PENALTY = 20
MIXED_PENALTY = 5

# =========================================================
# OPTIONAL ALPACA IMPORT
# =========================================================
alpaca_client = None
alpaca_options_ready = False

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import (
        MarketOrderRequest,
        LimitOrderRequest,
        GetOptionContractsRequest,
    )
    from alpaca.trading.enums import (
        OrderSide,
        TimeInForce,
        ContractType,
        AssetStatus,
    )

    if ALPACA_API_KEY and ALPACA_SECRET_KEY:
        alpaca_client = TradingClient(
            api_key=ALPACA_API_KEY,
            secret_key=ALPACA_SECRET_KEY,
            paper=ALPACA_PAPER,
        )
        alpaca_options_ready = True

except Exception as e:
    print(f"[ALPACA IMPORT WARNING] {e}", flush=True)
    alpaca_client = None
    alpaca_options_ready = False

# =========================================================
# ETF MAJOR CONSTITUENTS
# =========================================================
ETF_CONSTITUENTS = {
    "QQQ": [
        {"symbol": "AAPL", "weight": 9.0},
        {"symbol": "MSFT", "weight": 8.5},
        {"symbol": "NVDA", "weight": 8.0},
        {"symbol": "AMZN", "weight": 5.5},
        {"symbol": "META", "weight": 4.5},
        {"symbol": "GOOGL", "weight": 4.0},
        {"symbol": "TSLA", "weight": 3.0},
        {"symbol": "AVGO", "weight": 3.0},
        {"symbol": "NFLX", "weight": 2.0},
        {"symbol": "AMD", "weight": 2.0},
    ],
    "SPY": [
        {"symbol": "AAPL", "weight": 7.0},
        {"symbol": "MSFT", "weight": 6.8},
        {"symbol": "NVDA", "weight": 6.0},
        {"symbol": "AMZN", "weight": 3.8},
        {"symbol": "META", "weight": 2.8},
        {"symbol": "GOOGL", "weight": 2.2},
        {"symbol": "BRK.B", "weight": 1.8},
        {"symbol": "XOM", "weight": 1.3},
        {"symbol": "JPM", "weight": 1.2},
        {"symbol": "LLY", "weight": 1.5},
        {"symbol": "TSLA", "weight": 1.3},
    ],
}

# =========================================================
# DATA MODELS
# =========================================================
@dataclass
class ConstituentSnapshot:
    symbol: str
    price: float
    vwap: float
    change_pct: float
    volume_ratio: float = 1.0
    weight: float = 1.0

    @property
    def above_vwap(self) -> bool:
        return self.price > self.vwap

    @property
    def below_vwap(self) -> bool:
        return self.price < self.vwap


@dataclass
class ConstituentInternals:
    etf_symbol: str
    aligned_bullish_weight: float
    aligned_bearish_weight: float
    bullish_participation: float
    bearish_participation: float
    breadth_score: float
    leadership_score: float
    confirmation_bias: str
    summary: str
    leaders_up: List[str] = field(default_factory=list)
    leaders_down: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)


@dataclass
class MarketContext:
    symbol: str
    current_price: float
    vwap: float
    rsi: float
    change_pct: float
    volume_ratio: float
    above_vwap: bool
    below_vwap: bool
    constituent_internals: Optional[ConstituentInternals] = None
    constituent_snapshots: List[ConstituentSnapshot] = field(default_factory=list)


@dataclass
class TradePlan:
    symbol: str
    action: str
    grade: str
    score: int
    confidence: float
    reasons: List[str] = field(default_factory=list)
    execution_qty: int = 0
    execution_tier: str = "NONE"
    chasing: bool = False

# =========================================================
# TIME / UTILS
# =========================================================
def now_et() -> datetime:
    return datetime.now(ZoneInfo("America/New_York"))


def safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def passes_grade_threshold(grade: str, threshold: str) -> bool:
    return GRADE_ORDER.get(grade, 0) >= GRADE_ORDER.get(threshold, 0)


def is_regular_market_hours_et() -> bool:
    current = now_et()
    if current.weekday() > 4:
        return False
    current_minutes = current.hour * 60 + current.minute
    return (9 * 60 + 30) <= current_minutes <= (16 * 60)


def entry_cutoff_reached() -> bool:
    current = now_et()
    cutoff_minutes = ENTRY_CUTOFF_HOUR_ET * 60 + ENTRY_CUTOFF_MINUTE_ET
    return (current.hour * 60 + current.minute) >= cutoff_minutes


def force_exit_reached() -> bool:
    current = now_et()
    cutoff_minutes = FORCE_EXIT_HOUR_ET * 60 + FORCE_EXIT_MINUTE_ET
    return (current.hour * 60 + current.minute) >= cutoff_minutes


def round_option_limit_price(price: float) -> float:
    if price >= 1.0:
        return round(price + 1e-12, 2)
    return round(price + 1e-12, 4)

# =========================================================
# ALERTS
# =========================================================
def send_discord_free(message: str) -> None:
    if not DISCORD_WEBHOOK_FREE:
        return
    try:
        requests.post(DISCORD_WEBHOOK_FREE, json={"content": message}, timeout=12)
    except Exception as e:
        print(f"[DISCORD FREE ERROR] {e}", flush=True)


def send_discord_execution(message: str) -> None:
    if not DISCORD_WEBHOOK_EXECUTION:
        return
    try:
        requests.post(DISCORD_WEBHOOK_EXECUTION, json={"content": message}, timeout=12)
    except Exception as e:
        print(f"[DISCORD EXEC ERROR] {e}", flush=True)


def send_telegram(message: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        requests.post(url, data=payload, timeout=12)
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}", flush=True)


def broadcast_free(message: str) -> None:
    if not message:
        return
    print(message, flush=True)
    send_discord_free(message)
    send_telegram(message)


def broadcast_execution(message: str) -> None:
    if not message:
        return
    print(message, flush=True)
    send_discord_execution(message)
    send_telegram(message)

# =========================================================
# STATE / LOGGING
# =========================================================
def ensure_trade_log_exists() -> None:
    path = Path(TRADE_LOG_FILE)
    if path.exists():
        return

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp",
            "event",
            "underlying",
            "option_symbol",
            "action",
            "grade",
            "execution_tier",
            "qty",
            "entry_underlying",
            "current_underlying",
            "underlying_move_pct",
            "reason",
            "order_id",
        ])


def log_trade_event(
    event: str,
    underlying: str,
    option_symbol: str,
    action: str,
    grade: str,
    execution_tier: str,
    qty: int,
    entry_underlying: float,
    current_underlying: float,
    underlying_move_pct: float,
    reason: str,
    order_id: str,
) -> None:
    ensure_trade_log_exists()
    with open(TRADE_LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            now_et().isoformat(),
            event,
            underlying,
            option_symbol,
            action,
            grade,
            execution_tier,
            qty,
            round(entry_underlying, 4),
            round(current_underlying, 4),
            round(underlying_move_pct, 4),
            reason,
            order_id,
        ])


def load_state() -> Dict:
    path = Path(OPEN_TRADES_FILE)
    if not path.exists():
        return {"open_trades": [], "recent_closures": {}, "daily_entries": {}}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"open_trades": [], "recent_closures": {}, "daily_entries": {}}


def save_state(state: Dict) -> None:
    with open(OPEN_TRADES_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

# =========================================================
# MARKET DATA
# =========================================================
def fetch_twelve_time_series(symbol: str, interval: str = "1min", outputsize: int = 80) -> List[Dict]:
    if not TWELVE_DATA_API_KEY:
        raise RuntimeError("Missing TWELVE_DATA_API_KEY")

    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": TWELVE_DATA_API_KEY,
        "timezone": "America/New_York",
    }

    response = requests.get(url, params=params, timeout=20)
    data = response.json()

    if "values" not in data:
        raise RuntimeError(f"Twelve Data error for {symbol}: {data}")

    return list(reversed(data["values"]))


def compute_vwap_from_bars(bars: List[Dict]) -> float:
    cumulative_pv = 0.0
    cumulative_vol = 0.0
    for bar in bars:
        high = safe_float(bar.get("high"))
        low = safe_float(bar.get("low"))
        close = safe_float(bar.get("close"))
        volume = safe_float(bar.get("volume"), 1.0)
        typical_price = (high + low + close) / 3.0
        cumulative_pv += typical_price * volume
        cumulative_vol += volume

    if cumulative_vol <= 0:
        return safe_float(bars[-1].get("close"))
    return cumulative_pv / cumulative_vol


def compute_rsi_from_closes(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0

    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_volume_ratio(bars: List[Dict], lookback: int = 20) -> float:
    volumes = [safe_float(b.get("volume"), 0.0) for b in bars if b.get("volume") is not None]
    if len(volumes) < 2:
        return 1.0

    recent = volumes[-1]
    baseline_window = volumes[-(lookback + 1):-1] if len(volumes) > lookback else volumes[:-1]
    if not baseline_window:
        return 1.0

    baseline = sum(baseline_window) / len(baseline_window)
    if baseline <= 0:
        return 1.0

    return recent / baseline


def get_symbol_snapshot(symbol: str) -> Optional[Dict]:
    try:
        bars = fetch_twelve_time_series(symbol=symbol, interval="1min", outputsize=80)
        if len(bars) < 5:
            return None

        closes = [safe_float(b["close"]) for b in bars]
        latest = bars[-1]
        prev_close = closes[-2] if len(closes) >= 2 else closes[-1]

        price = safe_float(latest["close"])
        vwap = compute_vwap_from_bars(bars)
        rsi = compute_rsi_from_closes(closes)
        change_pct = ((price - prev_close) / prev_close * 100.0) if prev_close else 0.0
        volume_ratio = compute_volume_ratio(bars)

        return {
            "price": price,
            "vwap": vwap,
            "rsi": rsi,
            "change_pct": change_pct,
            "volume_ratio": volume_ratio,
        }
    except Exception as e:
        print(f"[SNAPSHOT ERROR] {symbol}: {e}", flush=True)
        return None

# =========================================================
# OPTION QUOTES / PRICING ENGINE
# =========================================================
def get_option_latest_quote(option_symbol: str) -> Optional[Dict]:
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        return None

    base_url = "https://data.alpaca.markets/v1beta1/options/quotes/latest"
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
    }
    params = {
        "symbols": option_symbol,
        "feed": OPTION_QUOTE_FEED,
    }

    try:
        response = requests.get(base_url, headers=headers, params=params, timeout=12)
        response.raise_for_status()
        data = response.json()
        quotes = data.get("quotes", {})
        quote = quotes.get(option_symbol)
        if not quote:
            return None

        bid = safe_float(quote.get("bp"), 0.0)
        ask = safe_float(quote.get("ap"), 0.0)
        bid_size = safe_float(quote.get("bs"), 0.0)
        ask_size = safe_float(quote.get("as"), 0.0)

        if ask <= 0:
            return None

        spread_abs = max(0.0, ask - bid)
        spread_pct = (spread_abs / ask * 100.0) if ask > 0 else 999.0

        return {
            "bid": bid,
            "ask": ask,
            "bid_size": bid_size,
            "ask_size": ask_size,
            "spread_abs": spread_abs,
            "spread_pct": spread_pct,
        }
    except Exception as e:
        print(f"[OPTION QUOTE ERROR] {option_symbol}: {e}", flush=True)
        return None


def quote_is_tradeable(quote: Dict) -> Tuple[bool, str]:
    if not quote:
        return False, "No option quote available."
    if quote["ask"] < MIN_OPTION_ASK:
        return False, f"Ask too low ({quote['ask']:.4f})."
    if quote["bid"] < MIN_OPTION_BID:
        return False, f"Bid too low ({quote['bid']:.4f})."
    if quote["spread_abs"] > MAX_OPTION_SPREAD_ABS:
        return False, f"Spread too wide (${quote['spread_abs']:.4f})."
    if quote["spread_pct"] > MAX_OPTION_SPREAD_PCT:
        return False, f"Spread too wide ({quote['spread_pct']:.2f}%)."
    return True, "Quote acceptable."


def compute_buy_limit_from_quote(quote: Dict) -> float:
    bid = quote["bid"]
    ask = quote["ask"]
    spread = max(0.0, ask - bid)
    raw = bid + (spread * BUY_LIMIT_SPREAD_FACTOR)
    raw = min(raw, ask)
    raw = max(raw, MIN_OPTION_ASK)
    return round_option_limit_price(raw)


def compute_sell_limit_from_quote(quote: Dict) -> float:
    bid = quote["bid"]
    ask = quote["ask"]
    spread = max(0.0, ask - bid)
    raw = bid + (spread * SELL_LIMIT_SPREAD_FACTOR)
    raw = max(raw, bid)
    return round_option_limit_price(max(raw, MIN_OPTION_BID))

# =========================================================
# CONSTITUENT ENGINE
# =========================================================
def load_constituent_snapshots(etf_symbol: str) -> List[ConstituentSnapshot]:
    snapshots: List[ConstituentSnapshot] = []

    for item in ETF_CONSTITUENTS.get(etf_symbol, []):
        data = get_symbol_snapshot(item["symbol"])
        if not data:
            continue

        snapshots.append(
            ConstituentSnapshot(
                symbol=item["symbol"],
                price=safe_float(data["price"]),
                vwap=safe_float(data["vwap"]),
                change_pct=safe_float(data["change_pct"]),
                volume_ratio=safe_float(data.get("volume_ratio", 1.0)),
                weight=safe_float(item["weight"]),
            )
        )
    return snapshots


def analyze_constituent_internals(etf_symbol: str, snapshots: List[ConstituentSnapshot]) -> ConstituentInternals:
    if not snapshots:
        return ConstituentInternals(
            etf_symbol=etf_symbol,
            aligned_bullish_weight=0.0,
            aligned_bearish_weight=0.0,
            bullish_participation=0.0,
            bearish_participation=0.0,
            breadth_score=0.0,
            leadership_score=0.0,
            confirmation_bias="NEUTRAL",
            summary=f"{etf_symbol} internals unavailable.",
            conflicts=["No constituent data available."],
        )

    total_weight = sum(x.weight for x in snapshots) or 1.0
    bullish_weight = 0.0
    bearish_weight = 0.0
    bullish_names = 0
    bearish_names = 0
    leaders_up = []
    leaders_down = []
    conflicts = []
    leadership_raw = []

    for snap in snapshots:
        weighted_push = snap.weight * abs(snap.change_pct)
        if snap.above_vwap and snap.change_pct > 0:
            bullish_weight += snap.weight
            bullish_names += 1
            leadership_raw.append(weighted_push)
            if snap.weight >= 3.0:
                leaders_up.append(snap.symbol)
        elif snap.below_vwap and snap.change_pct < 0:
            bearish_weight += snap.weight
            bearish_names += 1
            leadership_raw.append(-weighted_push)
            if snap.weight >= 3.0:
                leaders_down.append(snap.symbol)
        else:
            conflicts.append(snap.symbol)

    bullish_participation = bullish_names / len(snapshots)
    bearish_participation = bearish_names / len(snapshots)
    aligned_bullish_weight = bullish_weight / total_weight
    aligned_bearish_weight = bearish_weight / total_weight
    breadth_score = bullish_participation - bearish_participation
    leadership_score = sum(leadership_raw) / total_weight if leadership_raw else 0.0

    if aligned_bullish_weight >= 0.55 and bullish_participation >= 0.50:
        bias = "BULLISH_CONFIRMATION"
        summary = f"{etf_symbol} internals bullish."
    elif aligned_bearish_weight >= 0.55 and bearish_participation >= 0.50:
        bias = "BEARISH_CONFIRMATION"
        summary = f"{etf_symbol} internals bearish."
    else:
        bias = "MIXED"
        summary = f"{etf_symbol} internals mixed."

    return ConstituentInternals(
        etf_symbol=etf_symbol,
        aligned_bullish_weight=aligned_bullish_weight,
        aligned_bearish_weight=aligned_bearish_weight,
        bullish_participation=bullish_participation,
        bearish_participation=bearish_participation,
        breadth_score=breadth_score,
        leadership_score=leadership_score,
        confirmation_bias=bias,
        summary=summary,
        leaders_up=leaders_up,
        leaders_down=leaders_down,
        conflicts=conflicts,
    )


def enrich_context_with_constituents(context: MarketContext) -> MarketContext:
    if context.symbol not in ETF_CONSTITUENTS:
        return context
    context.constituent_snapshots = load_constituent_snapshots(context.symbol)
    context.constituent_internals = analyze_constituent_internals(context.symbol, context.constituent_snapshots)
    return context

# =========================================================
# DECISION ENGINE
# =========================================================
def score_to_grade(score: int) -> str:
    if score >= 90:
        return "A+"
    if score >= 75:
        return "A"
    if score >= 55:
        return "B"
    return "C"


def build_market_context(symbol: str) -> Optional[MarketContext]:
    data = get_symbol_snapshot(symbol)
    if not data:
        return None

    context = MarketContext(
        symbol=symbol,
        current_price=safe_float(data["price"]),
        vwap=safe_float(data["vwap"]),
        rsi=safe_float(data["rsi"]),
        change_pct=safe_float(data["change_pct"]),
        volume_ratio=safe_float(data["volume_ratio"]),
        above_vwap=safe_float(data["price"]) > safe_float(data["vwap"]),
        below_vwap=safe_float(data["price"]) < safe_float(data["vwap"]),
    )
    return enrich_context_with_constituents(context)


def make_hybrid_decision(context: MarketContext) -> TradePlan:
    reasons = []
    score = 50
    action = "NO_TRADE"

    if context.above_vwap:
        score += 12
        reasons.append("Price is above VWAP.")
    elif context.below_vwap:
        score += 12
        reasons.append("Price is below VWAP.")

    if context.above_vwap and context.rsi >= 55:
        score += 10
        reasons.append("Bullish RSI alignment.")
    elif context.below_vwap and context.rsi <= 45:
        score += 10
        reasons.append("Bearish RSI alignment.")
    else:
        reasons.append("RSI is neutral or not fully aligned.")

    if context.volume_ratio >= 1.20:
        score += 8
    if context.above_vwap and context.change_pct > 0:
        score += 8
    elif context.below_vwap and context.change_pct < 0:
        score += 8

    if context.above_vwap and context.rsi >= 52:
        action = "BUY_CALL"
    elif context.below_vwap and context.rsi <= 48:
        action = "BUY_PUT"

    return TradePlan(
        symbol=context.symbol,
        action=action,
        grade=score_to_grade(score),
        score=score,
        confidence=max(0.0, min(score / 100.0, 0.99)),
        reasons=reasons,
    )


def detect_chasing(context: MarketContext) -> Tuple[bool, str]:
    if context.vwap <= 0:
        return False, "VWAP unavailable for chase check."

    distance_pct = abs((context.current_price - context.vwap) / context.vwap) * 100.0
    if distance_pct >= CHASE_DISTANCE_PCT:
        return True, f"Price is extended {distance_pct:.2f}% from VWAP."
    return False, f"Price extension acceptable at {distance_pct:.2f}% from VWAP."


def assign_execution_tier(plan: TradePlan, context: MarketContext) -> TradePlan:
    plan.execution_qty = 0
    plan.execution_tier = "NONE"

    if plan.grade == "A+":
        plan.execution_tier = "FULL"
        plan.execution_qty = DEFAULT_ORDER_QTY
    elif plan.grade == "A":
        plan.execution_tier = "STANDARD"
        plan.execution_qty = DEFAULT_ORDER_QTY
    elif plan.grade == "B" and ALLOW_B_MICRO_SIZE and context.volume_ratio >= 3.0:
        plan.execution_tier = "MICRO"
        plan.execution_qty = B_MICRO_QTY

    return plan


def apply_constituent_confirmation(context: MarketContext, plan: TradePlan) -> TradePlan:
    ci = context.constituent_internals
    if ci:
        if plan.action == "BUY_CALL":
            if ci.confirmation_bias == "BULLISH_CONFIRMATION":
                plan.score += BULLISH_CONFIRM_BONUS
            elif ci.confirmation_bias == "BEARISH_CONFIRMATION":
                plan.score -= CONFLICT_PENALTY
            else:
                plan.score -= MIXED_PENALTY
        elif plan.action == "BUY_PUT":
            if ci.confirmation_bias == "BEARISH_CONFIRMATION":
                plan.score += BEARISH_CONFIRM_BONUS
            elif ci.confirmation_bias == "BULLISH_CONFIRMATION":
                plan.score -= CONFLICT_PENALTY
            else:
                plan.score -= MIXED_PENALTY

    if plan.action == "BUY_CALL" and context.rsi >= MIN_RSI_CALL:
        plan.score += 5
    elif plan.action == "BUY_CALL":
        plan.score -= 5

    if plan.action == "BUY_PUT" and context.rsi <= MAX_RSI_PUT:
        plan.score += 5
    elif plan.action == "BUY_PUT":
        plan.score -= 5

    chasing, _ = detect_chasing(context)
    plan.chasing = chasing
    if chasing:
        plan.score -= 15

    plan.grade = score_to_grade(plan.score)
    plan.confidence = max(0.0, min(plan.score / 100.0, 0.99))
    return assign_execution_tier(plan, context)


def execution_filter(plan: TradePlan, context: MarketContext) -> Tuple[str, List[str]]:
    notes = []
    ci = context.constituent_internals

    if plan.action == "NO_TRADE":
        return "AVOID", ["Blocked: no clear directional action."]
    if A_PLUS_ONLY_MODE and plan.grade != "A+":
        return "AVOID", ["Blocked: A+ sniper mode active."]
    if plan.chasing:
        return "AVOID", ["Blocked: trade is chasing away from decision zone."]
    if plan.confidence < MIN_CONFIDENCE and plan.grade != "B":
        return "AVOID", ["Blocked: confidence too low."]
    if ci:
        if plan.action == "BUY_CALL" and ci.confirmation_bias == "BEARISH_CONFIRMATION":
            return "AVOID", ["Blocked: bearish internals against call."]
        if plan.action == "BUY_PUT" and ci.confirmation_bias == "BULLISH_CONFIRMATION":
            return "AVOID", ["Blocked: bullish internals against put."]
    if context.volume_ratio < 0.85:
        return "AVOID", ["Blocked: volume too weak."]

    if plan.grade == "B":
        if not ALLOW_B_MICRO_SIZE or plan.execution_tier != "MICRO":
            return "AVOID", ["Blocked: B trade not approved."]
    elif not passes_grade_threshold(plan.grade, "A"):
        return "AVOID", ["Blocked: below A."]

    if plan.execution_qty <= 0:
        return "AVOID", ["Blocked: zero quantity."]

    notes.append(f"Execution filter passed. Tier={plan.execution_tier}, Qty={plan.execution_qty}")
    return "EXECUTE", notes

# =========================================================
# FREE ALERT
# =========================================================
def build_free_alert(plan: TradePlan, context: MarketContext, status: str) -> str:
    if status != "EXECUTE":
        return ""

    confidence_score = max(1, min(100, int(round(plan.confidence * 100))))
    return (
        f"📊 MARKET INSIGHT — {context.symbol}\n\n"
        f"A strong setup is active.\n"
        f"Timing: CONFIRMED\n"
        f"Confidence: {confidence_score}/100\n"
        f"Key Level: {context.vwap:.2f}\n\n"
        f"Join premium for execution access."
    )

# =========================================================
# OPTIONS CONTRACT PICKER
# =========================================================
def candidate_expirations() -> List[date]:
    today = now_et().date()
    return [today + timedelta(days=i) for i in range(OPTIONS_DTE_FALLBACK_DAYS + 1)]


def pick_option_contract(underlying: str, action: str, underlying_price: float):
    if not alpaca_client or not alpaca_options_ready:
        return None

    contract_type = ContractType.CALL if action == "BUY_CALL" else ContractType.PUT

    for exp in candidate_expirations():
        try:
            req = GetOptionContractsRequest(
                underlying_symbols=[underlying],
                status=AssetStatus.ACTIVE,
                expiration_date_gte=exp,
                expiration_date_lte=exp,
                type=contract_type,
            )
            result = alpaca_client.get_option_contracts(req)
            contracts = getattr(result, "option_contracts", []) or []

            ranked = []
            for contract in contracts:
                strike = safe_float(getattr(contract, "strike_price", 0.0))
                symbol = getattr(contract, "symbol", "")
                if strike <= 0 or not symbol:
                    continue

                target = underlying_price + OPTIONS_STRIKE_STEP_BUFFER if action == "BUY_CALL" else underlying_price - OPTIONS_STRIKE_STEP_BUFFER
                ranked.append((abs(strike - target), contract))

            if ranked:
                ranked.sort(key=lambda x: x[0])
                return ranked[0][1]
        except Exception as e:
            print(f"[OPTION PICKER WARN] {underlying} {action} {exp}: {e}", flush=True)

    return None

# =========================================================
# ALPACA ORDER STATUS / FILL TRACKING
# =========================================================
def get_order_status(order_id: str):
    if not alpaca_client or not order_id:
        return None
    try:
        return alpaca_client.get_order_by_id(order_id)
    except Exception as e:
        print(f"[ORDER STATUS ERROR] {order_id}: {e}", flush=True)
        return None


def normalize_order_status(order_obj) -> str:
    if order_obj is None:
        return "unknown"
    status = getattr(order_obj, "status", None)
    if status is None:
        return "unknown"
    try:
        return str(status).split(".")[-1].lower()
    except Exception:
        return str(status).lower()


def order_is_fill_like(status: str) -> bool:
    return status in {"filled", "partially_filled"}


def order_fill_price(order_obj) -> float:
    return safe_float(getattr(order_obj, "filled_avg_price", None), 0.0)


def order_filled_qty(order_obj) -> float:
    return safe_float(getattr(order_obj, "filled_qty", None), 0.0)

# =========================================================
# STATE HELPERS
# =========================================================
def get_today_key() -> str:
    return now_et().strftime("%Y-%m-%d")


def get_open_trades_for_symbol(state: Dict, symbol: str) -> List[Dict]:
    return [t for t in state.get("open_trades", []) if t.get("underlying") == symbol]


def get_daily_entry_count(state: Dict) -> int:
    return int(state.get("daily_entries", {}).get(get_today_key(), 0))


def increment_daily_entry_count(state: Dict) -> None:
    today_key = get_today_key()
    daily_entries = state.setdefault("daily_entries", {})
    daily_entries[today_key] = int(daily_entries.get(today_key, 0)) + 1


def set_recent_closure(state: Dict, symbol: str) -> None:
    state.setdefault("recent_closures", {})[symbol] = now_et().isoformat()


def cooldown_active(state: Dict, symbol: str) -> bool:
    recent = state.get("recent_closures", {}).get(symbol)
    if not recent:
        return False
    try:
        last_close = datetime.fromisoformat(recent)
        return (now_et() - last_close).total_seconds() < COOLDOWN_MINUTES * 60
    except Exception:
        return False


def can_open_new_trade(state: Dict, context: MarketContext) -> Tuple[bool, str]:
    if len(state.get("open_trades", [])) >= MAX_OPEN_TRADES:
        return False, "Max open trades reached."
    if get_open_trades_for_symbol(state, context.symbol):
        return False, f"Open trade already exists for {context.symbol}."
    if get_daily_entry_count(state) >= MAX_NEW_TRADES_PER_DAY:
        return False, "Max new trades per day reached."
    if cooldown_active(state, context.symbol):
        return False, f"Cooldown active for {context.symbol}."
    if entry_cutoff_reached():
        return False, "Entry cutoff reached."
    return True, "Entry allowed."

# =========================================================
# ENTRY / EXIT EXECUTION
# =========================================================
def submit_option_entry(plan: TradePlan, context: MarketContext, state: Dict) -> None:
    qty = max(0, int(plan.execution_qty))
    if qty <= 0:
        return

    allowed, reason = can_open_new_trade(state, context)
    if not allowed:
        broadcast_execution(f"⛔ ENTRY BLOCKED\nUnderlying: {context.symbol}\nReason: {reason}")
        return

    if not LIVE_TRADING:
        broadcast_execution(
            f"[PAPER MODE LOCAL] ENTRY TRACKED\nUnderlying: {context.symbol}\nAction: {plan.action}\nGrade: {plan.grade}\nTier: {plan.execution_tier}\nQty: {qty}"
        )
        return

    if alpaca_client is None:
        broadcast_execution("❌ LIVE_TRADING is ON but Alpaca is not connected.")
        return

    try:
        contract = pick_option_contract(context.symbol, plan.action, context.current_price)
        if contract is None:
            broadcast_execution(f"❌ No option contract found for {context.symbol} {plan.action}")
            return

        option_symbol = getattr(contract, "symbol", None)
        strike_price = getattr(contract, "strike_price", "NA")
        expiration_date = getattr(contract, "expiration_date", "NA")

        if not option_symbol:
            broadcast_execution(f"❌ Contract object missing symbol for {context.symbol} {plan.action}")
            return

        quote = get_option_latest_quote(option_symbol)
        ok, quote_reason = quote_is_tradeable(quote)
        if not ok:
            broadcast_execution(
                f"⛔ ENTRY BLOCKED — BAD OPTION QUOTE\n"
                f"Underlying: {context.symbol}\n"
                f"Contract: {option_symbol}\n"
                f"Reason: {quote_reason}"
            )
            return

        if is_regular_market_hours_et() and ALLOW_MARKET_ORDERS_DURING_RTH:
            order_request = MarketOrderRequest(
                symbol=option_symbol,
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
            )
            order_type_used = "MARKET"
            limit_price_used = None
        else:
            limit_price_used = compute_buy_limit_from_quote(quote)
            order_request = LimitOrderRequest(
                symbol=option_symbol,
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
                limit_price=limit_price_used,
            )
            order_type_used = "LIMIT"

        order = alpaca_client.submit_order(order_data=order_request)

        trade_record = {
            "underlying": context.symbol,
            "option_symbol": option_symbol,
            "action": plan.action,
            "grade": plan.grade,
            "score": plan.score,
            "execution_tier": plan.execution_tier,
            "qty": qty,
            "entry_underlying": context.current_price,
            "entry_time": now_et().isoformat(),
            "entry_order_id": str(order.id),
            "entry_order_status": "submitted",
            "entry_fill_price": None,
            "entry_filled_qty": 0,
            "entry_fill_alert_sent": False,
            "exit_order_id": None,
            "exit_order_status": None,
            "exit_fill_price": None,
            "exit_filled_qty": 0,
            "exit_fill_alert_sent": False,
            "be_armed": False,
            "strike": str(strike_price),
            "expiry": str(expiration_date),
        }
        state["open_trades"].append(trade_record)
        increment_daily_entry_count(state)
        save_state(state)

        broadcast_execution(
            f"✅ ALPACA OPTION ORDER SENT\n"
            f"Underlying: {context.symbol}\n"
            f"Contract: {option_symbol}\n"
            f"Action: {plan.action}\n"
            f"Qty: {qty}\n"
            f"Order Type: {order_type_used}\n"
            f"Bid: {quote['bid']:.4f}\n"
            f"Ask: {quote['ask']:.4f}\n"
            f"Spread: ${quote['spread_abs']:.4f} ({quote['spread_pct']:.2f}%)\n"
            f"Limit Price: {limit_price_used if limit_price_used is not None else 'N/A'}\n"
            f"Strike: {strike_price}\n"
            f"Expiry: {expiration_date}\n"
            f"Grade: {plan.grade}\n"
            f"Score: {plan.score}\n"
            f"Tier: {plan.execution_tier}\n"
            f"Order ID: {order.id}"
        )

        log_trade_event(
            event="ENTRY",
            underlying=context.symbol,
            option_symbol=option_symbol,
            action=plan.action,
            grade=plan.grade,
            execution_tier=plan.execution_tier,
            qty=qty,
            entry_underlying=context.current_price,
            current_underlying=context.current_price,
            underlying_move_pct=0.0,
            reason="entry_sent_real_quote_pricing",
            order_id=str(order.id),
        )

    except Exception as e:
        broadcast_execution(f"❌ ALPACA OPTION ENTRY FAILED: {e}")


def compute_directional_move_pct(trade: Dict, current_underlying: float) -> float:
    entry = safe_float(trade.get("entry_underlying"), 0.0)
    if entry <= 0:
        return 0.0

    raw_move = ((current_underlying - entry) / entry) * 100.0
    return raw_move if trade.get("action") == "BUY_CALL" else -raw_move


def should_exit_trade(trade: Dict, current_underlying: float) -> Tuple[bool, str, float]:
    move_pct = compute_directional_move_pct(trade, current_underlying)
    action = trade.get("action", "BUY_CALL")

    tp = CALL_TP_UNDERLYING_PCT if action == "BUY_CALL" else PUT_TP_UNDERLYING_PCT
    sl = CALL_SL_UNDERLYING_PCT if action == "BUY_CALL" else PUT_SL_UNDERLYING_PCT

    try:
        entry_time = datetime.fromisoformat(trade["entry_time"])
    except Exception:
        entry_time = now_et()

    age_minutes = max(0, (now_et() - entry_time).total_seconds() / 60.0)

    if move_pct >= BREAK_EVEN_TRIGGER_PCT and not trade.get("be_armed", False):
        trade["be_armed"] = True
        return False, "break_even_armed", move_pct

    if move_pct >= tp:
        return True, "take_profit_hit", move_pct

    effective_stop = 0.0 if trade.get("be_armed", False) else -sl
    if move_pct <= effective_stop:
        return True, "break_even_exit" if trade.get("be_armed", False) else "stop_hit", move_pct

    if age_minutes >= MAX_HOLD_MINUTES:
        return True, "max_hold_time_exit", move_pct

    if force_exit_reached():
        return True, "forced_end_of_day_exit", move_pct

    return False, "hold", move_pct


def submit_option_exit(trade: Dict, current_underlying: float, reason: str, move_pct: float, state: Dict) -> None:
    if alpaca_client is None:
        broadcast_execution(f"❌ EXIT FAILED — Alpaca not connected for {trade.get('underlying')}")
        return

    option_symbol = trade["option_symbol"]
    qty = int(trade["qty"])

    try:
        quote = get_option_latest_quote(option_symbol)
        ok, quote_reason = quote_is_tradeable(quote)
        if not ok:
            broadcast_execution(
                f"⛔ EXIT BLOCKED — BAD OPTION QUOTE\n"
                f"Underlying: {trade['underlying']}\n"
                f"Contract: {option_symbol}\n"
                f"Reason: {quote_reason}"
            )
            return

        if is_regular_market_hours_et() and ALLOW_MARKET_ORDERS_DURING_RTH:
            order_request = MarketOrderRequest(
                symbol=option_symbol,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            )
            order_type_used = "MARKET"
            limit_price_used = None
        else:
            limit_price_used = compute_sell_limit_from_quote(quote)
            order_request = LimitOrderRequest(
                symbol=option_symbol,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
                limit_price=limit_price_used,
            )
            order_type_used = "LIMIT"

        order = alpaca_client.submit_order(order_data=order_request)

        broadcast_execution(
            f"🔒 EXIT ORDER SENT\n"
            f"Underlying: {trade['underlying']}\n"
            f"Contract: {option_symbol}\n"
            f"Action: SELL TO CLOSE\n"
            f"Qty: {qty}\n"
            f"Order Type: {order_type_used}\n"
            f"Bid: {quote['bid']:.4f}\n"
            f"Ask: {quote['ask']:.4f}\n"
            f"Spread: ${quote['spread_abs']:.4f} ({quote['spread_pct']:.2f}%)\n"
            f"Limit Price: {limit_price_used if limit_price_used is not None else 'N/A'}\n"
            f"Reason: {reason}\n"
            f"Underlying Move: {move_pct:.2f}%\n"
            f"Order ID: {order.id}"
        )

        log_trade_event(
            event="EXIT",
            underlying=trade["underlying"],
            option_symbol=option_symbol,
            action=trade["action"],
            grade=trade["grade"],
            execution_tier=trade["execution_tier"],
            qty=qty,
            entry_underlying=safe_float(trade["entry_underlying"]),
            current_underlying=current_underlying,
            underlying_move_pct=move_pct,
            reason=reason,
            order_id=str(order.id),
        )

        trade["exit_order_id"] = str(order.id)
        trade["exit_order_status"] = "submitted"
        trade["exit_fill_price"] = None
        trade["exit_filled_qty"] = 0
        trade["exit_fill_alert_sent"] = False
        save_state(state)

    except Exception as e:
        broadcast_execution(
            f"❌ ALPACA OPTION EXIT FAILED\n"
            f"Underlying: {trade.get('underlying')}\n"
            f"Contract: {option_symbol}\n"
            f"Reason: {reason}\n"
            f"Error: {e}"
        )

# =========================================================
# FILL TRACKING
# =========================================================
def update_entry_fills(state: Dict) -> None:
    changed = False

    for trade in state.get("open_trades", []):
        order_id = trade.get("entry_order_id")
        if not order_id:
            continue

        order_obj = get_order_status(order_id)
        status = normalize_order_status(order_obj)
        prev_status = trade.get("entry_order_status")

        trade["entry_order_status"] = status
        trade["entry_filled_qty"] = order_filled_qty(order_obj)
        fill_price = order_fill_price(order_obj)
        if fill_price > 0:
            trade["entry_fill_price"] = fill_price

        if status != prev_status:
            broadcast_execution(
                f"📥 ENTRY ORDER STATUS UPDATE\n"
                f"Underlying: {trade['underlying']}\n"
                f"Contract: {trade['option_symbol']}\n"
                f"Order ID: {order_id}\n"
                f"Status: {status}\n"
                f"Filled Qty: {trade['entry_filled_qty']}\n"
                f"Avg Fill Price: {trade['entry_fill_price'] if trade['entry_fill_price'] else 'N/A'}"
            )
            changed = True

        if order_is_fill_like(status) and not trade.get("entry_fill_alert_sent", False):
            broadcast_execution(
                f"✅ ENTRY FILL CONFIRMED\n"
                f"Underlying: {trade['underlying']}\n"
                f"Contract: {trade['option_symbol']}\n"
                f"Status: {status}\n"
                f"Filled Qty: {trade['entry_filled_qty']}\n"
                f"Avg Fill Price: {trade['entry_fill_price'] if trade['entry_fill_price'] else 'N/A'}"
            )

            log_trade_event(
                event="ENTRY_FILL",
                underlying=trade["underlying"],
                option_symbol=trade["option_symbol"],
                action=trade["action"],
                grade=trade["grade"],
                execution_tier=trade["execution_tier"],
                qty=int(trade["qty"]),
                entry_underlying=safe_float(trade["entry_underlying"]),
                current_underlying=safe_float(trade["entry_underlying"]),
                underlying_move_pct=0.0,
                reason=status,
                order_id=order_id,
            )

            trade["entry_fill_alert_sent"] = True
            changed = True

    if changed:
        save_state(state)


def update_exit_fills(state: Dict) -> None:
    changed = False

    for trade in state.get("open_trades", []):
        exit_order_id = trade.get("exit_order_id")
        if not exit_order_id:
            continue

        order_obj = get_order_status(exit_order_id)
        status = normalize_order_status(order_obj)
        prev_status = trade.get("exit_order_status")

        trade["exit_order_status"] = status
        trade["exit_filled_qty"] = order_filled_qty(order_obj)
        fill_price = order_fill_price(order_obj)
        if fill_price > 0:
            trade["exit_fill_price"] = fill_price

        if status != prev_status:
            broadcast_execution(
                f"📤 EXIT ORDER STATUS UPDATE\n"
                f"Underlying: {trade['underlying']}\n"
                f"Contract: {trade['option_symbol']}\n"
                f"Order ID: {exit_order_id}\n"
                f"Status: {status}\n"
                f"Filled Qty: {trade['exit_filled_qty']}\n"
                f"Avg Fill Price: {trade['exit_fill_price'] if trade['exit_fill_price'] else 'N/A'}"
            )
            changed = True

        if status == "filled" and not trade.get("exit_fill_alert_sent", False):
            entry_fill = safe_float(trade.get("entry_fill_price"), 0.0)
            exit_fill = safe_float(trade.get("exit_fill_price"), 0.0)
            pnl_pct = ((exit_fill - entry_fill) / entry_fill * 100.0) if entry_fill > 0 else 0.0

            broadcast_execution(
                f"🏁 TRADE CLOSED\n"
                f"Underlying: {trade['underlying']}\n"
                f"Contract: {trade['option_symbol']}\n"
                f"Entry Fill: {entry_fill if entry_fill > 0 else 'N/A'}\n"
                f"Exit Fill: {exit_fill if exit_fill > 0 else 'N/A'}\n"
                f"PnL: {pnl_pct:.2f}%\n"
                f"Grade: {trade['grade']}\n"
                f"Tier: {trade['execution_tier']}"
            )

            log_trade_event(
                event="EXIT_FILL",
                underlying=trade["underlying"],
                option_symbol=trade["option_symbol"],
                action=trade["action"],
                grade=trade["grade"],
                execution_tier=trade["execution_tier"],
                qty=int(trade["qty"]),
                entry_underlying=safe_float(trade["entry_underlying"]),
                current_underlying=safe_float(trade["entry_underlying"]),
                underlying_move_pct=0.0,
                reason=f"pnl_pct={pnl_pct:.2f}",
                order_id=exit_order_id,
            )

            trade["exit_fill_alert_sent"] = True
            changed = True

    if changed:
        save_state(state)


def purge_filled_exits(state: Dict) -> None:
    remaining = []
    changed = False

    for trade in state.get("open_trades", []):
        if trade.get("exit_order_status") == "filled":
            set_recent_closure(state, trade["underlying"])
            changed = True
            continue
        remaining.append(trade)

    if changed:
        state["open_trades"] = remaining
        save_state(state)

# =========================================================
# OPEN TRADE MANAGEMENT
# =========================================================
def manage_open_trades(state: Dict) -> None:
    update_entry_fills(state)
    update_exit_fills(state)
    purge_filled_exits(state)

    open_trades = list(state.get("open_trades", []))
    if not open_trades:
        return

    for trade in open_trades:
        if trade.get("exit_order_id"):
            continue

        snapshot = get_symbol_snapshot(trade["underlying"])
        if not snapshot:
            continue

        current_underlying = safe_float(snapshot["price"])
        should_exit, reason, move_pct = should_exit_trade(trade, current_underlying)

        if reason == "break_even_armed":
            save_state(state)
            broadcast_execution(
                f"🛡 BREAK-EVEN ARMED\n"
                f"Underlying: {trade['underlying']}\n"
                f"Contract: {trade['option_symbol']}\n"
                f"Underlying Move: {move_pct:.2f}%"
            )
            continue

        if should_exit:
            submit_option_exit(trade, current_underlying, reason, move_pct, state)
        else:
            broadcast_execution(
                f"📡 OPEN TRADE CHECK\n"
                f"Underlying: {trade['underlying']}\n"
                f"Contract: {trade['option_symbol']}\n"
                f"Action: {trade['action']}\n"
                f"Grade: {trade['grade']}\n"
                f"Underlying Entry: {safe_float(trade['entry_underlying']):.2f}\n"
                f"Underlying Now: {current_underlying:.2f}\n"
                f"Underlying Move: {move_pct:.2f}%\n"
                f"Break-Even Armed: {trade.get('be_armed', False)}"
            )

# =========================================================
# MAIN
# =========================================================
def run_symbol(symbol: str, state: Dict) -> None:
    context = build_market_context(symbol)
    if not context:
        print(f"[WARN] Could not build context for {symbol}", flush=True)
        return

    plan = make_hybrid_decision(context)
    plan = apply_constituent_confirmation(context, plan)
    status, _ = execution_filter(plan, context)

    free_msg = build_free_alert(plan, context, status)
    if free_msg:
        broadcast_free(free_msg)

    if status == "EXECUTE":
        submit_option_entry(plan, context, state)


def run_cycle(state: Dict) -> None:
    manage_open_trades(state)

    for symbol in WATCHLIST:
        run_symbol(symbol, state)
        time.sleep(2)


def main() -> None:
    ensure_trade_log_exists()
    state = load_state()

    broadcast_execution(
        "🚀 ELITE EXECUTION ENGINE STARTED\n"
        f"Watchlist: {', '.join(WATCHLIST)}\n"
        f"LIVE_TRADING: {LIVE_TRADING}\n"
        f"ALPACA_PAPER: {ALPACA_PAPER}\n"
        f"Alpaca Connected: {alpaca_client is not None}\n"
        f"Alpaca Options Ready: {alpaca_options_ready}\n"
        f"Option Feed: {OPTION_QUOTE_FEED}\n"
        f"Open Trades Loaded: {len(state.get('open_trades', []))}\n"
        f"RUN_ONCE: {RUN_ONCE}"
    )

    if alpaca_client is not None:
        try:
            account = alpaca_client.get_account()
            broadcast_execution(
                "✅ ALPACA CONNECTION OK\n"
                f"Status: {account.status}\n"
                f"Buying Power: {account.buying_power}\n"
                f"Mode: {'PAPER' if ALPACA_PAPER else 'LIVE'}"
            )
        except Exception as e:
            broadcast_execution(f"❌ ALPACA CONNECTION FAILED: {e}")

    if RUN_ONCE:
        run_cycle(state)
        return

    while True:
        try:
            run_cycle(state)
        except Exception as e:
            broadcast_execution(f"❌ MAIN LOOP ERROR: {e}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()

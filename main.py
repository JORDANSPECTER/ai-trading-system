import os
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

import requests

# Optional Alpaca imports
ALPACA_AVAILABLE = True
try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest
    from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
except Exception:
    ALPACA_AVAILABLE = False


# ============================================================
# HELPERS
# ============================================================

def env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except Exception:
        return default


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except Exception:
        return default


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_float(value, default: Optional[float] = 0.0) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def pct_change(current_value: float, base_value: float) -> float:
    if not base_value:
        return 0.0
    return ((current_value - base_value) / base_value) * 100.0


def grade_rank(grade: str) -> int:
    ranks = {"A+": 5, "A": 4, "B": 3, "C": 2, "D": 1}
    return ranks.get(grade.upper(), 0)


def grade_from_score(score: int) -> str:
    if score >= 90:
        return "A+"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    return "D"


def is_daily_levels_window() -> bool:
    """
    9AM to 9PM Eastern approximated by UTC windows used in workflow:
    13:00-23:59 UTC and 00:00-01:59 UTC
    """
    now = datetime.now(timezone.utc)
    hour = now.hour
    return (13 <= hour <= 23) or (0 <= hour <= 1)


# ============================================================
# CONFIG
# ============================================================

@dataclass
class Config:
    # Market / alerts
    twelve_data_api_key: str
    primary_symbol: str
    secondary_symbol: str
    oil_symbol: str
    volatility_symbol: str

    state_file: str
    dedupe_price_rounding: int
    alert_cooldown_seconds: int
    daily_levels_cooldown_seconds: int

    telegram_enabled: bool
    telegram_bot_token: str
    telegram_chat_id: str

    discord_enabled: bool
    discord_free_webhook: str
    discord_premium_webhook: str
    discord_daily_levels_webhook: str

    premium_min_grade: str
    free_min_grade: str
    min_score_for_free: int
    min_score_for_premium: int

    oil_impact_threshold: float
    price_change_threshold_pct: float
    vwap_distance_threshold_pct: float

    daily_levels_enabled: bool
    risk_warning_text: str
    debug: bool

    # Execution / Alpaca
    execution_enabled: bool
    execution_min_grade: str
    alpaca_api_key: str
    alpaca_secret_key: str
    alpaca_paper: bool
    max_position_notional: float
    max_open_positions: int
    default_time_in_force: str


def load_config() -> Config:
    return Config(
        twelve_data_api_key=env_str("TWELVE_DATA_API_KEY"),

        primary_symbol=env_str("PRIMARY_SYMBOL", "QQQ"),
        secondary_symbol=env_str("SECONDARY_SYMBOL", "SPY"),
        oil_symbol=env_str("OIL_SYMBOL", "USO"),
        volatility_symbol=env_str("VOLATILITY_SYMBOL", "VIX"),

        state_file=env_str("STATE_FILE", "elite_state.json"),
        dedupe_price_rounding=env_int("DEDUPE_PRICE_ROUNDING", 2),
        alert_cooldown_seconds=env_int("ALERT_COOLDOWN_SECONDS", 900),
        daily_levels_cooldown_seconds=env_int("DAILY_LEVELS_COOLDOWN_SECONDS", 1200),

        telegram_enabled=env_bool("TELEGRAM_ENABLED", True),
        telegram_bot_token=env_str("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=env_str("TELEGRAM_CHAT_ID"),

        discord_enabled=env_bool("DISCORD_ENABLED", True),
        discord_free_webhook=env_str("DISCORD_FREE_WEBHOOK"),
        discord_premium_webhook=env_str("DISCORD_PREMIUM_WEBHOOK"),
        discord_daily_levels_webhook=env_str("DISCORD_DAILY_LEVELS_WEBHOOK"),

        premium_min_grade=env_str("PREMIUM_MIN_GRADE", "A"),
        free_min_grade=env_str("FREE_MIN_GRADE", "B"),
        min_score_for_free=env_int("MIN_SCORE_FOR_FREE", 70),
        min_score_for_premium=env_int("MIN_SCORE_FOR_PREMIUM", 80),

        oil_impact_threshold=env_float("OIL_IMPACT_THRESHOLD", 1.25),
        price_change_threshold_pct=env_float("PRICE_CHANGE_THRESHOLD_PCT", 0.35),
        vwap_distance_threshold_pct=env_float("VWAP_DISTANCE_THRESHOLD_PCT", 0.15),

        daily_levels_enabled=env_bool("DAILY_LEVELS_ENABLED", True),
        risk_warning_text=env_str(
            "RISK_WARNING_TEXT",
            "Educational alert only. Not financial advice. Wait for confirmation at key levels."
        ),
        debug=env_bool("DEBUG", False),

        execution_enabled=env_bool("EXECUTION_ENABLED", False),
        execution_min_grade=env_str("EXECUTION_MIN_GRADE", "A"),
        alpaca_api_key=env_str("ALPACA_API_KEY"),
        alpaca_secret_key=env_str("ALPACA_SECRET_KEY"),
        alpaca_paper=env_bool("ALPACA_PAPER", True),
        max_position_notional=env_float("MAX_POSITION_NOTIONAL", 500.0),
        max_open_positions=env_int("MAX_OPEN_POSITIONS", 2),
        default_time_in_force=env_str("DEFAULT_TIME_IN_FORCE", "day"),
    )


def debug_log(cfg: Config, msg: str) -> None:
    if cfg.debug:
        print(f"[DEBUG] {msg}")


# ============================================================
# DATA MODELS
# ============================================================

@dataclass
class Quote:
    symbol: str
    price: float
    open_price: float
    high: float
    low: float
    previous_close: float
    change_pct: float
    timestamp: str


@dataclass
class IndicatorPack:
    symbol: str
    vwap: Optional[float] = None
    rsi: Optional[float] = None
    ema9: Optional[float] = None
    ema20: Optional[float] = None


@dataclass
class MarketContext:
    primary: Quote
    secondary: Quote
    oil: Optional[Quote]
    volatility: Optional[Quote]
    primary_indicators: IndicatorPack
    secondary_indicators: IndicatorPack
    previous_day_high: Optional[float]
    previous_day_low: Optional[float]
    premarket_high: Optional[float]
    premarket_low: Optional[float]


@dataclass
class SetupScore:
    score: int
    grade: str
    direction: str
    reasons: List[str]
    premium_reasons: List[str]
    risk_flags: List[str]


@dataclass
class AlertPayload:
    alert_type: str
    symbol: str
    title: str
    body: str
    grade: str
    direction: str
    score: int
    tags: List[str]
    key: str
    timestamp_utc: str


@dataclass
class PersistentState:
    last_alert_times: Dict[str, float] = field(default_factory=dict)
    last_market_snapshot: Dict[str, float] = field(default_factory=dict)
    executed_signal_keys: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    @staticmethod
    def load(path: str) -> "PersistentState":
        if not os.path.exists(path):
            return PersistentState()
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            return PersistentState(
                last_alert_times=raw.get("last_alert_times", {}),
                last_market_snapshot=raw.get("last_market_snapshot", {}),
                executed_signal_keys=raw.get("executed_signal_keys", {}),
            )
        except Exception:
            return PersistentState()

    def save(self, path: str) -> None:
        payload = {
            "last_alert_times": self.last_alert_times,
            "last_market_snapshot": self.last_market_snapshot,
            "executed_signal_keys": self.executed_signal_keys,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)


# ============================================================
# TWELVE DATA CLIENT
# ============================================================

class TwelveDataClient:
    BASE_URL = "https://api.twelvedata.com"

    def __init__(self, api_key: str, cfg: Config):
        self.api_key = api_key
        self.cfg = cfg

    def _get(self, endpoint: str, params: Dict) -> Dict:
        params = dict(params)
        params["apikey"] = self.api_key
        response = requests.get(f"{self.BASE_URL}/{endpoint}", params=params, timeout=20)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, dict) and data.get("status") == "error":
            raise RuntimeError(f"Twelve Data error: {data}")
        return data

    def get_quote(self, symbol: str) -> Quote:
        if not symbol:
            raise RuntimeError("Symbol is blank. Check GitHub secrets.")

        data = self._get("quote", {"symbol": symbol})

        price = safe_float(data.get("close"), 0.0)
        open_price = safe_float(data.get("open"), 0.0)
        high = safe_float(data.get("high"), 0.0)
        low = safe_float(data.get("low"), 0.0)
        previous_close = safe_float(data.get("previous_close"), 0.0)

        change_pct_val = safe_float(data.get("percent_change"), 0.0)
        if change_pct_val == 0 and previous_close:
            change_pct_val = pct_change(price, previous_close)

        return Quote(
            symbol=symbol,
            price=price,
            open_price=open_price,
            high=high,
            low=low,
            previous_close=previous_close,
            change_pct=change_pct_val,
            timestamp=now_utc_iso(),
        )

    def get_indicator(self, symbol: str, endpoint: str, interval: str) -> Optional[float]:
        try:
            data = self._get(endpoint, {"symbol": symbol, "interval": interval, "outputsize": 1})
            values = data.get("values", [])
            if not values:
                return None

            latest = values[0]
            if endpoint == "vwap":
                return safe_float(latest.get("vwap"), None)
            if endpoint == "rsi":
                return safe_float(latest.get("rsi"), None)
            if endpoint == "ema":
                return safe_float(latest.get("ema"), None)
            return None
        except Exception as e:
            debug_log(self.cfg, f"{symbol} {endpoint} failed: {e}")
            return None

    def get_indicator_pack(self, symbol: str) -> IndicatorPack:
        return IndicatorPack(
            symbol=symbol,
            vwap=self.get_indicator(symbol, "vwap", "1min"),
            rsi=self.get_indicator(symbol, "rsi", "5min"),
            ema9=self.get_indicator(symbol, "ema", "5min"),
            ema20=self.get_indicator(symbol, "ema", "15min"),
        )


# ============================================================
# BUILD CONTEXT
# ============================================================

def build_market_context(client: TwelveDataClient, cfg: Config) -> MarketContext:
    primary = client.get_quote(cfg.primary_symbol)
    secondary = client.get_quote(cfg.secondary_symbol)

    oil = None
    volatility = None

    try:
        oil = client.get_quote(cfg.oil_symbol)
    except Exception as e:
        debug_log(cfg, f"oil quote failed: {e}")

    try:
        volatility = client.get_quote(cfg.volatility_symbol)
    except Exception as e:
        debug_log(cfg, f"volatility quote failed: {e}")

    primary_indicators = client.get_indicator_pack(cfg.primary_symbol)
    secondary_indicators = client.get_indicator_pack(cfg.secondary_symbol)

    previous_day_high = primary.high
    previous_day_low = primary.low
    premarket_high = primary.high
    premarket_low = primary.low

    return MarketContext(
        primary=primary,
        secondary=secondary,
        oil=oil,
        volatility=volatility,
        primary_indicators=primary_indicators,
        secondary_indicators=secondary_indicators,
        previous_day_high=previous_day_high,
        previous_day_low=previous_day_low,
        premarket_high=premarket_high,
        premarket_low=premarket_low,
    )


# ============================================================
# SCORING
# ============================================================

def score_setup(ctx: MarketContext, cfg: Config) -> SetupScore:
    score = 50
    reasons: List[str] = []
    premium_reasons: List[str] = []
    risk_flags: List[str] = []

    price = ctx.primary.price
    vwap = ctx.primary_indicators.vwap
    rsi = ctx.primary_indicators.rsi
    ema9 = ctx.primary_indicators.ema9
    ema20 = ctx.primary_indicators.ema20

    bullish_points = 0
    bearish_points = 0

    if vwap is not None:
        if price > vwap:
            score += 10
            bullish_points += 1
            reasons.append(f"{ctx.primary.symbol} is above VWAP ({vwap:.2f}).")
        elif price < vwap:
            score += 10
            bearish_points += 1
            reasons.append(f"{ctx.primary.symbol} is below VWAP ({vwap:.2f}).")

        distance_pct = abs(pct_change(price, vwap))
        if distance_pct <= cfg.vwap_distance_threshold_pct:
            score += 5
            premium_reasons.append("Price is trading tight around VWAP.")
        else:
            risk_flags.append("Price is extended away from VWAP.")
    else:
        risk_flags.append("VWAP unavailable.")

    if rsi is not None:
        if 48 <= rsi <= 62:
            score += 8
            reasons.append(f"RSI is healthy at {rsi:.1f}.")
        elif rsi > 70:
            score -= 6
            risk_flags.append(f"RSI is hot at {rsi:.1f}.")
        elif rsi < 30:
            score -= 6
            risk_flags.append(f"RSI is weak at {rsi:.1f}.")
    else:
        risk_flags.append("RSI unavailable.")

    if ema9 is not None and ema20 is not None:
        if ema9 > ema20:
            score += 7
            bullish_points += 1
            reasons.append("Short-term momentum is bullish (EMA9 > EMA20).")
        elif ema9 < ema20:
            score += 7
            bearish_points += 1
            reasons.append("Short-term momentum is bearish (EMA9 < EMA20).")
    else:
        risk_flags.append("EMA trend data unavailable.")

    if abs(ctx.primary.change_pct) >= cfg.price_change_threshold_pct:
        score += 8
        reasons.append(f"Price is moving with intent ({ctx.primary.change_pct:+.2f}%).")
    else:
        risk_flags.append("Move is still small; chop risk is higher.")

    if ctx.oil and abs(ctx.oil.change_pct) >= cfg.oil_impact_threshold:
        premium_reasons.append(
            f"Oil is making a meaningful move ({ctx.oil.symbol} {ctx.oil.change_pct:+.2f}%)."
        )
        if ctx.oil.change_pct > 0:
            bearish_points += 1
            reasons.append("Oil pressure favors caution on long-side index continuation.")
        else:
            bullish_points += 1
            reasons.append("Oil relief supports index stabilization or upside continuation.")

    if ctx.volatility:
        if ctx.volatility.change_pct > 2.0:
            bearish_points += 1
            risk_flags.append(f"{ctx.volatility.symbol} is elevated ({ctx.volatility.change_pct:+.2f}%).")
        elif ctx.volatility.change_pct < -2.0:
            bullish_points += 1
            premium_reasons.append(f"{ctx.volatility.symbol} is easing ({ctx.volatility.change_pct:+.2f}%).")

    if bullish_points > bearish_points:
        direction = "BULLISH"
        score += 5
    elif bearish_points > bullish_points:
        direction = "BEARISH"
        score += 5
    else:
        direction = "NEUTRAL"
        score -= 5
        risk_flags.append("Bullish and bearish evidence is mixed.")

    score = max(0, min(score, 100))
    grade = grade_from_score(score)

    return SetupScore(
        score=score,
        grade=grade,
        direction=direction,
        reasons=reasons,
        premium_reasons=premium_reasons,
        risk_flags=risk_flags,
    )


# ============================================================
# ALERT BUILDERS
# ============================================================

def build_daily_levels_alert(ctx: MarketContext, cfg: Config) -> Alert

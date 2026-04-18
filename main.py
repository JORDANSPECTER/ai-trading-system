import os
import json
import math
import time
import traceback
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import requests


# ============================================================
# NORMALIZED ELITE MAIN.PY
# ============================================================
# PURPOSE
# - Clean production alert engine
# - One scoring engine
# - One formatter
# - One routing layer
# - One main loop
#
# NOTES
# - This version is built for alerting / analysis / routing.
# - It does NOT place live broker orders.
# - It is designed so option pricing, fill tracking, and
#   execution memory can plug in cleanly next.
# ============================================================


# ============================================================
# ENV / CONFIG
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


@dataclass
class Config:
    # Core
    twelve_data_api_key: str
    poll_seconds: int
    state_file: str

    # Symbols
    primary_symbol: str
    secondary_symbol: str
    oil_symbol: str
    volatility_symbol: str

    # Telegram
    telegram_bot_token: str
    telegram_chat_id: str
    telegram_enabled: bool

    # Discord webhooks
    discord_free_webhook: str
    discord_premium_webhook: str
    discord_daily_levels_webhook: str
    discord_enabled: bool

    # Cooldowns / anti-spam
    alert_cooldown_seconds: int
    daily_levels_cooldown_seconds: int
    dedupe_price_rounding: int

    # Premium / grade routing
    premium_min_grade: str
    free_min_grade: str
    send_sub_a_to_premium: bool

    # Thresholds
    min_score_for_free: int
    min_score_for_premium: int
    min_volume_bias_score: int
    oil_impact_threshold: float
    price_change_threshold_pct: float
    vwap_distance_threshold_pct: float

    # Daily levels
    daily_levels_enabled: bool
    daily_levels_only_once_per_day: bool

    # Risk / info
    risk_warning_text: str

    # Debug
    debug: bool


def load_config() -> Config:
    return Config(
        twelve_data_api_key=env_str("TWELVE_DATA_API_KEY"),
        poll_seconds=env_int("POLL_SECONDS", 60),
        state_file=env_str("STATE_FILE", "elite_state.json"),

        primary_symbol=env_str("PRIMARY_SYMBOL", "QQQ"),
        secondary_symbol=env_str("SECONDARY_SYMBOL", "SPY"),
        oil_symbol=env_str("OIL_SYMBOL", "USO"),
        volatility_symbol=env_str("VOLATILITY_SYMBOL", "VIX"),

        telegram_bot_token=env_str("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=env_str("TELEGRAM_CHAT_ID"),
        telegram_enabled=env_bool("TELEGRAM_ENABLED", True),

        discord_free_webhook=env_str("DISCORD_FREE_WEBHOOK"),
        discord_premium_webhook=env_str("DISCORD_PREMIUM_WEBHOOK"),
        discord_daily_levels_webhook=env_str("DISCORD_DAILY_LEVELS_WEBHOOK"),
        discord_enabled=env_bool("DISCORD_ENABLED", True),

        alert_cooldown_seconds=env_int("ALERT_COOLDOWN_SECONDS", 900),
        daily_levels_cooldown_seconds=env_int("DAILY_LEVELS_COOLDOWN_SECONDS", 21600),
        dedupe_price_rounding=env_int("DEDUPE_PRICE_ROUNDING", 2),

        premium_min_grade=env_str("PREMIUM_MIN_GRADE", "A"),
        free_min_grade=env_str("FREE_MIN_GRADE", "B"),
        send_sub_a_to_premium=env_bool("SEND_SUB_A_TO_PREMIUM", True),

        min_score_for_free=env_int("MIN_SCORE_FOR_FREE", 60),
        min_score_for_premium=env_int("MIN_SCORE_FOR_PREMIUM", 80),
        min_volume_bias_score=env_int("MIN_VOLUME_BIAS_SCORE", 1),
        oil_impact_threshold=env_float("OIL_IMPACT_THRESHOLD", 1.25),
        price_change_threshold_pct=env_float("PRICE_CHANGE_THRESHOLD_PCT", 0.35),
        vwap_distance_threshold_pct=env_float("VWAP_DISTANCE_THRESHOLD_PCT", 0.15),

        daily_levels_enabled=env_bool("DAILY_LEVELS_ENABLED", True),
        daily_levels_only_once_per_day=env_bool("DAILY_LEVELS_ONLY_ONCE_PER_DAY", True),

        risk_warning_text=env_str(
            "RISK_WARNING_TEXT",
            "Educational alert only. Not financial advice. Wait for confirmation at key levels."
        ),

        debug=env_bool("DEBUG", False),
    )


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
    previous_day_high: Optional[float] = None
    previous_day_low: Optional[float] = None
    premarket_high: Optional[float] = None
    premarket_low: Optional[float] = None


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
    alert_type: str                   # TRADE_ALERT / DAILY_LEVELS / INFO
    symbol: str
    title: str
    body: str
    grade: str
    direction: str
    score: int
    tags: List[str]
    key: str                         # used for dedupe
    timestamp_utc: str


@dataclass
class FillRecord:
    timestamp_utc: str
    symbol: str
    direction: str
    entry_price: float
    stop_price: Optional[float]
    target_price: Optional[float]
    notes: str = ""


@dataclass
class PersistentState:
    last_alert_times: Dict[str, float] = field(default_factory=dict)
    last_daily_levels_date: str = ""
    last_market_snapshot: Dict[str, float] = field(default_factory=dict)
    fill_history: List[Dict] = field(default_factory=list)

    @staticmethod
    def load(path: str) -> "PersistentState":
        if not os.path.exists(path):
            return PersistentState()
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            return PersistentState(
                last_alert_times=raw.get("last_alert_times", {}),
                last_daily_levels_date=raw.get("last_daily_levels_date", ""),
                last_market_snapshot=raw.get("last_market_snapshot", {}),
                fill_history=raw.get("fill_history", []),
            )
        except Exception:
            return PersistentState()

    def save(self, path: str) -> None:
        payload = {
            "last_alert_times": self.last_alert_times,
            "last_daily_levels_date": self.last_daily_levels_date,
            "last_market_snapshot": self.last_market_snapshot,
            "fill_history": self.fill_history,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)


# ============================================================
# HELPERS
# ============================================================

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def safe_float(value: Optional[str], default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def pct_change(current_value: float, base_value: float) -> float:
    if base_value == 0:
        return 0.0
    return ((current_value - base_value) / base_value) * 100.0


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


def grade_rank(grade: str) -> int:
    order = {
        "A+": 5,
        "A": 4,
        "B": 3,
        "C": 2,
        "D": 1,
    }
    return order.get(grade.upper(), 0)


def debug_log(cfg: Config, message: str) -> None:
    if cfg.debug:
        print(f"[DEBUG] {message}")


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
        url = f"{self.BASE_URL}/{endpoint}"

        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, dict) and data.get("status") == "error":
            raise RuntimeError(f"Twelve Data error: {data}")
        return data

    def get_quote(self, symbol: str) -> Quote:
        data = self._get("quote", {"symbol": symbol})

        price = safe_float(data.get("close"))
        open_price = safe_float(data.get("open"))
        high = safe_float(data.get("high"))
        low = safe_float(data.get("low"))
        previous_close = safe_float(data.get("previous_close"))

        change_pct_val = safe_float(data.get("percent_change"))
        if change_pct_val == 0 and previous_close > 0:
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

    def get_indicator(self, symbol: str, indicator: str, interval: str = "1min", outputsize: int = 1) -> Optional[float]:
        try:
            data = self._get(
                indicator,
                {
                    "symbol": symbol,
                    "interval": interval,
                    "outputsize": outputsize,
                },
            )
            values = data.get("values", [])
            if not values:
                return None

            latest = values[0]
            # Twelve Data field name can vary by endpoint
            for key in ["vwap", "rsi", "ema"]:
                if key in latest:
                    return safe_float(latest[key], None)
            return None
        except Exception as e:
            debug_log(self.cfg, f"Indicator error {symbol} {indicator}: {e}")
            return None

    def get_indicator_pack(self, symbol: str) -> IndicatorPack:
        return IndicatorPack(
            symbol=symbol,
            vwap=self.get_indicator(symbol, "vwap", interval="1min"),
            rsi=self.get_indicator(symbol, "rsi", interval="5min"),
            ema9=self.get_indicator(symbol, "ema", interval="5min"),
            ema20=self.get_indicator(symbol, "ema", interval="15min"),
        )


# ============================================================
# MARKET BUILDER
# ============================================================

def build_market_context(client: TwelveDataClient, cfg: Config) -> MarketContext:
    primary_quote = client.get_quote(cfg.primary_symbol)
    secondary_quote = client.get_quote(cfg.secondary_symbol)

    oil_quote = None
    volatility_quote = None

    try:
        oil_quote = client.get_quote(cfg.oil_symbol)
    except Exception as e:
        debug_log(cfg, f"Oil quote unavailable: {e}")

    try:
        volatility_quote = client.get_quote(cfg.volatility_symbol)
    except Exception as e:
        debug_log(cfg, f"Volatility quote unavailable: {e}")

    primary_ind = client.get_indicator_pack(cfg.primary_symbol)
    secondary_ind = client.get_indicator_pack(cfg.secondary_symbol)

    # Elite placeholders:
    # These can later be replaced by true premarket and prior-day logic
    previous_day_high = max(primary_quote.open_price, primary_quote.high)
    previous_day_low = min(primary_quote.open_price, primary_quote.low)
    premarket_high = primary_quote.high
    premarket_low = primary_quote.low

    return MarketContext(
        primary=primary_quote,
        secondary=secondary_quote,
        oil=oil_quote,
        volatility=volatility_quote,
        primary_indicators=primary_ind,
        secondary_indicators=secondary_ind,
        previous_day_high=previous_day_high,
        previous_day_low=previous_day_low,
        premarket_high=premarket_high,
        premarket_low=premarket_low,
    )


# ============================================================
# ELITE OPTION PRICING PLACEHOLDER
# ============================================================

def norm_cdf(x: float) -> float:
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def black_scholes_call_price(spot: float, strike: float, time_to_expiry_years: float, rate: float, volatility: float) -> Optional[float]:
    try:
        if spot <= 0 or strike <= 0 or time_to_expiry_years <= 0 or volatility <= 0:
            return None
        d1 = (math.log(spot / strike) + (rate + 0.5 * volatility**2) * time_to_expiry_years) / (volatility * math.sqrt(time_to_expiry_years))
        d2 = d1 - volatility * math.sqrt(time_to_expiry_years)
        return spot * norm_cdf(d1) - strike * math.exp(-rate * time_to_expiry_years) * norm_cdf(d2)
    except Exception:
        return None


# ============================================================
# EXECUTION MEMORY / FILL TRACKING PLACEHOLDER
# ============================================================

def add_fill_record(state: PersistentState, record: FillRecord) -> None:
    state.fill_history.append(asdict(record))
    if len(state.fill_history) > 500:
        state.fill_history = state.fill_history[-500:]


# ============================================================
# SCORING ENGINE
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

    oil_change = ctx.oil.change_pct if ctx.oil else 0.0
    vol_change = ctx.volatility.change_pct if ctx.volatility else 0.0

    bullish_points = 0
    bearish_points = 0

    # -------------------------
    # VWAP logic
    # -------------------------
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
        if distance_pct < cfg.vwap_distance_threshold_pct:
            score += 5
            premium_reasons.append("Price is trading tight around VWAP, which improves reaction quality.")
        else:
            risk_flags.append("Price is extended away from VWAP.")
    else:
        risk_flags.append("VWAP unavailable.")

    # -------------------------
    # RSI logic
    # -------------------------
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

    # -------------------------
    # EMA logic
    # -------------------------
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

    # -------------------------
    # Price action / daily range
    # -------------------------
    if ctx.primary.previous_close > 0:
        if abs(ctx.primary.change_pct) >= cfg.price_change_threshold_pct:
            score += 8
            reasons.append(f"Price is moving with intent ({ctx.primary.change_pct:+.2f}%).")
        else:
            risk_flags.append("Move is small so far; chop risk is higher.")

    # -------------------------
    # Oil macro influence
    # -------------------------
    if ctx.oil:
        if abs(oil_change) >= cfg.oil_impact_threshold:
            premium_reasons.append(f"Oil is making a meaningful move ({ctx.oil.symbol} {oil_change:+.2f}%).")
            # User logic preference:
            # rising oil often pressures growth / index risk
            if oil_change > 0:
                bearish_points += 1
                reasons.append("Oil pressure favors caution on long-side index continuation.")
            else:
                bullish_points += 1
                reasons.append("Oil relief supports index stabilization or upside continuation.")

    # -------------------------
    # Volatility context
    # -------------------------
    if ctx.volatility:
        if vol_change > 2.0:
            bearish_points += 1
            risk_flags.append(f"{ctx.volatility.symbol} is elevated ({vol_change:+.2f}%).")
        elif vol_change < -2.0:
            bullish_points += 1
            premium_reasons.append(f"{ctx.volatility.symbol} is easing ({vol_change:+.2f}%).")

    # -------------------------
    # Key levels
    # -------------------------
    if ctx.previous_day_high and price > ctx.previous_day_high:
        score += 8
        bullish_points += 1
        reasons.append("Price is above the prior-day high zone.")
    elif ctx.previous_day_low and price < ctx.previous_day_low:
        score += 8
        bearish_points += 1
        reasons.append("Price is below the prior-day low zone.")

    # -------------------------
    # Direction decision
    # -------------------------
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

    # Clamp
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
# DAILY LEVELS ENGINE
# ============================================================

def build_daily_levels_alert(ctx: MarketContext, cfg: Config) -> AlertPayload:
    symbol = ctx.primary.symbol
    title = f"📍 {symbol} Daily Levels"
    tags = ["daily-levels", symbol.lower()]

    lines = [
        f"Symbol: {symbol}",
        f"Current Price: {ctx.primary.price:.2f}",
        f"Previous Day High: {ctx.previous_day_high:.2f}" if ctx.previous_day_high is not None else "Previous Day High: n/a",
        f"Previous Day Low: {ctx.previous_day_low:.2f}" if ctx.previous_day_low is not None else "Previous Day Low: n/a",
        f"Premarket High: {ctx.premarket_high:.2f}" if ctx.premarket_high is not None else "Premarket High: n/a",
        f"Premarket Low: {ctx.premarket_low:.2f}" if ctx.premarket_low is not None else "Premarket Low: n/a",
    ]

    if ctx.primary_indicators.vwap is not None:
        lines.append(f"VWAP: {ctx.primary_indicators.vwap:.2f}")
    if ctx.primary_indicators.rsi is not None:
        lines.append(f"RSI: {ctx.primary_indicators.rsi:.1f}")

    lines.append("")
    lines.append("Watch for acceptance / rejection at these levels before entry.")
    lines.append(cfg.risk_warning_text)

    body = "\n".join(lines)

    return AlertPayload(
        alert_type="DAILY_LEVELS",
        symbol=symbol,
        title=title,
        body=body,
        grade="INFO",
        direction="LEVELS",
        score=0,
        tags=tags,
        key=f"DAILY_LEVELS::{symbol}::{today_utc_date()}",
        timestamp_utc=now_utc_iso(),
    )


# ============================================================
# TRADE ALERT BUILDER
# ============================================================

def build_trade_alert(ctx: MarketContext, setup: SetupScore, cfg: Config) -> AlertPayload:
    symbol = ctx.primary.symbol

    emoji = "🟢" if setup.direction == "BULLISH" else "🔴" if setup.direction == "BEARISH" else "🟡"
    title = f"{emoji} {symbol} {setup.direction} Setup | Grade {setup.grade} | Score {setup.score}"

    lines: List[str] = [
        f"Symbol: {symbol}",
        f"Direction: {setup.direction}",
        f"Grade: {setup.grade}",
        f"Score: {setup.score}",
        f"Price: {ctx.primary.price:.2f}",
        f"Day Change: {ctx.primary.change_pct:+.2f}%",
    ]

    if ctx.primary_indicators.vwap is not None:
        lines.append(f"VWAP: {ctx.primary_indicators.vwap:.2f}")
    if ctx.primary_indicators.rsi is not None:
        lines.append(f"RSI: {ctx.primary_indicators.rsi:.1f}")

    if ctx.oil:
        lines.append(f"{ctx.oil.symbol}: {ctx.oil.change_pct:+.2f}%")
    if ctx.volatility:
        lines.append(f"{ctx.volatility.symbol}: {ctx.volatility.change_pct:+.2f}%")

    if setup.reasons:
        lines.append("")
        lines.append("Core reasons:")
        for reason in setup.reasons[:5]:
            lines.append(f"• {reason}")

    if setup.premium_reasons:
        lines.append("")
        lines.append("Institutional / premium context:")
        for reason in setup.premium_reasons[:4]:
            lines.append(f"• {reason}")

    if setup.risk_flags:
        lines.append("")
        lines.append("Risk flags:")
        for flag in setup.risk_flags[:4]:
            lines.append(f"• {flag}")

    lines.append("")
    lines.append(cfg.risk_warning_text)

    body = "\n".join(lines)

    rounded_price = round(ctx.primary.price, cfg.dedupe_price_rounding)
    key = f"TRADE::{symbol}::{setup.direction}::{setup.grade}::{rounded_price}"

    tags = [
        symbol.lower(),
        setup.direction.lower(),
        f"grade-{setup.grade.lower().replace('+', 'plus')}",
        "trade-alert",
    ]

    return AlertPayload(
        alert_type="TRADE_ALERT",
        symbol=symbol,
        title=title,
        body=body,
        grade=setup.grade,
        direction=setup.direction,
        score=setup.score,
        tags=tags,
        key=key,
        timestamp_utc=now_utc_iso(),
    )


# ============================================================
# NOTIFIERS
# ============================================================

class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, enabled: bool):
        self.token = token
        self.chat_id = chat_id
        self.enabled = enabled

    def send(self, text: str) -> None:
        if not self.enabled or not self.token or not self.chat_id:
            return

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
        }
        response = requests.post(url, json=payload, timeout=20)
        response.raise_for_status()


class DiscordNotifier:
    def __init__(self, enabled: bool):
        self.enabled = enabled

    def send(self, webhook_url: str, content: str) -> None:
        if not self.enabled or not webhook_url:
            return
        payload = {"content": content}
        response = requests.post(webhook_url, json=payload, timeout=20)
        response.raise_for_status()


# ============================================================
# FORMATTERS
# ============================================================

def format_for_telegram(alert: AlertPayload) -> str:
    return f"{alert.title}\n\n{alert.body}\n\nUTC: {alert.timestamp_utc}"


def format_for_discord(alert: AlertPayload) -> str:
    hashtags = " ".join(f"#{tag}" for tag in alert.tags[:6])
    return f"**{alert.title}**\n```{alert.body}```\n{hashtags}\nUTC: {alert.timestamp_utc}"


# ============================================================
# ROUTING RULES
# ============================================================

def should_send_by_cooldown(state: PersistentState, key: str, cooldown_seconds: int) -> bool:
    current_ts = time.time()
    last_ts = state.last_alert_times.get(key, 0)
    return (current_ts - last_ts) >= cooldown_seconds


def mark_sent(state: PersistentState, key: str) -> None:
    state.last_alert_times[key] = time.time()


def route_alert(
    alert: AlertPayload,
    cfg: Config,
    state: PersistentState,
    telegram: TelegramNotifier,
    discord: DiscordNotifier
) -> None:
    # DAILY LEVELS ROUTING
    if alert.alert_type == "DAILY_LEVELS":
        if not cfg.daily_levels_enabled:
            return

        if cfg.daily_levels_only_once_per_day and state.last_daily_levels_date == today_utc_date():
            return

        if not should_send_by_cooldown(state, alert.key, cfg.daily_levels_cooldown_seconds):
            return

        msg_discord = format_for_discord(alert)
        msg_telegram = format_for_telegram(alert)

        if cfg.discord_daily_levels_webhook:
            discord.send(cfg.discord_daily_levels_webhook, msg_discord)

        if cfg.telegram_enabled:
            telegram.send(msg_telegram)

        mark_sent(state, alert.key)
        state.last_daily_levels_date = today_utc_date()
        return

    # TRADE ALERT ROUTING
    if alert.alert_type == "TRADE_ALERT":
        if not should_send_by_cooldown(state, alert.key, cfg.alert_cooldown_seconds):
            return

        msg_discord = format_for_discord(alert)
        msg_telegram = format_for_telegram(alert)

        # Telegram always gets qualified trade alerts
        if cfg.telegram_enabled:
            telegram.send(msg_telegram)

        # Free Discord threshold
        if grade_rank(alert.grade) >= grade_rank(cfg.free_min_grade) and alert.score >= cfg.min_score_for_free:
            if cfg.discord_free_webhook:
                discord.send(cfg.discord_free_webhook, msg_discord)

        # Premium Discord threshold
        if grade_rank(alert.grade) >= grade_rank(cfg.premium_min_grade) and alert.score >= cfg.min_score_for_premium:
            if cfg.discord_premium_webhook:
                discord.send(cfg.discord_premium_webhook, msg_discord)
        else:
            # User preference path:
            # still allow sub-A qualified alerts to land in premium if enabled
            if cfg.send_sub_a_to_premium and cfg.discord_premium_webhook:
                discord.send(cfg.discord_premium_webhook, msg_discord)

        mark_sent(state, alert.key)
        return


# ============================================================
# DECISION ENGINE
# ============================================================

def generate_trade_alert_if_valid(ctx: MarketContext, cfg: Config) -> Optional[AlertPayload]:
    setup = score_setup(ctx, cfg)

    # Filter out neutral / weak conditions
    if setup.direction == "NEUTRAL":
        return None

    # Minimum meaningful setup
    if setup.score < min(cfg.min_score_for_free, cfg.min_score_for_premium):
        return None

    return build_trade_alert(ctx, setup, cfg)


# ============================================================
# HEARTBEAT / INFO
# ============================================================

def print_snapshot(ctx: MarketContext, cfg: Config) -> None:
    primary_vwap = f"{ctx.primary_indicators.vwap:.2f}" if ctx.primary_indicators.vwap is not None else "n/a"
    primary_rsi = f"{ctx.primary_indicators.rsi:.1f}" if ctx.primary_indicators.rsi is not None else "n/a"
    oil_info = f"{ctx.oil.symbol} {ctx.oil.change_pct:+.2f}%" if ctx.oil else "Oil n/a"
    vol_info = f"{ctx.volatility.symbol} {ctx.volatility.change_pct:+.2f}%" if ctx.volatility else "Vol n/a"

    print(
        f"[{now_utc_iso()}] "
        f"{ctx.primary.symbol} {ctx.primary.price:.2f} ({ctx.primary.change_pct:+.2f}%) | "
        f"VWAP {primary_vwap} | RSI {primary_rsi} | "
        f"{oil_info} | {vol_info}"
    )


# ============================================================
# MAIN LOOP
# ============================================================

def run_engine() -> None:
    cfg = load_config()

    if not cfg.twelve_data_api_key:
        raise RuntimeError("Missing TWELVE_DATA_API_KEY")

    state = PersistentState.load(cfg.state_file)
    client = TwelveDataClient(cfg.twelve_data_api_key, cfg)

    telegram = TelegramNotifier(
        token=cfg.telegram_bot_token,
        chat_id=cfg.telegram_chat_id,
        enabled=cfg.telegram_enabled,
    )
    discord = DiscordNotifier(enabled=cfg.discord_enabled)

    print("Elite normalized engine starting...")
    print(f"Primary symbol: {cfg.primary_symbol}")
    print(f"Secondary symbol: {cfg.secondary_symbol}")
    print(f"Oil symbol: {cfg.oil_symbol}")
    print(f"Poll seconds: {cfg.poll_seconds}")

    while True:
        try:
            ctx = build_market_context(client, cfg)
            print_snapshot(ctx, cfg)

            # 1) Daily levels alert path
            daily_levels_alert = build_daily_levels_alert(ctx, cfg)
            route_alert(daily_levels_alert, cfg, state, telegram, discord)

            # 2) Trade alert path
            trade_alert = generate_trade_alert_if_valid(ctx, cfg)
            if trade_alert:
                route_alert(trade_alert, cfg, state, telegram, discord)

            # Save lightweight market snapshot
            state.last_market_snapshot = {
                "primary_price": ctx.primary.price,
                "primary_change_pct": ctx.primary.change_pct,
                "oil_change_pct": ctx.oil.change_pct if ctx.oil else 0.0,
                "vol_change_pct": ctx.volatility.change_pct if ctx.volatility else 0.0,
                "updated_at": time.time(),
            }

            state.save(cfg.state_file)

        except KeyboardInterrupt:
            print("Shutting down cleanly...")
            state.save(cfg.state_file)
            break

        except Exception as e:
            print(f"[ERROR] {e}")
            traceback.print_exc()

        time.sleep(cfg.poll_seconds)


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":
    run_engine()

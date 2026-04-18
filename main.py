import os
import json
import math
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests


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


def today_utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


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


# ============================================================
# CONFIG
# ============================================================

@dataclass
class Config:
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
    daily_levels_only_once_per_day: bool
    risk_warning_text: str
    debug: bool


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
        daily_levels_cooldown_seconds=env_int("DAILY_LEVELS_COOLDOWN_SECONDS", 21600),

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
        daily_levels_only_once_per_day=env_bool("DAILY_LEVELS_ONLY_ONCE_PER_DAY", True),
        risk_warning_text=env_str(
            "RISK_WARNING_TEXT",
            "Educational alert only. Not financial advice. Wait for confirmation at key levels."
        ),
        debug=env_bool("DEBUG", False),
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
    last_daily_levels_date: str = ""
    last_market_snapshot: Dict[str, float] = field(default_factory=dict)

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
            )
        except Exception:
            return PersistentState()

    def save(self, path: str) -> None:
        payload = {
            "last_alert_times": self.last_alert_times,
            "last_daily_levels_date": self.last_daily_levels_date,
            "last_market_snapshot": self.last_market_snapshot,
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
            raise RuntimeError("Symbol is blank. Check your GitHub secrets.")
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

def build_daily_levels_alert(ctx: MarketContext, cfg: Config) -> AlertPayload:
    lines = [
        f"Symbol: {ctx.primary.symbol}",
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

    return AlertPayload(
        alert_type="DAILY_LEVELS",
        symbol=ctx.primary.symbol,
        title=f"📍 {ctx.primary.symbol} Daily Levels",
        body="\n".join(lines),
        grade="INFO",
        direction="LEVELS",
        score=0,
        tags=["daily-levels", ctx.primary.symbol.lower()],
        key=f"DAILY_LEVELS::{ctx.primary.symbol}::{today_utc_date()}",
        timestamp_utc=now_utc_iso(),
    )


def build_trade_alert(ctx: MarketContext, setup: SetupScore, cfg: Config) -> AlertPayload:
    emoji = "🟢" if setup.direction == "BULLISH" else "🔴"
    lines = [
        f"Symbol: {ctx.primary.symbol}",
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
        for item in setup.reasons[:5]:
            lines.append(f"• {item}")

    if setup.premium_reasons:
        lines.append("")
        lines.append("Institutional / premium context:")
        for item in setup.premium_reasons[:4]:
            lines.append(f"• {item}")

    if setup.risk_flags:
        lines.append("")
        lines.append("Risk flags:")
        for item in setup.risk_flags[:4]:
            lines.append(f"• {item}")

    lines.append("")
    lines.append(cfg.risk_warning_text)

    rounded_price = round(ctx.primary.price, cfg.dedupe_price_rounding)

    return AlertPayload(
        alert_type="TRADE_ALERT",
        symbol=ctx.primary.symbol,
        title=f"{emoji} {ctx.primary.symbol} {setup.direction} Setup | Grade {setup.grade} | Score {setup.score}",
        body="\n".join(lines),
        grade=setup.grade,
        direction=setup.direction,
        score=setup.score,
        tags=[
            ctx.primary.symbol.lower(),
            setup.direction.lower(),
            f"grade-{setup.grade.lower().replace('+', 'plus')}",
            "trade-alert",
        ],
        key=f"TRADE::{ctx.primary.symbol}::{setup.direction}::{setup.grade}::{rounded_price}",
        timestamp_utc=now_utc_iso(),
    )


def generate_trade_alert_if_valid(ctx: MarketContext, cfg: Config) -> Optional[AlertPayload]:
    setup = score_setup(ctx, cfg)
    if setup.direction == "NEUTRAL":
        return None
    if setup.score < cfg.min_score_for_free:
        return None
    return build_trade_alert(ctx, setup, cfg)


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
        response = requests.post(
            f"https://api.telegram.org/bot{self.token}/sendMessage",
            json={"chat_id": self.chat_id, "text": text},
            timeout=20,
        )
        response.raise_for_status()


class DiscordNotifier:
    def __init__(self, enabled: bool):
        self.enabled = enabled

    def send(self, webhook_url: str, content: str) -> None:
        if not self.enabled or not webhook_url:
            return
        response = requests.post(webhook_url, json={"content": content}, timeout=20)
        response.raise_for_status()


def format_for_telegram(alert: AlertPayload) -> str:
    return f"{alert.title}\n\n{alert.body}\n\nUTC: {alert.timestamp_utc}"


def format_for_discord(alert: AlertPayload) -> str:
    hashtags = " ".join(f"#{tag}" for tag in alert.tags[:6])
    return f"**{alert.title}**\n```{alert.body}```\n{hashtags}\nUTC: {alert.timestamp_utc}"


# ============================================================
# ROUTING
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
    msg_discord = format_for_discord(alert)
    msg_telegram = format_for_telegram(alert)

    if alert.alert_type == "DAILY_LEVELS":
        if not cfg.daily_levels_enabled:
            return
        if cfg.daily_levels_only_once_per_day and state.last_daily_levels_date == today_utc_date():
            return
        if not should_send_by_cooldown(state, alert.key, cfg.daily_levels_cooldown_seconds):
            return

        if cfg.discord_daily_levels_webhook:
            discord.send(cfg.discord_daily_levels_webhook, msg_discord)

        if cfg.telegram_enabled:
            telegram.send(msg_telegram)

        mark_sent(state, alert.key)
        state.last_daily_levels_date = today_utc_date()
        return

    if alert.alert_type != "TRADE_ALERT":
        return

    if not should_send_by_cooldown(state, alert.key, cfg.alert_cooldown_seconds):
        return

    # Telegram gets trade alerts too
    if cfg.telegram_enabled:
        telegram.send(msg_telegram)

    # STRICT ROUTING:
    # A / A+ = PREMIUM ONLY
    # B / C = FREE ONLY
    # D = nothing
    if (
        grade_rank(alert.grade) >= grade_rank(cfg.premium_min_grade)
        and alert.score >= cfg.min_score_for_premium
    ):
        if cfg.discord_premium_webhook:
            discord.send(cfg.discord_premium_webhook, msg_discord)

    elif (
        grade_rank(alert.grade) >= grade_rank(cfg.free_min_grade)
        and alert.score >= cfg.min_score_for_free
    ):
        if cfg.discord_free_webhook:
            discord.send(cfg.discord_free_webhook, msg_discord)

    mark_sent(state, alert.key)


# ============================================================
# ONE-RUN ENGINE
# ============================================================

def print_snapshot(ctx: MarketContext) -> None:
    print(
        f"[{now_utc_iso()}] "
        f"{ctx.primary.symbol} {ctx.primary.price:.2f} ({ctx.primary.change_pct:+.2f}%) | "
        f"VWAP {ctx.primary_indicators.vwap if ctx.primary_indicators.vwap is not None else 'n/a'} | "
        f"RSI {ctx.primary_indicators.rsi if ctx.primary_indicators.rsi is not None else 'n/a'}"
    )


def run_once() -> None:
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

    ctx = build_market_context(client, cfg)
    print_snapshot(ctx)

    daily_levels_alert = build_daily_levels_alert(ctx, cfg)
    route_alert(daily_levels_alert, cfg, state, telegram, discord)

    trade_alert = generate_trade_alert_if_valid(ctx, cfg)
    if trade_alert:
        route_alert(trade_alert, cfg, state, telegram, discord)

    state.last_market_snapshot = {
        "primary_price": ctx.primary.price,
        "primary_change_pct": ctx.primary.change_pct,
        "oil_change_pct": ctx.oil.change_pct if ctx.oil else 0.0,
        "vol_change_pct": ctx.volatility.change_pct if ctx.volatility else 0.0,
        "updated_at": time.time(),
    }
    state.save(cfg.state_file)
    print("Run complete.")


if __name__ == "__main__":
    run_once()

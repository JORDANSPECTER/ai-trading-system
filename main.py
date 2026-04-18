import os
import json
import time
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from zoneinfo import ZoneInfo

import requests
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce


ET = ZoneInfo("America/New_York")
TRACK_WINDOWS_MIN = [5, 15, 30, 60]
VALID_CONTROL_STATES = {"AUTO", "ACTIVE", "SOFT_BLOCK", "COOLDOWN", "BREACH", "PROBATION", "KILL_SWITCH"}


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


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_utc_iso() -> str:
    return now_utc().isoformat()


def now_et() -> datetime:
    return datetime.now(ET)


def today_et_str() -> str:
    return now_et().strftime("%Y-%m-%d")


def week_key_et() -> str:
    year, week_num, _ = now_et().isocalendar()
    return f"{year}-W{week_num:02d}"


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


def format_money(v: float) -> str:
    return f"${v:,.2f}"


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def minutes_since(ts: str) -> int:
    return int((now_utc() - parse_iso(ts)).total_seconds() // 60)


def is_daily_levels_window() -> bool:
    current = now_et()
    mins = current.hour * 60 + current.minute
    return 9 * 60 <= mins <= 21 * 60


def debug_log(cfg: "Config", msg: str) -> None:
    if cfg.debug:
        print(f"[DEBUG] {msg}")


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
    performance_state_file: str
    control_state_file: str
    dedupe_price_rounding: int
    alert_cooldown_seconds: int
    daily_levels_cooldown_seconds: int

    telegram_enabled: bool
    telegram_control_enabled: bool
    telegram_bot_token: str
    telegram_chat_id: str
    telegram_admin_chat_id: str

    discord_enabled: bool
    discord_free_webhook: str
    discord_premium_webhook: str
    discord_daily_levels_webhook: str
    discord_daily_performance_webhook: str
    discord_weekly_performance_webhook: str

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

    execution_enabled: bool
    execution_min_grade: str
    alpaca_api_key: str
    alpaca_secret_key: str
    alpaca_paper: bool
    allow_shorts: bool
    allow_fractional: bool
    max_position_notional: float
    max_open_positions: int
    default_time_in_force: str

    daily_reports_enabled: bool
    weekly_reports_enabled: bool
    morning_report_hour_et: int
    morning_report_minute_et: int
    evening_report_hour_et: int
    evening_report_minute_et: int
    weekly_report_hour_et: int
    weekly_report_minute_et: int

    tracking_enabled: bool
    tracking_target_pct: float
    tracking_fail_pct: float

    risk_enabled: bool
    session_filter_enabled: bool
    allow_midday_entries: bool
    market_quality_enabled: bool
    max_daily_loss: float
    max_drawdown_pct: float
    max_trades_per_day: int
    one_trade_per_symbol: bool
    cooldown_minutes_after_loss_cluster: int
    max_consecutive_losses: int
    max_order_notional: float
    max_symbol_exposure: float
    max_portfolio_exposure: float
    duplicate_signal_window_minutes: int
    vix_spike_block_pct: float
    max_vwap_distance_pct: float
    probation_size_multiplier: float

    control_notifications_enabled: bool
    control_admin_name: str


def load_config() -> Config:
    return Config(
        twelve_data_api_key=env_str("TWELVE_DATA_API_KEY"),
        primary_symbol=env_str("PRIMARY_SYMBOL", "QQQ"),
        secondary_symbol=env_str("SECONDARY_SYMBOL", "SPY"),
        oil_symbol=env_str("OIL_SYMBOL", "USO"),
        volatility_symbol=env_str("VOLATILITY_SYMBOL", "VIX"),

        state_file=env_str("STATE_FILE", "elite_state.json"),
        performance_state_file=env_str("PERFORMANCE_STATE_FILE", "performance_state.json"),
        control_state_file=env_str("CONTROL_STATE_FILE", "control_state.json"),
        dedupe_price_rounding=env_int("DEDUPE_PRICE_ROUNDING", 2),
        alert_cooldown_seconds=env_int("ALERT_COOLDOWN_SECONDS", 900),
        daily_levels_cooldown_seconds=env_int("DAILY_LEVELS_COOLDOWN_SECONDS", 1200),

        telegram_enabled=env_bool("TELEGRAM_ENABLED", True),
        telegram_control_enabled=env_bool("TELEGRAM_CONTROL_ENABLED", True),
        telegram_bot_token=env_str("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=env_str("TELEGRAM_CHAT_ID"),
        telegram_admin_chat_id=env_str("TELEGRAM_ADMIN_CHAT_ID"),

        discord_enabled=env_bool("DISCORD_ENABLED", True),
        discord_free_webhook=env_str("DISCORD_FREE_WEBHOOK"),
        discord_premium_webhook=env_str("DISCORD_PREMIUM_WEBHOOK"),
        discord_daily_levels_webhook=env_str("DISCORD_DAILY_LEVELS_WEBHOOK"),
        discord_daily_performance_webhook=env_str("DISCORD_DAILY_PERFORMANCE_WEBHOOK"),
        discord_weekly_performance_webhook=env_str("DISCORD_WEEKLY_PERFORMANCE_WEBHOOK"),

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
        allow_shorts=env_bool("ALLOW_SHORTS", False),
        allow_fractional=env_bool("ALLOW_FRACTIONAL", False),
        max_position_notional=env_float("MAX_POSITION_NOTIONAL", 500.0),
        max_open_positions=env_int("MAX_OPEN_POSITIONS", 2),
        default_time_in_force=env_str("DEFAULT_TIME_IN_FORCE", "day"),

        daily_reports_enabled=env_bool("DAILY_REPORTS_ENABLED", True),
        weekly_reports_enabled=env_bool("WEEKLY_REPORTS_ENABLED", True),
        morning_report_hour_et=env_int("MORNING_REPORT_HOUR_ET", 8),
        morning_report_minute_et=env_int("MORNING_REPORT_MINUTE_ET", 30),
        evening_report_hour_et=env_int("EVENING_REPORT_HOUR_ET", 17),
        evening_report_minute_et=env_int("EVENING_REPORT_MINUTE_ET", 30),
        weekly_report_hour_et=env_int("WEEKLY_REPORT_HOUR_ET", 9),
        weekly_report_minute_et=env_int("WEEKLY_REPORT_MINUTE_ET", 0),

        tracking_enabled=env_bool("TRACKING_ENABLED", True),
        tracking_target_pct=env_float("TRACKING_TARGET_PCT", 0.30),
        tracking_fail_pct=env_float("TRACKING_FAIL_PCT", 0.20),

        risk_enabled=env_bool("RISK_ENABLED", True),
        session_filter_enabled=env_bool("SESSION_FILTER_ENABLED", True),
        allow_midday_entries=env_bool("ALLOW_MIDDAY_ENTRIES", False),
        market_quality_enabled=env_bool("MARKET_QUALITY_ENABLED", True),
        max_daily_loss=env_float("MAX_DAILY_LOSS", 300.0),
        max_drawdown_pct=env_float("MAX_DRAWDOWN_PCT", 3.0),
        max_trades_per_day=env_int("MAX_TRADES_PER_DAY", 3),
        one_trade_per_symbol=env_bool("ONE_TRADE_PER_SYMBOL", True),
        cooldown_minutes_after_loss_cluster=env_int("COOLDOWN_MINUTES_AFTER_LOSS_CLUSTER", 45),
        max_consecutive_losses=env_int("MAX_CONSECUTIVE_LOSSES", 2),
        max_order_notional=env_float("MAX_ORDER_NOTIONAL", 500.0),
        max_symbol_exposure=env_float("MAX_SYMBOL_EXPOSURE", 1000.0),
        max_portfolio_exposure=env_float("MAX_PORTFOLIO_EXPOSURE", 2000.0),
        duplicate_signal_window_minutes=env_int("DUPLICATE_SIGNAL_WINDOW_MINUTES", 30),
        vix_spike_block_pct=env_float("VIX_SPIKE_BLOCK_PCT", 4.0),
        max_vwap_distance_pct=env_float("MAX_VWAP_DISTANCE_PCT", 0.35),
        probation_size_multiplier=env_float("PROBATION_SIZE_MULTIPLIER", 0.5),

        control_notifications_enabled=env_bool("CONTROL_NOTIFICATIONS_ENABLED", True),
        control_admin_name=env_str("CONTROL_ADMIN_NAME", "Jordan"),
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
class OrderIntent:
    signal_key: str
    symbol: str
    direction: str
    grade: str
    score: int
    reference_price: float
    requested_notional: float


@dataclass
class RiskDecision:
    action: str
    size_multiplier: float
    reason_codes: List[str]
    state_after: str


@dataclass
class PersistentState:
    last_alert_times: Dict[str, float] = field(default_factory=dict)
    last_market_snapshot: Dict[str, float] = field(default_factory=dict)
    execution_submitted_signals: Dict[str, Any] = field(default_factory=dict)
    risk_state: str = "ACTIVE"
    risk_state_until_utc: str = ""
    risk_peak_equity: float = 0.0
    risk_audit: List[Dict[str, Any]] = field(default_factory=list)

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
                execution_submitted_signals=raw.get("execution_submitted_signals", {}),
                risk_state=raw.get("risk_state", "ACTIVE"),
                risk_state_until_utc=raw.get("risk_state_until_utc", ""),
                risk_peak_equity=raw.get("risk_peak_equity", 0.0),
                risk_audit=raw.get("risk_audit", []),
            )
        except Exception:
            return PersistentState()

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "last_alert_times": self.last_alert_times,
                    "last_market_snapshot": self.last_market_snapshot,
                    "execution_submitted_signals": self.execution_submitted_signals,
                    "risk_state": self.risk_state,
                    "risk_state_until_utc": self.risk_state_until_utc,
                    "risk_peak_equity": self.risk_peak_equity,
                    "risk_audit": self.risk_audit[-1000:],
                },
                f,
                indent=2,
            )


@dataclass
class PerformanceState:
    history: List[Dict[str, Any]] = field(default_factory=list)
    pending_signals: List[Dict[str, Any]] = field(default_factory=list)
    last_daily_morning_report_date: str = ""
    last_daily_evening_report_date: str = ""
    last_weekly_report_key: str = ""

    @staticmethod
    def load(path: str) -> "PerformanceState":
        if not os.path.exists(path):
            return PerformanceState()
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            return PerformanceState(
                history=raw.get("history", []),
                pending_signals=raw.get("pending_signals", []),
                last_daily_morning_report_date=raw.get("last_daily_morning_report_date", ""),
                last_daily_evening_report_date=raw.get("last_daily_evening_report_date", ""),
                last_weekly_report_key=raw.get("last_weekly_report_key", ""),
            )
        except Exception:
            return PerformanceState()

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "history": self.history[-3000:],
                    "pending_signals": self.pending_signals[-500:],
                    "last_daily_morning_report_date": self.last_daily_morning_report_date,
                    "last_daily_evening_report_date": self.last_daily_evening_report_date,
                    "last_weekly_report_key": self.last_weekly_report_key,
                },
                f,
                indent=2,
            )


@dataclass
class ControlState:
    desired_state: str = "AUTO"
    kill_switch: bool = False
    override_minutes: int = 0
    operator: str = ""
    note: str = ""
    command_id: str = ""
    last_applied_command_id: str = ""
    last_applied_at_utc: str = ""
    telegram_update_offset: int = 0
    admin_log: List[Dict[str, Any]] = field(default_factory=list)

    @staticmethod
    def load(path: str) -> "ControlState":
        if not os.path.exists(path):
            return ControlState()
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            return ControlState(
                desired_state=raw.get("desired_state", "AUTO"),
                kill_switch=raw.get("kill_switch", False),
                override_minutes=raw.get("override_minutes", 0),
                operator=raw.get("operator", ""),
                note=raw.get("note", ""),
                command_id=raw.get("command_id", ""),
                last_applied_command_id=raw.get("last_applied_command_id", ""),
                last_applied_at_utc=raw.get("last_applied_at_utc", ""),
                telegram_update_offset=raw.get("telegram_update_offset", 0),
                admin_log=raw.get("admin_log", []),
            )
        except Exception:
            return ControlState()

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "desired_state": self.desired_state,
                    "kill_switch": self.kill_switch,
                    "override_minutes": self.override_minutes,
                    "operator": self.operator,
                    "note": self.note,
                    "command_id": self.command_id,
                    "last_applied_command_id": self.last_applied_command_id,
                    "last_applied_at_utc": self.last_applied_at_utc,
                    "telegram_update_offset": self.telegram_update_offset,
                    "admin_log": self.admin_log[-500:],
                },
                f,
                indent=2,
            )


# ============================================================
# CLIENTS
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
        data = self._get("quote", {"symbol": symbol})
        price = safe_float(data.get("close"), 0.0)
        prev = safe_float(data.get("previous_close"), 0.0)
        change_pct_val = safe_float(data.get("percent_change"), 0.0)
        if change_pct_val == 0 and prev:
            change_pct_val = pct_change(price, prev)

        return Quote(
            symbol=symbol,
            price=price,
            open_price=safe_float(data.get("open"), 0.0),
            high=safe_float(data.get("high"), 0.0),
            low=safe_float(data.get("low"), 0.0),
            previous_close=prev,
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


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, enabled: bool):
        self.token = token
        self.chat_id = chat_id
        self.enabled = enabled

    def send(self, text: str, chat_id: Optional[str] = None) -> None:
        target_chat = chat_id or self.chat_id
        if not self.enabled or not self.token or not target_chat:
            return
        requests.post(
            f"https://api.telegram.org/bot{self.token}/sendMessage",
            json={"chat_id": target_chat, "text": text},
            timeout=20,
        ).raise_for_status()

    def get_updates(self, offset: int = 0, limit: int = 20) -> List[Dict[str, Any]]:
        if not self.enabled or not self.token:
            return []
        response = requests.get(
            f"https://api.telegram.org/bot{self.token}/getUpdates",
            params={"offset": offset, "limit": limit, "timeout": 0},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            return []
        return data.get("result", [])


class DiscordNotifier:
    def __init__(self, enabled: bool):
        self.enabled = enabled

    def send(self, webhook_url: str, content: str) -> None:
        if not self.enabled or not webhook_url:
            return
        requests.post(webhook_url, json={"content": content}, timeout=20).raise_for_status()


# ============================================================
# CONTROL PLANE + TELEGRAM DEBUG
# ============================================================

def record_risk_audit(state: PersistentState, event_type: str, details: Dict[str, Any]) -> None:
    state.risk_audit.append({"ts_utc": now_utc_iso(), "event_type": event_type, "details": details})
    state.risk_audit = state.risk_audit[-1000:]


def set_risk_state(state: PersistentState, new_state: str, minutes: int = 0) -> None:
    state.risk_state = new_state
    if minutes > 0:
        until_ts = now_utc().timestamp() + minutes * 60
        state.risk_state_until_utc = datetime.fromtimestamp(until_ts, timezone.utc).isoformat()
    else:
        state.risk_state_until_utc = ""


def normalize_risk_state(state: PersistentState) -> None:
    if state.risk_state_until_utc:
        try:
            if now_utc() >= parse_iso(state.risk_state_until_utc):
                state.risk_state = "ACTIVE"
                state.risk_state_until_utc = ""
        except Exception:
            pass


def process_telegram_control_commands(cfg: Config, control: ControlState, state: PersistentState, telegram: TelegramNotifier) -> None:
    if not cfg.telegram_enabled or not cfg.telegram_control_enabled or not cfg.telegram_admin_chat_id:
        print("[TG DEBUG] Telegram control disabled or TELEGRAM_ADMIN_CHAT_ID missing.")
        return

    print(f"[TG DEBUG] Starting Telegram control check.")
    print(f"[TG DEBUG] Admin chat expected: {cfg.telegram_admin_chat_id}")
    print(f"[TG DEBUG] Current update offset: {control.telegram_update_offset}")

    try:
        updates = telegram.get_updates(offset=control.telegram_update_offset + 1)
    except Exception as e:
        print(f"[TG DEBUG] get_updates failed: {e}")
        return

    print(f"[TG DEBUG] Updates found: {len(updates)}")

    if not updates:
        return

    for upd in updates:
        update_id = upd.get("update_id", 0)
        control.telegram_update_offset = max(control.telegram_update_offset, update_id)

        print(f"[TG DEBUG] Processing update_id: {update_id}")

        msg = upd.get("message") or upd.get("edited_message")
        if not msg:
            print("[TG DEBUG] No message payload in update.")
            continue

        chat = msg.get("chat", {})
        chat_id = str(chat.get("id", ""))
        text = (msg.get("text") or "").strip()

        print(f"[TG DEBUG] Incoming chat_id: {chat_id}")
        print(f"[TG DEBUG] Incoming text: {text}")

        if not text:
            print("[TG DEBUG] Empty text, skipping.")
            continue

        if chat_id != str(cfg.telegram_admin_chat_id):
            print(f"[TG DEBUG] Unauthorized chat. Expected {cfg.telegram_admin_chat_id}, got {chat_id}")
            try:
                telegram.send("Unauthorized control attempt blocked.", chat_id=chat_id)
            except Exception as e:
                print(f"[TG DEBUG] Failed to send unauthorized reply: {e}")
            continue

        parts = text.split()
        cmd = parts[0].lower()
        args = parts[1:]

        print(f"[TG DEBUG] Command parsed: {cmd}")
        print(f"[TG DEBUG] Args parsed: {args}")

        changed = False
        reply = ""

        if cmd == "/status":
            normalize_risk_state(state)
            reply = (
                f"Control Status\n"
                f"Risk State: {state.risk_state}\n"
                f"State Until: {state.risk_state_until_utc or 'n/a'}\n"
                f"Desired State: {control.desired_state}\n"
                f"Kill Switch: {control.kill_switch}\n"
                f"Last Command ID: {control.last_applied_command_id or 'n/a'}\n"
                f"Last Applied At: {control.last_applied_at_utc or 'n/a'}\n"
                f"Note: {control.note or 'n/a'}"
            )

        elif cmd == "/active":
            control.desired_state = "ACTIVE"
            control.kill_switch = False
            control.override_minutes = 0
            control.command_id = f"tg-{update_id}"
            control.operator = cfg.control_admin_name
            control.note = "Activated from Telegram"
            changed = True
            reply = "Set to ACTIVE."

        elif cmd == "/auto":
            control.desired_state = "AUTO"
            control.kill_switch = False
            control.override_minutes = 0
            control.command_id = f"tg-{update_id}"
            control.operator = cfg.control_admin_name
            control.note = "Auto mode from Telegram"
            changed = True
            reply = "Set to AUTO."

        elif cmd == "/softblock":
            try:
                mins = int(args[0]) if args else 60
            except Exception:
                mins = 60
            control.desired_state = "SOFT_BLOCK"
            control.kill_switch = False
            control.override_minutes = mins
            control.command_id = f"tg-{update_id}"
            control.operator = cfg.control_admin_name
            control.note = f"Soft block from Telegram for {mins}m"
            changed = True
            reply = f"Set SOFT_BLOCK for {mins} minutes."

        elif cmd == "/cooldown":
            try:
                mins = int(args[0]) if args else cfg.cooldown_minutes_after_loss_cluster
            except Exception:
                mins = cfg.cooldown_minutes_after_loss_cluster
            control.desired_state = "COOLDOWN"
            control.kill_switch = False
            control.override_minutes = mins
            control.command_id = f"tg-{update_id}"
            control.operator = cfg.control_admin_name
            control.note = f"Cooldown from Telegram for {mins}m"
            changed = True
            reply = f"Set COOLDOWN for {mins} minutes."

        elif cmd == "/probation":
            try:
                mins = int(args[0]) if args else 120
            except Exception:
                mins = 120
            control.desired_state = "PROBATION"
            control.kill_switch = False
            control.override_minutes = mins
            control.command_id = f"tg-{update_id}"
            control.operator = cfg.control_admin_name
            control.note = f"Probation from Telegram for {mins}m"
            changed = True
            reply = f"Set PROBATION for {mins} minutes."

        elif cmd == "/breach":
            control.desired_state = "BREACH"
            control.kill_switch = False
            control.override_minutes = 0
            control.command_id = f"tg-{update_id}"
            control.operator = cfg.control_admin_name
            control.note = "Manual breach from Telegram"
            changed = True
            reply = "Set BREACH."

        elif cmd == "/killswitch_on":
            control.desired_state = "KILL_SWITCH"
            control.kill_switch = True
            control.override_minutes = 0
            control.command_id = f"tg-{update_id}"
            control.operator = cfg.control_admin_name
            control.note = "Kill switch ON from Telegram"
            changed = True
            reply = "Kill switch enabled."

        elif cmd == "/killswitch_off":
            control.desired_state = "ACTIVE"
            control.kill_switch = False
            control.override_minutes = 0
            control.command_id = f"tg-{update_id}"
            control.operator = cfg.control_admin_name
            control.note = "Kill switch OFF from Telegram"
            changed = True
            reply = "Kill switch disabled. Set ACTIVE."

        elif cmd == "/resume":
            control.desired_state = "ACTIVE"
            control.kill_switch = False
            control.override_minutes = 0
            control.command_id = f"tg-{update_id}"
            control.operator = cfg.control_admin_name
            control.note = "Resume from Telegram"
            changed = True
            reply = "Resumed ACTIVE state."

        elif cmd == "/note":
            note_text = " ".join(args).strip()
            if note_text:
                control.note = note_text
                control.command_id = f"tg-{update_id}"
                control.operator = cfg.control_admin_name
                changed = True
                reply = f"Updated note: {note_text}"
            else:
                reply = "Usage: /note your message"

        else:
            reply = (
                "Commands:\n"
                "/status\n"
                "/active\n"
                "/auto\n"
                "/softblock 60\n"
                "/cooldown 45\n"
                "/probation 120\n"
                "/breach\n"
                "/killswitch_on\n"
                "/killswitch_off\n"
                "/resume\n"
                "/note text"
            )

        print(f"[TG DEBUG] Command changed state: {changed}")
        print(f"[TG DEBUG] Reply prepared: {reply}")

        if changed:
            record_risk_audit(
                state,
                "TELEGRAM_CONTROL_COMMAND",
                {
                    "chat_id": chat_id,
                    "command": text,
                    "command_id": control.command_id,
                    "operator": control.operator,
                },
            )
            print(f"[TG DEBUG] Recorded control command with command_id: {control.command_id}")

        try:
            telegram.send(reply, chat_id=chat_id)
            print("[TG DEBUG] Reply sent successfully.")
        except Exception as e:
            print(f"[TG DEBUG] Failed to send reply: {e}")

    print(f"[TG DEBUG] Final update offset: {control.telegram_update_offset}")


def apply_control_plane(
    cfg: Config,
    control: ControlState,
    state: PersistentState,
    discord: DiscordNotifier,
    telegram: TelegramNotifier,
) -> None:
    if control.desired_state not in VALID_CONTROL_STATES:
        control.desired_state = "AUTO"

    if control.command_id and control.command_id != control.last_applied_command_id:
        previous_state = state.risk_state

        if control.kill_switch or control.desired_state == "KILL_SWITCH":
            set_risk_state(state, "KILL_SWITCH")
        elif control.desired_state == "AUTO":
            normalize_risk_state(state)
        elif control.desired_state == "ACTIVE":
            set_risk_state(state, "ACTIVE")
        elif control.desired_state == "SOFT_BLOCK":
            set_risk_state(state, "SOFT_BLOCK", control.override_minutes)
        elif control.desired_state == "COOLDOWN":
            set_risk_state(state, "COOLDOWN", control.override_minutes if control.override_minutes > 0 else cfg.cooldown_minutes_after_loss_cluster)
        elif control.desired_state == "BREACH":
            set_risk_state(state, "BREACH")
        elif control.desired_state == "PROBATION":
            set_risk_state(state, "PROBATION", control.override_minutes)

        control.last_applied_command_id = control.command_id
        control.last_applied_at_utc = now_utc_iso()

        log_entry = {
            "ts_utc": now_utc_iso(),
            "operator": control.operator or cfg.control_admin_name,
            "from_state": previous_state,
            "to_state": state.risk_state,
            "desired_state": control.desired_state,
            "kill_switch": control.kill_switch,
            "override_minutes": control.override_minutes,
            "note": control.note,
            "command_id": control.command_id,
        }
        control.admin_log.append(log_entry)
        record_risk_audit(state, "MANUAL_OVERRIDE_APPLIED", log_entry)

        if cfg.control_notifications_enabled:
            msg = (
                f"🛠 CONTROL PLANE UPDATE\n"
                f"Operator: {log_entry['operator']}\n"
                f"From: {log_entry['from_state']}\n"
                f"To: {log_entry['to_state']}\n"
                f"Desired: {log_entry['desired_state']}\n"
                f"Kill Switch: {log_entry['kill_switch']}\n"
                f"Duration (min): {log_entry['override_minutes']}\n"
                f"Note: {log_entry['note'] or 'n/a'}\n"
                f"Command ID: {log_entry['command_id']}"
            )
            if cfg.discord_premium_webhook:
                discord.send(cfg.discord_premium_webhook, msg)
            if cfg.telegram_enabled:
                telegram.send(msg, chat_id=cfg.telegram_admin_chat_id or cfg.telegram_chat_id)


# ============================================================
# RISK / EXECUTION / TRACKING / REPORTS
# ============================================================

def current_session_label() -> str:
    current = now_et()
    mins = current.hour * 60 + current.minute
    if 9 * 60 + 30 <= mins < 10 * 60 + 30:
        return "OPEN"
    if 10 * 60 + 30 <= mins < 14 * 60:
        return "MIDDAY"
    if 14 * 60 <= mins <= 16 * 60:
        return "POWER_HOUR"
    return "OFF_HOURS"


class ExposureService:
    def __init__(self, executor: "ExecutionEngine"):
        self.executor = executor

    def get_positions(self) -> List[Any]:
        return safe_get_positions(self.executor)

    def portfolio_exposure(self) -> float:
        total = 0.0
        for pos in self.get_positions():
            try:
                total += abs(float(getattr(pos, "market_value", 0.0)))
            except Exception:
                pass
        return total

    def symbol_exposure(self, symbol: str) -> float:
        total = 0.0
        for pos in self.get_positions():
            try:
                if str(pos.symbol).upper() == symbol.upper():
                    total += abs(float(getattr(pos, "market_value", 0.0)))
            except Exception:
                pass
        return total

    def has_symbol_position(self, symbol: str) -> bool:
        for pos in self.get_positions():
            try:
                if str(pos.symbol).upper() == symbol.upper():
                    return True
            except Exception:
                pass
        return False

    def open_position_count(self) -> int:
        return len(self.get_positions())


def trades_today_count(perf: PerformanceState) -> int:
    today = today_et_str()
    return sum(1 for x in perf.history if x.get("type") == "execution" and x.get("date_et") == today)


def consecutive_losses_today(perf: PerformanceState) -> int:
    today = today_et_str()
    outcomes = [x for x in perf.history if x.get("type") == "tracked_outcome" and x.get("date_et") == today]
    outcomes.sort(key=lambda x: x.get("ts_utc", ""))
    count = 0
    for item in reversed(outcomes):
        if item.get("final_status") == "LOSS":
            count += 1
        elif item.get("final_status") == "WIN":
            break
    return count


def realized_signal_pnl_estimate_today(perf: PerformanceState, cfg: Config) -> float:
    today = today_et_str()
    tracked = [x for x in perf.history if x.get("type") == "tracked_outcome" and x.get("date_et") == today]
    pnl = 0.0
    for item in tracked:
        status = item.get("final_status")
        if status == "WIN":
            pnl += cfg.max_order_notional * (cfg.tracking_target_pct / 100.0)
        elif status == "LOSS":
            pnl -= cfg.max_order_notional * (cfg.tracking_fail_pct / 100.0)
    return pnl


class PreTradeRiskEngine:
    def __init__(self, cfg: Config, state: PersistentState, perf: PerformanceState, executor: "ExecutionEngine", exposure: ExposureService):
        self.cfg = cfg
        self.state = state
        self.perf = perf
        self.executor = executor
        self.exposure = exposure

    def _sync_peak_equity(self) -> None:
        equity = safe_get_account_equity(self.executor)
        if equity > 0 and equity > self.state.risk_peak_equity:
            self.state.risk_peak_equity = equity

    def _check_state(self, reasons: List[str]) -> Optional[RiskDecision]:
        normalize_risk_state(self.state)
        if self.state.risk_state == "KILL_SWITCH":
            reasons.append("KILL_SWITCH_ACTIVE")
            return RiskDecision("KILL_SWITCH_ACTIVE", 0.0, reasons, self.state.risk_state)
        if self.state.risk_state == "BREACH":
            reasons.append("RISK_BREACH_ACTIVE")
            return RiskDecision("BLOCK_HARD", 0.0, reasons, self.state.risk_state)
        if self.state.risk_state == "SOFT_BLOCK":
            reasons.append("SOFT_BLOCK_ACTIVE")
            return RiskDecision("BLOCK_TEMP", 0.0, reasons, self.state.risk_state)
        if self.state.risk_state == "COOLDOWN":
            reasons.append("COOLDOWN_ACTIVE")
            return RiskDecision("BLOCK_TEMP", 0.0, reasons, self.state.risk_state)
        if self.state.risk_state == "PROBATION":
            reasons.append("PROBATION_ACTIVE")
            return None
        return None

    def _check_daily_loss_and_drawdown(self, reasons: List[str]) -> Optional[RiskDecision]:
        self._sync_peak_equity()
        pseudo_realized = realized_signal_pnl_estimate_today(self.perf, self.cfg)
        if abs(min(pseudo_realized, 0.0)) >= self.cfg.max_daily_loss:
            set_risk_state(self.state, "BREACH")
            reasons.append("MAX_DAILY_LOSS_BREACH")
            return RiskDecision("BLOCK_HARD", 0.0, reasons, self.state.risk_state)

        equity = safe_get_account_equity(self.executor)
        if equity > 0 and self.state.risk_peak_equity > 0:
            dd_pct = ((self.state.risk_peak_equity - equity) / self.state.risk_peak_equity) * 100.0
            if dd_pct >= self.cfg.max_drawdown_pct:
                set_risk_state(self.state, "BREACH")
                reasons.append("MAX_DRAWDOWN_BREACH")
                return RiskDecision("BLOCK_HARD", 0.0, reasons, self.state.risk_state)

        reasons.extend(["DAILY_LOSS_OK", "DRAWDOWN_OK"])
        return None

    def _check_strategy_health(self, reasons: List[str]) -> Optional[RiskDecision]:
        if consecutive_losses_today(self.perf) >= self.cfg.max_consecutive_losses:
            set_risk_state(self.state, "COOLDOWN", self.cfg.cooldown_minutes_after_loss_cluster)
            reasons.append("LOSS_CLUSTER_COOLDOWN")
            return RiskDecision("BLOCK_TEMP", 0.0, reasons, self.state.risk_state)
        reasons.append("LOSS_CLUSTER_OK")
        return None

    def _check_trade_count(self, reasons: List[str]) -> Optional[RiskDecision]:
        if trades_today_count(self.perf) >= self.cfg.max_trades_per_day:
            set_risk_state(self.state, "SOFT_BLOCK", 60)
            reasons.append("MAX_TRADES_PER_DAY_REACHED")
            return RiskDecision("BLOCK_TEMP", 0.0, reasons, self.state.risk_state)
        reasons.append("TRADE_COUNT_OK")
        return None

    def _check_duplicate(self, intent: OrderIntent, reasons: List[str]) -> Optional[RiskDecision]:
        for entry in self.perf.history:
            if entry.get("signal_key") != intent.signal_key and entry.get("symbol") == intent.symbol and entry.get("type") == "execution":
                ts = entry.get("ts_utc")
                if ts and minutes_since(ts) <= self.cfg.duplicate_signal_window_minutes:
                    reasons.append("DUPLICATE_SIGNAL_WINDOW")
                    return RiskDecision("BLOCK_TEMP", 0.0, reasons, self.state.risk_state)

        if intent.signal_key in self.state.execution_submitted_signals:
            reasons.append("DUPLICATE_SIGNAL_KEY")
            return RiskDecision("BLOCK_HARD", 0.0, reasons, self.state.risk_state)

        reasons.append("DUPLICATE_OK")
        return None

    def _check_exposure(self, intent: OrderIntent, reasons: List[str]) -> Optional[RiskDecision]:
        if intent.requested_notional > self.cfg.max_order_notional:
            reasons.append("MAX_ORDER_NOTIONAL_BREACH")
            return RiskDecision("BLOCK_HARD", 0.0, reasons, self.state.risk_state)

        portfolio_exposure = self.exposure.portfolio_exposure()
        symbol_exposure = self.exposure.symbol_exposure(intent.symbol)

        if self.cfg.one_trade_per_symbol and self.exposure.has_symbol_position(intent.symbol):
            reasons.append("ONE_TRADE_PER_SYMBOL_BLOCK")
            return RiskDecision("BLOCK_TEMP", 0.0, reasons, self.state.risk_state)

        if self.exposure.open_position_count() >= self.cfg.max_open_positions:
            reasons.append("MAX_OPEN_POSITIONS_BLOCK")
            return RiskDecision("BLOCK_TEMP", 0.0, reasons, self.state.risk_state)

        if symbol_exposure + intent.requested_notional > self.cfg.max_symbol_exposure:
            reasons.append("MAX_SYMBOL_EXPOSURE_BREACH")
            return RiskDecision("BLOCK_HARD", 0.0, reasons, self.state.risk_state)

        if portfolio_exposure + intent.requested_notional > self.cfg.max_portfolio_exposure:
            if portfolio_exposure < self.cfg.max_portfolio_exposure:
                remaining = self.cfg.max_portfolio_exposure - portfolio_exposure
                if remaining > 0:
                    mult = max(0.1, min(1.0, remaining / max(intent.requested_notional, 0.01)))
                    reasons.append("PORTFOLIO_EXPOSURE_HAIRCUT")
                    return RiskDecision("ALLOW_REDUCED", mult, reasons, self.state.risk_state)
            reasons.append("MAX_PORTFOLIO_EXPOSURE_BREACH")
            return RiskDecision("BLOCK_HARD", 0.0, reasons, self.state.risk_state)

        reasons.append("EXPOSURE_OK")
        return None

    def _check_session_and_market_quality(self, ctx: MarketContext, reasons: List[str]) -> Optional[RiskDecision]:
        if self.cfg.session_filter_enabled:
            session = current_session_label()
            if session == "OFF_HOURS":
                reasons.append("SESSION_OFF_HOURS_BLOCK")
                return RiskDecision("BLOCK_TEMP", 0.0, reasons, self.state.risk_state)
            if session == "MIDDAY" and not self.cfg.allow_midday_entries:
                reasons.append("SESSION_MIDDAY_BLOCK")
                return RiskDecision("BLOCK_TEMP", 0.0, reasons, self.state.risk_state)
            reasons.append(f"SESSION_{session}_OK")

        if self.cfg.market_quality_enabled:
            if ctx.volatility and ctx.volatility.change_pct >= self.cfg.vix_spike_block_pct:
                reasons.append("VOLATILITY_SPIKE_BLOCK")
                return RiskDecision("BLOCK_TEMP", 0.0, reasons, self.state.risk_state)

            if ctx.primary_indicators.vwap is not None:
                dist = abs(pct_change(ctx.primary.price, ctx.primary_indicators.vwap))
                if dist > self.cfg.max_vwap_distance_pct:
                    reasons.append("PRICE_COLLAR_VWAP_DISTANCE_BLOCK")
                    return RiskDecision("BLOCK_TEMP", 0.0, reasons, self.state.risk_state)

            reasons.append("MARKET_QUALITY_OK")
        return None

    def evaluate(self, intent: OrderIntent, ctx: MarketContext) -> RiskDecision:
        reasons: List[str] = []

        if not self.cfg.risk_enabled:
            reasons.append("RISK_ENGINE_DISABLED")
            return RiskDecision("ALLOW", 1.0, reasons, self.state.risk_state)

        for check in [
            self._check_state,
            self._check_daily_loss_and_drawdown,
            self._check_strategy_health,
            self._check_trade_count,
            lambda r: self._check_duplicate(intent, r),
            lambda r: self._check_exposure(intent, r),
            lambda r: self._check_session_and_market_quality(ctx, r),
        ]:
            decision = check(reasons)
            if decision:
                return decision

        if self.state.risk_state == "PROBATION":
            reasons.append("PROBATION_SIZE_REDUCTION")
            return RiskDecision("ALLOW_REDUCED", self.cfg.probation_size_multiplier, reasons, self.state.risk_state)

        reasons.append("PRETRADE_RISK_OK")
        return RiskDecision("ALLOW", 1.0, reasons, self.state.risk_state)


class ExecutionEngine:
    def __init__(self, cfg: Config, state: PersistentState):
        self.cfg = cfg
        self.state = state
        self.client = None
        if cfg.alpaca_api_key and cfg.alpaca_secret_key:
            self.client = TradingClient(
                api_key=cfg.alpaca_api_key,
                secret_key=cfg.alpaca_secret_key,
                paper=cfg.alpaca_paper,
            )

    def _eligible(self, alert: AlertPayload) -> Tuple[bool, str]:
        if not self.cfg.execution_enabled:
            return False, "Execution disabled"
        if self.client is None:
            return False, "Missing Alpaca credentials"
        if alert.alert_type != "TRADE_ALERT":
            return False, "Not a trade alert"
        if grade_rank(alert.grade) < grade_rank(self.cfg.execution_min_grade):
            return False, f"Grade below execution threshold ({self.cfg.execution_min_grade})"
        return True, "OK"

    def qty_from_price(self, price: float, notional: float) -> float:
        if price <= 0:
            return 0.0
        raw_qty = notional / price
        if self.cfg.allow_fractional:
            return round(raw_qty, 4)
        return max(1, math.floor(raw_qty))

    def execute(self, alert: AlertPayload, ctx: MarketContext, notional: float) -> Dict[str, Any]:
        ok, reason = self._eligible(alert)
        if not ok:
            return {"executed": False, "reason": reason}

        if alert.direction == "BEARISH" and not self.cfg.allow_shorts:
            return {"executed": False, "reason": "Bearish execution blocked because ALLOW_SHORTS=false"}

        qty = self.qty_from_price(ctx.primary.price, notional)
        if qty <= 0:
            return {"executed": False, "reason": "Calculated qty <= 0"}

        side = OrderSide.BUY if alert.direction == "BULLISH" else OrderSide.SELL
        tif = TimeInForce.DAY if self.cfg.default_time_in_force.lower() == "day" else TimeInForce.GTC
        client_order_id = alert.key[:48]

        order_request = MarketOrderRequest(
            symbol=alert.symbol,
            qty=qty,
            side=side,
            time_in_force=tif,
            client_order_id=client_order_id,
        )

        try:
            order = self.client.submit_order(order_data=order_request)
            self.state.execution_submitted_signals[alert.key] = {
                "symbol": alert.symbol,
                "grade": alert.grade,
                "direction": alert.direction,
                "qty": qty,
                "notional": notional,
                "price_snapshot": ctx.primary.price,
                "client_order_id": client_order_id,
                "submitted_at": now_utc_iso(),
                "alpaca_order_id": str(order.id),
                "alpaca_status": str(order.status),
            }
            return {
                "executed": True,
                "symbol": alert.symbol,
                "qty": qty,
                "side": side.value,
                "notional": notional,
                "client_order_id": client_order_id,
                "alpaca_order_id": str(order.id),
                "alpaca_status": str(order.status),
            }
        except Exception as e:
            return {"executed": False, "reason": f"Execution failed: {e}"}


def safe_get_account_equity(executor: ExecutionEngine) -> float:
    try:
        if executor.client is None:
            return 0.0
        return float(executor.client.get_account().equity)
    except Exception:
        return 0.0


def safe_get_account_last_equity(executor: ExecutionEngine) -> float:
    try:
        if executor.client is None:
            return 0.0
        return float(executor.client.get_account().last_equity)
    except Exception:
        return 0.0


def safe_get_positions(executor: ExecutionEngine) -> List[Any]:
    try:
        if executor.client is None:
            return []
        return executor.client.get_all_positions()
    except Exception:
        return []


def summarize_period(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    signals = [x for x in history if x.get("type") == "signal"]
    executions = [x for x in history if x.get("type") == "execution"]
    tracked = [x for x in history if x.get("type") == "tracked_outcome"]

    grade_counts: Dict[str, int] = {}
    symbol_counts: Dict[str, int] = {}
    grade_outcomes: Dict[str, Dict[str, int]] = {}
    symbol_outcomes: Dict[str, Dict[str, int]] = {}

    for item in signals:
        grade_counts[item["grade"]] = grade_counts.get(item["grade"], 0) + 1
        symbol_counts[item["symbol"]] = symbol_counts.get(item["symbol"], 0) + 1

    for item in tracked:
        grade = item["grade"]
        symbol = item["symbol"]
        status = item["final_status"]
        grade_outcomes.setdefault(grade, {"WIN": 0, "LOSS": 0, "NEUTRAL": 0})
        symbol_outcomes.setdefault(symbol, {"WIN": 0, "LOSS": 0, "NEUTRAL": 0})
        grade_outcomes[grade][status] = grade_outcomes[grade].get(status, 0) + 1
        symbol_outcomes[symbol][status] = symbol_outcomes[symbol].get(status, 0) + 1

    wins = sum(1 for x in tracked if x.get("final_status") == "WIN")
    losses = sum(1 for x in tracked if x.get("final_status") == "LOSS")
    neutrals = sum(1 for x in tracked if x.get("final_status") == "NEUTRAL")
    decided = wins + losses
    win_rate = round((wins / decided) * 100.0, 2) if decided else 0.0

    return {
        "signals": len(signals),
        "executions": len(executions),
        "tracked": len(tracked),
        "wins": wins,
        "losses": losses,
        "neutrals": neutrals,
        "win_rate": win_rate,
        "grade_counts": grade_counts,
        "symbol_counts": symbol_counts,
        "grade_outcomes": grade_outcomes,
        "symbol_outcomes": symbol_outcomes,
        "top_symbol": max(symbol_counts, key=symbol_counts.get) if symbol_counts else "n/a",
        "avg_score": round(sum(x.get("score", 0) for x in signals) / len(signals), 2) if signals else 0.0,
    }


def best_rate_bucket(outcomes: Dict[str, Dict[str, int]]) -> str:
    best_name = "n/a"
    best_rate = -1.0
    for name, bucket in outcomes.items():
        wins = bucket.get("WIN", 0)
        losses = bucket.get("LOSS", 0)
        decided = wins + losses
        if decided == 0:
            continue
        rate = (wins / decided) * 100.0
        if rate > best_rate:
            best_rate = rate
            best_name = f"{name} ({rate:.1f}%)"
    return best_name


def build_daily_report_text(cfg: Config, perf: PerformanceState, executor: ExecutionEngine, state: PersistentState, mode: str) -> str:
    date_key = today_et_str()
    summary = summarize_period([x for x in perf.history if x.get("date_et") == date_key])

    equity = safe_get_account_equity(executor)
    last_equity = safe_get_account_last_equity(executor)
    equity_change = equity - last_equity if equity and last_equity else 0.0
    positions = safe_get_positions(executor)

    return "\n".join(
        [
            f"📊 {'Morning' if mode == 'morning' else 'Evening'} Daily Performance Report",
            f"Date (ET): {date_key}",
            "",
            f"Signals Today: {summary['signals']}",
            f"Executions Today: {summary['executions']}",
            f"Tracked Outcomes: {summary['tracked']}",
            f"Win / Loss / Neutral: {summary['wins']} / {summary['losses']} / {summary['neutrals']}",
            f"Win Rate: {summary['win_rate']:.2f}%",
            f"Avg Signal Score: {summary['avg_score']}",
            f"Most Active Symbol: {summary['top_symbol']}",
            f"Best Grade: {best_rate_bucket(summary['grade_outcomes'])}",
            f"Best Symbol: {best_rate_bucket(summary['symbol_outcomes'])}",
            "",
            f"Risk State: {state.risk_state}",
            f"Peak Equity: {format_money(state.risk_peak_equity)}" if state.risk_peak_equity else "Peak Equity: n/a",
            f"Account Equity: {format_money(equity)}" if equity else "Account Equity: n/a",
            f"Equity Change vs Last Equity: {format_money(equity_change)}" if equity and last_equity else "Equity Change vs Last Equity: n/a",
            f"Open Positions: {len(positions)}",
        ]
    )


def build_weekly_report_text(cfg: Config, perf: PerformanceState, executor: ExecutionEngine, state: PersistentState) -> str:
    wk = week_key_et()
    summary = summarize_period([x for x in perf.history if x.get("week_key") == wk])
    equity = safe_get_account_equity(executor)

    return "\n".join(
        [
            "📈 Weekly Performance Report",
            f"Week: {wk}",
            "",
            f"Signals: {summary['signals']}",
            f"Executions: {summary['executions']}",
            f"Tracked Outcomes: {summary['tracked']}",
            f"Win / Loss / Neutral: {summary['wins']} / {summary['losses']} / {summary['neutrals']}",
            f"Weekly Win Rate: {summary['win_rate']:.2f}%",
            f"Best Grade: {best_rate_bucket(summary['grade_outcomes'])}",
            f"Best Symbol: {best_rate_bucket(summary['symbol_outcomes'])}",
            "",
            f"Risk State: {state.risk_state}",
            f"Current Equity: {format_money(equity)}" if equity else "Current Equity: n/a",
        ]
    )


def maybe_send_reports(cfg: Config, perf: PerformanceState, executor: ExecutionEngine, state: PersistentState, discord: DiscordNotifier) -> None:
    current = now_et()
    date_key = current.strftime("%Y-%m-%d")
    wk = week_key_et()

    if cfg.daily_reports_enabled:
        if current.hour == cfg.morning_report_hour_et and current.minute < 20 and perf.last_daily_morning_report_date != date_key:
            if cfg.discord_daily_performance_webhook:
                discord.send(cfg.discord_daily_performance_webhook, build_daily_report_text(cfg, perf, executor, state, "morning"))
            perf.last_daily_morning_report_date = date_key

        if current.hour == cfg.evening_report_hour_et and current.minute < 20 and perf.last_daily_evening_report_date != date_key:
            if cfg.discord_daily_performance_webhook:
                discord.send(cfg.discord_daily_performance_webhook, build_daily_report_text(cfg, perf, executor, state, "evening"))
            perf.last_daily_evening_report_date = date_key

    if cfg.weekly_reports_enabled:
        if current.weekday() == 6 and current.hour == cfg.weekly_report_hour_et and current.minute < 20 and perf.last_weekly_report_key != wk:
            if cfg.discord_weekly_performance_webhook:
                discord.send(cfg.discord_weekly_performance_webhook, build_weekly_report_text(cfg, perf, executor, state))
            perf.last_weekly_report_key = wk


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
        debug_log(cfg, f"vol quote failed: {e}")

    return MarketContext(
        primary=primary,
        secondary=secondary,
        oil=oil,
        volatility=volatility,
        primary_indicators=client.get_indicator_pack(cfg.primary_symbol),
        secondary_indicators=client.get_indicator_pack(cfg.secondary_symbol),
        previous_day_high=primary.high,
        previous_day_low=primary.low,
        premarket_high=primary.high,
        premarket_low=primary.low,
    )


def should_send_by_cooldown(state: PersistentState, key: str, cooldown_seconds: int) -> bool:
    current_ts = time.time()
    last_ts = state.last_alert_times.get(key, 0)
    return (current_ts - last_ts) >= cooldown_seconds


def mark_sent(state: PersistentState, key: str) -> None:
    state.last_alert_times[key] = time.time()


def format_for_telegram(alert: AlertPayload) -> str:
    return f"{alert.title}\n\n{alert.body}\n\nUTC: {alert.timestamp_utc}"


def format_for_discord(alert: AlertPayload) -> str:
    hashtags = " ".join(f"#{tag}" for tag in alert.tags[:6])
    return f"**{alert.title}**\n```{alert.body}```\n{hashtags}\nUTC: {alert.timestamp_utc}"


def route_alert(alert: AlertPayload, cfg: Config, state: PersistentState, telegram: TelegramNotifier, discord: DiscordNotifier) -> None:
    msg_discord = format_for_discord(alert)
    msg_telegram = format_for_telegram(alert)

    if alert.alert_type == "DAILY_LEVELS":
        if not cfg.daily_levels_enabled or not is_daily_levels_window():
            return
        if not should_send_by_cooldown(state, alert.key, cfg.daily_levels_cooldown_seconds):
            return
        if cfg.discord_daily_levels_webhook:
            discord.send(cfg.discord_daily_levels_webhook, msg_discord)
        if cfg.telegram_enabled:
            telegram.send(msg_telegram)
        mark_sent(state, alert.key)
        return

    if alert.alert_type != "TRADE_ALERT":
        return

    if not should_send_by_cooldown(state, alert.key, cfg.alert_cooldown_seconds):
        return

    if cfg.telegram_enabled:
        telegram.send(msg_telegram)

    if grade_rank(alert.grade) >= grade_rank(cfg.premium_min_grade) and alert.score >= cfg.min_score_for_premium:
        if cfg.discord_premium_webhook:
            discord.send(cfg.discord_premium_webhook, msg_discord)
    elif grade_rank(alert.grade) >= grade_rank(cfg.free_min_grade) and alert.score >= cfg.min_score_for_free:
        if cfg.discord_free_webhook:
            discord.send(cfg.discord_free_webhook, msg_discord)

    mark_sent(state, alert.key)


def append_risk_to_alert(alert: AlertPayload, decision: RiskDecision, control: ControlState, state: PersistentState) -> AlertPayload:
    extra = [
        "",
        "Risk Decision:",
        f"• Action: {decision.action}",
        f"• State: {decision.state_after}",
        f"• Size Multiplier: {decision.size_multiplier:.2f}",
        f"• Control Desired State: {control.desired_state}",
        f"• Kill Switch: {control.kill_switch}",
        "• Reason Codes:",
    ]
    for code in decision.reason_codes[:8]:
        extra.append(f"  - {code}")
    alert.body = alert.body + "\n" + "\n".join(extra)
    return alert


def evaluate_pending_signals(client: TwelveDataClient, perf: PerformanceState, cfg: Config) -> None:
    if not cfg.tracking_enabled:
        return

    still_pending: List[Dict[str, Any]] = []
    cache: Dict[str, float] = {}

    for pending in perf.pending_signals:
        symbol = pending["symbol"]
        try:
            if symbol not in cache:
                cache[symbol] = client.get_quote(symbol).price
            current_price = cache[symbol]
            age_min = minutes_since(pending["created_at_utc"])
            entry_price = float(pending["entry_price"])
            move_pct = pct_change(current_price, entry_price)

            for window in TRACK_WINDOWS_MIN:
                key = str(window)
                if age_min >= window and key not in pending["checkpoints"]:
                    status = compute_signal_status(
                        pending["direction"],
                        move_pct,
                        float(pending["target_pct"]),
                        float(pending["fail_pct"]),
                    )
                    pending["checkpoints"][key] = {
                        "minutes": window,
                        "price": current_price,
                        "move_pct": round(move_pct, 4),
                        "status": status,
                        "evaluated_at_utc": now_utc_iso(),
                    }

            if age_min >= 60:
                final_cp = pending["checkpoints"].get("60")
                if final_cp:
                    pending["final_status"] = final_cp["status"]

            if age_min >= 60 and pending["final_status"] != "PENDING":
                perf.history.append(
                    {
                        "ts_utc": now_utc_iso(),
                        "date_et": pending["date_et"],
                        "week_key": pending["week_key"],
                        "type": "tracked_outcome",
                        "signal_key": pending["signal_key"],
                        "symbol": pending["symbol"],
                        "grade": pending["grade"],
                        "direction": pending["direction"],
                        "score": pending["score"],
                        "entry_price": pending["entry_price"],
                        "final_status": pending["final_status"],
                        "checkpoints": pending["checkpoints"],
                    }
                )
            elif age_min >= 120:
                pending["final_status"] = "NEUTRAL"
                perf.history.append(
                    {
                        "ts_utc": now_utc_iso(),
                        "date_et": pending["date_et"],
                        "week_key": pending["week_key"],
                        "type": "tracked_outcome",
                        "signal_key": pending["signal_key"],
                        "symbol": pending["symbol"],
                        "grade": pending["grade"],
                        "direction": pending["direction"],
                        "score": pending["score"],
                        "entry_price": pending["entry_price"],
                        "final_status": pending["final_status"],
                        "checkpoints": pending["checkpoints"],
                    }
                )
            else:
                still_pending.append(pending)

        except Exception as e:
            debug_log(cfg, f"tracking quote failed for {symbol}: {e}")
            still_pending.append(pending)

    perf.pending_signals = still_pending


def run_once() -> None:
    cfg = load_config()
    if not cfg.twelve_data_api_key:
        raise RuntimeError("Missing TWELVE_DATA_API_KEY")

    state = PersistentState.load(cfg.state_file)
    perf = PerformanceState.load(cfg.performance_state_file)
    control = ControlState.load(cfg.control_state_file)
    client = TwelveDataClient(cfg.twelve_data_api_key, cfg)

    telegram = TelegramNotifier(cfg.telegram_bot_token, cfg.telegram_chat_id, cfg.telegram_enabled)
    discord = DiscordNotifier(cfg.discord_enabled)
    executor = ExecutionEngine(cfg, state)

    process_telegram_control_commands(cfg, control, state, telegram)
    apply_control_plane(cfg, control, state, discord, telegram)
    evaluate_pending_signals(client, perf, cfg)

    ctx = build_market_context(client, cfg)

    daily_levels_alert = build_daily_levels_alert(ctx, cfg)
    route_alert(daily_levels_alert, cfg, state, telegram, discord)

    trade_alert = generate_trade_alert_if_valid(ctx, cfg)
    if trade_alert:
        record_signal(perf, trade_alert, ctx, cfg)

        intent = OrderIntent(
            signal_key=trade_alert.key,
            symbol=trade_alert.symbol,
            direction=trade_alert.direction,
            grade=trade_alert.grade,
            score=trade_alert.score,
            reference_price=ctx.primary.price,
            requested_notional=min(cfg.max_position_notional, cfg.max_order_notional),
        )

        exposure = ExposureService(executor)
        risk_engine = PreTradeRiskEngine(cfg, state, perf, executor, exposure)
        risk_decision = risk_engine.evaluate(intent, ctx)
        record_risk_audit(state, "RISK_DECISION", {"intent": asdict(intent), "decision": asdict(risk_decision)})

        trade_alert = append_risk_to_alert(trade_alert, risk_decision, control, state)
        route_alert(trade_alert, cfg, state, telegram, discord)

        if risk_decision.action in {"ALLOW", "ALLOW_REDUCED"}:
            exec_notional = intent.requested_notional * risk_decision.size_multiplier
            exec_result = executor.execute(trade_alert, ctx, exec_notional)

            if exec_result.get("executed"):
                record_execution(perf, trade_alert, ctx, exec_result)
                exec_msg = (
                    f"🚀 EXECUTED {trade_alert.symbol}\n"
                    f"Direction: {trade_alert.direction}\n"
                    f"Grade: {trade_alert.grade}\n"
                    f"Qty: {exec_result['qty']}\n"
                    f"Notional: {format_money(exec_result['notional'])}\n"
                    f"Risk Action: {risk_decision.action}\n"
                    f"Risk State: {state.risk_state}\n"
                    f"Order ID: {exec_result['alpaca_order_id']}\n"
                    f"Status: {exec_result['alpaca_status']}"
                )
                if cfg.discord_premium_webhook:
                    discord.send(cfg.discord_premium_webhook, exec_msg)
                if cfg.telegram_enabled:
                    telegram.send(exec_msg)
            else:
                record_risk_audit(state, "EXECUTION_SKIPPED", exec_result)
        else:
            block_msg = (
                f"🛑 RISK BLOCKED {trade_alert.symbol}\n"
                f"Action: {risk_decision.action}\n"
                f"State: {risk_decision.state_after}\n"
                f"Control Desired State: {control.desired_state}\n"
                f"Reasons: {', '.join(risk_decision.reason_codes[:6])}"
            )
            if cfg.discord_premium_webhook:
                discord.send(cfg.discord_premium_webhook, block_msg)
            if cfg.telegram_enabled:
                telegram.send(block_msg)

    maybe_send_reports(cfg, perf, executor, state, discord)

    state.last_market_snapshot = {
        "primary_price": ctx.primary.price,
        "primary_change_pct": ctx.primary.change_pct,
        "oil_change_pct": ctx.oil.change_pct if ctx.oil else 0.0,
        "vol_change_pct": ctx.volatility.change_pct if ctx.volatility else 0.0,
        "updated_at": time.time(),
    }

    state.save(cfg.state_file)
    perf.save(cfg.performance_state_file)
    control.save(cfg.control_state_file)


if __name__ == "__main__":
    try:
        run_once()
    except Exception:
        import traceback
        print("\n===== FULL PYTHON ERROR =====")
        traceback.print_exc()
        print("===== END PYTHON ERROR =====\n")
        raise

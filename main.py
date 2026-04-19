import os
import time
import math
import json
import uuid
import traceback
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple

import requests

# =========================
# OPTIONAL ALPACA IMPORTS
# =========================
ALPACA_AVAILABLE = True
try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
except Exception:
    ALPACA_AVAILABLE = False


# ============================================================
# CONFIG
# ============================================================
APP_NAME = os.getenv("APP_NAME", "UB-ENGINE")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")

MODE = os.getenv("MODE", "paper").lower()              # paper | live | alerts_only
LOOP_SECONDS = int(os.getenv("LOOP_SECONDS", "60"))
ENABLE_EXECUTION = os.getenv("ENABLE_EXECUTION", "false").lower() == "true"
ENABLE_TELEGRAM_COMMANDS = os.getenv("ENABLE_TELEGRAM_COMMANDS", "true").lower() == "true"

PRIMARY_SYMBOL = os.getenv("PRIMARY_SYMBOL", "QQQ").upper()
SECONDARY_SYMBOL = os.getenv("SECONDARY_SYMBOL", "SPY").upper()
OIL_SYMBOL = os.getenv("OIL_SYMBOL", "USO").upper()    # you can swap later if desired

MIN_GRADE_TO_ALERT = os.getenv("MIN_GRADE_TO_ALERT", "C").upper()       # A/B/C
MIN_GRADE_TO_EXECUTE = os.getenv("MIN_GRADE_TO_EXECUTE", "A").upper()   # A/B/C

DEFAULT_ORDER_QTY = float(os.getenv("DEFAULT_ORDER_QTY", "1"))
MAX_POSITION_QTY = float(os.getenv("MAX_POSITION_QTY", "2"))
ALLOW_SHORT = os.getenv("ALLOW_SHORT", "false").lower() == "true"
KILL_SWITCH_DEFAULT = os.getenv("KILL_SWITCH_DEFAULT", "false").lower() == "true"

# Risk management
MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "500"))
MAX_TRADES_PER_DAY = int(os.getenv("MAX_TRADES_PER_DAY", "5"))
COOLDOWN_AFTER_TRADE_SEC = int(os.getenv("COOLDOWN_AFTER_TRADE_SEC", "180"))

# Price source
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
PRICE_SOURCE = os.getenv("PRICE_SOURCE", "twelvedata").lower()  # twelvedata | manual

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_ALLOWED_USER_ID = os.getenv("TELEGRAM_ALLOWED_USER_ID", "")  # optional safety lock

# Discord
DISCORD_FREE_WEBHOOK = os.getenv("DISCORD_FREE_WEBHOOK", "")
DISCORD_PREMIUM_WEBHOOK = os.getenv("DISCORD_PREMIUM_WEBHOOK", "")
DISCORD_DEBUG_WEBHOOK = os.getenv("DISCORD_DEBUG_WEBHOOK", "")

# Alpaca
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_PAPER = os.getenv("ALPACA_PAPER", "true").lower() == "true"

# Optional custom channels
ALERTS_CHANNEL_NAME = os.getenv("ALERTS_CHANNEL_NAME", "daily-levels")
PREMIUM_CHANNEL_NAME = os.getenv("PREMIUM_CHANNEL_NAME", "premium-daily-levels")

# State persistence
STATE_FILE = os.getenv("STATE_FILE", "ub_engine_state.json")

# Manual levels (comma-separated, optional)
MANUAL_LEVELS_QQQ = os.getenv("MANUAL_LEVELS_QQQ", "")
MANUAL_LEVELS_SPY = os.getenv("MANUAL_LEVELS_SPY", "")

# ============================================================
# HELPERS
# ============================================================
GRADE_RANK = {"C": 1, "B": 2, "A": 3}
SIGNAL_DIRECTIONS = {"CALL", "PUT", "NONE"}


def now_ts() -> int:
    return int(time.time())


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def parse_levels(raw: str) -> List[float]:
    if not raw.strip():
        return []
    out = []
    for piece in raw.split(","):
        piece = piece.strip()
        if piece:
            out.append(safe_float(piece))
    return out


def clamp(n: float, low: float, high: float) -> float:
    return max(low, min(high, n))


def fmt_price(x: Optional[float]) -> str:
    if x is None:
        return "N/A"
    return f"{x:.2f}"


def grade_meets_threshold(grade: str, threshold: str) -> bool:
    return GRADE_RANK.get(grade, 0) >= GRADE_RANK.get(threshold, 0)


def direction_to_order_side(direction: str):
    if direction == "CALL":
        return "buy"
    if direction == "PUT":
        return "sell"
    return None


# ============================================================
# DATA MODELS
# ============================================================
@dataclass
class MarketSnapshot:
    symbol: str
    price: Optional[float] = None
    open_price: Optional[float] = None
    prev_close: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    volume: Optional[float] = None
    vwap: Optional[float] = None
    timestamp: int = field(default_factory=now_ts)


@dataclass
class EngineContext:
    mode: str
    primary_symbol: str
    secondary_symbol: str
    oil_symbol: str
    primary: MarketSnapshot
    secondary: MarketSnapshot
    oil: MarketSnapshot
    manual_levels: Dict[str, List[float]]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TradePlan:
    symbol: str
    direction: str = "NONE"  # CALL | PUT | NONE
    grade: str = "C"
    entry_bias: str = "WAIT"
    confidence: float = 0.0
    reasons: List[str] = field(default_factory=list)
    execution_ok: bool = False
    qty: float = 0.0
    price: Optional[float] = None
    stop_hint: Optional[float] = None
    take_profit_hint: Optional[float] = None
    alert_text: str = ""
    premium_text: str = ""
    raw_scores: Dict[str, float] = field(default_factory=dict)
    debug: Dict[str, Any] = field(default_factory=dict)


# ============================================================
# STATE STORE
# ============================================================
class EngineState:
    def __init__(self, state_file: str):
        self.state_file = state_file
        self.state = {
            "kill_switch": KILL_SWITCH_DEFAULT,
            "execution_enabled": ENABLE_EXECUTION,
            "last_trade_ts": 0,
            "trades_today": 0,
            "daily_realized_pnl": 0.0,
            "last_telegram_update_id": 0,
            "last_alert_fingerprint": "",
            "mode_override": None,
        }
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.state_file):
            return
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self.state.update(loaded)
        except Exception:
            pass

    def save(self) -> None:
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2)
        except Exception:
            pass

    def get(self, key: str, default=None):
        return self.state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.state[key] = value
        self.save()


# ============================================================
# NOTIFIERS
# ============================================================
class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send(self, text: str) -> bool:
        if not self.enabled:
            return False
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            resp = requests.post(
                url,
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "Markdown"
                },
                timeout=15,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def get_updates(self, offset: Optional[int] = None) -> Dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "result": []}
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
            params = {"timeout": 1}
            if offset is not None:
                params["offset"] = offset
            resp = requests.get(url, params=params, timeout=20)
            return resp.json()
        except Exception:
            return {"ok": False, "result": []}


class DiscordNotifier:
    def __init__(self, free_webhook: str, premium_webhook: str, debug_webhook: str):
        self.free_webhook = free_webhook
        self.premium_webhook = premium_webhook
        self.debug_webhook = debug_webhook

    @staticmethod
    def _post_webhook(webhook_url: str, content: str) -> bool:
        if not webhook_url:
            return False
        try:
            resp = requests.post(
                webhook_url,
                json={"content": content},
                timeout=15,
            )
            return resp.status_code in (200, 204)
        except Exception:
            return False

    def send_free(self, content: str) -> bool:
        return self._post_webhook(self.free_webhook, content)

    def send_premium(self, content: str) -> bool:
        return self._post_webhook(self.premium_webhook, content)

    def send_debug(self, content: str) -> bool:
        return self._post_webhook(self.debug_webhook, content)


# ============================================================
# BROKER
# ============================================================
class AlpacaExecutionBroker:
    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        self.api_key = api_key
        self.secret_key = secret_key
        self.paper = paper
        self.client = None

        if ALPACA_AVAILABLE and api_key and secret_key:
            self.client = TradingClient(api_key, secret_key, paper=paper)

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def submit_market_order(self, symbol: str, qty: float, side: str) -> Tuple[bool, str]:
        if not self.enabled:
            return False, "Alpaca client not configured"

        try:
            if side == "buy":
                order_side = OrderSide.BUY
            elif side == "sell":
                order_side = OrderSide.SELL
            else:
                return False, f"Unsupported side: {side}"

            order = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                time_in_force=TimeInForce.DAY,
                client_order_id=f"ub-{uuid.uuid4().hex[:18]}"
            )
            submitted = self.client.submit_order(order_data=order)
            order_id = getattr(submitted, "id", "unknown")
            return True, f"Order submitted: {symbol} {side} {qty} | order_id={order_id}"
        except Exception as e:
            return False, f"Alpaca order failed: {e}"

    def close_all_positions(self) -> Tuple[bool, str]:
        if not self.enabled:
            return False, "Alpaca client not configured"
        try:
            result = self.client.close_all_positions(cancel_orders=True)
            return True, f"Flatten requested: {result}"
        except Exception as e:
            return False, f"Flatten failed: {e}"


# ============================================================
# MARKET DATA
# ============================================================
class MarketDataProvider:
    def __init__(self, source: str, twelve_data_api_key: str = ""):
        self.source = source
        self.twelve_data_api_key = twelve_data_api_key

    def get_snapshot(self, symbol: str) -> MarketSnapshot:
        if self.source == "twelvedata" and self.twelve_data_api_key:
            return self._get_twelvedata_snapshot(symbol)
        return MarketSnapshot(symbol=symbol)

    def _get_twelvedata_snapshot(self, symbol: str) -> MarketSnapshot:
        """
        Pull quote + eod-style fields from Twelve Data endpoints.
        """
        try:
            # Quote endpoint
            quote_resp = requests.get(
                "https://api.twelvedata.com/quote",
                params={"symbol": symbol, "apikey": self.twelve_data_api_key},
                timeout=15,
            )
            quote = quote_resp.json()

            price = safe_float(quote.get("close"))
            open_price = safe_float(quote.get("open"))
            prev_close = safe_float(quote.get("previous_close"))
            high = safe_float(quote.get("high"))
            low = safe_float(quote.get("low"))
            volume = safe_float(quote.get("volume"))

            # Lightweight synthetic vwap fallback
            vwap = None
            if high and low and price:
                vwap = (high + low + price) / 3.0

            return MarketSnapshot(
                symbol=symbol,
                price=price if price else None,
                open_price=open_price if open_price else None,
                prev_close=prev_close if prev_close else None,
                high=high if high else None,
                low=low if low else None,
                volume=volume if volume else None,
                vwap=vwap,
            )
        except Exception:
            return MarketSnapshot(symbol=symbol)


# ============================================================
# STRATEGY / SCORING
# ============================================================
def level_proximity_score(price: Optional[float], levels: List[float]) -> Tuple[float, Optional[float]]:
    """
    Higher score when price is close to an important level.
    """
    if price is None or not levels:
        return 0.0, None

    closest = min(levels, key=lambda x: abs(x - price))
    dist_pct = abs(closest - price) / max(price, 0.01)

    if dist_pct <= 0.001:
        score = 1.0
    elif dist_pct <= 0.0025:
        score = 0.8
    elif dist_pct <= 0.005:
        score = 0.55
    else:
        score = 0.2

    return score, closest


def price_vs_vwap_score(price: Optional[float], vwap: Optional[float]) -> Tuple[float, str]:
    if price is None or vwap is None:
        return 0.0, "VWAP unavailable"
    if price > vwap:
        return 1.0, "Above VWAP"
    if price < vwap:
        return -1.0, "Below VWAP"
    return 0.0, "At VWAP"


def oil_pressure_score(oil: MarketSnapshot) -> Tuple[float, str]:
    """
    Positive value = oil relief / better for bullish indices
    Negative value = oil pressure / better for bearish indices
    """
    if oil.price is None or oil.prev_close is None:
        return 0.0, "Oil data unavailable"

    delta = oil.price - oil.prev_close

    if delta <= -2:
        return 1.0, f"Oil relief strong ({delta:+.2f})"
    if -2 < delta <= -0.5:
        return 0.5, f"Oil easing ({delta:+.2f})"
    if -0.5 < delta < 0.5:
        return 0.1, f"Oil stable ({delta:+.2f})"
    if 0.5 <= delta < 2:
        return -0.5, f"Oil pressure rising ({delta:+.2f})"
    return -1.0, f"Oil pressure strong ({delta:+.2f})"


def compute_grade(confidence: float) -> str:
    if confidence >= 0.78:
        return "A"
    if confidence >= 0.58:
        return "B"
    return "C"


def choose_direction(vwap_score: float, oil_score: float, near_level_bias: float) -> str:
    """
    Simple directional blend:
    - bullish if above vwap, oil supportive, near key level
    - bearish if below vwap, oil pressuring, near key level
    """
    bullish = 0.45 * max(vwap_score, 0) + 0.35 * max(oil_score, 0) + 0.20 * near_level_bias
    bearish = 0.45 * max(-vwap_score, 0) + 0.35 * max(-oil_score, 0) + 0.20 * near_level_bias

    if bullish > bearish and bullish >= 0.45:
        return "CALL"
    if bearish > bullish and bearish >= 0.45:
        return "PUT"
    return "NONE"


def build_trade_plan(ctx: EngineContext) -> TradePlan:
    symbol = ctx.primary_symbol
    primary = ctx.primary
    oil = ctx.oil
    levels = ctx.manual_levels.get(symbol, [])

    plan = TradePlan(symbol=symbol, price=primary.price)

    level_score, nearest_level = level_proximity_score(primary.price, levels)
    vwap_score, vwap_note = price_vs_vwap_score(primary.price, primary.vwap)
    oil_score, oil_note = oil_pressure_score(oil)

    direction = choose_direction(vwap_score, oil_score, level_score)

    reasons = [vwap_note, oil_note]
    if nearest_level is not None:
        reasons.append(f"Near key level {nearest_level:.2f}")
    else:
        reasons.append("No manual key levels loaded")

    confidence = (
        0.50 * abs(vwap_score) +
        0.30 * abs(oil_score) +
        0.20 * level_score
    )
    confidence = clamp(confidence, 0.0, 1.0)

    grade = compute_grade(confidence)
    entry_bias = "WAIT"
    execution_ok = False

    if direction != "NONE":
        if grade == "A":
            entry_bias = "ACTIONABLE"
            execution_ok = True
        elif grade == "B":
            entry_bias = "WATCH / RETEST"
            execution_ok = False
        else:
            entry_bias = "LOW QUALITY"
            execution_ok = False

    qty = min(DEFAULT_ORDER_QTY, MAX_POSITION_QTY) if execution_ok else 0.0

    # Hint levels
    stop_hint = None
    take_profit_hint = None
    if primary.price is not None:
        if direction == "CALL":
            stop_hint = primary.price * 0.995
            take_profit_hint = primary.price * 1.01
        elif direction == "PUT":
            stop_hint = primary.price * 1.005
            take_profit_hint = primary.price * 0.99

    plan.direction = direction
    plan.grade = grade
    plan.entry_bias = entry_bias
    plan.confidence = confidence
    plan.reasons = reasons
    plan.execution_ok = execution_ok
    plan.qty = qty
    plan.stop_hint = stop_hint
    plan.take_profit_hint = take_profit_hint
    plan.raw_scores = {
        "level_score": round(level_score, 4),
        "vwap_score": round(vwap_score, 4),
        "oil_score": round(oil_score, 4),
    }
    plan.debug = {
        "nearest_level": nearest_level,
        "primary_price": primary.price,
        "primary_vwap": primary.vwap,
        "oil_price": oil.price,
        "oil_prev_close": oil.prev_close,
    }

    plan.alert_text = render_free_alert(plan, ctx)
    plan.premium_text = render_premium_alert(plan, ctx)
    return plan


# ============================================================
# RENDERERS
# ============================================================
def render_free_alert(plan: TradePlan, ctx: EngineContext) -> str:
    return (
        f"📡 *{APP_NAME}* | {ctx.primary_symbol}\n"
        f"Mode: `{ctx.mode}`\n"
        f"Signal: *{plan.direction}* | Grade: *{plan.grade}*\n"
        f"Price: `{fmt_price(plan.price)}` | Bias: `{plan.entry_bias}`\n"
        f"Why: " + " | ".join(plan.reasons[:3])
    )


def render_premium_alert(plan: TradePlan, ctx: EngineContext) -> str:
    return (
        f"💎 *{APP_NAME} PREMIUM* | {ctx.primary_symbol}\n"
        f"Signal: *{plan.direction}* | Grade: *{plan.grade}* | Confidence: `{plan.confidence:.2f}`\n"
        f"Price: `{fmt_price(plan.price)}`\n"
        f"Stop Hint: `{fmt_price(plan.stop_hint)}` | TP Hint: `{fmt_price(plan.take_profit_hint)}`\n"
        f"Scores: `{json.dumps(plan.raw_scores)}`\n"
        f"Why: " + " | ".join(plan.reasons)
    )


def render_status(state: EngineState, plan: Optional[TradePlan] = None) -> str:
    lines = [
        f"🧠 *{APP_NAME} STATUS*",
        f"Version: `{APP_VERSION}`",
        f"Mode: `{state.get('mode_override') or MODE}`",
        f"Kill Switch: `{state.get('kill_switch')}`",
        f"Execution Enabled: `{state.get('execution_enabled')}`",
        f"Trades Today: `{state.get('trades_today')}`",
        f"Daily PnL: `{state.get('daily_realized_pnl')}`",
    ]
    if plan:
        lines.extend([
            f"Last Signal: `{plan.direction}`",
            f"Last Grade: `{plan.grade}`",
            f"Last Bias: `{plan.entry_bias}`",
            f"Last Price: `{fmt_price(plan.price)}`"
        ])
    return "\n".join(lines)


# ============================================================
# COMMAND CENTER
# ============================================================
def parse_command(text: str) -> Tuple[str, List[str]]:
    raw = (text or "").strip()
    if not raw:
        return "", []
    parts = raw.split()
    cmd = parts[0].lower()
    args = parts[1:]
    return cmd, args


def handle_telegram_commands(
    tg: TelegramNotifier,
    state: EngineState,
    broker: AlpacaExecutionBroker,
    last_plan: Optional[TradePlan] = None
) -> None:
    if not (ENABLE_TELEGRAM_COMMANDS and tg.enabled):
        return

    offset = state.get("last_telegram_update_id", 0) + 1
    updates = tg.get_updates(offset=offset)
    if not updates.get("ok"):
        return

    for item in updates.get("result", []):
        update_id = item.get("update_id", 0)
        message = item.get("message", {}) or item.get("edited_message", {}) or {}
        text = message.get("text", "")
        from_user = message.get("from", {}) or {}
        from_user_id = str(from_user.get("id", ""))

        state.set("last_telegram_update_id", update_id)

        if TELEGRAM_ALLOWED_USER_ID and from_user_id != TELEGRAM_ALLOWED_USER_ID:
            continue

        cmd, args = parse_command(text)

        if cmd in ("/start", "start"):
            tg.send(
                "✅ UB Command Center Online\n\n"
                "Commands:\n"
                "/status\n"
                "/kill\n"
                "/resume\n"
                "/flatten\n"
                "/mode paper\n"
                "/mode live\n"
                "/exec on\n"
                "/exec off\n"
                "/test\n"
            )

        elif cmd == "/status":
            tg.send(render_status(state, last_plan))

        elif cmd == "/kill":
            state.set("kill_switch", True)
            tg.send("🛑 Kill switch ENABLED")

        elif cmd == "/resume":
            state.set("kill_switch", False)
            tg.send("✅ Kill switch DISABLED")

        elif cmd == "/flatten":
            ok, msg = broker.close_all_positions()
            tg.send(("✅ " if ok else "❌ ") + msg)

        elif cmd == "/mode":
            if not args:
                tg.send("Use: /mode paper OR /mode live")
                continue
            new_mode = args[0].lower()
            if new_mode not in ("paper", "live", "alerts_only"):
                tg.send("Invalid mode. Use paper, live, or alerts_only")
                continue
            state.set("mode_override", new_mode)
            tg.send(f"⚙️ Mode override set to `{new_mode}`")

        elif cmd == "/exec":
            if not args:
                tg.send("Use: /exec on OR /exec off")
                continue
            new_state = args[0].lower()
            if new_state == "on":
                state.set("execution_enabled", True)
                tg.send("✅ Execution enabled")
            elif new_state == "off":
                state.set("execution_enabled", False)
                tg.send("🛑 Execution disabled")
            else:
                tg.send("Use: /exec on OR /exec off")

        elif cmd == "/test":
            tg.send("🚨 TEST ALERT WORKING")

        elif cmd == "/help":
            tg.send("Use /start or /status")

        # ignore unknown commands


# ============================================================
# EXECUTION FILTERS
# ============================================================
def execution_filter(state: EngineState, plan: TradePlan) -> Tuple[bool, List[str]]:
    notes = []

    if state.get("kill_switch"):
        notes.append("Kill switch enabled")
        return False, notes

    if not state.get("execution_enabled"):
        notes.append("Execution disabled")
        return False, notes

    if plan.direction == "NONE":
        notes.append("No trade direction")
        return False, notes

    if not grade_meets_threshold(plan.grade, MIN_GRADE_TO_EXECUTE):
        notes.append(f"Grade below execute threshold ({MIN_GRADE_TO_EXECUTE})")
        return False, notes

    if plan.qty <= 0:
        notes.append("Qty is zero")
        return False, notes

    last_trade_ts = state.get("last_trade_ts", 0)
    if now_ts() - last_trade_ts < COOLDOWN_AFTER_TRADE_SEC:
        notes.append("Trade cooldown active")
        return False, notes

    trades_today = state.get("trades_today", 0)
    if trades_today >= MAX_TRADES_PER_DAY:
        notes.append("Max trades reached")
        return False, notes

    daily_pnl = safe_float(state.get("daily_realized_pnl", 0.0))
    if daily_pnl <= -abs(MAX_DAILY_LOSS):
        notes.append("Max daily loss exceeded")
        return False, notes

    if plan.direction == "PUT" and not ALLOW_SHORT:
        notes.append("PUT execution blocked (ALLOW_SHORT=false)")
        return False, notes

    notes.append("Execution approved")
    return True, notes


# ============================================================
# ALERT DEDUPE
# ============================================================
def make_alert_fingerprint(plan: TradePlan) -> str:
    return f"{plan.symbol}|{plan.direction}|{plan.grade}|{round(plan.price or 0, 2)}"


def should_send_alert(state: EngineState, plan: TradePlan) -> bool:
    if not grade_meets_threshold(plan.grade, MIN_GRADE_TO_ALERT):
        return False
    fp = make_alert_fingerprint(plan)
    return fp != state.get("last_alert_fingerprint", "")


# ============================================================
# ENGINE
# ============================================================
class UBEngine:
    def __init__(self):
        self.state = EngineState(STATE_FILE)
        self.tg = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        self.discord = DiscordNotifier(
            DISCORD_FREE_WEBHOOK,
            DISCORD_PREMIUM_WEBHOOK,
            DISCORD_DEBUG_WEBHOOK,
        )
        self.broker = AlpacaExecutionBroker(
            ALPACA_API_KEY,
            ALPACA_SECRET_KEY,
            paper=ALPACA_PAPER,
        )
        self.market = MarketDataProvider(
            source=PRICE_SOURCE,
            twelve_data_api_key=TWELVE_DATA_API_KEY,
        )
        self.last_plan: Optional[TradePlan] = None

    def resolve_mode(self) -> str:
        return self.state.get("mode_override") or MODE

    def gather_context(self) -> EngineContext:
        primary = self.market.get_snapshot(PRIMARY_SYMBOL)
        secondary = self.market.get_snapshot(SECONDARY_SYMBOL)
        oil = self.market.get_snapshot(OIL_SYMBOL)

        levels = {
            PRIMARY_SYMBOL: parse_levels(MANUAL_LEVELS_QQQ) if PRIMARY_SYMBOL == "QQQ" else parse_levels(MANUAL_LEVELS_SPY),
            SECONDARY_SYMBOL: parse_levels(MANUAL_LEVELS_SPY) if SECONDARY_SYMBOL == "SPY" else parse_levels(MANUAL_LEVELS_QQQ),
        }

        return EngineContext(
            mode=self.resolve_mode(),
            primary_symbol=PRIMARY_SYMBOL,
            secondary_symbol=SECONDARY_SYMBOL,
            oil_symbol=OIL_SYMBOL,
            primary=primary,
            secondary=secondary,
            oil=oil,
            manual_levels=levels,
        )

    def send_alerts(self, plan: TradePlan, ctx: EngineContext) -> None:
        if not should_send_alert(self.state, plan):
            return

        # Free channel gets all qualifying alerts
        self.discord.send_free(plan.alert_text)
        self.tg.send(plan.alert_text)

        # Premium gets detailed text
        self.discord.send_premium(plan.premium_text)

        self.state.set("last_alert_fingerprint", make_alert_fingerprint(plan))

    def maybe_execute(self, plan: TradePlan, ctx: EngineContext) -> None:
        mode = ctx.mode
        if mode == "alerts_only":
            return

        allowed, notes = execution_filter(self.state, plan)
        if not allowed:
            self.discord.send_debug(f"⚠️ Execution blocked | {plan.symbol} | {' | '.join(notes)}")
            return

        if mode not in ("paper", "live"):
            self.discord.send_debug(f"⚠️ Unknown mode: {mode}")
            return

        side = direction_to_order_side(plan.direction)
        if side is None:
            self.discord.send_debug("⚠️ No side resolved for trade")
            return

        ok, msg = self.broker.submit_market_order(plan.symbol, plan.qty, side)
        if ok:
            self.state.set("last_trade_ts", now_ts())
            self.state.set("trades_today", self.state.get("trades_today", 0) + 1)
            self.tg.send(f"✅ {msg}")
            self.discord.send_premium(f"✅ EXECUTED | {msg}")
        else:
            self.tg.send(f"❌ {msg}")
            self.discord.send_debug(f"❌ {msg}")

    def run_once(self) -> None:
        ctx = self.gather_context()
        plan = build_trade_plan(ctx)
        self.last_plan = plan

        self.handle_visibility(plan)
        self.send_alerts(plan, ctx)
        self.maybe_execute(plan, ctx)

    def handle_visibility(self, plan: TradePlan) -> None:
        # extra debug breadcrumbs
        dbg = (
            f"🧪 DEBUG | {plan.symbol} | Direction={plan.direction} | Grade={plan.grade} "
            f"| Price={fmt_price(plan.price)} | Scores={plan.raw_scores}"
        )
        self.discord.send_debug(dbg)

    def loop(self) -> None:
        startup = (
            f"🚀 {APP_NAME} online\n"
            f"Version: {APP_VERSION}\n"
            f"Mode: {self.resolve_mode()}\n"
            f"Execution Enabled: {self.state.get('execution_enabled')}\n"
            f"Kill Switch: {self.state.get('kill_switch')}\n"
            f"Alpaca Ready: {self.broker.enabled}\n"
            f"Telegram Ready: {self.tg.enabled}\n"
        )
        self.tg.send(startup)
        self.discord.send_debug(startup)

        while True:
            try:
                handle_telegram_commands(
                    tg=self.tg,
                    state=self.state,
                    broker=self.broker,
                    last_plan=self.last_plan,
                )
                self.run_once()
            except Exception as e:
                err = (
                    f"❌ ENGINE ERROR\n"
                    f"{e}\n\n"
                    f"```{traceback.format_exc()[:1500]}```"
                )
                self.tg.send(err)
                self.discord.send_debug(err)
            time.sleep(LOOP_SECONDS)


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    engine = UBEngine()
    engine.loop()

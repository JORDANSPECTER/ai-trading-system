import os
import time
import math
import json
import requests
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple
from datetime import datetime


# =========================================================
# CONFIG
# =========================================================

SYMBOLS = [s.strip().upper() for s in os.getenv("SYMBOLS", "SPY,QQQ").split(",") if s.strip()]
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "20"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
DISCORD_PREMIUM_WEBHOOK_URL = os.getenv("DISCORD_PREMIUM_WEBHOOK_URL", "")

TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")

STATE_FILE = os.getenv("STATE_FILE", "system_state.json")
ENABLE_HEARTBEAT = os.getenv("ENABLE_HEARTBEAT", "true").lower() == "true"
HEARTBEAT_MINUTES = int(os.getenv("HEARTBEAT_MINUTES", "30"))


# =========================================================
# DATA MODELS
# =========================================================

@dataclass
class MarketBar:
    symbol: str
    price: float
    open_price: float = 0.0
    high: float = 0.0
    low: float = 0.0
    volume: float = 0.0
    prev_close: float = 0.0
    timestamp: str = ""


@dataclass
class OpenPosition:
    symbol: str
    direction: str              # "LONG", "SHORT", "CALL", "PUT"
    market_value: float
    risk_value: float
    cluster: str
    beta_weighted_delta: float = 0.0


@dataclass
class MarketStressState:
    vix: float = 0.0
    vix_prev_close: float = 0.0
    spy_move_pct: float = 0.0
    qqq_move_pct: float = 0.0
    gap_move_pct: float = 0.0

    breadth_breaking_down: bool = False
    liquidity_thin: bool = False
    slippage_spike: bool = False
    abnormal_spread: bool = False
    trading_halt_detected: bool = False
    data_stale: bool = False
    execution_disconnect: bool = False
    rejected_orders_spiking: bool = False
    regime_break_detected: bool = False


@dataclass
class RiskSnapshot:
    equity: float
    cash: float
    daily_pnl: float
    weekly_pnl: float
    unrealized_pnl: float
    realized_pnl: float
    open_positions: List[OpenPosition] = field(default_factory=list)


@dataclass
class BlackSwanConfig:
    daily_loss_limit_pct: float = 2.5
    weekly_loss_limit_pct: float = 5.0

    max_gross_exposure_pct: float = 60.0
    max_net_exposure_pct: float = 35.0
    max_symbol_exposure_pct: float = 20.0
    max_cluster_exposure_pct: float = 30.0

    vix_reduce_risk: float = 22.0
    vix_hard_stop: float = 32.0
    gap_move_hard_stop_pct: float = 2.0
    intraday_index_shock_pct: float = 1.75

    abnormal_size_multiplier: float = 0.50
    severe_size_multiplier: float = 0.25

    max_rejected_orders_before_lock: int = 2
    allow_new_trades_after_lock: bool = False


@dataclass
class BlackSwanDecision:
    status: str                 # "ALLOW", "REDUCE_SIZE", "BLOCK_NEW", "FORCE_EXIT_ALL", "FLAT_AND_LOCK"
    size_multiplier: float
    reasons: List[str]
    alert: str
    lock_trading: bool = False


@dataclass
class SystemLockState:
    trading_locked: bool = False
    lock_reason: str = ""
    locked_at: str = ""


@dataclass
class TradePlan:
    symbol: str
    action: str                 # "ENTER_CALL", "ENTER_PUT", "HOLD", "EXIT_ALL"
    grade: str
    confidence: float
    size: int
    entry_price: float
    trigger_level: Optional[float]
    stop_level: Optional[float]
    target_level: Optional[float]
    reasons: List[str] = field(default_factory=list)
    alerts: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


@dataclass
class EngineState:
    lock_state: SystemLockState = field(default_factory=SystemLockState)
    rejected_order_count: int = 0
    last_heartbeat_ts: float = 0.0
    last_alert_hash: str = ""
    last_prices: Dict[str, float] = field(default_factory=dict)


# =========================================================
# UTILITIES
# =========================================================

def now_iso() -> str:
    return datetime.utcnow().isoformat()


def safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def pct_change(current: float, reference: float) -> float:
    if reference == 0:
        return 0.0
    return ((current - reference) / reference) * 100.0


def pct_of_equity(value: float, equity: float) -> float:
    if equity <= 0:
        return 0.0
    return (value / equity) * 100.0


def infer_cluster(symbol: str) -> str:
    s = symbol.upper()
    if s in ["SPY", "QQQ", "SPX", "NDX", "AAPL", "MSFT", "NVDA", "META", "AMZN", "GOOGL", "TSLA"]:
        return "INDEX_TECH"
    if s in ["XOM", "CVX", "USO"]:
        return "ENERGY"
    if s in ["JPM", "BAC", "GS"]:
        return "FINANCIALS"
    return "OTHER"


def hash_text(text: str) -> str:
    return str(abs(hash(text)))


# =========================================================
# STATE FILE
# =========================================================

def load_engine_state() -> EngineState:
    if not os.path.exists(STATE_FILE):
        return EngineState()

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        lock_raw = data.get("lock_state", {})
        return EngineState(
            lock_state=SystemLockState(
                trading_locked=lock_raw.get("trading_locked", False),
                lock_reason=lock_raw.get("lock_reason", ""),
                locked_at=lock_raw.get("locked_at", ""),
            ),
            rejected_order_count=data.get("rejected_order_count", 0),
            last_heartbeat_ts=data.get("last_heartbeat_ts", 0.0),
            last_alert_hash=data.get("last_alert_hash", ""),
            last_prices=data.get("last_prices", {}),
        )
    except Exception:
        return EngineState()


def save_engine_state(state: EngineState) -> None:
    payload = {
        "lock_state": asdict(state.lock_state),
        "rejected_order_count": state.rejected_order_count,
        "last_heartbeat_ts": state.last_heartbeat_ts,
        "last_alert_hash": state.last_alert_hash,
        "last_prices": state.last_prices,
    }
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


# =========================================================
# ALERTS
# =========================================================

def send_telegram_message(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        return r.ok
    except Exception:
        return False


def send_discord_message(message: str, premium: bool = False) -> bool:
    webhook_url = DISCORD_PREMIUM_WEBHOOK_URL if premium else DISCORD_WEBHOOK_URL
    if not webhook_url:
        return False

    try:
        r = requests.post(webhook_url, json={"content": message}, timeout=15)
        return r.ok
    except Exception:
        return False


def send_alert(message: str, premium: bool = False) -> None:
    send_telegram_message(message)
    send_discord_message(message, premium=premium)


# =========================================================
# MARKET DATA
# =========================================================

def fetch_twelve_quote(symbol: str) -> Optional[MarketBar]:
    if not TWELVE_DATA_API_KEY:
        return None

    url = "https://api.twelvedata.com/quote"
    params = {
        "symbol": symbol,
        "apikey": TWELVE_DATA_API_KEY
    }

    try:
        r = requests.get(url, params=params, timeout=20)
        data = r.json()

        if "code" in data and data.get("status") == "error":
            return None

        price = safe_float(data.get("close") or data.get("price"))
        open_price = safe_float(data.get("open"))
        high = safe_float(data.get("high"))
        low = safe_float(data.get("low"))
        prev_close = safe_float(data.get("previous_close"))
        volume = safe_float(data.get("volume"))

        return MarketBar(
            symbol=symbol,
            price=price,
            open_price=open_price,
            high=high,
            low=low,
            volume=volume,
            prev_close=prev_close,
            timestamp=now_iso()
        )
    except Exception:
        return None


def fetch_market_snapshot(symbols: List[str]) -> Dict[str, MarketBar]:
    out = {}
    for symbol in symbols:
        bar = fetch_twelve_quote(symbol)
        if bar:
            out[symbol] = bar
    return out


# =========================================================
# BLACK SWAN HELPERS
# =========================================================

def calc_gross_exposure_pct(snapshot: RiskSnapshot) -> float:
    gross = sum(abs(p.market_value) for p in snapshot.open_positions)
    return pct_of_equity(gross, snapshot.equity)


def calc_net_exposure_pct(snapshot: RiskSnapshot) -> float:
    net = sum(p.market_value for p in snapshot.open_positions)
    return pct_of_equity(abs(net), snapshot.equity)


def calc_symbol_exposures(snapshot: RiskSnapshot) -> Dict[str, float]:
    exposures = {}
    for p in snapshot.open_positions:
        exposures[p.symbol] = exposures.get(p.symbol, 0.0) + abs(p.market_value)
    return {k: pct_of_equity(v, snapshot.equity) for k, v in exposures.items()}


def calc_cluster_exposures(snapshot: RiskSnapshot) -> Dict[str, float]:
    exposures = {}
    for p in snapshot.open_positions:
        exposures[p.cluster] = exposures.get(p.cluster, 0.0) + abs(p.market_value)
    return {k: pct_of_equity(v, snapshot.equity) for k, v in exposures.items()}


def max_dict_item(d: Dict[str, float]) -> Optional[Tuple[str, float]]:
    if not d:
        return None
    k = max(d, key=d.get)
    return k, d[k]


# =========================================================
# BLACK SWAN ENGINE
# =========================================================

def evaluate_black_swan_risk(
    snapshot: RiskSnapshot,
    stress: MarketStressState,
    config: BlackSwanConfig,
    rejected_order_count: int = 0
) -> BlackSwanDecision:

    daily_loss_pct = pct_of_equity(abs(min(snapshot.daily_pnl, 0.0)), snapshot.equity)
    weekly_loss_pct = pct_of_equity(abs(min(snapshot.weekly_pnl, 0.0)), snapshot.equity)

    gross_exposure_pct = calc_gross_exposure_pct(snapshot)
    net_exposure_pct = calc_net_exposure_pct(snapshot)
    symbol_exposures = calc_symbol_exposures(snapshot)
    cluster_exposures = calc_cluster_exposures(snapshot)

    reasons = []

    if daily_loss_pct >= config.daily_loss_limit_pct:
        reasons.append(f"Daily loss breached: {daily_loss_pct:.2f}%")
        return BlackSwanDecision(
            status="FLAT_AND_LOCK",
            size_multiplier=0.0,
            reasons=reasons,
            alert="🛑 BLACK SWAN LOCK: daily loss limit breached. Flatten all positions and lock system.",
            lock_trading=True
        )

    if weekly_loss_pct >= config.weekly_loss_limit_pct:
        reasons.append(f"Weekly loss breached: {weekly_loss_pct:.2f}%")
        return BlackSwanDecision(
            status="FLAT_AND_LOCK",
            size_multiplier=0.0,
            reasons=reasons,
            alert="🛑 BLACK SWAN LOCK: weekly loss limit breached. Flatten all positions and lock system.",
            lock_trading=True
        )

    infra_fail_reasons = []

    if stress.execution_disconnect:
        infra_fail_reasons.append("Execution disconnect detected")
    if stress.data_stale:
        infra_fail_reasons.append("Data stale")
    if stress.trading_halt_detected:
        infra_fail_reasons.append("Trading halt detected")
    if stress.rejected_orders_spiking:
        infra_fail_reasons.append("Rejected orders spiking")
    if rejected_order_count >= config.max_rejected_orders_before_lock:
        infra_fail_reasons.append(f"Rejected orders >= {config.max_rejected_orders_before_lock}")
    if stress.slippage_spike and stress.abnormal_spread:
        infra_fail_reasons.append("Slippage spike with abnormal spread")

    if infra_fail_reasons:
        return BlackSwanDecision(
            status="FLAT_AND_LOCK",
            size_multiplier=0.0,
            reasons=infra_fail_reasons,
            alert="🚨 BLACK SWAN LOCK: broker/data/execution compromised. Flatten and lock trading.",
            lock_trading=True
        )

    shock_detected = False
    shock_reasons = []

    if stress.vix >= config.vix_hard_stop:
        shock_detected = True
        shock_reasons.append(f"VIX hard stop triggered ({stress.vix:.2f})")

    if abs(stress.gap_move_pct) >= config.gap_move_hard_stop_pct:
        shock_detected = True
        shock_reasons.append(f"Gap move too large ({stress.gap_move_pct:.2f}%)")

    if abs(stress.spy_move_pct) >= config.intraday_index_shock_pct:
        shock_detected = True
        shock_reasons.append(f"SPY shock move ({stress.spy_move_pct:.2f}%)")

    if abs(stress.qqq_move_pct) >= config.intraday_index_shock_pct:
        shock_detected = True
        shock_reasons.append(f"QQQ shock move ({stress.qqq_move_pct:.2f}%)")

    if shock_detected and stress.liquidity_thin:
        shock_reasons.append("Liquidity thin during shock")
        return BlackSwanDecision(
            status="FLAT_AND_LOCK",
            size_multiplier=0.0,
            reasons=shock_reasons,
            alert="⚠️ BLACK SWAN LOCK: shock regime with weak liquidity. Flatten all and lock.",
            lock_trading=True
        )

    if shock_detected:
        return BlackSwanDecision(
            status="BLOCK_NEW",
            size_multiplier=0.0,
            reasons=shock_reasons,
            alert="⚠️ BLACK SWAN DEFENSE: shock conditions detected. Block new trades.",
            lock_trading=False
        )

    if gross_exposure_pct >= config.max_gross_exposure_pct:
        reasons.append(f"Gross exposure too high ({gross_exposure_pct:.2f}%)")
        return BlackSwanDecision(
            status="BLOCK_NEW",
            size_multiplier=0.0,
            reasons=reasons,
            alert="⛔ BLOCK NEW TRADES: gross exposure cap reached.",
            lock_trading=False
        )

    if net_exposure_pct >= config.max_net_exposure_pct:
        reasons.append(f"Net exposure too high ({net_exposure_pct:.2f}%)")
        return BlackSwanDecision(
            status="BLOCK_NEW",
            size_multiplier=0.0,
            reasons=reasons,
            alert="⛔ BLOCK NEW TRADES: net exposure cap reached.",
            lock_trading=False
        )

    max_symbol = max_dict_item(symbol_exposures)
    if max_symbol and max_symbol[1] >= config.max_symbol_exposure_pct:
        reasons.append(f"Symbol concentration too high: {max_symbol[0]} = {max_symbol[1]:.2f}%")
        return BlackSwanDecision(
            status="BLOCK_NEW",
            size_multiplier=0.0,
            reasons=reasons,
            alert=f"⛔ BLOCK NEW TRADES: symbol concentration cap hit on {max_symbol[0]}.",
            lock_trading=False
        )

    max_cluster = max_dict_item(cluster_exposures)
    if max_cluster and max_cluster[1] >= config.max_cluster_exposure_pct:
        reasons.append(f"Cluster concentration too high: {max_cluster[0]} = {max_cluster[1]:.2f}%")
        return BlackSwanDecision(
            status="BLOCK_NEW",
            size_multiplier=0.0,
            reasons=reasons,
            alert=f"⛔ BLOCK NEW TRADES: correlated cluster cap hit on {max_cluster[0]}.",
            lock_trading=False
        )

    reduce_reasons = []

    if stress.vix >= config.vix_reduce_risk:
        reduce_reasons.append(f"VIX elevated ({stress.vix:.2f})")
    if stress.regime_break_detected:
        reduce_reasons.append("Regime break detected")
    if stress.breadth_breaking_down:
        reduce_reasons.append("Breadth deterioration")
    if stress.liquidity_thin:
        reduce_reasons.append("Liquidity thin")
    if stress.slippage_spike:
        reduce_reasons.append("Slippage spike")
    if stress.abnormal_spread:
        reduce_reasons.append("Abnormal spread")

    if len(reduce_reasons) >= 3:
        return BlackSwanDecision(
            status="REDUCE_SIZE",
            size_multiplier=config.severe_size_multiplier,
            reasons=reduce_reasons,
            alert=f"⚠️ SEVERE RISK REDUCTION: {' | '.join(reduce_reasons)}. Cut size aggressively.",
            lock_trading=False
        )

    if len(reduce_reasons) >= 1:
        return BlackSwanDecision(
            status="REDUCE_SIZE",
            size_multiplier=config.abnormal_size_multiplier,
            reasons=reduce_reasons,
            alert=f"⚠️ RISK REDUCTION: {' | '.join(reduce_reasons)}. Trade smaller.",
            lock_trading=False
        )

    return BlackSwanDecision(
        status="ALLOW",
        size_multiplier=1.0,
        reasons=["No black swan constraints triggered"],
        alert="✅ Risk layer clear. Trading allowed.",
        lock_trading=False
    )


# =========================================================
# PLAN ENGINE
# =========================================================

def classify_grade(confidence: float) -> str:
    if confidence >= 0.90:
        return "A+"
    if confidence >= 0.82:
        return "A"
    if confidence >= 0.74:
        return "B+"
    if confidence >= 0.65:
        return "B"
    if confidence >= 0.55:
        return "C"
    return "AVOID"


def detect_basic_signal(bar: MarketBar) -> TradePlan:
    move_from_open = pct_change(bar.price, bar.open_price) if bar.open_price else 0.0
    gap_pct = pct_change(bar.open_price, bar.prev_close) if bar.prev_close and bar.open_price else 0.0

    action = "HOLD"
    confidence = 0.50
    reasons = []
    tags = []

    if move_from_open > 0.45:
        action = "ENTER_CALL"
        confidence = 0.76
        reasons.append(f"{bar.symbol} showing positive expansion from open ({move_from_open:.2f}%).")
        tags.extend(["bullish", "expansion"])
    elif move_from_open < -0.45:
        action = "ENTER_PUT"
        confidence = 0.76
        reasons.append(f"{bar.symbol} showing negative expansion from open ({move_from_open:.2f}%).")
        tags.extend(["bearish", "expansion"])
    else:
        reasons.append(f"{bar.symbol} is inside neutral range from open ({move_from_open:.2f}%).")
        tags.append("neutral")

    if abs(gap_pct) >= 1.0:
        confidence += 0.05
        reasons.append(f"Gap context present ({gap_pct:.2f}%).")

    confidence = min(confidence, 0.95)
    grade = classify_grade(confidence)

    return TradePlan(
        symbol=bar.symbol,
        action=action if grade != "AVOID" else "HOLD",
        grade=grade,
        confidence=confidence,
        size=1,
        entry_price=bar.price,
        trigger_level=bar.open_price if bar.open_price else None,
        stop_level=bar.low if action == "ENTER_CALL" else (bar.high if action == "ENTER_PUT" else None),
        target_level=(bar.price * 1.01) if action == "ENTER_CALL" else ((bar.price * 0.99) if action == "ENTER_PUT" else None),
        reasons=reasons,
        alerts=[],
        tags=tags
    )


def apply_black_swan_override_to_plan(plan: TradePlan, black_swan: BlackSwanDecision) -> TradePlan:
    plan.reasons.extend(black_swan.reasons)
    plan.alerts.append(black_swan.alert)

    if black_swan.status == "ALLOW":
        return plan

    if black_swan.status == "REDUCE_SIZE":
        plan.size = max(1, int(round(plan.size * black_swan.size_multiplier))) if plan.size > 0 else 0
        plan.confidence = max(0.0, plan.confidence * 0.85)
        plan.reasons.append("Black swan defense reduced size.")
        return plan

    if black_swan.status == "BLOCK_NEW":
        if plan.action in ["ENTER_CALL", "ENTER_PUT", "BUY", "SELL", "OPEN"]:
            plan.action = "HOLD"
        plan.size = 0
        plan.confidence = min(plan.confidence, 0.20)
        plan.reasons.append("Black swan defense blocked new trades.")
        return plan

    if black_swan.status in ["FORCE_EXIT_ALL", "FLAT_AND_LOCK"]:
        plan.action = "EXIT_ALL"
        plan.size = 0
        plan.confidence = 1.0
        plan.reasons.append("Black swan defense forced exit / flat lock.")
        return plan

    return plan


# =========================================================
# LOCK MANAGEMENT
# =========================================================

def update_system_lock(lock_state: SystemLockState, black_swan: BlackSwanDecision) -> SystemLockState:
    if black_swan.lock_trading:
        lock_state.trading_locked = True
        lock_state.lock_reason = black_swan.alert
        if not lock_state.locked_at:
            lock_state.locked_at = now_iso()
    return lock_state


def manual_unlock_if_allowed(state: EngineState, config: BlackSwanConfig) -> None:
    if state.lock_state.trading_locked and config.allow_new_trades_after_lock:
        state.lock_state.trading_locked = False
        state.lock_state.lock_reason = ""
        state.lock_state.locked_at = ""


def can_trade(lock_state: SystemLockState) -> bool:
    return not lock_state.trading_locked


# =========================================================
# EXECUTION PLACEHOLDERS
# =========================================================

def flatten_all_positions(snapshot: RiskSnapshot) -> None:
    if snapshot.open_positions:
        send_alert("🛑 EMERGENCY FLATTEN: flattening all positions now.", premium=True)


def cancel_open_orders() -> None:
    send_alert("🧹 CANCEL OPEN ORDERS: cancelling all open orders.", premium=True)


# =========================================================
# STRESS MODEL
# =========================================================

def build_market_stress_state(market: Dict[str, MarketBar], state: EngineState) -> MarketStressState:
    spy = market.get("SPY")
    qqq = market.get("QQQ")
    vix = market.get("VIX") or market.get("^VIX")

    spy_move = pct_change(spy.price, spy.prev_close) if spy and spy.prev_close else 0.0
    qqq_move = pct_change(qqq.price, qqq.prev_close) if qqq and qqq.prev_close else 0.0
    gap_move = pct_change(spy.open_price, spy.prev_close) if spy and spy.prev_close and spy.open_price else 0.0

    vix_value = vix.price if vix else 0.0
    vix_prev = vix.prev_close if vix else 0.0

    breadth_breaking_down = (spy_move < -1.0 and qqq_move < -1.0)
    liquidity_thin = False
    slippage_spike = False
    abnormal_spread = False
    trading_halt_detected = False
    data_stale = len(market) == 0
    execution_disconnect = False
    rejected_orders_spiking = state.rejected_order_count >= 2
    regime_break_detected = abs(spy_move) > 1.0 or abs(qqq_move) > 1.0

    return MarketStressState(
        vix=vix_value,
        vix_prev_close=vix_prev,
        spy_move_pct=spy_move,
        qqq_move_pct=qqq_move,
        gap_move_pct=gap_move,
        breadth_breaking_down=breadth_breaking_down,
        liquidity_thin=liquidity_thin,
        slippage_spike=slippage_spike,
        abnormal_spread=abnormal_spread,
        trading_halt_detected=trading_halt_detected,
        data_stale=data_stale,
        execution_disconnect=execution_disconnect,
        rejected_orders_spiking=rejected_orders_spiking,
        regime_break_detected=regime_break_detected
    )


# =========================================================
# ACCOUNT SNAPSHOT PLACEHOLDER
# =========================================================

def build_risk_snapshot(state: EngineState) -> RiskSnapshot:
    # Replace this with live broker/account values when you connect execution.
    return RiskSnapshot(
        equity=100000.0,
        cash=100000.0,
        daily_pnl=0.0,
        weekly_pnl=0.0,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        open_positions=[]
    )


# =========================================================
# FORMATTERS
# =========================================================

def format_plan_alert(plan: TradePlan) -> str:
    lines = [
        f"📊 {plan.symbol} PLAN",
        f"Action: {plan.action}",
        f"Grade: {plan.grade}",
        f"Confidence: {plan.confidence:.2f}",
        f"Size: {plan.size}",
        f"Entry: {plan.entry_price:.2f}",
    ]

    if plan.trigger_level is not None:
        lines.append(f"Trigger: {plan.trigger_level:.2f}")
    if plan.stop_level is not None:
        lines.append(f"Stop: {plan.stop_level:.2f}")
    if plan.target_level is not None:
        lines.append(f"Target: {plan.target_level:.2f}")

    if plan.reasons:
        lines.append("Reasons:")
        lines.extend([f"- {r}" for r in plan.reasons[:5]])

    if plan.alerts:
        lines.append("Risk:")
        lines.extend([f"- {a}" for a in plan.alerts[:3]])

    return "\n".join(lines)


def format_heartbeat(state: EngineState, stress: MarketStressState) -> str:
    status = "LOCKED" if state.lock_state.trading_locked else "ACTIVE"
    return (
        f"💓 HEARTBEAT\n"
        f"Status: {status}\n"
        f"Lock Reason: {state.lock_state.lock_reason or 'None'}\n"
        f"Rejected Orders: {state.rejected_order_count}\n"
        f"VIX: {stress.vix:.2f}\n"
        f"SPY Move: {stress.spy_move_pct:.2f}%\n"
        f"QQQ Move: {stress.qqq_move_pct:.2f}%"
    )


# =========================================================
# CORE LOOP
# =========================================================

def should_send_heartbeat(state: EngineState) -> bool:
    if not ENABLE_HEARTBEAT:
        return False
    elapsed = time.time() - state.last_heartbeat_ts
    return elapsed >= HEARTBEAT_MINUTES * 60


def analyze_symbol(
    symbol: str,
    market: Dict[str, MarketBar],
    black_swan: BlackSwanDecision
) -> Optional[TradePlan]:
    bar = market.get(symbol)
    if not bar:
        return None

    plan = detect_basic_signal(bar)
    plan = apply_black_swan_override_to_plan(plan, black_swan)
    return plan


def maybe_send_plan_alert(state: EngineState, plan: TradePlan) -> None:
    text = format_plan_alert(plan)
    text_hash = hash_text(text)

    if text_hash == state.last_alert_hash:
        return

    premium = plan.grade in ["A+", "A", "B+"]
    send_alert(text, premium=premium)
    state.last_alert_hash = text_hash


def process_cycle(state: EngineState, config: BlackSwanConfig) -> None:
    symbols_to_fetch = list(set(SYMBOLS + ["SPY", "QQQ", "VIX"]))
    market = fetch_market_snapshot(symbols_to_fetch)

    for sym, bar in market.items():
        state.last_prices[sym] = bar.price

    snapshot = build_risk_snapshot(state)
    stress = build_market_stress_state(market, state)

    black_swan = evaluate_black_swan_risk(
        snapshot=snapshot,
        stress=stress,
        config=config,
        rejected_order_count=state.rejected_order_count
    )

    state.lock_state = update_system_lock(state.lock_state, black_swan)

    if black_swan.status in ["FORCE_EXIT_ALL", "FLAT_AND_LOCK"]:
        cancel_open_orders()
        flatten_all_positions(snapshot)
        send_alert(black_swan.alert, premium=True)

    if should_send_heartbeat(state):
        send_alert(format_heartbeat(state, stress), premium=False)
        state.last_heartbeat_ts = time.time()

    for symbol in SYMBOLS:
        plan = analyze_symbol(symbol, market, black_swan)
        if not plan:
            continue

        if state.lock_state.trading_locked:
            plan.action = "HOLD"
            plan.size = 0
            plan.reasons.append(f"System locked: {state.lock_state.lock_reason}")

        maybe_send_plan_alert(state, plan)


# =========================================================
# COMMANDS
# =========================================================

def run_status(config: BlackSwanConfig) -> None:
    state = load_engine_state()
    snapshot = build_risk_snapshot(state)
    market = fetch_market_snapshot(list(set(SYMBOLS + ["SPY", "QQQ", "VIX"])))
    stress = build_market_stress_state(market, state)
    black_swan = evaluate_black_swan_risk(snapshot, stress, config, state.rejected_order_count)

    print("========== STATUS ==========")
    print(f"Trading Locked: {state.lock_state.trading_locked}")
    print(f"Lock Reason: {state.lock_state.lock_reason}")
    print(f"Rejected Orders: {state.rejected_order_count}")
    print(f"Black Swan Status: {black_swan.status}")
    print(f"Black Swan Alert: {black_swan.alert}")
    print("============================")


def run_unlock() -> None:
    state = load_engine_state()
    state.lock_state = SystemLockState()
    save_engine_state(state)
    msg = "🔓 MANUAL RESET: trading lock cleared."
    print(msg)
    send_alert(msg, premium=True)


def run_flatten() -> None:
    state = load_engine_state()
    snapshot = build_risk_snapshot(state)
    cancel_open_orders()
    flatten_all_positions(snapshot)
    state.lock_state.trading_locked = True
    state.lock_state.lock_reason = "Manual flatten invoked."
    state.lock_state.locked_at = now_iso()
    save_engine_state(state)
    msg = "🛑 MANUAL FLATTEN: all positions should be flattened and system locked."
    print(msg)
    send_alert(msg, premium=True)


def run_once(config: BlackSwanConfig) -> None:
    state = load_engine_state()
    process_cycle(state, config)
    save_engine_state(state)


def run_loop(config: BlackSwanConfig) -> None:
    state = load_engine_state()
    send_alert("🚀 Analyzer started.", premium=False)

    while True:
        try:
            process_cycle(state, config)
            save_engine_state(state)
        except KeyboardInterrupt:
            send_alert("🛑 Analyzer stopped manually.", premium=False)
            save_engine_state(state)
            break
        except Exception as e:
            msg = f"❌ MAIN LOOP ERROR: {type(e).__name__}: {e}"
            print(msg)
            send_alert(msg, premium=True)
            save_engine_state(state)

        time.sleep(POLL_SECONDS)


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    config = BlackSwanConfig()

    command = os.getenv("BOT_COMMAND", "run").strip().lower()

    if command == "status":
        run_status(config)
    elif command == "unlock":
        run_unlock()
    elif command == "flatten":
        run_flatten()
    elif command == "once":
        run_once(config)
    else:
        run_loop(config)

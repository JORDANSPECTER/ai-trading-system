import os
import time
import requests
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime

# =========================================================
# CONFIG
# =========================================================
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_PAPER = os.getenv("ALPACA_PAPER", "true").lower() == "true"

LIVE_TRADING = os.getenv("LIVE_TRADING", "false").lower() == "true"
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "60"))
WATCHLIST = ["QQQ", "SPY"]

MIN_EXECUTION_GRADE = "A"
GRADE_ORDER = {"C": 1, "B": 2, "A": 3, "A+": 4}

BULLISH_CONFIRM_BONUS = 15
BEARISH_CONFIRM_BONUS = 15
CONFLICT_PENALTY = 20
MIXED_PENALTY = 5

DEFAULT_ORDER_QTY = int(os.getenv("DEFAULT_ORDER_QTY", "1"))

# =========================================================
# OPTIONAL ALPACA IMPORT
# =========================================================
alpaca_client = None
try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce

    if ALPACA_API_KEY and ALPACA_SECRET_KEY:
        alpaca_client = TradingClient(
            api_key=ALPACA_API_KEY,
            secret_key=ALPACA_SECRET_KEY,
            paper=ALPACA_PAPER,
        )
except Exception as e:
    print(f"[ALPACA IMPORT WARNING] {e}")
    alpaca_client = None

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

# =========================================================
# UTILS
# =========================================================
def safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def passes_grade_threshold(grade: str, threshold: str) -> bool:
    return GRADE_ORDER.get(grade, 0) >= GRADE_ORDER.get(threshold, 0)

# =========================================================
# ALERTS
# =========================================================
def send_discord(message: str) -> None:
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": message}, timeout=10)
    except Exception as e:
        print(f"[DISCORD ERROR] {e}")


def send_telegram(message: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")


def broadcast(message: str) -> None:
    print(message)
    send_discord(message)
    send_telegram(message)

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

    return list(reversed(data["values"]))  # oldest -> newest


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
            "bars": bars,
        }
    except Exception as e:
        print(f"[SNAPSHOT ERROR] {symbol}: {e}")
        return None

# =========================================================
# CONSTITUENT ENGINE
# =========================================================
def load_constituent_snapshots(etf_symbol: str) -> List[ConstituentSnapshot]:
    snapshots: List[ConstituentSnapshot] = []

    for item in ETF_CONSTITUENTS.get(etf_symbol, []):
        symbol = item["symbol"]
        weight = item["weight"]

        data = get_symbol_snapshot(symbol)
        if not data:
            continue

        snapshots.append(
            ConstituentSnapshot(
                symbol=symbol,
                price=safe_float(data["price"]),
                vwap=safe_float(data["vwap"]),
                change_pct=safe_float(data["change_pct"]),
                volume_ratio=safe_float(data.get("volume_ratio", 1.0)),
                weight=safe_float(weight),
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
    leaders_up: List[str] = []
    leaders_down: List[str] = []
    conflicts: List[str] = []
    leadership_raw: List[float] = []

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
        summary = f"{etf_symbol} internals bullish: {bullish_names}/{len(snapshots)} aligned, {aligned_bullish_weight:.0%} weighted support."
    elif aligned_bearish_weight >= 0.55 and bearish_participation >= 0.50:
        bias = "BEARISH_CONFIRMATION"
        summary = f"{etf_symbol} internals bearish: {bearish_names}/{len(snapshots)} aligned, {aligned_bearish_weight:.0%} weighted pressure."
    else:
        bias = "MIXED"
        summary = f"{etf_symbol} internals mixed: {bullish_names} bullish vs {bearish_names} bearish aligned names."

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

    snapshots = load_constituent_snapshots(context.symbol)
    internals = analyze_constituent_internals(context.symbol, snapshots)

    context.constituent_snapshots = snapshots
    context.constituent_internals = internals
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
    reasons: List[str] = []
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
        reasons.append(f"Volume expansion present ({context.volume_ratio:.2f}x).")
    else:
        reasons.append(f"Volume not expanding strongly ({context.volume_ratio:.2f}x).")

    if context.above_vwap and context.change_pct > 0:
        score += 8
        reasons.append("Price change supports bullish continuation.")
    elif context.below_vwap and context.change_pct < 0:
        score += 8
        reasons.append("Price change supports bearish continuation.")
    else:
        reasons.append("Price change is not cleanly aligned.")

    if context.above_vwap and context.rsi >= 52:
        action = "BUY_CALL"
    elif context.below_vwap and context.rsi <= 48:
        action = "BUY_PUT"
    else:
        action = "NO_TRADE"

    return TradePlan(
        symbol=context.symbol,
        action=action,
        grade=score_to_grade(score),
        score=score,
        confidence=max(0.0, min(score / 100.0, 0.99)),
        reasons=reasons,
    )


def apply_constituent_confirmation(context: MarketContext, plan: TradePlan) -> TradePlan:
    ci = context.constituent_internals
    if not ci:
        return plan

    plan.reasons.append(ci.summary)

    if plan.action == "BUY_CALL":
        if ci.confirmation_bias == "BULLISH_CONFIRMATION":
            plan.score += BULLISH_CONFIRM_BONUS
            plan.reasons.append(f"Constituent confirmation bullish. Leaders up: {', '.join(ci.leaders_up[:5]) or 'none'}.")
        elif ci.confirmation_bias == "BEARISH_CONFIRMATION":
            plan.score -= CONFLICT_PENALTY
            plan.reasons.append(f"Call setup weakened by bearish internals. Leaders down: {', '.join(ci.leaders_down[:5]) or 'none'}.")
        else:
            plan.score -= MIXED_PENALTY
            plan.reasons.append("Call setup has mixed internal participation.")
    elif plan.action == "BUY_PUT":
        if ci.confirmation_bias == "BEARISH_CONFIRMATION":
            plan.score += BEARISH_CONFIRM_BONUS
            plan.reasons.append(f"Constituent confirmation bearish. Leaders down: {', '.join(ci.leaders_down[:5]) or 'none'}.")
        elif ci.confirmation_bias == "BULLISH_CONFIRMATION":
            plan.score -= CONFLICT_PENALTY
            plan.reasons.append(f"Put setup weakened by bullish internals. Leaders up: {', '.join(ci.leaders_up[:5]) or 'none'}.")
        else:
            plan.score -= MIXED_PENALTY
            plan.reasons.append("Put setup has mixed internal participation.")

    plan.grade = score_to_grade(plan.score)
    plan.confidence = max(0.0, min(plan.score / 100.0, 0.99))
    return plan


def execution_filter(plan: TradePlan, context: MarketContext) -> Tuple[str, List[str]]:
    notes: List[str] = []
    ci = context.constituent_internals

    if plan.action == "NO_TRADE":
        notes.append("Blocked: no clear directional action.")
        return "AVOID", notes

    if not passes_grade_threshold(plan.grade, MIN_EXECUTION_GRADE):
        notes.append(f"Blocked: grade {plan.grade} is below execution threshold {MIN_EXECUTION_GRADE}.")
        return "AVOID", notes

    if ci:
        if plan.action == "BUY_CALL" and ci.confirmation_bias == "BEARISH_CONFIRMATION":
            notes.append("Blocked: ETF internals are bearish against bullish setup.")
            return "AVOID", notes

        if plan.action == "BUY_PUT" and ci.confirmation_bias == "BULLISH_CONFIRMATION":
            notes.append("Blocked: ETF internals are bullish against bearish setup.")
            return "AVOID", notes

        if ci.confirmation_bias == "MIXED":
            notes.append("Caution: constituent internals are mixed.")

    if context.volume_ratio < 0.85:
        notes.append("Blocked: volume too weak.")
        return "AVOID", notes

    notes.append("Execution filter passed.")
    return "EXECUTE", notes

# =========================================================
# ALPACA EXECUTION
# =========================================================
def execute_trade(plan: TradePlan, context: MarketContext) -> None:
    if not LIVE_TRADING:
        print(f"[PAPER MODE LOCAL] {plan.action} {context.symbol} | Grade {plan.grade} | Score {plan.score}")
        return

    if alpaca_client is None:
        msg = "❌ LIVE_TRADING is ON but Alpaca is not connected. Check ALPACA_API_KEY / ALPACA_SECRET_KEY / dependency install."
        print(msg)
        send_telegram(msg)
        send_discord(msg)
        return

    try:
        if plan.action == "BUY_CALL":
            side = OrderSide.BUY
        elif plan.action == "BUY_PUT":
            side = OrderSide.SELL
        else:
            print(f"[SKIP] No executable action: {plan.action}")
            return

        order_request = MarketOrderRequest(
            symbol=context.symbol,
            qty=DEFAULT_ORDER_QTY,
            side=side,
            time_in_force=TimeInForce.DAY,
        )

        order = alpaca_client.submit_order(order_data=order_request)

        msg = (
            f"✅ ALPACA ORDER SENT\n"
            f"Symbol: {context.symbol}\n"
            f"Action: {plan.action}\n"
            f"Side: {side.value}\n"
            f"Qty: {DEFAULT_ORDER_QTY}\n"
            f"Grade: {plan.grade}\n"
            f"Score: {plan.score}\n"
            f"Broker Mode: {'PAPER' if ALPACA_PAPER else 'LIVE'}\n"
            f"Order ID: {order.id}"
        )
        print(msg)
        send_telegram(msg)
        send_discord(msg)

    except Exception as e:
        err = f"❌ ALPACA ORDER FAILED: {e}"
        print(err)
        send_telegram(err)
        send_discord(err)

# =========================================================
# ALERT FORMAT
# =========================================================
def build_constituent_summary_for_alert(context: MarketContext) -> str:
    ci = context.constituent_internals
    if not ci:
        return "Constituent internals: unavailable."

    if ci.confirmation_bias == "BULLISH_CONFIRMATION":
        return f"📈 Internals bullish | Leaders up: {', '.join(ci.leaders_up[:4]) or 'none'} | Bull participation: {ci.bullish_participation:.0%}"
    if ci.confirmation_bias == "BEARISH_CONFIRMATION":
        return f"📉 Internals bearish | Leaders down: {', '.join(ci.leaders_down[:4]) or 'none'} | Bear participation: {ci.bearish_participation:.0%}"
    return f"⚖️ Internals mixed | Conflicts: {', '.join(ci.conflicts[:5]) or 'none'}"


def build_alert(plan: TradePlan, context: MarketContext, status: str, notes: List[str]) -> str:
    emoji = "🟢" if plan.action == "BUY_CALL" else "🔴" if plan.action == "BUY_PUT" else "⚪"
    now_str = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")

    lines = [
        f"{emoji} {context.symbol} FRAMEWORK UPDATE",
        f"Time: {now_str}",
        f"Price: {context.current_price:.2f}",
        f"VWAP: {context.vwap:.2f}",
        f"RSI: {context.rsi:.1f}",
        f"Change: {context.change_pct:.2f}%",
        f"Vol Ratio: {context.volume_ratio:.2f}x",
        f"Action: {plan.action}",
        f"Grade: {plan.grade}",
        f"Score: {plan.score}",
        f"Confidence: {plan.confidence:.0%}",
        build_constituent_summary_for_alert(context),
        "Reasons:",
    ]

    for reason in plan.reasons[:6]:
        lines.append(f"- {reason}")

    lines.append("Execution Filter:")
    for note in notes:
        lines.append(f"- {note}")

    lines.append(f"Final Status: {status}")
    lines.append(f"LIVE_TRADING: {LIVE_TRADING}")
    lines.append(f"ALPACA_PAPER: {ALPACA_PAPER}")

    return "\n".join(lines)

# =========================================================
# MAIN LOOP
# =========================================================
def run_symbol(symbol: str) -> None:
    context = build_market_context(symbol)
    if not context:
        print(f"[WARN] Could not build context for {symbol}")
        return

    plan = make_hybrid_decision(context)
    plan = apply_constituent_confirmation(context, plan)
    status, notes = execution_filter(plan, context)

    message = build_alert(plan, context, status, notes)
    broadcast(message)

    if status == "EXECUTE":
        execute_trade(plan, context)


def main() -> None:
    startup = (
        "🚀 UnBiased Framework started\n"
        f"Watchlist: {', '.join(WATCHLIST)}\n"
        f"LIVE_TRADING: {LIVE_TRADING}\n"
        f"ALPACA_PAPER: {ALPACA_PAPER}\n"
        f"Alpaca Connected: {alpaca_client is not None}\n"
        "Constituent engine active."
    )
    broadcast(startup)

    while True:
        try:
            for symbol in WATCHLIST:
                run_symbol(symbol)
                time.sleep(2)
        except Exception as e:
            err = f"❌ MAIN LOOP ERROR: {e}"
            print(err)
            send_telegram(err)
            send_discord(err)

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()

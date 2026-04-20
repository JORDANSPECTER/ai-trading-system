import os
import json
import time
import uuid
import requests
from datetime import datetime
from typing import Dict, Any, List, Optional

# =========================================================
# ENV
# =========================================================
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

POSITIONS_FILE = os.getenv("POSITIONS_FILE", "positions.json")
FILLS_FILE = os.getenv("FILLS_FILE", "fills.json")

PAPER_MODE = os.getenv("PAPER_MODE", "true").lower() == "true"
LIVE_TRADING = os.getenv("LIVE_TRADING", "false").lower() == "true"
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "300"))

MIN_ALERT_GRADE = os.getenv("MIN_ALERT_GRADE", "A")
DEFAULT_POSITION_SIZE = int(os.getenv("DEFAULT_POSITION_SIZE", "1"))

# -------------------------
# ALPACA
# -------------------------
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

# Example:
# paper: https://paper-api.alpaca.markets
# live:  https://api.alpaca.markets

# =========================================================
# HELPERS
# =========================================================
def utc_now_iso() -> str:
    return datetime.utcnow().isoformat()

def safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default

def safe_int(value, default=0) -> int:
    try:
        return int(value)
    except Exception:
        return default

def load_json_file(path: str, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[WARN] Failed loading {path}: {e}")
    return default

def save_json_file(path: str, data) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[WARN] Failed saving {path}: {e}")

# =========================================================
# ALERT DELIVERY
# =========================================================
def send_to_discord(message: str) -> bool:
    if not DISCORD_WEBHOOK_URL:
        print("[INFO] DISCORD_WEBHOOK_URL not set")
        return False

    try:
        payload = {"content": message[:1900]}
        r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=15)
        if 200 <= r.status_code < 300:
            return True
        print(f"[WARN] Discord failed: {r.status_code} | {r.text}")
        return False
    except Exception as e:
        print(f"[WARN] Discord exception: {e}")
        return False

def send_telegram_message(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[INFO] Telegram token/chat id not set")
        return False

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message[:4000]}
        r = requests.post(url, json=payload, timeout=15)
        if 200 <= r.status_code < 300:
            return True
        print(f"[WARN] Telegram failed: {r.status_code} | {r.text}")
        return False
    except Exception as e:
        print(f"[WARN] Telegram exception: {e}")
        return False

def send_alert(message: str) -> None:
    print(message)
    send_to_discord(message)
    send_telegram_message(message)

# =========================================================
# ALPACA CLIENT
# =========================================================
class AlpacaClient:
    def __init__(self, api_key: str, secret_key: str, base_url: str):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url.rstrip("/")

    def enabled(self) -> bool:
        return bool(self.api_key and self.secret_key)

    def _headers(self) -> Dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Content-Type": "application/json"
        }

    def submit_market_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        time_in_force: str = "day"
    ) -> Dict[str, Any]:
        if not self.enabled():
            raise ValueError("Alpaca keys not configured")

        url = f"{self.base_url}/v2/orders"
        payload = {
            "symbol": symbol.upper(),
            "qty": str(qty),
            "side": side.lower(),
            "type": "market",
            "time_in_force": time_in_force
        }

        r = requests.post(url, headers=self._headers(), json=payload, timeout=20)
        if not (200 <= r.status_code < 300):
            raise ValueError(f"Alpaca order failed: {r.status_code} | {r.text}")
        return r.json()

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        if not self.enabled():
            return None

        url = f"{self.base_url}/v2/positions/{symbol.upper()}"
        r = requests.get(url, headers=self._headers(), timeout=20)

        if r.status_code == 404:
            return None
        if not (200 <= r.status_code < 300):
            raise ValueError(f"Alpaca get_position failed: {r.status_code} | {r.text}")
        return r.json()

    def close_position(self, symbol: str) -> Dict[str, Any]:
        if not self.enabled():
            raise ValueError("Alpaca keys not configured")

        url = f"{self.base_url}/v2/positions/{symbol.upper()}"
        r = requests.delete(url, headers=self._headers(), timeout=20)
        if not (200 <= r.status_code < 300):
            raise ValueError(f"Alpaca close_position failed: {r.status_code} | {r.text}")
        return r.json()

alpaca_client = AlpacaClient(
    api_key=ALPACA_API_KEY,
    secret_key=ALPACA_SECRET_KEY,
    base_url=ALPACA_BASE_URL
)

# =========================================================
# PAPER EXECUTION ENGINE
# =========================================================
class PaperExecutionEngine:
    def __init__(self, positions_file: str = POSITIONS_FILE, fills_file: str = FILLS_FILE):
        self.positions_file = positions_file
        self.fills_file = fills_file
        self.positions: Dict[str, Dict[str, Any]] = load_json_file(self.positions_file, {})
        self.fills: List[Dict[str, Any]] = load_json_file(self.fills_file, [])

    def save(self):
        save_json_file(self.positions_file, self.positions)
        save_json_file(self.fills_file, self.fills)

    def _make_fill(
        self,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        strategy: str = "",
        reason: str = "",
        position_id: Optional[str] = None,
        status: str = "filled",
        broker_order_id: Optional[str] = None,
        mode: str = "paper"
    ) -> Dict[str, Any]:
        return {
            "fill_id": str(uuid.uuid4()),
            "position_id": position_id,
            "timestamp": utc_now_iso(),
            "symbol": symbol.upper(),
            "side": side.lower(),
            "qty": safe_int(qty),
            "price": round(safe_float(price), 4),
            "strategy": strategy,
            "reason": reason,
            "status": status,
            "broker_order_id": broker_order_id,
            "mode": mode
        }

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self.positions.get(symbol.upper())

    def get_all_positions(self) -> Dict[str, Dict[str, Any]]:
        return self.positions

    def get_fills(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.fills[-limit:]

    def open_or_add_position(
        self,
        symbol: str,
        qty: int,
        price: float,
        strategy: str = "",
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        alert_grade: str = "",
        note: str = "",
        entry_reason: str = "new_position",
        broker_order_id: Optional[str] = None,
        mode: str = "paper"
    ) -> Dict[str, Any]:
        symbol = symbol.upper()
        qty = safe_int(qty)
        price = safe_float(price)

        if qty <= 0 or price <= 0:
            raise ValueError("qty and price must be greater than 0")

        existing = self.positions.get(symbol)

        if existing:
            old_qty = safe_int(existing.get("qty", 0))
            old_avg = safe_float(existing.get("avg_price", 0.0))
            new_qty = old_qty + qty
            new_avg = ((old_qty * old_avg) + (qty * price)) / new_qty

            existing["qty"] = new_qty
            existing["avg_price"] = round(new_avg, 4)
            existing["last_price"] = round(price, 4)
            existing["market_value"] = round(new_qty * price, 4)
            existing["unrealized_pnl"] = round((price - new_avg) * new_qty, 4)
            existing["updated_at"] = utc_now_iso()
            existing["strategy"] = strategy or existing.get("strategy", "")
            existing["stop_loss"] = stop_loss if stop_loss is not None else existing.get("stop_loss")
            existing["take_profit"] = take_profit if take_profit is not None else existing.get("take_profit")
            existing["alert_grade"] = alert_grade or existing.get("alert_grade", "")
            existing["note"] = note or existing.get("note", "")
            existing["entry_count"] = safe_int(existing.get("entry_count", 1)) + 1
            existing["mode"] = mode

            fill = self._make_fill(
                symbol=symbol,
                side="buy",
                qty=qty,
                price=price,
                strategy=strategy,
                reason="add_to_position",
                position_id=existing["position_id"],
                broker_order_id=broker_order_id,
                mode=mode
            )
            self.fills.append(fill)
            self.save()
            return existing

        position = {
            "position_id": str(uuid.uuid4()),
            "symbol": symbol,
            "side": "long",
            "qty": qty,
            "avg_price": round(price, 4),
            "last_price": round(price, 4),
            "market_value": round(qty * price, 4),
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
            "strategy": strategy,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "alert_grade": alert_grade,
            "note": note,
            "entry_reason": entry_reason,
            "opened_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            "entry_count": 1,
            "mode": mode,
            "broker_order_id": broker_order_id
        }

        self.positions[symbol] = position

        fill = self._make_fill(
            symbol=symbol,
            side="buy",
            qty=qty,
            price=price,
            strategy=strategy,
            reason=entry_reason,
            position_id=position["position_id"],
            broker_order_id=broker_order_id,
            mode=mode
        )
        self.fills.append(fill)
        self.save()
        return position

    def close_position(
        self,
        symbol: str,
        qty: int,
        price: float,
        reason: str = "close",
        strategy: str = "",
        broker_order_id: Optional[str] = None,
        mode: str = "paper"
    ) -> Dict[str, Any]:
        symbol = symbol.upper()
        qty = safe_int(qty)
        price = safe_float(price)

        if symbol not in self.positions:
            raise ValueError(f"No open position found for {symbol}")

        pos = self.positions[symbol]
        current_qty = safe_int(pos.get("qty", 0))
        avg_price = safe_float(pos.get("avg_price", 0.0))

        if qty <= 0 or price <= 0:
            raise ValueError("qty and price must be greater than 0")

        if qty > current_qty:
            raise ValueError(f"Cannot close {qty}; only {current_qty} open for {symbol}")

        realized = (price - avg_price) * qty
        pos["realized_pnl"] = round(safe_float(pos.get("realized_pnl", 0.0)) + realized, 4)
        pos["last_price"] = round(price, 4)
        pos["updated_at"] = utc_now_iso()

        fill = self._make_fill(
            symbol=symbol,
            side="sell",
            qty=qty,
            price=price,
            strategy=strategy or pos.get("strategy", ""),
            reason=reason,
            position_id=pos["position_id"],
            broker_order_id=broker_order_id,
            mode=mode
        )
        self.fills.append(fill)

        remaining_qty = current_qty - qty

        if remaining_qty == 0:
            closed_summary = {
                **pos,
                "closed_at": utc_now_iso(),
                "close_price": round(price, 4),
                "closed_qty": qty,
                "final_realized_pnl": round(pos["realized_pnl"], 4),
                "status": "closed",
                "close_reason": reason,
                "broker_close_order_id": broker_order_id
            }
            del self.positions[symbol]
            self.save()
            return closed_summary

        pos["qty"] = remaining_qty
        pos["market_value"] = round(remaining_qty * price, 4)
        pos["unrealized_pnl"] = round((price - avg_price) * remaining_qty, 4)
        self.save()
        return pos

    def update_market_price(self, symbol: str, current_price: float) -> Optional[Dict[str, Any]]:
        symbol = symbol.upper()
        current_price = safe_float(current_price)

        if symbol not in self.positions or current_price <= 0:
            return None

        pos = self.positions[symbol]
        qty = safe_int(pos.get("qty", 0))
        avg_price = safe_float(pos.get("avg_price", 0.0))

        pos["last_price"] = round(current_price, 4)
        pos["market_value"] = round(qty * current_price, 4)
        pos["unrealized_pnl"] = round((current_price - avg_price) * qty, 4)
        pos["updated_at"] = utc_now_iso()

        self.save()
        return pos

    def portfolio_snapshot(self) -> Dict[str, Any]:
        total_market_value = 0.0
        total_unrealized = 0.0
        total_realized_open = 0.0

        for pos in self.positions.values():
            total_market_value += safe_float(pos.get("market_value", 0.0))
            total_unrealized += safe_float(pos.get("unrealized_pnl", 0.0))
            total_realized_open += safe_float(pos.get("realized_pnl", 0.0))

        return {
            "open_positions": len(self.positions),
            "total_market_value": round(total_market_value, 4),
            "total_unrealized_pnl": round(total_unrealized, 4),
            "total_realized_pnl_on_open_positions": round(total_realized_open, 4),
            "updated_at": utc_now_iso()
        }

paper_engine = PaperExecutionEngine()

# =========================================================
# FORMATTERS
# =========================================================
def format_position_message(pos: Dict[str, Any]) -> str:
    return (
        f"📌 POSITION UPDATE\n"
        f"Mode: {pos.get('mode', 'paper')}\n"
        f"Symbol: {pos.get('symbol')}\n"
        f"Qty: {pos.get('qty')}\n"
        f"Avg: {pos.get('avg_price')}\n"
        f"Last: {pos.get('last_price')}\n"
        f"Stop: {pos.get('stop_loss')}\n"
        f"Target: {pos.get('take_profit')}\n"
        f"Market Value: {pos.get('market_value')}\n"
        f"Unrealized P&L: {pos.get('unrealized_pnl')}\n"
        f"Realized P&L: {pos.get('realized_pnl')}\n"
        f"Strategy: {pos.get('strategy', '')}\n"
        f"Grade: {pos.get('alert_grade', '')}\n"
        f"Note: {pos.get('note', '')}\n"
        f"Opened: {pos.get('opened_at', '')}\n"
        f"Updated: {pos.get('updated_at', '')}"
    )

def format_close_message(closed: Dict[str, Any]) -> str:
    return (
        f"✅ POSITION CLOSED\n"
        f"Mode: {closed.get('mode', 'paper')}\n"
        f"Symbol: {closed.get('symbol')}\n"
        f"Closed Qty: {closed.get('closed_qty', closed.get('qty'))}\n"
        f"Entry Avg: {closed.get('avg_price')}\n"
        f"Exit: {closed.get('close_price', closed.get('last_price'))}\n"
        f"Final Realized P&L: {closed.get('final_realized_pnl', closed.get('realized_pnl'))}\n"
        f"Reason: {closed.get('close_reason', '')}\n"
        f"Closed At: {closed.get('closed_at', utc_now_iso())}"
    )

def format_alert_payload(alert: Dict[str, Any]) -> str:
    return (
        f"🚨 ALERT ENGINE SIGNAL\n"
        f"Symbol: {alert.get('symbol')}\n"
        f"Price: {alert.get('price')}\n"
        f"Grade: {alert.get('grade')}\n"
        f"Setup: {alert.get('setup')}\n"
        f"Bias: {alert.get('bias')}\n"
        f"Stop: {alert.get('stop_loss')}\n"
        f"Target: {alert.get('take_profit')}\n"
        f"Confidence: {alert.get('confidence')}\n"
        f"Reason: {alert.get('reason')}"
    )

def format_portfolio_snapshot(snapshot: Dict[str, Any]) -> str:
    return (
        f"📊 PORTFOLIO SNAPSHOT\n"
        f"Open Positions: {snapshot['open_positions']}\n"
        f"Market Value: {snapshot['total_market_value']}\n"
        f"Unrealized P&L: {snapshot['total_unrealized_pnl']}\n"
        f"Realized P&L (open positions): {snapshot['total_realized_pnl_on_open_positions']}\n"
        f"Updated: {snapshot['updated_at']}"
    )

# =========================================================
# ALERT ENGINE
# =========================================================
GRADE_RANK = {
    "A+": 5,
    "A": 4,
    "B": 3,
    "C": 2,
    "D": 1
}

def grade_passes(grade: str, minimum: str = MIN_ALERT_GRADE) -> bool:
    return GRADE_RANK.get(str(grade).upper(), 0) >= GRADE_RANK.get(str(minimum).upper(), 0)

def build_alert_payload(
    symbol: str,
    price: float,
    setup: str,
    bias: str,
    grade: str,
    confidence: float,
    stop_loss: Optional[float],
    take_profit: Optional[float],
    reason: str
) -> Dict[str, Any]:
    return {
        "symbol": symbol.upper(),
        "price": round(safe_float(price), 4),
        "setup": setup,
        "bias": str(bias).lower(),
        "grade": str(grade).upper(),
        "confidence": round(safe_float(confidence), 2),
        "stop_loss": safe_float(stop_loss) if stop_loss is not None else None,
        "take_profit": safe_float(take_profit) if take_profit is not None else None,
        "reason": reason,
        "timestamp": utc_now_iso()
    }

def default_position_size_from_grade(grade: str) -> int:
    grade = str(grade).upper()
    if grade == "A+":
        return max(DEFAULT_POSITION_SIZE + 2, 3)
    if grade == "A":
        return max(DEFAULT_POSITION_SIZE + 1, 2)
    if grade == "B":
        return DEFAULT_POSITION_SIZE
    return 1

# =========================================================
# EXECUTION ROUTING
# =========================================================
def route_entry_order(symbol: str, qty: int, price_hint: float) -> Dict[str, Any]:
    """
    Routes order either to Alpaca or paper mode.
    Returns normalized execution result.
    """
    if LIVE_TRADING:
        if not alpaca_client.enabled():
            raise ValueError("LIVE_TRADING is true but Alpaca keys are missing")

        broker_order = alpaca_client.submit_market_order(
            symbol=symbol,
            qty=qty,
            side="buy"
        )

        return {
            "mode": "live",
            "broker_order_id": broker_order.get("id"),
            "filled_price": safe_float(price_hint),
            "raw": broker_order
        }

    return {
        "mode": "paper",
        "broker_order_id": None,
        "filled_price": safe_float(price_hint),
        "raw": None
    }

def route_exit_order(symbol: str, qty: int, price_hint: float) -> Dict[str, Any]:
    if LIVE_TRADING:
        if not alpaca_client.enabled():
            raise ValueError("LIVE_TRADING is true but Alpaca keys are missing")

        broker_order = alpaca_client.submit_market_order(
            symbol=symbol,
            qty=qty,
            side="sell"
        )

        return {
            "mode": "live",
            "broker_order_id": broker_order.get("id"),
            "filled_price": safe_float(price_hint),
            "raw": broker_order
        }

    return {
        "mode": "paper",
        "broker_order_id": None,
        "filled_price": safe_float(price_hint),
        "raw": None
    }

def execute_entry_from_alert(alert: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    symbol = alert["symbol"]
    price = safe_float(alert["price"])
    grade = alert["grade"]
    setup = alert["setup"]
    stop_loss = alert.get("stop_loss")
    take_profit = alert.get("take_profit")
    reason = alert.get("reason", "")
    bias = alert.get("bias", "bullish")

    if bias != "bullish":
        send_alert(
            f"⚠️ ALERT QUALIFIED BUT NOT EXECUTED\n"
            f"Symbol: {symbol}\n"
            f"Bias: {bias}\n"
            f"Reason: this phase is long-only"
        )
        return None

    qty = default_position_size_from_grade(grade)
    routing = route_entry_order(symbol=symbol, qty=qty, price_hint=price)

    pos = paper_engine.open_or_add_position(
        symbol=symbol,
        qty=qty,
        price=routing["filled_price"],
        strategy=setup,
        stop_loss=stop_loss,
        take_profit=take_profit,
        alert_grade=grade,
        note=reason,
        entry_reason="alert_engine_entry",
        broker_order_id=routing["broker_order_id"],
        mode=routing["mode"]
    )

    send_alert(
        f"🎯 ALERT EXECUTED\n"
        f"Execution Mode: {routing['mode']}\n\n"
        f"{format_alert_payload(alert)}\n\n"
        f"{format_position_message(pos)}"
    )
    return pos

def process_alert(alert: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    send_alert(format_alert_payload(alert))

    grade = alert.get("grade", "D")
    if not grade_passes(grade):
        send_alert(
            f"⛔ ALERT BLOCKED\n"
            f"Symbol: {alert.get('symbol')}\n"
            f"Grade: {grade}\n"
            f"Minimum Required: {MIN_ALERT_GRADE}"
        )
        return None

    existing = paper_engine.get_position(alert["symbol"])
    if existing:
        send_alert(
            f"ℹ️ EXISTING POSITION FOUND\n"
            f"Symbol: {alert['symbol']}\n"
            f"Current Qty: {existing.get('qty')}\n"
            f"Engine will add to position."
        )

    return execute_entry_from_alert(alert)

def execute_exit(
    symbol: str,
    qty: int,
    exit_price: float,
    reason: str = "take_profit",
    strategy: str = ""
) -> Dict[str, Any]:
    routing = route_exit_order(symbol=symbol, qty=qty, price_hint=exit_price)

    result = paper_engine.close_position(
        symbol=symbol,
        qty=qty,
        price=routing["filled_price"],
        reason=reason,
        strategy=strategy,
        broker_order_id=routing["broker_order_id"],
        mode=routing["mode"]
    )

    if result.get("status") == "closed":
        send_alert(format_close_message(result))
    else:
        send_alert(format_position_message(result))
    return result

def check_position_exit_rules(symbol: str, current_price: float) -> Optional[str]:
    pos = paper_engine.get_position(symbol)
    if not pos:
        return None

    stop_loss = pos.get("stop_loss")
    take_profit = pos.get("take_profit")

    if stop_loss is not None and current_price <= safe_float(stop_loss):
        return "stop_loss_hit"

    if take_profit is not None and current_price >= safe_float(take_profit):
        return "take_profit_hit"

    return None

def update_open_position_prices(latest_prices: Dict[str, float]) -> Dict[str, Dict[str, Any]]:
    updated_positions = {}

    for symbol, current_price in latest_prices.items():
        pos = paper_engine.update_market_price(symbol, current_price)
        if not pos:
            continue

        updated_positions[symbol] = pos

        exit_reason = check_position_exit_rules(symbol, safe_float(current_price))
        if exit_reason:
            qty = safe_int(pos.get("qty", 0))
            execute_exit(
                symbol=symbol,
                qty=qty,
                exit_price=safe_float(current_price),
                reason=exit_reason,
                strategy=pos.get("strategy", "")
            )

    if updated_positions:
        send_alert(format_portfolio_snapshot(paper_engine.portfolio_snapshot()))

    return updated_positions

def send_portfolio_snapshot() -> None:
    send_alert(format_portfolio_snapshot(paper_engine.portfolio_snapshot()))

# =========================================================
# TEST / MOCK FEED
# Replace these with your real engine later
# =========================================================
def get_mock_alerts() -> List[Dict[str, Any]]:
    return [
        build_alert_payload(
            symbol="QQQ",
            price=518.25,
            setup="VWAP reclaim + momentum",
            bias="bullish",
            grade="A",
            confidence=0.91,
            stop_loss=516.90,
            take_profit=521.75,
            reason="reclaim over VWAP with momentum confirmation"
        )
    ]

def get_mock_market_prices() -> Dict[str, float]:
    return {
        "QQQ": 521.90
    }

# =========================================================
# MAIN
# =========================================================
def send_heartbeat() -> None:
    snapshot = paper_engine.portfolio_snapshot()
    send_alert(
        f"💓 ENGINE HEARTBEAT\n"
        f"PAPER_MODE: {PAPER_MODE}\n"
        f"LIVE_TRADING: {LIVE_TRADING}\n"
        f"ALPACA_ENABLED: {alpaca_client.enabled()}\n"
        f"MIN_ALERT_GRADE: {MIN_ALERT_GRADE}\n"
        f"Open Positions: {snapshot['open_positions']}\n"
        f"Market Value: {snapshot['total_market_value']}\n"
        f"Unrealized P&L: {snapshot['total_unrealized_pnl']}\n"
        f"Updated: {snapshot['updated_at']}"
    )

def main():
    print(">>> MAIN STARTED <<<")

    send_alert(
        "🚀 ELITE EXECUTION ENGINE ONLINE\n"
        f"PAPER_MODE={PAPER_MODE}\n"
        f"LIVE_TRADING={LIVE_TRADING}\n"
        f"ALPACA_ENABLED={alpaca_client.enabled()}"
    )

    # -----------------------------------------------------
    # FORCE TEST SIGNAL ON STARTUP
    # -----------------------------------------------------
    try:
        send_alert("🔥 TEST ALERT TRIGGER")

        test_alert = build_alert_payload(
            symbol="QQQ",
            price=518.25,
            setup="TEST VWAP",
            bias="bullish",
            grade="A",
            confidence=0.95,
            stop_loss=516.50,
            take_profit=522.00,
            reason="manual startup test trigger"
        )

        process_alert(test_alert)

        time.sleep(2)
        update_open_position_prices({"QQQ": 521.40})

    except Exception as e:
        send_alert(f"❌ STARTUP TEST FAILED: {e}")

    last_heartbeat = 0
    mock_alerts_processed = False
    mock_prices_processed = False

    while True:
        try:
            now = time.time()

            # ---------------------------------------------
            # MOCK ENGINE PASS
            # ---------------------------------------------
            if not mock_alerts_processed:
                alerts = get_mock_alerts()
                for alert in alerts:
                    process_alert(alert)
                mock_alerts_processed = True

            if mock_alerts_processed and not mock_prices_processed:
                time.sleep(3)
                latest_prices = get_mock_market_prices()
                update_open_position_prices(latest_prices)
                mock_prices_processed = True

            # ---------------------------------------------
            # HEARTBEAT
            # ---------------------------------------------
            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                send_heartbeat()
                last_heartbeat = now

            time.sleep(5)

        except KeyboardInterrupt:
            print("Stopped by user")
            break
        except Exception as e:
            send_alert(f"❌ MAIN LOOP ERROR: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()

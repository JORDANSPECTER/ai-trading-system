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
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "300"))

# =========================================================
# BASIC HELPERS
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
# ALERTING
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
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message[:4000]
        }
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
        status: str = "filled"
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
            "status": status
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
        note: str = ""
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
            if note:
                existing["note"] = note

            fill = self._make_fill(
                symbol=symbol,
                side="buy",
                qty=qty,
                price=price,
                strategy=strategy,
                reason="add_to_position",
                position_id=existing["position_id"]
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
            "opened_at": utc_now_iso(),
            "updated_at": utc_now_iso()
        }

        self.positions[symbol] = position

        fill = self._make_fill(
            symbol=symbol,
            side="buy",
            qty=qty,
            price=price,
            strategy=strategy,
            reason="new_position",
            position_id=position["position_id"]
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
        strategy: str = ""
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
            position_id=pos["position_id"]
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
                "status": "closed"
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

    def mark_all_to_market(self, price_map: Dict[str, float]) -> Dict[str, Dict[str, Any]]:
        updated = {}
        for symbol, px in price_map.items():
            pos = self.update_market_price(symbol, px)
            if pos:
                updated[symbol] = pos
        return updated

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
        f"📌 PAPER POSITION UPDATE\n"
        f"Symbol: {pos.get('symbol')}\n"
        f"Qty: {pos.get('qty')}\n"
        f"Avg: {pos.get('avg_price')}\n"
        f"Last: {pos.get('last_price')}\n"
        f"Market Value: {pos.get('market_value')}\n"
        f"Unrealized P&L: {pos.get('unrealized_pnl')}\n"
        f"Realized P&L: {pos.get('realized_pnl')}\n"
        f"Strategy: {pos.get('strategy', '')}\n"
        f"Grade: {pos.get('alert_grade', '')}\n"
        f"Opened: {pos.get('opened_at', '')}\n"
        f"Updated: {pos.get('updated_at', '')}"
    )

def format_close_message(closed: Dict[str, Any]) -> str:
    return (
        f"✅ PAPER POSITION CLOSED\n"
        f"Symbol: {closed.get('symbol')}\n"
        f"Closed Qty: {closed.get('closed_qty', closed.get('qty'))}\n"
        f"Entry Avg: {closed.get('avg_price')}\n"
        f"Exit: {closed.get('close_price', closed.get('last_price'))}\n"
        f"Final Realized P&L: {closed.get('final_realized_pnl', closed.get('realized_pnl'))}\n"
        f"Closed At: {closed.get('closed_at', utc_now_iso())}"
    )

def format_portfolio_snapshot(snapshot: Dict[str, Any]) -> str:
    return (
        f"📊 PAPER PORTFOLIO SNAPSHOT\n"
        f"Open Positions: {snapshot['open_positions']}\n"
        f"Market Value: {snapshot['total_market_value']}\n"
        f"Unrealized P&L: {snapshot['total_unrealized_pnl']}\n"
        f"Realized P&L (open positions): {snapshot['total_realized_pnl_on_open_positions']}\n"
        f"Updated: {snapshot['updated_at']}"
    )

def format_recent_fills(fills: List[Dict[str, Any]]) -> str:
    if not fills:
        return "🧾 NO FILLS YET"

    lines = ["🧾 RECENT PAPER FILLS"]
    for f in fills[-10:]:
        lines.append(
            f"{f.get('timestamp')} | {f.get('symbol')} | {f.get('side').upper()} | "
            f"QTY {f.get('qty')} | PX {f.get('price')} | {f.get('reason')}"
        )
    return "\n".join(lines)

# =========================================================
# EXECUTION ACTIONS
# =========================================================
def execute_paper_entry(
    symbol: str,
    qty: int,
    entry_price: float,
    strategy: str = "",
    grade: str = "",
    note: str = "",
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None
) -> Dict[str, Any]:
    pos = paper_engine.open_or_add_position(
        symbol=symbol,
        qty=qty,
        price=entry_price,
        strategy=strategy,
        alert_grade=grade,
        note=note,
        stop_loss=stop_loss,
        take_profit=take_profit
    )

    msg = format_position_message(pos)
    send_alert(msg)
    return pos

def execute_paper_exit(
    symbol: str,
    qty: int,
    exit_price: float,
    reason: str = "take_profit",
    strategy: str = ""
) -> Dict[str, Any]:
    result = paper_engine.close_position(
        symbol=symbol,
        qty=qty,
        price=exit_price,
        reason=reason,
        strategy=strategy
    )

    if result.get("status") == "closed":
        msg = format_close_message(result)
    else:
        msg = format_position_message(result)

    send_alert(msg)
    return result

def update_open_position_prices(latest_prices: Dict[str, float]) -> Dict[str, Dict[str, Any]]:
    updated = paper_engine.mark_all_to_market(latest_prices)
    if updated:
        snapshot = paper_engine.portfolio_snapshot()
        send_alert(format_portfolio_snapshot(snapshot))
    return updated

def send_portfolio_snapshot() -> None:
    snapshot = paper_engine.portfolio_snapshot()
    send_alert(format_portfolio_snapshot(snapshot))

def send_recent_fills(limit: int = 10) -> None:
    fills = paper_engine.get_fills(limit=limit)
    send_alert(format_recent_fills(fills))

# =========================================================
# OPTIONAL SIMPLE COMMAND ROUTER
# =========================================================
def handle_debug_command(command: str) -> None:
    """
    Local debug command examples:
    entry QQQ 2 518.25
    add QQQ 1 519.10
    price QQQ 521.40
    exit QQQ 1 522.00
    snapshot
    fills
    """

    try:
        parts = command.strip().split()
        if not parts:
            return

        action = parts[0].lower()

        if action == "entry":
            symbol = parts[1]
            qty = int(parts[2])
            price = float(parts[3])
            execute_paper_entry(
                symbol=symbol,
                qty=qty,
                entry_price=price,
                strategy="manual_debug_entry",
                grade="A",
                note="debug entry"
            )

        elif action == "add":
            symbol = parts[1]
            qty = int(parts[2])
            price = float(parts[3])
            execute_paper_entry(
                symbol=symbol,
                qty=qty,
                entry_price=price,
                strategy="manual_debug_add",
                grade="A",
                note="debug add"
            )

        elif action == "price":
            symbol = parts[1]
            price = float(parts[2])
            updated = paper_engine.update_market_price(symbol, price)
            if updated:
                send_alert(format_position_message(updated))
            else:
                send_alert(f"⚠️ No open position to update for {symbol}")

        elif action == "exit":
            symbol = parts[1]
            qty = int(parts[2])
            price = float(parts[3])
            execute_paper_exit(
                symbol=symbol,
                qty=qty,
                exit_price=price,
                reason="manual_debug_exit"
            )

        elif action == "snapshot":
            send_portfolio_snapshot()

        elif action == "fills":
            send_recent_fills()

        elif action == "positions":
            positions = paper_engine.get_all_positions()
            if not positions:
                send_alert("📭 NO OPEN POSITIONS")
            else:
                for pos in positions.values():
                    send_alert(format_position_message(pos))

        else:
            send_alert(f"Unknown command: {command}")

    except Exception as e:
        send_alert(f"❌ Command failed: {command}\nError: {e}")

# =========================================================
# HEARTBEAT
# =========================================================
def send_heartbeat() -> None:
    snapshot = paper_engine.portfolio_snapshot()
    msg = (
        f"💓 ENGINE HEARTBEAT\n"
        f"PAPER_MODE: {PAPER_MODE}\n"
        f"Open Positions: {snapshot['open_positions']}\n"
        f"Market Value: {snapshot['total_market_value']}\n"
        f"Unrealized P&L: {snapshot['total_unrealized_pnl']}\n"
        f"Updated: {snapshot['updated_at']}"
    )
    send_alert(msg)

# =========================================================
# MAIN LOOP
# =========================================================
def main():
    send_alert("🚀 ELITE EXECUTION PHASE 1 ONLINE\nPosition tracking + paper fill tracking active")

    # -----------------------------------------------------
    # TEST BLOCKS
    # Uncomment these one at a time if you want to test fast
    # -----------------------------------------------------

    # execute_paper_entry(
    #     symbol="QQQ",
    #     qty=2,
    #     entry_price=518.25,
    #     strategy="VWAP reclaim + momentum",
    #     grade="A",
    #     note="Pressure release setup"
    # )

    # execute_paper_entry(
    #     symbol="QQQ",
    #     qty=1,
    #     entry_price=519.10,
    #     strategy="VWAP reclaim + momentum",
    #     grade="A",
    #     note="Add on confirmation"
    # )

    # update_open_position_prices({"QQQ": 521.40})

    # execute_paper_exit(
    #     symbol="QQQ",
    #     qty=1,
    #     exit_price=522.00,
    #     reason="trim_strength"
    # )

    # execute_paper_exit(
    #     symbol="QQQ",
    #     qty=2,
    #     exit_price=523.25,
    #     reason="target_hit"
    # )

    # send_recent_fills()
    # send_portfolio_snapshot()

    last_heartbeat = 0

    while True:
        try:
            now = time.time()

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

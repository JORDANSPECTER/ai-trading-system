# ============================================================
# IMPORTS
# ============================================================

import requests
import time
import os
from datetime import datetime

# ============================================================
# TELEGRAM
# ============================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    requests.post(url, data=payload)

# ============================================================
# MAIN LOOP (WE WILL UPGRADE THIS)
# ============================================================

def run():
    send_telegram("✅ SYSTEM ONLINE")

    while True:
        send_telegram("📊 Running...")
        time.sleep(300)

if __name__ == "__main__":
    run()

# =========================================
# FAKE AI OBJECTS FOR ALERT TEST
# =========================================

class FakeContext:
    symbol = "QQQ"
    current_price = 527.35

class FakeStructure:
    above_vwap = True

class FakeDecision:
    direction = "LONG"
    grade = "A"
    setup_name = "Break + Hold Above Trigger"
    should_enter = True
    size = 1
    bias = "BULLISH CONTINUATION"

context = FakeContext()
structure = FakeStructure()
decision = FakeDecision()

push_ai_update(context, structure, decision, send_alerts=True)

import requests
import time
from datetime import datetime

# =========================================
# CONFIG
# =========================================
TOKEN = "8288769897:AAGoa0PFwm_Z4fFc4_ZMuKuAu_UPJymnY8E"
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"
ALLOWED_CHAT_ID = "8661143355"

# =========================================
# SYSTEM STATE
# =========================================
last_update_id = None

system_state = {
    "kill_switch": False,
    "flatten_requested": False,
    "ai_monitoring": True,
    "last_alert": "none",

    "watched_symbol": "QQQ",
    "market_bias": "NEUTRAL",
    "oil_regime": "UNKNOWN",
    "vwap_status": "UNKNOWN",
    "latest_setup_grade": "NONE",
    "latest_setup_name": "NONE",

    "open_position": False,
    "position_symbol": "NONE",
    "position_side": "NONE",
    "position_size": 0,
    "entry_price": 0,
    "current_price": 0,
}

# =========================================
# HELPERS
# =========================================
def now():
    return datetime.now().strftime("%H:%M:%S")

def send_message(chat_id, text):
    url = f"{BASE_URL}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": text})

def get_updates(offset=None):
    url = f"{BASE_URL}/getUpdates"
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    return requests.get(url, params=params).json()

# =========================================
# STATUS
# =========================================
def build_status():
    return (
        f"📊 AI COMMAND CENTER\n\n"
        f"Kill Switch: {system_state['kill_switch']}\n"
        f"Flatten: {system_state['flatten_requested']}\n\n"

        f"Symbol: {system_state['watched_symbol']}\n"
        f"Bias: {system_state['market_bias']}\n"
        f"VWAP: {system_state['vwap_status']}\n"
        f"Oil: {system_state['oil_regime']}\n"
        f"Setup: {system_state['latest_setup_name']}\n"
        f"Grade: {system_state['latest_setup_grade']}\n\n"

        f"Position: {system_state['position_symbol']} {system_state['position_side']}\n"
        f"Size: {system_state['position_size']}\n"
        f"Price: {system_state['current_price']}\n"
    )

# =========================================
# COMMANDS
# =========================================
def handle_command(chat_id, text):

    if str(chat_id) != str(ALLOWED_CHAT_ID):
        return

    if text == "/start":
        send_message(chat_id,
            "🤖 Command Center\n\n"
            "/status\n/kill\n/flatten\n/resume\n/test"
        )

    elif text == "/status":
        send_message(chat_id, build_status())

    elif text == "/kill":
        system_state["kill_switch"] = True
        send_message(chat_id, "🔴 KILL SWITCH ON")

    elif text == "/flatten":
        system_state["flatten_requested"] = True
        send_message(chat_id, "🟠 FLATTEN TRIGGERED")

    elif text == "/resume":
        system_state["kill_switch"] = False
        system_state["flatten_requested"] = False
        send_message(chat_id, "🟢 SYSTEM RESUMED")

    elif text == "/test":
        send_message(chat_id, "🚨 TEST ALERT WORKING")

# =========================================
# AI BRIDGE (KEY PART)
# =========================================
def push_ai_update(context, structure, decision):

    def get(obj, key, default=None):
        return getattr(obj, key, default) if hasattr(obj, key) else obj.get(key, default) if isinstance(obj, dict) else default

    symbol = get(context, "symbol", "QQQ")
    price = get(context, "current_price", 0)

    direction = str(get(decision, "direction", "NONE")).upper()
    grade = str(get(decision, "grade", "NONE"))
    setup = get(decision, "setup_name", "Setup")

    should_enter = get(decision, "should_enter", False)

    vwap = "ABOVE VWAP" if get(structure, "above_vwap", False) else "BELOW VWAP"
    oil = f"{get(context, 'oil_trend', '')} ({get(context, 'oil_change_dollars', '')})"

    # UPDATE DASHBOARD
    system_state.update({
        "watched_symbol": symbol,
        "market_bias": direction,
        "vwap_status": vwap,
        "oil_regime": oil,
        "latest_setup_grade": grade,
        "latest_setup_name": setup,
        "current_price": price
    })

    # BLOCK IF KILL
    if system_state["kill_switch"]:
        print("🚫 BLOCKED BY KILL SWITCH")
        return

    # FLATTEN MODE
    if system_state["flatten_requested"]:
        print("🟠 FLATTEN ACTIVE")
        return

    # POSITION UPDATE
    if should_enter:
        system_state.update({
            "open_position": True,
            "position_symbol": symbol,
            "position_side": direction,
            "position_size": get(decision, "size", 1),
            "entry_price": price
        })

        send_message(
            ALLOWED_CHAT_ID,
            f"📈 TRADE ALERT\n\n"
            f"{symbol} {direction}\n"
            f"Grade: {grade}\n"
            f"{setup}\n"
            f"Price: {price}\n"
            f"VWAP: {vwap} | Oil: {oil}"
        )

# =========================================
# MAIN LOOP
# =========================================
def run():
    global last_update_id

    while True:
        try:
            data = get_updates(last_update_id)

            if data.get("result"):
                for update in data["result"]:
                    last_update_id = update["update_id"] + 1

                    msg = update.get("message", {})
                    chat_id = msg.get("chat", {}).get("id")
                    text = msg.get("text", "")

                    if chat_id and text:
                        handle_command(chat_id, text.lower())

            time.sleep(2)

        except Exception as e:
            print("Error:", e)
            time.sleep(5)

# START BOT
run()

import requests
import time
from datetime import datetime

# =========================================
# CONFIG
# =========================================
TOKEN = "8288769897:AAGoa0PFwm_Z4fFc4_ZMuKuAu_UPJymnY8E"
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

# Your Telegram user/chat ID only
ALLOWED_CHAT_ID = 8661143355

# =========================================
# BOT / SYSTEM STATE
# =========================================
last_update_id = None

system_state = {
    "bot_online": True,
    "ai_monitoring": True,
    "kill_switch": False,
    "flatten_requested": False,
    "last_command": "none",
    "last_command_time": None,
    "last_alert": "none",

    # Live trading / analyzer state
    "watched_symbol": "QQQ",
    "market_bias": "NEUTRAL",
    "oil_regime": "UNKNOWN",
    "vwap_status": "UNKNOWN",
    "latest_setup_grade": "NONE",
    "latest_setup_name": "NONE",

    # Position state
    "open_position": False,
    "position_symbol": "NONE",
    "position_side": "NONE",
    "position_size": 0,
    "entry_price": 0.0,
    "current_price": 0.0,
    "unrealized_pnl": 0.0,
    "last_trade_action": "none",
}

# =========================================
# TELEGRAM HELPERS
# =========================================
def now_string():
    return datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")

def authorized(chat_id):
    return str(chat_id) == str(ALLOWED_CHAT_ID)

def send_message(chat_id, text):
    url = f"{BASE_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }

    try:
        r = requests.post(url, data=payload, timeout=10)
        print("send_message:", r.status_code, r.text)
    except Exception as e:
        print("send_message error:", e)

def get_updates(offset=None):
    url = f"{BASE_URL}/getUpdates"
    params = {"timeout": 30}

    if offset is not None:
        params["offset"] = offset

    try:
        r = requests.get(url, params=params, timeout=35)
        print("get_updates:", r.status_code)
        return r.json()
    except Exception as e:
        print("get_updates error:", e)
        return {"ok": False, "result": []}

# =========================================
# STATUS / DISPLAY
# =========================================
def build_status_text():
    return (
        "📊 UnBiased Alerts Command Center\n\n"
        f"Bot Online: {system_state['bot_online']}\n"
        f"AI Monitoring: {system_state['ai_monitoring']}\n"
        f"Kill Switch: {system_state['kill_switch']}\n"
        f"Flatten Requested: {system_state['flatten_requested']}\n\n"

        f"Watched Symbol: {system_state['watched_symbol']}\n"
        f"Market Bias: {system_state['market_bias']}\n"
        f"Oil Regime: {system_state['oil_regime']}\n"
        f"VWAP Status: {system_state['vwap_status']}\n"
        f"Latest Setup: {system_state['latest_setup_name']}\n"
        f"Latest Grade: {system_state['latest_setup_grade']}\n\n"

        f"Open Position: {system_state['open_position']}\n"
        f"Position Symbol: {system_state['position_symbol']}\n"
        f"Position Side: {system_state['position_side']}\n"
        f"Position Size: {system_state['position_size']}\n"
        f"Entry Price: {system_state['entry_price']}\n"
        f"Current Price: {system_state['current_price']}\n"
        f"Unrealized PnL: {system_state['unrealized_pnl']}\n"
        f"Last Trade Action: {system_state['last_trade_action']}\n\n"

        f"Last Command: {system_state['last_command']}\n"
        f"Last Command Time: {system_state['last_command_time']}\n"
        f"Last Alert: {system_state['last_alert']}\n"
    )

def help_menu(chat_id):
    send_message(
        chat_id,
        "🤖 UnBiased Alerts Command Center\n\n"
        "/start - open command center\n"
        "/help - show commands\n"
        "/heartbeat - send online ping\n"
        "/test - send test alert\n"
        "/status - full bot + AI status\n"
        "/flatten - flatten all positions\n"
        "/kill - stop new trading activity\n"
        "/resume - resume system\n"
        "/pause - pause AI monitoring\n"
        "/watchqqq - switch watched symbol to QQQ\n"
        "/watchspy - switch watched symbol to SPY\n"
    )

# =========================================
# CORE COMMAND ACTIONS
# =========================================
def heartbeat(chat_id):
    send_message(chat_id, "✅ AI SYSTEM ONLINE")

def test_alert(chat_id):
    system_state["last_alert"] = f"Test alert sent at {now_string()}"
    send_message(chat_id, "🚨 TEST ALERT WORKING")

def status(chat_id):
    send_message(chat_id, build_status_text())

def flatten_positions(chat_id):
    system_state["flatten_requested"] = True
    system_state["last_trade_action"] = "flatten_requested"

    # =====================================
    # PUT LIVE EXIT / BROKER LOGIC HERE
    # Example:
    # broker.flatten_all_positions()
    # broker.cancel_all_orders()
    # =====================================

    send_message(
        chat_id,
        "🟠 FLATTEN REQUEST RECEIVED\n"
        "All positions should be exited immediately.\n"
        "Pending entries should be blocked."
    )

def kill_system(chat_id):
    system_state["kill_switch"] = True
    system_state["ai_monitoring"] = False
    system_state["last_trade_action"] = "kill_switch_activated"

    # =====================================
    # PUT LIVE KILL LOGIC HERE
    # Example:
    # broker.cancel_all_orders()
    # broker.flatten_all_positions()
    # ai_engine.enabled = False
    # =====================================

    send_message(
        chat_id,
        "🔴 KILL SWITCH ACTIVATED\n"
        "AI monitoring disabled.\n"
        "New entries should now be blocked."
    )

def resume_system(chat_id):
    system_state["kill_switch"] = False
    system_state["ai_monitoring"] = True
    system_state["flatten_requested"] = False
    system_state["last_trade_action"] = "system_resumed"

    send_message(
        chat_id,
        "🟢 SYSTEM RESUMED\n"
        "AI monitoring re-enabled.\n"
        "Bot can continue normal operation."
    )

def pause_system(chat_id):
    system_state["ai_monitoring"] = False
    system_state["last_trade_action"] = "monitoring_paused"

    send_message(
        chat_id,
        "⏸️ AI MONITORING PAUSED\n"
        "Bot is still online, but monitoring is paused."
    )

def set_watch_symbol(chat_id, symbol):
    system_state["watched_symbol"] = symbol
    send_message(chat_id, f"👀 Now watching {symbol}")

# =========================================
# OPTIONAL AI / ENGINE UPDATE FUNCTIONS
# Call these from your analyzer later
# =========================================
def update_ai_state(
    watched_symbol=None,
    market_bias=None,
    oil_regime=None,
    vwap_status=None,
    latest_setup_grade=None,
    latest_setup_name=None
):
    if watched_symbol is not None:
        system_state["watched_symbol"] = watched_symbol
    if market_bias is not None:
        system_state["market_bias"] = market_bias
    if oil_regime is not None:
        system_state["oil_regime"] = oil_regime
    if vwap_status is not None:
        system_state["vwap_status"] = vwap_status
    if latest_setup_grade is not None:
        system_state["latest_setup_grade"] = latest_setup_grade
    if latest_setup_name is not None:
        system_state["latest_setup_name"] = latest_setup_name

def update_position_state(
    open_position=None,
    position_symbol=None,
    position_side=None,
    position_size=None,
    entry_price=None,
    current_price=None,
    unrealized_pnl=None,
    last_trade_action=None
):
    if open_position is not None:
        system_state["open_position"] = open_position
    if position_symbol is not None:
        system_state["position_symbol"] = position_symbol
    if position_side is not None:
        system_state["position_side"] = position_side
    if position_size is not None:
        system_state["position_size"] = position_size
    if entry_price is not None:
        system_state["entry_price"] = entry_price
    if current_price is not None:
        system_state["current_price"] = current_price
    if unrealized_pnl is not None:
        system_state["unrealized_pnl"] = unrealized_pnl
    if last_trade_action is not None:
        system_state["last_trade_action"] = last_trade_action

# =========================================
# ALERT HELPERS
# =========================================
def send_trade_alert(chat_id, symbol, side, grade, setup_name, price, note=""):
    system_state["last_alert"] = f"{symbol} {side} {grade} alert at {now_string()}"
    send_message(
        chat_id,
        f"📈 TRADE ALERT\n\n"
        f"Symbol: {symbol}\n"
        f"Side: {side}\n"
        f"Grade: {grade}\n"
        f"Setup: {setup_name}\n"
        f"Price: {price}\n"
        f"Note: {note}"
    )

# =========================================
# COMMAND ROUTER
# =========================================
def handle_command(chat_id, text):
    text = text.strip().lower()

    if not authorized(chat_id):
        send_message(chat_id, "⛔ Unauthorized user.")
        return

    system_state["last_command"] = text
    system_state["last_command_time"] = now_string()

    if text == "/start":
        help_menu(chat_id)

    elif text == "/help":
        help_menu(chat_id)

    elif text == "/heartbeat":
        heartbeat(chat_id)

    elif text == "/test":
        test_alert(chat_id)

    elif text == "/status":
        status(chat_id)

    elif text == "/flatten":
        flatten_positions(chat_id)

    elif text == "/kill":
        kill_system(chat_id)

    elif text == "/resume":
        resume_system(chat_id)

    elif text == "/pause":
        pause_system(chat_id)

    elif text == "/watchqqq":
        set_watch_symbol(chat_id, "QQQ")

    elif text == "/watchspy":
        set_watch_symbol(chat_id, "SPY")

    else:
        send_message(chat_id, "Unknown command. Use /help")

# =========================================
# ENGINE FLAGS
# =========================================
def process_engine_flags():
    """
    Put your live AI / broker enforcement here.
    """

    if system_state["kill_switch"]:
        # Example:
        # ai_engine.enabled = False
        # broker.cancel_all_orders()
        pass

    if system_state["flatten_requested"]:
        # Example:
        # broker.flatten_all_positions()
        # After done:
        # system_state["flatten_requested"] = False
        pass

# =========================================
# DEMO STATE UPDATER
# Remove this later when real AI is connected
# =========================================
def demo_update_state():
    if system_state["watched_symbol"] == "QQQ":
        system_state["market_bias"] = "BULLISH CONTINUATION"
        system_state["oil_regime"] = "STABILIZING"
        system_state["vwap_status"] = "ABOVE VWAP"
        system_state["latest_setup_grade"] = "A"
        system_state["latest_setup_name"] = "Break + Hold Above Trigger"
    else:
        system_state["market_bias"] = "NEUTRAL TO BEARISH"
        system_state["oil_regime"] = "PRESSURING"
        system_state["vwap_status"] = "TESTING VWAP"
        system_state["latest_setup_grade"] = "B"
        system_state["latest_setup_name"] = "Rejection At Resistance"

# =========================================
# MAIN LOOP
# =========================================
def run_bot():
    global last_update_id

    print("Bot started...")

    while True:
        try:
            demo_update_state()
            process_engine_flags()

            data = get_updates(last_update_id)

            if data.get("ok") and data.get("result"):
                for update in data["result"]:
                    last_update_id = update["update_id"] + 1

                    message = update.get("message", {})
                    chat = message.get("chat", {})
                    text = message.get("text", "")

                    chat_id = chat.get("id")
                    if chat_id and text:
                        handle_command(chat_id, text)

            time.sleep(2)

        except Exception as e:
            print("Bot loop error:", e)
            time.sleep(5)

if __name__ == "__main__":
    run_bot()

# =========================================
# AI → TELEGRAM BRIDGE CELL
# =========================================

def push_ai_update(context, structure, decision):
    """
    Call this AFTER your AI makes a decision.
    This updates Telegram command center + optionally sends alerts.
    """

    # -----------------------------
    # UPDATE AI STATE (DASHBOARD)
    # -----------------------------
    update_ai_state(
        watched_symbol=context.symbol,
        market_bias=decision.bias,
        oil_regime=f"{context.oil_trend} ({context.oil_change_dollars})",
        vwap_status="ABOVE VWAP" if structure.above_vwap else "BELOW VWAP",
        latest_setup_grade=decision.grade,
        latest_setup_name=decision.setup_name
    )

    # -----------------------------
    # UPDATE POSITION STATE
    # -----------------------------
    update_position_state(
        open_position=decision.should_enter,
        position_symbol=context.symbol if decision.should_enter else "NONE",
        position_side=decision.direction if decision.should_enter else "NONE",
        position_size=decision.size if hasattr(decision, "size") else 0,
        entry_price=context.current_price if decision.should_enter else 0,
        current_price=context.current_price,
        unrealized_pnl=0,  # plug real PnL later
        last_trade_action="ENTER" if decision.should_enter else "NO TRADE"
    )

    # -----------------------------
    # SEND ALERT (ONLY IF VALID)
    # -----------------------------
    if decision.should_enter and not system_state["kill_switch"]:

        send_trade_alert(
            chat_id=ALLOWED_CHAT_ID,
            symbol=context.symbol,
            side=decision.direction,
            grade=decision.grade,
            setup_name=decision.setup_name,
            price=context.current_price,
            note="AI CONFIRMED ENTRY"
        )

    # -----------------------------
    # BLOCK IF KILL SWITCH
    # -----------------------------
    if system_state["kill_switch"]:
        print("🚫 TRADE BLOCKED BY KILL SWITCH")

import requests
import time
from datetime import datetime

# =========================================
# CONFIG
# =========================================
TOKEN = "8288769897:AAGoa0PFwm_Z4fFc4_ZMuKuAu_UPJymnY8E"
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

# Optional: lock bot so only YOUR Telegram account can control it
# Put your personal Telegram chat id here after confirming it
ALLOWED_CHAT_ID = 8661143355

# =========================================
# BOT / SYSTEM STATE
# =========================================
last_update_id = None

system_state = {
    "bot_online": True,
    "ai_monitoring": True,
    "kill_switch": False,
    "flatten_requested": False,
    "last_command": "none",
    "last_command_time": None,
    "last_alert": "none",
    "open_position": False,         # hook this to your actual system later
    "position_symbol": "NONE",
    "position_side": "NONE",
    "position_size": 0,
}

# =========================================
# TELEGRAM HELPERS
# =========================================
def send_message(chat_id, text):
    url = f"{BASE_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }

    try:
        r = requests.post(url, data=payload, timeout=10)
        print("send_message:", r.status_code, r.text)
    except Exception as e:
        print("send_message error:", e)

def get_updates(offset=None):
    url = f"{BASE_URL}/getUpdates"
    params = {"timeout": 30}

    if offset is not None:
        params["offset"] = offset

    try:
        r = requests.get(url, params=params, timeout=35)
        print("get_updates:", r.status_code)
        return r.json()
    except Exception as e:
        print("get_updates error:", e)
        return {"ok": False, "result": []}

def authorized(chat_id):
    return str(chat_id) == str(ALLOWED_CHAT_ID)

def now_string():
    return datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")

# =========================================
# CORE SYSTEM ACTIONS
# =========================================
def heartbeat(chat_id):
    send_message(chat_id, "✅ AI SYSTEM ONLINE")

def test_alert(chat_id):
    system_state["last_alert"] = f"Test alert sent at {now_string()}"
    send_message(chat_id, "🚨 TEST ALERT WORKING")

def build_status_text():
    return (
        "📊 UnBiased Alerts Bot Status\n\n"
        f"Bot Online: {system_state['bot_online']}\n"
        f"AI Monitoring: {system_state['ai_monitoring']}\n"
        f"Kill Switch: {system_state['kill_switch']}\n"
        f"Flatten Requested: {system_state['flatten_requested']}\n"
        f"Open Position: {system_state['open_position']}\n"
        f"Position Symbol: {system_state['position_symbol']}\n"
        f"Position Side: {system_state['position_side']}\n"
        f"Position Size: {system_state['position_size']}\n"
        f"Last Command: {system_state['last_command']}\n"
        f"Last Command Time: {system_state['last_command_time']}\n"
        f"Last Alert: {system_state['last_alert']}\n"
    )

def status(chat_id):
    send_message(chat_id, build_status_text())

def flatten_positions(chat_id):
    system_state["flatten_requested"] = True
    system_state["last_command"] = "flatten"
    system_state["last_command_time"] = now_string()

    # =====================================
    # HOOK YOUR BROKER / AI EXIT LOGIC HERE
    # =====================================
    # Example:
    # broker.flatten_all_positions()
    # ai_engine.cancel_pending_entries()
    #
    # For now this is just a trigger/flag.

    send_message(
        chat_id,
        "🟠 FLATTEN REQUEST RECEIVED\n"
        "All positions should be exited immediately.\n"
        "Pending entries should be blocked."
    )

def kill_system(chat_id):
    system_state["kill_switch"] = True
    system_state["ai_monitoring"] = False
    system_state["last_command"] = "kill"
    system_state["last_command_time"] = now_string()

    # =====================================
    # HOOK YOUR SYSTEM SHUTDOWN LOGIC HERE
    # =====================================
    # Example:
    # broker.cancel_all_orders()
    # broker.flatten_all_positions()
    # ai_engine.enabled = False
    #
    # This should block new trade alerts.

    send_message(
        chat_id,
        "🔴 KILL SWITCH ACTIVATED\n"
        "AI monitoring disabled.\n"
        "New trade actions should now be blocked."
    )

def resume_system(chat_id):
    system_state["kill_switch"] = False
    system_state["ai_monitoring"] = True
    system_state["flatten_requested"] = False
    system_state["last_command"] = "resume"
    system_state["last_command_time"] = now_string()

    send_message(
        chat_id,
        "🟢 SYSTEM RESUMED\n"
        "AI monitoring re-enabled.\n"
        "Bot can continue normal operation."
    )

def help_menu(chat_id):
    send_message(
        chat_id,
        "🤖 UnBiased Alerts Command Center\n\n"
        "/start - open command center\n"
        "/heartbeat - send online ping\n"
        "/test - send test alert\n"
        "/status - full bot/system status\n"
        "/flatten - flatten all positions\n"
        "/kill - stop system / block trading\n"
        "/resume - re-enable system\n"
        "/help - show commands"
    )

# =========================================
# COMMAND ROUTER
# =========================================
def handle_command(chat_id, text):
    text = text.strip().lower()

    if not authorized(chat_id):
        send_message(chat_id, "⛔ Unauthorized user.")
        return

    system_state["last_command"] = text
    system_state["last_command_time"] = now_string()

    if text == "/start":
        help_menu(chat_id)

    elif text == "/help":
        help_menu(chat_id)

    elif text == "/heartbeat":
        heartbeat(chat_id)

    elif text == "/test":
        test_alert(chat_id)

    elif text == "/status":
        status(chat_id)

    elif text == "/flatten":
        flatten_positions(chat_id)

    elif text == "/kill":
        kill_system(chat_id)

    elif text == "/resume":
        resume_system(chat_id)

    else:
        send_message(
            chat_id,
            "Unknown command.\nUse /help to see the full command list."
        )

# =========================================
# OPTIONAL: ENGINE CHECKS
# =========================================
def process_engine_flags():
    """
    This runs in the background loop.
    Use it to connect Telegram commands to your live AI system.
    """

    if system_state["kill_switch"]:
        # Block all new trading actions here
        # Example:
        # ai_engine.enabled = False
        pass

    if system_state["flatten_requested"]:
        # Trigger one-time flatten logic here
        # After your flatten logic is done, reset the flag:
        # system_state["flatten_requested"] = False
        pass

# =========================================
# MAIN LOOP
# =========================================
def run_bot():
    global last_update_id

    print("Bot started...")

    while True:
        try:
            process_engine_flags()

            data = get_updates(last_update_id)

            if data.get("ok") and data.get("result"):
                for update in data["result"]:
                    last_update_id = update["update_id"] + 1

                    message = update.get("message", {})
                    chat = message.get("chat", {})
                    text = message.get("text", "")

                    chat_id = chat.get("id")
                    if chat_id and text:
                        handle_command(chat_id, text)

            time.sleep(2)

        except Exception as e:
            print("Bot loop error:", e)
            time.sleep(5)

if __name__ == "__main__":
    run_bot()

import requests
import time

TOKEN = "8288769897:AAGoa0PFwm_Z4fFc4_ZMuKuAu_UPJymnY8E"
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

last_update_id = None

def send_message(chat_id, text):
    url = f"{BASE_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    r = requests.post(url, data=payload, timeout=10)
    print("send_message:", r.status_code, r.text)

def get_updates(offset=None):
    url = f"{BASE_URL}/getUpdates"
    params = {"timeout": 30}
    if offset is not None:
        params["offset"] = offset
    r = requests.get(url, params=params, timeout=35)
    print("get_updates:", r.status_code, r.text)
    return r.json()

def handle_command(chat_id, text):
    if text == "/start":
        send_message(
            chat_id,
            "🤖 Heartbeat Command Center Live\n\n"
            "/heartbeat - send online ping\n"
            "/test - send test alert\n"
            "/status - bot status"
        )
    elif text == "/heartbeat":
        send_message(chat_id, "✅ AI SYSTEM ONLINE")
    elif text == "/test":
        send_message(chat_id, "🚨 TEST ALERT WORKING")
    elif text == "/status":
        send_message(chat_id, "📊 Bot is running and monitoring.")
    else:
        send_message(chat_id, "Unknown command. Try /start")

def run_bot():
    global last_update_id

    while True:
        try:
            data = get_updates(last_update_id)

            if data.get("ok") and data.get("result"):
                for update in data["result"]:
                    last_update_id = update["update_id"] + 1

                    message = update.get("message", {})
                    chat = message.get("chat", {})
                    text = message.get("text", "")

                    chat_id = chat.get("id")
                    if chat_id and text:
                        handle_command(chat_id, text)

            time.sleep(2)

        except Exception as e:
            print("Bot error:", e)
            time.sleep(5)

if __name__ == "__main__":
    run_bot()

import requests
import time

TOKEN = "8288769897:AAGoa0PFwm_Z4fFc4_ZMuKuAu_UPJymnY8E"
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

last_update_id = None

def send_message(chat_id, text):
    url = f"{BASE_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    r = requests.post(url, data=payload, timeout=10)
    print(r.status_code, r.text)

def get_updates(offset=None):
    url = f"{BASE_URL}/getUpdates"
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    r = requests.get(url, params=params, timeout=35)
    return r.json()

def handle_command(chat_id, text):
    if text == "/start":
        send_message(
            chat_id,
            "🤖 Heartbeat Command Center Live\n\n"
            "/heartbeat - send online ping\n"
            "/test - send test alert\n"
            "/status - bot status"
        )
    elif text == "/heartbeat":
        send_message(chat_id, "✅ AI SYSTEM ONLINE")
    elif text == "/test":
        send_message(chat_id, "🚨 TEST ALERT WORKING")
    elif text == "/status":
        send_message(chat_id, "📊 Bot is running and monitoring.")
    else:
        send_message(chat_id, "Unknown command. Try /start")

def run_bot():
    global last_update_id

    while True:
        try:
            data = get_updates(last_update_id)
            if data.get("ok") and data.get("result"):
                for update in data["result"]:
                    last_update_id = update["update_id"] + 1

                    message = update.get("message", {})
                    chat = message.get("chat", {})
                    text = message.get("text", "")

                    chat_id = chat.get("id")
                    if chat_id and text:
                        handle_command(chat_id, text)

            time.sleep(2)

        except Exception as e:
            print("Bot error:", e)
            time.sleep(5)

if __name__ == "__main__":
    run_bot()

import requests
import time

TOKEN = "8288769897:AAGoa0PFwm_Z4fFc4_ZMuKuAu_UPJymnY8E"
CHAT_ID = "8661143355"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:
        response = requests.post(url, data=payload, timeout=10)
        print(response.status_code)
        print(response.text)
    except Exception as e:
        print(f"Telegram error: {e}")

def heartbeat():
    send_telegram("✅ AI SYSTEM ONLINE")

def send_test_alert():
    send_telegram("🚨 TEST ALERT WORKING")

if __name__ == "__main__":
    heartbeat()
    send_test_alert()

send_telegram("🚨 TEST ALERT WORKING")

import requests
import time
import os

# =========================
# ENV VARIABLES (SET IN CLOUD)
# =========================
TOKEN = os.getenv("8288769897:AAGoa0PFwm_Z4fFc4_ZMuKuAu_UPJymnY8E")
CHAT_ID = os.getenv("8661143355")

# =========================
# TELEGRAM SEND FUNCTION
# =========================
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

# =========================
# HEARTBEAT (CONFIRMS BOT IS LIVE)
# =========================
def heartbeat():
    send_telegram("✅ AI SYSTEM ONLINE")

# =========================
# TEST ALERT FUNCTION
# =========================
def send_test_alert():
    send_telegram("🚨 TEST ALERT WORKING")

# =========================
# MAIN LOOP
# =========================
def run():
    heartbeat()

    while True:
        # 🔁 Replace this with your AI logic later
        send_telegram("📊 Monitoring markets...")

        time.sleep(300)  # runs every 5 minutes

# =========================
# ENTRY POINT
# =========================
if __name__ == "__main__":
    run()

log_trade_and_sync(
    ticker="QQQ",
    setup="BreakHoldHigh",
    grade="B+",
    entry=611.8,
    exit=612.5,
    result_pct=22,
    auto_sync=True
)

# ==========================================
# NEXT CELL: COMBINED LOGGER + GITHUB SYNC
# ==========================================

import os
import subprocess
import pandas as pd
from datetime import datetime
from getpass import getpass

CSV_FILE = "ai_trade_journal.csv"

# ---- GITHUB CONFIG ----
GITHUB_USERNAME = "JORDANSPECTER"      # change if needed
GITHUB_REPO = "ai-trading-report"      # change if needed
GIT_EMAIL = "jordnlbias@gmail.com"     # change if needed
GIT_NAME = "jordanspecter"             # change if needed


def _run_cmd(cmd, cwd=None):
    result = subprocess.run(cmd, cwd=cwd, shell=True, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr)
        raise RuntimeError(f"Command failed: {cmd}")
    return result.stdout


def _ensure_journal_exists():
    if not os.path.exists(CSV_FILE):
        df = pd.DataFrame(columns=[
            "date", "ticker", "setup", "grade",
            "entry", "exit", "result_pct"
        ])
        df.to_csv(CSV_FILE, index=False)


def sync_csv_to_github(csv_file=CSV_FILE):
    repo_name = GITHUB_REPO
    github_token = getpass("Enter GitHub token: ")

    if not os.path.exists(csv_file):
        raise FileNotFoundError(f"{csv_file} not found.")

    if os.path.exists(repo_name):
        _run_cmd(f'rm -rf "{repo_name}"')

    clone_url = f"https://{github_token}@github.com/{GITHUB_USERNAME}/{GITHUB_REPO}.git"
    print("Cloning from:")
    print(f"https://github.com/{GITHUB_USERNAME}/{GITHUB_REPO}.git")
    _run_cmd(f'git clone "{clone_url}"')

    print("Copying CSV...")
    _run_cmd(f'cp "{csv_file}" "{repo_name}/"')

    _run_cmd(f'git config user.email "{GIT_EMAIL}"', cwd=repo_name)
    _run_cmd(f'git config user.name "{GIT_NAME}"', cwd=repo_name)
    _run_cmd(f'git add "{csv_file}"', cwd=repo_name)

    status = subprocess.run('git status --porcelain', cwd=repo_name, shell=True, text=True, capture_output=True)
    if status.stdout.strip():
        _run_cmd('git commit -m "Update trade journal"', cwd=repo_name)
        _run_cmd('git push origin main', cwd=repo_name)
        print("✅ Sync complete")
    else:
        print("No changes to commit.")


def log_trade_and_sync(
    ticker,
    setup,
    grade,
    entry,
    exit,
    result_pct,
    auto_sync=True
):
    _ensure_journal_exists()

    df = pd.read_csv(CSV_FILE)

    new_trade = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "ticker": ticker,
        "setup": setup,
        "grade": grade,
        "entry": entry,
        "exit": exit,
        "result_pct": result_pct
    }

    df = pd.concat([df, pd.DataFrame([new_trade])], ignore_index=True)
    df.to_csv(CSV_FILE, index=False)

    print("✅ Trade logged")
    print(df.tail(3))

    if auto_sync:
        sync_csv_to_github(CSV_FILE)


# ==========================================
# EXAMPLE USAGE
# ==========================================
# log_trade_and_sync(
#     ticker="QQQ",
#     setup="BreakHoldHigh",
#     grade="B+",
#     entry=611.8,
#     exit=612.5,
#     result_pct=22,
#     auto_sync=True
# )

log_trade(
    ticker="QQQ",
    setup="BreakHoldHigh",
    grade="B+",
    entry=611.8,
    exit=612.5,
    result_pct=22
)

# ==========================================
# TRADE LOGGER (AUTO SAVE + AUTO PUSH)
# ==========================================

import pandas as pd
import os
from datetime import datetime

CSV_FILE = "ai_trade_journal.csv"

def log_trade(
    ticker,
    setup,
    grade,
    entry,
    exit,
    result_pct
):
    # create file if it doesn't exist
    if not os.path.exists(CSV_FILE):
        df = pd.DataFrame(columns=[
            "date", "ticker", "setup", "grade",
            "entry", "exit", "result_pct"
        ])
        df.to_csv(CSV_FILE, index=False)

    # load existing data
    df = pd.read_csv(CSV_FILE)

    # new row
    new_trade = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "ticker": ticker,
        "setup": setup,
        "grade": grade,
        "entry": entry,
        "exit": exit,
        "result_pct": result_pct
    }

    # append
    df = pd.concat([df, pd.DataFrame([new_trade])], ignore_index=True)

    # save
    df.to_csv(CSV_FILE, index=False)

    print("✅ Trade logged")
    print(df.tail(3))

log_trade(
    ticker="QQQ",
    setup="BreakHoldHigh",
    grade="B+",
    entry=611.8,
    exit=612.5,
    result_pct=+22
)

# ==========================================
# SYNC TRADE JOURNAL TO GITHUB
# ==========================================

import os

# ---- CONFIG ----
repo_url = "https://github.com/JORDANSPECTER/ai-trading-report.git"  # change this
repo_name = repo_url.split("/")[-1].replace(".git", "")
csv_file = "ai_trade_journal.csv"

# ---- AUTH ----
from getpass import getpass
github_token = getpass("Enter GitHub token: ")

# ---- CLEAN OLD REPO ----
if os.path.exists(repo_name):
    !rm -rf {repo_name}

# ---- CLONE REPO ----
print("Cloning repo...")
!git clone https://{github_token}@github.com/jordanspecter/{repo_name}.git

# ---- COPY CSV INTO REPO ----
print("Copying CSV...")
if not os.path.exists(csv_file):
    raise FileNotFoundError(f"{csv_file} not found. Create it first.")

!cp {csv_file} {repo_name}/

# ---- COMMIT + PUSH ----
print("Pushing to GitHub...")
%cd {repo_name}

!git config user.email "jordnlbias@gmail.com"
!git config user.name "jordanspecter"

!git add .
!git commit -m "Update trade journal"
!git push

print("✅ Sync complete")

import pandas as pd

df = pd.read_csv("ai_trade_journal.csv")

# Add a new row (test trade)
new_row = {
    "date": "2026-04-16",
    "ticker": "QQQ",
    "setup": "TEST",
    "result_pct": 99
}

df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

df.to_csv("ai_trade_journal.csv", index=False)

print("Added new test trade")

from getpass import getpass
github_token = getpass("Enter GitHub token: ")

# ==========================================
# EXPORT TRADE JOURNAL TO CSV
# ==========================================

csv_path = "/content/ai_trade_journal.csv"

# save your journal
saved_df = save_trade_journal_to_csv(
    memory=trade_journal_memory,
    csv_path=csv_path,
    dedupe=True
)

print("Saved to:", csv_path)

# =========================================================
# TEST CELL: SEND EMAIL TEST
# =========================================================

import smtplib
from email.mime.text import MIMEText

def send_test_email():
    try:
        subject = "✅ AI BOT EMAIL TEST SUCCESS"
        body = """
Your AI system is successfully connected.

This means:
- Email system is working
- Weekly reports will send
- Automation layer is ready

Next step: plug into trading reports
"""

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_CONFIG["sender_email"]
        msg["To"] = EMAIL_CONFIG["receiver_email"]

        with smtplib.SMTP(EMAIL_CONFIG["smtp_server"], EMAIL_CONFIG["smtp_port"]) as server:
            server.starttls()
            server.login(EMAIL_CONFIG["sender_email"], EMAIL_CONFIG["app_password"])
            server.send_message(msg)

        print("✅ EMAIL SENT SUCCESSFULLY — CHECK YOUR INBOX")

    except Exception as e:
        print("❌ EMAIL FAILED")
        print(str(e))


# Run test
send_test_email()

# =========================================================
# NEXT CELL: EMAIL CONFIG (WHO + HOW TO SEND)
# =========================================================

EMAIL_CONFIG = {
    "sender_email": "jordnlbias@gmail.com",       # <-- YOUR EMAIL
    "receiver_email": "unbiasedtrades313@gmail.com",     # <-- WHERE REPORT GOES
    "app_password": "rotj rpnu ixdf zbds",     # <-- NOT your real password
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
}

# =========================================================
# NEXT CELL: AUTO-SAVE TRADE JOURNAL TO CSV
# PURPOSE:
# - save every logged trade to CSV
# - avoid duplicates
# - keep one clean file for weekly email reports
# - create a simple wrapper so logging + saving happen together
# =========================================================

from __future__ import annotations
import os
import pandas as pd
from dataclasses import asdict


# =========================================================
# CONFIG
# =========================================================

JOURNAL_SAVE_CONFIG = {
    "journal_csv_path": "/content/ai_trade_journal.csv",
    "dedupe_on_fields": [
        "timestamp",
        "symbol",
        "direction",
        "setup_name",
        "entry_price_option",
        "exit_price_option",
        "contracts",
    ],
}


# =========================================================
# HELPERS
# =========================================================

def _memory_to_dataframe(memory: TradeJournalMemory) -> pd.DataFrame:
    if not memory.trades:
        return pd.DataFrame()
    return pd.DataFrame([asdict(t) for t in memory.trades])


def save_trade_journal_to_csv(
    memory: TradeJournalMemory,
    csv_path: str = None,
    dedupe: bool = True,
) -> pd.DataFrame:
    if csv_path is None:
        csv_path = JOURNAL_SAVE_CONFIG["journal_csv_path"]

    new_df = _memory_to_dataframe(memory)

    if new_df.empty:
        print("No trades in memory yet. Nothing saved.")
        return pd.DataFrame()

    # if file exists, merge with old data
    if os.path.exists(csv_path):
        old_df = pd.read_csv(csv_path)
        combined = pd.concat([old_df, new_df], ignore_index=True)
    else:
        combined = new_df.copy()

    # dedupe
    if dedupe:
        dedupe_fields = JOURNAL_SAVE_CONFIG["dedupe_on_fields"]
        existing_fields = [c for c in dedupe_fields if c in combined.columns]
        if existing_fields:
            combined = combined.drop_duplicates(subset=existing_fields, keep="last")

    # sort by timestamp if possible
    if "timestamp" in combined.columns:
        combined["timestamp"] = pd.to_datetime(combined["timestamp"], errors="coerce")
        combined = combined.sort_values("timestamp").reset_index(drop=True)
        combined["timestamp"] = combined["timestamp"].astype(str)

    combined.to_csv(csv_path, index=False)
    print(f"Trade journal saved to: {csv_path}")
    print(f"Rows saved: {len(combined)}")
    return combined


def append_logged_trade_to_csv(
    trade: LoggedTrade,
    csv_path: str = None,
) -> pd.DataFrame:
    if csv_path is None:
        csv_path = JOURNAL_SAVE_CONFIG["journal_csv_path"]

    row_df = pd.DataFrame([asdict(trade)])

    if os.path.exists(csv_path):
        old_df = pd.read_csv(csv_path)
        combined = pd.concat([old_df, row_df], ignore_index=True)
    else:
        combined = row_df.copy()

    dedupe_fields = JOURNAL_SAVE_CONFIG["dedupe_on_fields"]
    existing_fields = [c for c in dedupe_fields if c in combined.columns]
    if existing_fields:
        combined = combined.drop_duplicates(subset=existing_fields, keep="last")

    if "timestamp" in combined.columns:
        combined["timestamp"] = pd.to_datetime(combined["timestamp"], errors="coerce")
        combined = combined.sort_values("timestamp").reset_index(drop=True)
        combined["timestamp"] = combined["timestamp"].astype(str)

    combined.to_csv(csv_path, index=False)
    print(f"Trade appended and saved to: {csv_path}")
    print(f"Rows now in journal: {len(combined)}")
    return combined


# =========================================================
# LOG + SAVE WRAPPER
# Use this instead of log_ai_trade() when you want autosave
# =========================================================

def log_ai_trade_and_save(
    memory: TradeJournalMemory,
    symbol: str,
    direction: str,
    setup_name: str,
    grade: str,
    lesson_source: str,
    entry_price_underlying: float,
    exit_price_underlying: float,
    entry_price_option: float,
    exit_price_option: float,
    contracts: int,
    ai_confidence: float,
    setup_score: float,
    entry_quality_score: float,
    macro_alignment_score: float,
    allowed: bool,
    blocked: bool,
    size_fraction: float,
    chase_score: float,
    notes: Optional[List[str]] = None,
    stop_option_price: Optional[float] = None,
    csv_path: str = None,
) -> LoggedTrade:
    trade = log_ai_trade(
        memory=memory,
        symbol=symbol,
        direction=direction,
        setup_name=setup_name,
        grade=grade,
        lesson_source=lesson_source,
        entry_price_underlying=entry_price_underlying,
        exit_price_underlying=exit_price_underlying,
        entry_price_option=entry_price_option,
        exit_price_option=exit_price_option,
        contracts=contracts,
        ai_confidence=ai_confidence,
        setup_score=setup_score,
        entry_quality_score=entry_quality_score,
        macro_alignment_score=macro_alignment_score,
        allowed=allowed,
        blocked=blocked,
        size_fraction=size_fraction,
        chase_score=chase_score,
        notes=notes,
        stop_option_price=stop_option_price,
    )

    append_logged_trade_to_csv(trade, csv_path=csv_path)
    return trade


# =========================================================
# OPTIONAL: QUICK VIEW OF CURRENT CSV
# =========================================================

def load_saved_trade_journal(csv_path: str = None) -> pd.DataFrame:
    if csv_path is None:
        csv_path = JOURNAL_SAVE_CONFIG["journal_csv_path"]

    if not os.path.exists(csv_path):
        print("No saved journal file found yet.")
        return pd.DataFrame()

    df = pd.read_csv(csv_path)
    print(f"Loaded saved journal: {csv_path}")
    print(f"Rows: {len(df)}")
    return df


# =========================================================
# OPTIONAL: SAVE CURRENT IN-MEMORY JOURNAL RIGHT NOW
# =========================================================

saved_journal_df = save_trade_journal_to_csv(
    memory=trade_journal_memory,
    csv_path=JOURNAL_SAVE_CONFIG["journal_csv_path"],
    dedupe=True,
)

print()
print(saved_journal_df.tail(10).to_string(index=False) if not saved_journal_df.empty else "No data saved yet.")

# =========================================================
# WEEKLY EMAIL REPORTER FOR AI PROGRESSION
# PURPOSE:
# - read your trade journal CSV
# - build a weekly performance summary
# - send it to your email
#
# IMPORTANT:
# This works only when the script is actually run.
# For automatic weekly sending, schedule this script outside normal Colab runtime.
# =========================================================

import os
import math
import smtplib
import ssl
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pandas as pd


# =========================================================
# CONFIG
# =========================================================

EMAIL_CONFIG = {
    # Gmail sender account
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 465,

    # Put your sending Gmail here
    "sender_email": "your_email@gmail.com",

    # Put your Gmail App Password here
    # IMPORTANT: use an App Password, not your normal Gmail password
    "sender_app_password": "YOUR_APP_PASSWORD",

    # Where to send the report
    "recipient_email": "your_email@gmail.com",
}

REPORT_CONFIG = {
    # path to your saved journal CSV
    "journal_csv_path": "/content/ai_trade_journal.csv",

    # report window
    "days_back": 7,

    # title
    "report_title": "Weekly AI Progression Report",
}


# =========================================================
# HELPERS
# =========================================================

def safe_pct(numerator, denominator):
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 2)


def safe_mean(series):
    if len(series) == 0:
        return 0.0
    return round(float(series.mean()), 3)


def grade_rank(grade: str) -> int:
    mapping = {
        "A+": 5,
        "A": 4,
        "B+": 3,
        "B": 2,
        "C": 1,
        "WAIT": 1,
        "AVOID": 0,
    }
    return mapping.get(str(grade), 0)


# =========================================================
# LOAD JOURNAL
# Expected columns:
# timestamp, symbol, direction, setup_name, grade, lesson_source,
# ai_confidence, setup_score, entry_quality_score, macro_alignment_score,
# allowed, blocked, size_fraction, chase_score,
# pnl_dollars, pnl_pct, r_multiple, win
# =========================================================

def load_journal(csv_path: str) -> pd.DataFrame:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Journal CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    if "timestamp" not in df.columns:
        raise ValueError("Journal CSV must contain a 'timestamp' column.")

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).copy()

    # normalize expected columns if missing
    expected_defaults = {
        "symbol": "",
        "direction": "",
        "setup_name": "",
        "grade": "AVOID",
        "lesson_source": "",
        "ai_confidence": 0.0,
        "setup_score": 0.0,
        "entry_quality_score": 0.0,
        "macro_alignment_score": 0.0,
        "allowed": False,
        "blocked": False,
        "size_fraction": 0.0,
        "chase_score": 0.0,
        "pnl_dollars": 0.0,
        "pnl_pct": 0.0,
        "r_multiple": 0.0,
        "win": False,
    }

    for col, default in expected_defaults.items():
        if col not in df.columns:
            df[col] = default

    df["grade_rank"] = df["grade"].apply(grade_rank)
    return df.sort_values("timestamp").reset_index(drop=True)


# =========================================================
# REPORT BUILDERS
# =========================================================

def filter_last_n_days(df: pd.DataFrame, days_back: int) -> pd.DataFrame:
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=days_back)
    return df[df["timestamp"] >= cutoff].copy()


def build_overall_stats(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "avg_pnl": 0.0,
            "avg_pct": 0.0,
            "avg_r": 0.0,
            "blocked_rate": 0.0,
            "avg_confidence": 0.0,
            "avg_chase_score": 0.0,
        }

    trades = len(df)
    wins = int(df["win"].sum())

    return {
        "trades": trades,
        "win_rate": safe_pct(wins, trades),
        "total_pnl": round(float(df["pnl_dollars"].sum()), 2),
        "avg_pnl": round(float(df["pnl_dollars"].mean()), 2),
        "avg_pct": round(float(df["pnl_pct"].mean()), 2),
        "avg_r": round(float(df["r_multiple"].mean()), 3),
        "blocked_rate": round(float(df["blocked"].mean()) * 100.0, 2),
        "avg_confidence": round(float(df["ai_confidence"].mean()), 3),
        "avg_chase_score": round(float(df["chase_score"].mean()), 3),
    }


def build_group_summary(df: pd.DataFrame, group_col: str, top_n: int = 5) -> pd.DataFrame:
    if df.empty or group_col not in df.columns:
        return pd.DataFrame()

    out = (
        df.groupby(group_col)
        .agg(
            trades=("win", "count"),
            win_rate_pct=("win", lambda x: round(float(x.mean()) * 100.0, 2)),
            total_pnl=("pnl_dollars", lambda x: round(float(x.sum()), 2)),
            avg_pnl=("pnl_dollars", lambda x: round(float(x.mean()), 2)),
            avg_r=("r_multiple", lambda x: round(float(x.mean()), 3)),
            avg_conf=("ai_confidence", lambda x: round(float(x.mean()), 3)),
            avg_chase=("chase_score", lambda x: round(float(x.mean()), 3)),
        )
        .sort_values(["avg_r", "total_pnl"], ascending=False)
        .head(top_n)
        .reset_index()
    )
    return out


def compare_high_vs_low_confidence(df: pd.DataFrame, threshold: float = 0.75) -> dict:
    if df.empty:
        return {
            "high_conf_avg_r": 0.0,
            "low_conf_avg_r": 0.0,
            "high_conf_win_rate": 0.0,
            "low_conf_win_rate": 0.0,
        }

    high = df[df["ai_confidence"] >= threshold]
    low = df[df["ai_confidence"] < threshold]

    return {
        "high_conf_avg_r": safe_mean(high["r_multiple"]) if not high.empty else 0.0,
        "low_conf_avg_r": safe_mean(low["r_multiple"]) if not low.empty else 0.0,
        "high_conf_win_rate": round(float(high["win"].mean()) * 100.0, 2) if not high.empty else 0.0,
        "low_conf_win_rate": round(float(low["win"].mean()) * 100.0, 2) if not low.empty else 0.0,
    }


def build_weekly_report_text(df_all: pd.DataFrame, df_week: pd.DataFrame) -> str:
    overall_all = build_overall_stats(df_all)
    overall_week = build_overall_stats(df_week)

    by_grade = build_group_summary(df_week, "grade", top_n=10)
    by_lesson = build_group_summary(df_week, "lesson_source", top_n=10)
    by_setup = build_group_summary(df_week, "setup_name", top_n=10)
    by_symbol = build_group_summary(df_week, "symbol", top_n=10)

    conf_compare = compare_high_vs_low_confidence(df_week)

    lines = []
    lines.append(REPORT_CONFIG["report_title"])
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    lines.append("WEEKLY SNAPSHOT")
    lines.append(f"Trades: {overall_week['trades']}")
    lines.append(f"Win Rate: {overall_week['win_rate']}%")
    lines.append(f"Total PnL: ${overall_week['total_pnl']}")
    lines.append(f"Average PnL: ${overall_week['avg_pnl']}")
    lines.append(f"Average Return: {overall_week['avg_pct']}%")
    lines.append(f"Average R: {overall_week['avg_r']}")
    lines.append(f"Blocked Rate: {overall_week['blocked_rate']}%")
    lines.append(f"Average AI Confidence: {overall_week['avg_confidence']}")
    lines.append(f"Average Chase Score: {overall_week['avg_chase_score']}")
    lines.append("")

    lines.append("ALL-TIME SNAPSHOT")
    lines.append(f"Trades: {overall_all['trades']}")
    lines.append(f"Win Rate: {overall_all['win_rate']}%")
    lines.append(f"Total PnL: ${overall_all['total_pnl']}")
    lines.append(f"Average R: {overall_all['avg_r']}")
    lines.append("")

    lines.append("AI STRENGTH CHECK")
    lines.append(f"High-confidence avg R: {conf_compare['high_conf_avg_r']}")
    lines.append(f"Low-confidence avg R: {conf_compare['low_conf_avg_r']}")
    lines.append(f"High-confidence win rate: {conf_compare['high_conf_win_rate']}%")
    lines.append(f"Low-confidence win rate: {conf_compare['low_conf_win_rate']}%")
    lines.append("")

    def add_table_section(title: str, table: pd.DataFrame):
        lines.append(title)
        if table.empty:
            lines.append("No data")
        else:
            lines.append(table.to_string(index=False))
        lines.append("")

    add_table_section("PERFORMANCE BY GRADE", by_grade)
    add_table_section("PERFORMANCE BY LESSON SOURCE", by_lesson)
    add_table_section("PERFORMANCE BY SETUP", by_setup)
    add_table_section("PERFORMANCE BY SYMBOL", by_symbol)

    if not df_week.empty:
        worst_chase = df_week.sort_values("chase_score", ascending=False).head(5)[
            ["timestamp", "symbol", "setup_name", "grade", "chase_score", "pnl_dollars", "r_multiple"]
        ]
        add_table_section("HIGHEST-CHASE TRADES THIS WEEK", worst_chase)

        best_trades = df_week.sort_values("r_multiple", ascending=False).head(5)[
            ["timestamp", "symbol", "setup_name", "grade", "pnl_dollars", "r_multiple", "lesson_source"]
        ]
        add_table_section("BEST TRADES THIS WEEK", best_trades)

        worst_trades = df_week.sort_values("r_multiple", ascending=True).head(5)[
            ["timestamp", "symbol", "setup_name", "grade", "pnl_dollars", "r_multiple", "lesson_source"]
        ]
        add_table_section("WORST TRADES THIS WEEK", worst_trades)

    lines.append("KEY QUESTION")
    lines.append("Is the AI actually getting stronger?")
    lines.append(
        "A strong sign is when high-confidence trades outperform low-confidence trades, "
        "higher grades outperform lower grades, and high-chase trades underperform."
    )

    return "\n".join(lines)


# =========================================================
# EMAIL SENDER
# =========================================================

def send_weekly_email_report(subject: str, body: str, email_config: dict):
    sender_email = email_config["sender_email"]
    sender_password = email_config["sender_app_password"]
    recipient_email = email_config["recipient_email"]
    smtp_server = email_config["smtp_server"]
    smtp_port = email_config["smtp_port"]

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = recipient_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient_email, msg.as_string())


# =========================================================
# MASTER RUNNER
# =========================================================

def run_and_email_weekly_ai_report():
    df_all = load_journal(REPORT_CONFIG["journal_csv_path"])
    df_week = filter_last_n_days(df_all, REPORT_CONFIG["days_back"])

    report_text = build_weekly_report_text(df_all, df_week)
    subject = f"{REPORT_CONFIG['report_title']} — {datetime.now().strftime('%Y-%m-%d')}"

    send_weekly_email_report(
        subject=subject,
        body=report_text,
        email_config=EMAIL_CONFIG,
    )

    print("Weekly AI progression report sent successfully.")
    print()
    print(report_text[:4000])  # preview


# =========================================================
# OPTIONAL: SAVE CURRENT JOURNAL MEMORY TO CSV
# If you already use trade_journal_memory from prior cells
# =========================================================

def save_trade_journal_memory_to_csv(memory, csv_path):
    rows = []
    for trade in memory.trades:
        rows.append(asdict(trade))
    df = pd.DataFrame(rows)
    df.to_csv(csv_path, index=False)
    print(f"Saved journal to {csv_path}")


# =========================================================
# USAGE
# =========================================================

# If you want to save your in-memory journal first:
# save_trade_journal_memory_to_csv(trade_journal_memory, REPORT_CONFIG["journal_csv_path"])

# Then send the report:
# run_and_email_weekly_ai_report()

# =========================================================
# NEXT CELL: TRADE JOURNAL + PERFORMANCE FEEDBACK LOOP
# PURPOSE:
# Prove whether the AI is actually improving.
#
# THIS CELL:
# - logs trades
# - stores setup / grade / lesson source / outcome
# - measures win rate, expectancy, average return
# - shows which lessons are helping
# - shows where chasing is hurting
# =========================================================

from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np
import json
from datetime import datetime


# =========================================================
# MEMORY STORE
# =========================================================

@dataclass
class LoggedTrade:
    timestamp: str
    symbol: str
    direction: str                  # CALL / PUT
    setup_name: str
    grade: str                      # A+ / A / B+ / B / AVOID
    lesson_source: str              # e.g. PREMARKET, 62750, RANGE_PRINT, LATE_EXPANSION, OVERNIGHT_OIL
    entry_price_underlying: float
    exit_price_underlying: float
    entry_price_option: float
    exit_price_option: float
    contracts: int

    ai_confidence: float
    setup_score: float
    entry_quality_score: float
    macro_alignment_score: float

    allowed: bool
    blocked: bool
    size_fraction: float
    chase_score: float

    pnl_dollars: float
    pnl_pct: float
    r_multiple: float

    win: bool
    notes: List[str] = field(default_factory=list)


@dataclass
class TradeJournalMemory:
    trades: List[LoggedTrade] = field(default_factory=list)


# =========================================================
# GLOBAL MEMORY OBJECT
# If already exists, keep it
# =========================================================

if "trade_journal_memory" not in globals():
    trade_journal_memory = TradeJournalMemory()


# =========================================================
# HELPERS
# =========================================================

def safe_float(x, default=0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except:
        return default


def grade_rank(grade: str) -> int:
    mapping = {
        "A+": 5,
        "A": 4,
        "B+": 3,
        "B": 2,
        "AVOID": 0,
        "C": 1,
        "WAIT": 1,
    }
    return mapping.get(grade, 0)


def compute_option_pnl(entry_option_price: float, exit_option_price: float, contracts: int) -> float:
    return round((exit_option_price - entry_option_price) * 100 * contracts, 2)


def compute_option_return_pct(entry_option_price: float, exit_option_price: float) -> float:
    if entry_option_price <= 0:
        return 0.0
    return round(((exit_option_price / entry_option_price) - 1.0) * 100.0, 2)


def compute_r_multiple(entry_option_price: float, exit_option_price: float, stop_option_price: Optional[float] = None) -> float:
    """
    If stop_option_price is provided, use it for true R.
    Otherwise assume 35% premium risk as fallback.
    """
    if entry_option_price <= 0:
        return 0.0

    if stop_option_price is None:
        assumed_risk = entry_option_price * 0.35
    else:
        assumed_risk = max(0.01, abs(entry_option_price - stop_option_price))

    reward = exit_option_price - entry_option_price
    return round(reward / assumed_risk, 3)


# =========================================================
# LOG TRADE
# =========================================================

def log_ai_trade(
    memory: TradeJournalMemory,
    symbol: str,
    direction: str,
    setup_name: str,
    grade: str,
    lesson_source: str,
    entry_price_underlying: float,
    exit_price_underlying: float,
    entry_price_option: float,
    exit_price_option: float,
    contracts: int,
    ai_confidence: float,
    setup_score: float,
    entry_quality_score: float,
    macro_alignment_score: float,
    allowed: bool,
    blocked: bool,
    size_fraction: float,
    chase_score: float,
    notes: Optional[List[str]] = None,
    stop_option_price: Optional[float] = None,
) -> LoggedTrade:
    if notes is None:
        notes = []

    pnl_dollars = compute_option_pnl(entry_price_option, exit_price_option, contracts)
    pnl_pct = compute_option_return_pct(entry_price_option, exit_price_option)
    r_multiple = compute_r_multiple(entry_price_option, exit_price_option, stop_option_price=stop_option_price)

    trade = LoggedTrade(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        symbol=symbol,
        direction=direction,
        setup_name=setup_name,
        grade=grade,
        lesson_source=lesson_source,
        entry_price_underlying=safe_float(entry_price_underlying),
        exit_price_underlying=safe_float(exit_price_underlying),
        entry_price_option=safe_float(entry_price_option),
        exit_price_option=safe_float(exit_price_option),
        contracts=int(contracts),

        ai_confidence=round(safe_float(ai_confidence), 3),
        setup_score=round(safe_float(setup_score), 3),
        entry_quality_score=round(safe_float(entry_quality_score), 3),
        macro_alignment_score=round(safe_float(macro_alignment_score), 3),

        allowed=bool(allowed),
        blocked=bool(blocked),
        size_fraction=round(safe_float(size_fraction), 3),
        chase_score=round(safe_float(chase_score), 3),

        pnl_dollars=pnl_dollars,
        pnl_pct=pnl_pct,
        r_multiple=r_multiple,
        win=(pnl_dollars > 0),
        notes=notes,
    )

    memory.trades.append(trade)
    return trade


# =========================================================
# DATAFRAME VIEW
# =========================================================

def trade_journal_to_dataframe(memory: TradeJournalMemory) -> pd.DataFrame:
    if not memory.trades:
        return pd.DataFrame()

    df = pd.DataFrame([asdict(t) for t in memory.trades])
    df["grade_rank"] = df["grade"].apply(grade_rank)
    df["lesson_source"] = df["lesson_source"].astype(str)
    df["symbol"] = df["symbol"].astype(str)
    df["direction"] = df["direction"].astype(str)
    return df


# =========================================================
# PERFORMANCE REPORTS
# =========================================================

def build_overall_performance_report(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {"message": "No trades logged yet."}

    total_trades = len(df)
    win_rate = float((df["win"].mean()) * 100.0)
    avg_pnl = float(df["pnl_dollars"].mean())
    avg_pct = float(df["pnl_pct"].mean())
    avg_r = float(df["r_multiple"].mean())
    total_pnl = float(df["pnl_dollars"].sum())
    blocked_rate = float(df["blocked"].mean() * 100.0)

    return {
        "total_trades": total_trades,
        "win_rate_pct": round(win_rate, 2),
        "avg_pnl_dollars": round(avg_pnl, 2),
        "avg_return_pct": round(avg_pct, 2),
        "avg_r_multiple": round(avg_r, 3),
        "total_pnl_dollars": round(total_pnl, 2),
        "blocked_rate_pct": round(blocked_rate, 2),
    }


def build_group_report(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    if df.empty or group_col not in df.columns:
        return pd.DataFrame()

    out = (
        df.groupby(group_col)
        .agg(
            trades=("win", "count"),
            win_rate_pct=("win", lambda x: round(x.mean() * 100.0, 2)),
            avg_pnl_dollars=("pnl_dollars", lambda x: round(x.mean(), 2)),
            total_pnl_dollars=("pnl_dollars", lambda x: round(x.sum(), 2)),
            avg_return_pct=("pnl_pct", lambda x: round(x.mean(), 2)),
            avg_r_multiple=("r_multiple", lambda x: round(x.mean(), 3)),
            avg_confidence=("ai_confidence", lambda x: round(x.mean(), 3)),
            avg_setup_score=("setup_score", lambda x: round(x.mean(), 3)),
            avg_entry_quality=("entry_quality_score", lambda x: round(x.mean(), 3)),
            avg_chase_score=("chase_score", lambda x: round(x.mean(), 3)),
        )
        .sort_values(by="avg_r_multiple", ascending=False)
        .reset_index()
    )
    return out


def build_chasing_damage_report(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    temp = df.copy()

    def bucket(x):
        if x >= 7:
            return "extreme"
        if x >= 5:
            return "high"
        if x >= 3:
            return "moderate"
        if x >= 1:
            return "mild"
        return "low"

    temp["chase_bucket"] = temp["chase_score"].apply(bucket)

    out = (
        temp.groupby("chase_bucket")
        .agg(
            trades=("win", "count"),
            win_rate_pct=("win", lambda x: round(x.mean() * 100.0, 2)),
            avg_pnl_dollars=("pnl_dollars", lambda x: round(x.mean(), 2)),
            avg_return_pct=("pnl_pct", lambda x: round(x.mean(), 2)),
            avg_r_multiple=("r_multiple", lambda x: round(x.mean(), 3)),
        )
        .reset_index()
    )

    bucket_order = ["low", "mild", "moderate", "high", "extreme"]
    out["order"] = out["chase_bucket"].apply(lambda x: bucket_order.index(x))
    out = out.sort_values("order").drop(columns=["order"]).reset_index(drop=True)
    return out


def build_ai_strength_report(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {"message": "No trades logged yet."}

    high_conf = df[df["ai_confidence"] >= 0.75]
    low_conf = df[df["ai_confidence"] < 0.75]

    high_conf_r = float(high_conf["r_multiple"].mean()) if not high_conf.empty else 0.0
    low_conf_r = float(low_conf["r_multiple"].mean()) if not low_conf.empty else 0.0

    top_grade = build_group_report(df, "grade")
    top_lesson = build_group_report(df, "lesson_source")
    top_setup = build_group_report(df, "setup_name")

    return {
        "high_confidence_avg_r": round(high_conf_r, 3),
        "low_confidence_avg_r": round(low_conf_r, 3),
        "confidence_is_helping": high_conf_r > low_conf_r,
        "best_grade_rows": top_grade.head(3).to_dict(orient="records") if not top_grade.empty else [],
        "best_lesson_source_rows": top_lesson.head(5).to_dict(orient="records") if not top_lesson.empty else [],
        "best_setup_rows": top_setup.head(5).to_dict(orient="records") if not top_setup.empty else [],
    }


# =========================================================
# JOURNAL SUMMARY FORMATTER
# =========================================================

def format_trade_journal_summary(memory: TradeJournalMemory) -> str:
    df = trade_journal_to_dataframe(memory)
    overall = build_overall_performance_report(df)

    lines = ["AI TRADE JOURNAL SUMMARY"]

    if "message" in overall:
        lines.append(overall["message"])
        return "\n".join(lines)

    lines.extend([
        f"Total Trades: {overall['total_trades']}",
        f"Win Rate: {overall['win_rate_pct']}%",
        f"Average PnL: ${overall['avg_pnl_dollars']}",
        f"Average Return: {overall['avg_return_pct']}%",
        f"Average R: {overall['avg_r_multiple']}",
        f"Total PnL: ${overall['total_pnl_dollars']}",
        f"Blocked Rate: {overall['blocked_rate_pct']}%",
    ])

    return "\n".join(lines)


# =========================================================
# MASTER FEEDBACK RUNNER
# =========================================================

def run_ai_feedback_loop(memory: TradeJournalMemory) -> Dict[str, Any]:
    df = trade_journal_to_dataframe(memory)

    return {
        "trades_df": df,
        "overall_report": build_overall_performance_report(df),
        "grade_report": build_group_report(df, "grade"),
        "lesson_source_report": build_group_report(df, "lesson_source"),
        "setup_report": build_group_report(df, "setup_name"),
        "symbol_report": build_group_report(df, "symbol"),
        "direction_report": build_group_report(df, "direction"),
        "chasing_report": build_chasing_damage_report(df),
        "ai_strength_report": build_ai_strength_report(df),
    }


# =========================================================
# EXAMPLE LOGS
# Replace these with your real trades over time
# =========================================================

if len(trade_journal_memory.trades) == 0:
    log_ai_trade(
        memory=trade_journal_memory,
        symbol="QQQ",
        direction="CALL",
        setup_name="627.50 Hold + VWAP Confirmation",
        grade="A+",
        lesson_source="62750_TRIGGER",
        entry_price_underlying=627.56,
        exit_price_underlying=629.20,
        entry_price_option=1.25,
        exit_price_option=2.80,
        contracts=2,
        ai_confidence=0.91,
        setup_score=0.89,
        entry_quality_score=0.86,
        macro_alignment_score=0.62,
        allowed=True,
        blocked=False,
        size_fraction=1.0,
        chase_score=1,
        notes=["Clean hold at trigger", "VWAP aligned"],
    )

    log_ai_trade(
        memory=trade_journal_memory,
        symbol="QQQ",
        direction="CALL",
        setup_name="Trend Continuation — Late Expansion Entry",
        grade="B",
        lesson_source="LATE_EXPANSION_0DTE",
        entry_price_underlying=626.80,
        exit_price_underlying=626.10,
        entry_price_option=2.05,
        exit_price_option=1.20,
        contracts=1,
        ai_confidence=0.57,
        setup_score=0.58,
        entry_quality_score=0.34,
        macro_alignment_score=0.50,
        allowed=True,
        blocked=False,
        size_fraction=0.5,
        chase_score=6,
        notes=["Late entry", "RSI 80+", "Upper band tag"],
    )

    log_ai_trade(
        memory=trade_journal_memory,
        symbol="QQQ",
        direction="CALL",
        setup_name="Late-Day Bullish Continuation + Oil Relief Overnight Hold",
        grade="A",
        lesson_source="OVERNIGHT_OIL_RELIEF",
        entry_price_underlying=615.40,
        exit_price_underlying=621.00,
        entry_price_option=2.05,
        exit_price_option=5.80,
        contracts=1,
        ai_confidence=0.84,
        setup_score=0.81,
        entry_quality_score=0.77,
        macro_alignment_score=0.88,
        allowed=True,
        blocked=False,
        size_fraction=0.75,
        chase_score=1,
        notes=["Oil rolling over", "Accepted above 613.75 print", "Strong close"],
    )


# =========================================================
# RUN FEEDBACK LOOP
# =========================================================

feedback_results = run_ai_feedback_loop(trade_journal_memory)

print("=== OVERALL REPORT ===")
print(json.dumps(feedback_results["overall_report"], indent=2))

print("\n=== AI STRENGTH REPORT ===")
print(json.dumps(feedback_results["ai_strength_report"], indent=2))

print("\n=== SUMMARY ===")
print(format_trade_journal_summary(trade_journal_memory))

print("\n=== GRADE REPORT ===")
print(feedback_results["grade_report"].to_string(index=False) if not feedback_results["grade_report"].empty else "No data")

print("\n=== LESSON SOURCE REPORT ===")
print(feedback_results["lesson_source_report"].to_string(index=False) if not feedback_results["lesson_source_report"].empty else "No data")

print("\n=== CHASING DAMAGE REPORT ===")
print(feedback_results["chasing_report"].to_string(index=False) if not feedback_results["chasing_report"].empty else "No data")

print("\n=== RAW TRADE LOG ===")
print(feedback_results["trades_df"].tail(20).to_string(index=False) if not feedback_results["trades_df"].empty else "No data")

# =========================================================
# AI LEARNING CODE: QQQ OVERNIGHT CONTINUATION CALL
# INSTITUTIONAL SUPPORT + OIL RELIEF + STRONG CLOSE
# ONE-CELL VERSION
# =========================================================
# PURPOSE:
# Teach the AI why a next-day QQQ call bought before close
# can be high quality when:
# - QQQ accepts above key institutional support
# - the close is strong
# - oil is rolling over and removing macro pressure
# - the contract has real asymmetry into the next session
#
# CORE LESSON:
# This was not a random overnight gamble.
# This was a structured continuation hold with macro alignment.
# =========================================================

from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any
import json


# =========================================================
# DATA MODELS
# =========================================================

@dataclass
class OvernightCallContext:
    symbol: str
    underlying_price: float
    option_symbol: str
    strike: float
    avg_cost: float
    expiration_next_day: bool

    # institutional / dark pool levels
    major_print_level: float = 613.75
    nearby_supports: List[float] = field(default_factory=list)
    nearby_resistances: List[float] = field(default_factory=list)
    accepted_above_major_print: bool = False
    holding_above_major_print: bool = False

    # structure into the close
    strong_close: bool = False
    close_near_highs: bool = False
    higher_lows_into_close: bool = False
    break_and_hold_structure: bool = False
    no_late_day_breakdown: bool = False
    momentum_intact_into_close: bool = False

    # macro / oil context
    oil_price: float = 0.0
    oil_pct_change: float = 0.0
    oil_rolling_over: bool = False
    oil_failed_bounce: bool = False
    oil_macro_pressure_fading: bool = False

    # regime
    trend_day_or_continuation_regime: bool = False
    chop_regime: bool = False
    failed_breakout_regime: bool = False

    # contract logic
    breakeven: float = 0.0
    contract_near_itm: bool = False
    good_gamma_potential: bool = False
    upside_asymmetry_present: bool = False

    # risk flags
    overnight_gap_risk: bool = True
    headline_risk: bool = True
    theta_risk: bool = True
    possible_gap_and_fade: bool = True


@dataclass
class OvernightCallDecision:
    setup_name: str
    setup_grade: str                  # A+ / A / B+ / B / AVOID
    setup_bias: str                   # BULLISH / BEARISH / NEUTRAL
    hold_type: str                    # STRUCTURED_OVERNIGHT / SPECULATIVE_OVERNIGHT / AVOID
    confidence_score: float
    institutional_alignment: bool
    macro_alignment: bool
    structure_alignment: bool
    asymmetry_alignment: bool
    reasons: List[str]
    risks: List[str]
    lesson_label: str
    dataset_summary: str


# =========================================================
# HELPERS
# =========================================================

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def above_level(price: float, level: float, tol: float = 0.0) -> bool:
    return price >= (level + tol)


def near_itm(underlying_price: float, strike: float, buffer: float = 3.0) -> bool:
    return abs(underlying_price - strike) <= buffer or underlying_price > strike


# =========================================================
# OIL / MACRO CLASSIFICATION
# =========================================================

def classify_oil_setup(ctx: OvernightCallContext) -> str:
    if ctx.oil_rolling_over and ctx.oil_failed_bounce and ctx.oil_pct_change < 0:
        return "FAILED_BOUNCE_BEARISH_CONTINUATION"
    if ctx.oil_rolling_over and ctx.oil_pct_change < 0:
        return "BEARISH_ROLLOVER"
    if ctx.oil_pct_change < 0:
        return "OIL_RELIEF"
    return "NEUTRAL"


# =========================================================
# SCORING ENGINE
# =========================================================

def grade_overnight_continuation_call(ctx: OvernightCallContext) -> str:
    score = 0

    # institutional support / acceptance
    if ctx.accepted_above_major_print:
        score += 3
    if ctx.holding_above_major_print:
        score += 2
    if len(ctx.nearby_supports) >= 2:
        score += 1

    # structure
    if ctx.strong_close:
        score += 2
    if ctx.close_near_highs:
        score += 1
    if ctx.higher_lows_into_close:
        score += 1
    if ctx.break_and_hold_structure:
        score += 2
    if ctx.no_late_day_breakdown:
        score += 1
    if ctx.momentum_intact_into_close:
        score += 1

    # macro / oil
    if ctx.oil_macro_pressure_fading:
        score += 2
    if ctx.oil_rolling_over:
        score += 1
    if ctx.oil_failed_bounce:
        score += 1
    if ctx.oil_pct_change <= -2.0:
        score += 1

    # regime
    if ctx.trend_day_or_continuation_regime:
        score += 2
    if ctx.chop_regime:
        score -= 2
    if ctx.failed_breakout_regime:
        score -= 3

    # contract logic / asymmetry
    if ctx.contract_near_itm:
        score += 1
    if ctx.good_gamma_potential:
        score += 1
    if ctx.upside_asymmetry_present:
        score += 2
    if ctx.underlying_price > ctx.breakeven:
        score += 1

    # risk penalties
    if ctx.expiration_next_day:
        score -= 1
    if ctx.overnight_gap_risk:
        score -= 1
    if ctx.headline_risk:
        score -= 1
    if ctx.theta_risk:
        score -= 1
    if ctx.possible_gap_and_fade:
        score -= 1

    if score >= 16:
        return "A+"
    if score >= 13:
        return "A"
    if score >= 10:
        return "B+"
    if score >= 7:
        return "B"
    return "AVOID"


# =========================================================
# MAIN LEARNING DECISION
# =========================================================

def evaluate_overnight_qqq_call(ctx: OvernightCallContext) -> OvernightCallDecision:
    reasons: List[str] = []
    risks: List[str] = []

    institutional_alignment = False
    macro_alignment = False
    structure_alignment = False
    asymmetry_alignment = False

    # institutional
    if ctx.accepted_above_major_print:
        institutional_alignment = True
        reasons.append(f"Price accepted above the major institutional print at {ctx.major_print_level:.2f}.")
    if ctx.holding_above_major_print:
        reasons.append("Price held above the major print into the close.")
    if len(ctx.nearby_supports) >= 2:
        reasons.append("Nearby dark pool support stack underneath strengthens the hold thesis.")

    # structure
    if ctx.strong_close:
        structure_alignment = True
        reasons.append("The close was strong, not weak.")
    if ctx.close_near_highs:
        reasons.append("Price closed near session highs.")
    if ctx.higher_lows_into_close:
        reasons.append("Higher lows into the close supported continuation.")
    if ctx.break_and_hold_structure:
        reasons.append("The setup was break-and-hold continuation, not bottom picking.")
    if ctx.no_late_day_breakdown:
        reasons.append("There was no aggressive late-day breakdown.")
    if ctx.momentum_intact_into_close:
        reasons.append("Momentum stayed intact into the close.")

    # macro / oil
    oil_setup = classify_oil_setup(ctx)
    if ctx.oil_macro_pressure_fading:
        macro_alignment = True
        reasons.append("Oil pressure was fading, supporting equities.")
    if ctx.oil_rolling_over:
        reasons.append("Oil was rolling over instead of squeezing higher.")
    if ctx.oil_failed_bounce:
        reasons.append("Oil showed failed-bounce behavior, which reduced macro stress on QQQ.")
    reasons.append(f"Oil setup label: {oil_setup}.")

    # regime
    if ctx.trend_day_or_continuation_regime:
        reasons.append("Market regime favored continuation over mean reversion.")
    if ctx.chop_regime:
        risks.append("Chop regime would weaken overnight continuation odds.")
    if ctx.failed_breakout_regime:
        risks.append("A failed-breakout regime would strongly reduce hold quality.")

    # asymmetry / contract logic
    if ctx.contract_near_itm:
        asymmetry_alignment = True
        reasons.append("The contract was near ITM / becoming ITM, which improved realism of the hold.")
    if ctx.good_gamma_potential:
        reasons.append("Next-session gamma potential was attractive if QQQ opened strong.")
    if ctx.upside_asymmetry_present:
        reasons.append("Upside asymmetry was present if continuation persisted.")
    if ctx.underlying_price > ctx.breakeven:
        reasons.append("Underlying price had a realistic path above breakeven.")

    # risks
    if ctx.expiration_next_day:
        risks.append("Next-day expiration added time-decay risk.")
    if ctx.overnight_gap_risk:
        risks.append("Overnight hold carried gap risk.")
    if ctx.headline_risk:
        risks.append("Headline risk remained possible overnight.")
    if ctx.theta_risk:
        risks.append("Theta remained a real risk into next session.")
    if ctx.possible_gap_and_fade:
        risks.append("Morning gap-and-fade could still hurt the position.")

    setup_grade = grade_overnight_continuation_call(ctx)
    setup_bias = "BULLISH"
    hold_type = "STRUCTURED_OVERNIGHT" if setup_grade in {"A+", "A", "B+"} else "SPECULATIVE_OVERNIGHT"

    confidence = 0.50
    if setup_grade == "A+":
        confidence = 0.93
    elif setup_grade == "A":
        confidence = 0.84
    elif setup_grade == "B+":
        confidence = 0.72
    elif setup_grade == "B":
        confidence = 0.60
    elif setup_grade == "AVOID":
        confidence = 0.18

    if institutional_alignment:
        confidence += 0.03
    if structure_alignment:
        confidence += 0.03
    if macro_alignment:
        confidence += 0.03
    if asymmetry_alignment:
        confidence += 0.03

    if ctx.expiration_next_day:
        confidence -= 0.04
    if ctx.overnight_gap_risk:
        confidence -= 0.03
    if ctx.theta_risk:
        confidence -= 0.02

    confidence = clamp(confidence, 0.0, 1.0)

    dataset_summary = (
        "This QQQ overnight 615 call was a structured bullish continuation hold because price had already "
        "accepted above the major institutional print near 613.75, held above nearby support zones, and "
        "closed with strong structure rather than late-day breakdown. At the same time, oil was rolling over "
        "and failing to bounce, which reduced macro pressure on tech and supported continuation. The hold "
        "therefore had institutional alignment, bullish closing structure, macro relief, and next-day upside "
        "asymmetry. It was not risk-free because next-day expiration, overnight gap risk, headline risk, and "
        "theta still mattered, but it was a high-quality overnight momentum hold rather than a random 0DTE gamble."
    )

    return OvernightCallDecision(
        setup_name="Late-Day Bullish Continuation + Oil Relief Overnight Hold",
        setup_grade=setup_grade,
        setup_bias=setup_bias,
        hold_type=hold_type,
        confidence_score=round(confidence, 3),
        institutional_alignment=institutional_alignment,
        macro_alignment=macro_alignment,
        structure_alignment=structure_alignment,
        asymmetry_alignment=asymmetry_alignment,
        reasons=reasons,
        risks=risks,
        lesson_label="OVERNIGHT_QQQ_CALL_INSTITUTIONAL_MACRO_ALIGNMENT",
        dataset_summary=dataset_summary,
    )


# =========================================================
# TRAINING EXPORT
# =========================================================

def build_overnight_call_training_example(ctx: OvernightCallContext, decision: OvernightCallDecision) -> Dict[str, Any]:
    return {
        "features": {
            "symbol": ctx.symbol,
            "underlying_price": ctx.underlying_price,
            "option_symbol": ctx.option_symbol,
            "strike": ctx.strike,
            "avg_cost": ctx.avg_cost,
            "expiration_next_day": int(ctx.expiration_next_day),

            "major_print_level": ctx.major_print_level,
            "nearby_supports": ctx.nearby_supports,
            "nearby_resistances": ctx.nearby_resistances,
            "accepted_above_major_print": int(ctx.accepted_above_major_print),
            "holding_above_major_print": int(ctx.holding_above_major_print),

            "strong_close": int(ctx.strong_close),
            "close_near_highs": int(ctx.close_near_highs),
            "higher_lows_into_close": int(ctx.higher_lows_into_close),
            "break_and_hold_structure": int(ctx.break_and_hold_structure),
            "no_late_day_breakdown": int(ctx.no_late_day_breakdown),
            "momentum_intact_into_close": int(ctx.momentum_intact_into_close),

            "oil_price": ctx.oil_price,
            "oil_pct_change": ctx.oil_pct_change,
            "oil_rolling_over": int(ctx.oil_rolling_over),
            "oil_failed_bounce": int(ctx.oil_failed_bounce),
            "oil_macro_pressure_fading": int(ctx.oil_macro_pressure_fading),

            "trend_day_or_continuation_regime": int(ctx.trend_day_or_continuation_regime),
            "chop_regime": int(ctx.chop_regime),
            "failed_breakout_regime": int(ctx.failed_breakout_regime),

            "breakeven": ctx.breakeven,
            "contract_near_itm": int(ctx.contract_near_itm),
            "good_gamma_potential": int(ctx.good_gamma_potential),
            "upside_asymmetry_present": int(ctx.upside_asymmetry_present),

            "overnight_gap_risk": int(ctx.overnight_gap_risk),
            "headline_risk": int(ctx.headline_risk),
            "theta_risk": int(ctx.theta_risk),
            "possible_gap_and_fade": int(ctx.possible_gap_and_fade),
        },
        "label": {
            "setup_name": decision.setup_name,
            "setup_grade": decision.setup_grade,
            "setup_bias": decision.setup_bias,
            "hold_type": decision.hold_type,
            "confidence_score": decision.confidence_score,
            "institutional_alignment": decision.institutional_alignment,
            "macro_alignment": decision.macro_alignment,
            "structure_alignment": decision.structure_alignment,
            "asymmetry_alignment": decision.asymmetry_alignment,
            "lesson_label": decision.lesson_label,
            "reasons": decision.reasons,
            "risks": decision.risks,
            "dataset_summary": decision.dataset_summary,
        }
    }


# =========================================================
# BOT / ANALYZER FORMATTER
# =========================================================

def format_overnight_call_decision_for_bot(decision: OvernightCallDecision) -> str:
    icon = {
        "STRUCTURED_OVERNIGHT": "🌙",
        "SPECULATIVE_OVERNIGHT": "⚠️",
        "AVOID": "⛔",
    }.get(decision.hold_type, "⚪")

    lines = [
        f"{icon} OVERNIGHT CALL AI DECISION",
        f"Setup: {decision.setup_name}",
        f"Grade: {decision.setup_grade}",
        f"Bias: {decision.setup_bias}",
        f"Hold Type: {decision.hold_type}",
        f"Confidence: {decision.confidence_score}",
        f"Institutional Alignment: {decision.institutional_alignment}",
        f"Macro Alignment: {decision.macro_alignment}",
        f"Structure Alignment: {decision.structure_alignment}",
        f"Asymmetry Alignment: {decision.asymmetry_alignment}",
        f"Lesson Label: {decision.lesson_label}",
    ]

    if decision.reasons:
        lines.append("Reasons:")
        for r in decision.reasons:
            lines.append(f" - {r}")

    if decision.risks:
        lines.append("Risks:")
        for r in decision.risks:
            lines.append(f" - {r}")

    lines.append("Dataset Summary:")
    lines.append(decision.dataset_summary)

    return "\n".join(lines)


# =========================================================
# PIPELINE FEATURE EXPORT
# =========================================================

def build_overnight_call_pipeline_features(decision: OvernightCallDecision) -> Dict[str, Any]:
    return {
        "overnight_call_setup_name": decision.setup_name,
        "overnight_call_grade": decision.setup_grade,
        "overnight_call_bias": decision.setup_bias,
        "overnight_call_hold_type": decision.hold_type,
        "overnight_call_confidence": decision.confidence_score,
        "overnight_call_institutional_alignment": decision.institutional_alignment,
        "overnight_call_macro_alignment": decision.macro_alignment,
        "overnight_call_structure_alignment": decision.structure_alignment,
        "overnight_call_asymmetry_alignment": decision.asymmetry_alignment,
        "overnight_call_lesson_label": decision.lesson_label,
    }


# =========================================================
# ONE-SHOT RUNNER
# =========================================================

def run_overnight_qqq_call_brain(ctx: OvernightCallContext) -> Dict[str, Any]:
    decision = evaluate_overnight_qqq_call(ctx)
    training_example = build_overnight_call_training_example(ctx, decision)
    pipeline_features = build_overnight_call_pipeline_features(decision)

    return {
        "context": ctx,
        "decision": decision,
        "decision_dict": asdict(decision),
        "training_example": training_example,
        "pipeline_features": pipeline_features,
        "bot_text": format_overnight_call_decision_for_bot(decision),
    }


# =========================================================
# EXAMPLE: YOUR QQQ 615 CALL BOUGHT BEFORE CLOSE
# =========================================================

OVERNIGHT_QQQ_CALL_INPUT = OvernightCallContext(
    symbol="QQQ",
    underlying_price=621.00,
    option_symbol="QQQ 615C",
    strike=615.0,
    avg_cost=2.05,
    expiration_next_day=True,

    major_print_level=613.75,
    nearby_supports=[610.20, 610.70, 611.40],
    nearby_resistances=[617.50, 620.00],
    accepted_above_major_print=True,
    holding_above_major_print=True,

    strong_close=True,
    close_near_highs=True,
    higher_lows_into_close=True,
    break_and_hold_structure=True,
    no_late_day_breakdown=True,
    momentum_intact_into_close=True,

    oil_price=96.16,
    oil_pct_change=-2.95,
    oil_rolling_over=True,
    oil_failed_bounce=True,
    oil_macro_pressure_fading=True,

    trend_day_or_continuation_regime=True,
    chop_regime=False,
    failed_breakout_regime=False,

    breakeven=617.05,
    contract_near_itm=near_itm(621.00, 615.0),
    good_gamma_potential=True,
    upside_asymmetry_present=True,

    overnight_gap_risk=True,
    headline_risk=True,
    theta_risk=True,
    possible_gap_and_fade=True,
)


# =========================================================
# RUN
# =========================================================

overnight_call_results = run_overnight_qqq_call_brain(OVERNIGHT_QQQ_CALL_INPUT)

print("=== DECISION DICT ===")
print(json.dumps(overnight_call_results["decision_dict"], indent=2))

print("\n=== TRAINING EXAMPLE ===")
print(json.dumps(overnight_call_results["training_example"], indent=2))

print("\n=== PIPELINE FEATURES ===")
print(json.dumps(overnight_call_results["pipeline_features"], indent=2))

print("\n=== BOT OUTPUT ===")
print(overnight_call_results["bot_text"])

# =========================================================
# OPENING RANGE CONFIRMATION LAYER
# =========================================================
# PURPOSE:
# Add first-5-minute opening range logic on top of the
# premarket high / low engine.
#
# WHAT THIS DOES:
# - confirms breakout quality
# - blocks early fakeouts
# - upgrades A setups to A+
# - helps prevent chasing
# =========================================================

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
import math


# =========================================================
# OPENING RANGE MODELS
# =========================================================

@dataclass
class OpeningRange:
    or_high: float
    or_low: float
    or_mid: float = 0.0

    def __post_init__(self):
        if self.or_mid == 0.0:
            self.or_mid = (self.or_high + self.or_low) / 2.0


@dataclass
class OpeningRangeState:
    above_or_high: bool = False
    below_or_low: bool = False
    inside_or: bool = True

    broke_or_high: bool = False
    broke_or_low: bool = False

    held_above_or_high: bool = False
    held_below_or_low: bool = False

    rejected_or_high: bool = False
    rejected_or_low: bool = False

    retest_holding_or_high: bool = False
    retest_failing_or_high: bool = False

    retest_holding_or_low: bool = False
    retest_failing_or_low: bool = False

    opening_drive_bullish: bool = False
    opening_drive_bearish: bool = False

    volume_confirmed: bool = False
    momentum_confirmed: bool = False


def build_opening_range_state(
    current_price: float,
    opening_range: OpeningRange,
    broke_or_high: bool,
    broke_or_low: bool,
    held_above_or_high: bool,
    held_below_or_low: bool,
    rejected_or_high: bool,
    rejected_or_low: bool,
    retest_holding_or_high: bool,
    retest_failing_or_high: bool,
    retest_holding_or_low: bool,
    retest_failing_or_low: bool,
    opening_drive_bullish: bool,
    opening_drive_bearish: bool,
    volume_confirmed: bool,
    momentum_confirmed: bool,
) -> OpeningRangeState:
    above_or_high = current_price > opening_range.or_high
    below_or_low = current_price < opening_range.or_low
    inside_or = not above_or_high and not below_or_low

    return OpeningRangeState(
        above_or_high=above_or_high,
        below_or_low=below_or_low,
        inside_or=inside_or,
        broke_or_high=broke_or_high,
        broke_or_low=broke_or_low,
        held_above_or_high=held_above_or_high,
        held_below_or_low=held_below_or_low,
        rejected_or_high=rejected_or_high,
        rejected_or_low=rejected_or_low,
        retest_holding_or_high=retest_holding_or_high,
        retest_failing_or_high=retest_failing_or_high,
        retest_holding_or_low=retest_holding_or_low,
        retest_failing_or_low=retest_failing_or_low,
        opening_drive_bullish=opening_drive_bullish,
        opening_drive_bearish=opening_drive_bearish,
        volume_confirmed=volume_confirmed,
        momentum_confirmed=momentum_confirmed,
    )


def apply_opening_range_confirmation(
    decision: PremarketDecision,
    st: OpenMarketState,
    opening_range: OpeningRange,
    or_state: OpeningRangeState,
) -> PremarketDecision:
    notes = list(decision.notes)

    # -----------------------------------------------------
    # CALL CONFIRMATION
    # -----------------------------------------------------
    if decision.bias == "CALL":
        if (
            or_state.broke_or_high
            and or_state.held_above_or_high
            and or_state.retest_holding_or_high
            and or_state.volume_confirmed
            and or_state.momentum_confirmed
        ):
            notes.append("Opening range high broke and held.")
            notes.append("Retest of opening range high confirmed.")
            notes.append("Opening range confirms bullish continuation.")

            if decision.grade in ["A", "A+", "B+"]:
                decision.grade = "A+"

            decision.entry_allowed = True
            decision.reason += " Opening range confirms the long."
            decision.target_reference = "OR expansion / next resistance / trend continuation"
            decision.notes = notes
            return decision

        if or_state.inside_or:
            notes.append("Price is still inside the opening range.")
            notes.append("Long is not fully confirmed yet.")
            decision.entry_allowed = False

            if decision.grade == "A+":
                decision.grade = "A"
            elif decision.grade == "A":
                decision.grade = "B+"

            decision.reason += " Opening range has not resolved yet."
            decision.notes = notes
            return decision

        if or_state.rejected_or_high or or_state.retest_failing_or_high:
            notes.append("Opening range high failed.")
            notes.append("Bullish breakout lost confirmation.")
            decision.entry_allowed = False
            decision.grade = "B"
            decision.reason = "Bullish idea weakened because opening range breakout failed."
            decision.notes = notes
            return decision

    # -----------------------------------------------------
    # PUT CONFIRMATION
    # -----------------------------------------------------
    if decision.bias == "PUT":
        if (
            or_state.broke_or_low
            and or_state.held_below_or_low
            and or_state.retest_failing_or_low
            and or_state.volume_confirmed
            and or_state.momentum_confirmed
        ):
            notes.append("Opening range low broke and held below.")
            notes.append("Retest of opening range low failed.")
            notes.append("Opening range confirms bearish continuation.")

            if decision.grade in ["A", "A+", "B+"]:
                decision.grade = "A+"

            decision.entry_allowed = True
            decision.reason += " Opening range confirms the short."
            decision.target_reference = "OR breakdown / next support / trend continuation"
            decision.notes = notes
            return decision

        if or_state.inside_or:
            notes.append("Price is still inside the opening range.")
            notes.append("Short is not fully confirmed yet.")
            decision.entry_allowed = False

            if decision.grade == "A+":
                decision.grade = "A"
            elif decision.grade == "A":
                decision.grade = "B+"

            decision.reason += " Opening range has not resolved yet."
            decision.notes = notes
            return decision

        if or_state.rejected_or_low or or_state.retest_holding_or_low:
            notes.append("Opening range low failed to break cleanly.")
            notes.append("Bearish breakdown lost confirmation.")
            decision.entry_allowed = False
            decision.grade = "B"
            decision.reason = "Bearish idea weakened because opening range breakdown failed."
            decision.notes = notes
            return decision

    decision.notes = notes
    return decision


def format_opening_range_summary(
    opening_range: OpeningRange,
    or_state: OpeningRangeState,
) -> str:
    lines = [
        "OPENING RANGE STATUS",
        f"OR High: {opening_range.or_high:.2f}",
        f"OR Low: {opening_range.or_low:.2f}",
        f"OR Mid: {opening_range.or_mid:.2f}",
        f"Above OR High: {or_state.above_or_high}",
        f"Below OR Low: {or_state.below_or_low}",
        f"Inside OR: {or_state.inside_or}",
        f"Volume Confirmed: {or_state.volume_confirmed}",
        f"Momentum Confirmed: {or_state.momentum_confirmed}",
    ]
    return "\n".join(lines)


# =========================================================
# YOU ARE CHASING + SIZE ADJUSTMENT ENGINE
# =========================================================

@dataclass
class SizeAdjustmentDecision:
    allowed: bool
    size_fraction: float    # 1.0, 0.75, 0.5, 0.25, 0.0
    size_label: str         # FULL, THREE_QUARTER, HALF, QUARTER, BLOCKED
    chase_score: int
    confidence_score: int
    reason: str
    notes: List[str] = field(default_factory=list)


def grade_to_score(grade: str) -> int:
    grade_map = {
        "A+": 5,
        "A": 4,
        "B+": 3,
        "B": 2,
        "C": 1,
        "AVOID": 0,
    }
    return grade_map.get(grade, 0)


def detect_chase_blocker(
    decision: PremarketDecision,
    st: OpenMarketState,
    or_state: Optional[OpeningRangeState] = None,
) -> SizeAdjustmentDecision:
    notes: List[str] = []
    chase_score = 0
    confidence_score = grade_to_score(decision.grade)

    # EXTENSION FROM VWAP
    if st.extended_from_vwap_pct >= 1.50:
        chase_score += 4
        notes.append("Extreme extension from VWAP.")
    elif st.extended_from_vwap_pct >= 1.20:
        chase_score += 3
        notes.append("High extension from VWAP.")
    elif st.extended_from_vwap_pct >= 0.90:
        chase_score += 2
        notes.append("Moderate extension from VWAP.")
    elif st.extended_from_vwap_pct >= 0.60:
        chase_score += 1
        notes.append("Mild extension from VWAP.")

    # EXTENSION FROM PM LEVELS
    if decision.bias == "CALL":
        if st.extended_from_premarket_high_pct >= 1.00:
            chase_score += 3
            notes.append("Price is far above premarket high.")
        elif st.extended_from_premarket_high_pct >= 0.60:
            chase_score += 2
            notes.append("Price is extended above premarket high.")
        elif st.extended_from_premarket_high_pct >= 0.35:
            chase_score += 1
            notes.append("Price is slightly extended above premarket high.")

    if decision.bias == "PUT":
        if st.extended_from_premarket_low_pct >= 1.00:
            chase_score += 3
            notes.append("Price is far below premarket low.")
        elif st.extended_from_premarket_low_pct >= 0.60:
            chase_score += 2
            notes.append("Price is extended below premarket low.")
        elif st.extended_from_premarket_low_pct >= 0.35:
            chase_score += 1
            notes.append("Price is slightly extended below premarket low.")

    # RSI STRETCH
    if st.rsi is not None:
        if decision.bias == "CALL":
            if st.rsi >= 85:
                chase_score += 3
                notes.append("RSI is extremely overextended for a long.")
            elif st.rsi >= 78:
                chase_score += 2
                notes.append("RSI is stretched for a long.")
            elif st.rsi >= 72:
                chase_score += 1
                notes.append("RSI is elevated for a long.")

        if decision.bias == "PUT":
            if st.rsi <= 15:
                chase_score += 3
                notes.append("RSI is extremely compressed for a short.")
            elif st.rsi <= 22:
                chase_score += 2
                notes.append("RSI is stretched for a short.")
            elif st.rsi <= 28:
                chase_score += 1
                notes.append("RSI is low for a short.")

    # MOMENTUM FADE
    if st.momentum_fading:
        chase_score += 2
        notes.append("Momentum is fading.")

    if decision.bias == "CALL" and st.macd_histogram_falling:
        chase_score += 1
        notes.append("MACD histogram is fading on long idea.")

    if decision.bias == "PUT" and st.macd_histogram_rising:
        chase_score += 1
        notes.append("MACD histogram is fading on short idea.")

    # OPENING RANGE CONTEXT
    if or_state is not None:
        if decision.bias == "CALL":
            if or_state.inside_or:
                chase_score += 1
                notes.append("Long still inside opening range.")
            if or_state.rejected_or_high or or_state.retest_failing_or_high:
                chase_score += 2
                notes.append("Opening range high failed for long idea.")

        if decision.bias == "PUT":
            if or_state.inside_or:
                chase_score += 1
                notes.append("Short still inside opening range.")
            if or_state.rejected_or_low or or_state.retest_holding_or_low:
                chase_score += 2
                notes.append("Opening range low failed for short idea.")

    # DECISION MATRIX
    if decision.grade in ["AVOID", "C"]:
        return SizeAdjustmentDecision(
            allowed=False,
            size_fraction=0.0,
            size_label="BLOCKED",
            chase_score=chase_score,
            confidence_score=confidence_score,
            reason="Setup quality is too weak.",
            notes=notes,
        )

    if not decision.entry_allowed:
        return SizeAdjustmentDecision(
            allowed=False,
            size_fraction=0.0,
            size_label="BLOCKED",
            chase_score=chase_score,
            confidence_score=confidence_score,
            reason="Trade is not confirmed. Entry blocked.",
            notes=notes,
        )

    if chase_score >= 7:
        notes.append("YOU ARE CHASING: hard block triggered.")
        return SizeAdjustmentDecision(
            allowed=False,
            size_fraction=0.0,
            size_label="BLOCKED",
            chase_score=chase_score,
            confidence_score=confidence_score,
            reason="Entry is too extended. Do not chase.",
            notes=notes,
        )

    if chase_score >= 5:
        notes.append("High chase risk: reduce to quarter size.")
        return SizeAdjustmentDecision(
            allowed=True,
            size_fraction=0.25,
            size_label="QUARTER",
            chase_score=chase_score,
            confidence_score=confidence_score,
            reason="Setup is valid, but extension risk is high.",
            notes=notes,
        )

    if chase_score >= 3:
        notes.append("Moderate chase risk: reduce to half size.")
        return SizeAdjustmentDecision(
            allowed=True,
            size_fraction=0.50,
            size_label="HALF",
            chase_score=chase_score,
            confidence_score=confidence_score,
            reason="Setup is valid, but not clean enough for full size.",
            notes=notes,
        )

    if decision.grade in ["B", "B+"]:
        notes.append("B-grade setup capped at half size.")
        return SizeAdjustmentDecision(
            allowed=True,
            size_fraction=0.50,
            size_label="HALF",
            chase_score=chase_score,
            confidence_score=confidence_score,
            reason="Good setup, but not elite quality.",
            notes=notes,
        )

    if decision.grade == "A":
        notes.append("A-grade setup allowed at 75% size.")
        return SizeAdjustmentDecision(
            allowed=True,
            size_fraction=0.75,
            size_label="THREE_QUARTER",
            chase_score=chase_score,
            confidence_score=confidence_score,
            reason="Strong setup with acceptable risk.",
            notes=notes,
        )

    notes.append("A+ setup with low chase risk: full size allowed.")
    return SizeAdjustmentDecision(
        allowed=True,
        size_fraction=1.0,
        size_label="FULL",
        chase_score=chase_score,
        confidence_score=confidence_score,
        reason="Elite setup with clean confirmation and low extension.",
        notes=notes,
    )


def apply_size_adjustment_to_decision(
    decision: PremarketDecision,
    size_decision: SizeAdjustmentDecision,
) -> PremarketDecision:
    notes = list(decision.notes)

    notes.append(f"Size Label: {size_decision.size_label}")
    notes.append(f"Size Fraction: {size_decision.size_fraction:.2f}")
    notes.append(f"Chase Score: {size_decision.chase_score}")
    notes.append(f"Confidence Score: {size_decision.confidence_score}")

    for note in size_decision.notes:
        notes.append(note)

    if not size_decision.allowed:
        decision.entry_allowed = False
        if decision.grade != "AVOID":
            decision.grade = "B" if decision.grade in ["A+", "A", "B+"] else decision.grade
        decision.reason = size_decision.reason
    else:
        decision.reason += f" Recommended size: {size_decision.size_label}."

    decision.notes = notes
    return decision


def format_size_adjustment_summary(size_decision: SizeAdjustmentDecision) -> str:
    lines = [
        "SIZE ADJUSTMENT ENGINE",
        f"Allowed: {size_decision.allowed}",
        f"Size Label: {size_decision.size_label}",
        f"Size Fraction: {size_decision.size_fraction:.2f}",
        f"Chase Score: {size_decision.chase_score}",
        f"Confidence Score: {size_decision.confidence_score}",
        f"Reason: {size_decision.reason}",
    ]

    if size_decision.notes:
        lines.append("Notes:")
        for note in size_decision.notes:
            lines.append(f" - {note}")

    return "\n".join(lines)


def calculate_contract_size(base_contracts: int, size_fraction: float) -> int:
    if base_contracts <= 0:
        return 0

    contracts = int(round(base_contracts * size_fraction))

    if size_fraction > 0 and contracts == 0:
        contracts = 1

    return contracts


# =========================================================
# AUTO STOP-LOSS + SCALE-OUT ENGINE
# =========================================================

@dataclass
class TradeManagementPlan:
    trade_active: bool
    direction: str
    entry_price: float
    stop_price: float
    risk_per_share: float
    target_1: float
    target_2: float
    runner_target: float
    stop_reference: str
    target_1_reference: str
    target_2_reference: str
    runner_reference: str
    trim_1_pct: float
    trim_2_pct: float
    runner_pct: float
    move_to_be_after_target_1: bool
    trail_runner: bool
    plan_quality: str
    reason: str
    notes: List[str] = field(default_factory=list)


def safe_round_price(value: float) -> float:
    return round(float(value), 2)


def infer_stop_from_decision(
    decision: PremarketDecision,
    st: OpenMarketState,
    levels: PremarketLevels,
    opening_range: Optional[OpeningRange] = None,
) -> tuple[float, str, List[str]]:
    notes: List[str] = []

    if decision.bias == "CALL":
        candidates = []
        candidates.append(("VWAP", st.vwap))
        candidates.append(("Premarket High", levels.premarket_high))

        if opening_range is not None:
            candidates.append(("Opening Range Low", opening_range.or_low))
            candidates.append(("Opening Range Mid", opening_range.or_mid))

        valid = [(name, px) for name, px in candidates if px < st.current_price]

        if valid:
            stop_name, stop_px = max(valid, key=lambda x: x[1])
            stop_px = stop_px - 0.10
            notes.append(f"Stop anchored below {stop_name}.")
            return safe_round_price(stop_px), f"Below {stop_name}", notes

        fallback = st.current_price - max(st.current_price * 0.0035, 0.75)
        notes.append("No clear support level found. Used fallback long stop.")
        return safe_round_price(fallback), "Fallback Long Stop", notes

    if decision.bias == "PUT":
        candidates = []
        candidates.append(("VWAP", st.vwap))
        candidates.append(("Premarket Low", levels.premarket_low))

        if opening_range is not None:
            candidates.append(("Opening Range High", opening_range.or_high))
            candidates.append(("Opening Range Mid", opening_range.or_mid))

        valid = [(name, px) for name, px in candidates if px > st.current_price]

        if valid:
            stop_name, stop_px = min(valid, key=lambda x: x[1])
            stop_px = stop_px + 0.10
            notes.append(f"Stop anchored above {stop_name}.")
            return safe_round_price(stop_px), f"Above {stop_name}", notes

        fallback = st.current_price + max(st.current_price * 0.0035, 0.75)
        notes.append("No clear resistance level found. Used fallback short stop.")
        return safe_round_price(fallback), "Fallback Short Stop", notes

    return 0.0, "None", ["No directional trade."]


def build_trade_management_plan(
    decision: PremarketDecision,
    size_decision: SizeAdjustmentDecision,
    levels: PremarketLevels,
    st: OpenMarketState,
    opening_range: Optional[OpeningRange] = None,
    next_resistance: Optional[float] = None,
    next_support: Optional[float] = None,
) -> TradeManagementPlan:
    notes: List[str] = []

    if not decision.entry_allowed or not size_decision.allowed or decision.bias not in ["CALL", "PUT"]:
        return TradeManagementPlan(
            trade_active=False,
            direction="NONE",
            entry_price=safe_round_price(st.current_price),
            stop_price=0.0,
            risk_per_share=0.0,
            target_1=0.0,
            target_2=0.0,
            runner_target=0.0,
            stop_reference="None",
            target_1_reference="None",
            target_2_reference="None",
            runner_reference="None",
            trim_1_pct=0.0,
            trim_2_pct=0.0,
            runner_pct=0.0,
            move_to_be_after_target_1=False,
            trail_runner=False,
            plan_quality="BLOCKED",
            reason="Trade is not active because entry is blocked.",
            notes=["Management plan not created."],
        )

    entry_price = safe_round_price(st.current_price)
    stop_price, stop_reference, stop_notes = infer_stop_from_decision(
        decision, st, levels, opening_range
    )
    notes.extend(stop_notes)

    risk_per_share = abs(entry_price - stop_price)

    if risk_per_share <= 0:
        return TradeManagementPlan(
            trade_active=False,
            direction="NONE",
            entry_price=entry_price,
            stop_price=0.0,
            risk_per_share=0.0,
            target_1=0.0,
            target_2=0.0,
            runner_target=0.0,
            stop_reference="Invalid",
            target_1_reference="Invalid",
            target_2_reference="Invalid",
            runner_reference="Invalid",
            trim_1_pct=0.0,
            trim_2_pct=0.0,
            runner_pct=0.0,
            move_to_be_after_target_1=False,
            trail_runner=False,
            plan_quality="BLOCKED",
            reason="Risk calculation failed.",
            notes=["Stop and entry created invalid risk."],
        )

    if decision.bias == "CALL":
        target_1 = entry_price + risk_per_share * 1.0
        target_2 = entry_price + risk_per_share * 2.0

        if next_resistance is not None and next_resistance > entry_price:
            target_1 = min(target_1, next_resistance)

        if opening_range is not None and opening_range.or_high > entry_price:
            target_1 = min(target_1, opening_range.or_high)

        if next_resistance is not None and next_resistance > target_2:
            runner_target = next_resistance
            runner_reference = "Next Resistance"
        else:
            runner_target = entry_price + risk_per_share * 3.0
            runner_reference = "3R Extension"

        target_1_reference = "1R / nearest resistance"
        target_2_reference = "2R expansion"
        notes.append("Call targets built from risk and resistance.")

    else:
        target_1 = entry_price - risk_per_share * 1.0
        target_2 = entry_price - risk_per_share * 2.0

        if next_support is not None and next_support < entry_price:
            target_1 = max(target_1, next_support)

        if opening_range is not None and opening_range.or_low < entry_price:
            target_1 = max(target_1, opening_range.or_low)

        if next_support is not None and next_support < target_2:
            runner_target = next_support
            runner_reference = "Next Support"
        else:
            runner_target = entry_price - risk_per_share * 3.0
            runner_reference = "3R Flush Extension"

        target_1_reference = "1R / nearest support"
        target_2_reference = "2R expansion"
        notes.append("Put targets built from risk and support.")

    target_1 = safe_round_price(target_1)
    target_2 = safe_round_price(target_2)
    runner_target = safe_round_price(runner_target)

    if decision.grade == "A+":
        trim_1_pct = 0.25
        trim_2_pct = 0.50
        runner_pct = 0.25
        plan_quality = "A+"
        notes.append("A+ setup: keep meaningful runner.")
    elif decision.grade == "A":
        trim_1_pct = 0.33
        trim_2_pct = 0.34
        runner_pct = 0.33
        plan_quality = "A"
        notes.append("A setup: balanced trim structure.")
    elif decision.grade == "B+":
        trim_1_pct = 0.50
        trim_2_pct = 0.30
        runner_pct = 0.20
        plan_quality = "B+"
        notes.append("B+ setup: take more off early.")
    else:
        trim_1_pct = 0.60
        trim_2_pct = 0.25
        runner_pct = 0.15
        plan_quality = decision.grade
        notes.append("Lower-quality setup: prioritize faster de-risking.")

    return TradeManagementPlan(
        trade_active=True,
        direction=decision.bias,
        entry_price=entry_price,
        stop_price=stop_price,
        risk_per_share=safe_round_price(risk_per_share),
        target_1=target_1,
        target_2=target_2,
        runner_target=runner_target,
        stop_reference=stop_reference,
        target_1_reference=target_1_reference,
        target_2_reference=target_2_reference,
        runner_reference=runner_reference,
        trim_1_pct=trim_1_pct,
        trim_2_pct=trim_2_pct,
        runner_pct=runner_pct,
        move_to_be_after_target_1=True,
        trail_runner=True,
        plan_quality=plan_quality,
        reason="Trade management plan created successfully.",
        notes=notes,
    )


def format_trade_management_plan(plan: TradeManagementPlan) -> str:
    lines = [
        "TRADE MANAGEMENT PLAN",
        f"Trade Active: {plan.trade_active}",
        f"Direction: {plan.direction}",
        f"Plan Quality: {plan.plan_quality}",
        f"Entry: {plan.entry_price:.2f}",
        f"Stop: {plan.stop_price:.2f}",
        f"Risk/Share: {plan.risk_per_share:.2f}",
        f"Stop Reference: {plan.stop_reference}",
        f"Target 1: {plan.target_1:.2f}",
        f"Target 1 Ref: {plan.target_1_reference}",
        f"Trim 1 %: {plan.trim_1_pct:.0%}",
        f"Target 2: {plan.target_2:.2f}",
        f"Target 2 Ref: {plan.target_2_reference}",
        f"Trim 2 %: {plan.trim_2_pct:.0%}",
        f"Runner Target: {plan.runner_target:.2f}",
        f"Runner Ref: {plan.runner_reference}",
        f"Runner %: {plan.runner_pct:.0%}",
        f"Move Stop To BE After T1: {plan.move_to_be_after_target_1}",
        f"Trail Runner: {plan.trail_runner}",
        f"Reason: {plan.reason}",
    ]

    if plan.notes:
        lines.append("Notes:")
        for note in plan.notes:
            lines.append(f" - {note}")

    return "\n".join(lines)


def should_move_stop_to_breakeven(
    current_price: float,
    plan: TradeManagementPlan,
) -> bool:
    if not plan.trade_active or not plan.move_to_be_after_target_1:
        return False

    if plan.direction == "CALL":
        return current_price >= plan.target_1
    if plan.direction == "PUT":
        return current_price <= plan.target_1

    return False


def classify_trade_progress(
    current_price: float,
    plan: TradeManagementPlan,
) -> str:
    if not plan.trade_active:
        return "NO_TRADE"

    if plan.direction == "CALL":
        if current_price <= plan.stop_price:
            return "STOPPED"
        if current_price >= plan.runner_target:
            return "RUNNER_TARGET_HIT"
        if current_price >= plan.target_2:
            return "TARGET_2_HIT"
        if current_price >= plan.target_1:
            return "TARGET_1_HIT"
        return "ACTIVE"

    if plan.direction == "PUT":
        if current_price >= plan.stop_price:
            return "STOPPED"
        if current_price <= plan.runner_target:
            return "RUNNER_TARGET_HIT"
        if current_price <= plan.target_2:
            return "TARGET_2_HIT"
        if current_price <= plan.target_1:
            return "TARGET_1_HIT"
        return "ACTIVE"

    return "NO_TRADE"


def build_management_alert(
    current_price: float,
    plan: TradeManagementPlan,
) -> str:
    progress = classify_trade_progress(current_price, plan)
    move_be = should_move_stop_to_breakeven(current_price, plan)

    lines = [
        "LIVE MANAGEMENT STATUS",
        f"Current Price: {current_price:.2f}",
        f"Progress: {progress}",
    ]

    if move_be:
        lines.append("Action: Move stop to breakeven.")

    if progress == "TARGET_1_HIT":
        lines.append(f"Action: Trim {plan.trim_1_pct:.0%} at Target 1.")
    elif progress == "TARGET_2_HIT":
        lines.append(f"Action: Trim {plan.trim_2_pct:.0%} at Target 2.")
    elif progress == "RUNNER_TARGET_HIT":
        lines.append("Action: Runner target reached. Trail aggressively or close.")
    elif progress == "STOPPED":
        lines.append("Action: Stop hit. Exit remaining position.")
    else:
        lines.append("Action: Hold current plan.")

    return "\n".join(lines)


def estimate_option_scale_out(
    contracts: int,
    trim_1_pct: float,
    trim_2_pct: float,
    runner_pct: float,
) -> dict:
    if contracts <= 0:
        return {"trim_1": 0, "trim_2": 0, "runner": 0}

    trim_1 = max(1, int(round(contracts * trim_1_pct)))
    trim_2 = int(round(contracts * trim_2_pct))
    used = trim_1 + trim_2

    if used > contracts:
        trim_2 = max(0, contracts - trim_1)
        used = trim_1 + trim_2

    runner = max(0, contracts - used)

    return {
        "trim_1": trim_1,
        "trim_2": trim_2,
        "runner": runner
    }


# =========================================================
# EXAMPLE USAGE
# =========================================================
if __name__ == "__main__":
    levels = PremarketLevels(
        premarket_high=396.50,
        premarket_low=388.20
    )

    state = build_open_market_state(
        current_price=397.20,
        vwap=394.80,
        premarket_high=levels.premarket_high,
        premarket_low=levels.premarket_low,
        broke_premarket_high=True,
        broke_premarket_low=False,
        held_above_premarket_high=True,
        held_below_premarket_low=False,
        rejected_premarket_high=False,
        rejected_premarket_low=False,
        retest_holding_high=True,
        retest_failing_high=False,
        retest_holding_low=False,
        retest_failing_low=False,
        above_vwap=True,
        below_vwap=False,
        vwap_reclaimed=True,
        vwap_rejected=False,
        higher_low=True,
        lower_high=False,
        breakout_volume=True,
        breakdown_volume=False,
        momentum_strong=True,
        momentum_fading=False,
        rsi=74.0,
        macd_histogram_rising=True,
        macd_histogram_falling=False,
    )

    opening_range = OpeningRange(
        or_high=397.00,
        or_low=394.90
    )

    or_state = build_opening_range_state(
        current_price=397.20,
        opening_range=opening_range,
        broke_or_high=True,
        broke_or_low=False,
        held_above_or_high=True,
        held_below_or_low=False,
        rejected_or_high=False,
        rejected_or_low=False,
        retest_holding_or_high=True,
        retest_failing_or_high=False,
        retest_holding_or_low=False,
        retest_failing_or_low=False,
        opening_drive_bullish=True,
        opening_drive_bearish=False,
        volume_confirmed=True,
        momentum_confirmed=True,
    )

    decision = evaluate_premarket_open_logic(levels, state)
    decision = apply_opening_range_confirmation(decision, state, opening_range, or_state)
    decision = execution_filter_premarket(decision, state)

    size_decision = detect_chase_blocker(decision, state, or_state)
    decision = apply_size_adjustment_to_decision(decision, size_decision)

    plan = build_trade_management_plan(
        decision=decision,
        size_decision=size_decision,
        levels=levels,
        st=state,
        opening_range=opening_range,
        next_resistance=399.50,
        next_support=394.00,
    )

    print(format_opening_range_summary(opening_range, or_state))
    print()
    print(format_size_adjustment_summary(size_decision))
    print()
    print(format_trade_management_plan(plan))
    print()
    print(format_premarket_decision_for_bot(decision, levels, state))
    print()
    print(build_management_alert(current_price=398.10, plan=plan))
    print()
    print("Recommended Contracts:",
          calculate_contract_size(base_contracts=4, size_fraction=size_decision.size_fraction))
    print("Scale-Out Plan:",
          estimate_option_scale_out(
              contracts=4,
              trim_1_pct=plan.trim_1_pct,
              trim_2_pct=plan.trim_2_pct,
              runner_pct=plan.runner_pct
          ))

# =========================================================
# AI LEARNING CODE: QQQ 628 CALL 0DTE
# "TREND CONTINUATION — LATE EXPANSION ENTRY"
# ONE-CELL VERSION
# =========================================================
# PURPOSE:
# Teach the AI how to classify, manage, and learn from a late
# bullish continuation entry that had strong structure but poor
# location and weak reward/risk.
#
# CORE LESSON:
# "The move is not the entry. The setup is the entry."
#
# WHAT THIS MODULE TEACHES:
# - Strong trend continuation can still grade only B
# - Late expansion entries are lower quality than pullback/value entries
# - 0DTE + extension + RSI 80+ = fragile premium
# - B setups require fast profit-taking and tight exits
# =========================================================

from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any
import json


# =========================================================
# DATA MODELS
# =========================================================

@dataclass
class LateExpansionTradeContext:
    symbol: str
    current_price: float
    option_symbol: str
    option_type: str                  # CALL / PUT
    same_day_expiration: bool

    # structure
    above_vwap: bool = False
    above_emas: bool = False
    strong_higher_lows: bool = False
    bullish_structure: bool = False

    # momentum
    strong_green_candles: bool = False
    expansion_phase_active: bool = False
    macd_bullish: bool = False
    momentum_continuation_only: bool = False

    # location
    tagged_upper_bollinger: bool = False
    tagged_lower_bollinger: bool = False
    entered_at_top_of_move: bool = False
    entered_at_value_zone: bool = False
    pullback_entry: bool = False
    ema_retest_entry: bool = False
    vwap_reclaim_entry: bool = False
    break_retest_go_entry: bool = False

    # extension / risk
    rsi: float = 50.0
    premium_expensive: bool = False
    reward_to_risk_weak: bool = False
    emotional_continuation_entry: bool = False

    # option / trade specifics
    strike: float = 628.0
    breakeven_price: float = 628.29

    # risk management zones
    ideal_entry_low: float = 625.0
    ideal_entry_high: float = 625.5
    risk_exit_low: float = 625.8
    risk_exit_high: float = 626.0


@dataclass
class LateExpansionDecision:
    setup_name: str
    setup_grade: str                  # A+ / A / B+ / B / AVOID
    setup_bias: str                   # BULLISH / BEARISH / NEUTRAL
    entry_quality: str                # IDEAL / ACCEPTABLE / LATE / POOR
    management_style: str             # QUICK_SCALP / FAST_SCALE_OUT / HOLD_CORE / AVOID_ENTRY
    confidence_score: float
    force_fast_profits: bool
    force_tight_risk: bool
    continuation_required: bool
    reasons: List[str]
    lesson_label: str
    dataset_summary: str


# =========================================================
# HELPERS
# =========================================================

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def in_range(x: float, low: float, high: float) -> bool:
    return low <= x <= high


def is_rsi_extreme_high(rsi: float) -> bool:
    return rsi >= 80


def is_rsi_elevated(rsi: float) -> bool:
    return rsi >= 70


# =========================================================
# SETUP CLASSIFICATION
# =========================================================

def classify_entry_quality(ctx: LateExpansionTradeContext) -> str:
    if (
        ctx.entered_at_value_zone
        or ctx.pullback_entry
        or ctx.ema_retest_entry
        or ctx.vwap_reclaim_entry
        or ctx.break_retest_go_entry
    ):
        return "IDEAL"

    if ctx.entered_at_top_of_move and (ctx.tagged_upper_bollinger or is_rsi_extreme_high(ctx.rsi)):
        return "LATE"

    if ctx.entered_at_top_of_move:
        return "ACCEPTABLE"

    return "POOR"


def grade_late_expansion_continuation(ctx: LateExpansionTradeContext) -> str:
    score = 0

    # positives
    if ctx.above_vwap:
        score += 1
    if ctx.above_emas:
        score += 1
    if ctx.strong_higher_lows:
        score += 2
    if ctx.bullish_structure:
        score += 2
    if ctx.strong_green_candles:
        score += 1
    if ctx.expansion_phase_active:
        score += 1
    if ctx.macd_bullish:
        score += 1

    # negatives
    if ctx.entered_at_top_of_move:
        score -= 2
    if ctx.tagged_upper_bollinger:
        score -= 1
    if is_rsi_extreme_high(ctx.rsi):
        score -= 2
    elif is_rsi_elevated(ctx.rsi):
        score -= 1
    if not (
        ctx.pullback_entry
        or ctx.ema_retest_entry
        or ctx.vwap_reclaim_entry
        or ctx.break_retest_go_entry
        or ctx.entered_at_value_zone
    ):
        score -= 2
    if ctx.reward_to_risk_weak:
        score -= 2
    if ctx.same_day_expiration:
        score -= 1
    if ctx.premium_expensive:
        score -= 1
    if ctx.emotional_continuation_entry:
        score -= 1

    if score >= 8:
        return "A"
    if score >= 6:
        return "B+"
    if score >= 3:
        return "B"
    return "AVOID"


# =========================================================
# MANAGEMENT LOGIC
# =========================================================

def decide_management_style(ctx: LateExpansionTradeContext, grade: str, entry_quality: str) -> Dict[str, Any]:
    reasons = []
    force_fast_profits = False
    force_tight_risk = False
    continuation_required = False

    if grade == "A" and entry_quality == "IDEAL":
        style = "HOLD_CORE"
        reasons.append("High-quality structure with strong location allows broader management.")
    elif grade in {"B+", "B"}:
        style = "FAST_SCALE_OUT"
        force_fast_profits = True
        force_tight_risk = True
        continuation_required = True
        reasons.append("This setup relies on continuation, not value-zone asymmetry.")
    else:
        style = "AVOID_ENTRY"
        force_tight_risk = True
        reasons.append("Location and payoff are too weak for a fresh entry.")

    if ctx.same_day_expiration:
        force_fast_profits = True
        force_tight_risk = True
        reasons.append("0DTE premium requires faster management.")

    if ctx.reward_to_risk_weak:
        force_fast_profits = True
        reasons.append("Weak reward-to-risk means the trade should not be overheld.")

    if ctx.entered_at_top_of_move:
        force_fast_profits = True
        reasons.append("Top-of-move entry reduces hold quality.")

    if is_rsi_extreme_high(ctx.rsi):
        force_fast_profits = True
        reasons.append("RSI 80+ means momentum is already very mature.")

    return {
        "management_style": style,
        "force_fast_profits": force_fast_profits,
        "force_tight_risk": force_tight_risk,
        "continuation_required": continuation_required,
        "reasons": reasons,
    }


# =========================================================
# MAIN LEARNING DECISION
# =========================================================

def evaluate_late_expansion_trade(ctx: LateExpansionTradeContext) -> LateExpansionDecision:
    reasons: List[str] = []

    # positives
    if ctx.above_vwap:
        reasons.append("Price is above VWAP.")
    if ctx.above_emas:
        reasons.append("Price is above key short-term moving averages.")
    if ctx.strong_higher_lows:
        reasons.append("Higher lows support bullish continuation.")
    if ctx.bullish_structure:
        reasons.append("Overall structure is bullish.")
    if ctx.strong_green_candles:
        reasons.append("Strong green candles confirm momentum.")
    if ctx.expansion_phase_active:
        reasons.append("Trade was taken during expansion phase.")
    if ctx.macd_bullish:
        reasons.append("MACD supports bullish direction.")

    # negatives
    if ctx.entered_at_top_of_move:
        reasons.append("Entry was at the top of the move, not at value.")
    if ctx.tagged_upper_bollinger:
        reasons.append("Price was tagging the upper Bollinger Band.")
    if is_rsi_extreme_high(ctx.rsi):
        reasons.append("RSI was extreme (80+).")
    elif is_rsi_elevated(ctx.rsi):
        reasons.append("RSI was elevated.")
    if not ctx.pullback_entry:
        reasons.append("No pullback entry was taken.")
    if not ctx.vwap_reclaim_entry and not ctx.ema_retest_entry and not ctx.break_retest_go_entry:
        reasons.append("Entry was not at a true support reclaim or retest.")
    if ctx.reward_to_risk_weak:
        reasons.append("Reward-to-risk was weak and required continuation just to win.")
    if ctx.same_day_expiration:
        reasons.append("0DTE option structure increased premium fragility.")
    if ctx.premium_expensive:
        reasons.append("Premium was already expensive.")
    if ctx.emotional_continuation_entry:
        reasons.append("Entry had emotional continuation risk.")

    setup_grade = grade_late_expansion_continuation(ctx)
    setup_bias = "BULLISH" if ctx.bullish_structure else "NEUTRAL"
    entry_quality = classify_entry_quality(ctx)

    management = decide_management_style(ctx, setup_grade, entry_quality)
    reasons.extend(management["reasons"])

    confidence = 0.50
    if setup_grade == "A":
        confidence = 0.82
    elif setup_grade == "B+":
        confidence = 0.72
    elif setup_grade == "B":
        confidence = 0.63
    elif setup_grade == "AVOID":
        confidence = 0.18

    if entry_quality == "LATE":
        confidence -= 0.10
    if ctx.same_day_expiration:
        confidence -= 0.06
    if is_rsi_extreme_high(ctx.rsi):
        confidence -= 0.06
    if ctx.reward_to_risk_weak:
        confidence -= 0.08
    confidence = clamp(confidence, 0.0, 1.0)

    dataset_summary = (
        "This was a B bullish continuation setup because QQQ had strong structure, stayed above VWAP "
        "and EMAs, and maintained higher lows with bullish momentum still active. However, the entry was "
        "taken late in the move near the top of expansion, with price tagging the upper Bollinger Band and "
        "RSI above 80, making the location poor and the reward-to-risk weak. The trade depended on continued "
        "squeeze behavior rather than entering from value. For 0DTE options, this means premium is fragile, "
        "so the AI should label this as a fast-management trade: take quick profits, scale out early, and exit "
        "fast if price loses the 625.8 - 626.0 support zone."
    )

    return LateExpansionDecision(
        setup_name="Trend Continuation — Late Expansion Entry",
        setup_grade=setup_grade,
        setup_bias=setup_bias,
        entry_quality=entry_quality,
        management_style=management["management_style"],
        confidence_score=round(confidence, 3),
        force_fast_profits=management["force_fast_profits"],
        force_tight_risk=management["force_tight_risk"],
        continuation_required=management["continuation_required"],
        reasons=reasons,
        lesson_label="LATE_EXPANSION_0DTE_CONTINUATION_B",
        dataset_summary=dataset_summary,
    )


# =========================================================
# TRAINING EXPORT
# =========================================================

def build_late_expansion_training_example(ctx: LateExpansionTradeContext, decision: LateExpansionDecision) -> Dict[str, Any]:
    return {
        "features": {
            "symbol": ctx.symbol,
            "current_price": ctx.current_price,
            "option_symbol": ctx.option_symbol,
            "option_type": ctx.option_type,
            "same_day_expiration": int(ctx.same_day_expiration),

            "above_vwap": int(ctx.above_vwap),
            "above_emas": int(ctx.above_emas),
            "strong_higher_lows": int(ctx.strong_higher_lows),
            "bullish_structure": int(ctx.bullish_structure),

            "strong_green_candles": int(ctx.strong_green_candles),
            "expansion_phase_active": int(ctx.expansion_phase_active),
            "macd_bullish": int(ctx.macd_bullish),
            "momentum_continuation_only": int(ctx.momentum_continuation_only),

            "tagged_upper_bollinger": int(ctx.tagged_upper_bollinger),
            "tagged_lower_bollinger": int(ctx.tagged_lower_bollinger),
            "entered_at_top_of_move": int(ctx.entered_at_top_of_move),
            "entered_at_value_zone": int(ctx.entered_at_value_zone),
            "pullback_entry": int(ctx.pullback_entry),
            "ema_retest_entry": int(ctx.ema_retest_entry),
            "vwap_reclaim_entry": int(ctx.vwap_reclaim_entry),
            "break_retest_go_entry": int(ctx.break_retest_go_entry),

            "rsi": ctx.rsi,
            "premium_expensive": int(ctx.premium_expensive),
            "reward_to_risk_weak": int(ctx.reward_to_risk_weak),
            "emotional_continuation_entry": int(ctx.emotional_continuation_entry),

            "strike": ctx.strike,
            "breakeven_price": ctx.breakeven_price,
            "ideal_entry_low": ctx.ideal_entry_low,
            "ideal_entry_high": ctx.ideal_entry_high,
            "risk_exit_low": ctx.risk_exit_low,
            "risk_exit_high": ctx.risk_exit_high,
        },
        "label": {
            "setup_name": decision.setup_name,
            "setup_grade": decision.setup_grade,
            "setup_bias": decision.setup_bias,
            "entry_quality": decision.entry_quality,
            "management_style": decision.management_style,
            "confidence_score": decision.confidence_score,
            "force_fast_profits": decision.force_fast_profits,
            "force_tight_risk": decision.force_tight_risk,
            "continuation_required": decision.continuation_required,
            "lesson_label": decision.lesson_label,
            "reasons": decision.reasons,
            "dataset_summary": decision.dataset_summary,
        }
    }


# =========================================================
# BOT / ANALYZER FORMATTER
# =========================================================

def format_late_expansion_decision_for_bot(decision: LateExpansionDecision) -> str:
    icon = {
        "HOLD_CORE": "🟢",
        "FAST_SCALE_OUT": "📤",
        "QUICK_SCALP": "⚡",
        "AVOID_ENTRY": "⛔",
    }.get(decision.management_style, "⚪")

    lines = [
        f"{icon} LATE EXPANSION AI DECISION",
        f"Setup: {decision.setup_name}",
        f"Grade: {decision.setup_grade}",
        f"Bias: {decision.setup_bias}",
        f"Entry Quality: {decision.entry_quality}",
        f"Management Style: {decision.management_style}",
        f"Confidence: {decision.confidence_score}",
        f"Force Fast Profits: {'YES' if decision.force_fast_profits else 'NO'}",
        f"Force Tight Risk: {'YES' if decision.force_tight_risk else 'NO'}",
        f"Continuation Required: {'YES' if decision.continuation_required else 'NO'}",
        f"Lesson Label: {decision.lesson_label}",
    ]

    if decision.reasons:
        lines.append("Reasons:")
        for r in decision.reasons:
            lines.append(f" - {r}")

    lines.append("Dataset Summary:")
    lines.append(decision.dataset_summary)

    return "\n".join(lines)


# =========================================================
# PIPELINE FEATURE EXPORT
# =========================================================

def build_late_expansion_pipeline_features(decision: LateExpansionDecision) -> Dict[str, Any]:
    return {
        "late_expansion_setup_name": decision.setup_name,
        "late_expansion_grade": decision.setup_grade,
        "late_expansion_bias": decision.setup_bias,
        "late_expansion_entry_quality": decision.entry_quality,
        "late_expansion_management_style": decision.management_style,
        "late_expansion_confidence": decision.confidence_score,
        "late_expansion_force_fast_profits": decision.force_fast_profits,
        "late_expansion_force_tight_risk": decision.force_tight_risk,
        "late_expansion_continuation_required": decision.continuation_required,
        "late_expansion_lesson_label": decision.lesson_label,
    }


# =========================================================
# ONE-SHOT RUNNER
# =========================================================

def run_late_expansion_trade_brain(ctx: LateExpansionTradeContext) -> Dict[str, Any]:
    decision = evaluate_late_expansion_trade(ctx)
    training_example = build_late_expansion_training_example(ctx, decision)
    pipeline_features = build_late_expansion_pipeline_features(decision)

    return {
        "context": ctx,
        "decision": decision,
        "decision_dict": asdict(decision),
        "training_example": training_example,
        "pipeline_features": pipeline_features,
        "bot_text": format_late_expansion_decision_for_bot(decision),
    }


# =========================================================
# EXAMPLE: YOUR QQQ 628 CALL (0DTE)
# =========================================================

LATE_EXPANSION_INPUT = LateExpansionTradeContext(
    symbol="QQQ",
    current_price=626.80,
    option_symbol="QQQ 628C",
    option_type="CALL",
    same_day_expiration=True,

    above_vwap=True,
    above_emas=True,
    strong_higher_lows=True,
    bullish_structure=True,

    strong_green_candles=True,
    expansion_phase_active=True,
    macd_bullish=True,
    momentum_continuation_only=True,

    tagged_upper_bollinger=True,
    tagged_lower_bollinger=False,
    entered_at_top_of_move=True,
    entered_at_value_zone=False,
    pullback_entry=False,
    ema_retest_entry=False,
    vwap_reclaim_entry=False,
    break_retest_go_entry=False,

    rsi=82.0,
    premium_expensive=True,
    reward_to_risk_weak=True,
    emotional_continuation_entry=True,

    strike=628.0,
    breakeven_price=628.29,

    ideal_entry_low=625.0,
    ideal_entry_high=625.5,
    risk_exit_low=625.8,
    risk_exit_high=626.0,
)


# =========================================================
# RUN
# =========================================================

late_expansion_results = run_late_expansion_trade_brain(LATE_EXPANSION_INPUT)

print("=== DECISION DICT ===")
print(json.dumps(late_expansion_results["decision_dict"], indent=2))

print("\n=== TRAINING EXAMPLE ===")
print(json.dumps(late_expansion_results["training_example"], indent=2))

print("\n=== PIPELINE FEATURES ===")
print(json.dumps(late_expansion_results["pipeline_features"], indent=2))

print("\n=== BOT OUTPUT ===")
print(late_expansion_results["bot_text"])

# =========================================================
# NEXT CELL: MERGE TRADE-MANAGEMENT LOGIC INTO LIVE PIPELINE
# Put this AFTER the B+ trade-management learning cell
# =========================================================

import copy
import json
import pandas as pd


# =========================================================
# CONFIG
# How strongly should trade-management logic influence final output?
# =========================================================

TRADE_MANAGEMENT_MERGE_CONFIG = {
    "enable_trade_management_override": True,

    # If management says EXIT_FULL, hard block new risk
    "full_exit_blocks_entry": True,

    # If management says TAKE_PARTIALS, reduce size materially
    "partials_size_multiplier": 0.55,

    # If management says AVOID_NEW_ENTRY, reduce confidence hard
    "avoid_new_entry_confidence_cap": 0.35,

    # confidence adjustments
    "force_profit_take_confidence_penalty": 0.10,
    "block_new_entry_confidence_penalty": 0.14,

    # downgrade behavior
    "downgrade_one_step_on_partials": True,
    "downgrade_one_step_on_avoid_new_entry": True,
}


# =========================================================
# GRADE HELPERS
# =========================================================

MANAGEMENT_GRADE_ORDER = ["A+", "A", "B+", "B", "C", "WAIT", "AVOID"]

def normalize_management_grade(grade: str) -> str:
    if grade in MANAGEMENT_GRADE_ORDER:
        return grade
    return "AVOID"

def management_grade_index(grade: str) -> int:
    return MANAGEMENT_GRADE_ORDER.index(normalize_management_grade(grade))

def management_downgrade_grade_one_step(grade: str) -> str:
    idx = management_grade_index(grade)
    return MANAGEMENT_GRADE_ORDER[min(len(MANAGEMENT_GRADE_ORDER) - 1, idx + 1)]


# =========================================================
# CONTEXT BUILDER FROM INPUTS
# =========================================================

def build_trade_management_context_from_inputs(inputs: dict) -> TradeManagementContext:
    return TradeManagementContext(
        symbol=inputs["symbol"],
        current_price=float(inputs["price"]),
        option_symbol=inputs.get("option_symbol", f"{inputs['symbol']} option"),
        option_type=inputs.get("option_type", "CALL"),
        same_day_expiration=bool(inputs.get("same_day_expiration", False)),

        bullish_structure=bool(inputs.get("bullish_structure", False)),
        above_vwap=bool(inputs.get("above_vwap", False)),
        above_short_ma=bool(inputs.get("above_short_ma", False)),
        higher_highs_higher_lows=bool(inputs.get("higher_highs_higher_lows", False)),
        risk_on_intraday=bool(inputs.get("risk_on_intraday", False)),

        dark_pool_supports=list(inputs.get("dark_pool_supports", [])),
        dark_pool_resistances=list(inputs.get("dark_pool_resistances", [])),

        rsi=float(inputs.get("rsi", 50.0)),
        macd_extended=bool(inputs.get("macd_extended", False)),
        macd_fresh=bool(inputs.get("macd_fresh", False)),

        small_bodies_present=bool(inputs.get("small_bodies_present", False)),
        upper_wicks_present=bool(inputs.get("upper_wicks_present", False)),
        hesitation_candles_present=bool(inputs.get("hesitation_candles_present", False)),

        near_upper_band=bool(inputs.get("near_upper_band", False)),
        near_lower_band=bool(inputs.get("near_lower_band", False)),
        extended_from_vwap=bool(inputs.get("extended_from_vwap", False)),
        entering_resistance_zone=bool(inputs.get("entering_resistance_zone", False)),
        entering_support_zone=bool(inputs.get("entering_support_zone", False)),

        hour=int(inputs.get("hour", 10)),
        minute=int(inputs.get("minute", 0)),

        premium_fragile=bool(inputs.get("premium_fragile", False)),
        near_strike=bool(inputs.get("near_strike", False)),

        sell_zone_low=float(inputs.get("sell_zone_low", 612.40)),
        sell_zone_high=float(inputs.get("sell_zone_high", 612.50)),
    )


# =========================================================
# MERGE ENGINE
# =========================================================

def merge_trade_management_into_inputs(
    base_inputs: dict,
    merge_config: dict = None
) -> dict:
    if merge_config is None:
        merge_config = TRADE_MANAGEMENT_MERGE_CONFIG

    merged = copy.deepcopy(base_inputs)

    if not merge_config.get("enable_trade_management_override", True):
        merged["_trade_management_merge_note"] = "Trade-management override disabled."
        return merged

    tm_ctx = build_trade_management_context_from_inputs(merged)
    tm_results = run_bplus_trade_management_brain(tm_ctx)
    tm_decision = tm_results["decision"]
    tm_decision_dict = tm_results["decision_dict"]
    tm_pipeline = tm_results["pipeline_features"]

    merged["_trade_management_decision"] = tm_decision_dict
    merged["_trade_management_pipeline_features"] = tm_pipeline

    # start from existing inputs
    current_grade = normalize_management_grade(merged.get("trade_grade", "AVOID"))
    current_conf = float(merged.get("ai_confidence", 0.50))
    current_setup = float(merged.get("setup_score", 0.50))
    current_entry = float(merged.get("entry_quality_score", 0.50))

    action = tm_decision.management_action

    # EXIT_FULL = hard block if configured
    if action == "EXIT_FULL" and merge_config.get("full_exit_blocks_entry", True):
        merged["direction"] = "FLAT"
        merged["trade_grade"] = "AVOID"
        merged["ai_confidence"] = 0.10
        merged["setup_score"] = min(current_setup, 0.30)
        merged["entry_quality_score"] = min(current_entry, 0.20)
        merged["_trade_management_merge_note"] = (
            "Trade-management merged: EXIT_FULL triggered. "
            "New risk blocked due to forced full exit conditions."
        )
        return merged

    # TAKE_PARTIALS = reduce size quality / downgrade some
    if action == "TAKE_PARTIALS":
        current_conf -= merge_config["force_profit_take_confidence_penalty"]
        current_entry *= merge_config["partials_size_multiplier"]

        if merge_config.get("downgrade_one_step_on_partials", True):
            current_grade = management_downgrade_grade_one_step(current_grade)

    # AVOID_NEW_ENTRY = hard confidence cap + downgrade
    if action == "AVOID_NEW_ENTRY":
        current_conf -= merge_config["block_new_entry_confidence_penalty"]
        current_conf = min(current_conf, merge_config["avoid_new_entry_confidence_cap"])
        current_setup = min(current_setup, 0.45)
        current_entry = min(current_entry, 0.35)

        if merge_config.get("downgrade_one_step_on_avoid_new_entry", True):
            current_grade = management_downgrade_grade_one_step(current_grade)

    # HOLD still can add metadata without override
    merged["trade_grade"] = current_grade if current_grade in {"A+", "A", "B+", "B"} else "AVOID"
    merged["ai_confidence"] = round(clamp(current_conf, 0.0, 1.0), 3)
    merged["setup_score"] = round(clamp(current_setup, 0.0, 1.0), 3)
    merged["entry_quality_score"] = round(clamp(current_entry, 0.0, 1.0), 3)

    merged["_trade_management_merge_note"] = (
        f"Trade-management merged: action={action}, "
        f"grade={tm_decision.setup_grade}, conf={tm_decision.confidence_score}, "
        f"force_profit_take={tm_decision.should_force_profit_take}, "
        f"block_new_entry={tm_decision.should_block_new_entry}"
    )

    return merged


# =========================================================
# LIVE RUNNER WITH TRADE MANAGEMENT
# =========================================================

def run_live_trade_case_with_trade_management(
    memory: MemoryStore,
    inputs: dict,
    merge_config: dict = None,
):
    merged_inputs = merge_trade_management_into_inputs(inputs, merge_config=merge_config)

    live_results = run_live_trade_case(
        memory=memory,
        inputs=merged_inputs,
    )

    live_results["trade_management_decision"] = merged_inputs.get("_trade_management_decision", {})
    live_results["trade_management_pipeline_features"] = merged_inputs.get("_trade_management_pipeline_features", {})
    live_results["trade_management_merge_note"] = merged_inputs.get("_trade_management_merge_note", "")
    live_results["merged_inputs"] = merged_inputs

    return live_results


# =========================================================
# WATCHLIST RUNNER WITH TRADE MANAGEMENT
# =========================================================

def run_watchlist_cases_with_trade_management(
    memory: MemoryStore,
    base_inputs: dict,
    watchlist_cases: list,
    merge_config: dict = None,
):
    all_results = []

    for case in watchlist_cases:
        case_name = case.get("case_name", "Unnamed Case")
        case_inputs = build_case_inputs(base_inputs, case)

        try:
            results = run_live_trade_case_with_trade_management(
                memory=memory,
                inputs=case_inputs,
                merge_config=merge_config,
            )

            verdict = results["rl_augmented_verdict"]
            tm_decision = results.get("trade_management_decision", {})

            row = {
                "case_name": case_name,
                "symbol": case_inputs["symbol"],
                "direction": results["merged_inputs"]["direction"],
                "setup_name": case_inputs["setup_name"],
                "status": verdict.final_status,
                "grade": verdict.final_grade,
                "blocked": verdict.blocked,
                "final_ai_confidence": verdict.final_ai_confidence,
                "final_size_fraction": verdict.final_size_fraction,
                "rl_agent": verdict.selected_rl_agent,
                "rl_regime_bias": verdict.rl_regime_bias,
                "rl_confidence": verdict.rl_ensemble_confidence,

                "management_action": tm_decision.get("management_action", ""),
                "management_grade": tm_decision.get("setup_grade", ""),
                "management_force_profit_take": tm_decision.get("should_force_profit_take", False),
                "management_block_new_entry": tm_decision.get("should_block_new_entry", False),

                "approved_for_execution": verdict.approved_for_execution,
                "should_alert_discord": verdict.should_alert_discord,
                "opportunity_score": compute_watchlist_opportunity_score(verdict),
                "top_reason": verdict.reasons[0] if verdict.reasons else "",
                "top_warning": verdict.warnings[0] if verdict.warnings else "",
                "top_blocker": verdict.blockers[0] if verdict.blockers else "",
                "management_note": results.get("trade_management_merge_note", ""),
                "raw_results": results,
            }

        except Exception as e:
            row = {
                "case_name": case_name,
                "symbol": case.get("symbol", ""),
                "direction": case.get("direction", ""),
                "setup_name": case.get("setup_name", ""),
                "status": "ERROR",
                "grade": "AVOID",
                "blocked": True,
                "final_ai_confidence": 0.0,
                "final_size_fraction": 0.0,
                "rl_agent": "",
                "rl_regime_bias": "",
                "rl_confidence": 0.0,
                "management_action": "",
                "management_grade": "",
                "management_force_profit_take": False,
                "management_block_new_entry": False,
                "approved_for_execution": False,
                "should_alert_discord": False,
                "opportunity_score": -9999.0,
                "top_reason": "",
                "top_warning": "",
                "top_blocker": str(e),
                "management_note": "Error",
                "raw_results": None,
            }

        all_results.append(row)

    return all_results


# =========================================================
# DISPLAY HELPERS
# =========================================================

def print_live_trade_case_with_trade_management_summary(results: dict):
    market = results["market"]
    signal = results["signal"]
    rl_decision = results["rl_decision"]
    rl_augmented_verdict = results["rl_augmented_verdict"]

    print("=== TRADE-MANAGEMENT MERGE NOTE ===")
    print(results.get("trade_management_merge_note", ""))

    print("\n=== TRADE-MANAGEMENT DECISION ===")
    print(json.dumps(results.get("trade_management_decision", {}), indent=2))

    print("\n=== TRADE-MANAGEMENT PIPELINE FEATURES ===")
    print(json.dumps(results.get("trade_management_pipeline_features", {}), indent=2))

    print("\n=== RL DECISION ===")
    print(json.dumps(rl_decision_to_dict(rl_decision), indent=2))

    print("\n=== FINAL RL-AUGMENTED VERDICT ===")
    print(json.dumps(rl_augmented_verdict_to_dict(rl_augmented_verdict), indent=2))

    print("\n=== FINAL ALERT ===")
    print(format_rl_augmented_alert(market, signal, rl_augmented_verdict))


def trade_management_watchlist_results_to_dataframe(results: list) -> pd.DataFrame:
    if not results:
        return pd.DataFrame()

    df = pd.DataFrame([
        {k: v for k, v in r.items() if k != "raw_results"}
        for r in results
    ])

    if not df.empty:
        df = df.sort_values(
            by=["blocked", "opportunity_score", "final_size_fraction", "final_ai_confidence"],
            ascending=[True, False, False, False]
        ).reset_index(drop=True)

    return df


def print_watchlist_summary_with_trade_management(results: list):
    df = trade_management_watchlist_results_to_dataframe(results)

    if df.empty:
        print("No watchlist results.")
        return

    print("=== WATCHLIST RANKING WITH TRADE MANAGEMENT ===")
    print(df.to_string(index=False))

    valid = [r for r in results if r.get("raw_results") is not None]
    if valid:
        best = sorted(valid, key=lambda x: x["opportunity_score"], reverse=True)[0]
        print("\n=== TOP OPPORTUNITY ===")
        print(json.dumps({
            "case_name": best["case_name"],
            "symbol": best["symbol"],
            "direction": best["direction"],
            "setup_name": best["setup_name"],
            "status": best["status"],
            "grade": best["grade"],
            "blocked": best["blocked"],
            "final_ai_confidence": best["final_ai_confidence"],
            "final_size_fraction": best["final_size_fraction"],
            "rl_agent": best["rl_agent"],
            "rl_regime_bias": best["rl_regime_bias"],
            "rl_confidence": best["rl_confidence"],
            "management_action": best["management_action"],
            "management_grade": best["management_grade"],
            "management_force_profit_take": best["management_force_profit_take"],
            "management_block_new_entry": best["management_block_new_entry"],
            "approved_for_execution": best["approved_for_execution"],
            "opportunity_score": best["opportunity_score"],
            "top_reason": best["top_reason"],
            "top_warning": best["top_warning"],
            "top_blocker": best["top_blocker"],
            "management_note": best["management_note"],
        }, indent=2))


# =========================================================
# OPTIONAL EXAMPLE INPUTS
# Add into LIVE_INPUTS / WATCHLIST if not already there
# =========================================================

TRADE_MANAGEMENT_FIELDS_EXAMPLE = {
    "option_symbol": "QQQ 613C",
    "option_type": "CALL",
    "same_day_expiration": True,

    "bullish_structure": True,
    "above_vwap": True,
    "above_short_ma": True,
    "higher_highs_higher_lows": True,
    "risk_on_intraday": True,

    "dark_pool_supports": [609.80, 610.20, 610.70],
    "dark_pool_resistances": [611.00, 611.08, 611.40, 611.56, 612.74, 613.21],

    "rsi": 68.5,
    "macd_extended": True,
    "macd_fresh": False,

    "small_bodies_present": True,
    "upper_wicks_present": True,
    "hesitation_candles_present": True,

    "near_upper_band": True,
    "near_lower_band": False,
    "extended_from_vwap": True,
    "entering_resistance_zone": True,
    "entering_support_zone": False,

    "hour": 11,
    "minute": 30,

    "premium_fragile": True,
    "near_strike": True,

    "sell_zone_low": 612.40,
    "sell_zone_high": 612.50,
}


# =========================================================
# RUN SINGLE CASE
# Assumes LIVE_INPUTS exists
# =========================================================

live_inputs_with_trade_management = copy.deepcopy(LIVE_INPUTS)
live_inputs_with_trade_management.update(TRADE_MANAGEMENT_FIELDS_EXAMPLE)

live_results_with_trade_management = run_live_trade_case_with_trade_management(
    memory=memory,
    inputs=live_inputs_with_trade_management,
    merge_config=TRADE_MANAGEMENT_MERGE_CONFIG,
)

print_live_trade_case_with_trade_management_summary(live_results_with_trade_management)


# =========================================================
# RUN WATCHLIST
# Assumes WATCHLIST_CASES exists
# =========================================================

watchlist_results_with_trade_management = run_watchlist_cases_with_trade_management(
    memory=memory,
    base_inputs=live_inputs_with_trade_management,
    watchlist_cases=WATCHLIST_CASES,
    merge_config=TRADE_MANAGEMENT_MERGE_CONFIG,
)

print("\n")
print_watchlist_summary_with_trade_management(watchlist_results_with_trade_management)

# =========================================================
# AI LEARNING CODE: B+ CONTINUATION + SELL INTO 612.50 WALL
# ONE-CELL VERSION
# =========================================================
# PURPOSE:
# Teach the AI that a bullish continuation can still be only B+,
# and that 612.40 - 612.50 can be a forced profit-taking zone
# when dark pool resistance + extended momentum + late morning
# all line up.
#
# CORE LESSON:
# You were right on direction.
# You needed to get paid at the right location.
#
# MAIN RULE:
# If price enters known dark pool resistance
# AND RSI is elevated
# AND MACD is extended
# AND time is late morning
# => force profit take (partial or full)
# =========================================================

from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional
import json


# =========================================================
# DATA MODELS
# =========================================================

@dataclass
class TradeManagementContext:
    symbol: str
    current_price: float
    option_symbol: str
    option_type: str                  # CALL / PUT
    same_day_expiration: bool

    # structure / bias
    bullish_structure: bool = False
    above_vwap: bool = False
    above_short_ma: bool = False
    higher_highs_higher_lows: bool = False
    risk_on_intraday: bool = False

    # institutional / dark pool zones
    dark_pool_supports: List[float] = field(default_factory=list)
    dark_pool_resistances: List[float] = field(default_factory=list)

    # momentum
    rsi: float = 50.0
    macd_extended: bool = False
    macd_fresh: bool = False

    # candle behavior
    small_bodies_present: bool = False
    upper_wicks_present: bool = False
    hesitation_candles_present: bool = False

    # price location
    near_upper_band: bool = False
    near_lower_band: bool = False
    extended_from_vwap: bool = False
    entering_resistance_zone: bool = False
    entering_support_zone: bool = False

    # time of day
    hour: int = 10
    minute: int = 0

    # option-specific context
    premium_fragile: bool = False
    near_strike: bool = False

    # example zone
    sell_zone_low: float = 612.40
    sell_zone_high: float = 612.50


@dataclass
class TradeManagementDecision:
    setup_grade: str                  # A+ / A / B+ / B / AVOID
    setup_bias: str                   # BULLISH / BEARISH / NEUTRAL
    management_action: str            # HOLD / TAKE_PARTIALS / EXIT_FULL / AVOID_NEW_ENTRY
    should_force_profit_take: bool
    should_block_new_entry: bool
    confidence_score: float
    reason: List[str]
    lesson_label: str
    dataset_summary: str


# =========================================================
# HELPERS
# =========================================================

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def within_range(x: float, low: float, high: float) -> bool:
    return low <= x <= high


def is_late_morning_dead_zone(hour: int, minute: int) -> bool:
    total_minutes = hour * 60 + minute
    # roughly 11:15 to 12:15 ET style "dead zone"
    return 11 * 60 + 15 <= total_minutes <= 12 * 60 + 15


def is_rsi_elevated(rsi: float) -> bool:
    return rsi >= 65


def is_rsi_extreme(rsi: float) -> bool:
    return rsi >= 70


def near_dark_pool_resistance(price: float, resistance_levels: List[float], tolerance: float = 0.18) -> bool:
    for level in resistance_levels:
        if abs(price - level) <= tolerance:
            return True
    return False


def resistance_cluster_density(price: float, resistance_levels: List[float], cluster_tolerance: float = 1.0) -> int:
    return sum(1 for level in resistance_levels if abs(price - level) <= cluster_tolerance)


# =========================================================
# SETUP GRADING
# =========================================================

def grade_bullish_continuation(ctx: TradeManagementContext) -> str:
    score = 0

    if ctx.bullish_structure:
        score += 2
    if ctx.above_vwap:
        score += 1
    if ctx.above_short_ma:
        score += 1
    if ctx.higher_highs_higher_lows:
        score += 2
    if ctx.risk_on_intraday:
        score += 1
    if len(ctx.dark_pool_supports) >= 2:
        score += 1

    # penalties
    if ctx.entering_resistance_zone:
        score -= 1
    if ctx.near_upper_band:
        score -= 1
    if is_rsi_elevated(ctx.rsi):
        score -= 1
    if ctx.macd_extended and not ctx.macd_fresh:
        score -= 1
    if is_late_morning_dead_zone(ctx.hour, ctx.minute):
        score -= 1

    if score >= 7:
        return "A"
    if score >= 5:
        return "B+"
    if score >= 3:
        return "B"
    return "AVOID"


# =========================================================
# SELL / TAKE-PROFIT RULES
# =========================================================

def detect_forced_profit_take(ctx: TradeManagementContext) -> Dict[str, Any]:
    reasons = []
    score = 0

    in_sell_zone = within_range(ctx.current_price, ctx.sell_zone_low, ctx.sell_zone_high)
    dense_resistance = resistance_cluster_density(ctx.current_price, ctx.dark_pool_resistances) >= 2
    near_resistance = near_dark_pool_resistance(ctx.current_price, ctx.dark_pool_resistances)

    if in_sell_zone:
        score += 2
        reasons.append("Price entered the 612.40 - 612.50 sell zone.")

    if near_resistance:
        score += 2
        reasons.append("Price is at a known dark pool resistance level.")

    if dense_resistance:
        score += 1
        reasons.append("Price is inside a dense institutional resistance cluster.")

    if is_rsi_elevated(ctx.rsi):
        score += 1
        reasons.append("RSI is elevated.")

    if is_rsi_extreme(ctx.rsi):
        score += 1
        reasons.append("RSI is near/exceeding 70.")

    if ctx.macd_extended:
        score += 1
        reasons.append("MACD is extended, not fresh.")

    if ctx.small_bodies_present or ctx.upper_wicks_present or ctx.hesitation_candles_present:
        score += 1
        reasons.append("Candle behavior shows stall / hesitation.")

    if is_late_morning_dead_zone(ctx.hour, ctx.minute):
        score += 1
        reasons.append("Time of day is late morning dead zone.")

    if ctx.same_day_expiration:
        score += 1
        reasons.append("Same-day expiration increases premium fragility.")

    if ctx.premium_fragile:
        score += 1
        reasons.append("Option premium is fragile.")

    if ctx.near_strike:
        score += 1
        reasons.append("Contract is near strike, so stalling can hurt quickly.")

    force_take_profit = score >= 6
    force_full_exit = score >= 8

    return {
        "force_take_profit": force_take_profit,
        "force_full_exit": force_full_exit,
        "score": score,
        "reasons": reasons,
    }


def detect_block_new_call_entry(ctx: TradeManagementContext) -> Dict[str, Any]:
    reasons = []
    score = 0

    if ctx.option_type == "CALL" and ctx.entering_resistance_zone:
        score += 2
        reasons.append("New call would be entering resistance.")

    if ctx.near_upper_band:
        score += 1
        reasons.append("Price is near the upper band.")

    if is_rsi_elevated(ctx.rsi):
        score += 1
        reasons.append("RSI already elevated for a fresh long.")

    if ctx.macd_extended and not ctx.macd_fresh:
        score += 1
        reasons.append("MACD is mature, not fresh.")

    if is_late_morning_dead_zone(ctx.hour, ctx.minute):
        score += 1
        reasons.append("Time of day reduces continuation quality.")

    if ctx.same_day_expiration:
        score += 1
        reasons.append("Same-day options punish stalls and chop.")

    return {
        "block_new_entry": score >= 4,
        "score": score,
        "reasons": reasons,
    }


# =========================================================
# MAIN AI LEARNING DECISION
# =========================================================

def evaluate_bplus_continuation_and_sell_rule(ctx: TradeManagementContext) -> TradeManagementDecision:
    reasons: List[str] = []

    setup_grade = grade_bullish_continuation(ctx)
    setup_bias = "BULLISH" if ctx.bullish_structure else "NEUTRAL"

    if ctx.bullish_structure:
        reasons.append("Broader intraday structure is bullish.")
    if ctx.above_vwap:
        reasons.append("Price remains above VWAP.")
    if ctx.higher_highs_higher_lows:
        reasons.append("Higher highs / higher lows support continuation.")
    if len(ctx.dark_pool_supports) >= 2:
        reasons.append("Dark pool support exists underneath.")

    # key risk logic
    forced_profit = detect_forced_profit_take(ctx)
    blocked_entry = detect_block_new_call_entry(ctx)

    reasons.extend(forced_profit["reasons"])
    reasons.extend(blocked_entry["reasons"])

    if forced_profit["force_full_exit"]:
        action = "EXIT_FULL"
        lesson_label = "SELL_INTO_DARK_POOL_WALL_FULL_EXIT"
    elif forced_profit["force_take_profit"]:
        action = "TAKE_PARTIALS"
        lesson_label = "SELL_INTO_DARK_POOL_WALL_PARTIAL"
    elif blocked_entry["block_new_entry"]:
        action = "AVOID_NEW_ENTRY"
        lesson_label = "LATE_CONTINUATION_BLOCKED"
    else:
        action = "HOLD"
        lesson_label = "CONTINUATION_STILL_VALID"

    confidence = 0.55

    if setup_grade == "A":
        confidence = 0.82
    elif setup_grade == "B+":
        confidence = 0.72
    elif setup_grade == "B":
        confidence = 0.58
    elif setup_grade == "AVOID":
        confidence = 0.20

    # management confidence gets stronger if forced-exit conditions stack
    confidence += min(0.20, forced_profit["score"] * 0.02)
    confidence += min(0.12, blocked_entry["score"] * 0.02)
    confidence = clamp(confidence, 0.0, 1.0)

    dataset_summary = (
        "This was a B+ bullish continuation setup because structure remained bullish, "
        "price stayed above VWAP and short-term support, and dark pool support below remained valid. "
        "However, the trade became risky because price entered a dense institutional resistance zone "
        "around 612.40 - 612.50, RSI was elevated, MACD was extended, and time of day shifted into "
        "late-morning dead-zone conditions. That reduced reward-to-risk for calls and increased the "
        "probability of stall, chop, or premium decay. The correct AI lesson is to pay yourself into "
        "known resistance rather than hold fragile premium through an institutional wall."
    )

    return TradeManagementDecision(
        setup_grade=setup_grade,
        setup_bias=setup_bias,
        management_action=action,
        should_force_profit_take=forced_profit["force_take_profit"],
        should_block_new_entry=blocked_entry["block_new_entry"],
        confidence_score=round(confidence, 3),
        reason=reasons,
        lesson_label=lesson_label,
        dataset_summary=dataset_summary,
    )


# =========================================================
# TRAINING EXPORT
# =========================================================

def build_bplus_trade_management_training_example(ctx: TradeManagementContext, decision: TradeManagementDecision) -> Dict[str, Any]:
    return {
        "features": {
            "symbol": ctx.symbol,
            "current_price": ctx.current_price,
            "option_symbol": ctx.option_symbol,
            "option_type": ctx.option_type,
            "same_day_expiration": int(ctx.same_day_expiration),

            "bullish_structure": int(ctx.bullish_structure),
            "above_vwap": int(ctx.above_vwap),
            "above_short_ma": int(ctx.above_short_ma),
            "higher_highs_higher_lows": int(ctx.higher_highs_higher_lows),
            "risk_on_intraday": int(ctx.risk_on_intraday),

            "dark_pool_supports": ctx.dark_pool_supports,
            "dark_pool_resistances": ctx.dark_pool_resistances,

            "rsi": ctx.rsi,
            "macd_extended": int(ctx.macd_extended),
            "macd_fresh": int(ctx.macd_fresh),

            "small_bodies_present": int(ctx.small_bodies_present),
            "upper_wicks_present": int(ctx.upper_wicks_present),
            "hesitation_candles_present": int(ctx.hesitation_candles_present),

            "near_upper_band": int(ctx.near_upper_band),
            "near_lower_band": int(ctx.near_lower_band),
            "extended_from_vwap": int(ctx.extended_from_vwap),
            "entering_resistance_zone": int(ctx.entering_resistance_zone),
            "entering_support_zone": int(ctx.entering_support_zone),

            "hour": ctx.hour,
            "minute": ctx.minute,

            "premium_fragile": int(ctx.premium_fragile),
            "near_strike": int(ctx.near_strike),

            "sell_zone_low": ctx.sell_zone_low,
            "sell_zone_high": ctx.sell_zone_high,
        },
        "label": {
            "setup_grade": decision.setup_grade,
            "setup_bias": decision.setup_bias,
            "management_action": decision.management_action,
            "should_force_profit_take": decision.should_force_profit_take,
            "should_block_new_entry": decision.should_block_new_entry,
            "confidence_score": decision.confidence_score,
            "lesson_label": decision.lesson_label,
            "reasons": decision.reason,
            "dataset_summary": decision.dataset_summary,
        }
    }


# =========================================================
# BOT / ANALYZER FORMATTER
# =========================================================

def format_trade_management_decision_for_bot(decision: TradeManagementDecision) -> str:
    icon = {
        "EXIT_FULL": "💰",
        "TAKE_PARTIALS": "📤",
        "AVOID_NEW_ENTRY": "⚠️",
        "HOLD": "🟢",
    }.get(decision.management_action, "⚪")

    lines = [
        f"{icon} TRADE MANAGEMENT AI DECISION",
        f"Setup Grade: {decision.setup_grade}",
        f"Setup Bias: {decision.setup_bias}",
        f"Management Action: {decision.management_action}",
        f"Force Profit Take: {'YES' if decision.should_force_profit_take else 'NO'}",
        f"Block New Entry: {'YES' if decision.should_block_new_entry else 'NO'}",
        f"Confidence: {decision.confidence_score}",
        f"Lesson Label: {decision.lesson_label}",
    ]

    if decision.reason:
        lines.append("Reasons:")
        for r in decision.reason:
            lines.append(f" - {r}")

    lines.append("Dataset Summary:")
    lines.append(decision.dataset_summary)

    return "\n".join(lines)


# =========================================================
# PIPELINE FEATURE EXPORT
# =========================================================

def build_trade_management_pipeline_features(decision: TradeManagementDecision) -> Dict[str, Any]:
    return {
        "management_setup_grade": decision.setup_grade,
        "management_setup_bias": decision.setup_bias,
        "management_action": decision.management_action,
        "management_confidence": decision.confidence_score,
        "management_force_profit_take": decision.should_force_profit_take,
        "management_block_new_entry": decision.should_block_new_entry,
        "management_lesson_label": decision.lesson_label,
    }


# =========================================================
# ONE-SHOT RUNNER
# =========================================================

def run_bplus_trade_management_brain(ctx: TradeManagementContext) -> Dict[str, Any]:
    decision = evaluate_bplus_continuation_and_sell_rule(ctx)
    training_example = build_bplus_trade_management_training_example(ctx, decision)
    pipeline_features = build_trade_management_pipeline_features(decision)

    return {
        "context": ctx,
        "decision": decision,
        "decision_dict": asdict(decision),
        "training_example": training_example,
        "pipeline_features": pipeline_features,
        "bot_text": format_trade_management_decision_for_bot(decision),
    }


# =========================================================
# EXAMPLE: YOUR 612.50 LESSON
# =========================================================

BPLUS_TRADE_MANAGEMENT_INPUT = TradeManagementContext(
    symbol="QQQ",
    current_price=612.48,
    option_symbol="QQQ 613C",
    option_type="CALL",
    same_day_expiration=True,

    bullish_structure=True,
    above_vwap=True,
    above_short_ma=True,
    higher_highs_higher_lows=True,
    risk_on_intraday=True,

    dark_pool_supports=[609.80, 610.20, 610.70],
    dark_pool_resistances=[611.00, 611.08, 611.40, 611.56, 612.74, 613.21],

    rsi=68.5,
    macd_extended=True,
    macd_fresh=False,

    small_bodies_present=True,
    upper_wicks_present=True,
    hesitation_candles_present=True,

    near_upper_band=True,
    near_lower_band=False,
    extended_from_vwap=True,
    entering_resistance_zone=True,
    entering_support_zone=False,

    hour=11,
    minute=30,

    premium_fragile=True,
    near_strike=True,

    sell_zone_low=612.40,
    sell_zone_high=612.50,
)


# =========================================================
# RUN
# =========================================================

bplus_results = run_bplus_trade_management_brain(BPLUS_TRADE_MANAGEMENT_INPUT)

print("=== DECISION DICT ===")
print(json.dumps(bplus_results["decision_dict"], indent=2))

print("\n=== TRAINING EXAMPLE ===")
print(json.dumps(bplus_results["training_example"], indent=2))

print("\n=== PIPELINE FEATURES ===")
print(json.dumps(bplus_results["pipeline_features"], indent=2))

print("\n=== BOT OUTPUT ===")
print(bplus_results["bot_text"])

# =========================================================
# QQQ 627.50 INSTITUTIONAL TRIGGER LOGIC
# CLEAN ONE-CELL VERSION
# =========================================================

from __future__ import annotations
from dataclasses import dataclass
from typing import List
import json


# =========================
# DATA MODELS
# =========================

@dataclass
class MarketContext:
    symbol: str
    current_price: float
    vwap: float
    rsi: float

    # key institutional / chart levels
    trigger_level: float = 627.50
    resistance_1: float = 629.00
    resistance_2: float = 630.00
    support_1: float = 626.00
    support_2: float = 624.50

    # optional higher-timeframe context
    above_vwap: bool = False
    below_vwap: bool = False
    near_upper_band: bool = False
    near_lower_band: bool = False

    # optional extension / location info
    distance_from_trigger: float = 0.0
    prior_move_extended: bool = False


@dataclass
class StructureState:
    # bullish confirmations
    hold_at_trigger: bool = False
    vwap_reclaimed: bool = False
    vwap_held: bool = False
    higher_low: bool = False
    retest_hold: bool = False
    breakout_candle_with_volume: bool = False

    # bearish confirmations
    rejection_at_resistance: bool = False
    lower_high: bool = False
    clean_break_below_trigger: bool = False
    acceptance_below_trigger: bool = False
    failed_bounce: bool = False

    # chase / discipline filters
    no_retest: bool = False
    multiple_same_color_bars_extended: bool = False
    entering_directly_into_resistance: bool = False
    entering_directly_into_support: bool = False


@dataclass
class TradeDecision:
    ticker: str
    bias: str  # CALL / PUT / NO TRADE
    grade: str  # A+ / A / B / AVOID
    setup_name: str
    trigger_level: float
    entry_zone: str
    targets: List[str]
    invalidation: str
    reason: List[str]
    is_chasing: bool
    alert_text: str


# =========================
# HELPERS
# =========================

def approx_equal(a: float, b: float, tol: float = 0.12) -> bool:
    return abs(a - b) <= tol


def within_range(x: float, low: float, high: float) -> bool:
    return low <= x <= high


def is_testing_trigger(price: float, trigger: float, tol: float = 0.20) -> bool:
    return abs(price - trigger) <= tol


def calls_chasing(ctx: MarketContext, st: StructureState) -> bool:
    flags = 0

    if ctx.current_price > ctx.trigger_level + 0.80:
        flags += 1

    if ctx.rsi >= 72:
        flags += 1

    if ctx.near_upper_band:
        flags += 1

    if st.no_retest:
        flags += 1

    if st.multiple_same_color_bars_extended:
        flags += 1

    if st.entering_directly_into_resistance:
        flags += 1

    return flags >= 2


def puts_chasing(ctx: MarketContext, st: StructureState) -> bool:
    flags = 0

    if ctx.current_price < ctx.trigger_level - 0.80:
        flags += 1

    if ctx.rsi <= 28:
        flags += 1

    if ctx.near_lower_band:
        flags += 1

    if st.no_retest:
        flags += 1

    if st.multiple_same_color_bars_extended:
        flags += 1

    if st.entering_directly_into_support:
        flags += 1

    return flags >= 2


# =========================
# CORE LOGIC
# =========================

def make_qqq_62750_decision(ctx: MarketContext, st: StructureState) -> TradeDecision:
    """
    Exact setup logic for:
    - Bullish continuation if 627.50 holds and confirms
    - Bearish unwind if 627.50 fails and accepts below
    """
    reasons: List[str] = []

    # -------------------------
    # BULLISH CONDITIONS
    # -------------------------
    bull_confirmations = 0

    if st.hold_at_trigger:
        bull_confirmations += 1
        reasons.append("Price is holding at the 627.50 institutional trigger.")

    if st.vwap_reclaimed or st.vwap_held:
        bull_confirmations += 1
        reasons.append("VWAP is aligned with the long idea.")

    if st.higher_low:
        bull_confirmations += 1
        reasons.append("Higher low confirms buyers defending the level.")

    if st.retest_hold:
        bull_confirmations += 1
        reasons.append("Retest held after initial reaction.")

    if st.breakout_candle_with_volume:
        bull_confirmations += 1
        reasons.append("Breakout candle with volume confirms continuation.")

    bull_chasing = calls_chasing(ctx, st)

    # A+ CALL
    if (
        is_testing_trigger(ctx.current_price, ctx.trigger_level, tol=0.30)
        and bull_confirmations >= 4
        and not bull_chasing
    ):
        return TradeDecision(
            ticker=ctx.symbol,
            bias="CALL",
            grade="A+",
            setup_name="627.50 Hold + VWAP Confirmation",
            trigger_level=ctx.trigger_level,
            entry_zone="627.40 - 627.70 after hold/reclaim confirmation",
            targets=["629.00", "630.00", "631.00+"],
            invalidation="Lose 627.50 cleanly and accept below VWAP",
            reason=reasons,
            is_chasing=False,
            alert_text=(
                "💎 A+ QQQ CALL ALERT\n\n"
                f"Trigger: {ctx.trigger_level:.2f}\n"
                f"Price: {ctx.current_price:.2f}\n"
                "Setup: Institutional hold + VWAP alignment\n\n"
                "Entry Logic:\n"
                "- 627.50 is holding\n"
                "- VWAP confirms\n"
                "- Structure is forming a higher low / retest hold\n\n"
                "Targets:\n"
                "- 629.00\n"
                "- 630.00\n"
                "- 631.00+\n\n"
                "Invalidation:\n"
                "- Clean loss of 627.50\n"
                "- Acceptance below VWAP"
            ),
        )

    # Late long above trigger
    if (
        ctx.current_price > ctx.trigger_level + 0.30
        and ctx.current_price <= ctx.resistance_1
        and bull_confirmations >= 2
    ):
        return TradeDecision(
            ticker=ctx.symbol,
            bias="CALL",
            grade="B" if bull_chasing else "A",
            setup_name="Late Long Above 627.50",
            trigger_level=ctx.trigger_level,
            entry_zone="Only on pullback, not on extension",
            targets=["629.00", "630.00"],
            invalidation="Loss of intraday support / return under 627.50",
            reason=reasons + [
                "Long idea still has structure, but price is no longer at the best location."
            ],
            is_chasing=bull_chasing,
            alert_text=(
                "⚠️ QQQ LONG SETUP NOT AT IDEAL LOCATION\n\n"
                f"Price is above the key {ctx.trigger_level:.2f} trigger.\n"
                "This can still work, but reward/risk is worse here.\n\n"
                f"Grade: {'B' if bull_chasing else 'A'}\n"
                "Best action: wait for pullback or retest instead of chasing."
            ),
        )

    # -------------------------
    # BEARISH CONDITIONS
    # -------------------------
    bear_reasons: List[str] = []
    bear_confirmations = 0

    if st.clean_break_below_trigger:
        bear_confirmations += 1
        bear_reasons.append("627.50 broke cleanly.")

    if st.acceptance_below_trigger:
        bear_confirmations += 1
        bear_reasons.append("Price is accepting below the trigger, not just wicking it.")

    if st.lower_high:
        bear_confirmations += 1
        bear_reasons.append("Lower high confirms weak bounce structure.")

    if st.rejection_at_resistance:
        bear_confirmations += 1
        bear_reasons.append("Rejection formed before continuation lower.")

    if st.failed_bounce:
        bear_confirmations += 1
        bear_reasons.append("Bounce failed, showing weak demand.")

    bear_chasing = puts_chasing(ctx, st)

    # A+ PUT
    if (
        ctx.current_price < ctx.trigger_level
        and bear_confirmations >= 4
        and not bear_chasing
    ):
        return TradeDecision(
            ticker=ctx.symbol,
            bias="PUT",
            grade="A+",
            setup_name="627.50 Failure + Acceptance Below",
            trigger_level=ctx.trigger_level,
            entry_zone="627.40 down to 627.00 on failed reclaim / acceptance below",
            targets=["626.00", "624.50", "623.50"],
            invalidation="Reclaim of 627.50 and hold above VWAP",
            reason=bear_reasons,
            is_chasing=False,
            alert_text=(
                "💎 A+ QQQ PUT ALERT\n\n"
                f"Trigger: {ctx.trigger_level:.2f}\n"
                f"Price: {ctx.current_price:.2f}\n"
                "Setup: Institutional failure + acceptance below\n\n"
                "Entry Logic:\n"
                "- 627.50 failed\n"
                "- Price accepted below\n"
                "- Bounce is weak / lower high confirmed\n\n"
                "Targets:\n"
                "- 626.00\n"
                "- 624.50\n"
                "- 623.50\n\n"
                "Invalidation:\n"
                "- Strong reclaim of 627.50\n"
                "- Hold back above VWAP"
            ),
        )

    # Late short below trigger
    if (
        ctx.current_price < ctx.trigger_level - 0.50
        and bear_confirmations >= 2
    ):
        return TradeDecision(
            ticker=ctx.symbol,
            bias="PUT",
            grade="B" if bear_chasing else "A",
            setup_name="Late Short Below 627.50",
            trigger_level=ctx.trigger_level,
            entry_zone="Prefer failed reclaim, not extended breakdown",
            targets=["626.00", "624.50"],
            invalidation="Reclaim of 627.50",
            reason=bear_reasons + [
                "Short idea exists, but entry is no longer near the best location."
            ],
            is_chasing=bear_chasing,
            alert_text=(
                "⚠️ QQQ SHORT SETUP NOT AT IDEAL LOCATION\n\n"
                f"Price is already extended below the key {ctx.trigger_level:.2f} trigger.\n"
                f"Grade: {'B' if bear_chasing else 'A'}\n"
                "Best action: wait for failed reclaim instead of chasing breakdown."
            ),
        )

    # -------------------------
    # DEFAULT: NO TRADE
    # -------------------------
    return TradeDecision(
        ticker=ctx.symbol,
        bias="NO TRADE",
        grade="AVOID",
        setup_name="No clean trigger confirmation",
        trigger_level=ctx.trigger_level,
        entry_zone="None",
        targets=[],
        invalidation="None",
        reason=[
            "Price has not confirmed hold or failure at 627.50 with enough structure."
        ],
        is_chasing=False,
        alert_text=(
            "⛔ NO TRADE\n\n"
            "QQQ is around the decision zone, but structure is not clean enough yet.\n"
            "Wait for one of two things:\n"
            "- 627.50 hold + VWAP confirmation for calls\n"
            "- 627.50 failure + acceptance below for puts"
        ),
    )


# =========================
# DISCORD FORMATTER
# =========================

def format_discord_alert(decision: TradeDecision) -> str:
    reasons_text = "\n".join([f"- {r}" for r in decision.reason]) if decision.reason else "- None"
    targets_text = "\n".join([f"- {t}" for t in decision.targets]) if decision.targets else "- None"
    chasing_text = "YES" if decision.is_chasing else "NO"

    return (
        f"{decision.alert_text}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Ticker: {decision.ticker}\n"
        f"Bias: {decision.bias}\n"
        f"Grade: {decision.grade}\n"
        f"Setup: {decision.setup_name}\n"
        f"Trigger Level: {decision.trigger_level:.2f}\n"
        f"Entry Zone: {decision.entry_zone}\n"
        f"Targets:\n{targets_text}\n"
        f"Invalidation: {decision.invalidation}\n"
        f"Chasing: {chasing_text}\n"
        f"Reasons:\n{reasons_text}"
    )


# =========================
# EXAMPLE SCENARIOS
# =========================

# A+ CALL example
ctx_call = MarketContext(
    symbol="QQQ",
    current_price=627.56,
    vwap=627.42,
    rsi=64.8,
    above_vwap=True,
    near_upper_band=False,
)

st_call = StructureState(
    hold_at_trigger=True,
    vwap_reclaimed=True,
    vwap_held=True,
    higher_low=True,
    retest_hold=True,
    breakout_candle_with_volume=True,
    no_retest=False,
    multiple_same_color_bars_extended=False,
    entering_directly_into_resistance=False,
)

decision_call = make_qqq_62750_decision(ctx_call, st_call)
print("=== A+ CALL EXAMPLE ===")
print(format_discord_alert(decision_call))
print("\n" + "=" * 80 + "\n")

# B / chasing CALL example
ctx_b = MarketContext(
    symbol="QQQ",
    current_price=628.72,
    vwap=627.95,
    rsi=77.5,
    above_vwap=True,
    near_upper_band=True,
)

st_b = StructureState(
    hold_at_trigger=True,
    vwap_held=True,
    higher_low=True,
    no_retest=True,
    multiple_same_color_bars_extended=True,
    entering_directly_into_resistance=True,
)

decision_b = make_qqq_62750_decision(ctx_b, st_b)
print("=== LATE / CHASING CALL EXAMPLE ===")
print(format_discord_alert(decision_b))

print("\n=== RAW JSON ===")
print(json.dumps({
    "call_example": decision_call.__dict__,
    "late_call_example": decision_b.__dict__,
}, indent=2))

# =========================================================
# PATCH CELL: FIX DECISION TYPE COLLISION
# =========================================================
# Problem:
# - Multiple cells defined different "decision" dataclasses
# - One confidence function expected TradeDecision.is_chasing
# - But it received LogicDecision.chasing_blocked
#
# Fix:
# - Add safe confidence functions
# - Add a generic helper that works with either object
# - Rebind the 627.50 training / pipeline builders to use safe logic
# =========================================================

from typing import Any
import json


# =========================================================
# SAFE ATTRIBUTE HELPERS
# =========================================================

def safe_getattr(obj: Any, attr: str, default=None):
    return getattr(obj, attr, default)


def get_decision_chasing_flag(decision: Any) -> bool:
    """
    Works across:
    - TradeDecision -> is_chasing
    - LogicDecision -> chasing_blocked
    - anything else -> False
    """
    if hasattr(decision, "is_chasing"):
        return bool(getattr(decision, "is_chasing"))
    if hasattr(decision, "chasing_blocked"):
        return bool(getattr(decision, "chasing_blocked"))
    return False


# =========================================================
# SAFE 627.50 CONFIDENCE FUNCTION
# =========================================================

def decision_confidence_score_62750_safe(decision: Any, ctx: Any) -> float:
    score = 0.35

    grade = safe_getattr(decision, "grade", "AVOID")

    if grade == "A+":
        score = 0.95
    elif grade == "A":
        score = 0.82
    elif grade == "B":
        score = 0.62
    elif grade == "AVOID":
        score = 0.10
    elif grade == "WAIT":
        score = 0.20

    if get_decision_chasing_flag(decision):
        score -= 0.18

    if safe_getattr(ctx, "prior_move_extended", False):
        score -= 0.08

    rsi = safe_getattr(ctx, "rsi", None)
    if rsi is not None and (rsi >= 75 or rsi <= 25):
        score -= 0.06

    return round(clamp(score, 0.0, 1.0), 3)


# =========================================================
# PATCH 627.50 TRAINING EXPORT
# =========================================================

def build_62750_training_example(ctx: MarketContext, st: StructureState, decision: TradeDecision):
    label = TriggerTrainingLabel(
        pattern_name=decision.setup_name,
        bias=decision.bias,
        grade=decision.grade,
        valid_for_entry=decision.bias in ["CALL", "PUT"] and not get_decision_chasing_flag(decision) and decision.grade != "AVOID",
        confidence_score=decision_confidence_score_62750_safe(decision, ctx),
        reasons=decision.reason,
    )

    return {
        "features": {
            "symbol": ctx.symbol,
            "current_price": ctx.current_price,
            "vwap": ctx.vwap,
            "rsi": ctx.rsi,

            "trigger_level": ctx.trigger_level,
            "resistance_1": ctx.resistance_1,
            "resistance_2": ctx.resistance_2,
            "support_1": ctx.support_1,
            "support_2": ctx.support_2,

            "above_vwap": int(ctx.above_vwap),
            "below_vwap": int(ctx.below_vwap),
            "near_upper_band": int(ctx.near_upper_band),
            "near_lower_band": int(ctx.near_lower_band),
            "distance_from_trigger": ctx.distance_from_trigger,
            "prior_move_extended": int(ctx.prior_move_extended),

            "hold_at_trigger": int(st.hold_at_trigger),
            "vwap_reclaimed": int(st.vwap_reclaimed),
            "vwap_held": int(st.vwap_held),
            "higher_low": int(st.higher_low),
            "retest_hold": int(st.retest_hold),
            "breakout_candle_with_volume": int(st.breakout_candle_with_volume),

            "rejection_at_resistance": int(st.rejection_at_resistance),
            "lower_high": int(st.lower_high),
            "clean_break_below_trigger": int(st.clean_break_below_trigger),
            "acceptance_below_trigger": int(st.acceptance_below_trigger),
            "failed_bounce": int(st.failed_bounce),

            "no_retest": int(st.no_retest),
            "multiple_same_color_bars_extended": int(st.multiple_same_color_bars_extended),
            "entering_directly_into_resistance": int(st.entering_directly_into_resistance),
            "entering_directly_into_support": int(st.entering_directly_into_support),
        },
        "label": asdict(label),
    }


# =========================================================
# PATCH 627.50 PIPELINE FEATURES
# =========================================================

def build_62750_pipeline_features(ctx: MarketContext, decision: TradeDecision):
    direction = "FLAT"
    if decision.bias == "CALL":
        direction = "CALL"
    elif decision.bias == "PUT":
        direction = "PUT"

    mapped_grade = decision.grade if decision.grade in ["A+", "A", "B"] else "AVOID"
    confidence = decision_confidence_score_62750_safe(decision, ctx)
    setup_score = confidence
    entry_quality_score = 0.85 if not get_decision_chasing_flag(decision) else 0.35

    return {
        "trigger_62750_setup_name": decision.setup_name,
        "trigger_62750_bias": decision.bias,
        "trigger_62750_grade": decision.grade,
        "trigger_62750_confidence": confidence,
        "trigger_62750_is_chasing": get_decision_chasing_flag(decision),
        "trigger_62750_should_alert": decision.bias in ["CALL", "PUT"] and mapped_grade != "AVOID",

        "direction": direction,
        "trade_grade": mapped_grade,
        "ai_confidence": confidence,
        "setup_score": round(setup_score, 3),
        "entry_quality_score": round(entry_quality_score, 3),
        "macro_alignment_score": 0.50,
    }


# =========================================================
# PATCH 627.50 RUNNER
# =========================================================

def run_qqq_62750_brain(ctx: MarketContext, st: StructureState):
    decision = make_qqq_62750_decision(ctx, st)
    training_example = build_62750_training_example(ctx, st, decision)
    pipeline_features = build_62750_pipeline_features(ctx, decision)

    return {
        "context": ctx,
        "structure": st,
        "decision": decision,
        "decision_dict": asdict(decision),
        "training_example": training_example,
        "pipeline_features": pipeline_features,
        "bot_text": format_discord_alert(decision),
    }

print("✅ Patch applied: safe decision confidence + 627.50 builders rebound.")

# =========================================================
# NEXT CELL: UNIFIED MARKET-STRUCTURE SIGNAL MERGER
# Put this AFTER the 627.50 merge cell
# =========================================================

import copy
import json
from dataclasses import dataclass, asdict, field
from typing import Dict, Any, List


# =========================================================
# CONFIG
# =========================================================

UNIFIED_SIGNAL_CONFIG = {
    # module weights
    "base_weight": 0.30,
    "premarket_weight": 0.25,
    "range_print_weight": 0.20,
    "trigger_62750_weight": 0.25,

    # agreement / disagreement effects
    "strong_alignment_boost": 0.08,
    "moderate_alignment_boost": 0.04,
    "conflict_penalty": 0.12,
    "hard_conflict_penalty": 0.20,

    # confidence handling
    "min_confidence_floor": 0.05,
    "max_confidence_cap": 0.98,

    # grade behavior
    "allow_grade_upgrade_on_alignment": True,
    "allow_grade_downgrade_on_conflict": True,

    # avoid / wait behavior
    "avoid_vote_penalty": 0.10,
    "wait_vote_penalty": 0.08,

    # direction threshold
    "min_direction_margin": 0.08,
}


# =========================================================
# MODELS
# =========================================================

@dataclass
class ModuleVote:
    module_name: str
    direction: str              # CALL / PUT / FLAT / AVOID / NO TRADE
    grade: str
    confidence: float
    weight: float
    notes: List[str] = field(default_factory=list)


@dataclass
class UnifiedSignalDecision:
    final_direction: str
    final_grade: str
    final_confidence: float
    final_setup_score: float
    final_entry_quality_score: float
    final_macro_alignment_score: float
    bull_score: float
    bear_score: float
    conflict_score: float
    alignment_score: float
    reasons: List[str]
    warnings: List[str]
    module_votes: List[Dict[str, Any]]


# =========================================================
# HELPERS
# =========================================================

UNIFIED_GRADE_ORDER = ["A+", "A", "B+", "B", "C", "WAIT", "AVOID"]

def normalize_unified_grade(grade: str) -> str:
    if grade in UNIFIED_GRADE_ORDER:
        return grade
    return "AVOID"

def unified_grade_index(grade: str) -> int:
    return UNIFIED_GRADE_ORDER.index(normalize_unified_grade(grade))

def unified_upgrade_grade_one_step(grade: str) -> str:
    idx = unified_grade_index(grade)
    return UNIFIED_GRADE_ORDER[max(0, idx - 1)]

def unified_downgrade_grade_one_step(grade: str) -> str:
    idx = unified_grade_index(grade)
    return UNIFIED_GRADE_ORDER[min(len(UNIFIED_GRADE_ORDER) - 1, idx + 1)]

def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))

def map_direction_to_side(direction: str) -> str:
    if direction == "CALL":
        return "BULL"
    if direction == "PUT":
        return "BEAR"
    return "NEUTRAL"

def module_vote_to_dict(v: ModuleVote) -> Dict[str, Any]:
    return {
        "module_name": v.module_name,
        "direction": v.direction,
        "grade": v.grade,
        "confidence": round(v.confidence, 3),
        "weight": round(v.weight, 3),
        "notes": v.notes,
    }


# =========================================================
# EXTRACT MODULE VOTES
# =========================================================

def build_base_vote(inputs: dict, cfg: dict) -> ModuleVote:
    return ModuleVote(
        module_name="base_live_setup",
        direction=inputs.get("direction", "FLAT"),
        grade=inputs.get("trade_grade", "AVOID"),
        confidence=float(inputs.get("ai_confidence", 0.50)),
        weight=float(cfg["base_weight"]),
        notes=["Base live setup vote."],
    )


def build_premarket_vote(inputs: dict, cfg: dict) -> ModuleVote:
    if "premarket_high" not in inputs or "premarket_low" not in inputs:
        return ModuleVote(
            module_name="premarket",
            direction="FLAT",
            grade="WAIT",
            confidence=0.0,
            weight=float(cfg["premarket_weight"]),
            notes=["Premarket data not present."],
        )

    levels, state = build_premarket_state_from_inputs(inputs)
    scorecard = build_premarket_scorecard(levels, state)
    overrides = build_master_pipeline_overrides_from_premarket(scorecard)

    direction = overrides["direction"]
    grade = overrides["trade_grade"] if overrides["trade_grade"] in UNIFIED_GRADE_ORDER else "AVOID"

    return ModuleVote(
        module_name="premarket",
        direction=direction,
        grade=grade,
        confidence=float(overrides["ai_confidence"]),
        weight=float(cfg["premarket_weight"]),
        notes=[
            f"Premarket bias = {scorecard.final_bias}",
            f"Premarket grade = {scorecard.grade_suggestion}",
        ],
    )


def build_range_print_vote(inputs: dict, cfg: dict) -> ModuleVote:
    if inputs.get("symbol", "") != "QQQ":
        return ModuleVote(
            module_name="range_print",
            direction="FLAT",
            grade="WAIT",
            confidence=0.0,
            weight=float(cfg["range_print_weight"]),
            notes=["Range-print logic skipped because symbol is not QQQ."],
        )

    ctx = build_qqq_range_print_context_from_inputs(inputs)
    results = run_qqq_range_print_brain(ctx)
    pf = results["pipeline_features"]
    dd = results["decision_dict"]

    return ModuleVote(
        module_name="range_print",
        direction=pf["direction"],
        grade=pf["trade_grade"] if pf["trade_grade"] in UNIFIED_GRADE_ORDER else "AVOID",
        confidence=float(pf["ai_confidence"]),
        weight=float(cfg["range_print_weight"]),
        notes=[
            f"Range-print setup = {dd.get('setup_name')}",
            f"Range-print bias = {dd.get('bias')}",
            f"Range-print grade = {dd.get('grade')}",
        ],
    )


def build_trigger_62750_vote(inputs: dict, cfg: dict) -> ModuleVote:
    if inputs.get("symbol", "") != "QQQ":
        return ModuleVote(
            module_name="trigger_62750",
            direction="FLAT",
            grade="WAIT",
            confidence=0.0,
            weight=float(cfg["trigger_62750_weight"]),
            notes=["627.50 trigger logic skipped because symbol is not QQQ."],
        )

    ctx = build_62750_market_context_from_inputs(inputs)
    st = build_62750_structure_state_from_inputs(inputs)
    results = run_qqq_62750_brain(ctx, st)
    pf = results["pipeline_features"]
    dd = results["decision_dict"]

    return ModuleVote(
        module_name="trigger_62750",
        direction=pf["direction"],
        grade=pf["trade_grade"] if pf["trade_grade"] in UNIFIED_GRADE_ORDER else "AVOID",
        confidence=float(pf["ai_confidence"]),
        weight=float(cfg["trigger_62750_weight"]),
        notes=[
            f"627.50 setup = {dd.get('setup_name')}",
            f"627.50 bias = {dd.get('bias')}",
            f"627.50 grade = {dd.get('grade')}",
        ],
    )


# =========================================================
# CORE UNIFIED VOTE ENGINE
# =========================================================

def compute_unified_signal_decision(
    base_inputs: dict,
    cfg: dict = None
) -> UnifiedSignalDecision:
    if cfg is None:
        cfg = UNIFIED_SIGNAL_CONFIG

    reasons: List[str] = []
    warnings: List[str] = []

    module_votes = [
        build_base_vote(base_inputs, cfg),
        build_premarket_vote(base_inputs, cfg),
        build_range_print_vote(base_inputs, cfg),
        build_trigger_62750_vote(base_inputs, cfg),
    ]

    bull_score = 0.0
    bear_score = 0.0
    neutral_weight = 0.0
    confidence_sum = 0.0

    call_votes = 0
    put_votes = 0
    avoidish_votes = 0

    for mv in module_votes:
        side = map_direction_to_side(mv.direction)
        weighted_conf = mv.confidence * mv.weight
        confidence_sum += weighted_conf

        if side == "BULL":
            bull_score += weighted_conf
            call_votes += 1
        elif side == "BEAR":
            bear_score += weighted_conf
            put_votes += 1
        else:
            neutral_weight += mv.weight
            if mv.grade in {"AVOID", "WAIT"} or mv.direction in {"FLAT", "NO TRADE", "AVOID"}:
                avoidish_votes += 1

    # alignment and conflict
    alignment_score = 0.0
    conflict_score = 0.0

    if call_votes >= 3 or put_votes >= 3:
        alignment_score += cfg["strong_alignment_boost"]
        reasons.append("Strong alignment across structure modules.")
    elif call_votes >= 2 or put_votes >= 2:
        alignment_score += cfg["moderate_alignment_boost"]
        reasons.append("Moderate alignment across structure modules.")

    if call_votes > 0 and put_votes > 0:
        conflict_score += cfg["conflict_penalty"]
        warnings.append("Modules disagree on direction.")
        if abs(call_votes - put_votes) == 0:
            conflict_score += cfg["hard_conflict_penalty"]
            warnings.append("Directional vote split is severe.")

    if avoidish_votes >= 2:
        conflict_score += cfg["avoid_vote_penalty"]
        warnings.append("Multiple modules are signaling wait / avoid conditions.")

    raw_confidence = confidence_sum + alignment_score - conflict_score
    raw_confidence = clamp01(raw_confidence)

    bull_net = clamp01(bull_score - conflict_score)
    bear_net = clamp01(bear_score - conflict_score)
    direction_margin = abs(bull_net - bear_net)

    if bull_net > bear_net and bull_net >= cfg["min_direction_margin"]:
        final_direction = "CALL"
    elif bear_net > bull_net and bear_net >= cfg["min_direction_margin"]:
        final_direction = "PUT"
    else:
        final_direction = "FLAT"

    # choose reference grade from strongest aligned module
    aligned_modules = []
    for mv in module_votes:
        if final_direction == "CALL" and mv.direction == "CALL":
            aligned_modules.append(mv)
        elif final_direction == "PUT" and mv.direction == "PUT":
            aligned_modules.append(mv)

    if aligned_modules:
        strongest = sorted(
            aligned_modules,
            key=lambda x: (x.confidence * x.weight, -unified_grade_index(x.grade)),
            reverse=True
        )[0]
        final_grade = strongest.grade
        reasons.append(f"Strongest aligned module: {strongest.module_name}.")
    else:
        final_grade = "AVOID"

    # adjust grade for alignment / conflict
    if cfg["allow_grade_upgrade_on_alignment"] and alignment_score >= cfg["strong_alignment_boost"]:
        if final_grade in {"B+", "B", "C"}:
            final_grade = unified_upgrade_grade_one_step(final_grade)
            reasons.append("Grade upgraded due to strong multi-module alignment.")

    if cfg["allow_grade_downgrade_on_conflict"] and conflict_score >= cfg["conflict_penalty"]:
        if final_grade not in {"AVOID", "WAIT"}:
            final_grade = unified_downgrade_grade_one_step(final_grade)
            warnings.append("Grade downgraded due to signal conflict.")

    if final_direction == "FLAT":
        final_grade = "AVOID"
        raw_confidence = min(raw_confidence, 0.35)
        warnings.append("No clear directional edge after module merge.")

    if avoidish_votes >= 3:
        final_direction = "FLAT"
        final_grade = "AVOID"
        raw_confidence = min(raw_confidence, 0.25)
        warnings.append("Too many structure modules prefer wait / avoid.")

    # final scoring fields for pipeline
    final_setup_score = clamp01(max(bull_net, bear_net))
    final_entry_quality_score = clamp01(1.0 - conflict_score - (0.5 * neutral_weight))
    final_macro_alignment_score = 0.50  # placeholder until macro module is merged

    return UnifiedSignalDecision(
        final_direction=final_direction,
        final_grade=final_grade,
        final_confidence=round(clamp(raw_confidence, cfg["min_confidence_floor"], cfg["max_confidence_cap"]), 3),
        final_setup_score=round(final_setup_score, 3),
        final_entry_quality_score=round(final_entry_quality_score, 3),
        final_macro_alignment_score=round(final_macro_alignment_score, 3),
        bull_score=round(bull_net, 3),
        bear_score=round(bear_net, 3),
        conflict_score=round(conflict_score, 3),
        alignment_score=round(alignment_score, 3),
        reasons=reasons,
        warnings=warnings,
        module_votes=[module_vote_to_dict(x) for x in module_votes],
    )


# =========================================================
# PIPELINE OVERRIDES
# =========================================================

def unified_signal_to_pipeline_overrides(decision: UnifiedSignalDecision) -> Dict[str, Any]:
    return {
        "direction": decision.final_direction,
        "trade_grade": decision.final_grade if decision.final_grade in {"A+", "A", "B+", "B"} else "AVOID",
        "ai_confidence": decision.final_confidence,
        "setup_score": decision.final_setup_score,
        "entry_quality_score": decision.final_entry_quality_score,
        "macro_alignment_score": decision.final_macro_alignment_score,

        "unified_bull_score": decision.bull_score,
        "unified_bear_score": decision.bear_score,
        "unified_conflict_score": decision.conflict_score,
        "unified_alignment_score": decision.alignment_score,
        "unified_module_votes": decision.module_votes,
        "unified_reasons": decision.reasons,
        "unified_warnings": decision.warnings,
    }


# =========================================================
# MERGE UNIFIED SIGNAL INTO INPUTS
# =========================================================

def merge_unified_signal_into_inputs(
    base_inputs: dict,
    cfg: dict = None
) -> dict:
    if cfg is None:
        cfg = UNIFIED_SIGNAL_CONFIG

    merged = copy.deepcopy(base_inputs)

    unified_decision = compute_unified_signal_decision(merged, cfg=cfg)
    unified_overrides = unified_signal_to_pipeline_overrides(unified_decision)

    merged["_unified_signal_decision"] = asdict(unified_decision)
    merged["_unified_signal_overrides"] = unified_overrides

    merged["direction"] = unified_overrides["direction"]
    merged["trade_grade"] = unified_overrides["trade_grade"]
    merged["ai_confidence"] = unified_overrides["ai_confidence"]
    merged["setup_score"] = unified_overrides["setup_score"]
    merged["entry_quality_score"] = unified_overrides["entry_quality_score"]
    merged["macro_alignment_score"] = unified_overrides["macro_alignment_score"]

    merged["_unified_signal_note"] = (
        f"Unified signal merged: direction={unified_decision.final_direction}, "
        f"grade={unified_decision.final_grade}, conf={unified_decision.final_confidence}, "
        f"bull={unified_decision.bull_score}, bear={unified_decision.bear_score}, "
        f"conflict={unified_decision.conflict_score}"
    )

    return merged


# =========================================================
# LIVE RUNNER WITH UNIFIED SIGNAL
# =========================================================

def run_live_trade_case_with_unified_signal(
    memory: MemoryStore,
    inputs: dict,
    cfg: dict = None,
):
    merged_inputs = merge_unified_signal_into_inputs(inputs, cfg=cfg)

    live_results = run_live_trade_case(
        memory=memory,
        inputs=merged_inputs,
    )

    live_results["unified_signal_decision"] = merged_inputs.get("_unified_signal_decision", {})
    live_results["unified_signal_overrides"] = merged_inputs.get("_unified_signal_overrides", {})
    live_results["unified_signal_note"] = merged_inputs.get("_unified_signal_note", "")
    live_results["merged_inputs"] = merged_inputs

    return live_results


# =========================================================
# WATCHLIST RUNNER WITH UNIFIED SIGNAL
# =========================================================

def run_watchlist_cases_with_unified_signal(
    memory: MemoryStore,
    base_inputs: dict,
    watchlist_cases: list,
    cfg: dict = None,
):
    all_results = []

    for case in watchlist_cases:
        case_name = case.get("case_name", "Unnamed Case")
        case_inputs = build_case_inputs(base_inputs, case)

        try:
            results = run_live_trade_case_with_unified_signal(
                memory=memory,
                inputs=case_inputs,
                cfg=cfg,
            )

            verdict = results["rl_augmented_verdict"]
            unified = results.get("unified_signal_decision", {})

            row = {
                "case_name": case_name,
                "symbol": case_inputs["symbol"],
                "direction": results["merged_inputs"]["direction"],
                "setup_name": case_inputs["setup_name"],
                "status": verdict.final_status,
                "grade": verdict.final_grade,
                "blocked": verdict.blocked,
                "final_ai_confidence": verdict.final_ai_confidence,
                "final_size_fraction": verdict.final_size_fraction,
                "rl_agent": verdict.selected_rl_agent,
                "rl_regime_bias": verdict.rl_regime_bias,
                "rl_confidence": verdict.rl_ensemble_confidence,
                "unified_direction": unified.get("final_direction", ""),
                "unified_grade": unified.get("final_grade", ""),
                "unified_confidence": unified.get("final_confidence", 0.0),
                "unified_bull_score": unified.get("bull_score", 0.0),
                "unified_bear_score": unified.get("bear_score", 0.0),
                "unified_conflict_score": unified.get("conflict_score", 0.0),
                "approved_for_execution": verdict.approved_for_execution,
                "should_alert_discord": verdict.should_alert_discord,
                "opportunity_score": compute_watchlist_opportunity_score(verdict),
                "top_reason": verdict.reasons[0] if verdict.reasons else "",
                "top_warning": verdict.warnings[0] if verdict.warnings else "",
                "top_blocker": verdict.blockers[0] if verdict.blockers else "",
                "unified_note": results.get("unified_signal_note", ""),
                "raw_results": results,
            }

        except Exception as e:
            row = {
                "case_name": case_name,
                "symbol": case.get("symbol", ""),
                "direction": case.get("direction", ""),
                "setup_name": case.get("setup_name", ""),
                "status": "ERROR",
                "grade": "AVOID",
                "blocked": True,
                "final_ai_confidence": 0.0,
                "final_size_fraction": 0.0,
                "rl_agent": "",
                "rl_regime_bias": "",
                "rl_confidence": 0.0,
                "unified_direction": "",
                "unified_grade": "",
                "unified_confidence": 0.0,
                "unified_bull_score": 0.0,
                "unified_bear_score": 0.0,
                "unified_conflict_score": 0.0,
                "approved_for_execution": False,
                "should_alert_discord": False,
                "opportunity_score": -9999.0,
                "top_reason": "",
                "top_warning": "",
                "top_blocker": str(e),
                "unified_note": "Error",
                "raw_results": None,
            }

        all_results.append(row)

    return all_results


# =========================================================
# DISPLAY HELPERS
# =========================================================

def print_live_trade_case_with_unified_signal_summary(results: dict):
    market = results["market"]
    signal = results["signal"]
    rl_decision = results["rl_decision"]
    rl_augmented_verdict = results["rl_augmented_verdict"]

    print("=== UNIFIED SIGNAL NOTE ===")
    print(results.get("unified_signal_note", ""))

    print("\n=== UNIFIED SIGNAL DECISION ===")
    print(json.dumps(results.get("unified_signal_decision", {}), indent=2))

    print("\n=== UNIFIED SIGNAL OVERRIDES ===")
    print(json.dumps(results.get("unified_signal_overrides", {}), indent=2))

    print("\n=== RL DECISION ===")
    print(json.dumps(rl_decision_to_dict(rl_decision), indent=2))

    print("\n=== FINAL RL-AUGMENTED VERDICT ===")
    print(json.dumps(rl_augmented_verdict_to_dict(rl_augmented_verdict), indent=2))

    print("\n=== FINAL ALERT ===")
    print(format_rl_augmented_alert(market, signal, rl_augmented_verdict))


def unified_watchlist_results_to_dataframe(results: list) -> pd.DataFrame:
    if not results:
        return pd.DataFrame()

    df = pd.DataFrame([
        {k: v for k, v in r.items() if k != "raw_results"}
        for r in results
    ])

    if not df.empty:
        df = df.sort_values(
            by=["blocked", "opportunity_score", "final_size_fraction", "final_ai_confidence"],
            ascending=[True, False, False, False]
        ).reset_index(drop=True)

    return df


def print_watchlist_summary_with_unified_signal(results: list):
    df = unified_watchlist_results_to_dataframe(results)

    if df.empty:
        print("No watchlist results.")
        return

    print("=== WATCHLIST RANKING WITH UNIFIED SIGNAL ===")
    print(df.to_string(index=False))

    valid = [r for r in results if r.get("raw_results") is not None]
    if valid:
        best = sorted(valid, key=lambda x: x["opportunity_score"], reverse=True)[0]
        print("\n=== TOP OPPORTUNITY ===")
        print(json.dumps({
            "case_name": best["case_name"],
            "symbol": best["symbol"],
            "direction": best["direction"],
            "setup_name": best["setup_name"],
            "status": best["status"],
            "grade": best["grade"],
            "blocked": best["blocked"],
            "final_ai_confidence": best["final_ai_confidence"],
            "final_size_fraction": best["final_size_fraction"],
            "rl_agent": best["rl_agent"],
            "rl_regime_bias": best["rl_regime_bias"],
            "rl_confidence": best["rl_confidence"],
            "unified_direction": best["unified_direction"],
            "unified_grade": best["unified_grade"],
            "unified_confidence": best["unified_confidence"],
            "unified_bull_score": best["unified_bull_score"],
            "unified_bear_score": best["unified_bear_score"],
            "unified_conflict_score": best["unified_conflict_score"],
            "approved_for_execution": best["approved_for_execution"],
            "opportunity_score": best["opportunity_score"],
            "top_reason": best["top_reason"],
            "top_warning": best["top_warning"],
            "top_blocker": best["top_blocker"],
            "unified_note": best["unified_note"],
        }, indent=2))


# =========================================================
# RUN SINGLE CASE WITH UNIFIED SIGNAL
# Assumes LIVE_INPUTS plus your prior module fields exist
# =========================================================

live_inputs_unified = copy.deepcopy(LIVE_INPUTS)

# Optional: layer in your example fields from earlier modules if they exist
try:
    live_inputs_unified.update(PREMARKET_FIELDS_EXAMPLE)
except:
    pass

try:
    live_inputs_unified.update(QQQ_RANGE_PRINT_FIELDS_EXAMPLE)
except:
    pass

try:
    live_inputs_unified.update(TRIGGER_62750_FIELDS_EXAMPLE)
except:
    pass

live_results_unified = run_live_trade_case_with_unified_signal(
    memory=memory,
    inputs=live_inputs_unified,
    cfg=UNIFIED_SIGNAL_CONFIG,
)

print_live_trade_case_with_unified_signal_summary(live_results_unified)


# =========================================================
# RUN WATCHLIST WITH UNIFIED SIGNAL
# Assumes WATCHLIST_CASES exists
# =========================================================

watchlist_results_unified = run_watchlist_cases_with_unified_signal(
    memory=memory,
    base_inputs=live_inputs_unified,
    watchlist_cases=WATCHLIST_CASES,
    cfg=UNIFIED_SIGNAL_CONFIG,
)

print("\n")
print_watchlist_summary_with_unified_signal(watchlist_results_unified)

# =========================================================
# NEXT CELL: MERGE 627.50 TRIGGER LOGIC INTO LIVE / WATCHLIST
# Put this AFTER the QQQ 627.50 institutional trigger logic cell
# =========================================================

import copy
import json
import pandas as pd


# =========================================================
# CONFIG
# How strongly should 627.50 trigger logic influence the system?
# =========================================================

TRIGGER_62750_MERGE_CONFIG = {
    "enable_trigger_override": True,

    # confidence blend
    "confidence_blend_weight": 0.35,

    # setup score blend
    "setup_score_blend_weight": 0.30,

    # entry quality blend
    "entry_quality_blend_weight": 0.35,

    # respect no-trade / avoid logic
    "respect_no_trade_bias": True,

    # if trigger direction conflicts, penalize confidence
    "direction_conflict_penalty": 0.14,

    # if aligned, small boost
    "direction_alignment_boost": 0.05,

    # optional one-step grade changes
    "allow_grade_upgrade": True,
    "allow_grade_downgrade": True,
}


# =========================================================
# GRADE HELPERS
# =========================================================

TRIGGER_GRADE_ORDER = ["A+", "A", "B", "C", "WAIT", "AVOID"]

def normalize_trigger_grade(grade: str) -> str:
    if grade in TRIGGER_GRADE_ORDER:
        return grade
    return "AVOID"

def trigger_grade_index(grade: str) -> int:
    return TRIGGER_GRADE_ORDER.index(normalize_trigger_grade(grade))

def trigger_upgrade_grade_one_step(grade: str) -> str:
    idx = trigger_grade_index(grade)
    return TRIGGER_GRADE_ORDER[max(0, idx - 1)]

def trigger_downgrade_grade_one_step(grade: str) -> str:
    idx = trigger_grade_index(grade)
    return TRIGGER_GRADE_ORDER[min(len(TRIGGER_GRADE_ORDER) - 1, idx + 1)]


# =========================================================
# CONTEXT BUILDERS FROM INPUTS
# =========================================================

def build_62750_market_context_from_inputs(inputs: dict) -> MarketContext:
    trigger_level = float(inputs.get("trigger_level", 627.50))
    current_price = float(inputs["price"])

    return MarketContext(
        symbol=inputs["symbol"],
        current_price=current_price,
        vwap=float(inputs["vwap"]),
        rsi=float(inputs.get("rsi", 50.0)),
        trigger_level=trigger_level,
        resistance_1=float(inputs.get("resistance_1", 629.00)),
        resistance_2=float(inputs.get("resistance_2", 630.00)),
        support_1=float(inputs.get("support_1", 626.00)),
        support_2=float(inputs.get("support_2", 624.50)),
        above_vwap=bool(inputs.get("above_vwap", False)),
        below_vwap=bool(inputs.get("below_vwap", False)),
        near_upper_band=bool(inputs.get("near_upper_band", False)),
        near_lower_band=bool(inputs.get("near_lower_band", False)),
        distance_from_trigger=abs(current_price - trigger_level),
        prior_move_extended=bool(inputs.get("prior_move_extended", False)),
    )


def build_62750_structure_state_from_inputs(inputs: dict) -> StructureState:
    return StructureState(
        hold_at_trigger=bool(inputs.get("hold_at_trigger", False)),
        vwap_reclaimed=bool(inputs.get("vwap_reclaimed", False)),
        vwap_held=bool(inputs.get("vwap_held", False)),
        higher_low=bool(inputs.get("higher_low", False)),
        retest_hold=bool(inputs.get("retest_hold", False)),
        breakout_candle_with_volume=bool(inputs.get("breakout_candle_with_volume", False)),

        rejection_at_resistance=bool(inputs.get("rejection_at_resistance", False)),
        lower_high=bool(inputs.get("lower_high", False)),
        clean_break_below_trigger=bool(inputs.get("clean_break_below_trigger", False)),
        acceptance_below_trigger=bool(inputs.get("acceptance_below_trigger", False)),
        failed_bounce=bool(inputs.get("failed_bounce", False)),

        no_retest=bool(inputs.get("no_retest", False)),
        multiple_same_color_bars_extended=bool(inputs.get("multiple_same_color_bars_extended", False)),
        entering_directly_into_resistance=bool(inputs.get("entering_directly_into_resistance", False)),
        entering_directly_into_support=bool(inputs.get("entering_directly_into_support", False)),
    )


# =========================================================
# 627.50 OVERRIDE ENGINE
# =========================================================

def merge_62750_overrides_into_inputs(
    base_inputs: dict,
    merge_config: dict = None
) -> dict:
    if merge_config is None:
        merge_config = TRIGGER_62750_MERGE_CONFIG

    merged = copy.deepcopy(base_inputs)

    if not merge_config.get("enable_trigger_override", True):
        merged["_trigger_62750_merge_note"] = "627.50 trigger override disabled."
        return merged

    # only use for QQQ unless intentionally adapted
    if merged.get("symbol", "") != "QQQ":
        merged["_trigger_62750_merge_note"] = "627.50 trigger override skipped because symbol is not QQQ."
        return merged

    ctx = build_62750_market_context_from_inputs(merged)
    st = build_62750_structure_state_from_inputs(merged)

    trigger_results = run_qqq_62750_brain(ctx, st)
    pipeline_overrides = trigger_results["pipeline_features"]
    decision_dict = trigger_results["decision_dict"]

    merged["_trigger_62750_decision"] = decision_dict
    merged["_trigger_62750_pipeline_overrides"] = pipeline_overrides

    base_direction = merged.get("direction", "FLAT")
    base_grade = normalize_trigger_grade(merged.get("trade_grade", "AVOID"))
    base_conf = float(merged.get("ai_confidence", 0.50))
    base_setup = float(merged.get("setup_score", 0.50))
    base_entry = float(merged.get("entry_quality_score", 0.50))

    trg_direction = pipeline_overrides["direction"]
    trg_grade = normalize_trigger_grade(pipeline_overrides["trade_grade"])
    trg_conf = float(pipeline_overrides["ai_confidence"])
    trg_setup = float(pipeline_overrides["setup_score"])
    trg_entry = float(pipeline_overrides["entry_quality_score"])

    conf_w = float(merge_config["confidence_blend_weight"])
    setup_w = float(merge_config["setup_score_blend_weight"])
    entry_w = float(merge_config["entry_quality_blend_weight"])

    new_conf = ((1 - conf_w) * base_conf) + (conf_w * trg_conf)
    new_setup = ((1 - setup_w) * base_setup) + (setup_w * trg_setup)
    new_entry = ((1 - entry_w) * base_entry) + (entry_w * trg_entry)

    if trg_direction in {"CALL", "PUT"}:
        if trg_direction == base_direction:
            new_conf += merge_config["direction_alignment_boost"]
        elif base_direction in {"CALL", "PUT"} and trg_direction != base_direction:
            new_conf -= merge_config["direction_conflict_penalty"]

    if merge_config["respect_no_trade_bias"]:
        if decision_dict.get("bias") == "NO TRADE" or trg_direction == "FLAT":
            if base_direction in {"CALL", "PUT"}:
                new_conf = min(new_conf, 0.35)
                new_setup = min(new_setup, 0.40)

    new_grade = base_grade

    if merge_config["allow_grade_upgrade"]:
        if trg_direction == base_direction and trg_grade in {"A+", "A", "B"} and base_grade in {"B", "C"}:
            new_grade = trigger_upgrade_grade_one_step(new_grade)

    if merge_config["allow_grade_downgrade"]:
        if decision_dict.get("bias") == "NO TRADE" and base_grade in {"A+", "A", "B", "C"}:
            new_grade = trigger_downgrade_grade_one_step(new_grade)
        elif trg_direction in {"CALL", "PUT"} and base_direction in {"CALL", "PUT"} and trg_direction != base_direction:
            new_grade = trigger_downgrade_grade_one_step(new_grade)

    merged["ai_confidence"] = round(clamp01(new_conf), 3)
    merged["setup_score"] = round(clamp01(new_setup), 3)
    merged["entry_quality_score"] = round(clamp01(new_entry), 3)

    mapped_grade = new_grade
    if mapped_grade in {"WAIT", "C"}:
        mapped_grade = "AVOID"
    merged["trade_grade"] = mapped_grade

    if merged.get("direction", "FLAT") == "FLAT" and trg_direction in {"CALL", "PUT"}:
        merged["direction"] = trg_direction

    merged["_trigger_62750_merge_note"] = (
        f"627.50 merged: setup={decision_dict.get('setup_name')}, "
        f"bias={decision_dict.get('bias')}, grade={decision_dict.get('grade')}, "
        f"base_direction={base_direction}, final_grade={mapped_grade}"
    )

    return merged


# =========================================================
# ONE-SHOT LIVE RUNNER WITH 627.50 MERGE
# =========================================================

def run_live_trade_case_with_62750(
    memory: MemoryStore,
    inputs: dict,
    merge_config: dict = None,
):
    merged_inputs = merge_62750_overrides_into_inputs(inputs, merge_config=merge_config)

    live_results = run_live_trade_case(
        memory=memory,
        inputs=merged_inputs,
    )

    live_results["trigger_62750_decision"] = merged_inputs.get("_trigger_62750_decision", {})
    live_results["trigger_62750_pipeline_overrides"] = merged_inputs.get("_trigger_62750_pipeline_overrides", {})
    live_results["trigger_62750_merge_note"] = merged_inputs.get("_trigger_62750_merge_note", "")
    live_results["merged_inputs"] = merged_inputs

    return live_results


# =========================================================
# WATCHLIST RUNNER WITH 627.50 MERGE
# =========================================================

def run_watchlist_cases_with_62750(
    memory: MemoryStore,
    base_inputs: dict,
    watchlist_cases: list,
    merge_config: dict = None,
):
    all_results = []

    for case in watchlist_cases:
        case_name = case.get("case_name", "Unnamed Case")
        case_inputs = build_case_inputs(base_inputs, case)

        try:
            results = run_live_trade_case_with_62750(
                memory=memory,
                inputs=case_inputs,
                merge_config=merge_config,
            )

            verdict = results["rl_augmented_verdict"]
            trig_decision = results.get("trigger_62750_decision", {})

            row = {
                "case_name": case_name,
                "symbol": case_inputs["symbol"],
                "direction": results["merged_inputs"]["direction"],
                "setup_name": case_inputs["setup_name"],
                "status": verdict.final_status,
                "grade": verdict.final_grade,
                "blocked": verdict.blocked,
                "final_ai_confidence": verdict.final_ai_confidence,
                "final_size_fraction": verdict.final_size_fraction,
                "rl_agent": verdict.selected_rl_agent,
                "rl_regime_bias": verdict.rl_regime_bias,
                "rl_confidence": verdict.rl_ensemble_confidence,
                "trigger_setup": trig_decision.get("setup_name", ""),
                "trigger_bias": trig_decision.get("bias", ""),
                "trigger_grade": trig_decision.get("grade", ""),
                "approved_for_execution": verdict.approved_for_execution,
                "should_alert_discord": verdict.should_alert_discord,
                "opportunity_score": compute_watchlist_opportunity_score(verdict),
                "top_reason": verdict.reasons[0] if verdict.reasons else "",
                "top_warning": verdict.warnings[0] if verdict.warnings else "",
                "top_blocker": verdict.blockers[0] if verdict.blockers else "",
                "trigger_note": results.get("trigger_62750_merge_note", ""),
                "raw_results": results,
            }

        except Exception as e:
            row = {
                "case_name": case_name,
                "symbol": case.get("symbol", ""),
                "direction": case.get("direction", ""),
                "setup_name": case.get("setup_name", ""),
                "status": "ERROR",
                "grade": "AVOID",
                "blocked": True,
                "final_ai_confidence": 0.0,
                "final_size_fraction": 0.0,
                "rl_agent": "",
                "rl_regime_bias": "",
                "rl_confidence": 0.0,
                "trigger_setup": "",
                "trigger_bias": "",
                "trigger_grade": "",
                "approved_for_execution": False,
                "should_alert_discord": False,
                "opportunity_score": -9999.0,
                "top_reason": "",
                "top_warning": "",
                "top_blocker": str(e),
                "trigger_note": "Error",
                "raw_results": None,
            }

        all_results.append(row)

    return all_results


# =========================================================
# DISPLAY HELPERS
# =========================================================

def print_live_trade_case_with_62750_summary(results: dict):
    market = results["market"]
    signal = results["signal"]
    rl_decision = results["rl_decision"]
    rl_augmented_verdict = results["rl_augmented_verdict"]

    print("=== 627.50 MERGE NOTE ===")
    print(results.get("trigger_62750_merge_note", ""))

    print("\n=== 627.50 DECISION ===")
    print(json.dumps(results.get("trigger_62750_decision", {}), indent=2))

    print("\n=== 627.50 OVERRIDES ===")
    print(json.dumps(results.get("trigger_62750_pipeline_overrides", {}), indent=2))

    print("\n=== RL DECISION ===")
    print(json.dumps(rl_decision_to_dict(rl_decision), indent=2))

    print("\n=== FINAL RL-AUGMENTED VERDICT ===")
    print(json.dumps(rl_augmented_verdict_to_dict(rl_augmented_verdict), indent=2))

    print("\n=== FINAL ALERT ===")
    print(format_rl_augmented_alert(market, signal, rl_augmented_verdict))


def watchlist_results_with_62750_to_dataframe(results: list) -> pd.DataFrame:
    if not results:
        return pd.DataFrame()

    df = pd.DataFrame([
        {k: v for k, v in r.items() if k != "raw_results"}
        for r in results
    ])

    if not df.empty:
        df = df.sort_values(
            by=["blocked", "opportunity_score", "final_size_fraction", "final_ai_confidence"],
            ascending=[True, False, False, False]
        ).reset_index(drop=True)

    return df


def print_watchlist_summary_with_62750(results: list):
    df = watchlist_results_with_62750_to_dataframe(results)

    if df.empty:
        print("No watchlist results.")
        return

    print("=== WATCHLIST RANKING WITH 627.50 MERGE ===")
    print(df.to_string(index=False))

    valid = [r for r in results if r.get("raw_results") is not None]
    if valid:
        best = sorted(valid, key=lambda x: x["opportunity_score"], reverse=True)[0]
        print("\n=== TOP OPPORTUNITY ===")
        print(json.dumps({
            "case_name": best["case_name"],
            "symbol": best["symbol"],
            "direction": best["direction"],
            "setup_name": best["setup_name"],
            "status": best["status"],
            "grade": best["grade"],
            "blocked": best["blocked"],
            "final_ai_confidence": best["final_ai_confidence"],
            "final_size_fraction": best["final_size_fraction"],
            "rl_agent": best["rl_agent"],
            "rl_regime_bias": best["rl_regime_bias"],
            "rl_confidence": best["rl_confidence"],
            "trigger_setup": best["trigger_setup"],
            "trigger_bias": best["trigger_bias"],
            "trigger_grade": best["trigger_grade"],
            "approved_for_execution": best["approved_for_execution"],
            "opportunity_score": best["opportunity_score"],
            "top_reason": best["top_reason"],
            "top_warning": best["top_warning"],
            "top_blocker": best["top_blocker"],
            "trigger_note": best["trigger_note"],
        }, indent=2))


# =========================================================
# OPTIONAL EXAMPLE INPUTS FOR 627.50 FIELDS
# Add these into LIVE_INPUTS / WATCHLIST cases if not already present
# =========================================================

TRIGGER_62750_FIELDS_EXAMPLE = {
    "trigger_level": 627.50,
    "resistance_1": 629.00,
    "resistance_2": 630.00,
    "support_1": 626.00,
    "support_2": 624.50,

    "rsi": 64.8,
    "above_vwap": True,
    "below_vwap": False,
    "near_upper_band": False,
    "near_lower_band": False,
    "prior_move_extended": False,

    "hold_at_trigger": True,
    "vwap_reclaimed": True,
    "vwap_held": True,
    "higher_low": True,
    "retest_hold": True,
    "breakout_candle_with_volume": True,

    "rejection_at_resistance": False,
    "lower_high": False,
    "clean_break_below_trigger": False,
    "acceptance_below_trigger": False,
    "failed_bounce": False,

    "no_retest": False,
    "multiple_same_color_bars_extended": False,
    "entering_directly_into_resistance": False,
    "entering_directly_into_support": False,
}


# =========================================================
# RUN SINGLE CASE WITH 627.50 MERGE
# Assumes LIVE_INPUTS exists
# =========================================================

live_inputs_with_62750 = copy.deepcopy(LIVE_INPUTS)
live_inputs_with_62750.update(TRIGGER_62750_FIELDS_EXAMPLE)

live_results_with_62750 = run_live_trade_case_with_62750(
    memory=memory,
    inputs=live_inputs_with_62750,
    merge_config=TRIGGER_62750_MERGE_CONFIG,
)

print_live_trade_case_with_62750_summary(live_results_with_62750)


# =========================================================
# RUN WATCHLIST WITH 627.50 MERGE
# Assumes WATCHLIST_CASES exists
# =========================================================

watchlist_results_with_62750 = run_watchlist_cases_with_62750(
    memory=memory,
    base_inputs=live_inputs_with_62750,
    watchlist_cases=WATCHLIST_CASES,
    merge_config=TRIGGER_62750_MERGE_CONFIG,
)

print("\n")
print_watchlist_summary_with_62750(watchlist_results_with_62750)

# =========================================================
# QQQ 627.50 INSTITUTIONAL TRIGGER LOGIC
# ONE-CELL CLEAN COLAB VERSION
# =========================================================
# PURPOSE:
# Teach the bot how to trade around the 627.50 institutional trigger.
#
# CORE IDEA:
# - Bullish continuation if 627.50 holds and confirms
# - Bearish unwind if 627.50 fails and accepts below
# - VWAP alignment matters
# - No chasing late extensions
#
# STYLE:
# - 627.50 = trigger
# - 629.00 / 630.00 = upside targets
# - 626.00 / 624.50 = downside targets
# - A+ at the level with structure
# - worse grade if late / extended
# =========================================================

from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Dict, Any
import json


# =========================
# DATA MODELS
# =========================

@dataclass
class MarketContext:
    symbol: str
    current_price: float
    vwap: float
    rsi: float

    # key institutional / chart levels
    trigger_level: float = 627.50
    resistance_1: float = 629.00
    resistance_2: float = 630.00
    support_1: float = 626.00
    support_2: float = 624.50

    # optional higher-timeframe context
    above_vwap: bool = False
    below_vwap: bool = False
    near_upper_band: bool = False
    near_lower_band: bool = False

    # optional extension / location info
    distance_from_trigger: float = 0.0
    prior_move_extended: bool = False


@dataclass
class StructureState:
    # bullish confirmations
    hold_at_trigger: bool = False
    vwap_reclaimed: bool = False
    vwap_held: bool = False
    higher_low: bool = False
    retest_hold: bool = False
    breakout_candle_with_volume: bool = False

    # bearish confirmations
    rejection_at_resistance: bool = False
    lower_high: bool = False
    clean_break_below_trigger: bool = False
    acceptance_below_trigger: bool = False
    failed_bounce: bool = False

    # chase / discipline filters
    no_retest: bool = False
    multiple_same_color_bars_extended: bool = False
    entering_directly_into_resistance: bool = False
    entering_directly_into_support: bool = False


@dataclass
class TradeDecision:
    ticker: str
    bias: str                  # CALL / PUT / NO TRADE
    grade: str                 # A+ / A / B / AVOID / WAIT
    setup_name: str
    trigger_level: float
    entry_zone: str
    targets: List[str]
    invalidation: str
    reason: List[str]
    is_chasing: bool
    alert_text: str


@dataclass
class TriggerTrainingLabel:
    pattern_name: str
    bias: str
    grade: str
    valid_for_entry: bool
    confidence_score: float
    reasons: List[str] = field(default_factory=list)


# =========================
# HELPERS
# =========================

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def approx_equal(a: float, b: float, tol: float = 0.12) -> bool:
    return abs(a - b) <= tol


def within_range(x: float, low: float, high: float) -> bool:
    return low <= x <= high


def is_testing_trigger(price: float, trigger: float, tol: float = 0.20) -> bool:
    return abs(price - trigger) <= tol


def calls_chasing(ctx: MarketContext, st: StructureState) -> bool:
    flags = 0

    if ctx.current_price > ctx.trigger_level + 0.80:
        flags += 1
    if ctx.rsi >= 72:
        flags += 1
    if ctx.near_upper_band:
        flags += 1
    if st.no_retest:
        flags += 1
    if st.multiple_same_color_bars_extended:
        flags += 1
    if st.entering_directly_into_resistance:
        flags += 1

    return flags >= 2


def puts_chasing(ctx: MarketContext, st: StructureState) -> bool:
    flags = 0

    if ctx.current_price < ctx.trigger_level - 0.80:
        flags += 1
    if ctx.rsi <= 28:
        flags += 1
    if ctx.near_lower_band:
        flags += 1
    if st.no_retest:
        flags += 1
    if st.multiple_same_color_bars_extended:
        flags += 1
    if st.entering_directly_into_support:
        flags += 1

    return flags >= 2


# =========================
# CORE LOGIC
# =========================

def make_qqq_62750_decision(ctx: MarketContext, st: StructureState) -> TradeDecision:
    """
    Exact setup logic for:
    - Bullish continuation if 627.50 holds and confirms
    - Bearish unwind if 627.50 fails and accepts below
    """
    reasons: List[str] = []

    # -------------------------
    # BULLISH CONDITIONS
    # -------------------------
    bull_confirmations = 0

    if st.hold_at_trigger:
        bull_confirmations += 1
        reasons.append("Price is holding at the 627.50 institutional trigger.")

    if st.vwap_reclaimed or st.vwap_held:
        bull_confirmations += 1
        reasons.append("VWAP is aligned with the long idea.")

    if st.higher_low:
        bull_confirmations += 1
        reasons.append("Higher low confirms buyers defending the level.")

    if st.retest_hold:
        bull_confirmations += 1
        reasons.append("Retest held after initial reaction.")

    if st.breakout_candle_with_volume:
        bull_confirmations += 1
        reasons.append("Breakout candle with volume confirms continuation.")

    bull_chasing = calls_chasing(ctx, st)

    # A+ CALL
    if (
        is_testing_trigger(ctx.current_price, ctx.trigger_level, tol=0.30)
        and bull_confirmations >= 4
        and not bull_chasing
    ):
        return TradeDecision(
            ticker=ctx.symbol,
            bias="CALL",
            grade="A+",
            setup_name="627.50 Hold + VWAP Confirmation",
            trigger_level=ctx.trigger_level,
            entry_zone="627.40 - 627.70 after hold/reclaim confirmation",
            targets=["629.00", "630.00", "631.00+"],
            invalidation="Lose 627.50 cleanly and accept below VWAP",
            reason=reasons,
            is_chasing=False,
            alert_text=(
                "💎 A+ QQQ CALL ALERT\n\n"
                f"Trigger: {ctx.trigger_level:.2f}\n"
                f"Price: {ctx.current_price:.2f}\n"
                "Setup: Institutional hold + VWAP alignment\n\n"
                "Entry Logic:\n"
                "- 627.50 is holding\n"
                "- VWAP confirms\n"
                "- Structure is forming a higher low / retest hold\n\n"
                "Targets:\n"
                "- 629.00\n"
                "- 630.00\n"
                "- 631.00+\n\n"
                "Invalidation:\n"
                "- Clean loss of 627.50\n"
                "- Acceptance below VWAP"
            ),
        )

    # Late long above trigger
    if (
        (ctx.current_price > ctx.trigger_level + 0.30 and ctx.current_price <= ctx.resistance_1)
        and bull_confirmations >= 2
    ):
        return TradeDecision(
            ticker=ctx.symbol,
            bias="CALL",
            grade="B" if bull_chasing else "A",
            setup_name="Late Long Above 627.50",
            trigger_level=ctx.trigger_level,
            entry_zone="Only on pullback, not on extension",
            targets=["629.00", "630.00"],
            invalidation="Loss of intraday support / return under 627.50",
            reason=reasons + [
                "Long idea still has structure, but price is no longer at the best location."
            ],
            is_chasing=bull_chasing,
            alert_text=(
                "⚠️ QQQ LONG SETUP NOT AT IDEAL LOCATION\n\n"
                f"Price is above the key {ctx.trigger_level:.2f} trigger.\n"
                "This can still work, but reward/risk is worse here.\n\n"
                f"Grade: {'B' if bull_chasing else 'A'}\n"
                "Best action: wait for pullback or retest instead of chasing."
            ),
        )

    # -------------------------
    # BEARISH CONDITIONS
    # -------------------------
    bear_reasons: List[str] = []
    bear_confirmations = 0

    if st.clean_break_below_trigger:
        bear_confirmations += 1
        bear_reasons.append("627.50 broke cleanly.")

    if st.acceptance_below_trigger:
        bear_confirmations += 1
        bear_reasons.append("Price is accepting below the trigger, not just wicking it.")

    if st.lower_high:
        bear_confirmations += 1
        bear_reasons.append("Lower high confirms weak bounce structure.")

    if st.rejection_at_resistance:
        bear_confirmations += 1
        bear_reasons.append("Rejection formed before continuation lower.")

    if st.failed_bounce:
        bear_confirmations += 1
        bear_reasons.append("Bounce failed, showing weak demand.")

    bear_chasing = puts_chasing(ctx, st)

    # A+ PUT
    if (
        ctx.current_price < ctx.trigger_level
        and bear_confirmations >= 4
        and not bear_chasing
    ):
        return TradeDecision(
            ticker=ctx.symbol,
            bias="PUT",
            grade="A+",
            setup_name="627.50 Failure + Acceptance Below",
            trigger_level=ctx.trigger_level,
            entry_zone="627.40 down to 627.00 on failed reclaim / acceptance below",
            targets=["626.00", "624.50", "623.50"],
            invalidation="Reclaim of 627.50 and hold above VWAP",
            reason=bear_reasons,
            is_chasing=False,
            alert_text=(
                "💎 A+ QQQ PUT ALERT\n\n"
                f"Trigger: {ctx.trigger_level:.2f}\n"
                f"Price: {ctx.current_price:.2f}\n"
                "Setup: Institutional failure + acceptance below\n\n"
                "Entry Logic:\n"
                "- 627.50 failed\n"
                "- Price accepted below\n"
                "- Bounce is weak / lower high confirmed\n\n"
                "Targets:\n"
                "- 626.00\n"
                "- 624.50\n"
                "- 623.50\n\n"
                "Invalidation:\n"
                "- Strong reclaim of 627.50\n"
                "- Hold back above VWAP"
            ),
        )

    # Late short below trigger
    if (
        ctx.current_price < ctx.trigger_level - 0.50
        and bear_confirmations >= 2
    ):
        return TradeDecision(
            ticker=ctx.symbol,
            bias="PUT",
            grade="B" if bear_chasing else "A",
            setup_name="Late Short Below 627.50",
            trigger_level=ctx.trigger_level,
            entry_zone="Prefer failed reclaim, not extended breakdown",
            targets=["626.00", "624.50"],
            invalidation="Reclaim of 627.50",
            reason=bear_reasons + [
                "Short idea exists, but entry is no longer near the best location."
            ],
            is_chasing=bear_chasing,
            alert_text=(
                "⚠️ QQQ SHORT SETUP NOT AT IDEAL LOCATION\n\n"
                f"Price is already extended below the key {ctx.trigger_level:.2f} trigger.\n"
                f"Grade: {'B' if bear_chasing else 'A'}\n"
                "Best action: wait for failed reclaim instead of chasing breakdown."
            ),
        )

    # -------------------------
    # DEFAULT: NO TRADE
    # -------------------------
    return TradeDecision(
        ticker=ctx.symbol,
        bias="NO TRADE",
        grade="AVOID",
        setup_name="No clean trigger confirmation",
        trigger_level=ctx.trigger_level,
        entry_zone="None",
        targets=[],
        invalidation="None",
        reason=[
            "Price has not confirmed hold or failure at 627.50 with enough structure."
        ],
        is_chasing=False,
        alert_text=(
            "⛔ NO TRADE\n\n"
            "QQQ is around the decision zone, but structure is not clean enough yet.\n"
            "Wait for one of two things:\n"
            "- 627.50 hold + VWAP confirmation for calls\n"
            "- 627.50 failure + acceptance below for puts"
        ),
    )


# =========================
# DISCORD FORMATTER
# =========================

def format_discord_alert(decision: TradeDecision) -> str:
    reasons_text = "\n".join([f"- {r}" for r in decision.reason]) if decision.reason else "- None"
    targets_text = "\n".join([f"- {t}" for t in decision.targets]) if decision.targets else "- None"
    chasing_text = "YES" if decision.is_chasing else "NO"

    return (
        f"{decision.alert_text}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Ticker: {decision.ticker}\n"
        f"Bias: {decision.bias}\n"
        f"Grade: {decision.grade}\n"
        f"Setup: {decision.setup_name}\n"
        f"Trigger Level: {decision.trigger_level:.2f}\n"
        f"Entry Zone: {decision.entry_zone}\n"
        f"Targets:\n{targets_text}\n"
        f"Invalidation: {decision.invalidation}\n"
        f"Chasing: {chasing_text}\n"
        f"Reasons:\n{reasons_text}"
    )


# =========================
# TRAINING EXPORT
# =========================

def decision_confidence_score(decision: TradeDecision, ctx: MarketContext) -> float:
    score = 0.35

    if decision.grade == "A+":
        score = 0.95
    elif decision.grade == "A":
        score = 0.82
    elif decision.grade == "B":
        score = 0.62
    elif decision.grade == "AVOID":
        score = 0.10

    if decision.is_chasing:
        score -= 0.18
    if ctx.prior_move_extended:
        score -= 0.08
    if ctx.rsi >= 75 or ctx.rsi <= 25:
        score -= 0.06

    return round(clamp(score, 0.0, 1.0), 3)


def build_62750_training_example(ctx: MarketContext, st: StructureState, decision: TradeDecision) -> Dict[str, Any]:
    label = TriggerTrainingLabel(
        pattern_name=decision.setup_name,
        bias=decision.bias,
        grade=decision.grade,
        valid_for_entry=decision.bias in ["CALL", "PUT"] and not decision.is_chasing and decision.grade != "AVOID",
        confidence_score=decision_confidence_score(decision, ctx),
        reasons=decision.reason,
    )

    return {
        "features": {
            "symbol": ctx.symbol,
            "current_price": ctx.current_price,
            "vwap": ctx.vwap,
            "rsi": ctx.rsi,

            "trigger_level": ctx.trigger_level,
            "resistance_1": ctx.resistance_1,
            "resistance_2": ctx.resistance_2,
            "support_1": ctx.support_1,
            "support_2": ctx.support_2,

            "above_vwap": int(ctx.above_vwap),
            "below_vwap": int(ctx.below_vwap),
            "near_upper_band": int(ctx.near_upper_band),
            "near_lower_band": int(ctx.near_lower_band),
            "distance_from_trigger": ctx.distance_from_trigger,
            "prior_move_extended": int(ctx.prior_move_extended),

            "hold_at_trigger": int(st.hold_at_trigger),
            "vwap_reclaimed": int(st.vwap_reclaimed),
            "vwap_held": int(st.vwap_held),
            "higher_low": int(st.higher_low),
            "retest_hold": int(st.retest_hold),
            "breakout_candle_with_volume": int(st.breakout_candle_with_volume),

            "rejection_at_resistance": int(st.rejection_at_resistance),
            "lower_high": int(st.lower_high),
            "clean_break_below_trigger": int(st.clean_break_below_trigger),
            "acceptance_below_trigger": int(st.acceptance_below_trigger),
            "failed_bounce": int(st.failed_bounce),

            "no_retest": int(st.no_retest),
            "multiple_same_color_bars_extended": int(st.multiple_same_color_bars_extended),
            "entering_directly_into_resistance": int(st.entering_directly_into_resistance),
            "entering_directly_into_support": int(st.entering_directly_into_support),
        },
        "label": asdict(label),
    }


# =========================
# PIPELINE FEATURES
# =========================

def build_62750_pipeline_features(ctx: MarketContext, decision: TradeDecision) -> Dict[str, Any]:
    direction = "FLAT"
    if decision.bias == "CALL":
        direction = "CALL"
    elif decision.bias == "PUT":
        direction = "PUT"

    mapped_grade = decision.grade if decision.grade in ["A+", "A", "B"] else "AVOID"
    confidence = decision_confidence_score(decision, ctx)
    setup_score = confidence
    entry_quality_score = 0.85 if not decision.is_chasing else 0.35

    return {
        "trigger_62750_setup_name": decision.setup_name,
        "trigger_62750_bias": decision.bias,
        "trigger_62750_grade": decision.grade,
        "trigger_62750_confidence": confidence,
        "trigger_62750_is_chasing": decision.is_chasing,
        "trigger_62750_should_alert": decision.bias in ["CALL", "PUT"] and mapped_grade != "AVOID",

        "direction": direction,
        "trade_grade": mapped_grade,
        "ai_confidence": confidence,
        "setup_score": round(setup_score, 3),
        "entry_quality_score": round(entry_quality_score, 3),
        "macro_alignment_score": 0.50,
    }


# =========================
# ONE-SHOT RUNNER
# =========================

def run_qqq_62750_brain(ctx: MarketContext, st: StructureState) -> Dict[str, Any]:
    decision = make_qqq_62750_decision(ctx, st)
    training_example = build_62750_training_example(ctx, st, decision)
    pipeline_features = build_62750_pipeline_features(ctx, decision)

    return {
        "context": ctx,
        "structure": st,
        "decision": decision,
        "decision_dict": asdict(decision),
        "training_example": training_example,
        "pipeline_features": pipeline_features,
        "bot_text": format_discord_alert(decision),
    }


# =========================
# EXAMPLE SCENARIOS
# =========================

# A+ CALL example
ctx_call = MarketContext(
    symbol="QQQ",
    current_price=627.56,
    vwap=627.42,
    rsi=64.8,
    above_vwap=True,
    near_upper_band=False,
    distance_from_trigger=0.06,
    prior_move_extended=False,
)

st_call = StructureState(
    hold_at_trigger=True,
    vwap_reclaimed=True,
    vwap_held=True,
    higher_low=True,
    retest_hold=True,
    breakout_candle_with_volume=True,
    no_retest=False,
    multiple_same_color_bars_extended=False,
    entering_directly_into_resistance=False,
)

results_call = run_qqq_62750_brain(ctx_call, st_call)

print("=== A+ CALL DECISION ===")
print(json.dumps(results_call["decision_dict"], indent=2))
print("\n=== A+ CALL TRAINING EXAMPLE ===")
print(json.dumps(results_call["training_example"], indent=2))
print("\n=== A+ CALL PIPELINE FEATURES ===")
print(json.dumps(results_call["pipeline_features"], indent=2))
print("\n=== A+ CALL BOT OUTPUT ===")
print(results_call["bot_text"])

print("\n" + "=" * 100 + "\n")

# B / chasing CALL example
ctx_b = MarketContext(
    symbol="QQQ",
    current_price=628.72,
    vwap=627.95,
    rsi=77.5,
    above_vwap=True,
    near_upper_band=True,
    distance_from_trigger=1.22,
    prior_move_extended=True,
)

st_b = StructureState(
    hold_at_trigger=True,
    vwap_held=True,
    higher_low=True,
    no_retest=True,
    multiple_same_color_bars_extended=True,
    entering_directly_into_resistance=True,
)

results_b = run_qqq_62750_brain(ctx_b, st_b)

print("=== LATE / CHASING CALL DECISION ===")
print(json.dumps(results_b["decision_dict"], indent=2))
print("\n=== LATE / CHASING CALL TRAINING EXAMPLE ===")
print(json.dumps(results_b["training_example"], indent=2))
print("\n=== LATE / CHASING CALL PIPELINE FEATURES ===")
print(json.dumps(results_b["pipeline_features"], indent=2))
print("\n=== LATE / CHASING CALL BOT OUTPUT ===")
print(results_b["bot_text"])

# =========================================================
# PREMARKET HIGH / LOW OPEN LOGIC
# ONE-CELL CLEAN VERSION
# =========================================================
# PURPOSE:
# Teach the bot how to interpret premarket high and premarket low
# during the opening session and decide whether to:
# - take CALLS
# - take PUTS
# - avoid chop
#
# CORE IDEA:
# Premarket High = upside trigger / resistance / breakout decision zone
# Premarket Low = downside trigger / support / breakdown decision zone
# VWAP = confirms whether price is truly accepted or rejected
#
# STYLE:
# - Premarket high = calls trigger
# - Premarket low = puts trigger
# - VWAP = control filter
# - No chasing extended opens
# - Range = avoid unless confirmed
#
# BEST USE:
# 9:30am-10:30am ET, but can still remain active later in day.
# =========================================================

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
import json


# =========================================================
# DATA MODELS
# =========================================================

@dataclass
class PremarketLevels:
    premarket_high: float
    premarket_low: float


@dataclass
class OpenMarketState:
    current_price: float
    vwap: float

    # price behavior relative to PM levels
    above_premarket_high: bool = False
    below_premarket_low: bool = False
    inside_premarket_range: bool = True

    broke_premarket_high: bool = False
    broke_premarket_low: bool = False

    held_above_premarket_high: bool = False
    held_below_premarket_low: bool = False

    rejected_premarket_high: bool = False
    rejected_premarket_low: bool = False

    retest_holding_high: bool = False
    retest_failing_high: bool = False

    retest_holding_low: bool = False
    retest_failing_low: bool = False

    # trend / confirmation
    above_vwap: bool = False
    below_vwap: bool = False
    vwap_reclaimed: bool = False
    vwap_rejected: bool = False

    higher_low: bool = False
    lower_high: bool = False

    breakout_volume: bool = False
    breakdown_volume: bool = False

    momentum_strong: bool = False
    momentum_fading: bool = False

    # extension / chase filter
    extended_from_vwap_pct: float = 0.0
    extended_from_premarket_high_pct: float = 0.0
    extended_from_premarket_low_pct: float = 0.0

    # optional indicators
    rsi: Optional[float] = None
    macd_histogram_rising: bool = False
    macd_histogram_falling: bool = False


@dataclass
class PremarketDecision:
    bias: str  # CALL / PUT / NEUTRAL / AVOID
    setup: str  # BreakHoldHigh / RejectHigh / BreakHoldLow / RejectLow / Range / None
    grade: str  # A+, A, B+, B, C, AVOID
    entry_allowed: bool
    stop_reference: str
    target_reference: str
    reason: str
    notes: List[str] = field(default_factory=list)


@dataclass
class PremarketTrainingLabel:
    pattern_name: str
    bias: str
    grade: str
    valid_for_entry: bool
    confidence_score: float
    reasons: List[str] = field(default_factory=list)


# =========================================================
# HELPERS
# =========================================================

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def pct_distance(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return abs(a - b) / b * 100.0


# =========================================================
# PREMARKET CONTEXT EVALUATION
# =========================================================

def build_open_market_state(
    current_price: float,
    vwap: float,
    premarket_high: float,
    premarket_low: float,
    broke_premarket_high: bool,
    broke_premarket_low: bool,
    held_above_premarket_high: bool,
    held_below_premarket_low: bool,
    rejected_premarket_high: bool,
    rejected_premarket_low: bool,
    retest_holding_high: bool,
    retest_failing_high: bool,
    retest_holding_low: bool,
    retest_failing_low: bool,
    above_vwap: bool,
    below_vwap: bool,
    vwap_reclaimed: bool,
    vwap_rejected: bool,
    higher_low: bool,
    lower_high: bool,
    breakout_volume: bool,
    breakdown_volume: bool,
    momentum_strong: bool,
    momentum_fading: bool,
    rsi: Optional[float] = None,
    macd_histogram_rising: bool = False,
    macd_histogram_falling: bool = False,
) -> OpenMarketState:

    above_premarket_high = current_price > premarket_high
    below_premarket_low = current_price < premarket_low
    inside_premarket_range = not above_premarket_high and not below_premarket_low

    return OpenMarketState(
        current_price=current_price,
        vwap=vwap,
        above_premarket_high=above_premarket_high,
        below_premarket_low=below_premarket_low,
        inside_premarket_range=inside_premarket_range,
        broke_premarket_high=broke_premarket_high,
        broke_premarket_low=broke_premarket_low,
        held_above_premarket_high=held_above_premarket_high,
        held_below_premarket_low=held_below_premarket_low,
        rejected_premarket_high=rejected_premarket_high,
        rejected_premarket_low=rejected_premarket_low,
        retest_holding_high=retest_holding_high,
        retest_failing_high=retest_failing_high,
        retest_holding_low=retest_holding_low,
        retest_failing_low=retest_failing_low,
        above_vwap=above_vwap,
        below_vwap=below_vwap,
        vwap_reclaimed=vwap_reclaimed,
        vwap_rejected=vwap_rejected,
        higher_low=higher_low,
        lower_high=lower_high,
        breakout_volume=breakout_volume,
        breakdown_volume=breakdown_volume,
        momentum_strong=momentum_strong,
        momentum_fading=momentum_fading,
        extended_from_vwap_pct=pct_distance(current_price, vwap),
        extended_from_premarket_high_pct=pct_distance(current_price, premarket_high),
        extended_from_premarket_low_pct=pct_distance(current_price, premarket_low),
        rsi=rsi,
        macd_histogram_rising=macd_histogram_rising,
        macd_histogram_falling=macd_histogram_falling,
    )


# =========================================================
# CHASE FILTER
# =========================================================

def detect_chase_risk(st: OpenMarketState) -> List[str]:
    warnings = []

    if st.extended_from_vwap_pct >= 1.00:
        warnings.append("Price is extended too far from VWAP.")

    if st.above_premarket_high and st.extended_from_premarket_high_pct >= 0.60:
        warnings.append("Price is too far above premarket high; breakout may already be stretched.")

    if st.below_premarket_low and st.extended_from_premarket_low_pct >= 0.60:
        warnings.append("Price is too far below premarket low; downside may already be stretched.")

    if st.rsi is not None:
        if st.rsi >= 80:
            warnings.append("RSI is extremely extended.")
        elif st.rsi <= 20:
            warnings.append("RSI is extremely compressed.")

    if st.momentum_fading:
        warnings.append("Momentum is fading.")

    return warnings


# =========================================================
# MAIN PREMARKET DECISION ENGINE
# =========================================================

def evaluate_premarket_open_logic(levels: PremarketLevels, st: OpenMarketState) -> PremarketDecision:
    notes: List[str] = []
    chase_warnings = detect_chase_risk(st)

    # -----------------------------------------------------
    # 1. A+ CALL SETUP = Break above PM high + hold + VWAP support
    # -----------------------------------------------------
    if (
        st.broke_premarket_high
        and st.held_above_premarket_high
        and st.retest_holding_high
        and (st.above_vwap or st.vwap_reclaimed)
        and st.breakout_volume
        and (st.higher_low or st.momentum_strong)
    ):
        notes.append("Premarket high broke and held.")
        notes.append("Retest of premarket high is holding.")
        notes.append("VWAP confirms bullish acceptance.")
        notes.append("Volume supports the breakout.")

        if chase_warnings:
            notes.extend(chase_warnings)
            return PremarketDecision(
                bias="CALL",
                setup="BreakHoldHigh",
                grade="B+",
                entry_allowed=False,
                stop_reference="Premarket High / VWAP",
                target_reference="Next resistance / intraday expansion",
                reason="Bullish breakout exists, but entry is too extended. Do not chase.",
                notes=notes,
            )

        return PremarketDecision(
            bias="CALL",
            setup="BreakHoldHigh",
            grade="A+",
            entry_allowed=True,
            stop_reference="Below Premarket High or below VWAP",
            target_reference="Next resistance / opening range expansion / trend continuation",
            reason="Bullish breakout above premarket high is accepted and confirmed.",
            notes=notes,
        )

    # -----------------------------------------------------
    # 2. PUT SETUP = Rejection at PM high
    # -----------------------------------------------------
    if (
        st.rejected_premarket_high
        and st.retest_failing_high
        and (st.below_vwap or st.vwap_rejected)
        and st.lower_high
    ):
        notes.append("Premarket high acted as resistance.")
        notes.append("Breakout failed or was rejected.")
        notes.append("VWAP confirms rejection.")
        notes.append("Lower high suggests trapped buyers.")

        grade = "A" if st.breakdown_volume else "B+"
        if st.breakdown_volume:
            notes.append("Selling volume supports downside move.")

        return PremarketDecision(
            bias="PUT",
            setup="RejectHigh",
            grade=grade,
            entry_allowed=True,
            stop_reference="Above Premarket High / rejection wick high",
            target_reference="VWAP / range low / premarket low",
            reason="Price rejected at premarket high and failed to gain acceptance.",
            notes=notes,
        )

    # -----------------------------------------------------
    # 3. A+ PUT SETUP = Break below PM low + hold + VWAP resistance
    # -----------------------------------------------------
    if (
        st.broke_premarket_low
        and st.held_below_premarket_low
        and st.retest_failing_low
        and (st.below_vwap or st.vwap_rejected)
        and st.breakdown_volume
        and (st.lower_high or st.momentum_strong)
    ):
        notes.append("Premarket low broke and held below.")
        notes.append("Retest of premarket low failed.")
        notes.append("VWAP confirms bearish control.")
        notes.append("Volume supports breakdown.")

        if chase_warnings:
            notes.extend(chase_warnings)
            return PremarketDecision(
                bias="PUT",
                setup="BreakHoldLow",
                grade="B+",
                entry_allowed=False,
                stop_reference="Premarket Low / VWAP",
                target_reference="Next support / intraday flush",
                reason="Bearish breakdown exists, but downside is too extended. Do not chase.",
                notes=notes,
            )

        return PremarketDecision(
            bias="PUT",
            setup="BreakHoldLow",
            grade="A+",
            entry_allowed=True,
            stop_reference="Above Premarket Low or above VWAP",
            target_reference="Next support / opening flush / trend continuation",
            reason="Bearish breakdown below premarket low is accepted and confirmed.",
            notes=notes,
        )

    # -----------------------------------------------------
    # 4. CALL SETUP = Rejection at PM low
    # -----------------------------------------------------
    if (
        st.rejected_premarket_low
        and st.retest_holding_low
        and (st.above_vwap or st.vwap_reclaimed)
        and st.higher_low
    ):
        notes.append("Premarket low held as support.")
        notes.append("Breakdown failed or reversed.")
        notes.append("VWAP confirms reclaim.")
        notes.append("Higher low suggests seller failure.")

        grade = "A" if st.breakout_volume else "B+"
        if st.breakout_volume:
            notes.append("Buying volume supports reversal.")

        return PremarketDecision(
            bias="CALL",
            setup="RejectLow",
            grade=grade,
            entry_allowed=True,
            stop_reference="Below Premarket Low / reversal low",
            target_reference="VWAP / range high / premarket high",
            reason="Price rejected the premarket low and buyers regained control.",
            notes=notes,
        )

    # -----------------------------------------------------
    # 5. INSIDE RANGE = usually chop
    # -----------------------------------------------------
    if st.inside_premarket_range:
        notes.append("Price is trading inside the premarket range.")
        notes.append("No clean breakout or breakdown has been accepted yet.")

        if st.above_vwap and st.higher_low and st.momentum_strong:
            notes.append("Internal bullish structure exists, but range has not resolved.")
            return PremarketDecision(
                bias="CALL",
                setup="InsideRangeBullish",
                grade="B",
                entry_allowed=False,
                stop_reference="VWAP / intraday higher low",
                target_reference="Premarket High",
                reason="Bullish internal structure exists, but still inside range. Wait for confirmation.",
                notes=notes,
            )

        if st.below_vwap and st.lower_high and st.momentum_strong:
            notes.append("Internal bearish structure exists, but range has not resolved.")
            return PremarketDecision(
                bias="PUT",
                setup="InsideRangeBearish",
                grade="B",
                entry_allowed=False,
                stop_reference="VWAP / intraday lower high",
                target_reference="Premarket Low",
                reason="Bearish internal structure exists, but still inside range. Wait for confirmation.",
                notes=notes,
            )

        return PremarketDecision(
            bias="AVOID",
            setup="Range",
            grade="AVOID",
            entry_allowed=False,
            stop_reference="None",
            target_reference="Wait for break of PM high or PM low",
            reason="Inside premarket range = likely chop. No clean edge yet.",
            notes=notes,
        )

    # -----------------------------------------------------
    # 6. DEFAULT FALLBACK
    # -----------------------------------------------------
    return PremarketDecision(
        bias="NEUTRAL",
        setup="None",
        grade="C",
        entry_allowed=False,
        stop_reference="None",
        target_reference="Wait for confirmation",
        reason="Conditions are mixed and do not justify an automated trade.",
        notes=["No valid premarket-high/low setup is fully confirmed."],
    )


# =========================================================
# OPTIONAL EXECUTION FILTER
# =========================================================

def execution_filter_premarket(decision: PremarketDecision, st: OpenMarketState) -> PremarketDecision:
    notes = list(decision.notes)

    if not decision.entry_allowed:
        notes.append("Execution filter blocked the trade.")
        decision.notes = notes
        return decision

    if decision.bias == "CALL" and st.extended_from_vwap_pct >= 1.2:
        notes.append("Call blocked: too extended above VWAP.")
        decision.entry_allowed = False
        decision.grade = "B"
        decision.reason = "Bullish setup exists, but price is too extended above VWAP."
        decision.notes = notes
        return decision

    if decision.bias == "PUT" and st.extended_from_vwap_pct >= 1.2:
        notes.append("Put blocked: too extended below VWAP.")
        decision.entry_allowed = False
        decision.grade = "B"
        decision.reason = "Bearish setup exists, but price is too extended below VWAP."
        decision.notes = notes
        return decision

    decision.notes = notes
    return decision


# =========================================================
# TRAINING LABEL EXPORT
# =========================================================

def premarket_decision_to_training_label(decision: PremarketDecision, st: OpenMarketState) -> PremarketTrainingLabel:
    confidence = 0.35

    if decision.grade == "A+":
        confidence = 0.95
    elif decision.grade == "A":
        confidence = 0.85
    elif decision.grade == "B+":
        confidence = 0.72
    elif decision.grade == "B":
        confidence = 0.58
    elif decision.grade == "C":
        confidence = 0.40
    elif decision.grade == "AVOID":
        confidence = 0.10

    if not decision.entry_allowed:
        confidence = min(confidence, 0.45)

    if st.extended_from_vwap_pct >= 1.0:
        confidence -= 0.10
    if st.momentum_fading:
        confidence -= 0.08
    if st.rsi is not None and (st.rsi >= 80 or st.rsi <= 20):
        confidence -= 0.05

    confidence = clamp(confidence, 0.0, 1.0)

    return PremarketTrainingLabel(
        pattern_name=decision.setup,
        bias=decision.bias,
        grade=decision.grade,
        valid_for_entry=decision.entry_allowed,
        confidence_score=round(confidence, 3),
        reasons=[decision.reason] + decision.notes,
    )


def build_premarket_training_example(levels: PremarketLevels, st: OpenMarketState) -> Dict[str, Any]:
    decision = evaluate_premarket_open_logic(levels, st)
    decision = execution_filter_premarket(decision, st)
    label = premarket_decision_to_training_label(decision, st)

    return {
        "features": {
            "current_price": st.current_price,
            "vwap": st.vwap,
            "premarket_high": levels.premarket_high,
            "premarket_low": levels.premarket_low,

            "above_premarket_high": int(st.above_premarket_high),
            "below_premarket_low": int(st.below_premarket_low),
            "inside_premarket_range": int(st.inside_premarket_range),

            "broke_premarket_high": int(st.broke_premarket_high),
            "broke_premarket_low": int(st.broke_premarket_low),
            "held_above_premarket_high": int(st.held_above_premarket_high),
            "held_below_premarket_low": int(st.held_below_premarket_low),

            "rejected_premarket_high": int(st.rejected_premarket_high),
            "rejected_premarket_low": int(st.rejected_premarket_low),

            "retest_holding_high": int(st.retest_holding_high),
            "retest_failing_high": int(st.retest_failing_high),
            "retest_holding_low": int(st.retest_holding_low),
            "retest_failing_low": int(st.retest_failing_low),

            "above_vwap": int(st.above_vwap),
            "below_vwap": int(st.below_vwap),
            "vwap_reclaimed": int(st.vwap_reclaimed),
            "vwap_rejected": int(st.vwap_rejected),

            "higher_low": int(st.higher_low),
            "lower_high": int(st.lower_high),

            "breakout_volume": int(st.breakout_volume),
            "breakdown_volume": int(st.breakdown_volume),

            "momentum_strong": int(st.momentum_strong),
            "momentum_fading": int(st.momentum_fading),

            "extended_from_vwap_pct": round(st.extended_from_vwap_pct, 4),
            "extended_from_premarket_high_pct": round(st.extended_from_premarket_high_pct, 4),
            "extended_from_premarket_low_pct": round(st.extended_from_premarket_low_pct, 4),

            "rsi": None if st.rsi is None else round(st.rsi, 2),
            "macd_histogram_rising": int(st.macd_histogram_rising),
            "macd_histogram_falling": int(st.macd_histogram_falling),
        },
        "label": asdict(label),
    }


# =========================================================
# DISCORD / BOT OUTPUT FORMATTER
# =========================================================

def format_premarket_decision_for_bot(decision: PremarketDecision, levels: PremarketLevels, st: OpenMarketState) -> str:
    icon = {
        "CALL": "🟢",
        "PUT": "🔴",
        "AVOID": "⚠️",
        "NEUTRAL": "⚪"
    }.get(decision.bias, "⚪")

    allowed_text = "YES" if decision.entry_allowed else "NO"

    lines = [
        f"{icon} PREMARKET OPEN DECISION",
        f"Bias: {decision.bias}",
        f"Setup: {decision.setup}",
        f"Grade: {decision.grade}",
        f"Entry Allowed: {allowed_text}",
        f"Current Price: {st.current_price:.2f}",
        f"VWAP: {st.vwap:.2f}",
        f"Premarket High: {levels.premarket_high:.2f}",
        f"Premarket Low: {levels.premarket_low:.2f}",
        f"Stop Reference: {decision.stop_reference}",
        f"Target Reference: {decision.target_reference}",
        f"Reason: {decision.reason}",
    ]

    if decision.notes:
        lines.append("Notes:")
        for note in decision.notes:
            lines.append(f" - {note}")

    return "\n".join(lines)


# =========================================================
# ONE-SHOT RUNNER
# =========================================================

def run_premarket_open_brain(
    *,
    premarket_high: float,
    premarket_low: float,
    current_price: float,
    vwap: float,
    broke_premarket_high: bool,
    broke_premarket_low: bool,
    held_above_premarket_high: bool,
    held_below_premarket_low: bool,
    rejected_premarket_high: bool,
    rejected_premarket_low: bool,
    retest_holding_high: bool,
    retest_failing_high: bool,
    retest_holding_low: bool,
    retest_failing_low: bool,
    above_vwap: bool,
    below_vwap: bool,
    vwap_reclaimed: bool,
    vwap_rejected: bool,
    higher_low: bool,
    lower_high: bool,
    breakout_volume: bool,
    breakdown_volume: bool,
    momentum_strong: bool,
    momentum_fading: bool,
    rsi: Optional[float] = None,
    macd_histogram_rising: bool = False,
    macd_histogram_falling: bool = False,
) -> Dict[str, Any]:

    levels = PremarketLevels(
        premarket_high=premarket_high,
        premarket_low=premarket_low,
    )

    state = build_open_market_state(
        current_price=current_price,
        vwap=vwap,
        premarket_high=premarket_high,
        premarket_low=premarket_low,
        broke_premarket_high=broke_premarket_high,
        broke_premarket_low=broke_premarket_low,
        held_above_premarket_high=held_above_premarket_high,
        held_below_premarket_low=held_below_premarket_low,
        rejected_premarket_high=rejected_premarket_high,
        rejected_premarket_low=rejected_premarket_low,
        retest_holding_high=retest_holding_high,
        retest_failing_high=retest_failing_high,
        retest_holding_low=retest_holding_low,
        retest_failing_low=retest_failing_low,
        above_vwap=above_vwap,
        below_vwap=below_vwap,
        vwap_reclaimed=vwap_reclaimed,
        vwap_rejected=vwap_rejected,
        higher_low=higher_low,
        lower_high=lower_high,
        breakout_volume=breakout_volume,
        breakdown_volume=breakdown_volume,
        momentum_strong=momentum_strong,
        momentum_fading=momentum_fading,
        rsi=rsi,
        macd_histogram_rising=macd_histogram_rising,
        macd_histogram_falling=macd_histogram_falling,
    )

    decision = evaluate_premarket_open_logic(levels, state)
    decision = execution_filter_premarket(decision, state)
    training_example = build_premarket_training_example(levels, state)

    return {
        "levels": levels,
        "state": state,
        "decision": decision,
        "decision_dict": asdict(decision),
        "training_example": training_example,
        "bot_text": format_premarket_decision_for_bot(decision, levels, state),
    }


# =========================================================
# EXAMPLE INPUTS
# =========================================================

PREMARKET_OPEN_INPUTS = {
    "premarket_high": 396.50,
    "premarket_low": 388.20,
    "current_price": 397.10,
    "vwap": 394.80,

    "broke_premarket_high": True,
    "broke_premarket_low": False,
    "held_above_premarket_high": True,
    "held_below_premarket_low": False,
    "rejected_premarket_high": False,
    "rejected_premarket_low": False,
    "retest_holding_high": True,
    "retest_failing_high": False,
    "retest_holding_low": False,
    "retest_failing_low": False,

    "above_vwap": True,
    "below_vwap": False,
    "vwap_reclaimed": True,
    "vwap_rejected": False,

    "higher_low": True,
    "lower_high": False,

    "breakout_volume": True,
    "breakdown_volume": False,

    "momentum_strong": True,
    "momentum_fading": False,

    "rsi": 72.0,
    "macd_histogram_rising": True,
    "macd_histogram_falling": False,
}


# =========================================================
# RUN
# =========================================================

premarket_results = run_premarket_open_brain(**PREMARKET_OPEN_INPUTS)

print("=== DECISION DICT ===")
print(json.dumps(premarket_results["decision_dict"], indent=2))

print("\n=== TRAINING EXAMPLE ===")
print(json.dumps(premarket_results["training_example"], indent=2))

print("\n=== BOT OUTPUT ===")
print(premarket_results["bot_text"])

# =========================================================
# NEXT CELL: MERGE QQQ RANGE-PRINT LOGIC INTO LIVE / WATCHLIST
# Put this AFTER the QQQ range + print logic engine cell
# =========================================================

import copy
import json
import pandas as pd


# =========================================================
# CONFIG
# How strongly should QQQ range-print logic influence the system?
# =========================================================

QQQ_RANGE_PRINT_MERGE_CONFIG = {
    "enable_range_print_override": True,

    # confidence blend
    "confidence_blend_weight": 0.35,

    # setup score blend
    "setup_score_blend_weight": 0.30,

    # entry quality blend
    "entry_quality_blend_weight": 0.35,

    # respect WAIT / AVOID logic
    "respect_wait_bias": True,

    # if range-print direction conflicts, penalize confidence
    "direction_conflict_penalty": 0.14,

    # if aligned, small boost
    "direction_alignment_boost": 0.05,

    # optional one-step grade changes
    "allow_grade_upgrade": True,
    "allow_grade_downgrade": True,
}


# =========================================================
# GRADE HELPERS
# =========================================================

RANGE_PRINT_GRADE_ORDER = ["A+", "A", "B+", "B", "C", "WAIT", "AVOID"]

def normalize_range_print_grade(grade: str) -> str:
    if grade in RANGE_PRINT_GRADE_ORDER:
        return grade
    return "AVOID"

def rp_grade_index(grade: str) -> int:
    return RANGE_PRINT_GRADE_ORDER.index(normalize_range_print_grade(grade))

def rp_upgrade_grade_one_step(grade: str) -> str:
    idx = rp_grade_index(grade)
    return RANGE_PRINT_GRADE_ORDER[max(0, idx - 1)]

def rp_downgrade_grade_one_step(grade: str) -> str:
    idx = rp_grade_index(grade)
    return RANGE_PRINT_GRADE_ORDER[min(len(RANGE_PRINT_GRADE_ORDER) - 1, idx + 1)]


# =========================================================
# RANGE-PRINT CONTEXT BUILDER FROM INPUTS
# =========================================================

def build_qqq_range_print_context_from_inputs(inputs: dict) -> QQQRangePrintContext:
    return QQQRangePrintContext(
        symbol=inputs["symbol"],
        current_price=float(inputs["price"]),

        trend_4h_bullish=bool(inputs.get("trend_4h_bullish", False)),
        compression_30m_active=bool(inputs.get("compression_30m_active", False)),
        chop_5m_active=bool(inputs.get("chop_5m_active", False)),

        lower_high_active_15m=bool(inputs.get("lower_high_active_15m", False)),
        higher_low_active_15m=bool(inputs.get("higher_low_active_15m", False)),
        above_vwap=bool(inputs.get("above_vwap", False)),
        below_vwap=bool(inputs.get("below_vwap", False)),

        rsi_5m=float(inputs.get("rsi_5m", 50.0)),
        rsi_15m=float(inputs.get("rsi_15m", 50.0)),
        rsi_30m=float(inputs.get("rsi_30m", 50.0)),
        rsi_1h=float(inputs.get("rsi_1h", 50.0)),

        macd_5m=float(inputs.get("macd_5m", 0.0)),
        macd_signal_5m=float(inputs.get("macd_signal_5m", 0.0)),
        macd_hist_5m=float(inputs.get("macd_hist_5m", 0.0)),

        macd_15m=float(inputs.get("macd_15m", 0.0)),
        macd_signal_15m=float(inputs.get("macd_signal_15m", 0.0)),
        macd_hist_15m=float(inputs.get("macd_hist_15m", 0.0)),

        macd_30m=float(inputs.get("macd_30m", 0.0)),
        macd_signal_30m=float(inputs.get("macd_signal_30m", 0.0)),
        macd_hist_30m=float(inputs.get("macd_hist_30m", 0.0)),

        breakout_level=float(inputs.get("breakout_level", 0.0)),
        magnet_level=float(inputs.get("magnet_level", 0.0)),
        breakdown_level=float(inputs.get("breakdown_level", 0.0)),
        support_level_1=float(inputs.get("support_level_1", 0.0)),
        support_level_2=float(inputs.get("support_level_2", 0.0)),

        breakout_volume_present=bool(inputs.get("breakout_volume_present", False)),
        retest_hold_present=bool(inputs.get("retest_hold_present", False)),
        rejection_candle_present=bool(inputs.get("rejection_candle_present", False)),
        failed_breakout_present=bool(inputs.get("failed_breakout_present", False)),
    )


# =========================================================
# RANGE-PRINT OVERRIDE ENGINE
# =========================================================

def merge_qqq_range_print_overrides_into_inputs(
    base_inputs: dict,
    merge_config: dict = None
) -> dict:
    if merge_config is None:
        merge_config = QQQ_RANGE_PRINT_MERGE_CONFIG

    merged = copy.deepcopy(base_inputs)

    if not merge_config.get("enable_range_print_override", True):
        merged["_range_print_merge_note"] = "QQQ range-print override disabled."
        return merged

    # only use for QQQ unless you intentionally want to apply similar logic elsewhere
    if merged.get("symbol", "") != "QQQ":
        merged["_range_print_merge_note"] = "QQQ range-print override skipped because symbol is not QQQ."
        return merged

    ctx = build_qqq_range_print_context_from_inputs(merged)
    range_print_results = run_qqq_range_print_brain(ctx)
    pipeline_overrides = range_print_results["pipeline_features"]
    decision_dict = range_print_results["decision_dict"]

    merged["_range_print_decision"] = decision_dict
    merged["_range_print_pipeline_overrides"] = pipeline_overrides

    base_direction = merged.get("direction", "FLAT")
    base_grade = normalize_range_print_grade(merged.get("trade_grade", "AVOID"))
    base_conf = float(merged.get("ai_confidence", 0.50))
    base_setup = float(merged.get("setup_score", 0.50))
    base_entry = float(merged.get("entry_quality_score", 0.50))

    rp_direction = pipeline_overrides["direction"]
    rp_grade = normalize_range_print_grade(pipeline_overrides["trade_grade"])
    rp_conf = float(pipeline_overrides["ai_confidence"])
    rp_setup = float(pipeline_overrides["setup_score"])
    rp_entry = float(pipeline_overrides["entry_quality_score"])

    conf_w = float(merge_config["confidence_blend_weight"])
    setup_w = float(merge_config["setup_score_blend_weight"])
    entry_w = float(merge_config["entry_quality_blend_weight"])

    new_conf = ((1 - conf_w) * base_conf) + (conf_w * rp_conf)
    new_setup = ((1 - setup_w) * base_setup) + (setup_w * rp_setup)
    new_entry = ((1 - entry_w) * base_entry) + (entry_w * rp_entry)

    if rp_direction in {"CALL", "PUT"}:
        if rp_direction == base_direction:
            new_conf += merge_config["direction_alignment_boost"]
        elif base_direction in {"CALL", "PUT"} and rp_direction != base_direction:
            new_conf -= merge_config["direction_conflict_penalty"]

    if merge_config["respect_wait_bias"]:
        if decision_dict.get("grade") == "WAIT" or rp_direction == "FLAT":
            if base_direction in {"CALL", "PUT"}:
                new_conf = min(new_conf, 0.35)
                new_setup = min(new_setup, 0.40)

    new_grade = base_grade

    if merge_config["allow_grade_upgrade"]:
        if rp_direction == base_direction and rp_grade in {"A+", "A", "B"} and base_grade in {"B+", "B", "C"}:
            new_grade = rp_upgrade_grade_one_step(new_grade)

    if merge_config["allow_grade_downgrade"]:
        if decision_dict.get("grade") == "WAIT" and base_grade in {"A+", "A", "B+", "B", "C"}:
            new_grade = rp_downgrade_grade_one_step(new_grade)
        elif rp_direction in {"CALL", "PUT"} and base_direction in {"CALL", "PUT"} and rp_direction != base_direction:
            new_grade = rp_downgrade_grade_one_step(new_grade)

    merged["ai_confidence"] = round(clamp01(new_conf), 3)
    merged["setup_score"] = round(clamp01(new_setup), 3)
    merged["entry_quality_score"] = round(clamp01(new_entry), 3)

    # map WAIT -> AVOID for the bigger system if needed
    mapped_grade = new_grade
    if mapped_grade == "WAIT":
        mapped_grade = "AVOID"
    merged["trade_grade"] = mapped_grade

    if merged.get("direction", "FLAT") == "FLAT" and rp_direction in {"CALL", "PUT"}:
        merged["direction"] = rp_direction

    merged["_range_print_merge_note"] = (
        f"QQQ range-print merged: setup={decision_dict.get('setup_name')}, "
        f"bias={decision_dict.get('bias')}, grade={decision_dict.get('grade')}, "
        f"base_direction={base_direction}, final_grade={mapped_grade}"
    )

    return merged


# =========================================================
# ONE-SHOT LIVE RUNNER WITH RANGE-PRINT MERGE
# =========================================================

def run_live_trade_case_with_range_print(
    memory: MemoryStore,
    inputs: dict,
    merge_config: dict = None,
):
    merged_inputs = merge_qqq_range_print_overrides_into_inputs(inputs, merge_config=merge_config)

    live_results = run_live_trade_case(
        memory=memory,
        inputs=merged_inputs,
    )

    live_results["range_print_decision"] = merged_inputs.get("_range_print_decision", {})
    live_results["range_print_pipeline_overrides"] = merged_inputs.get("_range_print_pipeline_overrides", {})
    live_results["range_print_merge_note"] = merged_inputs.get("_range_print_merge_note", "")
    live_results["merged_inputs"] = merged_inputs

    return live_results


# =========================================================
# WATCHLIST RUNNER WITH RANGE-PRINT MERGE
# =========================================================

def run_watchlist_cases_with_range_print(
    memory: MemoryStore,
    base_inputs: dict,
    watchlist_cases: list,
    merge_config: dict = None,
):
    all_results = []

    for case in watchlist_cases:
        case_name = case.get("case_name", "Unnamed Case")
        case_inputs = build_case_inputs(base_inputs, case)

        try:
            results = run_live_trade_case_with_range_print(
                memory=memory,
                inputs=case_inputs,
                merge_config=merge_config,
            )

            verdict = results["rl_augmented_verdict"]
            rp_decision = results.get("range_print_decision", {})

            row = {
                "case_name": case_name,
                "symbol": case_inputs["symbol"],
                "direction": results["merged_inputs"]["direction"],
                "setup_name": case_inputs["setup_name"],
                "status": verdict.final_status,
                "grade": verdict.final_grade,
                "blocked": verdict.blocked,
                "final_ai_confidence": verdict.final_ai_confidence,
                "final_size_fraction": verdict.final_size_fraction,
                "rl_agent": verdict.selected_rl_agent,
                "rl_regime_bias": verdict.rl_regime_bias,
                "rl_confidence": verdict.rl_ensemble_confidence,
                "range_print_setup": rp_decision.get("setup_name", ""),
                "range_print_bias": rp_decision.get("bias", ""),
                "range_print_grade": rp_decision.get("grade", ""),
                "approved_for_execution": verdict.approved_for_execution,
                "should_alert_discord": verdict.should_alert_discord,
                "opportunity_score": compute_watchlist_opportunity_score(verdict),
                "top_reason": verdict.reasons[0] if verdict.reasons else "",
                "top_warning": verdict.warnings[0] if verdict.warnings else "",
                "top_blocker": verdict.blockers[0] if verdict.blockers else "",
                "range_print_note": results.get("range_print_merge_note", ""),
                "raw_results": results,
            }

        except Exception as e:
            row = {
                "case_name": case_name,
                "symbol": case.get("symbol", ""),
                "direction": case.get("direction", ""),
                "setup_name": case.get("setup_name", ""),
                "status": "ERROR",
                "grade": "AVOID",
                "blocked": True,
                "final_ai_confidence": 0.0,
                "final_size_fraction": 0.0,
                "rl_agent": "",
                "rl_regime_bias": "",
                "rl_confidence": 0.0,
                "range_print_setup": "",
                "range_print_bias": "",
                "range_print_grade": "",
                "approved_for_execution": False,
                "should_alert_discord": False,
                "opportunity_score": -9999.0,
                "top_reason": "",
                "top_warning": "",
                "top_blocker": str(e),
                "range_print_note": "Error",
                "raw_results": None,
            }

        all_results.append(row)

    return all_results


# =========================================================
# DISPLAY HELPERS
# =========================================================

def print_live_trade_case_with_range_print_summary(results: dict):
    market = results["market"]
    signal = results["signal"]
    rl_decision = results["rl_decision"]
    rl_augmented_verdict = results["rl_augmented_verdict"]

    print("=== RANGE-PRINT MERGE NOTE ===")
    print(results.get("range_print_merge_note", ""))

    print("\n=== RANGE-PRINT DECISION ===")
    print(json.dumps(results.get("range_print_decision", {}), indent=2))

    print("\n=== RANGE-PRINT OVERRIDES ===")
    print(json.dumps(results.get("range_print_pipeline_overrides", {}), indent=2))

    print("\n=== RL DECISION ===")
    print(json.dumps(rl_decision_to_dict(rl_decision), indent=2))

    print("\n=== FINAL RL-AUGMENTED VERDICT ===")
    print(json.dumps(rl_augmented_verdict_to_dict(rl_augmented_verdict), indent=2))

    print("\n=== FINAL ALERT ===")
    print(format_rl_augmented_alert(market, signal, rl_augmented_verdict))


def watchlist_results_with_range_print_to_dataframe(results: list) -> pd.DataFrame:
    if not results:
        return pd.DataFrame()

    df = pd.DataFrame([
        {k: v for k, v in r.items() if k != "raw_results"}
        for r in results
    ])

    if not df.empty:
        df = df.sort_values(
            by=["blocked", "opportunity_score", "final_size_fraction", "final_ai_confidence"],
            ascending=[True, False, False, False]
        ).reset_index(drop=True)

    return df


def print_watchlist_summary_with_range_print(results: list):
    df = watchlist_results_with_range_print_to_dataframe(results)

    if df.empty:
        print("No watchlist results.")
        return

    print("=== WATCHLIST RANKING WITH RANGE-PRINT MERGE ===")
    print(df.to_string(index=False))

    valid = [r for r in results if r.get("raw_results") is not None]
    if valid:
        best = sorted(valid, key=lambda x: x["opportunity_score"], reverse=True)[0]
        print("\n=== TOP OPPORTUNITY ===")
        print(json.dumps({
            "case_name": best["case_name"],
            "symbol": best["symbol"],
            "direction": best["direction"],
            "setup_name": best["setup_name"],
            "status": best["status"],
            "grade": best["grade"],
            "blocked": best["blocked"],
            "final_ai_confidence": best["final_ai_confidence"],
            "final_size_fraction": best["final_size_fraction"],
            "rl_agent": best["rl_agent"],
            "rl_regime_bias": best["rl_regime_bias"],
            "rl_confidence": best["rl_confidence"],
            "range_print_setup": best["range_print_setup"],
            "range_print_bias": best["range_print_bias"],
            "range_print_grade": best["range_print_grade"],
            "approved_for_execution": best["approved_for_execution"],
            "opportunity_score": best["opportunity_score"],
            "top_reason": best["top_reason"],
            "top_warning": best["top_warning"],
            "top_blocker": best["top_blocker"],
            "range_print_note": best["range_print_note"],
        }, indent=2))


# =========================================================
# OPTIONAL EXAMPLE INPUTS FOR QQQ RANGE-PRINT FIELDS
# Add these into LIVE_INPUTS / WATCHLIST cases if not already present
# =========================================================

QQQ_RANGE_PRINT_FIELDS_EXAMPLE = {
    "trend_4h_bullish": True,
    "compression_30m_active": True,
    "chop_5m_active": True,

    "lower_high_active_15m": True,
    "higher_low_active_15m": False,
    "above_vwap": True,
    "below_vwap": False,

    "rsi_5m": 54.77,
    "rsi_15m": 51.89,
    "rsi_30m": 54.42,
    "rsi_1h": 64.20,

    "macd_5m": 0.06,
    "macd_signal_5m": 0.02,
    "macd_hist_5m": 0.05,

    "macd_15m": -0.05,
    "macd_signal_15m": -0.08,
    "macd_hist_15m": 0.03,

    "macd_30m": 0.23,
    "macd_signal_30m": 0.39,
    "macd_hist_30m": -0.16,

    "breakout_level": 628.60,
    "magnet_level": 627.60,
    "breakdown_level": 627.20,
    "support_level_1": 626.00,
    "support_level_2": 624.50,

    "breakout_volume_present": False,
    "retest_hold_present": False,
    "rejection_candle_present": False,
    "failed_breakout_present": False,
}


# =========================================================
# RUN SINGLE CASE WITH RANGE-PRINT MERGE
# Assumes LIVE_INPUTS exists
# =========================================================

live_inputs_with_range_print = copy.deepcopy(LIVE_INPUTS)
live_inputs_with_range_print.update(QQQ_RANGE_PRINT_FIELDS_EXAMPLE)

live_results_with_range_print = run_live_trade_case_with_range_print(
    memory=memory,
    inputs=live_inputs_with_range_print,
    merge_config=QQQ_RANGE_PRINT_MERGE_CONFIG,
)

print_live_trade_case_with_range_print_summary(live_results_with_range_print)


# =========================================================
# RUN WATCHLIST WITH RANGE-PRINT MERGE
# Assumes WATCHLIST_CASES exists
# =========================================================

watchlist_results_with_range_print = run_watchlist_cases_with_range_print(
    memory=memory,
    base_inputs=live_inputs_with_range_print,
    watchlist_cases=WATCHLIST_CASES,
    merge_config=QQQ_RANGE_PRINT_MERGE_CONFIG,
)

print("\n")
print_watchlist_summary_with_range_print(watchlist_results_with_range_print)

# =========================================================
# QQQ RANGE + PRINT LOGIC ENGINE
# ONE-CELL CLEAN COLAB VERSION
# =========================================================
# PURPOSE:
# Teach the system how to read a QQQ decision zone built around:
# - 4H bullish trend
# - 30m compression
# - 5m chop
# - key print / breakout / breakdown levels
# - VWAP
# - RSI / MACD
# - breakout hold vs failed rotation
#
# STYLE LOGIC:
# - 628.60 = breakout ceiling
# - 627.60 = magnet / pivot
# - 627.20 = breakdown trigger
# - 626.00 / 624.50 = support targets
#
# SYSTEM BEHAVIOR:
# - Wait in compression/chop decision zone
# - CALL on accepted break-hold above breakout level
# - PUT on failed range hold / breakdown rotation
# - Block chasing if extended
# =========================================================

from __future__ import annotations
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional, List, Dict, Any
import json


# =========================================================
# DATA MODELS
# =========================================================

@dataclass
class QQQRangePrintContext:
    symbol: str
    current_price: float

    # higher timeframe
    trend_4h_bullish: bool
    compression_30m_active: bool
    chop_5m_active: bool

    # structure
    lower_high_active_15m: bool
    higher_low_active_15m: bool
    above_vwap: bool
    below_vwap: bool

    # momentum
    rsi_5m: float
    rsi_15m: float
    rsi_30m: float
    rsi_1h: float

    macd_5m: float
    macd_signal_5m: float
    macd_hist_5m: float

    macd_15m: float
    macd_signal_15m: float
    macd_hist_15m: float

    macd_30m: float
    macd_signal_30m: float
    macd_hist_30m: float

    # key levels
    breakout_level: float     # 628.60
    magnet_level: float       # 627.60
    breakdown_level: float    # 627.20
    support_level_1: float    # 626.00
    support_level_2: float    # 624.50

    # confirmations
    breakout_volume_present: bool
    retest_hold_present: bool
    rejection_candle_present: bool
    failed_breakout_present: bool


@dataclass
class LogicDecision:
    timestamp: str
    symbol: str
    setup_name: str
    bias: str
    grade: str
    entry_type: str
    should_alert: bool
    chasing_blocked: bool
    trigger_level: Optional[float]
    stop_level: Optional[float]
    target_1: Optional[float]
    target_2: Optional[float]
    target_3: Optional[float]
    reason: str
    notes: List[str] = field(default_factory=list)


@dataclass
class RangePrintTrainingLabel:
    pattern_name: str
    bias: str
    grade: str
    valid_for_entry: bool
    confidence_score: float
    reasons: List[str] = field(default_factory=list)


# =========================================================
# HELPERS
# =========================================================

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def macd_bullish(macd: float, signal: float, hist: float) -> bool:
    return macd > signal and hist >= 0


def macd_bearish(macd: float, signal: float, hist: float) -> bool:
    return macd < signal and hist <= 0


def in_range(price: float, low: float, high: float) -> bool:
    return low <= price <= high


# =========================================================
# CORE DETECTION LOGIC
# =========================================================

def detect_wait_zone(ctx: QQQRangePrintContext) -> bool:
    return all([
        ctx.trend_4h_bullish,
        ctx.compression_30m_active,
        ctx.chop_5m_active,
        in_range(ctx.current_price, ctx.breakdown_level, ctx.breakout_level),
    ])


def detect_bullish_break_hold(ctx: QQQRangePrintContext) -> bool:
    return all([
        ctx.current_price >= ctx.breakout_level,
        ctx.trend_4h_bullish,
        ctx.breakout_volume_present,
        ctx.retest_hold_present,
        ctx.above_vwap,
        macd_bullish(ctx.macd_5m, ctx.macd_signal_5m, ctx.macd_hist_5m),
    ])


def detect_failed_breakdown_or_reject(ctx: QQQRangePrintContext) -> bool:
    return all([
        (ctx.current_price <= ctx.breakdown_level or ctx.below_vwap),
        (ctx.lower_high_active_15m or ctx.rejection_candle_present or ctx.failed_breakout_present),
        macd_bearish(ctx.macd_5m, ctx.macd_signal_5m, ctx.macd_hist_5m),
    ])


def detect_chasing_calls(ctx: QQQRangePrintContext) -> bool:
    return all([
        ctx.current_price > ctx.breakout_level + 0.40,
        ctx.rsi_5m >= 68,
        not ctx.retest_hold_present,
    ])


def detect_chasing_puts(ctx: QQQRangePrintContext) -> bool:
    return all([
        ctx.current_price < ctx.breakdown_level - 0.40,
        ctx.rsi_5m <= 35,
        not ctx.rejection_candle_present,
    ])


# =========================================================
# GRADING
# =========================================================

def grade_bullish(ctx: QQQRangePrintContext) -> str:
    score = 0

    if ctx.trend_4h_bullish:
        score += 2
    if ctx.current_price >= ctx.breakout_level:
        score += 2
    if ctx.breakout_volume_present:
        score += 2
    if ctx.retest_hold_present:
        score += 2
    if ctx.above_vwap:
        score += 1
    if macd_bullish(ctx.macd_5m, ctx.macd_signal_5m, ctx.macd_hist_5m):
        score += 1

    if score >= 9:
        return "A+"
    if score >= 7:
        return "A"
    if score >= 5:
        return "B"
    return "WAIT"


def grade_bearish(ctx: QQQRangePrintContext) -> str:
    score = 0

    if ctx.current_price <= ctx.breakdown_level:
        score += 2
    if ctx.below_vwap:
        score += 1
    if ctx.lower_high_active_15m:
        score += 2
    if ctx.rejection_candle_present or ctx.failed_breakout_present:
        score += 2
    if macd_bearish(ctx.macd_5m, ctx.macd_signal_5m, ctx.macd_hist_5m):
        score += 1
    if ctx.rsi_5m < 50:
        score += 1

    if score >= 8:
        return "A"
    if score >= 6:
        return "B"
    return "WAIT"


# =========================================================
# MAIN ANALYZER
# =========================================================

def analyze_qqq_range_print_logic(ctx: QQQRangePrintContext) -> LogicDecision:
    now = datetime.now().isoformat(timespec="seconds")

    if detect_wait_zone(ctx):
        return LogicDecision(
            timestamp=now,
            symbol=ctx.symbol,
            setup_name="RANGE_PRINT_DECISION_ZONE",
            bias="SLIGHT_BULLISH_HTF",
            grade="WAIT",
            entry_type="NO_TRADE",
            should_alert=False,
            chasing_blocked=False,
            trigger_level=None,
            stop_level=None,
            target_1=None,
            target_2=None,
            target_3=None,
            reason=(
                "4H trend is bullish, but 30m compression and 5m chop show decision-zone conditions. "
                "Price is trapped between breakdown and breakout levels."
            ),
            notes=[
                "Decision zone active.",
                "Wait for expansion.",
                "No clean trigger yet.",
            ],
        )

    if detect_bullish_break_hold(ctx):
        grade = grade_bullish(ctx)

        if detect_chasing_calls(ctx):
            return LogicDecision(
                timestamp=now,
                symbol=ctx.symbol,
                setup_name="PRINT_BREAKOUT_CONTINUATION",
                bias="BULLISH",
                grade="WAIT",
                entry_type="WAIT_FOR_RETEST",
                should_alert=False,
                chasing_blocked=True,
                trigger_level=ctx.breakout_level,
                stop_level=ctx.magnet_level,
                target_1=629.50,
                target_2=630.50,
                target_3=632.00,
                reason="Breakout is active above the print ceiling, but price is extended. Wait for retest hold.",
                notes=[
                    "Bullish breakout confirmed.",
                    "Entry blocked for chasing.",
                    "Need cleaner retest hold.",
                ],
            )

        return LogicDecision(
            timestamp=now,
            symbol=ctx.symbol,
            setup_name="PRINT_BREAKOUT_CONTINUATION",
            bias="BULLISH",
            grade=grade,
            entry_type="CALL",
            should_alert=grade in ["A+", "A", "B"],
            chasing_blocked=False,
            trigger_level=ctx.breakout_level,
            stop_level=ctx.magnet_level,
            target_1=629.50,
            target_2=630.50,
            target_3=632.00,
            reason="Price accepted above breakout level with volume and hold. This confirms bullish expansion out of range.",
            notes=[
                "Accepted above breakout level.",
                "VWAP aligned.",
                "Retest hold confirmed.",
            ],
        )

    if detect_failed_breakdown_or_reject(ctx):
        grade = grade_bearish(ctx)

        if detect_chasing_puts(ctx):
            return LogicDecision(
                timestamp=now,
                symbol=ctx.symbol,
                setup_name="FAILED_RANGE_HOLD_BEARISH_ROTATION",
                bias="BEARISH",
                grade="WAIT",
                entry_type="WAIT_FOR_BOUNCE_REJECT",
                should_alert=False,
                chasing_blocked=True,
                trigger_level=ctx.breakdown_level,
                stop_level=ctx.breakout_level,
                target_1=ctx.support_level_1,
                target_2=ctx.support_level_2,
                target_3=623.50,
                reason="Breakdown is extended below support. Wait for bounce and rejection. Do not chase.",
                notes=[
                    "Bearish rotation active.",
                    "Entry blocked for chasing.",
                    "Need bounce/reject for cleaner put entry.",
                ],
            )

        return LogicDecision(
            timestamp=now,
            symbol=ctx.symbol,
            setup_name="FAILED_RANGE_HOLD_BEARISH_ROTATION",
            bias="BEARISH",
            grade=grade,
            entry_type="PUT",
            should_alert=grade in ["A", "B"],
            chasing_blocked=False,
            trigger_level=ctx.breakdown_level,
            stop_level=ctx.breakout_level,
            target_1=ctx.support_level_1,
            target_2=ctx.support_level_2,
            target_3=623.50,
            reason="Price lost breakdown / VWAP support and rolled over from the top range. This confirms bearish rotation.",
            notes=[
                "Lost key support / VWAP.",
                "Lower-high / rejection logic active.",
                "Downside rotation confirmed.",
            ],
        )

    return LogicDecision(
        timestamp=now,
        symbol=ctx.symbol,
        setup_name="NO_CLEAN_SETUP",
        bias="NEUTRAL",
        grade="WAIT",
        entry_type="NO_TRADE",
        should_alert=False,
        chasing_blocked=False,
        trigger_level=None,
        stop_level=None,
        target_1=None,
        target_2=None,
        target_3=None,
        reason="No clean break-hold or failed-breakdown trigger yet.",
        notes=[
            "Still waiting for confirmation.",
        ],
    )


# =========================================================
# TRAINING LABEL EXPORT
# =========================================================

def decision_confidence_score(decision: LogicDecision, ctx: QQQRangePrintContext) -> float:
    score = 0.40

    if decision.grade == "A+":
        score = 0.95
    elif decision.grade == "A":
        score = 0.85
    elif decision.grade == "B":
        score = 0.68
    elif decision.grade == "WAIT":
        score = 0.30

    if decision.chasing_blocked:
        score -= 0.20
    if ctx.chop_5m_active:
        score -= 0.05
    if ctx.compression_30m_active and decision.entry_type != "NO_TRADE":
        score -= 0.03

    return round(clamp(score, 0.0, 1.0), 3)


def build_range_print_training_example(ctx: QQQRangePrintContext, decision: LogicDecision) -> Dict[str, Any]:
    label = RangePrintTrainingLabel(
        pattern_name=decision.setup_name,
        bias=decision.bias,
        grade=decision.grade,
        valid_for_entry=decision.entry_type in ["CALL", "PUT"] and not decision.chasing_blocked,
        confidence_score=decision_confidence_score(decision, ctx),
        reasons=[decision.reason] + decision.notes,
    )

    return {
        "features": {
            "symbol": ctx.symbol,
            "current_price": ctx.current_price,

            "trend_4h_bullish": int(ctx.trend_4h_bullish),
            "compression_30m_active": int(ctx.compression_30m_active),
            "chop_5m_active": int(ctx.chop_5m_active),

            "lower_high_active_15m": int(ctx.lower_high_active_15m),
            "higher_low_active_15m": int(ctx.higher_low_active_15m),
            "above_vwap": int(ctx.above_vwap),
            "below_vwap": int(ctx.below_vwap),

            "rsi_5m": ctx.rsi_5m,
            "rsi_15m": ctx.rsi_15m,
            "rsi_30m": ctx.rsi_30m,
            "rsi_1h": ctx.rsi_1h,

            "macd_5m": ctx.macd_5m,
            "macd_signal_5m": ctx.macd_signal_5m,
            "macd_hist_5m": ctx.macd_hist_5m,

            "macd_15m": ctx.macd_15m,
            "macd_signal_15m": ctx.macd_signal_15m,
            "macd_hist_15m": ctx.macd_hist_15m,

            "macd_30m": ctx.macd_30m,
            "macd_signal_30m": ctx.macd_signal_30m,
            "macd_hist_30m": ctx.macd_hist_30m,

            "breakout_level": ctx.breakout_level,
            "magnet_level": ctx.magnet_level,
            "breakdown_level": ctx.breakdown_level,
            "support_level_1": ctx.support_level_1,
            "support_level_2": ctx.support_level_2,

            "breakout_volume_present": int(ctx.breakout_volume_present),
            "retest_hold_present": int(ctx.retest_hold_present),
            "rejection_candle_present": int(ctx.rejection_candle_present),
            "failed_breakout_present": int(ctx.failed_breakout_present),
        },
        "label": asdict(label),
    }


# =========================================================
# BOT FORMATTER
# =========================================================

def format_range_print_decision_for_bot(decision: LogicDecision) -> str:
    icon = {
        "BULLISH": "🟢",
        "BEARISH": "🔴",
        "NEUTRAL": "⚪",
        "SLIGHT_BULLISH_HTF": "🟡",
    }.get(decision.bias, "⚪")

    lines = [
        f"{icon} QQQ RANGE + PRINT DECISION",
        f"Timestamp: {decision.timestamp}",
        f"Symbol: {decision.symbol}",
        f"Setup: {decision.setup_name}",
        f"Bias: {decision.bias}",
        f"Grade: {decision.grade}",
        f"Entry Type: {decision.entry_type}",
        f"Should Alert: {'YES' if decision.should_alert else 'NO'}",
        f"Chasing Blocked: {'YES' if decision.chasing_blocked else 'NO'}",
        f"Trigger Level: {decision.trigger_level}",
        f"Stop Level: {decision.stop_level}",
        f"Target 1: {decision.target_1}",
        f"Target 2: {decision.target_2}",
        f"Target 3: {decision.target_3}",
        f"Reason: {decision.reason}",
    ]

    if decision.notes:
        lines.append("Notes:")
        for note in decision.notes:
            lines.append(f" - {note}")

    return "\n".join(lines)


# =========================================================
# PIPELINE FEATURE BLOCK
# =========================================================

def build_range_print_pipeline_features(ctx: QQQRangePrintContext, decision: LogicDecision) -> Dict[str, Any]:
    confidence = decision_confidence_score(decision, ctx)

    direction = "FLAT"
    if decision.entry_type == "CALL":
        direction = "CALL"
    elif decision.entry_type == "PUT":
        direction = "PUT"

    setup_score = confidence
    entry_quality_score = 0.85 if not decision.chasing_blocked else 0.35
    macro_alignment_score = 0.50  # placeholder until you inject macro separately

    return {
        "range_print_setup_name": decision.setup_name,
        "range_print_bias": decision.bias,
        "range_print_grade": decision.grade,
        "range_print_confidence": confidence,
        "range_print_should_alert": decision.should_alert,
        "range_print_chasing_blocked": decision.chasing_blocked,

        "direction": direction,
        "trade_grade": decision.grade if decision.grade in ["A+", "A", "B"] else "AVOID",
        "ai_confidence": confidence,
        "setup_score": round(setup_score, 3),
        "entry_quality_score": round(entry_quality_score, 3),
        "macro_alignment_score": round(macro_alignment_score, 3),
    }


# =========================================================
# ONE-SHOT RUNNER
# =========================================================

def run_qqq_range_print_brain(ctx: QQQRangePrintContext) -> Dict[str, Any]:
    decision = analyze_qqq_range_print_logic(ctx)
    training_example = build_range_print_training_example(ctx, decision)
    pipeline_features = build_range_print_pipeline_features(ctx, decision)

    return {
        "context": ctx,
        "decision": decision,
        "decision_dict": asdict(decision),
        "training_example": training_example,
        "pipeline_features": pipeline_features,
        "bot_text": format_range_print_decision_for_bot(decision),
    }


# =========================================================
# EXAMPLE INPUTS - EDIT THESE
# =========================================================

QQQ_RANGE_PRINT_INPUTS = QQQRangePrintContext(
    symbol="QQQ",
    current_price=628.51,

    trend_4h_bullish=True,
    compression_30m_active=True,
    chop_5m_active=True,

    lower_high_active_15m=True,
    higher_low_active_15m=False,
    above_vwap=True,
    below_vwap=False,

    rsi_5m=54.77,
    rsi_15m=51.89,
    rsi_30m=54.42,
    rsi_1h=64.20,

    macd_5m=0.06,
    macd_signal_5m=0.02,
    macd_hist_5m=0.05,

    macd_15m=-0.05,
    macd_signal_15m=-0.08,
    macd_hist_15m=0.03,

    macd_30m=0.23,
    macd_signal_30m=0.39,
    macd_hist_30m=-0.16,

    breakout_level=628.60,
    magnet_level=627.60,
    breakdown_level=627.20,
    support_level_1=626.00,
    support_level_2=624.50,

    breakout_volume_present=False,
    retest_hold_present=False,
    rejection_candle_present=False,
    failed_breakout_present=False,
)


# =========================================================
# RUN
# =========================================================

qqq_range_print_results = run_qqq_range_print_brain(QQQ_RANGE_PRINT_INPUTS)

print("=== DECISION DICT ===")
print(json.dumps(qqq_range_print_results["decision_dict"], indent=2))

print("\n=== TRAINING EXAMPLE ===")
print(json.dumps(qqq_range_print_results["training_example"], indent=2))

print("\n=== PIPELINE FEATURES ===")
print(json.dumps(qqq_range_print_results["pipeline_features"], indent=2))

print("\n=== BOT OUTPUT ===")
print(qqq_range_print_results["bot_text"])

# =========================================================
# NEXT CELL: MERGE PREMARKET OVERRIDES INTO LIVE / WATCHLIST
# Put this AFTER the premarket score engine + pipeline feature block cell
# =========================================================

import copy
import json
import pandas as pd


# =========================================================
# CONFIG
# How strongly should premarket logic influence the full system?
# =========================================================

PREMARKET_MERGE_CONFIG = {
    "enable_premarket_override": True,

    # Confidence blending
    # final_ai_confidence_input = base * (1-weight) + premarket * weight
    "confidence_blend_weight": 0.35,

    # Setup score blending
    "setup_score_blend_weight": 0.30,

    # Entry quality penalty from chase
    "entry_quality_blend_weight": 0.30,

    # If premarket says AVOID, optionally block direction override
    "respect_premarket_avoid": True,

    # If premarket bias conflicts with the case direction, reduce confidence
    "direction_conflict_penalty": 0.12,

    # If premarket bias supports direction, add small boost
    "direction_alignment_boost": 0.05,

    # Let strong premarket A+/A upgrade weak case grades by at most one step
    "allow_grade_upgrade": True,

    # Let weak premarket downgrade by at most one step
    "allow_grade_downgrade": True,
}


# =========================================================
# GRADE HELPERS
# =========================================================

GRADE_ORDER = ["A+", "A", "B+", "B", "C", "AVOID"]

def normalize_grade_for_merge(grade: str) -> str:
    if grade in GRADE_ORDER:
        return grade
    return "AVOID"

def grade_to_index(grade: str) -> int:
    return GRADE_ORDER.index(normalize_grade_for_merge(grade))

def upgrade_grade_one_step(grade: str) -> str:
    idx = grade_to_index(grade)
    return GRADE_ORDER[max(0, idx - 1)]

def downgrade_grade_one_step(grade: str) -> str:
    idx = grade_to_index(grade)
    return GRADE_ORDER[min(len(GRADE_ORDER) - 1, idx + 1)]


# =========================================================
# PREMARKET STATE BUILDER FROM INPUT DICT
# =========================================================

def build_premarket_state_from_inputs(inputs: dict):
    levels = PremarketLevels(
        premarket_high=float(inputs["premarket_high"]),
        premarket_low=float(inputs["premarket_low"]),
    )

    state = build_open_market_state(
        current_price=float(inputs["price"]),
        vwap=float(inputs["vwap"]),
        premarket_high=float(inputs["premarket_high"]),
        premarket_low=float(inputs["premarket_low"]),

        broke_premarket_high=bool(inputs.get("broke_premarket_high", False)),
        broke_premarket_low=bool(inputs.get("broke_premarket_low", False)),
        held_above_premarket_high=bool(inputs.get("held_above_premarket_high", False)),
        held_below_premarket_low=bool(inputs.get("held_below_premarket_low", False)),
        rejected_premarket_high=bool(inputs.get("rejected_premarket_high", False)),
        rejected_premarket_low=bool(inputs.get("rejected_premarket_low", False)),
        retest_holding_high=bool(inputs.get("retest_holding_high", False)),
        retest_failing_high=bool(inputs.get("retest_failing_high", False)),
        retest_holding_low=bool(inputs.get("retest_holding_low", False)),
        retest_failing_low=bool(inputs.get("retest_failing_low", False)),

        above_vwap=bool(inputs.get("above_vwap", False)),
        below_vwap=bool(inputs.get("below_vwap", False)),
        vwap_reclaimed=bool(inputs.get("vwap_reclaimed", False)),
        vwap_rejected=bool(inputs.get("vwap_rejected", False)),

        higher_low=bool(inputs.get("higher_low", False)),
        lower_high=bool(inputs.get("lower_high", False)),

        breakout_volume=bool(inputs.get("breakout_volume", False)),
        breakdown_volume=bool(inputs.get("breakdown_volume", False)),

        momentum_strong=bool(inputs.get("momentum_strong", False)),
        momentum_fading=bool(inputs.get("momentum_fading", False)),

        rsi=inputs.get("rsi", None),
        macd_histogram_rising=bool(inputs.get("macd_histogram_rising", False)),
        macd_histogram_falling=bool(inputs.get("macd_histogram_falling", False)),
    )

    return levels, state


# =========================================================
# PREMARKET OVERRIDE ENGINE
# =========================================================

def merge_premarket_overrides_into_inputs(
    base_inputs: dict,
    merge_config: dict = None
) -> dict:
    if merge_config is None:
        merge_config = PREMARKET_MERGE_CONFIG

    merged = copy.deepcopy(base_inputs)

    if not merge_config.get("enable_premarket_override", True):
        merged["_premarket_merge_note"] = "Premarket override disabled."
        return merged

    levels, state = build_premarket_state_from_inputs(merged)
    scorecard = build_premarket_scorecard(levels, state)
    premarket_overrides = build_master_pipeline_overrides_from_premarket(scorecard)

    # store metadata
    merged["_premarket_scorecard"] = scorecard_to_dict(scorecard)
    merged["_premarket_pipeline_overrides"] = premarket_overrides

    base_direction = merged.get("direction", "FLAT")
    base_grade = normalize_grade_for_merge(merged.get("trade_grade", "AVOID"))
    base_conf = float(merged.get("ai_confidence", 0.50))
    base_setup = float(merged.get("setup_score", 0.50))
    base_entry = float(merged.get("entry_quality_score", 0.50))

    pm_bias = premarket_overrides["premarket_bias"]
    pm_grade = normalize_grade_for_merge(premarket_overrides["premarket_grade_suggestion"])
    pm_conf = float(premarket_overrides["premarket_confidence"])
    pm_setup = float(premarket_overrides["setup_score"])
    pm_entry = float(premarket_overrides["entry_quality_score"])

    conf_w = float(merge_config["confidence_blend_weight"])
    setup_w = float(merge_config["setup_score_blend_weight"])
    entry_w = float(merge_config["entry_quality_blend_weight"])

    # Blend core scores
    new_conf = ((1 - conf_w) * base_conf) + (conf_w * pm_conf)
    new_setup = ((1 - setup_w) * base_setup) + (setup_w * pm_setup)
    new_entry = ((1 - entry_w) * base_entry) + (entry_w * pm_entry)

    # Direction alignment / conflict handling
    if pm_bias in {"CALL", "PUT"}:
        if pm_bias == base_direction:
            new_conf += merge_config["direction_alignment_boost"]
        elif base_direction in {"CALL", "PUT"} and pm_bias != base_direction:
            new_conf -= merge_config["direction_conflict_penalty"]

    # Respect strong premarket avoid
    if merge_config["respect_premarket_avoid"] and pm_bias == "AVOID":
        if base_direction in {"CALL", "PUT"}:
            new_conf = min(new_conf, 0.35)
            new_setup = min(new_setup, 0.40)

    # Grade adjustment
    new_grade = base_grade

    if merge_config["allow_grade_upgrade"]:
        if pm_bias == base_direction and pm_grade in {"A+", "A"} and base_grade in {"B+", "B", "C"}:
            new_grade = upgrade_grade_one_step(new_grade)

    if merge_config["allow_grade_downgrade"]:
        if pm_bias == "AVOID" and base_grade in {"A+", "A", "B+", "B"}:
            new_grade = downgrade_grade_one_step(new_grade)
        elif pm_bias in {"CALL", "PUT"} and base_direction in {"CALL", "PUT"} and pm_bias != base_direction:
            new_grade = downgrade_grade_one_step(new_grade)

    merged["ai_confidence"] = round(clamp01(new_conf), 3)
    merged["setup_score"] = round(clamp01(new_setup), 3)
    merged["entry_quality_score"] = round(clamp01(new_entry), 3)
    merged["trade_grade"] = new_grade

    # Optional: if base direction is FLAT and premarket is clear, allow premarket to suggest direction
    if merged.get("direction", "FLAT") == "FLAT" and pm_bias in {"CALL", "PUT"}:
        merged["direction"] = pm_bias

    merged["_premarket_merge_note"] = (
        f"Premarket merged: bias={pm_bias}, grade={pm_grade}, "
        f"conf={round(pm_conf,3)}, base_direction={base_direction}, final_grade={new_grade}"
    )

    return merged


# =========================================================
# ONE-SHOT LIVE RUNNER WITH PREMARKET MERGE
# =========================================================

def run_live_trade_case_with_premarket(
    memory: MemoryStore,
    inputs: dict,
    merge_config: dict = None,
):
    merged_inputs = merge_premarket_overrides_into_inputs(inputs, merge_config=merge_config)

    live_results = run_live_trade_case(
        memory=memory,
        inputs=merged_inputs,
    )

    live_results["premarket_scorecard"] = merged_inputs.get("_premarket_scorecard", {})
    live_results["premarket_pipeline_overrides"] = merged_inputs.get("_premarket_pipeline_overrides", {})
    live_results["premarket_merge_note"] = merged_inputs.get("_premarket_merge_note", "")
    live_results["merged_inputs"] = merged_inputs

    return live_results


# =========================================================
# WATCHLIST RUNNER WITH PREMARKET MERGE
# =========================================================

def run_watchlist_cases_with_premarket(
    memory: MemoryStore,
    base_inputs: dict,
    watchlist_cases: list,
    merge_config: dict = None,
):
    all_results = []

    for case in watchlist_cases:
        case_name = case.get("case_name", "Unnamed Case")
        case_inputs = build_case_inputs(base_inputs, case)

        try:
            results = run_live_trade_case_with_premarket(
                memory=memory,
                inputs=case_inputs,
                merge_config=merge_config,
            )

            verdict = results["rl_augmented_verdict"]
            pm_scorecard = results.get("premarket_scorecard", {})

            row = {
                "case_name": case_name,
                "symbol": case_inputs["symbol"],
                "direction": results["merged_inputs"]["direction"],
                "setup_name": case_inputs["setup_name"],
                "status": verdict.final_status,
                "grade": verdict.final_grade,
                "blocked": verdict.blocked,
                "final_ai_confidence": verdict.final_ai_confidence,
                "final_size_fraction": verdict.final_size_fraction,
                "rl_agent": verdict.selected_rl_agent,
                "rl_regime_bias": verdict.rl_regime_bias,
                "rl_confidence": verdict.rl_ensemble_confidence,
                "premarket_bias": pm_scorecard.get("final_bias", ""),
                "premarket_confidence": pm_scorecard.get("confidence_score", 0.0),
                "premarket_grade": pm_scorecard.get("grade_suggestion", ""),
                "approved_for_execution": verdict.approved_for_execution,
                "should_alert_discord": verdict.should_alert_discord,
                "opportunity_score": compute_watchlist_opportunity_score(verdict),
                "top_reason": verdict.reasons[0] if verdict.reasons else "",
                "top_warning": verdict.warnings[0] if verdict.warnings else "",
                "top_blocker": verdict.blockers[0] if verdict.blockers else "",
                "premarket_note": results.get("premarket_merge_note", ""),
                "raw_results": results,
            }

        except Exception as e:
            row = {
                "case_name": case_name,
                "symbol": case.get("symbol", ""),
                "direction": case.get("direction", ""),
                "setup_name": case.get("setup_name", ""),
                "status": "ERROR",
                "grade": "AVOID",
                "blocked": True,
                "final_ai_confidence": 0.0,
                "final_size_fraction": 0.0,
                "rl_agent": "",
                "rl_regime_bias": "",
                "rl_confidence": 0.0,
                "premarket_bias": "",
                "premarket_confidence": 0.0,
                "premarket_grade": "",
                "approved_for_execution": False,
                "should_alert_discord": False,
                "opportunity_score": -9999.0,
                "top_reason": "",
                "top_warning": "",
                "top_blocker": str(e),
                "premarket_note": "Error",
                "raw_results": None,
            }

        all_results.append(row)

    return all_results


# =========================================================
# DISPLAY HELPERS
# =========================================================

def print_live_trade_case_with_premarket_summary(results: dict):
    market = results["market"]
    signal = results["signal"]
    rl_decision = results["rl_decision"]
    rl_augmented_verdict = results["rl_augmented_verdict"]

    print("=== PREMARKET MERGE NOTE ===")
    print(results.get("premarket_merge_note", ""))

    print("\n=== PREMARKET SCORECARD ===")
    print(json.dumps(results.get("premarket_scorecard", {}), indent=2))

    print("\n=== PREMARKET OVERRIDES ===")
    print(json.dumps(results.get("premarket_pipeline_overrides", {}), indent=2))

    print("\n=== RL DECISION ===")
    print(json.dumps(rl_decision_to_dict(rl_decision), indent=2))

    print("\n=== FINAL RL-AUGMENTED VERDICT ===")
    print(json.dumps(rl_augmented_verdict_to_dict(rl_augmented_verdict), indent=2))

    print("\n=== FINAL ALERT ===")
    print(format_rl_augmented_alert(market, signal, rl_augmented_verdict))


def watchlist_results_with_premarket_to_dataframe(results: list) -> pd.DataFrame:
    if not results:
        return pd.DataFrame()

    df = pd.DataFrame([
        {k: v for k, v in r.items() if k != "raw_results"}
        for r in results
    ])

    if not df.empty:
        df = df.sort_values(
            by=["blocked", "opportunity_score", "final_size_fraction", "final_ai_confidence"],
            ascending=[True, False, False, False]
        ).reset_index(drop=True)

    return df


def print_watchlist_summary_with_premarket(results: list):
    df = watchlist_results_with_premarket_to_dataframe(results)

    if df.empty:
        print("No watchlist results.")
        return

    print("=== WATCHLIST RANKING WITH PREMARKET MERGE ===")
    print(df.to_string(index=False))

    valid = [r for r in results if r.get("raw_results") is not None]
    if valid:
        best = sorted(valid, key=lambda x: x["opportunity_score"], reverse=True)[0]
        print("\n=== TOP OPPORTUNITY ===")
        print(json.dumps({
            "case_name": best["case_name"],
            "symbol": best["symbol"],
            "direction": best["direction"],
            "setup_name": best["setup_name"],
            "status": best["status"],
            "grade": best["grade"],
            "blocked": best["blocked"],
            "final_ai_confidence": best["final_ai_confidence"],
            "final_size_fraction": best["final_size_fraction"],
            "rl_agent": best["rl_agent"],
            "rl_regime_bias": best["rl_regime_bias"],
            "rl_confidence": best["rl_confidence"],
            "premarket_bias": best["premarket_bias"],
            "premarket_confidence": best["premarket_confidence"],
            "premarket_grade": best["premarket_grade"],
            "approved_for_execution": best["approved_for_execution"],
            "opportunity_score": best["opportunity_score"],
            "top_reason": best["top_reason"],
            "top_warning": best["top_warning"],
            "top_blocker": best["top_blocker"],
            "premarket_note": best["premarket_note"],
        }, indent=2))


# =========================================================
# OPTIONAL EXAMPLE INPUTS FOR PREMARKET FIELDS
# Add these into LIVE_INPUTS / WATCHLIST cases if not already present
# =========================================================

PREMARKET_FIELDS_EXAMPLE = {
    "premarket_high": 396.50,
    "premarket_low": 388.20,

    "broke_premarket_high": True,
    "broke_premarket_low": False,
    "held_above_premarket_high": True,
    "held_below_premarket_low": False,
    "rejected_premarket_high": False,
    "rejected_premarket_low": False,
    "retest_holding_high": True,
    "retest_failing_high": False,
    "retest_holding_low": False,
    "retest_failing_low": False,

    "above_vwap": True,
    "below_vwap": False,
    "vwap_reclaimed": True,
    "vwap_rejected": False,

    "higher_low": True,
    "lower_high": False,

    "breakout_volume": True,
    "breakdown_volume": False,

    "momentum_strong": True,
    "momentum_fading": False,

    "rsi": 72.0,
    "macd_histogram_rising": True,
    "macd_histogram_falling": False,
}


# =========================================================
# RUN SINGLE CASE WITH PREMARKET MERGE
# Assumes LIVE_INPUTS exists
# =========================================================

live_inputs_with_premarket = copy.deepcopy(LIVE_INPUTS)
live_inputs_with_premarket.update(PREMARKET_FIELDS_EXAMPLE)

live_results_with_premarket = run_live_trade_case_with_premarket(
    memory=memory,
    inputs=live_inputs_with_premarket,
    merge_config=PREMARKET_MERGE_CONFIG,
)

print_live_trade_case_with_premarket_summary(live_results_with_premarket)


# =========================================================
# RUN WATCHLIST WITH PREMARKET MERGE
# Assumes WATCHLIST_CASES exists
# =========================================================

watchlist_results_with_premarket = run_watchlist_cases_with_premarket(
    memory=memory,
    base_inputs=live_inputs_with_premarket,
    watchlist_cases=WATCHLIST_CASES,
    merge_config=PREMARKET_MERGE_CONFIG,
)

print("\n")
print_watchlist_summary_with_premarket(watchlist_results_with_premarket)

# =========================================================
# NEXT CELL: PREMARKET SCORE ENGINE + PIPELINE FEATURE BLOCK
# Put this AFTER the one-cell premarket open logic module
# =========================================================

from dataclasses import dataclass, field
from typing import Dict, Any, List
import json


# =========================================================
# SCORE MODELS
# =========================================================

@dataclass
class PremarketScoreCard:
    bullish_score: float
    bearish_score: float
    range_penalty: float
    chase_penalty: float
    final_bias: str                 # CALL / PUT / AVOID / NEUTRAL
    confidence_score: float         # 0 to 1
    grade_suggestion: str           # A+ / A / B+ / B / C / AVOID
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# =========================================================
# HELPERS
# =========================================================

def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def score_to_grade(conf: float, bias: str) -> str:
    if bias in {"AVOID", "NEUTRAL"}:
        return "AVOID" if conf < 0.30 else "C"
    if conf >= 0.90:
        return "A+"
    if conf >= 0.78:
        return "A"
    if conf >= 0.64:
        return "B+"
    if conf >= 0.50:
        return "B"
    return "C"


# =========================================================
# BULL / BEAR COMPONENT SCORING
# =========================================================

def compute_bullish_score(levels: PremarketLevels, st: OpenMarketState) -> Dict[str, Any]:
    score = 0.0
    reasons = []

    if st.broke_premarket_high:
        score += 0.18
        reasons.append("Broke premarket high.")
    if st.held_above_premarket_high:
        score += 0.18
        reasons.append("Held above premarket high.")
    if st.retest_holding_high:
        score += 0.16
        reasons.append("Retest of premarket high is holding.")
    if st.above_vwap:
        score += 0.12
        reasons.append("Above VWAP.")
    if st.vwap_reclaimed:
        score += 0.08
        reasons.append("VWAP reclaimed.")
    if st.breakout_volume:
        score += 0.10
        reasons.append("Breakout volume confirmed.")
    if st.higher_low:
        score += 0.09
        reasons.append("Higher low present.")
    if st.momentum_strong:
        score += 0.07
        reasons.append("Momentum is strong.")
    if st.rejected_premarket_low and st.retest_holding_low:
        score += 0.10
        reasons.append("Rejected premarket low and held support.")

    if st.momentum_fading:
        score -= 0.06
    if st.below_vwap or st.vwap_rejected:
        score -= 0.12
    if st.lower_high:
        score -= 0.08

    return {
        "score": clamp01(score),
        "reasons": reasons
    }


def compute_bearish_score(levels: PremarketLevels, st: OpenMarketState) -> Dict[str, Any]:
    score = 0.0
    reasons = []

    if st.broke_premarket_low:
        score += 0.18
        reasons.append("Broke premarket low.")
    if st.held_below_premarket_low:
        score += 0.18
        reasons.append("Held below premarket low.")
    if st.retest_failing_low:
        score += 0.16
        reasons.append("Retest of premarket low failed.")
    if st.below_vwap:
        score += 0.12
        reasons.append("Below VWAP.")
    if st.vwap_rejected:
        score += 0.08
        reasons.append("VWAP rejected.")
    if st.breakdown_volume:
        score += 0.10
        reasons.append("Breakdown volume confirmed.")
    if st.lower_high:
        score += 0.09
        reasons.append("Lower high present.")
    if st.momentum_strong:
        score += 0.07
        reasons.append("Downside momentum is strong.")
    if st.rejected_premarket_high and st.retest_failing_high:
        score += 0.10
        reasons.append("Rejected premarket high and failed retest.")

    if st.momentum_fading:
        score -= 0.06
    if st.above_vwap or st.vwap_reclaimed:
        score -= 0.12
    if st.higher_low:
        score -= 0.08

    return {
        "score": clamp01(score),
        "reasons": reasons
    }


# =========================================================
# RANGE / CHASE PENALTIES
# =========================================================

def compute_range_penalty(st: OpenMarketState) -> Dict[str, Any]:
    penalty = 0.0
    warnings = []

    if st.inside_premarket_range:
        penalty += 0.22
        warnings.append("Inside premarket range.")
    if st.inside_premarket_range and not (st.momentum_strong or st.higher_low or st.lower_high):
        penalty += 0.10
        warnings.append("No internal structure inside range.")
    if st.inside_premarket_range and st.above_vwap and st.below_vwap is False:
        penalty += 0.03
    if st.inside_premarket_range and st.momentum_fading:
        penalty += 0.08
        warnings.append("Momentum fading inside range.")

    return {
        "penalty": clamp01(penalty),
        "warnings": warnings
    }


def compute_chase_penalty(st: OpenMarketState) -> Dict[str, Any]:
    penalty = 0.0
    warnings = []

    if st.extended_from_vwap_pct >= 1.00:
        penalty += 0.16
        warnings.append("Extended from VWAP.")
    if st.above_premarket_high and st.extended_from_premarket_high_pct >= 0.60:
        penalty += 0.14
        warnings.append("Extended above premarket high.")
    if st.below_premarket_low and st.extended_from_premarket_low_pct >= 0.60:
        penalty += 0.14
        warnings.append("Extended below premarket low.")
    if st.rsi is not None and st.rsi >= 80:
        penalty += 0.08
        warnings.append("RSI very extended.")
    if st.rsi is not None and st.rsi <= 20:
        penalty += 0.08
        warnings.append("RSI very compressed.")
    if st.momentum_fading:
        penalty += 0.08
        warnings.append("Momentum fading.")
    if st.extended_from_vwap_pct >= 1.20:
        penalty += 0.10
        warnings.append("Severely extended from VWAP.")

    return {
        "penalty": clamp01(penalty),
        "warnings": warnings
    }


# =========================================================
# MASTER SCORE ENGINE
# =========================================================

def build_premarket_scorecard(levels: PremarketLevels, st: OpenMarketState) -> PremarketScoreCard:
    bull = compute_bullish_score(levels, st)
    bear = compute_bearish_score(levels, st)
    range_info = compute_range_penalty(st)
    chase_info = compute_chase_penalty(st)

    bullish_score = bull["score"]
    bearish_score = bear["score"]
    range_penalty = range_info["penalty"]
    chase_penalty = chase_info["penalty"]

    reasons = []
    warnings = []

    reasons.extend(bull["reasons"][:])
    reasons.extend(bear["reasons"][:])

    warnings.extend(range_info["warnings"])
    warnings.extend(chase_info["warnings"])

    # net directional edge
    bull_net = bullish_score - (0.55 * range_penalty) - (0.65 * chase_penalty)
    bear_net = bearish_score - (0.55 * range_penalty) - (0.65 * chase_penalty)

    bull_net = clamp01(bull_net)
    bear_net = clamp01(bear_net)

    # decide final bias
    if bull_net >= 0.55 and bull_net > bear_net + 0.08:
        final_bias = "CALL"
        confidence = bull_net
    elif bear_net >= 0.55 and bear_net > bull_net + 0.08:
        final_bias = "PUT"
        confidence = bear_net
    elif max(bull_net, bear_net) < 0.35:
        final_bias = "AVOID"
        confidence = max(bull_net, bear_net)
    else:
        final_bias = "NEUTRAL"
        confidence = max(bull_net, bear_net)

    grade = score_to_grade(confidence, final_bias)

    return PremarketScoreCard(
        bullish_score=round(bullish_score, 3),
        bearish_score=round(bearish_score, 3),
        range_penalty=round(range_penalty, 3),
        chase_penalty=round(chase_penalty, 3),
        final_bias=final_bias,
        confidence_score=round(confidence, 3),
        grade_suggestion=grade,
        reasons=reasons,
        warnings=warnings,
    )


# =========================================================
# PIPELINE FEATURE EXPORT
# =========================================================

def premarket_scorecard_to_pipeline_features(
    levels: PremarketLevels,
    st: OpenMarketState,
    scorecard: PremarketScoreCard
) -> Dict[str, Any]:
    return {
        "premarket_bias": scorecard.final_bias,
        "premarket_confidence": scorecard.confidence_score,
        "premarket_grade_suggestion": scorecard.grade_suggestion,

        "premarket_bullish_score": scorecard.bullish_score,
        "premarket_bearish_score": scorecard.bearish_score,
        "premarket_range_penalty": scorecard.range_penalty,
        "premarket_chase_penalty": scorecard.chase_penalty,

        "premarket_high": levels.premarket_high,
        "premarket_low": levels.premarket_low,
        "current_price": st.current_price,
        "vwap": st.vwap,

        "above_premarket_high": int(st.above_premarket_high),
        "below_premarket_low": int(st.below_premarket_low),
        "inside_premarket_range": int(st.inside_premarket_range),
        "above_vwap": int(st.above_vwap),
        "below_vwap": int(st.below_vwap),
        "vwap_reclaimed": int(st.vwap_reclaimed),
        "vwap_rejected": int(st.vwap_rejected),

        "extended_from_vwap_pct": round(st.extended_from_vwap_pct, 4),
        "extended_from_premarket_high_pct": round(st.extended_from_premarket_high_pct, 4),
        "extended_from_premarket_low_pct": round(st.extended_from_premarket_low_pct, 4),

        "reasons": scorecard.reasons,
        "warnings": scorecard.warnings,
    }


# =========================================================
# BRIDGE INTO YOUR BIGGER SYSTEM
# =========================================================

def build_master_pipeline_overrides_from_premarket(
    scorecard: PremarketScoreCard
) -> Dict[str, Any]:
    """
    This turns premarket logic into suggested overrides
    for your larger AI pipeline.
    """
    direction = "FLAT"
    trade_grade = "AVOID"

    if scorecard.final_bias == "CALL":
        direction = "CALL"
        trade_grade = scorecard.grade_suggestion
    elif scorecard.final_bias == "PUT":
        direction = "PUT"
        trade_grade = scorecard.grade_suggestion

    ai_confidence = scorecard.confidence_score

    # map scorecard into your broader scoring style
    setup_score = clamp01(max(scorecard.bullish_score, scorecard.bearish_score))
    entry_quality_score = clamp01(1.0 - scorecard.chase_penalty)
    macro_alignment_score = 0.50   # neutral placeholder unless you inject macro separately

    return {
        "direction": direction,
        "trade_grade": trade_grade,
        "ai_confidence": round(ai_confidence, 3),
        "setup_score": round(setup_score, 3),
        "entry_quality_score": round(entry_quality_score, 3),
        "macro_alignment_score": round(macro_alignment_score, 3),
        "premarket_bias": scorecard.final_bias,
        "premarket_confidence": scorecard.confidence_score,
        "premarket_grade_suggestion": scorecard.grade_suggestion,
    }


# =========================================================
# FORMATTERS
# =========================================================

def scorecard_to_dict(scorecard: PremarketScoreCard) -> Dict[str, Any]:
    return {
        "bullish_score": scorecard.bullish_score,
        "bearish_score": scorecard.bearish_score,
        "range_penalty": scorecard.range_penalty,
        "chase_penalty": scorecard.chase_penalty,
        "final_bias": scorecard.final_bias,
        "confidence_score": scorecard.confidence_score,
        "grade_suggestion": scorecard.grade_suggestion,
        "reasons": scorecard.reasons,
        "warnings": scorecard.warnings,
    }


def format_premarket_scorecard(scorecard: PremarketScoreCard) -> str:
    icon = {
        "CALL": "🟢",
        "PUT": "🔴",
        "AVOID": "⚠️",
        "NEUTRAL": "⚪"
    }.get(scorecard.final_bias, "⚪")

    lines = [
        f"{icon} PREMARKET SCORE ENGINE",
        f"Final Bias: {scorecard.final_bias}",
        f"Confidence: {scorecard.confidence_score}",
        f"Grade Suggestion: {scorecard.grade_suggestion}",
        f"Bullish Score: {scorecard.bullish_score}",
        f"Bearish Score: {scorecard.bearish_score}",
        f"Range Penalty: {scorecard.range_penalty}",
        f"Chase Penalty: {scorecard.chase_penalty}",
    ]

    if scorecard.reasons:
        lines.append("Reasons:")
        for x in scorecard.reasons[:8]:
            lines.append(f" - {x}")

    if scorecard.warnings:
        lines.append("Warnings:")
        for x in scorecard.warnings[:8]:
            lines.append(f" - {x}")

    return "\n".join(lines)


# =========================================================
# RUN ON THE EXISTING PREMARKET RESULTS
# Assumes `premarket_results` exists from the previous cell
# =========================================================

levels = premarket_results["levels"]
state = premarket_results["state"]

premarket_scorecard = build_premarket_scorecard(levels, state)
premarket_pipeline_features = premarket_scorecard_to_pipeline_features(levels, state, premarket_scorecard)
premarket_master_overrides = build_master_pipeline_overrides_from_premarket(premarket_scorecard)

print("=== PREMARKET SCORECARD ===")
print(json.dumps(scorecard_to_dict(premarket_scorecard), indent=2))

print("\n=== PIPELINE FEATURES ===")
print(json.dumps(premarket_pipeline_features, indent=2))

print("\n=== MASTER PIPELINE OVERRIDES ===")
print(json.dumps(premarket_master_overrides, indent=2))

print("\n=== HUMAN READABLE ===")
print(format_premarket_scorecard(premarket_scorecard))

# =========================================================
# UNBIASED AI - PREMARKET HIGH / LOW OPEN LOGIC
# ONE-CELL VERSION FOR COLAB
# =========================================================
# PURPOSE:
# Teach the system how to interpret premarket high / low at the open.
#
# CORE RULES:
# - Premarket high = calls trigger if accepted
# - Premarket low = puts trigger if accepted
# - VWAP = control filter
# - No chasing extended opens
# - Inside range = avoid unless structure confirms, but still wait
#
# USE CASE:
# - 9:30am to 10:30am ET primary
# - can still be referenced later in session
# =========================================================

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import json


# =========================================================
# DATA MODELS
# =========================================================

@dataclass
class PremarketLevels:
    premarket_high: float
    premarket_low: float


@dataclass
class OpenMarketState:
    current_price: float
    vwap: float

    # relationship to PM range
    above_premarket_high: bool = False
    below_premarket_low: bool = False
    inside_premarket_range: bool = True

    # event state
    broke_premarket_high: bool = False
    broke_premarket_low: bool = False

    held_above_premarket_high: bool = False
    held_below_premarket_low: bool = False

    rejected_premarket_high: bool = False
    rejected_premarket_low: bool = False

    retest_holding_high: bool = False
    retest_failing_high: bool = False

    retest_holding_low: bool = False
    retest_failing_low: bool = False

    # VWAP / structure / momentum
    above_vwap: bool = False
    below_vwap: bool = False
    vwap_reclaimed: bool = False
    vwap_rejected: bool = False

    higher_low: bool = False
    lower_high: bool = False

    breakout_volume: bool = False
    breakdown_volume: bool = False

    momentum_strong: bool = False
    momentum_fading: bool = False

    # extension / anti-chase
    extended_from_vwap_pct: float = 0.0
    extended_from_premarket_high_pct: float = 0.0
    extended_from_premarket_low_pct: float = 0.0

    # optional indicators
    rsi: Optional[float] = None
    macd_histogram_rising: bool = False
    macd_histogram_falling: bool = False


@dataclass
class PremarketDecision:
    bias: str                      # CALL / PUT / NEUTRAL / AVOID
    setup: str                     # BreakHoldHigh / RejectHigh / BreakHoldLow / RejectLow / Range / None
    grade: str                     # A+ / A / B+ / B / C / AVOID
    entry_allowed: bool
    stop_reference: str
    target_reference: str
    reason: str
    notes: List[str] = field(default_factory=list)


@dataclass
class PremarketTrainingLabel:
    pattern_name: str
    bias: str
    grade: str
    valid_for_entry: bool
    confidence_score: float
    reasons: List[str] = field(default_factory=list)


# =========================================================
# HELPERS
# =========================================================

def pct_distance(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return abs(a - b) / b * 100.0


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# =========================================================
# STATE BUILDER
# =========================================================

def build_open_market_state(
    current_price: float,
    vwap: float,
    premarket_high: float,
    premarket_low: float,
    broke_premarket_high: bool,
    broke_premarket_low: bool,
    held_above_premarket_high: bool,
    held_below_premarket_low: bool,
    rejected_premarket_high: bool,
    rejected_premarket_low: bool,
    retest_holding_high: bool,
    retest_failing_high: bool,
    retest_holding_low: bool,
    retest_failing_low: bool,
    above_vwap: bool,
    below_vwap: bool,
    vwap_reclaimed: bool,
    vwap_rejected: bool,
    higher_low: bool,
    lower_high: bool,
    breakout_volume: bool,
    breakdown_volume: bool,
    momentum_strong: bool,
    momentum_fading: bool,
    rsi: Optional[float] = None,
    macd_histogram_rising: bool = False,
    macd_histogram_falling: bool = False,
) -> OpenMarketState:

    above_premarket_high = current_price > premarket_high
    below_premarket_low = current_price < premarket_low
    inside_premarket_range = not above_premarket_high and not below_premarket_low

    return OpenMarketState(
        current_price=current_price,
        vwap=vwap,
        above_premarket_high=above_premarket_high,
        below_premarket_low=below_premarket_low,
        inside_premarket_range=inside_premarket_range,
        broke_premarket_high=broke_premarket_high,
        broke_premarket_low=broke_premarket_low,
        held_above_premarket_high=held_above_premarket_high,
        held_below_premarket_low=held_below_premarket_low,
        rejected_premarket_high=rejected_premarket_high,
        rejected_premarket_low=rejected_premarket_low,
        retest_holding_high=retest_holding_high,
        retest_failing_high=retest_failing_high,
        retest_holding_low=retest_holding_low,
        retest_failing_low=retest_failing_low,
        above_vwap=above_vwap,
        below_vwap=below_vwap,
        vwap_reclaimed=vwap_reclaimed,
        vwap_rejected=vwap_rejected,
        higher_low=higher_low,
        lower_high=lower_high,
        breakout_volume=breakout_volume,
        breakdown_volume=breakdown_volume,
        momentum_strong=momentum_strong,
        momentum_fading=momentum_fading,
        extended_from_vwap_pct=pct_distance(current_price, vwap),
        extended_from_premarket_high_pct=pct_distance(current_price, premarket_high),
        extended_from_premarket_low_pct=pct_distance(current_price, premarket_low),
        rsi=rsi,
        macd_histogram_rising=macd_histogram_rising,
        macd_histogram_falling=macd_histogram_falling,
    )


# =========================================================
# CHASE FILTER
# =========================================================

def detect_chase_risk(st: OpenMarketState) -> List[str]:
    warnings: List[str] = []

    if st.extended_from_vwap_pct >= 1.00:
        warnings.append("Price is extended too far from VWAP.")

    if st.above_premarket_high and st.extended_from_premarket_high_pct >= 0.60:
        warnings.append("Price is too far above premarket high; breakout may already be stretched.")

    if st.below_premarket_low and st.extended_from_premarket_low_pct >= 0.60:
        warnings.append("Price is too far below premarket low; downside may already be stretched.")

    if st.rsi is not None:
        if st.rsi >= 80:
            warnings.append("RSI is extremely extended.")
        elif st.rsi <= 20:
            warnings.append("RSI is extremely compressed.")

    if st.momentum_fading:
        warnings.append("Momentum is fading.")

    return warnings


# =========================================================
# MAIN PREMARKET DECISION ENGINE
# =========================================================

def evaluate_premarket_open_logic(levels: PremarketLevels, st: OpenMarketState) -> PremarketDecision:
    notes: List[str] = []
    chase_warnings = detect_chase_risk(st)

    # -----------------------------------------------------
    # 1. A+ CALL = break above PM high + hold + retest + VWAP support
    # -----------------------------------------------------
    if (
        st.broke_premarket_high
        and st.held_above_premarket_high
        and st.retest_holding_high
        and (st.above_vwap or st.vwap_reclaimed)
        and st.breakout_volume
        and (st.higher_low or st.momentum_strong)
    ):
        notes.append("Premarket high broke and held.")
        notes.append("Retest of premarket high is holding.")
        notes.append("VWAP confirms bullish acceptance.")
        notes.append("Volume supports the breakout.")

        if chase_warnings:
            notes.extend(chase_warnings)
            return PremarketDecision(
                bias="CALL",
                setup="BreakHoldHigh",
                grade="B+",
                entry_allowed=False,
                stop_reference="Premarket High / VWAP",
                target_reference="Next resistance / intraday expansion",
                reason="Bullish breakout exists, but entry is too extended. Do not chase.",
                notes=notes,
            )

        return PremarketDecision(
            bias="CALL",
            setup="BreakHoldHigh",
            grade="A+",
            entry_allowed=True,
            stop_reference="Below Premarket High or below VWAP",
            target_reference="Next resistance / opening range expansion / trend continuation",
            reason="Bullish breakout above premarket high is accepted and confirmed.",
            notes=notes,
        )

    # -----------------------------------------------------
    # 2. PUT = rejection at PM high
    # -----------------------------------------------------
    if (
        st.rejected_premarket_high
        and st.retest_failing_high
        and (st.below_vwap or st.vwap_rejected)
        and st.lower_high
    ):
        notes.append("Premarket high acted as resistance.")
        notes.append("Breakout failed or was rejected.")
        notes.append("VWAP confirms rejection.")
        notes.append("Lower high suggests trapped buyers.")

        grade = "A" if st.breakdown_volume else "B+"
        if st.breakdown_volume:
            notes.append("Selling volume supports downside move.")

        return PremarketDecision(
            bias="PUT",
            setup="RejectHigh",
            grade=grade,
            entry_allowed=True,
            stop_reference="Above Premarket High / rejection wick high",
            target_reference="VWAP / range low / premarket low",
            reason="Price rejected at premarket high and failed to gain acceptance.",
            notes=notes,
        )

    # -----------------------------------------------------
    # 3. A+ PUT = break below PM low + hold + retest fail + VWAP resistance
    # -----------------------------------------------------
    if (
        st.broke_premarket_low
        and st.held_below_premarket_low
        and st.retest_failing_low
        and (st.below_vwap or st.vwap_rejected)
        and st.breakdown_volume
        and (st.lower_high or st.momentum_strong)
    ):
        notes.append("Premarket low broke and held below.")
        notes.append("Retest of premarket low failed.")
        notes.append("VWAP confirms bearish control.")
        notes.append("Volume supports breakdown.")

        if chase_warnings:
            notes.extend(chase_warnings)
            return PremarketDecision(
                bias="PUT",
                setup="BreakHoldLow",
                grade="B+",
                entry_allowed=False,
                stop_reference="Premarket Low / VWAP",
                target_reference="Next support / intraday flush",
                reason="Bearish breakdown exists, but downside is too extended. Do not chase.",
                notes=notes,
            )

        return PremarketDecision(
            bias="PUT",
            setup="BreakHoldLow",
            grade="A+",
            entry_allowed=True,
            stop_reference="Above Premarket Low or above VWAP",
            target_reference="Next support / opening flush / trend continuation",
            reason="Bearish breakdown below premarket low is accepted and confirmed.",
            notes=notes,
        )

    # -----------------------------------------------------
    # 4. CALL = rejection at PM low
    # -----------------------------------------------------
    if (
        st.rejected_premarket_low
        and st.retest_holding_low
        and (st.above_vwap or st.vwap_reclaimed)
        and st.higher_low
    ):
        notes.append("Premarket low held as support.")
        notes.append("Breakdown failed or reversed.")
        notes.append("VWAP confirms reclaim.")
        notes.append("Higher low suggests seller failure.")

        grade = "A" if st.breakout_volume else "B+"
        if st.breakout_volume:
            notes.append("Buying volume supports reversal.")

        return PremarketDecision(
            bias="CALL",
            setup="RejectLow",
            grade=grade,
            entry_allowed=True,
            stop_reference="Below Premarket Low / reversal low",
            target_reference="VWAP / range high / premarket high",
            reason="Price rejected the premarket low and buyers regained control.",
            notes=notes,
        )

    # -----------------------------------------------------
    # 5. Inside range = avoid unless structure forms, but still wait
    # -----------------------------------------------------
    if st.inside_premarket_range:
        notes.append("Price is trading inside the premarket range.")
        notes.append("No clean breakout or breakdown has been accepted yet.")

        if st.above_vwap and st.higher_low and st.momentum_strong:
            notes.append("Internal bullish structure exists, but range has not resolved.")
            return PremarketDecision(
                bias="CALL",
                setup="InsideRangeBullish",
                grade="B",
                entry_allowed=False,
                stop_reference="VWAP / intraday higher low",
                target_reference="Premarket High",
                reason="Bullish internal structure exists, but still inside range. Wait for confirmation.",
                notes=notes,
            )

        if st.below_vwap and st.lower_high and st.momentum_strong:
            notes.append("Internal bearish structure exists, but range has not resolved.")
            return PremarketDecision(
                bias="PUT",
                setup="InsideRangeBearish",
                grade="B",
                entry_allowed=False,
                stop_reference="VWAP / intraday lower high",
                target_reference="Premarket Low",
                reason="Bearish internal structure exists, but still inside range. Wait for confirmation.",
                notes=notes,
            )

        return PremarketDecision(
            bias="AVOID",
            setup="Range",
            grade="AVOID",
            entry_allowed=False,
            stop_reference="None",
            target_reference="Wait for break of PM high or PM low",
            reason="Inside premarket range = likely chop. No clean edge yet.",
            notes=notes,
        )

    # -----------------------------------------------------
    # 6. Fallback
    # -----------------------------------------------------
    return PremarketDecision(
        bias="NEUTRAL",
        setup="None",
        grade="C",
        entry_allowed=False,
        stop_reference="None",
        target_reference="Wait for confirmation",
        reason="Conditions are mixed and do not justify an automated trade.",
        notes=["No valid premarket-high/low setup is fully confirmed."],
    )


# =========================================================
# EXECUTION FILTER
# =========================================================

def execution_filter_premarket(decision: PremarketDecision, st: OpenMarketState) -> PremarketDecision:
    notes = list(decision.notes)

    if not decision.entry_allowed:
        notes.append("Execution filter blocked the trade.")
        decision.notes = notes
        return decision

    if decision.bias == "CALL" and st.extended_from_vwap_pct >= 1.20:
        notes.append("Call blocked: too extended above VWAP.")
        decision.entry_allowed = False
        decision.grade = "B"
        decision.reason = "Bullish setup exists, but price is too extended above VWAP."
        decision.notes = notes
        return decision

    if decision.bias == "PUT" and st.extended_from_vwap_pct >= 1.20:
        notes.append("Put blocked: too extended below VWAP.")
        decision.entry_allowed = False
        decision.grade = "B"
        decision.reason = "Bearish setup exists, but price is too extended below VWAP."
        decision.notes = notes
        return decision

    decision.notes = notes
    return decision


# =========================================================
# TRAINING LABEL BUILDER
# =========================================================

def premarket_decision_to_training_label(decision: PremarketDecision, st: OpenMarketState) -> PremarketTrainingLabel:
    confidence = 0.35

    if decision.grade == "A+":
        confidence = 0.95
    elif decision.grade == "A":
        confidence = 0.85
    elif decision.grade == "B+":
        confidence = 0.72
    elif decision.grade == "B":
        confidence = 0.58
    elif decision.grade == "C":
        confidence = 0.40
    elif decision.grade == "AVOID":
        confidence = 0.10

    if not decision.entry_allowed:
        confidence = min(confidence, 0.45)

    if st.extended_from_vwap_pct >= 1.0:
        confidence -= 0.10
    if st.momentum_fading:
        confidence -= 0.08
    if st.rsi is not None and (st.rsi >= 80 or st.rsi <= 20):
        confidence -= 0.05

    confidence = clamp(confidence, 0.0, 1.0)

    return PremarketTrainingLabel(
        pattern_name=decision.setup,
        bias=decision.bias,
        grade=decision.grade,
        valid_for_entry=decision.entry_allowed,
        confidence_score=round(confidence, 3),
        reasons=[decision.reason] + decision.notes,
    )


# =========================================================
# FEATURE EXPORT FOR AI LEARNING
# =========================================================

def open_market_state_to_features(levels: PremarketLevels, st: OpenMarketState) -> Dict[str, Any]:
    return {
        "current_price": st.current_price,
        "vwap": st.vwap,
        "premarket_high": levels.premarket_high,
        "premarket_low": levels.premarket_low,

        "above_premarket_high": int(st.above_premarket_high),
        "below_premarket_low": int(st.below_premarket_low),
        "inside_premarket_range": int(st.inside_premarket_range),

        "broke_premarket_high": int(st.broke_premarket_high),
        "broke_premarket_low": int(st.broke_premarket_low),
        "held_above_premarket_high": int(st.held_above_premarket_high),
        "held_below_premarket_low": int(st.held_below_premarket_low),

        "rejected_premarket_high": int(st.rejected_premarket_high),
        "rejected_premarket_low": int(st.rejected_premarket_low),

        "retest_holding_high": int(st.retest_holding_high),
        "retest_failing_high": int(st.retest_failing_high),
        "retest_holding_low": int(st.retest_holding_low),
        "retest_failing_low": int(st.retest_failing_low),

        "above_vwap": int(st.above_vwap),
        "below_vwap": int(st.below_vwap),
        "vwap_reclaimed": int(st.vwap_reclaimed),
        "vwap_rejected": int(st.vwap_rejected),

        "higher_low": int(st.higher_low),
        "lower_high": int(st.lower_high),

        "breakout_volume": int(st.breakout_volume),
        "breakdown_volume": int(st.breakdown_volume),

        "momentum_strong": int(st.momentum_strong),
        "momentum_fading": int(st.momentum_fading),

        "extended_from_vwap_pct": round(st.extended_from_vwap_pct, 4),
        "extended_from_premarket_high_pct": round(st.extended_from_premarket_high_pct, 4),
        "extended_from_premarket_low_pct": round(st.extended_from_premarket_low_pct, 4),

        "rsi": None if st.rsi is None else round(st.rsi, 2),
        "macd_histogram_rising": int(st.macd_histogram_rising),
        "macd_histogram_falling": int(st.macd_histogram_falling),
    }


def build_premarket_training_example(levels: PremarketLevels, st: OpenMarketState) -> Dict[str, Any]:
    decision = evaluate_premarket_open_logic(levels, st)
    decision = execution_filter_premarket(decision, st)
    label = premarket_decision_to_training_label(decision, st)

    return {
        "features": open_market_state_to_features(levels, st),
        "label": {
            "pattern_name": label.pattern_name,
            "bias": label.bias,
            "grade": label.grade,
            "valid_for_entry": label.valid_for_entry,
            "confidence_score": label.confidence_score,
            "reasons": label.reasons,
        }
    }


# =========================================================
# BOT / DISCORD FORMATTERS
# =========================================================

def format_premarket_decision_for_bot(decision: PremarketDecision, levels: PremarketLevels, st: OpenMarketState) -> str:
    icon = {
        "CALL": "🟢",
        "PUT": "🔴",
        "AVOID": "⚠️",
        "NEUTRAL": "⚪",
    }.get(decision.bias, "⚪")

    allowed_text = "YES" if decision.entry_allowed else "NO"

    lines = [
        f"{icon} PREMARKET OPEN DECISION",
        f"Bias: {decision.bias}",
        f"Setup: {decision.setup}",
        f"Grade: {decision.grade}",
        f"Entry Allowed: {allowed_text}",
        f"Current Price: {st.current_price:.2f}",
        f"VWAP: {st.vwap:.2f}",
        f"Premarket High: {levels.premarket_high:.2f}",
        f"Premarket Low: {levels.premarket_low:.2f}",
        f"Stop Reference: {decision.stop_reference}",
        f"Target Reference: {decision.target_reference}",
        f"Reason: {decision.reason}",
    ]

    if decision.notes:
        lines.append("Notes:")
        for note in decision.notes:
            lines.append(f" - {note}")

    return "\n".join(lines)


def decision_to_dict(decision: PremarketDecision) -> Dict[str, Any]:
    return {
        "bias": decision.bias,
        "setup": decision.setup,
        "grade": decision.grade,
        "entry_allowed": decision.entry_allowed,
        "stop_reference": decision.stop_reference,
        "target_reference": decision.target_reference,
        "reason": decision.reason,
        "notes": decision.notes,
    }


# =========================================================
# MASTER ONE-SHOT RUNNER
# =========================================================

def run_premarket_open_brain(
    *,
    premarket_high: float,
    premarket_low: float,
    current_price: float,
    vwap: float,

    broke_premarket_high: bool,
    broke_premarket_low: bool,
    held_above_premarket_high: bool,
    held_below_premarket_low: bool,
    rejected_premarket_high: bool,
    rejected_premarket_low: bool,
    retest_holding_high: bool,
    retest_failing_high: bool,
    retest_holding_low: bool,
    retest_failing_low: bool,

    above_vwap: bool,
    below_vwap: bool,
    vwap_reclaimed: bool,
    vwap_rejected: bool,

    higher_low: bool,
    lower_high: bool,

    breakout_volume: bool,
    breakdown_volume: bool,

    momentum_strong: bool,
    momentum_fading: bool,

    rsi: Optional[float] = None,
    macd_histogram_rising: bool = False,
    macd_histogram_falling: bool = False,
) -> Dict[str, Any]:

    levels = PremarketLevels(
        premarket_high=premarket_high,
        premarket_low=premarket_low,
    )

    state = build_open_market_state(
        current_price=current_price,
        vwap=vwap,
        premarket_high=premarket_high,
        premarket_low=premarket_low,
        broke_premarket_high=broke_premarket_high,
        broke_premarket_low=broke_premarket_low,
        held_above_premarket_high=held_above_premarket_high,
        held_below_premarket_low=held_below_premarket_low,
        rejected_premarket_high=rejected_premarket_high,
        rejected_premarket_low=rejected_premarket_low,
        retest_holding_high=retest_holding_high,
        retest_failing_high=retest_failing_high,
        retest_holding_low=retest_holding_low,
        retest_failing_low=retest_failing_low,
        above_vwap=above_vwap,
        below_vwap=below_vwap,
        vwap_reclaimed=vwap_reclaimed,
        vwap_rejected=vwap_rejected,
        higher_low=higher_low,
        lower_high=lower_high,
        breakout_volume=breakout_volume,
        breakdown_volume=breakdown_volume,
        momentum_strong=momentum_strong,
        momentum_fading=momentum_fading,
        rsi=rsi,
        macd_histogram_rising=macd_histogram_rising,
        macd_histogram_falling=macd_histogram_falling,
    )

    decision = evaluate_premarket_open_logic(levels, state)
    filtered_decision = execution_filter_premarket(decision, state)
    training_example = build_premarket_training_example(levels, state)

    return {
        "levels": levels,
        "state": state,
        "decision": filtered_decision,
        "decision_dict": decision_to_dict(filtered_decision),
        "training_example": training_example,
        "bot_text": format_premarket_decision_for_bot(filtered_decision, levels, state),
    }


# =========================================================
# EXAMPLE INPUTS - EDIT THESE EACH DAY
# =========================================================

PREMARKET_OPEN_INPUTS = {
    "premarket_high": 396.50,
    "premarket_low": 388.20,
    "current_price": 397.10,
    "vwap": 394.80,

    "broke_premarket_high": True,
    "broke_premarket_low": False,
    "held_above_premarket_high": True,
    "held_below_premarket_low": False,
    "rejected_premarket_high": False,
    "rejected_premarket_low": False,
    "retest_holding_high": True,
    "retest_failing_high": False,
    "retest_holding_low": False,
    "retest_failing_low": False,

    "above_vwap": True,
    "below_vwap": False,
    "vwap_reclaimed": True,
    "vwap_rejected": False,

    "higher_low": True,
    "lower_high": False,

    "breakout_volume": True,
    "breakdown_volume": False,

    "momentum_strong": True,
    "momentum_fading": False,

    "rsi": 72.0,
    "macd_histogram_rising": True,
    "macd_histogram_falling": False,
}


# =========================================================
# RUN
# =========================================================

premarket_results = run_premarket_open_brain(**PREMARKET_OPEN_INPUTS)

print("=== DECISION DICT ===")
print(json.dumps(premarket_results["decision_dict"], indent=2))

print("\n=== TRAINING EXAMPLE ===")
print(json.dumps(premarket_results["training_example"], indent=2))

print("\n=== BOT OUTPUT ===")
print(premarket_results["bot_text"])

# ============================================================
# NEXT CELL: WATCHLIST / MULTI-CASE RUNNER
# Put this AFTER the live input builder + one-shot runner cell
# ============================================================

import copy
import pandas as pd
import json


# ============================================================
# 1) WATCHLIST INPUTS
# Each case overrides LIVE_INPUTS
# ============================================================

WATCHLIST_CASES = [
    {
        "case_name": "QQQ CALL - VWAP reclaim",
        "symbol": "QQQ",
        "direction": "CALL",
        "trade_grade": "A",
        "setup_name": "VWAP reclaim + break and hold",
        "price": 621.40,
        "vwap": 620.95,
        "ai_confidence": 0.79,
        "setup_score": 0.84,
        "entry_quality_score": 0.80,
        "chasing_score": 0.24,
        "level_respect_score": 0.86,
        "vwap_alignment_score": 0.88,
        "momentum_alignment_score": 0.82,
        "macro_alignment_score": 0.69,
        "stop_distance_pct": 0.0024,
        "target_distance_pct": 0.0058,
        "has_retest_confirmation": True,
        "is_breakout_entry": True,
        "is_reversal_entry": False,
        "option_premium": 1.20,
    },
    {
        "case_name": "QQQ PUT - failed bounce",
        "symbol": "QQQ",
        "direction": "PUT",
        "trade_grade": "B+",
        "setup_name": "failed bounce lower high rejection",
        "price": 621.40,
        "vwap": 620.95,
        "ai_confidence": 0.66,
        "setup_score": 0.68,
        "entry_quality_score": 0.62,
        "chasing_score": 0.41,
        "level_respect_score": 0.70,
        "vwap_alignment_score": 0.55,
        "momentum_alignment_score": 0.64,
        "macro_alignment_score": 0.52,
        "stop_distance_pct": 0.0028,
        "target_distance_pct": 0.0050,
        "has_retest_confirmation": False,
        "is_breakout_entry": False,
        "is_reversal_entry": True,
        "option_premium": 1.05,
    },
    {
        "case_name": "SPY CALL - support hold",
        "symbol": "SPY",
        "direction": "CALL",
        "trade_grade": "A",
        "setup_name": "support hold + vwap reclaim",
        "price": 515.25,
        "vwap": 514.90,
        "ai_confidence": 0.76,
        "setup_score": 0.80,
        "entry_quality_score": 0.77,
        "chasing_score": 0.21,
        "level_respect_score": 0.84,
        "vwap_alignment_score": 0.86,
        "momentum_alignment_score": 0.78,
        "macro_alignment_score": 0.67,
        "stop_distance_pct": 0.0022,
        "target_distance_pct": 0.0054,
        "has_retest_confirmation": True,
        "is_breakout_entry": True,
        "is_reversal_entry": False,
        "option_premium": 1.35,
    },
    {
        "case_name": "SPY PUT - rejection",
        "symbol": "SPY",
        "direction": "PUT",
        "trade_grade": "B",
        "setup_name": "resistance rejection",
        "price": 515.25,
        "vwap": 514.90,
        "ai_confidence": 0.61,
        "setup_score": 0.60,
        "entry_quality_score": 0.56,
        "chasing_score": 0.49,
        "level_respect_score": 0.66,
        "vwap_alignment_score": 0.50,
        "momentum_alignment_score": 0.58,
        "macro_alignment_score": 0.46,
        "stop_distance_pct": 0.0027,
        "target_distance_pct": 0.0046,
        "has_retest_confirmation": False,
        "is_breakout_entry": False,
        "is_reversal_entry": True,
        "option_premium": 0.92,
    },
]


# ============================================================
# 2) CASE MERGE HELPER
# ============================================================

def build_case_inputs(base_inputs: dict, case_overrides: dict) -> dict:
    merged = copy.deepcopy(base_inputs)
    merged.update(case_overrides)
    return merged


# ============================================================
# 3) CASE SCORING
# ============================================================

def status_rank(status: str) -> int:
    mapping = {
        "APPROVED": 3,
        "SMALLER": 2,
        "BLOCKED": 1,
    }
    return mapping.get(status, 0)


def grade_rank(grade: str) -> int:
    mapping = {
        "A+": 5,
        "A": 4,
        "B+": 3,
        "B": 2,
        "AVOID": 1,
    }
    return mapping.get(grade, 0)


def compute_watchlist_opportunity_score(
    verdict: RLAugmentedVerdict
) -> float:
    """
    Risk-first ranking score.
    Higher is better.
    """
    if verdict.blocked:
        return -999.0

    score = 0.0
    score += status_rank(verdict.final_status) * 20.0
    score += grade_rank(verdict.final_grade) * 8.0
    score += verdict.final_ai_confidence * 25.0
    score += verdict.final_size_fraction * 25.0
    score += verdict.rl_ensemble_confidence * 12.0

    # slight preference for non-reduced approval
    if verdict.final_status == "APPROVED":
        score += 8.0
    elif verdict.final_status == "SMALLER":
        score -= 2.0

    return round(score, 3)


# ============================================================
# 4) RUN ALL WATCHLIST CASES
# ============================================================

def run_watchlist_cases(
    memory: MemoryStore,
    base_inputs: dict,
    watchlist_cases: list,
):
    all_results = []

    for case in watchlist_cases:
        case_name = case.get("case_name", "Unnamed Case")
        case_inputs = build_case_inputs(base_inputs, case)

        try:
            live_results = run_live_trade_case(
                memory=memory,
                inputs=case_inputs,
            )

            verdict = live_results["rl_augmented_verdict"]
            pipeline_verdict = live_results["pipeline_results"]["final_verdict"]

            row = {
                "case_name": case_name,
                "symbol": case_inputs["symbol"],
                "direction": case_inputs["direction"],
                "setup_name": case_inputs["setup_name"],
                "status": verdict.final_status,
                "grade": verdict.final_grade,
                "blocked": verdict.blocked,
                "final_ai_confidence": verdict.final_ai_confidence,
                "final_size_fraction": verdict.final_size_fraction,
                "rl_agent": verdict.selected_rl_agent,
                "rl_regime_bias": verdict.rl_regime_bias,
                "rl_confidence": verdict.rl_ensemble_confidence,
                "approved_for_execution": verdict.approved_for_execution,
                "should_alert_discord": verdict.should_alert_discord,
                "opportunity_score": compute_watchlist_opportunity_score(verdict),
                "top_reason": verdict.reasons[0] if verdict.reasons else "",
                "top_warning": verdict.warnings[0] if verdict.warnings else "",
                "top_blocker": verdict.blockers[0] if verdict.blockers else "",
                "raw_results": live_results,
            }

        except Exception as e:
            row = {
                "case_name": case_name,
                "symbol": case.get("symbol", ""),
                "direction": case.get("direction", ""),
                "setup_name": case.get("setup_name", ""),
                "status": "ERROR",
                "grade": "AVOID",
                "blocked": True,
                "final_ai_confidence": 0.0,
                "final_size_fraction": 0.0,
                "rl_agent": "",
                "rl_regime_bias": "",
                "rl_confidence": 0.0,
                "approved_for_execution": False,
                "should_alert_discord": False,
                "opportunity_score": -9999.0,
                "top_reason": "",
                "top_warning": "",
                "top_blocker": str(e),
                "raw_results": None,
            }

        all_results.append(row)

    return all_results


# ============================================================
# 5) DATAFRAME + RANKING
# ============================================================

def watchlist_results_to_dataframe(results: list) -> pd.DataFrame:
    if not results:
        return pd.DataFrame()

    df = pd.DataFrame([
        {k: v for k, v in r.items() if k != "raw_results"}
        for r in results
    ])

    if not df.empty:
        df = df.sort_values(
            by=["blocked", "opportunity_score", "final_size_fraction", "final_ai_confidence"],
            ascending=[True, False, False, False]
        ).reset_index(drop=True)

    return df


def get_best_watchlist_case(results: list):
    valid = [r for r in results if r.get("raw_results") is not None]
    if not valid:
        return None

    valid = sorted(valid, key=lambda x: x["opportunity_score"], reverse=True)
    return valid[0]


# ============================================================
# 6) DISPLAY HELPERS
# ============================================================

def print_watchlist_summary(results: list):
    df = watchlist_results_to_dataframe(results)

    if df.empty:
        print("No watchlist results.")
        return

    print("=== WATCHLIST RANKING ===")
    print(df.to_string(index=False))

    best = get_best_watchlist_case(results)
    if best is not None:
        print("\n=== TOP OPPORTUNITY ===")
        print(json.dumps({
            "case_name": best["case_name"],
            "symbol": best["symbol"],
            "direction": best["direction"],
            "setup_name": best["setup_name"],
            "status": best["status"],
            "grade": best["grade"],
            "blocked": best["blocked"],
            "final_ai_confidence": best["final_ai_confidence"],
            "final_size_fraction": best["final_size_fraction"],
            "rl_agent": best["rl_agent"],
            "rl_regime_bias": best["rl_regime_bias"],
            "rl_confidence": best["rl_confidence"],
            "approved_for_execution": best["approved_for_execution"],
            "opportunity_score": best["opportunity_score"],
            "top_reason": best["top_reason"],
            "top_warning": best["top_warning"],
            "top_blocker": best["top_blocker"],
        }, indent=2))


def print_watchlist_case_alert(results: list, case_name: str):
    for r in results:
        if r["case_name"] == case_name and r["raw_results"] is not None:
            market = r["raw_results"]["market"]
            signal = r["raw_results"]["signal"]
            verdict = r["raw_results"]["rl_augmented_verdict"]
            print(format_rl_augmented_alert(market, signal, verdict))
            return

    print(f"Case not found or unavailable: {case_name}")


# ============================================================
# 7) OPTIONAL SAFE PICKER
# Picks best non-blocked case only
# ============================================================

def get_best_non_blocked_case(results: list):
    valid = [
        r for r in results
        if r.get("raw_results") is not None and not r.get("blocked", True)
    ]
    if not valid:
        return None

    valid = sorted(
        valid,
        key=lambda x: (
            x["opportunity_score"],
            x["final_size_fraction"],
            x["final_ai_confidence"]
        ),
        reverse=True
    )
    return valid[0]


# ============================================================
# 8) RUN WATCHLIST
# Assumes `memory` and `LIVE_INPUTS` already exist
# ============================================================

watchlist_results = run_watchlist_cases(
    memory=memory,
    base_inputs=LIVE_INPUTS,
    watchlist_cases=WATCHLIST_CASES,
)

print_watchlist_summary(watchlist_results)

best_safe_case = get_best_non_blocked_case(watchlist_results)
if best_safe_case is not None:
    print("\n=== BEST SAFE CASE ALERT ===")
    print_watchlist_case_alert(watchlist_results, best_safe_case["case_name"])
else:
    print("\nNo safe non-blocked case found.")

logged_trade = log_live_trade_case_after_exit(
    memory=memory,
    results=live_results,
    entry_option_price=1.20,
    exit_option_price=2.05,
    contracts=1,
    risk_dollars=35.0,
    max_adverse_excursion_r=0.45,
    max_favorable_excursion_r=2.80,
)

print(format_completed_trade_review(logged_trade))

# ============================================================
# NEXT CELL: LIVE INPUT BUILDER + ONE-SHOT RUNNER
# Put this AFTER the shadow RL ensemble overlay cell
# ============================================================

import json


# ============================================================
# 1) LIVE INPUT BLOCK
# Edit these values before each run
# ============================================================

LIVE_INPUTS = {
    # -------------------------
    # Market
    # -------------------------
    "symbol": "QQQ",
    "price": 621.40,
    "vwap": 620.95,
    "atr_pct": 0.0028,
    "intraday_volatility_ratio": 1.20,
    "trend_strength": 0.74,
    "realized_day_range_pct": 0.010,
    "oil_change_dollars": 1.10,
    "oil_trend": "stabilizing",              # rising / falling / stabilizing / neutral
    "macro_bias": "neutral",                 # bullish / bearish / neutral / hostile
    "market_breadth_score": 0.66,
    "correlation_to_open_positions": 0.15,
    "time_quality_score": 0.84,
    "spread_quality_score": 0.90,
    "liquidity_score": 0.92,

    # -------------------------
    # Signal
    # -------------------------
    "direction": "CALL",                     # CALL / PUT / FLAT
    "trade_grade": "A",                     # A+ / A / B+ / B / AVOID
    "ai_confidence": 0.79,
    "setup_score": 0.84,
    "entry_quality_score": 0.80,
    "chasing_score": 0.24,
    "level_respect_score": 0.86,
    "vwap_alignment_score": 0.88,
    "momentum_alignment_score": 0.82,
    "macro_alignment_score": 0.69,
    "stop_distance_pct": 0.0024,
    "target_distance_pct": 0.0058,
    "has_retest_confirmation": True,
    "is_breakout_entry": True,
    "is_reversal_entry": False,
    "setup_name": "VWAP reclaim + break and hold",

    # -------------------------
    # Option / execution
    # -------------------------
    "option_premium": 1.20,
    "option_stop_fraction_of_premium": 0.35,

    # -------------------------
    # Portfolio
    # -------------------------
    "account_equity": 5000.0,
    "start_of_day_equity": 5000.0,
    "current_equity": 4975.0,
    "day_pnl": -10.0,
    "peak_equity": 5075.0,
    "consecutive_losses": 0,
    "recent_live_win_rate": 0.58,
    "recent_live_expectancy": 0.20,
    "model_health_score": 0.77,

    # -------------------------
    # Open positions
    # Each one should look like:
    # {"symbol": "SPY", "direction": "CALL", "open_risk_dollars": 25.0, "is_index_exposure": True}
    # -------------------------
    "open_positions": [],

    # -------------------------
    # Shadow RL research inputs
    # Replace these later with real PPO / A2C evaluation outputs
    # -------------------------
    "ppo_eval": {
        "agent_name": "PPO",
        "sharpe": 1.28,
        "sortino": 1.62,
        "max_drawdown_pct": 0.10,
        "win_rate": 0.57,
        "avg_return_pct": 0.85,
        "recent_30d_return_pct": 1.45,
        "recent_30d_sharpe": 1.10,
        "stability_score": 0.82,
        "regime_fit_score": 0.78,
        "sample_size": 180,
        "notes": ["Stable in trend", "Better consistency recently"],
    },

    "a2c_eval": {
        "agent_name": "A2C",
        "sharpe": 1.04,
        "sortino": 1.30,
        "max_drawdown_pct": 0.13,
        "win_rate": 0.54,
        "avg_return_pct": 0.72,
        "recent_30d_return_pct": 0.95,
        "recent_30d_sharpe": 0.76,
        "stability_score": 0.71,
        "regime_fit_score": 0.74,
        "sample_size": 180,
        "notes": ["More reactive", "Higher variance"],
    }
}


# ============================================================
# 2) BUILDERS
# ============================================================

def build_open_positions(position_rows):
    built = []
    for row in position_rows:
        built.append(
            Position(
                symbol=row["symbol"],
                direction=TradeDirection(row["direction"]),
                open_risk_dollars=float(row["open_risk_dollars"]),
                is_index_exposure=bool(row.get("is_index_exposure", True)),
            )
        )
    return built


def build_live_market(inputs: dict) -> MarketState:
    return MarketState(
        symbol=inputs["symbol"],
        price=float(inputs["price"]),
        vwap=float(inputs["vwap"]),
        atr_pct=float(inputs["atr_pct"]),
        intraday_volatility_ratio=float(inputs["intraday_volatility_ratio"]),
        trend_strength=float(inputs["trend_strength"]),
        realized_day_range_pct=float(inputs["realized_day_range_pct"]),
        oil_change_dollars=float(inputs["oil_change_dollars"]),
        oil_trend=inputs["oil_trend"],
        macro_bias=inputs["macro_bias"],
        market_breadth_score=float(inputs["market_breadth_score"]),
        correlation_to_open_positions=float(inputs["correlation_to_open_positions"]),
        time_quality_score=float(inputs["time_quality_score"]),
        spread_quality_score=float(inputs["spread_quality_score"]),
        liquidity_score=float(inputs["liquidity_score"]),
    )


def build_live_signal(inputs: dict) -> SignalState:
    grade_map = {
        "A+": TradeGrade.A_PLUS,
        "A": TradeGrade.A,
        "B+": TradeGrade.B_PLUS,
        "B": TradeGrade.B,
        "AVOID": TradeGrade.AVOID,
    }

    return SignalState(
        direction=TradeDirection(inputs["direction"]),
        trade_grade=grade_map[inputs["trade_grade"]],
        ai_confidence=float(inputs["ai_confidence"]),
        setup_score=float(inputs["setup_score"]),
        entry_quality_score=float(inputs["entry_quality_score"]),
        chasing_score=float(inputs["chasing_score"]),
        level_respect_score=float(inputs["level_respect_score"]),
        vwap_alignment_score=float(inputs["vwap_alignment_score"]),
        momentum_alignment_score=float(inputs["momentum_alignment_score"]),
        macro_alignment_score=float(inputs["macro_alignment_score"]),
        stop_distance_pct=float(inputs["stop_distance_pct"]),
        target_distance_pct=float(inputs["target_distance_pct"]),
        has_retest_confirmation=bool(inputs["has_retest_confirmation"]),
        is_breakout_entry=bool(inputs["is_breakout_entry"]),
        is_reversal_entry=bool(inputs["is_reversal_entry"]),
        setup_name=inputs["setup_name"],
    )


def build_live_portfolio(inputs: dict) -> PortfolioState:
    return PortfolioState(
        start_of_day_equity=float(inputs["start_of_day_equity"]),
        current_equity=float(inputs["current_equity"]),
        day_pnl=float(inputs["day_pnl"]),
        peak_equity=float(inputs["peak_equity"]),
        consecutive_losses=int(inputs["consecutive_losses"]),
        open_positions=build_open_positions(inputs.get("open_positions", [])),
        recent_live_win_rate=float(inputs["recent_live_win_rate"]),
        recent_live_expectancy=float(inputs["recent_live_expectancy"]),
        model_health_score=float(inputs["model_health_score"]),
    )


def build_live_config(inputs: dict) -> RiskConfig:
    return RiskConfig(
        account_equity=float(inputs["account_equity"])
    )


def build_rl_agent_eval(d: dict) -> RLAgentEval:
    return RLAgentEval(
        agent_name=d["agent_name"],
        sharpe=float(d["sharpe"]),
        sortino=float(d["sortino"]),
        max_drawdown_pct=float(d["max_drawdown_pct"]),
        win_rate=float(d["win_rate"]),
        avg_return_pct=float(d["avg_return_pct"]),
        recent_30d_return_pct=float(d["recent_30d_return_pct"]),
        recent_30d_sharpe=float(d["recent_30d_sharpe"]),
        stability_score=float(d["stability_score"]),
        regime_fit_score=float(d["regime_fit_score"]),
        sample_size=int(d["sample_size"]),
        notes=list(d.get("notes", [])),
    )


# ============================================================
# 3) MASTER ONE-SHOT RUNNER
# ============================================================

def run_live_trade_case(
    memory: MemoryStore,
    inputs: dict,
):
    market = build_live_market(inputs)
    signal = build_live_signal(inputs)
    portfolio = build_live_portfolio(inputs)
    cfg = build_live_config(inputs)

    option_premium = float(inputs["option_premium"])
    option_stop_fraction = float(inputs["option_stop_fraction_of_premium"])

    pipeline_results = run_full_unbiased_ai_pipeline(
        memory=memory,
        market=market,
        signal=signal,
        portfolio=portfolio,
        cfg=cfg,
        option_premium=option_premium,
        option_stop_fraction_of_premium=option_stop_fraction,
    )

    ppo_eval = build_rl_agent_eval(inputs["ppo_eval"])
    a2c_eval = build_rl_agent_eval(inputs["a2c_eval"])

    rl_decision = build_shadow_rl_ensemble(
        ppo_eval=ppo_eval,
        a2c_eval=a2c_eval,
        market=market,
        signal=signal,
        portfolio=portfolio,
    )

    rl_augmented_verdict = apply_rl_overlay_to_pipeline(
        pipeline_results=pipeline_results,
        rl_decision=rl_decision,
    )

    return {
        "market": market,
        "signal": signal,
        "portfolio": portfolio,
        "cfg": cfg,
        "pipeline_results": pipeline_results,
        "rl_decision": rl_decision,
        "rl_augmented_verdict": rl_augmented_verdict,
    }


# ============================================================
# 4) DISPLAY HELPERS
# ============================================================

def print_live_trade_case_summary(results: dict):
    market = results["market"]
    signal = results["signal"]
    rl_decision = results["rl_decision"]
    rl_augmented_verdict = results["rl_augmented_verdict"]

    print("=== RL DECISION ===")
    print(json.dumps(rl_decision_to_dict(rl_decision), indent=2))

    print("\n=== FINAL RL-AUGMENTED VERDICT ===")
    print(json.dumps(rl_augmented_verdict_to_dict(rl_augmented_verdict), indent=2))

    print("\n=== FINAL ALERT ===")
    print(format_rl_augmented_alert(market, signal, rl_augmented_verdict))


# ============================================================
# 5) OPTIONAL POST-TRADE LOGGER
# Use after the trade closes
# ============================================================

def log_live_trade_case_after_exit(
    memory: MemoryStore,
    results: dict,
    entry_option_price: float,
    exit_option_price: float,
    contracts: int,
    risk_dollars: float,
    max_adverse_excursion_r: float,
    max_favorable_excursion_r: float,
):
    market = results["market"]
    signal = results["signal"]
    portfolio = results["portfolio"]
    cfg = results["cfg"]
    pipeline_results = results["pipeline_results"]

    return log_pipeline_completed_trade(
        memory=memory,
        market=market,
        signal=signal,
        portfolio=portfolio,
        cfg=cfg,
        pipeline_results=pipeline_results,
        entry_option_price=entry_option_price,
        exit_option_price=exit_option_price,
        contracts=contracts,
        risk_dollars=risk_dollars,
        max_adverse_excursion_r=max_adverse_excursion_r,
        max_favorable_excursion_r=max_favorable_excursion_r,
    )


# ============================================================
# 6) RUN THE CASE
# Assumes `memory` already exists
# ============================================================

live_results = run_live_trade_case(
    memory=memory,
    inputs=LIVE_INPUTS,
)

print_live_trade_case_summary(live_results)

# ============================================================
# NEXT CELL: SHADOW RL ENSEMBLE OVERLAY
# Put this AFTER the master pipeline cell
# ============================================================

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import math
import json


# ============================================================
# RL RESEARCH MODELS
# ============================================================

@dataclass
class RLAgentEval:
    agent_name: str                     # PPO / A2C / DDPG if added later
    sharpe: float
    sortino: float
    max_drawdown_pct: float
    win_rate: float
    avg_return_pct: float
    recent_30d_return_pct: float
    recent_30d_sharpe: float
    stability_score: float              # 0 to 1
    regime_fit_score: float             # 0 to 1
    sample_size: int
    notes: List[str] = field(default_factory=list)


@dataclass
class RLEnsembleDecision:
    selected_agent: str
    selected_weight: float
    runner_up_agent: str
    runner_up_weight: float
    ensemble_confidence: float          # 0 to 1
    regime_bias: str                    # bullish / bearish / neutral / defensive
    size_multiplier: float              # bounded overlay
    confidence_adjustment: float        # bounded overlay
    block_new_risk: bool
    reasons: List[str]
    warnings: List[str]


# ============================================================
# HELPERS
# ============================================================

def softmax_scores(scores: List[float], temperature: float = 0.75) -> List[float]:
    if not scores:
        return []
    temperature = max(1e-6, temperature)
    scaled = [s / temperature for s in scores]
    max_scaled = max(scaled)
    exps = [math.exp(s - max_scaled) for s in scaled]
    total = sum(exps)
    if total == 0:
        return [1.0 / len(scores)] * len(scores)
    return [x / total for x in exps]


def bounded(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def score_rl_agent(agent: RLAgentEval) -> float:
    """
    Risk-first research score.
    Rewards risk-adjusted returns and stability.
    Penalizes drawdown.
    """
    score = 0.0
    score += 0.28 * agent.sharpe
    score += 0.16 * agent.sortino
    score += 0.14 * agent.recent_30d_sharpe
    score += 0.10 * agent.win_rate
    score += 0.08 * agent.avg_return_pct
    score += 0.08 * agent.recent_30d_return_pct
    score += 0.10 * agent.stability_score
    score += 0.12 * agent.regime_fit_score
    score -= 0.20 * agent.max_drawdown_pct
    return score


def infer_regime_bias_from_agents(
    ppo: RLAgentEval,
    a2c: RLAgentEval
) -> str:
    """
    Very simple research-layer interpretation.
    You can make this smarter later.
    """
    avg_recent = (ppo.recent_30d_return_pct + a2c.recent_30d_return_pct) / 2.0
    avg_sharpe = (ppo.recent_30d_sharpe + a2c.recent_30d_sharpe) / 2.0
    avg_dd = (ppo.max_drawdown_pct + a2c.max_drawdown_pct) / 2.0

    if avg_dd > 0.18:
        return "defensive"
    if avg_recent > 0.0 and avg_sharpe > 0.75:
        return "bullish"
    if avg_recent < 0.0 and avg_sharpe < 0.0:
        return "bearish"
    return "neutral"


# ============================================================
# RL SHADOW ENSEMBLE
# ============================================================

def build_shadow_rl_ensemble(
    ppo_eval: RLAgentEval,
    a2c_eval: RLAgentEval,
    market: MarketState,
    signal: SignalState,
    portfolio: PortfolioState,
) -> RLEnsembleDecision:
    reasons: List[str] = []
    warnings: List[str] = []

    ppo_score = score_rl_agent(ppo_eval)
    a2c_score = score_rl_agent(a2c_eval)

    weights = softmax_scores([ppo_score, a2c_score], temperature=0.75)
    ppo_w, a2c_w = weights

    if ppo_w >= a2c_w:
        selected_agent = "PPO"
        selected_weight = ppo_w
        runner_up_agent = "A2C"
        runner_up_weight = a2c_w
        winner = ppo_eval
    else:
        selected_agent = "A2C"
        selected_weight = a2c_w
        runner_up_agent = "PPO"
        runner_up_weight = ppo_w
        winner = a2c_eval

    reasons.append(f"PPO research score = {ppo_score:.3f}")
    reasons.append(f"A2C research score = {a2c_score:.3f}")
    reasons.append(f"Selected agent = {selected_agent}")
    reasons.append(f"Selected weight = {selected_weight:.3f}")

    regime_bias = infer_regime_bias_from_agents(ppo_eval, a2c_eval)
    reasons.append(f"RL ensemble regime bias = {regime_bias}")

    # --------------------------------------------------------
    # Build ensemble confidence
    # --------------------------------------------------------
    ensemble_confidence = (
        0.35 * bounded(winner.stability_score, 0.0, 1.0) +
        0.25 * bounded(winner.regime_fit_score, 0.0, 1.0) +
        0.20 * bounded((winner.recent_30d_sharpe + 1.5) / 3.0, 0.0, 1.0) +
        0.20 * bounded(winner.win_rate, 0.0, 1.0)
    )
    ensemble_confidence = bounded(ensemble_confidence, 0.0, 1.0)

    # --------------------------------------------------------
    # Risk-first overlay logic
    # These are intentionally bounded and small.
    # --------------------------------------------------------
    size_multiplier = 1.00
    confidence_adjustment = 0.00
    block_new_risk = False

    # Strong RL agreement helps a little
    agreement_strength = abs(ppo_w - a2c_w)
    if agreement_strength > 0.30 and ensemble_confidence > 0.70:
        size_multiplier *= 1.05
        confidence_adjustment += 0.04
        reasons.append("RL agents show strong agreement with acceptable confidence.")

    # Weak / unstable RL reduces size
    if ensemble_confidence < 0.45:
        size_multiplier *= 0.85
        confidence_adjustment -= 0.08
        warnings.append("RL ensemble confidence is weak. Size reduced.")

    # High drawdown in research branch = defensive
    if winner.max_drawdown_pct > 0.15:
        size_multiplier *= 0.80
        confidence_adjustment -= 0.06
        warnings.append("Winning RL agent still shows elevated drawdown. Risk reduced.")

    # Very poor recent research performance = do not add new risk
    if winner.recent_30d_return_pct < -2.0 and winner.recent_30d_sharpe < -0.25:
        block_new_risk = True
        warnings.append("RL research branch is deteriorating. Blocking new risk from RL overlay.")

    # Regime-aware handling
    if regime_bias == "defensive":
        size_multiplier *= 0.80
        confidence_adjustment -= 0.05
        warnings.append("RL ensemble indicates defensive regime.")
    elif regime_bias == "bullish" and signal.direction == TradeDirection.CALL:
        size_multiplier *= 1.03
        confidence_adjustment += 0.03
        reasons.append("RL regime bias supports long-side risk.")
    elif regime_bias == "bearish" and signal.direction == TradeDirection.PUT:
        size_multiplier *= 1.03
        confidence_adjustment += 0.03
        reasons.append("RL regime bias supports short-side risk.")
    elif regime_bias in {"bullish", "bearish"}:
        size_multiplier *= 0.92
        confidence_adjustment -= 0.03
        warnings.append("RL regime bias does not support current trade direction.")

    # If live portfolio is already stressed, RL overlay only reduces, never boosts
    day_loss_pct = pct_day_loss(portfolio.start_of_day_equity, portfolio.day_pnl)
    dd_pct = pct_drawdown_from_peak(portfolio.current_equity, portfolio.peak_equity)

    if day_loss_pct > 0.015 or dd_pct > 0.02:
        size_multiplier = min(size_multiplier, 1.0)
        confidence_adjustment = min(confidence_adjustment, 0.0)
        warnings.append("Live book is stressed. RL overlay cannot increase risk.")

    # Bound the final overlay tightly
    size_multiplier = bounded(size_multiplier, 0.75, 1.08)
    confidence_adjustment = bounded(confidence_adjustment, -0.10, 0.06)

    return RLEnsembleDecision(
        selected_agent=selected_agent,
        selected_weight=round(selected_weight, 3),
        runner_up_agent=runner_up_agent,
        runner_up_weight=round(runner_up_weight, 3),
        ensemble_confidence=round(ensemble_confidence, 3),
        regime_bias=regime_bias,
        size_multiplier=round(size_multiplier, 3),
        confidence_adjustment=round(confidence_adjustment, 3),
        block_new_risk=block_new_risk,
        reasons=reasons,
        warnings=warnings,
    )


# ============================================================
# APPLY RL OVERLAY TO MASTER PIPELINE VERDICT
# ============================================================

@dataclass
class RLAugmentedVerdict:
    blocked: bool
    final_status: str
    final_grade: str
    final_direction: str
    final_ai_confidence: float
    final_size_fraction: float
    selected_rl_agent: str
    rl_regime_bias: str
    rl_ensemble_confidence: float
    approved_for_execution: bool
    should_alert_discord: bool
    reasons: List[str]
    warnings: List[str]
    blockers: List[str]


def apply_rl_overlay_to_pipeline(
    pipeline_results: dict,
    rl_decision: RLEnsembleDecision,
) -> RLAugmentedVerdict:
    verdict = pipeline_results["final_verdict"]

    reasons = list(verdict.reasons) + list(rl_decision.reasons)
    warnings = list(verdict.warnings) + list(rl_decision.warnings)
    blockers = list(verdict.blockers)

    blocked = verdict.blocked
    final_status = verdict.final_status
    final_grade = verdict.final_grade
    final_direction = verdict.final_direction
    final_ai_confidence = verdict.final_ai_confidence
    final_size_fraction = verdict.final_size_fraction
    approved_for_execution = verdict.approved_for_execution
    should_alert_discord = verdict.should_alert_discord

    if rl_decision.block_new_risk:
        blocked = True
        final_status = "BLOCKED"
        final_grade = "AVOID"
        final_size_fraction = 0.0
        approved_for_execution = False
        should_alert_discord = False
        blockers.append("Shadow RL overlay blocked new risk.")

    if not blocked:
        final_ai_confidence = bounded(
            final_ai_confidence + rl_decision.confidence_adjustment,
            0.0,
            1.0
        )

        final_size_fraction = bounded(
            final_size_fraction * rl_decision.size_multiplier,
            0.0,
            1.0
        )

        if final_size_fraction < 0.75 and final_status == "APPROVED":
            final_status = "SMALLER"

        approved_for_execution = final_size_fraction > 0 and final_grade != "AVOID"
        should_alert_discord = approved_for_execution

    return RLAugmentedVerdict(
        blocked=blocked,
        final_status=final_status,
        final_grade=final_grade,
        final_direction=final_direction,
        final_ai_confidence=round(final_ai_confidence, 3),
        final_size_fraction=round(final_size_fraction, 3),
        selected_rl_agent=rl_decision.selected_agent,
        rl_regime_bias=rl_decision.regime_bias,
        rl_ensemble_confidence=rl_decision.ensemble_confidence,
        approved_for_execution=approved_for_execution,
        should_alert_discord=should_alert_discord,
        reasons=reasons,
        warnings=warnings,
        blockers=blockers,
    )


# ============================================================
# FORMATTERS
# ============================================================

def rl_decision_to_dict(rl: RLEnsembleDecision) -> dict:
    return {
        "selected_agent": rl.selected_agent,
        "selected_weight": rl.selected_weight,
        "runner_up_agent": rl.runner_up_agent,
        "runner_up_weight": rl.runner_up_weight,
        "ensemble_confidence": rl.ensemble_confidence,
        "regime_bias": rl.regime_bias,
        "size_multiplier": rl.size_multiplier,
        "confidence_adjustment": rl.confidence_adjustment,
        "block_new_risk": rl.block_new_risk,
        "reasons": rl.reasons,
        "warnings": rl.warnings,
    }


def rl_augmented_verdict_to_dict(v: RLAugmentedVerdict) -> dict:
    return {
        "blocked": v.blocked,
        "final_status": v.final_status,
        "final_grade": v.final_grade,
        "final_direction": v.final_direction,
        "final_ai_confidence": v.final_ai_confidence,
        "final_size_fraction": v.final_size_fraction,
        "selected_rl_agent": v.selected_rl_agent,
        "rl_regime_bias": v.rl_regime_bias,
        "rl_ensemble_confidence": v.rl_ensemble_confidence,
        "approved_for_execution": v.approved_for_execution,
        "should_alert_discord": v.should_alert_discord,
        "reasons": v.reasons,
        "warnings": v.warnings,
        "blockers": v.blockers,
    }


def format_rl_augmented_alert(
    market: MarketState,
    signal: SignalState,
    verdict: RLAugmentedVerdict
) -> str:
    emoji = {
        "APPROVED": "🟢",
        "SMALLER": "🟡",
        "BLOCKED": "🔴"
    }.get(verdict.final_status, "⚪")

    lines = [
        f"{emoji} **UNBIASED AI + SHADOW RL OVERLAY**",
        f"**Symbol:** {market.symbol}",
        f"**Setup:** {signal.setup_name}",
        f"**Direction:** {verdict.final_direction}",
        f"**Final Status:** {verdict.final_status}",
        f"**Final Grade:** {verdict.final_grade}",
        f"**AI Confidence:** {verdict.final_ai_confidence}",
        f"**Size Fraction:** {verdict.final_size_fraction}",
        f"**Selected RL Agent:** {verdict.selected_rl_agent}",
        f"**RL Regime Bias:** {verdict.rl_regime_bias}",
        f"**RL Ensemble Confidence:** {verdict.rl_ensemble_confidence}",
        f"**Approved For Execution:** {'YES' if verdict.approved_for_execution else 'NO'}",
    ]

    if verdict.reasons:
        lines.append("")
        lines.append("**Reasons:**")
        for x in verdict.reasons[:8]:
            lines.append(f"• {x}")

    if verdict.warnings:
        lines.append("")
        lines.append("**Warnings:**")
        for x in verdict.warnings[:8]:
            lines.append(f"• {x}")

    if verdict.blockers:
        lines.append("")
        lines.append("**Blockers:**")
        for x in verdict.blockers[:8]:
            lines.append(f"• {x}")

    return "\n".join(lines)


# ============================================================
# TEST INPUTS
# These are research metrics, not live-trade permissions.
# Replace these later with your real PPO/A2C backtest outputs.
# ============================================================

ppo_eval = RLAgentEval(
    agent_name="PPO",
    sharpe=1.28,
    sortino=1.62,
    max_drawdown_pct=0.10,
    win_rate=0.57,
    avg_return_pct=0.85,
    recent_30d_return_pct=1.45,
    recent_30d_sharpe=1.10,
    stability_score=0.82,
    regime_fit_score=0.78,
    sample_size=180,
    notes=["Stable in trend", "Better consistency recently"],
)

a2c_eval = RLAgentEval(
    agent_name="A2C",
    sharpe=1.04,
    sortino=1.30,
    max_drawdown_pct=0.13,
    win_rate=0.54,
    avg_return_pct=0.72,
    recent_30d_return_pct=0.95,
    recent_30d_sharpe=0.76,
    stability_score=0.71,
    regime_fit_score=0.74,
    sample_size=180,
    notes=["More reactive", "Higher variance"],
)


# ============================================================
# RUN OVER EXISTING MASTER PIPELINE RESULTS
# Assumes pipeline_results, market, signal, portfolio exist
# ============================================================

rl_decision = build_shadow_rl_ensemble(
    ppo_eval=ppo_eval,
    a2c_eval=a2c_eval,
    market=market,
    signal=signal,
    portfolio=portfolio,
)

rl_augmented_verdict = apply_rl_overlay_to_pipeline(
    pipeline_results=pipeline_results,
    rl_decision=rl_decision,
)

print("=== SHADOW RL DECISION ===")
print(json.dumps(rl_decision_to_dict(rl_decision), indent=2))

print("\n=== RL-AUGMENTED VERDICT ===")
print(json.dumps(rl_augmented_verdict_to_dict(rl_augmented_verdict), indent=2))

print("\n=== RL-AUGMENTED ALERT ===")
print(format_rl_augmented_alert(market, signal, rl_augmented_verdict))

# ============================================================
# NEXT CELL: MASTER PIPELINE
# Put this AFTER the self-adjusting policy engine cell
# ============================================================

from dataclasses import dataclass
from typing import Optional, Dict, Any
import json


# ============================================================
# MASTER OUTPUT MODELS
# ============================================================

@dataclass
class FinalTradeVerdict:
    blocked: bool
    final_status: str                  # APPROVED / SMALLER / BLOCKED
    final_grade: str
    final_direction: str
    final_ai_confidence: float
    final_size_fraction: float
    approved_for_execution: bool
    should_alert_discord: bool
    headline: str
    risk_status: str
    market_regime: str
    setup_name: str
    reasons: list
    warnings: list
    blockers: list


# ============================================================
# HELPERS
# ============================================================

def merge_unique_lists(*args) -> list:
    out = []
    seen = set()
    for group in args:
        for item in group:
            if item not in seen:
                out.append(item)
                seen.add(item)
    return out


def verdict_to_dict(verdict: FinalTradeVerdict) -> dict:
    return {
        "blocked": verdict.blocked,
        "final_status": verdict.final_status,
        "final_grade": verdict.final_grade,
        "final_direction": verdict.final_direction,
        "final_ai_confidence": verdict.final_ai_confidence,
        "final_size_fraction": verdict.final_size_fraction,
        "approved_for_execution": verdict.approved_for_execution,
        "should_alert_discord": verdict.should_alert_discord,
        "headline": verdict.headline,
        "risk_status": verdict.risk_status,
        "market_regime": verdict.market_regime,
        "setup_name": verdict.setup_name,
        "reasons": verdict.reasons,
        "warnings": verdict.warnings,
        "blockers": verdict.blockers,
    }


# ============================================================
# MASTER PIPELINE CORE
# ============================================================

def run_full_unbiased_ai_pipeline(
    memory: MemoryStore,
    market: MarketState,
    signal: SignalState,
    portfolio: PortfolioState,
    cfg: RiskConfig,
    option_premium: float,
    option_stop_fraction_of_premium: float = 0.35,
):
    """
    Runs the full stack:
    1. Risk engine
    2. Risk-first brain
    3. Memory-enhanced brain
    4. Self-adjusting policy
    5. Final verdict
    """

    # --------------------------------------------------------
    # STEP 1: BASE RISK DECISION
    # --------------------------------------------------------
    risk_decision = evaluate_trade_risk(
        market=market,
        signal=signal,
        portfolio=portfolio,
        cfg=cfg,
        option_premium=option_premium,
        option_stop_fraction_of_premium=option_stop_fraction_of_premium,
    )

    # --------------------------------------------------------
    # STEP 2: BRAIN DECISION
    # --------------------------------------------------------
    base_brain = run_risk_first_ai_brain(
        market=market,
        signal=signal,
        portfolio=portfolio,
        cfg=cfg,
        option_premium=option_premium,
        option_stop_fraction_of_premium=option_stop_fraction_of_premium,
    )

    # --------------------------------------------------------
    # STEP 3: MEMORY-ENHANCED BRAIN
    # --------------------------------------------------------
    _, enhanced_brain = run_memory_enhanced_brain(
        memory=memory,
        market=market,
        signal=signal,
        portfolio=portfolio,
        cfg=cfg,
        option_premium=option_premium,
        option_stop_fraction_of_premium=option_stop_fraction_of_premium,
    )

    # --------------------------------------------------------
    # STEP 4: SELF-ADJUSTING POLICY
    # --------------------------------------------------------
    policy_state = build_adaptive_policy_state(memory)

    policy_result = apply_adaptive_policy_to_brain(
        policy_state=policy_state,
        market=market,
        signal=signal,
        base_brain=base_brain,
        enhanced_brain=enhanced_brain
    )

    # --------------------------------------------------------
    # STEP 5: FINAL DECISION SYNTHESIS
    # --------------------------------------------------------
    blocked = (
        risk_decision.status == RiskStatus.BLOCK
        or base_brain.brain_status == "BLOCKED"
        or enhanced_brain.final_status == "BLOCKED"
        or policy_result.blocked
    )

    if blocked:
        final_status = "BLOCKED"
        final_grade = "AVOID"
        final_size_fraction = 0.0
        approved_for_execution = False
        should_alert_discord = False
        headline = "TRADE BLOCKED - RISK ENGINE HAS FINAL SAY"
    else:
        # size comes from the deepest live layer
        final_size_fraction = round(
            clamp(policy_result.adjusted_size_fraction, 0.0, 1.0),
            3
        )

        # grade comes from policy layer
        final_grade = policy_result.adjusted_grade

        # map final status
        if (
            risk_decision.status == RiskStatus.REDUCE
            or base_brain.brain_status == "SMALLER"
            or enhanced_brain.final_status == "SMALLER"
            or final_size_fraction < 0.75
        ):
            final_status = "SMALLER"
            headline = "REDUCED-SIZE APPROVAL - CAPITAL PRESERVATION ACTIVE"
        else:
            final_status = "APPROVED"
            headline = "APPROVED - RISK CONDITIONS ACCEPTABLE"

        approved_for_execution = final_size_fraction > 0 and final_grade != "AVOID"
        should_alert_discord = approved_for_execution

    final_ai_confidence = round(policy_result.adjusted_ai_confidence, 3)
    market_regime = detect_regime(market, cfg).value

    reasons = merge_unique_lists(
        risk_decision.reasons,
        base_brain.reasoning,
        enhanced_brain.notes,
        policy_result.reasons,
    )

    warnings = merge_unique_lists(
        risk_decision.warnings,
        base_brain.warnings,
        enhanced_brain.memory_warnings,
        policy_result.warnings,
    )

    blockers = merge_unique_lists(
        risk_decision.blockers,
        base_brain.blockers,
        (["Memory-enhanced brain blocked this trade."] if enhanced_brain.should_block_from_memory else []),
        (["Self-adjusting policy blocked this trade."] if policy_result.blocked else []),
    )

    verdict = FinalTradeVerdict(
        blocked=blocked,
        final_status=final_status,
        final_grade=final_grade,
        final_direction=signal.direction.value,
        final_ai_confidence=final_ai_confidence,
        final_size_fraction=final_size_fraction,
        approved_for_execution=approved_for_execution,
        should_alert_discord=should_alert_discord,
        headline=headline,
        risk_status=risk_decision.status.value,
        market_regime=market_regime,
        setup_name=signal.setup_name,
        reasons=reasons,
        warnings=warnings,
        blockers=blockers,
    )

    return {
        "risk_decision": risk_decision,
        "base_brain": base_brain,
        "enhanced_brain": enhanced_brain,
        "policy_state": policy_state,
        "policy_result": policy_result,
        "final_verdict": verdict,
    }


# ============================================================
# DISCORD / REVIEW FORMATTERS
# ============================================================

def format_final_trade_verdict_alert(
    market: MarketState,
    signal: SignalState,
    verdict: FinalTradeVerdict
) -> str:
    emoji = {
        "APPROVED": "🟢",
        "SMALLER": "🟡",
        "BLOCKED": "🔴"
    }.get(verdict.final_status, "⚪")

    lines = [
        f"{emoji} **UNBIASED MASTER PIPELINE VERDICT**",
        f"**Headline:** {verdict.headline}",
        f"**Symbol:** {market.symbol}",
        f"**Setup:** {verdict.setup_name}",
        f"**Direction:** {verdict.final_direction}",
        f"**Final Status:** {verdict.final_status}",
        f"**Risk Status:** {verdict.risk_status}",
        f"**Final Grade:** {verdict.final_grade}",
        f"**Market Regime:** {verdict.market_regime}",
        f"**AI Confidence:** {verdict.final_ai_confidence}",
        f"**Size Fraction:** {verdict.final_size_fraction}",
        f"**Approved For Execution:** {'YES' if verdict.approved_for_execution else 'NO'}",
        f"**Alert Discord:** {'YES' if verdict.should_alert_discord else 'NO'}",
    ]

    if verdict.reasons:
        lines.append("")
        lines.append("**Reasons:**")
        for x in verdict.reasons[:8]:
            lines.append(f"• {x}")

    if verdict.warnings:
        lines.append("")
        lines.append("**Warnings:**")
        for x in verdict.warnings[:8]:
            lines.append(f"• {x}")

    if verdict.blockers:
        lines.append("")
        lines.append("**Blockers:**")
        for x in verdict.blockers[:8]:
            lines.append(f"• {x}")

    return "\n".join(lines)


def print_master_pipeline_summary(results: dict) -> None:
    verdict = results["final_verdict"]

    print("=== FINAL VERDICT ===")
    print(json.dumps(verdict_to_dict(verdict), indent=2))

    print("\n=== RISK DECISION ===")
    print(json.dumps(risk_decision_to_dict(results["risk_decision"]), indent=2))

    print("\n=== BASE BRAIN ===")
    print(json.dumps(brain_decision_to_dict(results["base_brain"]), indent=2))

    print("\n=== ENHANCED BRAIN ===")
    print(json.dumps({
        "final_status": results["enhanced_brain"].final_status,
        "final_grade": results["enhanced_brain"].final_grade,
        "final_direction": results["enhanced_brain"].final_direction,
        "final_conviction": results["enhanced_brain"].final_conviction,
        "adjusted_ai_confidence": results["enhanced_brain"].adjusted_ai_confidence,
        "adjusted_size_fraction": results["enhanced_brain"].adjusted_size_fraction,
        "memory_policy_reason": results["enhanced_brain"].memory_policy_reason,
        "memory_warnings": results["enhanced_brain"].memory_warnings,
        "should_block_from_memory": results["enhanced_brain"].should_block_from_memory,
        "notes": results["enhanced_brain"].notes,
    }, indent=2))

    print("\n=== POLICY RESULT ===")
    print(format_policy_application_result(results["policy_result"]))

    print("\n=== DISCORD ALERT ===")
    print(format_final_trade_verdict_alert(market, signal, verdict))


# ============================================================
# OPTIONAL: POST-TRADE LOGGING HOOK
# ============================================================

def log_pipeline_completed_trade(
    memory: MemoryStore,
    market: MarketState,
    signal: SignalState,
    portfolio: PortfolioState,
    cfg: RiskConfig,
    pipeline_results: dict,
    entry_option_price: float,
    exit_option_price: float,
    contracts: int,
    risk_dollars: float,
    max_adverse_excursion_r: float,
    max_favorable_excursion_r: float,
):
    verdict = pipeline_results["final_verdict"]

    enhanced_proxy = EnhancedBrainDecision(
        final_status=verdict.final_status,
        final_grade=verdict.final_grade,
        final_direction=verdict.final_direction,
        final_conviction=0.0,
        adjusted_ai_confidence=verdict.final_ai_confidence,
        adjusted_size_fraction=verdict.final_size_fraction,
        memory_policy_reason="Logged from master pipeline",
        memory_warnings=[],
        should_block_from_memory=verdict.blocked,
        notes=[],
    )

    return auto_log_completed_trade(
        memory=memory,
        market=market,
        signal=signal,
        portfolio=portfolio,
        cfg=cfg,
        enhanced_brain=enhanced_proxy,
        entry_option_price=entry_option_price,
        exit_option_price=exit_option_price,
        contracts=contracts,
        risk_dollars=risk_dollars,
        max_adverse_excursion_r=max_adverse_excursion_r,
        max_favorable_excursion_r=max_favorable_excursion_r,
        approved=verdict.approved_for_execution,
        executed=verdict.approved_for_execution,
    )


# ============================================================
# TEST / RUN
# Assumes memory, market, signal, portfolio, cfg already exist
# ============================================================

pipeline_results = run_full_unbiased_ai_pipeline(
    memory=memory,
    market=market,
    signal=signal,
    portfolio=portfolio,
    cfg=cfg,
    option_premium=1.20,
    option_stop_fraction_of_premium=0.35,
)

print_master_pipeline_summary(pipeline_results)

# ============================================================
# NEXT CELL: SELF-ADJUSTING POLICY ENGINE
# Put this AFTER the performance dashboard / scorecard cell
# ============================================================

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import json


# ============================================================
# POLICY MODELS
# ============================================================

@dataclass
class SetupPolicyRule:
    setup_name: str
    size_multiplier: float = 1.0
    confidence_adjustment: float = 0.0
    grade_penalty_steps: int = 0
    blocked: bool = False
    reason: str = ""


@dataclass
class SetupRegimePolicyRule:
    setup_name: str
    regime: str
    size_multiplier: float = 1.0
    confidence_adjustment: float = 0.0
    grade_penalty_steps: int = 0
    blocked: bool = False
    reason: str = ""


@dataclass
class GlobalAdaptivePolicy:
    chasing_block_threshold: float = 0.80
    hostile_macro_block_threshold: float = 0.30
    defensive_size_multiplier: float = 0.85
    normal_size_multiplier: float = 1.00
    elite_setup_size_boost: float = 1.10
    weak_setup_size_penalty: float = 0.75
    persistent_loser_block_enabled: bool = True
    notes: List[str] = field(default_factory=list)


@dataclass
class AdaptivePolicyState:
    setup_rules: Dict[str, SetupPolicyRule] = field(default_factory=dict)
    setup_regime_rules: Dict[str, SetupRegimePolicyRule] = field(default_factory=dict)
    global_policy: GlobalAdaptivePolicy = field(default_factory=GlobalAdaptivePolicy)


# ============================================================
# HELPERS
# ============================================================

def evaluate_setup_strength(
    trades: int,
    win_rate: float,
    avg_r: float,
    recent_r: float
) -> str:
    if trades < 3:
        return "INSUFFICIENT"

    if trades >= 5 and win_rate >= 0.62 and avg_r >= 0.25 and recent_r >= 0.10:
        return "ELITE"
    if trades >= 4 and win_rate >= 0.54 and avg_r >= 0.08:
        return "GOOD"
    if trades >= 4 and win_rate >= 0.45 and avg_r >= -0.05:
        return "MIXED"
    return "WEAK"


def build_setup_rule(setup_name: str, stats: PatternStats) -> SetupPolicyRule:
    strength = evaluate_setup_strength(
        trades=stats.trades,
        win_rate=stats.win_rate,
        avg_r=stats.expectancy_r,
        recent_r=stats.recent_r
    )

    rule = SetupPolicyRule(setup_name=setup_name)

    if strength == "ELITE":
        rule.size_multiplier = 1.10
        rule.confidence_adjustment = 0.05
        rule.grade_penalty_steps = 0
        rule.blocked = False
        rule.reason = f"Elite setup memory: {setup_name}"
    elif strength == "GOOD":
        rule.size_multiplier = 1.03
        rule.confidence_adjustment = 0.02
        rule.grade_penalty_steps = 0
        rule.blocked = False
        rule.reason = f"Good setup memory: {setup_name}"
    elif strength == "MIXED":
        rule.size_multiplier = 0.88
        rule.confidence_adjustment = -0.04
        rule.grade_penalty_steps = 0
        rule.blocked = False
        rule.reason = f"Mixed setup memory: {setup_name}"
    elif strength == "WEAK":
        rule.size_multiplier = 0.65
        rule.confidence_adjustment = -0.10
        rule.grade_penalty_steps = 1
        rule.blocked = stats.trades >= 8 and stats.expectancy_r < -0.20
        rule.reason = f"Weak setup memory: {setup_name}"
    else:
        rule.reason = f"Insufficient setup memory: {setup_name}"

    return rule


def build_setup_regime_rule(key: str, stats: PatternStats) -> SetupRegimePolicyRule:
    if "__" in key:
        setup_name, regime = key.split("__", 1)
    else:
        setup_name, regime = key, "UNKNOWN"

    strength = evaluate_setup_strength(
        trades=stats.trades,
        win_rate=stats.win_rate,
        avg_r=stats.expectancy_r,
        recent_r=stats.recent_r
    )

    rule = SetupRegimePolicyRule(setup_name=setup_name, regime=regime)

    if strength == "ELITE":
        rule.size_multiplier = 1.12
        rule.confidence_adjustment = 0.05
        rule.grade_penalty_steps = 0
        rule.blocked = False
        rule.reason = f"Elite setup-regime memory: {setup_name} in {regime}"
    elif strength == "GOOD":
        rule.size_multiplier = 1.05
        rule.confidence_adjustment = 0.02
        rule.grade_penalty_steps = 0
        rule.blocked = False
        rule.reason = f"Good setup-regime memory: {setup_name} in {regime}"
    elif strength == "MIXED":
        rule.size_multiplier = 0.82
        rule.confidence_adjustment = -0.05
        rule.grade_penalty_steps = 1
        rule.blocked = False
        rule.reason = f"Mixed setup-regime memory: {setup_name} in {regime}"
    elif strength == "WEAK":
        rule.size_multiplier = 0.55
        rule.confidence_adjustment = -0.12
        rule.grade_penalty_steps = 1
        rule.blocked = stats.trades >= 6 and stats.expectancy_r < -0.20
        rule.reason = f"Weak setup-regime memory: {setup_name} in {regime}"
    else:
        rule.reason = f"Insufficient setup-regime memory: {setup_name} in {regime}"

    return rule


def build_global_policy(memory: MemoryStore) -> GlobalAdaptivePolicy:
    gp = GlobalAdaptivePolicy()
    df = memory_trade_log_to_dataframe(memory)

    if df.empty:
        gp.notes.append("No trade data yet. Using default global policy.")
        return gp

    # Chasing analysis
    chasing_report = get_chasing_damage_report(df)
    if not chasing_report.empty:
        extreme = chasing_report[chasing_report["chasing_bucket"].astype(str) == "extreme"]
        high = chasing_report[chasing_report["chasing_bucket"].astype(str) == "high"]

        if not extreme.empty and float(extreme.iloc[0]["avg_r"]) < 0:
            gp.chasing_block_threshold = 0.75
            gp.notes.append("Extreme chasing is losing money. Tightened chasing block threshold to 0.75.")
        elif not high.empty and float(high.iloc[0]["avg_r"]) < 0:
            gp.chasing_block_threshold = 0.78
            gp.notes.append("High chasing is underperforming. Tightened chasing block threshold to 0.78.")

    # Macro analysis
    macro_report = get_macro_alignment_report(df)
    if not macro_report.empty:
        hostile = macro_report[macro_report["macro_bucket"].astype(str) == "hostile"]
        weak = macro_report[macro_report["macro_bucket"].astype(str) == "weak"]

        if not hostile.empty and float(hostile.iloc[0]["avg_r"]) < 0:
            gp.hostile_macro_block_threshold = 0.35
            gp.notes.append("Hostile macro is underperforming. Tightened hostile macro block threshold to 0.35.")

        if not weak.empty and float(weak.iloc[0]["avg_r"]) < 0:
            gp.defensive_size_multiplier = 0.80
            gp.notes.append("Weak macro alignment is underperforming. Reduced defensive size multiplier to 0.80.")

    # Broad system health
    scorecard = build_ai_scorecard(memory)
    if scorecard.get("trade_count", 0) >= 5:
        if scorecard["avg_r"] < 0:
            gp.normal_size_multiplier = 0.92
            gp.notes.append("System avg R is negative. Reduced normal size multiplier to 0.92.")
        if scorecard["win_rate"] < 0.45:
            gp.defensive_size_multiplier = min(gp.defensive_size_multiplier, 0.78)
            gp.notes.append("System win rate is weak. Tightened defensive size multiplier.")

    return gp


# ============================================================
# POLICY BUILD
# ============================================================

def build_adaptive_policy_state(memory: MemoryStore) -> AdaptivePolicyState:
    state = AdaptivePolicyState()

    # Setup-level rules
    for setup_name, stats in memory.by_setup.items():
        state.setup_rules[setup_name] = build_setup_rule(setup_name, stats)

    # Setup-regime rules
    for key, stats in memory.by_setup_regime.items():
        state.setup_regime_rules[key] = build_setup_regime_rule(key, stats)

    # Global rules
    state.global_policy = build_global_policy(memory)

    return state


# ============================================================
# APPLY POLICY TO LIVE SIGNAL
# ============================================================

@dataclass
class PolicyApplicationResult:
    blocked: bool
    adjusted_grade: str
    adjusted_ai_confidence: float
    adjusted_size_fraction: float
    reasons: List[str]
    warnings: List[str]


def apply_adaptive_policy_to_brain(
    policy_state: AdaptivePolicyState,
    market: MarketState,
    signal: SignalState,
    base_brain: AIBrainDecision,
    enhanced_brain: EnhancedBrainDecision
) -> PolicyApplicationResult:

    reasons: List[str] = []
    warnings: List[str] = []

    regime = detect_regime(market, RiskConfig())  # only need regime label here
    setup_key = signal.setup_name
    setup_regime_key = f"{signal.setup_name}__{regime.value}"

    adjusted_grade = enhanced_brain.final_grade
    adjusted_ai_conf = enhanced_brain.adjusted_ai_confidence
    adjusted_size = enhanced_brain.adjusted_size_fraction
    blocked = False

    gp = policy_state.global_policy
    setup_rule = policy_state.setup_rules.get(setup_key)
    sr_rule = policy_state.setup_regime_rules.get(setup_regime_key)

    # Global chasing and macro rules
    if signal.chasing_score >= gp.chasing_block_threshold:
        blocked = True
        warnings.append(
            f"Global policy blocked trade: chasing score {signal.chasing_score:.2f} >= {gp.chasing_block_threshold:.2f}"
        )

    if signal.macro_alignment_score < gp.hostile_macro_block_threshold and adjusted_grade in {"B+", "B", "AVOID"}:
        blocked = True
        warnings.append(
            f"Global policy blocked trade: hostile macro alignment {signal.macro_alignment_score:.2f}"
        )

    # Apply setup rule
    if setup_rule:
        adjusted_ai_conf = clamp(adjusted_ai_conf + setup_rule.confidence_adjustment, 0.0, 1.0)
        adjusted_size *= setup_rule.size_multiplier
        adjusted_grade = downgrade_grade(adjusted_grade, setup_rule.grade_penalty_steps)
        reasons.append(setup_rule.reason)

        if setup_rule.blocked:
            blocked = True
            warnings.append(f"Setup policy blocked trade: {setup_rule.reason}")

    # Apply setup-regime rule
    if sr_rule:
        adjusted_ai_conf = clamp(adjusted_ai_conf + sr_rule.confidence_adjustment, 0.0, 1.0)
        adjusted_size *= sr_rule.size_multiplier
        adjusted_grade = downgrade_grade(adjusted_grade, sr_rule.grade_penalty_steps)
        reasons.append(sr_rule.reason)

        if sr_rule.blocked:
            blocked = True
            warnings.append(f"Setup-regime policy blocked trade: {sr_rule.reason}")

    # Apply global size environment
    if enhanced_brain.final_status == "SMALLER":
        adjusted_size *= gp.defensive_size_multiplier
        reasons.append(f"Applied defensive size multiplier {gp.defensive_size_multiplier:.2f}")
    else:
        adjusted_size *= gp.normal_size_multiplier
        reasons.append(f"Applied normal size multiplier {gp.normal_size_multiplier:.2f}")

    adjusted_size = round(clamp(adjusted_size, 0.0, 1.0), 3)

    return PolicyApplicationResult(
        blocked=blocked,
        adjusted_grade=adjusted_grade if not blocked else "AVOID",
        adjusted_ai_confidence=round(adjusted_ai_conf, 3),
        adjusted_size_fraction=0.0 if blocked else adjusted_size,
        reasons=reasons,
        warnings=warnings,
    )


# ============================================================
# REPORTING
# ============================================================

def policy_state_to_dict(policy_state: AdaptivePolicyState) -> dict:
    return {
        "setup_rules": {
            k: {
                "size_multiplier": v.size_multiplier,
                "confidence_adjustment": v.confidence_adjustment,
                "grade_penalty_steps": v.grade_penalty_steps,
                "blocked": v.blocked,
                "reason": v.reason,
            }
            for k, v in policy_state.setup_rules.items()
        },
        "setup_regime_rules": {
            k: {
                "setup_name": v.setup_name,
                "regime": v.regime,
                "size_multiplier": v.size_multiplier,
                "confidence_adjustment": v.confidence_adjustment,
                "grade_penalty_steps": v.grade_penalty_steps,
                "blocked": v.blocked,
                "reason": v.reason,
            }
            for k, v in policy_state.setup_regime_rules.items()
        },
        "global_policy": {
            "chasing_block_threshold": policy_state.global_policy.chasing_block_threshold,
            "hostile_macro_block_threshold": policy_state.global_policy.hostile_macro_block_threshold,
            "defensive_size_multiplier": policy_state.global_policy.defensive_size_multiplier,
            "normal_size_multiplier": policy_state.global_policy.normal_size_multiplier,
            "elite_setup_size_boost": policy_state.global_policy.elite_setup_size_boost,
            "weak_setup_size_penalty": policy_state.global_policy.weak_setup_size_penalty,
            "persistent_loser_block_enabled": policy_state.global_policy.persistent_loser_block_enabled,
            "notes": policy_state.global_policy.notes,
        }
    }


def format_policy_application_result(result: PolicyApplicationResult) -> str:
    emoji = "🔴" if result.blocked else "🟢"
    lines = [
        f"{emoji} **SELF-ADJUSTING POLICY RESULT**",
        f"**Blocked:** {'YES' if result.blocked else 'NO'}",
        f"**Adjusted Grade:** {result.adjusted_grade}",
        f"**Adjusted AI Confidence:** {result.adjusted_ai_confidence}",
        f"**Adjusted Size Fraction:** {result.adjusted_size_fraction}",
    ]

    if result.reasons:
        lines.append("")
        lines.append("**Reasons:**")
        for x in result.reasons[:8]:
            lines.append(f"• {x}")

    if result.warnings:
        lines.append("")
        lines.append("**Warnings:**")
        for x in result.warnings[:8]:
            lines.append(f"• {x}")

    return "\n".join(lines)


def print_policy_summary(policy_state: AdaptivePolicyState, max_items: int = 10) -> None:
    print("=== GLOBAL ADAPTIVE POLICY ===")
    print(json.dumps(policy_state_to_dict(policy_state)["global_policy"], indent=2))

    print("\n=== SETUP RULES ===")
    setup_items = list(policy_state.setup_rules.items())[:max_items]
    for k, v in setup_items:
        print(f"- {k}: size={v.size_multiplier}, conf_adj={v.confidence_adjustment}, "
              f"grade_penalty={v.grade_penalty_steps}, blocked={v.blocked}, reason={v.reason}")

    print("\n=== SETUP-REGIME RULES ===")
    sr_items = list(policy_state.setup_regime_rules.items())[:max_items]
    for k, v in sr_items:
        print(f"- {k}: size={v.size_multiplier}, conf_adj={v.confidence_adjustment}, "
              f"grade_penalty={v.grade_penalty_steps}, blocked={v.blocked}, reason={v.reason}")


# ============================================================
# TEST / RUN
# Assumes memory, market, signal, base_brain, enhanced_brain exist
# ============================================================

policy_state = build_adaptive_policy_state(memory)

print_policy_summary(policy_state, max_items=10)

policy_result = apply_adaptive_policy_to_brain(
    policy_state=policy_state,
    market=market,
    signal=signal,
    base_brain=base_brain,
    enhanced_brain=enhanced_brain
)

print("\n=== POLICY APPLICATION ===")
print(format_policy_application_result(policy_result))

# ============================================================
# NEXT CELL: PERFORMANCE DASHBOARD / SCORECARD
# Put this AFTER the auto-log completed trade cell
# ============================================================

import pandas as pd
import json


# ============================================================
# DATAFRAME BUILDERS
# ============================================================

def memory_trade_log_to_dataframe(memory: MemoryStore) -> pd.DataFrame:
    if not memory.trade_log:
        return pd.DataFrame()

    rows = [completed_trade_to_dict(t) for t in memory.trade_log]
    df = pd.DataFrame(rows)

    if not df.empty:
        df["win_rate_flag"] = df["win"].astype(int)

        df["chasing_bucket"] = pd.cut(
            df["chasing_score"],
            bins=[-0.001, 0.25, 0.50, 0.75, 1.0],
            labels=["low", "moderate", "high", "extreme"]
        )

        df["macro_bucket"] = pd.cut(
            df["macro_alignment_score"],
            bins=[-0.001, 0.40, 0.60, 0.80, 1.0],
            labels=["hostile", "weak", "good", "strong"]
        )

        df["entry_bucket"] = pd.cut(
            df["entry_quality_score"],
            bins=[-0.001, 0.45, 0.65, 0.80, 1.0],
            labels=["poor", "average", "good", "elite"]
        )

    return df


def summarize_group(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    if df.empty or group_col not in df.columns:
        return pd.DataFrame()

    grouped = (
        df.groupby(group_col, dropna=False)
        .agg(
            trades=("symbol", "count"),
            wins=("win_rate_flag", "sum"),
            win_rate=("win_rate_flag", "mean"),
            total_pnl=("pnl_dollars", "sum"),
            avg_pnl=("pnl_dollars", "mean"),
            total_r=("pnl_r", "sum"),
            avg_r=("pnl_r", "mean"),
            avg_mae_r=("max_adverse_excursion_r", "mean"),
            avg_mfe_r=("max_favorable_excursion_r", "mean"),
            avg_chasing=("chasing_score", "mean"),
            avg_macro_alignment=("macro_alignment_score", "mean"),
            avg_entry_quality=("entry_quality_score", "mean"),
            avg_ai_confidence=("ai_confidence", "mean"),
        )
        .reset_index()
    )

    grouped["win_rate"] = grouped["win_rate"].round(3)
    grouped["total_pnl"] = grouped["total_pnl"].round(2)
    grouped["avg_pnl"] = grouped["avg_pnl"].round(2)
    grouped["total_r"] = grouped["total_r"].round(3)
    grouped["avg_r"] = grouped["avg_r"].round(3)
    grouped["avg_mae_r"] = grouped["avg_mae_r"].round(3)
    grouped["avg_mfe_r"] = grouped["avg_mfe_r"].round(3)
    grouped["avg_chasing"] = grouped["avg_chasing"].round(3)
    grouped["avg_macro_alignment"] = grouped["avg_macro_alignment"].round(3)
    grouped["avg_entry_quality"] = grouped["avg_entry_quality"].round(3)
    grouped["avg_ai_confidence"] = grouped["avg_ai_confidence"].round(3)

    return grouped


# ============================================================
# RANKINGS
# ============================================================

def get_best_setups(df: pd.DataFrame, min_trades: int = 3) -> pd.DataFrame:
    summary = summarize_group(df, "setup_name")
    if summary.empty:
        return summary

    summary = summary[summary["trades"] >= min_trades].copy()
    summary["score"] = (
        summary["avg_r"] * 0.45 +
        summary["win_rate"] * 0.30 +
        (summary["avg_mfe_r"] - summary["avg_mae_r"]) * 0.25
    ).round(3)

    return summary.sort_values(["score", "total_pnl"], ascending=[False, False]).reset_index(drop=True)


def get_worst_setups(df: pd.DataFrame, min_trades: int = 3) -> pd.DataFrame:
    summary = summarize_group(df, "setup_name")
    if summary.empty:
        return summary

    summary = summary[summary["trades"] >= min_trades].copy()
    summary["score"] = (
        summary["avg_r"] * 0.45 +
        summary["win_rate"] * 0.30 +
        (summary["avg_mfe_r"] - summary["avg_mae_r"]) * 0.25
    ).round(3)

    return summary.sort_values(["score", "total_pnl"], ascending=[True, True]).reset_index(drop=True)


def get_best_setup_regime_combos(df: pd.DataFrame, min_trades: int = 2) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    temp = df.copy()
    temp["setup_regime"] = temp["setup_name"] + " | " + temp["regime"]

    summary = summarize_group(temp, "setup_regime")
    summary = summary[summary["trades"] >= min_trades].copy()

    if summary.empty:
        return summary

    summary["score"] = (
        summary["avg_r"] * 0.50 +
        summary["win_rate"] * 0.30 +
        (summary["avg_mfe_r"] - summary["avg_mae_r"]) * 0.20
    ).round(3)

    return summary.sort_values(["score", "total_pnl"], ascending=[False, False]).reset_index(drop=True)


# ============================================================
# BEHAVIOR ANALYSIS
# ============================================================

def get_chasing_damage_report(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "chasing_bucket" not in df.columns:
        return pd.DataFrame()

    summary = summarize_group(df, "chasing_bucket")
    if summary.empty:
        return summary

    summary["damage_score"] = (
        summary["avg_mae_r"] - summary["avg_r"]
    ).round(3)

    return summary.sort_values("chasing_bucket").reset_index(drop=True)


def get_macro_alignment_report(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "macro_bucket" not in df.columns:
        return pd.DataFrame()

    summary = summarize_group(df, "macro_bucket")
    return summary.sort_values("macro_bucket").reset_index(drop=True)


def get_entry_quality_report(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "entry_bucket" not in df.columns:
        return pd.DataFrame()

    summary = summarize_group(df, "entry_bucket")
    return summary.sort_values("entry_bucket").reset_index(drop=True)


# ============================================================
# TOP-LEVEL SCORECARD
# ============================================================

def build_ai_scorecard(memory: MemoryStore) -> dict:
    df = memory_trade_log_to_dataframe(memory)

    if df.empty:
        return {
            "trade_count": 0,
            "message": "No trade log data available yet."
        }

    total_trades = len(df)
    wins = int(df["win"].sum())
    losses = total_trades - wins
    win_rate = round(df["win"].mean(), 3)
    total_pnl = round(df["pnl_dollars"].sum(), 2)
    avg_pnl = round(df["pnl_dollars"].mean(), 2)
    total_r = round(df["pnl_r"].sum(), 3)
    avg_r = round(df["pnl_r"].mean(), 3)
    avg_mae_r = round(df["max_adverse_excursion_r"].mean(), 3)
    avg_mfe_r = round(df["max_favorable_excursion_r"].mean(), 3)
    avg_chasing = round(df["chasing_score"].mean(), 3)
    avg_macro = round(df["macro_alignment_score"].mean(), 3)
    avg_entry = round(df["entry_quality_score"].mean(), 3)
    avg_ai_conf = round(df["ai_confidence"].mean(), 3)

    scorecard = {
        "trade_count": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_pnl_dollars": total_pnl,
        "avg_pnl_dollars": avg_pnl,
        "total_r": total_r,
        "avg_r": avg_r,
        "avg_mae_r": avg_mae_r,
        "avg_mfe_r": avg_mfe_r,
        "avg_chasing_score": avg_chasing,
        "avg_macro_alignment": avg_macro,
        "avg_entry_quality": avg_entry,
        "avg_ai_confidence": avg_ai_conf,
    }

    return scorecard


def format_ai_scorecard(scorecard: dict) -> str:
    if scorecard.get("trade_count", 0) == 0:
        return "No trade data available yet."

    lines = [
        "=== UNBIASED AI SCORECARD ===",
        f"Trades: {scorecard['trade_count']}",
        f"Wins: {scorecard['wins']}",
        f"Losses: {scorecard['losses']}",
        f"Win Rate: {scorecard['win_rate']}",
        f"Total PnL: ${scorecard['total_pnl_dollars']}",
        f"Avg PnL: ${scorecard['avg_pnl_dollars']}",
        f"Total R: {scorecard['total_r']}",
        f"Avg R: {scorecard['avg_r']}",
        f"Avg MAE (R): {scorecard['avg_mae_r']}",
        f"Avg MFE (R): {scorecard['avg_mfe_r']}",
        f"Avg Chasing Score: {scorecard['avg_chasing_score']}",
        f"Avg Macro Alignment: {scorecard['avg_macro_alignment']}",
        f"Avg Entry Quality: {scorecard['avg_entry_quality']}",
        f"Avg AI Confidence: {scorecard['avg_ai_confidence']}",
    ]
    return "\n".join(lines)


# ============================================================
# DASHBOARD DISPLAY
# ============================================================

def show_full_ai_dashboard(memory: MemoryStore, min_setup_trades: int = 3, min_combo_trades: int = 2) -> None:
    df = memory_trade_log_to_dataframe(memory)

    scorecard = build_ai_scorecard(memory)
    print(format_ai_scorecard(scorecard))

    if df.empty:
        print("\nNo dashboard tables yet.")
        return

    print("\n=== BEST SETUPS ===")
    best_setups = get_best_setups(df, min_trades=min_setup_trades)
    if best_setups.empty:
        print("No best setup table yet.")
    else:
        print(best_setups.to_string(index=False))

    print("\n=== WORST SETUPS ===")
    worst_setups = get_worst_setups(df, min_trades=min_setup_trades)
    if worst_setups.empty:
        print("No worst setup table yet.")
    else:
        print(worst_setups.to_string(index=False))

    print("\n=== BEST SETUP + REGIME COMBOS ===")
    best_combos = get_best_setup_regime_combos(df, min_trades=min_combo_trades)
    if best_combos.empty:
        print("No setup+regime combo table yet.")
    else:
        print(best_combos.to_string(index=False))

    print("\n=== CHASING DAMAGE REPORT ===")
    chasing_report = get_chasing_damage_report(df)
    if chasing_report.empty:
        print("No chasing report yet.")
    else:
        print(chasing_report.to_string(index=False))

    print("\n=== MACRO ALIGNMENT REPORT ===")
    macro_report = get_macro_alignment_report(df)
    if macro_report.empty:
        print("No macro report yet.")
    else:
        print(macro_report.to_string(index=False))

    print("\n=== ENTRY QUALITY REPORT ===")
    entry_report = get_entry_quality_report(df)
    if entry_report.empty:
        print("No entry quality report yet.")
    else:
        print(entry_report.to_string(index=False))


# ============================================================
# OPTIONAL: DIAGNOSTIC INSIGHTS
# ============================================================

def generate_ai_diagnostics(memory: MemoryStore) -> List[str]:
    insights = []
    df = memory_trade_log_to_dataframe(memory)

    if df.empty:
        return ["No trade data available yet."]

    scorecard = build_ai_scorecard(memory)

    if scorecard["avg_r"] < 0:
        insights.append("Average R is negative. The system is losing efficiency overall.")

    if scorecard["avg_chasing_score"] > 0.55:
        insights.append("Chasing is too high overall. The brain should tighten late-entry blocking.")

    if scorecard["avg_mae_r"] > 1.0:
        insights.append("Average adverse excursion is high. Stops may be too wide or entries too early.")

    best_setups = get_best_setups(df, min_trades=3)
    if not best_setups.empty:
        top_row = best_setups.iloc[0]
        insights.append(
            f"Best current setup is '{top_row['setup_name']}' with avg R {top_row['avg_r']} and win rate {top_row['win_rate']}."
        )

    worst_setups = get_worst_setups(df, min_trades=3)
    if not worst_setups.empty:
        low_row = worst_setups.iloc[0]
        insights.append(
            f"Weakest current setup is '{low_row['setup_name']}' with avg R {low_row['avg_r']} and win rate {low_row['win_rate']}."
        )

    macro_report = get_macro_alignment_report(df)
    if not macro_report.empty and "hostile" in macro_report["macro_bucket"].astype(str).values:
        hostile_row = macro_report[macro_report["macro_bucket"].astype(str) == "hostile"]
        if not hostile_row.empty and float(hostile_row.iloc[0]["avg_r"]) < 0:
            insights.append("Hostile macro conditions are hurting performance. Size should stay reduced there.")

    chasing_report = get_chasing_damage_report(df)
    if not chasing_report.empty:
        extreme_rows = chasing_report[chasing_report["chasing_bucket"].astype(str) == "extreme"]
        if not extreme_rows.empty and float(extreme_rows.iloc[0]["avg_r"]) < 0:
            insights.append("Extreme chasing is clearly unprofitable. Those entries should be blocked.")

    if not insights:
        insights.append("No major weaknesses detected yet. Keep collecting trade data.")

    return insights


# ============================================================
# TEST / RUN DASHBOARD
# ============================================================

show_full_ai_dashboard(memory)

print("\n=== AI DIAGNOSTICS ===")
for item in generate_ai_diagnostics(memory):
    print("-", item)

# ============================================================
# NEXT CELL: AUTO LOG COMPLETED TRADES INTO MEMORY
# Put this AFTER the save/load memory cell
# ============================================================

from typing import Optional
import json


# ============================================================
# HELPERS FOR TRADE OUTCOME CALCULATION
# ============================================================

def safe_div(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return a / b


def calculate_trade_pnl_dollars(
    entry_price: float,
    exit_price: float,
    contracts: int,
    contract_multiplier: int = 100
) -> float:
    """
    Option PnL in dollars.
    Example: buy 1.20, sell 2.00, 1 contract => (2.00 - 1.20) * 100 = $80
    """
    return (exit_price - entry_price) * contracts * contract_multiplier


def calculate_trade_r_multiple(
    pnl_dollars: float,
    risk_dollars: float
) -> float:
    return safe_div(pnl_dollars, risk_dollars)


def calculate_win_flag(pnl_dollars: float) -> bool:
    return pnl_dollars > 0


# ============================================================
# AUTO LOGGER
# ============================================================

def auto_log_completed_trade(
    memory: MemoryStore,
    market: MarketState,
    signal: SignalState,
    portfolio: PortfolioState,
    cfg: RiskConfig,
    enhanced_brain: EnhancedBrainDecision,
    entry_option_price: float,
    exit_option_price: float,
    contracts: int,
    risk_dollars: float,
    max_adverse_excursion_r: float,
    max_favorable_excursion_r: float,
    approved: bool = True,
    executed: bool = True,
) -> TradeLogRecord:
    """
    Automatically creates and stores a completed trade record.
    """

    regime = detect_regime(market, cfg)

    pnl_dollars = calculate_trade_pnl_dollars(
        entry_price=entry_option_price,
        exit_price=exit_option_price,
        contracts=contracts,
        contract_multiplier=cfg.contract_multiplier,
    )

    pnl_r = calculate_trade_r_multiple(
        pnl_dollars=pnl_dollars,
        risk_dollars=risk_dollars,
    )

    win = calculate_win_flag(pnl_dollars)

    trade = TradeLogRecord(
        symbol=market.symbol,
        setup_name=signal.setup_name,
        regime=regime.value,
        trade_grade=enhanced_brain.final_grade,
        direction=enhanced_brain.final_direction,
        ai_confidence=enhanced_brain.adjusted_ai_confidence,
        entry_quality_score=signal.entry_quality_score,
        chasing_score=signal.chasing_score,
        macro_alignment_score=signal.macro_alignment_score,
        vwap_alignment_score=signal.vwap_alignment_score,
        level_respect_score=signal.level_respect_score,
        momentum_alignment_score=signal.momentum_alignment_score,
        approved=approved,
        executed=executed,
        contracts=contracts,
        risk_dollars=risk_dollars,
        pnl_dollars=round(pnl_dollars, 2),
        pnl_r=round(pnl_r, 3),
        max_adverse_excursion_r=round(max_adverse_excursion_r, 3),
        max_favorable_excursion_r=round(max_favorable_excursion_r, 3),
        win=win,
    )

    log_completed_trade(memory, trade)
    return trade


# ============================================================
# POST-TRADE SUMMARY FORMATTERS
# ============================================================

def completed_trade_to_dict(trade: TradeLogRecord) -> dict:
    return {
        "symbol": trade.symbol,
        "setup_name": trade.setup_name,
        "regime": trade.regime,
        "trade_grade": trade.trade_grade,
        "direction": trade.direction,
        "ai_confidence": trade.ai_confidence,
        "entry_quality_score": trade.entry_quality_score,
        "chasing_score": trade.chasing_score,
        "macro_alignment_score": trade.macro_alignment_score,
        "vwap_alignment_score": trade.vwap_alignment_score,
        "level_respect_score": trade.level_respect_score,
        "momentum_alignment_score": trade.momentum_alignment_score,
        "approved": trade.approved,
        "executed": trade.executed,
        "contracts": trade.contracts,
        "risk_dollars": trade.risk_dollars,
        "pnl_dollars": trade.pnl_dollars,
        "pnl_r": trade.pnl_r,
        "max_adverse_excursion_r": trade.max_adverse_excursion_r,
        "max_favorable_excursion_r": trade.max_favorable_excursion_r,
        "win": trade.win,
    }


def format_completed_trade_review(trade: TradeLogRecord) -> str:
    emoji = "🟢" if trade.win else "🔴"

    lines = [
        f"{emoji} **COMPLETED TRADE LOGGED**",
        f"**Symbol:** {trade.symbol}",
        f"**Setup:** {trade.setup_name}",
        f"**Regime:** {trade.regime}",
        f"**Direction:** {trade.direction}",
        f"**Grade:** {trade.trade_grade}",
        f"**Contracts:** {trade.contracts}",
        f"**Risk Dollars:** ${trade.risk_dollars}",
        f"**PnL Dollars:** ${trade.pnl_dollars}",
        f"**PnL (R):** {trade.pnl_r}",
        f"**MAE (R):** {trade.max_adverse_excursion_r}",
        f"**MFE (R):** {trade.max_favorable_excursion_r}",
        f"**Win:** {'YES' if trade.win else 'NO'}",
        f"**AI Confidence:** {trade.ai_confidence}",
        f"**Entry Quality:** {trade.entry_quality_score}",
        f"**Chasing Score:** {trade.chasing_score}",
        f"**Macro Alignment:** {trade.macro_alignment_score}",
    ]

    return "\n".join(lines)


def show_latest_trade_log(memory: MemoryStore) -> None:
    if not memory.trade_log:
        print("No trades logged yet.")
        return

    latest = memory.trade_log[-1]
    print(json.dumps(completed_trade_to_dict(latest), indent=2))


# ============================================================
# TEST EXAMPLE
# ============================================================

# Assumes these variables already exist from earlier cells:
# memory, market, signal, portfolio, cfg, enhanced_brain

logged_trade = auto_log_completed_trade(
    memory=memory,
    market=market,
    signal=signal,
    portfolio=portfolio,
    cfg=cfg,
    enhanced_brain=enhanced_brain,
    entry_option_price=1.20,
    exit_option_price=2.05,
    contracts=1,
    risk_dollars=35.0,
    max_adverse_excursion_r=0.45,
    max_favorable_excursion_r=2.80,
    approved=True,
    executed=True,
)

print("=== LATEST LOGGED TRADE ===")
print(json.dumps(completed_trade_to_dict(logged_trade), indent=2))

print("\n=== TRADE REVIEW ===")
print(format_completed_trade_review(logged_trade))

print("\n=== MEMORY OVERVIEW AFTER LOG ===")
show_memory_overview(memory)

# ============================================================
# NEXT CELL: SAVE / LOAD MEMORY TO JSON
# Put this AFTER the memory + adaptive learning cell
# ============================================================

import json
import os
from dataclasses import asdict, fields
from typing import Any


# ============================================================
# SERIALIZATION HELPERS
# ============================================================

def dataclass_from_dict(cls, data: dict):
    """
    Rebuild a dataclass from a dictionary using matching field names only.
    """
    field_names = {f.name for f in fields(cls)}
    clean = {k: v for k, v in data.items() if k in field_names}
    return cls(**clean)


def pattern_stats_to_dict(stats: PatternStats) -> dict:
    return {
        "trades": stats.trades,
        "wins": stats.wins,
        "losses": stats.losses,
        "total_pnl": stats.total_pnl,
        "total_r": stats.total_r,
        "avg_pnl": stats.avg_pnl,
        "avg_r": stats.avg_r,
        "avg_mae_r": stats.avg_mae_r,
        "avg_mfe_r": stats.avg_mfe_r,
        "avg_chasing_score": stats.avg_chasing_score,
        "avg_ai_confidence": stats.avg_ai_confidence,
        "avg_macro_alignment": stats.avg_macro_alignment,
        "avg_entry_quality": stats.avg_entry_quality,
        "last_5_r": list(stats.last_5_r),
    }


def pattern_stats_from_dict(data: dict) -> PatternStats:
    return PatternStats(
        trades=data.get("trades", 0),
        wins=data.get("wins", 0),
        losses=data.get("losses", 0),
        total_pnl=data.get("total_pnl", 0.0),
        total_r=data.get("total_r", 0.0),
        avg_pnl=data.get("avg_pnl", 0.0),
        avg_r=data.get("avg_r", 0.0),
        avg_mae_r=data.get("avg_mae_r", 0.0),
        avg_mfe_r=data.get("avg_mfe_r", 0.0),
        avg_chasing_score=data.get("avg_chasing_score", 0.0),
        avg_ai_confidence=data.get("avg_ai_confidence", 0.0),
        avg_macro_alignment=data.get("avg_macro_alignment", 0.0),
        avg_entry_quality=data.get("avg_entry_quality", 0.0),
        last_5_r=data.get("last_5_r", []),
    )


def trade_log_record_to_dict(trade: TradeLogRecord) -> dict:
    return asdict(trade)


def trade_log_record_from_dict(data: dict) -> TradeLogRecord:
    return dataclass_from_dict(TradeLogRecord, data)


# ============================================================
# MEMORY SAVE / LOAD
# ============================================================

def memory_store_to_dict(memory: MemoryStore) -> dict:
    return {
        "by_setup": {k: pattern_stats_to_dict(v) for k, v in memory.by_setup.items()},
        "by_regime": {k: pattern_stats_to_dict(v) for k, v in memory.by_regime.items()},
        "by_setup_regime": {k: pattern_stats_to_dict(v) for k, v in memory.by_setup_regime.items()},
        "by_grade": {k: pattern_stats_to_dict(v) for k, v in memory.by_grade.items()},
        "by_symbol": {k: pattern_stats_to_dict(v) for k, v in memory.by_symbol.items()},
        "trade_log": [trade_log_record_to_dict(t) for t in memory.trade_log],
    }


def memory_store_from_dict(data: dict) -> MemoryStore:
    memory = MemoryStore()

    memory.by_setup = {
        k: pattern_stats_from_dict(v)
        for k, v in data.get("by_setup", {}).items()
    }
    memory.by_regime = {
        k: pattern_stats_from_dict(v)
        for k, v in data.get("by_regime", {}).items()
    }
    memory.by_setup_regime = {
        k: pattern_stats_from_dict(v)
        for k, v in data.get("by_setup_regime", {}).items()
    }
    memory.by_grade = {
        k: pattern_stats_from_dict(v)
        for k, v in data.get("by_grade", {}).items()
    }
    memory.by_symbol = {
        k: pattern_stats_from_dict(v)
        for k, v in data.get("by_symbol", {}).items()
    }
    memory.trade_log = [
        trade_log_record_from_dict(x)
        for x in data.get("trade_log", [])
    ]

    return memory


def save_memory_to_json(memory: MemoryStore, filepath: str = "/content/unbiased_ai_memory.json") -> None:
    payload = memory_store_to_dict(memory)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"✅ Memory saved to: {filepath}")
    print(f"Saved trades: {len(memory.trade_log)}")


def load_memory_from_json(filepath: str = "/content/unbiased_ai_memory.json") -> MemoryStore:
    if not os.path.exists(filepath):
        print(f"⚠️ No memory file found at: {filepath}")
        print("Returning a new empty MemoryStore.")
        return MemoryStore()

    with open(filepath, "r", encoding="utf-8") as f:
        payload = json.load(f)

    memory = memory_store_from_dict(payload)
    print(f"✅ Memory loaded from: {filepath}")
    print(f"Loaded trades: {len(memory.trade_log)}")
    return memory


# ============================================================
# OPTIONAL BACKUP HELPERS
# ============================================================

def export_memory_snapshot(memory: MemoryStore, name: str = "unbiased_ai_memory_snapshot") -> str:
    """
    Saves a timestamp-free named snapshot file.
    """
    filepath = f"/content/{name}.json"
    save_memory_to_json(memory, filepath)
    return filepath


def reset_memory_store() -> MemoryStore:
    print("⚠️ Resetting memory store to empty.")
    return MemoryStore()


# ============================================================
# QUICK INSPECTION HELPERS
# ============================================================

def show_memory_overview(memory: MemoryStore) -> None:
    print("=== MEMORY OVERVIEW ===")
    print(f"Trade log count: {len(memory.trade_log)}")
    print(f"Setup buckets: {len(memory.by_setup)}")
    print(f"Regime buckets: {len(memory.by_regime)}")
    print(f"Setup+Regime buckets: {len(memory.by_setup_regime)}")
    print(f"Grade buckets: {len(memory.by_grade)}")
    print(f"Symbol buckets: {len(memory.by_symbol)}")

    if memory.by_setup:
        print("\nTop setups:")
        for k, v in list(memory.by_setup.items())[:5]:
            print(f"- {k}: trades={v.trades}, win_rate={round(v.win_rate, 3)}, expectancy_r={round(v.expectancy_r, 3)}")


# ============================================================
# TEST: SAVE CURRENT MEMORY THEN LOAD IT BACK
# ============================================================

# This assumes you already have a variable called `memory`
# from the previous cell. If not, create one first:
# memory = MemoryStore()

save_path = "/content/unbiased_ai_memory.json"

save_memory_to_json(memory, save_path)

loaded_memory = load_memory_from_json(save_path)

show_memory_overview(loaded_memory)

# ============================================================
# NEXT CELL: LIVE MEMORY + ADAPTIVE LEARNING LAYER
# Put this AFTER the risk engine + AI brain cells
# ============================================================

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import json


# ============================================================
# MEMORY MODELS
# ============================================================

@dataclass
class TradeLogRecord:
    symbol: str
    setup_name: str
    regime: str
    trade_grade: str
    direction: str
    ai_confidence: float
    entry_quality_score: float
    chasing_score: float
    macro_alignment_score: float
    vwap_alignment_score: float
    level_respect_score: float
    momentum_alignment_score: float
    approved: bool
    executed: bool
    contracts: int
    risk_dollars: float
    pnl_dollars: float
    pnl_r: float
    max_adverse_excursion_r: float
    max_favorable_excursion_r: float
    win: bool


@dataclass
class PatternStats:
    trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    total_r: float = 0.0
    avg_pnl: float = 0.0
    avg_r: float = 0.0
    avg_mae_r: float = 0.0
    avg_mfe_r: float = 0.0
    avg_chasing_score: float = 0.0
    avg_ai_confidence: float = 0.0
    avg_macro_alignment: float = 0.0
    avg_entry_quality: float = 0.0
    last_5_r: List[float] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades if self.trades > 0 else 0.0

    @property
    def expectancy_r(self) -> float:
        return self.total_r / self.trades if self.trades > 0 else 0.0

    @property
    def recent_r(self) -> float:
        if not self.last_5_r:
            return 0.0
        return sum(self.last_5_r) / len(self.last_5_r)


@dataclass
class MemoryStore:
    by_setup: Dict[str, PatternStats] = field(default_factory=dict)
    by_regime: Dict[str, PatternStats] = field(default_factory=dict)
    by_setup_regime: Dict[str, PatternStats] = field(default_factory=dict)
    by_grade: Dict[str, PatternStats] = field(default_factory=dict)
    by_symbol: Dict[str, PatternStats] = field(default_factory=dict)
    trade_log: List[TradeLogRecord] = field(default_factory=list)


# ============================================================
# MEMORY HELPERS
# ============================================================

def _get_or_create_stats(bucket: Dict[str, PatternStats], key: str) -> PatternStats:
    if key not in bucket:
        bucket[key] = PatternStats()
    return bucket[key]


def _update_running_average(old_avg: float, old_count: int, new_value: float) -> float:
    return ((old_avg * old_count) + new_value) / (old_count + 1)


def update_pattern_stats(stats: PatternStats, trade: TradeLogRecord) -> None:
    old_count = stats.trades

    stats.avg_pnl = _update_running_average(stats.avg_pnl, old_count, trade.pnl_dollars)
    stats.avg_r = _update_running_average(stats.avg_r, old_count, trade.pnl_r)
    stats.avg_mae_r = _update_running_average(stats.avg_mae_r, old_count, trade.max_adverse_excursion_r)
    stats.avg_mfe_r = _update_running_average(stats.avg_mfe_r, old_count, trade.max_favorable_excursion_r)
    stats.avg_chasing_score = _update_running_average(stats.avg_chasing_score, old_count, trade.chasing_score)
    stats.avg_ai_confidence = _update_running_average(stats.avg_ai_confidence, old_count, trade.ai_confidence)
    stats.avg_macro_alignment = _update_running_average(stats.avg_macro_alignment, old_count, trade.macro_alignment_score)
    stats.avg_entry_quality = _update_running_average(stats.avg_entry_quality, old_count, trade.entry_quality_score)

    stats.trades += 1
    stats.total_pnl += trade.pnl_dollars
    stats.total_r += trade.pnl_r

    if trade.win:
        stats.wins += 1
    else:
        stats.losses += 1

    stats.last_5_r.append(trade.pnl_r)
    if len(stats.last_5_r) > 5:
        stats.last_5_r = stats.last_5_r[-5:]


def log_completed_trade(memory: MemoryStore, trade: TradeLogRecord) -> None:
    memory.trade_log.append(trade)

    setup_stats = _get_or_create_stats(memory.by_setup, trade.setup_name)
    regime_stats = _get_or_create_stats(memory.by_regime, trade.regime)
    setup_regime_stats = _get_or_create_stats(memory.by_setup_regime, f"{trade.setup_name}__{trade.regime}")
    grade_stats = _get_or_create_stats(memory.by_grade, trade.trade_grade)
    symbol_stats = _get_or_create_stats(memory.by_symbol, trade.symbol)

    update_pattern_stats(setup_stats, trade)
    update_pattern_stats(regime_stats, trade)
    update_pattern_stats(setup_regime_stats, trade)
    update_pattern_stats(grade_stats, trade)
    update_pattern_stats(symbol_stats, trade)


# ============================================================
# ADAPTIVE POLICY LAYER
# ============================================================

@dataclass
class AdaptivePolicyDecision:
    size_multiplier_adjustment: float
    confidence_adjustment: float
    grade_penalty_steps: int
    should_block: bool
    policy_reason: str
    warnings: List[str]


def evaluate_pattern_quality(stats: PatternStats, min_trades: int = 5) -> str:
    if stats.trades < min_trades:
        return "INSUFFICIENT_DATA"

    wr = stats.win_rate
    exp_r = stats.expectancy_r
    recent = stats.recent_r

    if wr >= 0.62 and exp_r >= 0.25 and recent >= 0.10:
        return "STRONG"
    if wr >= 0.52 and exp_r >= 0.05:
        return "STABLE"
    if wr >= 0.42 and exp_r >= -0.05:
        return "MIXED"
    return "WEAK"


def adaptive_policy_from_memory(
    memory: MemoryStore,
    signal: SignalState,
    regime: MarketRegime,
) -> AdaptivePolicyDecision:
    warnings: List[str] = []

    setup_stats = memory.by_setup.get(signal.setup_name)
    setup_regime_stats = memory.by_setup_regime.get(f"{signal.setup_name}__{regime.value}")

    size_adj = 1.00
    conf_adj = 0.00
    grade_penalty_steps = 0
    should_block = False
    reason = "No meaningful memory adjustment."

    # prioritize setup+regime if enough data exists
    if setup_regime_stats and setup_regime_stats.trades >= 4:
        quality = evaluate_pattern_quality(setup_regime_stats, min_trades=4)

        if quality == "STRONG":
            size_adj *= 1.10
            conf_adj += 0.05
            reason = f"Strong setup-regime memory for {signal.setup_name} in {regime.value}."
        elif quality == "STABLE":
            size_adj *= 1.00
            conf_adj += 0.02
            reason = f"Stable setup-regime memory for {signal.setup_name} in {regime.value}."
        elif quality == "MIXED":
            size_adj *= 0.85
            conf_adj -= 0.05
            warnings.append("Setup-regime memory is mixed. Size reduced.")
            reason = f"Mixed setup-regime memory for {signal.setup_name} in {regime.value}."
        elif quality == "WEAK":
            size_adj *= 0.60
            conf_adj -= 0.10
            grade_penalty_steps += 1
            warnings.append("Weak setup-regime memory. Grade penalty applied.")
            reason = f"Weak setup-regime memory for {signal.setup_name} in {regime.value}."

            if setup_regime_stats.trades >= 8 and setup_regime_stats.expectancy_r < -0.20:
                should_block = True
                warnings.append("This setup-regime combo is deeply underperforming.")
                reason = f"Blocked weak setup-regime combo for {signal.setup_name} in {regime.value}."

    elif setup_stats and setup_stats.trades >= 5:
        quality = evaluate_pattern_quality(setup_stats, min_trades=5)

        if quality == "STRONG":
            size_adj *= 1.05
            conf_adj += 0.03
            reason = f"Strong setup memory for {signal.setup_name}."
        elif quality == "STABLE":
            reason = f"Stable setup memory for {signal.setup_name}."
        elif quality == "MIXED":
            size_adj *= 0.90
            conf_adj -= 0.04
            warnings.append("Setup memory is mixed. Slight size reduction.")
            reason = f"Mixed setup memory for {signal.setup_name}."
        elif quality == "WEAK":
            size_adj *= 0.65
            conf_adj -= 0.10
            grade_penalty_steps += 1
            warnings.append("Weak setup memory. Grade penalty applied.")
            reason = f"Weak setup memory for {signal.setup_name}."

            if setup_stats.trades >= 10 and setup_stats.expectancy_r < -0.25:
                should_block = True
                warnings.append("Setup is persistently underperforming.")
                reason = f"Blocked weak setup memory for {signal.setup_name}."

    # behavior penalties
    if signal.chasing_score >= 0.75:
        size_adj *= 0.75
        conf_adj -= 0.07
        warnings.append("Memory layer penalized high chasing behavior.")

    if signal.macro_alignment_score < 0.45:
        size_adj *= 0.85
        conf_adj -= 0.05
        warnings.append("Memory layer penalized weak macro alignment.")

    return AdaptivePolicyDecision(
        size_multiplier_adjustment=round(size_adj, 3),
        confidence_adjustment=round(conf_adj, 3),
        grade_penalty_steps=grade_penalty_steps,
        should_block=should_block,
        policy_reason=reason,
        warnings=warnings,
    )


# ============================================================
# GRADE ADJUSTMENT HELPERS
# ============================================================

GRADE_ORDER = ["A+", "A", "B+", "B", "AVOID"]

def downgrade_grade(grade: str, steps: int) -> str:
    idx = GRADE_ORDER.index(grade) if grade in GRADE_ORDER else len(GRADE_ORDER) - 1
    new_idx = min(len(GRADE_ORDER) - 1, idx + steps)
    return GRADE_ORDER[new_idx]


# ============================================================
# MEMORY-ENHANCED BRAIN
# ============================================================

@dataclass
class EnhancedBrainDecision:
    final_status: str
    final_grade: str
    final_direction: str
    final_conviction: float
    adjusted_ai_confidence: float
    adjusted_size_fraction: float
    memory_policy_reason: str
    memory_warnings: List[str]
    should_block_from_memory: bool
    notes: List[str]


def run_memory_enhanced_brain(
    memory: MemoryStore,
    market: MarketState,
    signal: SignalState,
    portfolio: PortfolioState,
    cfg: RiskConfig,
    option_premium: float,
    option_stop_fraction_of_premium: float = 0.35,
) -> Tuple[AIBrainDecision, EnhancedBrainDecision]:

    # run original brain first
    base_brain = run_risk_first_ai_brain(
        market=market,
        signal=signal,
        portfolio=portfolio,
        cfg=cfg,
        option_premium=option_premium,
        option_stop_fraction_of_premium=option_stop_fraction_of_premium,
    )

    regime = detect_regime(market, cfg)
    mem_policy = adaptive_policy_from_memory(memory, signal, regime)

    # adjust confidence
    adjusted_confidence = clamp(signal.ai_confidence + mem_policy.confidence_adjustment, 0.0, 1.0)

    # adjust grade
    adjusted_grade = downgrade_grade(base_brain.final_grade, mem_policy.grade_penalty_steps)

    # adjust size
    adjusted_size_fraction = round(
        clamp(base_brain.size_fraction_of_max * mem_policy.size_multiplier_adjustment, 0.0, 1.0),
        3
    )

    # adjust conviction
    conviction_adjustment = mem_policy.confidence_adjustment * 100.0 * 0.50
    adjusted_conviction = round(clamp(base_brain.conviction_score + conviction_adjustment, 0.0, 100.0), 2)

    final_status = base_brain.brain_status
    notes = list(base_brain.reasoning)

    if mem_policy.should_block:
        final_status = "BLOCKED"
        adjusted_grade = "AVOID"
        adjusted_size_fraction = 0.0
        notes.append("Memory layer blocked this setup due to persistent underperformance.")

    elif final_status == "APPROVED" and mem_policy.size_multiplier_adjustment < 0.85:
        final_status = "SMALLER"
        notes.append("Memory layer reduced size despite approval.")

    notes.append(mem_policy.policy_reason)

    enhanced = EnhancedBrainDecision(
        final_status=final_status,
        final_grade=adjusted_grade,
        final_direction=base_brain.final_direction,
        final_conviction=adjusted_conviction,
        adjusted_ai_confidence=round(adjusted_confidence, 3),
        adjusted_size_fraction=adjusted_size_fraction,
        memory_policy_reason=mem_policy.policy_reason,
        memory_warnings=mem_policy.warnings,
        should_block_from_memory=mem_policy.should_block,
        notes=mem_policy.warnings + notes,
    )

    return base_brain, enhanced


# ============================================================
# REPORTING
# ============================================================

def stats_to_dict(stats: PatternStats) -> dict:
    return {
        "trades": stats.trades,
        "wins": stats.wins,
        "losses": stats.losses,
        "win_rate": round(stats.win_rate, 3),
        "expectancy_r": round(stats.expectancy_r, 3),
        "recent_r": round(stats.recent_r, 3),
        "total_pnl": round(stats.total_pnl, 2),
        "avg_pnl": round(stats.avg_pnl, 2),
        "avg_r": round(stats.avg_r, 3),
        "avg_mae_r": round(stats.avg_mae_r, 3),
        "avg_mfe_r": round(stats.avg_mfe_r, 3),
        "avg_chasing_score": round(stats.avg_chasing_score, 3),
        "avg_ai_confidence": round(stats.avg_ai_confidence, 3),
        "avg_macro_alignment": round(stats.avg_macro_alignment, 3),
        "avg_entry_quality": round(stats.avg_entry_quality, 3),
        "last_5_r": [round(x, 3) for x in stats.last_5_r],
    }


def print_memory_summary(memory: MemoryStore) -> None:
    print("=== MEMORY SUMMARY ===")
    print(f"Total logged trades: {len(memory.trade_log)}")

    print("\nTop Setup Stats:")
    for k, v in list(memory.by_setup.items())[:10]:
        print(f"- {k}: {json.dumps(stats_to_dict(v))}")

    print("\nTop Regime Stats:")
    for k, v in list(memory.by_regime.items())[:10]:
        print(f"- {k}: {json.dumps(stats_to_dict(v))}")


def format_memory_brain_alert(
    market: MarketState,
    signal: SignalState,
    enhanced: EnhancedBrainDecision
) -> str:
    emoji = {
        "APPROVED": "🟢",
        "SMALLER": "🟡",
        "BLOCKED": "🔴"
    }.get(enhanced.final_status, "⚪")

    lines = [
        f"{emoji} **MEMORY-ENHANCED AI BRAIN**",
        f"**Symbol:** {market.symbol}",
        f"**Direction:** {enhanced.final_direction}",
        f"**Setup:** {signal.setup_name}",
        f"**Final Status:** {enhanced.final_status}",
        f"**Final Grade:** {enhanced.final_grade}",
        f"**Final Conviction:** {enhanced.final_conviction}",
        f"**Adjusted AI Confidence:** {enhanced.adjusted_ai_confidence}",
        f"**Adjusted Size Fraction:** {enhanced.adjusted_size_fraction}",
        f"**Memory Policy:** {enhanced.memory_policy_reason}",
    ]

    if enhanced.memory_warnings:
        lines.append("")
        lines.append("**Memory Warnings:**")
        for x in enhanced.memory_warnings[:5]:
            lines.append(f"• {x}")

    if enhanced.notes:
        lines.append("")
        lines.append("**Notes:**")
        for x in enhanced.notes[:7]:
            lines.append(f"• {x}")

    return "\n".join(lines)


# ============================================================
# TEST MEMORY DATA
# ============================================================

memory = MemoryStore()

sample_trades = [
    TradeLogRecord("QQQ", "VWAP reclaim + break and hold", "TRENDING", "A", "CALL", 0.78, 0.76, 0.20, 0.68, 0.87, 0.84, 0.80, True, True, 1, 35.0, 95.0, 2.7, 0.6, 3.4, True),
    TradeLogRecord("QQQ", "VWAP reclaim + break and hold", "TRENDING", "A", "CALL", 0.74, 0.73, 0.25, 0.64, 0.83, 0.81, 0.77, True, True, 1, 35.0, 42.0, 1.2, 0.5, 1.8, True),
    TradeLogRecord("QQQ", "VWAP reclaim + break and hold", "TRENDING", "A", "CALL", 0.72, 0.70, 0.28, 0.62, 0.80, 0.80, 0.71, True, True, 1, 35.0, -20.0, -0.6, 1.1, 1.0, False),
    TradeLogRecord("QQQ", "VWAP reclaim + break and hold", "TRENDING", "A", "CALL", 0.80, 0.79, 0.18, 0.71, 0.90, 0.88, 0.84, True, True, 1, 35.0, 88.0, 2.5, 0.4, 3.2, True),
    TradeLogRecord("QQQ", "VWAP reclaim + break and hold", "TRENDING", "A", "CALL", 0.77, 0.78, 0.22, 0.69, 0.89, 0.85, 0.83, True, True, 1, 35.0, 51.0, 1.45, 0.7, 2.0, True),

    TradeLogRecord("QQQ", "failed bounce lower high rejection", "CHOPPY", "B+", "PUT", 0.65, 0.60, 0.54, 0.48, 0.58, 0.64, 0.62, True, True, 1, 30.0, -38.0, -1.1, 1.4, 0.5, False),
    TradeLogRecord("QQQ", "failed bounce lower high rejection", "CHOPPY", "B+", "PUT", 0.60, 0.57, 0.61, 0.42, 0.51, 0.60, 0.59, True, True, 1, 30.0, -25.0, -0.8, 1.1, 0.3, False),
    TradeLogRecord("QQQ", "failed bounce lower high rejection", "CHOPPY", "B+", "PUT", 0.58, 0.55, 0.70, 0.38, 0.48, 0.57, 0.51, True, True, 1, 30.0, -47.0, -1.5, 1.6, 0.4, False),
    TradeLogRecord("QQQ", "failed bounce lower high rejection", "CHOPPY", "B+", "PUT", 0.63, 0.58, 0.67, 0.40, 0.50, 0.59, 0.56, True, True, 1, 30.0, 12.0, 0.4, 0.8, 1.0, True),
]

for t in sample_trades:
    log_completed_trade(memory, t)

print_memory_summary(memory)


# ============================================================
# TEST CURRENT SIGNAL THROUGH MEMORY BRAIN
# ============================================================

cfg = RiskConfig(account_equity=5000.0)

market = MarketState(
    symbol="QQQ",
    price=621.40,
    vwap=620.95,
    atr_pct=0.0028,
    intraday_volatility_ratio=1.20,
    trend_strength=0.74,
    realized_day_range_pct=0.010,
    oil_change_dollars=1.10,
    oil_trend="stabilizing",
    macro_bias="neutral",
    market_breadth_score=0.66,
    correlation_to_open_positions=0.15,
    time_quality_score=0.84,
    spread_quality_score=0.90,
    liquidity_score=0.92,
)

signal = SignalState(
    direction=TradeDirection.CALL,
    trade_grade=TradeGrade.A,
    ai_confidence=0.79,
    setup_score=0.84,
    entry_quality_score=0.80,
    chasing_score=0.24,
    level_respect_score=0.86,
    vwap_alignment_score=0.88,
    momentum_alignment_score=0.82,
    macro_alignment_score=0.69,
    stop_distance_pct=0.0024,
    target_distance_pct=0.0058,
    has_retest_confirmation=True,
    is_breakout_entry=True,
    is_reversal_entry=False,
    setup_name="VWAP reclaim + break and hold",
)

portfolio = PortfolioState(
    start_of_day_equity=5000.0,
    current_equity=4975.0,
    day_pnl=-10.0,
    peak_equity=5075.0,
    consecutive_losses=0,
    open_positions=[],
    recent_live_win_rate=0.58,
    recent_live_expectancy=0.20,
    model_health_score=0.77,
)

base_brain, enhanced_brain = run_memory_enhanced_brain(
    memory=memory,
    market=market,
    signal=signal,
    portfolio=portfolio,
    cfg=cfg,
    option_premium=1.20,
    option_stop_fraction_of_premium=0.35,
)

print("\n=== BASE BRAIN ===")
print(json.dumps(brain_decision_to_dict(base_brain), indent=2))

print("\n=== ENHANCED MEMORY BRAIN ===")
print(json.dumps({
    "final_status": enhanced_brain.final_status,
    "final_grade": enhanced_brain.final_grade,
    "final_direction": enhanced_brain.final_direction,
    "final_conviction": enhanced_brain.final_conviction,
    "adjusted_ai_confidence": enhanced_brain.adjusted_ai_confidence,
    "adjusted_size_fraction": enhanced_brain.adjusted_size_fraction,
    "memory_policy_reason": enhanced_brain.memory_policy_reason,
    "memory_warnings": enhanced_brain.memory_warnings,
    "should_block_from_memory": enhanced_brain.should_block_from_memory,
    "notes": enhanced_brain.notes,
}, indent=2))

print("\n=== MEMORY BRAIN ALERT ===")
print(format_memory_brain_alert(market, signal, enhanced_brain))

# ============================================================
# NEXT CELL: RISK-FIRST AI BRAIN LAYER
# Put this AFTER the hybrid risk engine cell
# ============================================================

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import json


# ============================================================
# BRAIN OUTPUT
# ============================================================

@dataclass
class AIBrainDecision:
    brain_status: str                    # APPROVED / SMALLER / BLOCKED
    trade_allowed: bool
    final_grade: str
    final_direction: str
    conviction_score: float              # 0 to 100
    capital_preservation_mode: bool
    risk_mode: str                       # NORMAL / DEFENSIVE / LOCKDOWN
    entry_label: str                     # EARLY / GOOD / LATE / CHASING
    size_fraction_of_max: float          # 0.0 to 1.0
    should_alert_discord: bool
    should_execute: bool
    headline: str
    reasoning: List[str]
    warnings: List[str]
    blockers: List[str]


# ============================================================
# HELPERS
# ============================================================

def normalize_0_100(x: float) -> float:
    return round(max(0.0, min(100.0, x * 100.0)), 2)


def classify_entry_timing(chasing_score: float, entry_quality_score: float) -> str:
    if chasing_score >= 0.80:
        return "CHASING"
    if chasing_score >= 0.65:
        return "LATE"
    if entry_quality_score >= 0.78:
        return "GOOD"
    return "EARLY"


def get_risk_mode(
    portfolio: PortfolioState,
    market: MarketState,
    cfg: RiskConfig
) -> str:
    day_loss = pct_day_loss(portfolio.start_of_day_equity, portfolio.day_pnl)
    trailing_dd = pct_drawdown_from_peak(portfolio.current_equity, portfolio.peak_equity)

    if (
        day_loss >= cfg.daily_loss_limit_pct
        or trailing_dd >= cfg.hard_drawdown_stop_pct
        or portfolio.consecutive_losses >= cfg.max_consecutive_losses
    ):
        return "LOCKDOWN"

    if (
        day_loss >= cfg.daily_loss_limit_pct * 0.65
        or trailing_dd >= cfg.soft_drawdown_throttle_pct
        or market.intraday_volatility_ratio >= cfg.high_volatility_threshold
        or portfolio.consecutive_losses >= max(1, cfg.max_consecutive_losses - 1)
    ):
        return "DEFENSIVE"

    return "NORMAL"


def capital_preservation_triggered(
    portfolio: PortfolioState,
    market: MarketState,
    signal: SignalState,
    cfg: RiskConfig
) -> bool:
    day_loss = pct_day_loss(portfolio.start_of_day_equity, portfolio.day_pnl)
    trailing_dd = pct_drawdown_from_peak(portfolio.current_equity, portfolio.peak_equity)

    if day_loss >= cfg.daily_loss_limit_pct * 0.50:
        return True
    if trailing_dd >= cfg.soft_drawdown_throttle_pct:
        return True
    if market.intraday_volatility_ratio >= cfg.high_volatility_threshold:
        return True
    if signal.macro_alignment_score < 0.45:
        return True
    return False


def compute_conviction_score(
    market: MarketState,
    signal: SignalState,
    risk_decision: RiskDecision
) -> float:
    """
    Conviction is not permission.
    It is the quality score of the opportunity AFTER risk framing.
    """

    setup_component = signal.setup_score * 0.20
    entry_component = signal.entry_quality_score * 0.18
    vwap_component = signal.vwap_alignment_score * 0.12
    level_component = signal.level_respect_score * 0.12
    momentum_component = signal.momentum_alignment_score * 0.10
    macro_component = signal.macro_alignment_score * 0.10
    ai_component = signal.ai_confidence * 0.08

    trend_bonus = 0.05 if risk_decision.market_regime == MarketRegime.TRENDING else 0.0
    retest_bonus = 0.03 if signal.has_retest_confirmation else 0.0
    breadth_bonus = market.market_breadth_score * 0.02

    chasing_penalty = signal.chasing_score * 0.12

    raw = (
        setup_component +
        entry_component +
        vwap_component +
        level_component +
        momentum_component +
        macro_component +
        ai_component +
        trend_bonus +
        retest_bonus +
        breadth_bonus -
        chasing_penalty
    )

    return normalize_0_100(max(0.0, min(1.0, raw)))


def choose_final_grade(
    signal: SignalState,
    conviction_score: float,
    risk_decision: RiskDecision
) -> str:
    if not risk_decision.approved:
        return "AVOID"

    if conviction_score >= 85 and signal.trade_grade in {TradeGrade.A_PLUS, TradeGrade.A}:
        return "A+"
    if conviction_score >= 75 and signal.trade_grade in {TradeGrade.A_PLUS, TradeGrade.A}:
        return "A"
    if conviction_score >= 65 and signal.trade_grade in {TradeGrade.A_PLUS, TradeGrade.A, TradeGrade.B_PLUS}:
        return "B+"
    if conviction_score >= 55:
        return "B"
    return "AVOID"


def size_fraction_from_risk_decision(
    risk_decision: RiskDecision,
    cfg: RiskConfig
) -> float:
    hard_max = cfg.account_equity * cfg.max_risk_pct_per_trade
    if hard_max <= 0:
        return 0.0
    frac = risk_decision.adjusted_risk_dollars / hard_max
    return round(max(0.0, min(1.0, frac)), 3)


# ============================================================
# MAIN BRAIN
# ============================================================

def run_risk_first_ai_brain(
    market: MarketState,
    signal: SignalState,
    portfolio: PortfolioState,
    cfg: RiskConfig,
    option_premium: float,
    option_stop_fraction_of_premium: float = 0.35,
) -> AIBrainDecision:

    reasoning: List[str] = []
    warnings: List[str] = []
    blockers: List[str] = []

    # 1) Run the hard risk engine first
    risk_decision = evaluate_trade_risk(
        market=market,
        signal=signal,
        portfolio=portfolio,
        cfg=cfg,
        option_premium=option_premium,
        option_stop_fraction_of_premium=option_stop_fraction_of_premium,
    )

    # 2) Determine higher-level operating mode
    risk_mode = get_risk_mode(portfolio, market, cfg)
    capital_mode = capital_preservation_triggered(portfolio, market, signal, cfg)
    entry_label = classify_entry_timing(signal.chasing_score, signal.entry_quality_score)
    conviction_score = compute_conviction_score(market, signal, risk_decision)
    final_grade = choose_final_grade(signal, conviction_score, risk_decision)
    size_fraction = size_fraction_from_risk_decision(risk_decision, cfg)

    reasoning.append(f"Conviction score = {conviction_score}")
    reasoning.append(f"Risk mode = {risk_mode}")
    reasoning.append(f"Entry timing = {entry_label}")
    reasoning.append(f"Capital preservation mode = {capital_mode}")

    # 3) Additional brain-level overrides
    if risk_mode == "LOCKDOWN":
        blockers.append("Brain override: system is in LOCKDOWN mode.")
    if capital_mode and final_grade in {"B", "AVOID"}:
        blockers.append("Brain override: capital preservation mode rejects lower-quality setups.")
    if entry_label == "CHASING":
        blockers.append("Brain override: entry is classified as CHASING.")
    if signal.macro_alignment_score < 0.35 and signal.trade_grade not in {TradeGrade.A_PLUS, TradeGrade.A}:
        blockers.append("Brain override: hostile macro alignment for non-elite setup.")
    if signal.vwap_alignment_score < 0.35 and signal.is_breakout_entry:
        blockers.append("Brain override: breakout entry without VWAP support.")
    if risk_decision.recommended_contracts <= 0 and risk_decision.status != RiskStatus.BLOCK:
        warnings.append("Risk engine produced no executable size.")

    # 4) Final trade permission
    if risk_decision.status == RiskStatus.BLOCK or blockers:
        brain_status = "BLOCKED"
        trade_allowed = False
        should_alert_discord = False
        should_execute = False
        size_fraction = 0.0
        headline = "TRADE BLOCKED - CAPITAL PROTECTION FIRST"
    elif risk_decision.status == RiskStatus.REDUCE or capital_mode or risk_mode == "DEFENSIVE":
        brain_status = "SMALLER"
        trade_allowed = risk_decision.approved
        should_alert_discord = risk_decision.approved
        should_execute = risk_decision.approved
        headline = "REDUCED-SIZE TRADE ONLY - DEFENSIVE RISK MODE"
    else:
        brain_status = "APPROVED"
        trade_allowed = risk_decision.approved
        should_alert_discord = risk_decision.approved
        should_execute = risk_decision.approved
        headline = "APPROVED - RISK CONDITIONS ACCEPTABLE"

    # 5) Merge explanations
    reasoning.extend(risk_decision.reasons)
    warnings.extend(risk_decision.warnings)
    blockers.extend(risk_decision.blockers)

    # remove duplicates while preserving order
    def dedupe(items):
        seen = set()
        out = []
        for x in items:
            if x not in seen:
                out.append(x)
                seen.add(x)
        return out

    reasoning = dedupe(reasoning)
    warnings = dedupe(warnings)
    blockers = dedupe(blockers)

    return AIBrainDecision(
        brain_status=brain_status,
        trade_allowed=trade_allowed,
        final_grade=final_grade,
        final_direction=signal.direction.value,
        conviction_score=conviction_score,
        capital_preservation_mode=capital_mode,
        risk_mode=risk_mode,
        entry_label=entry_label,
        size_fraction_of_max=size_fraction,
        should_alert_discord=should_alert_discord,
        should_execute=should_execute,
        headline=headline,
        reasoning=reasoning,
        warnings=warnings,
        blockers=blockers,
    )


# ============================================================
# FORMATTERS
# ============================================================

def brain_decision_to_dict(brain: AIBrainDecision) -> dict:
    return {
        "brain_status": brain.brain_status,
        "trade_allowed": brain.trade_allowed,
        "final_grade": brain.final_grade,
        "final_direction": brain.final_direction,
        "conviction_score": brain.conviction_score,
        "capital_preservation_mode": brain.capital_preservation_mode,
        "risk_mode": brain.risk_mode,
        "entry_label": brain.entry_label,
        "size_fraction_of_max": brain.size_fraction_of_max,
        "should_alert_discord": brain.should_alert_discord,
        "should_execute": brain.should_execute,
        "headline": brain.headline,
        "reasoning": brain.reasoning,
        "warnings": brain.warnings,
        "blockers": brain.blockers,
    }


def format_brain_discord_alert(
    market: MarketState,
    signal: SignalState,
    brain: AIBrainDecision
) -> str:
    emoji = {
        "APPROVED": "🟢",
        "SMALLER": "🟡",
        "BLOCKED": "🔴"
    }.get(brain.brain_status, "⚪")

    lines = [
        f"{emoji} **UNBIASED AI BRAIN**",
        f"**Headline:** {brain.headline}",
        f"**Symbol:** {market.symbol}",
        f"**Direction:** {brain.final_direction}",
        f"**Final Grade:** {brain.final_grade}",
        f"**Setup:** {signal.setup_name}",
        f"**Brain Status:** {brain.brain_status}",
        f"**Trade Allowed:** {'YES' if brain.trade_allowed else 'NO'}",
        f"**Risk Mode:** {brain.risk_mode}",
        f"**Capital Preservation:** {'ON' if brain.capital_preservation_mode else 'OFF'}",
        f"**Conviction:** {brain.conviction_score}",
        f"**Entry Label:** {brain.entry_label}",
        f"**Size Fraction of Max:** {brain.size_fraction_of_max}",
        f"**Should Execute:** {'YES' if brain.should_execute else 'NO'}",
    ]

    if brain.reasoning:
        lines.append("")
        lines.append("**Reasoning:**")
        for x in brain.reasoning[:7]:
            lines.append(f"• {x}")

    if brain.warnings:
        lines.append("")
        lines.append("**Warnings:**")
        for x in brain.warnings[:5]:
            lines.append(f"• {x}")

    if brain.blockers:
        lines.append("")
        lines.append("**Blockers:**")
        for x in brain.blockers[:5]:
            lines.append(f"• {x}")

    return "\n".join(lines)


# ============================================================
# TEST CELL OUTPUT
# ============================================================

cfg = RiskConfig(account_equity=5000.0)

market = MarketState(
    symbol="QQQ",
    price=621.40,
    vwap=620.95,
    atr_pct=0.0028,
    intraday_volatility_ratio=1.35,
    trend_strength=0.72,
    realized_day_range_pct=0.010,
    oil_change_dollars=1.85,
    oil_trend="stabilizing",
    macro_bias="neutral",
    market_breadth_score=0.64,
    correlation_to_open_positions=0.20,
    time_quality_score=0.82,
    spread_quality_score=0.88,
    liquidity_score=0.91,
)

signal = SignalState(
    direction=TradeDirection.CALL,
    trade_grade=TradeGrade.A,
    ai_confidence=0.80,
    setup_score=0.84,
    entry_quality_score=0.79,
    chasing_score=0.22,
    level_respect_score=0.86,
    vwap_alignment_score=0.89,
    momentum_alignment_score=0.81,
    macro_alignment_score=0.68,
    stop_distance_pct=0.0025,
    target_distance_pct=0.0060,
    has_retest_confirmation=True,
    is_breakout_entry=True,
    is_reversal_entry=False,
    setup_name="VWAP reclaim + break and hold",
    notes=["QQQ above VWAP", "good structure", "macro not hostile"],
)

portfolio = PortfolioState(
    start_of_day_equity=5000.0,
    current_equity=4965.0,
    day_pnl=-15.0,
    peak_equity=5075.0,
    consecutive_losses=0,
    open_positions=[],
    recent_live_win_rate=0.58,
    recent_live_expectancy=0.22,
    model_health_score=0.76,
)

brain = run_risk_first_ai_brain(
    market=market,
    signal=signal,
    portfolio=portfolio,
    cfg=cfg,
    option_premium=1.20,
    option_stop_fraction_of_premium=0.35,
)

print("=== AI BRAIN DECISION ===")
print(json.dumps(brain_decision_to_dict(brain), indent=2))

print("\n=== AI BRAIN DISCORD ALERT ===")
print(format_brain_discord_alert(market, signal, brain))

# ============================================================
# UNBIASED TRADES - HYBRID AI RISK ENGINE
# One-cell version
# ============================================================

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Dict, Optional, Tuple
import math
import json


# ============================================================
# ENUMS
# ============================================================

class TradeDirection(str, Enum):
    CALL = "CALL"
    PUT = "PUT"
    FLAT = "FLAT"


class TradeGrade(str, Enum):
    A_PLUS = "A+"
    A = "A"
    B_PLUS = "B+"
    B = "B"
    AVOID = "AVOID"


class MarketRegime(str, Enum):
    TRENDING = "TRENDING"
    CHOPPY = "CHOPPY"
    VOLATILE = "VOLATILE"
    NEUTRAL = "NEUTRAL"


class RiskStatus(str, Enum):
    ALLOW = "ALLOW"
    REDUCE = "REDUCE"
    BLOCK = "BLOCK"


# ============================================================
# CONFIG
# ============================================================

@dataclass
class RiskConfig:
    # account / capital
    account_equity: float = 5000.0

    # hard risk caps
    base_risk_pct_per_trade: float = 0.0075          # 0.75%
    max_risk_pct_per_trade: float = 0.0125           # 1.25% hard max
    daily_loss_limit_pct: float = 0.03               # 3.0%
    soft_drawdown_throttle_pct: float = 0.025        # 2.5%
    hard_drawdown_stop_pct: float = 0.05             # 5.0%

    # kill switches
    max_consecutive_losses: int = 3
    cooldown_after_loss_streak: bool = True

    # correlation / exposure
    max_same_direction_index_exposure_pct: float = 0.02
    max_open_positions: int = 2
    max_correlated_positions_same_direction: int = 1

    # regime control
    high_volatility_threshold: float = 1.60
    extreme_volatility_threshold: float = 2.25
    chop_threshold: float = 0.45

    # chasing control
    chasing_penalty_threshold: float = 0.65
    block_if_chasing_for_b_or_worse: bool = True

    # AI size bounds
    max_ai_size_boost: float = 1.25
    max_ai_size_cut: float = 0.50

    # macro penalties
    hostile_macro_size_penalty: float = 0.60
    neutral_macro_size_penalty: float = 0.85

    # stop logic
    min_stop_distance_pct: float = 0.0015
    max_stop_distance_pct: float = 0.0060

    # options assumptions
    slippage_buffer_pct: float = 0.10
    contract_multiplier: int = 100

    # grade sizing
    grade_size_map: Dict[str, float] = field(default_factory=lambda: {
        "A+": 1.00,
        "A": 0.85,
        "B+": 0.65,
        "B": 0.45,
        "AVOID": 0.00,
    })


# ============================================================
# INPUT MODELS
# ============================================================

@dataclass
class MarketState:
    symbol: str
    price: float
    vwap: float
    atr_pct: float
    intraday_volatility_ratio: float
    trend_strength: float
    realized_day_range_pct: float

    # macro / context
    oil_change_dollars: float = 0.0
    oil_trend: str = "neutral"                     # rising / falling / stabilizing / neutral
    macro_bias: str = "neutral"                    # bullish / bearish / neutral / hostile
    market_breadth_score: float = 0.5             # 0 to 1
    correlation_to_open_positions: float = 0.0    # 0 to 1
    time_quality_score: float = 0.5               # 0 to 1
    spread_quality_score: float = 0.7             # 0 to 1
    liquidity_score: float = 0.8                  # 0 to 1


@dataclass
class SignalState:
    direction: TradeDirection
    trade_grade: TradeGrade
    ai_confidence: float
    setup_score: float
    entry_quality_score: float
    chasing_score: float
    level_respect_score: float
    vwap_alignment_score: float
    momentum_alignment_score: float
    macro_alignment_score: float
    stop_distance_pct: float
    target_distance_pct: float

    # setup tags
    has_retest_confirmation: bool = False
    is_breakout_entry: bool = False
    is_reversal_entry: bool = False

    # your style / setup labels
    setup_name: str = "unknown"
    notes: List[str] = field(default_factory=list)


@dataclass
class Position:
    symbol: str
    direction: TradeDirection
    open_risk_dollars: float
    is_index_exposure: bool = True


@dataclass
class PortfolioState:
    start_of_day_equity: float
    current_equity: float
    day_pnl: float
    peak_equity: float
    consecutive_losses: int
    open_positions: List[Position] = field(default_factory=list)

    # live health stats
    recent_live_win_rate: float = 0.50
    recent_live_expectancy: float = 0.0
    model_health_score: float = 0.70


# ============================================================
# OUTPUT MODELS
# ============================================================

@dataclass
class RiskDecision:
    status: RiskStatus
    approved: bool
    direction: TradeDirection
    grade: TradeGrade
    market_regime: MarketRegime
    base_risk_dollars: float
    adjusted_risk_dollars: float
    recommended_contracts: int
    size_multiplier: float
    reasons: List[str]
    warnings: List[str]
    blockers: List[str]


# ============================================================
# HELPERS
# ============================================================

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def pct_drawdown_from_peak(current_equity: float, peak_equity: float) -> float:
    if peak_equity <= 0:
        return 0.0
    return max(0.0, (peak_equity - current_equity) / peak_equity)


def pct_day_loss(start_of_day_equity: float, day_pnl: float) -> float:
    if start_of_day_equity <= 0:
        return 0.0
    return max(0.0, -day_pnl / start_of_day_equity)


def detect_regime(market: MarketState, cfg: RiskConfig) -> MarketRegime:
    if market.intraday_volatility_ratio >= cfg.extreme_volatility_threshold:
        return MarketRegime.VOLATILE
    if market.trend_strength < cfg.chop_threshold:
        return MarketRegime.CHOPPY
    if market.intraday_volatility_ratio >= cfg.high_volatility_threshold:
        return MarketRegime.VOLATILE
    if market.trend_strength >= 0.65:
        return MarketRegime.TRENDING
    return MarketRegime.NEUTRAL


def grade_multiplier(grade: TradeGrade, cfg: RiskConfig) -> float:
    return cfg.grade_size_map.get(grade.value, 0.0)


def macro_penalty(signal: SignalState, market: MarketState, cfg: RiskConfig) -> float:
    if signal.macro_alignment_score >= 0.80:
        return 1.00
    if signal.macro_alignment_score >= 0.55:
        return cfg.neutral_macro_size_penalty
    return cfg.hostile_macro_size_penalty


def volatility_penalty(market: MarketState, cfg: RiskConfig) -> float:
    vr = market.intraday_volatility_ratio
    if vr >= cfg.extreme_volatility_threshold:
        return 0.45
    if vr >= cfg.high_volatility_threshold:
        return 0.70
    return 1.00


def regime_penalty(regime: MarketRegime, signal: SignalState) -> float:
    if regime == MarketRegime.CHOPPY:
        return 0.60 if signal.is_reversal_entry else 0.50
    if regime == MarketRegime.VOLATILE:
        return 0.65
    if regime == MarketRegime.NEUTRAL:
        return 0.90
    return 1.00


def drawdown_penalty(portfolio: PortfolioState, cfg: RiskConfig) -> float:
    dd = pct_drawdown_from_peak(portfolio.current_equity, portfolio.peak_equity)
    if dd >= cfg.hard_drawdown_stop_pct:
        return 0.0
    if dd >= cfg.soft_drawdown_throttle_pct:
        span = max(1e-9, cfg.hard_drawdown_stop_pct - cfg.soft_drawdown_throttle_pct)
        progress = (dd - cfg.soft_drawdown_throttle_pct) / span
        return clamp(1.0 - 0.60 * progress, 0.40, 1.0)
    return 1.00


def model_health_penalty(portfolio: PortfolioState) -> float:
    score = (
        0.50 * portfolio.model_health_score +
        0.25 * portfolio.recent_live_win_rate +
        0.25 * clamp((portfolio.recent_live_expectancy + 1.0) / 2.0, 0.0, 1.0)
    )
    if score >= 0.75:
        return 1.00
    if score >= 0.60:
        return 0.85
    if score >= 0.45:
        return 0.65
    return 0.45


def ai_policy_multiplier(signal: SignalState, cfg: RiskConfig) -> float:
    raw = 1.0 + (signal.ai_confidence - 0.5) * 0.60
    quality = 1.0 + ((signal.setup_score + signal.entry_quality_score) / 2.0 - 0.5) * 0.40
    combined = raw * quality
    return clamp(combined, cfg.max_ai_size_cut, cfg.max_ai_size_boost)


def chasing_penalty_or_block(signal: SignalState, cfg: RiskConfig) -> Tuple[float, Optional[str]]:
    if signal.chasing_score < cfg.chasing_penalty_threshold:
        return 1.0, None

    if cfg.block_if_chasing_for_b_or_worse and signal.trade_grade in {TradeGrade.B, TradeGrade.AVOID}:
        return 0.0, "Trade blocked: YOU ARE CHASING and setup quality is too low."

    severity = clamp((signal.chasing_score - cfg.chasing_penalty_threshold) / 0.35, 0.0, 1.0)
    penalty = 1.0 - 0.45 * severity
    return clamp(penalty, 0.50, 1.0), None


def stop_distance_penalty(signal: SignalState, cfg: RiskConfig) -> float:
    d = signal.stop_distance_pct
    if d < cfg.min_stop_distance_pct:
        return 0.75
    if d > cfg.max_stop_distance_pct:
        return 0.60
    return 1.00


def reward_to_risk_penalty(signal: SignalState) -> float:
    if signal.stop_distance_pct <= 0:
        return 0.0
    rr = signal.target_distance_pct / signal.stop_distance_pct
    if rr >= 2.0:
        return 1.00
    if rr >= 1.5:
        return 0.90
    if rr >= 1.2:
        return 0.75
    return 0.50


def correlation_block_or_penalty(
    signal: SignalState,
    market: MarketState,
    portfolio: PortfolioState,
    cfg: RiskConfig
) -> Tuple[float, Optional[str]]:
    if signal.direction == TradeDirection.FLAT:
        return 0.0, "Trade blocked: flat signal."

    same_direction_index_positions = [
        p for p in portfolio.open_positions
        if p.is_index_exposure and p.direction == signal.direction
    ]

    if len(same_direction_index_positions) >= cfg.max_correlated_positions_same_direction:
        return 0.0, "Trade blocked: correlated same-direction SPY/QQQ exposure already exists."

    corr = market.correlation_to_open_positions
    if corr >= 0.90:
        return 0.40, None
    if corr >= 0.75:
        return 0.60, None
    if corr >= 0.55:
        return 0.80, None
    return 1.00, None


def open_risk_same_direction(portfolio: PortfolioState, direction: TradeDirection) -> float:
    return sum(
        p.open_risk_dollars
        for p in portfolio.open_positions
        if p.direction == direction and p.is_index_exposure
    )


def estimate_contract_risk_dollars(
    option_premium: float,
    stop_loss_fraction_of_premium: float,
    cfg: RiskConfig
) -> float:
    return option_premium * stop_loss_fraction_of_premium * cfg.contract_multiplier


# ============================================================
# RISK ENGINE
# ============================================================

def evaluate_trade_risk(
    market: MarketState,
    signal: SignalState,
    portfolio: PortfolioState,
    cfg: RiskConfig,
    option_premium: float,
    option_stop_fraction_of_premium: float = 0.35,
) -> RiskDecision:
    reasons: List[str] = []
    warnings: List[str] = []
    blockers: List[str] = []

    regime = detect_regime(market, cfg)

    # --------------------------------------------------------
    # HARD KILL SWITCHES
    # --------------------------------------------------------
    day_loss = pct_day_loss(portfolio.start_of_day_equity, portfolio.day_pnl)
    trailing_dd = pct_drawdown_from_peak(portfolio.current_equity, portfolio.peak_equity)

    if day_loss >= cfg.daily_loss_limit_pct:
        blockers.append("Daily loss limit reached.")
    if trailing_dd >= cfg.hard_drawdown_stop_pct:
        blockers.append("Hard trailing drawdown stop reached.")
    if portfolio.consecutive_losses >= cfg.max_consecutive_losses and cfg.cooldown_after_loss_streak:
        blockers.append("Consecutive loss kill switch active.")
    if len(portfolio.open_positions) >= cfg.max_open_positions:
        blockers.append("Maximum open positions reached.")
    if market.intraday_volatility_ratio >= cfg.extreme_volatility_threshold and signal.trade_grade not in {TradeGrade.A_PLUS, TradeGrade.A}:
        blockers.append("Extreme volatility: only A+ or A trades allowed.")
    if signal.trade_grade == TradeGrade.AVOID:
        blockers.append("Trade grade is AVOID.")
    if signal.direction == TradeDirection.FLAT:
        blockers.append("Signal direction is FLAT.")

    if blockers:
        return RiskDecision(
            status=RiskStatus.BLOCK,
            approved=False,
            direction=signal.direction,
            grade=signal.trade_grade,
            market_regime=regime,
            base_risk_dollars=0.0,
            adjusted_risk_dollars=0.0,
            recommended_contracts=0,
            size_multiplier=0.0,
            reasons=reasons,
            warnings=warnings,
            blockers=blockers,
        )

    # --------------------------------------------------------
    # BASE RISK
    # --------------------------------------------------------
    base_risk_dollars = cfg.account_equity * cfg.base_risk_pct_per_trade
    hard_max_risk_dollars = cfg.account_equity * cfg.max_risk_pct_per_trade

    reasons.append(f"Base risk = ${base_risk_dollars:.2f}")
    reasons.append(f"Market regime = {regime.value}")

    # --------------------------------------------------------
    # MULTIPLIERS
    # --------------------------------------------------------
    g_mult = grade_multiplier(signal.trade_grade, cfg)
    vol_mult = volatility_penalty(market, cfg)
    reg_mult = regime_penalty(regime, signal)
    macro_mult = macro_penalty(signal, market, cfg)
    dd_mult = drawdown_penalty(portfolio, cfg)
    health_mult = model_health_penalty(portfolio)
    ai_mult = ai_policy_multiplier(signal, cfg)
    stop_mult = stop_distance_penalty(signal, cfg)
    rr_mult = reward_to_risk_penalty(signal)

    chase_mult, chase_block = chasing_penalty_or_block(signal, cfg)
    corr_mult, corr_block = correlation_block_or_penalty(signal, market, portfolio, cfg)

    if chase_block:
        blockers.append(chase_block)
    if corr_block:
        blockers.append(corr_block)

    if blockers:
        return RiskDecision(
            status=RiskStatus.BLOCK,
            approved=False,
            direction=signal.direction,
            grade=signal.trade_grade,
            market_regime=regime,
            base_risk_dollars=round(base_risk_dollars, 2),
            adjusted_risk_dollars=0.0,
            recommended_contracts=0,
            size_multiplier=0.0,
            reasons=reasons,
            warnings=warnings,
            blockers=blockers,
        )

    # --------------------------------------------------------
    # QUALITY BOOSTS
    # --------------------------------------------------------
    confirmation_mult = 1.0

    if signal.has_retest_confirmation:
        confirmation_mult *= 1.08
        reasons.append("Retest confirmation present.")
    if signal.level_respect_score >= 0.80:
        confirmation_mult *= 1.05
        reasons.append("Strong key-level respect.")
    if signal.vwap_alignment_score >= 0.80:
        confirmation_mult *= 1.05
        reasons.append("Strong VWAP alignment.")
    if signal.momentum_alignment_score < 0.45:
        confirmation_mult *= 0.80
        warnings.append("Momentum alignment weak.")

    # --------------------------------------------------------
    # FINAL SIZE MULTIPLIER
    # --------------------------------------------------------
    size_multiplier = (
        g_mult *
        vol_mult *
        reg_mult *
        macro_mult *
        dd_mult *
        health_mult *
        ai_mult *
        stop_mult *
        rr_mult *
        chase_mult *
        corr_mult *
        confirmation_mult
    )

    size_multiplier = clamp(size_multiplier, 0.0, 1.10)
    adjusted_risk_dollars = min(base_risk_dollars * size_multiplier, hard_max_risk_dollars)

    # --------------------------------------------------------
    # SAME-DIRECTION INDEX EXPOSURE CAP
    # --------------------------------------------------------
    currently_open_same_dir = open_risk_same_direction(portfolio, signal.direction)
    max_same_dir_allowed = cfg.account_equity * cfg.max_same_direction_index_exposure_pct
    remaining_same_dir_capacity = max(0.0, max_same_dir_allowed - currently_open_same_dir)

    if remaining_same_dir_capacity <= 0:
        blockers.append("No remaining same-direction index exposure capacity.")
        adjusted_risk_dollars = 0.0
    else:
        adjusted_risk_dollars = min(adjusted_risk_dollars, remaining_same_dir_capacity)

    # --------------------------------------------------------
    # CONTRACT CALCULATION
    # --------------------------------------------------------
    risk_per_contract = estimate_contract_risk_dollars(
        option_premium=option_premium,
        stop_loss_fraction_of_premium=option_stop_fraction_of_premium,
        cfg=cfg
    )

    if risk_per_contract <= 0:
        blockers.append("Invalid option risk estimate.")
        contracts = 0
    else:
        contracts = int(adjusted_risk_dollars // risk_per_contract)

    if contracts <= 0 and adjusted_risk_dollars > 0:
        warnings.append("Risk budget too small for 1 contract at current premium/stop.")
    if contracts <= 0:
        adjusted_risk_dollars = 0.0

    # --------------------------------------------------------
    # FINAL STATUS
    # --------------------------------------------------------
    if blockers:
        status = RiskStatus.BLOCK
        approved = False
    elif adjusted_risk_dollars < base_risk_dollars * 0.60:
        status = RiskStatus.REDUCE
        approved = contracts > 0
    else:
        status = RiskStatus.ALLOW
        approved = contracts > 0

    # --------------------------------------------------------
    # EXPLAINABILITY
    # --------------------------------------------------------
    reasons.append(f"Grade multiplier = {g_mult:.2f}")
    reasons.append(f"Volatility multiplier = {vol_mult:.2f}")
    reasons.append(f"Regime multiplier = {reg_mult:.2f}")
    reasons.append(f"Macro multiplier = {macro_mult:.2f}")
    reasons.append(f"Drawdown multiplier = {dd_mult:.2f}")
    reasons.append(f"Model health multiplier = {health_mult:.2f}")
    reasons.append(f"AI policy multiplier = {ai_mult:.2f}")
    reasons.append(f"Stop-distance multiplier = {stop_mult:.2f}")
    reasons.append(f"Reward-to-risk multiplier = {rr_mult:.2f}")
    reasons.append(f"Chasing multiplier = {chase_mult:.2f}")
    reasons.append(f"Correlation multiplier = {corr_mult:.2f}")
    reasons.append(f"Confirmation multiplier = {confirmation_mult:.2f}")
    reasons.append(f"Final size multiplier = {size_multiplier:.2f}")
    reasons.append(f"Risk per contract = ${risk_per_contract:.2f}")

    if trailing_dd >= cfg.soft_drawdown_throttle_pct:
        warnings.append("Drawdown throttle active.")
    if market.intraday_volatility_ratio >= cfg.high_volatility_threshold:
        warnings.append("High volatility regime detected.")
    if market.correlation_to_open_positions >= 0.75:
        warnings.append("High correlation to existing exposure.")
    if signal.chasing_score >= cfg.chasing_penalty_threshold:
        warnings.append("Late-entry / chasing penalty applied.")
    if signal.macro_alignment_score < 0.55:
        warnings.append("Macro alignment weak or hostile.")

    return RiskDecision(
        status=status,
        approved=approved,
        direction=signal.direction,
        grade=signal.trade_grade,
        market_regime=regime,
        base_risk_dollars=round(base_risk_dollars, 2),
        adjusted_risk_dollars=round(adjusted_risk_dollars, 2),
        recommended_contracts=contracts,
        size_multiplier=round(size_multiplier, 3),
        reasons=reasons,
        warnings=warnings,
        blockers=blockers,
    )


# ============================================================
# OPTIONAL REWARD SHAPING
# ============================================================

def risk_aware_reward(
    pnl_r_multiple: float,
    max_adverse_excursion_r: float,
    drawdown_pct: float,
    regime: MarketRegime,
    chasing_score: float,
    correlation_overlap: float,
) -> float:
    reward = pnl_r_multiple
    reward -= 0.35 * max(0.0, max_adverse_excursion_r)
    reward -= 8.0 * max(0.0, drawdown_pct)
    reward -= 0.40 * max(0.0, chasing_score)
    reward -= 0.35 * max(0.0, correlation_overlap)

    if regime == MarketRegime.VOLATILE:
        reward -= 0.20
    elif regime == MarketRegime.CHOPPY:
        reward -= 0.15

    return round(reward, 4)


# ============================================================
# BOT / DISCORD FORMATTERS
# ============================================================

def risk_decision_to_dict(decision: RiskDecision) -> dict:
    return {
        "status": decision.status.value,
        "approved": decision.approved,
        "direction": decision.direction.value,
        "grade": decision.grade.value,
        "market_regime": decision.market_regime.value,
        "base_risk_dollars": decision.base_risk_dollars,
        "adjusted_risk_dollars": decision.adjusted_risk_dollars,
        "recommended_contracts": decision.recommended_contracts,
        "size_multiplier": decision.size_multiplier,
        "reasons": decision.reasons,
        "warnings": decision.warnings,
        "blockers": decision.blockers,
    }


def format_discord_risk_alert(
    market: MarketState,
    signal: SignalState,
    decision: RiskDecision
) -> str:
    emoji = {
        "ALLOW": "🟢",
        "REDUCE": "🟡",
        "BLOCK": "🔴"
    }.get(decision.status.value, "⚪")

    lines = [
        f"{emoji} **HYBRID RISK ENGINE DECISION**",
        f"**Symbol:** {market.symbol}",
        f"**Direction:** {decision.direction.value}",
        f"**Grade:** {decision.grade.value}",
        f"**Setup:** {signal.setup_name}",
        f"**Status:** {decision.status.value}",
        f"**Approved:** {'YES' if decision.approved else 'NO'}",
        f"**Regime:** {decision.market_regime.value}",
        f"**Base Risk:** ${decision.base_risk_dollars}",
        f"**Adjusted Risk:** ${decision.adjusted_risk_dollars}",
        f"**Contracts:** {decision.recommended_contracts}",
        f"**Size Multiplier:** {decision.size_multiplier}",
        f"**AI Confidence:** {signal.ai_confidence:.2f}",
        f"**Chasing Score:** {signal.chasing_score:.2f}",
        f"**Macro Alignment:** {signal.macro_alignment_score:.2f}",
        f"**VWAP Alignment:** {signal.vwap_alignment_score:.2f}",
    ]

    if decision.reasons:
        lines.append("")
        lines.append("**Reasons:**")
        for r in decision.reasons[:6]:
            lines.append(f"• {r}")

    if decision.warnings:
        lines.append("")
        lines.append("**Warnings:**")
        for w in decision.warnings[:4]:
            lines.append(f"• {w}")

    if decision.blockers:
        lines.append("")
        lines.append("**Blockers:**")
        for b in decision.blockers[:4]:
            lines.append(f"• {b}")

    return "\n".join(lines)


# ============================================================
# SIMPLE WRAPPER FOR YOUR AI SYSTEM
# ============================================================

def make_hybrid_risk_decision(
    *,
    symbol: str,
    price: float,
    vwap: float,
    atr_pct: float,
    intraday_volatility_ratio: float,
    trend_strength: float,
    realized_day_range_pct: float,
    oil_change_dollars: float,
    oil_trend: str,
    macro_bias: str,
    market_breadth_score: float,
    correlation_to_open_positions: float,
    time_quality_score: float,
    spread_quality_score: float,
    liquidity_score: float,
    direction: str,
    trade_grade: str,
    ai_confidence: float,
    setup_score: float,
    entry_quality_score: float,
    chasing_score: float,
    level_respect_score: float,
    vwap_alignment_score: float,
    momentum_alignment_score: float,
    macro_alignment_score: float,
    stop_distance_pct: float,
    target_distance_pct: float,
    has_retest_confirmation: bool,
    is_breakout_entry: bool,
    is_reversal_entry: bool,
    setup_name: str,
    option_premium: float,
    option_stop_fraction_of_premium: float,
    start_of_day_equity: float,
    current_equity: float,
    day_pnl: float,
    peak_equity: float,
    consecutive_losses: int,
    recent_live_win_rate: float = 0.50,
    recent_live_expectancy: float = 0.0,
    model_health_score: float = 0.70,
    open_positions: Optional[List[Position]] = None,
    account_equity: float = 5000.0,
) -> RiskDecision:

    cfg = RiskConfig(account_equity=account_equity)

    market = MarketState(
        symbol=symbol,
        price=price,
        vwap=vwap,
        atr_pct=atr_pct,
        intraday_volatility_ratio=intraday_volatility_ratio,
        trend_strength=trend_strength,
        realized_day_range_pct=realized_day_range_pct,
        oil_change_dollars=oil_change_dollars,
        oil_trend=oil_trend,
        macro_bias=macro_bias,
        market_breadth_score=market_breadth_score,
        correlation_to_open_positions=correlation_to_open_positions,
        time_quality_score=time_quality_score,
        spread_quality_score=spread_quality_score,
        liquidity_score=liquidity_score,
    )

    direction_enum = TradeDirection(direction)
    grade_enum = {
        "A+": TradeGrade.A_PLUS,
        "A": TradeGrade.A,
        "B+": TradeGrade.B_PLUS,
        "B": TradeGrade.B,
        "AVOID": TradeGrade.AVOID,
    }[trade_grade]

    signal = SignalState(
        direction=direction_enum,
        trade_grade=grade_enum,
        ai_confidence=ai_confidence,
        setup_score=setup_score,
        entry_quality_score=entry_quality_score,
        chasing_score=chasing_score,
        level_respect_score=level_respect_score,
        vwap_alignment_score=vwap_alignment_score,
        momentum_alignment_score=momentum_alignment_score,
        macro_alignment_score=macro_alignment_score,
        stop_distance_pct=stop_distance_pct,
        target_distance_pct=target_distance_pct,
        has_retest_confirmation=has_retest_confirmation,
        is_breakout_entry=is_breakout_entry,
        is_reversal_entry=is_reversal_entry,
        setup_name=setup_name,
    )

    portfolio = PortfolioState(
        start_of_day_equity=start_of_day_equity,
        current_equity=current_equity,
        day_pnl=day_pnl,
        peak_equity=peak_equity,
        consecutive_losses=consecutive_losses,
        open_positions=open_positions or [],
        recent_live_win_rate=recent_live_win_rate,
        recent_live_expectancy=recent_live_expectancy,
        model_health_score=model_health_score,
    )

    return evaluate_trade_risk(
        market=market,
        signal=signal,
        portfolio=portfolio,
        cfg=cfg,
        option_premium=option_premium,
        option_stop_fraction_of_premium=option_stop_fraction_of_premium,
    )


# ============================================================
# EXAMPLE TEST
# ============================================================

if __name__ == "__main__":
    # Example: no current open positions
    open_positions = []

    decision = make_hybrid_risk_decision(
        symbol="QQQ",
        price=621.40,
        vwap=620.95,
        atr_pct=0.0028,
        intraday_volatility_ratio=1.35,
        trend_strength=0.72,
        realized_day_range_pct=0.010,
        oil_change_dollars=1.85,
        oil_trend="stabilizing",
        macro_bias="neutral",
        market_breadth_score=0.64,
        correlation_to_open_positions=0.25,
        time_quality_score=0.82,
        spread_quality_score=0.88,
        liquidity_score=0.91,

        direction="CALL",
        trade_grade="A",
        ai_confidence=0.78,
        setup_score=0.82,
        entry_quality_score=0.76,
        chasing_score=0.28,
        level_respect_score=0.84,
        vwap_alignment_score=0.87,
        momentum_alignment_score=0.80,
        macro_alignment_score=0.67,
        stop_distance_pct=0.0025,
        target_distance_pct=0.0058,
        has_retest_confirmation=True,
        is_breakout_entry=True,
        is_reversal_entry=False,
        setup_name="VWAP reclaim + break and hold",

        option_premium=1.20,
        option_stop_fraction_of_premium=0.35,

        start_of_day_equity=5000.0,
        current_equity=4940.0,
        day_pnl=-35.0,
        peak_equity=5075.0,
        consecutive_losses=1,
        recent_live_win_rate=0.56,
        recent_live_expectancy=0.18,
        model_health_score=0.74,
        open_positions=open_positions,
        account_equity=5000.0,
    )

    print("\n=== DECISION OBJECT ===")
    print(json.dumps(risk_decision_to_dict(decision), indent=2))

    # Example Discord output
    market_for_alert = MarketState(
        symbol="QQQ",
        price=621.40,
        vwap=620.95,
        atr_pct=0.0028,
        intraday_volatility_ratio=1.35,
        trend_strength=0.72,
        realized_day_range_pct=0.010,
        oil_change_dollars=1.85,
        oil_trend="stabilizing",
        macro_bias="neutral",
        market_breadth_score=0.64,
        correlation_to_open_positions=0.25,
        time_quality_score=0.82,
        spread_quality_score=0.88,
        liquidity_score=0.91,
    )

    signal_for_alert = SignalState(
        direction=TradeDirection.CALL,
        trade_grade=TradeGrade.A,
        ai_confidence=0.78,
        setup_score=0.82,
        entry_quality_score=0.76,
        chasing_score=0.28,
        level_respect_score=0.84,
        vwap_alignment_score=0.87,
        momentum_alignment_score=0.80,
        macro_alignment_score=0.67,
        stop_distance_pct=0.0025,
        target_distance_pct=0.0058,
        has_retest_confirmation=True,
        is_breakout_entry=True,
        is_reversal_entry=False,
        setup_name="VWAP reclaim + break and hold",
    )

    print("\n=== DISCORD ALERT ===")
    print(format_discord_risk_alert(market_for_alert, signal_for_alert, decision))

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Tuple
import math


# ============================================================
# ENUMS
# ============================================================

class TradeDirection(str, Enum):
    CALL = "CALL"
    PUT = "PUT"
    FLAT = "FLAT"


class TradeGrade(str, Enum):
    A_PLUS = "A+"
    A = "A"
    B_PLUS = "B+"
    B = "B"
    AVOID = "AVOID"


class MarketRegime(str, Enum):
    TRENDING = "TRENDING"
    CHOPPY = "CHOPPY"
    VOLATILE = "VOLATILE"
    NEUTRAL = "NEUTRAL"


class RiskStatus(str, Enum):
    ALLOW = "ALLOW"
    REDUCE = "REDUCE"
    BLOCK = "BLOCK"


# ============================================================
# CONFIG
# ============================================================

@dataclass
class RiskConfig:
    # Account / portfolio
    account_equity: float = 5000.0

    # Hard capital risk controls
    max_risk_pct_per_trade: float = 0.0125          # 1.25% hard max
    base_risk_pct_per_trade: float = 0.0075         # 0.75% normal base
    daily_loss_limit_pct: float = 0.03              # 3.0%
    max_trailing_drawdown_pct: float = 0.06         # 6.0%
    soft_drawdown_throttle_pct: float = 0.025       # 2.5%
    hard_drawdown_stop_pct: float = 0.05            # 5.0%

    # Consecutive losses / kill switches
    max_consecutive_losses: int = 3
    cooldown_after_loss_streak: bool = True

    # Correlation / exposure controls
    max_same_direction_index_exposure_pct: float = 0.02   # combined SPY+QQQ risk
    max_open_positions: int = 2
    max_correlated_positions_same_direction: int = 1

    # Volatility / regime controls
    high_volatility_threshold: float = 1.6           # normalized volatility ratio
    extreme_volatility_threshold: float = 2.25
    chop_threshold: float = 0.45                     # trend strength score below this = chop

    # Entry quality controls
    chasing_penalty_threshold: float = 0.65          # normalized late-entry score
    block_if_chasing_above_grade_b: bool = False
    block_if_chasing_for_b_or_worse: bool = True

    # AI policy bounds
    max_ai_size_boost: float = 1.25
    max_ai_size_cut: float = 0.50

    # Trade grade base multipliers
    grade_size_map: Dict[str, float] = field(default_factory=lambda: {
        "A+": 1.00,
        "A": 0.85,
        "B+": 0.65,
        "B": 0.45,
        "AVOID": 0.00,
    })

    # Macro / alignment controls
    require_macro_alignment_for_full_size: bool = True
    hostile_macro_size_penalty: float = 0.60
    neutral_macro_size_penalty: float = 0.85

    # Distance / stop logic
    min_stop_distance_pct: float = 0.0015           # 0.15%
    max_stop_distance_pct: float = 0.0060           # 0.60%

    # Execution assumptions
    slippage_buffer_pct: float = 0.10               # options slippage buffer
    contract_multiplier: int = 100


# ============================================================
# INPUT MODELS
# ============================================================

@dataclass
class MarketState:
    symbol: str
    price: float
    vwap: float
    atr_pct: float                      # ATR / price
    intraday_volatility_ratio: float    # current vol / normal vol
    trend_strength: float               # 0 to 1
    realized_day_range_pct: float
    oil_change_dollars: float = 0.0
    macro_bias: str = "neutral"         # bullish / bearish / neutral / hostile
    market_breadth_score: float = 0.5   # 0 to 1
    correlation_to_open_positions: float = 0.0  # 0 to 1
    time_quality_score: float = 0.5     # 0 to 1, higher = better timing window
    spread_quality_score: float = 0.7   # 0 to 1
    liquidity_score: float = 0.8        # 0 to 1


@dataclass
class SignalState:
    direction: TradeDirection
    trade_grade: TradeGrade
    ai_confidence: float                # 0 to 1
    setup_score: float                  # 0 to 1
    entry_quality_score: float          # 0 to 1
    chasing_score: float                # 0 to 1, higher = more chasing
    level_respect_score: float          # 0 to 1
    vwap_alignment_score: float         # 0 to 1
    momentum_alignment_score: float     # 0 to 1
    macro_alignment_score: float        # 0 to 1
    stop_distance_pct: float            # relative stop distance
    target_distance_pct: float          # relative target distance
    has_retest_confirmation: bool = False
    is_breakout_entry: bool = False
    is_reversal_entry: bool = False
    notes: List[str] = field(default_factory=list)


@dataclass
class Position:
    symbol: str
    direction: TradeDirection
    open_risk_dollars: float
    is_index_exposure: bool = True


@dataclass
class PortfolioState:
    start_of_day_equity: float
    current_equity: float
    day_pnl: float
    peak_equity: float
    consecutive_losses: int
    open_positions: List[Position] = field(default_factory=list)
    recent_live_win_rate: float = 0.5
    recent_live_expectancy: float = 0.0
    model_health_score: float = 0.7     # 0 to 1


# ============================================================
# OUTPUT MODELS
# ============================================================

@dataclass
class RiskDecision:
    status: RiskStatus
    approved: bool
    direction: TradeDirection
    grade: TradeGrade
    market_regime: MarketRegime
    base_risk_dollars: float
    adjusted_risk_dollars: float
    recommended_contracts: int
    size_multiplier: float
    reasons: List[str]
    warnings: List[str]
    blockers: List[str]


# ============================================================
# HELPERS
# ============================================================

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def pct_drawdown_from_peak(current_equity: float, peak_equity: float) -> float:
    if peak_equity <= 0:
        return 0.0
    return max(0.0, (peak_equity - current_equity) / peak_equity)


def pct_day_loss(start_of_day_equity: float, day_pnl: float) -> float:
    if start_of_day_equity <= 0:
        return 0.0
    return max(0.0, -day_pnl / start_of_day_equity)


def detect_regime(market: MarketState, cfg: RiskConfig) -> MarketRegime:
    if market.intraday_volatility_ratio >= cfg.extreme_volatility_threshold:
        return MarketRegime.VOLATILE
    if market.trend_strength < cfg.chop_threshold:
        return MarketRegime.CHOPPY
    if market.intraday_volatility_ratio >= cfg.high_volatility_threshold:
        return MarketRegime.VOLATILE
    if market.trend_strength >= 0.65:
        return MarketRegime.TRENDING
    return MarketRegime.NEUTRAL


def grade_multiplier(grade: TradeGrade, cfg: RiskConfig) -> float:
    return cfg.grade_size_map.get(grade.value, 0.0)


def macro_penalty(signal: SignalState, market: MarketState, cfg: RiskConfig) -> float:
    # signal.macro_alignment_score is primary. market.macro_bias is contextual.
    if signal.macro_alignment_score >= 0.80:
        return 1.00
    if signal.macro_alignment_score >= 0.55:
        return cfg.neutral_macro_size_penalty
    return cfg.hostile_macro_size_penalty


def volatility_penalty(market: MarketState, cfg: RiskConfig) -> float:
    vr = market.intraday_volatility_ratio
    if vr >= cfg.extreme_volatility_threshold:
        return 0.45
    if vr >= cfg.high_volatility_threshold:
        return 0.70
    return 1.00


def regime_penalty(regime: MarketRegime, signal: SignalState) -> float:
    if regime == MarketRegime.CHOPPY:
        # Reversal signals can work in chop, but size stays smaller.
        return 0.60 if signal.is_reversal_entry else 0.50
    if regime == MarketRegime.VOLATILE:
        return 0.65
    if regime == MarketRegime.NEUTRAL:
        return 0.90
    return 1.00


def drawdown_penalty(portfolio: PortfolioState, cfg: RiskConfig) -> float:
    dd = pct_drawdown_from_peak(portfolio.current_equity, portfolio.peak_equity)
    if dd >= cfg.hard_drawdown_stop_pct:
        return 0.0
    if dd >= cfg.soft_drawdown_throttle_pct:
        # linear throttle from soft DD to hard stop
        span = max(1e-9, cfg.hard_drawdown_stop_pct - cfg.soft_drawdown_throttle_pct)
        progress = (dd - cfg.soft_drawdown_throttle_pct) / span
        return clamp(1.0 - 0.60 * progress, 0.40, 1.0)
    return 1.00


def model_health_penalty(portfolio: PortfolioState) -> float:
    # Reduce risk if live performance is degrading
    score = (
        0.50 * portfolio.model_health_score +
        0.25 * portfolio.recent_live_win_rate +
        0.25 * clamp((portfolio.recent_live_expectancy + 1.0) / 2.0, 0.0, 1.0)
    )
    if score >= 0.75:
        return 1.00
    if score >= 0.60:
        return 0.85
    if score >= 0.45:
        return 0.65
    return 0.45


def ai_policy_multiplier(signal: SignalState, cfg: RiskConfig) -> float:
    """
    Bounded adaptive policy layer.
    This acts like a safe RL-style size adjustment without allowing the AI
    to violate hard risk limits.
    """
    # confidence centered around 0.5
    raw = 1.0 + (signal.ai_confidence - 0.5) * 0.60
    # entry/setup quality can nudge the size
    quality = 1.0 + ((signal.setup_score + signal.entry_quality_score) / 2.0 - 0.5) * 0.40
    combined = raw * quality
    return clamp(combined, cfg.max_ai_size_cut, cfg.max_ai_size_boost)


def chasing_penalty_or_block(signal: SignalState, cfg: RiskConfig) -> Tuple[float, Optional[str]]:
    if signal.chasing_score < cfg.chasing_penalty_threshold:
        return 1.0, None

    if cfg.block_if_chasing_for_b_or_worse and signal.trade_grade in {TradeGrade.B, TradeGrade.AVOID}:
        return 0.0, "Trade blocked: entry is chasing and setup quality is too low."
    if cfg.block_if_chasing_above_grade_b:
        return 0.0, "Trade blocked: chasing condition exceeded allowed threshold."

    # Otherwise reduce size materially
    severity = clamp((signal.chasing_score - cfg.chasing_penalty_threshold) / 0.35, 0.0, 1.0)
    penalty = 1.0 - 0.45 * severity
    return clamp(penalty, 0.50, 1.0), None


def stop_distance_penalty(signal: SignalState, cfg: RiskConfig) -> float:
    # Too tight = fragile, too wide = poor R
    d = signal.stop_distance_pct
    if d < cfg.min_stop_distance_pct:
        return 0.75
    if d > cfg.max_stop_distance_pct:
        return 0.60
    return 1.00


def reward_to_risk_penalty(signal: SignalState) -> float:
    if signal.stop_distance_pct <= 0:
        return 0.0
    rr = signal.target_distance_pct / signal.stop_distance_pct
    if rr >= 2.0:
        return 1.00
    if rr >= 1.5:
        return 0.90
    if rr >= 1.2:
        return 0.75
    return 0.50


def correlation_block_or_penalty(
    signal: SignalState,
    market: MarketState,
    portfolio: PortfolioState,
    cfg: RiskConfig
) -> Tuple[float, Optional[str]]:
    if signal.direction == TradeDirection.FLAT:
        return 0.0, "Trade blocked: flat signal."

    same_direction_index_positions = [
        p for p in portfolio.open_positions
        if p.is_index_exposure and p.direction == signal.direction
    ]

    if len(same_direction_index_positions) >= cfg.max_correlated_positions_same_direction:
        return 0.0, "Trade blocked: correlated same-direction index exposure already exists."

    corr = market.correlation_to_open_positions
    if corr >= 0.90:
        return 0.40, None
    if corr >= 0.75:
        return 0.60, None
    if corr >= 0.55:
        return 0.80, None
    return 1.00, None


def open_risk_same_direction(portfolio: PortfolioState, direction: TradeDirection) -> float:
    return sum(
        p.open_risk_dollars
        for p in portfolio.open_positions
        if p.direction == direction and p.is_index_exposure
    )


def estimate_contract_risk_dollars(
    option_premium: float,
    stop_loss_fraction_of_premium: float,
    cfg: RiskConfig
) -> float:
    """
    Example:
    premium = 1.20
    stop_loss_fraction = 0.35 means risking 35% of premium
    risk/contract = 1.20 * 0.35 * 100
    """
    return option_premium * stop_loss_fraction_of_premium * cfg.contract_multiplier


# ============================================================
# CORE ENGINE
# ============================================================

def evaluate_trade_risk(
    market: MarketState,
    signal: SignalState,
    portfolio: PortfolioState,
    cfg: RiskConfig,
    option_premium: float,
    option_stop_fraction_of_premium: float = 0.35,
) -> RiskDecision:
    reasons: List[str] = []
    warnings: List[str] = []
    blockers: List[str] = []

    regime = detect_regime(market, cfg)

    # --------------------------------------------------------
    # 1) HARD KILL SWITCHES
    # --------------------------------------------------------
    day_loss = pct_day_loss(portfolio.start_of_day_equity, portfolio.day_pnl)
    trailing_dd = pct_drawdown_from_peak(portfolio.current_equity, portfolio.peak_equity)

    if day_loss >= cfg.daily_loss_limit_pct:
        blockers.append("Daily loss limit reached.")
    if trailing_dd >= cfg.hard_drawdown_stop_pct:
        blockers.append("Hard trailing drawdown stop reached.")
    if portfolio.consecutive_losses >= cfg.max_consecutive_losses and cfg.cooldown_after_loss_streak:
        blockers.append("Consecutive loss kill switch active.")
    if len(portfolio.open_positions) >= cfg.max_open_positions:
        blockers.append("Maximum open positions reached.")
    if market.intraday_volatility_ratio >= cfg.extreme_volatility_threshold and signal.trade_grade not in {TradeGrade.A_PLUS, TradeGrade.A}:
        blockers.append("Extreme volatility: only top-grade setups allowed.")
    if signal.trade_grade == TradeGrade.AVOID:
        blockers.append("Trade grade is AVOID.")
    if signal.direction == TradeDirection.FLAT:
        blockers.append("Signal direction is FLAT.")

    if blockers:
        return RiskDecision(
            status=RiskStatus.BLOCK,
            approved=False,
            direction=signal.direction,
            grade=signal.trade_grade,
            market_regime=regime,
            base_risk_dollars=0.0,
            adjusted_risk_dollars=0.0,
            recommended_contracts=0,
            size_multiplier=0.0,
            reasons=reasons,
            warnings=warnings,
            blockers=blockers,
        )

    # --------------------------------------------------------
    # 2) BASE RISK
    # --------------------------------------------------------
    base_risk_dollars = cfg.account_equity * cfg.base_risk_pct_per_trade
    hard_max_risk_dollars = cfg.account_equity * cfg.max_risk_pct_per_trade

    reasons.append(f"Base risk set to ${base_risk_dollars:.2f}.")
    reasons.append(f"Detected regime: {regime.value}.")

    # --------------------------------------------------------
    # 3) LAYERED MULTIPLIERS
    # --------------------------------------------------------
    g_mult = grade_multiplier(signal.trade_grade, cfg)
    vol_mult = volatility_penalty(market, cfg)
    reg_mult = regime_penalty(regime, signal)
    macro_mult = macro_penalty(signal, market, cfg)
    dd_mult = drawdown_penalty(portfolio, cfg)
    health_mult = model_health_penalty(portfolio)
    ai_mult = ai_policy_multiplier(signal, cfg)
    stop_mult = stop_distance_penalty(signal, cfg)
    rr_mult = reward_to_risk_penalty(signal)

    chase_mult, chase_block = chasing_penalty_or_block(signal, cfg)
    corr_mult, corr_block = correlation_block_or_penalty(signal, market, portfolio, cfg)

    if chase_block:
        blockers.append(chase_block)
    if corr_block:
        blockers.append(corr_block)

    if blockers:
        return RiskDecision(
            status=RiskStatus.BLOCK,
            approved=False,
            direction=signal.direction,
            grade=signal.trade_grade,
            market_regime=regime,
            base_risk_dollars=base_risk_dollars,
            adjusted_risk_dollars=0.0,
            recommended_contracts=0,
            size_multiplier=0.0,
            reasons=reasons,
            warnings=warnings,
            blockers=blockers,
        )

    # --------------------------------------------------------
    # 4) QUALITY BOOST / PENALTY
    # --------------------------------------------------------
    confirmation_mult = 1.0
    if signal.has_retest_confirmation:
        confirmation_mult *= 1.08
        reasons.append("Retest confirmation present.")
    if signal.level_respect_score >= 0.80:
        confirmation_mult *= 1.05
        reasons.append("Strong key-level respect.")
    if signal.vwap_alignment_score >= 0.80:
        confirmation_mult *= 1.05
        reasons.append("VWAP alignment strong.")
    if signal.momentum_alignment_score < 0.45:
        confirmation_mult *= 0.80
        warnings.append("Momentum alignment is weak.")

    # --------------------------------------------------------
    # 5) COMBINED SIZE MULTIPLIER
    # --------------------------------------------------------
    size_multiplier = (
        g_mult *
        vol_mult *
        reg_mult *
        macro_mult *
        dd_mult *
        health_mult *
        ai_mult *
        stop_mult *
        rr_mult *
        chase_mult *
        corr_mult *
        confirmation_mult
    )

    # Clamp final size
    size_multiplier = clamp(size_multiplier, 0.0, 1.10)

    adjusted_risk_dollars = min(base_risk_dollars * size_multiplier, hard_max_risk_dollars)

    # --------------------------------------------------------
    # 6) SAME-DIRECTION INDEX EXPOSURE CAP
    # --------------------------------------------------------
    currently_open_same_dir = open_risk_same_direction(portfolio, signal.direction)
    max_same_dir_allowed = cfg.account_equity * cfg.max_same_direction_index_exposure_pct
    remaining_same_dir_capacity = max(0.0, max_same_dir_allowed - currently_open_same_dir)

    if remaining_same_dir_capacity <= 0:
        blockers.append("No remaining same-direction index exposure capacity.")
        adjusted_risk_dollars = 0.0
    else:
        adjusted_risk_dollars = min(adjusted_risk_dollars, remaining_same_dir_capacity)

    # --------------------------------------------------------
    # 7) CONTRACT CALCULATION
    # --------------------------------------------------------
    risk_per_contract = estimate_contract_risk_dollars(
        option_premium=option_premium,
        stop_loss_fraction_of_premium=option_stop_fraction_of_premium,
        cfg=cfg
    )

    if risk_per_contract <= 0:
        blockers.append("Invalid option risk estimate.")
        contracts = 0
    else:
        contracts = int(adjusted_risk_dollars // risk_per_contract)

    if contracts <= 0 and adjusted_risk_dollars > 0:
        warnings.append("Risk budget too small for even 1 contract at current premium/stop.")
    if contracts <= 0:
        adjusted_risk_dollars = 0.0

    # --------------------------------------------------------
    # 8) APPROVAL STATUS
    # --------------------------------------------------------
    if blockers:
        status = RiskStatus.BLOCK
        approved = False
    elif adjusted_risk_dollars < base_risk_dollars * 0.60:
        status = RiskStatus.REDUCE
        approved = contracts > 0
    else:
        status = RiskStatus.ALLOW
        approved = contracts > 0

    # --------------------------------------------------------
    # 9) EXPLAINABILITY NOTES
    # --------------------------------------------------------
    reasons.append(f"Grade multiplier: {g_mult:.2f}")
    reasons.append(f"Volatility multiplier: {vol_mult:.2f}")
    reasons.append(f"Regime multiplier: {reg_mult:.2f}")
    reasons.append(f"Macro multiplier: {macro_mult:.2f}")
    reasons.append(f"Drawdown multiplier: {dd_mult:.2f}")
    reasons.append(f"Model health multiplier: {health_mult:.2f}")
    reasons.append(f"AI policy multiplier: {ai_mult:.2f}")
    reasons.append(f"Stop-distance multiplier: {stop_mult:.2f}")
    reasons.append(f"Reward-to-risk multiplier: {rr_mult:.2f}")
    reasons.append(f"Chasing multiplier: {chase_mult:.2f}")
    reasons.append(f"Correlation multiplier: {corr_mult:.2f}")
    reasons.append(f"Final size multiplier: {size_multiplier:.2f}")
    reasons.append(f"Risk per contract estimate: ${risk_per_contract:.2f}")

    if trailing_dd >= cfg.soft_drawdown_throttle_pct:
        warnings.append("Drawdown throttle is active.")
    if market.intraday_volatility_ratio >= cfg.high_volatility_threshold:
        warnings.append("High volatility regime detected.")
    if market.correlation_to_open_positions >= 0.75:
        warnings.append("High correlation to existing exposure.")
    if signal.chasing_score >= cfg.chasing_penalty_threshold:
        warnings.append("Late-entry/chasing penalty applied.")
    if signal.macro_alignment_score < 0.55:
        warnings.append("Macro alignment is weak/hostile.")

    return RiskDecision(
        status=status,
        approved=approved,
        direction=signal.direction,
        grade=signal.trade_grade,
        market_regime=regime,
        base_risk_dollars=round(base_risk_dollars, 2),
        adjusted_risk_dollars=round(adjusted_risk_dollars, 2),
        recommended_contracts=contracts,
        size_multiplier=round(size_multiplier, 3),
        reasons=reasons,
        warnings=warnings,
        blockers=blockers,
    )


# ============================================================
# OPTIONAL: RESEARCH / TRAINING REWARD SHAPING
# ============================================================

def risk_aware_reward(
    pnl_r_multiple: float,
    max_adverse_excursion_r: float,
    drawdown_pct: float,
    regime: MarketRegime,
    chasing_score: float,
    correlation_overlap: float,
) -> float:
    """
    A simple reward function for training / scoring.
    This is NOT a full PPO implementation.
    It is a safe reward-shaping function you can use now.

    Reward philosophy:
    - reward positive pnl
    - penalize drawdown
    - penalize ugly MAE
    - penalize chasing
    - penalize correlated stacking
    - penalize poor performance in volatile/choppy regimes
    """
    reward = pnl_r_multiple

    # punish ugly path risk
    reward -= 0.35 * max(0.0, max_adverse_excursion_r)

    # punish drawdown strongly
    reward -= 8.0 * max(0.0, drawdown_pct)

    # punish chasing
    reward -= 0.40 * max(0.0, chasing_score)

    # punish duplicate/correlated exposure
    reward -= 0.35 * max(0.0, correlation_overlap)

    # regime-sensitive penalty
    if regime == MarketRegime.VOLATILE:
        reward -= 0.20
    elif regime == MarketRegime.CHOPPY:
        reward -= 0.15

    return round(reward, 4)


# ============================================================
# EXAMPLE USAGE
# ============================================================

if __name__ == "__main__":
    cfg = RiskConfig(account_equity=5000)

    market = MarketState(
        symbol="QQQ",
        price=621.40,
        vwap=620.95,
        atr_pct=0.0028,
        intraday_volatility_ratio=1.35,
        trend_strength=0.72,
        realized_day_range_pct=0.010,
        oil_change_dollars=1.85,
        macro_bias="neutral",
        market_breadth_score=0.64,
        correlation_to_open_positions=0.68,
        time_quality_score=0.82,
        spread_quality_score=0.88,
        liquidity_score=0.91,
    )

    signal = SignalState(
        direction=TradeDirection.CALL,
        trade_grade=TradeGrade.A,
        ai_confidence=0.78,
        setup_score=0.82,
        entry_quality_score=0.76,
        chasing_score=0.28,
        level_respect_score=0.84,
        vwap_alignment_score=0.87,
        momentum_alignment_score=0.80,
        macro_alignment_score=0.67,
        stop_distance_pct=0.0025,
        target_distance_pct=0.0058,
        has_retest_confirmation=True,
        is_breakout_entry=True,
        is_reversal_entry=False,
        notes=["VWAP reclaim", "Break-hold above key intraday trigger"],
    )

    portfolio = PortfolioState(
        start_of_day_equity=5000.0,
        current_equity=4940.0,
        day_pnl=-35.0,
        peak_equity=5075.0,
        consecutive_losses=1,
        open_positions=[],
        recent_live_win_rate=0.56,
        recent_live_expectancy=0.18,
        model_health_score=0.74,
    )

    # Example option:
    # premium 1.20, risking 35% of premium to stop
    decision = evaluate_trade_risk(
        market=market,
        signal=signal,
        portfolio=portfolio,
        cfg=cfg,
        option_premium=1.20,
        option_stop_fraction_of_premium=0.35,
    )

    print("\n=== RISK DECISION ===")
    print(f"Status: {decision.status.value}")
    print(f"Approved: {decision.approved}")
    print(f"Direction: {decision.direction.value}")
    print(f"Grade: {decision.grade.value}")
    print(f"Regime: {decision.market_regime.value}")
    print(f"Base Risk: ${decision.base_risk_dollars}")
    print(f"Adjusted Risk: ${decision.adjusted_risk_dollars}")
    print(f"Contracts: {decision.recommended_contracts}")
    print(f"Size Multiplier: {decision.size_multiplier}")

    print("\nReasons:")
    for r in decision.reasons:
        print("-", r)

    print("\nWarnings:")
    for w in decision.warnings:
        print("-", w)

    print("\nBlockers:")
    for b in decision.blockers:
        print("-", b)

print("=== REAL FUNCTION CHECK ===")
print("fetch_time_series =>", "fetch_time_series" in globals())
print("run_full_auto_bot =>", "run_full_auto_bot" in globals())

print("fetch_time_series exists:", "fetch_time_series" in globals())

print("Optional loaded:", "Optional" in globals())

print("=== REAL FUNCTION CHECK ===")

print("fetch_time_series =>", "fetch_time_series" in globals())
print("run_full_auto_bot =>", "run_full_auto_bot" in globals())

print("Running clean test...")
result = run_full_auto_bot()

# =========================
# LIVE BOT RUNNER
# =========================
last_alert_time = None
last_alert_signature = None

def run_full_auto_bot():
    global last_alert_time, last_alert_signature

    df = fetch_time_series(
        symbol=SYMBOL,
        interval=INTERVAL,
        outputsize=OUTPUTSIZE,
        timezone=TIMEZONE
    )

    if df is None or len(df) < 10:
        print("Not enough market data.")
        return None

    context, structure, oil_ctx = build_context_with_levels(
        df=df,
        symbol=SYMBOL,
        level_map=DAILY_LEVELS,
        oil_symbol=OIL_SYMBOL
    )

    decision = make_decision(
        context=context,
        structure=structure,
        candle_time=datetime.now(),
        level_map=DAILY_LEVELS,
        df=df
    )

    message = format_discord_alert(
        decision=decision,
        context=context,
        oil_ctx=oil_ctx,
        level_map=DAILY_LEVELS
    )

    signature = (
        f"{decision.regime}|{decision.setup}|{decision.grade}|"
        f"{decision.charge_label}|{decision.charge_grade}|{round(context.current_price, 2)}"
    )

    now = time_module.time()
    enough_time_passed = (
        last_alert_time is None or
        (now - last_alert_time) >= MIN_ALERT_GAP_SECONDS
    )

    new_signal = signature != last_alert_signature

    print("=" * 60)
    print(message)
    print("=" * 60)

    should_alert = (
        decision.entry_valid and
        (
            decision.grade in ["A+", "A", "B+"] or
            (
                decision.charge_label in ["BULLISH_CHARGE", "BEARISH_CHARGE"]
                and decision.charge_grade in ["A+", "A", "B+"]
            )
        ) and
        enough_time_passed and
        new_signal
    )

    if should_alert:
        if ENABLE_DISCORD_ALERTS:
            send_to_discord(message, WEBHOOK_URL)

        last_alert_time = now
        last_alert_signature = signature
        print("✅ Alert sent")
    else:
        print("⏳ No alert sent")
        print(
            f"SetupGrade={decision.grade} | Charge={decision.charge_label} "
            f"| ChargeGrade={decision.charge_grade} | Entry={decision.entry_valid} "
            f"| NewSignal={new_signal} | CooldownOK={enough_time_passed}"
        )

    return {
        "context": context,
        "structure": structure,
        "oil_ctx": oil_ctx,
        "decision": decision,
        "message": message
    }

print("Running clean test...")
result = run_full_auto_bot()

print("=== FUNCTION CHECK ===")

functions = [
    "fetch_time_series",
    "calculate_vwap",
    "detect_structure",
    "detect_regime",
    "detect_setup",
    "confirm_entry",
    "grade_setup",
    "detect_charge",
    "make_decision"
]

for f in functions:
    print(f, "loaded")

# =========================
# REGIME / SETUP / ENTRY
# =========================
def detect_regime(context: MarketContext, structure: StructureState, ts: datetime) -> Dict[str, Any]:
    bull_score = 0
    bear_score = 0
    notes = []

    if structure.above_vwap:
        bull_score += 2
        notes.append("Price is above VWAP.")
    if structure.below_vwap:
        bear_score += 2
        notes.append("Price is below VWAP.")
    if structure.vwap_reclaimed:
        bull_score += 2
        notes.append("VWAP reclaim detected.")
    if structure.vwap_rejected:
        bear_score += 2
        notes.append("VWAP rejection detected.")

    if structure.higher_lows:
        bull_score += 2
        notes.append("Higher lows support bullish structure.")
    if structure.lower_highs:
        bear_score += 2
        notes.append("Lower highs support bearish structure.")

    if structure.breakout_with_volume:
        bull_score += 1
        notes.append("Breakout with volume supports continuation.")
    if structure.rejection_at_level:
        bear_score += 1
        notes.append("Rejection at level supports downside pressure.")
    if structure.retest_hold:
        bull_score += 1
        notes.append("Retest hold supports bullish continuation.")
    if structure.failed_bounce:
        bear_score += 1
        notes.append("Failed bounce supports bearish continuation.")

    if context.oil_change_dollars >= 2 and context.oil_trend == "rising":
        bear_score += 2
        notes.append("Oil rising sharply adds pressure to the market.")
    elif context.oil_trend == "stabilizing":
        bull_score += 1
        notes.append("Oil stabilizing may allow market relief.")
    elif context.oil_trend == "falling":
        bull_score += 1
        notes.append("Oil falling reduces macro pressure.")

    if context.macro_headline_bias == "bullish":
        bull_score += 1
        notes.append("Macro headline bias is bullish.")
    elif context.macro_headline_bias == "bearish":
        bear_score += 1
        notes.append("Macro headline bias is bearish.")

    if is_priority_window(ts):
        notes.append("Signal occurred during a priority institutional time window.")

    if bull_score >= bear_score + 2:
        regime = "BULL"
        allowed_direction = "CALLS_ONLY"
    elif bear_score >= bull_score + 2:
        regime = "BEAR"
        allowed_direction = "PUTS_ONLY"
    else:
        regime = "CHOP"
        allowed_direction = "SCALPS_OR_AVOID"

    notes.append(f"Bull score: {bull_score}")
    notes.append(f"Bear score: {bear_score}")
    notes.append(f"Regime classified as {regime}.")

    return {
        "regime": regime,
        "allowed_direction": allowed_direction,
        "notes": notes,
        "bull_score": bull_score,
        "bear_score": bear_score,
    }


def detect_setup(regime: str, structure: StructureState) -> Optional[str]:
    if regime == "BULL":
        if structure.vwap_reclaimed and structure.retest_hold:
            return "VWAP_RECLAIM_RETEST_CALL"
        if structure.breakout_with_volume:
            return "BREAK_AND_HOLD_CALL"
        if structure.higher_lows and structure.retest_hold:
            return "HIGHER_LOW_RETEST_CALL"

    if regime == "BEAR":
        if structure.vwap_rejected and structure.rejection_at_level:
            return "VWAP_REJECTION_PUT"
        if structure.failed_bounce and structure.lower_highs:
            return "FAILED_BOUNCE_PUT"
        if structure.rejection_at_level:
            return "LEVEL_REJECTION_PUT"

    return None


def confirm_entry(regime: str, setup: Optional[str], context: MarketContext, structure: StructureState) -> Dict[str, Any]:
    reasons = []
    entry_valid = False
    stop_level = None
    target_level = None

    all_supports = sorted(list(set([
        x for x in [
            context.prior_day_low,
            context.premarket_low,
            *context.key_supports,
            *context.big_print_levels
        ] if x is not None
    ])))

    all_resistances = sorted(list(set([
        x for x in [
            context.prior_day_high,
            context.premarket_high,
            *context.key_resistances,
            *context.big_print_levels
        ] if x is not None
    ])))

    if regime == "BULL" and setup:
        if structure.above_vwap and (structure.retest_hold or structure.breakout_with_volume or structure.vwap_reclaimed):
            entry_valid = True
            reasons.append("Bull regime aligns with bullish setup.")
            reasons.append("Price is holding above VWAP.")
            if structure.retest_hold:
                reasons.append("Retest hold confirms buyers defended the level.")
            if structure.breakout_with_volume:
                reasons.append("Breakout volume confirms participation.")
            if structure.vwap_reclaimed:
                reasons.append("VWAP reclaim confirms momentum shift.")

            stop_level = nearest_support_below(context.current_price, all_supports)
            target_level = nearest_resistance_above(context.current_price, all_resistances)

    elif regime == "BEAR" and setup:
        if structure.below_vwap and (structure.rejection_at_level or structure.failed_bounce or structure.vwap_rejected):
            entry_valid = True
            reasons.append("Bear regime aligns with bearish setup.")
            reasons.append("Price is staying below VWAP.")
            if structure.rejection_at_level:
                reasons.append("Rejection at resistance confirms sellers are active.")
            if structure.failed_bounce:
                reasons.append("Failed bounce confirms weak buyer control.")
            if structure.vwap_rejected:
                reasons.append("VWAP rejection confirms bearish control.")

            stop_level = nearest_resistance_above(context.current_price, all_resistances)
            target_level = nearest_support_below(context.current_price, all_supports)

    else:
        reasons.append("No clean entry because regime and setup are not aligned.")

    if entry_valid and stop_level is None:
        reasons.append("Warning: no clear mapped stop level found.")
    if entry_valid and target_level is None:
        reasons.append("Warning: no clear mapped target level found.")

    return {
        "entry_valid": entry_valid,
        "reasons": reasons,
        "stop_level": stop_level,
        "target_level": target_level,
    }


def confidence_label(regime_data: Dict[str, Any], entry_valid: bool) -> str:
    bull_score = regime_data["bull_score"]
    bear_score = regime_data["bear_score"]
    spread = abs(bull_score - bear_score)

    if not entry_valid:
        return "LOW"
    if spread >= 4:
        return "HIGH"
    if spread >= 2:
        return "MEDIUM"
    return "LOW"

# =========================
# STRUCTURE DETECTION
# =========================
def detect_structure(df: pd.DataFrame) -> StructureState:
    if len(df) < 6:
        return StructureState()

    last = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]
    prev3 = df.iloc[-4]

    higher_lows = (
        prev["low"] > prev2["low"] and
        prev2["low"] >= prev3["low"]
    )

    lower_highs = (
        prev["high"] < prev2["high"] and
        prev2["high"] <= prev3["high"]
    )

    breakout_with_volume = (
        last["close"] > prev["high"] and
        last["volume"] >= prev["volume"]
    )

    rejection_at_level = (
        last["high"] > prev["high"] and
        last["close"] < last["open"]
    )

    failed_bounce = (
        prev2["close"] < prev["close"] and
        last["close"] < prev["low"]
    )

    liquidity_grab_reversal = (
        (last["high"] > prev["high"] and last["close"] < prev["close"]) or
        (last["low"] < prev["low"] and last["close"] > prev["close"])
    )

    retest_hold = (
        prev["low"] <= prev2["high"] and
        last["close"] > prev["close"]
    )

    return StructureState(
        higher_lows=higher_lows,
        lower_highs=lower_highs,
        above_vwap=False,
        below_vwap=False,
        vwap_reclaimed=False,
        vwap_rejected=False,
        breakout_with_volume=breakout_with_volume,
        rejection_at_level=rejection_at_level,
        retest_hold=retest_hold,
        failed_bounce=failed_bounce,
        liquidity_grab_reversal=liquidity_grab_reversal
    )


def build_context_with_levels(df: pd.DataFrame, symbol: str, level_map: Dict[str, Any], oil_symbol: str = "USO"):
    current_price = float(df["close"].iloc[-1])
    vwap = calculate_vwap(df)
    rsi = calculate_rsi(df["close"])

    structure = detect_structure(df)

    prev_close = float(df["close"].iloc[-2]) if len(df) >= 2 else current_price

    structure.above_vwap = current_price > vwap
    structure.below_vwap = current_price < vwap
    structure.vwap_reclaimed = prev_close < vwap and current_price > vwap
    structure.vwap_rejected = prev_close > vwap and current_price < vwap

    oil_ctx = get_oil_context(symbol=oil_symbol)

    context = MarketContext(
        symbol=symbol,
        current_price=current_price,
        vwap=vwap,
        rsi=rsi,
        oil_change_dollars=oil_ctx["oil_change_dollars"],
        oil_trend=oil_ctx["oil_trend"],
        oil_price=oil_ctx["oil_price"],
        macro_headline_bias="neutral",
        big_print_levels=level_map.get("big_print_levels", []),
        prior_day_high=level_map.get("prior_day_high"),
        prior_day_low=level_map.get("prior_day_low"),
        premarket_high=level_map.get("premarket_high"),
        premarket_low=level_map.get("premarket_low"),
        key_supports=level_map.get("key_supports", []),
        key_resistances=level_map.get("key_resistances", [])
    )

    return context, structure, oil_ctx

# =========================
# MARKET DATA
# =========================
def fetch_time_series(symbol: str, interval: str = "1min", outputsize: int = 100, timezone: str = "America/New_York") -> Optional[pd.DataFrame]:
    url = (
        "https://api.twelvedata.com/time_series"
        f"?symbol={symbol}"
        f"&interval={interval}"
        f"&outputsize={outputsize}"
        f"&timezone={timezone}"
        f"&apikey={TWELVE_API_KEY}"
    )

    response = requests.get(url, timeout=20)
    data = response.json()

    if "values" not in data:
        print(f"Error fetching time series for {symbol}: {data}")
        return None

    df = pd.DataFrame(data["values"])

    numeric_cols = ["open", "high", "low", "close"]
    if "volume" in df.columns:
        numeric_cols.append("volume")

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if "volume" not in df.columns:
        df["volume"] = 0.0

    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    return df


def calculate_vwap(df: pd.DataFrame) -> float:
    df = df.copy()
    df["typical_price"] = (df["high"] + df["low"] + df["close"]) / 3.0
    df["tp_volume"] = df["typical_price"] * df["volume"]

    if df["volume"].sum() == 0:
        return float(df["close"].iloc[-1])

    df["cum_tpv"] = df["tp_volume"].cumsum()
    df["cum_vol"] = df["volume"].cumsum()
    return float((df["cum_tpv"] / df["cum_vol"]).iloc[-1])


def calculate_rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.fillna(50)
    return float(rsi.iloc[-1])


def get_oil_context(symbol: str = "USO") -> Dict[str, Any]:
    df = fetch_time_series(symbol=symbol, interval="1min", outputsize=390, timezone=TIMEZONE)
    if df is None or len(df) < 5:
        return {
            "oil_change_dollars": 0.0,
            "oil_trend": "neutral",
            "oil_price": None
        }

    current_price = float(df["close"].iloc[-1])
    session_open = float(df["open"].iloc[0])
    oil_change_dollars = round(current_price - session_open, 2)

    recent_closes = df["close"].tail(5).tolist()

    if oil_change_dollars >= 2 and recent_closes[-1] > recent_closes[0]:
        oil_trend = "rising"
    elif oil_change_dollars <= -2 and recent_closes[-1] < recent_closes[0]:
        oil_trend = "falling"
    elif abs(oil_change_dollars) < 1 and abs(recent_closes[-1] - recent_closes[0]) < 0.35:
        oil_trend = "stabilizing"
    else:
        oil_trend = "neutral"

    return {
        "oil_change_dollars": oil_change_dollars,
        "oil_trend": oil_trend,
        "oil_price": current_price
    }

# =========================
# UTILITY FUNCTIONS
# =========================
def is_priority_window(ts: datetime) -> bool:
    current = ts.time()
    morning_start = time(9, 30)
    morning_end = time(11, 0)
    power_start = time(15, 0)
    power_end = time(16, 15)
    return (morning_start <= current <= morning_end) or (power_start <= current <= power_end)


def flatten_all_levels(level_map: Dict[str, Any]) -> List[float]:
    levels = []

    for key in ["prior_day_high", "prior_day_low", "premarket_high", "premarket_low"]:
        value = level_map.get(key)
        if value is not None:
            levels.append(float(value))

    for lvl in level_map.get("key_supports", []):
        levels.append(float(lvl))

    for lvl in level_map.get("key_resistances", []):
        levels.append(float(lvl))

    for lvl in level_map.get("big_print_levels", []):
        levels.append(float(lvl))

    return sorted(list(set(levels)))


def nearest_level(price: float, levels: List[float]) -> Optional[float]:
    clean_levels = [lvl for lvl in levels if lvl is not None]
    if not clean_levels:
        return None
    return min(clean_levels, key=lambda x: abs(x - price))


def nearest_support_below(price: float, levels: List[float]) -> Optional[float]:
    candidates = [lvl for lvl in levels if lvl is not None and lvl <= price]
    if not candidates:
        return None
    return max(candidates)


def nearest_resistance_above(price: float, levels: List[float]) -> Optional[float]:
    candidates = [lvl for lvl in levels if lvl is not None and lvl >= price]
    if not candidates:
        return None
    return min(candidates)


def is_near_level(price: float, level: Optional[float], threshold: float = 0.25) -> bool:
    if level is None:
        return False
    return abs(price - level) <= threshold


def level_type(level: Optional[float], level_map: Dict[str, Any]) -> str:
    if level is None:
        return "none"
    if level == level_map.get("prior_day_high"):
        return "prior_day_high"
    if level == level_map.get("prior_day_low"):
        return "prior_day_low"
    if level == level_map.get("premarket_high"):
        return "premarket_high"
    if level == level_map.get("premarket_low"):
        return "premarket_low"
    if level in level_map.get("big_print_levels", []):
        return "big_print"
    if level in level_map.get("key_supports", []):
        return "support"
    if level in level_map.get("key_resistances", []):
        return "resistance"
    return "other"


def level_quality_score(level: Optional[float], level_map: Dict[str, Any]) -> int:
    ltype = level_type(level, level_map)
    if ltype == "big_print":
        return 3
    if ltype in ["prior_day_high", "prior_day_low", "premarket_high", "premarket_low"]:
        return 2
    if ltype in ["support", "resistance"]:
        return 1
    return 0


def level_note(level: Optional[float], level_map: Dict[str, Any]) -> str:
    if level is None:
        return ""
    return level_map.get("level_notes", {}).get(level, "")

# =========================
# DATA CLASSES
# =========================
@dataclass
class MarketContext:
    symbol: str
    current_price: float
    vwap: float
    rsi: float
    oil_change_dollars: float = 0.0
    oil_trend: str = "neutral"
    oil_price: Optional[float] = None
    macro_headline_bias: str = "neutral"
    big_print_levels: List[float] = field(default_factory=list)
    prior_day_high: Optional[float] = None
    prior_day_low: Optional[float] = None
    premarket_high: Optional[float] = None
    premarket_low: Optional[float] = None
    key_supports: List[float] = field(default_factory=list)
    key_resistances: List[float] = field(default_factory=list)


@dataclass
class StructureState:
    higher_lows: bool = False
    lower_highs: bool = False
    above_vwap: bool = False
    below_vwap: bool = False
    vwap_reclaimed: bool = False
    vwap_rejected: bool = False
    breakout_with_volume: bool = False
    rejection_at_level: bool = False
    retest_hold: bool = False
    failed_bounce: bool = False
    liquidity_grab_reversal: bool = False


@dataclass
class BotDecision:
    regime: str
    allowed_direction: str
    setup: Optional[str]
    confidence: str
    grade: str
    grade_score: int
    charge_label: str
    charge_grade: str
    charge_score: int
    entry_valid: bool
    stop_level: Optional[float]
    target_level: Optional[float]
    reasoning: List[str]

# =========================
# DAILY LEVELS
# UPDATE THESE EACH MORNING
# =========================
DAILY_LEVELS = {
    "prior_day_high": 614.40,
    "prior_day_low": 608.90,
    "premarket_high": 613.95,
    "premarket_low": 611.80,
    "key_supports": [612.50, 611.80, 610.90],
    "key_resistances": [614.40, 615.20, 616.00],
    "big_print_levels": [613.75, 612.50],
    "level_notes": {
        613.75: "1B print",
        612.50: "major threshold",
        614.40: "PDH",
        611.80: "PM low"
    }
}

from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import datetime, time
import requests
import pandas as pd
import time as time_module
import json

# =========================
# CONFIG
# =========================
TWELVE_API_KEY = "PASTE_YOUR_TWELVE_DATA_API_KEY"
WEBHOOK_URL = "PASTE_YOUR_DISCORD_WEBHOOK"

SYMBOL = "QQQ"          # change to "SPY" when needed
OIL_SYMBOL = "USO"      # oil proxy
INTERVAL = "1min"
OUTPUTSIZE = 100
TIMEZONE = "America/New_York"

ENABLE_DISCORD_ALERTS = False   # keep False while testing
ENABLE_JSON_LOG = True
JSON_LOG_FILE = "trade_analyzer_log.jsonl"

MIN_ALERT_GAP_SECONDS = 120
LEVEL_NEAR_THRESHOLD = 0.25
CHARGE_LEVEL_THRESHOLD = 0.30

TEST_MODE = True  # True = safe testing mode

!pip install requests pandas

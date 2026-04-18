import os
import json
import time
import traceback
from datetime import datetime, timezone

import requests

# =========================================================
# CONFIG
# =========================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

STATE_FILE = "control_state.json"
OFFSET_FILE = "telegram_offset.txt"

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Optional runtime flags
DEBUG_MODE = os.getenv("DEBUG_MODE", "true").strip().lower() == "true"
BOT_NAME = os.getenv("BOT_NAME", "Heartbeat Command Center").strip()

# =========================================================
# DEFAULT STATE
# =========================================================
DEFAULT_STATE = {
    "bot_paused": False,
    "kill_switch": False,
    "flatten_requested": False,
    "armed": True,
    "mode": "paper",  # paper or live
    "last_command": "none",
    "last_command_time_utc": None,
    "last_command_from": None,
    "notes": "initialized"
}

# =========================================================
# FILE HELPERS
# =========================================================
def load_json_file(path, default_value):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        print(f"[WARN] Failed loading JSON file: {path}")
    return default_value.copy() if isinstance(default_value, dict) else default_value

def save_json_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def load_offset():
    try:
        if os.path.exists(OFFSET_FILE):
            with open(OFFSET_FILE, "r", encoding="utf-8") as f:
                return int(f.read().strip())
    except Exception:
        print("[WARN] Failed loading telegram offset")
    return 0

def save_offset(offset_value):
    with open(OFFSET_FILE, "w", encoding="utf-8") as f:
        f.write(str(offset_value))

# =========================================================
# TELEGRAM HELPERS
# =========================================================
def telegram_request(method, payload=None, timeout=30):
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("Missing TELEGRAM_BOT_TOKEN")

    url = f"{TELEGRAM_API_BASE}/{method}"
    response = requests.post(url, json=payload or {}, timeout=timeout)
    response.raise_for_status()
    data = response.json()

    if not data.get("ok", False):
        raise RuntimeError(f"Telegram API error on {method}: {data}")

    return data

def send_telegram_message(text, chat_id=None):
    target_chat_id = chat_id or TELEGRAM_CHAT_ID
    if not target_chat_id:
        print("[WARN] TELEGRAM_CHAT_ID missing, cannot send message")
        return None

    payload = {
        "chat_id": str(target_chat_id),
        "text": text
    }
    return telegram_request("sendMessage", payload=payload)

def get_telegram_updates(offset=0, timeout=10):
    payload = {
        "offset": offset,
        "timeout": timeout,
        "allowed_updates": ["message"]
    }
    return telegram_request("getUpdates", payload=payload, timeout=timeout + 10)

# =========================================================
# CONTROL STATE HELPERS
# =========================================================
def load_state():
    state = load_json_file(STATE_FILE, DEFAULT_STATE)
    for key, value in DEFAULT_STATE.items():
        if key not in state:
            state[key] = value
    return state

def save_state(state):
    save_json_file(STATE_FILE, state)

def utc_now_string():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def pretty_state(state):
    return (
        f"📡 {BOT_NAME}\n"
        f"• Mode: {state.get('mode', 'paper')}\n"
        f"• Armed: {state.get('armed', True)}\n"
        f"• Paused: {state.get('bot_paused', False)}\n"
        f"• Kill Switch: {state.get('kill_switch', False)}\n"
        f"• Flatten Requested: {state.get('flatten_requested', False)}\n"
        f"• Last Command: {state.get('last_command', 'none')}\n"
        f"• Last Command Time: {state.get('last_command_time_utc', 'n/a')}\n"
        f"• Last Command From: {state.get('last_command_from', 'n/a')}\n"
        f"• Notes: {state.get('notes', '')}"
    )

def update_state_command(state, command_name, user_label, note):
    state["last_command"] = command_name
    state["last_command_time_utc"] = utc_now_string()
    state["last_command_from"] = user_label
    state["notes"] = note
    save_state(state)

# =========================================================
# COMMAND PARSER
# =========================================================
def normalize_text(text):
    return (text or "").strip()

def extract_user_label(message):
    chat = message.get("chat", {})
    from_user = message.get("from", {})

    username = from_user.get("username")
    first_name = from_user.get("first_name", "")
    last_name = from_user.get("last_name", "")
    chat_id = str(chat.get("id", ""))

    if username:
        return f"@{username} ({chat_id})"

    full_name = f"{first_name} {last_name}".strip()
    if full_name:
        return f"{full_name} ({chat_id})"

    return f"unknown ({chat_id})"

def is_authorized_chat(message):
    if not TELEGRAM_CHAT_ID:
        return True
    incoming_chat_id = str(message.get("chat", {}).get("id", ""))
    return incoming_chat_id == str(TELEGRAM_CHAT_ID)

def command_menu_text():
    return (
        f"🤖 {BOT_NAME}\n\n"
        "Available commands:\n"
        "/start - Open command center\n"
        "/help - Show commands\n"
        "/status - Current bot state\n"
        "/pause - Pause bot actions\n"
        "/resume - Resume bot actions\n"
        "/kill - Turn ON kill switch\n"
        "/flatten - Request flatten\n"
        "/arm - Allow engine to operate\n"
        "/disarm - Disarm execution engine\n"
        "/mode paper - Set paper mode\n"
        "/mode live - Set live mode\n"
        "/clearflatten - Clear flatten request\n"
        "/unkill - Turn OFF kill switch\n"
        "/debugstate - Dump raw state\n"
        "/ping - Quick connectivity test"
    )

def process_command(text, state, user_label):
    cmd = normalize_text(text)
    cmd_lower = cmd.lower()

    if cmd_lower == "/start":
        update_state_command(state, "/start", user_label, "command center opened")
        return command_menu_text()

    if cmd_lower == "/help":
        update_state_command(state, "/help", user_label, "help requested")
        return command_menu_text()

    if cmd_lower == "/ping":
        update_state_command(state, "/ping", user_label, "ping ok")
        return f"🏓 Pong\n{utc_now_string()}"

    if cmd_lower == "/status":
        update_state_command(state, "/status", user_label, "status checked")
        return pretty_state(state)

    if cmd_lower == "/pause":
        state["bot_paused"] = True
        update_state_command(state, "/pause", user_label, "bot paused")
        return "⏸ Bot paused."

    if cmd_lower == "/resume":
        state["bot_paused"] = False
        update_state_command(state, "/resume", user_label, "bot resumed")
        return "▶️ Bot resumed."

    if cmd_lower == "/kill":
        state["kill_switch"] = True
        update_state_command(state, "/kill", user_label, "kill switch turned ON")
        return "🛑 Kill switch is now ON."

    if cmd_lower == "/unkill":
        state["kill_switch"] = False
        update_state_command(state, "/unkill", user_label, "kill switch turned OFF")
        return "✅ Kill switch is now OFF."

    if cmd_lower == "/flatten":
        state["flatten_requested"] = True
        update_state_command(state, "/flatten", user_label, "flatten requested")
        return "📉 Flatten request has been set to TRUE."

    if cmd_lower == "/clearflatten":
        state["flatten_requested"] = False
        update_state_command(state, "/clearflatten", user_label, "flatten request cleared")
        return "✅ Flatten request cleared."

    if cmd_lower == "/arm":
        state["armed"] = True
        update_state_command(state, "/arm", user_label, "engine armed")
        return "🟢 Engine armed."

    if cmd_lower == "/disarm":
        state["armed"] = False
        update_state_command(state, "/disarm", user_label, "engine disarmed")
        return "🔒 Engine disarmed."

    if cmd_lower == "/mode paper":
        state["mode"] = "paper"
        update_state_command(state, "/mode paper", user_label, "mode set to paper")
        return "🧪 Mode set to PAPER."

    if cmd_lower == "/mode live":
        state["mode"] = "live"
        update_state_command(state, "/mode live", user_label, "mode set to live")
        return "💸 Mode set to LIVE."

    if cmd_lower == "/debugstate":
        update_state_command(state, "/debugstate", user_label, "raw state requested")
        return "```json\n" + json.dumps(state, indent=2) + "\n```"

    update_state_command(state, cmd, user_label, "unknown command received")
    return (
        f"❓ Unknown command: {cmd}\n\n"
        "Use /help to see available commands."
    )

# =========================================================
# MAIN TELEGRAM LOOP
# =========================================================
def process_updates_once():
    state = load_state()
    last_offset = load_offset()

    if DEBUG_MODE:
        print(f"[DEBUG] Starting update check with offset={last_offset}")

    updates_data = get_telegram_updates(offset=last_offset, timeout=5)
    results = updates_data.get("result", [])

    if DEBUG_MODE:
        print(f"[DEBUG] Updates received: {len(results)}")

    if not results:
        return

    for item in results:
        update_id = item.get("update_id")
        message = item.get("message", {})
        text = normalize_text(message.get("text", ""))

        new_offset = update_id + 1
        save_offset(new_offset)

        if DEBUG_MODE:
            print(f"[DEBUG] Processing update_id={update_id} text={text!r}")

        if not message:
            continue

        incoming_chat_id = str(message.get("chat", {}).get("id", ""))
        user_label = extract_user_label(message)

        if not is_authorized_chat(message):
            if DEBUG_MODE:
                print(f"[DEBUG] Unauthorized chat attempted access: {incoming_chat_id}")
            try:
                send_telegram_message(
                    "⛔ This chat is not authorized for command control.",
                    chat_id=incoming_chat_id
                )
            except Exception as e:
                print(f"[WARN] Failed sending unauthorized notice: {e}")
            continue

        if not text.startswith("/"):
            if DEBUG_MODE:
                print(f"[DEBUG] Non-command message ignored from {user_label}")
            try:
                send_telegram_message(
                    f"📝 Received: {text}\n\nSend /help for available commands.",
                    chat_id=incoming_chat_id
                )
            except Exception as e:
                print(f"[WARN] Failed replying to non-command text: {e}")
            continue

        try:
            if DEBUG_MODE:
                send_telegram_message(
                    f"🛠 Debug:\nReceived command: {text}",
                    chat_id=incoming_chat_id
                )

            state = load_state()
            reply = process_command(text, state, user_label)

            if reply.startswith("```json"):
                # Telegram sendMessage doesn't consistently honor code fences without parse mode,
                # so send as normal text.
                reply = "Raw state:\n" + json.dumps(state, indent=2)

            send_telegram_message(reply, chat_id=incoming_chat_id)

            if DEBUG_MODE:
                print(f"[DEBUG] Command processed successfully: {text}")

        except Exception as command_error:
            err_text = (
                f"❌ Command failed: {text}\n"
                f"Error: {str(command_error)}"
            )
            print("[ERROR] Command processing failed")
            print(traceback.format_exc())
            try:
                send_telegram_message(err_text, chat_id=incoming_chat_id)
            except Exception:
                print("[ERROR] Also failed to send Telegram error message")

def startup_message():
    state = load_state()
    return (
        f"🚀 {BOT_NAME} check-in\n"
        f"Time: {utc_now_string()}\n"
        f"Mode: {state.get('mode')}\n"
        f"Armed: {state.get('armed')}\n"
        f"Paused: {state.get('bot_paused')}\n"
        f"Kill: {state.get('kill_switch')}\n"
        f"Flatten: {state.get('flatten_requested')}"
    )

# =========================================================
# ENTRYPOINT
# =========================================================
if __name__ == "__main__":
    try:
        if not TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN is missing.")
        if not TELEGRAM_CHAT_ID:
            print("[WARN] TELEGRAM_CHAT_ID is missing. Authorization filter will be open.")

        # Make sure files exist
        if not os.path.exists(STATE_FILE):
            save_state(DEFAULT_STATE)
        if not os.path.exists(OFFSET_FILE):
            save_offset(0)

        if DEBUG_MODE:
            print("[DEBUG] main.py started")
            print(startup_message())

        process_updates_once()

        if DEBUG_MODE:
            print("[DEBUG] main.py finished cleanly")

    except Exception as e:
        print("[FATAL ERROR]")
        print(str(e))
        print(traceback.format_exc())

        # Try to notify Telegram if possible
        try:
            send_telegram_message(
                f"🚨 Fatal error in {BOT_NAME}\n{str(e)}"
            )
        except Exception:
            print("[FATAL] Failed to send Telegram fatal error alert")

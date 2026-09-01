"""
Find your Telegram chat id and prove the alerting works.

Getting a chat id normally means opening a getUpdates URL and reading raw
JSON, which is a poor first task for anyone who just wants signals on their
phone. This does it for you, then sends a real test message -- so a pass
here means the collector will genuinely reach you, not that the values merely
look plausible.

    .venv\\Scripts\\python.exe telegram_setup.py

Reads TELEGRAM_BOT_TOKEN from apps/api/.env. Never prints the token, and
writes nothing -- it tells you the line to add.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ENV = Path(__file__).resolve().parent / ".env"


def read_env(name: str) -> str | None:
    if not ENV.exists():
        return None
    for line in ENV.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith(f"{name}=") and not line.startswith("#"):
            return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def main() -> None:
    try:
        import httpx
    except ImportError:
        print("httpx is not installed. Run:")
        print("   .venv\\Scripts\\python.exe -m pip install -r requirements.txt")
        sys.exit(1)

    token = read_env("TELEGRAM_BOT_TOKEN")
    if not token:
        print(f"\nTELEGRAM_BOT_TOKEN is not set in {ENV}\n")
        print("Get one in about a minute:")
        print("  1. Open Telegram and message @BotFather")
        print("  2. Send:  /newbot")
        print("  3. Give it a name, then a username ending in 'bot'")
        print("  4. It replies with a token like 8123456789:AAF-xxxxxxxxxxxxx")
        print(f"  5. Add this line to {ENV}:")
        print("        TELEGRAM_BOT_TOKEN=<the token>")
        print("  6. Run this script again\n")
        sys.exit(1)

    api = f"https://api.telegram.org/bot{token}"

    # Retried, and with a longer timeout, because the first symptom of an
    # ISP-level block is a timeout that looks exactly like a slow network.
    # Telling those apart matters: one clears on its own, the other never will.
    me = None
    last_error = None
    for attempt in (1, 2, 3):
        try:
            me = httpx.get(f"{api}/getMe", timeout=30).json()
            break
        except Exception as exc:  # noqa: BLE001
            # The URL carries the token, so report the type only.
            last_error = type(exc).__name__
            if attempt < 3:
                print(f"  attempt {attempt} failed ({last_error}) — retrying...")
                time.sleep(2)

    if me is None:
        print(f"\nCould not reach api.telegram.org after 3 attempts ({last_error}).")
        print("\nThe token was read fine, so this is the network, not the setup.")
        print("\nCheck which it is — open this in a browser:")
        print("    https://api.telegram.org")
        print("\n  * Page loads          -> transient. Just run this script again.")
        print("  * Page never loads    -> Telegram is blocked on this connection.")
        print("                           Several countries block it at the ISP.")
        print("\nIf it is blocked, alerting needs a channel that is not:")
        print("  * a VPN while the collector runs (simplest, but it must stay on)")
        print("  * a Discord webhook — usually reachable where Telegram is not")
        print("  * email, or a desktop notification on this machine")
        print("\nNothing else is affected: signals are still recorded and shown")
        print("in the dashboard. Only the push notification needs another route.\n")
        sys.exit(1)

    if not me.get("ok"):
        print("\nTelegram rejected that token. Check TELEGRAM_BOT_TOKEN in .env —")
        print("it should look like 8123456789:AAF-xxxxxxxxxxxxx, with no spaces.\n")
        sys.exit(1)

    bot = me["result"]["username"]
    print(f"\nToken is valid. Bot: @{bot}")

    updates = httpx.get(f"{api}/getUpdates", timeout=15).json()
    chats: dict[int, str] = {}
    for update in updates.get("result", []):
        message = update.get("message") or update.get("channel_post") or {}
        chat = message.get("chat") or {}
        if chat.get("id") is not None:
            name = chat.get("first_name") or chat.get("title") or chat.get("username") or "?"
            chats[chat["id"]] = name

    if not chats:
        print(f"\nNo messages yet — so Telegram has no chat to point at.")
        print(f"\n  Open Telegram, search for  @{bot},  and send it any message.")
        print("  (A bot cannot message you until you have messaged it first.)")
        print("\nThen run this script again.\n")
        sys.exit(1)

    print("\nFound:")
    for chat_id, name in chats.items():
        print(f"    {chat_id}   ({name})")

    chat_id = next(iter(chats))
    print(f"\nAdd this line to {ENV}:")
    print(f"\n    TELEGRAM_CHAT_ID={chat_id}\n")

    sent = httpx.post(
        f"{api}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": (
                "<b>NorthFXTrade — test message</b>\n\n"
                "Alerting works. New CALL/PUT signals will arrive here.\n\n"
                "<i>NO TRADE cycles and rejected setups never alert, and a "
                "signal that stays open is not re-sent.</i>"
            ),
            "parse_mode": "HTML",
        },
        timeout=15,
    ).json()

    if sent.get("ok"):
        print("Test message sent — check your phone.")
        print("Add the line above, restart the collector, and you are done.\n")
    else:
        print(f"Could not send: {sent.get('description', 'unknown error')}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()

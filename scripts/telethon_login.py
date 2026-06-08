"""One-time interactive login to mint a Telethon StringSession.

Run it yourself (the login code is sent to your Telegram — I can't receive it):

    uv run --extra runtime python scripts/telethon_login.py

Get api_id + api_hash from https://my.telegram.org → API development tools.
It will prompt for your phone number and the login code, then print a SESSION
string. Paste that into .env as TELEGRAM_SESSION (and api_id/api_hash too).
The session is a credential — never commit it.
"""
import sys
import io
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from telethon import TelegramClient
from telethon.sessions import StringSession


def main() -> int:
    api_id = os.environ.get("TELEGRAM_API_ID") or input("api_id: ").strip()
    api_hash = os.environ.get("TELEGRAM_API_HASH") or input("api_hash: ").strip()

    with TelegramClient(StringSession(), int(api_id), api_hash) as client:
        me = client.get_me()
        session = client.session.save()
        print("\n✅ Logged in as:", getattr(me, "username", None) or me.first_name)
        print("\n--- copy the line below into .env ---")
        print(f"TELEGRAM_SESSION={session}")
        print("-------------------------------------")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Convert a Telegram Desktop `tdata` folder into a Telethon StringSession.

Reuses the existing desktop authorization (no phone/code login). Outputs the
session string plus the api_id/api_hash it is bound to — paste all three into .env.

Run:
    uv run --with opentele --with telethon python scripts/tdata_to_session.py <path-to-tdata> [passcode]

The tdata folder and the resulting session are full account credentials — they are
gitignored; never commit them.
"""
import asyncio
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


async def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python scripts/tdata_to_session.py <path-to-tdata> [passcode]")
        return 2
    tdata_path = sys.argv[1]
    passcode = sys.argv[2] if len(sys.argv) > 2 else None

    from opentele.td import TDesktop
    from opentele.api import API, UseCurrentSession
    from telethon.sessions import StringSession

    tdesk = TDesktop(tdata_path, passcode=passcode) if passcode else TDesktop(tdata_path)
    if not tdesk.isLoaded():
        print("❌ tdata not loaded — check the path (and passcode if the desktop has a local passcode).")
        return 1

    api = API.TelegramDesktop.Generate()  # the api_id/api_hash the session binds to
    # opentele's FromTDesktop only binds an auth_session when `session` is a str/None
    # (it builds an in-memory SQLiteSession from it). Passing a StringSession() instance
    # slips through both branches and triggers UnboundLocalError, so pass None and
    # serialize the populated session ourselves via StringSession.save().
    client = await tdesk.ToTelethon(session=None, flag=UseCurrentSession, api=api)
    await client.connect()
    me = await client.get_me()
    session = StringSession.save(client.session)
    await client.disconnect()

    uname = getattr(me, "username", None) or me.first_name
    print(f"\n✅ Logged in as: {uname} (id={me.id})")
    print("\n--- paste these into .env (gitignored — never commit) ---")
    print(f"TELEGRAM_API_ID={api.api_id}")
    print(f"TELEGRAM_API_HASH={api.api_hash}")
    print(f"TELEGRAM_SESSION={session}")
    print("----------------------------------------------------------")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

"""TelethonFetch — account-based (MTProto) channel reader behind the Fetch seam.

Unlike the t.me/s preview client this uses a real Telegram account session, so it
reads full history, media captions, and channels without a web preview (incl.
private/invite-only). Reads TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION
from env. Mint the session once with `scripts/telethon_login.py`.

Pure helpers (message_to_rawpost, filter_recent) are unit-tested; the async client
is imported lazily and exercised at the live run.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

from .models import RawPost

log = logging.getLogger(__name__)


def message_to_rawpost(msg, channel: str) -> RawPost:
    """Map a Telethon Message to a RawPost (pure)."""
    text = getattr(msg, "message", None) or getattr(msg, "text", None) or ""
    return RawPost(
        id=msg.id,
        channel=channel,
        text=text,
        dt=getattr(msg, "date", None),
        permalink=f"https://t.me/{channel}/{msg.id}",
    )


def filter_recent(posts: list[RawPost], since: Optional[datetime]) -> list[RawPost]:
    """Keep posts at or newer than `since` (inclusive). No `since` → all."""
    if since is None:
        return posts
    return [p for p in posts if p.dt is None or p.dt >= since]


class TelethonFetch:
    def __init__(self, api_id: int, api_hash: str, session: str,
                 max_messages: int = 200, client_factory=None):
        self._api_id = api_id
        self._api_hash = api_hash
        self._session = session
        self._max = max_messages
        self._client_factory = client_factory  # injectable for tests

    def _make_client(self):
        if self._client_factory is not None:
            return self._client_factory()
        from telethon import TelegramClient  # lazy
        from telethon.sessions import StringSession
        return TelegramClient(StringSession(self._session), self._api_id, self._api_hash)

    async def _fetch(self, channel: str, since: Optional[datetime]) -> list[RawPost]:
        client = self._make_client()
        posts: list[RawPost] = []
        async with client:
            async for msg in client.iter_messages(channel, limit=self._max):
                p = message_to_rawpost(msg, channel)
                if since is not None and p.dt is not None and p.dt < since:
                    break  # iter_messages is newest-first; stop at the window edge
                posts.append(p)
        return filter_recent(posts, since)

    def fetch_recent(self, channel: str, since: Optional[datetime] = None) -> list[RawPost]:
        try:
            return asyncio.run(self._fetch(channel, since))
        except Exception as exc:  # one bad channel must not abort the whole run
            log.warning("telethon fetch failed for %s (%s); skipping", channel, exc)
            return []


def build_telethon_fetch(env: Optional[dict] = None) -> "TelethonFetch":
    env = env if env is not None else os.environ
    return TelethonFetch(
        api_id=int(env["TELEGRAM_API_ID"]),
        api_hash=env["TELEGRAM_API_HASH"],
        session=env["TELEGRAM_SESSION"],
        max_messages=int(env.get("TELETHON_MAX_MESSAGES", "200")),
    )

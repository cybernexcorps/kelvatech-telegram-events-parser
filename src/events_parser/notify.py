"""TelegramNotifier — delivers the digest via the Telegram Bot API.

Sending uses a plain HTTPS call to the Bot API (no python-telegram-bot needed for
delivery). Long digests are split under Telegram's 4096-char message limit.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

import httpx

log = logging.getLogger(__name__)

TG_LIMIT = 4096
HttpPost = Callable[[str, dict], object]


def split_message(text: str, limit: int = TG_LIMIT) -> list[str]:
    """Split text into chunks <= limit, preferring newline boundaries."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    cur = ""
    for line in text.split("\n"):
        # a single line longer than the limit must be hard-split
        while len(line) > limit:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = line if not cur else f"{cur}\n{line}"
        if len(candidate) > limit:
            chunks.append(cur)
            cur = line
        else:
            cur = candidate
    if cur:
        chunks.append(cur)
    return chunks


def _default_post(url: str, json: dict) -> object:
    resp = httpx.post(url, json=json, timeout=20.0)
    if resp.status_code >= 400:
        # Surface Telegram's own reason ("chat not found", "can't parse entities", ...);
        # raise_for_status() alone hides it behind a bare status code.
        description = ""
        try:
            description = resp.json().get("description", "")
        except Exception:
            description = resp.text
        raise RuntimeError(f"Telegram sendMessage failed: {resp.status_code} {description}")
    return resp.json()


class TelegramNotifier:
    def __init__(self, token: str, http_post: Optional[HttpPost] = None,
                 parse_mode: str = "HTML"):
        self._token = token
        self._post = http_post or _default_post
        self._parse_mode = parse_mode

    def send(self, chat_id: int, text: str) -> None:
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        for chunk in split_message(text):
            self._post(url, {"chat_id": chat_id, "text": chunk,
                             "parse_mode": self._parse_mode,
                             "disable_web_page_preview": True})

"""TelegramNotifier — delivers the digest via the Telegram Bot API.

Sending uses a plain HTTPS call to the Bot API (no python-telegram-bot needed for
delivery). Long digests are split under Telegram's 4096-char message limit.
"""
from __future__ import annotations

import logging
from typing import Callable, Mapping, Optional

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
            payload = {"chat_id": chat_id, "text": chunk,
                       "disable_web_page_preview": True}
            # Omit parse_mode entirely when unset — Telegram 400s on a null
            # parse_mode ("unsupported parse_mode"); plain text needs no mode.
            if self._parse_mode:
                payload["parse_mode"] = self._parse_mode
            self._post(url, payload)


def build_error_alerter(
    env: Mapping[str, str], http_post: Optional[HttpPost] = None
) -> Callable[[str], None]:
    """Return an operator-alert callable that pushes failure messages via the
    dedicated errors bot (@kelva_errors_bot). Issue #4.

    Configured by ``TELEGRAM_ERROR_BOT_TOKEN`` + ``TELEGRAM_ERROR_CHAT_ID``. If
    either is unset the returned callable is a logged no-op, so the feature stays
    dormant until the operator provisions the bot. Alerts are sent as plain text
    (no HTML parse) since error messages contain arbitrary characters.
    """
    token = env.get("TELEGRAM_ERROR_BOT_TOKEN")
    chat = env.get("TELEGRAM_ERROR_CHAT_ID")
    if not token or not chat:
        def _disabled(text: str) -> None:
            log.warning("error alert suppressed (TELEGRAM_ERROR_BOT_TOKEN/CHAT_ID unset): %s", text)
        return _disabled

    notifier = TelegramNotifier(token, http_post=http_post, parse_mode=None)
    chat_id = int(chat)

    def _alert(text: str) -> None:
        notifier.send(chat_id, text)

    return _alert

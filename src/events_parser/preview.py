"""PreviewClient — reads public t.me/s/{channel} HTML previews. No Telegram credentials.

Selectors confirmed against real markup in prototypes/NOTES.md:
  post block  div.tgme_widget_message  (data-post="channel/<id>")
  text        .tgme_widget_message_text
  permalink   a.tgme_widget_message_date[href]
  datetime    a.tgme_widget_message_date time[datetime]   (NOT a bare <time>)
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Optional

import httpx
from selectolax.parser import HTMLParser

from .models import ChannelFetchResult, RawPost

log = logging.getLogger(__name__)

_BASE = "https://t.me/s"
_UA = {"User-Agent": "Mozilla/5.0 (compatible; KelvaEventsParser/0.1)"}

HttpGet = Callable[[str], str]


def build_preview_url(channel: str, before: Optional[int] = None) -> str:
    url = f"{_BASE}/{channel}"
    if before is not None:
        url += f"?before={before}"
    return url


def _default_get(url: str) -> str:
    resp = httpx.get(url, headers=_UA, timeout=20.0, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


def parse_preview(html: str, channel: str) -> list[RawPost]:
    tree = HTMLParser(html)
    posts: list[RawPost] = []
    for w in tree.css("div.tgme_widget_message"):
        data_post = w.attributes.get("data-post")
        if not data_post:
            continue
        try:
            msg_id = int(data_post.rsplit("/", 1)[-1])
        except ValueError:
            continue

        text_node = w.css_first(".tgme_widget_message_text")
        text = text_node.text(separator="\n", strip=True) if text_node else ""

        date_a = w.css_first("a.tgme_widget_message_date")
        permalink = date_a.attributes.get("href") if date_a else None

        dt = None
        time_node = w.css_first("a.tgme_widget_message_date time")
        if time_node:
            raw = time_node.attributes.get("datetime")
            if raw:
                try:
                    dt = datetime.fromisoformat(raw)
                except ValueError:
                    dt = None

        posts.append(RawPost(id=msg_id, channel=channel, text=text, dt=dt, permalink=permalink))
    return posts


class PreviewClient:
    def __init__(self, http_get: Optional[HttpGet] = None):
        self._get = http_get or _default_get

    def fetch_posts(self, channel: str, before: Optional[int] = None) -> list[RawPost]:
        """Fetch and parse one preview page. Raises on network/HTTP failure —
        ``fetch_recent`` owns the skip-on-failure resilience (and reports it)."""
        html = self._get(build_preview_url(channel, before))
        return parse_preview(html, channel)

    def fetch_recent(
        self,
        channel: str,
        since: Optional[datetime] = None,
        max_pages: int = 3,
    ) -> ChannelFetchResult:
        """Paginate backward via ?before= until the scan window is covered.

        Stops when: a page is empty, the cursor stops advancing, max_pages is hit,
        or (when `since` is given) the oldest post on a page predates `since`. A
        fetch failure is captured as a failed ``ChannelFetchResult`` (not raised),
        so one bad channel never aborts the run but is no longer silently empty.
        """
        collected: dict[int, RawPost] = {}
        before: Optional[int] = None
        try:
            for _ in range(max_pages):
                page = self.fetch_posts(channel, before=before)
                if not page:
                    break
                for p in page:
                    collected.setdefault(p.id, p)
                page_min = min(p.id for p in page)
                if before is not None and page_min >= before:
                    break  # cursor did not advance — avoid an infinite loop
                if since is not None and any(p.dt and p.dt < since for p in page):
                    break  # reached posts older than the scan window
                before = page_min
        except Exception as exc:  # network/HTTP/parse failure: report, don't abort the run
            log.warning("preview fetch failed for %s (%s); skipping", channel, exc)
            return ChannelFetchResult.failed(channel, f"{type(exc).__name__}: {exc}")
        posts = sorted(collected.values(), key=lambda p: p.id, reverse=True)
        return ChannelFetchResult.succeeded(channel, posts)

"""run_digest — the top integration seam.

Every external dependency is injected via Deps so the whole pipeline is testable
with fakes (no network, LLM, or Telegram). Flow:

    fetch_recent → extract → tag domain → horizon-filter → dedup → render → deliver
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Protocol

from .config import Config
from .models import ChannelFetchResult, Event, RawPost
from .render import render_digest
from .rules import within_horizon


class Fetch(Protocol):
    def fetch_recent(self, channel: str, since: datetime | None = None) -> ChannelFetchResult: ...


class Extractor(Protocol):
    def extract(self, post: RawPost) -> list[Event]: ...


class SeenStore(Protocol):
    def is_new(self, event_hash: str) -> bool: ...
    def mark_seen(self, event: Event) -> None: ...


class Notifier(Protocol):
    def send(self, chat_id: int, text: str) -> None: ...


@dataclass
class Deps:
    fetch: Fetch
    extractor: Extractor
    seen_store: SeenStore
    notifier: Notifier


@dataclass
class DigestResult:
    digest_text: str
    events: list[Event] = field(default_factory=list)
    sent: bool = False
    # Channels whose fetch errored this run (≠ channels that were merely quiet).
    # Lets the scheduled-run guard alert precisely instead of via the 0-events proxy.
    fetch_failures: list[str] = field(default_factory=list)


def _collect(now: datetime, config: Config, deps: Deps) -> tuple[list[Event], list[str]]:
    """Fetch + extract across all channels; channel domain is authoritative.

    Returns the collected events and the handles whose fetch failed — a failed
    channel is kept distinct from one that simply had no recent posts.
    """
    since = now - timedelta(days=config.scan_days)
    events: list[Event] = []
    failures: list[str] = []
    for handle, domain in config.channels:
        result = deps.fetch.fetch_recent(handle, since)
        if not result.ok:
            failures.append(handle)
            continue
        for post in result.posts:
            for ev in deps.extractor.extract(post):
                if ev.domain != domain:
                    ev = ev.model_copy(update={"domain": domain})
                events.append(ev)
    return events, failures


def finish_digest(
    collected: list[Event], now: datetime, config: Config, deps: Deps,
    fetch_failures: Optional[list[str]] = None,
) -> DigestResult:
    """Shared finish path: horizon-filter → dedup → render → deliver.

    Both the deterministic collector (`_collect`) and the agentic collector
    (events gathered by Deep Agents subagents) feed this same path. `fetch_failures`
    carries through unchanged onto the result for the scheduled-run guard.
    """
    # keep events dated within the forward window OR undated ("open"); drop past/too-far
    in_scope = [
        e for e in collected
        if within_horizon(e, now, config.horizon_days) in (True, "open")
    ]

    # dedup: unseen only, collapsed within the batch (does not yet persist)
    fresh: list[Event] = []
    batch: set[str] = set()
    for e in in_scope:
        if e.event_hash in batch or not deps.seen_store.is_new(e.event_hash):
            continue
        batch.add(e.event_hash)
        fresh.append(e)

    digest_text = render_digest(fresh, now=now)

    sent = False
    should_send = bool(fresh) or config.send_on_empty
    if not config.dry_run and should_send:
        deps.notifier.send(config.target_chat_id, digest_text)
        sent = True
        for e in fresh:  # persist dedup only after a real send
            deps.seen_store.mark_seen(e)

    return DigestResult(digest_text=digest_text, events=fresh, sent=sent,
                        fetch_failures=list(fetch_failures or []))


def run_digest(now: datetime, config: Config, deps: Deps) -> DigestResult:
    events, failures = _collect(now, config, deps)
    return finish_digest(events, now, config, deps, fetch_failures=failures)

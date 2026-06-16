"""Core domain models shared across every pipeline stage."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, NamedTuple, Optional

from pydantic import BaseModel, Field, model_validator

EventType = Literal["conference", "meetup", "webinar", "other"]
CostStatus = Literal["free", "paid", "unknown"]
Domain = Literal["ai", "pr", "business", "legal"]


class DomainSpec(NamedTuple):
    """Presentation + agent metadata for one event domain."""

    section_title: str  # digest section header (render.py)
    ru_label: str       # short RU label injected into the subagent prompt (agents.py)


# Single source of truth for the domain taxonomy. Insertion order defines the
# order of sections in the rendered digest. Adding a domain here is all that the
# deterministic path, the renderer, and the agentic fan-out need.
DOMAINS: dict[str, DomainSpec] = {
    "ai":       DomainSpec("🤖 События в сфере ИИ", "ИИ"),
    "pr":       DomainSpec("📣 PR-события", "PR"),
    "business": DomainSpec("💼 Бизнес-события", "бизнес"),
    "legal":    DomainSpec("⚖️ Юридические события", "юридические"),
}


class RawPost(BaseModel):
    """A single post scraped from a t.me/s channel preview."""

    id: int
    channel: str
    text: str
    dt: Optional[datetime] = None
    permalink: Optional[str] = None


@dataclass
class ChannelFetchResult:
    """Outcome of fetching one channel: the posts plus whether the fetch succeeded.

    A failed fetch (network / auth / parse error) is deliberately distinct from a
    channel that simply had no recent posts — both used to collapse to an empty
    list, which is exactly why scheduled-run alerting could only fall back to the
    blunt "0 events" proxy. ``ok=False`` carries the failure up to the collectors.
    """

    channel: str
    posts: list[RawPost] = field(default_factory=list)
    ok: bool = True
    error: Optional[str] = None

    @classmethod
    def succeeded(cls, channel: str, posts: list[RawPost]) -> "ChannelFetchResult":
        return cls(channel=channel, posts=posts, ok=True)

    @classmethod
    def failed(cls, channel: str, error: str) -> "ChannelFetchResult":
        return cls(channel=channel, posts=[], ok=False, error=error)


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


class Event(BaseModel):
    """A structured event extracted from a post."""

    title: str
    description: Optional[str] = None
    event_type: EventType = "other"
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_online: Optional[bool] = None
    location: Optional[str] = None
    host: Optional[str] = None
    cost_status: CostStatus = "unknown"
    price_note: Optional[str] = None
    registration_url: Optional[str] = None
    domain: Domain = "ai"
    source_channel: Optional[str] = None
    source_post_url: Optional[str] = None
    source_post_dt: Optional[datetime] = None
    event_hash: str = Field(default="")

    @model_validator(mode="after")
    def _derive_hash(self) -> "Event":
        if not self.event_hash:
            day = self.start_date.date().isoformat() if self.start_date else "rolling"
            key = f"{_normalize(self.title)}|{day}|{_normalize(self.host or '')}"
            object.__setattr__(self, "event_hash", hashlib.sha256(key.encode()).hexdigest()[:16])
        return self

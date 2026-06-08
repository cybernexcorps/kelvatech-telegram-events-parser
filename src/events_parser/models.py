"""Core domain models shared across every pipeline stage."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

EventType = Literal["conference", "meetup", "webinar", "other"]
CostStatus = Literal["free", "paid", "unknown"]
Domain = Literal["ai", "pr"]


class RawPost(BaseModel):
    """A single post scraped from a t.me/s channel preview."""

    id: int
    channel: str
    text: str
    dt: Optional[datetime] = None
    permalink: Optional[str] = None


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

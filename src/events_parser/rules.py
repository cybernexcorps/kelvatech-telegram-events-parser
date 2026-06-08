"""Pure business rules: cost classification, horizon filtering, free-first ranking.

No I/O; deterministic given `now`. These carry the highest-bug-risk logic
(free-first ordering, the forward window) and are exhaustively unit-tested.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Literal, Union

from .models import CostStatus, Event

_FREE_RE = re.compile(r"бесплат|вход свободн|\bfree\b|(?<!\d)0\s*(?:₽|руб)", re.IGNORECASE)
_PAID_RE = re.compile(r"₽|руб|\bцена\b|\bстоимость\b|\bбилет|\bплатн|\bот\s*\d", re.IGNORECASE)

_COST_ORDER = {"free": 0, "paid": 1, "unknown": 2}


def classify_cost(event: Event) -> CostStatus:
    """Keep an explicit free/paid; otherwise infer from text signals."""
    if event.cost_status in ("free", "paid"):
        return event.cost_status
    blob = " ".join(filter(None, [event.title, event.description, event.price_note]))
    if _FREE_RE.search(blob):
        return "free"
    if _PAID_RE.search(blob):
        return "paid"
    return "unknown"


def within_horizon(
    event: Event, now: datetime, horizon_days: int = 28
) -> Union[bool, Literal["open"]]:
    """True if dated within [now, now+horizon]; 'open' if undated; False if past/too far."""
    if event.start_date is None:
        return "open"
    start = event.start_date
    if start.tzinfo is None and now.tzinfo is not None:
        start = start.replace(tzinfo=now.tzinfo)
    if start.date() < now.date():
        return False
    return start.date() <= (now + timedelta(days=horizon_days)).date()


def _date_key(event: Event) -> datetime:
    return event.start_date or datetime.max.replace(tzinfo=None)


def rank(events: list[Event]) -> list[Event]:
    """Free before paid before unknown; then by date ascending; stable within ties."""
    return sorted(
        events,
        key=lambda e: (
            _COST_ORDER.get(classify_cost(e), 2),
            _date_key(e).replace(tzinfo=None),
        ),
    )

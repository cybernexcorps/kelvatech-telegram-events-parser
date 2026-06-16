"""render_digest — Russian weekly digest (pure function), Telegram-HTML safe.

Sectioned by domain (one section per `models.DOMAINS` entry), free events first within each section, plus a
separate "open / by-request" section for undated events. Russian typography
(«», —). Empty input renders a graceful "no new events" message.

Output uses Telegram HTML parse mode: section headers are <b>, source links are
<a href>, and every interpolated field is html.escape'd so titles/hosts that
contain <, >, &, or Markdown punctuation can never break (or inject into) the
delivered message.
"""
from __future__ import annotations

import html
from datetime import datetime
from typing import Optional

from .models import DOMAINS, Event
from .rules import classify_cost, rank

_RU_MONTHS = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля", 5: "мая", 6: "июня",
    7: "июля", 8: "августа", 9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}
_COST_BADGE = {"free": "бесплатно", "paid": "платно", "unknown": "уточняется"}

EMPTY_MESSAGE = "На этой неделе новых событий не найдено."


def _esc(s: Optional[str]) -> str:
    return html.escape(s or "", quote=False)


def _fmt_date(dt: Optional[datetime]) -> str:
    if dt is None:
        return "по запросу"
    return f"{dt.day} {_RU_MONTHS[dt.month]}"


def _place(e: Event) -> str:
    if e.is_online is True:
        return "онлайн"
    if e.location:
        return _esc(e.location)
    return "офлайн" if e.is_online is False else "формат уточняется"


def _event_line(e: Event) -> str:
    parts = [_fmt_date(e.start_date), _place(e)]
    if e.host:
        parts.append(_esc(e.host))
    parts.append(_COST_BADGE[classify_cost(e)])
    meta = " · ".join(parts)
    link = f' — <a href="{_esc(e.source_post_url)}">источник</a>' if e.source_post_url else ""
    return f"• «{_esc(e.title)}» — {meta}{link}"


def _section(title: str, events: list[Event]) -> list[str]:
    if not events:
        return []
    lines = [f"<b>{title}</b>", ""]
    lines += [_event_line(e) for e in rank(events)]
    lines.append("")
    return lines


def render_digest(events: list[Event], *, now: datetime) -> str:
    if not events:
        return EMPTY_MESSAGE

    week = f"{now.day} {_RU_MONTHS[now.month]} {now.year}"
    out: list[str] = [f"<b>Дайджест событий — неделя от {week}</b>", ""]

    # One dated section per domain, in registry order; undated events of any
    # domain collapse into the shared "open / by-request" section below.
    for domain, spec in DOMAINS.items():
        dated = [e for e in events if e.domain == domain and e.start_date is not None]
        out += _section(spec.section_title, dated)

    open_ = [e for e in events if e.start_date is None]
    out += _section("🔓 Открытые события и вебинары по запросу", open_)

    if len(out) <= 2:  # only the header, nothing rendered
        return EMPTY_MESSAGE
    return "\n".join(out).rstrip() + "\n"

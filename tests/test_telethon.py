"""S12 — Telethon fetcher: pure message->RawPost mapping + since-window filter."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from events_parser.telethon_client import filter_recent, message_to_rawpost

NOW = datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc)


def _msg(id, text, dt):
    return SimpleNamespace(id=id, message=text, date=dt)


def test_message_maps_to_rawpost_with_permalink():
    m = _msg(321, "Бесплатный вебинар по ИИ", NOW)
    p = message_to_rawpost(m, "ai_chan")
    assert p.id == 321
    assert p.channel == "ai_chan"
    assert p.text == "Бесплатный вебинар по ИИ"
    assert p.dt == NOW
    assert p.permalink == "https://t.me/ai_chan/321"


def test_media_only_message_has_empty_text_not_none():
    m = SimpleNamespace(id=1, message=None, date=NOW)  # media post, no caption
    p = message_to_rawpost(m, "c")
    assert p.text == ""


def test_filter_recent_keeps_only_within_window():
    posts = [
        message_to_rawpost(_msg(3, "new", NOW - timedelta(days=1)), "c"),
        message_to_rawpost(_msg(2, "edge", NOW - timedelta(days=7)), "c"),
        message_to_rawpost(_msg(1, "old", NOW - timedelta(days=8)), "c"),
    ]
    since = NOW - timedelta(days=7)
    kept = filter_recent(posts, since)
    assert [p.id for p in kept] == [3, 2]  # day-8 dropped, day-7 edge kept


def test_filter_recent_without_since_returns_all():
    posts = [message_to_rawpost(_msg(1, "x", NOW), "c")]
    assert filter_recent(posts, None) == posts

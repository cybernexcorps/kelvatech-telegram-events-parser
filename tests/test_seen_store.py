"""S05 — SeenStore: SQLite dedup, stable hashing, cross-channel + cross-week."""
from datetime import datetime, timezone

from events_parser.models import Event
from events_parser.seen_store import SeenStore

NOW = datetime(2026, 6, 7, tzinfo=timezone.utc)


def _ev(title="Конференция ИИ", host="Kelva", channel="ai_chan", start=NOW):
    return Event(title=title, host=host, start_date=start, domain="ai",
                 source_channel=channel, cost_status="free")


def test_event_is_new_until_marked():
    store = SeenStore(":memory:")
    e = _ev()
    assert store.is_new(e.event_hash) is True
    store.mark_seen(e)
    assert store.is_new(e.event_hash) is False


def test_same_event_across_channels_collapses_to_one_hash():
    # identical title+date+host announced in two different channels -> one logical event
    a = _ev(channel="ai_chan")
    b = _ev(channel="general_chan")
    assert a.event_hash == b.event_hash
    store = SeenStore(":memory:")
    store.mark_seen(a)
    assert store.is_new(b.event_hash) is False


def test_mark_seen_is_idempotent():
    store = SeenStore(":memory:")
    e = _ev()
    store.mark_seen(e)
    store.mark_seen(e)  # must not raise on duplicate primary key
    assert store.is_new(e.event_hash) is False


def test_dedup_survives_restart(tmp_path):
    db = str(tmp_path / "seen.sqlite3")
    e = _ev()
    SeenStore(db).mark_seen(e)
    # new instance, same file = a later week's run
    assert SeenStore(db).is_new(e.event_hash) is False

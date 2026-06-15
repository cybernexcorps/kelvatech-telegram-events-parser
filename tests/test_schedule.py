"""Slice 2 (issue #3 / ADR-0001) — weekly fire lands on the configured weekday.

Standard crontab weekday semantics (1=Mon, 0/7=Sun) must hold regardless of
APScheduler's internal numbering. The mapping test below needs no heavy deps.
"""
from datetime import datetime, timezone

import pytest

from events_parser.orchestrator import DigestResult
from events_parser.schedule import guarded_scheduled_run, normalize_weekday_field

REF = datetime(2026, 6, 15, 9, 0, tzinfo=timezone.utc)


def _recorder():
    """Return (messages_list, alert_callable) for asserting what was alerted."""
    msgs: list[str] = []
    return msgs, msgs.append


def test_normalize_weekday_field_uses_standard_cron_semantics():
    # standard crontab: 0 and 7 are Sunday, 1 is Monday ... 6 is Saturday
    assert normalize_weekday_field("1") == "mon"
    assert normalize_weekday_field("0") == "sun"
    assert normalize_weekday_field("7") == "sun"
    assert normalize_weekday_field("6") == "sat"
    # '*' and already-named days pass through untouched
    assert normalize_weekday_field("*") == "*"
    assert normalize_weekday_field("mon") == "mon"
    # comma lists translate element-wise
    assert normalize_weekday_field("1,3") == "mon,wed"


def test_default_schedule_fires_on_monday_0900_utc():
    """The headline regression: '0 9 * * 1' must fire Monday, not Tuesday."""
    pytest.importorskip("apscheduler")
    from events_parser.schedule import build_weekly_trigger

    trigger = build_weekly_trigger("0 9 * * 1")  # standard cron: Monday 09:00 UTC
    ref = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)  # a Wednesday
    nxt = trigger.get_next_fire_time(None, ref)

    assert nxt is not None
    assert nxt.weekday() == 0          # Monday (Python: Mon=0); the bug fired Tuesday (1)
    assert (nxt.hour, nxt.minute) == (9, 0)
    assert nxt.utcoffset().total_seconds() == 0  # UTC


def test_sunday_schedule_fires_on_sunday():
    """Locks the 0/7=Sunday end of the mapping through the real trigger."""
    pytest.importorskip("apscheduler")
    from events_parser.schedule import build_weekly_trigger

    ref = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
    nxt = build_weekly_trigger("0 9 * * 0").get_next_fire_time(None, ref)
    assert nxt.weekday() == 6          # Sunday (Python: Sun=6)


# --- Issue #4: guarded scheduled run alerts the operator on failure ---

def test_guarded_run_alerts_on_exception_and_swallows():
    """An exception in the scheduled run must alert and be swallowed, so the
    scheduler keeps its next fire (matches today's non-crashing behavior)."""
    msgs, alert = _recorder()

    def boom():
        raise RuntimeError("sqlite boom")

    result = guarded_scheduled_run(boom, alert, now_fn=lambda: REF)

    assert result is None
    assert len(msgs) == 1
    assert "RuntimeError" in msgs[0] and "boom" in msgs[0]


def test_guarded_run_alerts_on_zero_events():
    """A scheduled run that delivers 0 events is the path-agnostic proxy for
    'all channels failed' (or a quiet week) — alert, but return the result."""
    msgs, alert = _recorder()
    empty = DigestResult(digest_text="(empty)", events=[], sent=True)

    result = guarded_scheduled_run(lambda: empty, alert, now_fn=lambda: REF)

    assert result is empty
    assert len(msgs) == 1
    assert "0" in msgs[0]


def test_guarded_run_is_silent_on_successful_delivery():
    msgs, alert = _recorder()
    ok = DigestResult(digest_text="d", events=["e1", "e2"], sent=True)

    result = guarded_scheduled_run(lambda: ok, alert, now_fn=lambda: REF)

    assert result is ok
    assert msgs == []


def test_guarded_run_is_silent_when_run_skipped():
    """run_fn returns None when a run is already in progress (lock) — not a failure."""
    msgs, alert = _recorder()
    result = guarded_scheduled_run(lambda: None, alert, now_fn=lambda: REF)
    assert result is None
    assert msgs == []


def test_guarded_run_survives_a_failing_alert():
    """A broken alert channel must never crash the scheduled run."""
    def boom():
        raise RuntimeError("run failed")

    def bad_alert(_text):
        raise RuntimeError("telegram down")

    # must not raise
    result = guarded_scheduled_run(boom, bad_alert, now_fn=lambda: REF)
    assert result is None

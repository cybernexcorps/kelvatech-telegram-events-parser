"""Slice 2 (issue #3 / ADR-0001) — weekly fire lands on the configured weekday.

Standard crontab weekday semantics (1=Mon, 0/7=Sun) must hold regardless of
APScheduler's internal numbering. The mapping test below needs no heavy deps.
"""
from datetime import datetime, timezone

import pytest

from events_parser.schedule import normalize_weekday_field

# The run-safety guard (#4) moved to DigestRunner.run_guarded / runner._guarded_run;
# its tests live in test_runner.py. This module now covers only trigger construction.


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

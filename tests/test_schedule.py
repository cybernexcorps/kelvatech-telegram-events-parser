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


# Slice (ADR-0006) — a weekly fire survives a scheduler misfire, and a missed fire
# alerts the operator. The headline regression: the 2026-06-22 fire was dropped because
# misfire_grace_time defaulted to 1s and pickup slipped 1.36s.


class _Ev:
    """Minimal stand-in for APScheduler's JobExecutionEvent — the listener only reads
    ``job_id``. Lets the pure tests run with no apscheduler import (light suite)."""
    def __init__(self, job_id: str):
        self.job_id = job_id


def test_make_misfire_alert_emits_missed_fire_text_to_the_alerter():
    """The pure half: a missed fire of the weekly job routes a distinct message to the
    supplied alerter. No apscheduler import — runs in the light suite."""
    from events_parser.schedule import WEEKLY_JOB_ID, make_misfire_alert

    sent: list[str] = []
    make_misfire_alert(sent.append)(_Ev(WEEKLY_JOB_ID))

    assert len(sent) == 1
    # Distinct from the run-level failure/0-events wording so the operator can tell
    # "never ran" from "ran and failed".
    assert "пропущен" in sent[0]


def test_make_misfire_alert_ignores_other_jobs():
    """A missed fire from a different job id must not alert (scoped to the weekly job)."""
    from events_parser.schedule import make_misfire_alert

    sent: list[str] = []
    make_misfire_alert(sent.append)(_Ev("some_other_job"))

    assert sent == []


def test_make_misfire_alert_is_silent_when_alerter_is_the_disabled_noop():
    """When alerting is unprovisioned the alerter is a no-op callable; the handler must
    simply call it for our job (no crash, no second channel)."""
    from events_parser.schedule import WEEKLY_JOB_ID, make_misfire_alert

    calls = {"n": 0}
    def _noop(_text: str) -> None:
        calls["n"] += 1

    make_misfire_alert(_noop)(_Ev(WEEKLY_JOB_ID))
    assert calls["n"] == 1


def test_configure_scheduler_registers_weekly_job_with_one_hour_grace():
    """The wiring half: the weekly job is added with misfire_grace_time=3600 (the fix),
    plus the coalesce/max_instances that were already correct."""
    pytest.importorskip("apscheduler")
    from apscheduler.schedulers.background import BackgroundScheduler

    from events_parser.schedule import configure_scheduler

    scheduler = BackgroundScheduler(timezone="UTC")  # not started — no threads
    ran: list[str] = []
    configure_scheduler(
        scheduler,
        run_fn=lambda: ran.append("run"),
        alerter=lambda _t: None,
        cron="0 9 * * 1",
    )

    job = scheduler.get_job("weekly_digest")
    assert job is not None
    assert job.misfire_grace_time == 3600   # the bug was the 1s default
    assert job.coalesce is True
    assert job.max_instances == 1


def test_configure_scheduler_alerts_on_a_missed_fire():
    """A missed weekly fire (EVENT_JOB_MISSED for our job id) pings the operator via the
    same alerter the run uses — closing the scheduler-seam gap ADR-0005 left open."""
    pytest.importorskip("apscheduler")
    from apscheduler.events import EVENT_JOB_MISSED, JobExecutionEvent
    from apscheduler.schedulers.background import BackgroundScheduler

    from events_parser.schedule import configure_scheduler

    scheduler = BackgroundScheduler(timezone="UTC")
    sent: list[str] = []
    configure_scheduler(
        scheduler,
        run_fn=lambda: None,
        alerter=sent.append,
        cron="0 9 * * 1",
    )

    # Simulate APScheduler dispatching a missed-fire event for the weekly job.
    event = JobExecutionEvent(
        EVENT_JOB_MISSED, "weekly_digest", "default",
        datetime(2026, 6, 22, 9, 0, tzinfo=timezone.utc),
    )
    scheduler._dispatch_event(event)

    assert len(sent) == 1
    assert "пропущен" in sent[0]


def test_configure_scheduler_ignores_a_missed_fire_from_another_job():
    """The listener must attribute a missed fire to the weekly digest only — a misfire
    from some other job (a future second schedule) must not masquerade as a missed
    digest. ADR-0006 scopes the alert to 'the weekly job'."""
    pytest.importorskip("apscheduler")
    from apscheduler.events import EVENT_JOB_MISSED, JobExecutionEvent
    from apscheduler.schedulers.background import BackgroundScheduler

    from events_parser.schedule import configure_scheduler

    scheduler = BackgroundScheduler(timezone="UTC")
    sent: list[str] = []
    configure_scheduler(
        scheduler, run_fn=lambda: None, alerter=sent.append, cron="0 9 * * 1",
    )

    foreign = JobExecutionEvent(
        EVENT_JOB_MISSED, "some_other_job", "default",
        datetime(2026, 6, 22, 9, 0, tzinfo=timezone.utc),
    )
    scheduler._dispatch_event(foreign)

    assert sent == []  # not our job → no operator ping

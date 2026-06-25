"""Weekly schedule trigger construction and scheduler wiring.

APScheduler v3 numbers ``day_of_week`` as 0=Monday, so feeding a standard crontab
expression (where 1=Monday, 0/7=Sunday) straight into ``CronTrigger.from_crontab``
fires on the wrong day. We translate the weekday field to **named** days, which v3
and v4 interpret identically, and build the trigger from explicit fields.
See docs/adr/0001-weekly-cron-weekday-named-day.md.

``configure_scheduler`` owns the weekly-job wiring (grace + misfire alert) so ``app.py``
stays thin and the policy is unit-testable. See docs/adr/0006 for the misfire decision.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable

log = logging.getLogger(__name__)

WEEKLY_JOB_ID = "weekly_digest"
# A weekly fire picked up within the hour is still useful; an hour is far beyond any
# plausible event-loop hiccup (the 2026-06-22 miss was 1.36s) yet bounded, so a fire is
# never resurrected at a bizarre hour after a long outage. The APScheduler default is 1s
# — which dropped that fire. See docs/adr/0006.
WEEKLY_MISFIRE_GRACE_S = 3600

# Standard crontab weekday numbering (0 and 7 are both Sunday).
_CRON_DOW_TO_NAME = {
    "0": "sun", "1": "mon", "2": "tue", "3": "wed",
    "4": "thu", "5": "fri", "6": "sat", "7": "sun",
}


def normalize_weekday_field(dow: str) -> str:
    """Translate a crontab day-of-week field to APScheduler-stable named days.

    Numeric values use standard crontab semantics (1=Mon, 0/7=Sun). ``*``, named
    days, and anything we don't recognise (ranges, step values) pass through
    untouched so they reach APScheduler as-is.
    """
    if dow == "*":
        return dow
    return ",".join(_CRON_DOW_TO_NAME.get(part, part) for part in dow.split(","))


def build_weekly_trigger(cron: str, tz: str = "UTC"):
    """Build a ``CronTrigger`` from a standard crontab string with correct weekday
    semantics. Use this instead of ``CronTrigger.from_crontab`` (see module docstring).

    ``CronTrigger`` is imported lazily so the unit suite need not install the
    ``runtime`` extra, matching the lazy-import convention in ``factory.py``.
    """
    from apscheduler.triggers.cron import CronTrigger

    minute, hour, day, month, dow = cron.split()
    return CronTrigger(
        minute=minute, hour=hour, day=day, month=month,
        day_of_week=normalize_weekday_field(dow), timezone=tz,
    )


def make_misfire_alert(alert: Callable[[str], None],
                       job_id: str = WEEKLY_JOB_ID) -> Callable[[object], None]:
    """Build an APScheduler listener that pings the operator on a **missed fire** of the
    weekly job. Pure text-formatting — takes no apscheduler import, so it is unit-testable
    in the light suite.

    The listener is scoped to ``job_id``: APScheduler dispatches ``EVENT_JOB_MISSED`` for
    *every* job, so a missed fire from some other (future) schedule must not masquerade as
    a missed digest. Events without a matching ``job_id`` are ignored.

    Reuses the run's ``alert`` callable (``build_error_alerter``) — one operator channel
    for every unattended-fire problem. Wording is distinct from the run-level
    failure/0-events messages so the operator can tell *the run never started* from
    *the run ran and failed*. See docs/adr/0006.
    """
    def _on_missed(event: object) -> None:
        if getattr(event, "job_id", None) != job_id:
            return
        log.warning("weekly digest fire was missed by the scheduler")
        alert(
            "⚠️ Дайджест: еженедельный запуск пропущен планировщиком · "
            f"{datetime.now(timezone.utc).isoformat()}"
        )
    return _on_missed


def configure_scheduler(scheduler, run_fn: Callable[[], object],
                        alerter: Callable[[str], None], cron: str,
                        tz: str = "UTC") -> None:
    """Wire the weekly digest onto ``scheduler``: the cron job (with a sane misfire
    grace) plus a missed-fire listener. Both halves of the docs/adr/0006 fix live here so
    ``app.py`` only has to call this.

    ``EVENT_JOB_MISSED`` is imported lazily (like ``CronTrigger`` in
    ``build_weekly_trigger``) so importing this module needs no ``runtime`` extra.
    """
    from apscheduler.events import EVENT_JOB_MISSED

    scheduler.add_job(
        run_fn, build_weekly_trigger(cron, tz), id=WEEKLY_JOB_ID,
        max_instances=1, coalesce=True,
        misfire_grace_time=WEEKLY_MISFIRE_GRACE_S,
    )
    scheduler.add_listener(make_misfire_alert(alerter, WEEKLY_JOB_ID), EVENT_JOB_MISSED)

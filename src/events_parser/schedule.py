"""Weekly schedule trigger construction.

APScheduler v3 numbers ``day_of_week`` as 0=Monday, so feeding a standard crontab
expression (where 1=Monday, 0/7=Sunday) straight into ``CronTrigger.from_crontab``
fires on the wrong day. We translate the weekday field to **named** days, which v3
and v4 interpret identically, and build the trigger from explicit fields.
See docs/adr/0001-weekly-cron-weekday-named-day.md.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Optional

log = logging.getLogger(__name__)

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


def _safe_alert(alert: Callable[[str], None], text: str) -> None:
    """Send an operator alert without ever letting its failure escape — a broken
    alert channel must not crash the scheduled run."""
    try:
        alert(text)
    except Exception:
        log.warning("failed to send failure alert", exc_info=True)


def guarded_scheduled_run(run_fn, alert: Callable[[str], None], now_fn=None):
    """Run the scheduled digest, alerting the operator on failure (issue #4).

    Wraps only the scheduled fire (manual /trigger and /digest report to their own
    callers). Best-effort and non-crashing: neither a run exception nor an
    alert-send failure propagates, so APScheduler keeps its next fire.
    """
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))
    try:
        result = run_fn()
    except Exception as exc:
        _safe_alert(alert, f"⚠️ Сбор дайджеста упал: {type(exc).__name__}: {exc} · {now_fn().isoformat()}")
        return None
    # result is None only when a run was already in progress (lock skip) — not a failure.
    if result is not None and not getattr(result, "events", None):
        _safe_alert(alert, f"⚠️ Дайджест: 0 событий (возможен сбой сбора или пустая неделя) · {now_fn().isoformat()}")
    return result

# Weekly fire survives a scheduler misfire; alerting extends to the scheduler layer

The weekly digest is started by an APScheduler cron job. APScheduler defaults
`misfire_grace_time` to **1 second**: if the executor picks the job up more than 1s
after its scheduled time, the run is dropped (a **missed fire**) and only a WARNING is
logged. On 2026-06-22 the Mon 09:00 UTC fire was picked up 1.36s late, so the very
first scheduled fire after deploy was dropped — no digest delivered, and no operator
alert, because the run never started.

That last part is the trap. ADR-0005 routes every caller through
`DigestRunner.run_guarded` and attaches the operator alerter to the unattended weekly
fire only — but `run_guarded`'s alert fires *inside the digest run*. A missed fire is
dropped by the scheduler **before** `DigestRunner.run` is entered, so the run-level
guard and its alert never see it. ADR-0005's "alert the operator when the unattended
fire goes wrong" intent had a blind spot at the scheduler seam: the one caller that is
supposed to alert is exactly the one whose failure mode (a missed fire) bypasses the
alert.

**Decision:** Two changes, both isolated in `schedule.py` behind `configure_scheduler`,
which `app.py`'s `lifespan` now calls instead of wiring the scheduler inline:

1. **Set `misfire_grace_time=3600`** (1 hour) on the weekly job. For a weekly cadence a
   fire picked up within the hour is still useful; an hour is far beyond any plausible
   event-loop hiccup (the real delay was ~1.3s). Bounded, not infinite, so a fire is
   never resurrected at a bizarre hour after a long outage. `coalesce=True` /
   `max_instances=1` are unchanged.
2. **Register an `EVENT_JOB_MISSED` listener** that, when the weekly job misfires,
   sends a distinct Russian message through the **same** `build_error_alerter` the run
   uses. The alerter is now emitted from two layers — the digest run (failure /
   fetch-failures / 0-events) and the scheduler (missed fire) — but it is one object,
   one bot (@kelva_errors_bot), one on/off switch (`TELEGRAM_ERROR_BOT_TOKEN` /
   `TELEGRAM_ERROR_CHAT_ID` unset → no-op). Distinct wording ("запуск пропущен
   планировщиком") lets the operator tell *the run failed* from *the run never happened*
   — different remediation.

This **extends** ADR-0005; it supersedes nothing. The boundary "alerting is attached to
the unattended fire only" still holds — a missed fire **is** the unattended fire failing.
What changes is that the alerter now guards two seams, not one.

## Considered options

- **Infinite grace (`misfire_grace_time=None`)** instead of a listener — rejected: an
  unbounded catch-up could deliver a "Monday" digest days later at an arbitrary time,
  and it still wouldn't *tell* anyone a fire slipped.
- **Lean on the existing 0-events / silence proxy** — rejected: that proxy lives inside
  the run and can't observe a fire that never produced a run. It cannot distinguish
  "ran, found nothing" from "never ran."
- **Log-only (status quo)** — rejected: WARNING-in-logs with no push is precisely the
  silent failure being fixed; nobody reads container logs proactively for a weekly job.
- **A second, separate alert channel for misfires** — rejected: redundant config and a
  second place to forget to provision; one operator channel for all unattended-fire
  problems is simpler.

## Consequences / constraints

- A missed fire is now **observable** (operator ping) but, with a 1h grace, also far
  less likely. The two defenses are independent: grace shrinks the failure rate, the
  listener catches whatever still slips.
- The alerter is emitted from two layers. A future change must keep both wired: removing
  the listener silently reopens the scheduler-seam gap; removing the run-level alert
  reopens ADR-0005's case. The "duplicate-looking" alert calls are deliberate — do not
  collapse them.
- `configure_scheduler` lazy-imports `apscheduler.events.EVENT_JOB_MISSED` (matching the
  `CronTrigger` lazy-import in `build_weekly_trigger`) so the unit suite still runs
  without the `runtime` extra. The message-formatting half (`make_misfire_alert`) takes
  no apscheduler import and is unit-tested directly against a fake event.
- New unattended schedules, if ever added, must register the same listener (or share
  `configure_scheduler`); attended callers (`/trigger`, `/digest`) still do not alert.
- The listener is **scoped by `job_id`**: APScheduler dispatches `EVENT_JOB_MISSED` for
  every job, so `make_misfire_alert` ignores any event whose `job_id` is not the weekly
  job's. Without this, a future second schedule's misfire would masquerade as a missed
  digest. A second schedule wanting its own missed-fire alert registers its own
  `make_misfire_alert(alerter, its_job_id)`.

_Tests: test_schedule.py — the weekly job is registered with `misfire_grace_time=3600`
(+ coalesce / max_instances); `make_misfire_alert` emits the missed-fire text to the
supplied alerter and is a no-op semantics-wise when the alerter is the disabled no-op._

# One guarded run entry; operator alerting stays scheduled-only

The digest is started by three callers: the weekly cron fire, `POST /trigger`, and the
`/digest` Telegram command. Originally only the cron fire was wrapped — by a
`guarded_scheduled_run` free function living in `schedule.py` — which caught exceptions,
alerted the operator, and never crashed (so APScheduler kept its next fire). `/trigger`
and `/digest` called `runner.run()` **raw**: an unhandled pipeline error would 500 the
endpoint / break the webhook handler, and a fourth caller could trivially reintroduce a
raw run. The guard logic also sat in the *scheduling* module, divorced from the runner it
guards.

**Decision:** fold the guard into `DigestRunner.run_guarded(alert=None)` — the single entry
every caller routes through. The overlap lock stays in `run()`; `run_guarded` adds
never-crash plus **optional** operator alerting (the alert-optional primitive is
`runner._guarded_run`). Only the unattended weekly fire passes an alerter. The manual
`/trigger` and `/digest` callers pass **no** alerter: they are attended — the human sees
the HTTP response or the Telegram acknowledgement — so an operator-bot ping would be
duplicate noise. They are still guarded, so a pipeline error can't 500 the endpoint.

This was a deliberate choice over "alert on every caller" (rejected: redundant noise when a
human is already watching) and over "leave `/trigger` raw + just document it" (rejected: an
unguarded run is a latent 500, and the raw path invites a future caller to skip the guard).

**Consequence / constraint:** `run_guarded` returns `None` for **both** a lock-skip and a
swallowed failure — manual callers report "no digest produced (in progress or failed; see
logs)" and the precise cause is in the logs. Do not reintroduce a raw `runner.run()` call
at an endpoint; route new callers through `run_guarded`. Keep alerting attached to the
unattended fire only — if a new unattended caller appears (e.g. a second schedule), it
passes the alerter; attended callers do not.

_Tests live in test_runner.py: run_guarded swallows a pipeline failure with no alerter
(can't 500); `_guarded_run` alerts only when an alerter is supplied (exception / fetch
failures / 0-events), and is silent on success, on lock-skip, and whenever alert is None._

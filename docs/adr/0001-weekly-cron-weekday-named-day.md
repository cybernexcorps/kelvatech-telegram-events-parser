# Build the weekly CronTrigger from a parsed crontab with named weekdays, and pin apscheduler < 4

`DIGEST_SCHEDULE_CRON` is operator-facing **standard crontab** (where `1` = Monday). But
APScheduler **v3**'s `CronTrigger.from_crontab(...)` interprets the numeric weekday field
with its own numbering (`0` = Monday), so `"0 9 * * 1"` scheduled the digest on **Tuesday**
— the prod digest fired on the wrong day for weeks (it then also crashed for an unrelated
reason; see ADR-0002). Crontab-standard weekday numbering only arrived in APScheduler v4.

**Decision:** stop passing numeric weekdays to APScheduler. Parse the crontab string and
translate the day-of-week field to **named days** (`mon`…`sun`), which v3 and v4 interpret
identically, then build the `CronTrigger` from explicit fields. Pin `apscheduler>=3.10,<4`
so a rebuild can't silently jump to v4's different API/semantics.

**Why not the obvious alternatives:** `from_crontab` directly is what a future reader will
reach for — it's wrong here. Just defaulting the env to `"0 9 * * mon"` leaves the same
footgun for any operator who types a number. Upgrading to v4 is a real API migration
(`Scheduler`/`add_schedule`), out of scope for a bug fix.

_A unit test asserts the next fire time for the default schedule lands on a Monday._

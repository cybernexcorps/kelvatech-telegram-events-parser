# Share one SQLite connection across threads, guarded by the single-run invariant

`SeenStore` opens its SQLite connection once at startup (in the FastAPI main thread), but
the weekly digest runs inside an APScheduler `BackgroundScheduler` **worker thread**.
Python's `sqlite3` defaults to `check_same_thread=True`, so the first DB call from the
worker raised `sqlite3.ProgrammingError` and the scheduled digest crashed before
delivering — the cron path never worked (manual one-shot runs did, being single-threaded).

**Decision:** open the connection with `check_same_thread=False` and keep sharing the
single connection, rather than opening a connection per call or adding an internal lock.

This is safe **only** because every digest run is serialized: `DigestRunner._lock`
(non-blocking acquire) plus APScheduler `max_instances=1` + `coalesce=True`, and all
callers (weekly fire, `/trigger`, `/telegram/webhook`) funnel through `DigestRunner.run`.
No two threads ever touch the connection concurrently — they only touch it from
*different* threads at different times, which `check_same_thread=False` permits.

**Consequence / constraint:** this invariant is load-bearing. If a future change lets two
digest runs overlap (e.g. removing the run lock, multiple uvicorn workers, a second caller
that bypasses `DigestRunner`), reopen this decision — switch to a connection-per-operation
or an internal lock. The connection line carries a comment pointing here.

_A regression test runs `DigestRunner.run` from a thread other than the one that built the
deps and asserts it neither raises nor fails to deliver._

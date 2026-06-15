# The fetch seam reports per-channel health (failed ≠ quiet)

Both channel readers (`PreviewClient`, `TelethonFetch`) used to swallow a fetch error
and return an empty `list[RawPost]` — "one bad channel must not abort the run." Correct
resilience, but lossy: a channel that **errored** became indistinguishable from one that
was simply **quiet** (fetched fine, no recent posts). The collectors saw `[]` either way,
so the scheduled-run guard (issue #4) could only alert on the blunt proxy "0 events
delivered" — which fires on a genuinely quiet week and stays silent when *some* channels
fail but others still produce events.

**Decision:** `fetch_recent` returns a `ChannelFetchResult` (`channel`, `posts`, `ok`,
`error`) instead of a bare list. Resilience moves up: `PreviewClient.fetch_posts` now
fetches one page **or raises**, and `fetch_recent` is the single boundary that catches and
reports a failure as `ok=False` (it still never raises, so one bad channel can't abort the
run). Both collectors thread the failed channels onto `DigestResult.fetch_failures`:

- deterministic — `_collect` returns `(events, failures)`;
- agentic — the subagent tools record into `EventCollector.failures`.

`guarded_scheduled_run` alerts on `fetch_failures` (naming the channels), and that
**supersedes** the 0-events proxy: failures explain the emptiness, so we alert once with
the precise cause and only fall back to the 0-events nudge when nothing failed.

**Consequence / constraint:** the failed-vs-quiet distinction is load-bearing — do not
"simplify" `fetch_recent` back to returning `[]` on error (it would re-blind the alerting).
The single-page `fetch_posts` is now allowed to raise; `fetch_recent` owns the skip-on-
failure behaviour. The Telethon `fetch_recent` is exercised live (no unit test), so keep
its `ChannelFetchResult` return in lockstep with the preview client.

_Tests: a failed channel surfaces in `DigestResult.fetch_failures` (deterministic +
agentic), the preview client returns a failed result without raising, and the guard alerts
on fetch failures, superseding the 0-events proxy._

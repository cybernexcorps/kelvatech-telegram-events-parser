# Telegram Events Parser

Weekly digest of upcoming RU AI/PR events, scraped from Telegram channels, filtered
free-first, and delivered to a Telegram channel. This glossary fixes the project's
domain language so issues, tests, and decisions use one set of words.

## Language

**Fire**:
The weekly cron trigger reaching its scheduled time and invoking a digest run. A fire
is distinct from delivery — the job can fire and still deliver nothing (empty week) or
fail mid-run.
_Avoid_: trigger (reserve "trigger" for the manual `/trigger` HTTP endpoint), run

**Digest run**:
One execution of the pipeline `fetch → extract → tag domain → horizon-filter → dedup →
render → deliver`, entered through `DigestRunner.run`. At most one runs at a time.
_Avoid_: job, cycle, execution

**Deliver**:
Sending the rendered digest to the target Telegram channel. Only a successful deliver
marks events seen.
_Avoid_: send (used at the Notifier level), post, publish

**Seen-store**:
The SQLite table of already-reported events, keyed by `event_hash`, that prevents an
event reported in a prior week from being re-delivered (cross-week dedup).
_Avoid_: cache, dedup db, history

**Horizon**:
The forward window (in days) an event's date must fall within to be included. Undated
("open") events are kept; past and too-far-future events are dropped.
_Avoid_: window (ambiguous with scan window), range

**Scan window**:
The look-back period (in days) over which recent channel posts are fetched for
extraction. Distinct from horizon, which filters on the event date, not the post date.
_Avoid_: lookback, scan range

**Deterministic path**:
The no-LLM-agent collection route (`run_digest` → `_collect`) used by the CLI and tests.
_Avoid_: simple path, fallback

**Agentic path**:
The Deep Agents supervisor route (`AgentDigestService`) that collects events via
subagents, then rejoins the shared `finish_digest`. Selected by `USE_AGENTS`.
_Avoid_: AI path, agent mode

**Domain**:
The subject a channel and its events belong to — `ai` or `pr`. The channel's configured
domain is authoritative and overrides whatever the extractor guessed.
_Avoid_: category, topic, vertical

**Fetch failure**:
A channel whose fetch errored this run (network / auth / parse), carried up as a
`ChannelFetchResult` with `ok=False` — deliberately distinct from a channel that was
merely **quiet** (fetched fine, no recent posts). The distinction is what lets the
scheduled-run guard alert precisely instead of via the blunt 0-events proxy. See
docs/adr/0004-fetch-seam-reports-channel-health.md.
_Avoid_: skip, empty channel, dead channel (a failure may be transient)

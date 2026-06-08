# PRD — Kelva Telegram Events Parser

**Product:** `kelvatech-telegram-events-parser`
**Type:** LangChain Deep Agents multi-agent service (Python)
**Status:** Ready for agent (build cycle: dev-until-testable)
**Author:** Slava Pospelov (grilled & synthesized with Claude)
**Date:** 2026-06-07
**Worktree/branch:** `parser-dev`

---

## Problem Statement

Kelva Tech's team (and its PR/AI-agency audience) needs to stay on top of relevant industry
events — AI conferences, meetups, and webinars, plus PR-industry events — but the signal is
scattered across Telegram channels. Manually reading channels every week, separating real
events from noise, working out whether attendance is **free or paid**, checking dates, and
deduplicating the same event announced repeatedly is tedious and gets skipped. As a result,
worthwhile **free** events (the highest-value, lowest-friction ones to attend) are missed
because nobody had time to comb the feeds.

From the user's perspective: *"Every week I want a single, trustworthy Russian digest of
upcoming AI and PR events — with free ones up top — delivered to me in Telegram, without me
reading a dozen channels myself."*

## Solution

A Dockerized **LangChain Deep Agents** service that, once a week, scans a configurable set of
Russian Telegram channels (one focus on **AI-field events**, one on **PR-field events**),
extracts structured event records from posts, classifies each as **free or paid**, filters to
events happening in the **next ~4 weeks**, removes events already reported in prior weeks, and
produces a **Russian-language weekly digest** — **free events prioritized first** — delivered
via a dedicated Telegram bot.

A **supervisor** Deep Agent coordinates two **async subagents** (`ai-events`, `pr-events`),
each owning one domain's channels, running concurrently over the Agent Protocol (ACP,
co-deployed in the same container). The same pipeline is also reachable on demand via a
`/digest` bot command. Telegram reading uses the **public `t.me/s/{channel}` web preview**
(paginated by `?before=<id>`) — **no Telegram API credentials needed for reading**. LLM work
runs on **Yandex Foundation Models** (keeping inference RU-resident), and every LLM/graph step
is traced in **LangSmith**.

## User Stories

1. As a Kelva team member, I want a weekly Russian digest of upcoming AI events, so that I can decide which conferences/meetups/webinars to attend without reading every channel.
2. As a Kelva team member, I want a weekly Russian digest of upcoming PR-industry events, so that I keep current on my own field's gatherings.
3. As a budget-conscious attendee, I want **free** events listed first and clearly marked, so that I can grab the no-cost opportunities before anything else.
4. As an attendee, I want each event's **cost status (free / paid / unknown)** shown explicitly, so that I'm never surprised by a paywall after I've planned to go.
5. As a planner, I want only events happening in the **next ~4 weeks**, so that the digest is actionable and not cluttered with far-off or already-past events.
6. As a reader, I want **undated or rolling events** (e.g. on-demand webinars) in a separate "open/rolling" section, so that they don't get dropped just because they lack a fixed date.
7. As a weekly reader, I want events I already saw in a previous digest to **not reappear**, so that each digest is genuinely "what's new this week."
8. As a reader, I want each event to show **what, when, where/online, host, and cost**, so that I have enough to decide and register.
9. As a reader, I want a **link back to the source post** for each event, so that I can verify details and register.
10. As a reader, I want the digest in **natural Russian** with proper typography («», em-dashes, "10 000"), so that it reads professionally, not machine-translated.
11. As an operator, I want the scanned channels defined in a **config file**, so that I can add/remove/reorder channels without code changes.
12. As an operator, I want to trigger a digest **on demand** via a `/digest` Telegram command, so that I can run it ad hoc or re-run after fixing config.
13. As an operator, I want the weekly run to fire **automatically on a schedule**, so that the digest arrives without me remembering to trigger it.
14. As an operator, I want the digest delivered to a **configurable Telegram chat** (my private chat for testing, a team channel later), so that I can move it to production audience without a rebuild.
15. As an operator, I want the whole service to run in a **single Docker container**, so that deployment and local testing are one command.
16. As an operator, I want a **persistent record of events already sent** that survives restarts, so that dedup isn't lost when the container recycles.
17. As a developer, I want every LLM call and agent step **traced in LangSmith**, so that I can debug extraction quality and see where a run failed.
18. As a developer, I want the **AI-events and PR-events work to run concurrently** as async subagents, so that the weekly run finishes faster and each domain's context stays isolated.
19. As a developer, I want a clear **"event" data model**, so that extraction, classification, ranking, dedup, and rendering all share one schema.
20. As a developer, I want **structured LLM extraction** (typed output) per post, so that downstream steps get reliable fields rather than free text.
21. As a developer, I want the **cost model split** — a cheap fast model for high-volume extraction, a stronger model for the digest prose — so that quality and cost are both controlled.
22. As a developer, I want each pipeline stage behind an **injectable seam**, so that I can unit-test business logic without network, LLM, or Telegram.
23. As a developer, I want **HTML fixtures of real `t.me/s` pages** in the test suite, so that scraping logic is tested deterministically and HTML drift is detectable.
24. As an operator, I want a run that finds **zero qualifying events** to still send a graceful "no new events this week" message (or be configurable to stay silent), so that I know the system ran.
25. As an operator, I want a channel that is **unreachable or empty** to be logged and skipped without aborting the whole run, so that one bad channel doesn't kill the digest.
26. As an operator, I want **malformed LLM output** to be retried once and then skipped-with-log, so that a single bad post doesn't crash the run or silently corrupt the digest.
27. As a reader, I want events **deduplicated across channels** within a single run (same event posted in both an AI and a general channel), so that I don't see duplicates in one digest.
28. As an operator, I want **secrets (bot token, Yandex key, LangSmith key) supplied via env / Docker secrets**, so that nothing sensitive is committed.
29. As a developer, I want the channel list to distinguish **domain (AI vs PR)** per channel, so that the right subagent owns it and the digest can be sectioned by domain.
30. As a reader, I want the digest **sectioned by domain (AI events, PR events)** with free-first ordering inside each section, so that it's scannable.
31. As an operator, I want a **dry-run mode** that renders the digest to stdout/file without sending to Telegram, so that I can preview output safely.
32. As a developer, I want the live end-to-end run reproducible **inside the container**, so that "works on my machine" equals "works in prod."

## Implementation Decisions

### Architecture & runtime
- **Hybrid trigger model.** Two entry points into one pipeline: (a) an **APScheduler** weekly job (in-process, started in the FastAPI lifespan); (b) a Telegram **`/digest` command** handler. Both call the same `run_digest(...)` orchestrator.
- **Deep Agents topology.** A **supervisor** `create_deep_agent` coordinates **two async subagents** — `ai-events` and `pr-events` — each owning its domain's channels. Async subagents communicate over the **Agent Protocol (ACP)**, **co-deployed via ASGI transport** in the same container (no separate URL). Supervisor merges subagent outputs, then runs cross-domain dedup, ranking, rendering, delivery.
- **Deep Agents middleware used:** `TodoListMiddleware` (planning), `FilesystemMiddleware` (offload large `t.me/s` HTML so it never floods the context window), subagent middleware for context-quarantine per domain.
- **Tools exposed to subagents:** `fetch_posts(channel, before)`, `extract_events(post)` — i.e. the subagents are thin orchestration over the testable seams below.

### Modules (logical, no file paths)
- **Preview client** — fetches `https://t.me/s/{channel}` HTML, paginates backward via `?before=<id>`, parses post blocks into `RawPost` records (text, post id, datetime, permalink). HTTP via `httpx`; HTML via `selectolax`. No Telegram credentials.
- **Event extractor** — per `RawPost`, an LLM structured-output call returns zero-or-more `Event` records. Backed by a configurable chat model (default `yandexgpt-lite`).
- **Cost classifier** — derives `cost_status ∈ {free, paid, unknown}` from event fields/post text (LLM-assisted during extraction; pure-function normalization downstream).
- **Horizon filter** — pure function `within_horizon(event, now)`; keeps dated events within the forward window (default 28 days) and routes undated/rolling events to the "open" bucket.
- **Ranker** — pure function ordering: **free before paid before unknown**, then by date ascending; stable within ties.
- **Seen store** — SQLite table keyed by a stable `event_hash` (normalized title + date + host). `is_new()` / `mark_seen()`. DB file on a mounted Docker volume.
- **Digest renderer** — pure function `Event[] → Russian markdown`, sectioned by domain (AI / PR), free-first within section, plus an "open/rolling" section; Russian typography; source links.
- **Notifier** — sends the rendered digest to a configured Telegram chat via the dedicated bot. Behind an interface so a fake can capture sends in tests.
- **Orchestrator** — `run_digest(now, config, deps)` wires all of the above with injected dependencies (the **top seam**).
- **Config** — `channels.yaml` (per-channel `{handle, domain}`), plus env for secrets and tunables (horizon days, schedule cron, target chat id, model ids, send-on-empty flag, dry-run).

### Data model (`Event`)
Pydantic model, fields (RU values where user-facing):
`title`, `description`, `event_type ∈ {conference, meetup, webinar, other}`, `start_date` (nullable for rolling), `end_date` (nullable), `is_online` (bool/unknown), `location` (nullable), `host`, `cost_status ∈ {free, paid, unknown}`, `price_note` (nullable), `registration_url` (nullable), `source_channel`, `source_post_url`, `source_post_dt`, `domain ∈ {ai, pr}`, `event_hash` (derived).

### Models / inference
- **Yandex Foundation Models.** Extraction → `yandexgpt-lite` (cheap, high-volume, structured). Digest prose → large open model (**Qwen-2.5-72B** or **DeepSeek**) via Yandex's **OpenAI-compatible** endpoint (`ChatOpenAI(base_url=...)`); YandexGPT via `langchain-community ChatYandexGPT`. Model ids env-configurable. Auth = Yandex API key/IAM + folder id. RU-resident inference.

### Observability
- **LangSmith** tracing enabled via standard env (`LANGSMITH_API_KEY`, `LANGSMITH_TRACING=true`, project name). All chat models and the agent graph emit traces; a run is one inspectable trace tree.

### Delivery & ops
- **Dedicated Telegram bot** (new token); default target = private chat **142068037** (testing). Target chat configurable for promotion to a team channel.
- **Single Docker container** runs FastAPI + APScheduler + the co-deployed ACP subagents. SQLite + `channels.yaml` mounted; secrets via env/Docker secrets.
- Packaging via **uv**; tracked **inside SharedWorkspace** (not a separate repo).

### Failure handling
- Unreachable/empty channel → log + skip, run continues.
- Malformed LLM extraction → retry once → skip-with-log (never silent placeholder, never crash).
- Zero qualifying events → send "no new events" message (configurable to stay silent).
- Idempotent: re-running the same week sends nothing new (seen-store guards).

## Testing Decisions

- **Test only external behavior, not implementation.** A good test asserts what a module *does* at its seam — given inputs (fixtures/fakes), assert outputs/side-effects — never internal call sequences or private state.
- **Highest seam preferred.** The top integration seam is `run_digest(now, config, deps)` with **all dependencies injected** (preview client, chat model, seen store, notifier, clock). This proves the whole pipeline with zero network/LLM/Telegram.
- **Per-module seams & doubles:**
  - *Preview client* — parsed against **saved `t.me/s` HTML fixtures** (no network). Asserts correct `RawPost` extraction and `?before=` pagination cursor handling.
  - *Event extractor* — **fake chat model** returning canned structured output; asserts post→`Event[]` mapping and the malformed-output retry/skip path.
  - *Cost classifier / horizon filter / ranker* — **pure functions, exhaustive unit tests** (free-first ordering; 28-day boundary incl. edge dates; undated→open bucket). Highest bug-risk, cheapest to cover.
  - *Seen store* — **in-memory SQLite**; asserts `is_new`/`mark_seen` and stable hashing (same event across channels → one hash).
  - *Renderer* — **golden/structural assertions** on RU markdown (section presence, free-before-paid order, typography, source links).
  - *Notifier* — **fake notifier** capturing `(chat_id, text)`; asserts dry-run sends nothing and empty-run behavior.
- **Agent graph** is covered by the **live Docker run + LangSmith trace** (the done-line), not brittle mocks — the supervisor/subagents are thin over already-tested seams.
- **TDD per vertical slice** (red→green→refactor): each slice = one seam taken to green before the next.
- **Prior art:** mirror the Python service conventions of `ceo-personal-blog-writer` (DeepAgents + FastAPI + Docker) and `news-digest`; pytest as the runner.

## Out of Scope

- Telegram **API/MTProto** reading (the `t.me/s/` public preview is sufficient; no credentials).
- A real-network **HTML-drift contract test** that hits live `t.me/s` (explicitly declined this cycle; noted as a recommended future opt-in).
- **Authenticated/private** channels (only public channels with a web preview).
- A **web UI / dashboard** for the digest (Telegram delivery only this cycle).
- **Calendar/CRM export** (.ics, Google Calendar) of events.
- **Multi-language** digest output (Russian only; EN geo-neutral surface is a separate concern).
- Automatic **registration** for events or any write action beyond posting the digest.
- A generalized **"add any topic/domain"** framework beyond AI + PR (two domains this cycle).
- Proving the **cron fires unattended over a real week** (cron is wired; the done-line is a manual end-to-end run in Docker).
- Image/video/attachment parsing from posts (text-only extraction).

## Further Notes

- **HTML-drift risk.** Scraping `t.me/s` is the most fragile surface. Mitigation this cycle = HTML fixtures + skip-on-parse-failure. **Recommended next step:** add a network-gated contract test (skipped by default in CI) that fetches one real page weekly to detect Telegram markup changes early.
- **Channel selection** is a separate confirmation step before the live run: candidate RU AI-event and PR-event channels will be researched, proposed with rationale, and confirmed; they live in `channels.yaml` and are swappable without code changes.
- **Geo-positioning:** this is a **Russia-aware** surface (RU channels, RU audience) — Russian publishers/events named directly; do not apply the EN geo-neutral rules here.
- **Promotion path:** moving from test (private chat) to production (team channel) is config-only — change target chat id and (if a channel) add the bot as admin.
- **Async-subagent rationale:** the hybrid model is what justifies async subagents (preview feature, deepagents 0.5.0) — the on-demand `/digest` path keeps the bot responsive while domain subagents work; the weekly path benefits from their concurrency and per-domain context isolation.

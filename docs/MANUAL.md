# Kelva Telegram Events Parser — Complete Manual

> Comprehensive technical documentation for the `kelvatech-telegram-events-parser`
> product: what it does, how it's built, how to run it, and how to operate it in
> production. For the original product spec see [`PRD.md`](PRD.md); for the VPS
> deploy runbook see [`DEPLOY.md`](DEPLOY.md); for the build backlog see
> [`issues/`](issues/).

---

## Table of contents

1. [What it is](#1-what-it-is)
2. [How it works — the pipeline](#2-how-it-works--the-pipeline)
3. [Architecture & design principles](#3-architecture--design-principles)
4. [The two execution paths](#4-the-two-execution-paths-deterministic-vs-agentic)
5. [Module reference](#5-module-reference)
6. [Data model](#6-data-model)
7. [Business rules](#7-business-rules-cost-horizon-ranking)
8. [Channel reading](#8-channel-reading-telethon-vs-preview)
9. [The LLM layer (Yandex Foundation Models)](#9-the-llm-layer-yandex-foundation-models)
10. [The Deep Agents layer](#10-the-deep-agents-layer)
11. [Output: the Russian digest](#11-output-the-russian-digest)
12. [Deduplication & persistence](#12-deduplication--persistence)
13. [Triggers: cron & on-demand](#13-triggers-cron--on-demand)
14. [Configuration reference](#14-configuration-reference)
15. [Running it](#15-running-it)
16. [Deployment](#16-deployment)
17. [Access & operations](#17-access--operations)
18. [Observability](#18-observability)
19. [Testing](#19-testing)
20. [Security model](#20-security-model)
21. [Operations runbook](#21-operations-runbook)
22. [Troubleshooting](#22-troubleshooting)
23. [File map & glossary](#23-file-map--glossary)

---

## 1. What it is

The **Kelva Telegram Events Parser** produces a **weekly Russian-language digest of
upcoming AI-industry and PR-industry events** (conferences, meetups, webinars,
forums, masterclasses) by scanning a configurable set of public Russian Telegram
channels. It is opinionated about three things:

- **Free-first.** Free events are listed before paid ones; every event's cost
  status (`free` / `paid` / `unknown`) is shown explicitly.
- **Forward-looking.** Only events within the next ~4 weeks are included; undated
  / on-demand events go into a separate "open" section so they aren't dropped.
- **No repeats.** An event reported in a prior week never reappears (cross-week
  dedup), and the same event posted in several channels collapses to one entry
  (intra-run dedup).

The digest is delivered through a dedicated Telegram bot (**@kelva_events_bot**,
"Kelva Events"), either automatically once a week or on demand via a `/digest`
command.

**Technology:** Python 3.12, LangChain **Deep Agents**, **Yandex Foundation
Models** for inference (keeps LLM work RU-resident), **Telethon** (MTProto) or the
zero-auth `t.me/s` web preview for reading channels, **FastAPI** + **APScheduler**
for the host and scheduler, **SQLite** for the dedup store, **LangSmith** for
tracing, packaged as a single **Docker** container.

**Audience for this product:** the Kelva Tech team and its PR/AI-agency audience.
**Audience for this manual:** the operator/developer maintaining the service
(future-you).

---

## 2. How it works — the pipeline

Every run, whichever way it is triggered, follows the same seven-stage pipeline:

```
fetch_recent → extract → tag domain → horizon-filter → dedup → render → deliver
```

| Stage | What happens | Where |
|---|---|---|
| **fetch** | For each configured channel, read recent posts within the scan window (default 7 days). | `preview.py` / `telethon_client.py` |
| **extract** | An LLM turns each post into zero-or-more structured `Event` records. | `extraction.py` |
| **tag domain** | Each event's `domain` is forced to its source channel's domain (`ai`/`pr`) — the channel config is authoritative, not the LLM. | `orchestrator.py` |
| **horizon-filter** | Keep events dated within `[now, now+28d]`, plus undated ("open") events; drop past/too-far. | `rules.py` |
| **dedup** | Drop events already in the seen-store, and collapse duplicates within the batch by `event_hash`. | `orchestrator.py` + `seen_store.py` |
| **render** | Build the Russian, Telegram-HTML-safe digest, sectioned by domain, free-first. | `render.py` |
| **deliver** | Send via the Telegram Bot API (split if >4096 chars). Only on a real (non-dry) run; only then are events marked seen. | `notify.py` |

The orchestration seam is `run_digest(now, config, deps)` in
[`orchestrator.py`](../src/events_parser/orchestrator.py). The two collection
strategies (deterministic loop vs Deep Agents) both feed the **same**
`finish_digest()` tail — so dedup, ranking, rendering, and delivery behave
identically regardless of how events were gathered.

---

## 3. Architecture & design principles

### Dependency injection at every seam

The pipeline depends only on four Protocols, bundled in a `Deps` dataclass:

```python
@dataclass
class Deps:
    fetch: Fetch          # .fetch_recent(channel, since) -> list[RawPost]
    extractor: Extractor  # .extract(post) -> list[Event]
    seen_store: SeenStore # .is_new(hash) -> bool ; .mark_seen(event)
    notifier: Notifier    # .send(chat_id, text)
```

Because every external dependency (network, LLM, Telegram, disk) is injected,
the entire business logic is unit-testable with in-memory fakes — no network,
no LLM, no Telegram. This is why the test suite runs in well under a second and
needs none of the heavy `runtime` dependencies.

### Lazy imports / split dependency sets

Heavy libraries (`deepagents`, `langchain*`, `telethon`, `fastapi`, `uvicorn`,
`apscheduler`) live in the **optional** `runtime` extra. The core package depends
only on `pydantic`, `httpx`, `selectolax`, `pyyaml`. Composition modules
(`factory.py`, `agents.py`, `extraction.py`, `notify.py`) import the heavy deps
**inside functions**, so importing `events_parser` for tests never pulls them in.

### Composition root

[`factory.py`](../src/events_parser/factory.py) is the single place where real
dependencies are assembled from config + environment: `build_config`,
`build_fetch`, `build_deps`, `build_agent_service`. Everything else takes its
dependencies as arguments.

### Channel config is authoritative for domain

The LLM may guess a domain, but `_collect` (and the agentic tool) always overwrite
`event.domain` with the **channel's** configured domain. This keeps AI/PR
sectioning deterministic and immune to extraction drift.

### Correctness never depends on parsing LLM free-text

In the agentic path the subagents call tools that perform the *real*
fetch+extract and write results into a typed `EventCollector` sink. The
supervisor's natural-language output is never parsed for events — it only
coordinates. The digest is always built deterministically from the collected
typed records.

---

## 4. The two execution paths (deterministic vs agentic)

The product can collect events two ways. Both share the `finish_digest()` tail.

### Deterministic path (`run_digest`)

A plain nested loop over `config.channels`: fetch → extract → tag domain. No
agent, no supervisor. Fast, cheap, fully reproducible. Selected by `USE_AGENTS=false`
or the CLI flag `--no-agents`.

### Agentic path (`AgentDigestService`)

A Deep Agents **supervisor** delegates to two subagents, `ai-events` and
`pr-events`, each owning its domain's channels. The subagents call the
`extract_and_record_events` tool per channel, writing into a shared
`EventCollector`. After the supervisor finishes, `finish_digest()` runs on the
collected events. Selected by `USE_AGENTS=true` or `--agents`.

> **Default differs by entry point.** The FastAPI host (`app.py`) defaults
> `USE_AGENTS=true`. The CLI `--live` path defaults to **deterministic** unless
> `USE_AGENTS=true` is set in the environment or `--agents` is passed. The
> production `.env` sets `USE_AGENTS=true`, so the deployed service runs agentic.

Both paths produce the same digest given the same inputs; the agentic path adds
per-domain concurrency, planning middleware, and LangSmith-visible agent steps.

---

## 5. Module reference

All modules live in [`src/events_parser/`](../src/events_parser/).

| Module | Responsibility | Key public surface |
|---|---|---|
| `models.py` | Domain types. | `RawPost`, `Event` (with derived `event_hash`) |
| `config.py` | Load + validate `channels.yaml`; build `Config` from env. | `load_channels`, `Config.from_env` |
| `preview.py` | Zero-auth `t.me/s` HTML reader, paginated by `?before=`. | `PreviewClient`, `parse_preview` |
| `telethon_client.py` | Account-based (MTProto) reader; full history, IPv6/DC-pin. | `TelethonFetch`, `build_telethon_fetch` |
| `extraction.py` | LLM structured extraction of events from a post. | `EventExtractor`, `build_yandex_extractor` |
| `rules.py` | Pure business rules. | `classify_cost`, `within_horizon`, `rank` |
| `render.py` | Russian, Telegram-HTML-safe digest renderer. | `render_digest` |
| `notify.py` | Telegram Bot API delivery + message splitting. | `TelegramNotifier`, `split_message` |
| `seen_store.py` | SQLite dedup store. | `SeenStore` |
| `orchestrator.py` | The pipeline seam + shared finish path. | `run_digest`, `finish_digest`, `Deps`, `DigestResult` |
| `agents.py` | Deep Agents supervisor/subagents + LangGraph graph entrypoints. | `AgentDigestService`, `build_supervisor`, `*_graph` |
| `factory.py` | Composition root — assembles real deps. | `build_config`, `build_fetch`, `build_deps`, `build_agent_service` |
| `runner.py` | Single entry for cron + `/digest`, with overlap guard. | `DigestRunner` |
| `app.py` | FastAPI host: scheduler lifespan + HTTP endpoints. | `app`, `make_runner` |
| `__main__.py` | CLI: `--demo` / `--live`, `--dry-run`, `--agents`/`--no-agents`. | `main` |

---

## 6. Data model

Defined in [`models.py`](../src/events_parser/models.py). Both are Pydantic v2
models.

### `RawPost`

A single post scraped from a channel:

| Field | Type | Notes |
|---|---|---|
| `id` | `int` | Telegram message id |
| `channel` | `str` | channel handle (no `@`) |
| `text` | `str` | post body |
| `dt` | `datetime?` | post datetime (ISO from the preview) |
| `permalink` | `str?` | `https://t.me/{channel}/{id}` |

### `Event`

The structured record carried through the rest of the pipeline:

| Field | Type | Default | Notes |
|---|---|---|---|
| `title` | `str` | — | taken verbatim from the post |
| `description` | `str?` | `None` | |
| `event_type` | `conference\|meetup\|webinar\|other` | `other` | |
| `start_date` / `end_date` | `datetime?` | `None` | undated → "open" section |
| `is_online` | `bool?` | `None` | drives the place label |
| `location` | `str?` | `None` | |
| `host` | `str?` | `None` | organizer |
| `cost_status` | `free\|paid\|unknown` | `unknown` | |
| `price_note` | `str?` | `None` | free-text price detail |
| `registration_url` | `str?` | `None` | |
| `domain` | `ai\|pr` | `ai` | overwritten by channel config |
| `source_channel` / `source_post_url` / `source_post_dt` | | `None` | provenance |
| `event_hash` | `str` | derived | dedup key |

**`event_hash`** is the dedup identity, derived once on construction if not set:

```
sha256( normalize(title) | day | normalize(host) )[:16]
```

where `day` is `start_date.date().isoformat()` or the literal `"rolling"` for
undated events, and `normalize` lowercases and collapses whitespace. This makes
the same event collapse across channels and across weeks, while keeping distinct
events apart.

---

## 7. Business rules (cost, horizon, ranking)

Pure, deterministic functions in [`rules.py`](../src/events_parser/rules.py).
These hold the highest-bug-risk logic and are exhaustively unit-tested.

### `classify_cost(event) -> "free" | "paid" | "unknown"`

If the LLM already set `free`/`paid`, that wins. Otherwise it scans
`title + description + price_note` for signals:

- **Free** signals: `бесплат`, `вход свободн`, `free`, `0 ₽`/`0 руб`.
- **Paid** signals: `₽`, `руб`, `цена`, `стоимость`, `билет`, `платн`, `от <N>`.
- Neither → `unknown`.

### `within_horizon(event, now, horizon_days=28) -> True | "open" | False`

- `start_date is None` → `"open"` (kept, routed to the open section).
- dated **before** today → `False` (dropped).
- dated within `now + horizon_days` → `True`.
- dated beyond the window → `False`.

Naïve datetimes are coerced to `now`'s tzinfo before comparison. The orchestrator
keeps events whose result is `True` **or** `"open"`.

### `rank(events) -> list[Event]`

Sort key: **cost first** (`free` 0 → `paid` 1 → `unknown` 2), then **date
ascending** (undated sort last via `datetime.max`). Python's stable sort preserves
input order within ties. This is what makes the digest "free-first."

---

## 8. Channel reading (Telethon vs preview)

[`factory.build_fetch`](../src/events_parser/factory.py) chooses the reader:

- **Telethon (MTProto)** when both `TELEGRAM_API_ID` and `TELEGRAM_SESSION` are
  set. Reads full history, media captions, and channels without a web preview
  (including preview-disabled). This is the production path.
- **`t.me/s` preview** (`PreviewClient`) otherwise — zero credentials, parses the
  public web preview, paginates backward via `?before=<id>` up to `max_pages=3`,
  stopping when a page is empty, the cursor stops advancing, or posts predate the
  scan window.

### Telethon specifics

`TelethonFetch` (in [`telethon_client.py`](../src/events_parser/telethon_client.py))
builds a `TelegramClient(StringSession(...), api_id, api_hash, use_ipv6=...)` and
iterates messages newest-first, stopping at the scan-window edge. A failed channel
is logged and skipped — one bad channel never aborts the run.

**IPv6 / DC pin (for IPv4-blackholing hosts).** Some RU clouds reach Telegram only
over IPv6. Set:

```
TELEGRAM_USE_IPV6=true
TELEGRAM_DC_ID=<your account home DC>     # e.g. 2
TELEGRAM_DC_IP=<that DC's IPv6 addr>      # e.g. 2001:67c:4e8:f002::a
TELEGRAM_DC_PORT=443
```

`use_ipv6` alone still dials the IPv4 address baked into the `StringSession`;
`session.set_dc()` rewrites the stored `(dc_id, addr, port)` to the reachable
IPv6 endpoint. The `dc_id` **must** match the account's home DC. DC IPv6 map:

| DC | IPv6 |
|---|---|
| DC1 | `2001:b28:f23d:f001::a` |
| DC2 | `2001:67c:4e8:f002::a` |
| DC3 | `2001:b28:f23d:f003::a` |
| DC4 | `2001:67c:4e8:f004::a` |
| DC5 | `2001:b28:f23f:f005::a` |

The production account (`hrhrgth`) is home **DC2**. See
[`DEPLOY.md`](DEPLOY.md#ipv6-only-hosts-eg-procloud).

### Minting a session

Run **once**, interactively, on a trusted machine (the login code is sent to your
Telegram):

```bash
uv run --extra runtime python scripts/telethon_login.py
```

It prints `TELEGRAM_SESSION=...` — paste into `.env` along with `api_id`/`api_hash`
from <https://my.telegram.org>. The session is a credential — never commit it.
(`scripts/tdata_to_session.py` exists to mint a session from an existing Telegram
Desktop `tdata` folder via opentele.)

---

## 9. The LLM layer (Yandex Foundation Models)

Inference runs on **Yandex Foundation Models** through their OpenAI-compatible
endpoint (`https://llm.api.cloud.yandex.net/v1`), wired via `langchain_openai`.
Model URIs embed the folder: `gpt://<folder>/<model>`.

| Role | Default model | Env var |
|---|---|---|
| **Extraction** (high-volume, cheap) | `yandexgpt-lite/latest` | `YANDEX_EXTRACT_MODEL` |
| **Agent / supervisor reasoning** | `yandexgpt/latest` (falls back to `YANDEX_DIGEST_MODEL`, set to `qwen3-235b-a22b-fp8` in prod) | `YANDEX_AGENT_MODEL` / `YANDEX_DIGEST_MODEL` |

### Structured extraction

`build_yandex_extractor` binds the model with
`.with_structured_output(ExtractionResult)`, so each post yields a typed
`ExtractionResult { events: list[ExtractedEvent] }` rather than free text. The
`EventExtractor`:

- Sends a Russian system prompt that **only** wants attendable announcements
  (conf/meetup/webinar/forum/masterclass/lecture) and explicitly rejects news,
  product releases, reviews, vacancies, ads, and past events.
- Retries once on malformed output, then skips-with-log.
- Detects Yandex's **content-filter** rejection and skips immediately (retrying
  can't help).
- Coerces literal blanks (`"null"`, `"none"`, `"-"`, `"не указано"`, …) to `None`
  so the renderer's fallbacks apply.

Temperature is `0` everywhere for determinism.

---

## 10. The Deep Agents layer

Defined in [`agents.py`](../src/events_parser/agents.py).

### Topology

```
            supervisor (create_deep_agent)
            ├── ai-events  subagent  → owns domain=="ai" channels
            └── pr-events  subagent  → owns domain=="pr" channels
```

Each subagent gets a Russian system prompt listing exactly its channels and is
told to call `extract_and_record_events(channel, domain)` once per channel, then
report a count. Two tools are exposed:

- `list_recent_posts(channel)` — returns `[id] text[:120]` snippets.
- `extract_and_record_events(channel, domain)` — real fetch+extract, writes typed
  `Event`s into the `EventCollector`, returns a count.

**Context-window discipline:** tools return only short snippets, so raw `t.me/s`
HTML never enters the supervisor's context. `create_deep_agent` also bundles the
`TodoList` (planning) and `Filesystem` (large-payload offload) middleware by
default, and subagent context is quarantined per domain.

### Two deployment forms

1. **Co-deployed sync subagents** (default, in-container). `AgentDigestService.run`
   builds the supervisor, invokes it with one Russian instruction, then runs
   `finish_digest` on the collected events. This is what the Docker container uses.
2. **Async-subagent-server** (deepagents 0.5 preview). Under a LangGraph
   deployment, the supervisor's `AsyncSubAgent` specs run co-deployed over
   ASGI/Agent Protocol. The graph entrypoints `supervisor_graph`, `ai_events_graph`,
   `pr_events_graph` are registered in
   [`langgraph.json`](../langgraph.json) for `langgraph dev` / LangSmith
   Deployments.

---

## 11. Output: the Russian digest

[`render_digest`](../src/events_parser/render.py) is a pure function producing a
Telegram-**HTML**-safe Russian message.

### Structure

```
<b>Дайджест событий — неделя от 8 июня 2026</b>

<b>🤖 События в сфере ИИ</b>

• «<title>» — 12 июня · онлайн · <host> · бесплатно — <a href="...">источник</a>
…

<b>📣 PR-события</b>
…

<b>🔓 Открытые события и вебинары по запросу</b>
…
```

- **Three sections:** AI events (dated, `domain==ai`), PR events (dated,
  `domain==pr`), and a combined **open** section for all undated events.
- **Free-first** ordering inside each section via `rank`.
- **Cost badges:** `бесплатно` / `платно` / `уточняется`.
- **Place label:** `онлайн` / `<location>` / `офлайн` / `формат уточняется`.
- **Date:** `<day> <month-in-Russian>` or `по запросу` for undated.
- **Russian typography:** guillemets `«»`, em-dashes `—`, middots `·`.
- **Safety:** every interpolated field is `html.escape`d, so titles/hosts with
  `<`, `>`, `&` can never break or inject into the message.
- **Empty run:** renders `На этой неделе новых событий не найдено.`

### Delivery

[`TelegramNotifier`](../src/events_parser/notify.py) POSTs to the Bot API
`sendMessage` with `parse_mode=HTML` and `disable_web_page_preview=true`. Messages
over Telegram's **4096-char** limit are split on newline boundaries (`split_message`),
hard-splitting any single over-long line. Bot API errors surface Telegram's own
reason (e.g. "chat not found", "can't parse entities") rather than a bare status
code.

> **Bot must be started.** Telegram blocks bot→user messages until the recipient
> presses **Start** on the bot. The target (`TELEGRAM_TARGET_CHAT_ID`) must have
> done this once, or delivery fails with "chat not found".

---

## 12. Deduplication & persistence

[`SeenStore`](../src/events_parser/seen_store.py) is a tiny SQLite table keyed by
`event_hash`:

```sql
CREATE TABLE seen_events (event_hash TEXT PRIMARY KEY, title TEXT, first_seen TEXT);
```

- **Intra-run dedup:** within `finish_digest`, a per-batch `set` collapses
  duplicates so the same event posted in two channels appears once.
- **Cross-week dedup:** `is_new(hash)` filters out anything already recorded.
- **Persist only after a real send.** Events are `mark_seen` **only** on a
  successful, non-dry delivery. A dry-run (or a failed send) marks nothing — so
  you can re-run safely while iterating.
- The DB path (`EVENTS_DB_PATH`, default `/data/seen.sqlite3`) lives on a Docker
  **named volume** (`events_data`), surviving restarts and redeploys. To wipe
  dedup history: `docker compose down && docker volume rm <project>_events_data`.

---

## 13. Triggers: cron & on-demand

Both routes call one `DigestRunner.run()`, which holds a non-blocking lock so a
manual trigger during a scheduled run (or a double-click) is skipped rather than
run concurrently.

| Trigger | How | Notes |
|---|---|---|
| **Weekly cron** | APScheduler `BackgroundScheduler` started in the FastAPI lifespan. | `DIGEST_SCHEDULE_CRON`, default `0 9 * * 1` = Mon 09:00 UTC = 12:00 MSK. `max_instances=1`, `coalesce=True`. |
| **`POST /trigger`** | Manual HTTP trigger. | Returns `{events, sent}` or `{status: skipped}`. |
| **`/digest` bot command** | `POST /telegram/webhook` handles the Telegram update. | Replies with progress + result in Russian. Requires the bot webhook to point here. |
| **CLI one-shot** | `python -m events_parser --live`. | The container's one-shot path; also the manual test entry. |

`GET /health` returns `{"status": "ok"}` for liveness checks.

---

## 14. Configuration reference

### Environment variables

Secrets live **only** in a gitignored `.env` (loaded by the CLI's minimal dotenv
reader, or via Docker `env_file`). Template: [`.env.example`](../.env.example).

| Var | Default | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | BotFather token for @kelva_events_bot (**required for delivery**) |
| `TELEGRAM_TARGET_CHAT_ID` | `142068037` | Recipient chat (must have pressed Start) |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` / `TELEGRAM_SESSION` | — | Telethon MTProto read; if unset → `t.me/s` preview |
| `TELETHON_MAX_MESSAGES` | `200` | Max messages scanned per channel |
| `TELEGRAM_USE_IPV6` | `false` | Dial Telegram DCs over IPv6 |
| `TELEGRAM_DC_ID` / `TELEGRAM_DC_IP` / `TELEGRAM_DC_PORT` | `0` / — / `443` | DC pin for IPv4-blackholing hosts |
| `YANDEX_API_KEY` / `YANDEX_FOLDER_ID` | — | Yandex FM auth (**required**) |
| `YANDEX_EXTRACT_MODEL` | `yandexgpt-lite/latest` | Extraction model |
| `YANDEX_AGENT_MODEL` / `YANDEX_DIGEST_MODEL` | `yandexgpt/latest` / `qwen3-235b-a22b-fp8` | Agent reasoning model |
| `YANDEX_OPENAI_BASE_URL` | `https://llm.api.cloud.yandex.net/v1` | OpenAI-compatible endpoint |
| `USE_AGENTS` | `true` (host) / `false` (CLI) | Agentic vs deterministic path |
| `LANGSMITH_TRACING` / `LANGSMITH_API_KEY` / `LANGSMITH_PROJECT` | `true` / — / `kelva-events-parser` | Tracing |
| `EVENTS_DB_PATH` | `/data/seen.sqlite3` | SQLite seen-store |
| `CHANNELS_CONFIG` | `channels.yaml` | Channel list path |
| `DIGEST_SCHEDULE_CRON` | `0 9 * * 1` | Weekly cron (UTC) |
| `HORIZON_DAYS` | `28` | Forward window |
| `SCAN_DAYS` | `7` | How far back to scan posts |
| `SEND_ON_EMPTY` | `true` | Send "no new events" when nothing qualifies |
| `DRY_RUN` | `false` | Render but don't send / don't mark seen |

### `channels.yaml`

A list of `{handle, domain}` entries; `domain` ∈ `{ai, pr}`. Validated on load —
an empty list, a missing handle, or an invalid domain raises immediately. Editing
this file (mounted read-only into the container) adds/removes channels with **no
code change**. Current set (verified live 2026-06-07):

- **AI:** `ITMeeting`, `freeitevent`, `iteventsrus`, `ai_machinelearning_big_data`
- **PR:** `companiesrbc`, `inter_comm`, `prexplore`, `roscongress`

---

## 15. Running it

### Local development (no network/LLM/Telegram)

```bash
uv run --extra dev pytest          # full unit suite, fast
python -m events_parser            # --demo: built-in sample event, proves shape
python -m events_parser --demo --dry-run
```

### Live one-shot (real deps from `.env`)

```bash
# dry run — scrape + extract + render, print, send nothing, mark nothing
uv run --extra runtime python -m events_parser --live --dry-run

# real — deliver a digest now and record seen events
uv run --extra runtime python -m events_parser --live

# force a path
uv run --extra runtime python -m events_parser --live --no-agents   # deterministic
uv run --extra runtime python -m events_parser --live --agents      # Deep Agents
```

### As the FastAPI host (scheduler + endpoints)

```bash
uv run --extra runtime uvicorn events_parser.app:app --host 0.0.0.0 --port 8080
curl -s localhost:8080/health           # {"status":"ok"}
curl -s -X POST localhost:8080/trigger  # fire a run on demand
```

---

## 16. Deployment

Single Docker container, **I/O-bound** (all inference is remote on Yandex FM), so
the box runs no model. Weekly cron needs **zero inbound** — only outbound HTTPS
(to `llm.api.cloud.yandex.net`, `api.telegram.org`, Telegram MTProto DCs, and
optionally `api.smith.langchain.com`).

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f --tail=50      # expect "scheduler started; weekly digest cron=..."
```

`restart: unless-stopped` keeps it alive across reboots; the `events_data` volume
persists the seen-store.

### Production specifics (ProCloud RU VPS)

The live deployment is on an **IPv6-only-egress** RU VPS, which blackholes
outbound IPv4 to Telegram DCs, PyPI, and ghcr.io. The repo is configured for this:

- **Dockerfile** installs `uv` from PyPI (not `ghcr.io/astral-sh/uv`).
- **docker-compose.yml** uses `build.network: host` (IPv6 at build time for
  `uv sync`) and `network_mode: host` (IPv6 at runtime for Telegram). The app
  binds `127.0.0.1:8080` — never publicly exposed; cron-only needs no inbound.
- **`.env`** opts into IPv6 + a DC pin (see §8).

Full host requirements, hardening, and the IPv6 section are in
[`DEPLOY.md`](DEPLOY.md). Redeploy: `git pull && docker compose up -d --build`.

---

## 17. Access & operations

The production VPS is hardened with a non-root sudo user, SSH on a **non-default
port** (key-only, root login + password auth disabled), `ufw` allowing the SSH
port only, `fail2ban`, `unattended-upgrades`, and MSK timezone.

### SSH access

On some RU networks, direct SSH to the box is disrupted by ISP-level DPI
(**ТСПУ**), which fingerprints the SSH flow and drops it at the identification
exchange — independent of the cloud provider, the server's firewall, and the
client machine. The robust fix is a **Tailscale** tunnel: SSH runs over WireGuard,
which the DPI cannot match, so access works from any network. A ProxyJump through
a second (unaffected) host is the fallback when not on the tailnet.

> Concrete host addresses, aliases, and tunnel coordinates are kept in internal
> ops notes, not in this repository.

---

## 18. Observability

Set `LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY` and every LLM call and agent
step appears in the **`kelva-events-parser`** LangSmith project. This is the
primary tool for debugging extraction quality and seeing where an agentic run
failed. Container logs (`docker compose logs`) cover the deterministic path and
scheduler lifecycle (`scheduler started; weekly digest cron=...`).

---

## 19. Testing

```bash
uv run --extra dev pytest
```

The suite (`tests/`) covers every module through its public interface with
in-memory fakes:

- `test_rules.py` — cost classification, horizon edges, free-first ranking
  (highest-bug-risk logic).
- `test_preview.py` — HTML parsing + pagination against **real fixtures**
  (`tests/fixtures/telegram_page*.html`), so scraping drift is detectable.
- `test_extraction.py` — extraction with a fake structured LLM (blanks, retries,
  content-filter skip).
- `test_render.py` — digest structure, sections, escaping, empty message.
- `test_seen_store.py` — dedup new/seen, persistence.
- `test_notify.py` — message splitting, Bot API error surfacing.
- `test_orchestrator.py` / `test_runner.py` — end-to-end pipeline + overlap guard
  with fakes.
- `test_telethon.py` — pure helpers (`message_to_rawpost`, `filter_recent`).
- `test_config.py` — channel validation.

Good tests here exercise **behavior through public APIs**, not implementation
details, so they survive refactors. No test touches the network, an LLM, or
Telegram.

---

## 20. Security model

- **Secrets live only in a gitignored `.env`** (bot token, Yandex key+folder,
  Telethon `api_id`/`api_hash`/`session`, LangSmith key). Nothing sensitive is
  committed. The standalone GitHub repo was created via `git archive` to guarantee
  no secret history.
- **The Telethon session is a credential** equivalent to the logged-in account —
  treat it like a password. Minted once, never committed, transferred to the VPS
  out-of-band.
- **No inbound required.** The cron deployment binds loopback only; `ufw` exposes
  nothing publicly.
- **Outbound delivery target** is the operator's own Telegram chat via the
  product bot — not an external recipient.
- The bot can only message users who have pressed **Start** (Telegram's
  anti-spam), which also bounds who can receive the digest.

---

## 21. Operations runbook

### Smoke-test after deploy (don't wait for Monday)

```bash
docker compose run --rm events-parser \
  uv run --extra runtime python -m events_parser --live --dry-run     # preview, sends nothing
docker compose run --rm events-parser \
  uv run --extra runtime python -m events_parser --live               # real send + records seen
# or, against the running host:
curl -s -X POST localhost:8080/trigger
```

### Add / remove / reorder a channel

1. Edit `channels.yaml` (handle without `@`, `domain: ai|pr`).
2. Verify it on `https://t.me/s/<handle>` (must have a public preview, or use the
   Telethon reader).
3. `docker compose up -d --build` (or just restart — the file is mounted RO).

### Rotate secrets

Edit `.env` on the VPS (in the project directory) → `docker compose up -d`
(recreates the container with new env). Never bake secrets into the image.

### Re-mint the Telethon session

If the session is invalidated, run `scripts/telethon_login.py` on a trusted
machine, paste the new `TELEGRAM_SESSION` into `.env`, redeploy.

### Wipe dedup history (resend everything)

```bash
docker compose down && docker volume rm <project>_events_data && docker compose up -d
```

### Redeploy after a code change

```bash
git pull && docker compose up -d --build
```

---

## 22. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Delivery fails "chat not found" | Target never pressed Start on the bot | Open @kelva_events_bot, press Start |
| `telethon ... Connection to Telegram failed` | Host blackholes DC IPv4 | Set `TELEGRAM_USE_IPV6=true` + DC pin (§8) |
| `uv sync ... operation timed out` at build | IPv6-only host, PyPI over IPv4 | `build.network: host` in compose (already set) |
| `ghcr.io ... TLS handshake timeout` at build | ghcr.io unreachable | Dockerfile installs `uv` from PyPI (already set) |
| Empty digest every week | scan/horizon too tight, or channels dead | Check `SCAN_DAYS`/`HORIZON_DAYS`; verify channels on `t.me/s` |
| Events reappear weekly | seen-store volume not persisted | Confirm `events_data` volume mounted at `EVENTS_DB_PATH` |
| Extraction returns nothing for a post | Yandex content filter, or it's not an event | Expected for news/ads; check LangSmith trace |
| Direct SSH fails on a RU network | ISP DPI (ТСПУ) on the SSH flow | Connect over the Tailscale tunnel, or use the ProxyJump fallback |
| One channel breaks the run | — | It won't: failed channels are logged and skipped |

---

## 23. File map & glossary

### Repository layout

```
kelvatech-telegram-events-parser/
├── src/events_parser/        # the package (see §5)
├── tests/                    # unit suite + HTML fixtures
├── scripts/                  # telethon_login.py, tdata_to_session.py
├── docs/
│   ├── PRD.md                # product spec & user stories
│   ├── DEPLOY.md             # VPS deploy runbook
│   ├── MANUAL.md             # this document
│   └── issues/               # build backlog S01–S12
├── channels.yaml             # scanned channels (handle + domain)
├── .env.example              # env template (copy to gitignored .env)
├── pyproject.toml            # deps: core + runtime/dev extras (uv)
├── Dockerfile                # single-container build
├── docker-compose.yml        # host networking, named volume, restart policy
├── langgraph.json            # async-subagent graph registry
└── assets/                   # brand social-preview
```

### Glossary

- **Domain** — `ai` or `pr`; routes a channel to its subagent and digest section.
- **Horizon** — the forward window (default 28 days) an event must fall within.
- **Open / rolling event** — an undated event (e.g. on-demand webinar) kept in its
  own section.
- **`event_hash`** — the dedup identity (normalized title + day + host, sha256[:16]).
- **Deterministic path** — collection via a plain loop (no agent).
- **Agentic path** — collection via the Deep Agents supervisor + subagents.
- **Seam** — an injectable boundary (Fetch/Extractor/SeenStore/Notifier) that makes
  the pipeline testable with fakes.
- **ТСПУ (TSPU)** — Russia's ISP-level DPI; the reason direct SSH is tunneled via
  Tailscale (see §17).

---

*Maintained alongside the code. When behavior changes, update this manual in the
same commit.*

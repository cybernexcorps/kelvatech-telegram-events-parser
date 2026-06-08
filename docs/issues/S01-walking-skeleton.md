# S01 — Walking skeleton (end-to-end spine)

**Type:** AFK · **Parent:** docs/PRD.md · **Stories:** 15, 19, 22, 31, 32

## What to build

The thinnest complete thread through every layer. A `run_digest(now, config, deps)`
orchestrator that takes a single hardcoded fake `RawPost`, runs it through a fake extractor
→ a real (trivial) renderer → a dry-run notifier that prints the digest. Define the `Event`
Pydantic model (the shared schema every later slice uses). Stand up the uv project, a minimal
FastAPI app, and a Dockerfile so `docker run` executes one digest cycle and prints output.
Everything is injectable via `deps` (fetch_client, chat_model, seen_store, notifier, clock).

## Acceptance criteria

- [ ] `uv` project with `pyproject.toml`; `uv run` works
- [ ] `Event` Pydantic model defined per PRD data model (all fields incl. derived `event_hash`)
- [ ] `run_digest(now, config, deps)` exists; all external dependencies injected, no globals
- [ ] Orchestrator test: with all-fake deps, asserts a non-empty digest string is produced and the notifier is called exactly once
- [ ] Dry-run mode renders to stdout and sends nothing
- [ ] `Dockerfile` builds; `docker run <img>` executes one cycle and prints a digest
- [ ] LangSmith env vars read (no-op when absent, no crash)

## Blocked by

None - can start immediately

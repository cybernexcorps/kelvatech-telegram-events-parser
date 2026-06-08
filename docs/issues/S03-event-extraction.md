# S03 — Event extraction (Yandex structured output)

**Type:** AFK · **Parent:** docs/PRD.md · **Stories:** 20, 21, 26

## What to build

`EventExtractor.extract(post) -> Event[]` that calls an LLM with **structured output** to turn
one `RawPost` into zero-or-more `Event` records (a post may announce several events or none).
Default extraction model `yandexgpt-lite` via Yandex Foundation Models; model id env-configurable.
Malformed/unparseable LLM output is retried once, then skipped-with-log (never a silent
placeholder, never a crash). The real Yandex call path is gated behind env (off in unit tests,
which use a fake chat model returning canned structured output).

## Acceptance criteria

- [ ] `extract(post)` returns typed `Event[]`; populates title, type, dates, host, cost fields, source refs, domain
- [ ] Post announcing multiple events → multiple `Event`s; non-event post → `[]`
- [ ] Malformed model output → one retry → skip-with-log; run never crashes
- [ ] Fake chat model used in tests; no live Yandex call in unit suite
- [ ] Model id (and provider base url for OpenAI-compatible open models) read from env
- [ ] LLM call emits a LangSmith span when tracing enabled

## Blocked by

- S01

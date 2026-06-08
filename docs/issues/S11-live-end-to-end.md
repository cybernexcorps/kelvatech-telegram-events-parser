# S11 — Live end-to-end in Docker + LangSmith (done-line)

**Type:** HITL · **Parent:** docs/PRD.md · **Stories:** 32 + full integration

## What to build

The done-line: one **real** weekly cycle running **inside the Docker container** —
real confirmed channels (S10) → real `t.me/s` fetch (S02) → real Yandex extraction (S03) →
classify/horizon/rank (S04) → dedup (S05) → RU render (S06) → deliver to Telegram chat
142068037 via the dedicated bot (S07), coordinated by the supervisor + async subagents (S08),
with the whole run visible as a **LangSmith trace tree**.

**HITL:** requires real secrets (bot token, Yandex key + folder, LangSmith key) and a human to
verify the delivered digest and the trace.

## Acceptance criteria

- [ ] `docker run` (with secrets) completes one full cycle end-to-end
- [ ] A Russian digest is delivered to chat 142068037, free events first, sectioned by domain
- [ ] Events are real, in-horizon, deduped; source links resolve
- [ ] The run appears as a single LangSmith trace tree (supervisor + ai/pr subagents + LLM spans)
- [ ] A second immediate run sends nothing new (dedup proven live)
- [ ] One unreachable channel does not abort the run (resilience proven live)
- [ ] Run instructions documented in the project README

## Blocked by

- S02, S03, S04, S05, S06, S07, S08, S09, S10

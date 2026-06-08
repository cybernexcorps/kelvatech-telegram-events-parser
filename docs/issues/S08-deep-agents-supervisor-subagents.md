# S08 — Deep Agents supervisor + 2 async subagents (ACP/ASGI)

**Type:** AFK · **Parent:** docs/PRD.md · **Stories:** 1, 2, 17, 18, 29

## What to build

The multi-agent layer over the already-tested seams. A **supervisor** `create_deep_agent`
coordinates two **async subagents** — `ai-events` and `pr-events` — each owning its domain's
channels and calling `fetch_posts` + `extract_events` as tools. Subagents run concurrently over
the **Agent Protocol (ACP)**, **co-deployed via ASGI** (same container, no external URL). The
supervisor merges subagent results, then hands off to the existing dedup → rank → render →
deliver path. Deep Agents middleware: `TodoListMiddleware` (planning), `FilesystemMiddleware`
(offload large `t.me/s` HTML out of context), per-subagent context quarantine. All steps traced
in LangSmith.

## Acceptance criteria

- [ ] Supervisor delegates AI vs PR channels to the matching async subagent by `channels.yaml` domain tag
- [ ] Subagents run concurrently over ACP co-deployed (ASGI transport, no URL)
- [ ] Subagent tools = the S02 `fetch_posts` and S03 `extract_events` seams (no logic duplication)
- [ ] Large HTML offloaded via FilesystemMiddleware, not dumped into supervisor context
- [ ] One agent run produces a single LangSmith trace tree showing supervisor + both subagents
- [ ] Merged subagent output feeds the existing dedup/rank/render/deliver path unchanged

## Blocked by

- S02
- S03

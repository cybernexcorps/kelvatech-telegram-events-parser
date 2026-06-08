# S04 — Rules: classify_cost + within_horizon + rank

**Type:** AFK · **Parent:** docs/PRD.md · **Stories:** 3, 4, 5, 6

## What to build

Three **pure functions** carrying the highest-bug-risk rules:

- `classify_cost(event) -> {free, paid, unknown}` — normalizes/derives cost status.
- `within_horizon(event, now) -> bool|"open"` — dated events kept only if start date ∈ [now, now+28d]; undated/rolling events routed to the "open" bucket; past events dropped.
- `rank(events) -> Event[]` — orders **free before paid before unknown**, then by date ascending; stable within ties.

Horizon days configurable (default 28). Wire all three into `run_digest`.

## Acceptance criteria

- [ ] `classify_cost` exhaustively unit-tested incl. ambiguous/unknown inputs
- [ ] `within_horizon` boundary tests: today, now+28d edge, now+29d (excluded), past (dropped), undated (→ open)
- [ ] `rank` proves free-first ordering and stable tie-breaking by date
- [ ] Horizon window is config-driven, not hardcoded
- [ ] Functions are pure (no I/O, deterministic given `now`)
- [ ] Integrated into `run_digest` between extraction and rendering

## Blocked by

- S01

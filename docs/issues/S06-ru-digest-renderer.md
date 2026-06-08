# S06 — RU digest renderer

**Type:** AFK · **Parent:** docs/PRD.md · **Stories:** 8, 10, 24, 30

## What to build

`render_digest(ranked_events, *, now) -> str` producing a **Russian-language** digest:
sectioned by domain (AI events / PR events), **free events first** within each section, plus a
separate **"open/rolling"** section for undated events. Each event shows what, when,
where/online, host, cost status, and a **source link**. Russian typography («», em-dashes,
"10 000" number format). When there are zero new events, render a graceful "no new events this
week" message (configurable to stay silent). Pure function — no I/O.

## Acceptance criteria

- [ ] Output sectioned by domain; free-before-paid order within each section verified
- [ ] Undated/rolling events render in their own "open" section
- [ ] Each event line includes source link + cost status + date/online
- [ ] Russian typography applied («», —, "10 000")
- [ ] Empty input → "no new events" message (or empty when configured silent)
- [ ] Golden/structural tests assert section presence and ordering; pure (deterministic given `now`)

## Blocked by

- S01 (consumes S04 ordering)

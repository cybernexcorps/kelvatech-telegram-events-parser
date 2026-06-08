# S10 — Channel research + channels.yaml

**Type:** HITL (user confirms channels) · **Parent:** docs/PRD.md · **Stories:** 11, 29

## What to build

Research active **RU Telegram channels** that announce (a) **AI-field events**
(conferences/meetups/webinars) and (b) **PR-field events**. Propose a shortlist with rationale
(activity, relevance, event density), get user confirmation, and populate `channels.yaml` with
per-channel `{handle, domain: ai|pr}`. The list is swappable without code changes; the `domain`
tag is what routes a channel to the correct subagent (S08).

**HITL:** user confirms the final channel set before it's wired for the live run.

## Acceptance criteria

- [ ] Shortlist of candidate AI-event and PR-event channels proposed with rationale
- [ ] User confirms the final set
- [ ] `channels.yaml` populated with `{handle, domain}` per channel; schema documented
- [ ] Config loads and validates at startup; bad/empty config fails fast with a clear error
- [ ] Adding/removing/reordering a channel requires no code change

## Blocked by

None - can start immediately (confirmation gates the live run, S11)

# S05 — SeenStore dedup (SQLite)

**Type:** AFK · **Parent:** docs/PRD.md · **Stories:** 7, 16, 27

## What to build

`SeenStore` backed by SQLite: `is_new(event_hash)` and `mark_seen(event)`. `event_hash` is a
stable derivation of normalized title + date + host, so the **same event posted in multiple
channels collapses to one hash** (intra-run dedup) and **an event seen in a prior week is not
re-sent** (cross-week dedup). DB file lives on a mounted Docker volume so it survives restarts.
Wire into `run_digest`: only new events reach the digest; sent events are marked.

## Acceptance criteria

- [ ] `event_hash` stable: same logical event across channels/posts → identical hash
- [ ] `is_new` true for unseen, false after `mark_seen`
- [ ] Cross-week: re-running the same week sends nothing new (idempotent)
- [ ] Intra-run: duplicate events within one run deduped before rendering
- [ ] Tests use in-memory SQLite; no file/volume needed in unit suite
- [ ] DB path configurable (defaults to a volume-mounted location in Docker)

## Blocked by

- S01

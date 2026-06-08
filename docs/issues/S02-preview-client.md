# S02 — Telegram preview client (t.me/s parsing)

**Type:** AFK · **Parent:** docs/PRD.md · **Stories:** 9, 23, 25

## What to build

`PreviewClient.fetch_posts(channel, before=None) -> RawPost[]` that fetches the public
`https://t.me/s/{channel}` HTML preview (httpx), parses post blocks (selectolax) into
`RawPost` records (text, post id, datetime, permalink), and supports backward pagination via
`?before=<id>`. No Telegram credentials. A channel that is unreachable or has no preview is
logged and yields an empty list (the run continues). Wire the client in behind `deps` so
`run_digest` can use it instead of the fake.

## Acceptance criteria

- [ ] `fetch_posts` parses saved `t.me/s` HTML **fixtures** into correct `RawPost[]` (text, id, dt, permalink)
- [ ] Pagination: passing `before=<id>` requests the correct earlier page; cursor extracted from the page
- [ ] Unreachable/empty channel → `[]` + a logged warning, no exception
- [ ] At least 2 HTML fixtures committed (a normal page + an empty/edge page)
- [ ] No network calls in the unit suite
- [ ] `run_digest` can be driven by the real client over fixtures end-to-end

## Blocked by

- S01

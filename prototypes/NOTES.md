# Prototype verdict — t.me/s preview parsing + pagination

**Question:** Does `PreviewClient.fetch_posts` via the public `t.me/s/{channel}` web preview,
paginated by `?before=<id>`, actually work? (de-risks S02)

**Answer: YES — confirmed against a real channel (`t.me/s/telegram`, 2026-06-07).**

## Confirmed selectors (selectolax / CSS) — these go into S02

| Field | Selector | Source |
|---|---|---|
| post block | `div.tgme_widget_message` | 20 per page |
| message id | block attr `data-post` → `"{channel}/{id}"`, take last segment as int | e.g. `telegram/425` |
| text | `.tgme_widget_message_text` → `.text(separator="\n", strip=True)` | |
| permalink | `a.tgme_widget_message_date` → `href` | `https://t.me/telegram/425` |
| **datetime** | **`a.tgme_widget_message_date time` → `datetime` attr** | ISO `2026-02-10T17:43:45+00:00` |

## Gotcha caught by the prototype
`css_first("time")` matches the **video-duration** `<time class="message_video_duration">`
(no `datetime` attr) BEFORE the real post `<time datetime=... class="time">`. **Must** scope to
`a.tgme_widget_message_date time` (or `time.time`), not a bare `time`. This bug would have
shipped silently (null dates) without the prototype.

## Pagination — confirmed
- Page 1 (`/s/telegram`): ids **425–445** (20 posts).
- Page 2 (`/s/telegram?before=425`): ids **405–424** (20 posts), **zero overlap**.
- Rule: `?before=<min id of current page>` returns the next-older 20. Loop until the scan
  window (7 days) is covered or a page returns 0 posts.

## Notes for S02
- Pin a desktop `User-Agent`; default urllib UA may be throttled. httpx in prod.
- 20 posts/page is the page size; budget ~1–2 pages/week for typical channels.
- Fixtures captured: `tests/fixtures/telegram_page1.html`, `telegram_page2_before425.html`
  (real markup — reuse as the S02 test fixtures; rename to neutral names when absorbed).
- Some posts have no text (media-only) → `text == ""`; extractor should skip empties.

**Status:** prototype answered its question. Delete `proto_tme_preview.py` when S02 absorbs the
selectors. Fixtures are kept and reused by S02 tests.

"""S02 — t.me/s preview client: parse fixtures + ?before= pagination + skip-on-failure."""
from pathlib import Path

import pytest

from events_parser.preview import PreviewClient, build_preview_url, parse_preview

FIX = Path(__file__).parent / "fixtures"
PAGE1 = (FIX / "telegram_page1.html").read_text(encoding="utf-8")
PAGE2 = (FIX / "telegram_page2_before425.html").read_text(encoding="utf-8")


def test_parse_preview_extracts_posts_from_real_html():
    posts = parse_preview(PAGE1, "telegram")
    assert len(posts) == 20
    p = posts[0]
    assert p.id == 425
    assert p.channel == "telegram"
    assert p.permalink == "https://t.me/telegram/425"
    assert p.text  # non-empty
    # datetime parsed from the message <time datetime=...>, not the video-duration <time>
    assert p.dt is not None
    assert p.dt.year == 2026


def test_build_preview_url_handles_pagination_cursor():
    assert build_preview_url("ai_chan") == "https://t.me/s/ai_chan"
    assert build_preview_url("ai_chan", before=425) == "https://t.me/s/ai_chan?before=425"


def test_fetch_posts_uses_before_cursor_for_older_page():
    calls = []

    def fake_get(url):
        calls.append(url)
        return PAGE2 if "before=425" in url else PAGE1

    client = PreviewClient(http_get=fake_get)
    page1 = client.fetch_posts("telegram")
    page2 = client.fetch_posts("telegram", before=min(p.id for p in page1))

    assert calls == ["https://t.me/s/telegram", "https://t.me/s/telegram?before=425"]
    ids1 = {p.id for p in page1}
    ids2 = {p.id for p in page2}
    assert max(ids2) < min(ids1)          # page2 is strictly older
    assert ids1.isdisjoint(ids2)          # no overlap


def test_unreachable_channel_yields_empty_and_does_not_raise():
    def boom(url):
        raise RuntimeError("network down")

    client = PreviewClient(http_get=boom)
    assert client.fetch_posts("dead_chan") == []


def test_blank_html_yields_empty():
    assert parse_preview("<html><body></body></html>", "x") == []


def test_fetch_recent_paginates_until_pages_run_out():
    pages = {
        "https://t.me/s/telegram": PAGE1,
        "https://t.me/s/telegram?before=425": PAGE2,
        "https://t.me/s/telegram?before=405": "<html></html>",  # empty → stop
    }
    client = PreviewClient(http_get=lambda url: pages[url])
    posts = client.fetch_recent("telegram", max_pages=5)
    assert len(posts) == 40                      # both non-empty pages collected
    assert len({p.id for p in posts}) == 40      # de-duplicated across pages


def test_fetch_recent_respects_max_pages():
    client = PreviewClient(http_get=lambda url: PAGE1)  # always returns same page
    posts = client.fetch_recent("telegram", max_pages=2)
    # 20 unique ids even though 2 pages fetched (same ids) — capped, no infinite loop
    assert len({p.id for p in posts}) == 20

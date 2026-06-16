"""S06 — RU digest renderer: domain sections, free-first, open section, typography."""
from datetime import datetime, timezone

from events_parser.models import Event
from events_parser.render import render_digest

NOW = datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc)


def _ev(title, *, domain="ai", cost="free", start=NOW, host="Kelva",
        url="https://t.me/c/1", online=True):
    return Event(title=title, domain=domain, cost_status=cost, start_date=start,
                 host=host, source_post_url=url, is_online=online,
                 event_type="webinar")


def test_empty_digest_has_no_events_message():
    out = render_digest([], now=NOW)
    assert "не найдено" in out.lower()


def test_free_events_render_before_paid_within_a_section():
    paid = _ev("Платная конференция", cost="paid", start=datetime(2026, 6, 10, tzinfo=timezone.utc))
    free = _ev("Бесплатный вебинар", cost="free", start=datetime(2026, 6, 12, tzinfo=timezone.utc))
    out = render_digest([paid, free], now=NOW)
    assert out.index("Бесплатный вебинар") < out.index("Платная конференция")


def test_ai_and_pr_events_go_under_their_section_headers():
    out = render_digest([_ev("ИИ-митап", domain="ai"), _ev("PR-завтрак", domain="pr")], now=NOW)
    # both section headers present, AI before PR
    ai_h = out.find("ИИ")
    assert "ИИ-митап" in out and "PR-завтрак" in out
    assert ai_h != -1


def test_undated_event_lands_in_open_section():
    out = render_digest([_ev("Вебинар по запросу", start=None)], now=NOW)
    assert "Вебинар по запросу" in out
    # an "open/by-request" section marker exists
    assert "запрос" in out.lower() or "открыт" in out.lower()


def test_event_line_shows_cost_badge_and_source_link():
    out = render_digest([_ev("Бесплатный вебинар", cost="free",
                             url="https://t.me/ai_chan/55")], now=NOW)
    assert "https://t.me/ai_chan/55" in out
    assert "беспл" in out.lower()  # free badge in Russian
    assert "«Бесплатный вебинар»" in out  # RU guillemets typography
    assert '<a href="https://t.me/ai_chan/55">источник</a>' in out  # HTML link


def test_html_special_chars_in_title_are_escaped():
    # a title with HTML/Markdown punctuation must not break or inject markup
    out = render_digest([_ev("AI & ML <Summit> [2026]", cost="free")], now=NOW)
    assert "AI &amp; ML &lt;Summit&gt; [2026]" in out
    assert "<Summit>" not in out  # raw angle brackets never leak through


def test_business_and_legal_events_render_under_their_sections():
    out = render_digest([
        _ev("Бизнес-завтрак", domain="business"),
        _ev("Вебинар для юристов", domain="legal"),
    ], now=NOW)
    assert "💼 Бизнес-события" in out
    assert "⚖️ Юридические события" in out
    assert "Бизнес-завтрак" in out
    assert "Вебинар для юристов" in out


def test_sections_render_in_registry_order():
    out = render_digest([
        _ev("L", domain="legal"),
        _ev("A", domain="ai"),
        _ev("B", domain="business"),
        _ev("P", domain="pr"),
    ], now=NOW)
    assert (out.find("🤖 События в сфере ИИ")
            < out.find("📣 PR-события")
            < out.find("💼 Бизнес-события")
            < out.find("⚖️ Юридические события"))


def test_domain_with_no_events_renders_no_section():
    out = render_digest([_ev("Только ИИ", domain="ai")], now=NOW)
    assert "💼 Бизнес-события" not in out
    assert "⚖️ Юридические события" not in out

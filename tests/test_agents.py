"""S08 agentic collection — the subagent tools route fetch through the shared
ChannelFetchResult seam, so a failed channel is recorded into the collector
(not silently empty). _build_tools takes injected fetch/extractor for testing;
the deepagents supervisor itself stays live-validated.
"""
from datetime import datetime, timedelta, timezone

from events_parser.agents import EventCollector, _build_tools
from events_parser.models import ChannelFetchResult, Event, RawPost

NOW = datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc)


class FakeFetch:
    def __init__(self, posts_by_channel, fail=()):
        self._by = posts_by_channel
        self._fail = set(fail)

    def fetch_recent(self, channel, since=None):
        if channel in self._fail:
            return ChannelFetchResult.failed(channel, "boom")
        return ChannelFetchResult.succeeded(channel, list(self._by.get(channel, [])))


class FakeExtractor:
    def extract(self, post):
        return [Event(title=f"E{post.id}", host="H", cost_status="free", domain="ai",
                      start_date=NOW + timedelta(days=5))]


def _post(pid, channel):
    return RawPost(id=pid, channel=channel, text="x", dt=NOW)


def _extract_tool(collector, fetch):
    _, extract_and_record = _build_tools(collector, scan_days=7, fetch=fetch,
                                         extractor=FakeExtractor())
    return extract_and_record


def test_agentic_tool_records_events_for_healthy_channel():
    collector = EventCollector()
    tool = _extract_tool(collector, FakeFetch({"ai_chan": [_post(1, "ai_chan")]}))

    msg = tool.invoke({"channel": "ai_chan", "domain": "ai"})

    assert len(collector.events) == 1
    assert collector.failures == []
    assert "1" in msg  # "recorded 1 events"


def test_agentic_tool_records_failure_for_unreachable_channel():
    collector = EventCollector()
    tool = _extract_tool(collector, FakeFetch({}, fail={"dead_chan"}))

    msg = tool.invoke({"channel": "dead_chan", "domain": "ai"})

    assert collector.events == []
    assert collector.failures == ["dead_chan"]   # surfaced, not silently empty
    assert "dead_chan" in msg


from events_parser.agents import build_subagent_specs
from events_parser.config import Config


def test_build_subagent_specs_one_per_configured_domain():
    config = Config(channels=[
        ("ai1", "ai"), ("pr1", "pr"),
        ("biz1", "business"), ("biz2", "business"),
        ("law1", "legal"),
    ])
    specs = build_subagent_specs(config)

    assert [s["name"] for s in specs] == [
        "ai-events", "pr-events", "business-events", "legal-events"
    ]
    biz = next(s for s in specs if s["name"] == "business-events")
    assert "biz1" in biz["system_prompt"] and "biz2" in biz["system_prompt"]
    assert "ai1" not in biz["system_prompt"]
    assert "domain='business'" in biz["system_prompt"]
    # pure path attaches no tools unless asked
    assert "tools" not in biz


def test_build_subagent_specs_skips_domains_with_no_channels():
    config = Config(channels=[("ai1", "ai")])
    specs = build_subagent_specs(config)
    assert [s["name"] for s in specs] == ["ai-events"]


def test_async_subagent_specs_cover_every_domain():
    from events_parser.agents import async_subagent_specs
    from events_parser.models import DOMAINS

    graph_ids = {s["graphId"] for s in async_subagent_specs()}
    assert graph_ids == {f"{d}_events" for d in DOMAINS}

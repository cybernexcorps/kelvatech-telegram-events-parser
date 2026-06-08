"""S03 — EventExtractor: structured output → Event[], retry-once-then-skip."""
from datetime import datetime, timezone

from events_parser.extraction import EventExtractor, ExtractedEvent, ExtractionResult
from events_parser.models import RawPost

POST = RawPost(
    id=55, channel="ai_chan", text="Бесплатный вебинар 15 июня",
    dt=datetime(2026, 6, 6, tzinfo=timezone.utc), permalink="https://t.me/ai_chan/55",
)


class FakeLLM:
    """Stand-in for an LLM bound with .with_structured_output(ExtractionResult)."""

    def __init__(self, result=None, *, fail_times=0, exc=ValueError("bad json")):
        self._result = result
        self._fail_times = fail_times
        self._exc = exc
        self.calls = 0

    def invoke(self, _input):
        self.calls += 1
        if self.calls <= self._fail_times:
            raise self._exc
        return self._result


def test_maps_extracted_event_to_full_event_with_source_fields():
    llm = FakeLLM(ExtractionResult(events=[
        ExtractedEvent(title="Вебинар по ИИ", event_type="webinar",
                       start_date=datetime(2026, 6, 15, tzinfo=timezone.utc),
                       host="AI Chan", cost_status="free")
    ]))
    out = EventExtractor(llm).extract(POST)
    assert len(out) == 1
    e = out[0]
    assert e.title == "Вебинар по ИИ"
    assert e.source_channel == "ai_chan"
    assert e.source_post_url == "https://t.me/ai_chan/55"
    assert e.source_post_dt == POST.dt
    assert e.event_hash  # derived


def test_one_post_can_yield_multiple_events():
    llm = FakeLLM(ExtractionResult(events=[
        ExtractedEvent(title="A", event_type="meetup"),
        ExtractedEvent(title="B", event_type="conference"),
    ]))
    assert [e.title for e in EventExtractor(llm).extract(POST)] == ["A", "B"]


def test_non_event_post_yields_empty():
    assert EventExtractor(FakeLLM(ExtractionResult(events=[]))).extract(POST) == []


def test_retries_once_then_succeeds():
    llm = FakeLLM(ExtractionResult(events=[ExtractedEvent(title="X", event_type="other")]),
                  fail_times=1)
    out = EventExtractor(llm, retries=1).extract(POST)
    assert [e.title for e in out] == ["X"]
    assert llm.calls == 2  # failed once, retried, succeeded


def test_persistent_failure_skips_with_empty_and_does_not_raise():
    llm = FakeLLM(fail_times=99)
    out = EventExtractor(llm, retries=1).extract(POST)
    assert out == []
    assert llm.calls == 2  # initial + one retry, then give up


def test_literal_null_strings_coerced_to_none():
    # yandexgpt-lite sometimes emits the string "null" instead of a real null.
    llm = FakeLLM(ExtractionResult(events=[
        ExtractedEvent(title="Saint HighLoad++", event_type="conference",
                       host="null", location="—")
    ]))
    e = EventExtractor(llm).extract(POST)[0]
    assert e.host is None
    assert e.location is None


def test_content_filter_rejection_is_not_retried():
    # Yandex content-filter rejections are deterministic; retrying wastes a call.
    llm = FakeLLM(fail_times=99,
                  exc=ValueError("Could not parse response content as the request "
                                 "was rejected by the content filter"))
    out = EventExtractor(llm, retries=1).extract(POST)
    assert out == []
    assert llm.calls == 1  # no retry on content-filter rejection

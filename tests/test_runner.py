"""S09 — DigestRunner: invokes the pipeline + guards against overlapping runs."""
from datetime import datetime, timedelta, timezone

from events_parser.config import Config
from events_parser.models import Event, RawPost
from events_parser.orchestrator import Deps
from events_parser.runner import DigestRunner

NOW = datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc)


def _deps(on_fetch=None):
    class _Fetch:
        def fetch_recent(self, channel, since=None):
            if on_fetch:
                on_fetch()
            return [RawPost(id=1, channel=channel, text="x", dt=NOW,
                            permalink="https://t.me/c/1")]

    class _Extractor:
        def extract(self, post):
            return [Event(title="E", host="H", cost_status="free",
                          start_date=NOW + timedelta(days=3), domain="ai",
                          source_post_url="https://t.me/c/1")]

    class _Seen:
        def is_new(self, h): return True
        def mark_seen(self, e): pass

    class _Notifier:
        def __init__(self): self.sent = []
        def send(self, chat_id, text): self.sent.append(text)

    return Deps(fetch=_Fetch(), extractor=_Extractor(), seen_store=_Seen(), notifier=_Notifier())


def test_runner_runs_the_pipeline():
    cfg = Config(channels=[("ai_chan", "ai")], target_chat_id=1, dry_run=True)
    runner = DigestRunner(lambda: NOW, cfg, _deps())
    result = runner.run()
    assert result is not None
    assert "E" in result.digest_text


def test_overlapping_run_is_skipped():
    cfg = Config(channels=[("ai_chan", "ai")], target_chat_id=1, dry_run=True)
    nested = {}

    def reenter():
        # called from inside the pipeline (during fetch) — the guard must reject it
        nested["result"] = runner.run()

    runner = DigestRunner(lambda: NOW, cfg, _deps(on_fetch=reenter))
    outer = runner.run()

    assert outer is not None
    assert nested["result"] is None  # the re-entrant run was guarded out

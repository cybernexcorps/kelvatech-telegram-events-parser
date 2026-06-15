"""S09 — DigestRunner: invokes the pipeline + guards against overlapping runs."""
import threading
from datetime import datetime, timedelta, timezone

from events_parser.config import Config
from events_parser.models import Event, RawPost
from events_parser.orchestrator import Deps
from events_parser.runner import DigestRunner
from events_parser.seen_store import SeenStore

NOW = datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc)

# A single, stable event the worker-thread regression test can also hash to assert
# the seen-store was written (dedup persisted) across the thread boundary.
WORKER_EVENT = Event(title="E", host="H", cost_status="free",
                     start_date=NOW + timedelta(days=3), domain="ai",
                     source_post_url="https://t.me/c/1")


def _real_seen_deps(db_path):
    """Deps wired to a REAL file-backed SeenStore (the thread-affine collaborator),
    with fetch/extract/notify faked. The connection is opened in whatever thread
    builds these deps — the digest run may execute in another."""
    class _Fetch:
        def fetch_recent(self, channel, since=None):
            return [RawPost(id=1, channel=channel, text="x", dt=NOW,
                            permalink="https://t.me/c/1")]

    class _Extractor:
        def extract(self, post):
            return [WORKER_EVENT]

    class _Notifier:
        def __init__(self): self.sent = []
        def send(self, chat_id, text): self.sent.append(text)

    return Deps(fetch=_Fetch(), extractor=_Extractor(),
                seen_store=SeenStore(db_path), notifier=_Notifier())


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


def test_run_from_worker_thread_delivers_and_persists(tmp_path):
    """Regression (issue #2 / ADR-0002): the weekly digest runs inside an
    APScheduler worker thread while the seen-store connection was opened on the
    main thread. The run must complete — deliver and persist dedup — without
    raising sqlite3.ProgrammingError across that thread boundary."""
    deps = _real_seen_deps(str(tmp_path / "seen.sqlite3"))  # connection built on THIS thread
    cfg = Config(channels=[("ai_chan", "ai")], target_chat_id=1, dry_run=False)
    runner = DigestRunner(lambda: NOW, cfg, deps)

    box = {}

    def worker():
        try:
            box["result"] = runner.run()
        except BaseException as exc:  # capture the cross-thread failure, if any
            box["error"] = exc

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    assert "error" not in box, f"run raised in worker thread: {box.get('error')!r}"
    assert box["result"] is not None
    assert box["result"].sent is True
    assert deps.notifier.sent, "digest was not delivered"
    # mark_seen (a DB write) also crossed the thread boundary: the event is now seen
    assert deps.seen_store.is_new(WORKER_EVENT.event_hash) is False

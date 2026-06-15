"""S09 — DigestRunner: invokes the pipeline + guards against overlapping runs."""
import dataclasses
import threading
from datetime import datetime, timedelta, timezone

from events_parser.config import Config
from events_parser.models import ChannelFetchResult, Event, RawPost
from events_parser.orchestrator import Deps, DigestResult
from events_parser.runner import DigestRunner, _guarded_run
from events_parser.seen_store import SeenStore

NOW = datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc)
REF = datetime(2026, 6, 15, 9, 0, tzinfo=timezone.utc)


def _recorder():
    """Return (messages_list, alert_callable) for asserting what was alerted."""
    msgs: list[str] = []
    return msgs, msgs.append

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
            return ChannelFetchResult.succeeded(channel, [
                RawPost(id=1, channel=channel, text="x", dt=NOW, permalink="https://t.me/c/1")])

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
            return ChannelFetchResult.succeeded(channel, [
                RawPost(id=1, channel=channel, text="x", dt=NOW, permalink="https://t.me/c/1")])

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


# --- run_guarded: the single never-crash entry every caller routes through (#4) ---

def test_run_guarded_swallows_pipeline_failure_without_alerter():
    """No caller runs raw: a pipeline exception is swallowed (returns None) so an
    endpoint can't 500. With no alerter, nothing is sent."""
    class _BoomFetch:
        def fetch_recent(self, channel, since=None):
            raise RuntimeError("pipeline kaboom")

    cfg = Config(channels=[("ai_chan", "ai")], target_chat_id=1, dry_run=True)
    runner = DigestRunner(lambda: NOW, cfg, dataclasses.replace(_deps(), fetch=_BoomFetch()))

    assert runner.run_guarded() is None  # must not raise


def test_run_guarded_delivers_and_returns_result_on_success():
    cfg = Config(channels=[("ai_chan", "ai")], target_chat_id=1, dry_run=True)
    runner = DigestRunner(lambda: NOW, cfg, _deps())

    result = runner.run_guarded()  # no alerter

    assert result is not None
    assert "E" in result.digest_text


# The guard primitive _guarded_run is exercised directly with lambdas (cheap, no deps).

def test_guarded_run_alerts_on_exception_and_swallows():
    msgs, alert = _recorder()

    def boom():
        raise RuntimeError("sqlite boom")

    result = _guarded_run(boom, alert, now_fn=lambda: REF)

    assert result is None
    assert len(msgs) == 1 and "RuntimeError" in msgs[0] and "boom" in msgs[0]


def test_guarded_run_without_alerter_swallows_exception_silently():
    """The manual /trigger + /digest path: guard but do NOT alert the operator."""
    msgs, alert = _recorder()

    def boom():
        raise RuntimeError("boom")

    result = _guarded_run(boom, alert=None, now_fn=lambda: REF)

    assert result is None
    assert msgs == []  # no operator alert on a manual run


def test_guarded_run_alerts_on_zero_events():
    msgs, alert = _recorder()
    empty = DigestResult(digest_text="(empty)", events=[], sent=True)

    result = _guarded_run(lambda: empty, alert, now_fn=lambda: REF)

    assert result is empty
    assert len(msgs) == 1 and "0" in msgs[0]


def test_guarded_run_alerts_on_fetch_failures_superseding_zero_events():
    msgs, alert = _recorder()
    res = DigestResult(digest_text="d", events=[], sent=True, fetch_failures=["dead_chan"])

    _guarded_run(lambda: res, alert, now_fn=lambda: REF)

    assert len(msgs) == 1 and "dead_chan" in msgs[0]


def test_guarded_run_zero_events_not_alerted_without_alerter():
    msgs, alert = _recorder()
    empty = DigestResult(digest_text="(empty)", events=[], sent=True)

    result = _guarded_run(lambda: empty, alert=None, now_fn=lambda: REF)

    assert result is empty
    assert msgs == []


def test_guarded_run_is_silent_on_successful_delivery():
    msgs, alert = _recorder()
    ok = DigestResult(digest_text="d", events=["e1", "e2"], sent=True)

    result = _guarded_run(lambda: ok, alert, now_fn=lambda: REF)

    assert result is ok
    assert msgs == []


def test_guarded_run_is_silent_when_run_skipped():
    """run_fn returns None when a run is already in progress (lock) — not a failure."""
    msgs, alert = _recorder()
    assert _guarded_run(lambda: None, alert, now_fn=lambda: REF) is None
    assert msgs == []


def test_guarded_run_survives_a_failing_alert():
    def boom():
        raise RuntimeError("run failed")

    def bad_alert(_text):
        raise RuntimeError("telegram down")

    assert _guarded_run(boom, bad_alert, now_fn=lambda: REF) is None  # must not raise

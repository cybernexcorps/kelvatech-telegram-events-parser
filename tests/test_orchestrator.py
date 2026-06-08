"""S01 + integration — run_digest threads posts through filter→dedup→render→deliver."""
from datetime import datetime, timedelta, timezone

from events_parser.config import Config
from events_parser.models import Event, RawPost
from events_parser.orchestrator import Deps, run_digest

NOW = datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc)


class FakeFetch:
    def __init__(self, posts_by_channel):
        self._by = posts_by_channel  # channel -> [RawPost]

    def fetch_recent(self, channel, since=None):
        return list(self._by.get(channel, []))


class FakeExtractor:
    def __init__(self, mapping):
        self._mapping = mapping  # post_id -> [Event]

    def extract(self, post):
        return list(self._mapping.get(post.id, []))


class FakeSeenStore:
    def __init__(self, already=()):
        self.seen = set(already)
        self.marked = []

    def is_new(self, event_hash):
        return event_hash not in self.seen

    def mark_seen(self, event):
        self.seen.add(event.event_hash)
        self.marked.append(event.event_hash)


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def send(self, chat_id, text):
        self.sent.append((chat_id, text))


def _post(pid, channel):
    return RawPost(id=pid, channel=channel, text="x", dt=NOW - timedelta(days=1),
                   permalink=f"https://t.me/{channel}/{pid}")


def _event(title, *, cost="free", start=None, domain="ai"):
    return Event(title=title, host="H", cost_status=cost,
                 start_date=start if start else NOW + timedelta(days=5),
                 domain=domain, source_post_url="https://t.me/c/1", source_post_dt=NOW)


def _deps(posts_by_channel, mapping, notifier, seen=None):
    return Deps(fetch=FakeFetch(posts_by_channel),
                extractor=FakeExtractor(mapping),
                seen_store=seen or FakeSeenStore(),
                notifier=notifier)


def test_run_digest_threads_one_post_to_a_delivered_digest():
    cfg = Config(channels=[("ai_chan", "ai")], target_chat_id=142068037, dry_run=False)
    notifier = FakeNotifier()
    deps = _deps({"ai_chan": [_post(101, "ai_chan")]}, {101: [_event("Вебинар по ИИ")]}, notifier)

    result = run_digest(NOW, cfg, deps)

    assert "Вебинар по ИИ" in result.digest_text
    assert len(notifier.sent) == 1
    assert notifier.sent[0][0] == 142068037
    assert result.sent is True


def test_dry_run_renders_but_sends_nothing_and_marks_nothing():
    cfg = Config(channels=[("ai_chan", "ai")], target_chat_id=1, dry_run=True)
    notifier = FakeNotifier()
    seen = FakeSeenStore()
    deps = _deps({"ai_chan": [_post(1, "ai_chan")]}, {1: [_event("Конференция X", cost="paid")]},
                 notifier, seen)

    result = run_digest(NOW, cfg, deps)

    assert result.digest_text
    assert notifier.sent == []
    assert seen.marked == []  # preview must not consume the seen-store


def test_events_outside_horizon_are_excluded():
    cfg = Config(channels=[("ai_chan", "ai")], target_chat_id=1, horizon_days=28)
    notifier = FakeNotifier()
    far = _event("Далёкое", start=NOW + timedelta(days=60))
    past = _event("Прошедшее", start=NOW - timedelta(days=3))
    soon = _event("Скоро", start=NOW + timedelta(days=10))
    deps = _deps({"ai_chan": [_post(1, "ai_chan")]}, {1: [far, past, soon]}, notifier)

    result = run_digest(NOW, cfg, deps)

    assert "Скоро" in result.digest_text
    assert "Далёкое" not in result.digest_text
    assert "Прошедшее" not in result.digest_text


def test_already_seen_events_are_skipped():
    e = _event("Старое событие")
    cfg = Config(channels=[("ai_chan", "ai")], target_chat_id=1)
    notifier = FakeNotifier()
    seen = FakeSeenStore(already=[e.event_hash])
    deps = _deps({"ai_chan": [_post(1, "ai_chan")]}, {1: [e]}, notifier, seen)

    result = run_digest(NOW, cfg, deps)

    assert "Старое событие" not in result.digest_text


def test_channel_domain_overrides_extractor_domain():
    # extractor mislabels as ai, but the post came from a pr-tagged channel
    mislabeled = _event("PR-форум", domain="ai")
    cfg = Config(channels=[("pr_chan", "pr")], target_chat_id=1)
    notifier = FakeNotifier()
    deps = _deps({"pr_chan": [_post(1, "pr_chan")]}, {1: [mislabeled]}, notifier)

    result = run_digest(NOW, cfg, deps)
    # PR section header present, event rendered under PR domain
    assert "PR" in result.digest_text and "PR-форум" in result.digest_text


def test_undated_events_marked_seen_only_on_real_send():
    open_ev = _event("Открытый вебинар", start=None)
    cfg = Config(channels=[("ai_chan", "ai")], target_chat_id=1, dry_run=False)
    notifier = FakeNotifier()
    seen = FakeSeenStore()
    deps = _deps({"ai_chan": [_post(1, "ai_chan")]}, {1: [open_ev]}, notifier, seen)

    run_digest(NOW, cfg, deps)
    assert open_ev.event_hash in seen.marked  # open events still get sent + recorded

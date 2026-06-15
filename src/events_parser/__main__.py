"""CLI entrypoint — `python -m events_parser`.

Two modes:
  --demo  : in-memory sample deps; proves the pipeline shape end-to-end (S01).
  --live  : real deps from environment (.env) — Telethon/preview fetch, Yandex
            extractor, SQLite seen-store, Telegram delivery. This is also the
            container one-shot path and the manual test entry for S11.

`--dry-run` renders the digest but does not deliver it (and does not mark events
seen), so it is safe to run repeatedly against real channels while iterating.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader (no python-dotenv dep). Does not overwrite real env vars."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        # strip inline comments only when value isn't quoted
        if value and value[0] not in "\"'" and "  #" in value:
            value = value.split("  #", 1)[0].strip()
        os.environ.setdefault(key, value)


def _demo_deps():
    """In-memory deps producing one sample event — skeleton only."""
    from datetime import timedelta

    from .models import ChannelFetchResult, Event, RawPost
    from .orchestrator import Deps

    class _Fetch:
        def fetch_recent(self, channel, since=None):
            posts = [RawPost(id=1, channel=channel, text="Бесплатный вебинар по ИИ",
                             dt=datetime.now(timezone.utc),
                             permalink=f"https://t.me/{channel}/1")]
            return ChannelFetchResult.succeeded(channel, posts)

    class _Extractor:
        def extract(self, post):
            return [Event(title="Демо-событие: вебинар по ИИ", event_type="webinar",
                          host="Kelva", cost_status="free", domain="ai",
                          start_date=datetime.now(timezone.utc) + timedelta(days=7),
                          source_channel=post.channel, source_post_url=post.permalink,
                          source_post_dt=post.dt)]

    class _Seen:
        def is_new(self, h): return True
        def mark_seen(self, e): pass

    class _Notifier:
        def send(self, chat_id, text):
            print(f"[notify chat={chat_id}]\n{text}")

    return Deps(fetch=_Fetch(), extractor=_Extractor(), seen_store=_Seen(), notifier=_Notifier())


def _run_demo(dry_run: bool) -> int:
    from .config import Config
    from .orchestrator import run_digest

    cfg = Config(channels=[("demo_ai_chan", "ai")], target_chat_id=0, dry_run=dry_run)
    result = run_digest(datetime.now(timezone.utc), cfg, _demo_deps())
    if dry_run:
        print(result.digest_text)
    print(f"\n[done] events={len(result.events)} sent={result.sent}", file=sys.stderr)
    return 0


def _run_live(dry_run: bool, use_agents: bool | None) -> int:
    """Build real deps from the environment and run one digest cycle."""
    import dataclasses

    from .factory import build_agent_service, build_config, build_deps
    from .runner import DigestRunner

    _load_dotenv()
    # The CLI defaults to the cheap deterministic path; USE_AGENTS in the env overrides.
    config = build_config(use_agents_default=False)
    if dry_run:
        config = dataclasses.replace(config, dry_run=True)

    # An explicit --agents/--no-agents flag wins over the env-resolved Config default.
    if use_agents is None:
        use_agents = config.use_agents

    deps = build_deps()
    agentic = build_agent_service(config, deps) if use_agents else None
    runner = DigestRunner(lambda: datetime.now(timezone.utc), config, deps, agentic_service=agentic)

    print(f"[live] channels={len(config.channels)} agents={use_agents} dry_run={config.dry_run} "
          f"scan_days={config.scan_days} horizon_days={config.horizon_days}", file=sys.stderr)
    result = runner.run()
    if result is None:
        print("[live] another run in progress; skipped", file=sys.stderr)
        return 1
    print("\n" + (result.digest_text or "(no digest text)"))
    print(f"\n[done] events={len(result.events)} sent={result.sent}", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    # Windows cp1252 crashes on Cyrillic stdout — force UTF-8.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    p = argparse.ArgumentParser(prog="events_parser")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--demo", action="store_true", help="run with built-in sample deps (skeleton)")
    mode.add_argument("--live", action="store_true", help="run with real env-built deps (one-shot digest)")
    p.add_argument("--dry-run", action="store_true", help="render but do not send (and do not mark seen)")
    agents = p.add_mutually_exclusive_group()
    agents.add_argument("--agents", dest="agents", action="store_true", default=None,
                        help="force the Deep Agents supervisor path")
    agents.add_argument("--no-agents", dest="agents", action="store_false",
                        help="force the deterministic path")
    args = p.parse_args(argv)

    if args.live:
        return _run_live(args.dry_run, args.agents)
    return _run_demo(args.dry_run)  # default + --demo


if __name__ == "__main__":
    raise SystemExit(main())

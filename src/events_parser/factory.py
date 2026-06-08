"""Composition root — assembles real dependencies from config + environment.

Imported lazily by the app/CLI so the unit suite never needs httpx/langchain/etc.
"""
from __future__ import annotations

import os
from typing import Mapping, Optional

from .config import Config, load_channels
from .orchestrator import Deps


def build_config(env: Optional[Mapping[str, str]] = None) -> Config:
    env = env if env is not None else os.environ
    channels = load_channels(env.get("CHANNELS_CONFIG", "channels.yaml"))
    return Config.from_env(env, channels=channels)


def build_fetch(env: Optional[Mapping[str, str]] = None):
    """Pick the channel reader: account-based Telethon when configured, else t.me/s preview.

    Telethon (MTProto) handles full history, media, and preview-disabled/private
    channels; the preview client is the zero-auth fallback.
    """
    env = env if env is not None else os.environ
    if env.get("TELEGRAM_API_ID") and env.get("TELEGRAM_SESSION"):
        from .telethon_client import build_telethon_fetch
        return build_telethon_fetch(env)
    from .preview import PreviewClient
    return PreviewClient()


def build_deps(env: Optional[Mapping[str, str]] = None) -> Deps:
    """Deterministic dependencies (fetch + Yandex extractor + SQLite + Telegram).

    The agentic path (S08) reuses the same seen-store + notifier via this Deps; only
    the collection step is driven by the Deep Agents supervisor.
    """
    env = env if env is not None else os.environ
    from .extraction import build_yandex_extractor
    from .notify import TelegramNotifier
    from .seen_store import SeenStore

    return Deps(
        fetch=build_fetch(env),
        extractor=build_yandex_extractor(),
        seen_store=SeenStore(env.get("EVENTS_DB_PATH", "data/seen.sqlite3")),
        notifier=TelegramNotifier(env["TELEGRAM_BOT_TOKEN"]),
    )


def build_agent_service(config, deps, env: Optional[Mapping[str, str]] = None):
    """Deep Agents supervisor service (S08) sharing the deterministic finish path."""
    from .agents import AgentDigestService
    return AgentDigestService(config, deps, env)

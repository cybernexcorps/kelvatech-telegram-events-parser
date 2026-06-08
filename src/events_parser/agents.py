"""S08 — Deep Agents layer: supervisor + per-domain subagents.

A supervisor `create_deep_agent` delegates to two subagents — `ai-events` and
`pr-events` — each owning its domain's channels. The subagents do the scanning by
calling tools; the tools perform deterministic fetch+extract and record results
into a typed collector (side-effect sink), so digest correctness never depends on
parsing the LLM's free-text output. The collected events are then handed to the
shared `finish_digest` path (dedup → rank → render → deliver).

Sync subagents run co-deployed in this container. The genuinely-async
`async-subagent-server` form (deepagents 0.5 preview, AsyncSubAgent over the Agent
Protocol) activates when deployed under a LangGraph deployment — see
`langgraph.json` and `async_subagent_specs()` below. All imports are lazy so the
unit suite never needs deepagents/langchain.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Mapping, Optional

from .config import Config
from .models import Event, RawPost
from .orchestrator import DigestResult, Deps, finish_digest


class EventCollector:
    """Typed sink the subagent tools write into."""

    def __init__(self) -> None:
        self.events: list[Event] = []


def _build_tools(collector: EventCollector, scan_days: int):
    """Tools backed by the deterministic preview client + Yandex extractor."""
    from langchain_core.tools import tool

    from .extraction import build_yandex_extractor
    from .factory import build_fetch

    preview = build_fetch()  # Telethon when configured, else t.me/s preview
    extractor = build_yandex_extractor()

    @tool
    def list_recent_posts(channel: str) -> str:
        """List recent post ids + text snippets from a public Telegram channel preview."""
        since = datetime.now(timezone.utc) - timedelta(days=scan_days)
        posts = preview.fetch_recent(channel, since)
        return "\n".join(f"[{p.id}] {p.text[:120]}" for p in posts) or "(no posts)"

    @tool
    def extract_and_record_events(channel: str, domain: str) -> str:
        """Scan a channel, extract events, and record them under the given domain (ai|pr).

        Returns how many events were recorded. Call this once per channel you own.
        """
        since = datetime.now(timezone.utc) - timedelta(days=scan_days)
        count = 0
        for post in preview.fetch_recent(channel, since):
            for ev in extractor.extract(post):
                if ev.domain != domain:
                    ev = ev.model_copy(update={"domain": domain})
                collector.events.append(ev)
                count += 1
        return f"recorded {count} events from {channel} ({domain})"

    return [list_recent_posts, extract_and_record_events]


def _agent_model(env: Mapping[str, str]):
    from langchain_openai import ChatOpenAI

    model = env.get("YANDEX_AGENT_MODEL", env.get("YANDEX_DIGEST_MODEL", "yandexgpt/latest"))
    base_url = env.get("YANDEX_OPENAI_BASE_URL", "https://llm.api.cloud.yandex.net/v1")
    folder = env.get("YANDEX_FOLDER_ID", "")
    api_key = env.get("YANDEX_API_KEY", "")
    model_uri = f"gpt://{folder}/{model}" if folder and "://" not in model else model
    return ChatOpenAI(model=model_uri, base_url=base_url, api_key=api_key, temperature=0)


def _domain_channels(config: Config, domain: str) -> list[str]:
    return [h for h, d in config.channels if d == domain]


def build_supervisor(collector: EventCollector, config: Config,
                     env: Optional[Mapping[str, str]] = None):
    """Construct the Deep Agents supervisor with ai-events / pr-events subagents."""
    from deepagents import create_deep_agent

    env = env if env is not None else os.environ
    tools = _build_tools(collector, config.scan_days)
    model = _agent_model(env)

    ai_channels = _domain_channels(config, "ai")
    pr_channels = _domain_channels(config, "pr")

    subagents = [
        {
            "name": "ai-events",
            "description": "Scans AI-field Telegram channels and records upcoming events.",
            "system_prompt": (
                "Ты отвечаешь за поиск мероприятий в сфере ИИ. Для КАЖДОГО из этих каналов "
                f"вызови extract_and_record_events(channel, domain='ai'): {ai_channels}. "
                "После обработки всех каналов кратко отчитайся, сколько событий записано."
            ),
            "tools": tools,
        },
        {
            "name": "pr-events",
            "description": "Scans PR-field Telegram channels and records upcoming events.",
            "system_prompt": (
                "Ты отвечаешь за поиск PR-мероприятий. Для КАЖДОГО из этих каналов "
                f"вызови extract_and_record_events(channel, domain='pr'): {pr_channels}. "
                "После обработки всех каналов кратко отчитайся, сколько событий записано."
            ),
            "tools": tools,
        },
    ]

    # create_deep_agent bundles the planning (TodoList) and Filesystem middleware by
    # default, so per-domain planning + large-payload offload are active without explicit
    # wiring. Additionally, the tools return only short snippets ([id] text[:120]), so raw
    # t.me/s HTML never enters the supervisor's context window in the first place.
    return create_deep_agent(
        model=model,
        tools=tools,
        subagents=subagents,
        system_prompt=(
            "Ты — супервайзер еженедельного дайджеста мероприятий. Делегируй сбор событий "
            "субагентам ai-events и pr-events, затем сообщи, что сбор завершён. Не пиши сам "
            "дайджест — его соберёт детерминированный пайплайн из записанных событий."
        ),
    )


def async_subagent_specs(env: Optional[Mapping[str, str]] = None) -> list[dict]:
    """Production async-subagent-server specs (deepagents 0.5 preview).

    Co-deployed (no url) over ASGI under a LangGraph deployment; each graphId must
    be registered in langgraph.json. Used instead of inline subagents when running
    under LangSmith Deployments / `langgraph dev`.
    """
    return [
        {"name": "ai-events", "description": "AI-field event scanner", "graphId": "ai_events"},
        {"name": "pr-events", "description": "PR-field event scanner", "graphId": "pr_events"},
    ]


def _domain_graph(domain: str):
    """Standalone per-domain Deep Agent, registered as a graph for async deployment."""
    from deepagents import create_deep_agent

    config = _load_config_from_env()
    channels = _domain_channels(config, domain)
    collector = EventCollector()  # in a deployment, swap for a shared store backend
    tools = _build_tools(collector, config.scan_days)
    return create_deep_agent(
        model=_agent_model(os.environ),
        tools=tools,
        system_prompt=(
            f"Найди мероприятия ({domain}) во всех каналах: {channels}. "
            "Для каждого канала вызови extract_and_record_events."
        ),
    )


def _load_config_from_env() -> Config:
    from .factory import build_config
    return build_config()


def ai_events_graph():
    """LangGraph entrypoint for the async ai-events subagent server."""
    return _domain_graph("ai")


def pr_events_graph():
    """LangGraph entrypoint for the async pr-events subagent server."""
    return _domain_graph("pr")


def supervisor_graph():
    """LangGraph entrypoint: supervisor wired to async subagents (co-deployed ASGI)."""
    from deepagents import create_deep_agent

    config = _load_config_from_env()
    collector = EventCollector()
    return create_deep_agent(
        model=_agent_model(os.environ),
        tools=_build_tools(collector, config.scan_days),
        subagents=async_subagent_specs(),  # AsyncSubAgent over Agent Protocol
        system_prompt="Делегируй сбор событий async-субагентам ai-events и pr-events.",
    )


class AgentDigestService:
    """Agentic entry: supervisor+subagents gather events, then the shared finish path runs."""

    def __init__(self, config: Config, deps: Deps, env: Optional[Mapping[str, str]] = None):
        self._config = config
        self._deps = deps
        self._env = env if env is not None else os.environ

    def run(self, now: datetime) -> DigestResult:
        collector = EventCollector()
        supervisor = build_supervisor(collector, self._config, self._env)
        supervisor.invoke({"messages": [{
            "role": "user",
            "content": "Собери мероприятия по всем каналам через субагентов ai-events и pr-events.",
        }]})
        return finish_digest(collector.events, now, self._config, self._deps)

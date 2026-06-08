"""Runtime configuration — channels.yaml + environment."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping, Optional

import yaml

# (handle, domain) pairs — domain routes a channel to its subagent.
ChannelSpec = tuple[str, str]
VALID_DOMAINS = {"ai", "pr"}


def load_channels(path: str) -> list[ChannelSpec]:
    """Parse and validate channels.yaml; fail fast on bad/empty config."""
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    raw = data.get("channels") or []
    if not raw:
        raise ValueError(f"no channels configured in {path}")
    specs: list[ChannelSpec] = []
    for entry in raw:
        handle = str(entry.get("handle", "")).lstrip("@").strip()
        domain = str(entry.get("domain", "")).strip().lower()
        if not handle:
            raise ValueError(f"channel entry missing handle: {entry}")
        if domain not in VALID_DOMAINS:
            raise ValueError(f"invalid domain {domain!r} for {handle} (expected one of {VALID_DOMAINS})")
        specs.append((handle, domain))
    return specs


def _as_bool(val: str, default: bool = True) -> bool:
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    channels: list[ChannelSpec] = field(default_factory=list)
    target_chat_id: int = 0
    dry_run: bool = False
    horizon_days: int = 28
    scan_days: int = 7
    send_on_empty: bool = True

    @classmethod
    def from_env(
        cls,
        env: Optional[Mapping[str, str]] = None,
        channels: Optional[list[ChannelSpec]] = None,
    ) -> "Config":
        env = env if env is not None else os.environ
        return cls(
            channels=channels or [],
            target_chat_id=int(env.get("TELEGRAM_TARGET_CHAT_ID", "0") or 0),
            dry_run=_as_bool(env.get("DRY_RUN"), default=False),
            horizon_days=int(env.get("HORIZON_DAYS", "28") or 28),
            scan_days=int(env.get("SCAN_DAYS", "7") or 7),
            send_on_empty=_as_bool(env.get("SEND_ON_EMPTY"), default=True),
        )

"""DigestRunner — single entry that both the weekly cron and the /digest command call.

Guards against overlapping runs so a manual trigger during a scheduled run (or a
second click) does not start a concurrent digest.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Callable, Optional

from .config import Config
from .orchestrator import Deps, DigestResult, run_digest

log = logging.getLogger(__name__)


class DigestRunner:
    def __init__(self, now_fn: Callable[[], datetime], config: Config, deps: Deps,
                 agentic_service=None):
        self._now_fn = now_fn
        self._config = config
        self._deps = deps
        self._agentic = agentic_service  # AgentDigestService, or None for deterministic
        self._lock = threading.Lock()

    def run(self) -> Optional[DigestResult]:
        if not self._lock.acquire(blocking=False):
            log.info("digest run already in progress; skipping this trigger")
            return None
        try:
            if self._agentic is not None:
                return self._agentic.run(self._now_fn())
            return run_digest(self._now_fn(), self._config, self._deps)
        finally:
            self._lock.release()

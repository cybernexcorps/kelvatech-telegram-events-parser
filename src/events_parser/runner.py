"""DigestRunner — the single entry every caller (weekly cron, /trigger, /digest) uses.

``run`` guards against overlapping runs so a manual trigger during a scheduled run
(or a second click) does not start a concurrent digest. ``run_guarded`` wraps that
in never-crash + optional operator alerting, so no caller runs raw: an endpoint
can't 500 on a pipeline error, and the unattended weekly fire (the only caller that
passes an alerter) pings the operator on failure. Manual callers pass no alerter —
they report to their own human caller. Alerting policy: see docs/adr/0005.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from .config import Config
from .orchestrator import Deps, DigestResult, run_digest

log = logging.getLogger(__name__)


def _safe_alert(alert: Callable[[str], None], text: str) -> None:
    """Send an operator alert without ever letting its failure escape — a broken
    alert channel must not crash the run."""
    try:
        alert(text)
    except Exception:
        log.warning("failed to send failure alert", exc_info=True)


def _guarded_run(run_fn, alert: Optional[Callable[[str], None]] = None, now_fn=None):
    """Run a digest callable, never crashing the caller, optionally alerting (#4).

    Best-effort and non-crashing: neither a run exception nor an alert-send failure
    propagates (so APScheduler keeps its next fire and an endpoint can't 500). When
    ``alert`` is None the run is still guarded but the operator is not pinged — the
    manual /trigger and /digest paths report to their own human caller.
    """
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))
    try:
        result = run_fn()
    except Exception as exc:
        log.warning("digest run failed", exc_info=True)
        if alert:
            _safe_alert(alert, f"⚠️ Сбор дайджеста упал: {type(exc).__name__}: {exc} · {now_fn().isoformat()}")
        return None
    # result is None only when a run was already in progress (lock skip) — not a failure.
    if result is None or alert is None:
        return result
    failures = getattr(result, "fetch_failures", None)
    if failures:
        # Precise signal (ChannelFetchResult): name the unreachable channels. This
        # supersedes the blunt 0-events proxy, which can't tell failed from quiet.
        _safe_alert(alert, f"⚠️ Сбор: каналы недоступны — {', '.join(failures)} · {now_fn().isoformat()}")
    elif not getattr(result, "events", None):
        _safe_alert(alert, f"⚠️ Дайджест: 0 событий (возможен сбой сбора или пустая неделя) · {now_fn().isoformat()}")
    return result


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

    def run_guarded(self, alert: Optional[Callable[[str], None]] = None) -> Optional[DigestResult]:
        """The never-crash entry every caller routes through (lock lives in ``run``).

        Pass ``alert`` only for the unattended weekly fire; manual callers omit it.
        """
        return _guarded_run(self.run, alert, self._now_fn)

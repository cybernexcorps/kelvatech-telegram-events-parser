"""FastAPI host — weekly APScheduler cron + on-demand /digest, both via DigestRunner.

Run:  uv run --extra runtime uvicorn events_parser.app:app --host 0.0.0.0 --port 8080
Requires the `runtime` extra (fastapi, uvicorn, apscheduler).
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request

from .factory import build_config, build_deps
from .notify import build_error_alerter
from .runner import DigestRunner
from .schedule import build_weekly_trigger, guarded_scheduled_run

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def make_runner() -> DigestRunner:
    use_agents = os.environ.get("USE_AGENTS", "true").lower() in ("1", "true", "yes")
    config = build_config()
    deps = build_deps()
    agentic = None
    if use_agents:
        from .factory import build_agent_service
        agentic = build_agent_service(config, deps)
    return DigestRunner(_now, config, deps, agentic_service=agentic)


@asynccontextmanager
async def lifespan(app: FastAPI):
    runner = make_runner()
    app.state.runner = runner

    scheduler = BackgroundScheduler(timezone="UTC")
    cron = os.environ.get("DIGEST_SCHEDULE_CRON", "0 9 * * 1")  # Mondays 09:00 UTC
    # Only the SCHEDULED fire is guarded with operator alerting (#4); the manual
    # /trigger and /digest paths already report failures to their own callers.
    alerter = build_error_alerter(os.environ)
    scheduler.add_job(lambda: guarded_scheduled_run(runner.run, alerter),
                      build_weekly_trigger(cron), id="weekly_digest",
                      max_instances=1, coalesce=True)
    scheduler.start()
    app.state.scheduler = scheduler
    log.info("scheduler started; weekly digest cron=%r", cron)
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Kelva Telegram Events Parser", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/trigger")
def trigger():
    """Manual digest trigger (testing / ad hoc)."""
    result = app.state.runner.run()
    if result is None:
        return {"status": "skipped", "reason": "a run is already in progress"}
    return {"status": "ok", "events": len(result.events), "sent": result.sent}


def _reply(chat_id, text: str) -> None:
    """Send a Telegram reply to the requester (best-effort)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not chat_id or not token:
        return
    import httpx
    try:
        httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
                   json={"chat_id": chat_id, "text": text}, timeout=20.0)
    except Exception:
        log.warning("failed to send /digest acknowledgement", exc_info=True)


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """Handles the /digest command from the dedicated bot (webhook mode)."""
    update = await request.json()
    msg = update.get("message", {}) or {}
    text = (msg.get("text", "") or "")
    chat_id = (msg.get("chat", {}) or {}).get("id")
    if text.strip().split("@")[0] == "/digest":
        _reply(chat_id, "⏳ Собираю дайджест мероприятий…")
        result = app.state.runner.run()
        if result is None:
            _reply(chat_id, "⚠️ Сбор уже выполняется — попробуйте чуть позже.")
            return {"status": "skipped"}
        _reply(chat_id, f"✅ Готово: {len(result.events)} событий "
                        f"(отправлено в канал: {'да' if result.sent else 'нет'}).")
        return {"status": "completed", "events": len(result.events)}
    return {"status": "ignored"}

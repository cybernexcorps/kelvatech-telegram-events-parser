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
from .notify import TelegramNotifier, build_error_alerter
from .runner import DigestRunner
from .schedule import build_weekly_trigger

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def make_runner() -> DigestRunner:
    # The cron host defaults to the agentic path; USE_AGENTS in the env still overrides.
    config = build_config(use_agents_default=True)
    deps = build_deps()
    agentic = None
    if config.use_agents:
        from .factory import build_agent_service
        agentic = build_agent_service(config, deps)
    return DigestRunner(_now, config, deps, agentic_service=agentic)


@asynccontextmanager
async def lifespan(app: FastAPI):
    runner = make_runner()
    app.state.runner = runner

    # Plain-text replier for /digest acknowledgements — same Telegram-send seam as the
    # digest (HTML) and the error alerter, so parse_mode/splitting can't diverge again.
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    app.state.replier = TelegramNotifier(bot_token, parse_mode=None) if bot_token else None

    scheduler = BackgroundScheduler(timezone="UTC")
    cron = os.environ.get("DIGEST_SCHEDULE_CRON", "0 9 * * 1")  # Mondays 09:00 UTC
    # Every caller routes through runner.run_guarded (never-crash); only the SCHEDULED
    # fire passes an alerter — the manual /trigger and /digest paths report failures to
    # their own human caller, so they guard without alerting. See docs/adr/0005.
    alerter = build_error_alerter(os.environ)
    scheduler.add_job(lambda: runner.run_guarded(alert=alerter),
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
    """Manual digest trigger (testing / ad hoc). Guarded — never 500s on a run error."""
    result = app.state.runner.run_guarded()  # no alerter: this caller sees the response
    if result is None:
        # None = a run is already in progress, or the run failed (swallowed; see logs).
        return {"status": "skipped", "reason": "no digest produced — run in progress or failed (see logs)"}
    return {"status": "ok", "events": len(result.events), "sent": result.sent}


def _reply(chat_id, text: str) -> None:
    """Acknowledge the requester via the shared Telegram-send seam (best-effort).

    Delegates to the plain-text replier built at startup. Never raises — a failed
    acknowledgement must not break the webhook handler or mask the digest result.
    """
    replier = getattr(app.state, "replier", None)
    if not chat_id or replier is None:
        return
    try:
        replier.send(chat_id, text)
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
        result = app.state.runner.run_guarded()  # guarded: a failure won't 500 the webhook
        if result is None:
            _reply(chat_id, "⚠️ Не удалось собрать дайджест (уже идёт сбор или ошибка). Попробуйте позже.")
            return {"status": "skipped"}
        _reply(chat_id, f"✅ Готово: {len(result.events)} событий "
                        f"(отправлено в канал: {'да' if result.sent else 'нет'}).")
        return {"status": "completed", "events": len(result.events)}
    return {"status": "ignored"}

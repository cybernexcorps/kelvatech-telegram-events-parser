# S09 — Hybrid triggers (weekly cron + /digest command)

**Type:** AFK · **Parent:** docs/PRD.md · **Stories:** 12, 13

## What to build

Two entry points into the same `run_digest` pipeline:

- **Weekly cron** via APScheduler, started in the FastAPI lifespan; schedule (cron expr / day /
  time) configurable via env.
- **On-demand `/digest`** Telegram bot command handler that triggers a run and reports
  start/completion back to the requester.

Both share one orchestrator; the on-demand path stays responsive while work runs (ties into the
async-subagent design).

## Acceptance criteria

- [ ] APScheduler job registered in FastAPI lifespan; schedule from env (default weekly)
- [ ] Scheduler job invokes `run_digest` and logs start/finish
- [ ] `/digest` command triggers a run and acknowledges to the user
- [ ] Concurrent guard: a second trigger while one is running does not start an overlapping run
- [ ] Tests assert the scheduler registers the job and the command handler calls the orchestrator (clock/orchestrator injected)

## Blocked by

- S01
- S07

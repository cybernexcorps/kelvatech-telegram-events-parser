# CLAUDE.md — Kelva Telegram Events Parser

Weekly RU AI/PR events digest (free-first) delivered via a dedicated Telegram bot.
LangChain Deep Agents + Telethon + Yandex Foundation Models + FastAPI, deployed as a
single Docker container (cron-only) on the `kelva` VPS. See `README.md`, `docs/PRD.md`,
`docs/DEPLOY.md`, and `docs/MANUAL.md`.

> **Repo note:** this subproject lives in two places — the standalone GitHub repo
> [`cybernexcorps/kelvatech-telegram-events-parser`](https://github.com/cybernexcorps/kelvatech-telegram-events-parser)
> (what the VPS deploys) and a mirrored working copy inside the `cybernexcorps/kelvatech`
> mono-repo at `Dev-Platform/agents/kelvatech-telegram-events-parser/`. `git remote` in
> the mono-repo working copy points at `kelvatech`, **not** the standalone repo.

## Dev commands

```bash
PYTHONPATH=src python -m events_parser --demo --dry-run   # pipeline shape, no secrets
PYTHONPATH=src python -m events_parser --live --dry-run    # real channels, no send (needs .env)
PYTHONPATH=src python -m pytest -q                         # unit suite
```

All files are UTF-8 (Russian Cyrillic content).

## Agent skills

### Issue tracker

GitHub issues in the **standalone** repo `cybernexcorps/kelvatech-telegram-events-parser`
— every `gh` command must pin `-R cybernexcorps/kelvatech-telegram-events-parser` (the
mono-repo working copy's `git remote` resolves elsewhere). See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical names (`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` /
`wontfix`), all present in the repo. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — one `CONTEXT.md` + `docs/adr/` at this project root. See `docs/agents/domain.md`.

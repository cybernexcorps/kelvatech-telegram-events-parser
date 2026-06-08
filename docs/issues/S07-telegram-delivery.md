# S07 — Telegram delivery (dedicated bot)

**Type:** HITL (needs a new bot token) · **Parent:** docs/PRD.md · **Stories:** 12, 14, 28

## What to build

`Notifier` that sends the rendered digest to a configured Telegram chat via a **dedicated bot**.
Default target = private chat **142068037** (testing); target chat id configurable for later
promotion to a team channel. Bot token + chat id supplied via env / Docker secrets (never
committed). Honors the dry-run flag (render, don't send). Long digests are split across messages
within Telegram's limits.

**HITL:** requires creating the bot with BotFather and providing the token.

## Acceptance criteria

- [ ] `Notifier.send(chat_id, text)` delivers via the dedicated bot
- [ ] Target chat id + bot token read from env/secrets; nothing sensitive committed
- [ ] Dry-run flag → renders, sends nothing
- [ ] Messages exceeding Telegram length limits are split correctly
- [ ] Unit tests use a fake notifier capturing `(chat_id, text)`; no live Telegram call in CI
- [ ] One manual delivery to chat 142068037 verified

## Blocked by

- S01

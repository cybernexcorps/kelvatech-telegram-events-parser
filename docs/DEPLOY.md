# Deploy — VPS (cron-only)

Single Docker container. **I/O-bound** (all LLM inference is remote on Yandex
Foundation Models), so the box runs no model. Weekly Monday digest needs **zero
inbound** — only outbound HTTPS.

## Host requirements

| Resource | Minimum | Recommended |
|---|---|---|
| vCPU | 1 | 1–2 |
| RAM | 1 GB (build elsewhere) | **2 GB** (comfortable `uv sync` build) |
| Disk | 10 GB SSD | 20 GB SSD |
| OS | Ubuntu 22.04/24.04 LTS or Debian 12 | same |
| Software | Docker Engine + Compose plugin | — |

**Outbound endpoints** (no inbound needed): `llm.api.cloud.yandex.net`,
`api.telegram.org`, Telegram MTProto DCs, optional `api.smith.langchain.com`.

**Region:** RU (Timeweb / Yandex Cloud) — lowest latency to Yandex FM + Telegram.

## 1. Install Docker (skip if present)

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER" && newgrp docker   # run docker without sudo
docker --version && docker compose version
```

## 2. Get the code

```bash
# private repo — use a PAT or deploy key
git clone https://github.com/cybernexcorps/kelvatech-telegram-events-parser.git
cd kelvatech-telegram-events-parser
```

(or `rsync` the project dir up from a workstation — exclude `.venv/`, `.git/`, `data/`.)

## 3. Create `.env` (secrets — never committed)

Copy the template and fill it in. **Transfer secrets out-of-band** (scp/paste over
SSH); do not bake them into the image.

```bash
cp .env.example .env && nano .env
```

Required for a live cron deployment:

| Var | Purpose |
|---|---|
| `TELEGRAM_BOT_TOKEN` | BotFather token for @kelva_events_bot |
| `TELEGRAM_TARGET_CHAT_ID` | recipient chat (must have pressed Start on the bot) |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` / `TELEGRAM_SESSION` | Telethon MTProto read (session already minted — no login on the VPS) |
| `YANDEX_API_KEY` / `YANDEX_FOLDER_ID` | Yandex Foundation Models auth |
| `USE_AGENTS` | `true` for the Deep Agents path |
| `DIGEST_SCHEDULE_CRON` | default `0 9 * * 1` = Mon 09:00 **UTC** = 12:00 MSK |

If `TELEGRAM_API_ID`/`TELEGRAM_SESSION` are absent the reader silently falls back
to the zero-auth `t.me/s` HTML preview client.

## 4. Build + run

```bash
docker compose up -d --build
docker compose ps
curl -s localhost:8080/health        # {"status":"ok"}
docker compose logs -f --tail=50     # expect "scheduler started; weekly digest cron=..."
```

`restart: unless-stopped` keeps it alive across reboots; the `events_data` volume
persists the SQLite seen-store (cross-week dedup) across redeploys.

## 5. Smoke test (don't wait until Monday)

```bash
# dry run — scrapes + extracts + renders, prints, sends nothing, marks nothing seen
docker compose run --rm events-parser \
  uv run --extra runtime python -m events_parser --live --dry-run

# real one-shot — delivers a digest now and records seen events
docker compose run --rm events-parser \
  uv run --extra runtime python -m events_parser --live
```

`/trigger` also fires a run on demand from the host:
`curl -s -X POST localhost:8080/trigger`.

## Update / redeploy

```bash
git pull            # or rsync
docker compose up -d --build
```

The seen-store survives (named volume). To wipe dedup history:
`docker compose down && docker volume rm <project>_events_data`.

## Logs / observability

Container logs via `docker compose logs`. For traced runs, set `LANGSMITH_TRACING=true`
+ `LANGSMITH_API_KEY` in `.env` → runs appear in the `kelva-events-parser` LangSmith project.

## IPv6-only hosts (e.g. ProCloud)

Some RU clouds **blackhole outbound IPv4** to Telegram DCs, PyPI, and ghcr.io,
reaching them only over IPv6. Symptoms: `telethon ... Connection to Telegram failed`,
`uv sync ... operation timed out`, `ghcr.io ... TLS handshake timeout`. The repo is
already configured for this:

- **Dockerfile** installs `uv` from PyPI (not `ghcr.io/astral-sh/uv`).
- **docker-compose.yml** sets `build.network: host` (so `uv sync` uses the host's
  IPv6 at build) and `network_mode: host` (so the runtime container has IPv6 for
  Telegram). The app binds `127.0.0.1:8080` — never publicly exposed.
- **`.env`** opts in: `TELEGRAM_USE_IPV6=true` plus a DC pin
  (`TELEGRAM_DC_ID` / `TELEGRAM_DC_IP` / `TELEGRAM_DC_PORT`). The pin is required —
  `use_ipv6` alone still dials the IPv4 address baked into `TELEGRAM_SESSION`;
  `session.set_dc()` overrides it with the DC's IPv6 endpoint.

Find your account's home DC by decoding the session's first byte; map to the IPv6
addr (DC1 `2001:b28:f23d:f001::a` · DC2 `2001:67c:4e8:f002::a` ·
DC3 `2001:b28:f23d:f003::a` · DC4 `2001:67c:4e8:f004::a` · DC5 `2001:b28:f23f:f005::a`).

Verify host IPv6 reaches a DC: `python3 -c "import socket;socket.create_connection(('2001:67c:4e8:f002::a',443),5)"`.

## Hardening (matches rgby-prod)

`kelva` user + passwordless sudo · SSH on **2022**, key-only, root login + password
auth disabled · `ufw` allows 2022 only (cron-only needs no inbound) · `fail2ban` on
sshd · `unattended-upgrades` · `Europe/Moscow` tz. SSH is the classic `ssh.service`
(socket activation disabled so `Port` in `sshd_config.d/` takes effect).

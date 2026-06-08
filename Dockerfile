# Kelva Telegram Events Parser — single-container deployment.
FROM python:3.12-slim

# uv for fast, reproducible installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install deps first (layer cache), then source.
COPY pyproject.toml README.md ./
COPY src ./src
RUN uv sync --extra runtime --no-dev

# Bake the channel list in so a standalone `docker run` is self-contained;
# docker-compose still overrides it with a read-only mount for live edits.
COPY channels.yaml ./channels.yaml

# Persisted state (SQLite seen-store) mounted as a volume.
VOLUME ["/data"]
ENV EVENTS_DB_PATH=/data/seen.sqlite3 \
    CHANNELS_CONFIG=/app/channels.yaml \
    PYTHONUNBUFFERED=1

EXPOSE 8080

# Default: the FastAPI host (APScheduler weekly cron + /digest bot, S09).
# One-shot digest instead:  docker run --env-file .env <img> \
#   uv run --extra runtime python -m events_parser --live [--dry-run] [--no-agents]
CMD ["uv", "run", "--extra", "runtime", "uvicorn", \
     "events_parser.app:app", "--host", "0.0.0.0", "--port", "8080"]

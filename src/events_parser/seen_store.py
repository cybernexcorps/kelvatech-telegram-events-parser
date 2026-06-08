"""SeenStore — SQLite-backed dedup of already-reported events.

Keyed by the event's stable `event_hash` (normalized title + date + host), so the
same event posted across multiple channels collapses to one row (intra-run dedup)
and an event reported in a prior week is not re-sent (cross-week dedup).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Event


class SeenStore:
    def __init__(self, db_path: str = ":memory:"):
        # Create the parent directory for file-backed stores so a fresh host (or a
        # not-yet-mounted volume) does not fail with "unable to open database file".
        if db_path != ":memory:":
            parent = Path(db_path).expanduser().parent
            if parent and not parent.exists():
                parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_events (
                event_hash TEXT PRIMARY KEY,
                title      TEXT,
                first_seen TEXT
            )
            """
        )
        self._conn.commit()

    def is_new(self, event_hash: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM seen_events WHERE event_hash = ?", (event_hash,)
        )
        return cur.fetchone() is None

    def mark_seen(self, event: Event) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO seen_events (event_hash, title, first_seen) VALUES (?, ?, ?)",
            (event.event_hash, event.title, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

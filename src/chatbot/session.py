"""SQLite-backed session store for multi-turn conversations."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class Turn:
    """A single conversation turn."""

    question: str
    answer: str
    timestamp: float


class SessionStore:
    """Simple SQLite session store for multi-turn chat.

    Each session is identified by a session_id. Turns are stored as a JSON
    array per session. This is intentionally simple — no TTL, no cleanup.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the sessions table."""
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    turns TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Open a connection, committing/rolling back and closing it on exit.

        sqlite3.Connection's own context manager only handles the
        transaction — it does not close the connection — so we wrap it here
        to avoid leaking connections.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def get_history(self, session_id: str) -> list[Turn]:
        """Retrieve all turns for a session."""
        with self._connect() as conn:
            cursor = conn.execute("SELECT turns FROM sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if not row:
                return []
            turns_data = json.loads(row[0])
            return [Turn(**t) for t in turns_data]

    def add_turn(self, session_id: str, question: str, answer: str) -> None:
        """Add a turn to a session."""
        now = time.time()
        with self._connect() as conn:
            cursor = conn.execute("SELECT turns FROM sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()

            if row:
                turns = json.loads(row[0])
            else:
                turns = []
                conn.execute(
                    "INSERT INTO sessions (session_id, turns, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?)",
                    (session_id, "[]", now, now),
                )

            turns.append(Turn(question=question, answer=answer, timestamp=now).__dict__)
            conn.execute(
                "UPDATE sessions SET turns = ?, updated_at = ? WHERE session_id = ?",
                (json.dumps(turns), now, session_id),
            )

        logger.debug("turn_added", session_id=session_id, turn_count=len(turns))

    def clear_session(self, session_id: str) -> None:
        """Clear all turns for a session."""
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

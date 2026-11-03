from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import sqlite3
from pathlib import Path
from typing import Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self, seed_api_key: str | None = None) -> None:
        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    used_input_tokens INTEGER NOT NULL DEFAULT 0,
                    used_output_tokens INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK (role IN ('user', 'model')),
                    content TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    truncated INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                    ON messages(conversation_id, id);

                CREATE TABLE IF NOT EXISTS api_keys (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    api_key TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            message_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(messages)").fetchall()
            }
            if "truncated" not in message_columns:
                connection.execute(
                    "ALTER TABLE messages ADD COLUMN truncated INTEGER NOT NULL DEFAULT 0"
                )
            if seed_api_key:
                now = utc_now()
                connection.execute(
                    """INSERT OR IGNORE INTO api_keys (id, api_key, created_at, updated_at)
                       VALUES (1, ?, ?, ?)""",
                    (seed_api_key, now, now),
                )

    def get_api_key(self) -> str | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT api_key FROM api_keys WHERE id = 1"
            ).fetchone()
        return str(row["api_key"]) if row else None

    def update_api_key(self, api_key: str) -> str:
        updated_at = utc_now()
        with self.connection() as connection:
            cursor = connection.execute(
                "UPDATE api_keys SET api_key = ?, updated_at = ? WHERE id = 1",
                (api_key, updated_at),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("API key singleton is not initialized")
        return updated_at


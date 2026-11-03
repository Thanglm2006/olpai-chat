from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import sqlite3
from pathlib import Path
from typing import Iterator

from .auth import session_token_hash


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
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_user
                    ON sessions(user_id);

                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
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
            user_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(users)").fetchall()
            }
            if "username" not in user_columns:
                connection.execute("ALTER TABLE users ADD COLUMN username TEXT")
                connection.execute(
                    "UPDATE users SET username = full_name "
                    "WHERE username IS NULL OR trim(username) = ''"
                )
            conversation_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(conversations)").fetchall()
            }
            if "user_id" not in conversation_columns:
                connection.execute(
                    "ALTER TABLE conversations ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE"
                )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversations_user_updated "
                "ON conversations(user_id, updated_at DESC)"
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

    def create_user(self, username: str, email: str, password_hash: str) -> dict:
        now = utc_now()
        with self.connection() as connection:
            cursor = connection.execute(
                """INSERT INTO users (username, full_name, email, password_hash, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (username, username, email, password_hash, now),
            )
            row = connection.execute(
                "SELECT id, username, email, created_at FROM users WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        return dict(row)

    def get_user_by_email(self, email: str) -> dict | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE lower(email) = lower(?)", (email,)
            ).fetchone()
        return dict(row) if row else None

    def get_user_by_identifier(self, identifier: str) -> dict | None:
        with self.connection() as connection:
            row = connection.execute(
                """SELECT * FROM users
                   WHERE lower(username) = lower(?) OR lower(email) = lower(?)""",
                (identifier, identifier),
            ).fetchone()
        return dict(row) if row else None

    def create_session(self, token: str, user_id: int, expires_at: str) -> None:
        with self.connection() as connection:
            connection.execute(
                """INSERT INTO sessions (token_hash, user_id, expires_at, created_at)
                   VALUES (?, ?, ?, ?)""",
                (session_token_hash(token), user_id, expires_at, utc_now()),
            )

    def get_user_by_session(self, token: str | None) -> dict | None:
        if not token:
            return None
        with self.connection() as connection:
            row = connection.execute(
                """SELECT u.id, u.username, u.email, u.created_at
                   FROM sessions s
                   JOIN users u ON u.id = s.user_id
                   WHERE s.token_hash = ? AND s.expires_at > ?""",
                (session_token_hash(token), utc_now()),
            ).fetchone()
        return dict(row) if row else None

    def delete_session(self, token: str | None) -> None:
        if not token:
            return
        with self.connection() as connection:
            connection.execute(
                "DELETE FROM sessions WHERE token_hash = ?",
                (session_token_hash(token),),
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


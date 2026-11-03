from __future__ import annotations

from collections import defaultdict
import re
from threading import BoundedSemaphore, Lock
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status

from .config import Settings
from .db import Database, utc_now
from .gemini import GeminiService


class ChatService:
    def __init__(self, database: Database, gemini: GeminiService, settings: Settings) -> None:
        self.database = database
        self.gemini = gemini
        self.settings = settings
        self._locks: defaultdict[str, Lock] = defaultdict(Lock)
        self._chat_slots = BoundedSemaphore(settings.max_concurrent_chats)

    def _get_conversation(
        self, conversation_id: str, user_id: int | None = None
    ) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            query = "SELECT * FROM conversations WHERE id = ?"
            params: list[Any] = [conversation_id]
            if user_id is not None:
                query += " AND user_id = ?"
                params.append(user_id)
            row = connection.execute(
                query, params
            ).fetchone()
            return dict(row) if row else None

    def _get_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id",
                (conversation_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def create_conversation(
        self, title: str = "New conversation", user_id: int | None = None
    ) -> dict[str, Any]:
        conversation_id = str(uuid4())
        now = utc_now()
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO conversations (id, user_id, title, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (conversation_id, user_id, title.strip() or "New conversation", now, now),
            )
        return self.get_conversation(conversation_id, user_id)

    def list_conversations(self, user_id: int | None = None) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            query = "SELECT * FROM conversations"
            params: list[Any] = []
            if user_id is not None:
                query += " WHERE user_id = ?"
                params.append(user_id)
            query += " ORDER BY updated_at DESC"
            rows = connection.execute(
                query, params
            ).fetchall()
        return [self._format_conversation(dict(row), []) for row in rows]

    def get_conversation(self, conversation_id: str, user_id: int | None = None) -> dict[str, Any]:
        conversation = self._get_conversation(conversation_id, user_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return self._format_conversation(conversation, self._get_messages(conversation_id))

    @staticmethod
    def _automatic_title(user_message: str) -> str:
        cleaned = re.sub(r"```(?:python|py)?", "", user_message, flags=re.IGNORECASE)
        cleaned = " ".join(cleaned.split()).strip()
        if not cleaned:
            return "New conversation"
        return f"{cleaned[:77]}..." if len(cleaned) > 80 else cleaned

    def rename_conversation(
        self, conversation_id: str, title: str, user_id: int | None = None
    ) -> dict[str, Any]:
        title = title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="Conversation title cannot be empty")
        lock = self._locks[conversation_id]
        with lock:
            if self._get_conversation(conversation_id, user_id) is None:
                raise HTTPException(status_code=404, detail="Conversation not found")
            with self.database.connection() as connection:
                connection.execute(
                    "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?"
                    + (" AND user_id = ?" if user_id is not None else ""),
                    (title, utc_now(), conversation_id)
                    if user_id is None
                    else (title, utc_now(), conversation_id, user_id),
                )
        return self.get_conversation(conversation_id, user_id)

    def delete_conversation(self, conversation_id: str, user_id: int | None = None) -> None:
        with self.database.connection() as connection:
            query = "DELETE FROM conversations WHERE id = ?"
            params: list[Any] = [conversation_id]
            if user_id is not None:
                query += " AND user_id = ?"
                params.append(user_id)
            cursor = connection.execute(
                query, params
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Conversation not found")

    def clear_conversation(
        self, conversation_id: str, user_id: int | None = None
    ) -> dict[str, Any]:
        lock = self._locks[conversation_id]
        with lock:
            if self._get_conversation(conversation_id, user_id) is None:
                raise HTTPException(status_code=404, detail="Conversation not found")
            now = utc_now()
            with self.database.connection() as connection:
                connection.execute(
                    "DELETE FROM messages WHERE conversation_id = ?", (conversation_id,)
                )
                connection.execute(
                    """UPDATE conversations
                       SET used_input_tokens = 0, used_output_tokens = 0, updated_at = ?
                       WHERE id = ?""",
                    (now, conversation_id),
                )
        return self.get_conversation(conversation_id, user_id)

    def add_message(
        self, conversation_id: str, user_message: str, user_id: int | None = None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        lock = self._locks[conversation_id]
        with lock:
            conversation = self._get_conversation(conversation_id, user_id)
            if conversation is None:
                raise HTTPException(status_code=404, detail="Conversation not found")

            old_messages = self._get_messages(conversation_id)
            if not old_messages and conversation["title"] == "New conversation":
                automatic_title = self._automatic_title(user_message)
                with self.database.connection() as connection:
                    connection.execute(
                        "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                        (automatic_title, utc_now(), conversation_id),
                    )
                conversation["title"] = automatic_title
            model_messages = [
                {"role": item["role"], "content": item["content"]}
                for item in old_messages
            ]
            model_messages.append({"role": "user", "content": user_message})

            self._chat_slots.acquire()
            try:
                input_tokens = self.gemini.count_input_tokens(model_messages)
                used_tokens = conversation["used_input_tokens"] + conversation["used_output_tokens"]
                remaining = self.settings.max_conversation_tokens - used_tokens
                if input_tokens >= remaining:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={
                            "message": "Conversation token budget exhausted before generation",
                            "remaining_tokens": max(remaining, 0),
                            "required_input_tokens": input_tokens,
                        },
                    )

                answer, _provider_input_tokens, output_tokens, truncated = self.gemini.generate(
                    model_messages,
                    max_output_tokens=remaining - input_tokens,
                )
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"Gemini API error: {exc}") from exc
            finally:
                self._chat_slots.release()

            # Use the count from the response when available, but never allow a bad
            # provider usage value to make the local budget negative.
            # The fixed system instruction is outside the per-conversation budget.
            # Count only the conversation contents here, not provider prompt metadata.
            actual_input = input_tokens
            total_added = actual_input + output_tokens
            if used_tokens + total_added > self.settings.max_conversation_tokens:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Gemini response exceeded the configured conversation budget",
                )

            now = utc_now()
            with self.database.connection() as connection:
                user_row = connection.execute(
                    """INSERT INTO messages
                       (conversation_id, role, content, input_tokens, output_tokens, truncated, created_at)
                       VALUES (?, 'user', ?, ?, 0, 0, ?) RETURNING *""",
                    (conversation_id, user_message, actual_input, now),
                ).fetchone()
                assistant_row = connection.execute(
                    """INSERT INTO messages
                       (conversation_id, role, content, input_tokens, output_tokens, truncated, created_at)
                       VALUES (?, 'model', ?, 0, ?, ?, ?) RETURNING *""",
                    (conversation_id, answer, output_tokens, int(truncated), now),
                ).fetchone()
                connection.execute(
                    """UPDATE conversations SET
                       used_input_tokens = used_input_tokens + ?,
                       used_output_tokens = used_output_tokens + ?,
                       updated_at = ? WHERE id = ?""",
                    (actual_input, output_tokens, now, conversation_id),
                )

            return dict(user_row), dict(assistant_row)

    def _format_conversation(
        self, conversation: dict[str, Any], messages: list[dict[str, Any]]
    ) -> dict[str, Any]:
        used = conversation["used_input_tokens"] + conversation["used_output_tokens"]
        return {
            **{key: value for key, value in conversation.items() if key != "user_id"},
            "used_tokens": used,
            "budget_tokens": self.settings.max_conversation_tokens,
            "remaining_tokens": max(self.settings.max_conversation_tokens - used, 0),
            "messages": messages,
        }


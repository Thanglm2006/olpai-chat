from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi import HTTPException

from app.auth import hash_password, verify_password
from app.config import Settings
from app.db import Database
from app.schemas import LoginRequest
from app.service import ChatService


class FakeGemini:
    def count_input_tokens(self, messages):
        return sum(len(item["content"].split()) for item in messages)

    def generate(self, messages, max_output_tokens):
        return "ok", self.count_input_tokens(messages), 1, False


class AuthStorageTest(unittest.TestCase):
    def test_passwords_and_sessions_are_stored_safely(self):
        with TemporaryDirectory() as directory:
            database = Database(Path(directory) / "auth.db")
            database.initialize()
            user = database.create_user(
                "Thi sinh A", "a@example.com", hash_password("password123")
            )

            stored = database.get_user_by_email("A@EXAMPLE.COM")
            self.assertIsNotNone(stored)
            self.assertNotEqual(stored["password_hash"], "password123")
            self.assertTrue(verify_password("password123", stored["password_hash"]))
            self.assertFalse(verify_password("wrongpass", stored["password_hash"]))
            self.assertEqual(
                database.get_user_by_identifier("thi sinh a")["id"], user["id"]
            )
            self.assertEqual(
                database.get_user_by_identifier("A@EXAMPLE.COM")["id"], user["id"]
            )

            token = "session-token"
            database.create_session(
                token,
                user["id"],
                (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            )
            self.assertEqual(database.get_user_by_session(token)["id"], user["id"])
            database.delete_session(token)
            self.assertIsNone(database.get_user_by_session(token))

    def test_login_request_has_only_identifier_and_password(self):
        payload = LoginRequest(identifier="a@example.com", password="password123")
        self.assertEqual(payload.identifier, "a@example.com")
        with self.assertRaises(ValueError):
            LoginRequest(
                identifier="a@example.com",
                password="password123",
                email="a@example.com",
            )

    def test_conversations_are_isolated_by_user(self):
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "auth.db"
            database = Database(database_path)
            database.initialize()
            settings = Settings(
                gemini_api_key="test-key",
                gemini_model="test-model",
                max_conversation_tokens=20,
                database_path=database_path,
                host="127.0.0.1",
                port=8000,
            )
            service = ChatService(database, FakeGemini(), settings)
            first_user = database.create_user("Thi sinh A", "a@example.com", "hash-a")
            second_user = database.create_user("Thi sinh B", "b@example.com", "hash-b")
            first = service.create_conversation(user_id=first_user["id"])
            second = service.create_conversation(user_id=second_user["id"])

            self.assertEqual(
                [item["id"] for item in service.list_conversations(first_user["id"])],
                [first["id"]],
            )
            with self.assertRaises(HTTPException) as error:
                service.get_conversation(second["id"], first_user["id"])
            self.assertEqual(error.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import sleep
import unittest

from fastapi import HTTPException

from app.config import Settings
from app.db import Database
from app.service import ChatService


class FakeGemini:
    def count_input_tokens(self, messages):
        return sum(len(item["content"].split()) for item in messages)

    def generate(self, messages, max_output_tokens):
        # Simulates a provider that obeys max_output_tokens exactly.
        output_tokens = max_output_tokens
        return "x " * output_tokens, self.count_input_tokens(messages), output_tokens, False


class ConcurrentFakeGemini(FakeGemini):
    def __init__(self):
        self.active = 0
        self.max_active = 0
        self.lock = Lock()

    def generate(self, messages, max_output_tokens):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        sleep(0.03)
        with self.lock:
            self.active -= 1
        return "ok", self.count_input_tokens(messages), 1, False


class TruncatedFakeGemini(FakeGemini):
    def generate(self, messages, max_output_tokens):
        return "partial response", self.count_input_tokens(messages), max_output_tokens, True


class ConversationBudgetTest(unittest.TestCase):
    def make_service(self, directory: str) -> ChatService:
        database_path = Path(directory) / "test.db"
        database = Database(database_path)
        database.initialize()
        settings = Settings(
            gemini_api_key="test-key",
            gemini_model="gemini-3.5-flash-lite",
            max_conversation_tokens=10,
            database_path=database_path,
            host="127.0.0.1",
            port=8000,
        )
        return ChatService(database, FakeGemini(), settings)

    def test_output_is_capped_and_next_request_is_rejected(self):
        with TemporaryDirectory() as directory:
            service = self.make_service(directory)
            conversation = service.create_conversation()

            _, answer = service.add_message(conversation["id"], "hello")
            state = service.get_conversation(conversation["id"])

            self.assertEqual(answer["output_tokens"], 9)
            self.assertEqual(state["used_tokens"], 10)
            self.assertEqual(state["remaining_tokens"], 0)

            with self.assertRaises(HTTPException) as error:
                service.add_message(conversation["id"], "again")
            self.assertEqual(error.exception.status_code, 429)
            self.assertEqual(len(service.get_conversation(conversation["id"])["messages"]), 2)

    def test_conversation_budgets_are_independent(self):
        with TemporaryDirectory() as directory:
            service = self.make_service(directory)
            first = service.create_conversation()
            second = service.create_conversation()

            service.add_message(first["id"], "hello")
            second_state = service.get_conversation(second["id"])

            self.assertEqual(first["id"] != second["id"], True)
            self.assertEqual(second_state["used_tokens"], 0)
            service.add_message(second["id"], "world")
            self.assertEqual(len(service.get_conversation(second["id"])["messages"]), 2)

    def test_concurrent_chat_limit_is_enforced(self):
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "test.db"
            database = Database(database_path)
            database.initialize()
            fake_gemini = ConcurrentFakeGemini()
            settings = Settings(
                gemini_api_key="test-key",
                gemini_model="gemini-3.5-flash-lite",
                max_conversation_tokens=100,
                database_path=database_path,
                host="127.0.0.1",
                port=8000,
                max_concurrent_chats=2,
            )
            service = ChatService(database, fake_gemini, settings)
            conversations = [service.create_conversation() for _ in range(8)]

            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = [
                    executor.submit(service.add_message, conversation["id"], "hello")
                    for conversation in conversations
                ]
                for future in futures:
                    future.result()

            self.assertLessEqual(fake_gemini.max_active, 2)
            self.assertGreater(fake_gemini.max_active, 1)

    def test_truncated_response_is_saved_with_notice_flag(self):
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "test.db"
            database = Database(database_path)
            database.initialize()
            settings = Settings(
                gemini_api_key="test-key",
                gemini_model="gemini-3.5-flash-lite",
                max_conversation_tokens=10,
                database_path=database_path,
                host="127.0.0.1",
                port=8000,
            )
            service = ChatService(database, TruncatedFakeGemini(), settings)
            conversation = service.create_conversation()

            _, answer = service.add_message(conversation["id"], "hello")

            self.assertTrue(answer["truncated"])
            self.assertTrue(service.get_conversation(conversation["id"])["messages"][1]["truncated"])


if __name__ == "__main__":
    unittest.main()


from __future__ import annotations

from threading import RLock
from typing import Any

from google import genai
from google.genai import types


class GeminiService:
    def __init__(self, api_key: str, model: str) -> None:
        self.model = model
        self._client_lock = RLock()
        self.client = genai.Client(api_key=api_key)

    def update_api_key(self, api_key: str) -> None:
        with self._client_lock:
            self.client = genai.Client(api_key=api_key)

    @staticmethod
    def _contents(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {"role": item["role"], "parts": [{"text": item["content"]}]}
            for item in messages
        ]

    def count_input_tokens(self, messages: list[dict[str, Any]]) -> int:
        if not messages:
            return 0
        with self._client_lock:
            result = self.client.models.count_tokens(
                model=self.model,
                contents=self._contents(messages),
            )
        return int(result.total_tokens or 0)

    def generate(
        self,
        messages: list[dict[str, Any]],
        max_output_tokens: int,
    ) -> tuple[str, int, int]:
        with self._client_lock:
            response = self.client.models.generate_content(
                model=self.model,
                contents=self._contents(messages),
                config=types.GenerateContentConfig(
                    max_output_tokens=max_output_tokens,
                ),
            )
        text = (response.text or "").strip()
        if not text:
            raise RuntimeError("Gemini returned an empty response")

        usage = response.usage_metadata
        input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
        output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)

        # Some API responses omit usage metadata. Count the generated text as a fallback.
        if input_tokens == 0:
            input_tokens = self.count_input_tokens(messages)
        if output_tokens == 0:
            output_tokens = self.count_input_tokens(
                [{"role": "model", "content": text}]
            )
        return text, input_tokens, output_tokens


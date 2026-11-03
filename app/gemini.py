from __future__ import annotations

from threading import RLock
from typing import Any

from google import genai
from google.genai import types


class GeminiService:
    def __init__(self, api_key: str, model: str, system_instruction: str) -> None:
        self.model = model
        self.system_instruction = system_instruction
        self._client_lock = RLock()
        self.client = genai.Client(api_key=api_key)

    def update_api_key(self, api_key: str) -> None:
        with self._client_lock:
            self.client = genai.Client(api_key=api_key)

    def _get_client(self) -> genai.Client:
        with self._client_lock:
            return self.client

    @staticmethod
    def _contents(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {"role": item["role"], "parts": [{"text": item["content"]}]}
            for item in messages
        ]

    @staticmethod
    def _was_truncated(response: Any) -> bool:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return False
        reason = getattr(candidates[0], "finish_reason", None)
        if reason is None:
            return False
        value = getattr(reason, "value", reason)
        return str(value).upper().endswith("MAX_TOKENS") or str(reason).upper().endswith("MAX_TOKENS")

    def count_input_tokens(self, messages: list[dict[str, Any]]) -> int:
        if not messages:
            return 0
        client = self._get_client()
        result = client.models.count_tokens(
            model=self.model,
            contents=self._contents(messages),
        )
        return int(result.total_tokens or 0)

    def generate(
        self,
        messages: list[dict[str, Any]],
        max_output_tokens: int,
    ) -> tuple[str, int, int, bool]:
        client = self._get_client()
        response = client.models.generate_content(
            model=self.model,
            contents=self._contents(messages),
            config=types.GenerateContentConfig(
                max_output_tokens=max_output_tokens,
                system_instruction=self.system_instruction,
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
        return text, input_tokens, output_tokens, self._was_truncated(response)


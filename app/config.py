from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_SYSTEM_INSTRUCTION = """You are OLP AI, an AI assistant for OLP AI problems.
Your role is to answer questions clearly and help users design, write, explain, review, and debug code for OLP AI tasks.
Respond in Vietnamese by default unless the user asks for another language.
Prefer practical, correct, and concise answers. When providing code, first give only a brief explanation of the approach and key complexity or edge cases, then provide the code. Do not give a long tutorial unless the user asks for one.
When the user explicitly asks for code only or says not to explain, return only valid Python source code with no prose and no Markdown fences. Otherwise, put every Python code block in its own ```python fenced block so it can be rendered separately.
Do not claim to have executed code or accessed data that you have not actually accessed."""


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    gemini_model: str
    max_conversation_tokens: int
    database_path: Path
    host: str
    port: int
    api_key_update_password: str = ""
    system_instruction: str = DEFAULT_SYSTEM_INSTRUCTION
    max_concurrent_chats: int = 6
    session_ttl_hours: int = 168
    secure_cookies: bool = False


def get_settings() -> Settings:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required in .env")

    database_path = Path(os.getenv("DATABASE_PATH", "./chatbot.db"))
    if not database_path.is_absolute():
        database_path = PROJECT_ROOT / database_path

    return Settings(
        gemini_api_key=api_key,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip(),
        max_conversation_tokens=int(os.getenv("MAX_CONVERSATION_TOKENS", "2000")),
        database_path=database_path,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        api_key_update_password=os.getenv("API_KEY_UPDATE_PASSWORD", "").strip(),
        system_instruction=(
            os.getenv("AI_SYSTEM_INSTRUCTION", DEFAULT_SYSTEM_INSTRUCTION).strip()
            or DEFAULT_SYSTEM_INSTRUCTION
        ),
        max_concurrent_chats=max(1, int(os.getenv("MAX_CONCURRENT_CHATS", "6"))),
        session_ttl_hours=max(1, int(os.getenv("SESSION_TTL_HOURS", "168"))),
        secure_cookies=os.getenv("SECURE_COOKIES", "false").strip().lower()
        in {"1", "true", "yes", "on"},
    )


settings = get_settings()


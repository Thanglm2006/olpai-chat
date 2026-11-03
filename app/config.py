from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    gemini_model: str
    max_conversation_tokens: int
    database_path: Path
    host: str
    port: int
    api_key_update_password: str = ""


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
    )


settings = get_settings()


from __future__ import annotations

from contextlib import asynccontextmanager
import hmac
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, status
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, JSONResponse

from .config import settings
from .db import Database
from .gemini import GeminiService
from .schemas import (
    ChatRequest,
    ChatResponse,
    ConversationResponse,
    CreateConversationRequest,
    ApiKeyUpdateRequest,
    ApiKeyUpdateResponse,
    MessageRequest,
    MessageResponse,
)
from .service import ChatService


database = Database(settings.database_path)
gemini = GeminiService(
    settings.gemini_api_key,
    settings.gemini_model,
    settings.system_instruction,
)
chat_service = ChatService(database, gemini, settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.initialize(settings.gemini_api_key)
    stored_api_key = database.get_api_key()
    if stored_api_key:
        gemini.update_api_key(stored_api_key)
    yield


app = FastAPI(
    title="Gemini Chatbot API",
    version="1.0.0",
    description="Chat API with a cumulative 2,000-token input/output budget per conversation.",
    lifespan=lifespan,
)


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/api-docs", include_in_schema=False)
def api_docs():
    return get_swagger_ui_html(
        openapi_url="/api-docs/openapi.json",
        title="Gemini Chatbot API Docs",
    )


@app.get("/api-docs/openapi.json", include_in_schema=False)
def api_docs_openapi():
    return JSONResponse(app.openapi())


@app.get("/health")
def health() -> dict[str, str | int]:
    return {"status": "ok", "model": settings.gemini_model, "budget_tokens": settings.max_conversation_tokens}


@app.post("/api/v1/conversations", response_model=ConversationResponse, status_code=201)
def create_conversation(payload: CreateConversationRequest):
    return chat_service.create_conversation(payload.title)


@app.get("/api/v1/conversations", response_model=list[ConversationResponse])
def list_conversations():
    return chat_service.list_conversations()


@app.get("/api/v1/conversations/{conversation_id}", response_model=ConversationResponse)
def get_conversation(conversation_id: UUID):
    return chat_service.get_conversation(str(conversation_id))


@app.delete("/api/v1/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: UUID):
    chat_service.delete_conversation(str(conversation_id))


@app.delete("/api/v1/conversations/{conversation_id}/messages", response_model=ConversationResponse)
def clear_conversation(conversation_id: UUID):
    return chat_service.clear_conversation(str(conversation_id))


@app.get("/api/v1/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
def list_messages(conversation_id: UUID):
    conversation = chat_service.get_conversation(str(conversation_id))
    return conversation["messages"]


@app.post("/api/v1/conversations/{conversation_id}/messages", response_model=ChatResponse)
def send_message(conversation_id: UUID, payload: MessageRequest):
    user_message, assistant_message = chat_service.add_message(
        str(conversation_id), payload.message
    )
    return {"conversation": chat_service.get_conversation(str(conversation_id)), "message": assistant_message}


@app.post("/api/v1/chat", response_model=ChatResponse)
def chat(payload: ChatRequest):
    conversation_id = payload.conversation_id
    if conversation_id is None:
        conversation = chat_service.create_conversation()
        conversation_id = conversation["id"]
    user_message, assistant_message = chat_service.add_message(str(conversation_id), payload.message)
    return {"conversation": chat_service.get_conversation(str(conversation_id)), "message": assistant_message}


@app.get("/api/v1/config")
def public_config() -> dict[str, str | int]:
    return {"model": settings.gemini_model, "budget_tokens": settings.max_conversation_tokens}


def _mask_api_key(api_key: str) -> str:
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}...{api_key[-4:]}"


@app.put("/api/v1/settings/api-key", response_model=ApiKeyUpdateResponse)
def update_api_key(
    payload: ApiKeyUpdateRequest,
    x_api_key_password: str | None = Header(default=None, alias="X-API-Key-Password"),
):
    configured_password = settings.api_key_update_password
    if not configured_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API_KEY_UPDATE_PASSWORD is not configured",
        )
    if not x_api_key_password or not hmac.compare_digest(
        x_api_key_password, configured_password
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid update password")

    new_api_key = payload.api_key.get_secret_value().strip()
    if not new_api_key:
        raise HTTPException(status_code=422, detail="api_key cannot be empty")

    updated_at = database.update_api_key(new_api_key)
    gemini.update_api_key(new_api_key)
    return {
        "configured": True,
        "masked_api_key": _mask_api_key(new_api_key),
        "updated_at": updated_at,
    }


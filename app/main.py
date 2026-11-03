from __future__ import annotations

from contextlib import asynccontextmanager
import hmac
from pathlib import Path
import re
import sqlite3
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .auth import (
    SESSION_COOKIE_NAME,
    hash_password,
    new_session_token,
    session_expiry,
    verify_password,
)
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
    RenameConversationRequest,
    LoginRequest,
    RegisterRequest,
    UserResponse,
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

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


def require_user(request: Request) -> dict:
    user = database.get_user_by_session(request.cookies.get(SESSION_COOKIE_NAME))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Vui lòng đăng nhập để sử dụng phòng chat",
        )
    return user


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=settings.session_ttl_hours * 60 * 60,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


def _normalise_email(email: str) -> str:
    return email.strip().lower()


def _validate_email(email: str) -> str:
    normalised = _normalise_email(email)
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalised):
        raise HTTPException(status_code=422, detail="Email không hợp lệ")
    return normalised


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(static_dir / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(static_dir / "assets" / "logo.jpg", media_type="image/jpeg")


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
    return {
        "status": "ok",
        "model": settings.gemini_model,
        "budget_tokens": settings.max_conversation_tokens,
        "max_concurrent_chats": settings.max_concurrent_chats,
    }


@app.post("/api/v1/auth/register", response_model=UserResponse, status_code=201)
def register(payload: RegisterRequest, response: Response):
    email = _validate_email(payload.email)
    username = " ".join(payload.username.split())
    if len(username) < 2:
        raise HTTPException(status_code=422, detail="Tên tài khoản không hợp lệ")
    try:
        user = database.create_user(
            username,
            email,
            hash_password(payload.password.get_secret_value()),
        )
    except sqlite3.IntegrityError as exc:
        if "users.email" not in str(exc):
            raise
        raise HTTPException(status_code=409, detail="Email này đã được đăng ký") from exc

    token = new_session_token()
    database.create_session(token, user["id"], session_expiry(settings.session_ttl_hours))
    _set_session_cookie(response, token)
    return user


@app.post("/api/v1/auth/login", response_model=UserResponse)
def login(payload: LoginRequest, response: Response):
    identifier = payload.identifier.strip()
    if not identifier:
        raise HTTPException(status_code=422, detail="Tên đăng nhập/email không được để trống")
    user = database.get_user_by_identifier(identifier)
    if user is None or not verify_password(
        payload.password.get_secret_value(), user["password_hash"]
    ):
        raise HTTPException(
            status_code=401,
            detail="Tên đăng nhập/email hoặc mật khẩu không đúng",
        )

    token = new_session_token()
    database.create_session(token, user["id"], session_expiry(settings.session_ttl_hours))
    _set_session_cookie(response, token)
    return {key: user[key] for key in ("id", "username", "email", "created_at")}


@app.post("/api/v1/auth/logout", status_code=204)
def logout(request: Request, response: Response):
    database.delete_session(request.cookies.get(SESSION_COOKIE_NAME))
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


@app.get("/api/v1/auth/me", response_model=UserResponse)
def current_user(user: dict = Depends(require_user)):
    return user


@app.post("/api/v1/conversations", response_model=ConversationResponse, status_code=201)
def create_conversation(payload: CreateConversationRequest, user: dict = Depends(require_user)):
    return chat_service.create_conversation(payload.title, user["id"])


@app.get("/api/v1/conversations", response_model=list[ConversationResponse])
def list_conversations(user: dict = Depends(require_user)):
    return chat_service.list_conversations(user["id"])


@app.get("/api/v1/conversations/{conversation_id}", response_model=ConversationResponse)
def get_conversation(conversation_id: UUID, user: dict = Depends(require_user)):
    return chat_service.get_conversation(str(conversation_id), user["id"])


@app.patch("/api/v1/conversations/{conversation_id}", response_model=ConversationResponse)
def rename_conversation(
    conversation_id: UUID,
    payload: RenameConversationRequest,
    user: dict = Depends(require_user),
):
    return chat_service.rename_conversation(str(conversation_id), payload.title, user["id"])


@app.delete("/api/v1/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: UUID, user: dict = Depends(require_user)):
    chat_service.delete_conversation(str(conversation_id), user["id"])


@app.delete("/api/v1/conversations/{conversation_id}/messages", response_model=ConversationResponse)
def clear_conversation(conversation_id: UUID, user: dict = Depends(require_user)):
    return chat_service.clear_conversation(str(conversation_id), user["id"])


@app.get("/api/v1/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
def list_messages(conversation_id: UUID, user: dict = Depends(require_user)):
    conversation = chat_service.get_conversation(str(conversation_id), user["id"])
    return conversation["messages"]


@app.post("/api/v1/conversations/{conversation_id}/messages", response_model=ChatResponse)
def send_message(
    conversation_id: UUID,
    payload: MessageRequest,
    user: dict = Depends(require_user),
):
    user_message, assistant_message = chat_service.add_message(
        str(conversation_id), payload.message, user["id"]
    )
    return {
        "conversation": chat_service.get_conversation(str(conversation_id), user["id"]),
        "message": assistant_message,
    }


@app.post("/api/v1/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, user: dict = Depends(require_user)):
    conversation_id = payload.conversation_id
    if conversation_id is None:
        conversation = chat_service.create_conversation(user_id=user["id"])
        conversation_id = conversation["id"]
    user_message, assistant_message = chat_service.add_message(
        str(conversation_id), payload.message, user["id"]
    )
    return {
        "conversation": chat_service.get_conversation(str(conversation_id), user["id"]),
        "message": assistant_message,
    }


@app.get("/api/v1/config")
def public_config() -> dict[str, str | int]:
    return {
        "model": settings.gemini_model,
        "budget_tokens": settings.max_conversation_tokens,
        "max_concurrent_chats": settings.max_concurrent_chats,
    }


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


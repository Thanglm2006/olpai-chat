from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class CreateConversationRequest(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=120)


class RenameConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class ChatRequest(BaseModel):
    conversation_id: Optional[UUID] = None
    message: str = Field(min_length=1, max_length=100_000)


class MessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=100_000)


class ApiKeyUpdateRequest(BaseModel):
    api_key: SecretStr = Field(min_length=1, max_length=1000)


class ApiKeyUpdateResponse(BaseModel):
    configured: bool
    masked_api_key: str
    updated_at: datetime


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=254)
    password: SecretStr = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: str = Field(min_length=2, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    input_tokens: int
    output_tokens: int
    truncated: bool = False
    created_at: datetime


class ConversationResponse(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    used_input_tokens: int
    used_output_tokens: int
    used_tokens: int
    budget_tokens: int
    remaining_tokens: int
    messages: list[MessageResponse] = Field(default_factory=list)


class ChatResponse(BaseModel):
    conversation: ConversationResponse
    message: MessageResponse


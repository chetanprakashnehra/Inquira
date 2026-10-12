from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
)


# ============================================================
# USER SCHEMAS
# ============================================================

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str | None
    is_active: bool

    model_config = ConfigDict(
        from_attributes=True
    )


# ============================================================
# LOGIN
# ============================================================

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ============================================================
# KNOWLEDGE BASE
# ============================================================

class KnowledgeBaseCreate(BaseModel):
    name: str
    description: str | None = None


class KnowledgeBaseResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )
class ChatRequest(BaseModel):
    knowledge_base_id: UUID
    question: str


class CitationResponse(BaseModel):
    id: int
    source: str | None = None
    page: int | None = None
    chunk_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[CitationResponse]
    supported: bool
    retry_count: int
class ChatSessionCreate(BaseModel):
    knowledge_base_id: UUID
    title: str | None = None


class ChatSessionResponse(BaseModel):
    id: UUID
    knowledge_base_id: UUID
    title: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatMessageResponse(BaseModel):
    id: UUID
    session_id: UUID
    role: str
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatRequest(BaseModel):
    session_id: UUID
    question: str
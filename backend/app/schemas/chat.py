import uuid
from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, Field, ConfigDict


class Citation(BaseModel):
    document_id: Optional[str] = None
    document_name: str
    page_number: Optional[int] = None
    chunk_index: int
    content: str
    relevance_score: Optional[float] = None


class ChatSessionCreate(BaseModel):
    knowledge_base_id: uuid.UUID
    title: Optional[str] = "New Conversation"


class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    user_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    citations: Optional[List[Citation]] = None
    created_at: datetime


class ChatQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User question / prompt")
    stream: bool = Field(True, description="Whether to stream response via SSE")
